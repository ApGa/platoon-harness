"""Scripted stand-ins for the worktree team's harnesses, which do what job.md and each role's instructions ask with git
and no model at all. With this folder on `PYTHONPATH`, a role whose harness is `stand_ins:lead`, `stand_ins:worker` or
`stand_ins:merger` runs one. They show the flow: two branches handed to the merger through the queue, one merged and
one in conflict, each worker told what came of its own. Each runs in the runtime's own process, so none shows what a
sandbox or an approval stops."""

import asyncio
import json
import subprocess
import uuid
from pathlib import Path
from typing import Any

from platoon_harness.testing import ScriptedDriver

WORKERS = ["ada", "bob"]
"""The workers the job asks for."""
ADDING = "Add a line naming yourself at the end of CONTRIBUTORS.md, and hand your branch to the merger."
ENDED = "Both workers have ended: each one's report says what came of its branch."


def answer(result: Any) -> Any:
    """What one of our tools answered, from its MCP result."""
    return json.loads(result["content"][0]["text"])


def git(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=False)


def why(done: subprocess.CompletedProcess[str]) -> str:
    """The first line git said of a command that failed."""
    said = (done.stderr or done.stdout).strip()
    return said.splitlines()[0] if said else f"exit {done.returncode}"


class Lead(ScriptedDriver):
    """It spawns ada and bob, then goes back to its wait on them until it holds, and finishes saying they have ended and
    no more, as it may read no task on `merges`."""

    spawned = False

    async def _walk(self, steps: Any) -> str:
        if not self.spawned:
            self.spawned = True
            for name in WORKERS:
                await self._call("agent_spawn", {"name": name, "child_role": "worker", "goal": ADDING})
        if answer(await self._call("wait", {"agents": WORKERS}))["state"] != "released":
            return "stopped"
        await self._call("agent_finish", {"gist": ENDED})
        return "stopped"


class Worker(ScriptedDriver):
    """Its first turn adds a line naming it at the end of CONTRIBUTORS.md, commits it on its branch and adds a task to
    `merges` naming the branch; each turn then waits on that task, and once it has settled finishes with its result. If
    its commit fails, it finishes saying so and adds no task."""

    task: str | None = None

    async def _walk(self, steps: Any) -> str:
        cwd, name = self._spec.cwd, self._spec.agent
        if self.task is None:
            branch = (await asyncio.to_thread(git, "symbolic-ref", "--short", "HEAD", cwd=cwd)).stdout.strip()
            with (cwd / "CONTRIBUTORS.md").open("a") as names:
                names.write(f"{name}\n")
            await asyncio.to_thread(git, "add", "CONTRIBUTORS.md", cwd=cwd)
            committed = await asyncio.to_thread(git, "commit", "-q", "-m", f"Add {name} to the contributors", cwd=cwd)
            if committed.returncode != 0:
                await self._call("agent_finish", {"gist": f"git commit failed: {why(committed)}"})
                return "stopped"
            self.task = answer(await self._call("task_add", {"queue": "merges", "gist": f"merge {branch}"}))["task"]
        if answer(await self._call("wait", {"tasks": [f"merges/{self.task}"]}))["state"] != "released":
            return "stopped"
        tasks = answer(await self._call("task_list", {"queue": "merges"}))["tasks"]
        await self._call("agent_finish", {"gist": next(task["result"] for task in tasks if task["id"] == self.task)})
        return "stopped"


class Merger(ScriptedDriver):
    """Each turn claims each task on `merges`, merges the branch it names into its own with git, and completes it with
    what came of that, a conflict naming its paths and left for a person to see, or why git could not merge, until a
    wait for work on the queue parks it. Each call carries an id of its own, as a harness's do, so a second claim in a
    turn is no repeat of the first."""

    async def _call_anew(self, tool: str, arguments: dict[str, Any]) -> Any:
        return await self._call(tool, arguments, native_id=f"merger-{uuid.uuid4().hex}")

    async def _walk(self, steps: Any) -> str:
        cwd = self._spec.cwd
        while True:
            claimed = await self._call_anew("task_claim", {"queue": "merges"})
            if claimed.get("isError"):
                if answer(await self._call_anew("wait", {"queue": ["merges"]}))["state"] == "parked":
                    return "stopped"
                continue
            branch = answer(claimed)["gist"].removeprefix("merge ")
            merged = await asyncio.to_thread(git, "merge", "--no-ff", "--no-edit", branch, cwd=cwd)
            if merged.returncode == 0:
                gist = f"merged {branch}"
            else:
                unmerged = await asyncio.to_thread(git, "diff", "--name-only", "--diff-filter=U", cwd=cwd)
                if paths := unmerged.stdout.split():
                    gist = f"conflict in {', '.join(paths)}: rebase {branch} onto mine and add it again"
                else:
                    gist = f"git merge failed: {why(merged)}"
            await self._call_anew("task_complete", {"queue": "merges", "gist": gist})


def lead() -> ScriptedDriver:
    return Lead()


def worker() -> ScriptedDriver:
    return Worker()


def merger() -> ScriptedDriver:
    return Merger()
