"""The examples as their pages run them, each in a copy of the sample project made as its page makes one, on its real
`pi` and OpenHands against FakeModel, which plays each agent from `plays.py`: the harnesses, their tools and approvals,
git and the team files are real, and only the model is scripted. A run names `fake-model` for MODEL and adds one
`--set` line, `plays.OFFLINE`, handing pi its switch for no network. The copy, `team check` and `team show` need no
harness, so they are fast tests, and run as shown. Real models run the examples in `tests/live/test_examples.py`. The
first session's guide runs the mixed team as the example's page does. None of these shows what a real model would
choose, which only a live run does."""

import ast
import asyncio
import contextlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

import pytest

from platoon_harness.testing import FakeModel

from ..unit.runtime.gitting import git
from . import plays
from .cli import ROOT, SECONDS, Cli, Done, finished, shown
from .plays import cast, copied, homed, on_fake_model, provider

pytestmark = pytest.mark.timeout(120)

RUN = 300.0
"""How long a run of an example on FakeModel may take, as it starts real harnesses, OpenHands' in seconds."""

EXAMPLE = ROOT / "examples" / "mixed-team"
README = EXAMPLE / "README.md"
SCRIPT = ROOT / "examples" / "sdk-script"
WORKTREE = ROOT / "examples" / "worktree-merge-queue" / "README.md"
REVIEW = ROOT / "examples" / "review-verification" / "README.md"
FIRST = ROOT / "docs" / "getting-started" / "first-session.md"
SWARM = ROOT / "examples" / "git-swarm" / "README.md"


async def started(cli: Cli, command: str) -> asyncio.subprocess.Process:
    """A command as a page shows it with the checkout's environment active, started: `platoon-harness` and its
    arguments, with the variables it sets in front, where `path/to/platoon-harness` is this checkout."""
    words = shlex.split(command.replace("path/to/platoon-harness", str(ROOT)))
    env = {}
    while re.fullmatch(r"[A-Z_]+=.*", words[0]):
        name, _, value = words.pop(0).partition("=")
        env[name] = value
    assert words[0] == "platoon-harness", command
    return await cli.start(*words[1:], **env)


async def typed(cli: Cli, command: str) -> Done:
    """A command as a page shows it, run to its end."""
    return await finished(await started(cli, command))


async def python_typed(cli: Cli, command: str, within: float = SECONDS) -> Done:
    """A `python` command as a page shows it with the checkout's environment active, run on this environment's
    interpreter with nothing on `PYTHONPATH`, where `path/to/platoon-harness` is this checkout."""
    python, *words = shlex.split(command.replace("path/to/platoon-harness", str(ROOT)))
    assert python == "python", command
    return await finished(await cli.start(*words, program=Path(sys.executable), PYTHONPATH=""), within=within)


def bash(cli: Cli, command: str) -> str:
    """A shell command as a page shows it, run in the command line's folder, for what it printed."""
    done = subprocess.run(["bash", "-c", command], cwd=cli.folder, env=cli.env, capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
    return done.stdout


async def journal(cli: Cli, session: str) -> list[dict[str, Any]]:
    """A session's events, as `events --json` prints them, every one in `seq` order."""
    read = await cli.run("events", session, "--json")
    events = [json.loads(line) for line in read.stdout.splitlines()]
    assert [event["seq"] for event in events] == list(range(1, len(events) + 1)), read.stderr
    return events


async def journaled(
    following: asyncio.subprocess.Process, wanted: Callable[[dict[str, Any]], bool], within: float = RUN
) -> dict[str, Any]:
    """The next event `events --follow --json` prints that is `wanted`."""
    assert following.stdout is not None
    async with asyncio.timeout(within):
        while line := await following.stdout.readline():
            if wanted(event := json.loads(line)):
                return event
    raise AssertionError("the session's runtime went before it journaled what was wanted")


def ref(event: dict) -> str:
    return f"{event['stream']}@{event['version']}"


def expected(page: Path, holding: str) -> str:
    """The output `page` says to expect: its first text block that holds `holding`."""
    blocks = re.findall(r"^```text\n(.*?)^```$", page.read_text(), re.MULTILINE | re.DOTALL)
    return next(block for block in blocks if holding in block)


def needs(*binaries: str) -> None:
    for binary in binaries:
        if shutil.which(binary) is None:
            pytest.skip(f"{binary} is not installed, so the example met no real {binary} here")


@contextlib.asynccontextmanager
async def on_sample(tmp_path: Path, page: Path, env: dict[str, str]) -> AsyncIterator[Cli]:
    """The command line in a copy of the sample project made by the commands `page` shows, with `env`, which names the
    provider, and a state root beside the copy, as yours is."""
    copy = copied(shown(page, where="cp -r"), tmp_path, {**os.environ, **env})
    made = Cli(copy)
    made.env |= {**env, "PLATOON_HARNESS_HOME": str(tmp_path / "state")}
    try:
        yield made
    finally:
        await asyncio.to_thread(made.end)


async def run_on_fake_model(cli: Cli, command: str, *, within: float = RUN) -> Done:
    """A run as a page shows it, on FakeModel, to its end."""
    return await finished(await started(cli, on_fake_model(command)), within=within)


def ran_tests(folder: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["python3", "-m", "unittest"], cwd=folder, capture_output=True, text=True, check=False)


def ran_tests_at(cli: Cli, commit: str, folder: Path) -> subprocess.CompletedProcess[str]:
    """The copy's tests, run at `commit` in a worktree of the copy's made at `folder`."""
    bash(cli, f"git worktree add -q --detach {shlex.quote(str(folder))} {commit}")
    return ran_tests(folder)


CHECKED = {"mixed-team": (README, "may message"), "worktree-merge-queue": (WORKTREE, "merges")}
CHECKED |= {"review-verification": (REVIEW, "to-reviewer"), "git-swarm": (SWARM, "may message no one")}
"""Each example whose page checks a team file, and a text of the output that page says `team show` prints."""


@pytest.mark.parametrize("example", CHECKED)
async def test_each_example_s_copy_check_and_show_run_as_its_page_shows_them(tmp_path: Path, example: str):
    """The copy, `team check` and `team show` as the page shows them, MODEL named, which need no harness, model or key,
    so they run where no pi is, as on GitHub's runners: the check says `no problems`, and the show says what the page
    says it does."""
    page, holding = CHECKED[example]
    check, show = shown(page, where="team check")

    async with on_sample(tmp_path, page, homed(tmp_path / "home")) as cli:
        checked, told = await typed(cli, check.replace("MODEL", plays.MODEL)), await typed(cli, show)

    assert (checked.code, checked.stdout, told.stdout) == (0, "no problems\n", expected(page, holding)), checked.stderr


@pytest.mark.slow
@pytest.mark.timeout(400)
async def test_the_mixed_team_fixes_issue_1_and_says_who_contributed_to_the_lead_s_answer(tmp_path: Path):
    """Its page's commands as it shows them, in a copy of the sample project, on the real `pi` and OpenHands against
    FakeModel: the person's job reaches the lead, the lead's task reaches `fixer` by the queue, whose fix and test land
    in the copy, uncommitted, with the tests passing; its note goes on the board and its report back by message, each
    write citing what it rests on; the session settles; and the page's reads find the task, the note and the report, and
    whose work the record ties to the lead's answer."""
    needs("pi")
    [run] = shown(README, where="--name tally ")
    reads = shown(README, where="task list")
    uses, reaching = shown(README, where="contributors")

    async with FakeModel() as model, on_sample(tmp_path, README, provider(model, tmp_path / "home")) as cli:
        cast(model, **plays.MIXED)
        ran = await run_on_fake_model(cli, run)
        listed, noted, messages = [await typed(cli, command) for command in reads]
        citing = json.loads((await typed(cli, uses)).stdout)["rows"]
        answer = next(
            row["ref"] for row in citing if (row.get("maker"), row.get("type")) == ("agent:lead", "agent.finished")
        )
        reached = await typed(cli, reaching.replace("REF", answer))
        events = await journal(cli, "tally")

    assert ran.code == 0, ran.stderr[-2000:]
    ending = ran.stdout[ran.stdout.rindex("settled, exit 0") :].splitlines()
    assert sorted(line.split()[:2] for line in ending[1:]) == [["@fixer", "finished"], ["@lead", "finished"]], ending
    job = (EXAMPLE / "job.md").read_text().strip()
    sent = [event for event in events if event["type"] == "message.sent"]
    assert [(event["stream"], event["gist"]) for event in sent if event["actor"] == "human:you"] == [
        ("inbox/lead", job)
    ]
    assert [event["stream"] for event in sent if event["data"]["subject"] == "fixer"] == ["inbox/lead"]
    tasks = [event["type"] for event in events if event["stream"] == "task/tasks/1"]
    assert tasks == ["task.added", "task.claimed", "task.completed"]
    cited = {ref(event): event["based_on"] for event in events if event["based_on"]}
    assert cited["task/tasks/1@1"] == ["inbox/lead@1"] and cited[plays.NOTE] == ["task/tasks/1@1"]
    assert cited["task/tasks/1@3"] == [plays.NOTE]
    finished_by = {event["agent"]: ref(event) for event in events if event["type"] == "agent.finished"}
    assert cited[finished_by["fixer"]] == cited[finished_by["lead"]] == [plays.NOTE]
    changed = git("status", "--porcelain", cwd=cli.folder).split()
    assert changed == ["M", "tally/money.py", "M", "tests/test_money.py"] and ran_tests(cli.folder).returncode == 0
    assert [task["state"] for task in json.loads(listed.stdout)["tasks"]] == ["done"]
    assert json.loads(noted.stdout)["ref"] == plays.NOTE
    entries = [(entry["sender"], entry["gist"]) for entry in json.loads(messages.stdout)["entries"]]
    assert entries == [("@you", job), ("runtime", plays.FIXED)]
    assert [row["maker"] for row in json.loads(reached.stdout)["rows"]] == ["agent:lead", "agent:fixer", "human:you"]


@pytest.mark.slow
@pytest.mark.timeout(400)
async def test_the_first_session_s_steps_run_the_mixed_team_and_read_the_record_back(tmp_path: Path):
    """The guide's first three steps as it shows them, on the real `pi` and OpenHands against FakeModel: the copy and
    the run, the reads of the closed session with what `session show` says, and whose work reached the lead's answer, by
    the ref `uses` names."""
    needs("pi")
    [run] = shown(FIRST, where="--prompt-file")
    reads = shown(FIRST, where="session show")
    uses, contributors = shown(FIRST, where="contributors")

    async with FakeModel() as model, on_sample(tmp_path, FIRST, provider(model, tmp_path / "home")) as cli:
        cast(model, **plays.MIXED)
        ran = await run_on_fake_model(cli, run)
        done = {command: await typed(cli, command) for command in reads}
        rows = json.loads((await typed(cli, uses)).stdout)["rows"]
        answer = next(
            row["ref"] for row in rows if (row.get("maker"), row.get("type")) == ("agent:lead", "agent.finished")
        )
        reached = await typed(cli, contributors.replace("REF", answer))

    assert ran.code == 0 and "settled, exit 0" in ran.stdout, ran.stderr[-2000:]
    assert [step.code for step in done.values()] == [0] * len(reads)
    shown_lines = next(step.stdout for command, step in done.items() if "session show" in command).splitlines()
    assert shown_lines[0] == "first  no runtime, closed, until role:lead", shown_lines
    assert [row["maker"] for row in json.loads(reached.stdout)["rows"]] == ["agent:lead", "agent:fixer", "human:you"]


@pytest.mark.slow
@pytest.mark.timeout(400)
async def test_the_sdk_script_s_agents_each_fix_an_issue_on_a_branch_of_its_own_and_report_it(tmp_path: Path):
    """Its page's commands as it shows them, in a copy of the sample project, on OpenHands against FakeModel: the
    script's two agents each commit their fix and its test on a branch of their own, where the copy's tests pass, with
    your checkout as it was; the script prints that the session settled and each one's report; and `session list`,
    `events` and `git log` read it back by the name the script printed."""
    page = SCRIPT / "README.md"
    [run] = [command for command in shown(page, where="run.py") if "run.py" in command]
    listing, reading, logging = shown(page, where="session list")

    async with FakeModel() as model, on_sample(tmp_path, page, provider(model, tmp_path / "home")) as cli:
        cast(model, **plays.SCRIPT)
        head = git("rev-parse", "HEAD", cwd=cli.folder)
        done = await python_typed(cli, run.replace("MODEL", plays.MODEL), within=RUN)
        first, *said = done.stdout.splitlines()
        named = re.fullmatch(r"session (\S+): settled", first)
        assert done.code == 0 and named, done.stderr[-2000:]
        listed, read = await typed(cli, listing), await typed(cli, reading.replace("NAME", named[1]))
        logged = bash(cli, logging.replace("NAME", named[1]))
        branches = {agent: f"platoon-harness/{named[1]}/{agent}" for agent in plays.SCRIPT}
        tested = {agent: ran_tests_at(cli, branch, tmp_path / agent).returncode for agent, branch in branches.items()}

    assert sorted(said) == [f"cents: {plays.CENTS}", f"comments: {plays.COMMENTS}"]
    assert named[1] in listed.stdout and read.code == 0 and "agent_finish" in read.stdout, read.stderr
    assert logged.split(maxsplit=1)[1] == "Read one digit of cents as tens of cents\n"
    for agent, path in (("cents", "tally/money.py"), ("comments", "tally/ledger.py")):
        changed = git("diff", "--name-only", f"{head.strip()}..{branches[agent]}", cwd=cli.folder).split()
        assert changed == sorted([path, path.replace("tally/", "tests/test_")]), changed
    assert tested == {"cents": 0, "comments": 0}
    assert (git("rev-parse", "HEAD", cwd=cli.folder), git("status", "--porcelain", cwd=cli.folder)) == (head, "")


@pytest.mark.slow
@pytest.mark.timeout(500)
async def test_the_merge_queue_example_merges_one_fix_and_hands_the_other_its_conflict(tmp_path: Path):
    """Its page's commands as it shows them, in a copy of the sample project, on the real `pi` and OpenHands against
    FakeModel: the run settles as the page says, one worker's branch merged by a commit the look records as the
    merger's, at which the copy's tests pass, and the other's conflict in `CHANGELOG.md` in its task's result, which its
    worker finishes with, the merger under Needs you while it rests on it. Git, the harnesses' tools and their approvals
    are real, and only the model is scripted."""
    needs("pi")
    [run] = shown(WORKTREE, where="--prompt-file")
    listing, showing = shown(WORKTREE, where="task list")

    async with FakeModel() as model, on_sample(tmp_path, WORKTREE, provider(model, tmp_path / "home")) as cli:
        cast(model, **plays.QUEUE)
        ran = await run_on_fake_model(cli, run, within=2 * RUN)
        listed, said = await typed(cli, listing), await typed(cli, showing)
        events = await journal(cli, "fixes")
        merges = [
            event["data"]
            for event in events
            if event["type"] == "repo.committed" and len(event["data"]["parents"]) == 2
        ]
        tested = [ran_tests_at(cli, merge["sha"], tmp_path / "merged").returncode for merge in merges]

    assert ran.code == 0, ran.stderr[-2000:]
    ending = [line.split(maxsplit=2) for line in ran.stdout[ran.stdout.rindex("settled, exit 0") :].splitlines()[1:]]
    reports = {name.removeprefix("@"): (state, words) for name, state, *words in ending}
    assert reports["lead"] == ("finished", [plays.ENDED]) and reports["merger"][0] == "waiting"
    results = {task["gist"].rpartition("/")[2]: task["result"] for task in json.loads(listed.stdout)["tasks"]}
    assert {name: (state, words) for name, (state, words) in reports.items() if name in results} == {
        name: ("finished", [result]) for name, result in results.items()
    }
    first, second = sorted(results, key=lambda name: results[name].startswith("conflict"))
    assert results == {
        first: f"merged platoon-harness/fixes/{first}",
        second: f"conflict in CHANGELOG.md: rebase platoon-harness/fixes/{second} onto mine and add it again",
    }
    committed = [event["data"] for event in events if event["type"] == "repo.committed"]
    assert sorted(commit["made_in"] for commit in committed) == ["@ada", "@bob", "@merger"]
    assert [merge["made_in"] for merge in merges] == ["@merger"] and tested == [0]
    assert "needs you: conflict conflict/@merger, merge stopped on conflicts in 1 file, CHANGELOG.md" in said.stdout


@pytest.mark.slow
@pytest.mark.timeout(500)
async def test_the_review_example_s_verifier_reads_the_commit_and_a_person_s_test_is_its_evidence(tmp_path: Path):
    """Its page's commands as it shows them, in a copy of the sample project, on the real `pi` and OpenHands against
    FakeModel: the run goes on while the verifier waits for you, as `session show` says. Your test of the commit the
    verifier names, which the changes view says passed, and your answer citing the test's record, let it finish: its
    verdict cites the commit, which it read through `repo.commit`, as the reviewer's review does, having read it so too
    and with git in its snapshot, and your answer, so the record ties the verdict to your test. A commit is recorded at
    the look after the author's turn, which the reviewer's turn can begin before, and no wait wakes an agent once a
    commit is recorded, so the reviewer's model may wait a second and ask again, a bounded retry on real time that its
    instructions ask of a real model too."""
    needs("pi")
    [run] = shown(REVIEW, where="--prompt-file")
    asking, testing, watching, answering = shown(REVIEW, where="repo test")
    listing, reaching = shown(REVIEW, where="contributors")

    async with FakeModel() as model, on_sample(tmp_path, REVIEW, provider(model, tmp_path / "home")) as cli:
        cast(model, **plays.REVIEWING)
        running = await started(cli, on_fake_model(run))
        assert running.stdout is not None and await asyncio.wait_for(running.stdout.readline(), SECONDS)
        following = await cli.start("events", "review", "--follow", "--json")
        asked = await journaled(following, lambda event: event["stream"] == "inbox/you")
        showed = await typed(cli, asking)
        sha = asked["gist"].split()[2]
        tested = await typed(cli, testing.replace("SHA", sha))
        record = await journaled(following, lambda event: event["type"] == "repo.tested")
        rows = json.loads((await typed(cli, watching)).stdout)["rows"]
        [commit_row] = [row for row in rows if row["kind"] == "commit"]
        answered = await typed(cli, answering.replace("ASK", ref(asked)).replace("TESTED", commit_row["tested"]))
        ran = await finished(running, within=RUN)
        listed = await typed(cli, listing)
        [verified] = json.loads(listed.stdout)["tasks"]
        reached = await typed(cli, reaching.replace("VERDICT", verified["result_ref"]))
        events = await journal(cli, "review")

    assert f"needs you: mention inbox/you@1, {asked['gist']}" in showed.stdout
    assert (tested.code, record["data"]["outcome"]) == (0, "passed"), tested.stderr
    assert (commit_row["tests"], commit_row["tested"]) == ("passed", ref(record))
    assert answered.code == 0 and ran.code == 0, answered.stderr + ran.stderr[-2000:]
    ending = ran.stdout[ran.stdout.rindex("settled, exit 0") :].splitlines()[1:]
    assert [line.split()[:2] for line in ending] == [[f"@{agent}", "finished"] for agent in plays.REVIEWING]
    [commit] = [event for event in events if event["type"] == "repo.committed"]
    [answer] = [event for event in events if event["stream"] == "inbox/verifier" and event["actor"] == "human:you"]
    done = {event["stream"]: event for event in events if event["type"] == "task.completed"}
    ends = {event["agent"]: event for event in events if event["type"] == "agent.finished"}
    offered = [event for event in events if event["type"] == "context.offered" and event["data"]["how"] == "read"]
    read = {
        agent: [item["ref"] for event in offered if event["agent"] == agent for item in event["data"]["items"]]
        for agent in ("reviewer", "verifier")
    }
    assert record["data"]["sha"] == commit["data"]["sha"] and commit["data"]["sha"].startswith(sha)
    assert commit["data"]["made_in"] == "@author"
    assert asked["based_on"] == [ref(commit)] and ref(commit) in read["verifier"]
    assert done["task/to-reviewer/1"]["based_on"] == [ref(commit)] and ref(commit) in read["reviewer"]
    assert answer["based_on"] == [ref(record)] and answer["data"]["reply_to"] == "inbox/you@1"
    verdict = [ref(commit), "task/to-verifier/1@1", ref(answer)]
    assert done["task/to-verifier/1"]["based_on"] == ends["verifier"]["based_on"] == verdict
    assert ends["verifier"]["data"]["gist"] == "Reviewed, and tested by you: passed"
    assert (verified["result"], verified["result_ref"]) == (ends["verifier"]["data"]["gist"], "task/to-verifier/1@3")
    assert [(row["maker"], row["first"]) for row in json.loads(reached.stdout)["rows"]] == [
        ("agent:verifier", "task/to-verifier/1@3"),
        ("agent:author", ref(commit)),
        ("agent:reviewer", "task/to-verifier/1@1"),
        ("human:you", ref(answer)),
        ("runtime", ref(record)),
    ]


@pytest.mark.slow
@pytest.mark.timeout(500)
async def test_the_git_swarm_example_ends_with_each_worker_s_outcome_on_the_sample_project(tmp_path: Path):
    """Its page's commands as it shows them, in a copy of the sample project, its script on the real `pi` against
    FakeModel: the script, which owns the session as `program:swarm`, starts four workers, at most two at once, each in
    a worktree of its own, and ends with each one's outcome as the program alone recorded it on `outcomes`: a
    contribution of `--json`, a test built on it by the SHA its outcome records, where the tests pass, a nomination
    citing that commit, seen through `repo.commit`, and an abstention. The script reads out no winner, and the commits
    stay on the workers' branches in the repository, with the checkout as it was."""
    needs("pi")
    [run] = shown(SWARM, where="run.py")
    reads = shown(SWARM, where="board query")

    async with FakeModel() as model, on_sample(tmp_path, SWARM, provider(model, tmp_path / "home")) as cli:
        cast(model, **plays.SWARM)
        head = git("rev-parse", "HEAD", cwd=cli.folder)
        ran = await python_typed(cli, on_fake_model(run), within=2 * RUN)
        first, *said = ran.stdout.splitlines()
        session = re.fullmatch(r"session (\S+): settled", first)
        assert ran.code == 0 and session, ran.stderr[-2000:]
        queried, read, traced = [await typed(cli, command.replace("NAME", session[1])) for command in reads]
        events = await journal(cli, session[1])
        branch = f"platoon-harness/{session[1]}/worker-2"
        tested = ran_tests_at(cli, branch, tmp_path / "tested")

    live, most = set(), 0
    for event in events:
        if event["type"] == "agent.spawned":
            live.add(event["data"]["name"])
            most = max(most, len(live))
        elif event["type"] == "agent.ended":
            live.discard(event["agent"])
    spawned = [(event["actor"], event["data"]["name"]) for event in events if event["type"] == "agent.spawned"]
    assert spawned == [("program:swarm", f"worker-{n}") for n in (1, 2, 3, 4)] and most <= 2
    made, built = [event for event in events if event["type"] == "repo.committed"]
    assert (made["data"]["made_in"], built["data"]["made_in"]) == ("@worker-1", "@worker-2")
    assert built["data"]["parents"] == [made["data"]["sha"]]
    assert said == [
        f"worker-1: contribute: {made['data']['sha'][:12]} Add --json",
        f"worker-2: contribute: {built['data']['sha'][:12]} Test --json",
        f"worker-3: nominate: {built['data']['sha'][:12]} Test --json",
        f"worker-4: abstain: {plays.ABSTAINED}",
    ]
    entries = {entry["name"]: entry["fields"] for entry in json.loads(queried.stdout)["results"]}
    assert entries == {
        "worker-1": {"outcome": "contribute", "sha": made["data"]["sha"]},
        "worker-2": {"outcome": "contribute", "sha": built["data"]["sha"]},
        "worker-3": {"outcome": "nominate", "sha": built["data"]["sha"]},
        "worker-4": {"outcome": "abstain"},
    }
    posted = [event for event in events if event["type"] in ("board.posted", "board.revised")]
    assert [(event["actor"], event["stream"]) for event in posted] == [
        ("program:swarm", f"board/outcomes/worker-{n}") for n in (1, 2, 3, 4)
    ]
    assert [entry["sender"] for entry in json.loads(read.stdout)["entries"]] == ["@worker-3"]
    cited = [(cite["ref"], cite["maker"], cite["exposure"]["answer"]) for cite in json.loads(traced.stdout)["declared"]]
    assert cited == [(ref(built), "agent:worker-2", "seen")]
    assert git("rev-parse", branch, cwd=cli.folder).strip() == built["data"]["sha"] and tested.returncode == 0
    assert git("rev-parse", "HEAD", cwd=cli.folder) == head


def imported(path: Path) -> set[str]:
    """Every module a Python file imports by its full name."""
    found = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            found |= {alias.name for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            found.add(node.module)
    return found


def test_no_example_imports_the_test_suite():
    """No module of an example imports one of the test suite, and no page or team file of an example names one, as a
    harness among them, so each example runs from its own folder, as a copy of it would."""
    examples = ROOT / "examples"
    importing = {
        str(path.relative_to(ROOT)): sorted(name for name in imported(path) if name.partition(".")[0] == "tests")
        for path in examples.rglob("*.py")
    }
    naming = [
        str(path.relative_to(ROOT))
        for path in sorted(examples.rglob("*"))
        if path.suffix in (".md", ".toml") and re.search(r"\btests\.\w", path.read_text())
    ]

    assert len(importing) >= 4
    assert ({path: names for path, names in importing.items() if names}, naming) == ({}, [])


def private(name: str) -> bool:
    """Whether a name is private: it starts with an underscore, and is no `__dunder__`."""
    return name.startswith("_") and not (name.startswith("__") and name.endswith("__"))


def test_every_example_reaches_the_sdk_by_public_names_alone():
    """Each name an example imports from the SDK is in `tests/public_api.txt`, and no example reaches an attribute, or
    defines a method, whose name is private, so an example teaches nothing a release may change without saying so."""
    public = {line.partition("(")[0] for line in (ROOT / "tests" / "public_api.txt").read_text().split()}
    imported, reached = [], []
    for path in sorted((ROOT / "examples").rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.ImportFrom) and (node.module or "").partition(".")[0] == "platoon_harness":
                imported += [f"{node.module}.{alias.name}" for alias in node.names]
            names = [node.attr] if isinstance(node, ast.Attribute) else []
            if isinstance(node, ast.ClassDef):
                names = [item.name for item in node.body if isinstance(item, ast.FunctionDef | ast.AsyncFunctionDef)]
            reached += [f"{path.relative_to(ROOT)}: {name}" for name in names if private(name)]

    assert len(imported) >= 5
    assert ([name for name in imported if name not in public], reached) == ([], [])
