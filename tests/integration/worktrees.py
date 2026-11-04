"""A worktree held on a real binary against FakeModel: its agent commits there, its runtime is killed, and it resumes in
the same folder. Each harness's test file runs this with its own shell tool and posture."""

import asyncio
import fcntl
import os
import signal
from collections.abc import Callable
from pathlib import Path

from platoon_harness import Session, Team
from platoon_harness.runtime.paths import read_running
from platoon_harness.testing import ToolCall

from ..unit.runtime.gitting import git
from ..unit.runtime.support import in_state, of_type, until

TIMEOUT = 60.0
COMMIT = "pwd -P > here && git add here && git commit -q -m here"
AGAIN = "pwd -P > again"


def replies(shell: Callable[[str], ToolCall]) -> tuple[ToolCall | str, ...]:
    """What FakeModel answers: a commit in the first turn, and a second look at where it runs in the next."""
    return (shell(COMMIT), "committed", shell(AGAIN), "here again")


def let_go(folder: Path) -> None:
    """Wait for a dead runtime's lock, which outlives its signal by a moment."""
    with (folder / "lock").open() as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)


async def commits_is_killed_and_resumes_in_its_worktree(team: Team, root: Path, repo: Path) -> None:
    """`team`'s one role, `bob`, in a worktree, with its approvals allowed, as a headless run that commits needs."""
    bob = team.roles["bob"].model_copy(update={"workspace": "worktree", "approvals": "allow"})
    team = team.model_copy(update={"roles": {"bob": bob}})
    guest = await Session.start(team, name="wt", root=root, cwd=repo, detach=True)
    try:
        await in_state(guest, "bob", "idle")
        await guest.send("@bob", "commit where you are")
        await until(lambda: of_type(guest, "turn.ended"), guest)
        [left] = (await guest.ending()).workspaces
        running = read_running(guest.folder)
        assert running is not None
        os.kill(running.pid, signal.SIGKILL)
    finally:
        await guest.leave()
    await asyncio.wait_for(asyncio.to_thread(let_go, guest.folder), TIMEOUT)

    async with Session.resume("wt", root=root) as owner:
        await in_state(owner, "bob", "idle")
        await owner.send("@bob", "say where you are again")
        await until(lambda: of_type(owner, "turn.ended"), owner, lambda ended: len(ended) == 2)
        resumed = await of_type(owner, "agent.resumed")

    folder = Path(left["path"])
    assert left["branch"] == "platoon-harness/wt/bob"
    assert (folder / "here").read_text().strip() == str(folder)
    assert (folder / "again").read_text().strip() == str(folder)
    assert git("log", "-1", "--format=%s", "platoon-harness/wt/bob", cwd=repo).strip() == "here"
    assert [event.agent for event in resumed] == ["bob"]
    assert git("status", "--porcelain", cwd=repo) == ""
