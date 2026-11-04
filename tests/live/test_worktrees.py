"""Real harnesses in worktrees of their own, on real models and native logins, through the public `Session`. Set
`PLATOON_HARNESS_LIVE=1` to run these, and say what ran.

Budget: at most 20 model calls on each harness, each test stating its own, `claude-haiku-5-5` or `gpt-6-luna` at low
effort. Every session has a `Budget`, so that a runaway stops itself, and every repository is a throwaway one under
`tmp_path`.
"""

import asyncio
import fcntl
import os
import shutil
import signal
import socket
from pathlib import Path

import pytest

from platoon_harness import Role, Session, Team
from platoon_harness.runtime.paths import read_running
from platoon_harness.team import Budget

from ..unit.runtime.support import in_state
from .support import CLAUDE, CODEX, EFFORT, git, seeded, seen, spent

pytestmark = [
    pytest.mark.live,
    pytest.mark.timeout(300),
    pytest.mark.skipif(os.environ.get("PLATOON_HARNESS_LIVE") != "1", reason="needs PLATOON_HARNESS_LIVE=1"),
]

LIMIT = Budget(turns=6, wall="4m")
STAY = "Stay after each task for the next message: never call agent_finish."
ROLES = {
    "claude": Role(
        harness="claude", model=CLAUDE, effort=EFFORT, approvals="allow", workspace="worktree", instructions=STAY
    ),
    # Codex keeps `.git` read-only under its sandboxes, so a commit needs no sandbox, or an escalation each time.
    "codex": Role(
        harness="codex",
        model=CODEX,
        effort=EFFORT,
        approvals="allow",
        sandbox="danger-full-access",
        workspace="worktree",
        instructions=STAY,
    ),
}
COMMIT = (
    "Run these shell commands in your working directory, then reply: done. "
    "`pwd -P > here.txt`, then `git add here.txt`, then `git commit -m here`."
)
AGAIN = "Run this shell command in your working directory, then reply: done. `pwd -P > again.txt`. Do not commit it."


def let_go(folder: Path) -> None:
    """Wait for a dead runtime's lock, which outlives its signal by a moment."""
    with (folder / "lock").open() as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)


@pytest.mark.parametrize("harness", ROLES)
async def test_an_agent_commits_in_its_worktree_is_killed_and_resumes_there(harness, tmp_path):
    """Budget: at most 10 model calls, counted from the journal: a commit in one turn, then, after a `kill -9` of its
    runtime and a resume, a file in the next. Its worktree is the same folder throughout, its commit is on its branch,
    and its end keeps the worktree, with the file it left uncommitted, named in the Ending."""
    if shutil.which(harness) is None:
        pytest.skip(f"{harness} is not installed")
    work, root = seeded(tmp_path / "work"), tmp_path / "root"
    git(work, "config", "user.name", "test")
    git(work, "config", "user.email", "test@example.com")
    team = Team(roles={"bob": ROLES[harness]}, budget=LIMIT)
    guest = await Session.start(team, name="wt", root=root, cwd=work, detach=True, plan_login=True)
    try:
        await in_state(guest, "bob", "idle")
        await guest.send("@bob", COMMIT)
        await seen(guest, "turn.ended", within=150.0)
        [left] = (await guest.ending()).workspaces
        running = read_running(guest.folder)
        assert running is not None
        os.kill(running.pid, signal.SIGKILL)
    finally:
        await guest.leave()
    await asyncio.wait_for(asyncio.to_thread(let_go, root / "sessions" / "wt"), 30.0)

    async with Session.resume("wt", root=root) as session:
        await seen(session, "agent.resumed")
        await in_state(session, "bob", "idle")
        await session.send("@bob", AGAIN)
        await seen(session, "turn.ended", count=2, within=150.0)
        await session.cancel_agent("@bob")
        ending = await session.settled(timeout="1m")
        used = await spent(session)
    print(f"{harness}: {used}")
    print(f"{harness}: kept {ending.workspaces}")

    folder = Path(left["path"])
    assert used["total"] <= 10, used
    assert (folder / "here.txt").read_text().strip() == str(folder)
    assert (folder / "again.txt").read_text().strip() == str(folder)
    assert git(work, "log", "-1", "--format=%s", "platoon-harness/wt/bob").strip() == "here"
    assert git(work, "status", "--porcelain") == ""
    [kept] = ending.workspaces
    assert (kept["path"], kept["host"], kept["why"]) == (str(folder), socket.gethostname(), ["1 uncommitted paths"])
