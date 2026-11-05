"""Real harnesses through crashes, on real models and native logins, through the public `Session`. Set
`PLATOON_HARNESS_LIVE=1` to run these, and say what ran.

Budget: at most 100 model calls in all, each test stating its own, all `claude-haiku-5-5` or `gpt-6-luna` at low effort.
Every session has a `Budget`, so that a runaway stops itself. A process outside the session is waited for by its pidfd,
and each wait is bounded.
"""

import asyncio
import os
import shutil
import signal
import time
from pathlib import Path

import pytest

from platoon_harness import Role, Session, Team
from platoon_harness.config import Secret
from platoon_harness.drivers.process import Record
from platoon_harness.runtime.paths import OWNER_TOKEN, VIEW_TOKEN, read_running
from platoon_harness.team import Budget

from ..unit.runtime.support import in_state, journal, of_type, until
from .support import (
    CLAUDE,
    CODEX,
    EFFORT,
    alive,
    empty_waits,
    end_what_is_left,
    gone,
    leaks,
    rereads,
    running_in,
    seeded,
    seen,
    spent,
    tools_called,
)

pytestmark = [
    pytest.mark.live,
    pytest.mark.timeout(240),
    pytest.mark.skipif(os.environ.get("PLATOON_HARNESS_LIVE") != "1", reason="needs PLATOON_HARNESS_LIVE=1"),
    pytest.mark.skipif(shutil.which("claude") is None, reason="claude is not installed"),
    pytest.mark.skipif(shutil.which("codex") is None, reason="codex is not installed"),
]

LIMIT = Budget(turns=12, wall="3m")
COMMAND = "echo start >> ran.log; sleep 15; echo end >> ran.log"
ASKED = f"Run this shell command once, then reply: done. The command: {COMMAND}"
QUOTE = "Quote exactly what your history shows as the result of that shell command, then say whether it ran to the end."
ROLES = {
    "claude": Role(harness="claude", model=CLAUDE, effort=EFFORT, approvals="allow"),
    "codex": Role(harness="codex", model=CODEX, effort=EFFORT, approvals="allow", sandbox="workspace-write"),
}


def harness_of(session: Session) -> int:
    record = Record.read(session.folder / "agents" / "ada")
    assert record is not None
    return record.pid


def token_of(pid: int) -> Secret:
    """A harness's own tool token, from its environment, which is this user's and this session's."""
    variables = Path(f"/proc/{pid}/environ").read_bytes().split(b"\0")
    found = next(line for line in variables if line.startswith(b"PLATOON_HARNESS_TOKEN="))
    return Secret(found.partition(b"=")[2].decode())


def log_of(work: Path) -> list[str]:
    path = work / "ran.log"
    return path.read_text().split() if path.exists() else []


async def started(session: Session) -> int:
    """Ask for the command, and return the harness that runs it, once its harness says the command is under way."""
    await in_state(session, "ada", "idle")
    await session.send("@ada", ASKED)
    await until(lambda: of_type(session, "item.recorded"), session, commands)
    return harness_of(session)


def commands(events: list) -> int:
    """How many times a model set the whole command going, as its harness reported. A part of it run again is a model
    repairing what it found, which the notice allows. One a kill cut before it ran was set going all the same, so the
    log holds no more runs than this, and may hold fewer."""
    items = [event for event in events if event.type == "item.recorded" and event.data["kind"] == "tool"]
    return len([event for event in items if event.data["phase"] == "started" and COMMAND in event.gist])


def words_of(events: list) -> list[str]:
    return [event.gist for event in events if event.type == "item.recorded" and event.data["kind"] == "message"]


@pytest.mark.parametrize("harness", ROLES)
@pytest.mark.parametrize("wait", [False, True], ids=["at-once", "after-it-went"])
async def test_a_killed_runtime_during_a_shell_tool_is_resumed_and_told(harness, wait, tmp_path):
    """Budget: at most 10 model calls, counted from the journal. `kill -9` of a detached runtime while a real shell tool
    runs, then a resume, at once or once the harness has gone. What the harness shows is asked of the model. Whether it
    runs the command again is its own call, having checked, so the test holds only that nothing ran behind the journal's
    back."""
    work, root = seeded(tmp_path / "work"), tmp_path / "root"
    team = Team(roles={"ada": ROLES[harness]}, budget=LIMIT)
    guest = await Session.start(team, name="crash", root=root, cwd=work, detach=True, plan_login=True)
    try:
        pid = await started(guest)
        secrets = [token_of(pid), Secret((guest.folder / OWNER_TOKEN).read_text())]
        secrets.append(Secret((guest.folder / VIEW_TOKEN).read_text()))
        running = read_running(guest.folder)
        assert running is not None
        os.kill(running.pid, signal.SIGKILL)
        killed = time.monotonic()
        await gone(running.pid)
        tools = [other for other in running_in(work) if other != pid]
        print(f"{harness}: at the kill: harness alive {alive(pid)}, {len(tools)} tool processes")
        if wait:
            async with asyncio.timeout(70.0):
                await gone(pid)
                print(f"{harness}: the harness went {time.monotonic() - killed:.1f} s after the runtime")
                await gone(*running_in(work))
                print(f"{harness}: the tool went {time.monotonic() - killed:.1f} s after the runtime: {log_of(work)}")

        async with Session.resume("crash", root=root) as session:
            print(f"{harness}: resumed {time.monotonic() - killed:.1f} s after the kill, {alive(pid)=}")
            await seen(session, "agent.resumed")
            secrets.append(token_of(harness_of(session)))
            await seen(session, "turn.ended")
            print(f"{harness}: told, log {log_of(work)}")
            await session.send("@ada", QUOTE)
            await seen(session, "turn.ended", count=2)
            secrets += [Secret((session.folder / name).read_text()) for name in (OWNER_TOKEN, VIEW_TOKEN)]
            events = await journal(session)
            used = await spent(session)
            tools = await tools_called(session)
            print(f"{harness}:", used, sorted(tools.items()))
            print(f"{harness}: words", words_of(events))
            print(f"{harness}: log", log_of(work))
            print(f"{harness}: empty waits", empty_waits(events), "rereads", rereads(events))
    finally:
        await guest.leave()
        print(f"{harness}: left behind", end_what_is_left(work))

    assert log_of(work).count("start") <= commands(events), "the shell tool ran behind the journal's back"
    assert leaks(guest.folder, *secrets) == []
    assert used["total"] <= 10


@pytest.mark.parametrize("harness", ROLES)
async def test_an_owner_s_stop_during_a_shell_tool_is_told_on_resume(harness, tmp_path):
    """Budget: at most 8 model calls, counted from the journal."""
    work, root = seeded(tmp_path / "work"), tmp_path / "root"
    team = Team(roles={"ada": ROLES[harness]}, budget=LIMIT)

    try:
        async with Session.start(team, name="stop", root=root, cwd=work, plan_login=True) as session:
            await started(session)
        print(f"{harness}: after the stop: {running_in(work)}, log {log_of(work)}")

        async with Session.resume("stop", root=root) as session:
            await seen(session, "turn.ended", count=2)
            ended = await of_type(session, "turn.ended")
            print(f"{harness}: turns {[event.data['reason'] for event in ended]}, log {log_of(work)}")
            await session.send("@ada", QUOTE)
            await seen(session, "turn.ended", count=3)
            events = await journal(session)
            used = await spent(session)
            tools = await tools_called(session)
            print(f"{harness}:", used, sorted(tools.items()))
            print(f"{harness}: words", words_of(events))
    finally:
        print(f"{harness}: left behind", end_what_is_left(work))

    assert log_of(work).count("start") == commands(events), "the shell tool ran behind the journal's back"
    assert used["total"] <= 8
