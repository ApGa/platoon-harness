"""Wait: one condition, checked and registered in one transaction, kept in the service and not in the model."""

import asyncio
import json
from collections.abc import Iterable
from typing import Annotated, Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from platoon_harness.kernel import (
    GIST_LIMIT,
    Args,
    Event,
    Grants,
    Kernel,
    Principal,
    Refused,
    Stamps,
    Txn,
    View,
    fold,
    op,
)

from .agents import Agents
from .common import Name
from .messages import Deliveries, ack, post

_END_TURN = "The wait is registered. End your turn: the runtime starts your next turn when it holds."
_TASK_SETTLED = ("task.completed", "task.died")
_BOARD_VERSIONED = ("board.posted", "board.revised")


class Condition(Args):
    """`on(stream, types, n, distinct)`: join, wait-any, version watch and barrier are this one condition.

    `n` counts events. With `distinct`, naming an envelope field, it counts different values, and a tuple names which.
    """

    stream: Annotated[str, Field(max_length=512)]
    types: tuple[str, ...] = ()
    n: Annotated[int, Field(ge=1)] | tuple[str, ...] = 1
    distinct: Literal["actor", "agent", "correlation"] | None = None

    @model_validator(mode="after")
    def _named_values_are_distinct(self) -> Self:
        if isinstance(self.n, tuple) and (not self.n or self.distinct is None):
            raise ValueError("n names values only with `distinct`, and at least one")
        return self


def on(stream: str, types: tuple[str, ...] = (), n: int | tuple[str, ...] = 1, distinct: Any = None) -> Condition:
    """One condition of a wait."""
    return Condition(stream=stream, types=types, n=n, distinct=distinct)


class Progress(BaseModel, frozen=True):
    """How far one condition has got. `missing` is what the UI shows: the values it lacks, or else its stream."""

    stream: str
    types: tuple[str, ...]
    need: int
    distinct: str | None
    expected: tuple[str, ...]
    have: int = 0
    seen: tuple[str, ...] = ()

    @classmethod
    def of(cls, condition: Condition) -> "Progress":
        n = condition.n
        return cls(
            stream=condition.stream,
            types=condition.types,
            need=n if isinstance(n, int) else len(n),
            distinct=condition.distinct,
            expected=() if isinstance(n, int) else n,
        )

    @property
    def done(self) -> bool:
        return self.have >= self.need

    @property
    def missing(self) -> tuple[str, ...]:
        if self.done:
            return ()
        return tuple(value for value in self.expected if value not in self.seen) or (self.stream,)

    def advanced(self, event: Event) -> "Progress":
        """This condition after one more event on its stream."""
        if self.done or (self.types and event.type not in self.types):
            return self
        if self.distinct is None:
            return self.model_copy(update={"have": self.have + 1})
        value = getattr(event, self.distinct)
        if value is None or value in self.seen or (self.expected and value not in self.expected):
            return self
        return self.model_copy(update={"have": self.have + 1, "seen": (*self.seen, value)})


class OpenWait(BaseModel, frozen=True):
    """A wait still open. `left` counts the conditions it needs, so it holds at zero."""

    id: int
    waiter: str
    left: int
    after: int | None
    deadline: float | None
    conditions: tuple[Progress, ...]

    @property
    def have(self) -> int:
        return sum(min(condition.have, condition.need) for condition in self.conditions)

    @property
    def need(self) -> int:
        return sum(condition.need for condition in self.conditions)

    @property
    def missing(self) -> tuple[str, ...]:
        return tuple(value for condition in self.conditions for value in condition.missing)

    def shown(self) -> dict[str, Any]:
        return {"id": self.id, "have": self.have, "need": self.need, "missing": self.missing}


class Waits(View):
    """Open waits and their folded progress. A wait that closes leaves this view; the journal keeps it."""

    schema = """
    CREATE TABLE v_waits(
        id INTEGER PRIMARY KEY,
        waiter TEXT NOT NULL,
        left INTEGER NOT NULL,
        after INTEGER,
        deadline REAL
    ) STRICT;
    CREATE INDEX v_waits_waiter ON v_waits(waiter);
    CREATE TABLE v_waits_conditions(
        wait INTEGER NOT NULL,
        position INTEGER NOT NULL,
        stream TEXT NOT NULL,
        progress TEXT NOT NULL,
        PRIMARY KEY (wait, position)
    ) WITHOUT ROWID, STRICT;
    CREATE INDEX v_waits_conditions_stream ON v_waits_conditions(stream);
    """

    @fold("wait.registered")
    def registered(self, event: Event) -> None:
        data = event.data
        self.db.execute(
            "INSERT INTO v_waits VALUES (?, ?, ?, ?, ?)",
            (event.seq, event.actor, data["left"], data["after"], data["deadline"]),
        )
        for position, progress in enumerate(data["conditions"]):
            self.db.execute(
                "INSERT INTO v_waits_conditions VALUES (?, ?, ?, ?)",
                (event.seq, position, progress["stream"], json.dumps(progress)),
            )

    @fold("*")
    def progressed(self, event: Event) -> None:
        rows = self.db.execute("SELECT * FROM v_waits_conditions WHERE stream = ?", (event.stream,)).fetchall()
        for row in rows:
            before = Progress.model_validate_json(row["progress"])
            after = before.advanced(event)
            if after == before:
                continue
            self.db.execute(
                "UPDATE v_waits_conditions SET progress = ? WHERE wait = ? AND position = ?",
                (after.model_dump_json(), row["wait"], row["position"]),
            )
            if after.done:
                self.db.execute("UPDATE v_waits SET left = left - 1 WHERE id = ?", (row["wait"],))

    @fold("wait.released", "wait.expired", "wait.cancelled")
    def closed(self, event: Event) -> None:
        self._forget(event.data["id"])

    @fold("agent.ended")
    def waiter_gone(self, event: Event) -> None:
        rows = self.db.execute("SELECT id FROM v_waits WHERE waiter = ?", (f"agent:{event.agent}",)).fetchall()
        for row in rows:
            self._forget(row["id"])

    def _forget(self, id: int) -> None:
        self.db.execute("DELETE FROM v_waits WHERE id = ?", (id,))
        self.db.execute("DELETE FROM v_waits_conditions WHERE wait = ?", (id,))

    def _load(self, row: Any) -> OpenWait:
        conditions = self.db.execute(
            "SELECT progress FROM v_waits_conditions WHERE wait = ? ORDER BY position", (row["id"],)
        ).fetchall()
        parsed = tuple(Progress.model_validate_json(condition["progress"]) for condition in conditions)
        return OpenWait(**dict(row), conditions=parsed)

    def get(self, id: int) -> OpenWait | None:
        row = self.db.execute("SELECT * FROM v_waits WHERE id = ?", (id,)).fetchone()
        return None if row is None else self._load(row)

    def open_for(self, waiter: str) -> list[OpenWait]:
        rows = self.db.execute("SELECT * FROM v_waits WHERE waiter = ? ORDER BY id", (waiter,)).fetchall()
        return [self._load(row) for row in rows]

    def closing(self, now: float) -> tuple[list[OpenWait], float | None]:
        """Waits whose condition holds or whose deadline has passed, and when the next deadline falls."""
        due = self.db.execute("SELECT min(deadline) AS due FROM v_waits WHERE deadline > ?", (now,)).fetchone()
        rows = self.db.execute("SELECT * FROM v_waits WHERE left <= 0 OR deadline <= ? ORDER BY id", (now,)).fetchall()
        return [self._load(row) for row in rows], due["due"]


class Wait(Args):
    """Friendly fields compile to `on`, so a model never learns stream names."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, populate_by_name=True)

    on: Annotated[tuple[Condition, ...], Field(max_length=64)] = ()
    agents: tuple[Name, ...] = ()
    senders: Annotated[tuple[Name, ...], Field(alias="from")] = ()
    tasks: tuple[str, ...] = ()
    board: tuple[str, ...] = ()
    mode: Literal["all", "any"] = "all"
    after: Annotated[int, Field(ge=0)] | None = None
    timeout: Annotated[float, Field(gt=0)] | None = None
    hold: Annotated[float, Field(gt=0)] | None = None


def _conditions(txn: Txn, a: Wait) -> tuple[Condition, ...]:
    """What a wait asks for, as conditions. `from` counts by subject, so a monitor's report counts as its child's."""
    conditions = [
        *a.on,
        *(Condition(stream=f"agent/{name}", types=("agent.ended",)) for name in a.agents),
        *(Condition(stream=f"task/{task}", types=_TASK_SETTLED) for task in a.tasks),
        *(Condition(stream=f"board/{name}", types=_BOARD_VERSIONED) for name in a.board),
    ]
    if a.senders:
        conditions.append(Condition(stream=f"inbox/{txn.me.name}", n=a.senders, distinct="agent"))
    if not conditions:
        raise Refused("invalid", "a wait needs something to wait on: `agents`, `from`, `tasks`, `board` or `on`")
    return tuple(conditions)


def _start(txn: Txn, reader: str | None, stream: str, after: int | None) -> int:
    """Where counting begins. An omitted `after` is the server-held cursor, never the head."""
    if after is not None:
        return after
    return txn.view(Deliveries).cursor(reader, stream).offered


def _reader(principal: str) -> str | None:
    """The agent behind a principal id: only agents have cursors."""
    kind, _, name = principal.partition(":")
    return name if kind == "agent" else None


def _check_call(txn: Txn, a: Wait) -> None:
    """A held call must stay below the harness's cap, and a one-shot harness cannot park at all."""
    agent = txn.view(Agents).get(txn.me.name) if txn.me.kind == "agent" else None
    if agent is None:
        return
    if a.hold is not None and agent.tool_timeout_s is not None and a.hold >= agent.tool_timeout_s:
        raise Refused("unsupported", f"hold must stay below this harness's {agent.tool_timeout_s} s tool timeout")
    if agent.persistent is False and (a.hold is None or a.timeout is None or a.timeout > a.hold):
        raise Refused("unsupported", "a one-shot harness cannot park: pass a `hold` no shorter than `timeout`")


def _close(txn: Txn, waiter: str, id: int, kind: str) -> None:
    stream = f"wait/{waiter.partition(':')[2] or waiter}"
    txn.emit(kind, stream, gist=f"wait {id} {kind.removeprefix('wait.')}", data={"id": id})


def _ack_all(txn: Txn, reader: str | None, streams: Iterable[str], after: int | None) -> None:
    """A wait that returned satisfied moved past what came before it. One cut off confirms nothing."""
    if reader is not None:
        for stream in streams:
            ack(txn, reader, stream, _start(txn, reader, stream, after))


@op("wait", on=lambda a: None, tool=True)
def wait_for(txn: Txn, a: Wait) -> dict[str, Any]:
    """Wait without spending a turn: for `agents` to end, a message `from` agents, `tasks` to settle (`queue/id`), or a
    new version on `board` (`board/name`). `mode` is `all` or `any`. Nothing can slip between a read and this call. Once
    registered, end your turn: the runtime starts your next one when the wait holds or `timeout` passes. Refused
    `not_permitted` for what you may not watch, and `unsupported` when this harness cannot park: pass a `hold` no
    shorter than `timeout`."""
    _check_call(txn, a)
    asked = _conditions(txn, a)
    for condition in asked:
        txn.view(Grants).authorize(txn.me, wait_for, condition.stream)
    reader = _reader(txn.me.id)
    stamps = txn.view(Stamps)
    starts = [_start(txn, reader, condition.stream, a.after) for condition in asked]
    conditions = []
    for condition, start in zip(asked, starts, strict=True):
        progress = Progress.of(condition)
        for seen in stamps.events(condition.stream, after=start):
            progress = progress.advanced(seen)
            if progress.done:
                break
        conditions.append(progress)
    if reader is not None:
        for replaced in txn.view(Waits).open_for(txn.me.id):
            _close(txn, txn.me.id, replaced.id, "wait.cancelled")

    left = (len(conditions) if a.mode == "all" else 1) - sum(progress.done for progress in conditions)
    deadline = None if a.timeout is None else txn.now + a.timeout
    data = {"left": left, "after": a.after, "deadline": deadline, "conditions": conditions}
    event = txn.emit(
        "wait.registered", f"wait/{txn.me.name}", gist=f"wait on {asked[0].stream}"[:GIST_LIMIT], data=data
    )
    shown = OpenWait(
        id=event.seq, waiter=txn.me.id, left=left, after=a.after, deadline=deadline, conditions=tuple(conditions)
    ).shown()
    if left <= 0:
        _close(txn, txn.me.id, event.seq, "wait.released")
        _ack_all(txn, reader, (condition.stream for condition in asked), a.after)
        return {**shown, "state": "released"}
    if a.hold is not None:
        return {**shown, "state": "pending", "hold": a.hold, "cursor": min(starts)}
    return {**shown, "state": "parked", "next": _END_TURN}


class WaitId(Args):
    id: int


@op("wait.cancel", tool=True)
def cancel(txn: Txn, a: WaitId) -> None:
    """Cancel your open wait. Refused `not_found` when it has closed already: nothing is waiting."""
    wait = txn.view(Waits).get(a.id)
    if wait is None or wait.waiter != txn.me.id:
        raise Refused("not_found", f"no open wait {a.id} of yours")
    _close(txn, wait.waiter, a.id, "wait.cancelled")


@op("wait.release", on=lambda a: f"wait/{a.id}", runtime=True)
def release(txn: Txn, a: WaitId) -> None:
    """Close a wait that holds or ran out of time. A waiter out of its turn hears through its inbox, which wakes it."""
    wait = txn.view(Waits).get(a.id)
    if wait is None:
        return
    holds = wait.left <= 0
    _close(txn, wait.waiter, a.id, "wait.released" if holds else "wait.expired")
    reader = _reader(wait.waiter)
    if holds:
        _ack_all(txn, reader, (condition.stream for condition in wait.conditions), wait.after)
    agent = None if reader is None else txn.view(Agents).get(reader)
    if agent is not None and agent.state in ("idle", "waiting"):
        gist = "Your wait holds." if holds else f"Your wait timed out, missing {', '.join(wait.missing)}."
        post(txn, f"inbox/{agent.name}", gist[:GIST_LIMIT], wake=True)


@op("wait.progress", query=True, tool=True)
def progress_of(txn: Txn, a: WaitId) -> dict[str, Any] | None:
    """Show an open wait's `have`, `need` and `missing`, or nothing once it has closed."""
    wait = txn.view(Waits).get(a.id)
    return None if wait is None else {**wait.shown(), "holds": wait.left <= 0}


async def hold_open(kernel: Kernel, principal: Principal, placed: dict[str, Any]) -> dict[str, Any]:
    """Keep a `wait` call open as a tool surface does, given its `pending` result. It returns `released` or `pending`.

    On expiry the wait stays registered, so the agent may call again from `cursor`, or end its turn.
    """
    expiry = kernel.clock.now() + placed["hold"]
    while True:
        head = kernel.head
        shown = kernel.query(principal, "wait.progress", {"id": placed["id"]}).result
        if shown is None or shown["holds"]:
            if shown is not None:
                await kernel.submit(kernel.runtime, "wait.release", {"id": placed["id"]})
            return {**placed, **(shown or {}), "state": "released"}
        remaining = expiry - kernel.clock.now()
        if remaining <= 0:
            return {**placed, **shown, "state": "pending"}
        tasks = [asyncio.ensure_future(kernel.changed(head)), asyncio.ensure_future(kernel.clock.sleep(remaining))]
        try:
            await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for task in tasks:
                task.cancel()
