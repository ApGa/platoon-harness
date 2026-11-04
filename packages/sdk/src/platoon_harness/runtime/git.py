"""The runtime's own git: one runner, which runs no hook, no fsmonitor and no gc, and asks nothing of a terminal.

An agent's git is its own and is never touched. Paths come from `rev-parse`, never from a literal `.git/`.
"""

import os
import subprocess
from collections.abc import Sequence
from pathlib import Path

SECONDS = 300.0

_SETTINGS = (
    "gc.auto=0",
    "maintenance.auto=false",
    "core.hooksPath=/dev/null",
    "core.fsmonitor=false",
    "core.logAllRefUpdates=true",
)
_ENVIRONMENT = (("GIT_OPTIONAL_LOCKS", "0"), ("LC_ALL", "C"), ("GIT_TERMINAL_PROMPT", "0"))
_LOCAL = (  # What `git rev-parse --local-env-vars` names: another repository's, if inherited.
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_CONFIG",
    "GIT_CONFIG_PARAMETERS",
    "GIT_CONFIG_COUNT",
    "GIT_OBJECT_DIRECTORY",
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_IMPLICIT_WORK_TREE",
    "GIT_GRAFT_FILE",
    "GIT_INDEX_FILE",
    "GIT_NO_REPLACE_OBJECTS",
    "GIT_REPLACE_REF_BASE",
    "GIT_PREFIX",
    "GIT_SHALLOW_FILE",
    "GIT_COMMON_DIR",
)

__all__ = ["SECONDS", "GitError", "git"]


class GitError(Exception):
    """What git said, or holds, that stops a workspace: its own words where it failed, ours where it holds what the
    runtime did not make."""


def git(*args: str, cwd: Path, input: str | None = None, ok: Sequence[int] = (0,)) -> str:
    """Run git in `cwd` and return what it printed, or raise `GitError` with what it said for an exit not in `ok`. Your
    config applies, as it would to your own git, but for the settings that would run something or start a gc."""
    settings = [part for setting in _SETTINGS for part in ("-c", setting)]
    env = {name: value for name, value in os.environ.items() if name not in _LOCAL} | dict(_ENVIRONMENT)
    try:
        done = subprocess.run(
            ["git", *settings, *args],
            cwd=cwd,
            input=input,
            capture_output=True,
            text=True,
            errors="surrogateescape",
            env=env,
            timeout=SECONDS,
        )
    except subprocess.TimeoutExpired:
        raise GitError(f"git {args[0]} took longer than {SECONDS:.0f} s") from None
    except OSError as error:
        raise GitError(f"git cannot run in {cwd}: {error.strerror}") from None
    if done.returncode not in ok:
        raise GitError(f"git {args[0]} failed: {done.stderr.strip() or done.stdout.strip() or done.returncode}")
    return done.stdout
