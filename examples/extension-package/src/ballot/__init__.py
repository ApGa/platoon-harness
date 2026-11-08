"""ballot: a vote on an agent's work, cast by a person or by a teammate the topology lets, and kept among that agent's
own events, so a client that shows the agent draws it by its gist. An op, the view that holds each vote, and a preset
that pairs an author with the reviewer who votes on its work."""

from typing import Annotated, Literal

from pydantic import Field

from platoon_harness.kernel import NAME, Args, Event, Extension, Grant, Principals, Refused, Txn, View, fold, op
from platoon_harness.topology import Topology


class Cast(Args):
    agent: Annotated[str, Field(pattern=f"^@{NAME}$", description="The agent whose work it is on, as `@agent`.")]
    choice: Annotated[Literal["yes", "no"], Field(description="Yes or no.")]


class Votes(View):
    """Each vote, by the agent whose work it is on and whoever cast it."""

    schema = """
    CREATE TABLE v_votes(
        agent TEXT NOT NULL,
        voter TEXT NOT NULL,
        choice TEXT NOT NULL,
        PRIMARY KEY (agent, voter)
    ) WITHOUT ROWID, STRICT;
    """

    @fold("ballot.voted")
    def voted(self, event: Event) -> None:
        self.db.execute(
            "INSERT INTO v_votes VALUES (?, ?, ?)", (event.data["agent"], event.actor, event.data["choice"])
        )

    def choice(self, agent: str, voter: str) -> str | None:
        """What `voter` voted on `agent`'s work, or None where it has not voted on it."""
        row = self.db.execute("SELECT choice FROM v_votes WHERE agent = ? AND voter = ?", (agent, voter)).fetchone()
        return None if row is None else row["choice"]


@op("ballot.cast", on=lambda a: f"agent/{a.agent[1:]}", tool=True)
def cast(txn: Txn, a: Cast) -> dict[str, str]:
    """Cast a vote on an agent's work, kept among that agent's own events. Refused `not_found` when there is no such
    agent, and `conflict` when you have voted on its work already."""
    if txn.view(Principals).get(f"agent:{a.agent[1:]}") is None:
        raise Refused("not_found", f"no agent {a.agent}")
    if (choice := txn.view(Votes).choice(a.agent, txn.me.id)) is not None:
        raise Refused("conflict", f"you voted {choice} on {a.agent}'s work already")
    txn.emit("ballot.voted", f"agent/{a.agent[1:]}", gist=f"a vote on {a.agent}'s work: {a.choice}", data=a)
    return {"choice": a.choice}


def pair_review(author: str, reviewer: str) -> Topology:
    """An author and a reviewer who talk directly, bounded by hops, and the reviewer's vote on the author's work."""
    vote = Grant(who=f"role:{reviewer}", ops="ballot.cast", on=f"agent/{{role:{author}}}")
    edges = {author: [f"role:{reviewer}"], reviewer: [f"role:{author}"]}
    return Topology(edges=edges, limits={"max_hops": 8}, grants=(vote,))


extension = Extension("ballot", ops=[cast], views=[Votes], presets=[pair_review])
