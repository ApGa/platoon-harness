"""The `codex` driver on a real model, on a native login. Set `PLATOON_HARNESS_LIVE=1` to run these, and say what ran.

Budget: at most 30 model calls in all, each test stating its own, every one of them `gpt-6-luna` at low effort, or
`claude-haiku-5-5` for the mixed team. A call an interrupt cut short reports nothing, so that one is counted by hand.
"""

import asyncio
import os
import shutil

import pytest

from platoon_harness import Role, Session, Team
from platoon_harness.drivers import Ready
from platoon_harness.drivers.codex import CodexDriver

from ..unit.drivers.support import Heard, make_spec
from ..unit.runtime.support import in_state, of_type, until

pytestmark = [
    pytest.mark.live,
    pytest.mark.timeout(240),
    pytest.mark.skipif(os.environ.get("PLATOON_HARNESS_LIVE") != "1", reason="needs PLATOON_HARNESS_LIVE=1"),
    pytest.mark.skipif(shutil.which("codex") is None, reason="codex is not installed"),
]

MODEL = "gpt-6-luna"
EFFORT = "low"
SECONDS = 90.0
BRIEF = "Be brief, and do exactly what you are asked and nothing else."
STAY = "You are never done, so never call agent_finish. A message reaches you whole, so never call message_read."
CHANNELS = {"notes": {"kind": "board", "writers": "all", "readers": "all"}}


async def ended(session: Session, count: int) -> list:
    async with asyncio.timeout(SECONDS):
        return await until(lambda: of_type(session, "turn.ended"), session, lambda found: len(found) >= count)


async def test_no_model_on_the_native_login_is_the_harness_s_default_and_the_login_is_a_plan(tmp_path):
    """Budget: 0 model calls. This opens a thread, reads what it runs, and stops."""
    driver, heard = CodexDriver(), Heard()

    await driver.start(make_spec(tmp_path, goal=""), heard)
    ready = await heard.until(Ready)
    await driver.stop(5.0)

    assert ready.effective_model
    assert ready.version
    assert CodexDriver().describe().login == "plan"


def one_agent() -> Team:
    role = Role(
        harness="codex", model=MODEL, effort=EFFORT, sandbox="read-only", count=0, instructions=f"{BRIEF} {STAY}"
    )
    return Team(roles={"worker": role}, topology={"channels": CHANNELS})


async def test_one_agent_reaches_our_tool_on_its_first_turn_takes_a_delivery_and_is_interrupted(tmp_path):
    """Budget: at most 8 model calls, counted from the journal, plus the one the interrupt cuts short. The catalog is
    served remotely and can change without a CLI update, so this is what shows our tool still reaches the model. The
    agent stays, so the preamble says what its role says: in run 27 the role's words alone did not keep it there."""
    async with Session.start(one_agent(), root=tmp_path / "root", cwd=tmp_path, plan_login=True) as session:
        goal = (
            "Call the board_post tool of the ph server once, to post `hi` as `hello` on the board `notes`. "
            "Then reply: alpha"
        )
        await session.spawn("ada", "worker", goal, stays=True)
        await ended(session, 1)
        started = (await of_type(session, "agent.started"))[0]
        items = await of_type(session, "item.recorded")
        tools = [event for event in items if event.data["kind"] == "tool" and event.data["phase"] == "started"]
        assert started.data["effective_model"] == MODEL
        assert [event for event in tools if event.gist.startswith("mcp__ph__board_post")], "our tool was never reached"
        posted = (await of_type(session, "board.posted"))[0]
        anchor = posted.native["callId"]
        assert anchor in [event.data["native_id"] for event in tools], (
            "the tool item names what the call was anchored to"
        )
        assert anchor.startswith("exec-"), "the anchor is the script's, not a model call's"

        await session.send("@ada", "Reply with the single word beta.")
        await ended(session, 2)

        await session.send("@ada", "Count aloud from 1 to 400, one number per line, with no other words.")
        await in_state(session, "ada", "running")
        async with asyncio.timeout(SECONDS):
            async for frame in session.deltas("@ada"):
                if any(character.isdigit() for character in frame.text):
                    break
        await session.interrupt("@ada")
        turns = await ended(session, 3)
        assert turns[-1].data["reason"] == "interrupted"
        gaps = await of_type(session, "gap.recorded")
        assert [event for event in gaps if event.data["what"] == "usage_lower_bound"], "a cut call reports nothing"
        calls = await of_type(session, "model.called")
        unknown = await of_type(session, "native.recorded")
        print(f"model calls: {len(calls)}; unknown frames: {[event.gist for event in unknown]}")

    assert len(calls) <= 8


async def test_an_approval_goes_through_the_runtime_and_a_new_process_resumes_the_thread(tmp_path):
    """Budget: at most 6 model calls, counted from the journal. The sandbox is read-only, so the command needs the
    runtime's word, and what came of it is read from the item."""
    root, work = tmp_path / "root", tmp_path / "work"
    work.mkdir()

    async with Session.start(one_agent(), name="live", root=root, cwd=work, plan_login=True) as session:
        goal = (
            "Run this shell command once, with sandbox_permissions set to require_escalated and a one-word "
            "justification, then reply: gamma. The command: touch approved.txt"
        )
        await session.spawn("ada", "worker", goal)
        async with asyncio.timeout(SECONDS):
            asked = (await until(session.approvals, session))[0]
        await session.resolve(asked["id"], "allow", expected_version=asked["version"])
        await ended(session, 1)
        assert (work / "approved.txt").exists()
        decided = [event for event in await of_type(session, "item.recorded") if event.data["approval"] is not None]
        assert (decided[0].data["approval"], decided[0].data["outcome"]) == (asked["id"], "completed")

    async with Session.resume("live", root=root) as session:
        await in_state(session, "ada", "idle")
        await session.send("@ada", "Which file did the command touch? Reply with its name alone.")
        await ended(session, 2)
        words = [event.gist for event in await of_type(session, "item.recorded") if event.data["kind"] == "message"]
        assert "approved" in words[-1].lower(), words
        assert await of_type(session, "agent.resumed")
        calls = await of_type(session, "model.called")
        unknown = await of_type(session, "native.recorded")
        print(f"model calls: {len(calls)}; unknown frames: {[event.gist for event in unknown]}")

    assert len(calls) <= 6


async def test_a_claude_agent_and_a_codex_agent_share_a_message_and_a_board_entry(tmp_path):
    """Budget: at most 12 model calls, counted from the journal, of `claude-haiku-5-5` and `gpt-6-luna`. The first
    agent posts on the board and tells the second, which reads the entry and answers."""
    ann = Role(harness="claude", model="claude-haiku-5-5", effort=EFFORT, count=0, instructions=f"{BRIEF} {STAY}")
    bea = Role(harness="codex", model=MODEL, effort=EFFORT, instructions=f"{BRIEF} {STAY}")
    edges = {"ann": ["role:bea"], "bea": ["role:ann"]}
    team = Team(
        roles={"ann": ann, "bea": bea}, topology={"channels": CHANNELS, "edges": edges, "limits": {"max_hops": 3}}
    )
    work = tmp_path / "work"
    work.mkdir()

    async with Session.start(team, name="mixed", root=tmp_path / "root", cwd=work, plan_login=True) as session:
        await in_state(session, "bea", "idle")
        goal = (
            "Call mcp__ph__board_post once, to post the word `cinnabar` as `word` on the board `notes`. Then call "
            "mcp__ph__message_send once, to tell @bea: read `word` on the board `notes` and send me what it says. "
            "Then stop."
        )
        await session.spawn("ann", "ann", goal)

        async with asyncio.timeout(SECONDS * 2):
            sent = await until(
                lambda: of_type(session, "message.sent"),
                session,
                lambda found: {event.actor for event in found} >= {"agent:ann", "agent:bea"},
            )
            await ended(session, 3)

        posted = await of_type(session, "board.posted")
        items = await of_type(session, "item.recorded")
        calls = await of_type(session, "model.called")
        unknown = await of_type(session, "native.recorded")
        started = {event.agent: event.data for event in await of_type(session, "agent.started")}
        print(f"model calls: {len(calls)}; unknown frames: {[event.gist for event in unknown]}")

    assert [event.agent for event in posted] == ["ann"]
    assert [event for event in items if event.agent == "bea" and event.gist.startswith("mcp__ph__board_get")]
    told = [event.gist for event in items if event.agent == "bea" and event.gist.startswith("mcp__ph__message_send")]
    assert told and "cinnabar" in told[0]
    assert {event.actor for event in sent} >= {"agent:ann", "agent:bea"}
    assert (started["ann"]["effective_model"], started["bea"]["effective_model"]) == ("claude-haiku-5-5", MODEL)
    assert len(calls) <= 12


async def test_a_codex_agent_s_own_sub_agent_runs_inside_the_turn_that_started_it(tmp_path):
    """Budget: at most 10 model calls, counted from the journal, a child's own among them, which reach us as the tree's.
    Current models reach their sub-agents through the multi-agent V2 tools, which had run on FakeModel alone, at V1.
    This says what frames come, whether the turn ends only once the child has, and whether `settled` sees it live."""
    team = Team(roles={"ada": Role(harness="codex", model=MODEL, effort=EFFORT, approvals="allow", instructions=BRIEF)})
    work = tmp_path / "work"
    work.mkdir()

    async with Session.start(team, name="native", root=tmp_path / "root", cwd=work, plan_login=True) as session:
        await in_state(session, "ada", "idle")
        await session.send(
            "@ada",
            "Use your own sub-agent tools, not the ph ones, to start one sub-agent that runs `sleep 8 && touch "
            "child.txt` in the shell and then says done. Wait for it to finish, then reply: done",
        )
        async with asyncio.timeout(SECONDS):
            seen = await until(lambda: of_type(session, "child.seen"), session)
        during = await session.status()
        live = not (work / "child.txt").exists()
        turns = await ended(session, 1)
        events = [event async for event in session.events()]
        calls = [event for event in events if event.type == "model.called"]
        items = [event.gist for event in events if event.type == "item.recorded" and event.data["kind"] == "tool"]
        unknown = [event.gist for event in events if event.type == "native.recorded"]
        gaps = [event.data["what"] for event in events if event.type == "gap.recorded"]
        print(f"model calls: {len(calls)}; child.seen: {[event.data for event in seen]}; during: {during}")
        print(f"tools: {items}; unknown frames: {unknown}; gaps: {gaps}; turn: {turns[-1].data}")

    assert live and "open_turn" in during["blockers"], "a live child sits inside an open turn"
    assert (work / "child.txt").exists(), "the turn ended before the child did"
    assert len(calls) <= 10
