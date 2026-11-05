"""The conformance suite, run on every driver that exists."""

import sys
from pathlib import Path

import pytest

from platoon_harness.drivers import Capabilities, Delivery, Offered
from platoon_harness.drivers.exec import ExecDriver
from platoon_harness.drivers.levels import Conformance, Profile, implementation, levels
from platoon_harness.drivers.wire import WireDriver
from platoon_harness.testing import SHELL, ScriptedDriver, ToolCall, check_driver, every_turn_asks_the_model

pytestmark = pytest.mark.timeout(120)

HERE = Path(__file__).parent
ONE_SHOT_SKIPS = {
    "delivered_text_in_next_prompt",
    "no_goal_takes_no_turn",
    "tool_in_first_request",
    "ready_with_pinned_model",
    "resume",
    "approval_answered",
    "malformed_frame_is_a_gap",
    "steers_at_declared_boundary",
    "measures_reported",
    "call_ids_reported",
    "dialects_spoken",
    "declared_but_unproven",
    "preamble_once_per_request",
    "tool_item_carries_its_anchor",
    "stop_ends_a_running_tool",
    "runs_in_its_workspace",
    "sealed_first_request_holds_only_ours",
    "environment_tools_in_first_request",
    "unset_model_refused",
    "native_children_off_by_default",
    "native_child_seen",
    "denial_holds",
    "effort_honored_or_refused",
    "reconcile_claims_nothing_unseen",
}
SCRIPTED_SKIPS = {
    "one_shot_exits",
    "declared_but_unproven",
    "tool_item_carries_its_anchor",
    "native_children_off_by_default",
    "native_child_seen",
}


def shell(command: str) -> ToolCall:
    """The scripted harness's own shell tool, which runs `command` once allowed."""
    return ToolCall(SHELL, {"command": command})


def states(result: Conformance) -> dict[str, str]:
    return {check.name: check.state for check in result.checks}


def assert_nothing_failed(result: Conformance) -> None:
    assert result.failed == (), str(result)


async def test_the_scripted_driver_conforms_in_this_process(tmp_path):
    result = await check_driver(lambda: ScriptedDriver(every_turn_asks_the_model()), folder=tmp_path, shell=shell)

    assert_nothing_failed(result)
    assert (result.driver, result.version) == ("scripted", "1")
    skipped = {check.name for check in result.checks if check.state == "skipped"}
    assert skipped == {*SCRIPTED_SKIPS, "stop_leaves_no_process", "malformed_frame_is_a_gap"}


@pytest.mark.timeout(240)  # Every check starts a program of its own, the shell's two among them.
async def test_a_wire_driver_conforms_across_a_process(tmp_path):
    command = [sys.executable, str(HERE / "wire_program.py")]

    async def garble(driver: WireDriver) -> None:
        item = Offered(ref="inbox/ada@1", gist="anything")
        await driver.deliver(Delivery(input="garble", boundary="turn", text=item.gist, items=(item,)))

    result = await check_driver(lambda: WireDriver(command), folder=tmp_path, garble=garble, shell=shell, timeout=20)

    assert_nothing_failed(result)
    assert (result.driver, result.version) == ("wire-scripted", "1")
    skipped = {check.name for check in result.checks if check.state == "skipped"}
    assert skipped == SCRIPTED_SKIPS
    profile = Profile(driver="wire-scripted", implementation=implementation(WireDriver(command)), version="1")
    earned = levels(WireDriver(command).describe().capabilities, profile, result)
    assert earned.operational.state == "met", earned.operational.reasons


async def test_the_exec_driver_conforms_as_far_as_a_one_shot_can(tmp_path):
    command = [sys.executable, "-I", str(HERE / "one_shot.py"), "{goal}"]

    result = await check_driver(lambda: ExecDriver(command), folder=tmp_path)

    assert_nothing_failed(result)
    assert (result.driver, result.version) == ("exec", None)
    assert {check.name for check in result.checks if check.state == "skipped"} == ONE_SHOT_SKIPS
    assert states(result)["one_shot_exits"] == "passed"


async def test_a_conformance_result_earns_only_what_it_proved(tmp_path):
    result = await check_driver(lambda: ScriptedDriver(every_turn_asks_the_model()), folder=tmp_path)
    capabilities = ScriptedDriver().describe().capabilities

    scripted = implementation(ScriptedDriver())
    profile = Profile(driver="scripted", implementation=scripted, version="1", login="key", tools="visible")
    earned = levels(capabilities, profile, result)

    assert earned.operational.state == "unverified"
    assert "stop_leaves_no_process" in earned.operational.reasons[0]
    assert earned.trainable.state == "unmet"
    assert Capabilities() != capabilities
