"""`propagate@1`: an episode's team reward split back along the record's own edges, on an ended session, by a named
producer at a version, and never a fact."""

import asyncio
from collections.abc import Sequence
from typing import Any

import pytest

from platoon_harness import Refused, Session, Team, credit
from platoon_harness.annotations import Annotation, Status
from platoon_harness.credit import PROPAGATE, propagate
from platoon_harness.kernel import ManualClock
from platoon_harness.testing import Call, Say

from .support import SECONDS, in_state, of_type, scripted, until

pytestmark = pytest.mark.timeout(60)

PROGRAM = "program:trainer"


def sends(to: str, cites: str) -> Call:
    return Call("message_send", {"to": to, "gist": f"to {to}, on {cites}", "based_on": [cites]})


async def ended(tmp_path, roles: dict[str, Sequence[Sequence[Any]]], messages: int, closing: Sequence[str]) -> Session:
    """A session of scripted agents that message each other once the program writes to `@alice`, closed, as a training
    system leaves one, once `messages` were sent and its episode closed on `closing`; and the same, attached."""
    edges = {name: ["all"] for name in roles}
    harnesses = {name: {"harness": scripted(*turns)} for name, turns in roles.items()}
    team = Team.model_validate({"roles": harnesses, "topology": {"edges": edges, "limits": {"max_hops": 16}}})
    async with Session.start(team, name="s", root=tmp_path, principal=PROGRAM) as session:
        for name in roles:
            await in_state(session, name, "idle")
        await session.open_episode("e")
        await session.send("@alice", "begin")
        await until(lambda: of_type(session, "message.sent"), session, lambda found: len(found) == messages)
        for name in roles:
            await in_state(session, name, "idle")
        await session.close_episode(based_on=closing)
        await session.close()
    return await Session.attach("s", root=tmp_path)


async def rewarded(session: Session, *statuses: tuple[Status, float | None]) -> None:
    """The team reward, as a training system writes it on the episode's close."""
    head = await session.head()
    for number, (status, value) in enumerate(statuses):
        await session.annotate(
            "episode/e@2",
            kind="reward",
            producer="environment",
            producer_version=str(number),
            scope="team",
            status=status,
            value=value,
            head_seq=head,
        )


async def credited(session: Session) -> dict[str, Annotation]:
    """Each row `propagate` wrote, by the agent whose first start it targets."""
    rows = [row for row in await session.annotations() if row.producer == PROPAGATE]
    return {(await session.lineage(row.target)).event.agent or "": row for row in rows}


def values(rows: dict[str, Annotation]) -> dict[str, float | None]:
    return {agent: row.value for agent, row in rows.items()}


CHAIN = {"alice": [[sends("@bob", "inbox/alice@1")]], "bob": [[sends("@alice", "inbox/bob@1")]]}
"""The program writes to alice, who writes to bob on it, who writes back on that: the episode closes on bob's."""


async def test_propagation_conserves_the_team_reward(tmp_path):
    """Bob keeps half of the reward, alice half of the rest, and what reaches the program's message stays nobody's:
    the rows and that unassigned share add up to the reward."""
    session = await ended(tmp_path, CHAIN, 3, ["inbox/alice@2"])
    await rewarded(session, ("scored", 1.0))

    await propagate(session, "e", judge=None, retained=0.5)

    rows = await credited(session)
    assert values(rows) == {"bob": 0.5, "alice": 0.25}
    unassigned = 1.0 - sum(row.value or 0.0 for row in rows.values())
    assert unassigned == 0.25 and (await session.lineage("inbox/alice@1")).made.maker == PROGRAM
    assert {row.status for row in rows.values()} == {"scored"}
    assert {(row.kind, row.scope, row.producer_version) for row in rows.values()} == {("credit", "local", "1")}


async def test_propagation_sums_reconverging_paths_once(tmp_path):
    """Alice's message is reached from the close and through bob's, and keeps its share of both, once."""
    session = await ended(tmp_path, CHAIN, 3, ["inbox/alice@2", "inbox/bob@1"])
    await rewarded(session, ("scored", 1.0))

    await propagate(session, "e", judge=None, retained=0.5)

    rows = await credited(session)
    assert values(rows) == {"bob": 0.25, "alice": 0.375}
    assert rows["alice"].evidence == ("inbox/bob@1",)


async def test_propagation_keeps_retained_credit_local(tmp_path):
    session = await ended(tmp_path, CHAIN, 3, ["inbox/alice@2"])
    await rewarded(session, ("scored", 2.0))

    await propagate(session, "e", judge=None, retained=0.25)

    assert values(await credited(session)) == {"bob": 0.5, "alice": 0.375}


async def test_propagation_ends_on_a_ring_of_citations(tmp_path):
    """Alice and bob answer each other twice, each on the last: a ring between agents, and a path back in time."""
    roles = {
        "alice": [[sends("@bob", "inbox/alice@1")], [sends("@bob", "inbox/alice@2")]],
        "bob": [[sends("@alice", "inbox/bob@1")], [sends("@alice", "inbox/bob@2")]],
    }
    session = await ended(tmp_path, roles, 5, ["inbox/alice@3"])
    await rewarded(session, ("scored", 1.0))

    await propagate(session, "e", judge=None, retained=0.5)

    rows = await credited(session)
    assert values(rows) == {"bob": 0.5 + 0.125, "alice": 0.25 + 0.0625}
    assert rows["bob"].evidence == ("inbox/alice@3", "inbox/alice@2")


async def test_propagation_never_moves_credit_along_an_unseen_citation_or_a_handed_only_edge(tmp_path):
    """Bob was handed alice's message and cites none of it, and cites the program's message to alice, which he was
    never handed: neither is an edge, so bob keeps everything and alice is never reached."""
    roles = {
        "alice": [[Call("message_send", {"to": "@bob", "gist": "handed"})]],
        "bob": [[sends("@alice", "inbox/alice@1")]],
    }
    session = await ended(tmp_path, roles, 3, ["inbox/alice@2"])
    await rewarded(session, ("scored", 1.0))

    await propagate(session, "e", judge=None, retained=0.5)

    cited = (await session.lineage("inbox/alice@2")).declared[0]
    assert cited.exposure is not None and cited.exposure.answer != "seen"
    assert values(await credited(session)) == {"bob": 1.0}


async def test_propagation_leaves_an_unreached_agent_unscored(tmp_path):
    roles = {**CHAIN, "carol": [[Call("message_send", {"to": "@alice", "gist": "unrelated"})]]}
    session = await ended(tmp_path, roles, 3, ["inbox/alice@2"])
    await rewarded(session, ("scored", 1.0))

    await propagate(session, "e", judge=None, retained=0.5)

    assert set(await credited(session)) == {"alice", "bob"}


@pytest.mark.parametrize("status", ["invalid", "error", "timeout", "cancelled"])
async def test_a_team_reward_that_is_not_scored_passes_its_status_to_each_row(tmp_path, status):
    session = await ended(tmp_path, CHAIN, 3, ["inbox/alice@2"])
    await rewarded(session, (status, None))

    await propagate(session, "e", judge=None, retained=0.5)

    rows = await credited(session)
    assert {agent: (row.status, row.value) for agent, row in rows.items()} == {
        "bob": (status, None),
        "alice": (status, None),
    }


async def test_a_walk_that_stops_short_writes_only_invalid_rows(tmp_path, monkeypatch):
    monkeypatch.setattr(credit, "WALK_LIMIT", 1)
    session = await ended(tmp_path, CHAIN, 3, ["inbox/alice@2"])
    await rewarded(session, ("scored", 1.0))

    await propagate(session, "e", judge=None, retained=0.5)

    assert {agent: (row.status, row.value) for agent, row in (await credited(session)).items()} == {
        "bob": ("invalid", None)
    }


async def test_propagation_refuses_several_team_rewards(tmp_path):
    session = await ended(tmp_path, CHAIN, 3, ["inbox/alice@2"])
    await rewarded(session, ("scored", 1.0), ("scored", 0.5))

    with pytest.raises(Refused, match="2 team rewards") as refused:
        await propagate(session, "e", judge=None, retained=0.5)

    assert refused.value.refusal.code == "conflict" and await credited(session) == {}


async def test_propagation_refuses_a_reward_on_an_episode_that_closed_on_no_ref(tmp_path):
    """Its reward would reach nobody's event, so every agent would be unscored for nothing it did: that is said."""
    session = await ended(tmp_path, CHAIN, 3, [])
    await rewarded(session, ("scored", 1.0))

    with pytest.raises(Refused, match="closed on no ref") as refused:
        await propagate(session, "e", judge=None, retained=0.5)

    assert refused.value.refusal.code == "invalid" and await credited(session) == {}


async def test_propagation_with_no_team_reward_writes_nothing_and_refuses_a_share_past_one(tmp_path):
    session = await ended(tmp_path, CHAIN, 3, ["inbox/alice@2"])

    await propagate(session, "e", judge=None, retained=0.5)
    with pytest.raises(Refused, match="from 0 to 1"):
        await propagate(session, "e", judge=None, retained=1.5)

    assert await session.annotations() == []


async def test_an_agents_credit_targets_its_first_start_never_its_spawn(tmp_path):
    session = await ended(tmp_path, CHAIN, 3, ["inbox/alice@2"])
    await rewarded(session, ("scored", 1.0))

    await propagate(session, "e", judge=None, retained=0.5)

    for agent, row in (await credited(session)).items():
        target = (await session.lineage(row.target)).event
        events = session.events(streams=[f"agent/{agent}"])
        started = [event.seq async for event in events if event.type == "agent.started"]
        assert (target.type, target.seq) == ("agent.started", started[0])
        assert row.target != f"agent/{agent}@1"


async def tree(tmp_path, name: str, on: str) -> tuple[dict[str, str], dict[str, float | None]]:
    """A root that does not stay and the child it waits on, each ended with its turn, and the episode closed on each
    one's `said` or on its last message: the refs it closed on, and the credit of each."""
    spawned = Call("agent_spawn", {"name": "kid", "child_role": "helper", "goal": "craft three"})
    crafter = [[spawned, Call("wait", {"agents": ["@kid"], "timeout": 1200})], [Say("all three are crafted")]]
    roles = {
        "crafter": {"harness": scripted(*crafter), "stays": False, "may_spawn": ["helper"]},
        "helper": {"harness": scripted([Say("the ingredient chain")]), "count": 0},
    }
    topology = {"edges": {"crafter": ["children"]}, "until": "role:crafter"}
    team = Team.model_validate({"roles": roles, "topology": topology})
    clock = ManualClock(1000.0)
    async with Session.start(team, name=name, root=tmp_path, clock=clock, principal=PROGRAM) as session:
        await session.open_episode("e")
        await session.send("@crafter", "craft three")
        await asyncio.wait_for(session.settled(), SECONDS)
        said = {row["agent"]: row["said"] for row in await session.agents()}
        messages = [event for event in await of_type(session, "item.recorded") if event.data["kind"] == "message"]
        closing = said if on == "said" else {event.agent: f"{event.stream}@{event.version}" for event in messages}
        await session.close_episode(based_on=list(closing.values()))
    attached = await Session.attach(name, root=tmp_path)
    await rewarded(attached, ("scored", 1.0))
    await propagate(attached, "e", judge=None, retained=0.5)
    return closing, values(await credited(attached))


async def test_a_tree_that_does_not_stay_credits_each_agent_alike_on_its_said_or_its_last_message(tmp_path):
    """Each `said` names its agent's end, which follows from nothing and cites nothing, as its harness's last message
    does not either, so each agent keeps all its ref was handed, the child as the root."""
    on_said, by_said = await tree(tmp_path, "said", "said")
    on_last, by_last = await tree(tmp_path, "last", "last")

    assert {ref.partition("/")[0] for ref in on_said.values()} == {"agent"}
    assert {ref.partition("/")[0] for ref in on_last.values()} == {"turn"}
    assert by_said == by_last == {"crafter": 0.5, "kid": 0.5}
