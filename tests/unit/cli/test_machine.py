"""`doctor`: what each harness's kept result says of the binary that runs, and a check going on past one that fails."""

import socket
from pathlib import Path

import pytest

from platoon_harness import __version__
from platoon_harness.drivers import DriverError
from platoon_harness.drivers.claude import ClaudeDriver
from platoon_harness.drivers.codex import CodexDriver
from platoon_harness.drivers.levels import CHECKED, Check, Conformance
from platoon_harness.runtime.paths import read_conformance, write_conformance
from platoon_harness_cli import machine


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
