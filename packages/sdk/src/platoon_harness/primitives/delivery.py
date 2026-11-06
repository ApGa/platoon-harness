"""Delivery: handing queued entries to a harness, and the courier that decides when."""

from typing import Any, Literal, NamedTuple

from platoon_harness.kernel import Args, Daemon, Effects, Kernel, Refused, Txn, first, op

from .agents import Agent, Agents
from .budgets import reserve
from .common import Exposed, Name, expose, fitted, name_of
from .messages import Deliveries, Entry, chain_of
from .sessions import SessionRecord
from .waits import WaitRecord, Waits, out_of_turn

_RETRY_SECONDS = 1.0
_ATTACHED = ("next-turn", "wake", "steer")
_HANDOVERS = 6
_REST_SECONDS = 600.0
"""How long an agent stays between turns before its harness's process is ended, with no setting."""


def _steerable(agent: Agent) -> str | None:
    """The earliest boundary a working agent offers. `turn` is no boundary at all while a turn runs."""
    return next((boundary for boundary in ("tool", "model_call") if boundary in agent.boundaries), None)


class Work(NamedTuple):
    """What the runtime could do now: agents to hand entries to, waits to close, and agents to end, with why. Then the
    agents with a wake to come, and when more falls due."""

    agents: list[str]
    waits: list[WaitRecord]
    stranded: list[tuple[str, str]]
    later: list[str]
    due: float | None


def _stranded(txn: Txn) -> list[tuple[str, str]]:
    """Agents nothing more can come of: a spawn with a step that failed, so what depended on it will never start, an
    agent out of a turn whose harness has refused handover after handover, and one with a goal to be told again in a
    session that hands nothing over now."""
    agents = txn.view(Agents)
    found = [
        (
            agent.name,
            f"its spawn failed: {agent.failure}"
            if agent.state == "spawning"
            else f"{agent.failures} handovers failed: {agent.failure}",
        )
        for agent in agents.failing(_HANDOVERS)
    ]
    if not txn.view(SessionRecord).accepting():
        queued = txn.view(Deliveries).queued
        told = (agent for agent in agents.live() if agent.unbegun and queued(agent.name, ("wake",))[0])
        found += [(agent.name, "its session closed before it began its goal") for agent in told]
    return found


def _under_way(txn: Txn, kind: str) -> set[str]:
    """Agents an effect of `kind` is under way for."""
    effects = txn.view(Effects)
    return {
        effect.agent
        for state in ("requested", "started")
        for effect in effects.in_state(state)
        if effect.kind == kind and effect.agent is not None
    }


def _awaiting_stops(txn: Txn) -> set[str]:
    """Agents a stop of a child of theirs is under way for. A stop tells the authority how its agent ended last."""
    stopping = (txn.view(Agents).get(name) for name in _under_way(txn, "stop"))
    return {name_of(agent.parent) for agent in stopping if agent is not None and agent.parent is not None}


def work(txn: Txn) -> Work:
    """The courier's input, and what `settled` asks about. A wait stays open while its agent's turn runs, and nothing is
    handed to an agent while an interrupt of it is under way, as it could land in the turn that interrupt cuts, nor
    while a stop of a child of its is, so that a parent hears of a child's end only once the authority has, and is on
    its way to a turn until then."""
    stranded = _stranded(txn)
    if not txn.view(SessionRecord).accepting():
        return Work([], [], stranded, [], None)
    agents = txn.view(Agents)
    interrupting, awaiting = _under_way(txn, "interrupt"), _awaiting_stops(txn)
    ready: list[str] = []
    later: list[str] = []
    dues: list[float] = []
    for reader, due, steer in txn.view(Deliveries).waking():
        agent = agents.get(reader)
        if agent is None or agent.failures >= _HANDOVERS or reader in interrupting:
            continue
        if not (agent.state in ("idle", "waiting") or (agent.state == "running" and steer and _steerable(agent))):
            continue
        due = max(due, agent.retry_at)
        if reader in awaiting:
            later.append(reader)
        elif due <= txn.now:
            ready.append(reader)
        else:
            later.append(reader)
            dues.append(due)
    closing, deadline = txn.view(Waits).closing(txn.now)
    waits = [wait for wait in closing if out_of_turn(txn, wait.waiter)]
    if deadline is not None:
        dues.append(deadline)
    return Work(ready, waits, stranded, later, min(dues, default=None))


def resting(txn: Txn) -> tuple[list[str], float | None]:
    """Agents whose harness has been between turns for ten minutes, while the session accepts work, and when the next
    will have been."""
    if not txn.view(SessionRecord).accepting():
        return [], None
    due, later = [], []
    for agent in txn.view(Agents).between_turns():
        assert agent.idle_since is not None
        rests_at = agent.idle_since + _REST_SECONDS
        (due if rests_at <= txn.now else later).append((agent.name, rests_at))
    return [name for name, _ in due], min((when for _, when in later), default=None)


class Offer(Args):
    agent: Name
    boundary: Literal["tool"] | None = None


def _hand_over(txn: Txn, agent: str, modes: tuple[str, ...], boundary: str, how: str) -> dict[str, Any] | None:
    deliveries = txn.view(Deliveries)
    queued, total = deliveries.queued(agent, modes)
    shown: list[Entry] = fitted(queued, show=Entry.shown)
    if not shown:
        return None
    input = expose(
        txn,
        agent,
        [Exposed.gist(entry.ref, entry.gist) for entry in shown],
        how=how,
        boundary=boundary,
        positions=deliveries.stops(agent, shown),
        **chain_of(txn, agent, shown),
    )
    return {
        "input": input,
        "boundary": boundary,
        "items": [{key: entry.shown()[key] for key in ("ref", "gist", "sender", "body")} for entry in shown],
        "behind": total - len(shown),
    }


def _wake(txn: Txn, agent: Agent) -> dict[str, Any] | None:
    """Start a turn with what is queued. A refused reservation is an event, so the courier does not retry forever."""
    if not txn.view(Deliveries).queued(agent.name, _ATTACHED)[0]:
        return None
    try:
        reserve(txn, agent.name, agent.role)
    except Refused as refused:
        code = refused.refusal.code
        data = {"why": code, "detail": refused.refusal.detail}
        txn.emit(
            "wake.refused",
            f"wake/{agent.name}",
            gist=f"wake of {agent.name} refused: {code}",
            agent=agent.name,
            data=data,
        )
        return None
    txn.emit("agent.woken", f"agent/{agent.name}", gist=f"{agent.name} woken", agent=agent.name)
    return _hand_over(txn, agent.name, _ATTACHED, "turn", "wake")


@op("delivery.offer", on=lambda a: f"agent/{a.agent}", runtime=True)
def offer(txn: Txn, a: Offer) -> dict[str, Any] | None:
    """Hand an agent what is queued: a new turn if it is out of one, its earliest boundary if it is working, and nothing
    while a stop of a child of its is under way.

    `boundary="tool"` asks for pending steer notices to go on a coordination tool's result, so no effect is requested.
    """
    agent = txn.view(Agents).get(a.agent)
    if agent is None:
        raise Refused("not_found", f"no agent {a.agent}")
    if a.agent in _awaiting_stops(txn):
        return None
    if a.boundary == "tool":
        return _hand_over(txn, a.agent, ("steer",), "tool", "notice")
    if agent.state in ("idle", "waiting"):
        handed = _wake(txn, agent)
    elif agent.state == "running" and (boundary := _steerable(agent)) is not None:
        handed = _hand_over(txn, a.agent, ("steer",), boundary, "steer")
    else:
        handed = None
    if handed is not None:
        txn.effect("deliver", handed, on_uncertain="reconcile", agent=a.agent)
    return handed


class Pending(Args):
    agent: Name


@op("delivery.pending", query=True, runtime=True)
def pending(txn: Txn, a: Pending) -> int:
    """Count the steer notices a tool result could carry, so a call with none to carry journals nothing."""
    return txn.view(Deliveries).queued(a.agent, ("steer",))[1]


def confirmed(txn: Txn, input: int, boundary: str | None, evidence: str | None, native_id: str | None = None) -> None:
    """Record that a harness said it took an offer, which is observed exposure, from its own report and nothing else:
    an input it said it delivered, or the tool item that came back `completed` with a read's result. It carries how the
    offer was made, and its hops and ask, which count in the turn it landed in. A repeat changes nothing."""
    found = txn.view(Deliveries).offer(input)
    if found is None:
        raise Refused("not_found", f"no offer {input}")
    if not found.delivered:
        data = {
            "input": input,
            "how": found.how,
            "positions": found.positions,
            "hops": found.hops,
            "asked": found.asked,
            "boundary": boundary,
            "evidence": evidence,
            "native_id": native_id,
        }
        txn.emit(
            "context.delivered",
            f"context/{found.reader}",
            gist=f"offer {input} delivered",
            agent=found.reader,
            data=data,
            cause=[input],
            v=3,
        )


@op("delivery.ready", query=True, runtime=True)
def delivery_ready(txn: Txn, a: Args) -> dict[str, Any]:
    """List what the courier could do now, the agents to put to rest among it, and when more falls due."""
    found = work(txn)
    waits = [wait.id for wait in found.waits]
    rest, rests_at = resting(txn)
    due = min((when for when in (found.due, rests_at) if when is not None), default=None)
    return {"agents": found.agents, "waits": waits, "stranded": found.stranded, "resting": rest, "due": due}


async def _pass(kernel: Kernel) -> float | None:
    """One level-triggered pass, returning when to look again if nothing commits first."""
    runtime = kernel.runtime
    found = kernel.query(runtime, "delivery.ready", {}).result
    commands = [("wait.release", {"id": id}) for id in found["waits"]]
    commands += [("delivery.offer", {"agent": agent}) for agent in found["agents"]]
    commands += [
        ("agent.report", {"agent": agent, "report": {"type": "exited", "reason": why}})
        for agent, why in found["stranded"]
    ]
    commands += [("agent.rest", {"agent": agent}) for agent in found["resting"]]
    for name, args in commands:
        outcome = await kernel.submit(runtime, name, args)
        if outcome.refusal is not None:
            return kernel.clock.now() + (outcome.refusal.retry_after or _RETRY_SECONDS)
    return found["due"]


async def _run(kernel: Kernel) -> None:
    while not kernel.closed:
        head = kernel.head
        due = await _pass(kernel)
        await first(kernel.changed(head), *(() if due is None else (kernel.clock.sleep(due - kernel.clock.now()),)))


courier = Daemon("courier", _run)
