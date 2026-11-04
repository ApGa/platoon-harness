"""Repositories a test makes under its `tmp_path`, on a git config of their own, so nobody's settings reach them, and
harnesses whose turns do git work in their workspaces, as an agent's own git would."""

import asyncio
import os
import subprocess
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import pytest

from platoon_harness.testing import Say, ScriptedDriver

from .support import harness


def git(*args: str, cwd: Path, input: str | None = None, when: int | None = None) -> str:
    """Run git as a person or an agent would, and return what it printed. `when` is the time it says it is, in seconds
    since the epoch, as a commit's dates and its reflog entries record it."""
    dates = {} if when is None else {"GIT_COMMITTER_DATE": f"@{when} +0000", "GIT_AUTHOR_DATE": f"@{when} +0000"}
    env = {**os.environ, **dates}
    done = subprocess.run(["git", *args], cwd=cwd, input=input, capture_output=True, text=True, check=True, env=env)
    return done.stdout


def repository(folder: Path, monkeypatch: pytest.MonkeyPatch, *, when: int | None = None) -> Path:
    """A repository with one commit, of `README` and `src/main.py`, made at `when` if a test says so, and git
    configured for this test alone."""
    config = folder.parent / f"{folder.name}.gitconfig"
    config.write_text("[user]\n\tname = Tester\n\temail = tester@example.invalid\n[init]\n\tdefaultBranch = main\n")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(config))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    (folder / "src").mkdir(parents=True)
    (folder / "README").write_text("hello\n")
    (folder / "src" / "main.py").write_text("print('hello')\n")
    git("init", "-q", cwd=folder)
    git("config", "user.name", "Tester", cwd=folder)  # For a harness, which is given no `GIT_CONFIG_GLOBAL`.
    git("config", "user.email", "tester@example.invalid", cwd=folder)
    git("add", "-A", cwd=folder)
    git("commit", "-q", "-m", "first", cwd=folder, when=when)
    return folder


def commit(
    cwd: Path, name: str, text: str = "x\n", message: str | None = None, *, when: int | None = None, cites: str = ""
) -> str:
    """Write a file and commit it, as an agent would, at `when` if a test says so, citing `cites` in an `Informed-By`
    trailer if it names anything, and return the commit."""
    (cwd / name).write_text(text)
    git("add", name, cwd=cwd)
    trailers = [part for value in filter(None, cites.split(",")) for part in ("--trailer", f"Informed-By={value}")]
    git("commit", "-q", "-m", message or f"add {name}", *trailers, cwd=cwd, when=when)
    return git("rev-parse", "HEAD", cwd=cwd).strip()


class Working(ScriptedDriver):
    """A harness each of whose turns first does its next piece of `work` in its workspace, then takes `steps`, which
    say it is done unless a test says otherwise."""

    def __init__(self, work: Sequence[Callable[[Path], Any]], steps: Sequence[Any] = (Say("done"),)) -> None:
        super().__init__([steps] * len(work))
        self._pieces = iter(work)

    async def _walk(self, steps: Sequence[Any]) -> str:
        if (piece := next(self._pieces, None)) is not None:
            await asyncio.to_thread(piece, self._spec.cwd)
        return await super()._walk(steps)


def working(*work: Callable[[Path], Any]) -> str:
    """The `harness` of a role whose agents each do `work`, a piece a turn."""
    return harness(lambda: Working(work))
