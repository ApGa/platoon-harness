"""Wait: one condition, checked and registered in one transaction, kept in the service and not in the model."""

import asyncio
import json
from collections.abc import Iterable
from typing import Annotated, Any, Literal, Self

from pydantic import BaseModel, Field, model_validator
from pydantic.json_schema import SkipJsonSchema

from platoon_harness.kernel import (
    GIST_LIMIT,
    Args,
    Event,
    Grants,
    Kernel,
    Refused,
    Stamps,
    Txn,
    View,
    fold,
    op,
)

from .agents import Agents
from .channels import Channels
from .common import AgentName, Seq, checked_after, stream_of
from .messages import Deliveries, ack, post
from .tasks import Tasks

_END_TURN = "The wait is registered. End your turn: the runtime starts your next turn when it holds."
_TASK_SETTLED = ("task.completed", "task.died")
_BOARD_VERSIONED = ("board.posted", "board.revised")
_OUT_OF_TURN = ("idle", "waiting")
_LABELS = {"agent": "@", "inbox": "@", "channel": "#", "task": "", "board": ""}


def _label(stream: str) -> str:
    """A stream as a model would name it."""
    kind, _, rest = stream.partition("/")
    return stream if kind not in _LABELS else rest if rest.startswith("+") else f"{_LABELS[kind]}{rest}"


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
    waiter: str
    have: int = 0
    seen: tuple[str, ...] = ()

    @classmethod
    def of(cls, condition: Condition, waiter: str) -> "Progress":
        n = condition.n
        return cls(
            stream=condition.stream,
            types=condition.types,
            need=n if isinstance(n, int) else len(n),
            distinct=condition.distinct,
            expected=() if isinstance(n, int) else n,
            waiter=waiter,
        )

    @property
    def done(self) -> bool:
        return self.have >= self.need

    @property
    def missing(self) -> tuple[str, ...]:
        if self.done:
            return ()
        prefix = "@" if self.distinct == "agent" else ""
        lacking = tuple(f"{prefix}{value}" for value in self.expected if value not in self.seen)
        return lacking or (_label(self.stream),)

    def _news(self, event: Event) -> bool:
        """Whether an event is news to the waiter: not its own doing, and no entry it was never meant to see."""
        if event.actor == self.waiter:
            return False
        kind, _, name = self.waiter.partition(":")
        return not (kind == "agent" and event.type == "message.sent" and name not in event.data["audience"])

    def advanced(self, event: Event) -> "Progress":
        """This condition after one more event on its stream."""
        if self.done or (self.types and event.type not in self.types):
            return self
        if self.distinct is None:
            return self.model_copy(update={"have": self.have + 1}) if self._news(event) else self
        value = getattr(event, self.distinct)
        if self.distinct == "agent":
            value = value or event.actor.partition(":")[2]  # A human or a program counts by name.
        if not value or value in self.seen or (self.expected and value not in self.expected):
            return self
        return self.model_copy(update={"have": self.have + 1, "seen": (*self.seen, value)})


class WaitRecord(BaseModel, frozen=True):
    """One wait. `left` counts the conditions it needs, so it holds at zero, and `closed` says how it ended. `hops` is
    what its waiter had heard, which a notice follows."""

    id: int
    waiter: str
    mode: str
    left: int
    after: int | None
    deadline: float | None
    hops: int
    closed: str | None = None
    conditions: tuple[Progress, ...] = ()

    @property
    def _counted(self) -> tuple[Progress, ...]:
        """The conditions that say how far along it is: all of them, or with `any` the nearest to holding."""
        if self.mode == "all":
            return self.conditions
        return (min(self.conditions, key=lambda condition: condition.need - min(condition.have, condition.need)),)

    @property
    def have(self) -> int:
        return sum(min(condition.have, condition.need) for condition in self._counted)

    @property
    def need(self) -> int:
        return sum(condition.need for condition in self._counted)

    @property
    def missing(self) -> tuple[str, ...]:
        return () if self.left <= 0 else tuple(value for condition in self.conditions for value in condition.missing)

    def shown(self) -> dict[str, Any]:
        return {"id": self.id, "have": self.have, "need": self.need, "missing": self.missing}


class Waits(View):
    """Waits, how each closed, and the folded progress of those still open."""

    schema = """
    CREATE TABLE v_waits(
        id INTEGER PRIMARY KEY,
        waiter TEXT NOT NULL,
        mode TEXT NOT NULL,
        left INTEGER NOT NULL,
        after INTEGER,
        deadline REAL,
        hops INTEGER NOT NULL,
        closed TEXT
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
            "INSERT INTO v_waits VALUES (?, ?, ?, ?, ?, ?, ?, NULL)",
            (event.seq, event.actor, data["mode"], data["left"], data["after"], data["deadline"], data["hops"]),
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
        self._forget(event.data["id"], event.type.removeprefix("wait."))

    @fold("agent.ended")
    def waiter_gone(self, event: Event) -> None:
        rows = self.db.execute(
            "SELECT id FROM v_waits WHERE waiter = ? AND closed IS NULL", (f"agent:{event.agent}",)
        ).fetchall()
        for row in rows:
            self._forget(row["id"], "cancelled")

    def _forget(self, id: int, how: str) -> None:
        self.db.execute("UPDATE v_waits SET closed = ? WHERE id = ?", (how, id))
        self.db.execute("DELETE FROM v_waits_conditions WHERE wait = ?", (id,))

    def _load(self, row: Any) -> WaitRecord:
        conditions = self.db.execute(
            "SELECT progress FROM v_waits_conditions WHERE wait = ? ORDER BY position", (row["id"],)
        ).fetchall()
        parsed = tuple(Progress.model_validate_json(condition["progress"]) for condition in conditions)
        return WaitRecord(**dict(row), conditions=parsed)

    def get(self, id: int) -> WaitRecord | None:
        row = self.db.execute("SELECT * FROM v_waits WHERE id = ?", (id,)).fetchone()
        return None if row is None else self._load(row)

    def open_for(self, waiter: str) -> list[WaitRecord]:
        rows = self.db.execute(
            "SELECT * FROM v_waits WHERE waiter = ? AND closed IS NULL ORDER BY id", (waiter,)
        ).fetchall()
        return [self._load(row) for row in rows]

    def closing(self, now: float) -> tuple[list[WaitRecord], float | None]:
        """Waits whose condition holds or whose deadline has passed, and when the next deadline falls."""
        due = self.db.execute(
            "SELECT min(deadline) AS due FROM v_waits WHERE closed IS NULL AND deadline > ?", (now,)
        ).fetchone()
        rows = self.db.execute(
            "SELECT * FROM v_waits WHERE closed IS NULL AND (left <= 0 OR deadline <= ?) ORDER BY id", (now,)
        ).fetchall()
        return [self._load(row) for row in rows], due["due"]


class Wait(Args):
    # A surface shows only the friendly fields, so a model never learns stream names. `on` is for programs.

    on: SkipJsonSchema[Annotated[tuple[Condition, ...], Field(max_length=64)]] = ()
    agents: Annotated[tuple[AgentName, ...], Field(description="Agents to end.")] = ()
    senders: Annotated[tuple[AgentName, ...], Field(alias="from", description="Agents to hear a message from.")] = ()
    tasks: Annotated[tuple[str, ...], Field(description="Tasks to settle, each `queue/id`.")] = ()
    board: Annotated[tuple[str, ...], Field(description="Objects to change, each `board/name`.")] = ()
    channels: Annotated[tuple[str, ...], Field(description="`#channel` or `+group`, for a new entry.")] = ()
    queue: Annotated[tuple[str, ...], Field(description="Queues to have open work.")] = ()
    mode: Annotated[Literal["all", "any"], Field(description="Whether everything must hold, or one thing.")] = "all"
    after: Annotated[Seq | None, Field(description="A `cursor` to count from, instead of what you have read.")] = None
    timeout: Annotated[float | None, Field(gt=0, description="Seconds until the wait gives up.")] = None
    hold: Annotated[float | None, Field(gt=0, description="Seconds to keep this call open before `pending`.")] = None


def _work_on(txn: Txn, queue: str) -> Condition:
    """Open work on a queue: the oldest open task, which holds at once, or else wherever the next will land. One
    transaction reads both, so a task added after `queue_empty` cannot slip by. `distinct` counts your own task too."""
    txn.view(Channels).require(f"queue/{queue}")
    tasks = txn.view(Tasks)
    task = tasks.next_open(queue)
    id = tasks.count(queue) + 1 if task is None else task.id
    return Condition(stream=f"task/{queue}/{id}", types=("task.added",), distinct="actor")


def _conditions(txn: Txn, a: Wait) -> tuple[Condition, ...]:
    """What a wait asks for, as conditions. `from` counts by subject, so a monitor's report counts as its child's."""
    conditions = (
        *a.on,
        *(Condition(stream=f"agent/{name}", types=("agent.ended",)) for name in a.agents),
        *(Condition(stream=f"inbox/{txn.me.name}", n=(name,), distinct="agent") for name in a.senders),
        *(Condition(stream=f"task/{task}", types=_TASK_SETTLED) for task in a.tasks),
        *(Condition(stream=f"board/{name}", types=_BOARD_VERSIONED) for name in a.board),
        *(Condition(stream=stream_of(channel)) for channel in a.channels),
        *(_work_on(txn, queue) for queue in a.queue),
    )
    if not conditions:
        raise Refused(
            "invalid", "a wait needs something to wait on: `agents`, `from`, `tasks`, `board`, `channels` or `queue`"
        )
    return conditions


def _start(txn: Txn, reader: str | None, stream: str, after: int | None) -> int:
    """Where counting begins. An omitted `after` is the server-held cursor, never the head."""
    if after is not None:
        return after
    return txn.view(Deliveries).cursor(reader, stream).offered


def _reader(principal: str) -> str | None:
    """The agent behind a principal id: only agents have cursors."""
    kind, _, name = principal.partition(":")
    return name if kind == "agent" else None


def out_of_turn(txn: Txn, waiter: str) -> bool:
    """Whether a wait may close now. One closes when its agent's turn does, so a wake cannot race that turn."""
    name = _reader(waiter)
    agent = None if name is None else txn.view(Agents).get(name)
    return agent is None or agent.state in _OUT_OF_TURN


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
    """Wait without spending a turn: for `agents` to end, a message `from` each named agent, `tasks` to settle, a
    version of `board` newer than you read, a new entry on `channels`, or `queue` to have open work. `mode` is `all` or
    `any`. One wait at a time: a new one replaces the old. `state` says what to do: `parked`, end your turn and the
    runtime starts your next when it holds or `timeout` passes; `released`, it holds, carry on; `pending`, `hold` ran
    out, call again or end your turn. Refused `not_permitted` for what you may not watch, and `unsupported` when this
    harness cannot park: pass `timeout` and a `hold` at least as long. `invalid` for an `after` past every event: leave
    it out."""
    _check_call(txn, a)
    after = checked_after(txn, a.after)
    asked = _conditions(txn, a)
    for condition in asked:
        txn.view(Grants).authorize(txn.me, wait_for, condition.stream)
    reader = _reader(txn.me.id)
    stamps = txn.view(Stamps)
    conditions = []
    for condition in asked:
        progress = Progress.of(condition, txn.me.id)
        for seen in stamps.events(condition.stream, after=_start(txn, reader, condition.stream, after)):
            progress = progress.advanced(seen)
            if progress.done:
                break
        conditions.append(progress)
    if reader is not None:
        for replaced in txn.view(Waits).open_for(txn.me.id):
            _close(txn, txn.me.id, replaced.id, "wait.cancelled")

    left = (len(conditions) if a.mode == "all" else 1) - sum(progress.done for progress in conditions)
    deadline = None if a.timeout is None else txn.now + a.timeout
    hops, _ = txn.view(Deliveries).heard(reader) or (-1, ())
    record = {"mode": a.mode, "left": left, "after": after, "deadline": deadline, "hops": hops}
    data = {**record, "conditions": conditions}
    event = txn.emit(
        "wait.registered", f"wait/{txn.me.name}", gist=f"wait on {asked[0].stream}"[:GIST_LIMIT], data=data
    )
    shown = WaitRecord.model_validate({**data, "id": event.seq, "waiter": txn.me.id}).shown()
    if left <= 0:
        _close(txn, txn.me.id, event.seq, "wait.released")
        _ack_all(txn, reader, (condition.stream for condition in asked), after)
        return {**shown, "state": "released"}
    if a.hold is not None:
        return {**shown, "state": "pending", "hold": a.hold}
    return {**shown, "state": "parked", "next": _END_TURN}


class WaitId(Args):
    id: Annotated[Seq | None, Field(description="A wait's id; your open wait if left out.")] = None


def _named_or_open(txn: Txn, id: int | None) -> WaitRecord | None:
    waits = txn.view(Waits)
    return waits.get(id) if id is not None else next(iter(waits.open_for(txn.me.id)), None)


@op("wait.cancel", tool=True)
def cancel(txn: Txn, a: WaitId) -> None:
    """Cancel your open wait. Refused `not_found` when it has closed already: nothing is waiting."""
    wait = _named_or_open(txn, a.id)
    if wait is None or wait.waiter != txn.me.id or wait.closed is not None:
        raise Refused("not_found", "no open wait of yours")
    _close(txn, wait.waiter, wait.id, "wait.cancelled")


class Release(Args):
    id: Seq
    told: bool = False


@op("wait.release", on=lambda a: f"wait/{a.id}", runtime=True)
def release(txn: Txn, a: Release) -> None:
    """Close a wait that holds or ran out of time. A waiter out of its turn hears through its inbox, which wakes it. One
    back in a turn keeps its wait until that turn ends, unless `told`: a held tool call is answering it."""
    wait = txn.view(Waits).get(a.id)
    if wait is None or wait.closed is not None or not (a.told or out_of_turn(txn, wait.waiter)):
        return
    holds = wait.left <= 0
    _close(txn, wait.waiter, a.id, "wait.released" if holds else "wait.expired")
    reader = _reader(wait.waiter)
    if holds:
        _ack_all(txn, reader, (condition.stream for condition in wait.conditions), wait.after)
    if reader is not None and not a.told:
        gist = "Your wait holds." if holds else f"Your wait timed out, missing {', '.join(wait.missing)}."
        post(txn, f"inbox/{reader}", gist[:GIST_LIMIT], wake=True, follows=wait.hops)


@op("wait.progress", query=True, tool=True)
def progress_of(txn: Txn, a: WaitId) -> dict[str, Any] | None:
    """Show your wait's `have`, `need` and `missing` while it is `open`, or how it closed: `released`, `expired` or
    `cancelled`. Nothing comes back when you have no such wait."""
    wait = _named_or_open(txn, a.id)
    if wait is None or (txn.me.kind == "agent" and wait.waiter != txn.me.id):
        return None
    if wait.closed is not None:
        return {"id": wait.id, "state": wait.closed}
    return {**wait.shown(), "state": "open", "holds": wait.left <= 0}


async def hold_open(kernel: Kernel, placed: dict[str, Any]) -> dict[str, Any]:
    """Keep a `wait` call open as a tool surface does, given its `pending` result. It returns how the wait stands: the
    way it closed, or `pending` with the wait still registered, so the agent may call again or end its turn.

    The call was authorized when it was placed, so this asks as the runtime.
    """
    expiry = kernel.clock.now() + placed["hold"]
    while True:
        head = kernel.head
        outcome = kernel.query(kernel.runtime, "wait.progress", {"id": placed["id"]})
        if outcome.refusal is not None:
            raise Refused(outcome.refusal.code, outcome.refusal.detail)
        shown = outcome.result
        if shown["state"] != "open":
            return {**placed, **shown}
        if shown["holds"]:
            await kernel.submit(kernel.runtime, "wait.release", {"id": placed["id"], "told": True})
            return {**placed, **shown, "state": "released"}
        remaining = expiry - kernel.clock.now()
        if remaining <= 0:
            return {**placed, **shown, "state": "pending"}
        tasks = [asyncio.ensure_future(kernel.changed(head)), asyncio.ensure_future(kernel.clock.sleep(remaining))]
        try:
            await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for task in tasks:
                task.cancel()
