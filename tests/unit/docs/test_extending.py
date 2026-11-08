"""The extending index names every entry-point group a package here declares and every field of an extension, and the
extension tutorial's steps run against the sample package, each printing what the page says it prints."""

import dataclasses
import re
import runpy
import shlex
import tomllib
from pathlib import Path

import pytest

from platoon_harness.extensions import DRIVERS, EXTENSIONS
from platoon_harness.kernel import Extension
from platoon_harness_cli.main import main

from ..conftest import Site
from .support import ROOT, tracked

INDEX = ROOT / "docs" / "extending" / "index.md"
TUTORIAL = ROOT / "docs" / "extending" / "extensions.md"
SAMPLE = ROOT / "examples" / "extension-package"
SHOWN = re.compile(r"^<!-- (?P<path>[\w./-]+) -->\n```\w+\n(?P<text>.*?)^```$", re.MULTILINE | re.DOTALL)
"""A file the tutorial shows, or a part of one, as a block its path heads."""
BLOCK = re.compile(r"^```(?P<language>\w+)\n(?P<text>.*?)^```$", re.MULTILINE | re.DOTALL)
NOT_RUN = {
    "uv pip install examples/extension-package": (
        "installs into the checkout's environment, so the test installs the sample's metadata and source in a folder "
        "of its own"
    ),
    "uv build": "builds a wheel, as the slow `tests/integration/test_installed_extensions.py` does",
    "uvx twine@7.0.0 check --strict dist/*": "checks what `uv build` built, and fails on the sample, as the page says",
    "uv publish": "uploads to PyPI",
}
"""Each command the tutorial shows that the test does not run, and why."""


def shown() -> dict[str, str]:
    """Each file the tutorial shows, by its path, its parts joined as a module's top-level statements are."""
    parts: dict[str, list[str]] = {}
    for match in SHOWN.finditer(TUTORIAL.read_text()):
        parts.setdefault(match["path"], []).append(match["text"])
    return {path: "\n\n".join(texts) for path, texts in parts.items()}


def blocks(language: str) -> list[str]:
    return [match["text"] for match in BLOCK.finditer(TUTORIAL.read_text()) if match["language"] == language]


def expected(holding: str) -> str:
    """The output the tutorial says to expect: its first text block that holds `holding`."""
    return next(text for text in blocks("text") if holding in text)


def test_the_index_names_every_entry_point_group_and_extension_field():
    """Each group discovery reads, which are every group a `pyproject.toml` here declares an entry point under, and a
    row of the parts table for each field of `Extension`, in its order."""
    text = INDEX.read_text()
    declared = {
        group
        for path in tracked("*pyproject.toml")
        for group in tomllib.loads(path.read_text()).get("project", {}).get("entry-points", {})
    }
    parts = text.partition("| Field | What it holds | What it becomes |")[2].partition("\n\n")[0]

    assert declared == {DRIVERS, EXTENSIONS}
    assert {f"`{DRIVERS}`", f"`{EXTENSIONS}`"} <= set(re.findall(r"`[^`]+`", text))
    assert re.findall(r"^\| `(\w+)` \|", parts, re.MULTILINE) == [field.name for field in dataclasses.fields(Extension)]


def test_the_tutorial_s_steps_run_against_the_sample_package(
    site: Site, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    """Its files are the sample's. With the sample installed as its metadata and its source, each command it shows is
    run as it shows it, in the folder that holds the files it writes, but those it says why it does not run: the
    command line's in this process, and each script as `python` runs it, as `__main__`."""
    files = shown()
    project = tomllib.loads(files["pyproject.toml"])["project"]
    site.install(
        project["name"],
        project["version"],
        entry_points=project["entry-points"],
        requires=tuple(project["dependencies"]),
    )
    monkeypatch.syspath_prepend(SAMPLE / "src")
    monkeypatch.setenv("PLATOON_HARNESS_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.chdir(tmp_path)
    for path in ("team.toml", "vote.py", "check.py"):
        (tmp_path / path).write_text(files[path])
    commands = [line.removeprefix("$ ") for block in blocks("console") for line in block.splitlines()]
    printed = {}

    for command in commands:
        match shlex.split(command):
            case ["uv", "run", "platoon-harness", *words]:
                assert main(words) == 0, capsys.readouterr().err
            case ["uv", "run", "python", script]:
                runpy.run_path(str(tmp_path / script), run_name="__main__")
            case _:
                assert command in NOT_RUN
                continue
        printed[command] = capsys.readouterr().out

    assert {path: files[path] for path in ("pyproject.toml", "src/ballot/__init__.py")} == {
        path: (SAMPLE / path).read_text() for path in ("pyproject.toml", "src/ballot/__init__.py")
    }
    assert set(NOT_RUN) <= set(commands)
    assert expected("extension  ballot") in printed["uv run platoon-harness extension list"].splitlines(keepends=True)
    assert printed["uv run platoon-harness team show team.toml"] == expected("may message reviewer")
    assert printed["uv run python vote.py"] == expected("conflict:")
    assert printed["uv run python check.py"] == expected("passed  names")
