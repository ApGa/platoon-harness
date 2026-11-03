"""What the team tests share: a throwaway repository with a seeded bug, and what a journal says was spent."""

import asyncio
import contextlib
import os
import signal
import subprocess
from collections import Counter
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

from platoon_harness import Session
from platoon_harness.config import Secret
from platoon_harness.drivers.env import Redactor
from platoon_harness.runtime import Admission, LocalAuthority, SpawnRequest

from ..unit.runtime.support import journal, of_type

CLAUDE = "claude-haiku-5-5"
CODEX = "gpt-6-luna"
EFFORT = "low"

_STATS = """def mean(values):
    return sum(values) / (len(values) - 1)
"""
_RANGES = """def clamp(value, low, high):
    return max(high, min(low, value))
"""
_TESTS = """import unittest

from ranges import clamp
from stats import mean


class Tests(unittest.TestCase):
    def test_mean(self):
        self.assertEqual(mean([1, 2, 3]), 2)

    def test_clamp(self):
        self.assertEqual(clamp(5, 0, 3), 3)
        self.assertEqual(clamp(-1, 0, 3), 0)
        self.assertEqual(clamp(2, 0, 3), 2)


if __name__ == "__main__":
    unittest.main()
"""


_REPORT = """#!/bin/sh
echo "report for $PLATOON_HARNESS_URL"
echo "ref $PLATOON_HARNESS_TOKEN"
printf %s "$PLATOON_HARNESS_TOKEN" | base64
"""


def git(work: Path, *args: str) -> str:
    identity = ("-c", "user.name=test", "-c", "user.email=test@example.com")
    done = subprocess.run(("git", *identity, *args), cwd=work, capture_output=True, text=True, check=True, timeout=30)
    return done.stdout


def seeded(work: Path) -> Path:
    """A repository of two modules, each with one bug, whose tests fail until both are fixed."""
    work.mkdir()
    git(work, "init", "-q")
    (work / "stats.py").write_text(_STATS)
    (work / "ranges.py").write_text(_RANGES)
    (work / "test_all.py").write_text(_TESTS)
    (work / "report.sh").write_text(_REPORT)
    git(work, "add", ".")
    git(work, "commit", "-q", "-m", "Seed two bugs")
    return work


def tests_pass(work: Path) -> bool:
    done = subprocess.run(("python3", "-m", "unittest", "-q"), cwd=work, capture_output=True, timeout=30, check=False)
    return done.returncode == 0


async def seen(session: Session, kind: str, *, count: int = 1, within: float = 75.0) -> list[Any]:
    """Events of one type, once `count` of them are in the journal."""
    async with asyncio.timeout(within):
        async for _ in session._moves():
            found = await of_type(session, kind)
            if len(found) >= count:
                return found
    raise AssertionError(f"the session ended before {count} {kind}")


async def gone(*pids: int) -> None:
    """Wait for processes outside the session to end. A pidfd can be read once its process has, so nothing looks."""
    loop = asyncio.get_running_loop()
    held = []
    for pid in pids:
        with contextlib.suppress(ProcessLookupError):
            held.append(os.pidfd_open(pid))
    ends = [loop.create_future() for _ in held]
    for pidfd, ended in zip(held, ends, strict=True):
        loop.add_reader(pidfd, lambda ended=ended: ended.done() or ended.set_result(None))
    try:
        await asyncio.gather(*ends)
    finally:
        for pidfd in held:
            loop.remove_reader(pidfd)
            os.close(pidfd)


@contextlib.asynccontextmanager
async def touched(path: Path) -> AsyncGenerator[asyncio.StreamReader]:
    """A named pipe at `path`, whose reader ends once a command has opened it and let go, as `touch` does, so a test
    can wait for a command it cannot see run."""
    os.mkfifo(path)
    reader = asyncio.StreamReader()
    pipe = os.fdopen(os.open(path, os.O_RDONLY | os.O_NONBLOCK), "rb", 0)
    protocol = asyncio.StreamReaderProtocol(reader)
    transport, _ = await asyncio.get_running_loop().connect_read_pipe(lambda: protocol, pipe)
    try:
        yield reader
    finally:
        transport.close()


def alive(pid: int) -> bool:
    """Whether a process is there and is not a zombie."""
    try:
        return Path(f"/proc/{pid}/stat").read_text().rpartition(")")[2].split()[0] != "Z"
    except OSError:
        return False


def running_in(work: Path) -> list[int]:
    """Every process working in a throwaway directory, which only a test can have started."""
    found = []
    for entry in Path("/proc").iterdir():
        if entry.name.isdecimal():
            try:
                if Path(os.readlink(entry / "cwd")).is_relative_to(work):
                    found.append(int(entry.name))
            except OSError:
                pass
    return found


def end_what_is_left(work: Path) -> list[int]:
    """End whatever still works in a throwaway directory, by pid, and say what that was."""
    left = running_in(work)
    for pid in left:
        os.kill(pid, signal.SIGKILL)
    return left


class Recording(LocalAuthority):
    """The local authority, keeping each token it gives, so that a test can look for them afterwards."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.tokens: list[Secret] = []

    async def admit(self, spawn: SpawnRequest) -> Admission:
        admission = await super().admit(spawn)
        self.tokens.append(admission.token)
        return admission


def leaks(folder: Path, *secrets: Secret) -> list[str]:
    """Every file under a session folder holding a credential, in plain or encoded form, by path relative to it. The
    tokens of a client live in their own files, which is no leak."""
    redact = Redactor(secrets)
    found = []
    for path in folder.rglob("*"):
        if path.is_file() and path.name not in ("owner.token", "view.token"):
            bytes = path.read_bytes()
            if redact(bytes) != bytes:
                found.append(str(path.relative_to(folder)))
    return found


async def tools_called(session: Session) -> Counter[tuple[str, str]]:
    """Each agent's tools by name, from the items its harness reported."""
    items = await of_type(session, "item.recorded")
    started = [event for event in items if event.data["kind"] == "tool" and event.data["phase"] == "started"]
    return Counter((event.agent, event.gist.partition(" ")[0]) for event in started)


def rereads(events: list[Any]) -> dict[str, tuple[int, int]]:
    """Per agent, the turns a wake began, and how many of those opened by calling `message_read` for nothing new: the
    wake had handed it all there was, so the read showed no entry. A read after other calls is polling, and not this."""
    woken: Counter[str] = Counter()
    handed: set[str] = set()
    opening: dict[str, str] = {}
    called: set[tuple[str, str]] = set()
    fresh: set[tuple[str, str]] = set()
    for event in events:
        agent, data = event.agent, event.data
        if event.type == "context.offered" and data["how"] == "wake":
            handed.add(agent)
        elif event.type == "turn.started":
            opening.pop(agent, None)
            if agent in handed:
                handed.discard(agent)
                woken[agent] += 1
                opening[agent] = data["turn"]
        elif event.type == "item.recorded" and data["kind"] == "tool" and data["phase"] == "started":
            if "message_read" in event.gist and opening.get(agent) == event.turn:
                called.add((agent, event.turn))
            opening.pop(agent, None)
        elif event.type == "context.offered" and data["how"] == "read" and data["items"]:
            fresh.add((agent, event.turn))
    wasted = Counter(agent for agent, _ in called - fresh)
    return {agent: (count, wasted[agent]) for agent, count in woken.items()}


async def spent(session: Session) -> dict[str, Any]:
    """What a live test states: model calls and turns per agent, counted from the journal."""
    events = await journal(session)
    calls = Counter(event.agent for event in events if event.type == "model.called")
    turns = Counter(event.agent for event in events if event.type == "turn.started")
    unknown = [event.gist for event in events if event.type == "native.recorded"]
    return {"calls": dict(calls), "total": calls.total(), "turns": dict(turns), "unknown": unknown}
