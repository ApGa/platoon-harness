"""Troubleshooting quotes what the command prints, so a person who searches the page for the message they got finds
it."""

import os
import sys
from importlib import metadata
from importlib.metadata import PackageNotFoundError

import pytest

from platoon_harness import Role, Team
from platoon_harness.drivers import DriverError
from platoon_harness.drivers.openhands import worker
from platoon_harness.runtime.opening import check
from platoon_harness_cli import launcher

from .support import ROOT

PAGE = (ROOT / "docs" / "how-to" / "troubleshooting.md").read_text()
INTERPRETER = "~/.local/share/uv/tools/platoon-harness/bin/python"
"""The interpreter the page's `openhands` line names, a tool install's."""
PROJECT = "~/project/.venv/bin/python"
"""The interpreter the page's launcher line names, a project's that holds the library alone."""


def test_the_page_quotes_what_the_command_says_without_its_extra(monkeypatch):
    """An install of the library alone: platoon-harness is there, and nothing its `cli` extra requires is."""
    installed = metadata.distribution

    def absent(name: str) -> metadata.Distribution:
        if name == "platoon-harness":
            return installed(name)
        raise PackageNotFoundError(name)

    monkeypatch.setattr(launcher.metadata, "distribution", absent)
    said = launcher.hint(launcher.missing()).replace(sys.executable, PROJECT)

    assert f"\n{said}\n" in PAGE


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


def test_the_page_quotes_what_a_run_says_of_a_pi_that_cannot_start(tmp_path, monkeypatch):
    """A pi whose Node cannot load libatomic, as in a slim image: `run` prints each problem `check` finds."""
    loader = (
        "node: error while loading shared libraries: libatomic.so.1: cannot open shared object file: "
        "No such file or directory"
    )
    pi = tmp_path / "pi"
    pi.write_text(f"#!/bin/sh\necho '{loader}' >&2\nexit 127\n")
    pi.chmod(0o700)
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ['PATH']}")

    found = check(Team(roles={"lead": Role(harness="pi")}), cwd=tmp_path, root=tmp_path)
    [problem] = [problem for problem in found if problem.where == "roles.lead.harness"]

    assert f"\nplatoon-harness: {problem}\n" in PAGE
