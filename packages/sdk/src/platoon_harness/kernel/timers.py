"""Timers: an event sets one, and the clock daemon fires it as a runtime command."""

import asyncio
import json
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field, JsonValue

from .daemon import Daemon
from .model import NAME_LIMIT, Event
from .op import Args, op
from .txn import Txn
from .view import View, fold

if TYPE_CHECKING:
    from .kernel import Kernel

_LIMIT = 64
_RETRY_SECONDS = 1.0


class Timer(BaseModel, frozen=True):
    """The data of a `timer.set` event: run `op` at `due`. `key` names one firing and is its idempotency key."""

    due: float
    op: str = Field(max_length=NAME_LIMIT)
    args: dict[str, JsonValue]
    key: str = Field(max_length=NAME_LIMIT)


class Timers(View):
    """Timers set and not yet cleared."""

    schema = """
    CREATE TABLE v_timers(
        key TEXT PRIMARY KEY,
        due REAL NOT NULL,
        op TEXT NOT NULL,
        args TEXT NOT NULL,
        seq INTEGER NOT NULL
    ) WITHOUT ROWID, STRICT;
    CREATE INDEX v_timers_due ON v_timers(due, seq);
    """

    @fold("timer.set")
    def set(self, event: Event) -> None:
        timer = Timer.model_validate(event.data)
        self.db.execute(
            "INSERT OR REPLACE INTO v_timers VALUES (?, ?, ?, ?, ?)",
            (timer.key, timer.due, timer.op, json.dumps(timer.args), event.seq),
        )

    @fold("timer.cleared")
    def cleared(self, event: Event) -> None:
        self.db.execute("DELETE FROM v_timers WHERE key = ?", (event.data["key"],))

    def next(self) -> list[Timer]:
        """The soonest timers."""
        rows = self.db.execute("SELECT * FROM v_timers ORDER BY due, seq LIMIT ?", (_LIMIT,))
        return [Timer(due=r["due"], op=r["op"], args=json.loads(r["args"]), key=r["key"]) for r in rows]

    def besides(self, *ops: str) -> bool:
        """Whether a timer is set for anything but `ops`, however many of those come first."""
        marks = ", ".join("?" * len(ops))
        found = self.db.execute(f"SELECT 1 FROM v_timers WHERE op NOT IN ({marks}) LIMIT 1", ops).fetchone()
        return found is not None


class TimerKey(Args):
    key: str = Field(max_length=NAME_LIMIT)


@op("timer.next", query=True, runtime=True)
def next_timers(txn: Txn, a: Args) -> list[Timer]:
    """List the soonest timers."""
    return txn.view(Timers).next()


@op("timer.clear", on=lambda a: f"timer/{a.key}", runtime=True)
def clear_timer(txn: Txn, a: TimerKey) -> None:
    """Forget a timer."""
    txn.emit("timer.cleared", f"timer/{a.key}", gist=f"timer {a.key} cleared", data={"key": a.key})


async def fire_timers(kernel: "Kernel") -> float | None:
    """Fire what is due and return when the next timer is.

    Firing and clearing are two commands. A crash between them fires again under the same key, which answers
    from the first firing, so an op runs once however often this runs. A firing that left no event is not cleared.
    """
    now = kernel.clock.now()
    for timer in kernel.query(kernel.runtime, "timer.next", {}).result:
        if timer["due"] > now:
            return timer["due"]
        outcome = await kernel.submit(kernel.runtime, timer["op"], timer["args"], key=timer["key"])
        if outcome.refusal is not None and outcome.seq is None:
            return now + (outcome.refusal.retry_after or _RETRY_SECONDS)
        await kernel.submit(kernel.runtime, "timer.clear", {"key": timer["key"]})
    return None


async def _tick(kernel: "Kernel") -> None:
    while not kernel.closed:
        head = kernel.head
        due = await fire_timers(kernel)
        waits = [asyncio.ensure_future(kernel.changed(head))]
        if due is not None:
            waits.append(asyncio.ensure_future(kernel.clock.sleep(due - kernel.clock.now())))
        try:
            await asyncio.wait(waits, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for wait in waits:
                wait.cancel()


clock_daemon = Daemon("clock", _tick)
