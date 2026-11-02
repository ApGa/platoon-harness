"""Queues: tasks leased to one owner at a time, fenced by the seq of the claim."""

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field

from platoon_harness.kernel import Args, Event, Refused, Timer, Txn, View, fold, op

from .channels import Channel, Channels
from .common import DIGEST_ITEMS, BodyRef, Exposed, Gist, Name, expose_read, fitted

TaskState = Literal["open", "claimed", "done", "failed", "dead"]


class Task(BaseModel, frozen=True):
    """One task. `fence` and `lease_until` belong to its latest claim. A failed task may be claimed again."""

    queue: str
    id: str
    state: TaskState
    gist: str
    body: str | None
    owner: str | None
    fence: int | None
    lease_until: float | None
    claimed_at: float | None
    attempts: int
    seq: int

    @property
    def stream(self) -> str:
        return f"task/{self.queue}/{self.id}"

    def live(self, now: float) -> bool:
        """Whether its lease holds by this clock. Time passing is enough: no event need have said so."""
        return self.state == "claimed" and self.lease_until is not None and self.lease_until > now


class Tasks(View):
    """Tasks by queue, oldest first."""

    schema = """
    CREATE TABLE v_tasks(
        queue TEXT NOT NULL,
        id TEXT NOT NULL,
        state TEXT NOT NULL,
        gist TEXT NOT NULL,
        body TEXT,
        owner TEXT,
        fence INTEGER,
        lease_until REAL,
        claimed_at REAL,
        attempts INTEGER NOT NULL,
        seq INTEGER NOT NULL,
        PRIMARY KEY (queue, id)
    ) WITHOUT ROWID, STRICT;
    CREATE INDEX v_tasks_state ON v_tasks(queue, state, seq);
    CREATE INDEX v_tasks_owner ON v_tasks(owner, state);
    """

    @fold("task.added")
    def added(self, event: Event) -> None:
        data = event.data
        self.db.execute(
            "INSERT INTO v_tasks VALUES (?, ?, 'open', ?, ?, NULL, NULL, NULL, NULL, 0, ?)",
            (data["queue"], data["task"], event.gist, data["body"], event.seq),
        )

    @fold("task.claimed")
    def claimed(self, event: Event) -> None:
        data = event.data
        self.db.execute(
            """
            UPDATE v_tasks SET state = 'claimed', owner = ?, fence = ?, lease_until = ?, claimed_at = ?,
                attempts = attempts + 1
            WHERE queue = ? AND id = ?
            """,
            (event.actor, event.seq, data["lease_until"], event.wall_time, data["queue"], data["task"]),
        )

    @fold("task.renewed")
    def renewed(self, event: Event) -> None:
        data = event.data
        self.db.execute(
            "UPDATE v_tasks SET lease_until = ? WHERE queue = ? AND id = ?",
            (data["lease_until"], data["queue"], data["task"]),
        )

    def _settle(self, event: Event, state: str, *also: str) -> None:
        data = event.data
        changes = ", ".join(("state = ?", "owner = NULL", *also))
        self.db.execute(
            f"UPDATE v_tasks SET {changes} WHERE queue = ? AND id = ?", (state, data["queue"], data["task"])
        )

    @fold("task.released")
    def released(self, event: Event) -> None:
        self._settle(event, "open", "attempts = attempts - 1")

    @fold("lease.expired")
    def expired(self, event: Event) -> None:
        self._settle(event, "open")

    @fold("task.completed")
    def completed(self, event: Event) -> None:
        self._settle(event, "done")

    @fold("task.failed")
    def failed(self, event: Event) -> None:
        self._settle(event, "failed")

    @fold("task.died")
    def died(self, event: Event) -> None:
        self._settle(event, "dead")

    @fold("agent.ended")
    def owner_gone(self, event: Event) -> None:
        self.db.execute(
            "UPDATE v_tasks SET state = 'open', owner = NULL WHERE owner = ? AND state = 'claimed'",
            (f"agent:{event.agent}",),
        )

    def get(self, queue: str, id: str) -> Task | None:
        row = self.db.execute("SELECT * FROM v_tasks WHERE queue = ? AND id = ?", (queue, id)).fetchone()
        return None if row is None else self._load(row)

    def _load(self, row: Any) -> Task:
        return Task(**{key: row[key] for key in Task.model_fields})

    def _where(self, condition: str, *values: Any) -> list[Task]:
        return [self._load(row) for row in self.db.execute(f"SELECT * FROM v_tasks WHERE {condition}", values)]

    def next_open(self, queue: str) -> Task | None:
        rows = self.db.execute(
            "SELECT * FROM v_tasks WHERE queue = ? AND state IN ('open', 'failed') ORDER BY seq LIMIT 1", (queue,)
        ).fetchone()
        return None if rows is None else self._load(rows)

    def lapsed(self, queue: str, now: float) -> list[Task]:
        """Claimed tasks whose lease has run out by this clock, whether or not its timer has fired."""
        return self._where("queue = ? AND state = 'claimed' AND lease_until <= ? ORDER BY seq", queue, now)

    def held_by(self, queue: str, owner: str) -> list[Task]:
        return self._where("queue = ? AND owner = ? AND state = 'claimed' ORDER BY seq", queue, owner)

    def owned(self, owner: str) -> list[Task]:
        return self._where("owner = ? AND state = 'claimed' ORDER BY seq", owner)

    def listed(self, queue: str, state: str | None, after: int, limit: int) -> tuple[list[Task], int]:
        """A page past `after`, oldest first, and the true total."""
        match = "queue = ?1 AND (?2 IS NULL OR state = ?2)"
        total = self.db.execute(f"SELECT count(*) AS n FROM v_tasks WHERE {match}", (queue, state)).fetchone()["n"]
        return self._where(f"{match} AND seq > ?3 ORDER BY seq LIMIT ?4", queue, state, after, limit), total

    def count(self, queue: str) -> int:
        return self.db.execute("SELECT count(*) AS n FROM v_tasks WHERE queue = ?", (queue,)).fetchone()["n"]


def _queue(txn: Txn, name: str) -> Channel:
    return txn.view(Channels).require(f"queue/{name}")


def _note(task: Task, **data: Any) -> dict[str, Any]:
    return {"queue": task.queue, "task": task.id, **data}


def bury_if_spent(txn: Txn, task: Task, channel: Channel) -> None:
    """After `max_attempts` a task is dead, and a human sees it."""
    if task.attempts >= channel.max_attempts:
        data = _note(task, attempts=task.attempts)
        txn.emit("task.died", task.stream, gist=f"task {task.id} dead after {task.attempts} attempts", data=data)


def expire(txn: Txn, task: Task, channel: Channel) -> None:
    """A lease ran out: the task is free again, or dead if that was its last attempt."""
    txn.emit("lease.expired", task.stream, gist=f"lease on task {task.id} expired", data=_note(task, fence=task.fence))
    bury_if_spent(txn, task, channel)


def _arm(txn: Txn, task: str, queue: str, fence: int, due: float, step: int) -> None:
    key = f"lease/{queue}/{task}/{fence}/{step}"
    args = {"queue": queue, "task": task, "fence": fence}
    timer = Timer(due=due, op="lease.expire", args=args, key=key)
    txn.emit("timer.set", f"timer/{key}", gist=f"timer {key} set", data=timer)


class Add(Args):
    queue: Name
    gist: Gist
    body: BodyRef | None = None
    based_on: tuple[str, ...] = ()


@op("task.add", on=lambda a: f"queue/{a.queue}", tool=True)
def add(txn: Txn, a: Add) -> dict[str, Any]:
    """Add a task to a queue. Refused `not_permitted` when you may not write this queue: call `channel.list`."""
    _queue(txn, a.queue)
    id = str(txn.view(Tasks).count(a.queue) + 1)
    data = {"queue": a.queue, "task": id, "body": a.body}
    refs = [a.body] if a.body else ()
    txn.emit("task.added", f"task/{a.queue}/{id}", gist=a.gist, based_on=a.based_on, refs=refs, data=data)
    return {"task": id}


class Claim(Args):
    queue: Name
    task: str | None = None


@op("task.claim", on=lambda a: f"queue/{a.queue}", tool=True)
def claim(txn: Txn, a: Claim) -> dict[str, Any]:
    """Claim the next open task, or `task`. First claim wins; a loss names the owner. Keep working: the runtime renews
    your lease while you are active, and `task.complete` finds it without being told. Exclusive ownership is not
    exactly-once execution. Refused `queue_empty` when nothing is open, `queue_full` at your `max_inflight`: finish
    what you hold first."""
    channel = _queue(txn, a.queue)
    tasks = txn.view(Tasks)
    for lapsed in tasks.lapsed(a.queue, txn.now):
        expire(txn, lapsed, channel)
    held = sum(task.live(txn.now) for task in tasks.held_by(a.queue, txn.me.id))
    if held >= channel.max_inflight:
        raise Refused("queue_full", {"held": held, "max_inflight": channel.max_inflight})
    if a.task is None:
        task = tasks.next_open(a.queue)
        if task is None:
            raise Refused("queue_empty", f"nothing is open on {a.queue}")
    else:
        task = tasks.get(a.queue, a.task)
        if task is None:
            raise Refused("not_found", f"no task {a.task} on {a.queue}")
        if task.state not in ("open", "failed"):
            raise Refused("conflict", {"state": task.state, "owner": task.owner})
    until = _lease_until(txn.now, txn.now, channel)
    data = _note(task, lease_until=until)
    event = txn.emit("task.claimed", task.stream, gist=f"task {task.id} claimed", data=data)
    expose_read(txn, [Exposed.of(f"{task.stream}@1", "gist", task.gist)])
    _arm(txn, task.id, a.queue, event.seq, until, event.seq)
    return {
        "queue": a.queue,
        "task": task.id,
        "fence": event.seq,
        "lease_until": until,
        "gist": task.gist,
        "body": task.body,
        "attempt": task.attempts + 1,
    }


def _lease_until(now: float, claimed_at: float, channel: Channel) -> float:
    until = now + channel.lease
    return until if channel.lease_max is None else min(until, claimed_at + channel.lease_max)


class Held(Args):
    queue: Name
    task: str | None = None
    fence: int | None = None


def _caller_lease(txn: Txn, a: Held, lapsed: Literal["stale_fence", "lease_lost"]) -> Task:
    """The task a caller's lease covers. With no `task` or `fence`, that is its live lease, since a model can lose both.

    Expiry alone stales a lease, reassigned or not. The runtime may act on an owner's behalf, fence in hand.
    """
    tasks = txn.view(Tasks)
    if a.task is not None:
        task = tasks.get(a.queue, a.task)
        if task is None:
            raise Refused("not_found", f"no task {a.task} on {a.queue}")
    else:
        held = tasks.held_by(a.queue, txn.me.id)
        if len(held) > 1:
            raise Refused("invalid", {"holding": [task.id for task in held], "detail": "name a task"})
        if not held:
            raise Refused(lapsed, f"you hold no lease on {a.queue}")
        task = held[0]
    mine = txn.me.kind == "runtime" or task.owner == txn.me.id
    if not (mine and task.live(txn.now)) or a.fence not in (None, task.fence):
        raise Refused(lapsed, {"task": task.id, "fence": a.fence, "current": task.fence, "state": task.state})
    return task


@op("task.renew", on=lambda a: f"queue/{a.queue}", tool=True)
def renew(txn: Txn, a: Held) -> dict[str, Any]:
    """Extend your lease, up to the queue's `lease_max`. The runtime already does this while you are active. Refused
    `lease_lost` when the lease has gone: claim again."""
    channel = _queue(txn, a.queue)
    task = _caller_lease(txn, a, "lease_lost")
    assert task.claimed_at is not None and task.fence is not None
    until = _lease_until(txn.now, task.claimed_at, channel)
    if task.lease_until is not None and until <= task.lease_until:
        return {"task": task.id, "fence": task.fence, "lease_until": task.lease_until}
    event = txn.emit("task.renewed", task.stream, gist=f"task {task.id} renewed", data=_note(task, lease_until=until))
    _arm(txn, task.id, a.queue, task.fence, until, event.seq)
    return {"task": task.id, "fence": task.fence, "lease_until": until}


@op("task.release", on=lambda a: f"queue/{a.queue}", tool=True)
def release(txn: Txn, a: Held) -> None:
    """Give a task back unfinished, which spends no attempt. Refused `stale_fence` when your lease has gone."""
    task = _caller_lease(txn, a, "stale_fence")
    txn.emit("task.released", task.stream, gist=f"task {task.id} released", data=_note(task))


class Finish(Held):
    gist: Gist = ""
    body: BodyRef | None = None
    based_on: tuple[str, ...] = ()


@op("task.complete", on=lambda a: f"queue/{a.queue}", tool=True)
def complete(txn: Txn, a: Finish) -> None:
    """Finish your task. `fence` defaults to your live lease. Refused `stale_fence` once the lease has expired, even if
    nobody else took the task: your work may be lost, so check the task and claim it again if it is open."""
    task = _caller_lease(txn, a, "stale_fence")
    assert task.fence is not None
    data = _note(task, fence=task.fence, body=a.body)
    gist = a.gist or f"task {task.id} completed"
    refs = [a.body] if a.body else ()
    txn.emit("task.completed", task.stream, gist=gist, cause=[task.fence], based_on=a.based_on, refs=refs, data=data)


@op("task.fail", on=lambda a: f"queue/{a.queue}", tool=True)
def fail(txn: Txn, a: Finish) -> None:
    """Report that this attempt failed. Someone may claim the task again until `max_attempts`, when it is dead and shown
    to a human. Refused `stale_fence` once your lease has expired: the task has moved on without you."""
    channel = _queue(txn, a.queue)
    task = _caller_lease(txn, a, "stale_fence")
    assert task.fence is not None
    gist = a.gist or f"task {task.id} failed"
    txn.emit("task.failed", task.stream, gist=gist, cause=[task.fence], data=_note(task, fence=task.fence, body=a.body))
    bury_if_spent(txn, task, channel)


class Fence(Args):
    queue: Name
    task: str
    fence: int


@op("lease.expire", on=lambda a: f"queue/{a.queue}", runtime=True)
def expire_lease(txn: Txn, a: Fence) -> None:
    """Fired by a timer. A lease renewed, reclaimed or settled since then is left alone."""
    task = txn.view(Tasks).get(a.queue, a.task)
    if task is not None and task.fence == a.fence and task.state == "claimed" and not task.live(txn.now):
        expire(txn, task, _queue(txn, a.queue))


class ListTasks(Args):
    queue: Name
    state: TaskState | None = None
    after: Annotated[int, Field(ge=0)] = 0
    limit: Annotated[int, Field(ge=1, le=DIGEST_ITEMS)] = DIGEST_ITEMS


@op("task.list", on=lambda a: f"queue/{a.queue}", exposes=True, tool=True)
def list_tasks(txn: Txn, a: ListTasks) -> dict[str, Any]:
    """List a queue's tasks as gists, oldest first, with the true `total` and a `cursor` to pass as `after`. Refused
    `not_permitted` when you may not read this queue."""
    rows, total = txn.view(Tasks).listed(a.queue, a.state, a.after, a.limit)
    tasks = fitted(rows, show=lambda task: task.model_dump())
    expose_read(txn, [Exposed.of(f"{task.stream}@1", "gist", task.gist) for task in tasks])
    return {
        "tasks": [task.model_dump() for task in tasks],
        "total": total,
        "cursor": tasks[-1].seq if tasks else a.after,
    }
