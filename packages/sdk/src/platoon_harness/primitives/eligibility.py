"""Eligibility: whether an agent's work in one episode can train, answered from the record alone, and never what a
training system decides. It reads the levels the agent's starts recorded and never a result kept since, so it answers
alike after a rebuild, on a closed copy and with the conformance store gone. See architecture section 11."""

from typing import Annotated, Any, Literal

from pydantic import Field

from platoon_harness.kernel import Args, Event, Principals, Refused, Stamps, Txn, op
from platoon_harness.schema import Model

from .agents import Agent, Agents
from .common import DIGEST_ITEMS, AgentName, Name, maker
from .exposures import Exposures
from .provenance import Calls

_PAGE = DIGEST_ITEMS

Attribution = Literal["exact", "forked"]
"""How well an agent's model calls are tied to it: `exact` where every start of it recorded its trainable level met and
no other agent's admission names its backend ids, and `forked` once a native child of its harness is seen, whose calls
go on its key. Neither is None."""

Verdict = Literal["eligible", "ineligible"]


def _ref(event: Event) -> str:
    return f"{event.stream}@{event.version}"


class Bar(Model):
    """One reason an agent, or one of its calls, cannot train, of a closed set, with the refs of the events that show
    it. An agent's: `not_trainable`, a start that recorded its trainable `level` short of met, or with no ref, that no
    start recorded one; `shared_key`, the spawns of other agents whose admissions name its backend ids; `forked`, the
    native children seen; and `no_end`, as it has not ended. A call's: `outside_episode`; `person`, the start of its
    turn, which a person held, or a person's entry its agent was handed below it, which exposure then never answers
    `not_seen`; and `purpose`, a purpose neither its turn's nor `compaction`."""

    reason: Literal["not_trainable", "shared_key", "forked", "no_end", "outside_episode", "person", "purpose"]
    refs: tuple[str, ...] = ()
    level: dict[str, Any] | None = None


class CallEligibility(Model):
    """One model call its agent's harness reported, by the ref of its `model.called`, with the id and the purpose it
    gave. Its attribution is its agent's, and it is eligible when its agent is and it has no bar of its own."""

    call: str
    call_id: str | None
    purpose: str | None
    attribution: Attribution | None
    verdict: Verdict
    reasons: tuple[Bar, ...]


class Eligibility(Model):
    """Whether an agent's work in one episode can train: its attribution, and its verdict with every bar, eligible when
    there is none, and a page of its calls, oldest first, `total` of them, with `cursor` to pass as `after` for the next
    page. `head` is where the record was read."""

    agent: str
    episode: str
    attribution: Attribution | None
    verdict: Verdict
    reasons: tuple[Bar, ...]
    calls: tuple[CallEligibility, ...]
    total: int
    cursor: str | None
    head: int


class AskedOf(Args):
    agent: Annotated[AgentName, Field(description="The agent, as `@agent`.")]
    episode: Annotated[Name, Field(description="The episode, by name.")]
    after: Annotated[str | None, Field(max_length=64, description="A `cursor` from an earlier answer.")] = None


def _agent_bars(txn: Txn, agent: Agent) -> list[Bar]:
    """What keeps an agent from training, read from its own stream and the other agents' admissions."""
    stream = list(txn.view(Stamps).events(f"agent/{agent.name}"))
    starts = [event for event in stream if event.type in ("agent.started", "agent.resumed")]
    bars = [] if starts else [Bar(reason="not_trainable")]
    for start in starts:
        level = (start.data.get("levels") or {}).get("trainable")
        if level is None or level["state"] != "met":
            bars.append(Bar(reason="not_trainable", refs=(_ref(start),), level=level))
    ids = set(agent.backend.items())
    sharing = [other for other in txn.view(Agents).listed() if other.name != agent.name and ids & other.backend.items()]
    if sharing:
        bars.append(Bar(reason="shared_key", refs=tuple(f"agent/{other.name}@1" for other in sharing)))
    if children := tuple(_ref(event) for event in stream if event.type == "child.seen"):
        bars.append(Bar(reason="forked", refs=children))
    if not agent.ended:
        bars.append(Bar(reason="no_end"))
    return bars


def _attribution(bars: list[Bar]) -> Attribution | None:
    reasons = {bar.reason for bar in bars}
    if "forked" in reasons:
        return "forked"
    return None if reasons & {"not_trainable", "shared_key"} else "exact"


def _handed_a_person(txn: Txn, agent: str) -> tuple[int, str] | None:
    """The first offer that handed the agent an entry a person made, and that entry's ref, or None."""
    stamps = txn.view(Stamps)
    for row in txn.view(Exposures).events_offered(agent, stamps.head() + 1):
        event = stamps.at(row["stream"], row["version"])
        if event is not None and (maker(event) or "").startswith("human:"):
            return row["offer"], _ref(event)
    return None


def _call_bars(txn: Txn, call: Event, episode: str, person: tuple[int, str] | None) -> list[Bar]:
    """What keeps one call from training: an episode other than the one asked of, a person, or a purpose of its own."""
    bars = [] if call.episode == episode else [Bar(reason="outside_episode")]
    began = txn.view(Calls).began(call.agent or "", call.seq)
    held = None if began is None or began["by"] is None else txn.view(Stamps).event(began["seq"])
    if held is not None:
        bars.append(Bar(reason="person", refs=(_ref(held),)))
    elif person is not None and person[0] < call.seq:
        bars.append(Bar(reason="person", refs=(person[1],)))
    if call.data["purpose"] not in (None, "compaction"):
        bars.append(Bar(reason="purpose"))
    return bars


@op("eligibility", query=True)
def eligibility(txn: Txn, a: AskedOf) -> Eligibility:
    """Say whether an agent's work in one episode can train, from the record alone: its attribution, `exact`, `forked`
    or none, and its verdict with each bar, of a closed set, and the same for a page of its model calls, oldest first,
    each eligible when its agent is and it has no bar of its own. It reads the levels its starts recorded, never a
    result kept since. Pass `cursor` as `after` for the next page. Refused `invalid` for a person or a program, which
    never trains, and `not_found` for no such agent or episode."""
    agent = txn.view(Agents).get(a.agent)
    if agent is None:
        found = txn.view(Principals).named(a.agent)
        if found is not None:
            raise Refused("invalid", f"{a.agent} is a {found.kind}, which never trains")
        raise Refused("not_found", f"no agent {a.agent}")
    stamps = txn.view(Stamps)
    if stamps.version_of(f"episode/{a.episode}") == 0:
        raise Refused("not_found", f"no episode {a.episode}")
    if a.after is not None and not a.after.isdecimal():
        raise Refused("invalid", "`after` is a `cursor` from an earlier answer")
    bars, person = _agent_bars(txn, agent), _handed_a_person(txn, agent.name)
    attribution, verdict = _attribution(bars), "ineligible" if bars else "eligible"
    called = [event for event in stamps.events(f"turn/{agent.name}") if event.type == "model.called"]
    page = [call for call in called if call.seq > int(a.after or 0)][:_PAGE]
    calls = []
    for call in page:
        own = tuple(_call_bars(txn, call, a.episode, person))
        judged = "eligible" if verdict == "eligible" and not own else "ineligible"
        data = {"call_id": call.data["call_id"], "purpose": call.data["purpose"]}
        calls.append(CallEligibility(call=_ref(call), **data, attribution=attribution, verdict=judged, reasons=own))
    return Eligibility(
        agent=agent.name,
        episode=a.episode,
        attribution=attribution,
        verdict=verdict,
        reasons=tuple(bars),
        calls=tuple(calls),
        total=len(called),
        cursor=str(page[-1].seq) if page and page[-1].seq != called[-1].seq else None,
        head=stamps.head(),
    )
