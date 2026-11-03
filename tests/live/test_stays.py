"""Agents that stay, on real models and native logins, through the public `Session`. Set `PLATOON_HARNESS_LIVE=1` to run
these, and say what ran.

Budget: at most 67 model calls in all, each test stating its own, `claude-haiku-5-5` or `gpt-6-luna` at low effort.
Every session has a `Budget`, so that a runaway stops itself.
"""

import os
import shutil
from collections import Counter

import pytest

from platoon_harness import Role, Session, Team
from platoon_harness.team import Budget

from ..unit.runtime.support import journal
from .support import CLAUDE, CODEX, EFFORT, rereads, seeded, seen, spent, tools_called

pytestmark = [
    pytest.mark.live,
    pytest.mark.timeout(540),
    pytest.mark.skipif(os.environ.get("PLATOON_HARNESS_LIVE") != "1", reason="needs PLATOON_HARNESS_LIVE=1"),
]

LIMIT = Budget(turns=24, wall="4m")
SETTLE = "180s"
STEPS = (
    "Start one agent in the role `helper`, with `stays` true and the goal: reply alpha. Each time it answers, take the "
    "next step and nothing else, then end your turn. First send it the task: reply beta. Then ask it what it meant by "
    "beta. Then {end}"
)


def team_of(role: Role) -> Team:
    """A lead that may spawn a helper and message it. The helper answers through the monitor alone."""
    lead = role.model_copy(update={"may_spawn": ("helper",)})
    topology = {"edges": {"lead": ["children", "human"]}, "limits": {"max_hops": 10}}
    return Team(roles={"lead": lead, "helper": role}, topology=topology, budget=LIMIT)


def claude() -> Role:
    return Role(harness="claude", model=CLAUDE, effort=EFFORT, approvals="allow")


def codex() -> Role:
    return Role(harness="codex", model=CODEX, effort=EFFORT, approvals="allow", sandbox="read-only")


async def flow(session: Session, end: str) -> tuple[list, dict]:
    """The owner's flow, asked of the lead in plain words, and what the journal says of it."""
    await session.send("@lead", STEPS.format(end=end))
    ending = await session.settled(timeout=SETTLE)
    events = await journal(session)
    used = await spent(session)
    print(ending.reason, used, sorted((await tools_called(session)).items()))
    print("woken turns, and reads of what a wake had handed:", rereads(events))
    print("statuses:", {row["agent"]: (row["status"], row["reason"]) for row in ending.agents})
    return events, used


def wakes_of(events: list, agent: str) -> list[list[str]]:
    """What each wake handed an agent, by sender: an agent's address, or the child a report is about."""
    entries = {
        f"{event.stream}@{event.version}": event.data["subject"] or event.data["sender"]
        for event in events
        if event.type == "message.sent"
    }
    offers = [event for event in events if event.type == "context.offered" and event.agent == agent]
    return [[entries[item["ref"]] for item in offer.data["items"]] for offer in offers if offer.data["how"] == "wake"]


def checked(events: list, helper_turns: int) -> str:
    """One helper process for every task, each of its answers sent to the lead, and the lead woken by those and by
    nothing else. The lead may take an answer within a turn, by a held `wait`, so it is woken at most once for each. It
    names the helper, which is returned."""
    helper = next(event.agent for event in events if event.type == "agent.spawned" and event.data["role"] == "helper")
    turns = Counter(event.agent for event in events if event.type == "turn.started")
    started = [event.agent for event in events if event.type in ("agent.started", "agent.resumed")]
    reports = [event for event in events if event.type == "message.sent" and event.data["subject"] == helper]
    wakes = wakes_of(events, "lead")
    print("the lead's wakes:", wakes)
    assert started == ["lead", helper], started
    assert turns[helper] == helper_turns
    assert len(reports) >= helper_turns
    assert all(helper in handed for handed in wakes[1:]), wakes
    assert turns["lead"] <= helper_turns + 1
    return helper


async def test_a_claude_lead_asks_a_helper_that_stays_twice_more_and_retires_it(tmp_path):
    """Budget: at most 30 model calls, counted from the journal. Three tasks for one helper process, then a retire."""
    work = seeded(tmp_path / "work")

    async with Session.start(team_of(claude()), root=tmp_path / "root", cwd=work, plan_login=True) as session:
        events, used = await flow(session, "retire it, and finish.")

    helper = checked(events, helper_turns=3)
    statuses = {event.agent: event.data["status"] for event in events if event.type == "agent.ended"}
    assert statuses == {helper: "retired", "lead": "finished"}
    assert used["total"] <= 30


@pytest.mark.skipif(shutil.which("codex") is None, reason="codex is not installed")
async def test_a_codex_lead_asks_a_helper_that_stays_twice_more_and_has_it_finish(tmp_path):
    """Budget: at most 30 model calls, counted from the journal. Three tasks for one helper process, then the lead tells
    it to finish, which it does itself."""
    work = seeded(tmp_path / "work")

    async with Session.start(team_of(codex()), root=tmp_path / "root", cwd=work, plan_login=True) as session:
        events, used = await flow(session, "tell it to finish; once it has, finish.")

    helper = checked(events, helper_turns=4)
    statuses = {event.agent: event.data["status"] for event in events if event.type == "agent.ended"}
    assert statuses == {helper: "finished", "lead": "finished"}
    assert [event.agent for event in events if event.type == "agent.finished"][:1] == [helper]
    assert used["total"] <= 30


@pytest.mark.skipif(shutil.which("codex") is None, reason="codex is not installed")
async def test_a_codex_agent_that_stays_answers_by_ending_its_turn_and_finishes_when_told(tmp_path):
    """Budget: at most 7 model calls, counted from the journal, what the test above had left when it failed on a helper
    that held a `wait` for its parent's next message instead of answering. A human is the parent, so only the child's
    half runs: two tasks, each answered at the end of a turn, then a finish when told."""
    team = Team(roles={"helper": codex().model_copy(update={"count": 0})}, budget=Budget(turns=4, wall="3m"))
    work = seeded(tmp_path / "work")

    async with Session.start(team, root=tmp_path / "root", cwd=work, plan_login=True) as session:
        await session.spawn("helper", "helper", "Reply alpha.", stays=True)
        await seen(session, "turn.ended")
        await session.send("@helper", "Reply beta.")
        await seen(session, "turn.ended", count=2)
        await session.send("@helper", "You are done: finish.")
        await seen(session, "agent.ended")
        events = await journal(session)
        used = await spent(session)
        tools = await tools_called(session)
        print(used, sorted(tools.items()), rereads(events))

    reports = [event.gist for event in events if event.type == "message.sent" and event.data["subject"] == "helper"]
    print("reports:", reports)
    assert used["turns"] == {"helper": 3}
    assert "alpha" in reports[0].lower() and "beta" in reports[1].lower()
    assert [event.data["status"] for event in events if event.type == "agent.ended"] == ["finished"]
    assert not [name for (_, name) in tools if name.endswith("__wait")], "it waited instead of ending its turn"
    assert used["total"] <= 7
