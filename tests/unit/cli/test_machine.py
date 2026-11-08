"""`doctor`: what each harness's kept result says of the binary that runs, a check going on past one that fails, and
with `extension list`, each installed extension the command line gives no command."""

import socket
import sys
from pathlib import Path

import pytest

from platoon_harness import __version__
from platoon_harness.drivers import DriverError
from platoon_harness.drivers.claude import ClaudeDriver
from platoon_harness.drivers.codex import CodexDriver
from platoon_harness.drivers.levels import CHECKED, Check, Conformance
from platoon_harness.extensions import EXTENSIONS
from platoon_harness.extensions import DRIVERS, load
from platoon_harness.runtime.paths import read_conformance, write_conformance
from platoon_harness_cli import machine
from platoon_harness_cli.exits import CONFIGURATION

from ..conftest import Site


class Foo(ClaudeDriver):
    """An installed driver no check ships for."""


def result(driver: str, version: str | None, *failed: str, sdk: str = __version__) -> Conformance:
    checks = (
        Check(name="turn_end_reported", state="passed"),
        Check(name="one_shot_exits", state="skipped", reason="it declares a persistent session"),
        *(Check(name=name, state="failed", reason="no") for name in failed),
    )
    pinned = {"implementation": CHECKED[driver], "sdk": sdk, "host": socket.gethostname()}
    return Conformance(driver=driver, version=version, checks=checks, **pinned)


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A root of its own, and stand-ins on PATH for claude, codex and foo that say a version and nothing else."""
    folder = tmp_path / "bin"
    folder.mkdir()
    for name, version in (("claude", "2.1.316 (Claude Code)"), ("codex", "codex-cli 0.164.0"), ("foo", "1.0")):
        (folder / name).write_text(f'#!/bin/sh\n[ "$1" = --version ] && echo "{version}"\nexit 0\n')
        (folder / name).chmod(0o755)
    monkeypatch.setenv("PATH", f"{folder}:/usr/bin:/bin")
    monkeypatch.setenv("PLATOON_HARNESS_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(
        machine, "harnesses", lambda: [("claude", ClaudeDriver()), ("codex", CodexDriver()), ("foo", Foo())]
    )
    return tmp_path / "home"


def lines(said: str) -> dict[str, str]:
    """Each harness's line by its name, and the line under it, if any, by its name with `+`."""
    found: dict[str, str] = {}
    last = ""
    for line in said.splitlines():
        name = line[:10].strip()
        if name:
            found[name], last = line[11:], name
        else:
            found[f"{last}+"] = line[11:]
    return found


def test_doctor_check_goes_on_past_a_check_that_cannot_run_and_leaves_what_was_kept(home, monkeypatch, capsys):
    """A check that raises keeps nothing, says why and leaves the earlier result, a harness no check ships for is not
    checked, and every other harness is checked and the report said as usual."""
    write_conformance(home, earlier := result("claude", "2.1.316"))
    asked: list[str] = []

    async def check(name: str, folder: Path) -> Conformance:
        asked.append(name)
        if name == "claude":
            raise DriverError("it did not describe itself")
        return result(name, "0.164.0", "runs_in_its_workspace")

    monkeypatch.setattr(machine, "check_harness", check)

    code = machine.doctor(check=True)
    said = lines(capsys.readouterr().out)

    assert code == 0 and asked == ["claude", "codex"]
    assert read_conformance(home, "claude") == earlier and read_conformance(home, "foo") is None
    assert said["claude+"] == "--check kept nothing: its check could not run: it did not describe itself"
    assert said["codex"].endswith(
        "checked on 0.164.0: 1 passed, 1 skipped, and runs_in_its_workspace failed, which leaves operational unmet"
    )
    assert said["foo"] == "1.0, login unknown, no check of it ships: `check_driver` checks it"


@pytest.mark.parametrize(
    ("kept", "made"),
    [
        (result("claude", "2.1.200"), f"2.1.200 under SDK {__version__} on {socket.gethostname()}"),
        (result("claude", "2.1.316", sdk="0.0.1"), f"2.1.316 under SDK 0.0.1 on {socket.gethostname()}"),
    ],
)
def test_doctor_says_a_result_kept_for_another_binary_says_nothing_of_the_one_that_runs(home, capsys, kept, made):
    write_conformance(home, kept)

    machine.doctor()

    claude = lines(capsys.readouterr().out)["claude"]
    assert claude.endswith(f"checked on {made}, which says nothing of this one: --check checks it")
    assert "passed" not in claude


def test_doctor_check_keeps_no_result_of_a_harness_that_says_no_version(home, monkeypatch, capsys):
    async def check(name: str, folder: Path) -> Conformance:
        return result(name, None)

    monkeypatch.setattr(machine, "check_harness", check)

    machine.doctor(check=True)

    said = lines(capsys.readouterr().out)
    assert read_conformance(home, "claude") is None and read_conformance(home, "codex") is None
    assert (
        said["claude+"]
        == "--check kept nothing: it said no version, so what its checks found would speak for no binary"
    )
    assert said["claude"].endswith("not checked: --check checks it")


def test_doctor_says_unknown_where_the_binary_says_no_version(home, monkeypatch, capsys):
    write_conformance(home, result("claude", "2.1.316"))
    monkeypatch.setattr(machine, "_first_line", lambda command: None)

    machine.doctor()

    said = lines(capsys.readouterr().out)["claude"]
    assert said.endswith("and this binary said no version, so whether that speaks for it is unknown")


def test_extension_list_and_doctor_say_why_an_installed_extension_has_no_command(home, site: Site, capsys):
    """`extension list` names each installed extension the command line gives no command, as a problem among what is
    installed: one named as an extension every session holds, which no session can load, and one named as a command of
    the command line's own. `doctor` names the first alone, as only it keeps a session from running, one whose team
    names it, and neither is imported."""
    for name in ("lease", "web"):
        site.module(f"never_{name}", "raise RuntimeError('imported')")
        site.install(f"{name}-maker", entry_points={EXTENSIONS: {name: f"never_{name}:extension"}})
    held = (
        "problem    extensions.lease: lease-maker 1.0.0's extension `lease` has no commands, and no session can load "
        "it, as every session holds the SDK's own extension `lease`"
    )
    own = (
        "problem    extensions.web: web-maker 1.0.0's extension `web` has no commands, as `web` is a command of the "
        "command line's own: its ops run through the SDK, MCP, `ph` and the clients' palettes, on a session whose team "
        "names it"
    )

    listed = machine.list_installed()
    said = capsys.readouterr().out.splitlines()
    usable = machine.doctor()
    doctored = capsys.readouterr().out.splitlines()

    assert listed == 0 and said[-2:] == [held, own]
    assert usable == CONFIGURATION and doctored[-2:] == [held, "not usable"]
    assert not {"never_lease", "never_web"} & set(sys.modules)


NAMED = """
import socket

from platoon_harness import __version__
from platoon_harness.drivers import DriverInfo
from platoon_harness.drivers.levels import Check, Conformance, implementation
from platoon_harness.testing import ScriptedDriver


class Named(ScriptedDriver):
    def describe(self):
        return DriverInfo(name="named", check="doctor_named:check")


class Liar(ScriptedDriver):
    def describe(self):
        return DriverInfo(name="liar", check="doctor_named:lie")


class Thief(ScriptedDriver):
    def describe(self):
        return DriverInfo(name="thief", check="doctor_named:steal")


class Broken(ScriptedDriver):
    def describe(self):
        return DriverInfo(name="broken", check="doctor_named:breaks")


class Odd(ScriptedDriver):
    def describe(self):
        return DriverInfo(name="odd", check="doctor_named:odd")


def found(made, driver):
    checks = (Check(name="turn_end_reported", state="passed"),)
    pinned = {"implementation": made, "sdk": __version__, "host": socket.gethostname()}
    return Conformance(driver=driver, version="1.0", checks=checks, **pinned)


async def check(folder):
    (folder / "ran").write_text("here")
    return found(implementation(Named()), "named")


async def lie(folder):
    return found(implementation(Named()), "liar")


async def steal(folder):
    return found(implementation(Thief()), "named")


async def breaks(folder):
    raise RuntimeError("it fell over")


async def odd(folder):
    return "all good"
"""
"""An installed distribution's drivers, each naming a check: one of itself, one of the first's class, one of its own
class under the first's name, one that breaks, and one that finds no result."""


def test_doctor_checks_an_installed_driver_that_names_its_check(home, tmp_path, monkeypatch, capsys):
    """`--check` runs the check an installed driver names, in the folder it keeps results beside, and keeps what it
    found, pinned to the driver's class and the release that holds it, as it does a check of the SDK's own. A check
    whose result is of another class than its driver's, or names another harness, speaks for a driver it did not check,
    so it keeps nothing, and leaves that harness's result as it was; and one that breaks, or finds no result, keeps
    nothing either, saying why, and doctor goes on."""
    site = tmp_path / "site"
    site.mkdir()
    (site / "doctor_named.py").write_text(NAMED)
    info = site / "doctor_named-2.0.0.dist-info"
    info.mkdir()
    (info / "METADATA").write_text("Metadata-Version: 2.1\nName: doctor-named\nVersion: 2.0.0\n")
    names = ("named", "liar", "thief", "broken", "odd")
    points = "".join(f"{name} = doctor_named:{name.title()}\n" for name in names)
    (info / "entry_points.txt").write_text(f"[{DRIVERS}]\n{points}")
    monkeypatch.syspath_prepend(site)
    for name in names:
        (tmp_path / "bin" / name).write_text('#!/bin/sh\necho "1.0"\n')
        (tmp_path / "bin" / name).chmod(0o755)
    monkeypatch.setattr(machine, "harnesses", lambda: [(name, load(DRIVERS, name)()) for name in names])

    machine.doctor()
    before = lines(capsys.readouterr().out)
    code = machine.doctor(check=True)
    said = lines(capsys.readouterr().out)

    kept = read_conformance(home, "named")
    assert before["named"] == "1.0, login unknown, not checked: --check checks it"
    assert code == 0 and (home / "conformance" / "named" / "ran").read_text() == "here"
    assert kept is not None and kept.implementation == "doctor_named:Named, doctor-named 2.0.0"
    assert said["named"] == "1.0, login unknown, checked on 1.0: 1 passed, 0 skipped, none failed"
    assert [read_conformance(home, name) for name in ("liar", "thief", "broken", "odd")] == [None] * 4
    assert said["liar+"] == (
        "--check kept nothing: its check could not run: its check doctor_named:lie checked doctor_named:Named, "
        "doctor-named 2.0.0, and liar is doctor_named:Liar, doctor-named 2.0.0"
    )
    assert said["thief+"] == (
        "--check kept nothing: its check could not run: its check doctor_named:steal checked named, and this is thief"
    )
    assert said["broken+"] == (
        "--check kept nothing: its check could not run: its check doctor_named:breaks broke: RuntimeError: it fell over"
    )
    assert said["odd+"] == (
        "--check kept nothing: its check could not run: its check doctor_named:odd found str, where `check_driver` "
        "finds a Conformance"
    )
