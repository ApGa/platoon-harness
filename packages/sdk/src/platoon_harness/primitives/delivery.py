"""Delivery: handing queued entries to a harness, and the courier that decides when."""

from typing import Any, Literal, NamedTuple

from platoon_harness.kernel import Args, Daemon, Kernel, Refused, Txn, first, op

from .agents import Agent, Agents
from .budgets import reserve
from .common import Exposed, Name, Seq, expose, fitted
from .messages import Deliveries, Entry, chain_of
from .sessions import SessionRecord
from .waits import WaitRecord, Waits, out_of_turn

_RETRY_SECONDS = 1.0
_ATTACHED = ("next-turn", "wake", "steer")
_HANDOVERS = 6


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
    """Agents nothing more can come of: a spawn with a step that failed, so what depended on it will never start, and an
    agent out of a turn whose harness has refused handover after handover."""
    return [
        (
            agent.name,
            f"its spawn failed: {agent.failure}"
            if agent.state == "spawning"
            else f"{agent.failures} handovers failed: {agent.failure}",
        )
        for agent in txn.view(Agents).failing(_HANDOVERS)
    ]


def work(txn: Txn) -> Work:
    """The courier's input, and what `settled` asks about. A wait stays open while its agent's turn runs."""
    stranded = _stranded(txn)
    if not txn.view(SessionRecord).accepting():
        return Work([], [], stranded, [], None)
    agents = txn.view(Agents)
    ready: list[str] = []
    later: list[str] = []
    dues: list[float] = []
    for reader, due, steer in txn.view(Deliveries).waking():
        agent = agents.get(reader)
        if agent is None or agent.failures >= _HANDOVERS:
            continue
        if not (agent.state in ("idle", "waiting") or (agent.state == "running" and steer and _steerable(agent))):
            continue
        due = max(due, agent.retry_at)
        if due <= txn.now:
            ready.append(reader)
        else:
            later.append(reader)
            dues.append(due)
    closing, deadline = txn.view(Waits).closing(txn.now)
    waits = [wait for wait in closing if out_of_turn(txn, wait.waiter)]
    if deadline is not None:
        dues.append(deadline)
    return Work(ready, waits, stranded, later, min(dues, default=None))


class Offer(Args):
    agent: Name
    boundary: Literal["tool"] | None = None


def _hand_over(txn: Txn, agent: str, modes: tuple[str, ...], boundary: str, how: str) -> dict[str, Any] | None:
    deliveries = txn.view(Deliveries)
    queued, total = deliveries.queued(agent, modes)
    shown: list[Entry] = fitted(queued, show=lambda entry: entry.shown())
    if not shown:
        return None
    input = expose(
        txn,
        agent,
        [Exposed.of(entry.ref, "gist", entry.gist) for entry in shown],
        how=how,
        boundary=boundary,
        positions=deliveries.stops(agent, shown),
        **chain_of(shown),
    )
    return {
        "input": input,
        "boundary": boundary,
        "items": [entry.model_dump(include={"ref", "gist", "sender", "body"}) for entry in shown],
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
    """Hand an agent what is queued: a new turn if it is out of one, its earliest boundary if it is working.

    `boundary="tool"` asks for pending steer notices to go on a coordination tool's result, so no effect is requested.
    """
    agent = txn.view(Agents).get(a.agent)
    if agent is None:
        raise Refused("not_found", f"no agent {a.agent}")
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
    """Record that a driver saw an offer injected, which is observed exposure. A repeat changes nothing."""
    found = txn.view(Deliveries).offer(input)
    if found is None:
        raise Refused("not_found", f"no offer {input}")
    reader, positions, delivered = found
    if not delivered:
        data = {
            "input": input,
            "positions": positions,
            "boundary": boundary,
            "evidence": evidence,
            "native_id": native_id,
        }
        txn.emit(
            "context.delivered",
            f"context/{reader}",
            gist=f"offer {input} delivered",
            agent=reader,
            data=data,
            cause=[input],
        )


class Confirm(Args):
    input: Seq
    boundary: str | None = None
    evidence: str | None = None


@op("delivery.confirm", on=lambda a: f"input/{a.input}", runtime=True)
def confirm(txn: Txn, a: Confirm) -> None:
    """Record that a driver saw an offer injected."""
    confirmed(txn, a.input, a.boundary, a.evidence)


@op("delivery.ready", query=True, runtime=True)
def delivery_ready(txn: Txn, a: Args) -> dict[str, Any]:
    """List what the courier could do now."""
    found = work(txn)
    waits = [wait.id for wait in found.waits]
    return {"agents": found.agents, "waits": waits, "stranded": found.stranded, "due": found.due}


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
