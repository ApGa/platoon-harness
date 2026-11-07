"""Approvals: durable decisions a harness waits on, resolved once by a human or a stated policy."""

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field

from platoon_harness.kernel import GIST_LIMIT, Args, Event, Refused, Stamps, Txn, View, fold, op

from .agents import Agent, Agents
from .common import BodyRef, Gist, Name, inline_body
from .sessions import SessionRecord

Verdict = Literal["allow", "deny"]
ASK_LIMIT = 64 * 1024
"""How many bytes of an approval's ask its record keeps: as much as the journal holds in an event's own body, as for a
patch. A reader takes it whole by its ref, as `blob.get` pages whole lines and gives no text for one past a result."""


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

    @fold("agent.ended", "turn.ended", "turn.lost")
    def moot(self, event: Event) -> None:
        """Nothing waits on an approval once the turn that asked has gone: a resumed harness has forgotten it."""
        self.db.execute("UPDATE v_approvals SET state = 'moot' WHERE agent = ? AND state = 'pending'", (event.agent,))

    def get(self, id: str) -> Approval | None:
        row = self.db.execute("SELECT * FROM v_approvals WHERE id = ?", (id,)).fetchone()
        return None if row is None else Approval(**dict(row))

    def asking(self) -> int:
        """How many wait on a human. A stated policy decides in the same command, so anything pending is left to ask."""
        return self.db.execute("SELECT count(*) AS n FROM v_approvals WHERE state = 'pending'").fetchone()["n"]

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


def bounded(ask: str) -> tuple[bytes, int]:
    """An ask as its record keeps it, in UTF-8, where a lone surrogate, which a harness's JSON can carry and UTF-8
    cannot, is written as its escape, `\\udcc3`, and not lost: whole, or its first `ASK_LIMIT` bytes cut at the end of
    the last whole character, and how many bytes of it that leaves out. Mask it first, as a cut can split a secret."""
    whole = ask.encode(errors="backslashreplace")
    if len(whole) <= ASK_LIMIT:
        return whole, 0
    kept = whole[:ASK_LIMIT].decode(errors="ignore").encode()
    return kept, len(whole) - len(kept)


def ask(txn: Txn, id: str, agent: Agent, gist: str, body: str | None = None, cut: int = 0) -> None:
    """Record that a harness is waiting on a decision, with `body`, the whole of what it asks, as a body the journal
    holds, and `cut`, the bytes of it that body leaves out, unknown where the ask is. Then apply the role's policy,
    which `ask` leaves to a person."""
    if txn.view(Approvals).get(id) is not None:
        raise Refused("conflict", f"approval {id} exists")
    if body is None and cut:
        raise Refused("invalid", "`cut` counts what a body leaves out, and there is no body")
    if body is not None and inline_body(txn, body) is None:
        raise Refused(
            "invalid", f"an ask is a body the journal holds, of at most {ASK_LIMIT // 1024} KiB and not redacted"
        )
    role = txn.view(SessionRecord).settings().roles.get(agent.role)
    policy = "ask" if role is None else role.approvals
    data = {"id": id, "policy": policy, "body": body, "cut": None if body is None else cut}
    refs = [body] if body is not None else ()
    txn.emit("approval.requested", f"approval/{id}", gist=gist, agent=agent.name, refs=refs, data=data, v=2)
    if policy != "ask":
        _decide(txn, id, agent.name, policy, "policy", "policy")


class Request(Args):
    id: Name
    agent: Name
    gist: Gist
    body: BodyRef | None = None
    cut: Annotated[int, Field(ge=0)] = 0


@op("approval.request", on=lambda a: f"approval/{a.id}", runtime=True)
def request(txn: Txn, a: Request) -> None:
    """Record that a harness is waiting on a decision, with the whole of what it asks as `body`, of which `cut` bytes
    were left out."""
    agent = txn.view(Agents).get(a.agent)
    if agent is None or agent.ended:
        raise Refused("not_found", f"no live agent {a.agent}")
    ask(txn, a.id, agent, a.gist, a.body, a.cut)


class Resolve(Args):
    id: Annotated[Name, Field(description="The approval, as its row in `attention.list` names it.")]
    verdict: Annotated[Verdict, Field(description="`allow` or `deny`.")]
    expected_version: Annotated[
        int, Field(description="Its version as you saw it, so that a decision someone made since stands.")
    ]
    via: Annotated[str | None, Field(description="What it was decided through, which a loser is told.")] = None


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
