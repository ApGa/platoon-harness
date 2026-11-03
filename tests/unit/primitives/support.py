"""Helpers for driving primitives through their public ops, as a driver and a runtime would."""

from pathlib import Path
from typing import Any

from platoon_harness.kernel import Kernel, Outcome, Principal, Refusal
from platoon_harness.primitives import Approvals, Cursor, Deliveries

from ..kernel.support import dump, enroll, events_of, grant, result_of

ROLES = {
    "lead": {"harness": "claude", "model": "m", "tools": ["*"]},
    "worker": {"harness": "codex", "model": "m", "on_parent_exit": "adopt"},
    "linked": {"harness": "codex", "on_parent_exit": "cancel-subtree"},
    "cramped": {"harness": "codex", "inbox_depth": 2},
    "steerer": {"harness": "codex", "delivery": "steer"},
    "quiet": {"harness": "codex", "delivery": "pull"},
    "narrow": {"harness": "codex", "tools": ["wait", "ops.list"]},
    "keeper": {"harness": "codex", "stays": True, "persistent": True},
    "leaver": {"harness": "codex", "stays": False, "persistent": True},
    "oneshot": {"harness": "exec", "persistent": False},
}


def agent(name: str) -> Principal:
    return Principal(id=f"agent:{name}")


async def spawn(
    kernel: Kernel,
    name: str,
    *,
    role: str = "worker",
    by: Principal | None = None,
    ready: dict[str, Any] | None = None,
    goal: str | None = None,
    stays: bool | None = None,
) -> Principal:
    """Spawn an agent through to started, doing what the host does between the two."""
    args = {"name": name, "child_role": role, "goal": f"be {name}" if goal is None else goal, "stays": stays}
    result_of(await kernel.submit(by or kernel.runtime, "agent.spawn", args))
    await settle_effects(kernel, name)
    await start(kernel, name, **(ready or {}))
    return agent(name)


async def settle_effects(kernel: Kernel, name: str | None = None) -> None:
    """Start and finish what a daemon would: one agent's effects, or everyone's."""
    while effects := [
        effect
        for effect in result_of(kernel.query(kernel.runtime, "effect.ready", {}))
        if name is None or effect["agent"] == name
    ]:
        for effect in effects:
            started = result_of(await kernel.submit(kernel.runtime, "effect.start", {"id": effect["id"]}))
            result_of(await kernel.submit(kernel.runtime, "effect.finish", {"id": effect["id"], "attempt": started}))


async def start(kernel: Kernel, name: str, /, *, levels: dict[str, Any] | None = None, **declared: Any) -> None:
    """Commit a harness as up, as a persistent one with turn boundaries unless a test says otherwise."""
    declared = {"persistent": True, "boundaries": ["turn"], **declared}
    args = {"agent": name, "ready": {}, "declared": declared, "levels": levels or {}}
    result_of(await kernel.submit(kernel.runtime, "agent.start", args))


async def report(kernel: Kernel, name: str, type: str, /, **fields: Any) -> None:
    result_of(await kernel.submit(kernel.runtime, "agent.report", {"agent": name, "report": {"type": type, **fields}}))


async def start_turn(kernel: Kernel, name: str, turn: str = "t1") -> None:
    await report(kernel, name, "turn.started", turn=turn)


async def end_turn(kernel: Kernel, name: str, reason: str = "stopped") -> None:
    await report(kernel, name, "turn.ended", reason=reason)


async def channel(kernel: Kernel, name: str, kind: str = "topic", **fields: Any) -> None:
    args = {"name": name, "kind": kind, **fields}
    result_of(await kernel.submit(kernel.runtime, "channel.create", args))


async def send(kernel: Kernel, by: Principal, to: str, gist: str = "hi", **fields: Any) -> dict[str, Any]:
    return result_of(await kernel.submit(by, "message.send", {"to": to, "gist": gist, **fields}))


async def read(kernel: Kernel, by: Principal, channel: str, **fields: Any) -> dict[str, Any]:
    return result_of(await kernel.submit(by, "message.read", {"channel": channel, **fields}))


def gists(result: dict[str, Any]) -> list[str]:
    return [entry["gist"] for entry in result["entries"]]


def of_type(kernel: Kernel, *types: str, after: int = 0) -> list[Any]:
    return [event for event in events_of(kernel, after=after) if event.type in types]


def cursor(kernel: Kernel, reader: str, stream: str) -> Cursor:
    """Where a reader stands, read the way a query reads."""
    with kernel._reading() as db:
        return Deliveries(db).cursor(reader, stream)


def approval(kernel: Kernel, id: str = "a1") -> Any:
    with kernel._reading() as db:
        return Approvals(db).get(id)


def refusal(outcome: Outcome) -> Refusal:
    assert outcome.refusal is not None, outcome
    return outcome.refusal


def logical_dump(folder: Path) -> dict[str, list[tuple[Any, ...]]]:
    """Every view's rows. An FTS index's own storage depends on how commits were batched, so it is left out."""
    shadows = ("_data", "_idx", "_content", "_docsize", "_config")
    return {name: rows for name, rows in dump(folder).items() if not name.endswith(shadows)}


__all__ = ["dump", "enroll", "events_of", "grant", "result_of"]
