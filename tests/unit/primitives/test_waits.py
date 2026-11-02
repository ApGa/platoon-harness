"""Wait: architecture section 7, and the Watch race from the brief."""

import asyncio
from typing import Any

from hypothesis import given, settings
from hypothesis import strategies as st

from platoon_harness.kernel import Kernel, ManualClock
from platoon_harness.primitives import PRIMITIVES, hold_open, on
from platoon_harness.primitives.waits import wait_for as PRIMITIVE_WAIT

from ..kernel.support import supervised, until
from .support import (
    agent,
    channel,
    end_turn,
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


def condition(stream: str, **fields: Any) -> dict[str, Any]:
    return {"stream": stream, **fields}


async def wait(kernel: Kernel, by, *conditions: dict[str, Any], **fields: Any) -> dict[str, Any]:
    return result_of(await kernel.submit(by, "wait", {"on": list(conditions), **fields}))


def released(kernel: Kernel) -> list[int]:
    return result_of(kernel.query(kernel.runtime, "delivery.ready", {}))["waits"]


async def test_a_condition_already_true_releases_at_once(kernel):
    alice, bob = await spawn(kernel, "alice"), await spawn(kernel, "bob")
    await send(kernel, alice, "@bob", "already here")

    placed = await wait(kernel, bob, condition("inbox/bob"))

    assert placed["state"] == "released" and placed["have"] == 1


async def test_check_and_registration_are_one_transaction_from_after(kernel):
    alice, bob = await spawn(kernel, "alice"), await spawn(kernel, "bob")
    cursor = (await read(kernel, bob, "@bob"))["cursor"]
    await send(kernel, alice, "@bob", "between the read and the wait")

    placed = await wait(kernel, bob, condition("inbox/bob"), after=cursor)

    assert placed["state"] == "released"


async def test_an_omitted_after_counts_from_the_cursor_never_the_head(kernel):
    alice, bob = await spawn(kernel, "alice"), await spawn(kernel, "bob")
    await send(kernel, alice, "@bob", "read")
    await read(kernel, bob, "@bob")
    await send(kernel, alice, "@bob", "unread")

    assert (await wait(kernel, bob, condition("inbox/bob")))["state"] == "released"


async def test_an_omitted_after_ignores_what_was_already_offered(kernel):
    alice, bob = await spawn(kernel, "alice"), await spawn(kernel, "bob")
    await send(kernel, alice, "@bob", "read")
    await read(kernel, bob, "@bob")

    assert (await wait(kernel, bob, condition("inbox/bob")))["state"] == "parked"


async def test_a_join_waits_for_every_condition(kernel):
    lead = await spawn(kernel, "lead", role="lead")
    w1, w2 = await spawn(kernel, "w1"), await spawn(kernel, "w2")
    ended = ["agent.ended"]
    placed = await wait(kernel, lead, condition("agent/w1", types=ended), condition("agent/w2", types=ended))
    result_of(await kernel.submit(w1, "agent.finish", {}))
    assert released(kernel) == []

    shown = result_of(kernel.query(kernel.runtime, "wait.progress", {"id": placed["id"]}))
    assert (shown["have"], shown["need"], shown["missing"]) == (1, 2, ["agent/w2"])

    result_of(await kernel.submit(w2, "agent.finish", {}))
    assert result_of(kernel.query(kernel.runtime, "wait.progress", {"id": placed["id"]}))["holds"]


async def test_wait_any_needs_one_condition(kernel):
    lead = await spawn(kernel, "lead", role="lead")
    w1 = await spawn(kernel, "w1")
    await spawn(kernel, "w2")
    ended = ["agent.ended"]
    await wait(kernel, lead, condition("agent/w1", types=ended), condition("agent/w2", types=ended), mode="any")

    result_of(await kernel.submit(w1, "agent.finish", {}))

    assert len(released(kernel)) == 1


async def test_n_counts_events_and_types_filter_them(kernel):
    alice, bob = await spawn(kernel, "alice"), await spawn(kernel, "bob")
    placed = await wait(kernel, bob, condition("inbox/bob", types=["message.sent"], n=2))

    await send(kernel, alice, "@bob", "one")
    shown = result_of(kernel.query(kernel.runtime, "wait.progress", {"id": placed["id"]}))
    assert (shown["have"], shown["need"]) == (1, 2)

    await send(kernel, alice, "@bob", "two")
    assert released(kernel) == [placed["id"]]


async def test_distinct_counts_different_values_for_a_barrier(kernel):
    w1, w2 = await spawn(kernel, "w1"), await spawn(kernel, "w2")
    w3 = await spawn(kernel, "w3")
    await channel(kernel, "barrier", history="full")
    watcher = await spawn(kernel, "lead", role="lead")
    placed = await wait(
        kernel, watcher, condition("channel/barrier", n=["agent:w1", "agent:w2", "agent:w3"], distinct="actor")
    )

    await send(kernel, w1, "#barrier", "here")
    await send(kernel, w1, "#barrier", "here again")
    await send(kernel, w2, "#barrier", "here")

    shown = result_of(kernel.query(kernel.runtime, "wait.progress", {"id": placed["id"]}))
    assert (shown["have"], shown["need"], shown["missing"]) == (2, 3, ["agent:w3"])

    await send(kernel, w3, "#barrier", "here")
    assert released(kernel) == [placed["id"]]


async def test_a_version_watch_is_a_wait_on_a_board_object(kernel):
    bob, carol = await spawn(kernel, "bob"), await spawn(kernel, "carol")
    await channel(kernel, "notes", kind="board")
    post = {"board": "notes", "name": "spec", "gist": "v1"}
    posted = result_of(await kernel.submit(bob, "board.post", post))
    head = kernel.head
    placed = await wait(kernel, carol, condition("board/notes/spec", types=["board.revised"]), after=head)
    assert placed["state"] == "parked"

    result_of(await kernel.submit(bob, "board.revise", {**post, "gist": "v2", "expected_version": posted["version"]}))

    assert released(kernel) == [placed["id"]]


async def test_tool_arguments_are_friendly_for_agents(kernel):
    lead = await spawn(kernel, "lead", role="lead")
    w1 = await spawn(kernel, "w1")
    placed = result_of(await kernel.submit(lead, "wait", {"agents": ["w1"]}))

    result_of(await kernel.submit(w1, "agent.finish", {}))

    assert released(kernel) == [placed["id"]]


async def test_tool_arguments_are_friendly_for_senders(kernel):
    lead = await spawn(kernel, "lead", role="lead")
    w1, w2 = await spawn(kernel, "w1"), await spawn(kernel, "w2")
    placed = result_of(await kernel.submit(lead, "wait", {"from": ["w1", "w2"]}))
    await send(kernel, w1, "@lead", "one")

    shown = result_of(kernel.query(kernel.runtime, "wait.progress", {"id": placed["id"]}))
    assert (shown["have"], shown["missing"]) == (1, ["w2"])

    await send(kernel, w2, "@lead", "two")
    assert released(kernel) == [placed["id"]]


async def test_a_monitor_report_counts_as_a_message_from_the_child(kernel):
    lead = await spawn(kernel, "lead", role="lead")
    w1 = await spawn(kernel, "w1", by=lead)
    placed = result_of(await kernel.submit(lead, "wait", {"from": ["w1"]}))

    result_of(await kernel.submit(w1, "agent.finish", {"gist": "done"}))

    assert released(kernel) == [placed["id"]]


async def test_tool_arguments_are_friendly_for_tasks(kernel):
    lead, bob = await spawn(kernel, "lead", role="lead"), await spawn(kernel, "bob")
    await channel(kernel, "work", kind="queue")
    result_of(await kernel.submit(lead, "task.add", {"queue": "work", "gist": "x"}))
    placed = result_of(await kernel.submit(lead, "wait", {"tasks": ["work/1"]}))
    result_of(await kernel.submit(bob, "task.claim", {"queue": "work"}))
    assert released(kernel) == []

    result_of(await kernel.submit(bob, "task.complete", {"queue": "work"}))

    assert released(kernel) == [placed["id"]]


async def test_tool_arguments_are_friendly_for_a_board(kernel):
    lead, bob = await spawn(kernel, "lead", role="lead"), await spawn(kernel, "bob")
    await channel(kernel, "notes", kind="board")
    placed = result_of(await kernel.submit(lead, "wait", {"board": ["notes/spec"]}))

    result_of(await kernel.submit(bob, "board.post", {"board": "notes", "name": "spec", "gist": "v1"}))

    assert released(kernel) == [placed["id"]]


async def test_a_wait_has_no_one_object_to_version(kernel):
    bob = await spawn(kernel, "bob")

    outcome = await kernel.submit(bob, "wait", {"agents": ["bob"]}, expected_version=1)

    assert refusal(outcome).code == "unsupported"


async def test_a_wait_on_nothing_is_refused(kernel):
    bob = await spawn(kernel, "bob")

    assert refusal(await kernel.submit(bob, "wait", {})).code == "invalid"


def test_no_stream_name_is_needed_to_wait():
    fields = PRIMITIVE_WAIT.input.model_json_schema()["properties"]

    assert {"agents", "from", "tasks", "board"} <= fields.keys()


async def test_on_is_the_one_condition_in_python():
    assert on("agent/w1", types=("agent.ended",)).model_dump() == {
        "stream": "agent/w1",
        "types": ("agent.ended",),
        "n": 1,
        "distinct": None,
    }


async def test_every_stream_of_a_wait_is_authorized(kernel):
    bob = await spawn(kernel, "bob")
    await kernel.submit(kernel.runtime, "grant.remove", {"who": "agent", "ops": "*", "on": "*"})
    await grant(kernel, "agent:bob", "wait", "inbox/{self}")

    outcome = await kernel.submit(bob, "wait", {"on": [condition("inbox/bob"), condition("inbox/alice")]})

    assert refusal(outcome).code == "not_permitted"


# Parking.


async def test_a_wait_parks_by_default_and_says_to_end_the_turn(kernel):
    bob = await spawn(kernel, "bob")

    placed = await wait(kernel, bob, condition("inbox/bob"))

    assert placed["state"] == "parked" and "End your turn" in placed["next"]


async def test_an_agent_becomes_waiting_when_its_turn_ends_not_at_the_call(kernel):
    bob = await spawn(kernel, "bob")
    await start_turn(kernel, "bob")
    await wait(kernel, bob, condition("inbox/bob"))
    assert result_of(kernel.query(kernel.runtime, "agent.status", {"agent": "bob"}))["state"] == "running"

    await end_turn(kernel, "bob")

    assert result_of(kernel.query(kernel.runtime, "agent.status", {"agent": "bob"}))["state"] == "waiting"


async def test_a_wait_stays_open_if_the_model_keeps_working(kernel):
    alice, bob = await spawn(kernel, "alice"), await spawn(kernel, "bob")
    await start_turn(kernel, "bob")
    placed = await wait(kernel, bob, condition("inbox/bob"))

    await send(kernel, alice, "@bob", "while you work")

    assert released(kernel) == []
    assert result_of(kernel.query(kernel.runtime, "wait.progress", {"id": placed["id"]}))["holds"]
    await end_turn(kernel, "bob")
    assert released(kernel) == [placed["id"]]


async def test_a_release_starts_the_next_turn_with_its_delivery_attached(kernel):
    alice, bob = await spawn(kernel, "alice"), await spawn(kernel, "bob")
    await start_turn(kernel, "bob")
    placed = await wait(kernel, bob, condition("inbox/bob"))
    await end_turn(kernel, "bob")
    head = kernel.head

    async with supervised(kernel):
        await send(kernel, alice, "@bob", "the news")
        deliver = await until(kernel, "effect.requested", after=head)

    assert of_type(kernel, "wait.released", after=head)[0].data == {"id": placed["id"]}
    assert deliver.data["kind"] == "deliver"
    assert deliver.data["data"]["items"][0]["gist"] == "the news"


async def test_a_wake_never_depends_on_the_model_seeing_the_tool_result(kernel):
    bob = await spawn(kernel, "bob")
    await start_turn(kernel, "bob")
    placed = await wait(kernel, bob, condition("agent/w1", types=["agent.ended"]))
    await end_turn(kernel, "bob", "interrupted")
    await spawn(kernel, "w1")
    head = kernel.head

    async with supervised(kernel):
        result_of(await kernel.submit(agent("w1"), "agent.finish", {}))
        await until(kernel, "agent.woken", after=head)

    assert of_type(kernel, "wait.released", after=head)[0].data == {"id": placed["id"]}


async def test_a_parked_agent_whose_harness_cannot_resume_is_lost(kernel):
    bob = await spawn(kernel, "bob", ready={"resume": False})
    await start_turn(kernel, "bob")
    placed = await wait(kernel, bob, condition("inbox/bob"))
    await end_turn(kernel, "bob")

    await report(kernel, "bob", "exited", reason="cannot resume")

    assert result_of(kernel.query(kernel.runtime, "agent.status", {"agent": "bob"}))["status"] == "lost"
    assert result_of(kernel.query(kernel.runtime, "wait.progress", {"id": placed["id"]})) is None


# Timeouts and cut-off waits.


async def test_a_timeout_ends_a_wait_and_tells_the_agent(kernel, clock):
    bob = await spawn(kernel, "bob")
    await start_turn(kernel, "bob")
    placed = await wait(kernel, bob, condition("inbox/bob"), timeout=30.0)
    await end_turn(kernel, "bob")
    assert result_of(kernel.query(kernel.runtime, "delivery.ready", {}))["due"] == 1030.0

    clock.advance(30)
    assert released(kernel) == [placed["id"]]
    head = kernel.head

    async with supervised(kernel):
        await until(kernel, "agent.woken", after=head)

    assert of_type(kernel, "wait.expired", after=head)[0].data == {"id": placed["id"]}
    assert "timed out" in of_type(kernel, "message.sent", after=head)[0].gist


async def test_the_courier_sleeps_until_the_next_deadline(kernel, clock):
    bob = await spawn(kernel, "bob")
    await start_turn(kernel, "bob")
    await wait(kernel, bob, condition("inbox/bob"), timeout=30.0)
    await end_turn(kernel, "bob")
    head = kernel.head

    async with supervised(kernel):
        await clock.slept_until(1030.0)
        clock.advance(30)
        await until(kernel, "wait.expired", after=head)


async def test_a_cut_off_wait_confirms_nothing(kernel, clock):
    alice, bob = await spawn(kernel, "alice"), await spawn(kernel, "bob")
    sent = await send(kernel, alice, "@bob", "offered, never acked")
    await read(kernel, bob, "@bob")
    await start_turn(kernel, "bob")
    placed = await wait(kernel, bob, condition("inbox/bob"), after=sent["seq"], timeout=5.0)
    head = kernel.head
    await end_turn(kernel, "bob")

    clock.advance(5)
    result_of(await kernel.submit(kernel.runtime, "wait.release", {"id": placed["id"]}))

    assert of_type(kernel, "message.acked", after=head) == []
    assert of_type(kernel, "context.delivered") == []


async def test_a_satisfied_wait_acks_up_to_after(kernel):
    alice, bob = await spawn(kernel, "alice"), await spawn(kernel, "bob")
    sent = await send(kernel, alice, "@bob", "seen")
    await read(kernel, bob, "@bob")
    await send(kernel, alice, "@bob", "new")

    await wait(kernel, bob, condition("inbox/bob"), after=sent["seq"])

    assert [event.data["upto"] for event in of_type(kernel, "message.acked")] == [sent["seq"]]


async def test_wait_after_is_clamped_like_read_after(kernel):
    alice, bob = await spawn(kernel, "alice"), await spawn(kernel, "bob")
    await send(kernel, alice, "@bob", "unshown")
    await send(kernel, alice, "@bob", "unshown too")

    await wait(kernel, bob, condition("inbox/bob", n=1), after=0)
    await wait(kernel, bob, condition("agent/bob", types=["agent.started"]), after=0)

    assert of_type(kernel, "message.acked") == []


async def test_wait_cancel_closes_only_your_own_wait(kernel):
    alice, bob = await spawn(kernel, "alice"), await spawn(kernel, "bob")
    placed = await wait(kernel, bob, condition("inbox/bob"))

    assert refusal(await kernel.submit(alice, "wait.cancel", {"id": placed["id"]})).code == "not_found"
    result_of(await kernel.submit(bob, "wait.cancel", {"id": placed["id"]}))

    assert result_of(kernel.query(kernel.runtime, "wait.progress", {"id": placed["id"]})) is None


async def test_an_agent_holds_one_open_wait(kernel):
    bob = await spawn(kernel, "bob")
    first = await wait(kernel, bob, condition("inbox/bob"))

    second = await wait(kernel, bob, condition("inbox/bob", n=2))

    assert result_of(kernel.query(kernel.runtime, "wait.progress", {"id": first["id"]})) is None
    assert result_of(kernel.query(kernel.runtime, "wait.progress", {"id": second["id"]})) is not None


async def test_ending_an_agent_cancels_its_waits(kernel):
    bob = await spawn(kernel, "bob")
    placed = await wait(kernel, bob, condition("inbox/bob"))

    result_of(await kernel.submit(bob, "agent.finish", {}))

    assert result_of(kernel.query(kernel.runtime, "wait.progress", {"id": placed["id"]})) is None


async def test_wait_release_is_a_runtime_op(kernel):
    bob = await spawn(kernel, "bob")
    placed = await wait(kernel, bob, condition("inbox/bob"))

    assert refusal(await kernel.submit(bob, "wait.release", {"id": placed["id"]})).code == "not_permitted"


# Hold.


async def test_hold_keeps_a_call_open_and_returns_when_the_wait_holds(kernel, clock):
    alice, bob = await spawn(kernel, "alice"), await spawn(kernel, "bob", ready={"tool_timeout_s": 300.0})
    await start_turn(kernel, "bob")
    placed = await wait(kernel, bob, condition("inbox/bob"), hold=20.0)
    assert placed["state"] == "pending"
    head = kernel.head

    held = asyncio.create_task(hold_open(kernel, kernel.runtime, placed))
    await clock.sleeping()
    await send(kernel, alice, "@bob", "in time")

    assert (await held)["state"] == "released"
    assert of_type(kernel, "agent.woken", after=head) == []


async def test_hold_returns_pending_with_a_cursor_on_expiry(kernel, clock):
    bob = await spawn(kernel, "bob", ready={"tool_timeout_s": 300.0})
    await start_turn(kernel, "bob")
    placed = await wait(kernel, bob, condition("inbox/bob"), hold=20.0)

    held = asyncio.create_task(hold_open(kernel, kernel.runtime, placed))
    await clock.sleeping()
    clock.advance(20)
    result = await held

    assert result["state"] == "pending" and result["cursor"] == placed["cursor"]
    assert result_of(kernel.query(kernel.runtime, "wait.progress", {"id": placed["id"]})) is not None


async def test_hold_stays_below_the_harness_tool_timeout(kernel):
    bob = await spawn(kernel, "bob", ready={"tool_timeout_s": 300.0})

    outcome = await kernel.submit(bob, "wait", {"on": [condition("inbox/bob")], "hold": 300.0})

    assert refusal(outcome).code == "unsupported"


async def test_a_one_shot_driver_cannot_wait_beyond_hold(kernel):
    bob = await spawn(kernel, "bob", ready={"persistent": False, "tool_timeout_s": 60.0})
    on_inbox = [condition("inbox/bob")]

    parked = await kernel.submit(bob, "wait", {"on": on_inbox})
    beyond = await kernel.submit(bob, "wait", {"on": on_inbox, "timeout": 30.0, "hold": 20.0})
    within = await kernel.submit(bob, "wait", {"on": on_inbox, "timeout": 20.0, "hold": 20.0})

    assert refusal(parked).code == "unsupported" and "one-shot" in refusal(parked).detail
    assert refusal(beyond).code == "unsupported"
    assert within.refusal is None


# Reachable views stay in step, even with an extension's events.


async def test_a_wait_counts_an_extensions_events_it_cannot_name(kernel):
    alice = await spawn(kernel, "alice")
    placed = await wait(kernel, alice, condition("agent/bob"))

    await spawn(kernel, "bob")

    assert result_of(kernel.query(kernel.runtime, "wait.progress", {"id": placed["id"]}))["holds"]


# The Watch race: nothing is lost across read, subscribe and reconnect boundaries.


async def test_watch_race_a_message_between_read_and_wait_is_not_lost(kernel):
    alice, bob = await spawn(kernel, "alice"), await spawn(kernel, "bob")
    await send(kernel, alice, "@bob", "one")
    assert gists(await read(kernel, bob, "@bob")) == ["one"]

    await send(kernel, alice, "@bob", "two")
    placed = await wait(kernel, bob, condition("inbox/bob"))

    assert placed["state"] == "released"
    assert gists(await read(kernel, bob, "@bob")) == ["two"]


async def test_watch_race_a_message_across_a_reconnect_is_not_lost(folder):
    kernel = Kernel.open(folder, clock=ManualClock(1.0), extensions=PRIMITIVES)
    result_of(await kernel.submit(kernel.runtime, "session.open", {"roles": {"worker": {}}}))
    await grant(kernel, "agent")
    alice, bob = await spawn(kernel, "alice"), await spawn(kernel, "bob")
    await send(kernel, alice, "@bob", "one")
    await read(kernel, bob, "@bob")
    placed = await wait(kernel, bob, condition("inbox/bob"))
    await send(kernel, alice, "@bob", "two")
    kernel.close()

    kernel = Kernel.open(folder, clock=ManualClock(2.0), extensions=PRIMITIVES)
    assert result_of(kernel.query(kernel.runtime, "wait.progress", {"id": placed["id"]}))["holds"]
    assert gists(await read(kernel, bob, "@bob")) == ["two"]
    kernel.close()


async def test_watch_race_a_client_watching_a_view_misses_no_change(kernel, ada):
    alice = await spawn(kernel, "alice")
    first = result_of(kernel.query(ada, "view.watch", {"name": "attention"}))
    await send(kernel, alice, "@ada", "one")
    second = result_of(kernel.query(ada, "view.watch", {"name": "attention", "after": first["cursor"]}))
    await send(kernel, alice, "@ada", "two")
    third = result_of(kernel.query(ada, "view.watch", {"name": "attention", "after": second["cursor"]}))

    assert [row["gist"] for row in second["rows"]] == ["one"]
    assert [row["gist"] for row in third["rows"]] == ["two"]


async def test_watch_race_a_follower_resumes_from_its_cursor(kernel):
    alice = await spawn(kernel, "alice")
    await send(kernel, alice, "@alice", "one")
    page = kernel.read(kernel.runtime, after=0, match="inbox/*")
    await send(kernel, alice, "@alice", "two")

    next_page = kernel.read(kernel.runtime, after=page.cursor, match="inbox/*")

    assert [event.gist for event in next_page.events] == ["two"]


actions = st.lists(st.sampled_from(["send", "read", "wait", "reconnect"]), min_size=1, max_size=24)


@settings(max_examples=25, deadline=None)
@given(script=actions)
def test_watch_race_nothing_sent_is_lost_under_any_interleaving(tmp_path_factory, script) -> None:
    """However sends, reads, waits and reconnects interleave, a reader sees every message in order."""
    folder = tmp_path_factory.mktemp("watch") / "session"

    async def body() -> None:
        kernel = Kernel.open(folder, clock=ManualClock(1.0), extensions=PRIMITIVES)
        result_of(await kernel.submit(kernel.runtime, "session.open", {"roles": {"worker": {}}}))
        await grant(kernel, "agent")
        alice, bob = await spawn(kernel, "alice"), await spawn(kernel, "bob")
        sent: list[str] = []
        seen: list[str] = []
        for step in script:
            if step == "send":
                sent.append(f"m{len(sent)}")
                await send(kernel, alice, "@bob", sent[-1])
            elif step == "read":
                seen += gists(await read(kernel, bob, "@bob", limit=3))
            elif step == "wait":
                await kernel.submit(bob, "wait", {"on": [condition("inbox/bob")]})
            else:
                kernel.close()
                kernel = Kernel.open(folder, clock=ManualClock(1.0), extensions=PRIMITIVES)
        while page := gists(await read(kernel, bob, "@bob")):
            seen += page
        kernel.close()
        assert seen == sent

    asyncio.run(body())
