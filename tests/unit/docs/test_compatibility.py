"""The compatibility page says of our own drivers and dependencies only what holds: each driver's state is the one
STATUS gives it, and each pin it spells is one the lock holds."""

import re
import tomllib

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
from packaging.version import Version

from .support import ROOT

PAGE = (ROOT / "docs" / "reference" / "compatibility.md").read_text()
STATUS = (ROOT / "docs" / "STATUS.md").read_text()
DRIVERS = {
    "`claude`": "The `claude` driver",
    "`codex`": "The `codex` driver",
    "`pi`": "The `pi` driver",
    "`openhands`": "OpenHands as a wire worker",
    "ACP": "The ACP driver",
    "`opencode`": "The `opencode` driver",
    "`prime`": "The `prime` driver",
    "`exec`": "The `exec` driver",
}
"""Each driver as the page's Driver status table names it, and how its row in STATUS begins."""
OPERATOR = r"(?:===|==|~=|!=|<=|>=|<|>)\d"
PIN = re.compile(rf"`([A-Za-z0-9][\w.-]*(?:\[[\w,-]+\])?{OPERATOR}[^`]*)`")
RANGE = re.compile(rf"`{OPERATOR}[^`]*`")
EXTRA = re.compile(r"`\[([\w-]+)\]` extra")


def cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def driver_states() -> dict[str, str]:
    """Each driver of the page's Driver status table, and its state there."""
    table = PAGE.split("\n### Driver status\n", 1)[1].split("\n### ", 1)[0]
    rows = [cells(line) for line in table.splitlines() if line.startswith("|")][2:]
    return {row[0]: row[3] for row in rows}


def status_state(begins: str) -> str:
    """The state of the one row of STATUS that begins so."""
    [line] = [line for line in STATUS.splitlines() if line.startswith(f"| {begins}")]
    return cells(line)[1]


def held(pin: Requirement) -> bool:
    """Whether the lock holds a version of what `pin` names that meets it."""
    lock = tomllib.loads((ROOT / "uv.lock").read_text())
    versions = {canonicalize_name(package["name"]): package.get("version") for package in lock["package"]}
    version = versions.get(canonicalize_name(pin.name))
    return version is not None and pin.specifier.contains(Version(version), prereleases=True)


def extras() -> set[str]:
    """Every extra platoon-harness declares."""
    return set(tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["optional-dependencies"])


def test_each_driver_s_state_on_the_compatibility_page_is_the_one_status_gives():
    states = driver_states()

    assert states.keys() == DRIVERS.keys()
    assert states == {driver: status_state(begins) for driver, begins in DRIVERS.items()}


def test_the_compatibility_page_names_no_pin_the_lock_does_not_hold():
    """A pin is spelled as a requirement, such as `swarmchat==0.1.0`, which the version the lock holds meets. A
    dependency's own range spelled so is held to the lock too, as `litellm`'s is, which `openhands-sdk` asks and the
    page says is not ours. A range that names no distribution pins nothing anyone can check, and an extra the page
    names is one a package declares."""
    pins = [Requirement(text) for text in PIN.findall(PAGE)]
    named = {extra for pin in pins for extra in pin.extras} | set(EXTRA.findall(PAGE))

    assert pins
    assert [str(pin) for pin in pins if not held(pin)] == []
    assert RANGE.findall(PAGE) == []
    assert named - extras() == set()
