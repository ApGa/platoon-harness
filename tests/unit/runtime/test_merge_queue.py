"""The merge queue for worktree teams, as topologies.md writes it out: workers add their branches to a `merges` queue,
a merger in a worktree of its own merges each with git, the look records the merge or the conflict, and a conflict
reaches its worker as its task's result. On real git under `tmp_path`, with scripted harnesses doing what an agent's
git would."""

import asyncio
import json
import subprocess
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from platoon_harness import Session, Team
from platoon_harness.testing import ScriptedDriver

from .gitting import commit, git, repository
from .support import harness, of_type, scripted, until

pytestmark = pytest.mark.timeout(60)


class Contributor(ScriptedDriver):
    """A worker: its first turn writes its branch's name into `shared.txt`, commits it and asks for its branch to be
    merged; each later turn reads its tasks on `merges`, as an agent learns what became of one, into `heard`."""

    def __init__(self, heard: list[Any]) -> None:
        super().__init__([[]] * 3)
        self._heard = heard
        self._walked = 0

    async def _walk(self, steps: Sequence[Any]) -> str:
        self._walked += 1
        cwd = self._spec.cwd
        if self._walked == 1:
            branch = (await asyncio.to_thread(git, "symbolic-ref", "--short", "HEAD", cwd=cwd)).strip()
            await asyncio.to_thread(commit, cwd, "shared.txt", f"{branch}\n")
            await self._call("task_add", {"queue": "merges", "gist": f"merge {branch}"})
        else:
            listed = await self._call("task_list", {"queue": "merges"})
            self._heard.append(json.loads(listed["content"][0]["text"]))
        return "stopped"


class Merger(ScriptedDriver):
    """A merger: each turn claims the next task on `merges`, merges the branch it names into its own with git, and
    completes it with what came of that. On a conflict it completes the task naming the paths, and leaves the merge
    for a person to see."""

    def __init__(self) -> None:
        super().__init__([[]] * 3)

    async def _walk(self, steps: Sequence[Any]) -> str:
        cwd = self._spec.cwd
        claimed = await self._call("task_claim", {"queue": "merges"})
        branch = json.loads(claimed["content"][0]["text"])["gist"].removeprefix("merge ")
        merge = ["git", "merge", "--no-ff", "--no-edit", branch]
        if (await asyncio.to_thread(subprocess.run, merge, cwd=cwd, capture_output=True)).returncode == 0:
            await self._call("task_complete", {"queue": "merges", "gist": f"merged {branch}"})
        else:
            paths = ", ".join((await asyncio.to_thread(git, "diff", "--name-only", "--diff-filter=U", cwd=cwd)).split())
            gist = f"conflict in {paths}: rebase {branch} onto mine and add it again"
            await self._call("task_complete", {"queue": "merges", "gist": gist})
        return "stopped"


@pytest.fixture
def repo(tmp_path, monkeypatch) -> Path:
    folder = repository(tmp_path / "repo", monkeypatch)
    commit(folder, "shared.txt", "base\n")
    return folder


def merge_queue(heard: list[Any]) -> Team:
    """The written-out merge queue of topologies.md, on scripted harnesses."""
    worktree = {"workspace": "worktree"}
    roles = {
        "lead": {"harness": scripted(), "may_spawn": ["worker"]},
        "worker": {"harness": harness(lambda: Contributor(heard)), **worktree},
        "merger": {"harness": harness(Merger), **worktree},
    }
    merges = {"kind": "queue", "writers": "role:worker", "readers": "role:merger"}
    topology = {"manager-worker": {"manager": "lead", "workers": "worker"}, "channels": {"merges": merges}}
    return Team.model_validate({"roles": roles, "topology": topology})


async def test_the_written_out_merge_queue_tells_the_worker_of_a_conflict(repo, tmp_path):
    heard: list[Any] = []
    async with Session.start(merge_queue(heard), name="s", root=tmp_path, cwd=repo) as session:
        for name in ("ada", "bob"):
            await session.spawn(name, "worker", "add your line")
        await until(lambda: of_type(session, "task.added"), session, lambda found: len(found) == 2)
        for count in (1, 2):
            await session.send("@merger", "merge the next")
            done = await until(
                lambda: of_type(session, "task.completed"), session, lambda found, count=count: len(found) == count
            )
        conflicted = next(event for event in done if event.gist.startswith("conflict"))
        author = conflicted.gist.split("platoon-harness/s/")[1].split()[0]
        await until(session.attention, session, lambda rows: any(row["kind"] == "conflict" for row in rows))
        await session.send(f"@{author}", "what became of your merge?")
        await until(
            lambda: of_type(session, "turn.ended"), session, lambda found: [e.agent for e in found].count(author) == 2
        )
        committed = await of_type(session, "repo.committed")
        readings = [event.data for event in await of_type(session, "workspace.changed")]
        attention = await session.attention()

    merges = [event.data for event in committed if len(event.data["parents"]) == 2]
    assert [merge["made_in"] for merge in merges] == ["@merger"]
    stopped = next(reading for reading in readings if reading["workspace"] == "@merger" and reading["conflicted"])
    assert stopped["under_way"] == "merge" and [path["path"] for path in stopped["paths"]] == ["shared.txt"]
    assert [row["agent"] for row in attention if row["kind"] == "conflict"] == ["merger"]
    [told] = heard
    results = {task["gist"]: task["result"] for task in told["tasks"]}
    assert results[f"merge platoon-harness/s/{author}"] == conflicted.gist
    assert "conflict in shared.txt" in conflicted.gist
