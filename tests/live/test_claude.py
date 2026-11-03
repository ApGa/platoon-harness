"""The `claude` driver on a real model, on a native login. Set `PLATOON_HARNESS_LIVE=1` to run these, and say what ran.

Budget: at most 30 model calls in all, every one of them `claude-haiku-5-5`.
"""

import asyncio
import json
import os
import shutil
from pathlib import Path

import pytest

from platoon_harness import Role, Session, Team
from platoon_harness.drivers import Ready
from platoon_harness.drivers.claude import ClaudeDriver

from ..unit.drivers.support import Heard, make_spec
from ..unit.runtime.support import in_state, of_type, until

pytestmark = [
    pytest.mark.live,
    pytest.mark.timeout(240),
    pytest.mark.skipif(os.environ.get("PLATOON_HARNESS_LIVE") != "1", reason="needs PLATOON_HARNESS_LIVE=1"),
    pytest.mark.skipif(shutil.which("claude") is None, reason="claude is not installed"),
]

MODEL = "claude-haiku-5-5"
CALLS = 30
SECONDS = 90.0
MARK = "the fourth word is celadon"


def transcript(native: str) -> list[dict]:
    """What the harness wrote down, which on a native login is the one place a request can be read."""
    home = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")
    paths = list(home.glob(f"projects/*/{native}.jsonl"))
    assert len(paths) == 1, f"{native} has {len(paths)} transcripts"
    return [json.loads(line) for line in paths[0].read_text().splitlines()]


async def ended(session: Session, count: int) -> list:
    async with asyncio.timeout(SECONDS):
        return await until(lambda: of_type(session, "turn.ended"), session, lambda found: len(found) >= count)


async def test_no_model_on_the_native_login_is_the_harness_s_default_and_the_login_is_a_plan(tmp_path):
    """Budget: 0 model calls. This starts a process, asks it what it runs, and stops it."""
    driver, heard = ClaudeDriver(), Heard()

    await driver.start(make_spec(tmp_path, goal=""), heard)
    ready = await heard.until(Ready)
    await driver.stop(5.0)

    assert ready.effective_model
    assert ready.version
    assert ClaudeDriver().describe().login == "plan"


async def test_one_agent_takes_a_goal_a_delivery_an_interrupt_an_approval_and_a_resume(tmp_path):
    """Budget: at most 30 model calls, counted from the journal. The agent takes a goal, calls one of our tools, ends
    its turn, takes a delivery, is interrupted, has an approval answered through the runtime, and is resumed by a new
    process."""
    instructions = f"{MARK}. Be brief, and do exactly what you are asked and nothing else. Never call agent_finish."
    role = Role(harness="claude", model=MODEL, effort="low", count=0, instructions=instructions)
    channels = {"notes": {"kind": "board", "writers": "all", "readers": "all"}}
    team = Team(roles={"worker": role}, topology={"channels": channels})
    root, work = tmp_path / "root", tmp_path / "work"
    work.mkdir()

    async with Session.start(team, name="live", root=root, cwd=work, plan_login=True) as session:
        goal = "Call mcp__ph__board_post once, to post `hi` as `hello` on the board `notes`. Then reply: alpha"
        await session.spawn("ada", "worker", goal)
        await ended(session, 1)
        started = (await of_type(session, "agent.started"))[0]
        items = await of_type(session, "item.recorded")
        tools = [event for event in items if event.data["kind"] == "tool" and event.data["phase"] == "started"]
        assert started.data["effective_model"] == MODEL
        assert [event.gist.partition(" ")[0] for event in tools] == ["mcp__ph__board_post"]
        posted = (await of_type(session, "board.posted"))[0]
        assert posted.native["claudecode/toolUseId"] == tools[0].data["native_id"]

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
        usages = await of_type(session, "usage.reported")
        assert [event for event in usages if event.data["label"] == "unavailable"], "an aborted call has no amount"

        await session.send("@ada", "Use the Bash tool to run exactly this command, once: touch approved.txt")
        async with asyncio.timeout(SECONDS):
            asked = (await until(session.approvals, session))[0]
        await session.resolve(asked["id"], "allow", expected_version=asked["version"])
        await ended(session, 4)
        assert (work / "approved.txt").exists()
        decided = [event for event in await of_type(session, "item.recorded") if event.data["approval"] is not None]
        assert (decided[0].data["approval"], decided[0].data["outcome"]) == (asked["id"], "completed")
        native = started.data["native"]

    async with Session.resume("live", root=root) as session:
        await in_state(session, "ada", "idle")
        await session.send("@ada", "Which single word did I ask for second? Reply with that word alone.")
        await ended(session, 5)
        words = [event.gist for event in await of_type(session, "item.recorded") if event.data["kind"] == "message"]
        assert "beta" in words[-1].lower(), words
        resumed = await of_type(session, "agent.resumed")
        assert resumed
        calls = await of_type(session, "model.called")
        unknown = await of_type(session, "native.recorded")
        print(f"model calls: {len(calls)}; unknown frames: {[event.gist for event in unknown]}")

    assert len(calls) <= CALLS

    lines = transcript(native)
    shapes = {line["shapeHash"]: json.dumps(line["shape"]) for line in lines if line.get("type") == "api-request-shape"}
    requests = [line["shapeHash"] for line in lines if line.get("type") == "api-request"]
    assert requests, "the transcript records no request"
    assert [shapes[shape].count(MARK) for shape in requests] == [1] * len(requests)
