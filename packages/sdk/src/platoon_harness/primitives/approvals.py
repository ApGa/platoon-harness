"""Approvals: durable decisions a harness waits on, resolved once by a human or a stated policy."""

from typing import Any, Literal

from pydantic import BaseModel

from platoon_harness.kernel import GIST_LIMIT, Args, Event, Refused, Stamps, Txn, View, fold, op

from .agents import Agents
from .common import Gist, Name
from .sessions import Session

Verdict = Literal["allow", "deny"]


class Approval(BaseModel, frozen=True):
    """Four facts kept apart: asked, `state` decided, `answered` reached the harness, and the observed `outcome`."""

    id: str
    agent: str
    gist: str
    state: Literal["pending", "resolved", "moot"]
    verdict: str | None
    resolved_by: str | None
    via: str | None
    effect: int | None
    answered: bool
    outcome: str | None


class Approvals(View):
    """Every approval, whichever fact it has reached."""

    schema = """
    CREATE TABLE v_approvals(
        id TEXT PRIMARY KEY,
        agent TEXT NOT NULL,
        gist TEXT NOT NULL,
        state TEXT NOT NULL,
        verdict TEXT,
        resolved_by TEXT,
        via TEXT,
        effect INTEGER,
        answered INTEGER NOT NULL,
        outcome TEXT
    ) WITHOUT ROWID, STRICT;
    CREATE INDEX v_approvals_agent ON v_approvals(agent, state);
    CREATE INDEX v_approvals_effect ON v_approvals(effect);
    """

    @fold("approval.requested")
    def requested(self, event: Event) -> None:
        self.db.execute(
            "INSERT INTO v_approvals VALUES (?, ?, ?, 'pending', NULL, NULL, NULL, NULL, 0, NULL)",
            (event.data["id"], event.agent, event.gist),
        )

    @fold("approval.resolved")
    def resolved(self, event: Event) -> None:
        data = event.data
        self.db.execute(
            "UPDATE v_approvals SET state = 'resolved', verdict = ?, resolved_by = ?, via = ?, effect = ? WHERE id = ?",
            (data["verdict"], data["resolved_by"], data["via"], data["effect"], data["id"]),
        )

    @fold("effect.finished")
    def answered(self, event: Event) -> None:
        self.db.execute("UPDATE v_approvals SET answered = 1 WHERE effect = ?", (event.data["id"],))

    @fold("item.recorded")
    def observed(self, event: Event) -> None:
        if event.data["approval"] is not None:
            self.db.execute(
                "UPDATE v_approvals SET outcome = ? WHERE id = ?", (event.data["outcome"], event.data["approval"])
            )

    @fold("agent.ended")
    def moot(self, event: Event) -> None:
        self.db.execute("UPDATE v_approvals SET state = 'moot' WHERE agent = ? AND state = 'pending'", (event.agent,))

    def get(self, id: str) -> Approval | None:
        row = self.db.execute("SELECT * FROM v_approvals WHERE id = ?", (id,)).fetchone()
        return None if row is None else Approval(**dict(row))

    def pending_for(self, agent: str) -> list[Approval]:
        rows = self.db.execute("SELECT * FROM v_approvals WHERE agent = ? AND state = 'pending' ORDER BY id", (agent,))
        return [Approval(**dict(row)) for row in rows]


def _decide(txn: Txn, id: str, agent: str, verdict: str, by: str, via: str | None) -> None:
    effect = txn.effect(
        "answer", {"approval": id, "verdict": verdict}, on_uncertain="reconcile", priority=1, agent=agent
    )
    data = {"id": id, "verdict": verdict, "resolved_by": by, "via": via, "effect": effect}
    txn.emit(
        "approval.resolved", f"approval/{id}", gist=f"approval {id}: {verdict}"[:GIST_LIMIT], agent=agent, data=data
    )


class Request(Args):
    id: Name
    agent: Name
    gist: Gist


@op("approval.request", on=lambda a: f"approval/{a.id}", runtime=True)
def request(txn: Txn, a: Request) -> None:
    """Record that a harness is waiting on a decision, then apply the role's policy. `ask` leaves it for a human."""
    agent = txn.view(Agents).get(a.agent)
    if agent is None or agent.ended:
        raise Refused("not_found", f"no live agent {a.agent}")
    if txn.view(Approvals).get(a.id) is not None:
        raise Refused("conflict", f"approval {a.id} exists")
    role = txn.view(Session).settings().roles.get(agent.role)
    policy = "ask" if role is None else role.approvals
    txn.emit("approval.requested", f"approval/{a.id}", gist=a.gist, agent=a.agent, data={"id": a.id, "policy": policy})
    if policy != "ask":
        _decide(txn, a.id, a.agent, policy, "policy", "policy")


class Resolve(Args):
    id: Name
    verdict: Verdict
    expected_version: int
    via: str | None = None


@op("approval.resolve", on=lambda a: f"approval/{a.id}")
def resolve(txn: Txn, a: Resolve) -> dict[str, Any]:
    """Decide an approval. The first commit wins, and the loser is refused `conflict`, told who won and how."""
    if txn.me.kind == "agent":
        raise Refused("not_permitted", "an agent cannot carry an approval")
    approval = txn.view(Approvals).get(a.id)
    if approval is None:
        raise Refused("not_found", f"no approval {a.id}")
    if approval.state != "pending":
        raise Refused("conflict", {"state": approval.state, "resolved_by": approval.resolved_by, "via": approval.via})
    current = txn.view(Stamps).version_of(f"approval/{a.id}")
    if current != a.expected_version:
        raise Refused("conflict", {"expected": a.expected_version, "current": current})
    _decide(txn, a.id, approval.agent, a.verdict, txn.me.id, a.via)
    return {"id": a.id, "verdict": a.verdict}
