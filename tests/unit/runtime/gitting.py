"""Repositories a test makes under its `tmp_path`, on a git config of their own, so nobody's settings reach them."""

import subprocess
from pathlib import Path

import pytest


def git(*args: str, cwd: Path, input: str | None = None) -> str:
    """Run git as a person or an agent would, and return what it printed."""
    return subprocess.run(["git", *args], cwd=cwd, input=input, capture_output=True, text=True, check=True).stdout


def repository(folder: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A repository with one commit, of `README` and `src/main.py`, and git configured for this test alone."""
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
    git("commit", "-q", "-m", "first", cwd=folder)
    return folder


def commit(cwd: Path, name: str, text: str = "x\n", message: str | None = None) -> str:
    """Write a file and commit it, as an agent would, and return the commit."""
    (cwd / name).write_text(text)
    git("add", name, cwd=cwd)
    git("commit", "-q", "-m", message or f"add {name}", cwd=cwd)
    return git("rev-parse", "HEAD", cwd=cwd).strip()
