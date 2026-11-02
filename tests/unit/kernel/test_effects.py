"""Effects: an outbox with states, policies, priorities and a recovery path."""

from platoon_harness.kernel import Effects

from .support import refusal_of, result_of, supervised, until


async def dispatch(kernel, **args) -> str:
    return result_of(await kernel.submit(kernel.runtime, "note.dispatch", args))


async def start(kernel, effect: str) -> None:
    result_of(await kernel.submit(kernel.runtime, "effect.start", {"id": effect}))


def ready(kernel, **args) -> list[str]:
    return [row["id"] for row in result_of(kernel.query(kernel.runtime, "effect.ready", args))]


def state_of(kernel, effect: str) -> str:
    return Effects(kernel._db).get(effect).state


def types_of(kernel, effect: str) -> list[str]:
    return [e.type for e in kernel.read(kernel.runtime, after=0, match=f"effect/{effect}").events]


async def test_an_effect_moves_from_requested_to_finished(kernel):
    effect = await dispatch(kernel)
    assert state_of(kernel, effect) == "requested"
    assert ready(kernel) == [effect]

    await start(kernel, effect)
    assert state_of(kernel, effect) == "started"
    assert ready(kernel) == []

    result_of(await kernel.submit(kernel.runtime, "effect.finish", {"id": effect, "result": {"ok": True}}))
    assert state_of(kernel, effect) == "finished"
    assert types_of(kernel, effect) == ["effect.requested", "effect.started", "effect.finished"]


async def test_an_effect_can_fail(kernel):
    effect = await dispatch(kernel)
    await start(kernel, effect)
    result_of(await kernel.submit(kernel.runtime, "effect.fail", {"id": effect, "error": "no route"}))
    assert state_of(kernel, effect) == "failed"


async def test_effect_transitions_are_guarded(kernel):
    effect = await dispatch(kernel)
    assert refusal_of(await kernel.submit(kernel.runtime, "effect.finish", {"id": effect})) == "conflict"
    await start(kernel, effect)
    assert refusal_of(await kernel.submit(kernel.runtime, "effect.start", {"id": effect})) == "conflict"
    assert refusal_of(await kernel.submit(kernel.runtime, "effect.finish", {"id": "nope"})) == "not_found"


async def test_a_daemon_filters_by_kind(kernel):
    deliver = await dispatch(kernel, kind="deliver")
    launch = await dispatch(kernel, kind="launch")
    assert ready(kernel, kind="launch") == [launch]
    assert ready(kernel, kind="deliver") == [deliver]


async def test_effects_of_one_agent_run_in_order(kernel):
    first = await dispatch(kernel, agent="alice")
    second = await dispatch(kernel, agent="alice")
    other = await dispatch(kernel, agent="bob")

    assert ready(kernel) == [first, other]
    await start(kernel, first)
    assert ready(kernel) == [other]
    result_of(await kernel.submit(kernel.runtime, "effect.finish", {"id": first}))
    assert ready(kernel) == [second, other]


async def test_interrupt_bypasses_a_hanging_delivery(kernel):
    hanging = await dispatch(kernel, agent="alice")
    queued = await dispatch(kernel, agent="alice")
    await start(kernel, hanging)

    interrupt = await dispatch(kernel, kind="interrupt", agent="alice", priority=1)

    assert ready(kernel) == [interrupt]
    await dispatch(kernel, agent="alice")
    assert queued not in ready(kernel)


async def test_priority_runs_first(kernel):
    plain = await dispatch(kernel)
    urgent = await dispatch(kernel, priority=1)
    assert ready(kernel) == [urgent, plain]


async def test_a_stuck_effect_becomes_uncertain_at_its_timeout(kernel, clock):
    effect = await dispatch(kernel, timeout=30.0, on_uncertain="surface")

    async with supervised(kernel):
        await start(kernel, effect)
        await clock.sleeping()
        assert clock.wakes == [1030.0]
        head = kernel.head
        clock.advance(30)
        await until(kernel, "effect.uncertain", after=head)

    assert state_of(kernel, effect) == "uncertain"
    assert Effects(kernel._db).get(effect).deadline is None


async def test_a_finished_effect_cancels_its_timeout(kernel, clock):
    effect = await dispatch(kernel, timeout=30.0)
    await start(kernel, effect)
    result_of(await kernel.submit(kernel.runtime, "effect.finish", {"id": effect}))

    assert result_of(kernel.query(kernel.runtime, "timer.next", {})) == []


async def test_a_retried_attempt_gets_its_own_timeout(kernel, clock):
    effect = await dispatch(kernel, timeout=30.0, on_uncertain="retry")
    await start(kernel, effect)
    result_of(await kernel.submit(kernel.runtime, "effect.expire", {"id": effect, "attempt": 1}))
    assert state_of(kernel, effect) == "requested"

    await start(kernel, effect)

    result_of(await kernel.submit(kernel.runtime, "effect.expire", {"id": effect, "attempt": 1}))
    assert state_of(kernel, effect) == "started"
    assert Effects(kernel._db).get(effect).attempts == 2


async def test_recovery_marks_started_effects_uncertain(kernel):
    surfaced = await dispatch(kernel, on_uncertain="surface")
    retried = await dispatch(kernel, on_uncertain="retry")
    reconciled = await dispatch(kernel, on_uncertain="reconcile")
    untouched = await dispatch(kernel)
    for effect in (surfaced, retried, reconciled):
        await start(kernel, effect)

    outcome = await kernel.recover()

    assert outcome.refusal is None
    assert state_of(kernel, surfaced) == "uncertain"
    assert state_of(kernel, reconciled) == "uncertain"
    assert state_of(kernel, retried) == "requested"
    assert state_of(kernel, untouched) == "requested"
    assert types_of(kernel, retried)[-2:] == ["effect.uncertain", "effect.retried"]


async def test_reconciling_settles_an_uncertain_effect(kernel):
    effect = await dispatch(kernel, on_uncertain="reconcile")
    await start(kernel, effect)
    await kernel.recover()

    result_of(await kernel.submit(kernel.runtime, "effect.finish", {"id": effect}))

    assert state_of(kernel, effect) == "finished"


async def test_each_recovery_is_a_new_incarnation(kernel):
    await kernel.recover()
    await kernel.recover()
    versions = [e.version for e in kernel.read(kernel.runtime, after=0, match="runtime").events]
    assert versions == [1, 2]


async def test_recovery_leaves_no_timeout_behind(kernel):
    effect = await dispatch(kernel, timeout=30.0)
    await start(kernel, effect)

    await kernel.recover()

    assert result_of(kernel.query(kernel.runtime, "timer.next", {})) == []
