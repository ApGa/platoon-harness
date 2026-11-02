"""Recovery, after `Kernel.recover()`: per agent reap, resume and reconcile. Dispatch is the host's own loop.

Each effect kind follows its row in architecture section 5.4. Nothing here guesses: what cannot be known stays
uncertain, and is shown.
"""

import asyncio
from pathlib import Path
from typing import Any

from platoon_harness.drivers import DriverError, Exited, GapReport, InputDelivered, Native, Reconciled, Report
from platoon_harness.drivers.process import reap
from platoon_harness.kernel import Effect, Kernel
from platoon_harness.schema import ConfigError

from .authority import SpawnRequest
from .host import GRACE, Host
from .paths import agent_folder

_CRASH = GapReport(plane="control", what="crash_window")

__all__ = ["recover_agents"]


async def _say(host: Host, agent: str, *reports: Report) -> None:
    for report in reports:
        await host.insist("agent.report", {"agent": agent, "report": report})


async def _reap(host: Host, folder: Path, agent: dict[str, Any]) -> None:
    """End what the crash left of an agent. A group that cannot be proved ours is left alone, and named."""
    for record in await reap(agent_folder(folder, agent["name"]), GRACE):
        raw = f"process group {record.pid} outlived its leader and cannot be proved ours"
        await _say(host, agent["name"], Native(kind="unproven_group", raw=raw), _CRASH)


async def _resume(host: Host, agent: dict[str, Any]) -> None:
    """Bring a harness back on a fresh credential, or lose its agent through the normal ended transition."""
    name, role, native = agent["name"], agent["role"], agent["native"]
    try:
        if native is None or not (await host.describe(role)).capabilities.resume:
            raise DriverError("its harness cannot resume")
        admission = await host.admit(SpawnRequest(agent=name, role=role, resumed=True))
        await host.connect(name, role, admission, resume=native)
    except (DriverError, ConfigError) as error:
        await _say(host, name, _CRASH, Exited(reason=str(error)))


async def _finish(host: Host, effect: Effect, result: Any = None) -> None:
    await host.insist("effect.finish", {"id": effect.id, "attempt": effect.attempts, "result": result})


async def _fail(host: Host, effect: Effect, error: str) -> None:
    await host.insist("effect.fail", {"id": effect.id, "attempt": effect.attempts, "error": error})


async def _found(host: Host, effect: Effect, key: str) -> Reconciled:
    """What a harness says became of what it was sent. With no harness to ask, or none that can say, nobody knows."""
    link = host.link(effect.agent)
    try:
        return "unknown" if link is None else await link.driver.reconcile(key)
    except DriverError:
        return "unknown"


async def _reconcile_delivery(host: Host, effect: Effect, agent: dict[str, Any] | None) -> None:
    """A delivery counts if it landed and its turn began. Otherwise it goes again under a new input, at-least-once, and
    its refs dedupe it: a harness that was killed before its turn began will not begin one now."""
    input = str(effect.data["input"])
    landed = await _found(host, effect, input) == "landed"
    if landed and agent is not None and agent["state"] != "waking":
        report = InputDelivered(input=input, boundary=effect.data["boundary"], evidence="reconcile")
        await _say(host, agent["name"], report)
        await _finish(host, effect)
    else:
        await _fail(host, effect, "it was in flight when the runtime died, so it goes again under a new input")


async def _reconcile_answer(host: Host, effect: Effect) -> None:
    """Whether an answer landed is read from the harness, or it stays uncertain in attention."""
    found = await _found(host, effect, effect.data["approval"])
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

    async def take_up(agent: dict[str, Any]) -> None:
        await _reap(host, folder, agent)
        if accepting and agent["state"] not in ("spawning", "ended"):
            await _resume(host, agent)

    await asyncio.gather(*map(take_up, agents.values()))
    for row in kernel.query(runtime, "effect.list", {"state": "uncertain"}).result:
        await _reconcile(host, cwd, Effect.model_validate(row), agents)
