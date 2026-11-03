"""The kernel: one journal, one writer, and every way in and out."""

import asyncio
import hashlib
import logging
import os
import queue
import sqlite3
from collections import defaultdict
from collections.abc import AsyncGenerator, AsyncIterator, Callable, Generator, Iterable, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Self

from pydantic import ValidationError

from . import bodies
from .auth import Grants, Principals
from .bodies import Blobs
from .clock import Clock, SystemClock
from .core import CORE, list_ops
from .daemon import keep_running
from .extension import Extension, Loaded, load
from .journal import (
    check_schema,
    decode,
    fingerprint,
    is_live,
    last_seq,
    open_reader,
    open_writer,
    prior_outcome,
    reader_uri,
    require_local,
    stream_version,
    take_lock,
)
from .model import (
    BODY_LIMIT,
    DATA_LIMIT,
    GIST_LIMIT,
    NAME_LIMIT,
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
from .pulse import Pulse, Ring, Tail, first
from .txn import Txn
from .view import View, refold
from .writer import Writer

log = logging.getLogger("platoon_harness.kernel")

_DETAIL_LIMIT = 512
_SCAN_LIMIT = 4096
_SEQ_LIMIT = 2**63
_IDLE_READERS = 4


@dataclass(frozen=True)
class _Command:
    """One invocation. `text` is its arguments as canonical JSON, which is what gets hashed and decoded."""

    principal: Principal
    op: str
    text: str
    args_hash: str
    key: str | None = None
    expected_version: int | None = None
    native: Mapping[str, str] | None = None

    @classmethod
    def of(
        cls,
        principal: Principal,
        op: str,
        args: Mapping[str, Any],
        key: str | None = None,
        expected_version: int | None = None,
        native: Mapping[str, str] | None = None,
    ) -> Self:
        try:
            text = canonical(jsonable(args))
        except (TypeError, ValueError, RecursionError):
            text = ""  # Decoding refuses this.
        return cls(principal, op, text, args_hash(op, text), key, expected_version, native)

    def check(self) -> None:
        """Refuse what could never be journaled, even as a refusal."""
        names = f"{self.op}{self.key or ''}"
        if not names.isprintable() or max(len(self.op), len(self.key or "")) > NAME_LIMIT:
            raise Refused("invalid", f"op names and keys are printable and at most {NAME_LIMIT} characters")

    def refused(self, refusal: Refusal, target: str | None) -> Outcome:
        """Fill in a refusal. Caller text is cut, because a journaled refusal is permanent."""
        detail = refusal.detail
        text = detail if isinstance(detail, str) else canonical(detail)
        filled = refusal.model_copy(
            update={
                "op": self.op,
                "object": None if target is None else target[:NAME_LIMIT],
                "detail": text[:_DETAIL_LIMIT] if len(text) > _DETAIL_LIMIT else detail,
            }
        )
        return Outcome(op=self.op, key=self.key, args_hash=self.args_hash, refusal=filled)

    def answered(self, result: Any) -> Outcome:
        return Outcome(op=self.op, key=self.key, args_hash=self.args_hash, result=result)


class Kernel:
    """One session's journal, reached through `submit`, `query`, `read`, `follow` and `deltas`.

    Closing checkpoints the WAL to empty, which is what makes the folder portable.
    """

    runtime = Principal(id="runtime")

    def __init__(
        self,
        folder: Path,
        clock: Clock,
        loaded: Loaded,
        uri: str,
        *,
        frozen: bool = False,
        writing: tuple[sqlite3.Connection, int] | None = None,
    ) -> None:
        self.clock = clock
        self.ops = loaded.ops
        self._daemons = loaded.daemons
        self._views = loaded.views
        self._folder = folder
        self._blobs = Blobs(folder / "blobs")
        self._uri = uri
        self._frozen = fingerprint(folder) if frozen else None
        self._idle: queue.SimpleQueue[sqlite3.Connection] = queue.SimpleQueue()
        self._rings: dict[str, Ring] = {}
        self._folds: dict[str, list[Callable[[Event], None]]] = defaultdict(list)
        self._pulse = Pulse()
        self._writer: Writer | None = None
        if writing is None:
            with self._reading() as reader:
                check_schema(reader)
        else:
            db, lock = writing
            check_schema(db)
            self._prepare_views(db)
            self._pulse.head = last_seq(db)
            self._writer = Writer(db, lock, folder / "journal.sqlite", self._pulse, self._seal)
        self._tail = Tail(lambda after: self.read(self.runtime, after=after).events, self.head)

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
        loaded = _loaded(extensions)
        if read_only:
            live = is_live(folder)
            if live:
                require_local(folder)
            return cls(folder, clock, loaded, reader_uri(folder, immutable=not live), frozen=not live)
        require_local(folder)
        folder.mkdir(parents=True, exist_ok=True)
        lock = take_lock(folder / "lock")
        db = None
        try:
            db = open_writer(folder / "journal.sqlite", clock.now())
            return cls(folder, clock, loaded, reader_uri(folder), writing=(db, lock))
        except BaseException:
            if db is not None:
                db.close()
            os.close(lock)
            raise

    def _find_stale(self, db: sqlite3.Connection) -> tuple[str, ...]:
        """Views that are new, of another version, or were away while the journal grew."""
        marks = {row["view"]: (row["version"], row["high_water"]) for row in db.execute("SELECT * FROM v_folds")}
        last = last_seq(db)
        return tuple(view.name for view in self._views if marks.get(view.name) != (view.version, last))

    def _prepare_views(self, db: sqlite3.Connection) -> None:
        db.execute("BEGIN IMMEDIATE")
        try:
            stale = self._find_stale(db)
            for view in self._views:
                if view.name in stale:
                    refold(db, view)
                for event_type, folds in view(db).bound_folds().items():
                    self._folds[event_type].extend(folds)
            db.execute("COMMIT")
        except BaseException:
            db.execute("ROLLBACK")
            raise

    def _seal(self, db: sqlite3.Connection) -> int:
        """Move the high-water marks, as the batch's last write."""
        seq = last_seq(db)
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
        native: Mapping[str, str] | None = None,
    ) -> Outcome:
        """Run one command and return its outcome once durable. A refusal is an outcome, not an exception. A read-only
        kernel answers only a command its journal answered under the same key, as any retry is answered.

        `native` holds a backend's ids for this command, stamped on its events as evidence and read by nothing.
        """
        command = _Command.of(principal, op, args, key, expected_version, native)
        operation = self.ops.get(op)
        if operation is not None and operation.exposes and principal.kind != "agent":
            if expected_version is None:
                return self.query(principal, op, args)
            return command.refused(Refusal(code="unsupported", detail="a query has no version to expect"), None)
        try:
            command.check()
            if self._writer is None:
                return self._answered_before(command)
            return await self._writer.call(lambda db: self._execute(db, command), owner=principal.id)
        except Refused as refused:
            return command.refused(refused.refusal, None)

    def _answered_before(self, command: _Command) -> Outcome:
        with self._reading() as db:
            prior = None if command.key is None else prior_outcome(db, command.principal.id, command.key)
        if prior is None or prior.args_hash != command.args_hash:
            raise Refused("unsupported", "this kernel is read-only")
        return prior

    def _decode(self, command: _Command) -> tuple[Op, Args]:
        operation = self.ops.get(command.op)
        if operation is None:
            raise Refused("not_found", "no such op")
        try:
            return operation, operation.input.model_validate_json(command.text)
        except ValidationError as error:
            faults = (f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in error.errors(include_url=False))
            raise Refused("invalid", "; ".join(faults)) from None

    def _execute(self, db: sqlite3.Connection, command: _Command) -> Outcome:
        """Run one command inside the open transaction. It ends on one event carrying its outcome."""
        principal = command.principal
        prior = None if command.key is None else prior_outcome(db, principal.id, command.key)
        if prior is not None and prior.args_hash == command.args_hash:
            return prior

        now = self.clock.now()
        target = None
        db.execute("SAVEPOINT command")
        try:
            if prior is not None:
                raise Refused("key_reused", f"this key answered other arguments at seq {prior.seq}")
            operation, args = self._decode(command)
            target = operation.on(args)
            me = Grants(db).authorize(principal, operation, target)
            if operation.query:
                raise Refused("unsupported", "a query has no command form")
            if command.expected_version is not None:
                if target is None:
                    raise Refused("unsupported", "this op has no one object to version")
                current = stream_version(db, target)
                if current != command.expected_version:
                    raise Refused("conflict", {"expected": command.expected_version, "current": current})
            txn = Txn(db, me, now, self._apply, command.native)
            result = jsonable(operation.fn(txn, args))
            if len(canonical(result).encode()) > DATA_LIMIT:
                raise Refused("invalid", f"result exceeds {DATA_LIMIT} bytes; store a body and cite its hash")
            outcome = txn._finish(command.answered(result))
        except BaseException as error:
            db.execute("ROLLBACK TO command")
            if not isinstance(error, Refused):
                command = replace(command, key=None)  # A crash answers nothing, so a retry runs.
            outcome = self._refuse(db, command, self._as_refusal(error), target, now)
        db.execute("RELEASE command")
        return outcome

    def _refuse(
        self, db: sqlite3.Connection, command: _Command, refusal: Refusal, target: str | None, now: float
    ) -> Outcome:
        """End a command on `op.refused`. If even that fails, nothing happened and a retry may run."""
        outcome = command.refused(refusal, target)
        try:
            txn = Txn(db, command.principal, now, self._apply, command.native)
            txn.emit(
                "op.refused",
                f"commands/{command.principal.id}",
                gist=f"{command.op} refused: {refusal.code}"[:GIST_LIMIT],
                data={"op": command.op, "code": refusal.code, "object": target and target[:NAME_LIMIT]},
            )
            return txn._finish(outcome)
        except Exception:
            log.exception("a refusal of %s could not be journaled", command.op)
            db.execute("ROLLBACK TO command")
            return command.refused(Refusal(code="unavailable", detail="the refusal could not be journaled"), target)

    def _as_refusal(self, error: BaseException) -> Refusal:
        if isinstance(error, Refused):
            return error.refusal
        log.error("an op failed", exc_info=error)
        return Refusal(code="unavailable", detail=f"the op failed: {type(error).__name__}")

    async def recover(self, *drift: str) -> Outcome:
        """Begin a new incarnation: started effects become uncertain, a turn in flight is lost, policies apply.
        `drift` says what runs now that differs from what the session began under, which `runtime.started` keeps."""
        return await self.submit(self.runtime, "runtime.start", {"drift": drift})

    async def rebuild(self, view: type[View]) -> None:
        """Drop one view and refold it."""
        await self._writing().call(lambda db: refold(db, view), owner="runtime")

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
        try:
            await writer.call(lambda db: bodies.record(db, sha256, len(body), inline), owner=None)
        except Refused as refused:
            if inline is None and refused.refusal.code == "conflict":  # Redacted: these bytes may not stay.
                await asyncio.to_thread(self._blobs.erase, sha256)
            raise
        return sha256

    def get_body(self, sha256: str, *, limit: int | None = None) -> bytes:
        """Read a body, or refuse `not_found` with the reason. An op decides who may; this checks no grant.

        One past `limit` bytes is refused `unsupported` before any of it is read.
        """
        with self._reading() as db:
            found = bodies.lookup(db, sha256)
        if limit is not None and found["size"] > limit:
            raise Refused("unsupported", f"this body is {found['size']} bytes, past the {limit} this reader takes")
        if found["data"] is not None:
            return found["data"]
        try:
            return self._blobs.read(sha256)
        except FileNotFoundError:
            raise Refused("not_found", "this body was tombstoned") from None

    async def erase_body(self, sha256: str) -> None:
        """Remove a tombstoned body's bytes from the journal, `blobs/` and the WAL. A daemon does this.

        Refuses `busy` while a reader holds the WAL, so the erase effect stays open until the bytes are gone.
        """
        writer = self._writing()
        await writer.call(lambda db: bodies.forget(db, sha256), owner=None)
        await asyncio.to_thread(self._blobs.erase, sha256)
        await asyncio.to_thread(writer.scrub)

    # Reads.

    @contextmanager
    def _reading(self) -> Generator[sqlite3.Connection]:
        """A connection inside one short read transaction."""
        if self.closed:
            raise Refused("unavailable", "the kernel is closed")
        if self._frozen is not None and fingerprint(self._folder) != self._frozen:
            raise Refused("unavailable", "a writer changed this journal; open it again")
        try:
            db = self._idle.get_nowait()
        except queue.Empty:
            db = open_reader(self._uri)
        try:
            db.execute("BEGIN")
            yield db
        finally:
            try:
                db.execute("COMMIT")
            except sqlite3.Error:
                db.close()
            else:
                if self._idle.qsize() < _IDLE_READERS:
                    self._idle.put(db)
                else:
                    db.close()

    def query(self, principal: Principal, op: str, args: Mapping[str, Any]) -> Outcome:
        """Run a read-only op on a read connection. It enters no history."""
        command = _Command.of(principal, op, args)
        target = None
        try:
            with self._reading() as db:
                if self._writer is None and (stale := self._find_stale(db)):
                    raise Refused("unavailable", f"stale views: {', '.join(stale)}")
                operation, decoded = self._decode(command)
                target = operation.on(decoded)
                me = Grants(db).authorize(principal, operation, target)
                if not (operation.query or operation.exposes):
                    raise Refused("unsupported", "this op is a command")
                if operation.exposes and principal.kind == "agent":
                    raise Refused("unsupported", "an agent's read is a command, because it records exposure")
                return command.answered(jsonable(operation.fn(Txn(db, me, self.clock.now()), decoded)))
        except Exception as error:
            return command.refused(self._as_refusal(error), target)

    def authenticate(self, token: str) -> Principal:
        """Resolve a credential by its hash, or refuse."""
        with self._reading() as db:
            principal = Principals(db).by_token(hash_token(token))
        if principal is None:
            raise Refused("not_permitted", "unknown credential")
        return principal

    def read(self, principal: Principal, *, after: int, match: str | None = None, limit: int = 512) -> Page:
        """Read a page past `after` in one short transaction. `match` globs stream names.

        This is for the runtime and live principals other than agents, whose reads are ops, checked against grants.
        """
        if principal.kind == "agent":
            raise Refused("not_permitted", "an agent's reads are ops")
        if not 0 < limit <= _SCAN_LIMIT:
            raise Refused("invalid", f"limit is 1 to {_SCAN_LIMIT}")
        if not 0 <= after < _SEQ_LIMIT:
            raise Refused("invalid", "after is a seq")
        if match is not None and not match.isprintable():
            raise Refused("invalid", "match is a glob over stream names")
        with self._reading() as db:
            if principal.kind != "runtime":
                Principals(db).live(principal.id)
            last = last_seq(db)
            end = min(last, after + (limit if match is None else _SCAN_LIMIT))
            rows = db.execute(
                "SELECT * FROM events WHERE seq > ? AND seq <= ? AND (? IS NULL OR matches(stream, ?)) "
                "ORDER BY seq LIMIT ?",
                (after, end, match, match, limit),
            ).fetchall()
        cursor = rows[-1]["seq"] if len(rows) == limit else max(after, end)
        return Page(events=tuple(decode(row) for row in rows), cursor=cursor, head=last)

    async def follow(self, principal: Principal, *, after: int, match: str | None = None) -> AsyncIterator[Page]:
        """Yield pages past `after` while the kernel is open. Catch-up and live are one loop.

        Near the head, followers share one read per pulse. One that has fallen behind pages by SQL, as does a page
        holding a revocation, so a revoked reader is refused there.
        """
        self.read(principal, after=after, match=match, limit=1)  # The tail checks neither the reader nor the page.
        while not self.closed:
            page = self._tail.page(after, match, self.head) or self.read(principal, after=after, match=match)
            after = page.cursor
            if page.events:
                yield page
            if after >= page.head and (self._writer is None or not await self._pulse.wait(after)):
                return

    @property
    def head(self) -> int:
        """The newest committed seq."""
        if self._writer is not None:
            return self._pulse.head
        with self._reading() as db:
            return last_seq(db)

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
        ring = self._rings.get(agent)
        if ring is None:
            ring = self._rings[agent] = Ring(agent)
            if self.closed:
                ring.close()
        return ring

    def push_delta(self, agent: str, text: str) -> None:
        """Offer a frame of an agent's live text. It may be lost and is never journaled."""
        self._ring(agent).push(text)

    def end_delta(self, agent: str, seq: int) -> None:
        """Say that the event at `seq` replaced an agent's live text so far: an item it said, or an end of its turn or
        of itself."""
        self._ring(agent).end(seq)

    async def deltas(self, agent: str, *, after: int | None = None) -> AsyncGenerator[Delta]:
        """Follow an agent's live text past frame `after`, or from what it is saying now, each delta joining what came
        since the last. An agent's text ends when its principal is revoked, at that seq, so a reader is told so once.
        It ends when the kernel closes, or once an agent that has ended has had all it said told."""
        ring = self._ring(agent)
        while not self.closed:
            if (delta := ring.since(after)) is not None:
                yield delta
                after = delta.frame
                continue
            with self._reading() as db:
                revoked = Principals(db).revoked_at(f"agent:{agent}")
            if revoked is not None:
                if not ring.end(revoked):
                    return
            else:
                place = ring.head if after is None or after > ring.head else after
                await first(ring.wait(place), self._pulse.wait(self.head))

    # Lifetime.

    async def supervise(self) -> None:
        """Run every daemon, one for one, until cancelled. Cancel this before `close`."""
        self._writing()
        await asyncio.gather(*(keep_running(daemon, self) for daemon in self._daemons))

    @property
    def closed(self) -> bool:
        return self._pulse.closed

    @property
    def read_only(self) -> bool:
        return self._writer is None

    def close(self) -> None:
        """Finish queued commands, checkpoint the WAL to empty, and let go of the lock."""
        if self.closed:
            return
        self._pulse.close()
        for ring in tuple(self._rings.values()):
            ring.close()
        while not self._idle.empty():
            self._idle.get_nowait().close()
        if self._writer is not None:
            self._writer.stop()


def _loaded(extensions: Iterable[Extension]) -> Loaded:
    """The kernel's own extensions, `ops.list` over every op, and `extensions`, checked against each other."""
    ops: dict[str, Op] = {}
    loaded = load([*CORE, Extension("ops", ops=[list_ops(ops)]), *extensions])
    ops.update(loaded.ops)
    return loaded


def registry(extensions: Iterable[Extension] = ()) -> dict[str, Op]:
    """Every op a kernel holding `extensions` has, its own among them, by name: what every surface derives from."""
    return dict(_loaded(extensions).ops)
