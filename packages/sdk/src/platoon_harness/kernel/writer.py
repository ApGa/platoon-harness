"""The writer thread: one connection, group commit, ack after COMMIT."""

import asyncio
import logging
import queue
import sqlite3
import threading
import time
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .model import Refused
from .pulse import Pulse, settle

log = logging.getLogger("platoon_harness.kernel")

BATCH_LIMIT = 64
PRINCIPAL_LIMIT = 32
SESSION_LIMIT = 1024
RUNTIME_RESERVE = 256


@dataclass(frozen=True)
class _Job:
    run: Callable[[sqlite3.Connection], Any]
    future: asyncio.Future[Any]
    owner: str | None


class Writer:
    """Drains jobs into transactions of up to BATCH_LIMIT, so one fsync covers a whole batch."""

    def __init__(self, db: sqlite3.Connection, pulse: Pulse, seal: Callable[[sqlite3.Connection], int]) -> None:
        self._db = db
        self._pulse = pulse
        self._seal = seal
        self._jobs: queue.SimpleQueue[_Job | None] = queue.SimpleQueue()
        self._lock = threading.Lock()
        self._depth = 0
        self._inflight: Counter[str] = Counter()
        self._batch_seconds = 0.001
        self._stopping = False
        self._thread = threading.Thread(target=self._run, name="journal-writer", daemon=True)
        self._thread.start()

    async def call[T](self, run: Callable[[sqlite3.Connection], T], *, owner: str | None, runtime: bool = False) -> T:
        """Run `run` on the writer thread and return once its transaction is durable."""
        future = asyncio.get_running_loop().create_future()
        self._admit(owner, runtime)
        self._jobs.put(_Job(run, future, owner))
        return await future

    def _admit(self, owner: str | None, runtime: bool) -> None:
        with self._lock:
            if self._stopping:
                raise Refused("unavailable", "the kernel is closing")
            limit = SESSION_LIMIT + RUNTIME_RESERVE if runtime else SESSION_LIMIT
            if self._depth >= limit or (not runtime and owner and self._inflight[owner] >= PRINCIPAL_LIMIT):
                raise Refused("busy", retry_after=(self._depth / BATCH_LIMIT + 1) * self._batch_seconds)
            self._depth += 1
            if owner:
                self._inflight[owner] += 1

    def _done(self, job: _Job) -> None:
        with self._lock:
            self._depth -= 1
            if job.owner:
                self._inflight[job.owner] -= 1
                if not self._inflight[job.owner]:
                    del self._inflight[job.owner]

    def stop(self) -> None:
        """Finish everything queued, then end the thread."""
        with self._lock:
            self._stopping = True
        self._jobs.put(None)
        self._thread.join()

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
            self._commit(jobs)

    def _commit(self, jobs: list[_Job]) -> None:
        db = self._db
        started = time.perf_counter()
        results: list[Any] = []
        head = None
        try:
            db.execute("BEGIN IMMEDIATE")
            for job in jobs:
                results.append(self._attempt(job))
            head = self._seal(db)
            db.execute("COMMIT")
        except Exception as error:
            log.exception("batch of %d failed", len(jobs))
            if db.in_transaction:
                db.execute("ROLLBACK")
            results = [Refused("unavailable", f"journal: {error}")] * len(jobs)
            head = None
        if head is not None:
            self._pulse.head = head  # Whoever is acked must find their write under `head`.
        settle((job.future, result) for job, result in zip(jobs, results, strict=True))
        for job in jobs:
            self._done(job)
        if head is not None:
            self._pulse.publish(head)
        self._batch_seconds = time.perf_counter() - started

    def _attempt(self, job: _Job) -> Any:
        """A job's failure is its own, unless it took the transaction with it."""
        try:
            return job.run(self._db)
        except Exception as error:
            if not self._db.in_transaction:
                raise
            return error
