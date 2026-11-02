"""The primitives under a real compiled topology: the only thing the two share is `Grant`."""

from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from platoon_harness.kernel import Kernel, ManualClock
from platoon_harness.primitives import PRIMITIVES
from platoon_harness.team import Team
from platoon_harness.topology.compile import compile

from .support import channel, gists, read, refusal, result_of, send, spawn

TEAM = """
[roles.lead]
harness = "claude"
may_spawn = ["worker"]

[roles.worker]
harness = "codex"

[topology.manager-worker]
manager = "lead"
workers = "worker"
"""


@pytest.fixture
async def team(tmp_path: Path) -> AsyncIterator[Kernel]:
    kernel = Kernel.open(tmp_path / "session", clock=ManualClock(1000.0), extensions=PRIMITIVES)
    result_of(await kernel.submit(kernel.runtime, "session.open", {"roles": {"lead": {}, "worker": {}}}))
    built = Team.loads(TEAM)
    for grant in compile(built):
        result_of(await kernel.submit(kernel.runtime, "grant.add", grant.model_dump()))
    await channel(kernel, "tasks", kind="queue")
    yield kernel
    kernel.close()


async def test_a_lead_spawns_only_what_may_spawn_allows(team):
    lead = await spawn(team, "lead", role="lead")
    worker = await spawn(team, "w1", by=lead)

    assert refusal(
        await team.submit(worker, "agent.spawn", {"name": "w2", "child_role": "worker", "goal": "x"})
    ).code == ("not_permitted")


async def test_edges_decide_who_reaches_whom(team):
    lead = await spawn(team, "lead", role="lead")
    w1, w2 = await spawn(team, "w1", by=lead), await spawn(team, "w2", by=lead)

    await send(team, lead, "@w1", "go")
    await send(team, w1, "@lead", "done")

    assert gists(await read(team, lead, "@lead")) == ["done"]
    assert refusal(await team.submit(w1, "message.send", {"to": "@w2", "gist": "psst"})).code == "not_permitted"
    assert refusal(await team.submit(w2, "message.read", {"channel": "@w1"})).code == "not_permitted"


async def test_a_lead_queues_and_workers_claim(team):
    lead = await spawn(team, "lead", role="lead")
    worker = await spawn(team, "w1", by=lead)

    result_of(await team.submit(lead, "task.add", {"queue": "tasks", "gist": "do it"}))
    result_of(await team.submit(worker, "task.claim", {"queue": "tasks"}))
    result_of(await team.submit(worker, "task.complete", {"queue": "tasks"}))

    assert refusal(await team.submit(worker, "task.add", {"queue": "tasks", "gist": "x"})).code == "not_permitted"


async def test_everyone_shares_the_board(team):
    lead = await spawn(team, "lead", role="lead")
    worker = await spawn(team, "w1", by=lead)
    await channel(team, "notes", kind="board")

    result_of(await team.submit(worker, "board.post", {"board": "notes", "name": "spec", "gist": "v1"}))

    assert result_of(await team.submit(lead, "board.query", {"board": "notes"}))["total"] == 1


async def test_a_parent_can_write_to_a_child_before_it_has_started(team):
    lead = await spawn(team, "lead", role="lead")
    result_of(await team.submit(lead, "agent.spawn", {"name": "w1", "child_role": "worker", "goal": "x"}))

    await send(team, lead, "@w1", "your brief")


async def test_a_join_on_a_child_that_has_not_started_parks(team):
    lead = await spawn(team, "lead", role="lead")
    result_of(await team.submit(lead, "agent.spawn", {"name": "w1", "child_role": "worker", "goal": "x"}))

    assert result_of(await team.submit(lead, "wait", {"agents": ["w1"]}))["state"] == "parked"


async def test_a_join_on_a_child_that_has_ended_releases(team):
    lead = await spawn(team, "lead", role="lead")
    worker = await spawn(team, "w1", by=lead)
    result_of(await team.submit(worker, "agent.finish", {"gist": "done"}))

    assert result_of(await team.submit(lead, "wait", {"agents": ["w1"]}))["state"] == "released"


async def test_an_ended_child_still_answers_for_itself(team):
    lead = await spawn(team, "lead", role="lead")
    worker = await spawn(team, "w1", by=lead)
    result_of(await team.submit(worker, "agent.finish", {"gist": "done"}))

    assert result_of(team.query(lead, "agent.status", {"agent": "w1"}))["state"] == "ended"
    assert refusal(await team.submit(lead, "message.send", {"to": "@w1", "gist": "there?"})).code == "undeliverable"


async def test_any_agent_may_wait_and_finish(team):
    lead = await spawn(team, "lead", role="lead")
    worker = await spawn(team, "w1", by=lead)

    assert result_of(await team.submit(lead, "wait", {"agents": ["w1"]}))["state"] == "parked"
    result_of(await team.submit(worker, "agent.finish", {"gist": "done"}))
