"""Agents and sessions, from spawn to the one ended transition."""

from typing import Annotated, Any, Literal

from pydantic import Field, JsonValue

from platoon_harness.kernel import (
    GIST_LIMIT,
    Args,
    Effects,
    Grants,
    Principals,
    Refused,
    Stamps,
    Timers,
    Txn,
    op,
)

from .agents import Agent, Agents
from .budgets import Budget, Label, reconcile, reserve
from .channels import Channels, regroup
from .common import BodyRef, Gist, Name
from .delivery import work
from .messages import post
from .sessions import Session
from .tasks import Tasks, bury_if_spent
from .waits import Waits

Status = Literal["finished", "cancelled", "retired", "lost", "failed"]
Gap = Literal[
    "stream_lost",
    "compaction_opaque",
    "exposure_unconfirmed",
    "native_child_unattributed",
    "usage_lower_bound",
    "unknown_update",
    "hidden_call",
    "crash_window",
    "takeover",
]


def _inbox_of(principal: str) -> str:
    return f"inbox/{principal.partition(':')[2]}"


def _live(txn: Txn, name: str) -> Agent:
    agent = txn.view(Agents).get(name)
    if agent is None:
        raise Refused("not_found", f"no agent {name}")
    if agent.ended:
        raise Refused("conflict", f"{name} has ended: {agent.status}")
    return agent


def _monitor(txn: Txn, agent: Agent, gist: str | None = None, body: str | None = None) -> None:
    """Post final text to the spawning parent as the runtime, so a worker reports back even if its tools are hidden."""
    if agent.parent is None:
        return
    if agent.parent.startswith("agent:"):
        parent = txn.view(Agents).get(agent.parent.partition(":")[2])
        if parent is None or parent.ended:
            return
    text = gist or agent.final_gist or f"{agent.name} ended its turn with no final text."
    post(txn, _inbox_of(agent.parent), text, body=body or agent.final_body, subject=agent.name)


def end(
    txn: Txn,
    agent: Agent,
    status: Status,
    *,
    reason: str | None = None,
    gist: str | None = None,
    body: str | None = None,
) -> None:
    """The ended transition: one event every view folds, then what no fold may do. Any open turn ends with it."""
    name = agent.name
    owned = txn.view(Tasks).owned(agent.id)
    reconcile(txn, name, agent.role)
    if status == "finished":
        _monitor(txn, agent, gist, body)
    data = {"status": status, "reason": reason}
    txn.emit("agent.ended", f"agent/{name}", gist=f"{name} {status}"[:GIST_LIMIT], agent=name, data=data)
    if txn.view(Stamps).turn(name) is not None:
        txn.emit("turn.ended", f"turn/{name}", gist=f"turn ended: {status}", agent=name, data={"reason": status})
    txn.effect("stop", {"agent": name}, on_uncertain="retry", priority=1, agent=name)
    for task in owned:
        bury_if_spent(txn, task, txn.view(Channels).require(f"queue/{task.queue}"))
    regroup(txn, name, agent.role, joined=False)
    for child in txn.view(Agents).children(agent.id):
        if child.on_parent_exit == "adopt":
            txn.emit("agent.adopted", f"agent/{child.name}", gist=f"{child.name} adopted", agent=child.name)
        else:
            end(txn, child, "cancelled", reason=f"parent {name} ended")


class Spawn(Args):
    name: Name
    child_role: Name
    goal: Gist
    body: BodyRef | None = None


def _admit(txn: Txn, depth: int, parent: str | None) -> None:
    """The limits on the live graph, counted with those still spawning, so concurrent spawns cannot pass them."""
    limits = txn.view(Session).settings().limits
    agents = txn.view(Agents)
    if limits.max_depth is not None and depth > limits.max_depth:
        raise Refused("not_permitted", f"depth {depth} is past max_depth {limits.max_depth}")
    if limits.max_live is not None and agents.count_live() >= limits.max_live:
        raise Refused("not_permitted", f"{limits.max_live} agents are live, which is max_live")
    if limits.max_children is not None and parent and len(agents.children(parent)) >= limits.max_children:
        raise Refused("not_permitted", f"{parent} has {limits.max_children} children, which is max_children")


@op("agent.spawn", on=lambda a: f"role/{a.child_role}", tool=True)
def spawn(txn: Txn, a: Spawn) -> dict[str, Any]:
    """Start a new agent in a role you may spawn. `goal` is a gist, and a long brief goes in `body`. It reports back to
    you when it finishes. Refused
    `not_permitted` for a role or limit outside your reach, `over_budget` when the budget cannot cover another agent,
    and `conflict` when the name is taken or the session is closing: use another name, or stop spawning."""
    session = txn.view(Session)
    if not session.accepting():
        raise Refused("conflict", f"the session is {session.state()}")
    role = session.settings().roles.get(a.child_role)
    if role is None:
        raise Refused("not_found", f"no role {a.child_role}")
    agents = txn.view(Agents)
    if agents.get(a.name) is not None or txn.view(Principals).get(f"agent:{a.name}") is not None:
        raise Refused("conflict", f"{a.name} exists")
    spawner = agents.get(txn.me.name) if txn.me.kind == "agent" else None
    depth = 0 if spawner is None else spawner.depth + 1
    parent = None if txn.me.kind == "runtime" else txn.me.id
    _admit(txn, depth, parent)
    reserve(txn, a.name, a.child_role, agents=1.0)
    txn.emit(
        "agent.spawned",
        f"agent/{a.name}",
        gist=f"{a.name} spawned as {a.child_role}"[:GIST_LIMIT],
        agent=a.name,
        refs=[a.body] if a.body else (),
        data={
            "name": a.name,
            "role": a.child_role,
            "parent": parent,
            "depth": depth,
            "goal": a.goal,
            "body": a.body,
            "harness": role.harness,
            "model": role.model,
            "on_parent_exit": role.on_parent_exit,
            "delivery": role.delivery,
            "inbox_depth": role.inbox_depth,
        },
    )
    spec = {"agent": a.name, "role": a.child_role}
    launch = {
        **spec,
        "goal": a.goal,
        "body": a.body,
        "model": role.model,
        "harness": role.harness,
        "scopes": role.tools,
    }
    txn.effect("admit", spec, on_uncertain="surface", agent=a.name)
    txn.effect("workspace", {**spec, "workspace": role.workspace}, on_uncertain="reconcile", agent=a.name)
    txn.effect("launch", launch, on_uncertain="reconcile", agent=a.name)
    return {"agent": a.name, "state": "spawning"}


class Finish(Args):
    gist: Gist = ""
    body: BodyRef | None = None


@op("agent.finish", tool=True)
def finish(txn: Txn, a: Finish) -> None:
    """Finish your work for good. `gist` and `body` are your final report, sent to whoever spawned you. Call it last:
    your credential ends here. Refused `invalid` for anyone but an agent."""
    if txn.me.kind != "agent":
        raise Refused("invalid", "only an agent can finish")
    end(txn, _live(txn, txn.me.name), "finished", gist=a.gist or None, body=a.body)


class Named(Args):
    agent: Name


@op("agent.interrupt", on=lambda a: f"agent/{a.agent}", tool=True)
def interrupt(txn: Txn, a: Named) -> dict[str, Any]:
    """Stop an agent's turn at the boundary its harness can. The agent lives on. Refused `conflict` when it has no open
    turn: there is nothing to stop."""
    agent = _live(txn, a.agent)
    if txn.view(Stamps).turn(agent.name) is None:
        raise Refused("conflict", f"{agent.name} has no open turn")
    return {
        "effect": txn.effect("interrupt", {"agent": agent.name}, on_uncertain="retry", priority=1, agent=agent.name)
    }


@op("agent.cancel", on=lambda a: f"agent/{a.agent}", tool=True)
def cancel(txn: Txn, a: Named) -> None:
    """End an agent now. Refused `conflict` when it has ended already."""
    end(txn, _live(txn, a.agent), "cancelled", reason=f"cancelled by {txn.me.id}")


@op("agent.retire", on=lambda a: f"agent/{a.agent}", tool=True)
def retire(txn: Txn, a: Named) -> None:
    """Take an agent out of the live team. Its history stays. Refused `conflict` when it has ended already."""
    end(txn, _live(txn, a.agent), "retired", reason=f"retired by {txn.me.id}")


@op("agent.takeover", on=lambda a: f"agent/{a.agent}")
def takeover(txn: Txn, a: Named) -> None:
    """Hold an agent's deliveries so a human can drive its native session. Refused `unsupported` with no resume."""
    if txn.me.kind != "human":
        raise Refused("not_permitted", "only a human takes over an agent")
    agent = _live(txn, a.agent)
    if not agent.resume:
        raise Refused("unsupported", f"{agent.name}'s harness cannot resume, so a human cannot return it")
    if agent.state == "held":
        raise Refused("conflict", {"held_by": agent.held_by})
    if txn.view(Stamps).turn(agent.name) is not None:
        txn.effect("interrupt", {"agent": agent.name}, on_uncertain="retry", priority=1, agent=agent.name)
    txn.emit(
        "agent.held",
        f"agent/{agent.name}",
        gist=f"{agent.name} held by {txn.me.id}",
        agent=agent.name,
        data={"by": txn.me.id},
    )


@op("agent.release", on=lambda a: f"agent/{a.agent}")
def release(txn: Txn, a: Named) -> None:
    """Return a held agent to the runtime and record the gap. Refused `conflict` when it is not held."""
    agent = _live(txn, a.agent)
    if agent.state != "held":
        raise Refused("conflict", f"{agent.name} is not held")
    txn.emit("agent.released", f"agent/{agent.name}", gist=f"{agent.name} released", agent=agent.name)
    _gap(txn, agent.name, "harness", "takeover")


def _gap(txn: Txn, agent: str, plane: str, what: str) -> None:
    data = {"plane": plane, "what": what}
    txn.emit("gap.recorded", f"agent/{agent}", gist=f"gap: {what}", agent=agent, data=data)


class Ready(Args):
    type: Literal["ready"]
    native: str | None = None
    version: str | None = None
    effective_model: str | None = None
    tools_visible: tuple[str, ...] | None = None
    persistent: bool = True
    resume: bool = False
    boundaries: tuple[Literal["turn", "tool", "model_call"], ...] = ("turn",)
    tool_timeout_s: float | None = None
    levels: dict[str, JsonValue] = {}


class TurnStarted(Args):
    type: Literal["turn.started"]
    turn: Annotated[str, Field(max_length=256)]


class TurnEnded(Args):
    type: Literal["turn.ended"]
    reason: Annotated[str, Field(max_length=256)] = "stopped"


class Item(Args):
    type: Literal["item"]
    kind: Literal["message", "thought", "tool", "patch"]
    gist: Gist
    phase: str | None = None
    native_id: str | None = None
    body: BodyRef | None = None
    approval: Name | None = None
    outcome: str | None = None


class Usage(Args):
    type: Literal["usage"]
    tokens: int | None = None
    usd: float | None = None
    label: Label


class Compacted(Args):
    type: Literal["compacted"]
    forgotten: tuple[str, ...] | None = None


class GapReport(Args):
    type: Literal["gap"]
    plane: str
    what: Gap


class Exited(Args):
    type: Literal["exited"]
    reason: str = "the harness exited"


class Changed(Args):
    type: Literal["changes"]
    path: Annotated[str, Field(max_length=1024)]
    added: int | None = None
    removed: int | None = None
    tests: str | None = None


Report = Ready | TurnStarted | TurnEnded | Item | Usage | Compacted | GapReport | Exited | Changed


class AgentReport(Args):
    agent: Name
    report: Annotated[Report, Field(discriminator="type")]


def _turn_ended(txn: Txn, agent: Agent, reason: str) -> None:
    """Park on an open wait, else report to the parent. Only now: a harness can batch `wait` with sibling tools."""
    name = agent.name
    if txn.view(Stamps).turn(name) is None:
        return
    parked = bool(txn.view(Waits).open_for(agent.id))
    if not parked and agent.state != "held":
        _monitor(txn, agent)
    txn.emit(
        "turn.ended", f"turn/{name}", gist=f"turn ended: {reason}"[:GIST_LIMIT], agent=name, data={"reason": reason}
    )
    reconcile(txn, name, agent.role)
    if parked and agent.state != "held":
        txn.emit("agent.parked", f"agent/{name}", gist=f"{name} parked", agent=name)


@op("agent.report", on=lambda a: f"agent/{a.agent}", runtime=True)
def report(txn: Txn, a: AgentReport) -> None:
    """Take one report from a driver, in the driver's closed vocabulary."""
    agent = txn.view(Agents).get(a.agent)
    if agent is None:
        raise Refused("not_found", f"no agent {a.agent}")
    name = agent.name
    match a.report:
        case Exited(reason=reason):
            if not agent.ended:
                end(txn, agent, "failed" if agent.state == "spawning" else "lost", reason=reason)
        case TurnEnded(reason=reason):
            _turn_ended(txn, agent, reason)
        case _ if agent.ended:
            raise Refused("conflict", f"{name} has ended: {agent.status}")
        case Ready() as ready:
            if agent.state != "spawning":
                raise Refused("conflict", f"{name} has started")
            data = ready.model_dump(exclude={"type"})
            txn.emit("agent.started", f"agent/{name}", gist=f"{name} started", agent=name, data=data)
            regroup(txn, name, agent.role, joined=True)
        case TurnStarted(turn=turn):
            data = {"turn": turn, "by": agent.held_by}
            txn.emit("turn.started", f"turn/{name}", gist=f"turn {turn} started"[:GIST_LIMIT], agent=name, data=data)
        case Item() as item:
            refs = [item.body] if item.body else ()
            data = item.model_dump(exclude={"type", "gist"})
            txn.emit("item.recorded", f"turn/{name}", gist=item.gist, agent=name, refs=refs, data=data)
        case Usage() as usage:
            data = usage.model_dump(exclude={"type"})
            txn.emit("usage.reported", f"turn/{name}", gist=f"usage: {usage.label}", agent=name, data=data)
        case Compacted(forgotten=forgotten):
            data = {"forgotten": forgotten}
            txn.emit("context.compacted", f"context/{name}", gist=f"{name} compacted", agent=name, data=data)
        case GapReport(plane=plane, what=what):
            _gap(txn, name, plane, what)
        case Changed() as change:
            data = change.model_dump(exclude={"type"})
            txn.emit("change.recorded", f"agent/{name}", gist=change.path[:GIST_LIMIT], agent=name, data=data)


def _public(agent: Agent) -> dict[str, Any]:
    """An agent as any peer may see it: its goal and activity are content, and reading content is evidence."""
    return agent.model_dump(include={"name", "role", "parent", "depth", "state", "status"})


@op("agent.list", query=True, tool=True)
def list_agents(txn: Txn, a: Args) -> list[dict[str, Any]]:
    """List every agent of this session, live or ended."""
    return [_public(agent) for agent in txn.view(Agents).listed()]


@op("agent.status", on=lambda a: f"agent/{a.agent}", query=True, tool=True)
def agent_status(txn: Txn, a: Named) -> dict[str, Any]:
    """Show one agent's state. Refused `not_found` when no such agent ever existed."""
    agent = txn.view(Agents).get(a.agent)
    if agent is None:
        raise Refused("not_found", f"no agent {a.agent}")
    return _public(agent)


@op("peers", query=True, tool=True)
def peers(txn: Txn, a: Args) -> list[dict[str, Any]]:
    """List whom you may message directly now. Targets change as agents come and go, so ask rather than remember."""
    grants = txn.view(Grants)
    live = txn.view(Principals).select(txn.me, "all")
    return [
        {"address": f"@{principal.name}", "kind": principal.kind, "role": principal.role}
        for principal in live
        if principal.id != txn.me.id and grants.permits(txn.me, "message.send", f"inbox/{principal.name}")
    ]


def _blockers(txn: Txn) -> list[str]:
    """What stands between this session and `settled`: each clause of its definition, checked."""
    found: list[str] = []
    if txn.view(Stamps).open_turns():
        found.append("open_turn")
    pending = work(txn)
    if pending.agents or pending.waits:
        found.append("deliverable_delivery")
    effects = txn.view(Effects)
    if effects.in_state("requested") or effects.in_state("started"):
        found.append("open_effect")
    if any(timer.due <= txn.now for timer in txn.view(Timers).next()):
        found.append("due_timer")
    return found


def _done(txn: Txn, until: str, settled: bool) -> bool:
    """Whether a headless session may close. Every kind stops at budget exhaustion."""
    if txn.view(Budget).exhausted(txn.now):
        return True
    if until == "settled":
        return settled
    if until == "program":
        return False
    leads = [agent for agent in txn.view(Agents).listed() if agent.role == until.removeprefix("role:")]
    return bool(leads) and all(agent.ended for agent in leads)


@op("session.status", query=True, tool=True)
def session_status(txn: Txn, a: Args) -> dict[str, Any]:
    """Say whether this session is settled and, if not, what remains. A message can un-settle it; only close ends it."""
    session = txn.view(Session)
    blockers = _blockers(txn)
    until = session.settings().until
    return {
        "state": session.state(),
        "settled": not blockers,
        "blockers": blockers,
        "until": until,
        "done": _done(txn, until, not blockers),
    }


@op("session.close")
def close(txn: Txn, a: Args) -> None:
    """Drain: nothing new starts, and what is in flight finishes. Refused `conflict` when the session is not open."""
    state = txn.view(Session).state()
    if state != "open":
        raise Refused("conflict", f"the session is {state}")
    txn.emit("session.closed", "session", gist="session closing")


@op("session.cancel")
def cancel_session(txn: Txn, a: Args) -> None:
    """Stop now: every live agent ends, cancelled. Refused `conflict` once the session has stopped."""
    session = txn.view(Session)
    if session.state() in ("cancelled", "stopped"):
        raise Refused("conflict", f"the session is {session.state()}")
    txn.emit("session.cancelled", "session", gist="session cancelled")
    agents = txn.view(Agents)
    for name in [agent.name for agent in agents.live()]:
        agent = agents.get(name)
        if agent is not None and not agent.ended:  # An earlier one may have taken it down with its subtree.
            end(txn, agent, "cancelled", reason="session cancelled")


@op("session.stop", runtime=True)
def stop(txn: Txn, a: Args) -> None:
    """Record that the owner has shut down. The folder stays resumable."""
    txn.emit("session.stopped", "session", gist="session stopped")
