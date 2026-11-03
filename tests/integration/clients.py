"""What the TUI and SwarmChat read, held on a real binary against FakeModel. Each scenario takes a team whose one role,
`bob`, runs that binary, and each harness's test file runs it on its own."""

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

from platoon_harness import Session, Team
from platoon_harness.kernel import Delta, Event
from platoon_harness.team import Budget
from platoon_harness.testing import FakeModel

from ..unit.runtime.support import in_state, of_type, until
from .scripts import over

TIMEOUT = 60.0
SPAWN = {"name": "w", "child_role": "bob"}
SAID = "every word of this comes live before it is an item"
LIMIT = Budget(tokens=1_000_000, estimate={"tokens": 100_000})


async def followed(frames: AsyncIterator[Delta]) -> tuple[str, int]:
    """What a follower was shown live until something replaced it, and the seq of what did."""
    said = ""
    async for frame in frames:
        if frame.ended is not None and said:
            return said, frame.ended
        said = frame.text if frame.ended is not None else said + frame.text
    raise AssertionError("the live text ended before anything was said")


async def a_tail_joined_to_what_was_committed_is_the_text(team: Team, root: Path) -> None:
    async with Session.start(team, root=root, cwd=root) as session:
        await in_state(session, "bob", "idle")
        following = asyncio.ensure_future(followed(session.deltas("@bob")))
        await session.send("@bob", "go")
        said, ended = await asyncio.wait_for(following, TIMEOUT)
        messages = [event for event in await of_type(session, "item.recorded") if event.data["kind"] == "message"]
        item = [event for event in messages if event.seq <= ended][-1]
        text = (await session.get_body(item.data["body"])).decode()

    assert said.strip() and text == SAID and text.startswith(said)


async def stop_below_stops_the_turns_of_a_lead_and_its_child_and_keeps_both(team: Team, root: Path, model: FakeModel):
    async with Session.start(over(team), root=root, cwd=root) as session:
        await in_state(session, "lead", "idle")
        await session.send("@lead", "go")
        await asyncio.wait_for(model.call(0), TIMEOUT)
        await in_state(session, "w", "running")

        stopped = await session.interrupt("@lead", below=True)

        ended = await until(lambda: of_type(session, "turn.ended"), session, lambda found: len(found) == 2)
        states = {row["agent"]: row["state"] for row in await session.agents()}

    assert stopped == {"stopped": ["@lead", "@w"]}
    assert [event.data["reason"] for event in ended] == ["interrupted", "interrupted"]
    assert states == {"lead": "idle", "w": "idle"}


async def an_interrupt_under_a_tokens_limit_leaves_the_session_to_go_on(team: Team, root: Path, model: FakeModel):
    """No harness measures a call an interrupt cuts short, so the turn is charged its estimate, and the next wakes."""
    async with Session.start(team.model_copy(update={"budget": LIMIT}), root=root, cwd=root) as session:
        await in_state(session, "bob", "idle")
        await session.send("@bob", "go")
        await asyncio.wait_for(model.call(0), TIMEOUT)
        await session.interrupt("@bob")
        await until(lambda: of_type(session, "turn.ended"), session)
        cut = (await session.budgets())[0]
        await session.send("@bob", "again")
        ended = await until(lambda: of_type(session, "turn.ended"), session, lambda found: len(found) == 2)
        refused = await of_type(session, "wake.refused")
        usage = (await session.ending()).usage["tokens"]

    assert [event.data["reason"] for event in ended] == ["interrupted", "stopped"]
    assert refused == []
    assert (cut["spent"], cut["label"], cut["unmeasured"]) == (100_000, "estimated", 1)
    assert (usage["label"], usage["unmeasured"]) == ("estimated", 1) and usage["amount"] > 100_000


async def a_child_and_the_call_that_started_it(team: Team, root: Path) -> tuple[Event, list[Event], str]:
    """`bob` spawns `w` by our tool: the spawn, the tool items of `bob`'s whose `native_id` is among its anchors, and
    the turn `bob` was in."""
    given = team.canonical()
    roles = {"bob": {**given["roles"]["bob"], "may_spawn": ["bob"]}}
    spawning = Team.model_validate({**given, "roles": roles, "topology": {"limits": {"max_depth": 1}}})
    async with Session.start(spawning, root=root, cwd=root) as session:
        await in_state(session, "bob", "idle")
        await session.send("@bob", "go")
        await until(lambda: of_type(session, "turn.ended"), session)
        spawned = next(event for event in await of_type(session, "agent.spawned") if event.agent == "w")
        tools = [event for event in await of_type(session, "item.recorded") if event.data["kind"] == "tool"]
        turn = next(event for event in await of_type(session, "turn.started") if event.agent == "bob")

    under = [item for item in tools if item.agent == "bob" and item.data["native_id"] in spawned.native.values()]
    return spawned, under, turn.data["turn"]
