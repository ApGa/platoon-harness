"""Queues: tasks leased to one owner at a time, fenced by the seq of the claim."""

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field

from platoon_harness.kernel import Args, Event, Refused, Timer, Txn, View, fold, op

from .channels import Channel, Channels
from .common import (
    DIGEST_ITEMS,
    BasedOn,
    Body,
    Exposed,
    Gist,
    Labels,
    Name,
    Seq,
    address,
    cited,
    expose_read,
    fitted,
)
from .messages import announce
from .sessions import labelled

TaskState = Literal["open", "claimed", "done", "failed", "dead"]


class Task(BaseModel, frozen=True):
    """One task. `fence` and `lease_until` belong to its latest claim. A failed task may be claimed again. `result` is
    what its latest attempt reported, and `result_ref` the ref of that report. `body` and `result_body` are hashes,
    which no reader sees."""

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
    result: str | None
    result_body: str | None
    result_ref: str | None

    @property
    def stream(self) -> str:
        return f"task/{self.queue}/{self.id}"

    @property
    def ref(self) -> str:
        """The task as a ref: its `task.added`."""
        return f"{self.stream}@1"

    def shown(self) -> dict[str, Any]:
        """The task as a reader gets it, by its ref, saying whether it and its result have a body, which `blob.get`
        reads by `ref` and `result_ref`."""
        owner = None if self.owner is None else address(self.owner)
        flags = {"body": self.body is not None, "result_body": self.result_body is not None}
        return {**self.model_dump(), "ref": self.ref, "owner": owner, **flags}

    def live(self, now: float) -> bool:
        """Whether its lease holds by this clock. Time passing is enough: no event need have said so."""
        return self.state == "claimed" and self.lease_until is not None and self.lease_until > now


class Tasks(View):
    """Tasks by queue, oldest first, and each claim by its claimant, with the event that ended it: its completion,
    failure, release or lapse, or its claimant's end."""

    version = 2
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
        result TEXT,
        result_body TEXT,
        result_ref TEXT,
        PRIMARY KEY (queue, id)
    ) WITHOUT ROWID, STRICT;
    CREATE INDEX v_tasks_state ON v_tasks(queue, state, seq);
    CREATE INDEX v_tasks_owner ON v_tasks(owner, state);
    CREATE TABLE v_tasks_claims(
        owner TEXT NOT NULL,
        queue TEXT NOT NULL,
        id TEXT NOT NULL,
        claimed INTEGER NOT NULL,
        ended INTEGER,
        PRIMARY KEY (owner, claimed)
    ) WITHOUT ROWID, STRICT;
    CREATE INDEX v_tasks_claims_open ON v_tasks_claims(queue, id, ended);
    """

    @fold("task.added")
    def added(self, event: Event) -> None:
        data = event.data
        self.db.execute(
            "INSERT INTO v_tasks VALUES (?, ?, 'open', ?, ?, NULL, NULL, NULL, NULL, 0, ?, NULL, NULL, NULL)",
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
        claim = (event.actor, data["queue"], data["task"], event.seq)
        self.db.execute("INSERT INTO v_tasks_claims VALUES (?, ?, ?, ?, NULL)", claim)

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

    def _end_claim(self, event: Event) -> None:
        """A task's one live claim ends with this event."""
        data = event.data
        self.db.execute(
            "UPDATE v_tasks_claims SET ended = ? WHERE queue = ? AND id = ? AND ended IS NULL",
            (event.seq, data["queue"], data["task"]),
        )

    @fold("task.released")
    def released(self, event: Event) -> None:
        self._settle(event, "open", "attempts = attempts - 1")
        self._end_claim(event)

    @fold("lease.expired")
    def expired(self, event: Event) -> None:
        self._settle(event, "open")
        self._end_claim(event)

    @fold("task.completed", "task.failed")
    def reported(self, event: Event) -> None:
        data = event.data
        self._settle(event, "done" if event.type == "task.completed" else "failed")
        self._end_claim(event)
        self.db.execute(
            "UPDATE v_tasks SET result = ?, result_body = ?, result_ref = ? WHERE queue = ? AND id = ?",
            (event.gist, data["body"], f"{event.stream}@{event.version}", data["queue"], data["task"]),
        )

    @fold("task.died")
    def died(self, event: Event) -> None:
        self._settle(event, "dead")

    @fold("agent.ended")
    def owner_gone(self, event: Event) -> None:
        self.db.execute(
            "UPDATE v_tasks SET state = 'open', owner = NULL WHERE owner = ? AND state = 'claimed'",
            (f"agent:{event.agent}",),
        )
        self.db.execute(
            "UPDATE v_tasks_claims SET ended = ? WHERE owner = ? AND ended IS NULL", (event.seq, f"agent:{event.agent}")
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

    def claims(self, owner: str) -> list[tuple[str, str, int, int | None]]:
        """Each claim `owner` made, oldest first: its queue, its task, the seq of its claim and of the event that ended
        it, or None while it holds."""
        rows = self.db.execute("SELECT * FROM v_tasks_claims WHERE owner = ? ORDER BY claimed", (owner,))
        return [(row["queue"], row["id"], row["claimed"], row["ended"]) for row in rows]

    def any_claimed(self) -> bool:
        return self.db.execute("SELECT 1 FROM v_tasks WHERE state = 'claimed' LIMIT 1").fetchone() is not None

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


QueueName = Annotated[Name, Field(description="The queue. `channel.list` names them.")]
TaskId = Annotated[str | None, Field(description="A task's id; your live lease if left out.")]


class Add(Args):
    queue: QueueName
    gist: Gist
    body: Body = None
    labels: Labels = {}
    based_on: BasedOn = ()


@op("task.add", on=lambda a: f"queue/{a.queue}", tool=True)
def add(txn: Txn, a: Add) -> dict[str, Any]:
    """Add a task to a queue. `gist` says what to do; put anything longer in `body`. Refused `not_permitted` when you
    may not write this queue, and `not_found` when no such queue exists. Call `channel.list` to see yours."""
    channel = _queue(txn, a.queue)
    id = str(txn.view(Tasks).count(a.queue) + 1)
    data = {"queue": a.queue, "task": id, "body": a.body, "labels": labelled(txn, a.labels)}
    refs = [a.body] if a.body else ()
    based_on = cited(txn, a.based_on)
    stream = f"task/{a.queue}/{id}"
    event = txn.emit("task.added", stream, gist=a.gist, based_on=based_on, refs=refs, data=data, v=2)
    announce(txn, channel, a.gist, event)
    return {"task": id, "ref": f"{event.stream}@{event.version}"}


class Claim(Args):
    queue: QueueName
    task: Annotated[str | None, Field(description="A task's id; the next open task if left out.")] = None


@op("task.claim", on=lambda a: f"queue/{a.queue}", tool=True)
def claim(txn: Txn, a: Claim) -> dict[str, Any]:
    """Claim the next open task, or `task` by id. `text` is its body; a long one comes back cut, with `rest` a ref. Pass
    it to `blob.get`. The runtime renews an agent's lease while its harness is at work. `task.complete` finds the task
    without being told. If your lease lapses someone else may redo the work, so make it safe to repeat. Refused
    `conflict`, naming the owner, when `task` is taken, and when you hold `max_inflight` tasks: claim another, or finish
    one first. `not_found` when no such task or queue exists. `queue_empty` when nothing is open. Call `wait` with
    `queue` then, and end your turn."""
    channel = _queue(txn, a.queue)
    tasks = txn.view(Tasks)
    for lapsed in tasks.lapsed(a.queue, txn.now):
        expire(txn, lapsed, channel)
    held = sum(task.live(txn.now) for task in tasks.held_by(a.queue, txn.me.id))
    if held >= channel.max_inflight:
        raise Refused("conflict", {"held": held, "max_inflight": channel.max_inflight})
    if a.task is None:
        task = tasks.next_open(a.queue)
        if task is None:
            raise Refused("queue_empty", f"nothing is open on {a.queue}")
    else:
        task = tasks.get(a.queue, a.task)
        if task is None:
            raise Refused("not_found", f"no task {a.task} on {a.queue}")
        if task.state not in ("open", "failed"):
            raise Refused("conflict", {"state": task.state, "owner": task.shown()["owner"]})
    until = _lease_until(txn.now, txn.now, channel)
    data = _note(task, lease_until=until)
    event = txn.emit("task.claimed", task.stream, gist=f"task {task.id} claimed", data=data)
    expose_read(txn, [Exposed.gist(task.ref, task.gist)])
    _arm(txn, task.id, a.queue, event.seq, until, event.seq)
    claimed = {
        "queue": a.queue,
        "task": task.id,
        "ref": task.ref,
        "fence": event.seq,
        "lease_until": until,
        "gist": task.gist,
        "body": task.body is not None,
        "attempt": task.attempts + 1,
    }
    return claimed if task.body is None else {**claimed, "text": None}  # A surface fetches what an op may not read.


def _lease_until(now: float, claimed_at: float, channel: Channel) -> float:
    until = now + channel.lease
    return until if channel.lease_max is None else min(until, claimed_at + channel.lease_max)


class Held(Args):
    queue: QueueName
    task: TaskId = None
    fence: Annotated[int | None, Field(description="The `fence` from your claim; your live lease if left out.")] = None


def _caller_lease(txn: Txn, a: Held) -> Task:
    """The task a caller's lease covers. With no `task` or `fence`, that is its live lease, since a model can lose both.

    Expiry alone stales a lease, reassigned or not. The runtime may act on an owner's behalf, fence in hand.
    """
    tasks = txn.view(Tasks)
    if a.task is not None:
        task = tasks.get(a.queue, a.task)
        if task is None:
            raise Refused("not_found", f"no task {a.task} on {a.queue}")
    else:
        held = [task for task in tasks.held_by(a.queue, txn.me.id) if task.live(txn.now)]
        if len(held) > 1:
            raise Refused("invalid", {"holding": [task.id for task in held], "detail": "name a task"})
        if not held:
            raise Refused("stale_fence", f"you hold no live lease on {a.queue}")
        task = held[0]
    mine = txn.me.kind == "runtime" or task.owner == txn.me.id
    if not (mine and task.live(txn.now)) or a.fence not in (None, task.fence):
        raise Refused("stale_fence", {"task": task.id, "fence": a.fence, "current": task.fence, "state": task.state})
    return task


@op("task.renew", on=lambda a: f"queue/{a.queue}")
def renew(txn: Txn, a: Held) -> dict[str, Any]:
    """Extend your lease, up to the queue's `lease_max`. The runtime already does this for an agent while its harness
    is at work. Refused `stale_fence` when the lease has gone: claim again."""
    channel = _queue(txn, a.queue)
    task = _caller_lease(txn, a)
    assert task.claimed_at is not None and task.fence is not None
    until = _lease_until(txn.now, task.claimed_at, channel)
    if task.lease_until is not None and until <= task.lease_until:
        return {"task": task.id, "fence": task.fence, "lease_until": task.lease_until}
    event = txn.emit("task.renewed", task.stream, gist=f"task {task.id} renewed", data=_note(task, lease_until=until))
    _arm(txn, task.id, a.queue, task.fence, until, event.seq)
    return {"task": task.id, "fence": task.fence, "lease_until": until}


@op("task.release", on=lambda a: f"queue/{a.queue}", tool=True)
def release(txn: Txn, a: Held) -> None:
    """Give a task back unfinished, which spends no attempt. Refused `stale_fence` when your lease has gone: there is
    nothing to give back."""
    task = _caller_lease(txn, a)
    txn.emit("task.released", task.stream, gist=f"task {task.id} released", data=_note(task))


class Finish(Held):
    gist: Annotated[Gist, Field(description="The result, at most 280 characters. `task.list` shows it.")] = ""
    body: Body = None
    based_on: BasedOn = ()


def _report(txn: Txn, a: Finish, event_type: str, outcome: str) -> tuple[Task, str]:
    """Settle the caller's lease with its result, and give the result's ref. A failure says what it rests on as much as
    a success does."""
    task = _caller_lease(txn, a)
    assert task.fence is not None
    data = _note(task, fence=task.fence, body=a.body)
    gist = a.gist or f"task {task.id} {outcome}"
    refs = [a.body] if a.body else ()
    based_on = cited(txn, a.based_on)
    event = txn.emit(event_type, task.stream, gist=gist, cause=[task.fence], based_on=based_on, refs=refs, data=data)
    return task, f"{event.stream}@{event.version}"


@op("task.complete", on=lambda a: f"queue/{a.queue}", tool=True)
def complete(txn: Txn, a: Finish) -> dict[str, Any]:
    """Finish your task, with `gist` and `body` as its result. `task.list` shows it. Refused `stale_fence` once the
    lease has expired, even if nobody else took the task: your work may be lost, so check the task and claim it again if
    it is open. `invalid` when you hold several: name `task`."""
    return {"ref": _report(txn, a, "task.completed", "completed")[1]}


@op("task.fail", on=lambda a: f"queue/{a.queue}", tool=True)
def fail(txn: Txn, a: Finish) -> dict[str, Any]:
    """Report that this attempt failed, and why. Someone may claim the task again until `max_attempts`, when it is dead
    and shown to a human. Refused `stale_fence` once your lease has expired: the task has moved on without you."""
    task, ref = _report(txn, a, "task.failed", "failed")
    bury_if_spent(txn, task, _queue(txn, a.queue))
    return {"ref": ref}


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


class Owner(Args):
    agent: Name


@op("lease.due", query=True, runtime=True)
def leases_due(txn: Txn, a: Owner) -> list[dict[str, Any]]:
    """List an agent's leases past half their time that `task.renew` could extend, which the host does on harness
    activity. It asks first, so that activity with nothing to renew journals nothing."""
    due = []
    for task in txn.view(Tasks).owned(f"agent:{a.agent}"):
        channel = _queue(txn, task.queue)
        assert task.lease_until is not None and task.claimed_at is not None
        grows = _lease_until(txn.now, task.claimed_at, channel) > task.lease_until
        if task.live(txn.now) and grows and task.lease_until - txn.now < channel.lease / 2:
            due.append({"queue": task.queue, "task": task.id, "fence": task.fence})
    return due


class ListTasks(Args):
    queue: QueueName
    state: Annotated[TaskState | None, Field(description="Only tasks in this state.")] = None
    after: Annotated[Seq, Field(description="A `cursor` from an earlier list.")] = 0
    limit: Annotated[int, Field(ge=1, le=DIGEST_ITEMS, description="The most tasks to return.")] = DIGEST_ITEMS


@op("task.list", on=lambda a: f"queue/{a.queue}", exposes=True, tool=True)
def list_tasks(txn: Txn, a: ListTasks) -> dict[str, Any]:
    """List a queue's tasks, oldest first, each with its `result` once it has one, with the true `total` and a `cursor`
    to pass as `after`, or none at the end. Refused `not_permitted` when you may not read this queue, and `not_found`
    when no such queue exists. Call `channel.list` to see yours."""
    _queue(txn, a.queue)
    rows, total = txn.view(Tasks).listed(a.queue, a.state, a.after, a.limit)
    tasks = fitted(rows, show=Task.shown)
    exposed = [Exposed.gist(task.ref, task.gist) for task in tasks]
    exposed += [Exposed.gist(task.result_ref, task.result) for task in tasks if task.result_ref and task.result]
    expose_read(txn, exposed)
    more = len(tasks) < len(rows) or len(rows) == a.limit
    return {
        "tasks": [task.shown() for task in tasks],
        "total": total,
        "cursor": tasks[-1].seq if tasks and more else None,
    }
