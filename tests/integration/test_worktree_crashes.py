"""SIGKILL at each step of making a worktree, then a resume: the workspace is retried and adopts what the last attempt
made, and its agent starts once, in it, with nothing half made left behind in your repository."""

import asyncio
import os
from pathlib import Path

import pytest

from platoon_harness import Session, Team
from platoon_harness.runtime.opening import prepare

from ..unit.runtime.gitting import git, repository
from ..unit.runtime.support import journal, rebuilt_equals_live
from .scripts import wire
from .test_kill_matrix import attached, died, killable

pytestmark = [pytest.mark.slow, pytest.mark.timeout(90)]

STEPS = [
    ("git:update-ref", "before"),
    ("git:update-ref", "after"),
    ("git:worktree add", "before"),
    ("git:worktree add", "after"),
    ("git:reset", "before"),
    ("git:reset", "after"),
    ("effect.finish:workspace", "before"),
]


def team() -> Team:
    says = wire("saying")
    worker = {"harness": says, "count": 0, "workspace": "worktree"}
    return Team.model_validate({"roles": {"bob": {"harness": says}, "ada": worker}})


@pytest.mark.parametrize(("point", "when"), STEPS)
async def test_a_kill_at_each_step_of_making_a_worktree_is_adopted_on_resume(tmp_path, monkeypatch, point, when):
    repo = repository(tmp_path / "repo", monkeypatch)
    folder = await asyncio.to_thread(prepare, team(), name="s", root=tmp_path, cwd=repo)
    nth = 2 if point.startswith("effect.") else 1
    runtime = killable(folder, point, when, nth)
    try:
        guest = await attached(folder, tmp_path)
        await guest.submit("agent.spawn", name="ada", child_role="ada", goal="the important thing")
        await died(runtime)
        await guest.leave()
    finally:
        runtime.kill()
        runtime.wait()

    async with Session.resume("s", root=tmp_path) as owner:
        ending = await owner.settled(timeout="20s")
        events = await journal(owner)
    await rebuilt_equals_live(folder)

    root = (folder / "agents" / "ada" / "workspace").resolve()
    assert next(row for row in ending.agents if row["agent"] == "ada")["status"] not in ("failed", "lost"), ending
    assert any(event.type == "turn.started" and event.agent == "ada" for event in events)
    assert [event.agent for event in events if event.type == "agent.started"].count("ada") == 1
    made = [event for event in events if event.type == "effect.finished" and event.data["kind"] == "workspace"]
    assert made[-1].data["result"]["path"] == str(root)
    made_by = git("reflog", "show", "--format=%gs", "platoon-harness/s/ada", cwd=repo)
    assert made_by.splitlines() == [made_by.splitlines()[0]] and made_by.startswith("platoon-harness: made by")
    registrations = Path(git("rev-parse", "--path-format=absolute", "--git-path", "worktrees", cwd=repo).strip())
    assert len(os.listdir(registrations)) <= 1, os.listdir(registrations)
    assert git("worktree", "list", "--porcelain", cwd=repo).count("worktree ") <= 2
