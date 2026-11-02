"""What clients render: `roster`, `attention` and `changes`, watched as a snapshot and then keyed changes."""

import json
from typing import Annotated, Any, Literal

from pydantic import Field

from platoon_harness.kernel import Args, Effect, Effects, Event, Stamps, Txn, View, fold, op

from . import why
from .agents import Agent, Agents
from .approvals import Approvals
from .budgets import Budget
from .messages import Deliveries
from .tasks import Tasks
from .waits import Waits

WATCH_SPAN = 4096


def _resolve_actions(event: Event) -> list[dict[str, Any]]:
    """Buttons as op references, each with the version it was drawn from."""
    return [
        {
            "label": verdict.capitalize(),
            "op": "approval.resolve",
            "args": {"id": event.data["id"], "verdict": verdict, "expected_version": event.version},
        }
        for verdict in ("allow", "deny")
    ]


class Attention(View):
    """Where a human must act. A row closes in place, so a watcher hears that it went away."""

    schema = """
    CREATE TABLE v_attention(
        id TEXT PRIMARY KEY,
        kind TEXT NOT NULL,
        agent TEXT,
        gist TEXT NOT NULL,
        since_seq INTEGER NOT NULL,
        version INTEGER NOT NULL,
        actions TEXT NOT NULL,
        open INTEGER NOT NULL,
        seq INTEGER NOT NULL
    ) WITHOUT ROWID, STRICT;
    CREATE INDEX v_attention_open ON v_attention(open, since_seq);
    CREATE INDEX v_attention_seq ON v_attention(seq);
    """

    def _raise(self, id: str, kind: str, event: Event, actions: list[dict[str, Any]] | None = None) -> None:
        self.db.execute(
            "INSERT OR REPLACE INTO v_attention VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)",
            (id, kind, event.agent, event.gist, event.seq, event.version, json.dumps(actions or []), event.seq),
        )

    def _lower(self, event: Event, condition: str, *values: Any) -> None:
        self.db.execute(
            f"UPDATE v_attention SET open = 0, seq = ? WHERE open = 1 AND {condition}", (event.seq, *values)
        )

    @fold("approval.requested")
    def approval_asked(self, event: Event) -> None:
        if event.data["policy"] == "ask":
            self._raise(f"approval/{event.data['id']}", "approval", event, _resolve_actions(event))

    @fold("approval.resolved")
    def approval_decided(self, event: Event) -> None:
        self._lower(event, "id = ?", f"approval/{event.data['id']}")

    @fold("agent.ended")
    def agent_gone(self, event: Event) -> None:
        self._lower(event, "agent = ?", event.agent)

    @fold("message.sent")
    def mention(self, event: Event) -> None:
        if event.data["mention"] is not None:
            self._raise(f"{event.stream}@{event.version}", "mention", event)
        if event.data["reply_to"] is not None:
            self._lower(event, "id = ?", event.data["reply_to"])

    @fold("effect.uncertain")
    def uncertain(self, event: Event) -> None:
        self._raise(f"effect/{event.data['id']}", "uncertain", event)

    @fold("effect.finished", "effect.retried")
    def certain(self, event: Event) -> None:
        self._lower(event, "id = ?", f"effect/{event.data['id']}")

    @fold("effect.failed")
    def failed(self, event: Event) -> None:
        self._raise(f"effect/{event.data['id']}", "failed", event)

    @fold("task.died")
    def dead_task(self, event: Event) -> None:
        self._raise(event.stream, "dead_task", event)

    @fold("wake.refused")
    def wake_refused(self, event: Event) -> None:
        self._raise(f"wake/{event.agent}", "hops" if event.data["why"] == "hops" else "budget", event)

    @fold("budget.set")
    def budget_set(self, event: Event) -> None:
        self._lower(event, "kind = 'budget'")

    @fold("turn.started")
    def turn_started(self, event: Event) -> None:
        self._lower(event, "id = ? OR (agent = ? AND kind = 'failed')", f"wake/{event.agent}", event.agent)

    def _row(self, row: Any) -> dict[str, Any]:
        return {**dict(row), "actions": json.loads(row["actions"]), "open": bool(row["open"])}

    def rows(self) -> list[dict[str, Any]]:
        return [
            self._row(row) for row in self.db.execute("SELECT * FROM v_attention WHERE open = 1 ORDER BY since_seq")
        ]

    def since(self, after: int) -> list[dict[str, Any]]:
        return [
            self._row(row) for row in self.db.execute("SELECT * FROM v_attention WHERE seq > ? ORDER BY seq", (after,))
        ]


class Changes(View):
    """What changed, per agent and path, from a runtime probe at each turn end. `None` means not measured."""

    schema = """
    CREATE TABLE v_changes(
        agent TEXT NOT NULL,
        path TEXT NOT NULL,
        added INTEGER,
        removed INTEGER,
        tests TEXT,
        seq INTEGER NOT NULL,
        PRIMARY KEY (agent, path)
    ) WITHOUT ROWID, STRICT;
    CREATE INDEX v_changes_seq ON v_changes(seq);
    """

    @fold("change.recorded")
    def recorded(self, event: Event) -> None:
        data = event.data
        self.db.execute(
            "INSERT OR REPLACE INTO v_changes VALUES (?, ?, ?, ?, ?, ?)",
            (event.agent, data["path"], data["added"], data["removed"], data["tests"], event.seq),
        )

    def since(self, after: int) -> list[dict[str, Any]]:
        rows = self.db.execute("SELECT * FROM v_changes WHERE seq > ? ORDER BY seq", (after,))
        return [{**dict(row), "since_mark": after} for row in rows]


def _why(txn: Txn, agent: Agent, uncertain: list[Effect], dues: dict[str, float]) -> why.Why | None:
    """The one thing most worth saying about this agent, or nothing if it needs no explaining."""
    if agent.ended:
        return why.Lost(reason=agent.reason or "unknown") if agent.status == "lost" else None
    if pending := txn.view(Approvals).pending_for(agent.name):
        return why.Approval(id=pending[0].id)
    if (blocked := txn.view(Deliveries).blocked(agent.name)) is not None:
        return why.Budget(code=blocked)
    if failing := [effect for effect in uncertain if effect.agent == agent.name]:
        return why.Infra(detail=f"{failing[0].kind} is uncertain")
    if agent.state == "waiting" and (waits := txn.view(Waits).open_for(agent.id)):
        wait = waits[0]
        missing = wait.missing
        if len(missing) == 1 and missing[0].startswith("@"):
            return why.Peer(id=missing[0].removeprefix("@"))
        return why.Wait(have=wait.have, need=wait.need, missing=missing)
    if agent.name in dues:
        return why.Timer(at=dues[agent.name])
    if agent.state == "idle" and (leases := txn.view(Tasks).owned(agent.id)):
        return why.Lease(id=leases[0].stream)
    return None


def _roster(txn: Txn, names: set[str] | None = None) -> list[dict[str, Any]]:
    uncertain = txn.view(Effects).in_state("uncertain")
    dues = {reader: due for reader, due, _ in txn.view(Deliveries).waking() if due > txn.now}
    deliveries = txn.view(Deliveries)
    budget = txn.view(Budget)
    return [
        {
            "agent": agent.name,
            "role": agent.role,
            "harness": agent.harness,
            "model": agent.model,
            "state": agent.state,
            "activity": agent.activity,
            "why": _why(txn, agent, uncertain, dues),
            "unread": deliveries.unread(agent.name),
            "levels": agent.levels,
            "usage": budget.usage_of(agent.name),
        }
        for agent in txn.view(Agents).listed()
        if names is None or agent.name in names
    ]


@op("attention.list", query=True)
def attention_list(txn: Txn, a: Args) -> list[dict[str, Any]]:
    """List what needs a human now, each with the actions that would settle it."""
    return txn.view(Attention).rows()


class Watch(Args):
    name: Literal["roster", "attention", "changes"]
    after: Annotated[int, Field(ge=0)] | None = None


def _snapshot(txn: Txn, name: str) -> list[dict[str, Any]]:
    if name == "roster":
        return _roster(txn)
    return txn.view(Attention).rows() if name == "attention" else txn.view(Changes).since(0)


def _changed(txn: Txn, name: str, after: int) -> tuple[list[dict[str, Any]], list[str]]:
    """Rows changed past `after`, and the keys that went away."""
    if name == "roster":
        touched = {event.agent for event in txn.view(Stamps).events(after=after) if event.agent is not None}
        return _roster(txn, touched), []
    if name == "changes":
        return txn.view(Changes).since(after), []
    rows = txn.view(Attention).since(after)
    return [row for row in rows if row["open"]], [row["id"] for row in rows if not row["open"]]


@op("view.watch", query=True)
def watch(txn: Txn, a: Watch) -> dict[str, Any]:
    """A snapshot, then keyed changes. Pass `cursor` as the next `after`; a reader too far behind gets a new snapshot.

    Snapshot and cursor come from one read, so nothing commits between them.
    """
    head = txn.view(Stamps).head()
    if a.after is None or head - a.after > WATCH_SPAN:
        return {"snapshot": True, "rows": _snapshot(txn, a.name), "removed": [], "cursor": head}
    rows, removed = _changed(txn, a.name, a.after)
    return {"snapshot": False, "rows": rows, "removed": removed, "cursor": head}
