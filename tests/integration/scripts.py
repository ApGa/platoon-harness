"""One team's harnesses, scripted: in-process, or `scripts.py <name>` as a wire program of its own."""

import asyncio
import gc
import itertools
import json
import sqlite3
import subprocess
import sys
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from platoon_harness import Team
from platoon_harness.drivers import AgentSpec, Capabilities, Delivery, Delta, DriverInfo, Item, Reporter
from platoon_harness.drivers.env import PYTHON
from platoon_harness.drivers.wire import serve
from platoon_harness.kernel import GIST_LIMIT
from platoon_harness.kernel.writer import Writer
from platoon_harness.testing import (
    ENVIRONMENT_TOOL,
    Ask,
    AskModel,
    Call,
    Compact,
    Exit,
    Hang,
    Say,
    ScriptedDriver,
    every_turn_asks_the_model,
)

PROGRAM = str(Path(__file__))
TOLD = "Begin every reply with the word kestrel, then use `peers`."
HOSTILE = "kestrel \x1b]0;owned\x1b\\ \x1b]52;c;ZXZpbA==\x1b\\ \x1b[2J \x9b31m \x1bc \u202eevil"

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
ASK_THEN_HANG = [Ask("Ship the fix?"), Hang()]
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


CONTRIBUTORS = ["ada", "bob"]
"""The workers of the worktree example's job."""
ADDING = "Add a line naming yourself at the end of CONTRIBUTORS.md, and hand your branch to the merger."
ENDED = "Both workers have ended: each one's report says what came of its branch."


def _answer(result: Any) -> Any:
    return json.loads(result["content"][0]["text"])


def _git(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=False)


def _why(done: subprocess.CompletedProcess[str]) -> str:
    """The first line git said of a command that failed."""
    said = (done.stderr or done.stdout).strip()
    return said.splitlines()[0] if said else f"exit {done.returncode}"


class Spawning(Templated):
    """The worktree example's lead: it spawns ada and bob, then goes back to its wait on them until it holds, and
    finishes saying they have ended and no more, as it may read no task on `merges`."""

    spawned = False

    async def _walk(self, steps: Any) -> str:
        if not self.spawned:
            self.spawned = True
            for name in CONTRIBUTORS:
                await self._call("agent_spawn", {"name": name, "child_role": "worker", "goal": ADDING})
        if _answer(await self._call("wait", {"agents": CONTRIBUTORS}))["state"] != "released":
            return "stopped"
        return await super()._walk([Call("agent_finish", {"gist": ENDED})])


class Contributing(Templated):
    """The worktree example's worker: its first turn adds a line naming it at the end of CONTRIBUTORS.md, commits it on
    its branch and adds a task to `merges` naming the branch; each turn then waits on that task, and once it has
    settled finishes with its result. If its commit fails, it finishes saying so and adds no task."""

    task: str | None = None

    async def _walk(self, steps: Any) -> str:
        cwd = self._spec.cwd
        if self.task is None:
            branch = (await asyncio.to_thread(_git, "symbolic-ref", "--short", "HEAD", cwd=cwd)).stdout.strip()
            with (cwd / "CONTRIBUTORS.md").open("a") as names:
                names.write(f"{self._spec.agent}\n")
            await asyncio.to_thread(_git, "add", "CONTRIBUTORS.md", cwd=cwd)
            message = f"Add {self._spec.agent} to the contributors"
            committed = await asyncio.to_thread(_git, "commit", "-q", "-m", message, cwd=cwd)
            if committed.returncode != 0:
                return await super()._walk([Call("agent_finish", {"gist": f"git commit failed: {_why(committed)}"})])
            self.task = _answer(await self._call("task_add", {"queue": "merges", "gist": f"merge {branch}"}))["task"]
        if _answer(await self._call("wait", {"tasks": [f"merges/{self.task}"]}))["state"] != "released":
            return "stopped"
        tasks = _answer(await self._call("task_list", {"queue": "merges"}))["tasks"]
        result = next(task["result"] for task in tasks if task["id"] == self.task)
        return await super()._walk([Call("agent_finish", {"gist": result})])


class Merging(ScriptedDriver):
    """The worktree example's merger: each turn claims each task on `merges`, merges the branch it names into its own
    with git, and completes it with what came of that, a conflict naming its paths and left for a person to see, or why
    git could not merge, until a wait for work on the queue parks it. Each call carries an id of its own, as a harness's
    do, so a second claim in a turn is no repeat of the first."""

    async def _call_anew(self, tool: str, arguments: dict[str, Any]) -> Any:
        return await self._call(tool, arguments, native_id=f"merging-{uuid.uuid4().hex}")

    async def _walk(self, steps: Any) -> str:
        cwd = self._spec.cwd
        while True:
            claimed = await self._call_anew("task_claim", {"queue": "merges"})
            if claimed.get("isError"):
                if _answer(await self._call_anew("wait", {"queue": ["merges"]}))["state"] == "parked":
                    return "stopped"
                continue
            branch = _answer(claimed)["gist"].removeprefix("merge ")
            merged = await asyncio.to_thread(_git, "merge", "--no-ff", "--no-edit", branch, cwd=cwd)
            if merged.returncode == 0:
                gist = f"merged {branch}"
            else:
                unmerged = await asyncio.to_thread(_git, "diff", "--name-only", "--diff-filter=U", cwd=cwd)
                if paths := unmerged.stdout.split():
                    gist = f"conflict in {', '.join(paths)}: rebase {branch} onto mine and add it again"
                else:
                    gist = f"git merge failed: {_why(merged)}"
            await self._call_anew("task_complete", {"queue": "merges", "gist": gist})


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


class Streaming(ScriptedDriver):
    """It says a long answer a word at a time, a hundred words a second for five seconds, as a model streams one."""

    async def _say(self, text: str, call_id: str | None = None) -> None:
        words = [f"word{n} " for n in range(500)]
        for word in words:
            await self._report(Delta(text=word))
            await asyncio.sleep(0.01)
        said = "".join(words)
        await self._report(Item(kind="message", gist=said[:GIST_LIMIT], body=said, call_id=call_id))


class OnAPlan(ScriptedDriver):
    """A harness signed in on a plan, as its status command would say."""

    def describe(self) -> DriverInfo:
        return super().describe().model_copy(update={"login": "plan"})


class Installed(ScriptedDriver):
    """It says where it is installed, our Python and this file, as an isolation needs to confine it."""

    def describe(self) -> DriverInfo:
        return super().describe().model_copy(update={"installed": (*PYTHON, Path(PROGRAM))})


class Returning(ScriptedDriver):
    """Once back, it never comes up, and says on stderr that it is on its way, which is the runtime's own."""

    async def start(self, spec: AgentSpec, report: Reporter) -> None:
        if ran_before(spec):
            print(f"{spec.agent} is on its way back", file=sys.stderr, flush=True)
            await asyncio.Event().wait()
        await super().start(spec, report)


class Deaf(ScriptedDriver):
    """It never hears an interrupt, so the owner's shutdown waits out its grace for the turn to end."""

    async def interrupt(self) -> None:
        return None


class Breaking(Resumable):
    """Its first turn makes the next commit of the runtime it runs in fail, as on a disk that has gone, and hangs. Once
    back it behaves."""

    async def _walk(self, steps: Any) -> str:
        if not self.back:
            writer = next(found for found in gc.get_objects() if isinstance(found, Writer))
            writer._seal = _gone
        return await super()._walk(steps)


def _gone(db: Any) -> int:
    raise sqlite3.OperationalError("disk I/O error")


FRAGILE = Capabilities(persistent=True, boundaries={"turn"}, tool_paths={"mcp-http"}, interrupt=True)
LISTENING = [[Call("wait", {"from": ["@you"], "timeout": 60})], [Call("agent_finish", {"gist": "heard you"})]]
SPAWNING = [[Call("agent_spawn", {"name": "w", "child_role": "bob", "goal": "Work on it."}), Hang()]]
CRAFTING = [
    [
        Call("agent_spawn", {"name": "kid", "child_role": "bob"}),
        Call("message_send", {"to": "@kid", "gist": "Craft three, then say what you found."}),
        Call("wait", {"agents": ["@kid"]}),
    ],
    [Say("all three are crafted")],
]
"""A root that does not stay, as the first GPU run's was: it hands its child the task, waits on its end, and ends its
next turn without finishing."""
SEALED = [Call(f"mcp__environment__{ENVIRONMENT_TOOL}", {"note": "looked"}), AskModel(), Compact()]
"""A sealed turn: the environment's tool, the model, and a compaction."""

HARNESSES = {
    "lead": lambda: Lead([FIX_THE_TEST]),
    "worker": lambda: Templated([WORK]),
    "asking": lambda: Templated([ASK_FIRST]),
    "asks_then_hangs": lambda: ScriptedDriver([ASK_THEN_HANG]),
    "hanging": lambda: Resumable([HANG_IN_A_TURN], [AFTER_A_RESUME]),
    "stuck": lambda: Stuck([], [[Say("heard it, the second time")]]),
    "fragile": lambda: Templated([[Hang()]], capabilities=FRAGILE),
    "saying": lambda: ScriptedDriver(itertools.repeat([Say("done")])),
    "asks_more": lambda: ScriptedDriver(FOLLOWING_UP),
    "spawning": lambda: ScriptedDriver(SPAWNING),
    "crafting": lambda: ScriptedDriver(CRAFTING),
    "exiting": lambda: ScriptedDriver([[Exit()]]),
    "listening": lambda: ScriptedDriver(LISTENING),
    "returning": lambda: Returning([[Hang()]]),
    "deaf": lambda: Deaf([[Hang()]]),
    "planned": lambda: OnAPlan(itertools.repeat([Say("done")])),
    "hostile": lambda: ScriptedDriver([[Say(HOSTILE)]]),
    "streaming": lambda: Streaming(itertools.repeat([Say("")])),
    "breaking": lambda: Breaking([[Say("on it"), Hang()]], [[Say("back")]]),
    "sealed": lambda: Installed(itertools.repeat(SEALED), name="wire-sealed"),
    "sealed_checked": lambda: Installed(every_turn_asks_the_model(), name="wire-sealed"),
    "spawning_contributors": lambda: Spawning([]),
    "contributing": lambda: Contributing([]),
    "merging": lambda: Merging([]),
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


def over(team: Team) -> Team:
    """`team`, whose one role is `bob`, under a scripted lead that spawns `bob` as `w` and goes on working itself."""
    given = team.canonical()
    lead = {"harness": inside("spawning"), "may_spawn": ["bob"]}
    return Team.model_validate({**given, "roles": {**given["roles"], "lead": lead}, "topology": {"edges": {}}})


def crafting_tree(team: Team) -> Team:
    """`team`, whose one role is `bob`, under a scripted lead that does not stay and spawns `bob`, which does not stay
    either, as `kid`, closing when the lead ends."""
    given = team.canonical()
    bob = {**given["roles"]["bob"], "count": 0}
    lead = {"harness": inside("crafting"), "may_spawn": ["bob"], "stays": False}
    topology = {"edges": {"lead": ["children"]}, "until": "role:lead", "limits": {"max_hops": 8}}
    return Team.model_validate({**given, "roles": {"bob": bob, "lead": lead}, "topology": topology})


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
