"""The command's launcher: where the `cli` extra is not installed, it says what to install and exits 78, and where it
is, it runs the command line."""

import sys
from importlib import metadata

import pytest

from platoon_harness import __version__
from platoon_harness_cli import launcher
from platoon_harness_cli.exits import CONFIGURATION


def test_the_launcher_says_what_to_install_where_the_cli_extra_is_missing(monkeypatch, capsys):
    found = metadata.distribution

    def distribution(name: str) -> metadata.Distribution:
        if name == "textual":
            raise metadata.PackageNotFoundError(name)
        return found(name)

    monkeypatch.setattr(metadata, "distribution", distribution)

    assert launcher.missing() == ["textual"]
    assert launcher.main() == CONFIGURATION
    assert capsys.readouterr() == ("", f"{launcher.HINT}\n")


def test_the_launcher_runs_the_command_line_where_the_cli_extra_is_installed(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["platoon-harness", "--version"])

    assert launcher.missing() == []
    assert launcher.main() == 0
    assert capsys.readouterr().out == f"platoon-harness {__version__}\n"


@pytest.mark.parametrize("line", ["textual<9,>=8.2; extra == 'cli'", 'textual>=8.2 ; extra == "cli"'])
def test_the_launcher_reads_a_requirement_of_the_cli_extra_however_its_marker_is_quoted(line):
    found = launcher._EXTRA.match(line)

    assert found is not None and found["name"] == "textual"
    assert launcher._EXTRA.match(line.replace("cli", "openhands")) is None
