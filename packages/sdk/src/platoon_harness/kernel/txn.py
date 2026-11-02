"""Txn: what an op receives, and the envelope it cannot touch."""

import json
import re
import sqlite3
from collections.abc import Callable, Iterable, Mapping
from typing import Any, Literal, NoReturn

from .journal import head, insert, stream_version
from .model import (
    DATA_LIMIT,
    GIST_LIMIT,
    Event,
    ModelRef,
    Outcome,
    Principal,
    RefusalCode,
    Refused,
    canonical,
    jsonable,
)
from .naming import check_event_type
from .view import View, fold

_STREAM = re.compile(r"[^\s@#]+")
_REF = re.compile(r"(?P<stream>[^\s@#]+)@(?P<version>\d+)(#\S+)?")
_BODY_REF = re.compile(r"sha256:(?P<sha256>[0-9a-f]{64})")


class Commands(View):
    """The answer to each keyed command, so a retry receives the first one."""

    _folds_outcomes = True
    schema = """
    CREATE TABLE v_commands(
        actor TEXT NOT NULL,
        key TEXT NOT NULL,
        op TEXT NOT NULL,
        args_hash TEXT NOT NULL,
        outcome TEXT NOT NULL,
        seq INTEGER NOT NULL,
        PRIMARY KEY (actor, key)
    ) WITHOUT ROWID, STRICT;
    """

    @fold("*")
    def recorded(self, event: Event) -> None:
        outcome = event.outcome
        if outcome is not None and outcome.key is not None:
            self.db.execute(
                "INSERT OR IGNORE INTO v_commands VALUES (?, ?, ?, ?, ?, ?)",
                (
                    event.actor,
                    outcome.key,
                    outcome.op,
                    outcome.args_hash,
                    outcome.model_dump_json(exclude={"seq"}),
                    event.seq,
                ),
            )

    def get(self, actor: str, key: str) -> Outcome | None:
        row = self.db.execute(
            "SELECT outcome, seq FROM v_commands WHERE actor = ? AND key = ?", (actor, key)
        ).fetchone()
        return (
            None if row is None else Outcome.model_validate_json(row["outcome"]).model_copy(update={"seq": row["seq"]})
        )


class Stamps(View):
    """The open turn of each agent and the open episode, for stamping the envelope."""

    schema = "CREATE TABLE v_stamps(scope TEXT PRIMARY KEY, value TEXT NOT NULL) WITHOUT ROWID, STRICT;"

    def _scope(self, event: Event) -> str:
        return "episode" if event.type.startswith("episode.") else f"turn/{event.agent}"

    @fold("turn.started", "episode.opened")
    def opened(self, event: Event) -> None:
        value = event.turn if event.type == "turn.started" else event.episode
        self.db.execute("INSERT OR REPLACE INTO v_stamps VALUES (?, ?)", (self._scope(event), value))

    @fold("turn.ended", "turn.lost", "episode.closed")
    def closed(self, event: Event) -> None:
        self.db.execute("DELETE FROM v_stamps WHERE scope = ?", (self._scope(event),))

    def _get(self, scope: str) -> str | None:
        row = self.db.execute("SELECT value FROM v_stamps WHERE scope = ?", (scope,)).fetchone()
        return None if row is None else row["value"]

    def turn(self, agent: str | None) -> str | None:
        return None if agent is None else self._get(f"turn/{agent}")

    def episode(self) -> str | None:
        return self._get("episode")


class Txn:
    """What an op receives, and all an op receives. Fixed for one command: `me` and `now`."""

    __slots__ = ("_apply", "_db", "_held", "me", "now")

    def __init__(self, db: sqlite3.Connection, me: Principal, now: float, apply: Callable[[Event], None] | None = None):
        self._db = db
        self._apply = apply
        self._held: tuple[Event, str] | None = None
        self.me = me
        self.now = now

    def view[V: View](self, view: type[V]) -> V:
        """Read a view inside this transaction."""
        return view(self._db)

    def emit(
        self,
        type: str,
        stream: str,
        *,
        gist: str,
        data: Any = None,
        agent: str | None = None,
        cause: Iterable[int] = (),
        based_on: Iterable[str] = (),
        refs: Iterable[str] = (),
        correlation: str | None = None,
        native: Mapping[str, str] | None = None,
        model: ModelRef | None = None,
        v: int = 1,
    ) -> Event:
        """Append one event and run its folds. `refs` are the refs held in `data`."""
        if self._apply is None:
            raise Refused("unsupported", "a query cannot emit")
        self._flush()
        check_event_type(type)
        if _STREAM.fullmatch(stream) is None:
            raise Refused("invalid", f"bad stream name: {stream!r}")
        if len(gist) > GIST_LIMIT:
            raise Refused("invalid", f"gist exceeds {GIST_LIMIT} characters")
        text = self._encode(data)
        if len(text.encode()) > DATA_LIMIT:
            raise Refused("invalid", f"data exceeds {DATA_LIMIT} bytes; store a body and cite its hash")

        db = self._db
        seq = head(db) + 1
        version = stream_version(db, stream) + 1
        cause = tuple(cause)
        based_on = tuple(based_on)
        for earlier in cause:
            if not 0 < earlier < seq:
                raise Refused("not_found", f"cause {earlier} does not point backward")
        for ref in (*based_on, *refs):
            self._check_ref(ref)

        payload = json.loads(text)
        if agent is None and self.me.kind == "agent":
            agent = self.me.name
        stamps = Stamps(db)
        context = f"context/{agent}"
        event = Event.model_construct(
            v=v,
            seq=seq,
            stream=stream,
            version=version,
            type=type,
            actor=self.me.id,
            agent=agent,
            turn=payload["turn"] if type == "turn.started" else stamps.turn(agent),
            context_version=None if agent is None else self._version_of(context, stream, version),
            episode=payload["episode"] if type == "episode.opened" else stamps.episode(),
            topology_rev=self._version_of("topology", stream, version),
            correlation=correlation,
            cause=cause,
            based_on=based_on,
            native={} if native is None else dict(native),
            model=model,
            wall_time=self.now,
            gist=gist,
            data=payload,
            outcome=None,
        )
        self._held = (event, text)
        self._apply(event)
        return event

    def effect(
        self,
        kind: str,
        data: Any = None,
        *,
        on_uncertain: Literal["retry", "reconcile", "surface"] = "surface",
        timeout: float | None = None,
        priority: int = 0,
        agent: str | None = None,
    ) -> str:
        """Request a touch of the world and return the effect's id.

        Effects of one agent run in order; a priority above zero goes first and bypasses that order.
        """
        self._flush()
        effect = str(head(self._db) + 1)
        self.emit(
            "effect.requested",
            f"effect/{effect}",
            gist=f"{kind} requested",
            agent=agent,
            data={
                "id": effect,
                "kind": kind,
                "data": data,
                "on_uncertain": on_uncertain,
                "timeout": timeout,
                "priority": priority,
            },
        )
        return effect

    def refuse(
        self,
        code: RefusalCode,
        detail: Any = "",
        *,
        reachable: tuple[str, ...] | None = None,
        retry_after: float | None = None,
    ) -> NoReturn:
        """End the command with a refusal. Its events roll back and the refusal is journaled."""
        raise Refused(code, detail, reachable=reachable, retry_after=retry_after)

    def _encode(self, data: Any) -> str:
        try:
            return canonical(jsonable(data))
        except ValueError as error:
            raise Refused("invalid", f"data is not JSON: {error}") from None

    def _version_of(self, name: str, stream: str, version: int) -> int:
        return version if name == stream else stream_version(self._db, name)

    def _check_ref(self, ref: str) -> None:
        db = self._db
        if body := _BODY_REF.fullmatch(ref):
            found = db.execute("SELECT 1 FROM bodies WHERE sha256 = ?", (body["sha256"],)).fetchone()
        elif event := _REF.fullmatch(ref):
            found = db.execute(
                "SELECT 1 FROM events WHERE stream = ? AND version = ?", (event["stream"], int(event["version"]))
            ).fetchone()
        else:
            raise Refused("invalid", f"not a ref: {ref!r}")
        if found is None:
            raise Refused("not_found", f"ref {ref} does not point backward")

    def _flush(self) -> None:
        """Write the held event. The last event of a command waits here for its outcome."""
        if self._held is not None:
            insert(self._db, *self._held)
            self._held = None

    def _finish(self, outcome: Outcome) -> Event:
        """Put the outcome on the command's last event, which only now can be written."""
        if self._held is None:
            stream = f"commands/{self.me.id}"
            self.emit("op.completed", stream, gist=f"{outcome.op} completed", data={"op": outcome.op})
        assert self._held is not None
        event, text = self._held
        event = event.model_copy(update={"outcome": outcome})
        insert(self._db, event, text)
        self._held = None
        Commands(self._db).recorded(event)
        return event
