"""A person's flow from a terminal: the installed `platoon-harness` on real harnesses and native logins. Set
`PLATOON_HARNESS_LIVE=1` to run these, and say what ran.

Budget: at most 60 model calls in all, counted from the journals, each test stating its own: `claude-haiku-5-5` on
Claude Code, and `gpt-6-luna` at low effort on Codex. Every session has a budget, so that a runaway stops itself.
"""

import asyncio
import json
import os
import shutil
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from ..integration.cli import Cli, Done, checked, finished, line_where, said
from .support import CLAUDE, CODEX, EFFORT, seeded, tests_pass

pytestmark = [
    pytest.mark.live,
    pytest.mark.timeout(540),
    pytest.mark.skipif(os.environ.get("PLATOON_HARNESS_LIVE") != "1", reason="needs PLATOON_HARNESS_LIVE=1"),
    pytest.mark.skipif(shutil.which("claude") is None, reason="claude is not installed"),
    pytest.mark.skipif(shutil.which("codex") is None, reason="codex is not installed"),
]

WITHIN = 300.0
LIMITS = ("budget.turns = 12", 'budget.wall = "4m"')
"""No `tokens` limit, which `test_interrupts.py` holds. A live run had one, when a turn a stop cut off left a limit in
tokens unable to let the next turn begin, and it exited 2."""
HARNESSES = {
    "claude": (f'model = "{CLAUDE}"', f'effort = "{EFFORT}"'),
    "codex": (f'model = "{CODEX}"', f'effort = "{EFFORT}"', 'sandbox = "workspace-write"'),
}
JOB = (
    "`python3 -m unittest` fails in this repository, which has two bugs. Put one task per bug on the queue `tasks`, "
    "start one worker to claim and fix them both, and finish when both are fixed."
)
FOLLOW_UP = "When it is fixed, leave a one-line summary as `summary` on the board `notes`."
SLOW = "Run this shell command once and wait for it to end: sleep 20; echo done > slow.txt. Then reply with one word."


@pytest.fixture
async def cli(tmp_path: Path) -> AsyncIterator[Cli]:
    work = seeded(tmp_path / "work")
    made = Cli(work)
    made.env = {**os.environ, "PLATOON_HARNESS_HOME": str(tmp_path / "root")}
    yield made
    await asyncio.to_thread(made.end)


def settings(role: str, harness: str) -> list[str]:
    """`--set` lines that put a role on its live model, and the session under its budget."""
    lines = [f"roles.{role}.{line}" for line in HARNESSES[harness]]
    return [word for line in (*lines, *LIMITS) for word in ("--set", line)]


def calls(events: list[dict]) -> int:
    return sum(event["type"] == "model.called" for event in events)


async def test_init_then_a_claude_lead_and_a_codex_worker_settle_headless(cli: Cli):
    """Budget: at most 40 model calls, counted from the journal. `init` writes the team, `run --json` takes the job on
    stdin, and from other processes a person's message reaches the lead mid-run while `events --follow` watches."""
    initialized = await cli.run("init")
    run = await cli.start(
        "run",
        "--json",
        "--plan-login",
        "--approvals",
        "allow",
        "--name",
        "m1",
        *settings("lead", "claude"),
        *settings("worker", "codex"),
        stdin=asyncio.subprocess.PIPE,
    )
    assert run.stdin is not None
    run.stdin.write(JOB.encode())
    run.stdin.close()
    await said(run, "session m1")
    following = asyncio.ensure_future(finished(await cli.start("events", "m1", "--follow", "--json"), within=WITHIN))
    seen: list[dict] = []
    await line_where(run, seen, "type", "task.claimed", within=WITHIN)
    running = asyncio.ensure_future(finished(run, within=WITHIN))
    sent = await cli.run("message", "send", "m1", "--to", "@lead", "--gist", FOLLOW_UP)
    done = await running
    followed = (await following).lines()

    events = [*seen, *done.lines()[:-1]]
    ending = done.lines()[-1]
    print(initialized.stderr, ending["reason"], f"model calls: {calls(events)}", sent.stdout, sep="\n")
    assert initialized.code == 0 and 'harness = "claude"' in (cli.folder / "platoon-harness.toml").read_text()
    assert (done.code, ending["reason"]) == (0, "settled"), done.stderr
    assert checked(Done(done.code, "\n".join(map(json.dumps, [*seen, *done.lines()])), done.stderr)) == events
    ref = json.loads(sent.stdout)["ref"]
    offered = [event for event in events if event["type"] == "context.offered" and event["agent"] == "lead"]
    assert any(item["ref"] == ref for event in offered for item in event["data"]["items"])
    assert [event["seq"] for event in followed] == [event["seq"] for event in events]
    assert tests_pass(cli.folder)
    assert calls(events) <= 40


@pytest.mark.parametrize("harness", ["claude", "codex"])
async def test_a_session_stopped_mid_turn_resumes_told_what_it_was_told_at_launch(cli: Cli, harness: str):
    """Budget: at most 10 model calls, counted from the journal. A team of one named on the command line is stopped by
    `session stop` while its shell command runs, and `session resume` hands its harness again what it was told at
    launch, and tells it the turn was cut off."""
    run = await cli.start(
        "run", SLOW, "--json", "--approvals", "allow", "--name", "r1", "--harness", harness, *settings(harness, harness)
    )
    seen: list[dict] = []
    while not (seen and seen[-1]["type"] == "item.recorded" and seen[-1]["data"]["kind"] == "tool"):
        await line_where(run, seen, "type", "item.recorded", within=WITHIN)
    stopped = await cli.run("session", "stop", "r1")
    ran = await finished(run)
    resumed = await finished(await cli.start("session", "resume", "r1", "--json"), within=WITHIN)
    journal = (await cli.run("events", "r1", "--json")).lines()

    told = [event["data"]["instructions"] for event in journal if event["type"] == "agent.instructed"]
    print(f"model calls: {calls(journal)}", [event["gist"] for event in journal if event["type"] == "item.recorded"])
    assert (stopped.code, ran.code, resumed.code) == (0, 130, 0), resumed.stderr
    assert len(told) == 2 and told[0] == told[1] is not None
    assert [event["type"] for event in journal].count("agent.resumed") == 1
    assert "stopped by its owner" in [event["data"]["reason"] for event in journal if event["type"] == "turn.ended"]
    assert calls(journal) <= 10
