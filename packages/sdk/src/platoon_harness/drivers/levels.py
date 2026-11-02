"""The three levels of an agent, computed from what was verified. No driver can claim one."""

from collections.abc import Iterable, Iterator, Sequence
from typing import Literal

from platoon_harness.primitives import Capabilities
from platoon_harness.schema import Model

from . import Login

SURFACES = ("prompt", "tool_results", "shell_reads", "files", "native_children", "compaction", "external")

Visibility = Literal["visible", "hidden", "unverified"]
Standing = Literal["met", "unmet", "unverified"]

_Finding = tuple[Standing, str]

__all__ = [
    "SURFACES",
    "Check",
    "Checks",
    "Conformance",
    "Level",
    "Levels",
    "Profile",
    "Standing",
    "Visibility",
    "levels",
    "tool_visibility",
]


class Check(Model):
    """One named check. A skipped check is no pass, and `reason` says why it did not run."""

    name: str
    state: Literal["passed", "failed", "skipped"]
    reason: str = ""


class Checks(Model):
    """Named checks, every failure at once."""

    checks: tuple[Check, ...]

    @property
    def failed(self) -> tuple[Check, ...]:
        return tuple(check for check in self.checks if check.state == "failed")

    def get(self, name: str) -> Check | None:
        return next((check for check in self.checks if check.name == name), None)

    def __str__(self) -> str:
        lines = (f"{check.state:8}{check.name}{f': {check.reason}' if check.reason else ''}" for check in self.checks)
        return "\n".join(lines)


class Conformance(Checks):
    """What `check_driver` found, pinned to one driver at one harness version."""

    driver: str
    version: str | None


class Profile(Model):
    """One agent as it runs: which driver at which harness version, on which login, and whether its tools were seen."""

    driver: str
    version: str | None = None
    login: Login | None = None
    tools: Visibility = "unverified"


class Level(Model):
    """Whether a level holds, and why, or why not. `unverified` is not `unmet`: nobody has looked."""

    state: Standing
    reasons: tuple[str, ...] = ()


class Levels(Model):
    operational: Level
    observable: Level
    trainable: Level


def tool_visibility(shown: tuple[str, ...] | None, ours: Sequence[str]) -> Visibility:
    """Whether a harness shows our tools. `shown` comes from `ready`, and is None unless it was observed. A harness may
    prefix a name with `mcp__<ns>__`, so a tool is seen by its name or that ending. With no tools to look for, nothing
    was seen."""
    if shown is None or not ours:
        return "unverified"
    seen = all(any(name == tool or name.endswith(f"__{tool}") for name in shown) for tool in ours)
    return "visible" if seen else "hidden"


def _level(findings: Iterable[_Finding]) -> Level:
    found = tuple(findings)
    for state in ("unmet", "unverified"):
        if any(standing == state for standing, _ in found):
            return Level(state=state, reasons=tuple(reason for standing, reason in found if standing == state))
    return Level(state="met", reasons=tuple(reason for _, reason in found))


def _pin(profile: Profile, conformance: Conformance | None) -> str | None:
    """Why a result says nothing of this agent, if it does not."""
    if conformance is None:
        return f"no conformance result for {profile.driver}"
    pin = (conformance.driver, conformance.version)
    if pin != (profile.driver, profile.version):
        return f"conformance ran on {pin[0]} {pin[1]}, and this is {profile.driver} {profile.version}"
    return None


def _verified(
    profile: Profile, conformance: Conformance | None, needed: Iterable[str], declared: Iterable[str] = ()
) -> Iterator[_Finding]:
    """`needed` checks must have passed. `declared` ones cover what a harness may leave out, so they must not fail."""
    if (unpinned := _pin(profile, conformance)) is not None:
        yield "unverified", unpinned
        return
    assert conformance is not None
    for name in needed:
        check = conformance.get(name)
        if check is None or check.state == "skipped":
            yield "unverified", f"`{name}` did not run{f': {check.reason}' if check else ''}"
    for check in conformance.failed:
        if check.name in (*needed, *declared):
            yield "unmet", f"`{check.name}` failed: {check.reason}"


def _operational(capabilities: Capabilities, profile: Profile, conformance: Conformance | None) -> Iterator[_Finding]:
    yield from _verified(
        profile,
        conformance,
        (
            "describe_starts_nothing",
            "turn_end_reported",
            "exit_reported",
            "stop_leaves_no_process",
            "stop_ends_a_running_tool",
        ),
        (
            "delivered_text_in_next_prompt",
            "no_goal_takes_no_turn",
            "interrupt",
            "resume",
            "approval_answered",
            "steers_at_declared_boundary",
            "preamble_once_per_request",
        ),
    )
    if not capabilities.tool_paths:
        yield "unmet", "it has no path to our tools"
    elif profile.tools == "hidden" and "shell" not in capabilities.tool_paths:
        yield "unmet", "it hides our tools and has no shell path to them"
    elif profile.tools == "unverified":
        yield "met", "tools unverified"


def _observable(capabilities: Capabilities, profile: Profile, conformance: Conformance | None) -> Iterator[_Finding]:
    yield from _verified(
        profile,
        conformance,
        ("turn_end_reported", "malformed_frame_is_a_gap"),
        ("measures_reported", "call_ids_reported", "tool_item_carries_its_anchor"),
    )
    blind = [surface for surface in SURFACES if capabilities.coverage.get(surface, "none") == "none"]
    if len(blind) == len(SURFACES):
        yield "unmet", "it observes no surface"
    else:
        yield from (("met", f"blind to {surface}") for surface in blind)


def _trainable(capabilities: Capabilities, profile: Profile, conformance: Conformance | None) -> Iterator[_Finding]:
    if profile.login != "gateway":
        yield "unmet", f"exact data needs a gateway key, and this login is {profile.login or 'unknown'}"
    if capabilities.call_ids == "none":
        yield "unmet", "it cannot tie a model call to an agent"
    if capabilities.native_children == "opaque":
        yield "unmet", "its native children are opaque"
    if profile.tools == "hidden":
        yield "unmet", "our tools never reach the policy"
    elif profile.tools == "unverified":
        yield "unverified", "tools unverified"
    yield from _verified(
        profile, conformance, ("ready_with_pinned_model", "tool_in_first_request", "call_ids_reported")
    )


def levels(capabilities: Capabilities, profile: Profile, conformance: Conformance | None) -> Levels:
    """What this agent has earned. Pure: all it knows arrives as arguments, and a capability counts only as far as a
    check pinned to this driver and this version proved it. Platoon still decides eligibility."""
    return Levels(
        operational=_level(_operational(capabilities, profile, conformance)),
        observable=_level(_observable(capabilities, profile, conformance)),
        trainable=_level(_trainable(capabilities, profile, conformance)),
    )
