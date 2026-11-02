"""Effects: tracked requests to touch the world, and the outbox daemons read."""

import json
import sqlite3
from typing import Any, Literal

from pydantic import BaseModel, JsonValue

from .model import GIST_LIMIT, Event, Refused
from .op import Args, op
from .timers import Timer
from .txn import Stamps, Txn
from .view import View, fold

_LIMIT = 64
_ERROR_LIMIT = 2048


class Effect(BaseModel, frozen=True):
    """One row of the outbox."""

    id: int
    kind: str
    state: Literal["requested", "started", "finished", "failed", "uncertain", "cancelled"]
    on_uncertain: Literal["retry", "reconcile", "surface"]
    timeout: float | None
    priority: int
    agent: str | None
    attempts: int
    after: int | None
    data: Any


class Effects(View):
    """The outbox and the input to recovery."""

    schema = """
    CREATE TABLE v_effects(
        id INTEGER PRIMARY KEY,
        kind TEXT NOT NULL,
        state TEXT NOT NULL,
        on_uncertain TEXT NOT NULL CHECK (on_uncertain IN ('retry', 'reconcile', 'surface')),
        timeout REAL,
        priority INTEGER NOT NULL,
        agent TEXT,
        attempts INTEGER NOT NULL,
        after INTEGER,
        data TEXT NOT NULL
    ) STRICT;
    CREATE INDEX v_effects_state ON v_effects(state, priority);
    """

    @fold("effect.requested")
    def requested(self, event: Event) -> None:
        data = event.data
        self.db.execute(
            "INSERT INTO v_effects VALUES (?, ?, 'requested', ?, ?, ?, ?, 0, ?, ?)",
            (
                data["id"],
                data["kind"],
                data["on_uncertain"],
                data["timeout"],
                data["priority"],
                event.agent,
                data["after"],
                json.dumps(data["data"]),
            ),
        )

    @fold("effect.started")
    def started(self, event: Event) -> None:
        self.db.execute(
            "UPDATE v_effects SET state = 'started', attempts = attempts + 1 WHERE id = ?", (event.data["id"],)
        )

    @fold("effect.finished", "effect.failed", "effect.uncertain", "effect.retried", "effect.cancelled")
    def moved(self, event: Event) -> None:
        state = "requested" if event.type == "effect.retried" else event.type.removeprefix("effect.")
        self.db.execute("UPDATE v_effects SET state = ? WHERE id = ?", (state, event.data["id"]))

    def _load(self, rows: list[sqlite3.Row]) -> list[Effect]:
        return [Effect(**{**dict(row), "data": json.loads(row["data"])}) for row in rows]

    def get(self, id: int) -> Effect | None:
        rows = self.db.execute("SELECT * FROM v_effects WHERE id = ?", (id,)).fetchall()
        return next(iter(self._load(rows)), None)

    def in_state(self, state: str) -> list[Effect]:
        return self._load(self.db.execute("SELECT * FROM v_effects WHERE state = ? ORDER BY id", (state,)).fetchall())

    def requested_for(self, agent: str) -> list[Effect]:
        rows = self.db.execute("SELECT * FROM v_effects WHERE agent = ? AND state = 'requested' ORDER BY id", (agent,))
        return self._load(rows.fetchall())

    def ready(self, kind: str | None = None) -> list[Effect]:
        """Requested effects a daemon may start now: per agent in order, unless priority bypasses that."""
        rows = self.db.execute(
            """
            SELECT * FROM v_effects AS e
            WHERE e.state = 'requested' AND (:kind IS NULL OR e.kind = :kind)
            AND (e.after IS NULL OR e.after IN (SELECT id FROM v_effects WHERE state = 'finished'))
            AND (
                e.priority > 0 OR e.agent IS NULL OR NOT EXISTS (
                    SELECT 1 FROM v_effects AS o
                    WHERE o.agent = e.agent AND o.priority = 0 AND o.id < e.id
                        AND o.state IN ('requested', 'started')
                )
            )
            ORDER BY e.priority DESC, e.id LIMIT :limit
            """,
            {"kind": kind, "limit": _LIMIT},
        )
        return self._load(rows.fetchall())


def _note(txn: Txn, effect: Effect, event_type: str, gist: str, **data: Any) -> None:
    data |= {"id": effect.id, "kind": effect.kind}
    txn.emit(event_type, f"effect/{effect.id}", gist=gist[:GIST_LIMIT], agent=effect.agent, data=data)


def _timer_key(effect: Effect, attempt: int) -> str:
    return f"effect/{effect.id}/{attempt}"


def _cancel_timeout(txn: Txn, effect: Effect) -> None:
    if effect.timeout is not None and effect.state == "started":
        key = _timer_key(effect, effect.attempts)
        txn.emit("timer.cleared", f"timer/{key}", gist=f"timer {key} cleared", data={"key": key})


def _require(txn: Txn, id: int, *states: str) -> Effect:
    effect = txn.view(Effects).get(id)
    if effect is None:
        raise Refused("not_found", f"no effect {id}")
    if effect.state not in states:
        raise Refused("conflict", {"state": effect.state, "expected": list(states)})
    return effect


def _settling(txn: Txn, id: int, attempt: int) -> Effect:
    """The effect a report settles. A late report from an older attempt is refused, while a newer one runs."""
    effect = _require(txn, id, "started", "uncertain")
    if effect.state == "started" and effect.attempts != attempt:
        raise Refused("conflict", {"attempt": attempt, "running": effect.attempts})
    return effect


def _mark_uncertain(txn: Txn, effect: Effect, why: str) -> None:
    """Nobody knows whether the effect happened, so apply its declared policy."""
    _note(txn, effect, "effect.uncertain", f"{effect.kind} uncertain: {why}", why=why)
    if effect.on_uncertain == "retry":
        _note(txn, effect, "effect.retried", f"{effect.kind} retried", why=why)


class EffectId(Args):
    id: int


class EffectResult(Args):
    id: int
    attempt: int
    result: JsonValue = None


class EffectError(Args):
    id: int
    attempt: int
    error: str


class EffectAttempt(Args):
    id: int
    attempt: int


class EffectVerdict(Args):
    id: int
    happened: bool


class Incarnation(Args):
    changed: tuple[str, ...] = ()


class EffectKind(Args):
    kind: str | None = None


class EffectState(Args):
    state: Literal["requested", "started", "finished", "failed", "uncertain", "cancelled"]


@op("effect.ready", query=True, runtime=True)
def ready_effects(txn: Txn, a: EffectKind) -> list[Effect]:
    """List the effects a daemon may start now."""
    return txn.view(Effects).ready(a.kind)


@op("effect.list", query=True, runtime=True)
def list_effects(txn: Txn, a: EffectState) -> list[Effect]:
    """List the effects in one state, which is what recovery works through."""
    return txn.view(Effects).in_state(a.state)


@op("effect.start", on=lambda a: f"effect/{a.id}", runtime=True)
def start_effect(txn: Txn, a: EffectId) -> int:
    """Record that a daemon is about to act, and return the attempt. An effect with a timeout gets a timer now."""
    effect = _require(txn, a.id, "requested")
    attempt = effect.attempts + 1
    _note(txn, effect, "effect.started", f"{effect.kind} started")
    if effect.timeout is not None:
        key = _timer_key(effect, attempt)
        args = {"id": a.id, "attempt": attempt}
        timer = Timer(due=txn.now + effect.timeout, op="effect.expire", args=args, key=key)
        txn.emit("timer.set", f"timer/{key}", gist=f"timer {key} set", data=timer)
    return attempt


@op("effect.finish", on=lambda a: f"effect/{a.id}", runtime=True)
def finish_effect(txn: Txn, a: EffectResult) -> None:
    """Record that an effect happened. Reconciling an uncertain one lands here too."""
    effect = _settling(txn, a.id, a.attempt)
    _cancel_timeout(txn, effect)
    _note(txn, effect, "effect.finished", f"{effect.kind} finished", result=a.result)


@op("effect.fail", on=lambda a: f"effect/{a.id}", runtime=True)
def fail_effect(txn: Txn, a: EffectError) -> None:
    """Record that an effect did not happen. A long error is cut, so that failure can always be reported."""
    effect = _settling(txn, a.id, a.attempt)
    _cancel_timeout(txn, effect)
    error = a.error if len(a.error) <= _ERROR_LIMIT else f"{a.error[:_ERROR_LIMIT]} [cut]"
    _note(txn, effect, "effect.failed", f"{effect.kind} failed: {error}", error=error)


@op("effect.settle", on=lambda a: f"effect/{a.id}")
def settle_effect(txn: Txn, a: EffectVerdict) -> None:
    """Say whether an uncertain effect happened, which is what `surface` leaves to a person. Refused `conflict` once it
    is no longer uncertain, as when recovery got there first."""
    if txn.me.kind == "agent":
        raise Refused("not_permitted", "an agent cannot vouch for an effect")
    effect = _require(txn, a.id, "uncertain")
    by = f"{txn.me.id} says so"
    if a.happened:
        _note(txn, effect, "effect.finished", f"{effect.kind} finished: {by}", result=None)
    else:
        _note(txn, effect, "effect.failed", f"{effect.kind} failed: {by}", error=f"it did not happen: {by}")


@op("effect.expire", on=lambda a: f"effect/{a.id}", runtime=True)
def expire_effect(txn: Txn, a: EffectAttempt) -> None:
    """Fired by a timer: an attempt still running past its timeout becomes uncertain."""
    effect = txn.view(Effects).get(a.id)
    if effect is not None and effect.state == "started" and effect.attempts == a.attempt:
        _mark_uncertain(txn, effect, "timed out")


@op("runtime.start", on=lambda a: "runtime", runtime=True)
def start_runtime(txn: Txn, a: Incarnation) -> int:
    """Begin an incarnation, and return its number, which is this event's stream version.

    Started effects become uncertain, and a turn in flight is lost: its tool effects are unknown and never re-run.
    """
    gist = "; ".join(("runtime started", *a.changed))[:GIST_LIMIT]
    incarnation = txn.emit("runtime.started", "runtime", gist=gist, data={"changed": a.changed}).version
    for effect in txn.view(Effects).in_state("started"):
        _cancel_timeout(txn, effect)
        _mark_uncertain(txn, effect, "the runtime restarted")
    for agent, turn in txn.view(Stamps).open_turns().items():
        txn.emit("turn.lost", f"turn/{agent}", gist=f"turn {turn} lost", agent=agent, data={"gap": "crash_window"})
    return incarnation
