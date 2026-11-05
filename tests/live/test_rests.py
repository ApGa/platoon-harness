"""An agent's process is not its identity, on real models and native logins, through the public `Session`. Set
`PLATOON_HARNESS_LIVE=1` to run these, and say what ran.

Budget: at most 30 model calls in all, each test stating its own, all `claude-haiku-5-5` or `gpt-6-luna` at low effort:
10 for each harness's idle agent that rests and comes back, and 5 for each one whose harness is killed alone. Every
session has a `Budget` of turns, and none of time, as the first test moves the session's clock ten minutes.
"""

import asyncio
import os
import shutil
import signal
import time

import pytest

from platoon_harness import Session, Team
from platoon_harness.drivers.process import Record
from platoon_harness.kernel import ManualClock
from platoon_harness.team import Budget

from ..unit.runtime.support import in_state, journal, of_type
from .support import alive, end_what_is_left, running_in, seeded, seen, spent
from .test_crashes import ROLES, harness_of, started, words_of

pytestmark = [
    pytest.mark.live,
    pytest.mark.timeout(240),
    pytest.mark.skipif(os.environ.get("PLATOON_HARNESS_LIVE") != "1", reason="needs PLATOON_HARNESS_LIVE=1"),
    pytest.mark.skipif(shutil.which("claude") is None, reason="claude is not installed"),
    pytest.mark.skipif(shutil.which("codex") is None, reason="codex is not installed"),
]

LIMIT = Budget(turns=6)
REMEMBER = "Remember the word heliotrope. Reply with the single word noted."
RECALL = "Which word did I ask you to remember? Reply with that word alone."


async def rested(session: Session) -> None:
    """Until a rest has finished, as ending a real harness takes some seconds."""
    async with asyncio.timeout(75.0):
        async for _ in session._moves():
            if [event for event in await of_type(session, "effect.finished") if event.data["kind"] == "rest"]:
                return


@pytest.mark.parametrize("harness", ROLES)
async def test_an_idle_agent_rests_and_its_next_message_resumes_it_natively(harness, tmp_path):
    """Budget: at most 10 model calls, counted from the journal. Ten minutes between turns, on the session's clock, end
    the harness's process, and the next message brings it back on its native session, which still knows the word."""
    work, root = tmp_path / "work", tmp_path / "root"
    work.mkdir()
    clock = ManualClock(time.time())
    team = Team(roles={"ada": ROLES[harness]}, budget=LIMIT)

    try:
        async with Session.start(team, name="rest", root=root, cwd=work, clock=clock, plan_login=True) as session:
            await in_state(session, "ada", "idle")
            await session.send("@ada", REMEMBER)
            ended = (await seen(session, "turn.ended"))[0]
            pid = harness_of(session)
            await clock.slept_until(ended.wall_time + 600)
            clock.advance(600)
            await rested(session)
            recorded = Record.read(session.folder / "agents" / "ada")
            print(f"{harness}: after the rest, harness {pid} alive {alive(pid)}, record {recorded}")
            await session.send("@ada", RECALL)
            await seen(session, "turn.ended", count=2)
            events = await journal(session)
            used = await spent(session)
            print(f"{harness}:", used)
            print(f"{harness}: words", words_of(events))
    finally:
        print(f"{harness}: left behind", end_what_is_left(work))

    rests = [event for event in events if event.type == "effect.finished" and event.data["kind"] == "rest"]
    resumed = [event for event in events if event.type == "agent.resumed"]
    assert len(rests) == 1 and recorded is None and not alive(pid)
    assert len(resumed) == 1
    assert "heliotrope" in words_of(events)[-1].lower()
    assert used["total"] <= 10


@pytest.mark.parametrize("harness", ROLES)
async def test_a_harness_killed_alone_in_a_turn_is_resumed_once_and_told_its_turn_was_cut_off(harness, tmp_path):
    """Budget: at most 5 model calls, counted from the journal. `kill -9` of the harness alone during a real shell tool,
    as the spike did, cuts its turn off: the turn is lost with `crash_window`, the tool it left is ended, and the same
    agent comes back on its native session, told so. A kill before a harness has written its session leaves it nothing
    to reopen, which is why this waits for the tool."""
    work, root = seeded(tmp_path / "work"), tmp_path / "root"
    team = Team(roles={"ada": ROLES[harness]}, budget=LIMIT)

    try:
        async with Session.start(team, name="alone", root=root, cwd=work, plan_login=True) as session:
            os.kill(await started(session), signal.SIGKILL)
            await seen(session, "agent.resumed")
            print(f"{harness}: after the resume, still running in the work tree: {running_in(work)}")
            await seen(session, "turn.ended")
            events = await journal(session)
            ending = await session.ending()
            used = await spent(session)
            print(f"{harness}:", used, ending.reason, ending.gaps)
            print(f"{harness}: words", words_of(events))
    finally:
        print(f"{harness}: left behind", end_what_is_left(work))

    requested = [event.data for event in events if event.type == "effect.requested"]
    rests = [effect["data"]["exited"] for effect in requested if effect["kind"] == "rest"]
    told = [event.gist for event in events if event.type == "message.sent" and event.stream == "inbox/ada"]
    assert [event.type for event in events].count("turn.lost") == 1
    assert rests == ["killed by signal 9"] and ending.agents[0]["state"] == "idle"
    assert told[-1].startswith("Your last turn was cut off by a crash.")
    assert used["total"] <= 5
