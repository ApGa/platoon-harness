"""Credit: producers that estimate what each agent's work in an episode was worth, written beside the journal.

Every producer is `async def produce(session, episode, *, judge, **params) -> None`, named by `module:attr`, run on an
ended session, and writes only through `Session.annotate`: an estimate by a named producer at a version, never a fact.
`judge` is model access for a producer that asks a model, or None. See architecture section 14.
"""

import heapq
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass

from platoon_harness.drivers import Gateway
from platoon_harness.kernel import Refused
from platoon_harness.primitives import WALK_LIMIT, Lineage, Span
from platoon_harness.session import Session

__all__ = ["PROPAGATE", "propagate"]

PROPAGATE = "platoon_harness.credit:propagate"
"""The producer `propagate` writes as, the name an entry runs it by."""


async def propagate(session: Session, episode: str, *, judge: Gateway | None, retained: float) -> None:
    """`propagate@2`, a heuristic: split an episode's one team reward back along the record's own edges, and write
    each agent it reaches a local credit row on its first `agent.started`, and each span it reaches one on its name.

    The reward on the episode's `episode.closed` splits equally over the refs the episode closed on. Each event it
    reaches keeps `retained` of what reached it for its maker, an agent's or nobody's, and the rest splits equally over
    its causes, its previous version or a commit's parents, and its citations, an agent's only where its exposure says
    Seen; an event with none of these keeps it all. What an agent's event keeps is that agent's, and also its span's
    when the event lies in one: the span holding the model call that made it, for an entry that carries an event that
    event's, and for an event tied to no call its turn's when that turn is one span. So an agent's row is its spans'
    rows and what it kept in no span. The walk takes events newest first, so a path that reconverges adds once, and it
    stops at 4,096 events, when every row is `invalid`. A team reward that is not scored passes its status to each row,
    and an agent or a span it never reaches gets no row, so is unscored. What nobody's events kept is the reward less
    the agents' rows, and is no row. Citing gives away all but `retained` of what reaches the citer, and work nobody
    cites earns nothing from it. `judge` is not read. Refused `invalid` for a `retained` outside [0, 1] or a reward on
    an episode that closed on no ref, and `conflict` for several team rewards."""
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
    status = "invalid" if short else reward.status
    for target, share in kept.items():
        await session.annotate(
            target,
            kind="credit",
            producer=PROPAGATE,
            producer_version="2",
            scope="local",
            status=status,
            value=share if status == "scored" else None,
            params={"retained": retained},
            evidence=evidence[target],
            head_seq=head,
        )


@dataclass(frozen=True)
class _Agent:
    """An agent as the walk books to it: its name, its first `agent.started`, which its row targets, its spans, and
    the span holding each model call its harness reported in a turn, by the call's ref."""

    name: str
    started: str
    spans: tuple[Span, ...]
    holding: Mapping[str, Span]


async def _closed(session: Session, episode: str) -> str:
    """The ref of the latest `episode.closed` of an episode."""
    closed = [event async for event in session.events(streams=[f"episode/{episode}"]) if event.type == "episode.closed"]
    if not closed:
        raise Refused("not_found", f"episode {episode} never closed")
    return f"{closed[-1].stream}@{closed[-1].version}"


async def _agent(session: Session, name: str) -> _Agent:
    """An agent's first start, its spans, every page of them, and the span holding each call, by where each call stands
    on its turn stream between its span's first call and its last."""
    started = None
    async for event in session.events(streams=[f"agent/{name}"]):
        if event.type == "agent.started":
            started = f"{event.stream}@{event.version}"
            break
    if started is None:
        raise Refused("not_found", f"@{name} never started")
    page = await session.spans(f"@{name}")
    spans = list(page.spans)
    while page.cursor is not None:
        page = await session.spans(f"@{name}", after=page.cursor)
        spans += page.spans
    holding: dict[str, Span] = {}
    coming, span = iter(spans), None
    upcoming = next(coming, None)
    async for event in session.events(streams=[f"turn/{name}"]):
        if event.type != "model.called":
            continue
        ref = f"{event.stream}@{event.version}"
        if span is None and upcoming is not None and ref == upcoming.first:
            span, upcoming = upcoming, next(coming, None)
        if span is not None:
            holding[ref] = span
            if ref == span.ref:
                span = None
    return _Agent(name, started, tuple(spans), holding)


async def _carried(session: Session, found: Lineage) -> str | None:
    """The ref of the event an entry carries, as an announce of a write or a child's report does, or None."""
    if found.event.type != "message.sent":
        return None
    [event] = (await session.page(after=found.event.seq - 1, limit=1)).events
    return event.data.get("carries")


async def _walk(
    session: Session, closed: str, reward: float, retained: float
) -> tuple[Mapping[str, float], Mapping[str, list[str]], bool, int]:
    """What each agent's events kept of `reward`, and each span's, by the event its row targets, the refs of those
    events, whether the walk stopped short, and the head it read at."""
    traced: dict[str, Lineage] = {}
    agents: dict[str, _Agent] = {}

    async def trace(ref: str) -> Lineage:
        if ref not in traced:
            traced[ref] = await session.lineage(ref)
        return traced[ref]

    async def part(agent: _Agent, found: Lineage) -> Span | None:
        """The span of an agent's event: its call's, what it carries', or its turn's when that turn is one span."""
        if found.made.call is not None:
            return agent.holding.get(found.made.call)
        if (carried := await _carried(session, found)) is not None:
            carrying = await trace(carried)
            return await part(agent, carrying) if carrying.made.maker == f"agent:{agent.name}" else None
        whole = [span for span in agent.spans if found.made.turn is not None and span.turn == found.made.turn]
        return whole[0] if len(whole) == 1 else None

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
            name = maker.removeprefix("agent:")
            if name not in agents:
                agents[name] = await _agent(session, name)
            span = await part(agents[name], found)
            for target in (agents[name].started, *(() if span is None else (span.ref,))):
                kept[target] = kept.get(target, 0.0) + keeping
                evidence[target].append(ref)
        for edge in edges:
            await hand(edge, (share - keeping) / len(edges))
    return kept, evidence, False, outcome.head
