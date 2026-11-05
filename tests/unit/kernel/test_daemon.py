"""The supervisor: one for one, with backoff on the injected clock."""

import asyncio

import pytest

from platoon_harness.kernel import Daemon, Extension, Kernel, Refused
from platoon_harness.kernel.daemon import keep_running

from .support import refused_code


def open_with(folder, clock, *daemons) -> Kernel:
    return Kernel.open(folder, clock=clock, extensions=[Extension("test", daemons=list(daemons))])


async def test_a_failed_daemon_restarts_with_doubling_backoff(folder, clock):
    starts = []
    healthy = asyncio.Event()

    async def flaky(kernel: Kernel) -> None:
        starts.append(clock.now())
        if len(starts) == 4:
            healthy.set()
            return
        raise RuntimeError("no luck")

    kernel = open_with(folder, clock, Daemon("flaky", flaky))
    task = asyncio.create_task(kernel.supervise())

    for delay in (0.1, 0.2, 0.4):
        await clock.slept_until(clock.now() + delay)
        clock.advance(delay)
    await healthy.wait()

    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    kernel.close()
    assert len(starts) == 4


async def test_backoff_is_capped(folder, clock):
    async def broken(kernel: Kernel) -> None:
        raise RuntimeError("always")

    kernel = open_with(folder, clock, Daemon("broken", broken))
    task = asyncio.create_task(kernel.supervise())

    for delay in (0.1, 0.2, 0.4, 0.8, 1.6, 3.2, 6.4, 12.8, 25.6, 30.0, 30.0, 30.0):
        await clock.slept_until(clock.now() + min(delay, 30.0))
        clock.advance(delay)

    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    kernel.close()


async def test_a_run_that_lasted_forgives_earlier_failures(folder, clock):
    runs = []

    async def fails_late(kernel: Kernel) -> None:
        runs.append(1)
        if len(runs) == 3:
            await clock.sleep(120)
        raise RuntimeError("again")

    kernel = open_with(folder, clock, Daemon("late", fails_late))
    task = asyncio.create_task(kernel.supervise())
    for delay in (0.1, 0.2, 120):
        await clock.slept_until(clock.now() + delay)
        clock.advance(delay)

    await clock.slept_until(clock.now() + 0.1)
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    kernel.close()


async def test_daemons_fail_one_for_one(folder, clock):
    calm_cancelled = asyncio.Event()
    calm_running = asyncio.Event()

    async def calm(kernel: Kernel) -> None:
        calm_running.set()
        try:
            await asyncio.Event().wait()
        finally:
            calm_cancelled.set()

    async def broken(kernel: Kernel) -> None:
        raise RuntimeError("always")

    kernel = open_with(folder, clock, Daemon("calm", calm), Daemon("broken", broken))
    task = asyncio.create_task(kernel.supervise())
    await calm_running.wait()
    await clock.sleeping()
    clock.advance(0.1)
    await clock.sleeping()

    assert not calm_cancelled.is_set()
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    kernel.close()
    assert calm_cancelled.is_set()


async def test_a_daemon_that_returns_is_not_restarted(folder, clock):
    runs = []

    async def once(kernel: Kernel) -> None:
        runs.append(1)

    kernel = Kernel.open(folder, clock=clock)
    await keep_running(Daemon("once", once), kernel)
    kernel.close()
    assert runs == [1]


async def test_a_read_only_kernel_runs_no_daemons(folder, clock):
    Kernel.open(folder, clock=clock).close()
    reader = Kernel.open(folder, clock=clock, read_only=True)
    with pytest.raises(Refused) as error:
        await reader.supervise()
    assert refused_code(error) == "unsupported"
    reader.close()


async def test_closing_during_a_failure_stops_the_supervisor(folder, clock):
    async def tries_after_close(kernel: Kernel) -> None:
        kernel.close()
        raise RuntimeError("closed under me")

    kernel = open_with(folder, clock, Daemon("closing", tries_after_close))
    await kernel.supervise()


def said(kernel: Kernel) -> list[tuple[str, str]]:
    return [(event.type, event.gist) for event in kernel.read(kernel.runtime).events if event.stream == "daemon/flaky"]


async def test_a_daemon_that_keeps_failing_is_said_at_each_new_error_until_a_run_of_it_lasts_a_minute(folder, clock):
    """A failure is journaled when it begins a run of them and when it says another error than the last, and so is the
    next run that lasts, which the supervisor already took as forgiving what came before: a daemon that fails on every
    pass with one error is said once, not once a pass, and what is said last is its latest error."""
    errors = iter(["no luck", "no luck", "worse"])
    runs = []
    lasting = asyncio.Event()

    async def flaky(kernel: Kernel) -> None:
        runs.append(clock.now())
        if len(runs) in (4, 5):
            lasting.set()
            await clock.sleep(600)
        raise RuntimeError(next(errors, f"pass {len(runs)}"))

    kernel = open_with(folder, clock, Daemon("flaky", flaky))
    task = asyncio.create_task(kernel.supervise())
    for delay in (0.1, 0.2, 0.4):
        await clock.slept_until(clock.now() + delay)
        clock.advance(delay)
    await lasting.wait()
    failing = said(kernel)
    clock.advance(60)
    await until_said(kernel, 3)
    clock.advance(600)
    await until_said(kernel, 4)
    lasting.clear()
    await clock.slept_until(clock.now() + 0.1)
    clock.advance(0.1)
    await lasting.wait()
    clock.advance(60)
    await until_said(kernel, 5)

    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    events = said(kernel)
    kernel.close()
    failed = "flaky failed and is restarted with backoff, its traceback in the session folder's runtime.log, and"
    assert [gist.partition(" `session stop`")[0] for _, gist in failing] == [failed, failed]
    assert [gist.rpartition(": ")[2] for _, gist in failing] == ["no luck", "worse"]
    assert [type for type, _ in events] == [
        "daemon.failed",
        "daemon.failed",
        "daemon.recovered",
        "daemon.failed",
        "daemon.recovered",
    ]
    assert events[3][1].endswith("RuntimeError: pass 4")


async def until_said(kernel: Kernel, count: int) -> None:
    while len(said(kernel)) < count:
        head = kernel.head
        await kernel.changed(head)


async def test_a_daemon_that_never_failed_says_nothing(folder, clock):
    done = asyncio.Event()

    async def calm(kernel: Kernel) -> None:
        await clock.sleep(600)
        done.set()

    kernel = open_with(folder, clock, Daemon("flaky", calm))
    task = asyncio.create_task(kernel.supervise())
    await clock.slept_until(clock.now() + 600)
    clock.advance(600)
    await done.wait()
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    events = said(kernel)
    kernel.close()

    assert events == []
