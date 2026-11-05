"""What the TUI and SwarmChat read, the TUI itself and what the provenance queries answer, held on a real binary against
FakeModel. Each scenario takes a team whose one role, `bob`, runs that binary, and each harness's test file runs it on
its own."""

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from typing import NamedTuple

from platoon_harness import Session, Team
from platoon_harness.kernel import Delta, Event
from platoon_harness.primitives import Contributors, Exposure, Lineage, Seen, Uses
from platoon_harness.team import Budget
from platoon_harness.testing import FakeModel
from platoon_harness_cli.provenance import Line, read
from platoon_harness_cli.tui.app import TerminalUI
from platoon_harness_cli.tui.provenance import Provenance
from platoon_harness_cli.tui.transcript import Focus, Transcript

from ..unit.runtime.support import in_state, of_type, until
from ..unit.tui.support import drawn, workspace
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


async def a_spawn_and_the_call_that_made_it(team: Team, root: Path) -> tuple[Event, list[Event]]:
    """`bob` spawns `w` by our tool: the spawn, and the tool items of `bob`'s whose `native_id` is among its anchors."""
    given = team.canonical()
    roles = {"bob": {**given["roles"]["bob"], "may_spawn": ["bob"]}}
    spawning = Team.model_validate({**given, "roles": roles, "topology": {"limits": {"max_depth": 1}}})
    async with Session.start(spawning, root=root, cwd=root) as session:
        await in_state(session, "bob", "idle")
        await session.send("@bob", "go")
        await until(lambda: of_type(session, "turn.ended"), session)
        spawned = next(event for event in await of_type(session, "agent.spawned") if event.data["name"] == "w")
        tools = [event for event in await of_type(session, "item.recorded") if event.data["kind"] == "tool"]

    under = [item for item in tools if item.agent == "bob" and item.data["native_id"] in spawned.native.values()]
    return spawned, under


async def a_read_and_what_confirmed_it(team: Team, root: Path) -> tuple[Event, list[Event]]:
    """`bob`, woken by a person's message, reads its inbox by our tool: that read's offer, and every confirmation of an
    offer to `bob`, which only its harness's own reports write."""
    async with Session.start(team, root=root, cwd=root) as session:
        await in_state(session, "bob", "idle")
        await session.send("@bob", "read your inbox")
        await until(lambda: of_type(session, "turn.ended"), session)
        offers = await of_type(session, "context.offered")
        confirmations = await of_type(session, "context.delivered")

    read = next(offer for offer in offers if offer.data["how"] == "read")
    return read, confirmations


CITED = "inbox/bob@1"
CITING = {"to": "@you", "gist": "read it", "based_on": [CITED]}
"""What `bob` sends once it has read its inbox: an answer citing the message that woke it."""


class Traced(NamedTuple):
    """What the four queries say of a cited write and of what it cites."""

    lineage: Lineage
    exposure: Exposure
    uses: Uses
    contributors: Contributors


async def a_read_then_a_cited_write(team: Team, root: Path) -> Traced:
    """`bob`, woken by a person's message, reads its inbox by our tool and answers citing that message: lineage and
    contributors of the answer, bob's exposure to the message before it, and the message's uses."""
    answering = Team.model_validate({**team.canonical(), "topology": {"edges": {"bob": ["human"]}}})
    async with Session.start(answering, root=root, cwd=root) as session:
        await in_state(session, "bob", "idle")
        await session.send("@bob", "read your inbox, then answer citing what you read")
        await until(lambda: of_type(session, "turn.ended"), session)
        sent = next(event for event in await of_type(session, "message.sent") if event.actor == "agent:bob")
        answer = f"{sent.stream}@{sent.version}"
        return Traced(
            await session.lineage(answer),
            await session.exposure("@bob", CITED, before=answer),
            await session.uses(CITED),
            await session.contributors(answer),
        )


def hold_their_bounds(traced: Traced, bound: str) -> None:
    """What every harness's answers say alike: the citation is the person's message, which bob was handed and took
    below the bound, every answer is about a turn that has ended, and the walk back reaches bob and then the person."""
    lineage, exposure, uses, contributors = traced
    (declared,) = lineage.declared
    assert (declared.ref, declared.maker, lineage.bound.by) == (CITED, "human:you", bound)
    assert isinstance(declared.exposure, Seen) and isinstance(exposure, Seen) and exposure.bound == lineage.bound
    assert {row.kind for row in uses.rows} == {"declared", "observed"} and uses.totals["declared"] == 1
    assert [(row.maker, row.kinds) for row in contributors.rows] == [("agent:bob", ()), ("human:you", ("declared",))]
    assert not (lineage.open or exposure.open or uses.open or contributors.open)


async def the_tui_shows_where_a_cited_write_came_from(team: Team, root: Path) -> list[Line]:
    """What the TUI's `/provenance` says of `bob`'s answer, the newest line sent to the person, once bob has read the
    message that woke it by our tool and answered citing it. Its caller points `PLATOON_HARNESS_HOME` at `root`."""
    answering = Team.model_validate({**team.canonical(), "topology": {"edges": {"bob": ["human"]}}})
    async with Session.start(answering, name="s", root=root, cwd=root) as session:
        await in_state(session, "bob", "idle")
        await session.send("@bob", "read your inbox, then answer citing what you read")
        await until(lambda: of_type(session, "turn.ended"), session)
        app = TerminalUI("s")
        async with app.run_test(size=(140, 40)) as pilot:
            await drawn(pilot, lambda text: "@bob" in text, within=TIMEOUT)
            await workspace(app).show(Focus.of_person("human:you"))
            await drawn(pilot, lambda text: CITING["gist"] in text, within=TIMEOUT)
            await pilot.press("slash", *"provenance", "enter")
            await drawn(pilot, lambda text: "Credit and rewards" in text, within=TIMEOUT)
            panel = app.screen
            assert isinstance(panel, Provenance)
            return panel.lines


class Panelled(NamedTuple):
    """What a provenance panel says of `bob`'s tool item for its cited write, with the ref of the model call that item's
    report names and of the write its command made."""

    lines: list[Line]
    call: str
    written: str


async def a_tool_item_and_what_its_command_made(team: Team, root: Path) -> Panelled:
    """`bob`, woken by a person's message, reads its inbox and answers citing it: the panel of the tool item its
    harness reported for the answer, as a person reaches it from bob's own transcript, where the answer shows as it."""
    answering = Team.model_validate({**team.canonical(), "topology": {"edges": {"bob": ["human"]}}})
    async with Session.start(answering, root=root, cwd=root) as session:
        await in_state(session, "bob", "idle")
        await session.send("@bob", "read your inbox, then answer citing what you read")
        await until(lambda: of_type(session, "turn.ended"), session)
        sent = next(event for event in await of_type(session, "message.sent") if event.actor == "agent:bob")
        (anchor,) = sent.native.values()
        items = [event for event in await of_type(session, "item.recorded") if event.data["native_id"] == anchor]
        calls = [event for event in await of_type(session, "model.called") if event.model is not None]
        call = next(event for event in calls if event.model and event.model.call_id == items[0].data["call_id"])
        panel = await read(session, f"{items[-1].stream}@{items[-1].version}")
        return Panelled(panel.lines, f"{call.stream}@{call.version}", f"{sent.stream}@{sent.version}")


async def the_tui_sends_from_its_composer_and_draws_the_reply_once(team: Team, root: Path) -> None:
    """The TUI, as a guest over the socket: a message typed in its composer reaches the harness once, and the reply
    is drawn once, as a line of the transcript. Its caller points `PLATOON_HARNESS_HOME` at `root`."""
    async with Session.start(team, name="s", root=root, cwd=root) as session:
        await in_state(session, "bob", "idle")
        app = TerminalUI("s")
        async with app.run_test(size=(120, 30)) as pilot:
            await drawn(pilot, lambda text: "@bob" in text, within=TIMEOUT)
            await pilot.press(*"go", "enter")
            await drawn(pilot, lambda text: f"@bob  {SAID}" in text, within=TIMEOUT)
            lines = [block.line.plain for block in workspace(app).query_one(Transcript).blocks]
        sent = [event for event in await of_type(session, "message.sent") if event.actor == "human:you"]
        said = [event for event in await of_type(session, "item.recorded") if event.data["kind"] == "message"]

    assert [event.gist for event in sent] == ["go"] and [event.gist for event in said] == [SAID]
    assert sum(SAID in line for line in lines) == 1 and sum(line.endswith("go") for line in lines) == 1
