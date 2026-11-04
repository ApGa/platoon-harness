"""Inboxes and topics: architecture section 7, promise by promise."""

import hashlib

import pytest

from platoon_harness.kernel import Kernel, ManualClock, Principal
from platoon_harness.primitives import PRIMITIVES

from .support import (
    agent,
    channel,
    confirm,
    cursor,
    enroll,
    events_of,
    gists,
    grant,
    of_type,
    read,
    refusal,
    result_of,
    send,
    spawn,
)


async def test_inbox_is_one_stream_per_agent(kernel):
    alice, bob = await spawn(kernel, "alice"), await spawn(kernel, "bob")

    receipt = await send(kernel, alice, "@bob", "hello")

    assert receipt["ref"] == "inbox/bob@1"
    assert gists(await read(kernel, bob, "@bob")) == ["hello"]
    assert gists(await read(kernel, alice, "@alice")) == []


async def test_topic_is_one_stream_per_channel(kernel):
    alice, bob = await spawn(kernel, "alice"), await spawn(kernel, "bob")
    await channel(kernel, "news")

    receipt = await send(kernel, alice, "#news", "headline")

    assert receipt["ref"] == "channel/news@1"
    assert gists(await read(kernel, bob, "#news")) == ["headline"]


async def test_order_is_total_per_stream(kernel):
    alice, bob = await spawn(kernel, "alice"), await spawn(kernel, "bob")
    for index in range(5):
        await send(kernel, alice, "@bob", f"m{index}")

    assert gists(await read(kernel, bob, "@bob")) == [f"m{index}" for index in range(5)]


@pytest.mark.parametrize("address", ["bob", "@", "#a b", "+", "@a/b", "@@a"])
async def test_only_the_address_grammar_names_a_target(kernel, address):
    alice = await spawn(kernel, "alice")

    outcome = await kernel.submit(alice, "message.send", {"to": address, "gist": "x"})

    assert refusal(outcome).code == "invalid"


async def test_a_message_to_nobody_is_refused(kernel):
    alice = await spawn(kernel, "alice")

    assert refusal(await kernel.submit(alice, "message.send", {"to": "@ghost", "gist": "x"})).code == "not_found"


async def test_a_human_has_an_inbox(kernel, ada):
    alice = await spawn(kernel, "alice")

    await send(kernel, alice, "@ada", "are you there")

    assert gists(await read(kernel, ada, "@ada")) == ["are you there"]


async def test_grants_decide_who_may_send(kernel):
    bare = await spawn(kernel, "bare")
    await spawn(kernel, "bob")
    result_of(await kernel.submit(kernel.runtime, "grant.remove", {"who": "agent", "ops": "*", "on": "*"}))
    await grant(kernel, "agent:bare", "message.send", "inbox/{parent}")

    assert refusal(await kernel.submit(bare, "message.send", {"to": "@bob", "gist": "x"})).code == "not_permitted"


# Replies and threads.


async def test_reply_joins_the_thread_of_what_it_answers(kernel):
    alice, bob = await spawn(kernel, "alice"), await spawn(kernel, "bob")
    first = await send(kernel, alice, "@bob", "question")
    reply = await send(kernel, bob, "@alice", "answer", reply_to=first["ref"])
    await send(kernel, alice, "@bob", "thanks", reply_to=reply["ref"])
    await send(kernel, alice, "@bob", "unrelated")

    thread = await read(kernel, bob, "@bob", thread=first["ref"])

    assert gists(thread) == ["question", "thanks"]
    sent = of_type(kernel, "message.sent")
    assert sent[1].correlation == first["ref"] and sent[2].correlation == first["ref"]
    assert sent[1].cause == (first["seq"],)


async def test_a_reply_to_nothing_is_refused(kernel):
    alice = await spawn(kernel, "alice")
    await spawn(kernel, "bob")

    outcome = await kernel.submit(alice, "message.send", {"to": "@bob", "gist": "x", "reply_to": "inbox/bob@9"})

    assert refusal(outcome).code == "not_found"


# Entries.


async def test_an_entry_is_a_capped_gist_plus_an_optional_body(kernel):
    alice, bob = await spawn(kernel, "alice"), await spawn(kernel, "bob")
    body = await kernel.put_body(b"the whole story")

    await send(kernel, alice, "@bob", "short", body=f"sha256:{body}")
    too_long = await kernel.submit(alice, "message.send", {"to": "@bob", "gist": "x" * 281})

    assert refusal(too_long).code == "invalid"
    entry = (await read(kernel, bob, "@bob"))["entries"][0]
    assert entry["gist"] == "short" and entry["body"] is True and "text" not in entry


async def test_a_body_is_cited_only_if_it_exists(kernel):
    alice = await spawn(kernel, "alice")
    await spawn(kernel, "bob")

    outcome = await kernel.submit(alice, "message.send", {"to": "@bob", "gist": "x", "body": f"sha256:{'0' * 64}"})

    assert refusal(outcome).code == "not_found"


async def test_exposure_of_a_gist_is_recorded_apart_from_a_body(kernel):
    alice, bob = await spawn(kernel, "alice"), await spawn(kernel, "bob")
    body = await kernel.put_body(b"the whole story")
    await send(kernel, alice, "@bob", "short", body=f"sha256:{body}")

    await read(kernel, bob, "@bob")
    full = await read(kernel, bob, "@bob", after=0, bodies=True)

    assert full["entries"][0]["text"] == "the whole story"
    offers = of_type(kernel, "context.offered")
    assert [[item["form"] for item in offer.data["items"]] for offer in offers] == [["gist"], ["gist", "body"]]
    assert offers[1].data["items"][1]["digest"] == hashlib.sha256(b"the whole story").hexdigest()


# Delivery states.


async def test_a_new_entry_is_queued_then_offered_delivered_and_acked(kernel):
    alice, bob = await spawn(kernel, "alice"), await spawn(kernel, "bob")
    seq = (await send(kernel, alice, "@bob"))["seq"]
    assert cursor(kernel, "bob", "inbox/bob").state_of(seq) == "queued"

    offered = result_of(await kernel.submit(kernel.runtime, "delivery.offer", {"agent": "bob"}))
    assert cursor(kernel, "bob", "inbox/bob").state_of(seq) == "offered"

    await confirm(kernel, "bob", offered["input"])
    assert cursor(kernel, "bob", "inbox/bob").state_of(seq) == "delivered"

    await read(kernel, bob, "@bob")
    assert cursor(kernel, "bob", "inbox/bob").state_of(seq) == "acked"


async def test_delivered_is_only_what_a_driver_confirmed(kernel):
    alice, bob = await spawn(kernel, "alice"), await spawn(kernel, "bob")
    seq = (await send(kernel, alice, "@bob"))["seq"]

    await read(kernel, bob, "@bob")

    assert cursor(kernel, "bob", "inbox/bob").state_of(seq) == "offered"
    assert of_type(kernel, "context.delivered") == []


async def test_redelivery_is_deduped_by_event_id(kernel):
    alice, _ = await spawn(kernel, "alice"), await spawn(kernel, "bob")
    await send(kernel, alice, "@bob", "once")
    offered = result_of(await kernel.submit(kernel.runtime, "delivery.offer", {"agent": "bob"}))
    head = kernel.head

    for _ in range(2):
        await confirm(kernel, "bob", offered["input"])

    assert len(of_type(kernel, "context.delivered", after=head)) == 1


async def test_a_confirmation_of_nothing_is_refused(kernel):
    await spawn(kernel, "bob")
    delivered = {"type": "input.delivered", "input": "999", "boundary": "turn"}
    outcome = await kernel.submit(kernel.runtime, "agent.report", {"agent": "bob", "report": delivered})

    assert refusal(outcome).code == "not_found"


# Cursors.


async def test_cursors_are_per_reader_and_stream(kernel):
    alice, bob = await spawn(kernel, "alice"), await spawn(kernel, "bob")
    carol = await spawn(kernel, "carol")
    await channel(kernel, "news")
    await send(kernel, alice, "#news", "one")

    await read(kernel, bob, "#news")

    assert gists(await read(kernel, carol, "#news")) == ["one"]
    assert gists(await read(kernel, bob, "#news")) == []


async def test_an_omitted_after_means_the_server_held_cursor_never_the_head(kernel):
    alice, bob = await spawn(kernel, "alice"), await spawn(kernel, "bob")
    for gist in ("one", "two"):
        await send(kernel, alice, "@bob", gist)

    assert gists(await read(kernel, bob, "@bob", limit=1)) == ["one"]
    await send(kernel, alice, "@bob", "three")

    assert gists(await read(kernel, bob, "@bob")) == ["two", "three"]


async def test_after_acks_up_to_n(kernel):
    alice, bob = await spawn(kernel, "alice"), await spawn(kernel, "bob")
    seqs = [(await send(kernel, alice, "@bob", gist))["seq"] for gist in ("one", "two", "three")]
    await read(kernel, bob, "@bob")

    await read(kernel, bob, "@bob", after=seqs[1])

    assert cursor(kernel, "bob", "inbox/bob").acked == seqs[1]


async def test_after_is_clamped_so_a_hallucinated_number_acks_nothing_unshown(kernel):
    alice, bob = await spawn(kernel, "alice"), await spawn(kernel, "bob")
    seqs = [(await send(kernel, alice, "@bob", gist))["seq"] for gist in ("one", "two")]
    await read(kernel, bob, "@bob", limit=1)

    await read(kernel, bob, "@bob", after=kernel.head)

    place = cursor(kernel, "bob", "inbox/bob")
    assert place.acked == seqs[0] and place.state_of(seqs[1]) == "queued"
    assert gists(await read(kernel, bob, "@bob")) == ["two"]


async def test_an_after_past_every_event_is_no_cursor(kernel):
    alice, bob = await spawn(kernel, "alice"), await spawn(kernel, "bob")
    await send(kernel, alice, "@bob", "unread")

    outcome = await kernel.submit(bob, "message.read", {"channel": "@bob", "after": kernel.head + 1})

    assert refusal(outcome).code == "invalid"
    assert gists(await read(kernel, bob, "@bob")) == ["unread"]


@pytest.mark.parametrize(
    ("op", "args"),
    [
        ("message.read", {"after": 10**30}),
        ("wait", {"on": [{"stream": "inbox/bob"}], "after": 10**30}),
        ("message.send", {"to": "@bob", "gist": "x", "reply_to": "inbox/bob@" + "9" * 30}),
        ("message.send", {"to": "@bob", "gist": "x", "based_on": ["inbox/bob@" + "9" * 30]}),
        ("wait.progress", {"id": 10**30}),
    ],
)
async def test_an_enormous_number_is_no_failure_of_infrastructure(kernel, op, args):
    bob = await spawn(kernel, "bob")

    assert refusal(await kernel.submit(bob, op, args)).code in ("invalid", "not_found", "unsupported")


async def test_a_read_acks_nothing_still_in_flight(kernel):
    alice, bob = await spawn(kernel, "alice"), await spawn(kernel, "bob")
    sent = await send(kernel, alice, "@bob", "in flight")
    result_of(await kernel.submit(kernel.runtime, "delivery.offer", {"agent": "bob"}))

    assert gists(await read(kernel, bob, "@bob")) == []

    assert cursor(kernel, "bob", "inbox/bob").acked < sent["seq"]


async def test_a_confirmed_handover_can_be_acked(kernel):
    alice, bob = await spawn(kernel, "alice"), await spawn(kernel, "bob")
    sent = await send(kernel, alice, "@bob", "seen")
    handed = result_of(await kernel.submit(kernel.runtime, "delivery.offer", {"agent": "bob"}))
    await confirm(kernel, "bob", handed["input"])

    await read(kernel, bob, "@bob")

    assert cursor(kernel, "bob", "inbox/bob").acked == sent["seq"]


async def test_a_read_defaults_to_your_own_inbox(kernel):
    alice, bob = await spawn(kernel, "alice"), await spawn(kernel, "bob")
    await send(kernel, alice, "@bob", "hello")

    assert gists(result_of(await kernel.submit(bob, "message.read", {}))) == ["hello"]


async def test_a_sender_filter_takes_any_spelling_and_finds_a_childs_report(kernel):
    lead = await spawn(kernel, "lead", role="lead")
    bob = await spawn(kernel, "bob", by=lead)
    result_of(await kernel.submit(bob, "agent.finish", {"gist": "my report"}))

    for spelling in ("bob", "@bob", "agent:bob"):
        assert gists(await read(kernel, lead, "@lead", sender=spelling, after=0)) == ["my report"]


async def test_a_body_that_fits_no_result_is_left_for_a_surface_to_fetch_by_the_entry_s_ref(kernel):
    alice, bob = await spawn(kernel, "alice"), await spawn(kernel, "bob")
    body = await kernel.put_body(b"x\n" * 5000)
    await send(kernel, alice, "@bob", "see the body", body=f"sha256:{body}")

    page = await read(kernel, bob, "@bob", bodies=True)

    assert gists(page) == ["see the body"] and page["behind"] == 0
    entry = page["entries"][0]
    assert (entry["ref"], entry["body"], entry["text"]) == ("inbox/bob@1", True, None)


async def test_a_filtered_read_can_page_past_its_scan_window(kernel):
    alice, bob = await spawn(kernel, "alice"), await spawn(kernel, "bob")
    await channel(kernel, "t")
    for number in range(4100):
        result_of(await kernel.submit(kernel.runtime, "message.send", {"to": "#t", "gist": f"{number}"}))
    await send(kernel, alice, "#t", "needle")

    first = await read(kernel, bob, "#t", sender="@alice")
    second = await read(kernel, bob, "#t", sender="@alice", after=first["cursor"])

    assert gists(first) == [] and first["cursor"] > 0
    assert gists(second) == ["needle"]


async def test_a_confirmed_handover_drains_an_inbox_whose_agent_never_reads(kernel):
    alice = await spawn(kernel, "alice")
    await spawn(kernel, "bob", role="cramped")
    await send(kernel, alice, "@bob", "one")
    await send(kernel, alice, "@bob", "two")
    handed = result_of(await kernel.submit(kernel.runtime, "delivery.offer", {"agent": "bob"}))
    await confirm(kernel, "bob", handed["input"])

    assert (await send(kernel, alice, "@bob", "three"))["audience"] == 1


async def test_a_program_carries_a_chain_by_replying(kernel):
    program = Principal(id="program:relay")
    await enroll(kernel, program)
    await grant(kernel, "program")
    alice = await spawn(kernel, "alice")
    await spawn(kernel, "bob")
    heard = await send(kernel, alice, "@relay", "pass it on")

    relayed = await send(kernel, program, "@bob", "from alice", reply_to=heard["ref"])
    fresh = await send(kernel, program, "@bob", "a new piece of work")

    assert (relayed["hops"], fresh["hops"]) == (1, 0)


async def test_a_read_past_the_cursor_with_after_moves_nothing_it_skipped(kernel):
    alice, bob = await spawn(kernel, "alice"), await spawn(kernel, "bob")
    seqs = [(await send(kernel, alice, "@bob", gist))["seq"] for gist in ("one", "two", "three")]

    assert gists(await read(kernel, bob, "@bob", after=seqs[1])) == ["three"]

    assert cursor(kernel, "bob", "inbox/bob").offered == 0
    assert gists(await read(kernel, bob, "@bob")) == ["one", "two", "three"]


async def test_a_reread_is_allowed_and_rewinds_nothing(kernel):
    alice, bob = await spawn(kernel, "alice"), await spawn(kernel, "bob")
    await send(kernel, alice, "@bob", "one")
    await read(kernel, bob, "@bob")
    await read(kernel, bob, "@bob")
    held = cursor(kernel, "bob", "inbox/bob")

    assert gists(await read(kernel, bob, "@bob", after=0)) == ["one"]

    assert cursor(kernel, "bob", "inbox/bob") == held


async def test_a_filtered_read_never_moves_past_what_it_left_out(kernel):
    alice, bob = await spawn(kernel, "alice"), await spawn(kernel, "bob")
    carol = await spawn(kernel, "carol")
    await send(kernel, alice, "@bob", "a1")
    await send(kernel, carol, "@bob", "c1")
    await send(kernel, alice, "@bob", "a2")

    assert gists(await read(kernel, bob, "@bob", sender="@carol")) == ["c1"]

    assert cursor(kernel, "bob", "inbox/bob").offered == 0
    assert gists(await read(kernel, bob, "@bob")) == ["a1", "c1", "a2"]


async def test_a_filtered_read_moves_up_to_the_first_thing_it_left_out(kernel):
    alice, bob = await spawn(kernel, "alice"), await spawn(kernel, "bob")
    carol = await spawn(kernel, "carol")
    first = await send(kernel, alice, "@bob", "a1")
    await send(kernel, carol, "@bob", "c1")
    await send(kernel, alice, "@bob", "a2")

    assert gists(await read(kernel, bob, "@bob", sender="@alice")) == ["a1", "a2"]

    assert cursor(kernel, "bob", "inbox/bob").offered == first["seq"]


async def test_a_lagging_reader_gets_a_capped_digest_and_a_gap_notice(kernel):
    alice, bob = await spawn(kernel, "alice"), await spawn(kernel, "bob")
    await channel(kernel, "news")
    for index in range(40):
        await send(kernel, alice, "#news", f"m{index}")

    page = await read(kernel, bob, "#news")

    assert len(page["entries"]) == 32 and page["behind"] == 8
    assert gists(await read(kernel, bob, "#news")) == [f"m{index}" for index in range(32, 40)]


async def test_a_page_stays_inside_the_result_limit(kernel):
    alice, bob = await spawn(kernel, "alice"), await spawn(kernel, "bob")
    for _ in range(32):
        await send(kernel, alice, "@bob", "é" * 280)

    page = await read(kernel, bob, "@bob")

    assert 0 < len(page["entries"]) < 32 and page["behind"] == 32 - len(page["entries"])


async def test_a_human_read_is_a_query_that_writes_nothing(kernel, ada):
    alice, bob = await spawn(kernel, "alice"), await spawn(kernel, "bob")
    await send(kernel, alice, "@bob", "private to the team")
    head = kernel.head

    outcome = await kernel.submit(ada, "message.read", {"channel": "@bob"})

    assert gists(result_of(outcome)) == ["private to the team"]
    assert kernel.head == head and outcome.seq is None
    assert cursor(kernel, "bob", "inbox/bob").offered == 0
    assert gists(await read(kernel, bob, "@bob")) == ["private to the team"]


async def test_an_agent_read_is_a_command_that_records_exposure(kernel):
    alice, bob = await spawn(kernel, "alice"), await spawn(kernel, "bob")
    sent = await send(kernel, alice, "@bob", "seen")

    outcome = await kernel.submit(bob, "message.read", {"channel": "@bob"})

    assert outcome.seq is not None
    offer = of_type(kernel, "context.offered")[-1]
    assert offer.stream == "context/bob" and offer.data["items"][0]["ref"] == sent["ref"]
    assert offer.data["how"] == "read"


async def test_an_agent_query_of_message_read_is_refused(kernel):
    bob = await spawn(kernel, "bob")

    assert refusal(kernel.query(bob, "message.read", {"channel": "@bob"})).code == "unsupported"


async def test_context_version_advances_with_each_offer(kernel):
    alice, bob = await spawn(kernel, "alice"), await spawn(kernel, "bob")
    for gist in ("one", "two"):
        await send(kernel, alice, "@bob", gist)
        await read(kernel, bob, "@bob")
    reply = await send(kernel, bob, "@alice", "after two reads")

    event = next(event for event in events_of(kernel) if event.seq == reply["seq"])
    assert event.context_version == 2


# Broadcast.


async def test_a_broadcast_records_its_audience_and_generation(kernel):
    alice, bob = await spawn(kernel, "alice"), await spawn(kernel, "bob")
    result_of(await kernel.submit(kernel.runtime, "group.define", {"name": "crew", "roles": ["worker"]}))

    await send(kernel, alice, "+crew", "all hands")

    sent = of_type(kernel, "message.sent")[-1]
    assert sent.stream == "channel/+crew"
    assert sent.data["audience"] == ["bob"] and sent.data["generation"] == 1
    assert gists(await read(kernel, bob, "+crew")) == ["all hands"]


async def test_each_membership_change_moves_the_generation(kernel):
    alice = await spawn(kernel, "alice")
    result_of(await kernel.submit(kernel.runtime, "group.define", {"name": "crew", "roles": ["worker"]}))
    await spawn(kernel, "bob")
    await spawn(kernel, "carol")

    await send(kernel, alice, "+crew", "three of us")

    sent = of_type(kernel, "message.sent")[-1]
    assert sent.data["audience"] == ["bob", "carol"] and sent.data["generation"] == 3
    assert [event.data["members"] for event in of_type(kernel, "group.changed")] == [
        ["alice"],
        ["alice", "bob"],
        ["alice", "bob", "carol"],
    ]


async def test_a_member_named_by_the_rule_joins_when_it_starts(kernel):
    result_of(await kernel.submit(kernel.runtime, "group.define", {"name": "crew", "members": ["agent:bob"]}))
    await spawn(kernel, "alice")

    await spawn(kernel, "bob")

    assert of_type(kernel, "group.changed")[-1].data["members"] == ["bob"]


async def test_leaving_a_group_moves_its_generation(kernel):
    result_of(await kernel.submit(kernel.runtime, "group.define", {"name": "crew", "roles": ["worker"]}))
    alice, bob = await spawn(kernel, "alice"), await spawn(kernel, "bob")

    result_of(await kernel.submit(bob, "agent.finish", {}))
    await send(kernel, alice, "+crew", "just me")

    sent = of_type(kernel, "message.sent")[-1]
    assert sent.data["audience"] == [] and sent.data["generation"] == 4


async def test_membership_changes_only_on_success(kernel):
    result_of(await kernel.submit(kernel.runtime, "group.define", {"name": "crew", "roles": ["worker"]}))
    args = {"name": "doomed", "child_role": "worker", "goal": "fail"}
    result_of(await kernel.submit(kernel.runtime, "agent.spawn", args))
    head = kernel.head

    await kernel.submit(
        kernel.runtime, "agent.report", {"agent": "doomed", "report": {"type": "exited", "reason": "no such binary"}}
    )

    assert of_type(kernel, "group.changed", after=head) == []


async def test_a_late_joiner_does_not_see_a_broadcast_before_it(kernel):
    alice = await spawn(kernel, "alice")
    result_of(await kernel.submit(kernel.runtime, "group.define", {"name": "crew", "roles": ["worker"]}))
    await send(kernel, alice, "+crew", "before you came")
    late = await spawn(kernel, "late")

    assert gists(await read(kernel, late, "+crew")) == []


async def test_history_full_lets_a_late_joiner_see_history(kernel):
    alice = await spawn(kernel, "alice")
    await channel(kernel, "log", history="full")
    await send(kernel, alice, "#log", "before you came")
    late = await spawn(kernel, "late")

    assert gists(await read(kernel, late, "#log")) == ["before you came"]


# The inbox cap.


async def test_an_inbox_depth_cap_returns_a_full_receipt_never_a_silent_drop(kernel):
    alice = await spawn(kernel, "alice")
    await spawn(kernel, "bob", role="cramped")
    head = kernel.head
    for index in range(2):
        await send(kernel, alice, "@bob", f"m{index}")

    outcome = await kernel.submit(alice, "message.send", {"to": "@bob", "gist": "one too many"})

    assert refusal(outcome).code == "queue_full"
    assert refusal(outcome).detail == {"receipt": "full", "depth": 2, "cap": 2}
    assert of_type(kernel, "op.refused", after=head)[-1].data["code"] == "queue_full"


async def test_acking_makes_room_in_an_inbox(kernel):
    alice, bob = await spawn(kernel, "alice"), await spawn(kernel, "bob", role="cramped")
    for index in range(2):
        await send(kernel, alice, "@bob", f"m{index}")
    await read(kernel, bob, "@bob")
    await read(kernel, bob, "@bob")

    assert (await send(kernel, alice, "@bob", "room now"))["audience"] == 1


# Ended readers.


async def test_a_message_to_an_ended_agent_is_undeliverable(kernel):
    alice, bob = await spawn(kernel, "alice"), await spawn(kernel, "bob")
    result_of(await kernel.submit(bob, "agent.finish", {}))

    outcome = await kernel.submit(alice, "message.send", {"to": "@bob", "gist": "too late"})

    assert refusal(outcome).code == "undeliverable"


async def test_ending_an_agent_marks_its_queued_input_undeliverable(kernel):
    alice, bob = await spawn(kernel, "alice"), await spawn(kernel, "bob")
    seq = (await send(kernel, alice, "@bob"))["seq"]

    result_of(await kernel.submit(bob, "agent.finish", {}))

    assert cursor(kernel, "bob", "inbox/bob").state_of(seq) == "undeliverable"


# Hops.


async def test_every_message_carries_one_more_hop_than_its_cause(kernel, ada):
    alice, bob = await spawn(kernel, "alice"), await spawn(kernel, "bob")

    first = await send(kernel, ada, "@alice", "start")
    second = await send(kernel, alice, "@bob", "on", reply_to=first["ref"])
    third = await send(kernel, bob, "@alice", "and on", reply_to=second["ref"])

    assert [first["hops"], second["hops"], third["hops"]] == [0, 1, 2]


async def test_hops_follow_what_a_turn_was_offered_with_no_cause_passed(kernel, ada):
    alice, bob = await spawn(kernel, "alice"), await spawn(kernel, "bob")
    await send(kernel, ada, "@alice", "start")
    await read(kernel, alice, "@alice")

    second = await send(kernel, alice, "@bob", "a model passes no cause")
    await read(kernel, bob, "@bob")
    third = await send(kernel, bob, "@alice", "nor does this one")

    assert [second["hops"], third["hops"]] == [1, 2]


async def test_a_human_message_resets_hops(kernel, ada):
    alice = await spawn(kernel, "alice")
    bob = await spawn(kernel, "bob")
    deep = await send(kernel, alice, "@bob", "deep")
    deeper = await send(kernel, bob, "@alice", "deeper", reply_to=deep["ref"])

    reset = await send(kernel, ada, "@alice", "stop", reply_to=deeper["ref"])

    assert reset["hops"] == 0


@pytest.mark.parametrize("limits", [{"max_hops": 1}])
async def test_a_wake_past_max_hops_is_refused_and_shown_in_attention(kernel, ada, limits):
    alice, bob = await spawn(kernel, "alice"), await spawn(kernel, "bob")
    first = await send(kernel, ada, "@alice", "go")
    second = await send(kernel, alice, "@bob", "on", reply_to=first["ref"])

    third = await send(kernel, bob, "@alice", "too far", reply_to=second["ref"])

    assert third["hops"] == 2
    refused = of_type(kernel, "wake.refused")
    assert [event.agent for event in refused] == ["alice"] and refused[0].data["why"] == "hops"
    rows = result_of(kernel.query(ada, "attention.list", {}))
    assert [row["kind"] for row in rows if row["id"] == "wake/alice"] == ["hops"]


@pytest.mark.parametrize("limits", [{"max_hops": 1}])
async def test_a_message_past_max_hops_still_arrives_at_the_next_turn(kernel, limits):
    alice, bob = await spawn(kernel, "alice"), await spawn(kernel, "bob")
    first = await send(kernel, alice, "@bob", "a")
    second = await send(kernel, bob, "@alice", "b", reply_to=first["ref"])

    await send(kernel, alice, "@bob", "c", reply_to=second["ref"])

    assert gists(await read(kernel, bob, "@bob"))[-1] == "c"


# Channels.


async def test_channel_create_grants_readers_and_writers(kernel):
    alice, bob = await spawn(kernel, "alice"), await spawn(kernel, "bob", role="lead")
    await kernel.submit(kernel.runtime, "grant.remove", {"who": "agent", "ops": "*", "on": "*"})
    await channel(kernel, "news", readers=["role:lead"], writers=["role:worker"])

    await send(kernel, alice, "#news", "headline")

    assert gists(await read(kernel, bob, "#news")) == ["headline"]
    assert refusal(await kernel.submit(bob, "message.send", {"to": "#news", "gist": "x"})).code == "not_permitted"
    assert refusal(await kernel.submit(alice, "message.read", {"channel": "#news"})).code == "not_permitted"


async def test_channel_create_is_attenuated_to_the_creators_reach(kernel):
    alice = await spawn(kernel, "alice")
    await spawn(kernel, "bob")
    await kernel.submit(kernel.runtime, "grant.remove", {"who": "agent", "ops": "*", "on": "*"})
    await grant(kernel, "agent:alice", "channel.create", "channel/*")
    await grant(kernel, "agent:alice", "message.send", "inbox/{self}")

    within = await kernel.submit(alice, "channel.create", {"name": "mine", "kind": "topic", "readers": ["self"]})
    beyond = await kernel.submit(alice, "channel.create", {"name": "ours", "kind": "topic", "readers": ["role:worker"]})

    assert within.refusal is None
    assert refusal(beyond).code == "not_permitted"


async def test_a_selector_with_no_evaluator_is_refused(kernel):
    alice = await spawn(kernel, "alice")

    outcome = await kernel.submit(alice, "channel.create", {"name": "x", "kind": "topic", "readers": ["next"]})

    assert refusal(outcome).code == "unsupported"


async def test_a_channel_name_is_taken_once(kernel):
    await channel(kernel, "news")

    outcome = await kernel.submit(kernel.runtime, "channel.create", {"name": "news", "kind": "topic"})

    assert refusal(outcome).code == "conflict"


async def test_channel_list_shows_what_a_caller_may_use(kernel):
    alice, bob = await spawn(kernel, "alice"), await spawn(kernel, "bob", role="lead")
    await kernel.submit(kernel.runtime, "grant.remove", {"who": "agent", "ops": "*", "on": "*"})
    await grant(kernel, "agent", "channel.list")
    await channel(kernel, "news", readers=["role:lead"])
    await channel(kernel, "notes", kind="board", writers=["role:lead"])

    assert result_of(kernel.query(alice, "channel.list", {}))["channels"] == []
    assert result_of(kernel.query(bob, "channel.list", {}))["channels"] == [
        {"name": "#news", "kind": "topic"},
        {"name": "notes", "kind": "board"},
    ]


async def test_channels_go_a_page_at_a_time(kernel):
    bob = await spawn(kernel, "bob")
    names = [f"a-channel-with-a-long-name-of-its-own-{number:03}" for number in range(300)]
    for name in names:
        await channel(kernel, name, kind="board")

    first = result_of(kernel.query(bob, "channel.list", {}))
    second = result_of(kernel.query(bob, "channel.list", {"after": first["cursor"]}))

    assert first["total"] == second["total"] == 300 and second["cursor"] is None
    assert [row["name"] for row in (*first["channels"], *second["channels"])] == names


async def test_channel_list_gives_what_the_next_call_takes(kernel):
    bob = await spawn(kernel, "bob")
    await channel(kernel, "news")
    await channel(kernel, "tasks", kind="queue")
    result_of(await kernel.submit(kernel.runtime, "group.define", {"name": "crew", "roles": ["worker"]}))

    rows = result_of(kernel.query(bob, "channel.list", {}))["channels"]
    names = {row["kind"]: [] for row in rows}
    for row in rows:
        names[row["kind"]].append(row["name"])

    assert names == {"topic": ["#news", "+crew"], "queue": ["tasks"]}
    assert result_of(await kernel.submit(bob, "message.send", {"to": "#news", "gist": "hi"}))["audience"] == 0
    assert result_of(await kernel.submit(bob, "task.add", {"queue": "tasks", "gist": "go"}))["task"] == "1"


async def test_rebuild_after_reopening_keeps_cursors(folder, clock):
    kernel = Kernel.open(folder, clock=ManualClock(1.0), extensions=PRIMITIVES)
    result_of(await kernel.submit(kernel.runtime, "session.open", {"roles": {"worker": {}}}))
    await grant(kernel, "agent")
    alice, bob = await spawn(kernel, "alice"), await spawn(kernel, "bob")
    await send(kernel, alice, "@bob", "one")
    await read(kernel, bob, "@bob")
    await send(kernel, alice, "@bob", "two")
    kernel.close()

    kernel = Kernel.open(folder, clock=ManualClock(2.0), extensions=PRIMITIVES)
    assert gists(await read(kernel, bob, "@bob")) == ["two"]
    kernel.close()


async def test_a_principal_enrolled_without_a_spawn_cannot_be_written_to(kernel):
    alice = await spawn(kernel, "alice")
    await enroll(kernel, agent("stray"))

    assert refusal(await kernel.submit(alice, "message.send", {"to": "@stray", "gist": "x"})).code == "not_found"


async def test_a_redacted_body_leaves_the_rest_of_a_read_alone(kernel):
    alice, bob = await spawn(kernel, "alice"), await spawn(kernel, "bob")
    secret = await kernel.put_body(b"a secret")
    await send(kernel, alice, "@bob", "redacted later", body=f"sha256:{secret}")
    await send(kernel, alice, "@bob", "plain")
    result_of(await kernel.submit(kernel.runtime, "body.tombstone", {"sha256": secret}))

    page = await read(kernel, bob, "@bob", bodies=True)

    assert gists(page) == ["redacted later", "plain"] and page["entries"][0]["text"] is None
