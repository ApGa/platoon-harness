"""Lifecycle and completion: spawn, the one ended transition, the monitor, and what `settled` means."""

import pytest

from platoon_harness.kernel import Kernel, Principal, Refused, hash_token
from platoon_harness.primitives import OWNER_STOP, PRIMITIVES, hold_open
from platoon_harness.tools import shell_name
from platoon_harness.tools.surface import refusal_text

from ..kernel.support import supervised, until
from .support import (
    agent,
    channel,
    end_turn,
    enroll,
    events_of,
    gists,
    grant,
    of_type,
    read,
    refusal,
    report,
    result_of,
    send,
    settle_effects,
    spawn,
    start,
    start_turn,
)


def state_of(kernel, name: str) -> dict:
    return result_of(kernel.query(kernel.runtime, "agent.status", {"agent": name}))


def spawning(name: str, role: str = "worker") -> dict:
    return {"name": name, "child_role": role, "goal": f"be {name}"}


async def test_spawn_requests_admit_workspace_and_launch_in_order(kernel):
    result_of(await kernel.submit(kernel.runtime, "agent.spawn", spawning("w1")))

    effects = result_of(kernel.query(kernel.runtime, "effect.ready", {}))

    assert [effect["kind"] for effect in effects] == ["admit"]
    head = of_type(kernel, "effect.requested")
    assert [event.data["kind"] for event in head] == ["admit", "workspace", "launch"]
    assert head[0].data["on_uncertain"] == "surface"
    assert head[2].data["data"]["goal"] == "be w1"


async def test_spawn_needs_a_grant_on_the_role(kernel):
    lead = await spawn(kernel, "lead", role="lead")
    await kernel.submit(kernel.runtime, "grant.remove", {"who": "agent", "ops": "*", "on": "*"})
    await grant(kernel, "role:lead", "agent.spawn", "role/worker")

    allowed = await kernel.submit(lead, "agent.spawn", spawning("w1"))
    refused = await kernel.submit(lead, "agent.spawn", spawning("l2", "lead"))

    assert allowed.refusal is None and refusal(refused).code == "not_permitted"


async def test_a_child_never_holds_more_than_may_spawn_allows(kernel):
    lead = await spawn(kernel, "lead", role="lead")

    outcome = await kernel.submit(lead, "agent.spawn", {**spawning("w1"), "scopes": ["*"]})

    assert refusal(outcome).code == "invalid"
    assert of_type(kernel, "op.refused")


async def test_spawn_of_an_unknown_role_is_refused(kernel):
    assert refusal(await kernel.submit(kernel.runtime, "agent.spawn", spawning("x", "nobody"))).code == "not_found"


async def test_a_name_is_used_once_for_good(kernel):
    bob = await spawn(kernel, "bob")
    result_of(await kernel.submit(bob, "agent.finish", {}))

    assert refusal(await kernel.submit(kernel.runtime, "agent.spawn", spawning("bob"))).code == "conflict"


async def test_depth_comes_from_the_parent_record_never_from_arguments(kernel):
    lead = await spawn(kernel, "lead", role="lead")
    worker = await spawn(kernel, "w1", by=lead)
    await spawn(kernel, "w2", by=worker)

    assert state_of(kernel, "w2")["depth"] == 2
    assert refusal(await kernel.submit(lead, "agent.spawn", {**spawning("w3"), "depth": 0})).code == "invalid"


@pytest.mark.parametrize("limits", [{"max_depth": 1}])
async def test_max_depth_is_enforced_from_the_parent_record(kernel, limits):
    lead = await spawn(kernel, "lead", role="lead")
    worker = await spawn(kernel, "w1", by=lead)

    refused = refusal(await kernel.submit(worker, "agent.spawn", spawning("w2")))

    assert refused.code == "not_permitted" and "max_depth" in refused.detail


@pytest.mark.parametrize("limits", [{"max_children": 1}])
async def test_max_children_counts_those_still_spawning(kernel, limits):
    lead = await spawn(kernel, "lead", role="lead")
    result_of(await kernel.submit(lead, "agent.spawn", spawning("w1")))

    assert refusal(await kernel.submit(lead, "agent.spawn", spawning("w2"))).code == "not_permitted"


@pytest.mark.parametrize("limits", [{"max_live": 2}])
async def test_max_live_counts_those_still_spawning(kernel, limits):
    result_of(await kernel.submit(kernel.runtime, "agent.spawn", spawning("w1")))
    result_of(await kernel.submit(kernel.runtime, "agent.spawn", spawning("w2")))

    assert refusal(await kernel.submit(kernel.runtime, "agent.spawn", spawning("w3"))).code == "not_permitted"


async def test_spawn_reserves_in_the_admission_transaction(kernel):
    result_of(await kernel.submit(kernel.runtime, "budget.set", {"limits": {"agents": 1}}))
    result_of(await kernel.submit(kernel.runtime, "agent.spawn", spawning("w1")))
    head = kernel.head

    refused = refusal(await kernel.submit(kernel.runtime, "agent.spawn", spawning("w2")))

    assert refused.code == "over_budget"
    assert of_type(kernel, "agent.spawned", after=head) == []
    assert result_of(kernel.query(kernel.runtime, "budget.status", {}))[0]["held"] == 1


async def test_a_failed_spawn_releases_its_reservation(kernel):
    result_of(await kernel.submit(kernel.runtime, "budget.set", {"limits": {"agents": 1}}))
    result_of(await kernel.submit(kernel.runtime, "agent.spawn", spawning("w1")))

    await report(kernel, "w1", "exited", reason="mint failed")

    assert state_of(kernel, "w1")["status"] == "failed"
    assert result_of(kernel.query(kernel.runtime, "budget.status", {}))[0]["held"] == 0
    result_of(await kernel.submit(kernel.runtime, "agent.spawn", spawning("w2")))


async def test_a_closing_session_refuses_a_spawn(kernel, ada):
    result_of(await kernel.submit(ada, "session.close", {}))

    assert refusal(await kernel.submit(kernel.runtime, "agent.spawn", spawning("w1"))).code == "conflict"


async def test_report_vocabulary_is_closed(kernel):
    await spawn(kernel, "bob")
    args = {"agent": "bob", "report": {"type": "made-up"}}

    assert refusal(await kernel.submit(kernel.runtime, "agent.report", args)).code == "invalid"


async def test_a_harness_starts_once(kernel):
    await spawn(kernel, "bob")
    args = {"agent": "bob", "ready": {}, "declared": {}}

    assert refusal(await kernel.submit(kernel.runtime, "agent.start", args)).code == "conflict"


@pytest.mark.parametrize("type", ["ready", "delta"])
async def test_what_no_journal_takes_from_a_report_is_refused(kernel, type):
    await spawn(kernel, "bob")
    report = {"type": type, "text": "live"} if type == "delta" else {"type": type}

    args = {"agent": "bob", "report": report}

    assert refusal(await kernel.submit(kernel.runtime, "agent.report", args)).code == "invalid"


# The ended transition.


@pytest.mark.parametrize("op", ["agent.cancel", "agent.retire"])
async def test_ended_is_one_event_every_view_folds(kernel, ada, op):
    bob = await spawn(kernel, "bob", role="lead")
    alice = await spawn(kernel, "alice")
    await channel(kernel, "work", kind="queue")
    result_of(await kernel.submit(kernel.runtime, "task.add", {"queue": "work", "gist": "x"}))
    result_of(await kernel.submit(bob, "task.claim", {"queue": "work"}))
    wait = result_of(await kernel.submit(bob, "wait", {"on": [{"stream": "inbox/bob"}]}))
    await send(kernel, alice, "@bob", "queued")
    await kernel.submit(kernel.runtime, "approval.request", {"id": "a1", "agent": "bob", "gist": "rm -rf?"})
    if op == "agent.cancel":
        await report(kernel, "bob", "turn.started", turn="t1")
    head = kernel.head

    result_of(await kernel.submit(ada, op, {"agent": "bob"}))

    ended = of_type(kernel, "agent.ended", after=head)
    assert len(ended) == 1
    assert result_of(kernel.query(kernel.runtime, "wait.progress", {"id": wait["id"]}))["state"] == "cancelled"
    assert result_of(kernel.query(kernel.runtime, "task.list", {"queue": "work"}))["tasks"][0]["state"] == "open"
    assert result_of(kernel.query(ada, "attention.list", {})) == []
    assert refusal(await kernel.submit(bob, "message.read", {"channel": "@bob"})).code == "not_permitted"


async def test_finish_cancel_retire_and_lost_end_the_same_way(kernel, ada):
    for name in "abcd":
        await spawn(kernel, name)

    result_of(await kernel.submit(agent("a"), "agent.finish", {}))
    result_of(await kernel.submit(ada, "agent.cancel", {"agent": "b"}))
    result_of(await kernel.submit(ada, "agent.retire", {"agent": "c"}))
    await report(kernel, "d", "exited")

    ended = of_type(kernel, "agent.ended")
    assert [(event.agent, event.data["status"]) for event in ended] == [
        ("a", "finished"),
        ("b", "cancelled"),
        ("c", "retired"),
        ("d", "lost"),
    ]


async def test_a_lost_child_tells_a_parent_parked_on_it(kernel):
    lead = await spawn(kernel, "lead", role="lead")
    await spawn(kernel, "bob", by=lead)
    placed = result_of(await kernel.submit(lead, "wait", {"from": ["bob"]}))

    await report(kernel, "bob", "exited", reason="segfault")

    assert of_type(kernel, "message.sent")[-1].gist == "bob lost: segfault"
    assert result_of(kernel.query(kernel.runtime, "delivery.ready", {}))["waits"] == [placed["id"]]


@pytest.mark.parametrize(("op", "status"), [("agent.cancel", "cancelled"), ("agent.retire", "retired")])
async def test_a_child_ended_by_someone_else_is_reported(kernel, ada, op, status):
    lead = await spawn(kernel, "lead", role="lead")
    await spawn(kernel, "bob", by=lead)

    result_of(await kernel.submit(ada, op, {"agent": "bob"}))

    report_sent = of_type(kernel, "message.sent")[-1]
    assert report_sent.gist.startswith(f"bob {status}:") and report_sent.data["subject"] == "bob"
    assert report_sent.actor == "runtime"


async def test_a_failed_spawn_tells_whoever_spawned_it(kernel):
    lead = await spawn(kernel, "lead", role="lead")
    result_of(await kernel.submit(lead, "agent.spawn", spawning("bob")))

    await report(kernel, "bob", "exited", reason="no such binary")

    assert gists(await read(kernel, lead, "@lead")) == ["bob failed: no such binary"]


async def test_a_parent_ended_first_hears_nothing_and_stops_nothing(kernel, ada):
    lead = await spawn(kernel, "lead", role="lead")
    await spawn(kernel, "bob", role="linked", by=lead)

    result_of(await kernel.submit(ada, "agent.cancel", {"agent": "lead"}))

    assert state_of(kernel, "bob")["status"] == "cancelled"
    assert of_type(kernel, "message.sent") == []


async def test_a_revoked_human_parent_hears_nothing_and_stops_nothing(kernel, ada):
    bob = await spawn(kernel, "bob", by=ada)
    result_of(await kernel.submit(kernel.runtime, "principal.revoke", {"id": ada.id}))

    result_of(await kernel.submit(bob, "agent.finish", {"gist": "done"}))

    assert state_of(kernel, "bob")["status"] == "finished"


async def test_a_root_agents_final_report_stays_in_the_journal_and_reaches_a_human(kernel, ada):
    lead = await spawn(kernel, "lead", role="lead")
    body = await kernel.put_body(b"the whole answer")

    result_of(await kernel.submit(lead, "agent.finish", {"gist": "the answer", "body": f"sha256:{body}"}))

    ended = of_type(kernel, "agent.ended")[-1]
    assert ended.data["report"] == "the answer" and ended.data["body"] == f"sha256:{body}"
    rows = result_of(kernel.query(ada, "attention.list", {}))
    assert [(row["kind"], row["gist"]) for row in rows] == [("mention", "lead finished: the answer")]


async def test_a_report_that_reached_a_parent_asks_no_human(kernel, ada):
    lead = await spawn(kernel, "lead", role="lead")
    bob = await spawn(kernel, "bob", by=lead)

    result_of(await kernel.submit(bob, "agent.finish", {"gist": "done"}))

    assert result_of(kernel.query(ada, "attention.list", {})) == []


async def test_the_monitor_posts_this_turns_final_text_and_no_earlier_one(kernel):
    lead = await spawn(kernel, "lead", role="lead")
    await spawn(kernel, "bob", by=lead)
    await start_turn(kernel, "bob")
    await report(kernel, "bob", "item", kind="message", gist="the result of turn one")
    await end_turn(kernel, "bob")
    await start_turn(kernel, "bob", "t2")
    await report(kernel, "bob", "item", kind="tool", gist="ran something")

    await end_turn(kernel, "bob")

    assert of_type(kernel, "message.sent")[-1].gist == "bob ended its turn with no final text."


async def test_ending_cancels_what_an_agent_had_still_to_start(kernel, ada):
    result_of(await kernel.submit(ada, "agent.spawn", spawning("bob")))

    result_of(await kernel.submit(ada, "agent.cancel", {"agent": "bob"}))

    ready = result_of(kernel.query(kernel.runtime, "effect.ready", {}))
    assert [effect["kind"] for effect in ready] == ["stop"]
    assert [event.data["kind"] for event in of_type(kernel, "effect.cancelled")] == ["admit", "workspace", "launch"]


async def test_ending_cancels_a_queued_delivery_too(kernel, ada):
    await spawn(kernel, "bob")
    await send(kernel, kernel.runtime, "@bob", "go")
    result_of(await kernel.submit(kernel.runtime, "delivery.offer", {"agent": "bob"}))

    result_of(await kernel.submit(ada, "agent.cancel", {"agent": "bob"}))

    assert [effect["kind"] for effect in result_of(kernel.query(kernel.runtime, "effect.ready", {}))] == ["stop"]


@pytest.mark.parametrize("step", ["admit", "workspace", "launch"])
async def test_a_failed_spawn_step_ends_the_agent_and_stops_the_rest(kernel, step):
    await set_limits_turns(kernel)
    result_of(await kernel.submit(kernel.runtime, "agent.spawn", spawning("bob")))
    while (effect := result_of(kernel.query(kernel.runtime, "effect.ready", {}))[0])["kind"] != step:
        attempt = result_of(await kernel.submit(kernel.runtime, "effect.start", {"id": effect["id"]}))
        result_of(await kernel.submit(kernel.runtime, "effect.finish", {"id": effect["id"], "attempt": attempt}))
    attempt = result_of(await kernel.submit(kernel.runtime, "effect.start", {"id": effect["id"]}))
    head = kernel.head

    async with supervised(kernel):
        args = {"id": effect["id"], "attempt": attempt, "error": "refused"}
        result_of(await kernel.submit(kernel.runtime, "effect.fail", args))
        ended = await until(kernel, "agent.ended", after=head)

    assert ended.data["status"] == "failed"
    held = next(row for row in result_of(kernel.query(kernel.runtime, "budget.status", {})) if row["unit"] == "turns")
    assert held["held"] == 0


async def set_limits_turns(kernel) -> None:
    result_of(await kernel.submit(kernel.runtime, "budget.set", {"limits": {"turns": 9}}))


async def test_a_failed_admit_leaves_nothing_to_start_while_it_is_being_ended(kernel):
    result_of(await kernel.submit(kernel.runtime, "agent.spawn", spawning("bob")))
    admit = result_of(kernel.query(kernel.runtime, "effect.ready", {}))[0]
    attempt = result_of(await kernel.submit(kernel.runtime, "effect.start", {"id": admit["id"]}))

    args = {"id": admit["id"], "attempt": attempt, "error": "refused"}
    result_of(await kernel.submit(kernel.runtime, "effect.fail", args))

    assert result_of(kernel.query(kernel.runtime, "effect.ready", {})) == []
    assert result_of(kernel.query(kernel.runtime, "delivery.ready", {}))["stranded"] == [
        ["bob", "its spawn failed: refused"]
    ]


async def test_retiring_is_refused_while_a_turn_is_open(kernel, ada):
    await spawn(kernel, "bob")
    await start_turn(kernel, "bob")

    assert refusal(await kernel.submit(ada, "agent.retire", {"agent": "bob"})).code == "conflict"
    assert state_of(kernel, "bob")["state"] == "running"


async def test_an_agent_ends_once(kernel, ada):
    await spawn(kernel, "bob")
    result_of(await kernel.submit(ada, "agent.cancel", {"agent": "bob"}))

    assert refusal(await kernel.submit(ada, "agent.retire", {"agent": "bob"})).code == "conflict"


async def test_ending_stops_the_process_and_closes_an_open_turn(kernel, ada):
    await spawn(kernel, "bob")
    await start_turn(kernel, "bob")

    result_of(await kernel.submit(ada, "agent.cancel", {"agent": "bob"}))

    stops = [event for event in of_type(kernel, "effect.requested") if event.data["kind"] == "stop"]
    assert stops[0].data["priority"] == 1 and stops[0].data["on_uncertain"] == "retry"
    assert "open_turn" not in result_of(kernel.query(kernel.runtime, "session.status", {}))["blockers"]


async def test_finishing_outside_a_turn_ends_the_agent_at_once(kernel):
    bob = await spawn(kernel, "bob")

    result_of(await kernel.submit(bob, "agent.finish", {"gist": "done"}))

    assert state_of(kernel, "bob")["status"] == "finished"


async def test_finishing_in_a_turn_ends_the_agent_with_that_turn(kernel):
    bob = await spawn(kernel, "bob")
    await start_turn(kernel, "bob")

    result_of(await kernel.submit(bob, "agent.finish", {"gist": "done"}))

    assert state_of(kernel, "bob")["state"] == "running"
    await end_turn(kernel, "bob")
    assert state_of(kernel, "bob")["status"] == "finished"
    assert of_type(kernel, "agent.ended")[-1].data["report"] == "done"
    assert [event.data["key"] for event in of_type(kernel, "timer.cleared")] == ["agent/bob/finish"]


async def test_what_a_harness_says_as_its_turn_ends_counts_after_a_finish(kernel):
    bob = await spawn(kernel, "bob")
    await start_turn(kernel, "bob")
    result_of(await kernel.submit(bob, "agent.finish", {}))

    await report(kernel, "bob", "item", kind="message", gist="my last words")
    await report(kernel, "bob", "usage", tokens=1000, label="provider")
    await end_turn(kernel, "bob")

    assert of_type(kernel, "agent.ended")[-1].data["report"] == "my last words"
    ending = result_of(kernel.query(kernel.runtime, "session.ending", {}))
    assert ending["usage"]["tokens"] == {"amount": 1000.0, "label": "provider"}


async def test_a_stated_report_outranks_a_last_message(kernel):
    bob = await spawn(kernel, "bob")
    await start_turn(kernel, "bob")
    result_of(await kernel.submit(bob, "agent.finish", {"gist": "the report"}))

    await report(kernel, "bob", "item", kind="message", gist="bye")
    await end_turn(kernel, "bob")

    assert of_type(kernel, "agent.ended")[-1].data["report"] == "the report"


async def test_finishing_twice_is_refused(kernel):
    bob = await spawn(kernel, "bob")
    await start_turn(kernel, "bob")
    result_of(await kernel.submit(bob, "agent.finish", {}))

    assert refusal(await kernel.submit(bob, "agent.finish", {})).code == "conflict"


async def test_a_turn_that_goes_on_after_a_finish_is_cut_off_by_a_timer(kernel, clock):
    bob = await spawn(kernel, "bob")
    await start_turn(kernel, "bob")

    result_of(await kernel.submit(bob, "agent.finish", {"gist": "done"}))

    timer = of_type(kernel, "timer.set")[-1]
    assert (timer.data["op"], timer.data["due"]) == ("agent.conclude", clock.now() + 60.0)
    result_of(await kernel.submit(kernel.runtime, "agent.conclude", {"agent": "bob"}))
    assert (state_of(kernel, "bob")["status"], state_of(kernel, "bob")["turn"]) == ("finished", None)


async def test_a_conclusion_leaves_an_agent_that_has_ended_alone(kernel, ada):
    bob = await spawn(kernel, "bob")
    await start_turn(kernel, "bob")
    result_of(await kernel.submit(bob, "agent.finish", {}))
    result_of(await kernel.submit(ada, "agent.cancel", {"agent": "bob"}))

    result_of(await kernel.submit(kernel.runtime, "agent.conclude", {"agent": "bob"}))

    assert state_of(kernel, "bob")["status"] == "cancelled"


async def test_a_harness_that_exits_after_a_finish_has_finished(kernel):
    bob = await spawn(kernel, "bob")
    await start_turn(kernel, "bob")
    result_of(await kernel.submit(bob, "agent.finish", {"gist": "done"}))

    await report(kernel, "bob", "exited", reason="it went")

    assert state_of(kernel, "bob")["status"] == "finished"


# Finishing over working children.


async def working_child(kernel, *, state: str = "running") -> Principal:
    """A parent over a child that would end with it, in one of the ways of working."""
    lead = await spawn(kernel, "lead", role="lead")
    if state == "spawning":
        result_of(await kernel.submit(lead, "agent.spawn", spawning("bob", "linked")))
        return lead
    await spawn(kernel, "bob", role="linked", by=lead, goal="" if state == "waking" else None)
    if state == "waking":
        await send(kernel, lead, "@bob", "go")
        result_of(await kernel.submit(kernel.runtime, "delivery.offer", {"agent": "bob"}))
    elif state == "running":
        await start_turn(kernel, "bob")
    return lead


@pytest.mark.parametrize("state", ["spawning", "goal not begun", "waking", "running"])
async def test_finishing_is_refused_over_a_child_on_its_way_to_a_turn_or_in_one(kernel, state):
    lead = await working_child(kernel, state=state)
    await start_turn(kernel, "lead")

    refused = refusal(await kernel.submit(lead, "agent.finish", {"gist": "all done"}))

    assert refused.code == "conflict"
    assert "@bob" in refused.detail
    assert of_type(kernel, "agent.finished") == []
    assert state_of(kernel, "bob")["status"] is None


async def test_finishing_is_refused_over_a_child_the_courier_is_about_to_wake(kernel):
    lead = await spawn(kernel, "lead", role="lead", goal="")
    await spawn(kernel, "bob", role="linked", by=lead, goal="")
    await start_turn(kernel, "lead")
    await send(kernel, lead, "@bob", "do the last thing")

    assert "@bob" in refusal(await kernel.submit(lead, "agent.finish", {"gist": "all done"})).detail


async def test_finishing_is_refused_over_a_child_whose_wait_holds(kernel):
    lead = await spawn(kernel, "lead", role="lead", goal="")
    await channel(kernel, "t")
    bob = await spawn(kernel, "bob", role="linked", by=lead, goal="")
    await start_turn(kernel, "bob")
    result_of(await kernel.submit(bob, "wait", {"channels": ["#t"]}))
    await end_turn(kernel, "bob")
    await start_turn(kernel, "lead")
    await send(kernel, lead, "#t", "go on")

    assert "@bob" in refusal(await kernel.submit(lead, "agent.finish", {"gist": "all done"})).detail


async def test_finishing_goes_through_over_a_child_the_budget_will_not_wake(kernel):
    result_of(await kernel.submit(kernel.runtime, "budget.set", {"scope": "role:linked", "limits": {"turns": 1}}))
    lead = await spawn(kernel, "lead", role="lead", goal="")
    await spawn(kernel, "bob", role="linked", by=lead)
    await start_turn(kernel, "bob")
    await end_turn(kernel, "bob")
    await send(kernel, lead, "@bob", "more")
    assert result_of(await kernel.submit(kernel.runtime, "delivery.offer", {"agent": "bob"})) is None

    result_of(await kernel.submit(lead, "agent.finish", {"gist": "all done"}))

    assert state_of(kernel, "lead")["status"] == "finished"


async def test_finishing_out_of_a_turn_is_refused_over_a_working_child_too(kernel):
    lead = await working_child(kernel)

    assert refusal(await kernel.submit(lead, "agent.finish", {})).code == "conflict"
    assert state_of(kernel, "lead")["status"] is None


async def test_a_refused_finish_says_what_to_do_next(kernel):
    lead = await working_child(kernel)

    refused = refusal(await kernel.submit(lead, "agent.finish", {}))

    text = refusal_text(refused, shell_name, kernel.ops, {"wait", "agent.cancel"})
    assert "`ph wait`" in text and "`ph agent.cancel`" in text
    assert " on session" not in text
    assert text.index("who would end with it") < text.index("`ph wait`") < text.index("@bob")


async def test_a_retire_refused_tells_a_person_nothing_of_a_turn(kernel, ada):
    await working_child(kernel)

    assert "turn" not in refusal(await kernel.submit(ada, "agent.retire", {"agent": "lead"})).detail


async def test_a_finish_refused_over_many_children_keeps_what_to_do_next(kernel):
    lead = await spawn(kernel, "lead", role="lead")
    for n in range(64):
        await spawn(kernel, f"some-child-with-a-long-name-{n}", role="linked", by=lead)

    refused = refusal(await kernel.submit(lead, "agent.finish", {}))

    assert "`wait`" in refused.detail and "`agent.cancel`" in refused.detail


async def test_a_refused_finish_leaves_the_turn_to_end_as_any_other(kernel):
    lead = await working_child(kernel)
    await start_turn(kernel, "lead")
    refusal(await kernel.submit(lead, "agent.finish", {}))

    await end_turn(kernel, "lead")

    assert state_of(kernel, "lead")["state"] == "idle"


async def test_a_finish_goes_through_once_the_child_has_ended(kernel):
    lead = await working_child(kernel)
    await start_turn(kernel, "lead")
    refusal(await kernel.submit(lead, "agent.finish", {}))
    result_of(await kernel.submit(lead, "agent.cancel", {"agent": "bob"}))

    result_of(await kernel.submit(lead, "agent.finish", {"gist": "all done"}))

    await end_turn(kernel, "lead")
    assert state_of(kernel, "lead")["status"] == "finished"


async def test_a_working_grandchild_holds_up_a_finish_through_a_child_that_ends_with_its_parent(kernel):
    lead = await spawn(kernel, "lead", role="lead")
    mid = await spawn(kernel, "mid", role="linked", by=lead)
    await spawn(kernel, "bob", role="linked", by=mid)
    await start_turn(kernel, "bob")

    assert "@bob" in refusal(await kernel.submit(lead, "agent.finish", {})).detail


@pytest.mark.parametrize("parked", [False, True])
async def test_a_child_out_of_a_turn_does_not_hold_up_a_finish(kernel, parked):
    lead = await spawn(kernel, "lead", role="lead")
    bob = await spawn(kernel, "bob", role="linked", by=lead, goal="")
    if parked:
        await start_turn(kernel, "bob")
        result_of(await kernel.submit(bob, "wait", {"from": ["lead"]}))
        await end_turn(kernel, "bob")
        assert state_of(kernel, "bob")["state"] == "waiting"

    result_of(await kernel.submit(lead, "agent.finish", {}))

    assert (state_of(kernel, "bob")["status"], of_type(kernel, "agent.ended")[-1].data["reason"]) == (
        "cancelled",
        "parent lead ended",
    )


async def test_an_adopted_child_and_all_below_it_do_not_hold_up_a_finish(kernel):
    lead = await spawn(kernel, "lead", role="lead")
    mid = await spawn(kernel, "mid", role="worker", by=lead)
    await spawn(kernel, "bob", role="linked", by=mid)
    await start_turn(kernel, "mid")
    await start_turn(kernel, "bob")

    result_of(await kernel.submit(lead, "agent.finish", {}))

    assert state_of(kernel, "lead")["status"] == "finished"
    assert state_of(kernel, "bob")["status"] is None


async def test_retiring_is_refused_over_a_working_child(kernel, ada):
    await working_child(kernel)

    refused = refusal(await kernel.submit(ada, "agent.retire", {"agent": "lead"}))

    assert refused.code == "conflict" and "@bob" in refused.detail
    assert state_of(kernel, "bob")["status"] is None


async def test_a_held_child_with_a_turn_open_holds_up_a_finish(kernel, ada):
    lead = await spawn(kernel, "lead", role="lead")
    await spawn(kernel, "bob", role="linked", by=lead, ready={"resume": True})
    await start_turn(kernel, "bob")
    result_of(await kernel.submit(ada, "agent.takeover", {"agent": "bob"}))

    assert "@bob" in refusal(await kernel.submit(lead, "agent.finish", {})).detail


async def test_cancelling_is_never_refused_over_working_children(kernel, ada):
    await working_child(kernel)

    result_of(await kernel.submit(ada, "agent.cancel", {"agent": "lead"}))

    assert state_of(kernel, "bob")["status"] == "cancelled"


async def test_an_agent_that_has_finished_starts_nothing_it_would_take_down_with_it(kernel):
    lead = await spawn(kernel, "lead", role="lead")
    await start_turn(kernel, "lead")
    result_of(await kernel.submit(lead, "agent.finish", {}))

    assert refusal(await kernel.submit(lead, "agent.spawn", spawning("bob", "linked"))).code == "conflict"


@pytest.mark.parametrize("how", ["its turn ended", "the timer fired", "its harness exited"])
async def test_a_child_that_began_work_after_a_finish_ends_with_its_parent(kernel, how):
    """The check is at the call. What comes after it ends with the agent, and says so."""
    lead = await spawn(kernel, "lead", role="lead")
    await spawn(kernel, "bob", role="linked", by=lead, goal="")
    await start_turn(kernel, "lead")
    result_of(await kernel.submit(lead, "agent.finish", {"gist": "all done"}))
    await start_turn(kernel, "bob")

    if how == "its turn ended":
        await end_turn(kernel, "lead")
    elif how == "the timer fired":
        result_of(await kernel.submit(kernel.runtime, "agent.conclude", {"agent": "lead"}))
    else:
        await report(kernel, "lead", "exited", reason="it went")

    assert state_of(kernel, "lead")["status"] == "finished"
    assert state_of(kernel, "bob")["status"] == "cancelled"
    assert of_type(kernel, "agent.ended")[-1].data["reason"] == "parent lead ended"


async def test_a_harness_that_exits_takes_its_working_children_with_it(kernel):
    await working_child(kernel)

    await report(kernel, "lead", "exited", reason="segfault")

    assert (state_of(kernel, "lead")["status"], state_of(kernel, "bob")["status"]) == ("lost", "cancelled")


async def test_a_one_shot_parent_takes_its_working_children_with_it(kernel):
    lead = await spawn(kernel, "lead", role="lead", ready={"persistent": False})
    await start_turn(kernel, "lead")
    await spawn(kernel, "bob", role="linked", by=lead)
    await start_turn(kernel, "bob")
    refusal(await kernel.submit(lead, "agent.finish", {}))

    await end_turn(kernel, "lead")

    assert (state_of(kernel, "lead")["status"], state_of(kernel, "bob")["status"]) == ("finished", "cancelled")


async def test_a_one_shot_agent_that_finished_is_finished_however_its_turn_ended(kernel):
    bob = await spawn(kernel, "bob", ready={"persistent": False})
    await start_turn(kernel, "bob")
    result_of(await kernel.submit(bob, "agent.finish", {}))

    await end_turn(kernel, "bob", "exited with code 1")

    assert state_of(kernel, "bob")["status"] == "finished"


async def test_an_ended_agent_can_still_be_named_in_evidence(kernel, ada):
    await spawn(kernel, "bob")
    result_of(await kernel.submit(ada, "agent.cancel", {"agent": "bob"}))

    await report(kernel, "bob", "native", kind="unproven_group", raw="group 7")
    await report(kernel, "bob", "gap", plane="control", what="crash_window")

    assert of_type(kernel, "native.recorded")[-1].data["raw"] == "group 7"
    assert of_type(kernel, "gap.recorded")[-1].agent == "bob"


async def test_an_ended_agent_says_nothing_else(kernel, ada):
    await spawn(kernel, "bob")
    result_of(await kernel.submit(ada, "agent.cancel", {"agent": "bob"}))

    args = {"agent": "bob", "report": {"type": "usage", "tokens": 1, "label": "provider"}}
    assert refusal(await kernel.submit(kernel.runtime, "agent.report", args)).code == "conflict"


async def test_a_reason_of_any_length_can_end_an_agent(kernel):
    await spawn(kernel, "bob")

    await report(kernel, "bob", "exited", reason="x" * 20_000)

    assert state_of(kernel, "bob")["status"] == "lost"
    assert len(of_type(kernel, "agent.ended")[-1].data["reason"]) == 1024


async def test_an_interrupt_reaches_a_wake_whose_turn_has_not_begun(kernel, ada):
    await spawn(kernel, "bob", goal="")
    await send(kernel, ada, "@bob", "go")
    result_of(await kernel.submit(kernel.runtime, "delivery.offer", {"agent": "bob"}))

    result_of(await kernel.submit(ada, "agent.interrupt", {"agent": "bob"}))

    assert "interrupt" in [effect["kind"] for effect in result_of(kernel.query(kernel.runtime, "effect.ready", {}))]


async def test_an_interrupt_with_nothing_under_way_is_refused(kernel, ada):
    await spawn(kernel, "bob", goal="")

    assert refusal(await kernel.submit(ada, "agent.interrupt", {"agent": "bob"})).code == "conflict"


async def test_a_goal_never_begun_is_told_again_as_a_delivery(kernel):
    await spawn(kernel, "bob", goal="do the important thing")

    result_of(await kernel.submit(kernel.runtime, "agent.retell", {"agent": "bob"}))

    handed = result_of(await kernel.submit(kernel.runtime, "delivery.offer", {"agent": "bob"}))
    assert [item["gist"] for item in handed["items"]] == ["do the important thing"]
    assert state_of(kernel, "bob")["state"] == "waking"


async def test_a_turn_a_crash_cut_off_is_told_until_another_begins(kernel):
    await spawn(kernel, "bob", goal="")
    await start_turn(kernel, "bob")
    await kernel.recover()

    for _ in range(2):
        result_of(await kernel.submit(kernel.runtime, "agent.retell", {"agent": "bob"}))
    await start_turn(kernel, "bob", "t2")
    result_of(await kernel.submit(kernel.runtime, "agent.retell", {"agent": "bob"}))

    assert len(of_type(kernel, "message.sent")) == 2


async def test_an_agent_that_has_ended_is_told_nothing(kernel):
    await spawn(kernel, "bob", goal="be bob")
    result_of(await kernel.submit(kernel.runtime, "agent.cancel", {"agent": "bob"}))

    result_of(await kernel.submit(kernel.runtime, "agent.retell", {"agent": "bob"}))

    assert of_type(kernel, "message.sent") == []


async def test_a_second_turn_cut_off_is_a_second_thing_to_tell(kernel):
    await spawn(kernel, "bob", goal="")
    for turn in ("t1", "t2"):
        await start_turn(kernel, "bob", turn)
        await kernel.recover()
        result_of(await kernel.submit(kernel.runtime, "agent.retell", {"agent": "bob"}))

    assert len(of_type(kernel, "message.sent")) == 2


async def test_a_harness_with_nothing_to_be_told_is_told_nothing(kernel):
    await spawn(kernel, "bob", goal="")

    result_of(await kernel.submit(kernel.runtime, "agent.retell", {"agent": "bob"}))

    assert of_type(kernel, "message.sent") == []


async def test_a_notice_wakes_an_agent_whose_inbox_would_not(kernel):
    await spawn(kernel, "bob", role="quiet", goal="")
    await start_turn(kernel, "bob")
    await kernel.recover()

    result_of(await kernel.submit(kernel.runtime, "agent.retell", {"agent": "bob"}))

    assert ready(kernel)["agents"] == ["bob"]


@pytest.mark.parametrize("reason", ["interrupted", OWNER_STOP])
async def test_a_turn_stopped_on_purpose_wakes_no_parent(kernel, reason):
    lead = await spawn(kernel, "lead", role="lead", goal="")
    await spawn(kernel, "bob", by=lead, goal="")
    await start_turn(kernel, "bob")

    await end_turn(kernel, "bob", reason)

    sent = of_type(kernel, "message.sent")[-1]
    assert sent.gist == f"bob turn {reason}"
    assert sent.data["delivery"] == "next-turn"


async def test_retiring_removes_an_agent_from_relations_never_from_history(kernel):
    lead = await spawn(kernel, "lead", role="lead")
    await spawn(kernel, "w1", by=lead)
    await spawn(kernel, "w2", by=lead)
    result_of(await kernel.submit(lead, "agent.retire", {"agent": "w1"}))

    await kernel.submit(kernel.runtime, "grant.remove", {"who": "agent", "ops": "*", "on": "*"})
    await grant(kernel, "role:lead", "message.send", "inbox/{children}")
    await grant(kernel, "role:lead", "peers")

    assert [peer["address"] for peer in result_of(kernel.query(lead, "peers", {}))["peers"]] == ["@w2"]
    assert state_of(kernel, "w1")["state"] == "ended"
    assert any(event.agent == "w1" for event in events_of(kernel))


async def test_on_parent_exit_cancel_subtree_ends_descendants(kernel, ada):
    lead = await spawn(kernel, "lead", role="lead")
    child = await spawn(kernel, "child", role="linked", by=lead)
    await spawn(kernel, "grandchild", role="linked", by=child)

    result_of(await kernel.submit(ada, "agent.cancel", {"agent": "lead"}))

    assert state_of(kernel, "child")["status"] == "cancelled"
    assert state_of(kernel, "grandchild")["status"] == "cancelled"


async def test_on_parent_exit_adopt_gives_orphans_to_the_session(kernel, ada):
    lead = await spawn(kernel, "lead", role="lead")
    await spawn(kernel, "child", role="worker", by=lead)

    result_of(await kernel.submit(ada, "agent.cancel", {"agent": "lead"}))

    assert state_of(kernel, "child")["state"] == "idle" and state_of(kernel, "child")["parent"] is None
    assert of_type(kernel, "agent.adopted")[0].agent == "child"


async def test_finish_is_only_for_agents(kernel, ada):
    assert refusal(await kernel.submit(ada, "agent.finish", {})).code == "invalid"


# Interrupt and takeover.


async def test_interrupt_stops_a_turn_and_leaves_the_agent(kernel, ada):
    await spawn(kernel, "bob")
    await start_turn(kernel, "bob")

    effect = result_of(await kernel.submit(ada, "agent.interrupt", {"agent": "bob"}))["effect"]

    ready = result_of(kernel.query(kernel.runtime, "effect.ready", {"kind": "interrupt"}))
    assert [(row["id"], row["priority"]) for row in ready] == [(effect, 1)]
    assert state_of(kernel, "bob")["state"] == "running"


async def test_interrupt_with_no_turn_is_refused(kernel, ada):
    await spawn(kernel, "bob")

    assert refusal(await kernel.submit(ada, "agent.interrupt", {"agent": "bob"})).code == "conflict"


async def test_takeover_holds_deliveries_and_release_records_a_gap(kernel, ada):
    await spawn(kernel, "bob", ready={"resume": True})

    result_of(await kernel.submit(ada, "agent.takeover", {"agent": "bob"}))
    assert state_of(kernel, "bob")["state"] == "held"

    result_of(await kernel.submit(ada, "agent.release", {"agent": "bob"}))
    assert state_of(kernel, "bob")["state"] == "idle"
    assert of_type(kernel, "gap.recorded")[-1].data["what"] == "takeover"


async def test_release_during_an_open_turn_returns_to_that_turn(kernel, ada):
    await spawn(kernel, "bob", ready={"resume": True})
    await start_turn(kernel, "bob")
    result_of(await kernel.submit(ada, "agent.takeover", {"agent": "bob"}))

    result_of(await kernel.submit(ada, "agent.release", {"agent": "bob"}))
    await send(kernel, ada, "@bob", "go")

    assert state_of(kernel, "bob")["state"] == "running"
    assert result_of(kernel.query(kernel.runtime, "delivery.ready", {}))["agents"] == []


async def test_takeover_is_disabled_with_a_reason_without_resume(kernel, ada):
    await spawn(kernel, "bob", ready={"resume": False})

    refused = refusal(await kernel.submit(ada, "agent.takeover", {"agent": "bob"}))

    assert refused.code == "unsupported" and "resume" in refused.detail


async def test_takeover_is_for_humans(kernel):
    alice = await spawn(kernel, "alice")
    await spawn(kernel, "bob", ready={"resume": True})

    assert refusal(await kernel.submit(alice, "agent.takeover", {"agent": "bob"})).code == "not_permitted"


async def test_human_driven_turns_carry_human_identity(kernel, ada):
    await spawn(kernel, "bob", ready={"resume": True})
    result_of(await kernel.submit(ada, "agent.takeover", {"agent": "bob"}))

    await start_turn(kernel, "bob")

    assert of_type(kernel, "turn.started")[-1].data["by"] == "human:ada"
    assert state_of(kernel, "bob")["state"] == "held"


async def test_a_held_turn_posts_no_monitor(kernel, ada):
    lead = await spawn(kernel, "lead", role="lead")
    await spawn(kernel, "bob", by=lead, ready={"resume": True})
    result_of(await kernel.submit(ada, "agent.takeover", {"agent": "bob"}))
    await start_turn(kernel, "bob")
    head = kernel.head

    await end_turn(kernel, "bob")

    assert of_type(kernel, "message.sent", after=head) == []


# The monitor.


async def test_a_turn_with_no_finish_and_no_wait_reports_to_the_parent(kernel):
    lead = await spawn(kernel, "lead", role="lead")
    await spawn(kernel, "bob", by=lead)
    await start_turn(kernel, "bob")
    await report(kernel, "bob", "item", kind="message", gist="all done here")

    await end_turn(kernel, "bob")

    assert gists(await read(kernel, lead, "@lead")) == ["all done here"]


async def test_the_monitor_is_runtime_authored_naming_the_child_as_subject(kernel):
    lead = await spawn(kernel, "lead", role="lead")
    bob = await spawn(kernel, "bob", by=lead)

    result_of(await kernel.submit(bob, "agent.finish", {"gist": "shipped"}))

    posted = of_type(kernel, "message.sent")[-1]
    assert posted.actor == "runtime" and posted.agent == "bob" and posted.stream == "inbox/lead"
    assert posted.gist == "shipped" and posted.data["subject"] == "bob"


async def test_a_turn_with_an_open_wait_posts_no_monitor(kernel):
    lead = await spawn(kernel, "lead", role="lead")
    bob = await spawn(kernel, "bob", by=lead)
    await start_turn(kernel, "bob")
    result_of(await kernel.submit(bob, "wait", {"on": [{"stream": "inbox/bob"}]}))

    await end_turn(kernel, "bob")

    assert of_type(kernel, "message.sent") == []


async def test_a_worker_reports_back_even_if_its_harness_hides_our_tools(kernel):
    lead = await spawn(kernel, "lead", role="lead")
    await spawn(kernel, "silent", by=lead)
    await start_turn(kernel, "silent")

    await end_turn(kernel, "silent")

    assert "no final text" in gists(await read(kernel, lead, "@lead"))[0]


async def test_a_human_parent_hears_from_the_monitor(kernel, ada):
    await spawn(kernel, "bob", by=ada)
    await start_turn(kernel, "bob")

    await end_turn(kernel, "bob")

    assert [row["kind"] for row in result_of(kernel.query(ada, "attention.list", {}))] == ["mention"]


async def test_an_agent_with_no_spawning_parent_has_no_monitor(kernel):
    await spawn(kernel, "bob")
    await start_turn(kernel, "bob")

    await end_turn(kernel, "bob")

    assert of_type(kernel, "message.sent") == []


async def test_the_monitor_wakes_at_most_once_per_causal_chain(kernel):
    lead = await spawn(kernel, "lead", role="lead")
    bob = await spawn(kernel, "bob", by=lead)
    await start_turn(kernel, "bob")
    await end_turn(kernel, "bob")
    assert of_type(kernel, "message.sent")[-1].data["delivery"] == "wake"

    await read(kernel, lead, "@lead")
    reply = await send(kernel, lead, "@bob", "and then?")
    await start_turn(kernel, "bob", "t2")
    await read(kernel, bob, "@bob")
    await end_turn(kernel, "bob")

    second = of_type(kernel, "message.sent")[-1]
    assert second.seq > reply["seq"] and second.data["delivery"] == "next-turn"


async def test_a_second_child_still_reports_back_with_a_wake(kernel):
    lead = await spawn(kernel, "lead", role="lead")
    c1, c2 = await spawn(kernel, "c1", by=lead), await spawn(kernel, "c2", by=lead)
    await send(kernel, lead, "@c1", "step one")
    await start_turn(kernel, "c1")
    await read(kernel, c1, "@c1")
    await end_turn(kernel, "c1")
    await start_turn(kernel, "lead")
    await read(kernel, lead, "@lead")
    await send(kernel, lead, "@c2", "step two")
    await end_turn(kernel, "lead")
    await start_turn(kernel, "c2")
    await read(kernel, c2, "@c2")

    await end_turn(kernel, "c2")

    assert of_type(kernel, "message.sent")[-1].data["delivery"] == "wake"


async def test_a_new_human_message_starts_a_new_chain(kernel, ada):
    lead = await spawn(kernel, "lead", role="lead")
    bob = await spawn(kernel, "bob", by=lead)
    await send(kernel, ada, "@bob", "fresh start")
    await start_turn(kernel, "bob")
    await read(kernel, bob, "@bob")

    await end_turn(kernel, "bob")

    assert of_type(kernel, "message.sent")[-1].data["delivery"] == "wake"


def ready(kernel: Kernel) -> dict:
    return result_of(kernel.query(kernel.runtime, "delivery.ready", {}))


async def parked_on(kernel: Kernel, *children: str, role: str = "worker", **wait) -> Principal:
    """A lead over these children, parked on a wait that says `wait`, or for all of them to end."""
    lead = await spawn(kernel, "lead", role="lead", goal="")
    for child in children:
        await spawn(kernel, child, role=role, by=lead, goal="")
    await start_turn(kernel, "lead")
    result_of(await kernel.submit(lead, "wait", wait or {"agents": list(children)}))
    await end_turn(kernel, "lead")
    assert state_of(kernel, "lead")["state"] == "waiting"
    return lead


async def finished(kernel: Kernel, by: Principal) -> None:
    result_of(await kernel.submit(by, "agent.finish", {"gist": f"{by.name} is done"}))


async def test_a_join_of_three_costs_one_wake(kernel):
    await parked_on(kernel, "a", "b", "c")

    for name in ("a", "b"):
        await finished(kernel, agent(name))
        assert ready(kernel) == {"agents": [], "waits": [], "stranded": [], "due": None}
    await finished(kernel, agent("c"))

    wait = ready(kernel)["waits"]
    assert ready(kernel)["agents"] == []
    result_of(await kernel.submit(kernel.runtime, "wait.release", {"id": wait[0]}))
    assert ready(kernel)["agents"] == ["lead"]
    handed = result_of(await kernel.submit(kernel.runtime, "delivery.offer", {"agent": "lead"}))
    assert [item["gist"] for item in handed["items"]] == [
        "a is done",
        "b is done",
        "c is done",
        "Your wait holds.",
    ]
    assert handed["behind"] == 0


@pytest.mark.parametrize("wait", [{"from": ["a", "b"]}, {"agents": ["a", "b"]}])
async def test_a_report_the_parent_is_counting_does_not_wake_it(kernel, wait):
    await parked_on(kernel, "a", "b", **wait)

    await finished(kernel, agent("a"))

    assert of_type(kernel, "message.sent")[-1].data["delivery"] == "next-turn"
    assert ready(kernel)["agents"] == []


async def test_a_join_on_tasks_costs_one_wake(kernel):
    lead = await spawn(kernel, "lead", role="lead", goal="")
    await channel(kernel, "q", "queue")
    workers = [await spawn(kernel, name, by=lead, goal="") for name in ("a", "b")]
    ids = [result_of(await kernel.submit(lead, "task.add", {"queue": "q", "gist": "do"}))["task"] for _ in workers]
    await start_turn(kernel, "lead")
    placed = result_of(await kernel.submit(lead, "wait", {"tasks": [f"q/{id}" for id in ids]}))
    await end_turn(kernel, "lead")

    first, second = workers
    await start_turn(kernel, "b")
    result_of(await kernel.submit(first, "task.claim", {"queue": "q"}))
    result_of(await kernel.submit(first, "task.complete", {"queue": "q"}))
    await finished(kernel, first)

    assert ready(kernel)["agents"] == []
    result_of(await kernel.submit(second, "task.claim", {"queue": "q"}))
    result_of(await kernel.submit(second, "task.complete", {"queue": "q"}))
    await end_turn(kernel, "b")

    assert ready(kernel)["waits"] == [placed["id"]]
    result_of(await kernel.submit(kernel.runtime, "wait.release", {"id": placed["id"]}))
    result_of(await kernel.submit(kernel.runtime, "delivery.offer", {"agent": "lead"}))
    assert ready(kernel)["agents"] == []
    assert len(of_type(kernel, "agent.woken")) == 1


async def test_a_task_a_child_left_undone_is_no_report_the_wait_counts(kernel):
    lead = await spawn(kernel, "lead", role="lead", goal="")
    await channel(kernel, "q", "queue")
    worker = await spawn(kernel, "a", by=lead, goal="")
    id = result_of(await kernel.submit(lead, "task.add", {"queue": "q", "gist": "do"}))["task"]
    await start_turn(kernel, "lead")
    result_of(await kernel.submit(lead, "wait", {"tasks": [f"q/{id}"]}))
    await end_turn(kernel, "lead")
    result_of(await kernel.submit(worker, "task.claim", {"queue": "q"}))
    result_of(await kernel.submit(worker, "task.fail", {"queue": "q", "gist": "no good"}))

    await finished(kernel, worker)

    assert ready(kernel)["agents"] == ["lead"]


@pytest.mark.parametrize("how", ["agent.cancel", "agent.retire", "exited"])
async def test_a_counted_child_that_ended_badly_wakes_the_parent_and_the_wait_stays(kernel, ada, how):
    lead = await parked_on(kernel, "a", "b")

    if how == "exited":
        await report(kernel, "a", "exited", reason="segfault")
    else:
        result_of(await kernel.submit(ada, how, {"agent": "a"}))

    assert of_type(kernel, "message.sent")[-1].data["delivery"] == "wake"
    assert ready(kernel)["agents"] == ["lead"]
    wait = result_of(kernel.query(lead, "wait.progress", {}))
    assert (wait["state"], wait["have"], wait["need"]) == ("open", 1, 2)


async def test_a_report_the_wait_does_not_count_wakes_the_parent(kernel):
    await parked_on(kernel, "a", "b", agents=["b"])

    await finished(kernel, agent("a"))

    assert ready(kernel)["agents"] == ["lead"]


async def test_a_turn_end_is_no_end_so_a_join_on_that_child_is_woken_by_it(kernel):
    """A child that ends a turn with no finish has not ended, and only this wake can rescue the join."""
    await parked_on(kernel, "a", "b")

    await start_turn(kernel, "a")
    await end_turn(kernel, "a")

    assert ready(kernel)["agents"] == ["lead"]


async def test_a_turn_the_parent_was_waiting_to_hear_of_does_not_wake_it(kernel):
    await parked_on(kernel, "a", "b", **{"from": ["a", "b"]})

    await start_turn(kernel, "a")
    await report(kernel, "a", "item", kind="message", gist="here it is")
    await end_turn(kernel, "a")

    assert ready(kernel)["agents"] == []


async def on_two_tasks(kernel: Kernel, *others: str) -> Principal:
    """A lead parked on two tasks, of which its worker `a` has settled one, and these others below it."""
    lead = await spawn(kernel, "lead", role="lead", goal="")
    await channel(kernel, "q", "queue")
    worker = await spawn(kernel, "a", by=lead, goal="")
    for name in others:
        await spawn(kernel, name, by=lead, goal="")
    ids = [result_of(await kernel.submit(lead, "task.add", {"queue": "q", "gist": "do"}))["task"] for _ in "ab"]
    await start_turn(kernel, "lead")
    result_of(await kernel.submit(lead, "wait", {"tasks": [f"q/{id}" for id in ids]}))
    await end_turn(kernel, "lead")
    await start_turn(kernel, "a")
    result_of(await kernel.submit(worker, "task.claim", {"queue": "q"}))
    result_of(await kernel.submit(worker, "task.complete", {"queue": "q"}))
    return lead


async def test_a_report_of_a_counted_task_leaves_the_wake_to_those_still_at_work(kernel):
    await on_two_tasks(kernel, "b")
    await start_turn(kernel, "b")

    await end_turn(kernel, "a")

    assert ready(kernel)["agents"] == []


async def test_the_last_worker_at_work_wakes_a_join_on_tasks_it_left_open(kernel):
    await on_two_tasks(kernel, "b")

    await end_turn(kernel, "a")

    assert ready(kernel)["agents"] == ["lead"]


async def test_a_worker_that_finishes_with_a_task_open_wakes_a_join_it_cannot_end(kernel):
    await on_two_tasks(kernel)

    await finished(kernel, agent("a"))
    await end_turn(kernel, "a")

    assert ready(kernel)["agents"] == ["lead"]


async def test_someone_at_work_elsewhere_is_no_reason_to_stay_quiet(kernel):
    await on_two_tasks(kernel)
    await spawn(kernel, "stranger", goal="")
    await start_turn(kernel, "stranger")

    await end_turn(kernel, "a")

    assert ready(kernel)["agents"] == ["lead"]


async def test_a_child_of_a_parent_that_has_gone_still_ends(kernel, ada):
    child = await spawn(kernel, "a", by=ada, goal="")
    await channel(kernel, "q", "queue")
    result_of(await kernel.submit(ada, "task.add", {"queue": "q", "gist": "do"}))
    result_of(await kernel.submit(ada, "task.add", {"queue": "q", "gist": "do"}))
    result_of(await kernel.submit(ada, "wait", {"tasks": ["q/1", "q/2"]}))
    result_of(await kernel.submit(child, "task.claim", {"queue": "q"}))
    result_of(await kernel.submit(child, "task.complete", {"queue": "q"}))
    result_of(await kernel.submit(kernel.runtime, "principal.revoke", {"id": ada.id}))

    result_of(await kernel.submit(child, "agent.finish", {"gist": "done"}))

    assert state_of(kernel, "a")["status"] == "finished"


async def test_a_wait_on_other_events_of_a_child_does_not_count_its_end(kernel):
    lead = await spawn(kernel, "lead", role="lead", goal="")
    child = await spawn(kernel, "a", by=lead, goal="")
    await start_turn(kernel, "lead")
    result_of(await kernel.submit(lead, "wait", {"on": [{"stream": "agent/a", "types": ["gap.recorded"]}]}))
    await end_turn(kernel, "lead")

    await finished(kernel, child)

    assert ready(kernel)["agents"] == ["lead"]


async def report_held_back(kernel: Kernel, **wait: object) -> tuple[Principal, dict]:
    """A lead in a turn with a wait open on its child, whose report that wait held back."""
    lead = await spawn(kernel, "lead", role="lead", goal="")
    child = await spawn(kernel, "a", by=lead, goal="")
    await start_turn(kernel, "lead")
    placed = result_of(await kernel.submit(lead, "wait", {"agents": ["a"], **wait}))
    await finished(kernel, child)
    assert of_type(kernel, "message.sent")[-1].data["delivery"] == "next-turn"
    return lead, placed


async def test_a_report_a_wait_held_back_reaches_a_turn_after_wait_cancel(kernel):
    lead, _ = await report_held_back(kernel)

    result_of(await kernel.submit(lead, "wait.cancel", {}))
    await end_turn(kernel, "lead")

    assert ready(kernel)["agents"] == ["lead"]
    handed = result_of(await kernel.submit(kernel.runtime, "delivery.offer", {"agent": "lead"}))
    assert "a is done" in [item["gist"] for item in handed["items"]]


async def test_a_report_a_held_wait_held_back_reaches_a_turn_after_its_answer(kernel):
    _, placed = await report_held_back(kernel, hold=30.0)

    shown = await hold_open(kernel, placed)
    assert shown["state"] == "released"
    result_of(await kernel.submit(kernel.runtime, "wait.release", {"id": placed["id"], "told": True}))
    await end_turn(kernel, "lead")

    assert ready(kernel)["agents"] == ["lead"]
    handed = result_of(await kernel.submit(kernel.runtime, "delivery.offer", {"agent": "lead"}))
    assert "a is done" in [item["gist"] for item in handed["items"]]


async def test_a_wait_cancelled_with_nothing_held_back_wakes_nobody(kernel):
    lead = await spawn(kernel, "lead", role="lead", goal="")
    await spawn(kernel, "a", by=lead, goal="")
    await channel(kernel, "t")
    await channel(kernel, "news", "topic", delivery="next-turn")
    await start_turn(kernel, "lead")
    result_of(await kernel.submit(lead, "wait", {"agents": ["a"]}))
    await send(kernel, agent("a"), "#news", "not for waking")

    result_of(await kernel.submit(lead, "wait.cancel", {}))
    await end_turn(kernel, "lead")

    assert ready(kernel)["agents"] == []


async def spent_chain(kernel: Kernel) -> None:
    """A child that reported, spending its chain's wake, and a lead that replied and parked on its end."""
    lead = await spawn(kernel, "lead", role="lead", goal="")
    await spawn(kernel, "a", by=lead, goal="")
    await start_turn(kernel, "a")
    await report(kernel, "a", "item", kind="message", gist="first go")
    await end_turn(kernel, "a")
    result_of(await kernel.submit(kernel.runtime, "delivery.offer", {"agent": "lead"}))
    await start_turn(kernel, "lead")
    await send(kernel, lead, "@a", "again")
    result_of(await kernel.submit(lead, "wait", {"agents": ["a"]}))
    await end_turn(kernel, "lead")
    result_of(await kernel.submit(kernel.runtime, "delivery.offer", {"agent": "a"}))
    await start_turn(kernel, "a", "t2")


async def test_a_failed_turn_breaks_in_on_a_parked_parent_past_a_spent_chain(kernel):
    await spent_chain(kernel)

    await end_turn(kernel, "a", "rate limited")

    assert ready(kernel)["agents"] == ["lead"]


async def test_a_spent_chain_still_stops_a_turn_that_went_well(kernel):
    await spent_chain(kernel)

    await end_turn(kernel, "a")

    assert ready(kernel)["agents"] == []


@pytest.mark.parametrize("limits", [{"max_hops": 1}])
async def test_max_hops_stops_a_failed_turn_breaking_in(kernel, limits):
    await spent_chain(kernel)

    await end_turn(kernel, "a", "rate limited")

    assert ready(kernel)["agents"] == []
    assert of_type(kernel, "wake.refused")[-1].data["why"] == "hops"


@pytest.mark.parametrize("limits", [{"max_hops": 0}])
async def test_a_report_that_wants_no_wake_is_refused_none(kernel, limits):
    lead = await parked_on(kernel, "a", "b")
    await send(kernel, lead, "@a", "go")
    await start_turn(kernel, "a")
    await read(kernel, agent("a"), "@a")
    head = kernel.head

    await finished(kernel, agent("a"))
    await end_turn(kernel, "a")

    assert of_type(kernel, "wake.refused", after=head) == []


@pytest.mark.parametrize("op", ["agent.cancel", "agent.retire"])
async def test_a_parent_that_ended_its_own_child_is_not_woken_to_hear_of_it(kernel, op):
    lead = await spawn(kernel, "lead", role="lead", goal="")
    await spawn(kernel, "bob", by=lead, goal="")
    await start_turn(kernel, "lead")

    result_of(await kernel.submit(lead, op, {"agent": "bob"}))
    await end_turn(kernel, "lead")

    assert of_type(kernel, "message.sent")[-1].data["delivery"] == "next-turn"
    assert ready(kernel)["agents"] == []
    assert of_type(kernel, "agent.ended")[-1].data["heard"] is True


async def test_a_parent_s_own_cancel_still_closes_its_join_and_that_wakes_it(kernel):
    lead = await parked_on(kernel, "a", "b")

    result_of(await kernel.submit(lead, "agent.cancel", {"agent": "a"}))
    result_of(await kernel.submit(lead, "agent.cancel", {"agent": "b"}))

    assert ready(kernel)["agents"] == []
    assert len(ready(kernel)["waits"]) == 1


async def test_an_interrupted_turn_says_so_and_waits_for_the_parent_s_next_turn(kernel, ada):
    lead = await spawn(kernel, "lead", role="lead", goal="")
    await spawn(kernel, "bob", by=lead, goal="")
    await start_turn(kernel, "bob")
    await report(kernel, "bob", "item", kind="message", gist="half a sentence, and then")

    await end_turn(kernel, "bob", "interrupted")

    sent = of_type(kernel, "message.sent")[-1]
    assert sent.gist == "bob turn interrupted: half a sentence, and then"
    assert sent.data["delivery"] == "next-turn"
    assert ready(kernel)["agents"] == []


async def test_a_turn_that_failed_says_so_and_wakes_the_parent(kernel):
    lead = await spawn(kernel, "lead", role="lead", goal="")
    await spawn(kernel, "bob", by=lead, goal="")
    await start_turn(kernel, "bob")

    await end_turn(kernel, "bob", "failed: out of memory")

    sent = of_type(kernel, "message.sent")[-1]
    assert sent.gist == "bob turn failed: out of memory"
    assert sent.data["delivery"] == "wake"


async def test_a_turn_cut_off_keeps_within_a_gist_whatever_it_said(kernel):
    lead = await spawn(kernel, "lead", role="lead", goal="")
    await spawn(kernel, "bob", by=lead, goal="")
    await start_turn(kernel, "bob")
    await report(kernel, "bob", "item", kind="message", gist="x" * 280)

    await end_turn(kernel, "bob", "interrupted")

    assert of_type(kernel, "message.sent")[-1].gist.startswith("bob turn interrupted: xxx")


async def test_a_counted_turn_that_failed_still_wakes_the_parent(kernel):
    await parked_on(kernel, "a", "b", **{"from": ["a", "b"]})

    await start_turn(kernel, "a")
    await end_turn(kernel, "a", "failed: boom")

    assert ready(kernel)["agents"] == ["lead"]


@pytest.mark.parametrize("limits", [{"max_hops": 1}])
async def test_the_monitor_stops_at_max_hops(kernel, limits):
    lead = await spawn(kernel, "lead", role="lead")
    bob = await spawn(kernel, "bob", by=lead)
    first = await send(kernel, lead, "@bob", "go")
    second = await send(kernel, bob, "@lead", "on", reply_to=first["ref"])
    third = await send(kernel, lead, "@bob", "on", reply_to=second["ref"])
    await start_turn(kernel, "bob")
    await read(kernel, bob, "@bob", after=0)
    head = kernel.head

    await end_turn(kernel, "bob")

    assert third["hops"] == 2
    assert of_type(kernel, "message.sent", after=head)[0].data["delivery"] == "next-turn"
    assert [event.data["why"] for event in of_type(kernel, "wake.refused", after=head)] == ["hops"]


# Peers and lists.


async def test_peers_lists_whom_you_may_reach_now(kernel):
    lead = await spawn(kernel, "lead", role="lead")
    await spawn(kernel, "w1", by=lead)
    outsider = await spawn(kernel, "outsider")
    await kernel.submit(kernel.runtime, "grant.remove", {"who": "agent", "ops": "*", "on": "*"})
    await grant(kernel, "agent", "peers")
    await grant(kernel, "role:lead", "message.send", "inbox/{children}")

    assert [peer["address"] for peer in result_of(kernel.query(lead, "peers", {}))["peers"]] == ["@w1"]
    assert result_of(kernel.query(outsider, "peers", {}))["peers"] == []


async def test_agent_list_shows_no_content(kernel):
    bob = await spawn(kernel, "bob")

    rows = result_of(kernel.query(bob, "agent.list", {}))

    assert [row["agent"] for row in rows] == ["bob"] and "goal" not in rows[0] and "activity" not in rows[0]


@pytest.mark.parametrize("spelling", ["bob", "@bob", "agent:bob"])
async def test_an_agent_has_one_address_and_takes_any_spelling(kernel, spelling):
    alice = await spawn(kernel, "alice")
    await spawn(kernel, "bob", by=alice)

    shown = result_of(kernel.query(alice, "agent.status", {"agent": spelling}))

    assert (shown["agent"], shown["parent"]) == ("bob", "alice")


async def test_agent_status_of_nobody_is_refused(kernel):
    assert refusal(kernel.query(kernel.runtime, "agent.status", {"agent": "ghost"})).code == "not_found"


# Completion.


def status(kernel) -> dict:
    return result_of(kernel.query(kernel.runtime, "session.status", {}))


async def test_settled_means_no_turn_no_delivery_no_effect_and_no_due_timer(kernel, clock):
    assert status(kernel)["settled"]

    await spawn(kernel, "bob", goal="")
    assert status(kernel)["settled"]


async def test_a_goal_not_begun_unsettles(kernel):
    await spawn(kernel, "bob", goal="do it")
    assert status(kernel)["blockers"] == ["starting_agent"]

    await start_turn(kernel, "bob")
    await end_turn(kernel, "bob")

    assert status(kernel)["settled"]


async def test_an_open_effect_unsettles(kernel):
    result_of(await kernel.submit(kernel.runtime, "agent.spawn", spawning("bob")))

    assert "open_effect" in status(kernel)["blockers"]


async def test_an_agent_on_its_way_to_a_turn_unsettles(kernel):
    result_of(await kernel.submit(kernel.runtime, "agent.spawn", spawning("bob")))
    await settle_effects(kernel, "bob")
    assert status(kernel)["blockers"] == ["starting_agent"]

    await start(kernel, "bob")
    await send(kernel, kernel.runtime, "@bob", "go")
    result_of(await kernel.submit(kernel.runtime, "delivery.offer", {"agent": "bob"}))
    await settle_effects(kernel, "bob")

    assert status(kernel)["blockers"] == ["starting_agent"]


async def test_a_coalesced_wake_unsettles_before_it_falls_due(kernel):
    await channel(kernel, "t", delivery="wake", coalesce=5.0)
    await grant(kernel, "agent")
    await spawn(kernel, "bob", goal="")

    result_of(await kernel.submit(kernel.runtime, "message.send", {"to": "#t", "gist": "soon"}))

    assert status(kernel)["blockers"] == ["deliverable_delivery"]


async def test_a_wait_with_a_deadline_to_come_does_not_unsettle(kernel):
    bob = await spawn(kernel, "bob", goal="")

    result_of(await kernel.submit(bob, "wait", {"on": [{"stream": "agent/ghost"}], "timeout": 60.0}))

    assert status(kernel)["settled"]


async def test_an_open_turn_unsettles(kernel):
    await spawn(kernel, "bob")

    await start_turn(kernel, "bob")

    assert status(kernel)["blockers"] == ["open_turn"]


async def test_a_due_timer_unsettles(kernel, clock):
    bob = await spawn(kernel, "bob", goal="")
    await channel(kernel, "work", kind="queue", lease=60.0)
    result_of(await kernel.submit(kernel.runtime, "task.add", {"queue": "work", "gist": "x"}))
    result_of(await kernel.submit(bob, "task.claim", {"queue": "work"}))
    assert status(kernel)["settled"]

    clock.advance(60)

    assert status(kernel)["blockers"] == ["due_timer"]


async def test_a_human_message_can_unsettle_a_session(kernel, ada):
    await spawn(kernel, "bob", goal="")
    assert status(kernel)["settled"]

    await send(kernel, ada, "@bob", "one more thing")

    assert status(kernel)["blockers"] == ["deliverable_delivery"]


async def test_a_wait_that_holds_keeps_the_session_unsettled(kernel):
    alice, bob = await spawn(kernel, "alice"), await spawn(kernel, "bob")
    await start_turn(kernel, "bob")
    result_of(await kernel.submit(bob, "wait", {"on": [{"stream": "agent/alice"}], "after": kernel.head}))
    await end_turn(kernel, "bob")
    await kernel.submit(alice, "agent.finish", {})
    await settle_effects(kernel)

    assert status(kernel)["blockers"] == ["deliverable_delivery"]


async def test_a_close_that_asks_is_refused_when_a_message_got_in_first(kernel, ada):
    await spawn(kernel, "bob", goal="")
    await send(kernel, ada, "@bob", "one more thing")

    assert refusal(await kernel.submit(ada, "session.close", {"if_done": True})).code == "conflict"
    assert status(kernel)["state"] == "open"


async def test_a_close_that_asks_closes_a_session_that_is_done(kernel, ada):
    await spawn(kernel, "bob", goal="")

    result_of(await kernel.submit(ada, "session.close", {"if_done": True}))

    assert status(kernel)["state"] == "closing"


async def test_a_message_is_refused_once_the_session_is_closing(kernel, ada):
    await spawn(kernel, "bob", goal="")
    result_of(await kernel.submit(ada, "session.close", {}))

    args = {"to": "@bob", "gist": "too late"}
    assert refusal(await kernel.submit(ada, "message.send", args)).code == "conflict"


async def test_only_close_ends_a_session(kernel, ada):
    assert status(kernel)["state"] == "open"

    result_of(await kernel.submit(ada, "session.close", {}))

    assert status(kernel)["state"] == "closing"
    assert refusal(await kernel.submit(ada, "session.close", {})).code == "conflict"


async def test_only_an_open_session_closes(tmp_path, clock):
    kernel = Kernel.open(tmp_path / "other", clock=clock, extensions=PRIMITIVES)

    assert refusal(await kernel.submit(kernel.runtime, "session.close", {})).code == "conflict"
    kernel.close()


async def test_session_cancel_stops_now(kernel, ada):
    lead = await spawn(kernel, "lead", role="lead")
    await spawn(kernel, "w1", role="linked", by=lead)
    await spawn(kernel, "w2")

    result_of(await kernel.submit(ada, "session.cancel", {}))

    assert status(kernel)["state"] == "cancelled"
    assert {event.agent for event in of_type(kernel, "agent.ended")} == {"lead", "w1", "w2"}
    assert refusal(await kernel.submit(ada, "session.cancel", {})).code == "conflict"


async def test_a_stopped_session_resumes(tmp_path, clock):
    folder = tmp_path / "session"
    kernel = Kernel.open(folder, clock=clock, extensions=PRIMITIVES)
    result_of(await kernel.submit(kernel.runtime, "session.open", {"roles": {"worker": {}}}))
    await spawn(kernel, "bob")
    result_of(await kernel.submit(kernel.runtime, "session.stop", {}))
    kernel.close()

    kernel = Kernel.open(folder, clock=clock, extensions=PRIMITIVES)
    await kernel.recover()
    await send(kernel, kernel.runtime, "@bob", "after resume")

    assert result_of(kernel.query(kernel.runtime, "delivery.ready", {}))["agents"] == ["bob"]
    kernel.close()


async def test_a_session_closing_when_it_stopped_still_closes(kernel, ada):
    result_of(await kernel.submit(ada, "session.close", {}))
    result_of(await kernel.submit(kernel.runtime, "session.stop", {}))

    await kernel.recover()

    assert status(kernel)["state"] == "closing"


async def test_session_stop_is_the_owners_to_write(kernel, ada):
    assert refusal(await kernel.submit(ada, "session.stop", {})).code == "not_permitted"

    result_of(await kernel.submit(kernel.runtime, "session.stop", {}))

    assert status(kernel)["state"] == "stopped"


async def test_until_settled_is_done_when_settled(kernel):
    assert status(kernel)["until"] == "settled" and status(kernel)["done"]


async def until_session(tmp_path, clock, until: str):
    kernel = Kernel.open(tmp_path / "other", clock=clock, extensions=PRIMITIVES)
    args = {"roles": {"lead": {}}, "until": until}
    result_of(await kernel.submit(kernel.runtime, "session.open", args))
    await grant(kernel, "agent")
    return kernel


async def test_until_role_is_done_when_that_role_has_ended(tmp_path, clock):
    kernel = await until_session(tmp_path, clock, "role:lead")
    assert not status(kernel)["done"]

    lead = await spawn(kernel, "lead", role="lead")
    assert not status(kernel)["done"]

    result_of(await kernel.submit(lead, "agent.finish", {}))
    assert status(kernel)["done"]
    kernel.close()


async def test_until_program_is_left_to_the_program(tmp_path, clock):
    kernel = await until_session(tmp_path, clock, "program")

    assert status(kernel)["settled"] and not status(kernel)["done"]
    kernel.close()


async def test_every_until_stops_at_budget_exhaustion(tmp_path, clock):
    kernel = await until_session(tmp_path, clock, "program")
    result_of(await kernel.submit(kernel.runtime, "budget.set", {"limits": {"wall": 60}}))

    clock.advance(60)

    assert status(kernel)["done"]
    kernel.close()


async def short_of_until(tmp_path, clock, until: str = "role:lead"):
    """A session whose lead has ended a turn and has not finished, so nothing but a human can bring it to `until`."""
    kernel = await until_session(tmp_path, clock, until)
    lead = await spawn(kernel, "lead", role="lead", goal="")
    await start_turn(kernel, "lead")
    await report(kernel, "lead", "item", kind="message", gist="I think we are done")
    await end_turn(kernel, "lead")
    return kernel, lead


async def test_a_session_settled_short_of_until_with_nothing_scheduled_has_stalled(tmp_path, clock):
    kernel, _ = await short_of_until(tmp_path, clock)

    assert status(kernel)["settled"] and not status(kernel)["done"]
    assert status(kernel)["stalled"]
    kernel.close()


async def test_a_session_that_reached_until_has_not_stalled(kernel):
    assert status(kernel)["done"] and not status(kernel)["stalled"]


async def test_a_session_with_work_under_way_has_not_stalled(tmp_path, clock):
    kernel, _ = await short_of_until(tmp_path, clock)
    await start_turn(kernel, "lead", "t2")

    assert not status(kernel)["settled"] and not status(kernel)["stalled"]
    kernel.close()


async def test_a_program_session_is_left_to_its_program_and_never_stalls(tmp_path, clock):
    kernel, _ = await short_of_until(tmp_path, clock, "program")

    assert not status(kernel)["stalled"]
    kernel.close()


async def test_a_lease_to_expire_can_still_move_a_session_so_it_has_not_stalled(tmp_path, clock):
    kernel, lead = await short_of_until(tmp_path, clock)
    await channel(kernel, "q", "queue")
    result_of(await kernel.submit(lead, "task.add", {"queue": "q", "gist": "do"}))
    result_of(await kernel.submit(lead, "task.claim", {"queue": "q"}))

    assert not status(kernel)["stalled"]
    kernel.close()


async def test_a_settled_task_leaves_no_lease_to_wait_for(tmp_path, clock):
    kernel, lead = await short_of_until(tmp_path, clock)
    await channel(kernel, "q", "queue")
    result_of(await kernel.submit(lead, "task.add", {"queue": "q", "gist": "do"}))
    result_of(await kernel.submit(lead, "task.claim", {"queue": "q"}))

    result_of(await kernel.submit(lead, "task.complete", {"queue": "q"}))

    assert status(kernel)["stalled"]
    kernel.close()


async def test_timers_of_leases_long_gone_hide_no_timer_to_come(tmp_path, clock):
    kernel, lead = await short_of_until(tmp_path, clock)
    await channel(kernel, "q", "queue")
    result_of(await kernel.submit(kernel.runtime, "budget.set", {"limits": {"wall": 100_000}}))
    for _ in range(70):
        result_of(await kernel.submit(lead, "task.add", {"queue": "q", "gist": "do"}))
        result_of(await kernel.submit(lead, "task.claim", {"queue": "q"}))
        result_of(await kernel.submit(lead, "task.complete", {"queue": "q"}))

    assert not status(kernel)["stalled"]
    kernel.close()


async def test_a_wall_limit_to_come_can_still_end_a_session_so_it_has_not_stalled(tmp_path, clock):
    kernel, _ = await short_of_until(tmp_path, clock)

    result_of(await kernel.submit(kernel.runtime, "budget.set", {"limits": {"wall": 60}}))

    assert not status(kernel)["stalled"]
    kernel.close()


async def test_a_wait_deadline_to_come_can_still_wake_an_agent_so_it_has_not_stalled(tmp_path, clock):
    kernel, lead = await short_of_until(tmp_path, clock)
    await start_turn(kernel, "lead", "t2")
    result_of(await kernel.submit(lead, "wait", {"from": ["nobody-yet"], "timeout": 60.0}))
    await end_turn(kernel, "lead")

    assert status(kernel)["settled"] and not status(kernel)["stalled"]
    kernel.close()


async def test_a_wake_the_budget_refused_is_not_settled_enough_to_close(kernel, ada):
    limits = {"limits": {"tokens": 10}, "estimate": {"tokens": 100}}
    result_of(await kernel.submit(kernel.runtime, "budget.set", limits))
    await spawn(kernel, "bob", goal="")
    await send(kernel, ada, "@bob", "go")
    result_of(await kernel.submit(kernel.runtime, "delivery.offer", {"agent": "bob"}))
    assert of_type(kernel, "wake.refused")[-1].data["why"] == "over_budget"

    assert status(kernel)["settled"] and not status(kernel)["done"]
    assert status(kernel)["stalled"]
    assert refusal(await kernel.submit(ada, "session.close", {"if_done": True})).code == "conflict"


async def test_a_spent_budget_is_done_whatever_it_refused(kernel, ada):
    result_of(await kernel.submit(kernel.runtime, "budget.set", {"limits": {"wall": 60}}))
    await spawn(kernel, "bob", goal="")
    await send(kernel, ada, "@bob", "go")
    kernel.clock.advance(60)
    result_of(await kernel.submit(kernel.runtime, "delivery.offer", {"agent": "bob"}))

    assert status(kernel)["done"] and not status(kernel)["stalled"]


async def test_session_open_is_once(kernel):
    assert refusal(await kernel.submit(kernel.runtime, "session.open", {})).code == "conflict"


async def test_session_manifest_names_the_stored_manifest(tmp_path, clock):
    kernel = Kernel.open(tmp_path / "other", clock=clock, extensions=PRIMITIVES)
    body = f"sha256:{await kernel.put_body(b'{}')}"
    result_of(await kernel.submit(kernel.runtime, "session.open", {"manifest": body}))

    assert result_of(kernel.query(kernel.runtime, "session.manifest", {})) == {"manifest": body}
    kernel.close()


# Episodes.


async def test_events_inside_an_episode_carry_it(kernel, ada):
    alice = await spawn(kernel, "alice")

    result_of(await kernel.submit(ada, "episode.open", {"episode": "e1"}))
    inside = await send(kernel, alice, "@alice", "in")
    result_of(await kernel.submit(ada, "episode.close", {"outcome": {"score": 1}}))
    outside = await send(kernel, alice, "@alice", "out")

    stamped = {event.seq: event.episode for event in of_type(kernel, "message.sent")}
    assert stamped[inside["seq"]] == "e1" and stamped[outside["seq"]] is None


async def test_a_session_has_one_open_episode(kernel, ada):
    result_of(await kernel.submit(ada, "episode.open", {"episode": "e1"}))

    assert refusal(await kernel.submit(ada, "episode.open", {"episode": "e2"})).code == "conflict"


async def test_closing_no_episode_is_refused(kernel, ada):
    assert refusal(await kernel.submit(ada, "episode.close", {})).code == "conflict"


async def test_a_blob_can_be_read(kernel):
    bob = await spawn(kernel, "bob")
    sha = await kernel.put_body(b"a stored thing")

    read_back = result_of(await kernel.submit(bob, "blob.get", {"ref": f"sha256:{sha}"}))

    assert read_back["text"] == "a stored thing"
    assert of_type(kernel, "context.offered")[-1].data["items"][0]["form"] == "body"


async def test_a_blob_that_was_never_stored_is_not_found(kernel):
    bob = await spawn(kernel, "bob")

    assert refusal(await kernel.submit(bob, "blob.get", {"ref": f"sha256:{'0' * 64}"})).code == "not_found"


async def test_a_blob_comes_back_cut_with_a_ref_to_the_rest(kernel):
    bob = await spawn(kernel, "bob")
    sha = await kernel.put_body(b"a line of a long body\n" * 2000)

    first = result_of(await kernel.submit(bob, "blob.get", {"ref": f"sha256:{sha}"}))
    last = int(first["ref"].rpartition("-")[2])

    assert first["ref"].startswith(f"sha256:{sha}#L1-")
    assert first["lines"] == 2000
    assert first["rest"] == f"sha256:{sha}#L{last + 1}-2000"
    assert result_of(await kernel.submit(bob, "blob.get", {"ref": first["rest"]}))["rest"] is not None


async def test_the_exposure_of_a_cut_blob_names_the_lines_shown(kernel):
    bob = await spawn(kernel, "bob")
    sha = await kernel.put_body(b"one\ntwo\nthree\n")

    result_of(await kernel.submit(bob, "blob.get", {"ref": f"sha256:{sha}#L2-2"}))

    assert of_type(kernel, "context.offered")[-1].data["items"][0]["ref"] == f"sha256:{sha}#L2-2"


async def test_a_blob_range_past_the_end_says_how_many_lines_there_are(kernel):
    bob = await spawn(kernel, "bob")
    sha = await kernel.put_body(b"one\ntwo\n")

    assert refusal(await kernel.submit(bob, "blob.get", {"ref": f"sha256:{sha}#L9-10"})).detail["lines"] == 2


async def test_an_empty_blob_is_text(kernel):
    bob = await spawn(kernel, "bob")
    sha = await kernel.put_body(b"")

    assert result_of(await kernel.submit(bob, "blob.get", {"ref": f"sha256:{sha}"}))["text"] == ""


async def test_a_blob_held_outside_the_journal_comes_back_for_a_surface_to_fetch(kernel):
    bob = await spawn(kernel, "bob")
    sha = await kernel.put_body(b"x" * (70 * 1024))
    head = kernel.head

    assert result_of(await kernel.submit(bob, "blob.get", {"ref": f"sha256:{sha}"})) == {
        "ref": f"sha256:{sha}",
        "text": None,
    }
    assert of_type(kernel, "context.offered", after=head) == []


async def test_a_surface_records_what_it_showed_of_a_body(kernel):
    await spawn(kernel, "bob")
    sha = await kernel.put_body(b"x" * (70 * 1024))
    offer = {"agent": "bob", "ref": f"sha256:{sha}#L1-3", "digest": "0" * 64}

    result_of(await kernel.submit(kernel.runtime, "blob.offer", offer))

    offered = of_type(kernel, "context.offered")[-1]
    assert offered.data["how"] == "read"
    assert offered.data["items"] == [{"ref": offer["ref"], "form": "body", "digest": offer["digest"]}]


async def test_only_the_runtime_records_what_a_surface_showed(kernel):
    bob = await spawn(kernel, "bob")
    offer = {"agent": "bob", "ref": f"sha256:{'0' * 64}", "digest": "0" * 64}

    assert refusal(await kernel.submit(bob, "blob.offer", offer)).code == "not_permitted"


async def test_agent_status_names_the_open_turn(kernel):
    await spawn(kernel, "bob")
    assert result_of(kernel.query(kernel.runtime, "agent.status", {"agent": "bob"}))["turn"] is None

    await start_turn(kernel, "bob", "t7")

    assert result_of(kernel.query(kernel.runtime, "agent.status", {"agent": "bob"}))["turn"] == "t7"


async def test_a_blob_too_long_for_a_result_comes_back_without_text(kernel):
    bob = await spawn(kernel, "bob")
    sha = await kernel.put_body(b"x" * (20 * 1024))

    assert result_of(await kernel.submit(bob, "blob.get", {"ref": f"sha256:{sha}"}))["text"] is None


async def test_a_program_principal_may_spawn_with_itself_as_parent(kernel):
    program = Principal(id="program:driver")
    await enroll(kernel, program)
    await grant(kernel, "program")

    result_of(await kernel.submit(program, "agent.spawn", spawning("w1")))

    assert state_of(kernel, "w1")["parent"] == "driver"


async def test_a_spawned_agent_is_a_principal_at_once_with_no_credential(kernel):
    lead = await spawn(kernel, "lead", role="lead")
    result_of(await kernel.submit(lead, "agent.spawn", spawning("w1")))

    assert any(peer["address"] == "@w1" for peer in result_of(kernel.query(lead, "peers", {}))["peers"])
    with pytest.raises(Refused):
        kernel.authenticate("tok")

    token = {"id": "agent:w1", "token_hash": hash_token("tok")}
    result_of(await kernel.submit(kernel.runtime, "principal.issue", token))

    assert kernel.authenticate("tok").parent == lead.id


async def test_an_agent_ended_before_launch_gets_no_credential(kernel, ada):
    result_of(await kernel.submit(kernel.runtime, "agent.spawn", spawning("w1")))
    result_of(await kernel.submit(ada, "agent.cancel", {"agent": "w1"}))

    token = {"id": "agent:w1", "token_hash": hash_token("tok")}

    assert refusal(await kernel.submit(kernel.runtime, "principal.issue", token)).code == "conflict"
    assert refusal(await kernel.submit(kernel.runtime, "principal.add", {"id": "agent:w1"})).code == "conflict"


async def test_an_agent_cannot_take_a_name_of_another_kind(kernel, ada):
    outcome = await kernel.submit(kernel.runtime, "agent.spawn", spawning("ada"))

    assert refusal(outcome).code == "conflict"


async def test_a_name_that_is_no_safe_path_part_is_refused(kernel):
    for name in ("..", ".", "-rf", "--help", "w\u0430"):
        assert refusal(await kernel.submit(kernel.runtime, "agent.spawn", spawning(name))).code == "invalid"


async def test_an_adopted_orphan_leaves_its_old_ancestors_reach(kernel, ada):
    lead = await spawn(kernel, "lead", role="lead")
    middle = await spawn(kernel, "middle", role="linked", by=lead)
    orphan = await spawn(kernel, "orphan", role="worker", by=middle)
    await spawn(kernel, "below", role="worker", by=orphan)
    await kernel.submit(kernel.runtime, "grant.remove", {"who": "agent", "ops": "*", "on": "*"})
    await grant(kernel, "agent", "agent.status", "agent/{descendants}")

    result_of(await kernel.submit(ada, "agent.cancel", {"agent": "middle"}))

    assert refusal(kernel.query(lead, "agent.status", {"agent": "orphan"})).code == "not_permitted"
    assert refusal(kernel.query(lead, "agent.status", {"agent": "below"})).code == "not_permitted"
    assert result_of(kernel.query(orphan, "agent.status", {"agent": "below"}))["parent"] == "orphan"


# What a host needs from the record.


async def test_an_agent_with_no_goal_holds_no_turn(kernel):
    args = {"name": "bob", "child_role": "worker"}

    result_of(await kernel.submit(kernel.runtime, "agent.spawn", args))

    assert of_type(kernel, "budget.reserved")[-1].data["amounts"] == {"agents": 1.0}


async def test_a_body_is_a_goal_enough_to_hold_a_turn(kernel):
    body = f"sha256:{await kernel.put_body(b'all of it')}"

    result_of(await kernel.submit(kernel.runtime, "agent.spawn", {"name": "bob", "child_role": "worker", "body": body}))

    assert of_type(kernel, "budget.reserved")[-1].data["amounts"]["turns"] == 1.0


@pytest.mark.parametrize(
    ("reason", "status", "said"),
    [("stopped", "finished", None), ("exited with code 1", "failed", "exited with code 1")],
)
async def test_a_one_shot_agent_ends_with_its_turn(kernel, reason, status, said):
    await spawn(kernel, "bob", ready={"persistent": False})
    await start_turn(kernel, "bob")

    await end_turn(kernel, "bob", reason)

    ended = of_type(kernel, "agent.ended")[-1].data
    assert (ended["status"], ended["reason"]) == (status, said)
    assert state_of(kernel, "bob")["turn"] is None


async def test_a_one_shot_agent_s_end_tells_its_parent_once(kernel):
    alice = await spawn(kernel, "alice", role="lead")
    await grant(kernel, "agent:alice", ops="agent.spawn")
    await spawn(kernel, "bob", by=alice, ready={"persistent": False})
    await start_turn(kernel, "bob")
    await report(kernel, "bob", "item", kind="message", gist="all done")

    await end_turn(kernel, "bob")

    assert [event.gist for event in of_type(kernel, "message.sent")] == ["all done"]


async def test_a_one_shot_that_exits_in_its_turn_is_lost(kernel):
    await spawn(kernel, "bob", ready={"persistent": False})
    await start_turn(kernel, "bob")

    await report(kernel, "bob", "exited")

    assert of_type(kernel, "agent.ended")[-1].data["status"] == "lost"


async def test_a_persistent_harness_that_exits_is_lost(kernel):
    await spawn(kernel, "bob")

    await report(kernel, "bob", "exited")

    assert of_type(kernel, "agent.ended")[-1].data["status"] == "lost"


async def test_a_resumed_harness_comes_back_to_the_agent_as_it_stood(kernel):
    await spawn(kernel, "bob")
    await start_turn(kernel, "bob")
    args = {"agent": "bob", "ready": {"native": "s-2", "version": "2"}, "declared": {"resume": True}, "resumed": True}

    result_of(await kernel.submit(kernel.runtime, "agent.start", args))

    record = next(row for row in result_of(kernel.query(kernel.runtime, "agent.records", {})) if row["name"] == "bob")
    assert (record["state"], record["native"], record["resume"], record["turn"]) == ("running", "s-2", True, "t1")
    assert of_type(kernel, "agent.resumed")[-1].data["version"] == "2"


async def test_only_a_harness_that_started_can_resume(kernel):
    result_of(await kernel.submit(kernel.runtime, "agent.spawn", {"name": "bob", "child_role": "worker"}))
    args = {"agent": "bob", "ready": {}, "declared": {}, "resumed": True}

    assert refusal(await kernel.submit(kernel.runtime, "agent.start", args)).code == "conflict"


async def test_a_session_named_only_by_start_reaches_the_record_through_the_launch(kernel):
    result_of(await kernel.submit(kernel.runtime, "agent.spawn", {"name": "bob", "child_role": "worker"}))
    while effects := result_of(kernel.query(kernel.runtime, "effect.ready", {})):
        for effect in effects:
            attempt = result_of(await kernel.submit(kernel.runtime, "effect.start", {"id": effect["id"]}))
            result = {"native": "s-9"} if effect["kind"] == "launch" else None
            done = {"id": effect["id"], "attempt": attempt, "result": result}
            result_of(await kernel.submit(kernel.runtime, "effect.finish", done))
    await start(kernel, "bob")

    assert result_of(kernel.query(kernel.runtime, "agent.records", {}))[0]["native"] == "s-9"


# What a session came to.


async def ending(kernel: Kernel) -> dict:
    return result_of(kernel.query(kernel.runtime, "session.ending", {}))


async def test_an_ending_says_why_with_each_agent_and_what_was_measured(kernel):
    await spawn(kernel, "bob")
    await start_turn(kernel, "bob")
    await report(kernel, "bob", "usage", tokens=120, label="estimated")
    await end_turn(kernel, "bob")

    found = await ending(kernel)

    assert found["reason"] == "settled"
    assert found["usage"]["tokens"] == {"amount": 120.0, "label": "estimated"}
    assert [(row["agent"], row["role"], row["state"]) for row in found["agents"]] == [("bob", "worker", "idle")]
    assert found["agents"][0]["usage"]["tokens"]["amount"] == 120.0


@pytest.mark.parametrize("how", ["exited", "spawn"])
async def test_an_agent_that_failed_or_was_lost_is_what_an_ending_says(kernel, how):
    if how == "exited":
        await spawn(kernel, "bob")
        await report(kernel, "bob", "exited")
    else:
        result_of(await kernel.submit(kernel.runtime, "agent.spawn", {"name": "bob", "child_role": "worker"}))
        await report(kernel, "bob", "exited")

    assert (await ending(kernel))["reason"] == "agent_failed"


async def test_exhausting_the_budget_outranks_a_failed_agent(kernel):
    await spawn(kernel, "bob")
    await kernel.submit(kernel.runtime, "budget.set", {"limits": {"tokens": 10}})
    await start_turn(kernel, "bob")
    await report(kernel, "bob", "usage", tokens=120, label="provider")
    await report(kernel, "bob", "exited")

    assert (await ending(kernel))["reason"] == "budget_exhausted"


async def test_cancelling_outranks_everything(kernel):
    await spawn(kernel, "bob")
    await kernel.submit(kernel.runtime, "session.cancel", {})

    found = await ending(kernel)

    assert (found["state"], found["reason"]) == ("cancelled", "cancelled")


async def test_gaps_are_counted_by_agent_and_kind_and_a_lost_turn_is_one(kernel):
    await spawn(kernel, "bob")
    await report(kernel, "bob", "gap", plane="model", what="hidden_call")
    await report(kernel, "bob", "gap", plane="model", what="hidden_call")
    await start_turn(kernel, "bob")

    await kernel.recover()

    assert (await ending(kernel))["gaps"] == [
        {"agent": "bob", "what": "crash_window", "plane": "control", "count": 1},
        {"agent": "bob", "what": "hidden_call", "plane": "model", "count": 2},
    ]


async def test_a_harness_that_exits_in_a_turn_leaves_a_gap_and_one_between_turns_does_not(kernel):
    await spawn(kernel, "bob")
    await spawn(kernel, "ann")
    await start_turn(kernel, "bob")

    await report(kernel, "bob", "exited", reason="killed by signal 9")
    await report(kernel, "ann", "exited", reason="killed by signal 9")

    assert (await ending(kernel))["gaps"] == [{"agent": "bob", "what": "crash_window", "plane": "control", "count": 1}]


async def test_status_counts_what_is_left_to_a_human(kernel):
    await spawn(kernel, "bob")
    await report(kernel, "bob", "approval.requested", id="a1", gist="may I")

    assert result_of(kernel.query(kernel.runtime, "session.status", {}))["asking"] == 1


async def test_the_ending_holds_what_each_agent_said_last(kernel):
    await spawn(kernel, "bob")
    await spawn(kernel, "eve", goal="")
    body = f"sha256:{await kernel.put_body(b'the whole answer')}"
    await start_turn(kernel, "bob")
    await report(kernel, "bob", "item", kind="message", gist="the answer", body=body)
    await end_turn(kernel, "bob")

    ending = result_of(kernel.query(kernel.runtime, "session.ending", {}))

    assert {row["agent"]: row["report"] for row in ending["agents"]} == {
        "bob": {"gist": "the answer", "body": body},
        "eve": None,
    }


async def test_the_ending_holds_a_finished_agent_s_report(kernel):
    bob = await spawn(kernel, "bob")

    result_of(await kernel.submit(bob, "agent.finish", {"gist": "shipped"}))

    rows = result_of(kernel.query(kernel.runtime, "session.ending", {}))["agents"]
    assert rows[0]["report"] == {"gist": "shipped", "body": None}


async def test_a_lost_agent_keeps_what_it_said_and_not_how_it_ended(kernel):
    await spawn(kernel, "bob")
    await start_turn(kernel, "bob")
    await report(kernel, "bob", "item", kind="message", gist="so far")
    await report(kernel, "bob", "exited", reason="it fell over")

    rows = result_of(kernel.query(kernel.runtime, "session.ending", {}))["agents"]

    assert rows[0]["report"] == {"gist": "so far", "body": None}


# What holds off a stall.


def stalled(kernel: Kernel) -> bool:
    return result_of(kernel.query(kernel.runtime, "session.status", {}))["stalled"]


@pytest.mark.parametrize("wait", [{"from": ["b"]}, {"agents": ["b"]}])
async def test_a_wait_on_someone_still_here_keeps_a_settled_session_from_done(kernel, wait):
    a = await spawn(kernel, "a", goal="")
    await spawn(kernel, "b", goal="")
    await start_turn(kernel, "a")
    result_of(await kernel.submit(a, "wait", wait))
    await end_turn(kernel, "a")

    assert stalled(kernel)


async def test_a_wait_on_someone_gone_leaves_a_settled_session_done(kernel):
    a = await spawn(kernel, "a", goal="")
    await spawn(kernel, "b", goal="")
    await start_turn(kernel, "a")
    result_of(await kernel.submit(a, "wait", {"from": ["b"]}))
    await end_turn(kernel, "a")

    result_of(await kernel.submit(kernel.runtime, "agent.cancel", {"agent": "b"}))
    await settle_effects(kernel)

    assert result_of(kernel.query(kernel.runtime, "session.status", {}))["done"]


async def test_a_wait_s_timeout_is_waited_for_before_a_settled_session_stalls(kernel):
    a = await spawn(kernel, "a", goal="")
    await spawn(kernel, "b", goal="")
    await start_turn(kernel, "a")
    result_of(await kernel.submit(a, "wait", {"from": ["b"], "timeout": 60.0}))
    await end_turn(kernel, "a")

    assert not stalled(kernel)
