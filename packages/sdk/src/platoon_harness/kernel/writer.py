"""The writer thread: one connection, group commit, ack after COMMIT."""

import asyncio
import fcntl
import logging
import math
import os
import queue
import resource
import sqlite3
import sys
import threading
from bisect import bisect_left
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter, process_time
from typing import Any

from .journal import Checkpointer, scrub_wal, truncate_wal
from .model import Gauges, JournalError, Refused
from .pulse import Pulse, settle

log = logging.getLogger("platoon_harness.kernel")

BATCH_LIMIT = 64
PRINCIPAL_LIMIT = 32
SESSION_LIMIT = 1024
RUNTIME_RESERVE = 256
ACK_BOUNDS = tuple(0.00001 * 2 ** (step / 4) for step in range(96))
"""The upper bounds, in seconds, of the buckets an ack's latency is counted in: a quarter octave apart from 10 µs to
about two minutes, past which one more bucket takes the rest."""


@dataclass(frozen=True)
class _Job:
    run: Callable[[sqlite3.Connection], Any]
    future: asyncio.Future[Any]
    owner: str | None
    queued: float


def _rank(counts: Sequence[int], share: float, slowest: float) -> float:
    """The latency below which `share` of the counted acks fall: the bound of the bucket that holds it, or the slowest
    ack where that is lower."""
    wanted, seen = math.ceil(share * sum(counts)), 0
    for bound, count in zip((*ACK_BOUNDS, math.inf), counts, strict=True):
        seen += count
        if seen >= wanted:
            return min(bound, slowest)
    return slowest


def _peak_resident_bytes() -> int | None:
    """The most memory this process has held, which Linux gives in KiB. Elsewhere the unit is unchecked."""
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024 if sys.platform == "linux" else None


class Writer:
    """Holds the journal for writing: the one connection, the lock and the checkpoints.

    Drains jobs into transactions of up to BATCH_LIMIT, so one fsync covers a whole batch. A batch that fails ends the
    writing, as a kill would: `failure` says why, every later job is refused with it, and the pulse closes before the
    batch's callers hear, so that whoever waits on the journal learns it at once, and whoever hears finds it closed.
    """

    def __init__(
        self,
        db: sqlite3.Connection,
        flock: int,
        path: Path,
        pulse: Pulse,
        seal: Callable[[sqlite3.Connection], int],
    ) -> None:
        self._db = db
        self._flock = flock
        self._path = path
        self._pulse = pulse
        self._seal = seal
        self._jobs: queue.SimpleQueue[_Job | None] = queue.SimpleQueue()
        self._lock = threading.Lock()
        self._depth = 0
        self._deepest = 0
        self._in_flight: Counter[str] = Counter()
        self._busy = 0
        self._began = perf_counter()
        self._first = pulse.head
        self._commits = 0
        self._acks = [0] * (len(ACK_BOUNDS) + 1)
        self._slowest = 0.0
        self._batch_seconds = 0.001
        self._stopping = False
        self.failure: JournalError | None = None
        self._checkpointer = Checkpointer(path)
        self._thread = threading.Thread(target=self._run, name="journal-writer", daemon=True)
        self._thread.start()

    async def call[T](self, run: Callable[[sqlite3.Connection], T], *, owner: str | None) -> T:
        """Run `run` on the writer thread and return once its transaction is durable."""
        job = _Job(run, asyncio.get_running_loop().create_future(), owner, perf_counter())
        self._admit(job)
        return await job.future

    def _admit(self, job: _Job) -> None:
        """Queue a job or refuse it. Queueing under the lock puts every job ahead of the stop."""
        owner = job.owner
        reserved = owner == "runtime"
        with self._lock:
            if self.failure is not None:
                raise Refused("unavailable", str(self.failure))
            if self._stopping:
                raise Refused("unavailable", "the kernel is closing")
            limit = SESSION_LIMIT + RUNTIME_RESERVE if reserved else SESSION_LIMIT
            if self._depth >= limit or (not reserved and owner and self._in_flight[owner] >= PRINCIPAL_LIMIT):
                self._busy += 1
                raise Refused("busy", retry_after=(self._depth / BATCH_LIMIT + 1) * self._batch_seconds)
            self._depth += 1
            self._deepest = max(self._deepest, self._depth)
            if owner:
                self._in_flight[owner] += 1
            self._jobs.put(job)

    def _done(self, job: _Job, answered: float) -> None:
        latency = answered - job.queued
        with self._lock:
            self._depth -= 1
            if job.owner:
                self._in_flight[job.owner] -= 1
                if not self._in_flight[job.owner]:
                    del self._in_flight[job.owner]
            self._acks[bisect_left(ACK_BOUNDS, latency)] += 1
            self._slowest = max(self._slowest, latency)

    def gauges(self) -> Gauges:
        """What this writer has measured since it opened the journal, and what the process holding it has used."""
        with self._lock:
            depth, deepest, in_flight, busy = self._depth, self._deepest, dict(self._in_flight), self._busy
            acks, slowest = list(self._acks), self._slowest
        answered = sum(acks)
        return Gauges(
            seconds=perf_counter() - self._began,
            events=self._pulse.head - self._first,
            commits=self._commits,
            depth=depth,
            deepest=deepest,
            in_flight=in_flight,
            busy=busy,
            acks=answered,
            ack_p50=_rank(acks, 0.5, slowest) if answered else None,
            ack_p99=_rank(acks, 0.99, slowest) if answered else None,
            ack_max=slowest if answered else None,
            cpu_seconds=process_time(),
            peak_resident_bytes=_peak_resident_bytes(),
        )

    def scrub(self) -> None:
        """Take erased bytes out of the WAL, or refuse `busy` while a reader holds them there."""
        if not scrub_wal(self._path):
            raise Refused("busy", "a reader is holding the WAL", retry_after=1.0)

    def stop(self) -> None:
        """Finish everything queued, checkpoint the WAL to empty, and let go of the journal. After a failed batch the
        WAL stays as a kill would leave it. Stopping again does nothing."""
        with self._lock:
            if self._stopping:
                return
            self._stopping = True
            self._jobs.put(None)
        self._thread.join()
        self._checkpointer.stop()
        try:
            if self.failure is None and not truncate_wal(self._db):
                log.warning("%s keeps a WAL: a reader held it, so the folder is not portable yet", self._path)
        finally:
            self._db.close()
            fcntl.flock(self._flock, fcntl.LOCK_UN)
            os.close(self._flock)

    def _run(self) -> None:
        running = True
        while running:
            first = self._jobs.get()
            if first is None:
                break
            jobs = [first]
            while len(jobs) < BATCH_LIMIT:
                try:
                    job = self._jobs.get_nowait()
                except queue.Empty:
                    break
                if job is None:
                    running = False
                    break
                jobs.append(job)
            if self.failure is None:
                self._commit(jobs)
            else:
                self._answer(jobs, [Refused("unavailable", str(self.failure))] * len(jobs), None)

    def _commit(self, jobs: list[_Job]) -> None:
        """One batch, in one transaction. One that fails is no command's own, and what it left is unknown."""
        db = self._db
        started = perf_counter()
        results: list[Any] = []
        head = None
        try:
            db.execute("BEGIN IMMEDIATE")
            for job in jobs:
                results.append(self._attempt(job))
            sealed = self._seal(db)
            db.execute("COMMIT")
            head = sealed
            self._commits += 1
        except BaseException as error:
            log.exception("batch of %d failed", len(jobs))
            self._roll_back()
            results = [Refused("unavailable", f"journal: {error}")] * len(jobs)
            with self._lock:
                self.failure = JournalError(f"{self._path}: a commit failed, so nothing more is recorded: {error}")
            self._pulse.close()
        self._answer(jobs, results, head)
        self._batch_seconds = perf_counter() - started

    def _answer(self, jobs: list[_Job], results: list[Any], head: int | None) -> None:
        """Callers hear their acks before followers hear the head move, so what a caller does on its ack, such as ending
        live text an item replaced, is done before a follower on its loop looks. A command is out of flight before its
        caller hears, so one that sends again at once is not refused over what it has heard of."""
        answered = perf_counter()
        for job in jobs:
            self._done(job, answered)
        woken = () if head is None else self._pulse.advance(head)
        acks = zip((job.future for job in jobs), results, strict=True)
        settle([*acks, *((waiter, None) for waiter in woken)])

    def _attempt(self, job: _Job) -> Any:
        """A refusal is the job's own. Anything else takes the batch with it."""
        try:
            return job.run(self._db)
        except Refused as refused:
            return refused

    def _roll_back(self) -> None:
        """Leave no batch behind. If that fails too, the next batch fails at BEGIN and says so."""
        try:
            if self._db.in_transaction:
                self._db.execute("ROLLBACK")
        except sqlite3.Error:
            log.exception("a rollback failed")
