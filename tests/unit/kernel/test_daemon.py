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
        await clock.sleeping()
        assert clock.wakes == [pytest.approx(clock.now() + delay)]
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

    waits = []
    for _ in range(12):
        await clock.sleeping()
        waits.append(clock.wakes[0] - clock.now())
        clock.advance(waits[-1])

    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    kernel.close()
    assert max(waits) == 30.0


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
        await clock.sleeping()
        clock.advance(delay)
    await clock.sleeping()

    assert clock.wakes == [pytest.approx(clock.now() + 0.1)]
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
