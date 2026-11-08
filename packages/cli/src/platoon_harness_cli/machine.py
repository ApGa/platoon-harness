"""What this machine has: the harnesses on its PATH and their logins, where sessions live, and what is installed."""

import asyncio
import os
import re
import shutil
import socket
from collections.abc import Collection
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Self

from cyclopts import App

from platoon_harness import ConfigError
from platoon_harness.config import PROJECT_FILE
from platoon_harness.drivers import Driver, DriverError
from platoon_harness.drivers.levels import CHECKED, Conformance, implementation, unmet_by
from platoon_harness.drivers.openhands import OpenHandsDriver, worker
from platoon_harness.drivers.process import status
from platoon_harness.extensions import DRIVERS, EXTENSIONS, Installed, check_installed, discover, load
from platoon_harness.kernel import filesystem
from platoon_harness.runtime.paths import (
    CONFORMANCE,
    HOME_VARIABLE,
    find_root,
    read_conformance,
    socket_path,
    write_conformance,
)
from platoon_harness.schema import Problem, dumps
from platoon_harness.testing import check_harness
from platoon_harness.version import __version__ as sdk_version

from . import __version__
from .exits import CONFIGURATION, REFUSED
from .ops import commandless
from .output import note, safe, say, shown

_NODE = (22, 19)
"""The oldest Node that runs pi, as compatibility.md says."""
_LABELS = {DRIVERS: "driver", EXTENSIONS: "extension"}


def harnesses() -> list[tuple[str, Driver]]:
    """Each installed driver that names a harness, which by the naming law is a command of that name, or a library, as
    `openhands` is. A driver that needs a command of its own, as `exec` and `wire` do, names none."""
    found = []
    for name in Installed(DRIVERS):
        try:
            found.append((name, load(DRIVERS, name)()))
        except TypeError:
            continue
    return found


def _first_line(command: list[str]) -> str | None:
    done = status(command, os.environ)
    if done is None:
        return None
    return done.stdout.decode(errors="replace").strip().partition("\n")[0] or None


def _harness(name: str, driver: Driver, root: Path) -> dict[str, Any]:
    """What a harness says of itself: its version from `--version`, and the kind of its login from its own status
    command, which is all of what it said that is kept, or why it is not here; and what its checks found, as kept."""
    found: dict[str, Any]
    if isinstance(driver, OpenHandsDriver):
        found = _openhands(name)
    elif shutil.which(name) is None:
        found = {"name": name, "found": False, "reason": "not on PATH"}
    else:
        found = {"name": name, "found": True, "version": _first_line([name, "--version"]), "login": _login(driver)}
    if not found["found"]:
        return found
    return {**found, "checked": _checked(read_conformance(root, name), found["version"], implementation(driver))}


def _checked(result: Conformance | None, version: str | None, made_by: str) -> dict[str, Any] | None:
    """What a kept result says, by what it was made on, and whether that is what runs here, `current`: the driver's
    class, this SDK, this host and a harness version among the words the binary's version says, or None when the binary
    said none. None when none is kept."""
    if result is None:
        return None
    states = [check.state for check in result.checks]
    pinned = (result.implementation, result.sdk, result.host)
    here = result.version is not None and pinned == (made_by, sdk_version, socket.gethostname())
    return {
        "version": result.version,
        "sdk": result.sdk,
        "host": result.host,
        "current": None if version is None else here and result.version in version.split(),
        "passed": states.count("passed"),
        "failed": [check.name for check in result.failed],
        "skipped": states.count("skipped"),
        "unmet": list(unmet_by(result)),
    }


def _check(found: list[dict[str, Any]], root: Path) -> None:
    """Check each harness found that the SDK ships a check of, against a model of ours and on no account, and keep what
    its checks found under the root, where the runtime reads it at every launch and resume, beside the folder the checks
    ran in, whose logs a failed check names, until the next check of that harness. A check that cannot run, or a
    harness that says no version, which no result could speak for, keeps nothing and leaves what was kept, and says
    why."""
    for harness in found:
        if not harness["found"] or harness["name"] not in CHECKED:
            continue
        name = harness["name"]
        note(f"checking {name} against a model of ours, which takes a few minutes and no account")
        folder = root / CONFORMANCE / name
        shutil.rmtree(folder, ignore_errors=True)
        folder.mkdir(mode=0o700, parents=True)
        try:
            result = asyncio.run(check_harness(name, folder))
        except DriverError as error:
            harness["unchecked"] = f"its check could not run: {error}"
            continue
        if result.version is None:
            harness["unchecked"] = "it said no version, so what its checks found would speak for no binary"
            continue
        write_conformance(root, result)
        harness["checked"] = _checked(result, harness["version"], CHECKED[name])


def _openhands(name: str) -> dict[str, Any]:
    """OpenHands, from the metadata of the SDK's `openhands` extra on this interpreter, which is the worker's. Its login
    is unknown, as it keeps none, and only a role's auth profile gives it a key."""
    try:
        return {"name": name, "found": True, "version": worker.sdk_version(), "login": None}
    except DriverError as error:
        return {"name": name, "found": False, "reason": str(error)}


def _login(driver: Driver) -> str | None:
    """The kind of login a harness says it has, or None if it cannot tell."""
    try:
        return driver.describe().login
    except DriverError:
        return None


def _node() -> dict[str, Any]:
    version = _first_line(["node", "--version"])
    found = re.match(r"v?(\d+)\.(\d+)", version or "")
    return {"version": version, "enough": bool(found) and (int(found[1]), int(found[2])) >= _NODE}


def _root() -> dict[str, Any]:
    """Where sessions live, what holds it, why it is there when that is not where it was asked to be, and what a
    session written there would meet."""
    root = find_root()
    held = filesystem(root)
    found: dict[str, Any] = {"path": str(root), "filesystem": held.name, "kind": held.kind, "problem": None}
    if not os.environ.get(HOME_VARIABLE) and root == Path(f"/var/tmp/platoon-harness-{os.getuid()}"):
        found["notice"] = "the default root is on a network filesystem, so sessions live here instead"
    try:
        find_root(writing=True)
        found["sockets"] = str(socket_path(root / "sessions" / "doctor").parent)
    except ConfigError as error:
        found["problem"] = str(error)
    return found


def _installed(own: Collection[str] = ()) -> dict[str, Any]:
    """What is installed, from metadata, and each problem among it: what `check_installed` finds, and each extension
    with no commands, as one every session holds or one of the command line's `own` commands holds its name."""
    found = discover()
    components = [
        {
            "kind": _LABELS[component.group],
            "name": component.name,
            "distribution": component.distribution,
            "version": component.version,
        }
        for component in found
    ]
    problems = [*check_installed(), *commandless(found, own)]
    return {"components": components, "problems": [str(problem) for problem in problems]}


def doctor(*, json: bool = False, check: bool = False) -> int:
    """Say whether this machine can run sessions, and what it has.

    Each harness on PATH, with its version, the kind of its login and what its checks found, `openhands` where the
    SDK's `openhands` extra is installed, and where not the interpreter to install it for, pi's Node, where sessions and
    sockets live, and what is installed. It exits 0 when it can run sessions, and 78 when it cannot. A login's kind
    comes from the harness's own status command: no account name is kept, and no credential file is read.

    A harness's levels come from a result of its checks kept under the root, which `--check` makes for each harness it
    finds that the SDK ships a check of, on the binary that runs, against a model of ours on loopback and on no account.
    The runtime reads it at every launch and resume, and a result made of another version, under another SDK or on
    another host says nothing of the one that runs. A check that cannot run keeps nothing, says why, and goes on.

    For example:

        platoon-harness doctor
        platoon-harness doctor --check
        platoon-harness doctor --json | jq .harnesses

    Parameters
    ----------
    json
        Say it as one JSON object.
    check
        Check each harness found that a check ships for, and keep what its checks found.
    """
    report: dict[str, Any] = {
        "versions": {"cli": __version__, "sdk": sdk_version},
        "root": _root(),
        "installed": _installed(),
    }
    root = Path(report["root"]["path"])
    found = [_harness(name, driver, root) for name, driver in harnesses()]
    if check and report["root"]["problem"] is None:
        _check(found, root)
    pi = any(harness["name"] == "pi" and harness["found"] for harness in found)
    report |= {"harnesses": found, "node": _node() if pi else None}
    problems = [
        *([] if any(harness["found"] for harness in found) else ["no harness is on PATH"]),
        *([] if report["root"]["problem"] is None else [report["root"]["problem"]]),
        *report["installed"]["problems"],
    ]
    report["usable"] = not problems
    if json:
        say(shown(report))
    else:
        _say_report(report, problems)
    return 0 if not problems else CONFIGURATION


def _say_report(report: dict[str, Any], problems: list[str]) -> None:
    lines = [f"platoon-harness {__version__}, SDK {sdk_version}"]
    for harness in report["harnesses"]:
        lines.append(f"{harness['name']:<10} {_said(harness)}")
        if "unchecked" in harness:
            lines.append(f"{'':<10} --check kept nothing: {harness['unchecked']}")
    if (node := report["node"]) is not None:
        enough = "" if node["enough"] else f", and pi needs {'.'.join(map(str, _NODE))} or later"
        lines.append(f"{'node':<10} {node['version'] or 'not on PATH'}{enough}")
    root = report["root"]
    lines.append(f"{'root':<10} {root['path']}, on {root['filesystem']}")
    if "notice" in root:
        lines.append(f"{'':<10} {root['notice']}")
    lines.append(f"{'sockets':<10} {root.get('sockets', 'none usable')}")
    for component in report["installed"]["components"]:
        lines.append(f"{component['kind']:<10} {component['name']}, {component['distribution']} {component['version']}")
    lines += [f"problem    {problem}" for problem in problems]
    lines.append("usable" if not problems else "not usable")
    say(safe("\n".join(lines)))


def finding(name: str) -> str | None:
    """What `doctor` says of the harness `name`, after its name, or None where it looks for no harness of that name."""
    driver = dict(harnesses()).get(name)
    return None if driver is None else _said(_harness(name, driver, find_root()))


def _said(harness: dict[str, Any]) -> str:
    """What `doctor` says of a harness after its name: why it is not here, or its version, its login's kind and what
    its checks found."""
    if not harness["found"]:
        return harness["reason"]
    login = f"{harness['login']} login" if harness["login"] else "login unknown"
    checked = _said_checked(harness["name"], harness["checked"])
    return f"{harness['version'] or 'version unknown'}, {login}, {checked}"


def _said_checked(name: str, checked: dict[str, Any] | None) -> str:
    """What a kept result says of the binary that runs, and what makes one where none speaks for it."""
    if checked is None:
        return "not checked: --check checks it" if name in CHECKED else "no check of it ships: `check_driver` checks it"
    made = f"{checked['version'] or 'no version'} under SDK {checked['sdk']} on {checked['host']}"
    if checked["current"] is None:
        return f"checked on {made}, and this binary said no version, so whether that speaks for it is unknown"
    if not checked["current"]:
        return f"checked on {made}, which says nothing of this one: --check checks it"
    counted = f"{checked['passed']} passed, {checked['skipped']} skipped"
    if not checked["failed"]:
        return f"checked on {checked['version']}: {counted}, none failed"
    unmet = f", which leaves {' and '.join(checked['unmet'])} unmet" if checked["unmet"] else ""
    return f"checked on {checked['version']}: {counted}, and {', '.join(checked['failed'])} failed{unmet}"


@dataclass(frozen=True)
class Starter:
    """The team `init` writes from the harnesses on PATH: a lead on the first, which starts workers on the second, or on
    the first again where it is alone. It writes no auth profile, so it passes over `openhands`, which signs in only
    with a key from one."""

    lead: str
    worker: str

    @classmethod
    def on_path(cls) -> Self:
        candidates = [name for name, driver in harnesses() if not isinstance(driver, OpenHandsDriver)]
        found = [name for name in candidates if shutil.which(name)]
        if not found:
            raise ConfigError([Problem("harness", f"none is on PATH: install one of {', '.join(candidates)}")])
        return cls(found[0], found[min(1, len(found) - 1)])

    @property
    def said(self) -> str:
        return f"a lead on {self.lead}, which starts workers on {self.worker}"

    def write(self) -> None:
        """Write it here as the project file, over nothing and through no link: anything there, a link to nothing
        among them, raises `FileExistsError`."""
        team = {
            "roles": {"lead": {"harness": self.lead, "may_spawn": ["worker"]}, "worker": {"harness": self.worker}},
            "topology": {"manager-worker": {"manager": "lead", "workers": "worker"}},
        }
        with open(PROJECT_FILE, "x") as file:
            file.write(
                f"# A team for this project: {self.said}.\n# `platoon-harness team show` says what it allows.\n\n"
            )
            file.write(dumps(team))


def init() -> int:
    """Write a starter `platoon-harness.toml` from the harnesses on PATH, and say how to run it.

    A lead on the first, which starts workers on the second. It never overwrites one. It writes no auth profile, so it
    passes over `openhands`, which signs in only with a key from one.

    For example:

        platoon-harness init
        platoon-harness team show
        platoon-harness run "Fix the flaky test"
    """
    starter = Starter.on_path()
    try:
        starter.write()
    except FileExistsError:
        note(f"{PROJECT_FILE} exists, and init writes over nothing: edit it, or move it away first")
        return REFUSED
    drivers = dict(harnesses())
    plan = any(_login(drivers[name]) == "plan" for name in {starter.lead, starter.worker})
    note(f"wrote {PROJECT_FILE}: {starter.said}")
    note('run it with `platoon-harness run "..."`' + (", adding --plan-login on your own plan login" if plan else ""))
    return 0


extension = App(
    name="extension",
    help="""What is installed, read from metadata alone.

Nothing is imported, and installing activates nothing.

For example:

    platoon-harness extension list""",
)


@extension.command(name="list")
def list_installed(*, json: bool = False) -> int:
    """List every installed driver and extension, with its distribution, and any problem among them: two that share a
    name, one that needs another SDK, and an extension with no commands, as a command of the command line's own or an
    extension every session holds has its name.

    Parameters
    ----------
    json
        Say it as one JSON object.
    """
    from .main import build  # Imported here, as main imports this module to build the command line.

    installed = _installed(set(build()))
    if json:
        say(shown(installed))
        return 0
    for component in installed["components"]:
        say(safe(f"{component['kind']:<10} {component['name']:<12} {component['distribution']} {component['version']}"))
    for problem in installed["problems"]:
        say(safe(f"problem    {problem}"))
    return 0
