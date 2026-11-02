"""Lifecycle and completion: spawn, the one ended transition, the monitor, and what `settled` means."""

import pytest

from platoon_harness.kernel import Kernel, Principal, Refused, hash_token
from platoon_harness.primitives import PRIMITIVES

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


async def test_ready_twice_is_refused(kernel):
    await spawn(kernel, "bob")
    args = {"agent": "bob", "report": {"type": "ready"}}

    assert refusal(await kernel.submit(kernel.runtime, "agent.report", args)).code == "conflict"


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
    assert result_of(kernel.query(kernel.runtime, "delivery.ready", {}))["stranded"] == ["bob"]


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


async def test_a_late_turn_end_after_finish_changes_nothing(kernel):
    bob = await spawn(kernel, "bob")
    await start_turn(kernel, "bob")
    result_of(await kernel.submit(bob, "agent.finish", {}))
    head = kernel.head

    await end_turn(kernel, "bob")

    assert of_type(kernel, "turn.ended", after=head) == []


async def test_retiring_removes_an_agent_from_relations_never_from_history(kernel):
    lead = await spawn(kernel, "lead", role="lead")
    await spawn(kernel, "w1", by=lead)
    await spawn(kernel, "w2", by=lead)
    result_of(await kernel.submit(lead, "agent.retire", {"agent": "w1"}))

    await kernel.submit(kernel.runtime, "grant.remove", {"who": "agent", "ops": "*", "on": "*"})
    await grant(kernel, "role:lead", "message.send", "inbox/{children}")
    await grant(kernel, "role:lead", "peers")

    assert [peer["address"] for peer in result_of(kernel.query(lead, "peers", {}))] == ["@w2"]
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

    assert [peer["address"] for peer in result_of(kernel.query(lead, "peers", {}))] == ["@w1"]
    assert result_of(kernel.query(outsider, "peers", {})) == []


async def test_agent_list_shows_no_content(kernel):
    bob = await spawn(kernel, "bob")

    rows = result_of(kernel.query(bob, "agent.list", {}))

    assert [row["name"] for row in rows] == ["@bob"] and "goal" not in rows[0] and "activity" not in rows[0]


async def test_agent_status_of_nobody_is_refused(kernel):
    assert refusal(kernel.query(kernel.runtime, "agent.status", {"agent": "ghost"})).code == "not_found"


# Completion.


def status(kernel) -> dict:
    return result_of(kernel.query(kernel.runtime, "session.status", {}))


async def test_settled_means_no_turn_no_delivery_no_effect_and_no_due_timer(kernel, clock):
    assert status(kernel)["settled"]

    await spawn(kernel, "bob")
    assert status(kernel)["settled"]


async def test_an_open_effect_unsettles(kernel):
    result_of(await kernel.submit(kernel.runtime, "agent.spawn", spawning("bob")))

    assert "open_effect" in status(kernel)["blockers"]


async def test_an_agent_on_its_way_to_a_turn_unsettles(kernel):
    result_of(await kernel.submit(kernel.runtime, "agent.spawn", spawning("bob")))
    await settle_effects(kernel, "bob")
    assert status(kernel)["blockers"] == ["starting_agent"]

    await report(kernel, "bob", "ready")
    await send(kernel, kernel.runtime, "@bob", "go")
    result_of(await kernel.submit(kernel.runtime, "delivery.offer", {"agent": "bob"}))
    await settle_effects(kernel, "bob")

    assert status(kernel)["blockers"] == ["starting_agent"]


async def test_a_coalesced_wake_unsettles_before_it_falls_due(kernel):
    await channel(kernel, "t", delivery="wake", coalesce=5.0)
    await grant(kernel, "agent")
    await spawn(kernel, "bob")

    result_of(await kernel.submit(kernel.runtime, "message.send", {"to": "#t", "gist": "soon"}))

    assert status(kernel)["blockers"] == ["deliverable_delivery"]


async def test_a_wait_with_a_deadline_to_come_does_not_unsettle(kernel):
    bob = await spawn(kernel, "bob")

    result_of(await kernel.submit(bob, "wait", {"on": [{"stream": "agent/ghost"}], "timeout": 60.0}))

    assert status(kernel)["settled"]


async def test_an_open_turn_unsettles(kernel):
    await spawn(kernel, "bob")

    await start_turn(kernel, "bob")

    assert status(kernel)["blockers"] == ["open_turn"]


async def test_a_due_timer_unsettles(kernel, clock):
    bob = await spawn(kernel, "bob")
    await channel(kernel, "work", kind="queue", lease=60.0)
    result_of(await kernel.submit(kernel.runtime, "task.add", {"queue": "work", "gist": "x"}))
    result_of(await kernel.submit(bob, "task.claim", {"queue": "work"}))
    assert status(kernel)["settled"]

    clock.advance(60)

    assert status(kernel)["blockers"] == ["due_timer"]


async def test_a_human_message_can_unsettle_a_session(kernel, ada):
    await spawn(kernel, "bob")
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


async def test_a_blob_can_be_cited_and_read(kernel):
    bob = await spawn(kernel, "bob")
    sha = await kernel.put_body(b"a stored thing")

    assert result_of(await kernel.submit(bob, "blob.put", {"sha256": sha})) == {"ref": f"sha256:{sha}"}
    read_back = result_of(await kernel.submit(bob, "blob.get", {"sha256": sha}))

    assert read_back["text"] == "a stored thing"
    assert of_type(kernel, "context.offered")[-1].data["items"][0]["form"] == "body"


async def test_a_blob_that_was_never_stored_is_not_found(kernel):
    bob = await spawn(kernel, "bob")

    assert refusal(await kernel.submit(bob, "blob.put", {"sha256": "0" * 64})).code == "not_found"


async def test_a_program_principal_may_spawn_with_itself_as_parent(kernel):
    program = Principal(id="program:driver")
    await enroll(kernel, program)
    await grant(kernel, "program")

    result_of(await kernel.submit(program, "agent.spawn", spawning("w1")))

    assert state_of(kernel, "w1")["parent"] == "@driver"


async def test_a_spawned_agent_is_a_principal_at_once_with_no_credential(kernel):
    lead = await spawn(kernel, "lead", role="lead")
    result_of(await kernel.submit(lead, "agent.spawn", spawning("w1")))

    assert any(peer["address"] == "@w1" for peer in result_of(kernel.query(lead, "peers", {})))
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
    assert result_of(kernel.query(orphan, "agent.status", {"agent": "below"}))["parent"] == "@orphan"
