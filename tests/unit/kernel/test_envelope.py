"""The envelope: stamped by the kernel, bounded, and never passed by an op."""

import inspect

import pytest

from platoon_harness.kernel import Args, Extension, Kernel, Principal, Stamps, Txn, op

from .support import ALICE, enroll, events_of, grant, refusal_of, result_of


async def mark(kernel, type, stream, *, principal=None, agent=None, **data):
    args = {"type": type, "stream": stream, "agent": agent, "data": data}
    return result_of(await kernel.submit(principal or kernel.runtime, "note.mark", args))


def test_txn_is_exactly_me_now_view_emit_effect():
    assert {name for name in dir(Txn) if not name.startswith("_")} == {"me", "now", "view", "emit", "effect"}


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


async def test_a_session_has_one_open_episode(kernel):
    await mark(kernel, "episode.opened", "episode/e1", episode="e1")

    args = {"type": "episode.opened", "stream": "episode/e2", "data": {"episode": "e2"}}
    assert refusal_of(await kernel.submit(kernel.runtime, "note.mark", args)) == "conflict"

    await mark(kernel, "episode.closed", "episode/e1")
    await mark(kernel, "episode.opened", "episode/e2", episode="e2")


@pytest.mark.parametrize(
    ("type", "agent", "data"),
    [
        ("turn.started", "alice", {}),
        ("turn.started", None, {"turn": "t1"}),
        ("turn.started", "alice", {"turn": 7}),
        ("episode.opened", None, {}),
    ],
)
async def test_a_boundary_event_must_name_what_it_opens(kernel, type, agent, data):
    args = {"type": type, "stream": "boundary", "agent": agent, "data": data}
    assert refusal_of(await kernel.submit(kernel.runtime, "note.mark", args)) == "invalid"


async def test_a_stream_reports_its_version(folder, clock):
    @op("seen.version")
    def version(txn: Txn, a: Args) -> int:
        """Say how far a stream has got, then add to it."""
        current = txn.view(Stamps).version_of("seen/a")
        txn.emit("seen.noted", "seen/a", gist="noted")
        return current

    kernel = Kernel.open(folder, clock=clock, extensions=[Extension("seen", ops=[version])])
    assert result_of(await kernel.submit(kernel.runtime, "seen.version", {})) == 0
    assert result_of(await kernel.submit(kernel.runtime, "seen.version", {})) == 1
    kernel.close()


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


async def test_data_that_is_not_text_is_refused(kernel):
    args = {"type": "note.happened", "stream": "note/a", "data": {"text": "\ud800"}}
    assert refusal_of(await kernel.submit(kernel.runtime, "note.mark", args)) == "invalid"


async def test_the_envelope_is_capped_too(kernel):
    first = result_of(await kernel.submit(kernel.runtime, "note.add", {}))
    args = {"cause": [first["seq"]] * 16 * 1024}
    assert refusal_of(await kernel.submit(kernel.runtime, "note.add", args)) == "invalid"


async def test_stream_names_are_capped(kernel):
    assert refusal_of(await kernel.submit(kernel.runtime, "note.add", {"stream": "x" * 513})) == "invalid"
    assert result_of(await kernel.submit(kernel.runtime, "note.add", {"stream": "x" * 512}))


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
