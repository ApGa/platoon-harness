"""Who reached whom: the `interactions` query of architecture section 11, which counts the edges between makers kind
by kind, from the record at a head."""

import shutil
from typing import Any

import pytest

from platoon_harness import Refused, Session
from platoon_harness.kernel import Kernel, ManualClock, Principal, registry
from platoon_harness.primitives import PRIMITIVES, Interactions, Pair, Unknown
from platoon_harness.testing import Say

from ..runtime import support as running
from .support import (
    channel,
    confirm,
    end_turn,
    enroll,
    grant,
    of_type,
    refusal,
    report,
    result_of,
    send,
    spawn,
    start_turn,
)

SURFACES = ("prompt", "tool_results", "shell_reads", "files", "native_children", "compaction", "external")
COUNTS = ("declared", "observed", "cause", "ancestry", "unconfirmed")


def interactions(kernel: Kernel, after: str | None = None) -> Interactions:
    return Interactions.model_validate(result_of(kernel.query(kernel.runtime, "interactions", {"after": after})))


def counts(pair: Pair) -> dict[str, int]:
    return {name: getattr(pair, name) for name in COUNTS}


def ref_of(event: Any) -> str:
    return f"{event.stream}@{event.version}"


async def handed(kernel: Kernel, agent: str, *, taken: bool) -> str:
    """Offer an agent what waits for it, and with `taken` begin a turn and say, as its harness would, that it took it:
    the offer's ref."""
    offer = result_of(await kernel.submit(kernel.runtime, "delivery.offer", {"agent": agent}))
    if taken:
        await start_turn(kernel, agent)
        await confirm(kernel, agent, offer["input"], evidence="message_start")
    return ref_of(of_type(kernel, "context.offered")[-1])


async def test_each_kind_of_edge_is_counted_apart_and_never_merged(kernel):
    """One reply that cites the message it answers is a citation and a cause, and two ranges of one body cited are one
    edge: an edge joins two events, and nothing adds one kind to another."""
    alice, bob = await spawn(kernel, "alice"), await spawn(kernel, "bob")
    await channel(kernel, "notes", kind="board", delivery="pull")
    body = f"sha256:{await kernel.put_body(b'line one\nline two\n')}"
    post = {"board": "notes", "name": "spec", "gist": "v1", "body": body}
    posted = result_of(await kernel.submit(alice, "board.post", post))["ref"]
    asked = (await send(kernel, alice, "@bob", "the plan"))["ref"]
    offer = await handed(kernel, "bob", taken=True)
    revise = {"board": "notes", "name": "spec", "gist": "v2", "expected_version": 1, "based_on": [asked]}
    revised = result_of(await kernel.submit(bob, "board.revise", revise))["ref"]
    cited = [asked, f"{posted}#L1-1", f"{posted}#L2-2"]
    replied = (await send(kernel, bob, "@alice", "agreed", reply_to=asked, based_on=cited))["ref"]

    found = interactions(kernel)

    (pair,) = found.pairs
    assert (pair.who, pair.whom) == ("agent:alice", "agent:bob")
    assert counts(pair) == {"declared": 3, "observed": 1, "cause": 1, "ancestry": 1, "unconfirmed": 0}
    assert pair.first == {"observed": offer, "declared": revised, "ancestry": revised, "cause": replied}
    assert set(Pair.model_fields) == {"who", "whom", *COUNTS, "first"}
    assert found.total == 1 and found.cursor is None


async def test_who_reached_whom_may_run_both_ways(kernel):
    """Alice reached Bob and Bob reached Alice: two pairs, each counted its own way, though every reference in the
    record points back."""
    alice, bob = await spawn(kernel, "alice"), await spawn(kernel, "bob")
    asked = (await send(kernel, alice, "@bob", "a question"))["ref"]
    answered = (await send(kernel, bob, "@alice", "an answer", reply_to=asked))["ref"]
    (await send(kernel, alice, "@alice", "noted", based_on=[answered]))["ref"]

    found = interactions(kernel)

    assert [(pair.who, pair.whom, counts(pair)) for pair in found.pairs] == [
        ("agent:alice", "agent:bob", {"declared": 0, "observed": 0, "cause": 1, "ancestry": 0, "unconfirmed": 0}),
        ("agent:bob", "agent:alice", {"declared": 1, "observed": 0, "cause": 0, "ancestry": 0, "unconfirmed": 0}),
    ]


async def test_an_agent_s_unknowns_read_as_unknown_never_as_no_interaction(kernel):
    """An offer its harness never said it took is unknown, and an agent no edge reaches, even one declaring every
    surface observed, is named with why what reached it is unknown: no result proves a surface, as exposure leaves it
    standing, and a gap content could come through stands in its record."""
    alice = await spawn(kernel, "alice")
    await spawn(kernel, "bob")
    await spawn(kernel, "carol", ready={"coverage": dict.fromkeys(SURFACES, "observed")})
    asked = (await send(kernel, alice, "@bob", "maybe read"))["ref"]
    offer = await handed(kernel, "bob", taken=False)
    await report(kernel, "carol", "gap", what="stream_lost")
    await report(kernel, "carol", "gap", what="usage_lower_bound")

    found = interactions(kernel)
    exposed = Unknown.model_validate(
        result_of(kernel.query(kernel.runtime, "exposure", {"agent": "carol", "ref": asked}))
    )

    (pair,) = found.pairs
    assert (pair.who, pair.whom, pair.observed, pair.unconfirmed) == ("agent:alice", "agent:bob", 0, 1)
    assert pair.first == {"unconfirmed": offer}
    assert [(row.agent, row.unproved, row.incidents, row.older_offers) for row in found.unknowns] == [
        ("alice", SURFACES, {}, 0),
        ("bob", SURFACES, {}, 0),
        ("carol", SURFACES, {"stream_lost": 1}, 0),
    ]
    assert found.unknowns[2].unproved == tuple(coverage.surface for coverage in exposed.standing)


async def test_interactions_answer_at_a_head_and_page_by_pair(kernel):
    """Seven agents each cite each other's message: 42 pairs, oldest first, a page at a time. A later page is read at
    the first one's head, so what the record learned since is in no page of that answer until it is asked anew."""
    agents = [await spawn(kernel, f"a{n}") for n in range(7)]
    said = [(await send(kernel, agent, f"@{agent.name}", "mine"))["ref"] for agent in agents]
    order = []
    for citer in agents:
        for maker, ref in zip(agents, said, strict=True):
            if maker != citer:
                await send(kernel, citer, f"@{citer.name}", "citing", based_on=[ref])
                order.append((maker.id, citer.id))

    first = interactions(kernel)
    await send(kernel, agents[1], "@a1", "again", based_on=[said[0]])
    late = await spawn(kernel, "late")
    await send(kernel, late, "@late", "late", based_on=[said[0]])
    second = interactions(kernel, after=first.cursor)
    fresh = interactions(kernel)

    assert (len(first.pairs), first.total, first.head) == (32, 42, second.head)
    assert second.cursor is None and [pair.declared for pair in (*first.pairs, *second.pairs)] == [1] * 42
    assert [(pair.who, pair.whom) for pair in (*first.pairs, *second.pairs)] == order
    assert [row.agent for row in first.unknowns] == [f"a{n}" for n in range(7)] and second.unknowns == ()
    again = next(pair for pair in fresh.pairs if (pair.who, pair.whom) == ("agent:a0", "agent:a1"))
    assert (fresh.total, again.declared, fresh.head) == (43, 2, kernel.head)
    assert [row.agent for row in fresh.unknowns][-1] == "late"
    for after in (f"{kernel.head + 1}:0", "a0@1", "32"):
        assert refusal(kernel.query(kernel.runtime, "interactions", {"after": after})).code == "invalid"


async def test_each_agent_s_unknowns_come_a_page_at_a_time_beside_the_pairs(kernel):
    """32 agents' unknowns a page, in the order they were spawned, so a page stays bounded however many agents a
    session spawns, and the cursor runs on until the agents are through too, though no pair is left."""
    agents = [await spawn(kernel, f"a{n:02}") for n in range(33)]
    await send(kernel, agents[0], "@a01", "the one edge")
    await handed(kernel, "a01", taken=True)

    first = interactions(kernel)
    second = interactions(kernel, after=first.cursor)

    assert (len(first.pairs), first.total, len(second.pairs), second.total) == (1, 1, 0, 1)
    assert [row.agent for row in (*first.unknowns, *second.unknowns)] == [agent.name for agent in agents]
    assert (len(first.unknowns), first.cursor, second.cursor) == (32, f"{first.head}:32", None)


async def test_an_answer_is_open_while_an_offer_it_counts_unconfirmed_can_still_be_taken(kernel):
    """An offer made before the turn it starts, as on a wake, can still be taken, so the answer is open though no turn
    had begun at its head. Once taken it is observed, and once its reader has ended an offer it never took is unknown
    for good, so the answer is no longer open."""
    alice = await spawn(kernel, "alice")
    await spawn(kernel, "bob")
    await send(kernel, alice, "@bob", "the plan")
    offer = result_of(await kernel.submit(kernel.runtime, "delivery.offer", {"agent": "bob"}))

    waking = interactions(kernel)
    await start_turn(kernel, "bob")
    await confirm(kernel, "bob", offer["input"], evidence="message_start")
    taken = interactions(kernel)
    await end_turn(kernel, "bob")
    await send(kernel, alice, "@bob", "and then")
    await handed(kernel, "bob", taken=False)
    pending = interactions(kernel)
    await report(kernel, "bob", "exited", reason="the harness crashed")
    ended = interactions(kernel)

    assert (waking.pairs[0].unconfirmed, waking.pairs[0].observed, waking.open) == (1, 0, True)
    assert interactions(kernel, after=f"{waking.head}:0") == waking
    assert (taken.pairs[0].unconfirmed, taken.pairs[0].observed, taken.open) == (0, 1, False)
    assert (pending.pairs[0].unconfirmed, pending.open) == (1, True)
    assert of_type(kernel, "agent.ended")[-1].agent == "bob"
    assert (ended.pairs[0].unconfirmed, ended.pairs[0].observed, ended.open) == (1, 1, False)


async def test_a_person_s_and_a_program_s_writes_count_as_theirs(kernel, ada):
    """A person's message and a program's task reach an agent as theirs, the claim handing the task over unconfirmed,
    as no harness said it took it, and an agent's work reaches a person who cites it. A person's or a program's reading
    is no evidence, so only agents have unknowns."""
    program = Principal(id="program:merger")
    await enroll(kernel, program)
    await grant(kernel, "program")
    bob = await spawn(kernel, "bob")
    await channel(kernel, "work", kind="queue", delivery="pull")
    asked = (await send(kernel, ada, "@bob", "please do the work"))["ref"]
    await handed(kernel, "bob", taken=True)
    result_of(await kernel.submit(program, "task.add", {"queue": "work", "gist": "merge it"}))
    result_of(await kernel.submit(bob, "task.claim", {"queue": "work"}))
    done = {"queue": "work", "gist": "merged", "based_on": [asked]}
    completed = result_of(await kernel.submit(bob, "task.complete", done))["ref"]
    await send(kernel, ada, "@bob", "thanks", based_on=[completed])

    found = interactions(kernel)

    assert [(pair.who, pair.whom, counts(pair)) for pair in found.pairs] == [
        ("human:ada", "agent:bob", {"declared": 1, "observed": 1, "cause": 0, "ancestry": 0, "unconfirmed": 0}),
        ("program:merger", "agent:bob", {"declared": 0, "observed": 0, "cause": 0, "ancestry": 1, "unconfirmed": 1}),
        ("agent:bob", "human:ada", {"declared": 1, "observed": 0, "cause": 0, "ancestry": 0, "unconfirmed": 0}),
    ]
    assert [row.agent for row in found.unknowns] == ["bob"]


async def test_a_view_credential_reads_interactions_and_writes_nothing(tmp_path):
    """A view link reads who reached whom as the owner does, at the same head, and the reading writes nothing. It is no
    agent's tool."""
    team = running.solo([Say("on it")])
    async with Session.start(team, name="s", root=tmp_path, clock=ManualClock(1000.0)) as session:
        await running.in_state(session, "bob", "idle")
        await session.send("@bob", "go")
        await running.until(lambda: running.of_type(session, "turn.ended"), session)
        await running.in_state(session, "bob", "idle")
        (go,) = [event for event in await running.of_type(session, "message.sent") if event.gist == "go"]
        owned = await session.interactions()
        async with Session.attach("s", root=tmp_path, view=True) as viewer:
            viewed = await viewer.interactions(after=f"{owned.head}:0")
            with pytest.raises(Refused) as refused:
                await viewer.send("@bob", "a view link cannot say this")
        after = await session.head()

    assert viewed == owned and after == owned.head
    assert any((pair.who, pair.whom, pair.observed) == (go.actor, "agent:bob", 1) for pair in owned.pairs)
    assert refused.value.refusal.code == "not_permitted"
    operation = registry(PRIMITIVES)["interactions"]
    assert operation.query and not operation.tool


async def test_interactions_answer_alike_after_a_rebuild_and_on_a_closed_copy(kernel, folder, tmp_path):
    alice, bob = await spawn(kernel, "alice"), await spawn(kernel, "bob")
    asked = (await send(kernel, alice, "@bob", "the plan"))["ref"]
    await handed(kernel, "bob", taken=True)
    await send(kernel, bob, "@alice", "agreed", reply_to=asked, based_on=[asked])

    live = interactions(kernel)
    await kernel.rebuild_all()
    rebuilt = interactions(kernel)
    kernel.close()
    shutil.copytree(folder, tmp_path / "copy")
    closed = Kernel.open(tmp_path / "copy", extensions=PRIMITIVES, read_only=True)
    copied = interactions(closed)
    closed.close()
    assert len(live.pairs) == 1 and live == rebuilt == copied
