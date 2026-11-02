"""Effects: tracked requests to touch the world, and the outbox daemons read."""

import json
import sqlite3
from typing import Any, Literal

from pydantic import BaseModel, JsonValue

from .model import GIST_LIMIT, Event
from .op import Args, op
from .timers import Timer
from .txn import Txn
from .view import View, fold


class Effect(BaseModel, frozen=True):
    """One row of the outbox."""

    id: str
    kind: str
    state: Literal["requested", "started", "finished", "failed", "uncertain"]
    on_uncertain: Literal["retry", "reconcile", "surface"]
    timeout: float | None
    deadline: float | None
    priority: int
    agent: str | None
    attempts: int
    data: JsonValue
    seq: int


class Effects(View):
    """The outbox and the input to recovery."""

    schema = """
    CREATE TABLE v_effects(
        id TEXT PRIMARY KEY,
        kind TEXT NOT NULL,
        state TEXT NOT NULL,
        on_uncertain TEXT NOT NULL CHECK (on_uncertain IN ('retry', 'reconcile', 'surface')),
        timeout REAL,
        deadline REAL,
        priority INTEGER NOT NULL,
        agent TEXT,
        attempts INTEGER NOT NULL,
        data TEXT NOT NULL,
        seq INTEGER NOT NULL
    ) WITHOUT ROWID, STRICT;
    CREATE INDEX v_effects_state ON v_effects(state, priority, seq);
    """

    @fold("effect.requested")
    def requested(self, event: Event) -> None:
        data = event.data
        self.db.execute(
            "INSERT INTO v_effects VALUES (?, ?, 'requested', ?, ?, NULL, ?, ?, 0, ?, ?)",
            (
                data["id"],
                data["kind"],
                data["on_uncertain"],
                data["timeout"],
                data["priority"],
                event.agent,
                json.dumps(data["data"]),
                event.seq,
            ),
        )

    @fold("effect.started")
    def started(self, event: Event) -> None:
        self.db.execute(
            "UPDATE v_effects SET state = 'started', deadline = ?, attempts = attempts + 1 WHERE id = ?",
            (event.data["deadline"], event.data["id"]),
        )

    @fold("effect.finished", "effect.failed", "effect.uncertain", "effect.retried")
    def moved(self, event: Event) -> None:
        state = "requested" if event.type == "effect.retried" else event.type.removeprefix("effect.")
        self.db.execute("UPDATE v_effects SET state = ?, deadline = NULL WHERE id = ?", (state, event.data["id"]))

    def _load(self, rows: list[sqlite3.Row]) -> list[Effect]:
        return [Effect(**{**dict(row), "data": json.loads(row["data"])}) for row in rows]

    def get(self, id: str) -> Effect | None:
        rows = self.db.execute("SELECT * FROM v_effects WHERE id = ?", (id,)).fetchall()
        return next(iter(self._load(rows)), None)

    def in_state(self, state: str) -> list[Effect]:
        return self._load(self.db.execute("SELECT * FROM v_effects WHERE state = ? ORDER BY seq", (state,)).fetchall())

    def ready(self, kind: str | None = None, *, limit: int = 64) -> list[Effect]:
        """Requested effects a daemon may start now: per agent in order, unless priority bypasses that."""
        rows = self.db.execute(
            """
            SELECT * FROM v_effects AS e
            WHERE e.state = 'requested' AND (:kind IS NULL OR e.kind = :kind) AND (
                e.priority > 0 OR e.agent IS NULL OR NOT EXISTS (
                    SELECT 1 FROM v_effects AS o
                    WHERE o.agent = e.agent AND o.priority = 0 AND o.seq < e.seq
                        AND o.state IN ('requested', 'started')
                )
            )
            ORDER BY e.priority DESC, e.seq LIMIT :limit
            """,
            {"kind": kind, "limit": limit},
        )
        return self._load(rows.fetchall())


def _report(txn: Txn, effect: Effect, event_type: str, gist: str, **data: Any) -> None:
    data |= {"id": effect.id, "kind": effect.kind}
    txn.emit(event_type, f"effect/{effect.id}", gist=gist[:GIST_LIMIT], agent=effect.agent, data=data)


def _timer_key(effect: Effect, attempt: int) -> str:
    return f"effect/{effect.id}/{attempt}"


def _cancel_timeout(txn: Txn, effect: Effect) -> None:
    if effect.timeout is not None and effect.state == "started":
        key = _timer_key(effect, effect.attempts)
        txn.emit("timer.cleared", f"timer/{key}", gist=f"timer {key} cleared", data={"key": key})


def _in_state(txn: Txn, id: str, *states: str) -> Effect:
    effect = txn.view(Effects).get(id)
    if effect is None:
        txn.refuse("not_found", f"no effect {id}")
    if effect.state not in states:
        txn.refuse("conflict", {"state": effect.state, "expected": list(states)})
    return effect


def _mark_uncertain(txn: Txn, effect: Effect, why: str) -> None:
    """Nobody knows whether the effect happened, so apply its declared policy."""
    _report(txn, effect, "effect.uncertain", f"{effect.kind} uncertain: {why}", why=why)
    if effect.on_uncertain == "retry":
        _report(txn, effect, "effect.retried", f"{effect.kind} retried", why=why)


class EffectId(Args):
    id: str


class EffectResult(Args):
    id: str
    result: JsonValue = None


class EffectError(Args):
    id: str
    error: str


class EffectAttempt(Args):
    id: str
    attempt: int


class ReadyEffects(Args):
    kind: str | None = None
    limit: int = 64


@op("effect.ready", query=True, runtime=True)
def ready_effects(txn: Txn, a: ReadyEffects) -> list[Effect]:
    """List the effects a daemon may start now."""
    return txn.view(Effects).ready(a.kind, limit=a.limit)


@op("effect.start", on=lambda a: f"effect/{a.id}", runtime=True)
def start_effect(txn: Txn, a: EffectId) -> None:
    """Record that a daemon is about to act. An effect with a timeout gets a timer now."""
    effect = _in_state(txn, a.id, "requested")
    deadline = None if effect.timeout is None else txn.now + effect.timeout
    _report(txn, effect, "effect.started", f"{effect.kind} started", deadline=deadline)
    if deadline is not None:
        attempt = effect.attempts + 1
        key = _timer_key(effect, attempt)
        timer = Timer(due=deadline, op="effect.expire", args={"id": a.id, "attempt": attempt}, key=key)
        txn.emit("timer.set", f"timer/{key}", gist=f"timer {key} set", data=timer)


@op("effect.finish", on=lambda a: f"effect/{a.id}", runtime=True)
def finish_effect(txn: Txn, a: EffectResult) -> None:
    """Record that an effect happened. Reconciling an uncertain one lands here too."""
    effect = _in_state(txn, a.id, "started", "uncertain")
    _cancel_timeout(txn, effect)
    _report(txn, effect, "effect.finished", f"{effect.kind} finished", result=a.result)


@op("effect.fail", on=lambda a: f"effect/{a.id}", runtime=True)
def fail_effect(txn: Txn, a: EffectError) -> None:
    """Record that an effect did not happen. Reconciling an uncertain one lands here too."""
    effect = _in_state(txn, a.id, "started", "uncertain")
    _cancel_timeout(txn, effect)
    _report(txn, effect, "effect.failed", f"{effect.kind} failed: {a.error}", error=a.error)


@op("effect.expire", on=lambda a: f"effect/{a.id}", runtime=True)
def expire_effect(txn: Txn, a: EffectAttempt) -> None:
    """Fired by a timer: an attempt still running past its timeout becomes uncertain."""
    effect = txn.view(Effects).get(a.id)
    if effect is not None and effect.state == "started" and effect.attempts == a.attempt:
        _mark_uncertain(txn, effect, "timed out")


@op("runtime.start", on=lambda a: "runtime", runtime=True)
def start_runtime(txn: Txn, a: Args) -> None:
    """Begin an incarnation, whose number is this event's stream version. Started effects become uncertain."""
    txn.emit("runtime.started", "runtime", gist="runtime started")
    for effect in txn.view(Effects).in_state("started"):
        _cancel_timeout(txn, effect)
        _mark_uncertain(txn, effect, "the runtime restarted")
