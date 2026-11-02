"""check_driver: named checks against a loopback model's log, every failure at once.

"Connected" counts for nothing here. A check passes on what the harness actually sent, or it does not pass. Unsupported
is a skip with a reason, and a skip is never a pass.
"""

import asyncio
import contextlib
import os
import signal
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from types import FunctionType
from typing import Any

from platoon_harness.config import Secret
from platoon_harness.drivers import (
    AgentSpec,
    ApprovalRequested,
    Boundary,
    Capabilities,
    Delivery,
    Driver,
    Exited,
    GapReport,
    InputDelivered,
    ModelCall,
    Native,
    Offered,
    Ready,
    Report,
    Started,
    TurnEnded,
    TurnStarted,
    Usage,
)
from platoon_harness.drivers.levels import Check, Conformance
from platoon_harness.drivers.process import RECORD, Record, reap

from .model import FakeModel, Reply, Request, Stall, ToolCall
from .scripted import API_KEY, BASE_URL
from .tools import TOOL, FakeTools

_GRACE = 2.0
_MODEL = "fake-model"
_GOAL = "conformance goal: the first word is heliotrope"
_GIST = "conformance delivery: the second word is cinnabar"
_GATED = ToolCall("shell", {"command": "true"}, id="call_gated")

Factory = Callable[[], Driver]
Access = Callable[[FakeModel], Mapping[str, Secret]]
Garble = Callable[[Any], Awaitable[Any]]
_Needs = Callable[[Capabilities], str | None]


class _Failed(Exception):
    pass


class _Skipped(Exception):
    pass


def _expect(condition: Any, otherwise: str) -> None:
    if not condition:
        raise _Failed(otherwise)


def chat_access(model: FakeModel) -> dict[str, Secret]:
    """Model access for a harness that speaks Chat Completions, with a dummy key."""
    return {BASE_URL: Secret(f"{model.url}/v1"), API_KEY: Secret("dummy-key")}


class _Rig:
    """One check's world: a fresh model, tools and folder, and whatever drivers the check starts in it."""

    def __init__(
        self, factory: Factory, folder: Path, model: FakeModel, tools: FakeTools, access: Access, options: "_Options"
    ) -> None:
        self.factory = factory
        self.folder = folder
        self.model = model
        self.tools = tools
        self.access = access
        self.options = options
        self.driver = factory()
        self.capabilities = self.driver.describe().capabilities
        self.reports: list[Report] = []
        self.awaiting = "the driver"
        self.drivers = [self.driver]
        self._arrived = asyncio.Event()

    def _spec(self, **changes: Any) -> AgentSpec:
        bin, cwd = self.folder / "bin", self.folder / "work"
        bin.mkdir(parents=True, exist_ok=True)
        cwd.mkdir(exist_ok=True)
        fields = {
            "agent": "conformance",
            "role": "worker",
            "goal": _GOAL,
            "cwd": cwd,
            "folder": self.folder / "agent",
            "model": _MODEL,
            "tools": self.tools.binding(bin),
            "access": self.access(self.model),
        }
        return AgentSpec.model_validate({**fields, **changes})

    async def _report(self, report: Report) -> None:
        self.reports.append(report)
        self._arrived.set()

    async def start(self, **changes: Any) -> Started:
        self.awaiting = "an answer to `start`"
        return await self.driver.start(self._spec(**changes), self._report)

    async def restart(self, **changes: Any) -> Started:
        """Start again as a crash recovery would: a new instance, on the same folder."""
        self.reports.clear()
        self.driver = self.factory()
        self.drivers.append(self.driver)
        return await self.start(**changes)

    async def until[T](self, kind: type[T], where: Callable[[T], bool] = lambda _: True) -> T:
        """The first report of `kind` that holds, when it has arrived."""
        self.awaiting = f"a `{kind.__name__}` report"
        while True:
            for report in self.reports:
                if isinstance(report, kind) and where(report):
                    return report
            self._arrived.clear()
            await self._arrived.wait()

    async def call(self, index: int) -> Request:
        self.awaiting = f"model call {index + 1}"
        return await self.model.call(index)

    async def deliver(self, boundary: Boundary = "turn", *, input: str = "1") -> Delivery:
        item = Offered(ref="inbox/conformance@1", gist=_GIST)
        delivery = Delivery(input=input, boundary=boundary, text=_GIST, items=(item,))
        self.awaiting = "an answer to `deliver`"
        await self.driver.deliver(delivery)
        return delivery

    def records(self) -> list[Record]:
        found = (Record.read(path.parent) for path in self.folder.rglob(RECORD))
        return [record for record in found if record is not None]

    async def close(self) -> None:
        """Stop what this check started. What a driver failed to stop goes to `reap`, so the suite leaves no process."""
        self.model.release()
        for driver in self.drivers:
            with contextlib.suppress(Exception):
                await asyncio.wait_for(driver.stop(_GRACE), self.options.timeout)
        await reap(self.folder, _GRACE)


@dataclass(frozen=True)
class _Options:
    garble: Garble | None
    gated: ToolCall
    timeout: float


@dataclass(frozen=True)
class _Definition:
    name: str
    run: Callable[[_Rig], Awaitable[None]]
    needs: _Needs


_CHECKS: list[_Definition] = []


def _check(needs: _Needs = lambda _: None) -> Callable[[FunctionType], None]:
    """Define a check by its function. `needs` says why a harness's capabilities leave nothing to check."""

    def define(run: FunctionType) -> None:
        _CHECKS.append(_Definition(run.__name__, run, needs))

    return define


def _persistent(capabilities: Capabilities) -> str | None:
    if not capabilities.persistent:
        return "it declares no persistent session"
    return None if "turn" in capabilities.boundaries else "it declares no turn boundary"


def _mcp(capabilities: Capabilities) -> str | None:
    return None if capabilities.tool_paths & {"mcp-http", "mcp-stdio"} else "it declares no MCP path"


def _steerable(capabilities: Capabilities) -> str | None:
    if not capabilities.boundaries & {"tool", "model_call"}:
        return "it declares no boundary inside a turn"
    return _mcp(capabilities)


@_check()
async def describe_starts_nothing(rig: _Rig) -> None:
    first, second = rig.driver.describe(), rig.driver.describe()

    _expect(first == second, "two descriptions differ")
    _expect(not rig.model.requests, "describing it reached the model")
    _expect(not rig.tools.calls, "describing it reached the tools")
    _expect(not rig.records(), "describing it started a process that was recorded")


@_check()
async def ready_with_pinned_model(rig: _Rig) -> None:
    await rig.start()
    ready = await rig.until(Ready)
    if ready.effective_model is None:
        raise _Skipped("the harness does not say which model it runs")
    _expect(ready.effective_model == _MODEL, f"it runs {ready.effective_model}, and {_MODEL} was asked for")

    call = await rig.call(0)

    _expect(call.model == _MODEL, f"it asked the model for {call.model}, and {_MODEL} was asked for")


@_check(_mcp)
async def tool_in_first_request(rig: _Rig) -> None:
    await rig.start()

    _expect((await rig.call(0)).offers(TOOL), f"the first model request does not show {TOOL}")
    ready = await rig.until(Ready)
    _expect(ready.tools_visible is None or any(TOOL in tool for tool in ready.tools_visible), "`ready` hides our tool")


@_check(_persistent)
async def delivered_text_in_next_prompt(rig: _Rig) -> None:
    await rig.start()
    await rig.until(TurnEnded)
    next_call = len(rig.model.calls)

    await rig.deliver()
    await rig.until(InputDelivered, lambda delivered: delivered.input == "1")

    _expect((await rig.call(next_call)).says(_GIST), "the delivered text is not in the next prompt")


@_check()
async def turn_end_reported(rig: _Rig) -> None:
    await rig.start()
    await rig.until(TurnStarted)
    await rig.until(TurnEnded)


@_check(_persistent)
async def no_goal_takes_no_turn(rig: _Rig) -> None:
    await rig.start(goal="")
    await rig.until(Ready)

    await rig.deliver()
    await rig.until(InputDelivered)

    _expect((await rig.call(0)).says(_GIST), "its first model call came before anything was delivered")


def _interruptible(capabilities: Capabilities) -> str | None:
    return "it declares no interrupt" if capabilities.interrupt == "none" else None


@_check(_interruptible)
async def interrupt(rig: _Rig) -> None:
    rig.model.script([Stall()])
    await rig.start()
    await rig.call(0)

    await rig.driver.interrupt()
    await rig.until(TurnEnded)

    if rig.capabilities.persistent:
        rig.reports.clear()
        await rig.deliver()
        await rig.until(InputDelivered)
        _expect((await rig.call(1)).says(_GIST), "the agent did not live on past its interrupted turn")


def _resumable(capabilities: Capabilities) -> str | None:
    return None if capabilities.resume else "it declares no resume"


@_check(_resumable)
async def resume(rig: _Rig) -> None:
    started = await rig.start()
    await rig.until(TurnEnded)
    _expect(started.native, "`start` gave no native id to resume by")
    await rig.driver.stop(_GRACE)

    await rig.restart(resume=started.native)
    await rig.until(Ready)
    next_call = len(rig.model.calls)
    await rig.deliver()

    resumed = await rig.call(next_call)
    _expect(resumed.says(_GIST), "a resumed harness did not take a delivery")
    _expect(resumed.says("heliotrope"), "a resumed harness lost what came before")


def _approving(capabilities: Capabilities) -> str | None:
    return "it declares no approvals" if capabilities.approvals == "none" else None


@_check(_approving)
async def approval_answered(rig: _Rig) -> None:
    gated: Reply = rig.options.gated
    rig.model.script([gated])
    await rig.start()

    asked = await rig.until(ApprovalRequested)
    await rig.driver.answer(asked.id, "allow")

    _expect((await rig.call(1)).says(rig.options.gated.id), "the tool's result never reached the model")


@_check()
async def exit_reported(rig: _Rig) -> None:
    await rig.start()
    await rig.until(Ready)
    records = rig.records()
    if records:
        for record in records:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(record.pid, signal.SIGKILL)
    else:
        await rig.driver.stop(_GRACE)

    await rig.until(Exited)


@_check()
async def stop_leaves_no_process(rig: _Rig) -> None:
    await rig.start()
    await rig.until(Ready)
    records = rig.records()
    if not records:
        raise _Skipped("this driver starts no process of its own")

    rig.awaiting = "`stop`"
    await rig.driver.stop(_GRACE)

    alive = [record.pid for record in records if record.state() != "gone"]
    _expect(not alive, f"groups {alive} outlived `stop`")


@_check()
async def malformed_frame_is_a_gap(rig: _Rig) -> None:
    if rig.options.garble is None:
        raise _Skipped("nothing was given that makes this harness write a bad frame")
    await rig.start()
    await rig.until(Ready)

    await rig.options.garble(rig.driver)

    await rig.until(Native)
    await rig.until(GapReport, lambda gap: gap.what == "unknown_update")


@_check(_steerable)
async def steers_at_declared_boundary(rig: _Rig) -> None:
    boundary: Boundary = "tool" if "tool" in rig.capabilities.boundaries else "model_call"
    rig.model.script([[Stall(), ToolCall(TOOL, {"note": "steer"})]])
    await rig.start()
    await rig.call(0)

    await rig.deliver(boundary)
    rig.model.release()

    delivered = await rig.until(InputDelivered)
    _expect(delivered.boundary == boundary, f"it landed at {delivered.boundary}, and {boundary} was asked for")
    _expect((await rig.call(1)).says(_GIST), "the steer is not in the next prompt")


def _measuring(capabilities: Capabilities) -> str | None:
    return None if capabilities.measures else "it declares no measures"


@_check(_measuring)
async def measures_reported(rig: _Rig) -> None:
    await rig.start()
    await rig.until(TurnEnded)
    usages = [report for report in rig.reports if isinstance(report, Usage)]

    for unit in rig.capabilities.measures:
        _expect(any(getattr(usage, unit) is not None for usage in usages), f"no {unit} came with the turn")


def _exact(capabilities: Capabilities) -> str | None:
    return None if capabilities.call_ids == "call" else "it declares no id per model call"


@_check(_exact)
async def call_ids_reported(rig: _Rig) -> None:
    await rig.start()
    reported = await rig.until(ModelCall)
    call = await rig.call(0)

    _expect(reported.call_id == call.response_id, f"it said {reported.call_id}, and the model said {call.response_id}")


def _dialects(capabilities: Capabilities) -> str | None:
    return None if capabilities.dialects else "it declares no dialect"


@_check(_dialects)
async def dialects_spoken(rig: _Rig) -> None:
    await rig.start()
    await rig.until(TurnEnded)
    spoken = {call.dialect for call in rig.model.calls}

    _expect(spoken, "no model call arrived")
    _expect(spoken <= rig.capabilities.dialects, f"it spoke {sorted(map(str, spoken))}")


def _one_shot(capabilities: Capabilities) -> str | None:
    return "it declares a persistent session" if capabilities.persistent else None


@_check(_one_shot)
async def one_shot_exits(rig: _Rig) -> None:
    await rig.start()
    await rig.until(TurnEnded)
    await rig.until(Exited)


def _unproven(capabilities: Capabilities) -> str | None:
    declared = {
        "tool_timeout_s": capabilities.tool_timeout_s is not None,
        "native_children": capabilities.native_children != "none",
        "coverage": bool(capabilities.coverage),
        "sandboxes": bool(capabilities.sandboxes),
    }
    unproven = [field for field, stated in declared.items() if stated]
    return f"no check proves {', '.join(unproven)}" if unproven else "nothing else was declared"


@_check(_unproven)
async def declared_but_unproven(rig: _Rig) -> None:
    raise AssertionError("this check only ever skips, to say what the others left unproven")


async def _run(
    definition: _Definition, factory: Factory, folder: Path, access: Access, options: _Options
) -> tuple[Check, str | None]:
    """Run one check in a world of its own. Its verdict, and the harness version it saw, if it saw one."""
    version = None
    async with FakeModel() as model, FakeTools() as tools:
        rig = _Rig(factory, folder / definition.name, model, tools, access, options)
        why = definition.needs(rig.capabilities)
        if why is not None:
            return Check(name=definition.name, state="skipped", reason=why), None
        try:
            async with asyncio.timeout(options.timeout):
                await definition.run(rig)
            check = Check(name=definition.name, state="passed")
        except _Skipped as skipped:
            check = Check(name=definition.name, state="skipped", reason=str(skipped))
        except _Failed as failed:
            check = Check(name=definition.name, state="failed", reason=str(failed))
        except TimeoutError:
            check = Check(name=definition.name, state="failed", reason=f"{rig.awaiting} never came")
        except Exception as error:
            check = Check(name=definition.name, state="failed", reason=f"{type(error).__name__}: {error}")
        version = next((report.version for report in rig.reports if isinstance(report, Ready)), None)
        await rig.close()
    return check, version


async def check_driver(
    factory: Factory,
    *,
    folder: Path,
    access: Access = chat_access,
    garble: Garble | None = None,
    gated: ToolCall = _GATED,
    timeout: float = 10.0,  # noqa: ASYNC109  It bounds each check, not this call.
) -> Conformance:
    """Run every check on fresh instances of a driver, and report all failures at once, pinned to the driver and the
    harness version it reported. `levels` reads the result.

    `factory` makes one instance per check. `access` says how a harness reaches the model. `garble` makes the harness
    write a frame no parser knows, and with none that check is skipped. `gated` is a tool call this harness asks
    approval for. `timeout` bounds each check, so one wedged harness costs only its own checks.
    """
    name = factory().describe().name
    options = _Options(garble, gated, timeout)
    checks, version = [], None
    for definition in _CHECKS:
        check, seen = await _run(definition, factory, folder, access, options)
        checks.append(check)
        version = version or seen
    return Conformance(driver=name, version=version, checks=tuple(checks))
