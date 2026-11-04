"""Timers: set by an event, fired by the clock daemon, moved only by the injected clock."""

import asyncio
import sqlite3

import pytest

from platoon_harness.kernel import Kernel, Timers
from platoon_harness.kernel.timers import fire_timers

from .support import events_of, notes, refusal_of, result_of, supervised, until


async def remind(kernel, due: float, key: str) -> None:
    result_of(await kernel.submit(kernel.runtime, "note.remind", {"due": due, "key": key}))


def reminders(kernel) -> list[str]:
    return result_of(kernel.query(kernel.runtime, "note.list", {"stream": "note/reminders"}))


def pending(kernel) -> list[str]:
    return [timer["key"] for timer in result_of(kernel.query(kernel.runtime, "timer.next", {}))]


async def test_a_timer_does_not_fire_before_it_is_due(kernel, clock):
    await remind(kernel, 1010.0, "ring")

    assert await fire_timers(kernel) == 1010.0

    assert reminders(kernel) == []
    assert pending(kernel) == ["ring"]


async def test_a_due_timer_fires_as_a_runtime_command(kernel, clock):
    await remind(kernel, 1010.0, "ring")
    clock.advance(10)

    assert await fire_timers(kernel) is None

    assert reminders(kernel) == ["ring"]
    assert pending(kernel) == []
    fired = next(event for event in events_of(kernel) if event.type == "note.added")
    assert fired.actor == "runtime"
    assert fired.outcome.key == "ring"


async def test_timers_fire_in_due_order(kernel, clock):
    await remind(kernel, 1020.0, "late")
    await remind(kernel, 1010.0, "early")
    clock.advance(30)

    await fire_timers(kernel)

    assert reminders(kernel) == ["early", "late"]


async def test_a_refiring_after_a_crash_runs_the_op_once(kernel, clock):
    await remind(kernel, 1000.0, "ring")
    first = result_of(
        await kernel.submit(kernel.runtime, "note.add", {"stream": "note/reminders", "text": "ring"}, key="ring")
    )
    head = kernel.head

    await fire_timers(kernel)

    assert reminders(kernel) == ["ring"]
    assert first["version"] == 1
    assert [event.type for event in events_of(kernel, after=head)] == ["timer.cleared"]


async def test_a_firing_lost_to_a_failed_commit_stays_set_for_the_next_kernel(folder, clock):
    kernel = Kernel.open(folder, clock=clock, extensions=[notes])
    await remind(kernel, 1000.0, "ring")

    def failing(db):
        raise sqlite3.OperationalError("disk I/O error")

    kernel._writer._seal = failing

    assert await fire_timers(kernel) == 1001.0
    assert kernel.failure is not None
    kernel.close()

    again = Kernel.open(folder, clock=clock, extensions=[notes])
    assert pending(again) == ["ring"]
    assert reminders(again) == []
    assert await fire_timers(again) is None
    assert reminders(again) == ["ring"]
    assert pending(again) == []
    again.close()


async def test_a_busy_firing_stays_set_until_told_when_to_retry(kernel, clock, gate):
    await remind(kernel, 1000.0, "ring")
    held = asyncio.create_task(kernel.submit(kernel.runtime, "gate.hold", {}))
    await gate.wait_entered()
    tasks = [asyncio.create_task(kernel.submit(kernel.runtime, "note.silence", {})) for _ in range(1279)]
    await asyncio.sleep(0)

    due = await fire_timers(kernel)

    assert due > 1000.0
    assert pending(kernel) == ["ring"]
    gate.release.set()
    await asyncio.gather(held, *tasks)


async def test_an_exposed_op_can_fire(kernel, clock):
    timer = {"due": 1000.0, "op": "note.read", "args": {}, "key": "peek"}
    args = {"type": "timer.set", "stream": "timer/peek", "data": timer}
    result_of(await kernel.submit(kernel.runtime, "note.mark", args))

    assert await fire_timers(kernel) is None

    assert pending(kernel) == []


@pytest.mark.parametrize("field", ["key", "op"])
async def test_a_timer_name_past_the_limit_cannot_be_set(kernel, field):
    timer = {"due": 1000.0, "op": "note.add", "args": {}, "key": "k"} | {field: "x" * 257}
    args = {"type": "timer.set", "stream": "timer/k", "data": timer}
    assert refusal_of(await kernel.submit(kernel.runtime, "note.mark", args)) == "unavailable"
    assert pending(kernel) == []


async def test_a_timer_at_the_limit_fires_and_clears(kernel, clock):
    await remind(kernel, 1000.0, "k" * 256)

    await fire_timers(kernel)

    assert reminders(kernel) == ["k" * 256]
    assert pending(kernel) == []


async def test_the_clock_daemon_sleeps_until_the_next_due_time(kernel, clock):
    await remind(kernel, 1010.0, "ring")

    async with supervised(kernel):
        await clock.sleeping()
        assert clock.wakes == [1010.0]
        head = kernel.head
        clock.advance(10)
        await until(kernel, "note.added", after=head)

    assert reminders(kernel) == ["ring"]


async def test_a_new_earlier_timer_wakes_the_daemon(kernel, clock):
    await remind(kernel, 1100.0, "late")

    async with supervised(kernel):
        await clock.sleeping()
        head = kernel.head
        await remind(kernel, 1010.0, "early")
        await clock.slept_until(1010.0)
        clock.advance(10)
        await until(kernel, "timer.cleared", after=head)

    assert reminders(kernel) == ["early"]
    assert pending(kernel) == ["late"]


async def test_timers_survive_a_restart(folder, clock, kernel):
    await remind(kernel, 1010.0, "ring")
    assert pending(kernel) == ["ring"]
    kernel.close()

    again = Kernel.open(folder, clock=clock, extensions=[notes])
    clock.advance(10)
    await fire_timers(again)
    assert reminders(again) == ["ring"]
    again.close()


async def test_a_refused_timer_is_still_cleared(kernel, clock):
    timer = {"due": 1000.0, "op": "note.nope", "args": {}, "key": "doomed"}
    args = {"type": "timer.set", "stream": "timer/doomed", "data": timer}
    result_of(await kernel.submit(kernel.runtime, "note.mark", args))

    await fire_timers(kernel)

    assert pending(kernel) == []
    assert events_of(kernel)[-2].type == "op.refused"


async def test_timers_left_out_hide_no_timer_to_come(kernel):
    async def set_timer(op: str, key: str, due: float) -> None:
        timer = {"due": due, "op": op, "args": {}, "key": key}
        args = {"type": "timer.set", "stream": f"timer/{key}", "data": timer}
        result_of(await kernel.submit(kernel.runtime, "note.mark", args))

    for number in range(70):
        await set_timer("lease.expire", f"lease/{number}", 1010.0 + number)
    await set_timer("note.add", "later", 9000.0)

    with kernel._reading() as db:
        assert Timers(db).besides("lease.expire")
        assert not Timers(db).besides("lease.expire", "note.add")
