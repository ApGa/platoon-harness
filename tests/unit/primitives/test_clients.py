"""What clients render: typed `why`, actions as op references, and `view.watch`."""

import pytest

from platoon_harness.primitives import clients

from .support import channel, end_turn, refusal, report, result_of, send, spawn, start_turn


def roster(kernel, name: str) -> dict:
    rows = result_of(kernel.query(kernel.runtime, "view.watch", {"name": "roster"}))["rows"]
    return next(row for row in rows if row["agent"] == name)


def why(kernel, name: str) -> dict | None:
    return roster(kernel, name)["why"]


async def started_effect(kernel) -> dict:
    """Wake bob and start delivering, so that one effect is in flight."""
    await send(kernel, kernel.runtime, "@bob", "go")
    result_of(await kernel.submit(kernel.runtime, "delivery.offer", {"agent": "bob"}))
    effect = result_of(kernel.query(kernel.runtime, "effect.ready", {"kind": "deliver"}))[0]
    return {
        "id": effect["id"],
        "attempt": result_of(await kernel.submit(kernel.runtime, "effect.start", {"id": effect["id"]})),
    }


async def test_a_roster_row_answers_who_is_working_on_what(kernel):
    bob = await spawn(kernel, "bob", ready={"levels": {"operational": True}})
    await start_turn(kernel, "bob")
    await report(kernel, "bob", "item", kind="tool", gist="running tests")

    row = roster(kernel, "bob")

    assert (row["role"], row["harness"], row["model"], row["state"]) == ("worker", "codex", "m", "running")
    assert row["activity"] == "running tests" and row["levels"] == {"operational": True}
    assert row["unread"] == 0 and row["why"] is None
    assert bob.id == "agent:bob"


async def test_roster_counts_unread(kernel):
    alice = await spawn(kernel, "alice")
    await spawn(kernel, "bob")
    await send(kernel, alice, "@bob", "one")
    await send(kernel, alice, "@bob", "two")

    assert roster(kernel, "bob")["unread"] == 2


async def test_roster_shows_usage_with_its_label(kernel):
    await spawn(kernel, "bob")
    await send(kernel, kernel.runtime, "@bob", "go")
    result_of(await kernel.submit(kernel.runtime, "delivery.offer", {"agent": "bob"}))
    await start_turn(kernel, "bob")
    await report(kernel, "bob", "usage", tokens=10, label="provider")
    await end_turn(kernel, "bob")

    assert roster(kernel, "bob")["usage"]["tokens"] == {"amount": 10, "label": "provider"}


async def test_why_is_an_approval(kernel):
    await spawn(kernel, "bob")
    await kernel.submit(kernel.runtime, "approval.request", {"id": "a1", "agent": "bob", "gist": "may I"})

    assert why(kernel, "bob") == {"kind": "approval", "id": "a1"}


async def test_why_is_a_wait_with_have_need_and_missing(kernel):
    alice, bob = await spawn(kernel, "alice"), await spawn(kernel, "bob")
    await channel(kernel, "barrier")
    await start_turn(kernel, "bob")
    n = ["agent:alice", "agent:carol", "agent:w7"]
    args = {"on": [{"stream": "channel/barrier", "n": n, "distinct": "actor"}]}
    result_of(await kernel.submit(bob, "wait", args))
    await end_turn(kernel, "bob")
    await send(kernel, alice, "#barrier", "here")

    assert why(kernel, "bob") == {"kind": "wait", "have": 1, "need": 3, "missing": ["agent:carol", "agent:w7"]}


async def test_why_is_a_peer_when_one_agent_is_all_that_is_missing(kernel):
    bob = await spawn(kernel, "bob")
    await spawn(kernel, "carol")
    await start_turn(kernel, "bob")
    args = {"on": [{"stream": "agent/carol", "types": ["agent.ended"]}]}
    result_of(await kernel.submit(bob, "wait", args))
    await end_turn(kernel, "bob")

    assert why(kernel, "bob") == {"kind": "peer", "id": "carol"}


async def test_why_is_a_budget_when_a_wake_was_refused(kernel):
    await spawn(kernel, "bob")
    result_of(await kernel.submit(kernel.runtime, "budget.set", {"limits": {"tokens": 10}, "estimate": {"tokens": 99}}))
    await send(kernel, kernel.runtime, "@bob", "go")
    await kernel.submit(kernel.runtime, "delivery.offer", {"agent": "bob"})

    assert why(kernel, "bob") == {"kind": "budget", "code": "over_budget"}


async def test_why_is_a_lease_when_an_idle_agent_still_holds_work(kernel):
    bob = await spawn(kernel, "bob")
    await channel(kernel, "work", kind="queue")
    await kernel.submit(kernel.runtime, "task.add", {"queue": "work", "gist": "x"})
    result_of(await kernel.submit(bob, "task.claim", {"queue": "work"}))

    assert why(kernel, "bob") == {"kind": "lease", "id": "task/work/1"}


async def test_why_is_a_timer_while_a_wake_coalesces(kernel):
    alice = await spawn(kernel, "alice")
    await spawn(kernel, "bob")
    await channel(kernel, "burst", delivery="wake", coalesce=30.0)
    await send(kernel, alice, "#burst", "one")

    assert why(kernel, "bob") == {"kind": "timer", "at": 1030.0}


async def test_why_is_infra_when_an_effect_is_uncertain(kernel):
    await spawn(kernel, "bob")
    await started_effect(kernel)

    await kernel.recover()

    assert why(kernel, "bob") == {"kind": "infra", "detail": "deliver is uncertain"}


async def test_why_is_lost_with_the_reason(kernel):
    await spawn(kernel, "bob")
    await report(kernel, "bob", "exited", reason="the harness crashed")

    assert why(kernel, "bob") == {"kind": "lost", "reason": "the harness crashed"}


async def test_attention_holds_a_mention_until_it_is_answered(kernel, ada):
    alice = await spawn(kernel, "alice")
    sent = await send(kernel, alice, "@ada", "got a minute?")
    assert [row["kind"] for row in result_of(kernel.query(ada, "attention.list", {}))] == ["mention"]

    await send(kernel, ada, "@alice", "yes", reply_to=sent["ref"])

    assert result_of(kernel.query(ada, "attention.list", {})) == []


async def test_attention_shows_an_uncertain_effect_until_it_settles(kernel, ada):
    await spawn(kernel, "bob")
    args = await started_effect(kernel)
    await kernel.recover()
    assert [row["kind"] for row in result_of(kernel.query(ada, "attention.list", {}))] == ["uncertain"]

    result_of(await kernel.submit(kernel.runtime, "effect.finish", args))

    assert result_of(kernel.query(ada, "attention.list", {})) == []


async def test_attention_shows_a_failed_effect(kernel, ada):
    await spawn(kernel, "bob")
    args = await started_effect(kernel)

    result_of(await kernel.submit(kernel.runtime, "effect.fail", {**args, "error": "the pipe broke"}))

    assert [row["kind"] for row in result_of(kernel.query(ada, "attention.list", {}))] == ["failed"]


async def test_a_failed_handover_leaves_attention_when_the_agent_recovers(kernel, ada):
    await spawn(kernel, "bob")
    args = await started_effect(kernel)
    result_of(await kernel.submit(kernel.runtime, "effect.fail", {**args, "error": "the pipe broke"}))

    await start_turn(kernel, "bob")

    assert result_of(kernel.query(ada, "attention.list", {})) == []


async def test_an_ended_agent_leaves_nothing_in_attention(kernel, ada):
    await spawn(kernel, "bob")
    args = await started_effect(kernel)
    result_of(await kernel.submit(kernel.runtime, "effect.fail", {**args, "error": "the pipe broke"}))

    result_of(await kernel.submit(ada, "agent.cancel", {"agent": "bob"}))

    assert result_of(kernel.query(ada, "attention.list", {})) == []


async def test_a_mention_outlives_its_sender(kernel, ada):
    bob = await spawn(kernel, "bob")
    await send(kernel, bob, "@ada", "please look")

    result_of(await kernel.submit(bob, "agent.finish", {"gist": "done"}))

    assert "mention" in [row["kind"] for row in result_of(kernel.query(ada, "attention.list", {}))]


async def test_a_childs_report_to_a_human_stays_in_attention(kernel, ada):
    bob = await spawn(kernel, "bob", by=ada)

    result_of(await kernel.submit(bob, "agent.finish", {"gist": "here is the result"}))

    rows = result_of(kernel.query(ada, "attention.list", {}))
    assert [(row["kind"], row["gist"]) for row in rows] == [("mention", "here is the result")]


async def test_a_dead_task_stays_in_attention_after_its_last_worker_ends(kernel, ada):
    await channel(kernel, "q", kind="queue", max_attempts=1)
    bob = await spawn(kernel, "bob")
    result_of(await kernel.submit(kernel.runtime, "task.add", {"queue": "q", "gist": "x"}))
    result_of(await kernel.submit(bob, "task.claim", {"queue": "q"}))
    result_of(await kernel.submit(bob, "task.fail", {"queue": "q"}))

    result_of(await kernel.submit(ada, "agent.cancel", {"agent": "bob"}))

    assert [row["kind"] for row in result_of(kernel.query(ada, "attention.list", {}))] == ["dead_task"]


async def test_watching_is_a_query_that_writes_nothing(kernel, ada):
    await spawn(kernel, "bob")
    head = kernel.head

    outcome = kernel.query(ada, "view.watch", {"name": "roster"})

    assert outcome.seq is None and kernel.head == head


async def test_watch_is_a_snapshot_then_keyed_changes(kernel):
    await spawn(kernel, "alice")
    await spawn(kernel, "bob")
    first = result_of(kernel.query(kernel.runtime, "view.watch", {"name": "roster"}))
    assert first["snapshot"] and [row["agent"] for row in first["rows"]] == ["alice", "bob"]

    await report(kernel, "alice", "item", kind="tool", gist="working")
    next_page = result_of(kernel.query(kernel.runtime, "view.watch", {"name": "roster", "after": first["cursor"]}))

    assert not next_page["snapshot"]
    assert [(row["agent"], row["activity"]) for row in next_page["rows"]] == [("alice", "working")]
    assert next_page["cursor"] == kernel.head


async def test_watch_says_when_a_key_went_away(kernel, ada):
    await spawn(kernel, "bob")
    await kernel.submit(kernel.runtime, "approval.request", {"id": "a1", "agent": "bob", "gist": "may I"})
    first = result_of(kernel.query(ada, "view.watch", {"name": "attention"}))
    assert [row["id"] for row in first["rows"]] == ["approval/a1"]

    action = first["rows"][0]["actions"][0]
    result_of(await kernel.submit(ada, action["op"], action["args"]))
    second = result_of(kernel.query(ada, "view.watch", {"name": "attention", "after": first["cursor"]}))

    assert second["rows"] == [] and second["removed"] == ["approval/a1"]


async def test_changes_come_from_the_runtime_probe_with_absence_kept_honest(kernel):
    await spawn(kernel, "bob")
    await report(kernel, "bob", "changes", path="src/app.py", added=3, removed=1, tests="passed")
    await report(kernel, "bob", "changes", path="opaque.bin")

    rows = result_of(kernel.query(kernel.runtime, "view.watch", {"name": "changes"}))["rows"]

    assert [(row["agent"], row["path"], row["added"]) for row in rows] == [
        ("bob", "src/app.py", 3),
        ("bob", "opaque.bin", None),
    ]


async def test_changes_since_a_mark(kernel):
    await spawn(kernel, "bob")
    await report(kernel, "bob", "changes", path="a.py", added=1, removed=0)
    mark = kernel.head
    await report(kernel, "bob", "changes", path="b.py", added=1, removed=0)

    rows = result_of(kernel.query(kernel.runtime, "view.watch", {"name": "changes", "after": mark}))["rows"]

    assert [(row["path"], row["since_mark"]) for row in rows] == [("b.py", mark)]


async def test_a_watcher_too_far_behind_gets_a_new_snapshot(kernel, monkeypatch):
    await spawn(kernel, "bob")
    cursor = kernel.head
    monkeypatch.setattr(clients, "WATCH_SPAN", 2)
    for index in range(3):
        await report(kernel, "bob", "item", kind="tool", gist=f"step {index}")

    page = result_of(kernel.query(kernel.runtime, "view.watch", {"name": "roster", "after": cursor}))

    assert page["snapshot"] and page["rows"][0]["agent"] == "bob"


async def test_an_unknown_view_is_refused(kernel):
    assert refusal(kernel.query(kernel.runtime, "view.watch", {"name": "nope"})).code == "invalid"


@pytest.mark.parametrize("limits", [{"max_hops": 0}])
async def test_a_wake_past_hops_leaves_attention_when_a_turn_starts(kernel, ada, limits):
    alice = await spawn(kernel, "alice")
    await spawn(kernel, "bob")
    first = await send(kernel, alice, "@alice", "to myself")
    await send(kernel, alice, "@bob", "past the limit", reply_to=first["ref"])
    assert [row["kind"] for row in result_of(kernel.query(ada, "attention.list", {}))] == ["hops"]

    await start_turn(kernel, "bob")

    assert result_of(kernel.query(ada, "attention.list", {})) == []
