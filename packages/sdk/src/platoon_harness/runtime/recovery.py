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

from .authority import SpawnRequest
from .host import GRACE, Host
from .paths import agent_folder

_CRASH = GapReport(plane="control", what="crash_window")

log = logging.getLogger("platoon_harness.runtime")

__all__ = ["recover_agents"]


async def _say(host: Host, agent: str, *reports: Report) -> None:
    for report in reports:
        outcome = await host.insist("agent.report", {"agent": agent, "report": report})
        if outcome.refusal is not None:
            raise Refused.of(outcome.refusal)


async def _reap(host: Host, folder: Path, agent: dict[str, Any]) -> None:
    """End what the crash left of an agent. What cannot be proved ours is left alone, and named."""
    for left in await reap(agent_folder(folder, agent["name"]), GRACE):
        await _say(host, agent["name"], Native(kind="unproven_group", raw=left), _CRASH)


async def _resume(host: Host, agent: dict[str, Any]) -> None:
    """Bring a harness back on a fresh credential. If its goal never began, it is told again, since a resumed harness
    waits to be told."""
    name, role, native = agent["name"], agent["role"], agent["native"]
    if native is None or not (await host.describe(role)).capabilities.resume:
        raise DriverError("its harness cannot resume")
    admission = await host.admit(SpawnRequest(agent=name, role=role, resumed=True))
    await host.connect(name, role, admission, resume=native)
    if agent["unbegun"]:
        await host.insist("agent.retell", {"agent": name})


async def _take_up(host: Host, folder: Path, agent: dict[str, Any], accepting: bool) -> None:
    """Reap one agent and bring it back, or lose it through the normal ended transition. It answers for itself, so one
    broken driver takes down one agent."""
    name = agent["name"]
    try:
        await _reap(host, folder, agent)
        if agent["finishing"]:
            await host.insist("agent.conclude", {"agent": name})
        elif agent["state"] in ("spawning", "ended"):
            return
        elif accepting:
            await _resume(host, agent)
        elif agent["unbegun"]:
            raise DriverError("its session closed before it began its goal")
    except (DriverError, ConfigError) as error:
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


async def _reconcile(host: Host, cwd: Path, effect: Effect, agents: dict[str, dict[str, Any]]) -> None:
    agent = agents.get(effect.agent or "")
    match effect.kind:
        case "admit":
            await _fail(host, effect, "it was in flight when the runtime died, and an admission is never retried")
            if agent is not None:
                await _say(host, agent["name"], GapReport(plane="model", what="crash_window"))
        case "workspace":
            await _finish(host, effect, {"path": str(cwd)})
        case "launch" if agent is not None and agent["state"] != "spawning":
            await _finish(host, effect, {"native": agent["native"]})
        case "launch":
            await _fail(host, effect, "its harness was launching when the runtime died, and has no id to resume by")
            if agent is not None:
                await _say(host, agent["name"], _CRASH)
        case "deliver":
            await _reconcile_delivery(host, effect, agent)
        case "answer":
            await _reconcile_answer(host, effect)


async def recover_agents(kernel: Kernel, host: Host, folder: Path, cwd: Path) -> None:
    """Take a session up again. A session that has stopped accepting work spends nothing: it is reaped and no more."""
    runtime = kernel.runtime
    agents = {row["name"]: row for row in kernel.query(runtime, "agent.records", {}).result}
    accepting = kernel.query(runtime, "session.status", {}).result["state"] == "open"
    await asyncio.gather(*(_take_up(host, folder, agent, accepting) for agent in agents.values()))
    for row in kernel.query(runtime, "effect.list", {"state": "uncertain"}).result:
        await _reconcile(host, cwd, Effect.model_validate(row), agents)
