"""The runtime's own git: one runner, which runs no hook, no fsmonitor and no gc, and asks nothing of a terminal.

An agent's git is its own and is never touched. Paths come from `rev-parse`, never from a literal `.git/`.
"""

import os
import subprocess
import tempfile
import threading
from collections.abc import Mapping, Sequence
from pathlib import Path

from platoon_harness.drivers.env import inherited

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


def git(
    *args: str,
    cwd: Path,
    input: str | None = None,
    ok: Sequence[int] = (0,),
    env: Mapping[str, str] | None = None,
    wrap: Sequence[str] = (),
    limit: int | None = None,
) -> str:
    """Run git in `cwd` and return what it printed, or raise `GitError` with what it said for an exit not in `ok`. Your
    config applies, as it would to your own git, but for the settings that would run something or start a gc. `env`
    is what this one call sets besides, such as the index and object store a snapshot's capture writes instead. `wrap`
    is the isolation git runs in, in an isolated agent's tree, whose config the agent writes: there it runs on the same
    allowlist its harness gets, never the runtime's whole environment, since the agent's config may name a program to
    run on it. With `limit`, what it printed past `limit` bytes and one more is not read: git is ended there, as a
    reader that stops ends what it reads from, and what comes back is then one byte longer than `limit`, whatever its
    exit."""
    settings = [part for setting in _SETTINGS for part in ("-c", setting)]
    base = inherited() if wrap else {name: value for name, value in os.environ.items() if name not in _LOCAL}
    env = base | dict(_ENVIRONMENT) | dict(env or {})
    argv = [*wrap, "git", *settings, *args]
    try:
        if limit is None:
            done = subprocess.run(
                argv,
                cwd=cwd,
                input=input,
                capture_output=True,
                text=True,
                errors="surrogateescape",
                env=env,
                timeout=SECONDS,
            )
            printed, code, said = done.stdout, done.returncode, done.stderr
        else:
            printed, code, said = _head(argv, cwd, env, limit)
    except subprocess.TimeoutExpired:
        raise GitError(f"git {args[0]} took longer than {SECONDS:.0f} s") from None
    except OSError as error:
        raise GitError(f"git cannot run in {cwd}: {error.strerror}") from None
    if code is not None and code not in ok:
        raise GitError(f"git {args[0]} failed: {said.strip() or printed.strip() or code}")
    return printed


def _head(argv: Sequence[str], cwd: Path, env: Mapping[str, str], limit: int) -> tuple[str, int | None, str]:
    """The first `limit` bytes and one more of what `argv` printed, its exit, None once it printed more, and what it
    said on stderr, which goes to a file, so that a command saying much there never waits on us."""
    with (
        tempfile.TemporaryFile() as said,
        subprocess.Popen(argv, cwd=cwd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=said, env=env) as run,
    ):
        assert run.stdout is not None
        expired = threading.Event()
        timer = threading.Timer(SECONDS, lambda: (expired.set(), run.kill()))
        timer.start()
        try:
            printed = run.stdout.read(limit + 1)
            run.stdout.close()
            code = run.wait()
        finally:
            timer.cancel()
        if expired.is_set():
            raise subprocess.TimeoutExpired(argv, SECONDS)
        said.seek(0)
        text = said.read().decode(errors="surrogateescape")
    return printed.decode(errors="surrogateescape"), None if len(printed) > limit else code, text
