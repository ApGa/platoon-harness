"""Recovery, after `Kernel.recover()`: per agent reap, resume and reconcile. Dispatch is the host's own loop.

Each effect kind follows its row in architecture section 5.4. Nothing here guesses: what cannot be known stays
uncertain, and is shown.
"""

import asyncio
import logging
from pathlib import Path
from typing import Any

from platoon_harness.drivers import DriverError, Exited, GapReport, InputDelivered, Native, Report
from platoon_harness.drivers.process import reap
from platoon_harness.kernel import Effect, Kernel, Refused
from platoon_harness.schema import ConfigError

from .git import GitError
from .host import GRACE, Host
from .paths import agent_folder

_CRASH = GapReport(what="crash_window")

log = logging.getLogger("platoon_harness.runtime")

__all__ = ["recover_agents"]


async def _must(host: Host, op: str, args: dict[str, Any]) -> None:
    outcome = await host.insist(op, args)
    if outcome.refusal is not None:
        raise Refused.of(outcome.refusal)


async def _say(host: Host, agent: str, *reports: Report) -> None:
    for report in reports:
        await _must(host, "agent.report", {"agent": agent, "report": report})


async def _reap(host: Host, folder: Path, agent: dict[str, Any]) -> None:
    """End what the crash left of an agent. What cannot be proved ours is left alone, and named."""
    for left in await reap(agent_folder(folder, agent["name"]), GRACE):
        await _say(host, agent["name"], Native(kind="unproven_group", raw=left), _CRASH)


async def _resume(host: Host, agent: dict[str, Any]) -> None:
    """Bring a harness back. It is told what it cannot know, a goal that never began or a turn that was cut off, since a
    resumed harness waits to be told, and a resume is someone wanting the session to go on."""
    await host.resume(agent)
    await _must(host, "agent.retell", {"agent": agent["name"]})


async def _take_up(host: Host, folder: Path, agent: dict[str, Any], accepting: bool) -> None:
    """Reap one agent and bring it back, or lose it through the normal ended transition. It answers for itself, so one
    broken driver takes down one agent."""
    name = agent["name"]
    try:
        await _reap(host, folder, agent)
        if agent["finishing"]:
            await host.insist("agent.conclude", {"agent": name})
        elif agent["state"] in ("spawning", "ended") or agent["resting"]:  # A resting one comes back at its handover.
            return
        elif accepting:
            await _resume(host, agent)
        elif agent["unbegun"]:
            raise DriverError("its session closed before it began its goal")
    except (DriverError, ConfigError, GitError) as error:
        await _say(host, name, _CRASH, Exited(reason=str(error)))
    except Exception as error:
        log.error("%s could not be taken up: %s", name, type(error).__name__)
        await _say(host, name, _CRASH, Exited(reason=f"its harness could not resume: {type(error).__name__}"))


async def _finish(host: Host, effect: Effect, result: Any = None) -> None:
    await host.insist("effect.finish", {"id": effect.id, "attempt": effect.attempts, "result": result})


async def _fail(host: Host, effect: Effect, error: str) -> None:
    await host.insist("effect.fail", {"id": effect.id, "attempt": effect.attempts, "error": error})


async def _reconcile_delivery(host: Host, effect: Effect, agent: dict[str, Any] | None) -> None:
    """A delivery counts if it landed and its turn began. Otherwise it goes again under a new input, at-least-once, and
    its refs dedupe it: a harness that was killed before its turn began will not begin one now."""
    input = str(effect.data["input"])
    landed = await host.reconcile(effect.agent, input) == "landed"
    if landed and agent is not None and agent["state"] != "waking":
        report = InputDelivered(input=input, boundary=effect.data["boundary"], evidence="reconcile")
        await _say(host, agent["name"], report)
        await _finish(host, effect)
    else:
        await _fail(host, effect, "it was in flight when the runtime died, so it goes again under a new input")


async def _reconcile_answer(host: Host, effect: Effect) -> None:
    """Whether an answer landed is read from the harness, or it stays uncertain in attention."""
    found = await host.reconcile(effect.agent, effect.data["approval"])
    if found == "landed":
        await _finish(host, effect)
    elif found == "not_landed":
        await _fail(host, effect, "the answer never reached the harness")


async def _reconcile(host: Host, effect: Effect, agents: dict[str, dict[str, Any]]) -> None:
    """An admission or a launch in flight is a crash window, said while its effect is uncertain, so the gap begins at
    that effect's request."""
    agent = agents.get(effect.agent or "")
    match effect.kind:
        case "admit":
            if agent is not None:
                await _say(host, agent["name"], _CRASH)
            await _fail(host, effect, "it was in flight when the runtime died, and an admission is never retried")
        case "workspace":  # Asked before a workspace was retried, so the shared one, and made again.
            await _finish(host, effect, await host.workspace(effect))
        case "launch" if agent is not None and agent["state"] != "spawning":
            await _finish(host, effect)
        case "launch":
            if agent is not None:
                await _say(host, agent["name"], _CRASH)
            await _fail(host, effect, "its harness was launching when the runtime died, and has no id to resume by")
        case "deliver":
            await _reconcile_delivery(host, effect, agent)
        case "answer":
            await _reconcile_answer(host, effect)


def _asked(kernel: Kernel, op: str, args: dict[str, Any]) -> Any:
    outcome = kernel.query(kernel.runtime, op, args)
    if outcome.refusal is not None:
        raise Refused.of(outcome.refusal)
    return outcome.result


async def recover_agents(kernel: Kernel, host: Host, folder: Path) -> None:
    """Take a session up again. A session that has stopped accepting work spends nothing: it is reaped and no more."""
    agents = {row["name"]: row for row in _asked(kernel, "agent.records", {})}
    accepting = _asked(kernel, "session.status", {})["state"] == "open"
    await asyncio.gather(*(_take_up(host, folder, agent, accepting) for agent in agents.values()))
    for row in _asked(kernel, "effect.list", {"state": "uncertain"}):
        await _reconcile(host, Effect.model_validate(row), agents)
