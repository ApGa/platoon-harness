"""The kernel: one journal, one writer, and every way in and out."""

import asyncio
import fcntl
import hashlib
import logging
import os
import queue
import sqlite3
from collections import defaultdict
from collections.abc import AsyncIterator, Callable, Generator, Iterable, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from .auth import Principals, authorize
from .bodies import Blobs, forget, lookup, record
from .clock import Clock, SystemClock
from .core import CORE, list_ops
from .daemon import keep_running
from .extension import Extension, Loaded, load
from .journal import (
    Checkpointer,
    decode,
    head,
    is_live,
    open_reader,
    open_writer,
    reader_uri,
    require_local,
    stream_version,
    take_lock,
)
from .model import (
    BODY_LIMIT,
    DATA_LIMIT,
    GIST_LIMIT,
    Delta,
    Event,
    Outcome,
    Page,
    Principal,
    Refusal,
    Refused,
    args_hash,
    canonical,
    hash_token,
    jsonable,
)
from .op import Args, Op
from .pulse import Pulse, Ring, Tail
from .txn import Commands, Txn
from .view import View, rebuild
from .writer import Writer

log = logging.getLogger("platoon_harness.kernel")

_NAME_LIMIT = 256
_DETAIL_LIMIT = 512
_SCAN_LIMIT = 4096
_IDLE_READERS = 4


@dataclass(frozen=True)
class _Command:
    principal: Principal
    op: str
    args: Mapping[str, Any]
    args_hash: str
    key: str | None = None
    expected_version: int | None = None

    def refused(self, refusal: Refusal, target: str | None) -> Outcome:
        filled = refusal.model_copy(update={"op": self.op, "object": target})
        return Outcome(op=self.op, key=self.key, args_hash=self.args_hash, refusal=filled)

    def answered(self, result: Any) -> Outcome:
        return Outcome(op=self.op, key=self.key, args_hash=self.args_hash, result=result)


class Kernel:
    """One session's journal, reached through `submit`, `query`, `read`, `follow` and `deltas`.

    Closing checkpoints the WAL to empty, which is what makes the folder portable.
    """

    runtime = Principal(id="runtime")

    def __init__(self, folder: Path, clock: Clock, loaded: Loaded, db: sqlite3.Connection | None, uri: str) -> None:
        self.clock = clock
        self.extensions = loaded.extensions
        self.ops = loaded.ops
        self.ops["ops.list"] = list_ops(self.ops)
        self.daemons = loaded.daemons
        self._views = loaded.views
        self._blobs = Blobs(folder / "blobs")
        self._db = db
        self._uri = uri
        self._idle: queue.SimpleQueue[sqlite3.Connection] = queue.SimpleQueue()
        self._lock: int | None = None
        self._rings: dict[str, Ring] = {}
        self._folds: dict[str, list[Callable[[Event], None]]] = defaultdict(list)
        self._stale: tuple[str, ...] = ()
        self._pulse = Pulse()
        self._writer: Writer | None = None
        self._checkpointer: Checkpointer | None = None
        if db is None:
            with self._reading() as reader:
                reader.execute("BEGIN")
                self._pulse.head = head(reader)
                self._stale = self._find_stale(reader)
                reader.execute("COMMIT")
        else:
            self._prepare_views(db)
            self._pulse.head = head(db)
            self._writer = Writer(db, self._pulse, self._seal)
            self._checkpointer = Checkpointer(folder / "journal.sqlite")
        self._tail = Tail(lambda after: self.read(self.runtime, after=after).events, self._pulse.head)

    @classmethod
    def open(
        cls,
        path: str | os.PathLike[str],
        *,
        clock: Clock | None = None,
        extensions: Iterable[Extension] = (),
        read_only: bool = False,
    ) -> "Kernel":
        """Open a session folder as its one live writer, or read-only.

        Read-only opens a closed journal anywhere, since `immutable=1` takes no locks; a live one, only on a local disk.
        """
        folder = Path(path)
        clock = SystemClock() if clock is None else clock
        loaded = load([*CORE, *extensions])
        if read_only:
            live = is_live(folder)
            if live:
                require_local(folder)
            return cls(folder, clock, loaded, None, reader_uri(folder, immutable=not live))
        require_local(folder)
        folder.mkdir(parents=True, exist_ok=True)
        lock = take_lock(folder / "lock")
        db = None
        try:
            db = open_writer(folder / "journal.sqlite", clock.now())
            kernel = cls(folder, clock, loaded, db, reader_uri(folder))
        except BaseException:
            if db is not None:
                db.close()
            os.close(lock)
            raise
        kernel._lock = lock
        return kernel

    def _find_stale(self, db: sqlite3.Connection) -> tuple[str, ...]:
        """Views that are new, of another version, or were away while the journal grew."""
        marks = {row["view"]: (row["version"], row["high_water"]) for row in db.execute("SELECT * FROM v_folds")}
        last = head(db)
        return tuple(view.name for view in self._views if marks.get(view.name) != (view.version, last))

    def _prepare_views(self, db: sqlite3.Connection) -> None:
        db.execute("BEGIN IMMEDIATE")
        try:
            stale = self._find_stale(db)
            for view in self._views:
                if view.name in stale:
                    rebuild(db, view)
                for event_type, folds in view(db).bound_folds().items():
                    self._folds[event_type].extend(folds)
            db.execute("COMMIT")
        except BaseException:
            db.execute("ROLLBACK")
            raise

    def _seal(self, db: sqlite3.Connection) -> int:
        """Move the high-water marks, as the batch's last write."""
        seq = head(db)
        names = [view.name for view in self._views]
        marks = ", ".join("?" * len(names))
        db.execute(f"UPDATE v_folds SET high_water = ? WHERE view IN ({marks})", (seq, *names))
        return seq

    def _apply(self, event: Event) -> None:
        for apply in self._folds.get(event.type, ()):
            apply(event)
        for apply in self._folds.get("*", ()):
            apply(event)

    def _writing(self) -> Writer:
        if self._writer is None:
            raise Refused("unsupported", "this kernel is read-only")
        return self._writer

    # Commands.

    async def submit(
        self,
        principal: Principal,
        op: str,
        args: Mapping[str, Any],
        *,
        key: str | None = None,
        expected_version: int | None = None,
    ) -> Outcome:
        """Run one command and return its outcome once durable. A refusal is an outcome, not an exception."""
        operation = self.ops.get(op)
        if operation is not None and operation.exposes and principal.kind != "agent":
            return self.query(principal, op, args)
        command = _Command(principal, op, args, args_hash(op, args), key, expected_version)
        try:
            if len(op) > _NAME_LIMIT or (key is not None and len(key) > _NAME_LIMIT):
                raise Refused("invalid", f"op names and keys are at most {_NAME_LIMIT} characters")
            writer = self._writing()
            run = lambda db: self._execute(db, command)  # noqa: E731
            return await writer.call(run, owner=principal.id, runtime=principal.kind == "runtime")
        except Refused as refused:
            return command.refused(refused.refusal, None)

    def _decode(self, name: str, args: Mapping[str, Any]) -> tuple[Op, Args]:
        operation = self.ops.get(name)
        if operation is None:
            raise Refused("not_found", "no such op")
        try:
            return operation, operation.input.model_validate(args)
        except ValidationError as error:
            faults = (f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in error.errors(include_url=False))
            raise Refused("invalid", "; ".join(faults)[:_DETAIL_LIMIT]) from None

    def _execute(self, db: sqlite3.Connection, command: _Command) -> Outcome:
        """Run one command inside the open transaction. It ends on one event carrying its outcome."""
        principal = command.principal
        prior = None if command.key is None else Commands(db).get(principal.id, command.key)
        if prior is not None and prior.args_hash == command.args_hash:
            return prior

        now = self.clock.now()
        target = None
        db.execute("SAVEPOINT command")
        try:
            if prior is not None:
                raise Refused("key_reused", f"this key answered other arguments at seq {prior.seq}")
            operation, args = self._decode(command.op, command.args)
            target = operation.target(args)
            me = authorize(db, principal, operation, target)
            if operation.query and not operation.exposes:
                raise Refused("unsupported", "a query has no command form")
            if command.expected_version is not None:
                current = stream_version(db, target)
                if current != command.expected_version:
                    raise Refused("conflict", {"expected": command.expected_version, "current": current})
            txn = Txn(db, me, now, self._apply)
            result = jsonable(operation.fn(txn, args))
            if len(canonical(result).encode()) > DATA_LIMIT:
                raise Refused("invalid", f"result exceeds {DATA_LIMIT} bytes; store a body and cite its hash")
            outcome = command.answered(result)
            event = txn._finish(outcome)
        except Exception as error:
            db.execute("ROLLBACK TO command")
            refusal = self._as_refusal(error)
            outcome = command.refused(refusal, target)
            txn = Txn(db, principal, now, self._apply)
            txn.emit(
                "op.refused",
                f"commands/{principal.id}",
                gist=f"{command.op} refused: {refusal.code}"[:GIST_LIMIT],
                data={"op": command.op, "code": refusal.code, "object": target},
            )
            event = txn._finish(outcome)
        db.execute("RELEASE command")
        return outcome.model_copy(update={"seq": event.seq})

    def _as_refusal(self, error: Exception) -> Refusal:
        if isinstance(error, Refused):
            return error.refusal
        log.error("an op failed", exc_info=error)
        return Refusal(code="unavailable", detail=f"the op failed: {type(error).__name__}")

    async def recover(self) -> Outcome:
        """Begin a new incarnation: every effect left `started` becomes uncertain and its policy applies."""
        return await self.submit(self.runtime, "runtime.start", {})

    async def rebuild(self, view: type[View]) -> None:
        """Drop one view and refold it."""
        await self._writing().call(lambda db: rebuild(db, view), owner=None, runtime=True)

    async def rebuild_all(self) -> None:
        """Drop every view and refold it. Identical contents are the point."""
        for view in self._views:
            await self.rebuild(view)

    # Bodies.

    async def put_body(self, body: bytes) -> str:
        """Store a body and return its sha256, durable before this returns. An orphan is harmless."""
        writer = self._writing()
        sha256 = hashlib.sha256(body).hexdigest()
        inline = body if len(body) <= BODY_LIMIT else None
        if inline is None:
            await asyncio.to_thread(self._blobs.write, sha256, body)
        await writer.call(lambda db: record(db, sha256, len(body), inline), owner=None)
        return sha256

    def get_body(self, sha256: str) -> bytes:
        """Read a body, or refuse `not_found` with the reason. An op decides who may; this checks no grant."""
        with self._reading() as db:
            data = lookup(db, sha256)["data"]
        return self._blobs.read(sha256) if data is None else data

    async def erase_body(self, sha256: str) -> None:
        """Remove a tombstoned body's bytes. A daemon does this once the tombstone has committed."""
        await self._writing().call(lambda db: forget(db, sha256), owner=None)
        await asyncio.to_thread(self._blobs.erase, sha256)

    # Reads.

    @contextmanager
    def _reading(self) -> Generator[sqlite3.Connection]:
        if self.closed:
            raise Refused("unavailable", "the kernel is closed")
        try:
            db = self._idle.get_nowait()
        except queue.Empty:
            db = open_reader(self._uri)
        try:
            yield db
        finally:
            if self._idle.qsize() < _IDLE_READERS:
                self._idle.put(db)
            else:
                db.close()

    def query(self, principal: Principal, op: str, args: Mapping[str, Any]) -> Outcome:
        """Run a read-only op on a read connection. It enters no history."""
        command = _Command(principal, op, args, args_hash(op, args))
        target = None
        with self._reading() as db:
            db.execute("BEGIN")
            try:
                if self._stale:
                    raise Refused("unavailable", f"stale views: {', '.join(self._stale)}")
                operation, decoded = self._decode(op, args)
                target = operation.target(decoded)
                me = authorize(db, principal, operation, target)
                if not (operation.query or operation.exposes):
                    raise Refused("unsupported", "this op is a command")
                if operation.exposes and principal.kind == "agent":
                    raise Refused("unsupported", "an agent's read is a command, because it records exposure")
                return command.answered(jsonable(operation.fn(Txn(db, me, self.clock.now()), decoded)))
            except Exception as error:
                return command.refused(self._as_refusal(error), target)
            finally:
                db.execute("COMMIT")

    def authenticate(self, token: str) -> Principal:
        """Resolve a credential by its hash, or refuse."""
        with self._reading() as db:
            principal = Principals(db).by_token(hash_token(token))
        if principal is None:
            raise Refused("not_permitted", "unknown credential")
        return principal

    def _refuse_agents(self, principal: Principal) -> None:
        if principal.kind == "agent":
            raise Refused("not_permitted", "an agent's reads are ops")

    def read(self, principal: Principal, *, after: int, match: str | None = None, limit: int = 512) -> Page:
        """Read a page past `after` in one short transaction. `match` globs stream names.

        Agents never get this: their reads are ops, checked against grants.
        """
        self._refuse_agents(principal)
        with self._reading() as db:
            db.execute("BEGIN")
            last = head(db)
            end = min(last, after + (limit if match is None else _SCAN_LIMIT))
            rows = db.execute(
                "SELECT * FROM events WHERE seq > ? AND seq <= ? AND (? IS NULL OR matches(stream, ?)) "
                "ORDER BY seq LIMIT ?",
                (after, end, match, match, limit),
            ).fetchall()
            db.execute("COMMIT")
        cursor = rows[-1]["seq"] if len(rows) == limit else max(after, end)
        return Page(events=tuple(decode(row) for row in rows), cursor=cursor, head=last)

    async def follow(self, principal: Principal, *, after: int, match: str | None = None) -> AsyncIterator[Page]:
        """Yield pages past `after` while the kernel is open. Catch-up and live are one loop.

        Near the head, followers share one read per pulse. One that has fallen behind pages by SQL.
        """
        self._refuse_agents(principal)
        while not self.closed:
            page = None if self._writer is None else self._tail.page(after, match, self.head)
            page = page or self.read(principal, after=after, match=match)
            after = page.cursor
            if page.events:
                yield page
            if after >= page.head and (self._writer is None or not await self._pulse.wait(after)):
                return

    @property
    def head(self) -> int:
        """The newest committed seq."""
        return self._pulse.head

    @property
    def session_id(self) -> str:
        """The constant of this journal."""
        with self._reading() as db:
            return db.execute("SELECT value FROM meta WHERE key = 'session_id'").fetchone()[0]

    async def changed(self, after: int) -> None:
        """Sleep until the head passes `after`, or the kernel closes."""
        self._writing()
        await self._pulse.wait(after)

    def _ring(self, agent: str) -> Ring:
        return self._rings.setdefault(agent, Ring(agent))

    def push_delta(self, agent: str, text: str) -> None:
        """Offer a frame of live text. It may be lost and is never journaled."""
        self._ring(agent).push(text)

    def deltas(self, agent: str) -> AsyncIterator[Delta]:
        """Follow an agent's live text until the kernel closes."""
        return self._ring(agent).tail()

    # Lifetime.

    async def supervise(self) -> None:
        """Run every daemon, one for one, until cancelled. Cancel this before `close`."""
        self._writing()
        await asyncio.gather(*(keep_running(daemon, self) for daemon in self.daemons))

    @property
    def closed(self) -> bool:
        return self._pulse.closed

    def close(self) -> None:
        """Finish queued commands, checkpoint the WAL to empty, and let go of the lock."""
        if self.closed:
            return
        if self._writer is not None:
            self._writer.stop()
        if self._checkpointer is not None:
            self._checkpointer.stop()
        self._pulse.close()
        for ring in self._rings.values():
            ring.close()
        while not self._idle.empty():
            self._idle.get_nowait().close()
        if self._db is not None:
            self._db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            self._db.close()
        if self._lock is not None:
            fcntl.flock(self._lock, fcntl.LOCK_UN)
            os.close(self._lock)
