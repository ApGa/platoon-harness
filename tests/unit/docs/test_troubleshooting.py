"""Troubleshooting quotes what the command prints, so a person who searches the page for the message they got finds
it."""

import sys
from importlib.metadata import PackageNotFoundError

import pytest

from platoon_harness.drivers import DriverError
from platoon_harness.drivers.openhands import worker
from platoon_harness_cli.launcher import HINT

from .support import ROOT

PAGE = (ROOT / "docs" / "how-to" / "troubleshooting.md").read_text()
INTERPRETER = "~/.local/share/uv/tools/platoon-harness/bin/python"
"""The interpreter the page's `openhands` line names, a tool install's."""


def test_the_page_quotes_what_the_command_says_without_its_extra():
    assert f"\n{HINT}\n" in PAGE


def test_the_page_quotes_what_doctor_says_without_the_openhands_extra(monkeypatch):
    def absent(name: str) -> str:
        raise PackageNotFoundError(name)

    monkeypatch.setattr(worker, "version", absent)
    with pytest.raises(DriverError) as raised:
        worker.sdk_version()
    [line] = [line for line in PAGE.splitlines() if line.startswith("openhands  ")]

    assert (
        str(raised.value)
        .replace(sys.executable, INTERPRETER)
        .startswith(line.removeprefix("openhands").lstrip().removesuffix(" …"))
    )
