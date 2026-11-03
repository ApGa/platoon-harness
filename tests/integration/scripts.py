"""One team's harnesses, scripted: in-process, or `scripts.py <name>` as a wire program of its own."""

import asyncio
import itertools
import json
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from platoon_harness import Team
from platoon_harness.drivers import AgentSpec, Capabilities, Delivery, DriverInfo, Reporter
from platoon_harness.drivers.wire import serve
from platoon_harness.testing import Ask, Call, Exit, Hang, Say, ScriptedDriver

PROGRAM = str(Path(__file__))
TOLD = "Begin every reply with the word kestrel, then use `peers`."

WORKERS = ["w1", "w2"]
FIX_THE_TEST = [
    Say("On it."),
    Call("task_add", {"queue": "tasks", "gist": "fix the flaky test", "body": "It fails one run in ten."}),
    Call("task_add", {"queue": "tasks", "gist": "add a regression test"}),
    Call("agent_spawn", {"name": "w1", "child_role": "worker", "goal": "take work from the queue"}),
    Call("agent_spawn", {"name": "w2", "child_role": "worker", "goal": "take work from the queue"}),
    Call("wait", {"agents": WORKERS}),
]
REPORT_BACK = [
    Call("board_query", {"board": "notes"}),
    Call("message_send", {"to": "@you", "gist": "The test is fixed."}),
    Call("agent_finish", {"gist": "Both tasks are done."}),
]
WORK = [
    Call("task_claim", {"queue": "tasks"}),
    Call("board_post", {"board": "notes", "name": "from-{agent}", "gist": "what {agent} found", "body": "All of it."}),
    Call("task_complete", {"queue": "tasks", "gist": "done by {agent}"}),
    Call("message_send", {"to": "@lead", "gist": "{agent} is done"}),
    Call("agent_finish", {"gist": "{agent} finished"}),
]
ASK_FIRST = [Ask("Ship the fix?"), *WORK]
FOLLOWING_UP = [
    [Call("agent_spawn", {"name": "bob", "child_role": "bob", "goal": "Say: first answer", "stays": True})],
    [Call("message_send", {"to": "@bob", "gist": "A follow-up task. Say: second answer"})],
    [Call("message_send", {"to": "@bob", "gist": "A question about it. Say: it meant this"})],
    [Call("agent_retire", {"agent": "@bob"}), Call("agent_finish", {"gist": "all done"})],
]
HANG_IN_A_TURN = [Call("task_claim", {"queue": "tasks"}), Hang()]
AFTER_A_RESUME = [Call("task_complete", {"queue": "tasks", "gist": "done after the crash"}), Call("agent_finish", {})]


def ran_before(spec: AgentSpec) -> bool:
    """Whether a harness has started in this agent's folder before, as one coming back after a crash has, whether it
    reopened a session or began anew, having taken no turn. Ask once a start."""
    mark = spec.folder / "ran"
    before = mark.exists()
    spec.folder.mkdir(parents=True, exist_ok=True)
    mark.touch()
    return before


class Templated(ScriptedDriver):
    """A scripted harness whose tool arguments may say `{agent}`, since one role's agents share a script. `back` says
    it has started in this agent's folder before."""

    back = False

    async def start(self, spec: AgentSpec, report: Reporter) -> None:
        self.back = ran_before(spec)
        await super().start(spec, report)

    async def _call(self, tool: str, arguments: Any) -> Any:
        return await super()._call(tool, {key: self._filled(value) for key, value in arguments.items()})

    def _filled(self, value: Any) -> Any:
        return value.replace("{agent}", self._spec.agent) if isinstance(value, str) else value


class Lead(Templated):
    """A lead that goes back to its wait until it holds, as a model would: each message from a worker wakes it. Once
    resumed it has done its first turn, as a harness with a session has."""

    async def start(self, spec: AgentSpec, report: Reporter) -> None:
        await super().start(spec, report)
        if self.back:
            self._turns = iter(())

    async def _walk(self, steps: Any) -> str:
        if steps:
            return await super()._walk(steps)
        placed = await self._call("wait", {"agents": WORKERS})
        holds = json.loads(placed["content"][0]["text"])["state"] == "released"
        return await super()._walk(REPORT_BACK if holds else ())


class Resumable(Templated):
    """It runs one script fresh, and another once back."""

    def __init__(self, fresh: Any, resumed: Any) -> None:
        super().__init__(fresh)
        self._resumed = resumed

    async def start(self, spec: AgentSpec, report: Reporter) -> None:
        await super().start(spec, report)
        if self.back:
            self._turns = iter(self._resumed)


class Stuck(Resumable):
    """Its first handover never comes back. Once back it behaves."""

    async def deliver(self, delivery: Delivery) -> None:
        if not self.back:
            await asyncio.Event().wait()
        return await super().deliver(delivery)


class OnAPlan(ScriptedDriver):
    """A harness signed in on a plan, as its status command would say."""

    def describe(self) -> DriverInfo:
        return super().describe().model_copy(update={"login": "plan"})


FRAGILE = Capabilities(persistent=True, boundaries={"turn"}, tool_paths={"mcp-http"}, interrupt=True)
LISTENING = [[Call("wait", {"from": ["@you"], "timeout": 60})], [Call("agent_finish", {"gist": "heard you"})]]

HARNESSES = {
    "lead": lambda: Lead([FIX_THE_TEST]),
    "worker": lambda: Templated([WORK]),
    "asking": lambda: Templated([ASK_FIRST]),
    "hanging": lambda: Resumable([HANG_IN_A_TURN], [AFTER_A_RESUME]),
    "stuck": lambda: Stuck([], [[Say("heard it, the second time")]]),
    "fragile": lambda: Templated([[Hang()]], capabilities=FRAGILE),
    "saying": lambda: ScriptedDriver(itertools.repeat([Say("done")])),
    "asks_more": lambda: ScriptedDriver(FOLLOWING_UP),
    "exiting": lambda: ScriptedDriver([[Exit()]]),
    "listening": lambda: ScriptedDriver(LISTENING),
    "planned": lambda: OnAPlan(itertools.repeat([Say("done")])),
}


def __getattr__(name: str) -> Any:
    try:
        return HARNESSES[name]
    except KeyError:
        raise AttributeError(name) from None


def wire(name: str) -> dict[str, Any]:
    """A role's `harness`, as a wire program."""
    return {"command": [sys.executable, PROGRAM, name], "mode": "wire"}


def inside(name: str) -> str:
    """A role's `harness`, inside the runtime, which is quicker to start than a process of its own."""
    return f"{__name__}:{name}"


def following_up(team: Team) -> Team:
    """`team`, whose one role is `bob`, under a scripted lead that spawns `bob` to stay, gives it a follow-up task and
    a question, each once the last is answered, and retires it."""
    given = team.canonical()
    lead = {"harness": inside("asks_more"), "may_spawn": ["bob"]}
    topology = {"edges": {"lead": ["children"]}, "limits": {"max_hops": 8}}
    return Team.model_validate({**given, "roles": {**given["roles"], "lead": lead}, "topology": topology})


def manager_worker(lead: Any, worker: Any, **roles: Any) -> Team:
    return Team.model_validate(
        {
            "roles": {
                "lead": {"harness": lead, "may_spawn": ["worker"]},
                "worker": {"harness": worker},
                **roles,
            },
            "topology": {"manager-worker": {"manager": "lead", "workers": "worker"}},
        }
    )


def strings(value: Any) -> Iterator[str]:
    """Every string in a JSON value, as decoded, so that text is found whatever escapes carried it."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from strings(item)


if __name__ == "__main__":
    serve(HARNESSES[sys.argv[1]]())
