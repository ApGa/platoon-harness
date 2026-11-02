"""Budgets: limits, reservations, reconciliation, labels, and the overshoot bound."""

import asyncio
from typing import Any

from hypothesis import given, settings
from hypothesis import strategies as st

from platoon_harness.kernel import Kernel, ManualClock
from platoon_harness.primitives import PRIMITIVES, Budget, Deliveries

from .support import end_turn, grant, of_type, refusal, report, result_of, send, settle_effects, spawn, start_turn


async def set_budget(kernel, **fields: Any) -> None:
    result_of(await kernel.submit(kernel.runtime, "budget.set", fields))


def limit(kernel, unit: str, scope: str = "shared") -> dict[str, Any]:
    rows = result_of(kernel.query(kernel.runtime, "budget.status", {}))
    return next(row for row in rows if row["unit"] == unit and row["scope"] == scope)


async def wake(kernel, name: str) -> dict[str, Any] | None:
    """Queue something for an agent and start its turn, as the courier would."""
    await send(kernel, kernel.runtime, f"@{name}", "go")
    return result_of(await kernel.submit(kernel.runtime, "delivery.offer", {"agent": name}))


async def fail_next_handover(kernel) -> None:
    effect = result_of(kernel.query(kernel.runtime, "effect.ready", {"kind": "deliver"}))[0]
    attempt = result_of(await kernel.submit(kernel.runtime, "effect.start", {"id": effect["id"]}))
    args = {"id": effect["id"], "attempt": attempt, "error": "the pipe broke"}
    result_of(await kernel.submit(kernel.runtime, "effect.fail", args))


async def test_a_wake_reserves_an_estimate(kernel):
    await spawn(kernel, "bob")
    await set_budget(kernel, limits={"tokens": 1000}, estimate={"tokens": 100})

    await wake(kernel, "bob")

    assert limit(kernel, "tokens")["held"] == 100


async def test_turn_end_reconciles_the_estimate_to_what_was_measured(kernel):
    await spawn(kernel, "bob")
    await set_budget(kernel, limits={"tokens": 1000}, estimate={"tokens": 100})
    await wake(kernel, "bob")
    await start_turn(kernel, "bob")
    await report(kernel, "bob", "usage", tokens=40, label="provider")
    await report(kernel, "bob", "usage", tokens=30, label="provider")

    await end_turn(kernel, "bob")

    row = limit(kernel, "tokens")
    assert (row["spent"], row["held"], row["label"]) == (70, 0, "provider")


async def test_a_limit_past_its_reservation_refuses_the_wake_as_an_event(kernel):
    await spawn(kernel, "bob")
    await set_budget(kernel, limits={"tokens": 100}, estimate={"tokens": 150})

    assert await wake(kernel, "bob") is None

    refused = of_type(kernel, "wake.refused")[0]
    assert refused.data["why"] == "over_budget" and refused.data["detail"]["unit"] == "tokens"


async def test_a_refused_wake_is_shown_in_attention_until_the_budget_moves(kernel, ada):
    await spawn(kernel, "bob")
    await set_budget(kernel, limits={"turns": 1})
    await wake(kernel, "bob")
    await start_turn(kernel, "bob")
    await report(kernel, "bob", "usage", tokens=1, usd=0.1, label="provider")
    await end_turn(kernel, "bob")
    await wake(kernel, "bob")

    assert [row["kind"] for row in result_of(kernel.query(ada, "attention.list", {}))] == ["budget"]

    await set_budget(kernel, limits={"turns": 5})
    assert result_of(kernel.query(ada, "attention.list", {})) == []


async def test_limits_hold_per_role(kernel):
    await spawn(kernel, "lead", role="lead")
    await spawn(kernel, "bob")
    await set_budget(kernel, scope="role:worker", limits={"turns": 1})
    await wake(kernel, "bob")
    await start_turn(kernel, "bob")
    await end_turn(kernel, "bob")

    assert await wake(kernel, "bob") is None
    assert await wake(kernel, "lead") is not None


async def test_shared_and_role_limits_both_apply(kernel):
    await spawn(kernel, "bob")
    await set_budget(kernel, limits={"turns": 1})
    await set_budget(kernel, scope="role:worker", limits={"turns": 9})

    await wake(kernel, "bob")

    assert limit(kernel, "turns")["held"] == 1 and limit(kernel, "turns", "role:worker")["held"] == 1


async def test_ending_an_agent_returns_its_reservation(kernel, ada):
    await spawn(kernel, "bob")
    await set_budget(kernel, limits={"tokens": 1000}, estimate={"tokens": 100})
    await wake(kernel, "bob")

    result_of(await kernel.submit(ada, "agent.cancel", {"agent": "bob"}))

    assert limit(kernel, "tokens")["held"] == 0


async def test_a_turn_lost_to_a_crash_keeps_its_estimate_as_spent(kernel):
    await spawn(kernel, "bob")
    await set_budget(kernel, limits={"tokens": 1000}, estimate={"tokens": 100})
    await wake(kernel, "bob")
    await start_turn(kernel, "bob")

    await kernel.recover()

    row = limit(kernel, "tokens")
    assert (row["spent"], row["held"], row["label"], row["unmeasured"]) == (100, 0, "unavailable", 1)


async def test_a_lost_turn_with_no_estimate_is_unmeasured_and_not_free(kernel):
    await spawn(kernel, "bob")
    await set_budget(kernel, limits={"tokens": 1000})
    await wake(kernel, "bob")
    await start_turn(kernel, "bob")

    await kernel.recover()

    assert limit(kernel, "tokens")["unmeasured"] == 1
    await send(kernel, kernel.runtime, "@bob", "again")
    assert result_of(await kernel.submit(kernel.runtime, "delivery.offer", {"agent": "bob"})) is None
    assert of_type(kernel, "wake.refused")[-1].data["why"] == "unavailable"


async def test_partial_usage_of_a_lost_turn_does_not_leak_into_the_next(kernel):
    await spawn(kernel, "bob")
    await set_budget(kernel, limits={"tokens": 1000}, estimate={"tokens": 100})
    await wake(kernel, "bob")
    await start_turn(kernel, "bob")
    await report(kernel, "bob", "usage", tokens=40, label="provider")

    await kernel.recover()

    with kernel._reading() as db:
        assert Budget(db).turn_usage("bob") == {}


async def test_a_failed_steer_leaves_the_running_turn_its_reservation(kernel):
    await spawn(kernel, "bob", role="steerer", ready={"boundaries": ["tool", "turn"]})
    await set_budget(kernel, limits={"turns": 9})
    await wake(kernel, "bob")
    await settle_effects(kernel, "bob")
    await start_turn(kernel, "bob")
    await wake(kernel, "bob")

    await fail_next_handover(kernel)

    assert limit(kernel, "turns")["held"] == 1
    await end_turn(kernel, "bob")
    assert limit(kernel, "turns")["spent"] == 1


async def test_a_failed_wake_returns_its_reservation(kernel):
    await spawn(kernel, "bob")
    await set_budget(kernel, limits={"turns": 9})
    await wake(kernel, "bob")
    assert limit(kernel, "turns")["held"] == 1

    await fail_next_handover(kernel)

    assert (limit(kernel, "turns")["held"], limit(kernel, "turns")["spent"]) == (0, 0)


async def test_a_failed_spawn_is_charged_nothing_and_blocks_nothing(kernel):
    await set_budget(kernel, limits={"tokens": 1000, "turns": 9}, estimate={"tokens": 100})
    args = {"name": "bob", "child_role": "worker", "goal": "x"}
    result_of(await kernel.submit(kernel.runtime, "agent.spawn", args))

    await report(kernel, "bob", "exited", reason="launch failed")

    row = limit(kernel, "tokens")
    assert (row["spent"], row["unmeasured"], limit(kernel, "turns")["spent"]) == (0, 0, 0)
    result_of(await kernel.submit(kernel.runtime, "agent.spawn", {**args, "name": "carol"}))


async def test_an_agent_ended_between_turns_is_charged_no_turn(kernel, ada):
    await spawn(kernel, "bob")
    await set_budget(kernel, limits={"tokens": 1000, "turns": 9}, estimate={"tokens": 100})
    await wake(kernel, "bob")

    result_of(await kernel.submit(ada, "agent.cancel", {"agent": "bob"}))

    assert (limit(kernel, "tokens")["unmeasured"], limit(kernel, "turns")["spent"]) == (0, 0)


async def test_exhausted_means_spent_and_never_merely_held(kernel):
    await spawn(kernel, "a")
    await spawn(kernel, "b")
    await set_budget(kernel, limits={"tokens": 100}, estimate={"tokens": 40})
    for name in ("a", "b"):
        await wake(kernel, name)
        await settle_effects(kernel, name)
        await start_turn(kernel, name)

    await report(kernel, "a", "usage", tokens=90, usd=0.0, label="provider")
    await end_turn(kernel, "a")

    assert result_of(kernel.query(kernel.runtime, "session.status", {}))["done"] is False


async def test_a_refused_wake_retries_when_a_failed_handover_returns_a_reservation(kernel):
    await spawn(kernel, "alice")
    await spawn(kernel, "bob")
    await set_budget(kernel, limits={"tokens": 100}, estimate={"tokens": 60})
    await wake(kernel, "alice")
    assert await wake(kernel, "bob") is None

    await fail_next_handover(kernel)

    assert "bob" in result_of(kernel.query(kernel.runtime, "delivery.ready", {}))["agents"]


async def test_a_refused_wake_retries_when_a_lost_turn_moves_the_budget(kernel):
    await spawn(kernel, "alice")
    await spawn(kernel, "bob")
    await set_budget(kernel, limits={"tokens": 1000}, estimate={"tokens": 700})
    await wake(kernel, "alice")
    await settle_effects(kernel, "alice")
    await start_turn(kernel, "alice")
    assert await wake(kernel, "bob") is None

    await kernel.recover()

    with kernel._reading() as db:
        assert Deliveries(db).blocked("bob") is None


async def test_measurements_carry_a_label_and_the_weakest_wins(kernel):
    await spawn(kernel, "bob")
    await set_budget(kernel, limits={"tokens": 1000})
    await wake(kernel, "bob")
    await start_turn(kernel, "bob")
    await report(kernel, "bob", "usage", tokens=10, label="provider")
    await report(kernel, "bob", "usage", tokens=10, label="lower_bound")

    await end_turn(kernel, "bob")

    assert limit(kernel, "tokens")["label"] == "lower_bound"


async def test_over_budget_is_policy_and_unavailable_is_infrastructure(kernel):
    await spawn(kernel, "bob")
    await set_budget(kernel, limits={"usd": 10.0}, estimate={"usd": 1.0})
    await wake(kernel, "bob")
    await start_turn(kernel, "bob")
    await report(kernel, "bob", "usage", label="unavailable")
    await end_turn(kernel, "bob")

    assert await wake(kernel, "bob") is None

    refused = of_type(kernel, "wake.refused")[-1]
    assert refused.data["why"] == "unavailable"
    row = limit(kernel, "usd")
    assert (row["spent"], row["label"], row["unmeasured"]) == (1.0, "unavailable", 1)


async def test_a_turn_with_no_usage_report_is_unmeasured_and_not_free(kernel):
    await spawn(kernel, "bob")
    await set_budget(kernel, limits={"usd": 10.0}, estimate={"usd": 1.0})
    await wake(kernel, "bob")
    await start_turn(kernel, "bob")

    await end_turn(kernel, "bob")

    row = limit(kernel, "usd")
    assert (row["spent"], row["label"], row["unmeasured"]) == (1.0, "unavailable", 1)


async def test_an_unmeasurable_unit_falls_back_to_turns_when_the_team_says_so(kernel):
    await spawn(kernel, "bob")
    await set_budget(kernel, limits={"usd": 10.0, "turns": 2}, fallback="turns")
    await wake(kernel, "bob")
    await start_turn(kernel, "bob")
    await end_turn(kernel, "bob")

    assert await wake(kernel, "bob") is not None
    await start_turn(kernel, "bob", "t2")
    await end_turn(kernel, "bob")

    assert await wake(kernel, "bob") is None
    assert of_type(kernel, "wake.refused")[-1].data["detail"]["unit"] == "turns"


async def test_a_fallback_needs_something_to_fall_back_to(kernel):
    outcome = await kernel.submit(kernel.runtime, "budget.set", {"limits": {"usd": 1.0}, "fallback": "turns"})

    assert refusal(outcome).code == "invalid"


async def test_an_agent_cannot_spend_past_wall_time(kernel, clock):
    await spawn(kernel, "bob")
    await set_budget(kernel, limits={"wall": 60})

    clock.advance(60)

    assert await wake(kernel, "bob") is None
    assert of_type(kernel, "wake.refused")[-1].data["detail"]["unit"] == "wall"


async def test_usage_unknown_is_not_zero(kernel):
    await spawn(kernel, "bob")

    rows = result_of(kernel.query(kernel.runtime, "view.watch", {"name": "roster"}))["rows"]

    assert rows[0]["usage"] == {}


async def test_budget_set_is_for_humans_and_programs(kernel):
    bob = await spawn(kernel, "bob")
    await kernel.submit(kernel.runtime, "grant.remove", {"who": "agent", "ops": "*", "on": "*"})

    assert refusal(await kernel.submit(bob, "budget.set", {"limits": {"turns": 9}})).code == "not_permitted"


turns = st.lists(st.tuples(st.integers(0, 3), st.integers(0, 500)), min_size=1, max_size=30)


@settings(max_examples=30, deadline=None)
@given(script=turns, cap=st.integers(100, 2000), estimate=st.integers(0, 300))
def test_overshoot_is_bounded_by_the_largest_turn_times_the_live_agents(
    tmp_path_factory, script, cap, estimate
) -> None:
    folder = tmp_path_factory.mktemp("budget") / "session"

    async def body() -> None:
        kernel = Kernel.open(folder, clock=ManualClock(1.0), extensions=PRIMITIVES)
        result_of(await kernel.submit(kernel.runtime, "session.open", {"roles": {"worker": {}}}))
        await grant(kernel, "agent")
        names = [f"a{index}" for index in range(4)]
        for name in names:
            await spawn(kernel, name)
        await set_budget(kernel, limits={"tokens": cap}, estimate={"tokens": estimate})
        running: set[str] = set()
        for index, cost in script:
            name = names[index]
            if name in running:
                await report(kernel, name, "usage", tokens=cost, label="provider")
                await end_turn(kernel, name)
                running.discard(name)
            elif await wake(kernel, name) is not None:
                await report(kernel, name, "turn.started", turn=f"t{kernel.head}")
                running.add(name)
        for name in sorted(running):
            await report(kernel, name, "usage", tokens=500, label="provider")
            await end_turn(kernel, name)
        spent = result_of(kernel.query(kernel.runtime, "budget.status", {}))[0]["spent"]
        assert spent <= cap + 500 * len(names)
        kernel.close()

    asyncio.run(body())
