"""What this machine has: the harnesses on its PATH and their logins, where sessions live, and what is installed."""

import os
import re
import shutil
from pathlib import Path
from typing import Any

from cyclopts import App

from platoon_harness import ConfigError
from platoon_harness.config import PROJECT_FILE
from platoon_harness.drivers import Driver, DriverError
from platoon_harness.drivers.process import exit_reason, status
from platoon_harness.drivers.wire import WireDriver
from platoon_harness.extensions import DRIVERS, EXTENSIONS, Installed, check_installed, discover, load
from platoon_harness.kernel import filesystem
from platoon_harness.runtime.paths import HOME_VARIABLE, find_root, socket_path
from platoon_harness.schema import Problem, dumps
from platoon_harness.version import __version__ as sdk_version

from . import __version__
from .exits import CONFIGURATION, REFUSED
from .output import note, safe, say, shown

_NODE = (22, 19)
"""The oldest Node that runs pi, as compatibility.md says."""
_LABELS = {DRIVERS: "driver", EXTENSIONS: "extension"}


def harnesses() -> list[tuple[str, Driver]]:
    """Each installed driver that names a harness, which by the naming law is a command of that name, or runs a wire
    program of its own, as `openhands` does. A driver that needs a command given it, as `exec` and `wire` do, names
    none."""
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


def _harness(name: str, driver: Driver) -> dict[str, Any]:
    """What a harness says of itself: its version from `--version`, and the kind of its login from its own status
    command, which is all of what it said that is kept."""
    if isinstance(driver, WireDriver):
        return _wire_harness(name, driver)
    if shutil.which(name) is None:
        return {"name": name, "found": False}
    return {"name": name, "found": True, "version": _first_line([name, "--version"]), "login": _login(driver)}


def _wire_harness(name: str, driver: WireDriver) -> dict[str, Any]:
    """A harness behind a wire program of its own, as `openhands` is: there when the program says its version, and
    otherwise not, for the reason the program gave."""
    done = status([*driver.command, "--version"], os.environ)
    if done is None:
        return {"name": name, "found": False, "reason": "it said no version in time"}
    said = (done.stderr if done.returncode else done.stdout).decode(errors="replace").strip()
    if done.returncode:
        return {"name": name, "found": False, "reason": said.rpartition("\n")[2] or exit_reason(done.returncode)}
    return {"name": name, "found": True, "version": said.partition("\n")[0] or None, "login": _login(driver)}


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


def _installed() -> dict[str, Any]:
    components = [
        {
            "kind": _LABELS[component.group],
            "name": component.name,
            "distribution": component.distribution,
            "version": component.version,
        }
        for component in discover()
    ]
    return {"components": components, "problems": [str(problem) for problem in check_installed()]}


def doctor(*, json: bool = False) -> int:
    """Say whether this machine can run sessions, and what it has.

    Each harness on PATH, with its version and the kind of its login, `openhands` where the SDK's `openhands` extra is
    installed, and how to install it where not, pi's Node, where sessions and sockets live, and what is installed. It
    exits 0 when it can run sessions, and 78 when it cannot. A login's kind comes from the harness's own status command:
    no account name is kept, and no credential file is read.

    For example:

        platoon-harness doctor
        platoon-harness doctor --json | jq .harnesses

    Parameters
    ----------
    json
        Say it as one JSON object.
    """
    found = [_harness(name, driver) for name, driver in harnesses()]
    pi = any(harness["name"] == "pi" and harness["found"] for harness in found)
    report = {
        "versions": {"cli": __version__, "sdk": sdk_version},
        "harnesses": found,
        "node": _node() if pi else None,
        "root": _root(),
        "installed": _installed(),
    }
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
        if harness["found"]:
            login = f"{harness['login']} login" if harness["login"] else "login unknown"
            lines.append(f"{harness['name']:<10} {harness['version'] or 'version unknown'}, {login}")
        else:
            lines.append(f"{harness['name']:<10} {harness.get('reason', 'not on PATH')}")
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


def init() -> int:
    """Write a starter `platoon-harness.toml` from the harnesses on PATH, and say how to run it.

    A lead on the first, which starts workers on the second. It never overwrites one. It writes no auth profile, so it
    passes over a harness behind a wire program, as `openhands` is, since nothing tells it how one signs in.

    For example:

        platoon-harness init
        platoon-harness team show
        platoon-harness run "Fix the flaky test"
    """
    candidates = [(name, driver) for name, driver in harnesses() if not isinstance(driver, WireDriver)]
    found = [(name, driver) for name, driver in candidates if shutil.which(name)]
    if not found:
        names = ", ".join(name for name, _ in candidates)
        raise ConfigError([Problem("harness", f"none is on PATH: install one of {names}")])
    lead, worker = found[0], found[min(1, len(found) - 1)]
    team = {
        "roles": {"lead": {"harness": lead[0], "may_spawn": ["worker"]}, "worker": {"harness": worker[0]}},
        "topology": {"manager-worker": {"manager": "lead", "workers": "worker"}},
    }
    said = f"a lead on {lead[0]}, which starts workers on {worker[0]}"
    try:
        with open(PROJECT_FILE, "x") as file:
            file.write(f"# A team for this project: {said}.\n# `platoon-harness team show` says what it allows.\n\n")
            file.write(dumps(team))
    except FileExistsError:
        note(f"{PROJECT_FILE} exists, and init writes over nothing: edit it, or move it away first")
        return REFUSED
    plan = any(_login(driver) == "plan" for _, driver in {lead, worker})
    note(f"wrote {PROJECT_FILE}: {said}")
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
    """List every installed driver and extension, with its distribution, and any problem among them.

    Parameters
    ----------
    json
        Say it as one JSON object.
    """
    installed = _installed()
    if json:
        say(shown(installed))
        return 0
    for component in installed["components"]:
        say(safe(f"{component['kind']:<10} {component['name']:<12} {component['distribution']} {component['version']}"))
    for problem in installed["problems"]:
        say(safe(f"problem    {problem}"))
    return 0
