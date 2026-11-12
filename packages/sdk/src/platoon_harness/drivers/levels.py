"""The three levels of an agent, computed from what was verified. No driver can claim one."""

import functools
import socket
from collections.abc import Iterable, Iterator, Mapping, Sequence
from typing import Literal

from pydantic import Field

from platoon_harness.extensions import DRIVERS, discover
from platoon_harness.primitives import Capabilities
from platoon_harness.schema import Model
from platoon_harness.version import __version__

from . import Login

SURFACES = ("prompt", "tool_results", "shell_reads", "files", "native_children", "compaction", "external")

CHECKED: Mapping[str, str] = {
    "claude": "platoon_harness.drivers.claude:ClaudeDriver",
    "codex": "platoon_harness.drivers.codex:CodexDriver",
    "openhands": "platoon_harness.drivers.openhands:OpenHandsDriver",
    "opencode": "platoon_harness.drivers.opencode:OpenCodeDriver",
    "pi": "platoon_harness.drivers.pi:PiDriver",
}
"""Each harness a check of ships with the SDK, which `platoon-harness doctor --check` checks where it finds it, by the
class that drives it."""

Visibility = Literal["visible", "hidden", "unverified"]
Standing = Literal["met", "unmet", "unverified"]

_Finding = tuple[Standing, str]

_STANDS_ON: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "operational": (
        (
            "describe_starts_nothing",
            "turn_end_reported",
            "exit_reported",
            "stop_leaves_no_process",
            "stop_ends_a_running_tool",
            "runs_in_its_workspace",
        ),
        (
            "delivered_text_in_next_prompt",
            "no_goal_takes_no_turn",
            "interrupt",
            "resume",
            "approval_answered",
            "denial_holds",
            "approval_shows_its_ask",
            "effort_honored_or_refused",
            "reconcile_claims_nothing_unseen",
            "steers_at_declared_boundary",
            "preamble_once_per_request",
            "native_children_off_by_default",
        ),
    ),
    "observable": (
        ("turn_end_reported", "malformed_frame_is_a_gap"),
        ("measures_reported", "call_ids_reported", "tool_item_carries_its_anchor"),
    ),
    "trainable": (
        (
            "ready_with_pinned_model",
            "tool_in_first_request",
            "call_ids_reported",
            "sealed_first_request_holds_only_ours",
            "environment_tools_in_first_request",
        ),
        (),
    ),
}
"""The checks each level stands on: those it needs passed, and those covering what a harness may leave out, which must
not fail."""

__all__ = [
    "CHECKED",
    "SURFACES",
    "Check",
    "Checks",
    "Conformance",
    "Level",
    "Levels",
    "Profile",
    "Standing",
    "Visibility",
    "implementation",
    "levels",
    "speaks_for",
    "tool_visibility",
    "unearned",
    "unmet_by",
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
    """What `check_driver` found, pinned to one driver, by the name it gave and the class that implements it, at the
    harness version it said, under one SDK, on one host, since the checks prove the driver's code and the binary
    together, where they ran."""

    driver: str
    implementation: str
    version: str | None
    sdk: str
    host: str


class Profile(Model):
    """One agent as it runs: which driver, by name and class, at which harness version, under which SDK on which host,
    on which login, whether its tools were seen, and whether its role lets its harness start agents of its own."""

    driver: str
    implementation: str
    version: str | None = None
    sdk: str = __version__
    host: str = Field(default_factory=socket.gethostname)
    login: Login | None = None
    tools: Visibility = "unverified"
    allow_native_children: bool = False


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


def _making(profile: Profile) -> str:
    """What makes a result that speaks for an agent's driver here."""
    if CHECKED.get(profile.driver) == profile.implementation:
        return "`platoon-harness doctor --check` checks it here and keeps what it found"
    return "`check_driver` checks it, and `write_conformance` keeps what it found here"


def _pin(profile: Profile, conformance: Conformance | None) -> str | None:
    """Why a result says nothing of this agent, if it does not, and what makes one that does. A version nobody said
    pins nothing, as no result can be known to have run on it."""
    making = _making(profile)
    if conformance is None:
        return f"no conformance result for {profile.driver} is kept: {making}"
    if profile.version is None:
        return f"{profile.driver} said no version, so no result can speak for it"
    if conformance.version is None:
        return f"the result kept for {conformance.driver} names no version, so it speaks for none: {making}"
    for ran, runs in (
        (f"{conformance.driver} {conformance.version}", f"{profile.driver} {profile.version}"),
        (conformance.implementation, profile.implementation),
        (f"SDK {conformance.sdk}", f"SDK {profile.sdk}"),
        (conformance.host, profile.host),
    ):
        if ran != runs:
            return f"conformance ran on {ran}, and this is {runs}: {making}"
    return None


def implementation(driver: object) -> str:
    """The class that implements a driver, by module and name, which a result is pinned to, as a name is the driver's
    own to give, and the release of each installed distribution outside the SDK whose driver entry points name the
    package of that class or of a class it is built on, which release apart from the SDK, so that an upgrade of any of
    them reads as one."""
    made = type(driver)
    releases = dict.fromkeys(filter(None, (_release(base.__module__.partition(".")[0]) for base in made.__mro__)))
    return ", ".join((f"{made.__module__}:{made.__qualname__}", *releases))


@functools.cache
def _release(package: str) -> str | None:
    """The distribution and version whose driver entry points name the import package `package`, from metadata alone,
    or None for the SDK's own and for a package no driver entry point names."""
    if package == "platoon_harness":
        return None
    held = {
        f"{component.distribution} {component.version}"
        for component in discover()
        if component.group == DRIVERS and component.value.partition(":")[0].partition(".")[0] == package
    }
    return held.pop() if len(held) == 1 else None


def speaks_for(profile: Profile, conformance: Conformance | None) -> bool:
    """Whether a result was made of the agent's driver, by name and class, at its harness version, under its SDK, on
    its host, as only such a result counts toward a level."""
    return _pin(profile, conformance) is None


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
    yield from _verified(profile, conformance, *_STANDS_ON["operational"])
    if not capabilities.tool_paths:
        yield "unmet", "it has no path to our tools"
    elif profile.tools == "hidden" and "shell" not in capabilities.tool_paths:
        yield "unmet", "it hides our tools and has no shell path to them"
    elif profile.tools == "unverified":
        yield "met", "tools unverified"


def _observable(capabilities: Capabilities, profile: Profile, conformance: Conformance | None) -> Iterator[_Finding]:
    yield from _verified(profile, conformance, *_STANDS_ON["observable"])
    blind = [surface for surface in SURFACES if capabilities.coverage.get(surface, "none") == "none"]
    if len(blind) == len(SURFACES):
        yield "unmet", "it observes no surface"
    else:
        yield from (("met", f"blind to {surface}") for surface in blind)


def _trainable(capabilities: Capabilities, profile: Profile, conformance: Conformance | None) -> Iterator[_Finding]:
    if profile.login != "gateway":
        yield "unmet", f"exact data needs a gateway key, and this login is {profile.login or 'unknown'}"
    if not capabilities.sealed:
        yield "unmet", "it has no sealed launch, so the user's own setup reaches the policy"
    if capabilities.call_ids == "none":
        yield "unmet", "it cannot tie a model call to an agent"
    if capabilities.native_children == "opaque" and profile.allow_native_children:
        yield "unmet", "its native children are opaque"
    if profile.tools == "hidden":
        yield "unmet", "our tools never reach the policy"
    elif profile.tools == "unverified":
        yield "unverified", "tools unverified"
    yield from _verified(profile, conformance, *_STANDS_ON["trainable"])


def unearned(
    profile: Profile, conformance: Conformance | None, level: Literal["operational", "observable", "trainable"]
) -> tuple[str, ...]:
    """Why a result does not prove what `level` stands on for the harness a profile names, naming what makes one that
    does, or nothing when it proves it."""
    return tuple(reason for _, reason in _verified(profile, conformance, *_STANDS_ON[level]))


def levels(capabilities: Capabilities, profile: Profile, conformance: Conformance | None) -> Levels:
    """What this agent has earned. Pure: all it knows arrives as arguments, and a capability counts only as far as a
    check that speaks for this agent proved it. A training system still decides what trains."""
    return Levels(
        operational=_level(_operational(capabilities, profile, conformance)),
        observable=_level(_observable(capabilities, profile, conformance)),
        trainable=_level(_trainable(capabilities, profile, conformance)),
    )


def unmet_by(conformance: Conformance) -> tuple[str, ...]:
    """The levels a result's failed checks leave unmet for any agent it speaks for."""
    failed = {check.name for check in conformance.failed}
    return tuple(level for level, (needed, declared) in _STANDS_ON.items() if failed & {*needed, *declared})
