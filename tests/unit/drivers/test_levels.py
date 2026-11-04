"""Levels: computed from what was verified, each with reasons, and claimed by nobody."""

import pytest

from platoon_harness.drivers import Capabilities
from platoon_harness.drivers.levels import Check, Conformance, Profile, levels, tool_visibility

PROFILE = Profile(driver="pi", version="1.4.0", login="gateway", tools="visible")
CAPABILITIES = Capabilities(
    tool_paths={"mcp-http", "shell"},
    call_ids="call",
    dialects={"chat"},
    native_children="none",
    coverage={"prompt": "observed", "tool_results": "observed"},
)
NEEDED = (
    "describe_starts_nothing",
    "turn_end_reported",
    "exit_reported",
    "stop_leaves_no_process",
    "stop_ends_a_running_tool",
    "malformed_frame_is_a_gap",
    "ready_with_pinned_model",
    "tool_in_first_request",
    "call_ids_reported",
)


def conformance(*checks: Check, driver="pi", version="1.4.0") -> Conformance:
    named = {check.name for check in checks}
    passed = tuple(Check(name=name, state="passed") for name in NEEDED if name not in named)
    return Conformance(driver=driver, version=version, checks=(*passed, *checks))


def test_a_harness_that_proved_everything_earns_all_three():
    earned = levels(CAPABILITIES, PROFILE, conformance())

    assert (earned.operational.state, earned.observable.state, earned.trainable.state) == ("met", "met", "met")


def test_no_result_is_unverified_rather_than_unmet():
    earned = levels(CAPABILITIES, PROFILE, None)

    assert earned.operational.state == "unverified"
    assert earned.operational.reasons == ("no conformance result for pi",)


@pytest.mark.parametrize(("driver", "version"), [("pi", "1.5.0"), ("codex", "1.4.0"), ("pi", None)])
def test_a_result_pinned_elsewhere_says_nothing_of_this_agent(driver, version):
    earned = levels(CAPABILITIES, PROFILE, conformance(driver=driver, version=version))

    assert earned.operational.state == "unverified"
    assert "conformance ran on" in earned.operational.reasons[0]


def test_a_declared_capability_counts_for_nothing_on_its_own():
    everything = Capabilities(
        persistent=True, resume=True, interrupt=True, approvals="native", call_ids="call", tool_paths={"shell"}
    )

    assert levels(everything, PROFILE, None).operational.state == "unverified"


def test_a_failed_check_is_unmet_and_named():
    earned = levels(CAPABILITIES, PROFILE, conformance(Check(name="exit_reported", state="failed", reason="silence")))

    assert earned.operational.state == "unmet"
    assert earned.operational.reasons == ("`exit_reported` failed: silence",)


def test_a_skipped_check_a_level_needs_is_no_pass():
    skipped = Check(name="stop_leaves_no_process", state="skipped", reason="no process")

    earned = levels(CAPABILITIES, PROFILE, conformance(skipped))

    assert earned.operational.state == "unverified"
    assert earned.operational.reasons == ("`stop_leaves_no_process` did not run: no process",)


def test_a_stop_nobody_saw_end_a_running_tool_is_no_pass():
    skipped = Check(name="stop_ends_a_running_tool", state="skipped", reason="nothing runs a shell command")

    earned = levels(CAPABILITIES, PROFILE, conformance(skipped))

    assert earned.operational.state == "unverified"
    assert earned.operational.reasons == ("`stop_ends_a_running_tool` did not run: nothing runs a shell command",)


def test_a_skip_of_what_a_harness_never_declared_costs_nothing():
    skipped = Check(name="resume", state="skipped", reason="it declares no resume")

    assert levels(CAPABILITIES, PROFILE, conformance(skipped)).operational.state == "met"


def test_a_failed_declared_capability_is_unmet():
    failed = Check(name="resume", state="failed", reason="it lost the past")

    assert levels(CAPABILITIES, PROFILE, conformance(failed)).operational.state == "unmet"


def test_a_check_that_never_ran_is_named():
    empty = Conformance(driver="pi", version="1.4.0", checks=())

    reasons = levels(CAPABILITIES, PROFILE, empty).operational.reasons

    assert "`describe_starts_nothing` did not run" in reasons


def test_no_path_to_our_tools_is_not_operational():
    earned = levels(Capabilities(), PROFILE, conformance())

    assert earned.operational.reasons == ("it has no path to our tools",)


def test_unverified_tools_refuse_nothing_and_are_said():
    earned = levels(CAPABILITIES, PROFILE.model_copy(update={"tools": "unverified"}), conformance())

    assert earned.operational.state == "met"
    assert earned.operational.reasons == ("tools unverified",)
    assert earned.trainable.state == "unverified"


def test_hidden_tools_fall_back_to_the_shell_when_there_is_one():
    hidden = PROFILE.model_copy(update={"tools": "hidden"})
    shell_less = CAPABILITIES.model_copy(update={"tool_paths": frozenset({"mcp-http"})})

    assert levels(CAPABILITIES, hidden, conformance()).operational.state == "met"
    assert levels(shell_less, hidden, conformance()).operational.state == "unmet"
    assert levels(CAPABILITIES, hidden, conformance()).trainable.state == "unmet"


def test_observable_says_what_it_is_blind_to():
    reasons = levels(CAPABILITIES, PROFILE, conformance()).observable.reasons

    assert "blind to shell_reads" in reasons
    assert "blind to prompt" not in reasons


def test_a_harness_blind_to_every_surface_is_not_observable():
    blind = CAPABILITIES.model_copy(update={"coverage": {}})

    assert levels(blind, PROFILE, conformance()).observable.reasons == ("it observes no surface",)


@pytest.mark.parametrize("login", ["native", "plan", "key", None])
def test_only_a_gateway_key_is_trainable(login):
    earned = levels(CAPABILITIES, PROFILE.model_copy(update={"login": login}), conformance())

    assert earned.trainable.state == "unmet"
    assert (earned.operational.state, earned.observable.state) == ("met", "met")


def test_opaque_children_a_role_allows_and_no_call_ids_are_not_trainable():
    opaque = CAPABILITIES.model_copy(update={"native_children": "opaque", "call_ids": "none"})
    allowing = PROFILE.model_copy(update={"allow_native_children": True})

    assert levels(opaque, allowing, conformance()).trainable.reasons == (
        "it cannot tie a model call to an agent",
        "its native children are opaque",
    )


def test_opaque_children_a_role_keeps_off_cost_nothing():
    opaque = CAPABILITIES.model_copy(update={"native_children": "opaque"})

    assert levels(opaque, PROFILE, conformance()).trainable.state == "met"


def test_tool_visibility_has_three_values():
    assert tool_visibility(None, ["wait"]) == "unverified"
    assert tool_visibility((), ["wait"]) == "hidden"
    assert tool_visibility(("mcp__ph__wait", "bash"), ["wait"]) == "visible"
    assert tool_visibility(("mcp__ph__wait",), ["wait", "task_claim"]) == "hidden"


def test_a_tool_is_seen_by_its_name_and_not_by_a_name_that_holds_it():
    assert tool_visibility(("wait",), ["wait"]) == "visible"
    assert tool_visibility(("mcp__other__await_all",), ["wait"]) == "hidden"


def test_with_no_tools_to_look_for_nothing_was_seen():
    assert tool_visibility((), ()) == "unverified"
    assert tool_visibility(("bash",), ()) == "unverified"
