"""What every test shares: no runtime a test started outlives it, however the test ended."""

import contextlib
import os
import select
import signal
from pathlib import Path

import pytest

from platoon_harness.kernel import is_held

_RUNTIME = b"platoon_harness.runtime"
_SECONDS = 10.0


def runtimes_under(folder: Path) -> list[int]:
    """Detached runtimes of sessions under `folder`, which only a test can have started: each runs as `python -P -m
    platoon_harness.runtime <session>`."""
    found = []
    for entry in Path("/proc").iterdir():
        if entry.name.isdecimal():
            try:
                argv = (entry / "cmdline").read_bytes().split(b"\0")[:-1]
            except OSError:
                continue
            if _RUNTIME in argv[:-1] and Path(os.fsdecode(argv[-1])).is_relative_to(folder):
                found.append(int(entry.name))
    return found


def end_group(pid: int) -> None:
    """End a process that leads its own group, and the group with it: `SIGTERM`, which a runtime takes as its owner's
    shutdown, then `SIGKILL` if it is still there. Its pidfd says when it has gone, so nothing sleeps."""
    try:
        pidfd = os.pidfd_open(pid)
    except ProcessLookupError:
        return
    try:
        for signum in (signal.SIGTERM, signal.SIGKILL):
            with contextlib.suppress(ProcessLookupError):
                os.killpg(pid, signum)
            if select.select([pidfd], [], [], _SECONDS)[0]:
                return
    finally:
        os.close(pidfd)


@pytest.fixture(autouse=True)
def outside_any_repository(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    """Each test runs in a folder of its own, outside this checkout, so that no session it starts takes this repository
    for its own: a test that wants one makes it under its `tmp_path`."""
    monkeypatch.chdir(tmp_path_factory.mktemp("cwd"))


@pytest.fixture(autouse=True)
def no_runtime_left(request: pytest.FixtureRequest):
    """End each detached runtime a test left holding a session under its `tmp_path`, by its pid and its group."""
    folder = request.getfixturevalue("tmp_path") if "tmp_path" in request.fixturenames else None
    yield
    if folder is not None and any(is_held(lock.parent) for lock in folder.glob("**/sessions/*/lock")):
        end_runtimes(folder)


def end_runtimes(folder: Path) -> None:
    """End every detached runtime of a session under `folder`, each the leader of its own group."""
    for pid in runtimes_under(folder):
        with contextlib.suppress(ProcessLookupError):
            if os.getpgid(pid) == pid:
                end_group(pid)
