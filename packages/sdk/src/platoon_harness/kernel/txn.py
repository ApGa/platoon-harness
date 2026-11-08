"""Txn: what an op receives, and the envelope it cannot touch."""

import json
import re
import sqlite3
from collections.abc import Callable, Iterable, Iterator, Mapping
from typing import Any, Literal

from .journal import decode, insert, last_seq, stream_version
from .model import (
    DATA_LIMIT,
    GIST_LIMIT,
    Event,
    Gauges,
    ModelRef,
    Outcome,
    Principal,
    Refused,
    canonical,
    jsonable,
)
from .naming import check_event_type
from .view import View, fold

_STREAM = re.compile(r"[^\s@#]+")
_STREAM_LIMIT = 512
_REF = re.compile(r"(?P<stream>[^\s@#]+)@(?P<version>\d{1,18})(#\S+)?")
_BODY_REF = re.compile(r"sha256:(?P<sha256>[0-9a-f]{64})(#\S+)?")


def _named(payload: Any, field: str) -> str:
    """The name a boundary event opens."""
    name = payload.get(field) if isinstance(payload, dict) else None
    if not isinstance(name, str):
        raise Refused("invalid", f"this event needs a {field}")
    return name


class Stamps(View):
    """What `emit` stamps: the open turn of each agent, the open episode, and the version of any stream."""

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

    def open_turns(self) -> dict[str, str]:
        """Each agent with a turn in flight, and that turn."""
        rows = self.db.execute("SELECT scope, value FROM v_stamps WHERE scope GLOB 'turn/*'")
        return {row["scope"].removeprefix("turn/"): row["value"] for row in rows}

    def began(self, agent: str | None) -> int | None:
        """The seq of the `turn.started` that opened an agent's open turn, or None while it has none."""
        if self.turn(agent) is None:
            return None
        row = self.db.execute(
            "SELECT seq FROM events WHERE stream = ? AND type = 'turn.started' ORDER BY version DESC LIMIT 1",
            (f"turn/{agent}",),
        ).fetchone()
        return None if row is None else row["seq"]

    def episode(self) -> str | None:
        return self._get("episode")

    def version_of(self, stream: str) -> int:
        """A stream's version: a group's generation, a board object's version. Read it before emitting.

        A command's last event is written when the op returns, so this cannot see that one.
        """
        return stream_version(self.db, stream)

    def at(self, stream: str, version: int) -> Event | None:
        """The event a ref names, by its stream and version, or None. Read it before emitting, too."""
        row = self.db.execute("SELECT * FROM events WHERE stream = ? AND version = ?", (stream, version)).fetchone()
        return None if row is None else decode(row)

    def event(self, seq: int) -> Event | None:
        """The event at a seq, as a `cause` names it, or None."""
        row = self.db.execute("SELECT * FROM events WHERE seq = ?", (seq,)).fetchone()
        return None if row is None else decode(row)

    def events(self, stream: str | None = None, *, after: int = 0) -> Iterator[Event]:
        """The events past `after`, oldest first, on one stream or all of them. Read it before emitting, too."""
        if stream is None:
            rows = self.db.execute("SELECT * FROM events WHERE seq > ? ORDER BY seq", (after,))
        else:
            rows = self.db.execute(
                "SELECT * FROM events WHERE stream = ? AND seq > ? ORDER BY version", (stream, after)
            )
        return (decode(row) for row in rows)

    def head(self) -> int:
        """The newest seq this transaction can see."""
        return last_seq(self.db)


class Txn:
    """What an op receives, and all an op receives. Fixed for one command: `me` and `now`."""

    __slots__ = ("_apply", "_db", "_fault", "_gauges", "_held", "_native", "me", "now")

    def __init__(
        self,
        db: sqlite3.Connection,
        me: Principal,
        now: float,
        apply: Callable[[Event], None] | None = None,
        native: Mapping[str, str] | None = None,
        gauges: Callable[[], Gauges | None] | None = None,
    ):
        self._db = db
        self._apply = apply
        self._native = native
        self._gauges = gauges
        self._held: tuple[Event, str] | None = None
        self._fault: BaseException | None = None
        self.me = me
        self.now = now

    def view[V: View](self, view: type[V]) -> V:
        """Read a view inside this transaction."""
        return view(self._db)

    def gauges(self) -> Gauges | None:
        """What the kernel running this query has measured of its writer and its process, as they stand now, or None
        from one that holds no writer, which measures nothing. A command cannot read them, so nothing it does or records
        rests on what no journal holds."""
        if self._apply is not None:
            raise Refused("unsupported", "a command cannot read the gauges: only a query can")
        return None if self._gauges is None else self._gauges()

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
        runtime: bool = False,
    ) -> Event:
        """Append one event and run its folds. `refs` are the refs held in `data`.

        `runtime` authors the event as the runtime, for what the runtime posts in the middle of someone else's command.
        """
        if self._apply is None:
            raise Refused("unsupported", "a query cannot emit")
        self._flush()
        check_event_type(type)
        if _STREAM.fullmatch(stream) is None or len(stream) > _STREAM_LIMIT:
            raise Refused("invalid", f"bad stream name: {stream!r}")
        if len(gist) > GIST_LIMIT:
            raise Refused("invalid", f"gist exceeds {GIST_LIMIT} characters")
        text = self._encode(data)
        cause = tuple(cause)
        based_on = tuple(based_on)
        native = self._native if native is None else native
        self._encode((cause, based_on, native, correlation))

        db = self._db
        seq = last_seq(db) + 1
        version = stream_version(db, stream) + 1
        for earlier in cause:
            if not 0 < earlier < seq:
                raise Refused("not_found", f"cause {earlier} does not point backward")
        for ref in based_on:
            if _BODY_REF.fullmatch(ref):
                raise Refused("invalid", "a body's hash is no ref: cite the event that carries it")
        for ref in (*based_on, *refs):
            self._check_ref(ref)

        payload = json.loads(text)
        if agent is None and self.me.kind == "agent":
            agent = self.me.name
        stamps = Stamps(db)
        turn = stamps.turn(agent)
        episode = stamps.episode()
        if type == "turn.started":
            turn = _named(payload, "turn")
            if agent is None:
                raise Refused("invalid", "a turn belongs to an agent")
        elif type == "episode.opened":
            if episode is not None:
                raise Refused("conflict", f"episode {episode} is open")
            episode = _named(payload, "episode")
        context = f"context/{agent}"
        event = Event.model_construct(
            v=v,
            seq=seq,
            stream=stream,
            version=version,
            type=type,
            actor="runtime" if runtime else self.me.id,
            agent=agent,
            turn=turn,
            context_version=None if agent is None else self._version_of(context, stream, version),
            episode=episode,
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
        try:
            self._apply(event)
        except BaseException as error:
            self._fault = error  # An op may catch this. The command must still fail, or a half fold commits.
            raise
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
        after: int | None = None,
    ) -> int:
        """Request a touch of the world and return the effect's id.

        Effects of one agent run in order; a priority above zero goes first and bypasses that order. With `after`, this
        one starts only once that one has finished, so a failure stops what depended on it.
        """
        self._flush()
        effect = last_seq(self._db) + 1
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
                "after": after,
            },
        )
        return effect

    def _encode(self, data: Any) -> str:
        try:
            text = canonical(jsonable(data))
            size = len(text.encode())
        except ValueError as error:
            raise Refused("invalid", f"data is not JSON: {error}") from None
        if size > DATA_LIMIT:
            raise Refused("invalid", f"data exceeds {DATA_LIMIT} bytes: store a body")
        return text

    def _version_of(self, name: str, stream: str, version: int) -> int:
        return version if name == stream else stream_version(self._db, name)

    def _check_ref(self, ref: str) -> None:
        """A ref points backward to an event, or to a body the journal holds or a person redacted, whose hash outlives
        its bytes."""
        db = self._db
        if body := _BODY_REF.fullmatch(ref):
            found = db.execute(
                "SELECT 1 FROM bodies WHERE sha256 = ?1 UNION ALL SELECT 1 FROM v_tombstones WHERE sha256 = ?1",
                (body["sha256"],),
            ).fetchone()
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

    def _finish(self, outcome: Outcome) -> Outcome:
        """Put the outcome on the command's last event, which only now can be written."""
        if self._fault is not None:
            raise self._fault
        if self._held is None:
            stream = f"commands/{self.me.id}"
            self.emit("op.completed", stream, gist=f"{outcome.op} completed", data={"op": outcome.op})
        assert self._held is not None
        event, text = self._held
        outcome = outcome.model_copy(update={"seq": event.seq})
        insert(self._db, event.model_copy(update={"outcome": outcome}), text)
        self._held = None
        return outcome
