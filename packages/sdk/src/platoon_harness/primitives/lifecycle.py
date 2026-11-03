"""Agents and sessions, from spawn to the one ended transition."""

from typing import Annotated, Any, Literal

from pydantic import Field, JsonValue

from platoon_harness.kernel import (
    GIST_LIMIT,
    Args,
    Effects,
    Grants,
    ModelRef,
    Principals,
    Refused,
    Stamps,
    Timer,
    Timers,
    Txn,
    op,
)

from .agents import Agent, Agents
from .approvals import Approvals, ask
from .budgets import Budgets, reconcile, reserve
from .channels import Channels, regroup
from .clients import Gaps
from .common import AgentName, Body, Gist, Name, Paging, name_of, paged
from .delivery import confirmed, work
from .messages import Deliveries, post
from .reports import (
    CUT_OFF,
    OWNER_STOP,
    ApprovalRequested,
    Capabilities,
    Changed,
    ChildSeen,
    Compacted,
    Delta,
    Exited,
    GapReport,
    InputDelivered,
    Item,
    ModelCall,
    Native,
    Plane,
    Ready,
    Report,
    TurnEnded,
    TurnStarted,
    Usage,
)
from .sessions import SessionRecord
from .tasks import Tasks, bury_if_spent
from .waits import Waits

Status = Literal["finished", "cancelled", "retired", "lost", "failed"]

_FINISH_SECONDS = 60.0
_REASON_LIMIT = 1024
_ON_PURPOSE = ("interrupted", OWNER_STOP)
_NOTICE = (
    "Your last turn was cut off by {cause}. Any tool call in it may have run, in part or in full, whatever your "
    "history shows, and none was repeated. Check before you repeat anything, then carry on."
)
_STAYS = (
    "It stays when its task is done, and what it says at the end of each of its turns comes back to you. Message it "
    "for more. To end it, tell it to finish. `agent.retire` ends it when it is idle. `agent.cancel` ends it at any "
    "time."
)


def _inbox_of(principal: str) -> str:
    return f"inbox/{name_of(principal)}"


def _live(txn: Txn, name: str) -> Agent:
    agent = txn.view(Agents).get(name)
    if agent is None:
        raise Refused("not_found", f"no agent {name}")
    if agent.ended:
        raise Refused("conflict", f"{name} has ended: {agent.status}")
    return agent


def _starting(txn: Txn) -> list[str]:
    """Agents a turn is on its way to. One the budget refused to wake is on its way nowhere until the budget moves."""
    deliveries = txn.view(Deliveries)
    return [agent.name for agent in txn.view(Agents).live() if agent.starting and not deliveries.blocked(agent.name)]


def _at_work(txn: Txn) -> set[str]:
    """Agents in a turn or on their way to one, by a wake that is due or a wait that holds as well."""
    pending = work(txn)
    waiters = (name_of(wait.waiter) for wait in pending.waits)
    return {*_starting(txn), *txn.view(Stamps).open_turns(), *pending.agents, *pending.later, *waiters}


def _working(txn: Txn, agent: Agent, at_work: set[str]) -> list[str]:
    """Who would end with this agent and is at work. A child that holds no turn is left to `on_parent_exit`, and an
    adopted child outlives it, with all below that child."""
    found: list[str] = []
    for child in txn.view(Agents).children(agent.id):
        if child.on_parent_exit != "adopt":
            found += [child.name] if child.name in at_work else []
            found += _working(txn, child, at_work)
    return found


def _refuse_over_working(txn: Txn, agent: Agent) -> None:
    """A refusal is cut to 512 characters, so the names go last. Each tool has a sentence of its own, which a reader who
    does not hold it goes without."""
    if working := _working(txn, agent, _at_work(txn)):
        names = ", ".join(f"@{name}" for name in working)
        raise Refused(
            "conflict",
            f"{agent.name} has children at work, who would end with it. `wait` with `agents` lets them finish, and "
            f"with `from` hears one that stays when it answers. `agent.cancel` stops one now. They are {names}",
        )


def _monitor(
    txn: Txn,
    agent: Agent,
    gist: str | None = None,
    body: str | None = None,
    *,
    wake: bool | None = None,
    answers: bool = True,
) -> bool:
    """Post final text to the spawning parent as the runtime, so a worker reports back even if its tools are hidden.
    Returns whether a parent was there to hear it."""
    parent = None if agent.parent is None else txn.view(Principals).get(agent.parent)
    if parent is None or parent.state != "live":
        return False
    text = gist or agent.final_gist or f"{agent.name} ended its turn with no final text."
    body = body or agent.final_body
    post(txn, _inbox_of(parent.id), text, body=body, subject=agent.name, wake=wake, answers=answers)
    return True


def _others_at_work(txn: Txn, agent: Agent) -> bool:
    """Whether anyone else below this agent's parent is at work."""
    principals = txn.view(Principals)
    parent = principals.get(agent.parent or "")
    below = () if parent is None else principals.select(parent, "descendants")
    return bool(_at_work(txn) & {found.name for found in below} - {agent.name})


def _wakes(txn: Txn, agent: Agent, *, ended: bool = False, badly: bool = False) -> bool | None:
    """Whether a report wakes the parent: True whatever its chain has spent, False not at all, None as its inbox says.
    What went badly breaks in on a parent with a wait open, which may now never hold. Else a wait that is counting this
    agent wakes the parent when it holds, so a join of N costs one turn. But one that has only counted something of its
    doing, such as a task it settled, may need what nobody is left to do, so that takes someone else still at work."""
    if agent.parent is None:
        return None
    waits = txn.view(Waits).open_for(agent.parent)
    if badly:
        return True if waits else None
    if any(wait.awaits(agent.name, ended=ended) for wait in waits):
        return False
    counted = any(wait.counted(agent.name) for wait in waits)
    return False if counted and _others_at_work(txn, agent) else None


def end(
    txn: Txn,
    agent: Agent,
    status: Status,
    *,
    reason: str | None = None,
    gist: str | None = None,
    body: str | None = None,
) -> None:
    """The ended transition: one event every view folds, then what no fold may do. Any open turn ends with it, whoever
    spawned the agent hears how it ended, and what it had still to start never does. Only a turn is charged."""
    name = agent.name
    owned = txn.view(Tasks).owned(agent.id)
    if txn.view(Stamps).turn(name) is not None or txn.view(Budgets).turn_usage(name):
        reconcile(txn, name, agent.role)
    reason = reason and reason[:_REASON_LIMIT]
    ending = f"{name} {status}: {reason}" if reason else f"{name} {status}"
    report = gist or agent.final_gist if status == "finished" else ending[:GIST_LIMIT]
    body = body or agent.final_body
    wake = False if txn.me.id == agent.parent else _wakes(txn, agent, ended=True, badly=status != "finished")
    heard = _monitor(txn, agent, report, body, wake=wake)
    txn.emit(
        "agent.ended",
        f"agent/{name}",
        gist=(f"{name} finished: {report}" if status == "finished" and report else ending)[:GIST_LIMIT],
        agent=name,
        refs=[body] if body else (),
        data={"status": status, "reason": reason, "report": report, "body": body, "heard": heard},
    )
    if txn.view(Stamps).turn(name) is not None:
        txn.emit("turn.ended", f"turn/{name}", gist=f"turn ended: {status}", agent=name, data={"reason": status})
    if agent.finishing:
        key = _finish_key(name)
        txn.emit("timer.cleared", f"timer/{key}", gist=f"timer {key} cleared", data={"key": key})
    for effect in txn.view(Effects).requested_for(name):
        data = {"id": effect.id, "kind": effect.kind}
        txn.emit("effect.cancelled", f"effect/{effect.id}", gist=f"{effect.kind} cancelled", agent=name, data=data)
    txn.effect("stop", {"agent": name}, on_uncertain="retry", priority=1, agent=name)
    for task in owned:
        bury_if_spent(txn, task, txn.view(Channels).require(f"queue/{task.queue}"))
    regroup(txn, name, agent.role, joined=False)
    at_work = _at_work(txn)
    cancelled = txn.view(SessionRecord).state() == "cancelled"
    for child in txn.view(Agents).children(agent.id):
        if child.on_parent_exit == "adopt":
            txn.emit("agent.adopted", f"agent/{child.name}", gist=f"{child.name} adopted", agent=child.name)
        else:  # One with every turn whole is no failure, and is not dropped from training as a cancelled one is.
            status = "cancelled" if cancelled or child.name in at_work else "retired"
            end(txn, child, status, reason=f"parent {name} ended")


class Spawn(Args):
    name: Annotated[Name, Field(description="A name nobody in this session has used.")]
    child_role: Annotated[Name, Field(description="The role to start it in.")]
    goal: Annotated[Gist, Field(description="What it should do, at most 280 characters.")] = ""
    body: Body = None
    stays: Annotated[
        bool | None, Field(description="Whether it stays after its task for more. Left out, its role decides.")
    ] = None


def _admit(txn: Txn, depth: int, parent: str | None) -> None:
    """The limits on the live graph, counted with those still spawning, so concurrent spawns cannot pass them."""
    limits = txn.view(SessionRecord).settings().limits
    agents = txn.view(Agents)
    if limits.max_depth is not None and depth > limits.max_depth:
        raise Refused("not_permitted", f"depth {depth} is past max_depth {limits.max_depth}")
    if limits.max_live is not None and agents.count_live() >= limits.max_live:
        raise Refused("not_permitted", f"{limits.max_live} agents are live, which is max_live")
    if limits.max_children is not None and parent and len(agents.children(parent)) >= limits.max_children:
        raise Refused(
            "not_permitted",
            f"{parent} has {limits.max_children} children, which is max_children, and ending one makes room. "
            "`agent.retire` ends one that is idle",
        )


@op("agent.spawn", on=lambda a: f"role/{a.child_role}", tool=True)
def spawn(txn: Txn, a: Spawn) -> dict[str, Any]:
    """Start a new agent in a role you may spawn. Put anything longer than `goal` in `body`. With neither it starts idle
    and takes no turn until a message wakes it. What it says at the end of a turn comes back to you, and so does how it
    ends, so a parent can simply wait. Refused `not_permitted` for a role or limit outside your
    reach, `over_budget` when the budget cannot cover another agent, and `conflict` when the name is taken, the
    session is closing or you have finished: use another name, or stop. `not_found` when no such role exists.
    `unsupported` for `stays` on a harness that cannot stay."""
    session = txn.view(SessionRecord)
    if not session.accepting():
        raise Refused("conflict", f"the session is {session.state()}")
    role = session.settings().roles.get(a.child_role)
    if role is None:
        raise Refused("not_found", f"no role {a.child_role}")
    if txn.view(Principals).named(a.name) is not None:
        raise Refused("conflict", f"{a.name} is taken")
    agents = txn.view(Agents)
    spawner = agents.get(txn.me.name) if txn.me.kind == "agent" else None
    if spawner is not None and spawner.finishing:
        raise Refused("conflict", f"{spawner.name} has finished: end your turn")
    depth = 0 if spawner is None else spawner.depth + 1
    parent = None if txn.me.kind == "runtime" else txn.me.id
    stays = next(said for said in (a.stays, role.stays, parent is None) if said is not None)
    if stays and role.persistent is False:
        raise Refused(
            "unsupported", f"{a.child_role} runs a one-shot harness, which ends with its turn: it cannot stay"
        )
    _admit(txn, depth, parent)
    reserve(txn, a.name, a.child_role, turn=bool(a.goal or a.body), agents=1.0)
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
            "stays": stays,
            "goal": a.goal,
            "body": a.body,
            "harness": role.harness,
            "model": role.model,
            "on_parent_exit": role.on_parent_exit,
            "delivery": role.delivery,
            "inbox_depth": role.inbox_depth,
        },
        v=2,
    )
    principal = {"id": f"agent:{a.name}", "role": a.child_role, "parent": parent, "scopes": role.tools}
    txn.emit(
        "principal.added",
        f"principal/agent:{a.name}",
        gist=f"agent:{a.name} added"[:GIST_LIMIT],
        agent=a.name,
        data={**principal, "token_hash": None},
    )
    spec = {"agent": a.name, "role": a.child_role}
    launch = {**spec, "goal": a.goal, "body": a.body, "model": role.model, "harness": role.harness}
    admit = txn.effect("admit", spec, on_uncertain="surface", agent=a.name)
    workspace = txn.effect(
        "workspace", {**spec, "workspace": role.workspace}, on_uncertain="reconcile", agent=a.name, after=admit
    )
    txn.effect("launch", launch, on_uncertain="reconcile", agent=a.name, after=workspace)
    spawned = {"agent": f"@{a.name}", "state": "spawning", "stays": stays}
    return {**spawned, "next": _STAYS} if stays else spawned


class Finish(Args):
    gist: Annotated[Gist, Field(description="Your final report, at most 280 characters.")] = ""
    body: Body = None


def _finish_key(name: str) -> str:
    return f"agent/{name}/finish"


def _conclude(txn: Txn, agent: Agent) -> None:
    end(txn, agent, "finished", gist=agent.finish_gist or None, body=agent.finish_body)


@op("agent.finish", on=lambda a: None, tool=True)
def finish(txn: Txn, a: Finish) -> None:
    """End your own work for good, as this turn ends, so end your turn now. `gist` and `body` are your final report:
    your spawner receives them, and the session keeps them either way. Your tools stop working when the turn ends, and
    a turn still going a minute from now is cut off. Refused `conflict` when you have finished already, and while
    children that would end with you are working. Call `wait` with `agents` for them, or with `from` for one that
    stays. `agent.cancel` stops one now."""
    if txn.me.kind != "agent":
        raise Refused("invalid", "only an agent can finish")
    agent = _live(txn, txn.me.name)
    if agent.finishing:
        raise Refused("conflict", f"{agent.name} has finished: end your turn")
    _refuse_over_working(txn, agent)
    if txn.view(Stamps).turn(agent.name) is None:
        end(txn, agent, "finished", gist=a.gist or None, body=a.body)
        return
    data = {"gist": a.gist, "body": a.body}
    stream = f"agent/{agent.name}"
    refs = [a.body] if a.body else ()
    txn.emit("agent.finished", stream, gist=f"{agent.name} finishing", agent=agent.name, refs=refs, data=data)
    key = _finish_key(agent.name)
    timer = Timer(due=txn.now + _FINISH_SECONDS, op="agent.conclude", args={"agent": agent.name}, key=key)
    txn.emit("timer.set", f"timer/{key}", gist=f"timer {key} set", data=timer)


class Named(Args):
    agent: Annotated[AgentName, Field(description="An agent, as `@agent`. `peers` shows who is here.")]


@op("agent.conclude", on=lambda a: f"agent/{a.agent}", runtime=True)
def conclude(txn: Txn, a: Named) -> None:
    """End an agent that finished, whether or not its turn did: fired by a timer, and by recovery once that turn is
    lost. One that has ended since is left alone."""
    agent = txn.view(Agents).get(a.agent)
    if agent is not None and agent.finishing:
        _conclude(txn, agent)


@op("agent.interrupt", on=lambda a: f"agent/{a.agent}", tool=True)
def interrupt(txn: Txn, a: Named) -> dict[str, Any]:
    """Stop an agent's turn at the boundary its harness can, or a handover that has begun none, which goes back on its
    queue. The agent lives on. Refused `conflict` when neither is under way: there is nothing to stop. `not_permitted`
    when it is not below you."""
    agent = _live(txn, a.agent)
    if txn.view(Stamps).turn(agent.name) is None and agent.state != "waking":
        raise Refused("conflict", f"{agent.name} has no open turn")
    return {
        "effect": txn.effect("interrupt", {"agent": agent.name}, on_uncertain="retry", priority=1, agent=agent.name)
    }


@op("agent.cancel", on=lambda a: f"agent/{a.agent}", tool=True)
def cancel(txn: Txn, a: Named) -> None:
    """End an agent now, mid-turn if need be, with the children that cannot outlive it. Its tasks reopen. Refused
    `conflict` when it has ended already: nothing to do. `not_permitted` when it is not below you."""
    end(txn, _live(txn, a.agent), "cancelled", reason=f"cancelled by {txn.me.id}")


@op("agent.retire", on=lambda a: f"agent/{a.agent}", tool=True)
def retire(txn: Txn, a: Named) -> None:
    """Retire an agent that has stopped working: it leaves the team, and its history stays. Refused `conflict` while it
    is at work, in a turn or on its way to one, or while children that would end with it are, and when it has ended
    already. Call `wait` with `agents` for them, or with `from` for one that stays. `agent.cancel` stops one now."""
    agent = _live(txn, a.agent)
    if agent.name in _at_work(txn):
        raise Refused("conflict", f"{agent.name} is at work, in a turn or on its way to one")
    _refuse_over_working(txn, agent)
    end(txn, agent, "retired", reason=f"retired by {txn.me.id}")


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
    state = "idle" if txn.view(Stamps).turn(agent.name) is None else "running"
    data = {"state": state}
    txn.emit("agent.released", f"agent/{agent.name}", gist=f"{agent.name} released", agent=agent.name, data=data)
    _gap(txn, agent.name, "control", "takeover")


def _model(call_id: str | None) -> ModelRef | None:
    """The model call behind an event, only when a harness named a real one."""
    return ModelRef(call_id=call_id) if call_id else None


def _gap(txn: Txn, agent: str, plane: Plane, what: str) -> None:
    data = {"plane": plane, "what": what}
    txn.emit("gap.recorded", f"agent/{agent}", gist=f"gap: {what}", agent=agent, data=data)


class Start(Args):
    agent: Name
    ready: Ready
    declared: Capabilities
    verified: dict[str, JsonValue] | None = None
    levels: dict[str, JsonValue] = {}
    assurance: Literal["cooperative", "isolated"] = "cooperative"
    resumed: bool = False


@op("agent.start", on=lambda a: f"agent/{a.agent}", runtime=True)
def start(txn: Txn, a: Start) -> None:
    """Record that a harness is up, with what its driver declared and what the runtime verified of it. A report cannot
    carry these, so no driver can claim a level. A resumed harness comes back to the agent as it stood."""
    agent = _live(txn, a.agent)
    if (agent.state != "spawning") != a.resumed:
        raise Refused("conflict", f"{agent.name} has started" if not a.resumed else f"{agent.name} has not started")
    stated = a.model_dump(include={"declared", "verified", "levels", "assurance"})
    data = {**a.ready.model_dump(exclude={"type"}), **stated}
    stream = f"agent/{agent.name}"
    if a.resumed:
        txn.emit("agent.resumed", stream, gist=f"{agent.name} resumed", agent=agent.name, data=data)
    else:
        txn.emit("agent.started", stream, gist=f"{agent.name} started", agent=agent.name, data=data)
        regroup(txn, agent.name, agent.role, joined=True)


@op("agent.retell", on=lambda a: f"agent/{a.agent}", runtime=True)
def retell(txn: Txn, a: Named) -> None:
    """Tell a resumed harness what it has no way to know, as a delivery, since a resume starts no turn of its own: the
    goal it never began, or that its last turn was cut off. With neither there is nothing to say, and one that has ended
    since is left alone."""
    agent = txn.view(Agents).get(a.agent)
    if agent is None or agent.ended:
        return
    inbox = f"inbox/{agent.name}"
    if agent.unbegun:
        post(txn, inbox, agent.goal, body=agent.goal_body, wake=True)
    elif cause := CUT_OFF.get(agent.stopped or ""):
        post(txn, inbox, _NOTICE.format(cause=cause), wake=True)


class AgentReport(Args):
    agent: Name
    report: Report


def _report_turn(txn: Txn, agent: Agent, reason: str) -> None:
    """Tell the parent how a turn went. One that did not stop on its own says so, or it reads as a final answer, and one
    stopped on purpose wakes nobody and answers nothing yet."""
    if reason == "stopped":
        _monitor(txn, agent, wake=_wakes(txn, agent))
    else:
        said = f": {agent.final_gist}" if agent.final_gist else ""
        gist = f"{agent.name} turn {reason}{said}"[:GIST_LIMIT]
        on_purpose = reason in _ON_PURPOSE
        wake = False if on_purpose else _wakes(txn, agent, badly=True)
        _monitor(txn, agent, gist, wake=wake, answers=not on_purpose)


def _turn_ended(txn: Txn, agent: Agent, reason: str) -> None:
    """Park on an open wait, else report to the parent. Only now: a harness can batch `wait` with sibling tools. A
    one-shot harness has nothing after its turn, so its agent ends with it, and `stopped` means it finished."""
    name = agent.name
    if txn.view(Stamps).turn(name) is None:
        return
    if agent.finishing:
        _conclude(txn, agent)
        return
    if agent.persistent is False:
        finished = reason == "stopped"
        end(txn, agent, "finished" if finished else "failed", reason=None if finished else reason)
        return
    parked = bool(txn.view(Waits).open_for(agent.id))
    if not parked and agent.state != "held":
        _report_turn(txn, agent, reason)
    txn.emit(
        "turn.ended", f"turn/{name}", gist=f"turn ended: {reason}"[:GIST_LIMIT], agent=name, data={"reason": reason}
    )
    reconcile(txn, name, agent.role)
    if parked and agent.state != "held":
        txn.emit("agent.parked", f"agent/{name}", gist=f"{name} parked", agent=name)


@op("agent.report", on=lambda a: f"agent/{a.agent}", runtime=True)
def report(txn: Txn, a: AgentReport) -> None:
    """Take one report from a driver, in the driver's closed vocabulary. Two never come here: `ready` commits through
    `agent.start` with what the runtime verified, and a `delta` is lossy, so the host pushes it to the kernel."""
    agent = txn.view(Agents).get(a.agent)
    if agent is None:
        raise Refused("not_found", f"no agent {a.agent}")
    name = agent.name
    match a.report:
        case Ready() | Delta():
            raise Refused("invalid", f"a {a.report.type} report is not journaled through agent.report")
        case Exited(reason=reason):
            if agent.finishing:
                _conclude(txn, agent)
            elif not agent.ended:
                if txn.view(Stamps).turn(name) is not None:  # What it was doing is unknown, and a tool may run on.
                    _gap(txn, name, "control", "crash_window")
                end(txn, agent, "failed" if agent.state == "spawning" else "lost", reason=reason)
        case TurnEnded(reason=reason):
            _turn_ended(txn, agent, reason)
        case Native() as native:
            data = native.model_dump(exclude={"type"})
            gist = f"unknown {native.kind}"[:GIST_LIMIT]
            txn.emit("native.recorded", f"agent/{name}", gist=gist, agent=name, data=data)
        case GapReport(plane=plane, what=what):
            _gap(txn, name, plane, what)
        case _ if agent.ended:
            raise Refused("conflict", f"{name} has ended: {agent.status}")
        case TurnStarted(turn=turn):
            data = {"turn": turn, "by": agent.held_by}
            txn.emit("turn.started", f"turn/{name}", gist=f"turn {turn} started"[:GIST_LIMIT], agent=name, data=data)
        case Item() as item:
            refs = [item.body] if item.body else ()
            data = item.model_dump(exclude={"type", "gist"})
            model = _model(item.call_id)
            txn.emit("item.recorded", f"turn/{name}", gist=item.gist, agent=name, refs=refs, data=data, model=model)
        case Usage() as usage:
            data = usage.model_dump(exclude={"type"})
            gist = f"usage: {usage.label}"
            txn.emit("usage.reported", f"turn/{name}", gist=gist, agent=name, data=data, model=_model(usage.call_id))
        case Compacted(forgotten=tuple()):
            raise Refused("invalid", "what was forgotten is cited as a stored body")
        case Compacted(forgotten=forgotten, summary=summary):
            data = {"forgotten": forgotten, "summary": summary}
            refs = [ref for ref in (forgotten, summary) if isinstance(ref, str)]
            txn.emit("context.compacted", f"context/{name}", gist=f"{name} compacted", agent=name, refs=refs, data=data)
            if forgotten is None:
                _gap(txn, name, "control", "compaction_opaque")
        case InputDelivered() as delivered:
            if not delivered.input.isdecimal():
                raise Refused("not_found", f"no offer {delivered.input}")
            confirmed(txn, int(delivered.input), delivered.boundary, delivered.evidence, delivered.native_id)
        case ApprovalRequested(id=id, gist=gist):
            ask(txn, id, agent, gist)
        case ModelCall(call_id=call_id) as call:
            data = call.model_dump(exclude={"type"})
            gist = f"{name} called a model"
            txn.emit("model.called", f"turn/{name}", gist=gist, agent=name, data=data, model=_model(call_id))
        case ChildSeen() as child:
            data = child.model_dump(exclude={"type"})
            txn.emit("child.seen", f"agent/{name}", gist=f"{name} has a native child", agent=name, data=data)
        case Changed() as change:
            data = change.model_dump(exclude={"type"})
            txn.emit("change.recorded", f"agent/{name}", gist=change.path[:GIST_LIMIT], agent=name, data=data)


def _public(agent: Agent) -> dict[str, Any]:
    """An agent as any peer may see it: its goal and activity are content, and reading content is evidence."""
    parent = agent.parent and name_of(agent.parent)
    shown = agent.model_dump(include={"role", "depth", "stays", "state", "status"})
    return {**shown, "agent": agent.name, "parent": parent}


@op("agent.list", query=True)
def list_agents(txn: Txn, a: Args) -> list[dict[str, Any]]:
    """List every agent of this session, live or ended, as `agent`, which is what the ops that take one go by."""
    return [_public(agent) for agent in txn.view(Agents).listed()]


class Records(Args):
    agent: Name | None = None


@op("agent.records", query=True, runtime=True)
def agent_records(txn: Txn, a: Records) -> list[dict[str, Any]]:
    """List every agent as the runtime keeps it, or one, with its open turn, and whether its harness has ever said
    anything of a turn. Recovery and shutdown read these."""
    stamps = txn.view(Stamps)
    agents = txn.view(Agents)
    found = agents.listed() if a.agent is None else filter(None, [agents.get(a.agent)])
    return [
        {**agent.model_dump(), "turn": stamps.turn(agent.name), "began": stamps.version_of(f"turn/{agent.name}") > 0}
        for agent in found
    ]


@op("agent.status", on=lambda a: f"agent/{a.agent}", query=True, tool=True)
def agent_status(txn: Txn, a: Named) -> dict[str, Any]:
    """Show one agent's state, live or ended, and its open `turn`. Refused `not_found` when no such agent ever existed,
    and `not_permitted` when it is not below you."""
    agent = txn.view(Agents).get(a.agent)
    if agent is None:
        raise Refused("not_found", f"no agent {a.agent}")
    return {**_public(agent), "turn": txn.view(Stamps).turn(agent.name)}


@op("peers", query=True, tool=True)
def peers(txn: Txn, a: Paging) -> dict[str, Any]:
    """List whom you may message directly now, in `peers`, with the true `total` and a `cursor` to pass as `after`, or
    none at the end. Targets change as agents come and go, so ask rather than remember. `roles` lists the roles you may
    start an agent in."""
    grants = txn.view(Grants)
    roles = txn.view(SessionRecord).settings().roles
    live = txn.view(Principals).select(txn.me, "all")
    rows = [
        {"address": f"@{principal.name}", "kind": principal.kind, "role": principal.role}
        for principal in live
        if principal.id != txn.me.id and grants.permits(txn.me, "message.send", f"inbox/{principal.name}")
    ]
    startable = sorted(role for role in roles if grants.permits(txn.me, "agent.spawn", f"role/{role}"))
    return {**paged(rows, "peers", "address", a.after), "roles": startable}


def _blockers(txn: Txn) -> list[str]:
    """What stands between this session and `settled`: each clause of its definition, checked."""
    found: list[str] = []
    if _starting(txn):
        found.append("starting_agent")
    if txn.view(Stamps).open_turns():
        found.append("open_turn")
    pending = work(txn)
    if pending.agents or pending.waits or pending.stranded or pending.later:
        found.append("deliverable_delivery")
    effects = txn.view(Effects)
    if effects.in_state("requested") or effects.in_state("started"):
        found.append("open_effect")
    if any(timer.due <= txn.now for timer in txn.view(Timers).next()):
        found.append("due_timer")
    return found


def _parked_on_someone(txn: Txn) -> bool:
    """Whether an agent has a wait open on someone still here, which only they can end."""
    principals, waits = txn.view(Principals), txn.view(Waits)
    missing = (name for agent in txn.view(Agents).live() for wait in waits.open_for(agent.id) for name in wait.missing)
    named = (principals.named(name.removeprefix("@")) for name in missing if name.startswith("@"))
    return any(principal is not None and principal.state == "live" for principal in named)


def _done(txn: Txn, until: str, settled: bool) -> bool:
    """Whether a headless session may close. Every kind stops at budget exhaustion. A wake the budget refused is work
    left undone, and only a human can raise that budget. So is a wait on someone still here, which is no worker parked
    for more work: that waits on a queue or a channel."""
    if txn.view(Budgets).exhausted(txn.now):
        return True
    if until == "settled":
        return settled and not txn.view(Deliveries).any_blocked() and not _parked_on_someone(txn)
    if until == "program":
        return False
    leads = [agent for agent in txn.view(Agents).listed() if agent.role == until.removeprefix("role:")]
    return bool(leads) and all(agent.ended for agent in leads)


def _scheduled(txn: Txn) -> bool:
    """Whether anything the journal knows of can still move this session with nobody acting. A lease's timer outlives
    the lease, so a lease counts by its claim. An extension daemon's private schedule is not in the journal."""
    return txn.view(Timers).besides("lease.expire") or txn.view(Tasks).any_claimed() or work(txn).due is not None


def _standing(txn: Txn) -> dict[str, Any]:
    session = txn.view(SessionRecord)
    state = session.state()
    blockers = _blockers(txn)
    until = session.settings().until
    done = _done(txn, until, not blockers)
    return {
        "state": state,
        "settled": not blockers,
        "blockers": blockers,
        "until": until,
        "done": done,
        "asking": txn.view(Approvals).asking(),
        "stalled": state == "open" and not blockers and not done and until != "program" and not _scheduled(txn),
    }


@op("session.status", query=True, tool=True)
def session_status(txn: Txn, a: Args) -> dict[str, Any]:
    """Say whether this session is settled and what remains. Your own open turn is always among `blockers` while you
    ask. A message can un-settle it; only close ends it. `stalled` says it has stopped short of `until` with nothing
    scheduled, so only someone acting can move it."""
    return _standing(txn)


def _came_to(txn: Txn, state: str) -> str:
    if state == "cancelled":
        return "cancelled"
    if txn.view(Budgets).exhausted(txn.now):
        return "budget_exhausted"
    standing = _standing(txn)
    if standing["asking"] or standing["stalled"]:
        return "needs_human"
    failed = any(agent.status in ("failed", "lost") for agent in txn.view(Agents).listed())
    return "agent_failed" if failed else "settled"


@op("session.ending", query=True)
def session_ending(txn: Txn, a: Args) -> dict[str, Any]:
    """What this session has come to: its state, why, each agent and its last report, what was spent with its labels,
    and every gap."""
    state = txn.view(SessionRecord).state()
    budget = txn.view(Budgets)
    return {
        "state": state,
        "reason": _came_to(txn, state),
        "agents": [
            {
                **agent.model_dump(include={"role", "state", "status", "reason"}),
                "agent": agent.name,
                "report": None if agent.final_gist is None else {"gist": agent.final_gist, "body": agent.final_body},
                "usage": budget.usage_of(f"agent:{agent.name}"),
            }
            for agent in txn.view(Agents).listed()
        ],
        "usage": budget.usage_of("shared"),
        "gaps": txn.view(Gaps).rows(),
    }


class Close(Args):
    if_done: bool = False


@op("session.close")
def close(txn: Txn, a: Close) -> None:
    """Drain: nothing new starts, and what is in flight finishes. Refused `conflict` when the session is not open, and
    with `if_done` when `session.status` would no longer say done, as a message that got in first makes it."""
    session = txn.view(SessionRecord)
    state = session.state()
    if state != "open":
        raise Refused("conflict", f"the session is {state}")
    if a.if_done and not _done(txn, session.settings().until, not _blockers(txn)):
        raise Refused("conflict", "this session is not done")
    txn.emit("session.closed", "session", gist="session closing")


@op("session.cancel")
def cancel_session(txn: Txn, a: Args) -> None:
    """Stop now: every live agent ends, cancelled. Refused `conflict` once the session has stopped."""
    session = txn.view(SessionRecord)
    if session.state() in ("cancelled", "stopped"):
        raise Refused("conflict", f"the session is {session.state()}")
    txn.emit("session.cancelled", "session", gist="session cancelled")
    agents = txn.view(Agents)
    for name in [agent.name for agent in sorted(agents.live(), key=lambda agent: agent.depth)]:
        agent = agents.get(name)
        if agent is not None and not agent.ended:  # Each parent first, so no report goes to one that is ending too.
            end(txn, agent, "cancelled", reason="session cancelled")


@op("session.stop", runtime=True)
def stop(txn: Txn, a: Args) -> None:
    """Record that the owner has shut down. The folder stays resumable."""
    txn.emit("session.stopped", "session", gist="session stopped")
