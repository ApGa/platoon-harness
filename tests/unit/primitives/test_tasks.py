"""Queues: architecture section 7, and the Claim race from the brief."""

import asyncio
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from platoon_harness.kernel import Kernel, ManualClock
from platoon_harness.kernel.timers import fire_timers
from platoon_harness.primitives import PRIMITIVES
from platoon_harness.primitives.tasks import claim as claim_op

from .support import channel, grant, of_type, read, refusal, result_of, send, spawn


@pytest.fixture
async def queue(kernel) -> str:
    await channel(kernel, "work", kind="queue", lease=60.0, max_attempts=2)
    return "work"


async def add(kernel, gist: str = "do it") -> str:
    return result_of(await kernel.submit(kernel.runtime, "task.add", {"queue": "work", "gist": gist}))["task"]


async def claim(kernel, by, **fields: Any) -> dict[str, Any]:
    return result_of(await kernel.submit(by, "task.claim", {"queue": "work", **fields}))


def tasks(kernel, **fields: Any) -> list[dict[str, Any]]:
    return result_of(kernel.query(kernel.runtime, "task.list", {"queue": "work", **fields}))["tasks"]


async def test_a_task_is_one_stream(kernel, queue):
    id = await add(kernel)

    assert of_type(kernel, "task.added")[0].stream == f"task/work/{id}"


async def test_a_task_needs_a_queue(kernel):
    outcome = await kernel.submit(kernel.runtime, "task.add", {"queue": "nowhere", "gist": "x"})

    assert refusal(outcome).code == "not_found"


async def test_claim_takes_the_oldest_open_task(kernel, queue):
    bob = await spawn(kernel, "bob")
    first = await add(kernel, "first")
    await add(kernel, "second")

    lease = await claim(kernel, bob)

    assert lease["task"] == first and lease["gist"] == "first"


async def test_the_fence_is_the_seq_of_the_claim_event(kernel, queue):
    bob = await spawn(kernel, "bob")
    await add(kernel)

    lease = await claim(kernel, bob)

    assert lease["fence"] == of_type(kernel, "task.claimed")[0].seq


async def test_an_empty_queue_is_refused(kernel, queue):
    bob = await spawn(kernel, "bob")

    assert refusal(await kernel.submit(bob, "task.claim", {"queue": "work"})).code == "queue_empty"


async def test_a_loss_names_the_owner(kernel, queue):
    alice, bob = await spawn(kernel, "alice"), await spawn(kernel, "bob")
    id = await add(kernel)
    await claim(kernel, alice)

    refused = refusal(await kernel.submit(bob, "task.claim", {"queue": "work", "task": id}))

    assert refused.code == "conflict" and refused.detail["owner"] == "@alice"


async def test_max_inflight_limits_a_reader(kernel, queue):
    bob = await spawn(kernel, "bob")
    await add(kernel)
    await add(kernel)
    await claim(kernel, bob)

    refused = refusal(await kernel.submit(bob, "task.claim", {"queue": "work"}))

    assert refused.code == "conflict" and refused.detail == {"held": 1, "max_inflight": 1}


async def test_complete_finishes_a_task(kernel, queue):
    bob = await spawn(kernel, "bob")
    await add(kernel)
    lease = await claim(kernel, bob)

    result_of(
        await kernel.submit(bob, "task.complete", {"queue": "work", "task": lease["task"], "fence": lease["fence"]})
    )

    assert tasks(kernel)[0]["state"] == "done"
    assert of_type(kernel, "task.completed")[0].cause == (lease["fence"],)


async def test_the_fence_defaults_to_the_callers_live_lease(kernel, queue):
    bob = await spawn(kernel, "bob")
    await add(kernel)
    await claim(kernel, bob)

    result_of(await kernel.submit(bob, "task.complete", {"queue": "work"}))

    assert tasks(kernel)[0]["state"] == "done"


async def test_complete_after_expiry_is_refused_stale_fence_even_with_no_reassignment(kernel, queue, clock):
    bob = await spawn(kernel, "bob")
    await add(kernel)
    lease = await claim(kernel, bob)
    clock.advance(60)

    explicit = {"queue": "work", "task": lease["task"], "fence": lease["fence"]}

    assert refusal(await kernel.submit(bob, "task.complete", explicit)).code == "stale_fence"
    assert refusal(await kernel.submit(bob, "task.complete", {"queue": "work"})).code == "stale_fence"
    assert of_type(kernel, "task.completed") == []


async def test_a_lease_expires_as_an_event_through_a_timer(kernel, queue, clock):
    bob = await spawn(kernel, "bob")
    await add(kernel)
    await claim(kernel, bob)
    clock.advance(60)

    await fire_timers(kernel)

    assert of_type(kernel, "lease.expired")[0].data["task"] == "1"
    assert tasks(kernel)[0]["state"] == "open" and tasks(kernel)[0]["owner"] is None


async def test_claim_treats_an_expired_lease_as_free_before_its_timer_fires(kernel, queue, clock):
    alice, bob = await spawn(kernel, "alice"), await spawn(kernel, "bob")
    await add(kernel)
    first = await claim(kernel, alice)
    clock.advance(60)

    second = await claim(kernel, bob)

    assert second["task"] == first["task"] and second["fence"] > first["fence"]
    assert of_type(kernel, "lease.expired")[0].data["fence"] == first["fence"]


async def test_a_late_timer_changes_nothing_after_a_reclaim(kernel, queue, clock):
    alice, bob = await spawn(kernel, "alice"), await spawn(kernel, "bob")
    await add(kernel)
    await claim(kernel, alice)
    clock.advance(60)
    await claim(kernel, bob)
    head = kernel.head

    await fire_timers(kernel)

    assert of_type(kernel, "lease.expired", after=head) == []
    assert tasks(kernel)[0]["owner"] == "@bob"


async def test_renew_extends_a_lease_and_its_timer(kernel, queue, clock):
    bob = await spawn(kernel, "bob")
    await add(kernel)
    await claim(kernel, bob)
    clock.advance(30)

    renewed = result_of(await kernel.submit(bob, "task.renew", {"queue": "work"}))
    clock.advance(40)
    await fire_timers(kernel)

    assert renewed["lease_until"] == 1090.0
    assert of_type(kernel, "lease.expired") == []
    result_of(await kernel.submit(bob, "task.complete", {"queue": "work"}))


async def test_renew_after_expiry_is_stale(kernel, queue, clock):
    bob = await spawn(kernel, "bob")
    id = await add(kernel)
    await claim(kernel, bob)
    clock.advance(60)

    outcome = await kernel.submit(bob, "task.renew", {"queue": "work", "task": id})

    assert refusal(outcome).code == "stale_fence"


async def test_the_runtime_renews_for_the_owner_up_to_lease_max(kernel, clock):
    await channel(kernel, "work", kind="queue", lease=60.0, lease_max=100.0)
    bob = await spawn(kernel, "bob")
    id = await add(kernel)
    lease = await claim(kernel, bob)
    args = {"queue": "work", "task": id, "fence": lease["fence"]}

    clock.advance(50)
    assert result_of(await kernel.submit(kernel.runtime, "task.renew", args))["lease_until"] == 1100.0
    clock.advance(40)
    assert result_of(await kernel.submit(kernel.runtime, "task.renew", args))["lease_until"] == 1100.0
    clock.advance(10)
    assert refusal(await kernel.submit(kernel.runtime, "task.renew", args)).code == "stale_fence"


async def test_release_gives_a_task_back_and_spends_no_attempt(kernel, queue):
    alice, bob = await spawn(kernel, "alice"), await spawn(kernel, "bob")
    await add(kernel)
    await claim(kernel, alice)

    result_of(await kernel.submit(alice, "task.release", {"queue": "work"}))
    lease = await claim(kernel, bob)

    assert lease["attempt"] == 1


async def test_a_failed_task_is_claimed_again_until_max_attempts_then_dead(kernel, queue, ada):
    bob = await spawn(kernel, "bob")
    id = await add(kernel)

    await claim(kernel, bob)
    result_of(await kernel.submit(bob, "task.fail", {"queue": "work", "gist": "no luck"}))
    assert tasks(kernel)[0]["state"] == "failed"

    await claim(kernel, bob)
    result_of(await kernel.submit(bob, "task.fail", {"queue": "work"}))
    assert tasks(kernel)[0]["state"] == "dead"

    rows = result_of(kernel.query(ada, "attention.list", {}))
    assert [(row["kind"], row["id"]) for row in rows] == [("dead_task", f"task/work/{id}")]
    assert refusal(await kernel.submit(bob, "task.claim", {"queue": "work"})).code == "queue_empty"


async def test_repeated_expiry_ends_dead(kernel, queue, clock):
    alice = await spawn(kernel, "alice")
    await add(kernel)
    await claim(kernel, alice)
    clock.advance(60)
    await claim(kernel, alice)
    clock.advance(60)

    await fire_timers(kernel)

    assert tasks(kernel)[0]["state"] == "dead"


async def test_ending_an_agent_frees_its_leases(kernel, queue, ada):
    alice, bob = await spawn(kernel, "alice"), await spawn(kernel, "bob")
    await add(kernel)
    await claim(kernel, alice)

    result_of(await kernel.submit(ada, "agent.cancel", {"agent": "alice"}))

    assert tasks(kernel)[0]["state"] == "open"
    assert (await claim(kernel, bob))["attempt"] == 2


async def test_ending_an_agent_on_its_last_attempt_buries_the_task(kernel, queue, clock, ada):
    alice = await spawn(kernel, "alice")
    await add(kernel)
    await claim(kernel, alice)
    clock.advance(60)
    await claim(kernel, alice)

    result_of(await kernel.submit(ada, "agent.cancel", {"agent": "alice"}))

    assert tasks(kernel)[0]["state"] == "dead"


async def test_task_list_is_paged_with_a_true_total(kernel, queue):
    for index in range(5):
        await add(kernel, f"t{index}")

    page = result_of(kernel.query(kernel.runtime, "task.list", {"queue": "work", "limit": 2}))
    rest = result_of(kernel.query(kernel.runtime, "task.list", {"queue": "work", "after": page["cursor"], "limit": 9}))

    assert page["total"] == 5 and [task["gist"] for task in rest["tasks"]] == ["t2", "t3", "t4"]


async def test_an_agents_task_list_records_exposure(kernel, queue):
    bob = await spawn(kernel, "bob")
    await add(kernel, "secret plan")

    result_of(await kernel.submit(bob, "task.list", {"queue": "work"}))

    assert of_type(kernel, "context.offered")[-1].data["items"][0]["ref"] == "task/work/1@1"


def test_the_claim_tool_says_work_may_be_redone():
    assert "make it safe to repeat" in " ".join(claim_op.fn.__doc__.split())


async def test_the_default_fence_is_the_callers_live_lease_past_a_lapsed_one(kernel, clock):
    await channel(kernel, "many", kind="queue", max_inflight=2, lease=10.0)
    bob = await spawn(kernel, "bob")
    for _ in range(2):
        result_of(await kernel.submit(kernel.runtime, "task.add", {"queue": "many", "gist": "x"}))
    result_of(await kernel.submit(bob, "task.claim", {"queue": "many"}))
    clock.advance(6)
    second = result_of(await kernel.submit(bob, "task.claim", {"queue": "many"}))
    clock.advance(6)

    result_of(await kernel.submit(bob, "task.complete", {"queue": "many"}))

    listed = result_of(kernel.query(kernel.runtime, "task.list", {"queue": "many"}))["tasks"]
    assert next(task for task in listed if task["id"] == second["task"])["state"] == "done"


async def test_a_failed_task_keeps_what_it_rests_on(kernel, queue):
    bob = await spawn(kernel, "bob")
    await add(kernel)
    await claim(kernel, bob)
    source = result_of(await kernel.submit(kernel.runtime, "message.send", {"to": "@bob", "gist": "why"}))

    result_of(await kernel.submit(bob, "task.fail", {"queue": "work", "based_on": [source["ref"]]}))

    assert of_type(kernel, "task.failed")[0].based_on == (source["ref"],)


@pytest.mark.parametrize(("field", "value"), [("based_on", ["nothing/here@9"]), ("body", "sha256:" + "0" * 64)])
async def test_a_failed_task_cites_only_what_exists(kernel, queue, field, value):
    bob = await spawn(kernel, "bob")
    await add(kernel)
    await claim(kernel, bob)

    assert refusal(await kernel.submit(bob, "task.fail", {"queue": "work", field: value})).code == "not_found"


async def test_a_workers_result_can_be_read_back_and_reading_it_is_evidence(kernel, queue):
    lead, bob = await spawn(kernel, "lead"), await spawn(kernel, "bob")
    await add(kernel)
    await claim(kernel, bob)
    body = await kernel.put_body(b"the working")
    done = {"queue": "work", "gist": "the answer is 42", "body": f"sha256:{body}"}
    result_of(await kernel.submit(bob, "task.complete", done))

    listed = result_of(await kernel.submit(lead, "task.list", {"queue": "work"}))["tasks"][0]

    assert (listed["ref"], listed["result"], listed["result_ref"], listed["result_body"]) == (
        "task/work/1@1",
        "the answer is 42",
        "task/work/1@3",
        True,
    )
    assert of_type(kernel, "context.offered")[-1].data["items"][1]["ref"] == "task/work/1@3"
    read_back = result_of(await kernel.submit(lead, "blob.get", {"ref": listed["result_ref"]}))
    assert read_back["text"] == "the working"


async def test_a_list_of_no_queue_is_refused_even_for_a_human(kernel, ada):
    assert refusal(await kernel.submit(ada, "task.list", {"queue": "wrok"})).code == "not_found"


async def test_a_list_says_when_it_has_reached_the_end(kernel, queue):
    await add(kernel)

    page = result_of(kernel.query(kernel.runtime, "task.list", {"queue": "work"}))

    assert page["cursor"] is None


async def test_a_queue_that_wakes_announces_work_to_its_readers(kernel):
    await channel(kernel, "tasks", kind="queue", delivery="wake")
    await spawn(kernel, "bob")

    result_of(await kernel.submit(kernel.runtime, "task.add", {"queue": "tasks", "gist": "do it"}))

    assert result_of(kernel.query(kernel.runtime, "delivery.ready", {}))["agents"] == ["bob"]
    handed = result_of(await kernel.submit(kernel.runtime, "delivery.offer", {"agent": "bob"}))
    assert [item["gist"] for item in handed["items"]] == ["do it"]


async def test_a_queue_announcement_goes_to_who_may_claim_and_to_nobody_else(kernel):
    await channel(kernel, "tasks", kind="queue", delivery="wake")
    await spawn(kernel, "bob")
    await spawn(kernel, "alice")
    await kernel.submit(kernel.runtime, "grant.remove", {"who": "agent", "ops": "*", "on": "*"})
    await grant(kernel, "agent:bob", "task.claim", "queue/tasks")

    result_of(await kernel.submit(kernel.runtime, "task.add", {"queue": "tasks", "gist": "do it"}))

    assert result_of(kernel.query(kernel.runtime, "delivery.ready", {}))["agents"] == ["bob"]


async def test_a_pull_queue_posts_no_entry(kernel, queue):
    await spawn(kernel, "bob")

    await add(kernel)

    assert of_type(kernel, "message.sent") == []


@pytest.mark.parametrize("limits", [{"max_hops": 1}])
async def test_a_chain_through_a_queue_stops_at_max_hops(kernel, limits):
    await channel(kernel, "tasks", kind="queue", delivery="wake")
    alice = await spawn(kernel, "alice")
    await spawn(kernel, "bob")
    await send(kernel, kernel.runtime, "@alice", "go")
    await read(kernel, alice, "@alice")
    await send(kernel, alice, "@alice", "and on")
    await read(kernel, alice, "@alice")

    result_of(await kernel.submit(alice, "task.add", {"queue": "tasks", "gist": "past the limit"}))

    assert [event.data["why"] for event in of_type(kernel, "wake.refused")][-1] == "hops"


async def test_a_claim_records_exposure_of_the_task(kernel, queue):
    bob = await spawn(kernel, "bob")
    await add(kernel)

    await claim(kernel, bob)

    assert of_type(kernel, "context.offered")[-1].data["how"] == "read"


# The Claim race: one valid lease, and no stale owner can complete.


async def test_claim_race_concurrent_claimants_get_one_valid_lease(kernel, queue):
    agents = [await spawn(kernel, f"a{index}") for index in range(8)]
    await add(kernel)

    outcomes = await asyncio.gather(*(kernel.submit(agent, "task.claim", {"queue": "work"}) for agent in agents))

    won = [outcome for outcome in outcomes if outcome.refusal is None]
    assert len(won) == 1
    assert {outcome.refusal.code for outcome in outcomes if outcome.refusal} == {"queue_empty"}


async def test_claim_race_a_stale_owner_cannot_complete_after_reassignment(kernel, queue, clock):
    alice, bob = await spawn(kernel, "alice"), await spawn(kernel, "bob")
    id = await add(kernel)
    stale = await claim(kernel, alice)
    clock.advance(60)
    fresh = await claim(kernel, bob)

    args = {"queue": "work", "task": id, "fence": stale["fence"]}

    assert refusal(await kernel.submit(alice, "task.complete", args)).code == "stale_fence"
    assert refusal(await kernel.submit(alice, "task.complete", {"queue": "work", "task": id})).code == "stale_fence"
    assert refusal(await kernel.submit(alice, "task.fail", args)).code == "stale_fence"
    assert refusal(await kernel.submit(bob, "task.complete", args)).code == "stale_fence"
    result_of(await kernel.submit(bob, "task.complete", {"queue": "work", "fence": fresh["fence"]}))
    assert tasks(kernel)[0]["state"] == "done"


async def test_claim_race_a_stale_fence_cannot_slip_in_at_the_same_commit(kernel, queue, clock):
    alice = await spawn(kernel, "alice")
    agents = [await spawn(kernel, f"a{index}") for index in range(4)]
    id = await add(kernel)
    stale = await claim(kernel, alice)
    clock.advance(60)
    completing = {"queue": "work", "task": id, "fence": stale["fence"]}

    outcomes = await asyncio.gather(
        kernel.submit(alice, "task.complete", completing),
        *(kernel.submit(agent, "task.claim", {"queue": "work"}) for agent in agents),
    )

    assert outcomes[0].refusal.code == "stale_fence"
    assert sum(outcome.refusal is None for outcome in outcomes[1:]) == 1


steps = st.lists(
    st.one_of(
        st.tuples(st.just("claim"), st.integers(0, 2)),
        st.tuples(st.just("complete"), st.integers(0, 2)),
        st.tuples(st.just("advance"), st.sampled_from([10, 30, 60])),
    ),
    max_size=20,
)


@settings(max_examples=30, deadline=None)
@given(script=steps)
def test_claim_race_a_task_has_at_most_one_completer_and_it_held_a_live_lease(tmp_path_factory, script) -> None:
    folder = tmp_path_factory.mktemp("claims") / "session"

    async def body() -> None:
        clock = ManualClock(1000.0)
        kernel = Kernel.open(folder, clock=clock, extensions=PRIMITIVES)
        result_of(await kernel.submit(kernel.runtime, "session.open", {"roles": {"worker": {}}}))
        await grant(kernel, "agent")
        await channel(kernel, "work", kind="queue", lease=45.0, max_attempts=99)
        agents = [await spawn(kernel, f"a{index}") for index in range(3)]
        await add(kernel)
        leases: dict[int, dict[str, Any]] = {}
        latest = 0
        done = False
        for step, value in script:
            if step == "advance":
                clock.advance(value)
            elif step == "claim":
                outcome = await kernel.submit(agents[value], "task.claim", {"queue": "work"})
                if outcome.refusal is None:
                    leases[value] = outcome.result
                    latest = outcome.result["fence"]
            elif value in leases:
                lease = leases[value]
                args = {"queue": "work", "task": "1", "fence": lease["fence"]}
                outcome = await kernel.submit(agents[value], "task.complete", args)
                valid = not done and lease["fence"] == latest and lease["lease_until"] > clock.now()
                assert (outcome.refusal is None) == valid
                done = done or valid
        assert len(of_type(kernel, "task.completed")) == int(done)
        kernel.close()

    asyncio.run(body())


def due(kernel, agent: str) -> list[dict[str, Any]]:
    return result_of(kernel.query(kernel.runtime, "lease.due", {"agent": agent}))


async def test_a_lease_is_due_for_renewal_past_half_its_time(kernel, queue, clock):
    bob = await spawn(kernel, "bob")
    await add(kernel)
    claimed = await claim(kernel, bob)

    assert due(kernel, "bob") == []

    clock.advance(31.0)

    assert due(kernel, "bob") == [{"queue": "work", "task": claimed["task"], "fence": claimed["fence"]}]


async def test_a_lease_that_lapsed_or_cannot_grow_is_not_due(kernel, clock):
    await channel(kernel, "work", kind="queue", lease=60.0, lease_max=60.0)
    bob = await spawn(kernel, "bob")
    await add(kernel)
    await claim(kernel, bob)

    clock.advance(31.0)
    assert due(kernel, "bob") == []

    clock.advance(30.0)
    assert due(kernel, "bob") == []


async def test_what_is_due_renews_with_no_fence_in_the_model_s_hands(kernel, queue, clock):
    bob = await spawn(kernel, "bob")
    await add(kernel)
    await claim(kernel, bob)
    clock.advance(31.0)

    renewed = result_of(await kernel.submit(kernel.runtime, "task.renew", due(kernel, "bob")[0]))

    assert renewed["lease_until"] == clock.now() + 60.0
    assert due(kernel, "bob") == []
