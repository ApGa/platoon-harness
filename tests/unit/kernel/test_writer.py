"""One writer thread: group commit, bounded admission, safe acks."""

import asyncio
import sqlite3

from platoon_harness.kernel import Args, Extension, JournalError, Kernel, Principal, Txn, op, writer
from platoon_harness.kernel.writer import BATCH_LIMIT, PRINCIPAL_LIMIT, RUNTIME_RESERVE, SESSION_LIMIT

from .support import HUMAN, enroll, events_of, grant, notes, refusal_of, result_of


async def hold_writer(kernel, gate) -> asyncio.Task:
    held = asyncio.create_task(kernel.submit(kernel.runtime, "gate.hold", {}))
    await gate.wait_entered()
    return held


async def test_a_batch_is_one_transaction_of_at_most_64_commands(kernel, gate):
    statements: list[str] = []
    db = kernel._writer._db
    db.set_trace_callback(statements.append)
    held = await hold_writer(kernel, gate)
    tasks = [asyncio.create_task(kernel.submit(kernel.runtime, "note.add", {})) for _ in range(150)]
    await asyncio.sleep(0)
    gate.release.set()
    await asyncio.gather(held, *tasks)
    db.set_trace_callback(None)

    sizes, size = [], 0
    for statement in statements:
        if statement == "COMMIT":
            sizes.append(size)
            size = 0
        elif statement == "SAVEPOINT command":
            size += 1
    assert sizes == [1, BATCH_LIMIT, BATCH_LIMIT, 150 - 2 * BATCH_LIMIT]


async def test_a_failed_commit_ends_the_writer_as_a_kill_would_and_a_retry_answers_from_the_next(folder, clock, gate):
    kernel = Kernel.open(folder, clock=clock, extensions=[notes, gate.extension()])
    held = await hold_writer(kernel, gate)
    seal = kernel._writer._seal
    faults = iter([None, OSError("disk gone")])

    def failing_seal(db):
        fault = next(faults, None)
        if fault is not None:
            raise fault
        return seal(db)

    kernel._writer._seal = failing_seal
    task = asyncio.create_task(kernel.submit(kernel.runtime, "note.add", {}, key="k"))
    await asyncio.sleep(0)
    gate.release.set()
    await held

    assert refusal_of(await task) == "unavailable"
    later = await kernel.submit(kernel.runtime, "note.add", {}, key="k")
    assert refusal_of(later) == "unavailable"
    assert "a commit failed" in later.refusal.detail and "journal.sqlite" in later.refusal.detail
    assert isinstance(kernel.failure, JournalError) and "disk gone" in str(kernel.failure)
    assert kernel.closed
    assert not await kernel._pulse.wait(kernel.head)
    kernel.close()
    kernel.close()

    again = Kernel.open(folder, clock=clock, extensions=[notes, gate.extension()])
    assert again.failure is None
    assert result_of(await again.submit(again.runtime, "note.add", {}, key="k"))
    assert [event.type for event in events_of(again)].count("note.added") == 1
    again.close()


async def test_a_caller_hears_its_commit_failed_only_once_the_kernel_has_closed(folder, clock, monkeypatch):
    """So whoever hears of the failure finds the kernel closed, however long the writer takes to go on."""
    kernel = Kernel.open(folder, clock=clock, extensions=[notes])
    real, closed = writer.settle, []

    def settling(outcomes):
        closed.append(kernel.closed)
        real(outcomes)

    def failing_seal(db):
        raise OSError("disk gone")

    monkeypatch.setattr(writer, "settle", settling)
    kernel._writer._seal = failing_seal

    assert refusal_of(await kernel.submit(kernel.runtime, "note.add", {})) == "unavailable"
    assert closed == [True]
    kernel.close()


async def test_a_failed_rollback_still_answers_and_ends_the_writer_loudly(folder, clock):
    class Broken:
        """A connection on a disk that has gone: nothing can be committed or rolled back."""

        def __init__(self, db):
            self.db = db

        def __getattr__(self, name):
            return getattr(self.db, name)

        def execute(self, sql, *args):
            if sql in ("COMMIT", "ROLLBACK"):
                raise sqlite3.OperationalError(f"disk I/O error on {sql}")
            return self.db.execute(sql, *args)

    kernel = Kernel.open(folder, clock=clock, extensions=[notes])
    real = kernel._writer._db
    kernel._writer._db = Broken(real)

    assert refusal_of(await kernel.submit(kernel.runtime, "note.add", {})) == "unavailable"
    assert refusal_of(await kernel.submit(kernel.runtime, "note.add", {})) == "unavailable"
    assert "disk I/O error on COMMIT" in str(kernel.failure)

    kernel._writer._db = real
    real.execute("ROLLBACK")
    kernel.close()


async def test_an_op_that_exits_does_not_end_the_writer(folder, clock):
    @op("exit.now", runtime=True)
    def exits(txn: Txn, a: Args) -> None:
        """Exit, as a library might."""
        raise SystemExit(3)

    kernel = Kernel.open(folder, clock=clock, extensions=[notes, Extension("exit", ops=[exits])])

    assert refusal_of(await kernel.submit(kernel.runtime, "exit.now", {})) == "unavailable"
    assert result_of(await kernel.submit(kernel.runtime, "note.add", {}))
    kernel.close()


async def test_a_command_admitted_as_the_kernel_closes_is_answered(folder, clock):
    kernel = Kernel.open(folder, clock=clock, extensions=[notes])
    writer = kernel._writer
    admit = writer._admit

    def racing(job):
        admit(job)
        kernel.close()

    writer._admit = racing

    assert result_of(await asyncio.wait_for(kernel.submit(kernel.runtime, "note.add", {}), 30))


async def test_a_principal_holds_at_most_32_inflight(kernel, gate):
    held = await hold_writer(kernel, gate)
    tasks = [asyncio.create_task(kernel.submit(HUMAN, "note.silence", {})) for _ in range(PRINCIPAL_LIMIT)]
    await asyncio.sleep(0)

    busy = await kernel.submit(HUMAN, "note.silence", {})
    other = asyncio.create_task(kernel.submit(Principal(id="human:bo"), "note.silence", {}))
    await asyncio.sleep(0)

    assert refusal_of(busy) == "busy"
    assert busy.refusal.retry_after > 0
    assert busy.seq is None
    assert not other.done()
    gate.release.set()
    await asyncio.gather(held, other, *tasks)


async def test_a_command_is_out_of_flight_before_its_caller_hears_of_it(kernel, monkeypatch):
    """So a caller that sends again as soon as it hears is never refused `busy` over what it has heard of."""
    real, in_flight = writer.settle, []

    def settling(outcomes):
        gauges = kernel.gauges()
        assert gauges is not None
        in_flight.append(sum(gauges.in_flight.values()))
        real(outcomes)

    monkeypatch.setattr(writer, "settle", settling)
    result_of(await kernel.submit(kernel.runtime, "note.add", {}))

    assert in_flight == [0]


async def test_the_writer_reports_its_depth_in_flight_and_ack_latency_by_public_names(folder, clock, gate, monkeypatch):
    """`Kernel.gauges`: what is queued now and whose, the most there were, the writes refused `busy`, and how long each
    write waited for its answer, a percentile read from the bucket that holds it. A read-only kernel has none."""
    now = [100.0]
    monkeypatch.setattr(writer, "perf_counter", lambda: now[0])
    kernel = Kernel.open(folder, clock=clock, extensions=[notes, gate.extension()])
    fresh = kernel.gauges()
    held = await hold_writer(kernel, gate)
    tasks = [asyncio.create_task(kernel.submit(HUMAN, "note.silence", {})) for _ in range(PRINCIPAL_LIMIT)]
    await asyncio.sleep(0)
    assert refusal_of(await kernel.submit(HUMAN, "note.silence", {})) == "busy"
    during = kernel.gauges()
    now[0] = 100.003
    gate.release.set()
    await asyncio.gather(held, *tasks)
    gate.entered.clear()
    gate.release.clear()
    now[0] = 200.0
    held = await hold_writer(kernel, gate)
    now[0] = 200.5
    gate.release.set()
    await held
    after = kernel.gauges()
    kernel.close()
    closed = Kernel.open(folder, clock=clock, extensions=[notes, gate.extension()], read_only=True)

    assert fresh is not None and during is not None and after is not None
    assert (fresh.depth, fresh.in_flight, fresh.acks, fresh.events, fresh.commits) == (0, {}, 0, 0, 0)
    assert fresh.ack_p50 is fresh.ack_p99 is fresh.ack_max is None
    assert (during.depth, during.deepest, during.busy) == (PRINCIPAL_LIMIT + 1, PRINCIPAL_LIMIT + 1, 1)
    assert during.in_flight == {"runtime": 1, HUMAN.id: PRINCIPAL_LIMIT}
    assert (after.depth, after.in_flight, after.deepest, after.busy) == (0, {}, PRINCIPAL_LIMIT + 1, 1)
    assert (after.acks, after.events, after.commits) == (PRINCIPAL_LIMIT + 2, PRINCIPAL_LIMIT + 2, 3)
    assert after.seconds == 100.5
    assert 0.003 <= after.ack_p50 < 0.003 * 2 ** (1 / 4) and after.ack_p99 == after.ack_max == 0.5
    assert after.cpu_seconds > 0 and (after.peak_resident_bytes or 0) > 0
    assert closed.gauges() is None
    closed.close()


async def test_runtime_principals_have_reserved_capacity(kernel, gate):
    held = await hold_writer(kernel, gate)
    tasks = [
        asyncio.create_task(kernel.submit(Principal(id=f"human:h{n // PRINCIPAL_LIMIT}"), "note.silence", {}))
        for n in range(SESSION_LIMIT - 1)
    ]
    await asyncio.sleep(0)

    assert refusal_of(await kernel.submit(Principal(id="human:late"), "note.silence", {})) == "busy"
    reserved = [asyncio.create_task(kernel.submit(kernel.runtime, "note.add", {})) for _ in range(RUNTIME_RESERVE)]
    await asyncio.sleep(0)
    assert refusal_of(await kernel.submit(kernel.runtime, "note.add", {})) == "busy"

    gate.release.set()
    await asyncio.gather(held, *tasks)
    assert all(outcome.refusal is None for outcome in await asyncio.gather(*reserved))


async def test_busy_is_not_journaled_and_a_retry_goes_through(kernel, gate):
    await enroll(kernel, HUMAN)
    await grant(kernel, "human:ada")
    held = await hold_writer(kernel, gate)
    tasks = [asyncio.create_task(kernel.submit(HUMAN, "note.silence", {})) for _ in range(PRINCIPAL_LIMIT)]
    await asyncio.sleep(0)
    assert refusal_of(await kernel.submit(HUMAN, "note.add", {}, key="k")) == "busy"
    gate.release.set()
    await asyncio.gather(held, *tasks)

    assert result_of(await kernel.submit(HUMAN, "note.add", {}, key="k"))


def test_an_ack_to_a_closed_loop_is_dropped(folder, clock, gate):
    kernel = Kernel.open(folder, clock=clock, extensions=[notes, gate.extension()])
    loop = asyncio.new_event_loop()
    task = loop.create_task(kernel.submit(kernel.runtime, "gate.hold", {}))
    loop.run_until_complete(asyncio.sleep(0))
    assert gate.entered.wait(30)
    task.cancel()
    loop.run_until_complete(asyncio.gather(task, return_exceptions=True))
    loop.close()

    gate.release.set()

    assert result_of(asyncio.run(kernel.submit(kernel.runtime, "note.add", {})))
    kernel.close()


def test_a_loop_that_stops_before_the_ack_loses_nothing(folder, clock, gate):
    kernel = Kernel.open(folder, clock=clock, extensions=[notes, gate.extension()])
    loop = asyncio.new_event_loop()
    task = loop.create_task(kernel.submit(kernel.runtime, "gate.hold", {}))
    loop.run_until_complete(asyncio.sleep(0))
    assert gate.entered.wait(30)
    gate.release.set()
    kernel.close()

    loop.run_until_complete(task)
    loop.close()
