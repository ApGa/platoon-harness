"""Credit: producers that estimate what each agent's work in an episode was worth, written beside the journal.

Every producer is `async def produce(session, episode, *, judge, **params) -> None`, named by `module:attr`, run on an
ended session, and writes only through `Session.annotate`: an estimate by a named producer at a version, never a fact.
`judge` is model access for a producer that asks a model, or None. See architecture section 14.
"""

import heapq
from collections import defaultdict
from collections.abc import Mapping

from platoon_harness.drivers import Gateway
from platoon_harness.kernel import Refused
from platoon_harness.primitives import WALK_LIMIT, Lineage
from platoon_harness.session import Session

__all__ = ["PROPAGATE", "propagate"]

PROPAGATE = "platoon_harness.credit:propagate"
"""The producer `propagate` writes as, the name an entry runs it by."""


async def propagate(session: Session, episode: str, *, judge: Gateway | None, retained: float) -> None:
    """`propagate@1`, a heuristic: split an episode's one team reward back along the record's own edges, and write
    each agent it reaches a local credit row on its first `agent.started`.

    The reward on the episode's `episode.closed` splits equally over the refs the episode closed on. Each event it
    reaches keeps `retained` of what reached it for its maker, an agent's or nobody's, and the rest splits equally over
    its causes, its previous version or a commit's parents, and its citations, an agent's only where its exposure says
    Seen; an event with none of these keeps it all. The walk takes events newest first, so a path that reconverges adds
    once, and it stops at 4,096 events, when every row is `invalid`. A team reward that is not scored passes its status
    to each row, and an agent it never reaches gets no row, so is unscored. What nobody's events kept is the reward
    less the rows, and is no row. Citing gives away all but `retained` of what reaches the citer, and work nobody cites
    earns nothing from it. `judge` is not read. Refused `invalid` for a `retained` outside [0, 1] or a reward on an
    episode that closed on no ref, and `conflict` for several team rewards."""
    if not 0 <= retained <= 1:
        raise Refused("invalid", f"`retained` is a share, from 0 to 1, and {retained} is not")
    closed = await _closed(session, episode)
    rewards = [row for row in await session.annotations(closed) if (row.kind, row.scope) == ("reward", "team")]
    if len(rewards) > 1:
        raise Refused("conflict", f"{closed} has {len(rewards)} team rewards, and propagate splits one")
    if not rewards:
        return
    reward = rewards[0]
    kept, evidence, short, head = await _walk(session, closed, reward.value or 0.0, retained)
    for agent, share in kept.items():
        status = "invalid" if short else reward.status
        await session.annotate(
            await _started(session, agent),
            kind="credit",
            producer=PROPAGATE,
            producer_version="1",
            scope="local",
            status=status,
            value=share if status == "scored" else None,
            params={"retained": retained},
            evidence=evidence[agent],
            head_seq=head,
        )


async def _closed(session: Session, episode: str) -> str:
    """The ref of the latest `episode.closed` of an episode."""
    closed = [event async for event in session.events(streams=[f"episode/{episode}"]) if event.type == "episode.closed"]
    if not closed:
        raise Refused("not_found", f"episode {episode} never closed")
    return f"{closed[-1].stream}@{closed[-1].version}"


async def _started(session: Session, agent: str) -> str:
    """The ref of an agent's first `agent.started`, the event of its own its credit is about."""
    async for event in session.events(streams=[f"agent/{agent}"]):
        if event.type == "agent.started":
            return f"{event.stream}@{event.version}"
    raise Refused("not_found", f"@{agent} never started")


async def _walk(
    session: Session, closed: str, reward: float, retained: float
) -> tuple[Mapping[str, float], Mapping[str, list[str]], bool, int]:
    """What each agent's events kept of `reward`, the refs of those events, whether the walk stopped short, and the
    head it read at."""
    traced: dict[str, Lineage] = {}

    async def trace(ref: str) -> Lineage:
        if ref not in traced:
            traced[ref] = await session.lineage(ref)
        return traced[ref]

    outcome = await trace(closed)
    reaching: dict[str, float] = defaultdict(float)
    queue: list[tuple[int, str]] = []

    async def hand(ref: str, share: float) -> None:
        if ref not in reaching:
            heapq.heappush(queue, (-(await trace(ref)).event.seq, ref))
        reaching[ref] += share

    cited = [declared.ref.partition("#")[0] for declared in outcome.declared]
    if not cited:
        raise Refused("invalid", f"{closed} closed on no ref, so its reward has nothing to split over")
    for ref in cited:
        await hand(ref, reward / len(cited))
    kept: dict[str, float] = {}
    evidence: dict[str, list[str]] = defaultdict(list)
    walked = 0
    while queue:
        if walked == WALK_LIMIT:
            return kept, evidence, True, outcome.head
        walked += 1
        ref = heapq.heappop(queue)[1]
        share, found = reaching[ref], await trace(ref)
        edges = [step.ref for step in (*found.cause, *found.ancestry) if step.ref is not None]
        edges += [d.ref.partition("#")[0] for d in found.declared if d.exposure is None or d.exposure.answer == "seen"]
        keeping = share * retained if edges else share
        if (maker := found.made.maker or "").startswith("agent:"):
            agent = maker.removeprefix("agent:")
            kept[agent] = kept.get(agent, 0.0) + keeping
            evidence[agent].append(ref)
        for edge in edges:
            await hand(edge, (share - keeping) / len(edges))
    return kept, evidence, False, outcome.head
