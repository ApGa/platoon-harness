"""A conformance suite is worth what it catches: each check fails for the lie it exists to catch."""

import asyncio
import json
import signal
import sys

import pytest

from platoon_harness.drivers import (
    AgentSpec,
    Capabilities,
    DriverError,
    Exited,
    Item,
    ModelCall,
    Ready,
    Receipt,
    Report,
    Reporter,
    Started,
    TurnEnded,
    Usage,
)
from platoon_harness.drivers.exec import ExecDriver
from platoon_harness.drivers.wire import WireDriver
from platoon_harness.testing import ScriptedDriver, ToolCall, check_driver, every_turn_asks_the_model
from platoon_harness.testing.conformance import _CHECKS
from platoon_harness.testing.model import OUTPUT_TOKENS

pytestmark = pytest.mark.timeout(60)

TIMEOUT = 0.3


class Filtered(ScriptedDriver):
    """A scripted harness that hides or changes what it reports."""

    def __init__(self, change=lambda report: report, **options) -> None:
        super().__init__(every_turn_asks_the_model(), **options)
        self._change = change

    async def start(self, spec: AgentSpec, report: Reporter) -> Started:
        async def changed(item: Report) -> None:
            if (kept := self._change(item)) is not None:
                await report(kept)

        return await super().start(spec, changed)


def without(kind):
    return lambda report: None if isinstance(report, kind) else report


async def check(factory, tmp_path, **options):
    return await check_driver(factory, folder=tmp_path, timeout=TIMEOUT, **options)


def test_every_check_a_level_reads_exists():
    names = {definition.name for definition in _CHECKS}

    assert {
        "describe_starts_nothing",
        "turn_end_reported",
        "exit_reported",
        "stop_leaves_no_process",
        "malformed_frame_is_a_gap",
        "ready_with_pinned_model",
        "tool_in_first_request",
        "call_ids_reported",
        "delivered_text_in_next_prompt",
        "no_goal_takes_no_turn",
        "interrupt",
        "resume",
        "approval_answered",
        "steers_at_declared_boundary",
        "measures_reported",
        "preamble_once_per_request",
        "tool_item_carries_its_anchor",
        "stop_ends_a_running_tool",
    } <= names


async def test_every_failure_is_reported_at_once(tmp_path):
    class Silent(Filtered):
        def __init__(self) -> None:
            super().__init__(without((TurnEnded, Usage, ModelCall)))

    result = await check(Silent, tmp_path)

    assert {check.name for check in result.failed} >= {
        "turn_end_reported",
        "measures_reported",
        "call_ids_reported",
        "dialects_spoken",
        "delivered_text_in_next_prompt",
        "resume",
    }


async def test_a_failure_says_what_never_came(tmp_path):
    result = await check(lambda: Filtered(without(TurnEnded)), tmp_path)

    assert result.get("turn_end_reported").reason == "a `TurnEnded` report never came"


async def test_a_driver_that_starts_something_to_describe_itself_fails(tmp_path):
    class Eager(ScriptedDriver):
        def __init__(self) -> None:
            super().__init__(every_turn_asks_the_model())
            self._descriptions = 0

        def describe(self):
            self._descriptions += 1
            return self._info.model_copy(update={"version": str(self._descriptions)})

    result = await check(Eager, tmp_path)

    assert result.get("describe_starts_nothing").state == "failed"


async def test_a_driver_that_reports_another_model_fails(tmp_path):
    def wrong(report):
        return report.model_copy(update={"effective_model": "another"}) if isinstance(report, Ready) else report

    result = await check(lambda: Filtered(wrong), tmp_path)

    assert result.get("ready_with_pinned_model").reason == "it runs another, and fake-model was asked for"


async def test_a_driver_that_asks_for_another_model_than_it_reports_fails(tmp_path):
    class Unpinned(Filtered):
        async def start(self, spec, report):
            self._real = spec
            return await super().start(spec, report)

        async def _complete(self):
            self._spec = self._spec.model_copy(update={"model": "hosted-default"})
            return await super()._complete()

    result = await check(Unpinned, tmp_path)

    assert result.get("ready_with_pinned_model").state == "failed"
    assert "hosted-default" in result.get("ready_with_pinned_model").reason


async def test_an_unknown_effective_model_is_skipped_not_passed(tmp_path):
    def unknown(report):
        return report.model_copy(update={"effective_model": None}) if isinstance(report, Ready) else report

    result = await check(lambda: Filtered(unknown), tmp_path)

    assert result.get("ready_with_pinned_model").state == "skipped"


async def test_tools_that_never_reach_the_model_fail_however_connected(tmp_path):
    class Hidden(Filtered):
        async def _list_tools(self):
            found = await super()._list_tools()
            self._tools = []
            return found

    result = await check(Hidden, tmp_path)

    assert result.get("tool_in_first_request").reason == "the first model request does not show conformance_ping"


async def test_a_delivery_that_never_reaches_the_prompt_fails(tmp_path):
    class Forgetful(Filtered):
        async def _land(self, delivery, evidence):
            await super()._land(delivery, evidence)
            self._messages.pop()

    result = await check(Forgetful, tmp_path)

    assert result.get("delivered_text_in_next_prompt").reason == "the delivered text is not in the next prompt"


async def test_a_turn_taken_on_no_goal_fails(tmp_path):
    class Restless(Filtered):
        async def start(self, spec: AgentSpec, report: Reporter) -> Started:
            return await super().start(spec.model_copy(update={"goal": spec.goal or "carry on"}), report)

    result = await check(Restless, tmp_path)

    assert result.get("no_goal_takes_no_turn").reason == "its first model call came before anything was delivered"


async def test_an_interrupt_that_stops_nothing_fails(tmp_path):
    class Stubborn(Filtered):
        async def interrupt(self):
            return Receipt(boundary="turn")

    result = await check(Stubborn, tmp_path)

    assert result.get("interrupt").state == "failed"


async def test_an_interrupt_reported_as_anything_else_fails(tmp_path):
    def stopped(report):
        return TurnEnded(reason="stopped") if isinstance(report, TurnEnded) else report

    result = await check_driver(lambda: Filtered(stopped), folder=tmp_path, timeout=5)

    said = result.get("interrupt")
    assert (said.state, said.reason) == (
        "failed",
        "it ended its turn `stopped`, and an interrupt must say `interrupted`",
    )


async def test_an_interrupt_that_ends_the_agent_fails(tmp_path):
    class Fatal(Filtered):
        async def interrupt(self):
            receipt = await super().interrupt()
            self._capabilities = self._capabilities.model_copy(update={"persistent": False})
            self._exited = True
            return receipt

    result = await check(Fatal, tmp_path)

    assert "DriverError" in result.get("interrupt").reason


async def test_a_resume_that_loses_the_past_fails(tmp_path):
    class Amnesiac(Filtered):
        async def start(self, spec, report):
            started = await super().start(spec, report)
            if spec.resume is not None:
                self._messages = []
            return started

    result = await check(Amnesiac, tmp_path)

    assert result.get("resume").reason == "a resumed harness lost what came before"


async def test_an_approval_that_never_reaches_the_model_fails(tmp_path):
    class Deaf(Filtered):
        async def answer(self, approval, verdict):
            pass

    result = await check(Deaf, tmp_path)

    assert result.get("approval_answered").state == "failed"


async def test_a_harness_that_never_says_it_exited_fails(tmp_path):
    result = await check(lambda: Filtered(without(Exited)), tmp_path)

    assert result.get("exit_reported").state == "failed"


async def test_a_call_id_that_is_not_the_model_s_fails(tmp_path):
    def invented(report):
        return report.model_copy(update={"call_id": "invented"}) if isinstance(report, ModelCall) else report

    result = await check(lambda: Filtered(invented), tmp_path)

    assert "invented" in result.get("call_ids_reported").reason


async def test_a_dialect_it_did_not_declare_fails(tmp_path):
    def declaring():
        capabilities = ScriptedDriver().describe().capabilities
        return Filtered(capabilities=capabilities.model_copy(update={"dialects": frozenset({"messages"})}))

    result = await check(declaring, tmp_path)

    assert result.get("dialects_spoken").reason == "it spoke ['chat']"


async def test_a_steer_at_a_boundary_it_does_not_honor_fails(tmp_path):
    class Tardy(Filtered):
        async def _land_steers(self):
            pass

    result = await check(Tardy, tmp_path)

    assert result.get("steers_at_declared_boundary").state == "failed"


async def test_a_one_shot_that_lives_on_fails(tmp_path):
    def declaring():
        capabilities = ScriptedDriver().describe().capabilities
        return Filtered(without(Exited), capabilities=capabilities.model_copy(update={"persistent": False}))

    result = await check(declaring, tmp_path)

    assert result.get("one_shot_exits").state == "failed"


async def test_a_process_left_behind_fails(tmp_path):
    class Leaky(ExecDriver):
        async def stop(self, grace):
            pass

    result = await check(lambda: Leaky(["sleep", "100"]), tmp_path)

    assert result.get("stop_leaves_no_process").state == "failed"
    assert not list(tmp_path.rglob("proc.json"))


class Shelling(ScriptedDriver):
    """A harness that really runs a shell tool, and that may or may not end it in `stop`."""

    def __init__(self, ends_it: bool) -> None:
        super().__init__(every_turn_asks_the_model())
        self._ends_it = ends_it
        self._tool: asyncio.subprocess.Process | None = None

    async def _run_call(self, call, call_id):
        self._tool = await asyncio.create_subprocess_shell(json.loads(call["function"]["arguments"])["command"])
        await self._tool.wait()
        return {"role": "tool", "tool_call_id": call["id"], "content": ""}

    async def stop(self, grace):
        if self._ends_it and self._tool is not None:
            self._tool.kill()
        await super().stop(grace)


def shell(command):
    return ToolCall("shell", {"command": command})


async def test_a_stop_that_ends_a_running_shell_tool_passes(tmp_path):
    result = await check_driver(lambda: Shelling(True), folder=tmp_path, shell=shell, timeout=5)

    assert result.get("stop_ends_a_running_tool").state == "passed"


async def test_a_folder_with_a_space_fails_no_good_driver(tmp_path):
    result = await check_driver(lambda: Shelling(True), folder=tmp_path / "a b", shell=shell, timeout=5)

    assert result.get("stop_ends_a_running_tool").state == "passed"


async def test_a_shell_tool_that_outlives_stop_fails_and_is_ended(tmp_path):
    drivers: list[Shelling] = []

    def leaky() -> Shelling:
        drivers.append(Shelling(False))
        return drivers[-1]

    result = await check_driver(leaky, folder=tmp_path, shell=shell, timeout=2)

    check = result.get("stop_ends_a_running_tool")
    assert (check.state, check.reason) == ("failed", "the end of the running shell tool never came")
    ran = [driver._tool for driver in drivers if driver._tool is not None]
    assert -signal.SIGKILL in [await tool.wait() for tool in ran]


async def test_a_stop_during_a_tool_is_a_skip_with_nothing_to_run_it(tmp_path):
    result = await check(lambda: ScriptedDriver(every_turn_asks_the_model()), tmp_path)

    assert result.get("stop_ends_a_running_tool").state == "skipped"


async def test_a_preamble_sent_again_each_turn_fails(tmp_path):
    class Repeating(Filtered):
        async def _land(self, delivery, evidence):
            await super()._land(delivery, evidence)
            self._messages.append({"role": "user", "content": self._spec.instructions})

    result = await check(Repeating, tmp_path)

    assert result.get("preamble_once_per_request").reason == "the preamble came [1, 1, 2] times in its requests"


async def test_a_preamble_that_never_reaches_a_request_fails(tmp_path):
    class Dropping(Filtered):
        async def start(self, spec, report):
            return await super().start(spec.model_copy(update={"instructions": None}), report)

    result = await check(Dropping, tmp_path)

    assert result.get("preamble_once_per_request").state == "failed"


class Anchored(Filtered):
    """A harness whose MCP client names each call, as Claude Code does."""

    async def _mcp(self, method, params):
        meta = {"_meta": {"claudecode/toolUseId": "toolu_1"}} if method == "tools/call" else {}
        return await super()._mcp(method, {**params, **meta})


async def test_an_item_that_carries_the_anchor_passes(tmp_path):
    def anchored(report):
        return report.model_copy(update={"native_id": "toolu_1"}) if isinstance(report, Item) else report

    result = await check(lambda: Anchored(anchored), tmp_path)

    assert result.get("tool_item_carries_its_anchor").state == "passed"


async def test_an_item_with_another_id_than_the_anchor_fails(tmp_path):
    result = await check(Anchored, tmp_path)

    assert result.get("tool_item_carries_its_anchor").state == "failed"
    assert "toolu_1" in result.get("tool_item_carries_its_anchor").reason


async def test_a_harness_with_no_anchor_is_a_skip_and_no_pass(tmp_path):
    result = await check(lambda: ScriptedDriver(every_turn_asks_the_model()), tmp_path)

    assert result.get("tool_item_carries_its_anchor").state == "skipped"


async def test_a_tool_item_that_names_no_model_call_fails(tmp_path):
    def unlinked(report):
        return report.model_copy(update={"call_id": None}) if isinstance(report, Item) else report

    result = await check(lambda: Filtered(unlinked), tmp_path)

    assert result.get("call_ids_reported").reason == "no item names the model call that made it"


async def test_usage_of_a_call_that_names_no_call_fails(tmp_path):
    def unlinked(report):
        return report.model_copy(update={"call_id": None}) if isinstance(report, Usage) else report

    result = await check(lambda: Filtered(unlinked), tmp_path)

    assert result.get("call_ids_reported").reason == "usage of one call does not name it"


async def test_tokens_that_leave_out_input_fail(tmp_path):
    def outputs_only(report):
        return report.model_copy(update={"tokens": OUTPUT_TOKENS}) if isinstance(report, Usage) else report

    result = await check(lambda: Filtered(outputs_only), tmp_path)

    assert "it counted 3 tokens" in result.get("measures_reported").reason


async def test_a_garbled_frame_nobody_reports_fails(tmp_path):
    async def nothing_happens(driver) -> None:
        pass

    result = await check(lambda: ScriptedDriver(every_turn_asks_the_model()), tmp_path, garble=nothing_happens)

    assert result.get("malformed_frame_is_a_gap").state == "failed"


async def test_unsupported_is_a_skip_with_a_reason_never_a_pass(tmp_path):
    result = await check(lambda: ScriptedDriver(every_turn_asks_the_model(), capabilities=Capabilities()), tmp_path)

    for name, reason in {
        "tool_in_first_request": "it declares no MCP path",
        "delivered_text_in_next_prompt": "it declares no persistent session",
        "interrupt": "it declares no interrupt",
        "resume": "it declares no resume",
        "approval_answered": "it declares no approvals",
        "steers_at_declared_boundary": "it declares no boundary inside a turn",
        "measures_reported": "it declares no measures",
        "call_ids_reported": "it declares no id per model call",
        "dialects_spoken": "it declares no dialect",
    }.items():
        assert (result.get(name).state, result.get(name).reason) == ("skipped", reason)


async def test_what_no_check_proves_is_named(tmp_path):
    capabilities = Capabilities(tool_timeout_s=60.0, native_children="observed", sandboxes={"read-only"})

    result = await check(lambda: ScriptedDriver(capabilities=capabilities), tmp_path)

    assert result.get("declared_but_unproven").state == "skipped"
    assert result.get("declared_but_unproven").reason == "no check proves tool_timeout_s, native_children, sandboxes"


async def test_a_wedged_driver_costs_each_check_its_timeout_and_no_more(tmp_path):
    class Wedged(ScriptedDriver):
        async def start(self, spec, report):
            await asyncio.Event().wait()

        async def stop(self, grace):
            await asyncio.Event().wait()

    loop = asyncio.get_running_loop()
    started = loop.time()

    result = await check_driver(Wedged, folder=tmp_path, timeout=0.01)

    assert loop.time() - started < 45
    assert result.get("turn_end_reported").reason == "an answer to `start` never came"


async def test_the_pin_is_the_version_the_harness_reported(tmp_path):
    result = await check(lambda: Filtered(version="9.9"), tmp_path)

    assert (result.driver, result.version) == ("scripted", "9.9")


async def test_a_program_that_is_no_driver_fails_its_checks_and_ends(tmp_path):
    script = tmp_path / "broken.py"
    script.write_text("import sys\nprint('hello, no protocol here', flush=True)\nsys.stdin.read()\n")

    with pytest.raises(DriverError, match="did not describe itself"):
        await check(lambda: WireDriver([sys.executable, "-I", str(script)]), tmp_path)
