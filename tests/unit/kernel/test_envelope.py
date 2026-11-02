"""The envelope: stamped by the kernel, bounded, and never passed by an op."""

import inspect

from platoon_harness.kernel import Principal, Txn

from .support import ALICE, enroll, events_of, grant, refusal_of, result_of


async def mark(kernel, type, stream, *, principal=None, agent=None, **data):
    args = {"type": type, "stream": stream, "agent": agent, "data": data}
    return result_of(await kernel.submit(principal or kernel.runtime, "note.mark", args))


def test_txn_is_exactly_me_now_view_emit_effect_refuse():
    assert {name for name in dir(Txn) if not name.startswith("_")} == {"me", "now", "view", "emit", "effect", "refuse"}


def test_ops_cannot_pass_stamped_fields():
    stamped = {"turn", "context_version", "episode", "topology_rev", "seq", "version", "actor", "wall_time"}
    assert not stamped & set(inspect.signature(Txn.emit).parameters)


async def test_every_event_carries_the_topology_revision(kernel):
    result_of(await kernel.submit(kernel.runtime, "note.add", {}))
    await grant(kernel, "all")
    await grant(kernel, "human")
    result_of(await kernel.submit(kernel.runtime, "note.add", {}))

    assert [(e.type, e.topology_rev) for e in events_of(kernel)] == [
        ("note.added", 0),
        ("grant.added", 1),
        ("grant.added", 2),
        ("note.added", 2),
    ]


async def test_an_agents_events_carry_its_context_version(kernel):
    await enroll(kernel, ALICE)
    await grant(kernel, "agent:alice")
    head = kernel.head
    result_of(await kernel.submit(ALICE, "note.add", {}))
    await mark(kernel, "context.offered", "context/alice", agent="alice")
    result_of(await kernel.submit(ALICE, "note.add", {}))
    result_of(await kernel.submit(kernel.runtime, "note.add", {}))

    assert [e.context_version for e in events_of(kernel, after=head)] == [0, 1, 1, None]


async def test_the_agent_defaults_to_the_acting_agent(kernel):
    await enroll(kernel, ALICE)
    await grant(kernel, "agent:alice")
    head = kernel.head
    result_of(await kernel.submit(ALICE, "note.add", {}))
    await mark(kernel, "agent.reported", "agent/bob", agent="bob")

    agents = [(e.actor, e.agent) for e in events_of(kernel, after=head)]

    assert agents == [("agent:alice", "alice"), ("runtime", "bob")]


async def test_a_turn_is_stamped_between_its_boundaries(kernel):
    await mark(kernel, "turn.started", "turn/alice", agent="alice", turn="t1")
    await mark(kernel, "agent.reported", "agent/alice", agent="alice")
    await mark(kernel, "agent.reported", "agent/bob", agent="bob")
    await mark(kernel, "turn.ended", "turn/alice", agent="alice")
    await mark(kernel, "agent.reported", "agent/alice", agent="alice")

    assert [e.turn for e in events_of(kernel)] == ["t1", "t1", None, "t1", None]


async def test_an_episode_is_stamped_between_its_boundaries(kernel):
    await mark(kernel, "note.happened", "note/a")
    await mark(kernel, "episode.opened", "episode/e1", episode="e1")
    await mark(kernel, "note.happened", "note/a")
    await mark(kernel, "episode.closed", "episode/e1")
    await mark(kernel, "note.happened", "note/a")

    assert [e.episode for e in events_of(kernel)] == [None, "e1", "e1", "e1", None]


async def test_wall_time_comes_from_the_injected_clock(kernel, clock):
    clock.advance(5)
    result_of(await kernel.submit(kernel.runtime, "note.add", {}))
    assert events_of(kernel)[0].wall_time == 1005.0


async def test_a_gist_is_capped_loudly(kernel):
    args = {"type": "note.happened", "stream": "note/a"}
    assert result_of(await kernel.submit(kernel.runtime, "note.add", {"text": "x" * 280}))
    assert refusal_of(await kernel.submit(kernel.runtime, "note.add", {"text": "x" * 280, "cause": [0]})) == "not_found"
    assert result_of(await kernel.submit(kernel.runtime, "note.mark", args))


async def test_data_is_capped_loudly(kernel):
    args = {"type": "note.happened", "stream": "note/a"}
    fits = {"blob": "x" * (16 * 1024 - 20)}
    assert result_of(await kernel.submit(kernel.runtime, "note.mark", args | {"data": fits}))
    too_much = {"blob": "x" * (16 * 1024)}
    assert refusal_of(await kernel.submit(kernel.runtime, "note.mark", args | {"data": too_much})) == "invalid"


async def test_event_names_must_be_past_tense(kernel):
    args = {"type": "note.happen", "stream": "note/a"}
    assert refusal_of(await kernel.submit(kernel.runtime, "note.mark", args)) == "invalid"


async def test_stream_names_exclude_the_ref_grammar(kernel):
    for stream in ("a@1", "a#b", "a b"):
        outcome = await kernel.submit(kernel.runtime, "note.add", {"stream": stream})
        assert refusal_of(outcome) == "invalid"


async def test_events_round_trip_through_the_journal(kernel):
    principal = Principal(id="runtime")
    result_of(await kernel.submit(principal, "note.add", {"text": "héllo"}))
    event = events_of(kernel)[0]
    assert (event.v, event.version, event.gist, event.data) == (1, 1, "héllo", {"text": "héllo"})
    assert event.outcome.seq == event.seq
