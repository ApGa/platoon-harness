"""One way to confirm an offer, from its harness's own report, and the launch offer: architecture section 11."""

from platoon_harness.kernel import Kernel

from .support import (
    confirm,
    end_turn,
    of_type,
    read,
    report,
    result_of,
    send,
    settle_effects,
    spawn,
    start,
    start_turn,
)

ANCHOR = {"claudecode/toolUseId": "toolu_1"}


async def instruct(kernel: Kernel, name: str, **args) -> int | None:
    body = f"sha256:{await kernel.put_body(b'You are a worker.')}"
    return result_of(await kernel.submit(kernel.runtime, "agent.instruct", {"agent": name, "body": body, **args}))


async def spawned(kernel: Kernel, name: str, goal: str = "") -> None:
    """An agent spawned by the runtime with `goal`, its effects done, not yet launched."""
    args = {"name": name, "child_role": "worker", "goal": goal}
    result_of(await kernel.submit(kernel.runtime, "agent.spawn", args))
    await settle_effects(kernel, name)


def delivered(kernel: Kernel) -> dict[int, dict]:
    return {event.data["input"]: event.data for event in of_type(kernel, "context.delivered")}


async def returned(kernel: Kernel, name: str, anchor: str, outcome: str = "completed") -> None:
    """A tool item ended, as a driver reports one: `completed` with what its call returned, or `failed`."""
    await report(kernel, name, "item", kind="tool", phase="completed", gist="a tool", native_id=anchor, outcome=outcome)


async def test_a_launch_offer_is_confirmed_by_the_first_input_its_harness_reports_delivered(kernel):
    await spawned(kernel, "bob", goal="fix the test")
    await spawned(kernel, "idle")

    launched = await instruct(kernel, "bob", goal=True)
    started = await instruct(kernel, "idle")
    await start(kernel, "bob")
    await start(kernel, "idle")
    offer = of_type(kernel, "context.offered")[-2]
    await confirm(kernel, "bob", launched, evidence="command_lifecycle", native_id="u-1")
    await send(kernel, kernel.runtime, "@idle", "wake up")
    handed = result_of(await kernel.submit(kernel.runtime, "delivery.offer", {"agent": "idle"}))
    await confirm(kernel, "idle", handed["input"], evidence="message_start")

    assert (offer.seq, offer.data["how"], offer.data["boundary"]) == (launched, "launch", "turn")
    assert [(item["ref"], item["form"]) for item in offer.data["items"]] == [
        ("agent/bob@1", "gist"),
        ("agent/bob@2", "body"),
    ]
    confirmations = delivered(kernel)
    assert (confirmations[launched]["evidence"], confirmations[launched]["native_id"]) == ("command_lifecycle", "u-1")
    assert (confirmations[started]["evidence"], confirmations[started]["native_id"]) == ("message_start", None)
    assert confirmations[handed["input"]]["how"] == "wake"


async def test_a_launch_that_goes_unconfirmed_stays_so(kernel):
    """`exec` puts the goal in argv, which says nothing of whether it landed, so nothing confirms its launch, and what
    it was handed stays unknown, with the launch named."""
    await spawned(kernel, "once", goal="say hi")

    launched = await instruct(kernel, "once", goal=True)
    await start(kernel, "once", persistent=False)
    await start_turn(kernel, "once")
    await end_turn(kernel, "once")
    answer = result_of(kernel.query(kernel.runtime, "exposure", {"agent": "once", "ref": "agent/once@1"}))

    assert launched is not None and delivered(kernel) == {}
    assert answer["answer"] == "unknown"
    assert [(offer["seq"], offer["how"], offer["confirmed"]) for offer in answer["handed"]] == [
        (launched, "launch", None)
    ]


async def test_a_relaunch_s_first_input_confirms_only_its_own_launch(kernel):
    """A harness that died before it took its launch is gone, and the fresh one's input says nothing of what it took."""
    await spawned(kernel, "bob", goal="the secret is heliotrope")
    dead = await instruct(kernel, "bob", goal=True)
    relaunched = await instruct(kernel, "bob")
    await start(kernel, "bob")
    await send(kernel, kernel.runtime, "@bob", "wake up")
    handed = result_of(await kernel.submit(kernel.runtime, "delivery.offer", {"agent": "bob"}))

    await confirm(kernel, "bob", handed["input"], evidence="command_lifecycle", native_id="u-9")

    assert sorted(delivered(kernel)) == [relaunched, handed["input"]] and dead not in delivered(kernel)


async def test_an_input_after_a_native_resume_confirms_no_launch_before_it(kernel):
    """A resumed harness keeps its session, but whether that session ever took its launch is not what it now says."""
    await spawned(kernel, "bob", goal="fix the test")
    launched = await instruct(kernel, "bob", goal=True)
    await start(kernel, "bob")
    await instruct(kernel, "bob", resumed=True)
    await send(kernel, kernel.runtime, "@bob", "go on")
    handed = result_of(await kernel.submit(kernel.runtime, "delivery.offer", {"agent": "bob"}))

    await confirm(kernel, "bob", handed["input"], evidence="command_lifecycle")

    assert sorted(delivered(kernel)) == [handed["input"]] and launched not in delivered(kernel)


async def test_a_native_resume_offers_nothing_its_harness_keeps(kernel):
    await spawned(kernel, "bob", goal="fix the test")
    await instruct(kernel, "bob", goal=True)
    head = kernel.head

    assert await instruct(kernel, "bob", resumed=True) is None
    assert of_type(kernel, "context.offered", after=head) == []
    assert of_type(kernel, "agent.instructed")[-1].v == 2
    refused = await kernel.submit(
        kernel.runtime, "agent.instruct", {"agent": "bob", "body": None, "goal": True, "resumed": True}
    )
    assert refused.refusal is not None and refused.refusal.code == "invalid"


async def test_a_relaunch_with_no_native_session_offers_afresh(kernel):
    await spawned(kernel, "bob", goal="fix the test")
    first = await instruct(kernel, "bob", goal=True)

    again = await instruct(kernel, "bob")

    offers = [event for event in of_type(kernel, "context.offered") if event.data["how"] == "launch"]
    assert [offer.seq for offer in offers] == [first, again]
    assert [item["ref"] for item in offers[1].data["items"]] == ["agent/bob@3"]


async def test_a_spawned_child_s_first_event_counts_its_goal_in_its_context_version(kernel):
    await spawned(kernel, "bob", goal="fix the test")
    await instruct(kernel, "bob", goal=True)
    await start(kernel, "bob")

    await start_turn(kernel, "bob")

    assert of_type(kernel, "turn.started")[-1].context_version == 1


async def test_a_read_is_confirmed_only_by_the_tool_item_that_holds_its_anchor(kernel):
    alice, bob = await spawn(kernel, "alice"), await spawn(kernel, "bob")
    await send(kernel, alice, "@bob", "read me")
    await start_turn(kernel, "bob")

    result_of(await kernel.submit(bob, "message.read", {}, native=ANCHOR))
    read_offer = of_type(kernel, "context.offered")[-1]
    unconfirmed = delivered(kernel)
    await returned(kernel, "bob", "toolu_2")
    await report(kernel, "bob", "item", kind="tool", phase="started", gist="read", native_id="toolu_1")
    still = delivered(kernel)
    await returned(kernel, "bob", "toolu_1")

    assert read_offer.native == ANCHOR and unconfirmed == {} and still == {}
    item, confirmation = of_type(kernel, "item.recorded", "context.delivered")[-2:]
    assert (confirmation.type, confirmation.cause, confirmation.seq) == (
        "context.delivered",
        (read_offer.seq,),
        item.seq + 1,
    )
    assert {key: confirmation.data[key] for key in ("how", "evidence", "native_id", "boundary")} == {
        "how": "read",
        "evidence": "tool_item",
        "native_id": "toolu_1",
        "boundary": "tool",
    }


async def test_a_tool_item_that_failed_confirms_nothing_under_it(kernel):
    """An interrupt, or a reply lost after the read committed, ends the item `failed`: its call returned no result."""
    alice, bob = await spawn(kernel, "alice"), await spawn(kernel, "bob")
    await send(kernel, alice, "@bob", "read me")
    await start_turn(kernel, "bob")
    result_of(await kernel.submit(bob, "message.read", {}, native=ANCHOR))

    await returned(kernel, "bob", "toolu_1", outcome="failed")
    failed = delivered(kernel)
    await report(kernel, "bob", "item", kind="tool", phase="completed", gist="said nothing", native_id="toolu_1")

    assert failed == {} and delivered(kernel) == {}


async def test_a_tool_item_finds_its_unconfirmed_offers_by_anchor_through_the_index(kernel):
    with kernel._reading() as db:
        plan = db.execute(
            "EXPLAIN QUERY PLAN SELECT input FROM v_deliveries_offers "
            "WHERE reader = ? AND anchor = ? AND delivered = 0 ORDER BY input",
            ("bob", "toolu_1"),
        ).fetchall()
    assert "INDEX v_deliveries_offers_anchor (reader=? AND anchor=?)" in plan[0]["detail"]


async def test_a_confirmed_read_moves_no_cursor_and_asks_nothing_again(kernel):
    lead = await spawn(kernel, "lead", role="lead")
    bob = await spawn(kernel, "bob", by=lead, stays=True)
    await send(kernel, lead, "@bob", "a question")
    await start_turn(kernel, "bob")
    result_of(await kernel.submit(bob, "message.read", {}, native=ANCHOR))
    await report(kernel, "bob", "item", kind="message", gist="an answer")
    await end_turn(kernel, "bob")
    head = kernel.head

    await returned(kernel, "bob", "toolu_1")

    assert [event.type for event in of_type(kernel, "context.delivered", after=head)] == ["context.delivered"]
    status = result_of(kernel.query(kernel.runtime, "agent.records", {"agent": "bob"}))[0]
    assert status["asked"] is False


async def test_a_shared_anchor_confirms_each_offer_under_it(kernel):
    """A Codex script makes several calls under one `callId`, and the item that ends it confirms each of them."""
    alice, bob = await spawn(kernel, "alice"), await spawn(kernel, "bob")
    await send(kernel, alice, "@bob", "one")
    await start_turn(kernel, "bob")
    script = {"callId": "exec-1"}
    result_of(await kernel.submit(bob, "message.read", {}, native=script))
    result_of(await kernel.submit(bob, "message.read", {"after": 0}, native=script))

    await returned(kernel, "bob", "exec-1")

    reads = [event.seq for event in of_type(kernel, "context.offered") if event.data["how"] == "read"]
    assert sorted(delivered(kernel)) == reads and len(reads) == 2


async def test_a_read_cut_off_before_its_item_stays_unconfirmed(kernel):
    alice, bob = await spawn(kernel, "alice"), await spawn(kernel, "bob")
    await send(kernel, alice, "@bob", "read me")
    await start_turn(kernel, "bob")
    page = await read(kernel, bob, "@bob")

    await report(kernel, "bob", "gap", what="stream_lost")
    await report(kernel, "bob", "exited", reason="its reports stopped")

    assert page["entries"] and delivered(kernel) == {}
