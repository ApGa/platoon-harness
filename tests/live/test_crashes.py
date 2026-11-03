"""Real harnesses through crashes, on real models and native logins, through the public `Session`. Set
`PLATOON_HARNESS_LIVE=1` to run these, and say what ran.

Budget: at most 100 model calls in all, each test stating its own, all `claude-haiku-5-5` or `gpt-6-luna` at low effort.
Every session has a `Budget`, so that a runaway stops itself. What a process outside the session did only a look can
tell, so these look, and each look is bounded.
"""

import os
import shutil
import signal
import time
from pathlib import Path

import pytest

from platoon_harness import Role, Session, Team
from platoon_harness.config import Secret
from platoon_harness.drivers import Delivery, Item, Ready, TurnEnded
from platoon_harness.drivers.claude import ClaudeDriver
from platoon_harness.drivers.codex import CodexDriver
from platoon_harness.drivers.process import Record
from platoon_harness.runtime.paths import OWNER_TOKEN, VIEW_TOKEN, read_running
from platoon_harness.team import Budget

from ..unit.drivers.support import Heard, make_spec
from ..unit.runtime.support import in_state, journal, of_type
from .support import (
    CLAUDE,
    CODEX,
    EFFORT,
    alive,
    end_what_is_left,
    leaks,
    polled,
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

LIMIT = Budget(turns=12, wall="3m")  # A limit in tokens would refuse the wake a lost turn needs, which is by design.
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


async def started(session: Session, work: Path) -> int:
    """Ask for the command, and return the harness that runs it, once the command is under way."""
    await in_state(session, "ada", "idle")
    await session.send("@ada", ASKED)
    await polled(lambda: log_of(work))
    return harness_of(session)


def commands(events: list) -> int:
    """How many times a model set the command going, as its harness reported."""
    items = [event for event in events if event.type == "item.recorded" and event.data["kind"] == "tool"]
    return len([event for event in items if event.data["phase"] == "started" and "echo start" in event.gist])


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
        pid = await started(guest, work)
        secrets = [token_of(pid), Secret((guest.folder / OWNER_TOKEN).read_text())]
        secrets.append(Secret((guest.folder / VIEW_TOKEN).read_text()))
        running = read_running(guest.folder)
        assert running is not None
        os.kill(running.pid, signal.SIGKILL)
        killed = time.monotonic()
        await polled(lambda: not alive(running.pid))
        tools = [other for other in running_in(work) if other != pid]
        print(f"{harness}: at the kill: harness alive {alive(pid)}, {len(tools)} tool processes")
        if wait:
            await polled(lambda: not alive(pid), within=40.0)
            print(f"{harness}: the harness went {time.monotonic() - killed:.1f} s after the runtime")
            await polled(lambda: not running_in(work), within=30.0)
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
    finally:
        await guest.leave()
        print(f"{harness}: left behind", end_what_is_left(work))

    assert log_of(work).count("start") == commands(events), "the shell tool ran behind the journal's back"
    assert leaks(guest.folder, *secrets) == []
    assert used["total"] <= 10


@pytest.mark.parametrize("harness", ROLES)
async def test_an_owner_s_stop_during_a_shell_tool_is_told_on_resume(harness, tmp_path):
    """Budget: at most 8 model calls, counted from the journal."""
    work, root = seeded(tmp_path / "work"), tmp_path / "root"
    team = Team(roles={"ada": ROLES[harness]}, budget=LIMIT)

    try:
        async with Session.start(team, name="stop", root=root, cwd=work, plan_login=True) as session:
            await started(session, work)
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


def driver_of(harness: str) -> ClaudeDriver | CodexDriver:
    return ClaudeDriver() if harness == "claude" else CodexDriver()


async def cured(harness: str, native: str, work: Path, folder: Path) -> str:
    """Whether a harness's own resume gets its session back, as nothing in a session asks it to yet."""
    spec = make_spec(
        folder, goal="", cwd=work, model=ROLES[harness].model, effort=EFFORT, resume=native, folder=folder / "again"
    )
    driver, heard = driver_of(harness), Heard()
    await driver.start(spec, heard)
    await heard.until(Ready)
    try:
        await driver.deliver(
            Delivery(input="1", boundary="turn", text="Which command did I ask for? One line.", items=())
        )
        await heard.until(TurnEnded)
    finally:
        await driver.stop(5.0)
    return " ".join(item.gist for item in heard.of(Item) if item.kind == "message")


@pytest.mark.parametrize("harness", ROLES)
@pytest.mark.parametrize("when", ["during-a-tool", "between-turns"])
async def test_a_harness_killed_alone_ends_its_agent_and_a_native_resume_cures_it(harness, when, tmp_path):
    """Budget: at most 8 model calls, counted from the journal, plus the one turn of a native resume, which no session
    counts, at most 3. `kill -9` of the harness alone, with the runtime well, shows how its turn ends. Then a new
    process on its native id shows what a resume would cure."""
    work, root = seeded(tmp_path / "work"), tmp_path / "root"
    team = Team(roles={"ada": ROLES[harness]}, budget=LIMIT)

    try:
        async with Session.start(team, name="alone", root=root, cwd=work, plan_login=True) as session:
            if when == "during-a-tool":
                pid = await started(session, work)
            else:
                await in_state(session, "ada", "idle")
                await session.send("@ada", "Reply with the single word ready, and do not finish.")
                await seen(session, "turn.ended")
                pid = harness_of(session)
            native = (await of_type(session, "agent.started"))[0].data["native"]
            os.kill(pid, signal.SIGKILL)
            killed = time.monotonic()
            lost = (await seen(session, "agent.ended"))[0]
            print(f"{harness} {when}: ended in {time.monotonic() - killed:.2f} s: {lost.data}")
            turns = [event.data["reason"] for event in await of_type(session, "turn.ended")]
            print(f"{harness} {when}: turns {turns}, still running {running_in(work)}")
            ending = await session.ending()
            used = await spent(session)
            print(f"{harness} {when}:", ending.reason, ending.gaps, used)
        print(f"{harness} {when}: after the session {running_in(work)}, log {log_of(work)}")
        end_what_is_left(work)

        said = await cured(harness, native, work, tmp_path / "cure")
        print(f"{harness} {when}: on a native resume: {said}")
    finally:
        print(f"{harness} {when}: left behind", end_what_is_left(work))

    assert lost.data["status"] == "lost"
    assert used["total"] <= 8
