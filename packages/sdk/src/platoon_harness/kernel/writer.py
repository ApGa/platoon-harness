"""The writer thread: one connection, group commit, ack after COMMIT."""

import asyncio
import fcntl
import logging
import os
import queue
import sqlite3
import threading
import time
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .journal import Checkpointer, scrub_wal, truncate_wal
from .model import JournalError, Refused
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
        self._inflight: Counter[str] = Counter()
        self._batch_seconds = 0.001
        self._stopping = False
        self.failure: JournalError | None = None
        self._checkpointer = Checkpointer(path)
        self._thread = threading.Thread(target=self._run, name="journal-writer", daemon=True)
        self._thread.start()

    async def call[T](self, run: Callable[[sqlite3.Connection], T], *, owner: str | None) -> T:
        """Run `run` on the writer thread and return once its transaction is durable."""
        job = _Job(run, asyncio.get_running_loop().create_future(), owner)
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
            if self._depth >= limit or (not reserved and owner and self._inflight[owner] >= PRINCIPAL_LIMIT):
                raise Refused("busy", retry_after=(self._depth / BATCH_LIMIT + 1) * self._batch_seconds)
            self._depth += 1
            if owner:
                self._inflight[owner] += 1
            self._jobs.put(job)

    def _done(self, job: _Job) -> None:
        with self._lock:
            self._depth -= 1
            if job.owner:
                self._inflight[job.owner] -= 1
                if not self._inflight[job.owner]:
                    del self._inflight[job.owner]

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
        started = time.perf_counter()
        results: list[Any] = []
        head = None
        try:
            db.execute("BEGIN IMMEDIATE")
            for job in jobs:
                results.append(self._attempt(job))
            sealed = self._seal(db)
            db.execute("COMMIT")
            head = sealed
        except BaseException as error:
            log.exception("batch of %d failed", len(jobs))
            self._roll_back()
            results = [Refused("unavailable", f"journal: {error}")] * len(jobs)
            with self._lock:
                self.failure = JournalError(f"{self._path}: a commit failed, so nothing more is recorded: {error}")
            self._pulse.close()
        self._answer(jobs, results, head)
        self._batch_seconds = time.perf_counter() - started

    def _answer(self, jobs: list[_Job], results: list[Any], head: int | None) -> None:
        """Callers hear their acks before followers hear the head move, so what a caller does on its ack, such as ending
        live text an item replaced, is done before a follower on its loop looks. A command is out of flight before its
        caller hears, so one that sends again at once is not refused over what it has heard of."""
        for job in jobs:
            self._done(job)
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
