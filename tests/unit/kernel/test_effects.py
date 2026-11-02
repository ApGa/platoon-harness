"""Effects: an outbox with states, policies, priorities and a recovery path."""

from platoon_harness.kernel import Effect, Effects

from .support import events_of, refusal_of, result_of, supervised, until


async def dispatch(kernel, **args) -> int:
    return result_of(await kernel.submit(kernel.runtime, "note.dispatch", args))


async def start(kernel, effect: int) -> int:
    return result_of(await kernel.submit(kernel.runtime, "effect.start", {"id": effect}))


async def finish(kernel, effect: int, attempt: int = 1) -> None:
    result_of(await kernel.submit(kernel.runtime, "effect.finish", {"id": effect, "attempt": attempt}))


def ready(kernel, **args) -> list[int]:
    return [row["id"] for row in result_of(kernel.query(kernel.runtime, "effect.ready", args))]


def effect_of(kernel, effect: int) -> Effect:
    with kernel._reading() as db:
        found = Effects(db).get(effect)
    assert found is not None
    return found


def state_of(kernel, effect: int) -> str:
    return effect_of(kernel, effect).state


def types_of(kernel, effect: int) -> list[str]:
    return [e.type for e in kernel.read(kernel.runtime, after=0, match=f"effect/{effect}").events]


async def test_an_effect_moves_from_requested_to_finished(kernel):
    effect = await dispatch(kernel)
    assert state_of(kernel, effect) == "requested"
    assert ready(kernel) == [effect]

    attempt = await start(kernel, effect)
    assert attempt == 1
    assert state_of(kernel, effect) == "started"
    assert ready(kernel) == []

    args = {"id": effect, "attempt": attempt, "result": {"ok": True}}
    result_of(await kernel.submit(kernel.runtime, "effect.finish", args))
    assert state_of(kernel, effect) == "finished"
    assert types_of(kernel, effect) == ["effect.requested", "effect.started", "effect.finished"]


async def test_an_effects_id_is_the_seq_of_its_request(kernel):
    effect = await dispatch(kernel)
    assert next(e for e in events_of(kernel) if e.type == "effect.requested").seq == effect


async def test_an_effect_can_fail(kernel):
    effect = await dispatch(kernel)
    await start(kernel, effect)
    result_of(await kernel.submit(kernel.runtime, "effect.fail", {"id": effect, "attempt": 1, "error": "no route"}))
    assert state_of(kernel, effect) == "failed"


async def test_a_long_error_still_fails_the_effect(kernel):
    effect = await dispatch(kernel)
    await start(kernel, effect)

    args = {"id": effect, "attempt": 1, "error": "x" * 20000}
    result_of(await kernel.submit(kernel.runtime, "effect.fail", args))

    failed = next(e for e in events_of(kernel) if e.type == "effect.failed")
    assert state_of(kernel, effect) == "failed"
    assert failed.data["error"].endswith("[cut]")


async def test_effect_transitions_are_guarded(kernel):
    effect = await dispatch(kernel)
    finishing = {"id": effect, "attempt": 1}
    assert refusal_of(await kernel.submit(kernel.runtime, "effect.finish", finishing)) == "conflict"
    await start(kernel, effect)
    assert refusal_of(await kernel.submit(kernel.runtime, "effect.start", {"id": effect})) == "conflict"
    missing = {"id": 999, "attempt": 1}
    assert refusal_of(await kernel.submit(kernel.runtime, "effect.finish", missing)) == "not_found"


async def test_a_late_report_cannot_settle_a_newer_attempt(kernel):
    effect = await dispatch(kernel, timeout=30.0, on_uncertain="retry")
    assert await start(kernel, effect) == 1
    result_of(await kernel.submit(kernel.runtime, "effect.expire", {"id": effect, "attempt": 1}))
    assert await start(kernel, effect) == 2

    late = await kernel.submit(kernel.runtime, "effect.fail", {"id": effect, "attempt": 1, "error": "lost my socket"})

    assert refusal_of(late) == "conflict"
    assert state_of(kernel, effect) == "started"
    await finish(kernel, effect, attempt=2)
    assert state_of(kernel, effect) == "finished"


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
    await finish(kernel, first)
    assert ready(kernel) == [second, other]


async def test_interrupt_bypasses_a_hanging_delivery(kernel):
    hanging = await dispatch(kernel, agent="alice")
    queued = await dispatch(kernel, agent="alice")
    await start(kernel, hanging)

    interrupt = await dispatch(kernel, kind="interrupt", agent="alice", priority=1)

    assert ready(kernel) == [interrupt]
    await dispatch(kernel, agent="alice")
    assert queued not in ready(kernel)


async def test_an_effect_after_another_waits_for_it_to_finish(kernel):
    first = await dispatch(kernel, kind="admit")
    second = await dispatch(kernel, kind="launch", after=first)

    assert ready(kernel) == [first]
    await start(kernel, first)
    await finish(kernel, first)

    assert ready(kernel) == [second]


async def test_a_failure_stops_what_depended_on_it(kernel):
    first = await dispatch(kernel, kind="admit")
    second = await dispatch(kernel, kind="launch", after=first)
    attempt = await start(kernel, first)
    result_of(await kernel.submit(kernel.runtime, "effect.fail", {"id": first, "attempt": attempt, "error": "no"}))

    assert second not in ready(kernel)


async def test_a_cancelled_effect_never_starts(kernel):
    effect = await dispatch(kernel, agent="alice")
    queued = await dispatch(kernel, agent="alice")

    result_of(await kernel.submit(kernel.runtime, "note.cancel", {"id": effect}))

    assert state_of(kernel, effect) == "cancelled"
    assert ready(kernel) == [queued]


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


async def test_a_finished_effect_cancels_its_timeout(kernel, clock):
    effect = await dispatch(kernel, timeout=30.0)
    await start(kernel, effect)
    await finish(kernel, effect)

    assert result_of(kernel.query(kernel.runtime, "timer.next", {})) == []


async def test_a_retried_attempt_gets_its_own_timeout(kernel, clock):
    effect = await dispatch(kernel, timeout=30.0, on_uncertain="retry")
    await start(kernel, effect)
    result_of(await kernel.submit(kernel.runtime, "effect.expire", {"id": effect, "attempt": 1}))
    assert state_of(kernel, effect) == "requested"

    await start(kernel, effect)

    result_of(await kernel.submit(kernel.runtime, "effect.expire", {"id": effect, "attempt": 1}))
    assert state_of(kernel, effect) == "started"
    assert effect_of(kernel, effect).attempts == 2


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


async def test_recovery_loses_a_turn_in_flight(kernel):
    args = {"type": "turn.started", "stream": "turn/alice", "agent": "alice", "data": {"turn": "t1"}}
    result_of(await kernel.submit(kernel.runtime, "note.mark", args))

    await kernel.recover()

    lost = events_of(kernel)[-1]
    assert (lost.type, lost.agent, lost.turn, lost.data) == ("turn.lost", "alice", "t1", {"gap": "crash_window"})
    after = {"type": "agent.reported", "stream": "agent/alice", "agent": "alice"}
    assert result_of(await kernel.submit(kernel.runtime, "note.mark", after))["turn"] is None


async def test_reconciling_settles_an_uncertain_effect(kernel):
    effect = await dispatch(kernel, on_uncertain="reconcile")
    await start(kernel, effect)
    await kernel.recover()

    await finish(kernel, effect)

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


async def test_effects_can_be_listed_by_state_for_recovery(kernel):
    reconciled = await dispatch(kernel, on_uncertain="reconcile")
    await start(kernel, reconciled)
    await kernel.recover()

    listed = result_of(kernel.query(kernel.runtime, "effect.list", {"state": "uncertain"}))

    assert [row["id"] for row in listed] == [reconciled]


async def test_an_incarnation_is_numbered_from_one(kernel):
    assert result_of(await kernel.recover()) == 1
    assert result_of(await kernel.recover()) == 2
