"""The examples on a real model, each run as its page runs it, in a copy of the sample project: the commands it shows,
with MODEL the model `PLATOON_HARNESS_LIVE_MODEL` names, at the endpoint `OPENAI_BASE_URL` names, on the key
`OPENAI_API_KEY` holds, which every role's auth profile hands its harness. Set `PLATOON_HARNESS_LIVE=1` and those three
to run them, and say what ran. A real model chooses its own steps, so each test holds an example to what its page
promises of any model, and to the budget its page states, in model calls counted from the journal and in wall time.
"""

import asyncio
import json
import os
import re
import shutil
from pathlib import Path
from typing import Any

import pytest

from ..integration.cli import SECONDS, finished, shown
from ..integration.test_examples import (
    FIRST,
    README,
    REVIEW,
    SCRIPT,
    SWARM,
    WORKTREE,
    journal,
    journaled,
    on_sample,
    python_typed,
    ran_tests,
    started,
    typed,
)
from ..unit.runtime.gitting import git

LIVE = ("PLATOON_HARNESS_LIVE_MODEL", "OPENAI_BASE_URL", "OPENAI_API_KEY")
"""What a live run of an example needs set, beside `PLATOON_HARNESS_LIVE=1`."""

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(os.environ.get("PLATOON_HARNESS_LIVE") != "1", reason="needs PLATOON_HARNESS_LIVE=1"),
    pytest.mark.skipif(not all(map(os.environ.get, LIVE)), reason=f"needs {', '.join(LIVE)}"),
    pytest.mark.skipif(shutil.which("pi") is None, reason="needs pi"),
]

MINUTE = 60.0


def yours(home: Path) -> dict[str, str]:
    """The environment of a live run: your endpoint and key, and a home of the run's own, whose git config names who
    commits, so no setting of yours takes part."""
    home.mkdir(parents=True, exist_ok=True)
    (home / ".gitconfig").write_text(
        "[user]\n\tname = Tester\n\temail = tester@example.invalid\n[init]\n\tdefaultBranch = main\n"
    )
    return {name: os.environ[name] for name in ("OPENAI_BASE_URL", "OPENAI_API_KEY")} | {"HOME": str(home)}


def on_your_model(command: str) -> str:
    return command.replace("MODEL", os.environ["PLATOON_HARNESS_LIVE_MODEL"])


def calls(events: list[dict[str, Any]]) -> int:
    """How many model calls a session made, as its journal counts them."""
    return sum(event["type"] == "model.called" for event in events)


def stated(events: list[dict[str, Any]]) -> str:
    """What a live test prints of a run: each agent's report, and the model calls each made."""
    reports = {event["agent"]: event["data"]["gist"] for event in events if event["type"] == "agent.finished"}
    made: dict[str, int] = {}
    for event in events:
        if event["type"] == "model.called":
            made[event["agent"]] = made.get(event["agent"], 0) + 1
    return json.dumps({"reports": reports, "calls": made, "total": calls(events)})


@pytest.mark.timeout(int(20 * MINUTE))
async def test_the_mixed_team_fixes_issue_1_on_a_real_model(tmp_path: Path):
    """Budget: at most 40 model calls and 15 minutes. The page's run in a copy of the sample project settles, the task
    on `tasks` is done, the worker's note is `fix-1` on `notes`, and the copy's tests pass with its change to
    `tally/money.py` uncommitted."""
    [run] = shown(README, where="--name tally ")

    async with on_sample(tmp_path, README, yours(tmp_path / "home")) as cli:
        ran = await finished(await started(cli, on_your_model(run)), within=15 * MINUTE)
        listed = await typed(cli, "platoon-harness task list tally --queue tasks")
        events = await journal(cli, "tally")
    print(stated(events), flush=True)

    assert ran.code == 0 and "settled, exit 0" in ran.stdout, ran.stderr[-2000:]
    assert [task["state"] for task in json.loads(listed.stdout)["tasks"]] == ["done"]
    assert "board/notes/fix-1" in {event["stream"] for event in events if event["type"] == "board.posted"}
    assert "tally/money.py" in git("status", "--porcelain", cwd=cli.folder)
    assert ran_tests(cli.folder).returncode == 0
    assert calls(events) <= 40


@pytest.mark.timeout(int(20 * MINUTE))
async def test_the_first_session_s_run_settles_on_a_real_model(tmp_path: Path):
    """Budget: at most 40 model calls and 15 minutes. The guide's run, the mixed team's, settles, and `session show`
    says it is closed."""
    [run] = shown(FIRST, where="--prompt-file")

    async with on_sample(tmp_path, FIRST, yours(tmp_path / "home")) as cli:
        ran = await finished(await started(cli, on_your_model(run)), within=15 * MINUTE)
        told = await typed(cli, "platoon-harness session show first")
        events = await journal(cli, "first")
    print(stated(events), flush=True)

    assert ran.code == 0, ran.stderr[-2000:]
    assert told.stdout.startswith("first  no runtime, closed, until role:lead"), told.stdout
    assert calls(events) <= 40


@pytest.mark.timeout(int(20 * MINUTE))
async def test_the_sdk_script_s_agents_each_commit_a_fix_on_a_real_model(tmp_path: Path):
    """Budget: at most 30 model calls and 15 minutes. The script's session settles, it prints each agent's report, and
    each agent made a commit on its own branch."""
    page = SCRIPT / "README.md"
    [run] = [command for command in shown(page, where="run.py") if "run.py" in command]

    async with on_sample(tmp_path, page, yours(tmp_path / "home")) as cli:
        done = await python_typed(cli, on_your_model(run), within=15 * MINUTE)
        first, *said = done.stdout.splitlines()
        named = re.fullmatch(r"session (\S+): settled", first)
        assert done.code == 0 and named, done.stderr[-2000:]
        events = await journal(cli, named[1])
    print(stated(events), flush=True)

    assert sorted(line.partition(":")[0] for line in said) == ["cents", "comments"]
    made_in = {event["data"]["made_in"] for event in events if event["type"] == "repo.committed"}
    assert made_in == {"@cents", "@comments"}
    assert calls(events) <= 30


@pytest.mark.timeout(int(30 * MINUTE))
async def test_the_merge_queue_example_merges_on_a_real_model(tmp_path: Path):
    """Budget: at most 80 model calls and 25 minutes. The run settles, each worker's task on `merges` is completed with
    what came of its merge, and only the merger made a merge commit, at least one."""
    [run] = shown(WORKTREE, where="--prompt-file")

    async with on_sample(tmp_path, WORKTREE, yours(tmp_path / "home")) as cli:
        ran = await finished(await started(cli, on_your_model(run)), within=25 * MINUTE)
        listed = await typed(cli, "platoon-harness task list fixes --queue merges")
        events = await journal(cli, "fixes")
    print(stated(events), flush=True)

    assert ran.code == 0 and "settled, exit 0" in ran.stdout, ran.stderr[-2000:]
    tasks = json.loads(listed.stdout)["tasks"]
    assert len(tasks) == 2 and all(task["state"] == "done" and task["result"] for task in tasks), tasks
    merges = [event for event in events if event["type"] == "repo.committed" and len(event["data"]["parents"]) == 2]
    assert {event["data"]["made_in"] for event in merges} == {"@merger"}
    assert calls(events) <= 80


@pytest.mark.timeout(int(45 * MINUTE))
async def test_the_review_example_s_verdict_rests_on_your_test_on_a_real_model(tmp_path: Path):
    """Budget: at most 60 model calls and 40 minutes, your answer included. The run goes on until the verifier asks
    you; the test then tests the author's commit and answers citing the test's record, as a person would, and the run
    settles with the verifier finished, having asked you citing that commit."""
    [run] = shown(REVIEW, where="--prompt-file")

    async with on_sample(tmp_path, REVIEW, yours(tmp_path / "home")) as cli:
        running = await started(cli, on_your_model(run))
        assert running.stdout is not None and await asyncio.wait_for(running.stdout.readline(), SECONDS)
        following = await cli.start("events", "review", "--follow", "--json")
        asked = await journaled(following, lambda event: event["stream"] == "inbox/you", within=30 * MINUTE)
        authored = [event for event in await journal(cli, "review") if event["type"] == "repo.committed"]
        tested = await typed(cli, f"platoon-harness repo test review --commit {authored[-1]['data']['sha']}")
        result = await journaled(following, lambda event: event["type"] == "repo.tested", within=5 * MINUTE)
        cited = f"{result['stream']}@{result['version']}"
        answer = f"--gist {result['data']['outcome']} --based-on {cited}"
        replied = await typed(
            cli, f"platoon-harness message send review --to @verifier --reply-to inbox/you@1 {answer}"
        )
        ran = await finished(running, within=10 * MINUTE)
        events = await journal(cli, "review")
    print(stated(events), flush=True)

    assert (tested.code, replied.code, ran.code) == (0, 0, 0), ran.stderr[-2000:]
    assert (
        result["data"]["outcome"] == "passed"
        and f"{authored[-1]['stream']}@{authored[-1]['version']}" in asked["based_on"]
    )
    assert "verifier" in {event["agent"] for event in events if event["type"] == "agent.finished"}
    assert calls(events) <= 60


@pytest.mark.timeout(int(30 * MINUTE))
async def test_the_git_swarm_example_gives_each_worker_one_outcome_on_a_real_model(tmp_path: Path):
    """Budget: at most 60 model calls and 25 minutes. The script's session settles, and each of its four workers has
    one outcome on `outcomes`, whatever its model chose."""
    [run] = shown(SWARM, where="run.py")

    async with on_sample(tmp_path, SWARM, yours(tmp_path / "home")) as cli:
        ran = await python_typed(cli, on_your_model(run), within=25 * MINUTE)
        first, *said = ran.stdout.splitlines()
        named = re.fullmatch(r"session (\S+): settled", first)
        assert ran.code == 0 and named, ran.stderr[-2000:]
        queried = await typed(cli, f"platoon-harness board query {named[1]} --board outcomes")
        events = await journal(cli, named[1])
    print(stated(events), *said, sep="\n", flush=True)

    outcomes = {entry["name"]: entry["fields"]["outcome"] for entry in json.loads(queried.stdout)["results"]}
    assert sorted(outcomes) == [f"worker-{n}" for n in (1, 2, 3, 4)], outcomes
    assert calls(events) <= 60
