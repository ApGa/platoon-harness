"""A small extension to exercise the kernel, and helpers for reading what it did."""

import asyncio
import contextlib
import sqlite3
import threading
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any, Literal

import pytest

from platoon_harness.kernel import (
    Args,
    Event,
    Extension,
    Kernel,
    Outcome,
    Principal,
    Refused,
    Timer,
    Txn,
    View,
    fold,
    hash_token,
    op,
)

HUMAN = Principal(id="human:ada")
ALICE = Principal(id="agent:alice")
BOB = Principal(id="agent:bob")


class Note(Args):
    stream: str = "note/a"
    text: str = "hello"
    cause: tuple[int, ...] = ()
    based_on: tuple[str, ...] = ()
    refs: tuple[str, ...] = ()
    copies: int = 1
    fail: bool = False


class Notes(View):
    schema = """
    CREATE TABLE v_notes(
        stream TEXT NOT NULL, version INTEGER NOT NULL, text TEXT NOT NULL, PRIMARY KEY (stream, version)
    ) WITHOUT ROWID, STRICT;
    """

    @fold("note.added")
    def added(self, event: Event) -> None:
        self.db.execute("INSERT INTO v_notes VALUES (?, ?, ?)", (event.stream, event.version, event.data["text"]))

    def texts(self, stream: str) -> list[str]:
        rows = self.db.execute("SELECT text FROM v_notes WHERE stream = ? ORDER BY version", (stream,))
        return [row["text"] for row in rows]


@op("note.add", on=lambda a: a.stream, tool=True)
def add(txn: Txn, a: Note) -> dict[str, Any]:
    """Add copies of a note, then fail if told to."""
    event = None
    for _ in range(a.copies):
        event = txn.emit(
            "note.added",
            a.stream,
            gist=a.text[:280],
            data={"text": a.text},
            cause=a.cause,
            based_on=a.based_on,
            refs=a.refs,
        )
    if a.fail:
        raise Refused("conflict", "told to fail")
    assert event is not None
    return {"seq": event.seq, "version": event.version}


@op("note.silence")
def silence(txn: Txn, a: Args) -> str:
    """Change nothing."""
    return "quiet"


class Stream(Args):
    stream: str = "note/a"


@op("note.list", on=lambda a: a.stream, query=True)
def list_notes(txn: Txn, a: Stream) -> list[str]:
    """Read notes without a trace."""
    return txn.view(Notes).texts(a.stream)


@op("note.read", on=lambda a: a.stream, exposes=True, tool=True)
def read_notes(txn: Txn, a: Stream) -> list[str]:
    """Read notes, recording what an agent was offered."""
    texts = txn.view(Notes).texts(a.stream)
    if txn.me.kind == "agent":
        txn.emit("note.offered", f"context/{txn.me.name}", gist="notes offered", data={"count": len(texts)})
    return texts


@op("note.reset", runtime=True)
def reset(txn: Txn, a: Args) -> None:
    """Runtime only."""
    txn.emit("note.cleared", "note/admin", gist="reset")


@op("note.sign", agent=True)
def sign(txn: Txn, a: Args) -> str:
    """Agents only."""
    return txn.me.id


class Dispatch(Args):
    kind: str = "deliver"
    on_uncertain: Literal["retry", "reconcile", "surface"] = "surface"
    timeout: float | None = None
    priority: int = 0
    agent: str | None = None
    after: int | None = None


class Cancel(Args):
    id: int


@op("note.cancel")
def cancel(txn: Txn, a: Cancel) -> None:
    """Cancel a requested effect, as a primitive does when what it served has gone."""
    txn.emit("effect.cancelled", f"effect/{a.id}", gist="cancelled", data={"id": a.id})


@op("note.dispatch")
def dispatch(txn: Txn, a: Dispatch) -> int:
    """Request an effect."""
    return txn.effect(
        a.kind,
        {"kind": a.kind},
        on_uncertain=a.on_uncertain,
        timeout=a.timeout,
        priority=a.priority,
        agent=a.agent,
        after=a.after,
    )


class Remind(Args):
    due: float
    key: str
    stream: str = "note/reminders"


@op("note.remind")
def remind(txn: Txn, a: Remind) -> None:
    """Set a timer that adds a note."""
    timer = Timer(due=a.due, op="note.add", args={"stream": a.stream, "text": a.key}, key=a.key)
    txn.emit("timer.set", f"timer/{a.key}", gist=f"remind {a.key}", data=timer)


class Span(Args):
    type: str
    stream: str
    agent: str | None = None
    data: dict[str, Any] = {}


@op("note.mark", on=lambda a: a.stream)
def mark(txn: Txn, a: Span) -> dict[str, Any]:
    """Emit any event, for envelope tests."""
    event = txn.emit(a.type, a.stream, gist=a.type, agent=a.agent, data=a.data)
    return {"turn": event.turn, "episode": event.episode, "context": event.context_version}


notes = Extension(
    "note",
    ops=[add, silence, list_notes, read_notes, reset, sign, dispatch, cancel, remind, mark],
    views=[Notes],
)


class Gate:
    """Holds the writer inside an op until released."""

    def __init__(self) -> None:
        self.entered = threading.Event()
        self.release = threading.Event()

    async def wait_entered(self) -> None:
        assert await asyncio.to_thread(self.entered.wait, 30)

    def extension(self) -> Extension:
        @op("gate.hold", runtime=True)
        def hold(txn: Txn, a: Args) -> None:
            """Wait at the gate."""
            self.entered.set()
            assert self.release.wait(30)

        return Extension("gate", ops=[hold])


def result_of(outcome: Outcome) -> Any:
    assert outcome.refusal is None, outcome.refusal
    return outcome.result


def refusal_of(outcome: Outcome) -> str:
    assert outcome.refusal is not None, outcome
    return outcome.refusal.code


def refused_code(error: pytest.ExceptionInfo[Refused]) -> str:
    return error.value.refusal.code


def dump(folder: Path) -> dict[str, list[tuple[Any, ...]]]:
    """Every fold table, row by row."""
    db = sqlite3.connect(f"{(folder / 'journal.sqlite').as_uri()}?mode=ro", uri=True)
    names = db.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name GLOB 'v_*'").fetchall()
    contents = {name: sorted(db.execute(f"SELECT * FROM {name}").fetchall(), key=repr) for (name,) in names}
    db.close()
    return contents


async def enroll(kernel: Kernel, principal: Principal, *, token: str | None = None, **fields: Any) -> None:
    token_hash = None if token is None else hash_token(token)
    result_of(
        await kernel.submit(kernel.runtime, "principal.add", {"id": principal.id, "token_hash": token_hash} | fields)
    )


async def grant(kernel: Kernel, who: str, ops: str = "*", on: str = "*") -> None:
    result_of(await kernel.submit(kernel.runtime, "grant.add", {"who": who, "ops": ops, "on": on}))


def events_of(kernel: Kernel, *, after: int = 0) -> list[Event]:
    return list(kernel.read(kernel.runtime, after=after, limit=4096).events)


async def until(kernel: Kernel, event_type: str, *, after: int = 0) -> Event:
    """Wait for an event of this type past `after`, without sleeping."""
    async for page in kernel.follow(kernel.runtime, after=after):
        for event in page.events:
            if event.type == event_type:
                return event
    raise AssertionError(f"the kernel closed before {event_type}")


@contextlib.asynccontextmanager
async def supervised(kernel: Kernel) -> AsyncIterator[None]:
    """Run the kernel's daemons for the length of a block."""
    task = asyncio.create_task(kernel.supervise())
    try:
        yield
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
