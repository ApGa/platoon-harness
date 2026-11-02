"""Injection: `pull < next-turn < wake < steer`, set on the reader's side, and the courier that acts on it."""

from platoon_harness.kernel import Principal

from ..kernel.support import supervised, until
from .support import (
    channel,
    end_turn,
    enroll,
    gists,
    grant,
    of_type,
    read,
    refusal,
    report,
    result_of,
    send,
    spawn,
    start_turn,
)


def ready(kernel) -> list[str]:
    return result_of(kernel.query(kernel.runtime, "delivery.ready", {}))["agents"]


async def offer(kernel, name: str, **fields):
    return result_of(await kernel.submit(kernel.runtime, "delivery.offer", {"agent": name, **fields}))


async def test_an_inbox_wakes_an_idle_agent_by_default(kernel):
    alice, _ = await spawn(kernel, "alice"), await spawn(kernel, "bob")

    await send(kernel, alice, "@bob", "wake up")

    assert ready(kernel) == ["bob"]


async def test_pull_never_offers_anything(kernel):
    alice, _ = await spawn(kernel, "alice"), await spawn(kernel, "bob")
    await channel(kernel, "log", delivery="pull")

    await send(kernel, alice, "#log", "read me if you like")

    assert ready(kernel) == []
    assert await offer(kernel, "bob") is None


async def test_next_turn_rides_on_a_turn_that_starts_for_another_reason(kernel):
    alice, _ = await spawn(kernel, "alice"), await spawn(kernel, "bob")
    await channel(kernel, "news")
    await send(kernel, alice, "#news", "for your next turn")
    assert ready(kernel) == []

    await send(kernel, alice, "@bob", "wake up")
    handed = await offer(kernel, "bob")

    assert [item["gist"] for item in handed["items"]] == ["for your next turn", "wake up"]


async def test_wake_starts_a_turn_only_if_the_agent_is_idle(kernel):
    alice, _ = await spawn(kernel, "alice"), await spawn(kernel, "bob")
    await start_turn(kernel, "bob")

    await send(kernel, alice, "@bob", "busy now")
    assert ready(kernel) == []

    await end_turn(kernel, "bob")
    assert ready(kernel) == ["bob"]


async def test_a_wake_requests_a_deliver_effect_with_the_input_as_its_key(kernel):
    alice, _ = await spawn(kernel, "alice"), await spawn(kernel, "bob")
    sent = await send(kernel, alice, "@bob", "wake up")

    handed = await offer(kernel, "bob")

    effect = result_of(kernel.query(kernel.runtime, "effect.ready", {"kind": "deliver"}))[-1]
    assert effect["agent"] == "bob" and effect["on_uncertain"] == "reconcile"
    assert effect["data"]["input"] == handed["input"]
    assert effect["data"]["items"] == [{"ref": sent["ref"], "gist": "wake up"}]
    assert effect["data"]["boundary"] == "turn"


async def test_one_turn_is_started_however_many_messages_arrive(kernel):
    alice, _ = await spawn(kernel, "alice"), await spawn(kernel, "bob")
    await send(kernel, alice, "@bob", "one")
    await offer(kernel, "bob")

    await send(kernel, alice, "@bob", "two")

    assert ready(kernel) == []


async def test_a_sender_cannot_buy_a_wake(kernel):
    alice = await spawn(kernel, "alice")

    outcome = await kernel.submit(alice, "channel.create", {"name": "loud", "kind": "topic", "delivery": "wake"})

    assert refusal(outcome).code == "not_permitted"
    assert "delivery" not in kernel.ops["message.send"].input.model_fields


async def test_steer_asks_for_the_earliest_boundary_the_harness_has(kernel):
    alice = await spawn(kernel, "alice")
    await spawn(kernel, "bob", ready={"boundaries": ["turn", "tool", "model_call"]})
    await channel(kernel, "urgent", delivery="steer")
    await start_turn(kernel, "bob")

    await send(kernel, alice, "#urgent", "stop that")

    assert ready(kernel) == ["bob"]
    assert (await offer(kernel, "bob"))["boundary"] == "tool"


async def test_steer_degrades_visibly_to_model_call(kernel):
    alice = await spawn(kernel, "alice")
    await spawn(kernel, "bob", ready={"boundaries": ["turn", "model_call"]})
    await channel(kernel, "urgent", delivery="steer")
    await start_turn(kernel, "bob")
    await send(kernel, alice, "#urgent", "stop that")

    await offer(kernel, "bob")

    assert of_type(kernel, "context.offered")[-1].data["boundary"] == "model_call"


async def test_steer_degrades_visibly_to_turn(kernel):
    alice = await spawn(kernel, "alice")
    await spawn(kernel, "bob", ready={"boundaries": ["turn"]})
    await channel(kernel, "urgent", delivery="steer")
    await start_turn(kernel, "bob")
    await send(kernel, alice, "#urgent", "stop that")
    assert ready(kernel) == []

    await end_turn(kernel, "bob")
    handed = await offer(kernel, "bob")

    assert handed["boundary"] == "turn"


async def test_a_tool_result_carries_pending_steer_notices(kernel):
    alice = await spawn(kernel, "alice")
    await spawn(kernel, "bob", ready={"boundaries": ["turn"]})
    await channel(kernel, "urgent", delivery="steer")
    await start_turn(kernel, "bob")
    await send(kernel, alice, "#urgent", "stop that")
    head = kernel.head

    handed = await offer(kernel, "bob", boundary="tool")

    assert [item["gist"] for item in handed["items"]] == ["stop that"]
    assert of_type(kernel, "context.offered", after=head)[0].data["how"] == "notice"
    assert result_of(kernel.query(kernel.runtime, "effect.ready", {"kind": "deliver"})) == []


async def test_coalesce_merges_wakes_into_one_turn(kernel, clock):
    alice = await spawn(kernel, "alice")
    await spawn(kernel, "bob")
    await channel(kernel, "burst", delivery="wake", coalesce=30.0)

    await send(kernel, alice, "#burst", "one")
    clock.advance(10)
    await send(kernel, alice, "#burst", "two")
    assert ready(kernel) == []
    assert result_of(kernel.query(kernel.runtime, "delivery.ready", {}))["due"] == 1030.0

    clock.advance(20)
    assert ready(kernel) == ["bob"]
    assert [item["gist"] for item in (await offer(kernel, "bob"))["items"]] == ["one", "two"]


async def test_a_digest_is_capped_with_a_gap_notice(kernel):
    alice = await spawn(kernel, "alice")
    await spawn(kernel, "bob")
    await channel(kernel, "firehose")
    for index in range(40):
        await send(kernel, alice, "#firehose", f"m{index}")
    await send(kernel, alice, "@bob", "wake up")

    handed = await offer(kernel, "bob")

    assert len(handed["items"]) == 32 and handed["behind"] == 9


async def test_an_offered_entry_is_not_offered_twice(kernel):
    alice, bob = await spawn(kernel, "alice"), await spawn(kernel, "bob")
    await send(kernel, alice, "@bob", "once")
    await offer(kernel, "bob")
    await start_turn(kernel, "bob")

    assert gists(await read(kernel, bob, "@bob")) == []


async def test_a_held_agent_gets_nothing(kernel, ada):
    alice = await spawn(kernel, "alice")
    await spawn(kernel, "bob", ready={"resume": True})
    result_of(await kernel.submit(ada, "agent.takeover", {"agent": "bob"}))

    await send(kernel, alice, "@bob", "queued")

    assert ready(kernel) == []
    assert await offer(kernel, "bob") is None


async def test_a_closing_session_starts_nothing(kernel, ada):
    alice = await spawn(kernel, "alice")
    await spawn(kernel, "bob")
    await send(kernel, alice, "@bob", "wake up")
    result_of(await kernel.submit(ada, "session.close", {}))

    assert ready(kernel) == []


async def test_the_courier_acts_on_a_wake_with_no_prompting(kernel):
    alice = await spawn(kernel, "alice")
    await spawn(kernel, "bob")
    head = kernel.head

    async with supervised(kernel):
        await send(kernel, alice, "@bob", "wake up")
        woken = await until(kernel, "agent.woken", after=head)

    assert woken.agent == "bob"


async def test_the_courier_stops_at_a_refused_wake_and_tries_again_when_the_budget_moves(kernel, clock):
    alice = await spawn(kernel, "alice")
    await spawn(kernel, "bob")
    set_budget = {"limits": {"turns": 2}}
    result_of(await kernel.submit(kernel.runtime, "budget.set", set_budget))
    head = kernel.head

    async with supervised(kernel):
        await send(kernel, alice, "@bob", "wake up")
        refused = await until(kernel, "wake.refused", after=head)
        assert refused.data["why"] == "over_budget"
        assert ready(kernel) == []
        settled = kernel.head
        result_of(await kernel.submit(kernel.runtime, "budget.set", {"limits": {"turns": 9}}))
        await until(kernel, "agent.woken", after=settled)


async def test_an_offer_to_nobody_is_refused(kernel):
    assert refusal(await kernel.submit(kernel.runtime, "delivery.offer", {"agent": "ghost"})).code == "not_found"


async def test_grants_filter_who_a_topic_reaches(kernel):
    alice = await spawn(kernel, "alice")
    await spawn(kernel, "bob")
    await spawn(kernel, "carol")
    await kernel.submit(kernel.runtime, "grant.remove", {"who": "agent", "ops": "*", "on": "*"})
    await grant(kernel, "agent", "message.send", "channel/*")
    await grant(kernel, "agent:bob", "message.read", "channel/*")
    await channel(kernel, "news")

    await send(kernel, alice, "#news", "for readers")

    assert of_type(kernel, "message.sent")[-1].data["audience"] == ["bob"]


async def test_a_program_gets_no_cursor_and_reads_by_after(kernel):
    program = Principal(id="program:map")
    await enroll(kernel, program)
    await grant(kernel, "program")
    alice = await spawn(kernel, "alice")
    sent = await send(kernel, alice, "@map", "for the program")

    page = result_of(await kernel.submit(program, "message.read", {"channel": "@map"}))
    again = result_of(await kernel.submit(program, "message.read", {"channel": "@map", "after": sent["seq"]}))

    assert gists(page) == ["for the program"] and gists(again) == []


async def test_compaction_advances_the_context_version(kernel):
    alice = await spawn(kernel, "alice")

    await report(kernel, "alice", "compacted", forgotten=["inbox/alice@1"])
    sent = await send(kernel, alice, "@alice", "to myself")

    event = next(event for event in of_type(kernel, "message.sent") if event.seq == sent["seq"])
    assert event.context_version == 1


async def failed_delivery(kernel) -> tuple[dict, dict]:
    """Wake bob, then have the driver fail to hand it over."""
    handed = await offer(kernel, "bob")
    effect = result_of(kernel.query(kernel.runtime, "effect.ready", {"kind": "deliver"}))[0]
    attempt = result_of(await kernel.submit(kernel.runtime, "effect.start", {"id": effect["id"]}))
    args = {"id": effect["id"], "attempt": attempt, "error": "the pipe broke"}
    result_of(await kernel.submit(kernel.runtime, "effect.fail", args))
    return handed, effect


async def test_delivery_is_at_least_once_a_failed_handover_is_offered_again(kernel):
    alice, _ = await spawn(kernel, "alice"), await spawn(kernel, "bob")
    sent = await send(kernel, alice, "@bob", "must arrive")
    first, _ = await failed_delivery(kernel)

    assert ready(kernel) == ["bob"]
    second = await offer(kernel, "bob")

    assert second["input"] != first["input"]
    assert [item["ref"] for item in second["items"]] == [sent["ref"]]


async def test_a_failed_handover_leaves_the_message_for_the_reader(kernel):
    alice, bob = await spawn(kernel, "alice"), await spawn(kernel, "bob")
    await send(kernel, alice, "@bob", "must arrive")
    await failed_delivery(kernel)

    assert gists(await read(kernel, bob, "@bob")) == ["must arrive"]


async def test_a_failed_handover_puts_the_agent_back_and_returns_the_reservation(kernel):
    await spawn(kernel, "bob")
    result_of(await kernel.submit(kernel.runtime, "budget.set", {"limits": {"turns": 9}}))
    await send(kernel, kernel.runtime, "@bob", "must arrive")
    await failed_delivery(kernel)

    assert result_of(kernel.query(kernel.runtime, "agent.status", {"agent": "bob"}))["state"] == "idle"
    assert result_of(kernel.query(kernel.runtime, "budget.status", {}))[0]["held"] == 0


async def test_a_failed_handover_does_not_step_back_past_a_newer_offer(kernel):
    alice, bob = await spawn(kernel, "alice"), await spawn(kernel, "bob")
    await send(kernel, alice, "@bob", "one")
    handed = await offer(kernel, "bob")
    await send(kernel, alice, "@bob", "two")
    newest = await read(kernel, bob, "@bob")
    assert gists(newest) == ["two"]
    effect = result_of(kernel.query(kernel.runtime, "effect.ready", {"kind": "deliver"}))[0]
    attempt = result_of(await kernel.submit(kernel.runtime, "effect.start", {"id": effect["id"]}))

    args = {"id": effect["id"], "attempt": attempt, "error": "the pipe broke"}
    result_of(await kernel.submit(kernel.runtime, "effect.fail", args))

    assert handed["input"] and gists(await read(kernel, bob, "@bob")) == []


async def test_a_refused_wake_is_tried_again_when_a_reservation_comes_back(kernel):
    await spawn(kernel, "alice")
    await spawn(kernel, "bob")
    result_of(
        await kernel.submit(kernel.runtime, "budget.set", {"limits": {"tokens": 100}, "estimate": {"tokens": 60}})
    )
    await send(kernel, kernel.runtime, "@alice", "go")
    await offer(kernel, "alice")
    await send(kernel, kernel.runtime, "@bob", "go")
    assert await offer(kernel, "bob") is None
    assert ready(kernel) == []

    await start_turn(kernel, "alice")
    await report(kernel, "alice", "usage", tokens=10, usd=0.0, label="provider")
    await end_turn(kernel, "alice")

    assert ready(kernel) == ["bob"]
