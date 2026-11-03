"""What clients render: `roster`, `attention` and `changes`, watched as a snapshot and then keyed changes."""

import json
from typing import Annotated, Any, Literal

from pydantic import Field

from platoon_harness.kernel import Args, Effect, Effects, Event, Stamps, Txn, View, fold, op

from . import why
from .agents import Agent, Agents
from .approvals import Approvals
from .budgets import Budgets
from .common import name_of
from .messages import Deliveries
from .tasks import Tasks
from .waits import Waits

WATCH_SPAN = 4096
_MOOT_WITH_ITS_AGENT = ("approval", "uncertain", "failed", "hops", "budget")


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


def _settle_actions(event: Event) -> list[dict[str, Any]]:
    """Whether an effect happened is for a person to say, and the first to say wins."""
    return [
        {"label": label, "op": "effect.settle", "args": {"id": event.data["id"], "happened": happened}}
        for label, happened in (("It happened", True), ("It did not", False))
    ]


class Attention(View):
    """Where a human must act. A row closes in place, so a watcher hears that it went away."""

    version = 2
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
        """What only that agent could have settled is moot. A final report nobody received waits for a human."""
        marks = ", ".join("?" * len(_MOOT_WITH_ITS_AGENT))
        self._lower(event, f"agent = ? AND kind IN ({marks})", event.agent, *_MOOT_WITH_ITS_AGENT)
        if event.data["status"] == "finished" and not event.data["heard"]:
            self._raise(event.stream, "mention", event)

    @fold("message.sent")
    def mention(self, event: Event) -> None:
        if event.data["mention"] is not None:
            self._raise(f"{event.stream}@{event.version}", "mention", event)
        if event.data["reply_to"] is not None:
            self._lower(event, "id = ?", event.data["reply_to"])

    @fold("effect.uncertain")
    def uncertain(self, event: Event) -> None:
        self._raise(f"effect/{event.data['id']}", "uncertain", event, _settle_actions(event))

    @fold("effect.finished", "effect.retried")
    def certain(self, event: Event) -> None:
        self._lower(event, "id = ?", f"effect/{event.data['id']}")

    @fold("effect.failed")
    def failed(self, event: Event) -> None:
        """A failure is news, unless a person said so, who has nothing left to do here."""
        if event.actor == "runtime":
            self._raise(f"effect/{event.data['id']}", "failed", event)
        else:
            self._lower(event, "id = ?", f"effect/{event.data['id']}")

    @fold("task.died")
    def dead_task(self, event: Event) -> None:
        self._raise(event.stream, "dead_task", event)

    @fold("wake.refused")
    def wake_refused(self, event: Event) -> None:
        self._raise(f"wake/{event.agent}", "hops" if event.data["why"] == "hops" else "budget", event)

    @fold("budget.lapsed")
    def budget_lapsed(self, event: Event) -> None:
        self._raise(event.stream, "budget", event)

    @fold("budget.set")
    def budget_set(self, event: Event) -> None:
        self._lower(event, "kind = 'budget'")

    @fold("turn.lost")
    def turn_lost(self, event: Event) -> None:
        """Nobody knows what a lost turn did, until its agent's next turn has looked."""
        self._raise(f"turn/{event.agent}", "uncertain", event)

    @fold("turn.ended", "turn.lost")
    def approval_moot(self, event: Event) -> None:
        self._lower(event, "agent = ? AND kind = 'approval'", event.agent)

    @fold("turn.started")
    def turn_started(self, event: Event) -> None:
        turn = f"turn/{event.agent}"
        self._lower(event, "id IN (?, ?) OR (agent = ? AND kind = 'failed')", f"wake/{event.agent}", turn, event.agent)

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


class Gaps(View):
    """Every incident gap, counted by agent and kind, which is what an ending has to state."""

    schema = """
    CREATE TABLE v_gaps(
        agent TEXT NOT NULL,
        what TEXT NOT NULL,
        plane TEXT NOT NULL,
        count INTEGER NOT NULL,
        PRIMARY KEY (agent, what)
    ) WITHOUT ROWID, STRICT;
    """

    def _count(self, agent: str | None, what: str, plane: str) -> None:
        self.db.execute(
            "INSERT INTO v_gaps VALUES (?, ?, ?, 1) ON CONFLICT DO UPDATE SET count = count + 1", (agent, what, plane)
        )

    @fold("gap.recorded")
    def recorded(self, event: Event) -> None:
        self._count(event.agent, event.data["what"], event.data["plane"])

    @fold("turn.lost")
    def turn_lost(self, event: Event) -> None:
        self._count(event.agent, event.data["gap"], "control")

    def rows(self) -> list[dict[str, Any]]:
        return [dict(row) for row in self.db.execute("SELECT * FROM v_gaps ORDER BY agent, what")]


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


def _roster(txn: Txn) -> list[dict[str, Any]]:
    uncertain = txn.view(Effects).in_state("uncertain")
    dues = {reader: due for reader, due, _ in txn.view(Deliveries).waking() if due > txn.now}
    deliveries = txn.view(Deliveries)
    budget = txn.view(Budgets)
    return [
        {
            "agent": agent.name,
            "role": agent.role,
            "harness": agent.harness,
            "model": agent.model,
            "parent": agent.parent and name_of(agent.parent),
            "state": agent.state,
            "activity": agent.activity,
            "stopped": agent.stopped,
            "held_by": agent.held_by and name_of(agent.held_by),
            "why": _why(txn, agent, uncertain, dues),
            "unread": deliveries.unread(agent.name),
            "levels": agent.levels,
            "usage": budget.usage_of(f"agent:{agent.name}"),
        }
        for agent in txn.view(Agents).listed()
    ]


@op("attention.list", query=True)
def attention_list(txn: Txn, a: Args) -> list[dict[str, Any]]:
    """List what needs a human now, each with the actions that would settle it."""
    return txn.view(Attention).rows()


class Watch(Args):
    name: Annotated[Literal["roster", "attention", "changes"], Field(description="The view.")]
    after: Annotated[
        int | None, Field(ge=0, description="The `cursor` of an earlier answer, for what changed since it.")
    ] = None


def _snapshot(txn: Txn, name: str) -> list[dict[str, Any]]:
    if name == "roster":
        return _roster(txn)
    return txn.view(Attention).rows() if name == "attention" else txn.view(Changes).since(0)


def _changed(txn: Txn, name: str, after: int) -> tuple[list[dict[str, Any]], list[str]]:
    """Rows changed past `after`, and the keys that went away. Almost any event can move a roster row, under a name
    that is not that agent's, so a roster changes as a whole whenever the journal moves."""
    if name == "roster":
        return (_roster(txn) if txn.view(Stamps).head() > after else []), []
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
