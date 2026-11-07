"""What clients render: typed `why`, actions as op references, and `view.watch`."""

import pytest

from platoon_harness.primitives import clients

from .support import channel, end_turn, refusal, report, result_of, send, spawn, start_turn
from .test_repo import BASE, ONE, conflicted, looked, path, reading


def roster(kernel, name: str) -> dict:
    rows = result_of(kernel.query(kernel.runtime, "view.watch", {"name": "roster"}))["rows"]
    return next(row for row in rows if row["agent"] == name)


def attention(kernel) -> list[dict]:
    return result_of(kernel.query(kernel.runtime, "attention.list", {}))


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


async def test_what_waits_for_an_agent_is_what_its_unread_counts_with_how_each_would_land(kernel, ada):
    alice = await spawn(kernel, "alice")
    await spawn(kernel, "bob", goal="")
    await start_turn(kernel, "bob")
    await send(kernel, alice, "@bob", "one")
    result_of(await kernel.submit(ada, "agent.interrupt", {"agent": "bob"}))
    await send(kernel, alice, "@bob", "two")

    waiting = result_of(kernel.query(ada, "agent.unread", {"agent": "bob"}))

    assert [(entry["gist"], entry["sender"], entry["delivery"]) for entry in waiting["entries"]] == [
        ("one", "@alice", "next-turn"),
        ("two", "@alice", "wake"),
    ]
    assert waiting["total"] == roster(kernel, "bob")["unread"] == 2


async def test_what_waits_for_an_agent_is_no_other_agent_s_to_read(kernel):
    alice = await spawn(kernel, "alice")
    await spawn(kernel, "bob")

    assert refusal(kernel.query(alice, "agent.unread", {"agent": "bob"})).code == "not_permitted"


async def test_roster_shows_usage_with_its_label(kernel):
    await spawn(kernel, "bob")
    await send(kernel, kernel.runtime, "@bob", "go")
    result_of(await kernel.submit(kernel.runtime, "delivery.offer", {"agent": "bob"}))
    await start_turn(kernel, "bob")
    await report(kernel, "bob", "usage", tokens=10, label="provider")
    await end_turn(kernel, "bob")

    usage = roster(kernel, "bob")["usage"]
    assert usage["tokens"] == {"amount": 10, "label": "provider", "unmeasured": 0}
    assert usage["usd"] == {"amount": None, "label": "unavailable", "unmeasured": 1}


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


def group(kernel, name: str) -> str:
    return roster(kernel, name)["group"]


async def test_a_roster_row_is_grouped_by_what_a_person_must_do_about_it(kernel, ada):
    """Needs you while an attention row other than a mention names it, done or failed once ended, working in a turn or
    on its way to one, blocked while `why` names what it waits on, and idle otherwise."""
    await spawn(kernel, "idle", goal="")
    await spawn(kernel, "busy")
    await start_turn(kernel, "busy")
    await spawn(kernel, "asking")
    await kernel.submit(kernel.runtime, "approval.request", {"id": "a1", "agent": "asking", "gist": "may I"})
    holding = await spawn(kernel, "holding", goal="")
    await channel(kernel, "work", kind="queue")
    await kernel.submit(kernel.runtime, "task.add", {"queue": "work", "gist": "x"})
    result_of(await kernel.submit(holding, "task.claim", {"queue": "work"}))
    talking = await spawn(kernel, "talking", goal="")
    await send(kernel, talking, "@ada", "got a minute?")
    done = await spawn(kernel, "done")
    result_of(await kernel.submit(done, "agent.finish", {"gist": "all of it"}))
    await spawn(kernel, "lost")
    await report(kernel, "lost", "exited", reason="the harness crashed")

    groups = {name: group(kernel, name) for name in ("idle", "busy", "asking", "holding", "talking", "done", "lost")}

    assert groups == {
        "idle": "idle",
        "busy": "working",
        "asking": "needs_you",
        "holding": "blocked",
        "talking": "idle",
        "done": "done",
        "lost": "failed",
    }


async def test_attention_holds_a_mention_until_it_is_answered(kernel, ada):
    alice = await spawn(kernel, "alice")
    sent = await send(kernel, alice, "@ada", "got a minute?")
    assert [row["kind"] for row in result_of(kernel.query(ada, "attention.list", {}))] == ["mention"]

    await send(kernel, ada, "@alice", "yes", reply_to=sent["ref"])

    assert result_of(kernel.query(ada, "attention.list", {})) == []


async def test_an_uncertain_row_offers_what_settles_it(kernel, ada):
    await spawn(kernel, "bob", goal="")
    effect = await started_effect(kernel)
    await kernel.recover()

    row = next(row for row in attention(kernel) if row["id"] == f"effect/{effect['id']}")
    assert [(action["op"], action["args"]["happened"]) for action in row["actions"]] == [
        ("effect.settle", True),
        ("effect.settle", False),
    ]
    action = row["actions"][0]
    result_of(await kernel.submit(ada, action["op"], action["args"]))

    assert row["id"] not in [found["id"] for found in attention(kernel)]


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
    assert [(row["agent"], row["activity"]) for row in next_page["rows"]] == [("alice", "working"), ("bob", None)]
    assert next_page["cursor"] == kernel.head


async def test_a_roster_delta_agrees_with_a_fresh_snapshot(kernel):
    """A row moves on events that name someone else or nobody, so what a watcher folds must equal a new snapshot."""
    boss = await spawn(kernel, "boss", role="lead")
    alice, _ = await spawn(kernel, "alice"), await spawn(kernel, "bob")
    await channel(kernel, "barrier")
    watching = result_of(kernel.query(kernel.runtime, "view.watch", {"name": "roster"}))
    rows = {row["agent"]: row for row in watching["rows"]}

    async def agrees() -> None:
        state = result_of(kernel.query(kernel.runtime, "view.watch", {"name": "roster", "after": watching["cursor"]}))
        rows.update({row["agent"]: row for row in state["rows"]})
        watching["cursor"] = state["cursor"]
        fresh = result_of(kernel.query(kernel.runtime, "view.watch", {"name": "roster"}))["rows"]
        assert rows == {row["agent"]: row for row in fresh}

    await send(kernel, alice, "@bob", "from an agent")
    await agrees()
    await send(kernel, kernel.runtime, "@bob", "from nobody in the roster")
    await agrees()
    await kernel.submit(boss, "wait", {"on": [{"stream": "channel/barrier", "n": 2, "distinct": "actor"}]})
    await send(kernel, alice, "#barrier", "here")
    await agrees()
    result_of(await kernel.submit(kernel.runtime, "budget.set", {"limits": {"tokens": 10}, "estimate": {"tokens": 99}}))
    await send(kernel, kernel.runtime, "@alice", "go")
    await kernel.submit(kernel.runtime, "delivery.offer", {"agent": "alice"})
    await agrees()
    result_of(await kernel.submit(kernel.runtime, "budget.set", {"limits": {"tokens": 99}, "estimate": {"tokens": 9}}))
    await agrees()


async def test_a_roster_delta_is_empty_while_the_journal_is_still(kernel):
    await spawn(kernel, "bob")
    first = result_of(kernel.query(kernel.runtime, "view.watch", {"name": "roster"}))

    state = result_of(kernel.query(kernel.runtime, "view.watch", {"name": "roster", "after": first["cursor"]}))

    assert state["rows"] == [] and state["cursor"] == first["cursor"]


async def test_a_roster_row_says_why_the_last_turn_stopped_until_the_next_begins(kernel):
    await spawn(kernel, "bob")
    assert roster(kernel, "bob")["stopped"] is None

    await start_turn(kernel, "bob")
    assert roster(kernel, "bob")["stopped"] is None
    await end_turn(kernel, "bob", "failed: out of memory")
    assert roster(kernel, "bob")["stopped"] == "failed: out of memory"

    await start_turn(kernel, "bob", "t2")
    assert roster(kernel, "bob")["stopped"] is None


async def test_a_roster_row_says_nothing_of_a_turn_that_stopped_on_its_own(kernel):
    await spawn(kernel, "bob")
    await start_turn(kernel, "bob")

    await end_turn(kernel, "bob")

    assert roster(kernel, "bob")["stopped"] is None


async def test_a_roster_row_says_a_lost_turn_was_lost(kernel):
    await spawn(kernel, "bob")
    await start_turn(kernel, "bob")

    await kernel.recover()

    assert roster(kernel, "bob")["stopped"] == "lost"


async def test_a_roster_row_names_its_parent_as_that_parent_s_row_does(kernel):
    boss = await spawn(kernel, "boss", role="lead")
    await spawn(kernel, "bob", by=boss)

    assert roster(kernel, "boss")["parent"] is None
    assert roster(kernel, "bob")["parent"] == roster(kernel, "boss")["agent"]


async def test_a_roster_row_says_who_holds_an_agent(kernel, ada):
    await spawn(kernel, "bob", ready={"resume": True})

    result_of(await kernel.submit(ada, "agent.takeover", {"agent": "bob"}))
    assert roster(kernel, "bob")["held_by"] == "ada"

    result_of(await kernel.submit(ada, "agent.release", {"agent": "bob"}))
    assert roster(kernel, "bob")["held_by"] is None


async def test_activity_reads_the_running_tool_from_its_started_item(kernel):
    await spawn(kernel, "bob")
    await start_turn(kernel, "bob")

    await report(kernel, "bob", "item", kind="tool", phase="started", gist="pytest called")

    assert roster(kernel, "bob")["activity"] == "pytest called"


async def test_watch_says_when_a_key_went_away(kernel, ada):
    await spawn(kernel, "bob")
    await kernel.submit(kernel.runtime, "approval.request", {"id": "a1", "agent": "bob", "gist": "may I"})
    first = result_of(kernel.query(ada, "view.watch", {"name": "attention"}))
    assert [row["id"] for row in first["rows"]] == ["approval/a1"]

    action = first["rows"][0]["actions"][0]
    result_of(await kernel.submit(ada, action["op"], action["args"]))
    second = result_of(kernel.query(ada, "view.watch", {"name": "attention", "after": first["cursor"]}))

    assert second["rows"] == [] and second["removed"] == ["approval/a1"]


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


async def test_a_lost_turn_asks_for_attention_until_a_turn_starts(kernel):
    await spawn(kernel, "bob")
    await start_turn(kernel, "bob")

    await kernel.recover()

    assert [(row["id"], row["kind"]) for row in attention(kernel)] == [("turn/bob", "uncertain")]

    await start_turn(kernel, "bob", "t2")

    assert attention(kernel) == []


async def test_a_daemon_that_keeps_failing_stands_in_attention_until_a_run_of_it_lasts(kernel):
    """Loud failure: a daemon that fails on every pass would otherwise look like a quiet session. The row names it,
    where its traceback is, what starts it anew and its latest error, and goes once a run lasts a minute, or a new
    runtime brings new daemons."""
    said = {"daemon": "courier", "error": "RuntimeError: no luck"}
    result_of(await kernel.submit(kernel.runtime, "daemon.fail", said))
    raised = attention(kernel)
    result_of(await kernel.submit(kernel.runtime, "daemon.fail", {**said, "error": "RuntimeError: worse"}))
    latest = attention(kernel)
    result_of(await kernel.submit(kernel.runtime, "daemon.recover", {"daemon": "courier"}))
    lowered = attention(kernel)
    result_of(await kernel.submit(kernel.runtime, "daemon.fail", said))
    result_of(await kernel.submit(kernel.runtime, "runtime.start", {}))

    assert [(row["id"], row["kind"], row["agent"], row["actions"]) for row in raised] == [
        ("daemon/courier", "daemon", None, [])
    ]
    assert raised[0]["gist"] == (
        "courier failed and is restarted with backoff, its traceback in the session folder's runtime.log, and "
        "`session stop` then `session resume` start it anew: RuntimeError: no luck"
    )
    assert [row["gist"].rpartition(": ")[2] for row in latest] == ["worse"]
    assert lowered == [] and attention(kernel) == []


async def offered(kernel, name: str) -> None:
    """Queue something for an agent and offer it a turn, as the courier would."""
    await send(kernel, kernel.runtime, f"@{name}", "go")
    await kernel.submit(kernel.runtime, "delivery.offer", {"agent": name})


async def test_a_budget_place_offers_budget_set_with_its_scope_fixed(kernel, ada, clock):
    """Setting a budget settles every place a budget held up: the scope the record names is fixed, and the limits are
    the person's to give, in its op's form."""
    await spawn(kernel, "bob")
    over = {"scope": "role:worker", "limits": {"tokens": 10}, "estimate": {"tokens": 99}}
    result_of(await kernel.submit(kernel.runtime, "budget.set", over))
    await offered(kernel, "bob")
    refused = attention(kernel)
    result_of(await kernel.submit(kernel.runtime, "budget.set", {"limits": {"wall": 60}}))
    clock.advance(60.0)
    result_of(await kernel.submit(kernel.runtime, "budget.lapse", {}))
    lapsed = [row for row in attention(kernel) if row["id"] == "budget/shared"]

    set_it = {"label": "Set the budget", "op": "budget.set", "form": True}
    assert [(row["id"], row["kind"], row["actions"]) for row in refused] == [
        ("wake/bob", "budget", [{**set_it, "args": {"scope": "role:worker"}}])
    ]
    assert [row["actions"] for row in lapsed] == [[{**set_it, "args": {"scope": "shared"}}]]
    result_of(await kernel.submit(ada, "budget.set", {**lapsed[0]["actions"][0]["args"], "limits": {"wall": 600}}))
    assert attention(kernel) == []


async def test_an_action_names_only_the_arguments_it_knows(kernel):
    """A limit no amount can hold refuses a wake in words that name no scope, so its action fixes none, and leaves the
    scope to its op's form with the limits."""
    await spawn(kernel, "bob")
    await offered(kernel, "bob")
    await start_turn(kernel, "bob")
    await end_turn(kernel, "bob")
    limited = {"limits": {"tokens": 1000}, "estimate": {"tokens": 1}}
    result_of(await kernel.submit(kernel.runtime, "budget.set", limited))

    await offered(kernel, "bob")

    [row] = attention(kernel)
    assert (row["kind"], row["gist"]) == ("budget", "wake of bob refused: unavailable")
    assert [(action["op"], action["args"], action["form"]) for action in row["actions"]] == [("budget.set", {}, True)]


async def in_flight(kernel, name: str, kind: str) -> dict:
    """Start the one effect of `kind` that waits, as a daemon would, and give its id and attempt."""
    effect = next(row for row in result_of(kernel.query(kernel.runtime, "effect.ready", {})) if row["kind"] == kind)
    assert effect["agent"] == name
    started = result_of(await kernel.submit(kernel.runtime, "effect.start", {"id": effect["id"]}))
    return {"id": effect["id"], "attempt": started}


REPO = {"name": "app", "top": "/work/app", "prefix": "", "head": BASE, "branch": "main", "repository": "/work/.git"}
KINDS = {"approval", "uncertain", "mention", "conflict", "failed", "dead_task", "hops", "budget", "daemon"}
SETTLED_BY = {
    "conflict": "resolve it in",
    "failed": "nothing tries it again",
    "daemon": "`session stop` then `session resume` start it anew",
}
"""What the gist of a place with no action says settles it, by its kind."""


@pytest.mark.parametrize(("limits", "repo"), [({"max_hops": 0}, REPO)])
async def test_every_kind_of_place_carries_an_action_or_names_what_settles_it(kernel, ada, clock, limits, repo):
    """Each kind of place the view raises, from each event that raises it, carries an action, or says in its gist what
    settles it. A mention is the person's to read, which their marks say, with a Reply where its sender takes one."""
    await spawn(kernel, "carol", goal="")
    await send(kernel, kernel.runtime, "@carol", "go")
    result_of(await kernel.submit(kernel.runtime, "delivery.offer", {"agent": "carol"}))
    uncertain = await in_flight(kernel, "carol", "deliver")
    await spawn(kernel, "dave")
    await start_turn(kernel, "dave")
    await kernel.recover()
    await spawn(kernel, "erin")
    result_of(await kernel.submit(kernel.runtime, "approval.request", {"id": "a1", "agent": "erin", "gist": "may I"}))
    frank = await spawn(kernel, "frank")
    asked = await send(kernel, frank, "@ada", "got a minute?")
    gus = await spawn(kernel, "gus", by=ada)
    result_of(await kernel.submit(gus, "agent.finish", {"gist": "here is the result"}))
    kim = await spawn(kernel, "kim")
    result_of(await kernel.submit(kim, "agent.finish", {"gist": "nobody asked, but here"}))
    await spawn(kernel, "bob")
    await conflicted(kernel, "a.py")
    await looked(kernel, "shared", reading={**reading(ONE, path("a.py", "conflicted")), "branch": "main"})
    await spawn(kernel, "hank", goal="")
    await send(kernel, kernel.runtime, "@hank", "go")
    result_of(await kernel.submit(kernel.runtime, "delivery.offer", {"agent": "hank"}))
    failing = await in_flight(kernel, "hank", "deliver")
    result_of(await kernel.submit(kernel.runtime, "effect.fail", {**failing, "error": "the pipe broke"}))
    erased = (await kernel.put_body(b"something to erase")).removeprefix("sha256:")
    result_of(await kernel.submit(ada, "body.tombstone", {"sha256": erased}))
    erasing = await in_flight(kernel, None, "erase")
    result_of(await kernel.submit(kernel.runtime, "effect.fail", {**erasing, "error": "the disk went"}))
    await channel(kernel, "q", kind="queue", max_attempts=1)
    ivan = await spawn(kernel, "ivan")
    result_of(await kernel.submit(kernel.runtime, "task.add", {"queue": "q", "gist": "x"}))
    result_of(await kernel.submit(ivan, "task.claim", {"queue": "q"}))
    result_of(await kernel.submit(ivan, "task.fail", {"queue": "q"}))
    alice = await spawn(kernel, "alice")
    await spawn(kernel, "judy")
    first = await send(kernel, alice, "@alice", "to myself")
    await send(kernel, alice, "@judy", "past the limit", reply_to=first["ref"])
    result_of(await kernel.submit(kernel.runtime, "budget.set", {"limits": {"wall": 60}}))
    clock.advance(60.0)
    result_of(await kernel.submit(kernel.runtime, "budget.lapse", {}))
    failed = {"daemon": "courier", "error": "RuntimeError: no luck"}
    result_of(await kernel.submit(kernel.runtime, "daemon.fail", failed))

    rows = attention(kernel)
    acts = {row["id"]: [(act["label"], act["op"], act["args"], act["form"]) for act in row["actions"]] for row in rows}
    assert {row["kind"] for row in rows} == KINDS
    for row in rows:
        assert row["actions"] or row["kind"] == "mention" or SETTLED_BY[row["kind"]] in row["gist"], row
    write_to = [("Write to it", "message.send", {"to": f"@{name}"}, True) for name in ("dave", "bob", "hank", "judy")]
    assert [acts[id] for id in ("turn/dave", "conflict/@bob", f"effect/{failing['id']}", "wake/judy")] == [
        [act] for act in write_to
    ]
    assert acts[asked["ref"]] == [("Reply", "message.send", {"to": "@frank", "reply_to": asked["ref"]}, True)]
    reports = [row for row in rows if row["kind"] == "mention" and row["id"] != asked["ref"]]
    assert [(row["gist"], acts[row["id"]]) for row in reports] == [
        ("here is the result", []),
        ("kim finished: nobody asked, but here", []),
    ]
    assert acts["task/q/1"] == [("Add it again", "task.add", {"queue": "q", "based_on": ["task/q/1@1"]}, True)]
    assert acts["budget/shared"] == [("Set the budget", "budget.set", {"scope": "shared"}, True)]
    assert [act[:2] for act in acts["approval/a1"]] == [("Allow", "approval.resolve"), ("Deny", "approval.resolve")]
    assert [act[:2] for act in acts[f"effect/{uncertain['id']}"]] == [
        ("It happened", "effect.settle"),
        ("It did not", "effect.settle"),
    ]
    assert [row["gist"] for row in rows if not row["actions"] and row["kind"] == "failed"] == [
        "erase failed, and nothing tries it again: the disk went"
    ]


async def test_a_dead_task_s_place_closes_once_a_task_citing_it_is_added(kernel, ada):
    """Its action adds it again, citing it, which settles it; a task that cites nothing leaves it standing."""
    await channel(kernel, "q", kind="queue", max_attempts=1)
    bob = await spawn(kernel, "bob")
    result_of(await kernel.submit(kernel.runtime, "task.add", {"queue": "q", "gist": "fix the flaky test"}))
    result_of(await kernel.submit(bob, "task.claim", {"queue": "q"}))
    result_of(await kernel.submit(bob, "task.fail", {"queue": "q"}))
    [row] = attention(kernel)
    action = row["actions"][0]

    result_of(await kernel.submit(ada, "task.add", {"queue": "q", "gist": "something else"}))
    standing = attention(kernel)
    result_of(await kernel.submit(ada, action["op"], {**action["args"], "gist": "fix the flaky test, again"}))

    assert [found["id"] for found in standing] == ["task/q/1"]
    assert attention(kernel) == []
