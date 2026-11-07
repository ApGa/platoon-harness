"""The examples as their pages run them, with no keys. The mixed team: its README's own command, which swaps the
scripted stand-ins of its `stand_ins.py` in for its harnesses through `--set`, as the project's README and the first
session's guide run it too, and on the real binaries against FakeModel, each model saying what a stand-in does; real
models run it in `tests/live/test_examples.py`. The SDK script: its README's commands, on the `exec` driver. The
worktree team: its README's commands, in a repository of their own, on the stand-ins of `scripts.py` through `--set`.
The review team: its README's commands, in a repository of their own, on the stand-ins of its own `stand_ins.py`
through `--set`, which show its flow and nothing of what a harness's sandbox or approvals stop, which only a run on
the real harnesses does."""

import asyncio
import importlib.util
import json
import re
import shlex
import shutil
from collections.abc import AsyncIterator, Callable, Sequence
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from platoon_harness import Session, load_team
from platoon_harness.testing import Call, FakeModel, ToolCall

from ..unit.runtime.gitting import repository
from ..unit.runtime.support import of_type
from . import test_claude, test_codex, test_openhands, test_pi
from .cli import ROOT, SECONDS, Cli, Done, finished, shown

pytestmark = pytest.mark.timeout(120)

EXAMPLE = ROOT / "examples" / "mixed-team"
README = EXAMPLE / "README.md"
SCRIPT = ROOT / "examples" / "sdk-script"
WORKTREE = ROOT / "examples" / "worktree-merge-queue" / "README.md"
REVIEW = ROOT / "examples" / "review-verification" / "README.md"
FIRST = ROOT / "docs" / "getting-started" / "first-session.md"


def loaded(path: Path) -> ModuleType:
    """A module of an example from its file, as an example is no package."""
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


STAND_INS = loaded(EXAMPLE / "stand_ins.py")


@pytest.fixture
async def cli(tmp_path: Path) -> AsyncIterator[Cli]:
    """The command line in a folder holding a copy of the examples where a checkout has them, as their READMEs run
    there."""
    shutil.copytree(ROOT / "examples", tmp_path / "examples", ignore=shutil.ignore_patterns("__pycache__"))
    made = Cli(tmp_path)
    yield made
    await asyncio.to_thread(made.end)


async def test_the_sdk_script_runs_a_team_with_no_keys_and_the_command_line_reads_it_back(cli: Cli):
    """The script's two agents each say what the README shows, the session settles, and `session list` and `events`
    read it back by the name the script printed."""
    [command] = shown(SCRIPT / "README.md", where="run.py")
    listing, reading = shown(SCRIPT / "README.md", where="session list")

    done = await cli.as_shown(command)

    first, *said = done.stdout.splitlines()
    match = re.fullmatch(r"session (\S+): settled", first)
    assert done.code == 0 and match, done.stderr
    assert len(said) == 2 and "\n".join(said) in (SCRIPT / "README.md").read_text()
    assert match[1] in (await cli.as_shown(listing)).stdout
    read = await cli.as_shown(reading.replace("NAME", match[1]))
    assert read.code == 0 and "counter-2" in read.stdout, read.stderr


@pytest.fixture
async def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[Cli]:
    """The command line in a repository of its own with a commit, which ignores the state root there, as the worktree
    team's page runs it from a repository of yours."""
    folder = repository(tmp_path / "repo", monkeypatch)
    (folder / ".git" / "info" / "exclude").write_text("home/\n")
    made = Cli(folder)
    yield made
    await asyncio.to_thread(made.end)


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


def the_other_way(ending: str) -> str:
    """The worktree team's ending with `ada` and `bob` the other way round, each agent's line where it stands."""
    swapped = re.sub(r"\b(ada|bob)\b", lambda name: {"ada": "bob", "bob": "ada"}[name[1]], ending)
    first, one, other, *rest = swapped.splitlines(keepends=True)
    return "".join([first, other, one, *rest])


async def test_the_worktree_team_hands_each_branch_to_its_merger_and_a_conflict_back_through_the_task(repo: Cli):
    """Its page's commands as it shows them, on the stand-ins it names: the team checks and says what it allows, and
    the run settles as the page says, one branch merged by a commit the look records as the merger's and the other's
    conflict in its task's result, which its worker finishes with, the merger under Needs you while it rests on it."""
    check, show = shown(WORKTREE, where="team check")[1:]
    [run] = shown(WORKTREE, where="--prompt-file")
    listing, showing = shown(WORKTREE, where="task list")

    checked, told, ran = await typed(repo, check), await typed(repo, show), await typed(repo, run)
    listed, said = await typed(repo, listing), await typed(repo, showing)

    assert (checked.code, checked.stdout, told.stdout) == (0, "no problems\n", expected(WORKTREE, "merges")), checked
    ending = expected(WORKTREE, "settled")
    assert ran.code == 0 and ran.stdout.endswith((ending, the_other_way(ending))), ran.stdout[-600:]
    events = await journal(repo, "contributors")
    reports = {event["agent"]: event["data"]["gist"] for event in events if event["type"] == "agent.finished"}
    results = {task["gist"].rpartition("/")[2]: task["result"] for task in json.loads(listed.stdout)["tasks"]}
    assert results == {name: reports[name] for name in ("ada", "bob")}
    committed = [event["data"] for event in events if event["type"] == "repo.committed"]
    assert [commit["made_in"] for commit in committed if len(commit["parents"]) == 2] == ["@merger"]
    assert "needs you: conflict conflict/@merger, merge stopped on conflicts in 1 file, CONTRIBUTORS.md" in said.stdout


async def journaled(following: asyncio.subprocess.Process, wanted: Callable[[dict[str, Any]], bool]) -> dict[str, Any]:
    """The next event `events --follow --json` prints that is `wanted`."""
    assert following.stdout is not None
    async with asyncio.timeout(SECONDS):
        while line := await following.stdout.readline():
            if wanted(event := json.loads(line)):
                return event
    raise AssertionError("the session's runtime went before it journaled what was wanted")


async def test_the_review_example_s_verifier_reads_the_commit_and_a_person_s_test_is_its_evidence(repo: Cli):
    """Its page's commands as it shows them, on the stand-ins of its own `stand_ins.py`: the team checks and says what
    it allows, and the run goes on while the verifier waits for you, as `session show` says. Your test of the commit
    the verifier names, and your answer citing the test's record, let it finish: its verdict cites the commit, which
    it read through `repo.commit`, as the reviewer's review does, and your answer, so the record ties the verdict to
    your test. The stand-ins show the flow, and nothing of what Codex's read-only sandbox or the approvals denied stop:
    only a run on the real harnesses shows that the verifier cannot write."""
    check, show = shown(REVIEW, where="team check")[1:]
    [run] = shown(REVIEW, where="--prompt-file")
    asking, testing, watching, answering = shown(REVIEW, where="repo test")
    listing, reaching = shown(REVIEW, where="contributors")

    checked, told = await typed(repo, check), await typed(repo, show)
    running = await started(repo, run)
    assert running.stdout is not None and await asyncio.wait_for(running.stdout.readline(), SECONDS)
    following = await repo.start("events", "review", "--follow", "--json")
    asked = await journaled(following, lambda event: event["stream"] == "inbox/you")
    showed = await typed(repo, asking)
    sha = asked["gist"].split()[2]
    tested = await typed(repo, testing.replace("SHA", sha))
    record = await journaled(following, lambda event: event["type"] == "repo.tested")
    [commit_row] = [row for row in json.loads((await typed(repo, watching)).stdout)["rows"] if row["kind"] == "commit"]
    answered = await typed(repo, answering.replace("TESTED", commit_row["tested"]))
    ran = await finished(running)
    listed, reached = await typed(repo, listing), await typed(repo, reaching)

    assert (checked.code, checked.stdout, told.stdout) == (0, "no problems\n", expected(REVIEW, "to-reviewer")), checked
    assert f"needs you: mention inbox/you@1, {asked['gist']}" in showed.stdout
    assert (tested.code, record["data"]["outcome"], commit_row["tested"]) == (0, "passed", ref(record)), tested.stderr
    assert answered.code == 0 and ran.code == 0, answered.stderr
    assert ran.stdout.endswith(expected(REVIEW, "settled")), ran.stdout[-600:]
    events = await journal(repo, "review")
    [commit] = [event for event in events if event["type"] == "repo.committed"]
    [answer] = [event for event in events if event["stream"] == "inbox/verifier" and event["actor"] == "human:you"]
    done = {event["stream"]: event for event in events if event["type"] == "task.completed"}
    ends = {event["agent"]: event for event in events if event["type"] == "agent.finished"}
    offered = [event["data"] for event in events if (event["type"], event["agent"]) == ("context.offered", "verifier")]
    read = [item["ref"] for data in offered if data["how"] == "read" for item in data["items"]]
    assert record["data"]["sha"] == commit["data"]["sha"] and commit["data"]["sha"].startswith(sha)
    assert commit["data"]["made_in"] == "@author"
    assert asked["based_on"] == [ref(commit)] and ref(commit) in read
    assert done["task/to-reviewer/1"]["based_on"] == [ref(commit)]
    assert answer["based_on"] == [ref(record)] and answer["data"]["reply_to"] == "inbox/you@1"
    verdict = [ref(commit), "task/to-verifier/1@1", ref(answer)]
    assert done["task/to-verifier/1"]["based_on"] == ends["verifier"]["based_on"] == verdict
    assert [task["result"] for task in json.loads(listed.stdout)["tasks"]] == [ends["verifier"]["data"]["gist"]]
    assert [(row["maker"], row["first"]) for row in json.loads(reached.stdout)["rows"]] == [
        ("agent:verifier", "task/to-verifier/1@3"),
        ("agent:author", ref(commit)),
        ("agent:reviewer", "task/to-verifier/1@1"),
        ("human:you", ref(answer)),
        ("runtime", ref(record)),
    ]


def ref(event: dict) -> str:
    return f"{event['stream']}@{event['version']}"


def expected(page: Path, holding: str) -> str:
    """The output `page` says to expect: its first text block that holds `holding`."""
    blocks = re.findall(r"^```text\n(.*?)^```$", page.read_text(), re.MULTILINE | re.DOTALL)
    return next(block for block in blocks if holding in block)


async def journal(cli: Cli, session: str) -> list[dict[str, Any]]:
    """A session's events, as `events --json` prints them, every one in `seq` order."""
    read = await cli.run("events", session, "--json")
    events = [json.loads(line) for line in read.stdout.splitlines()]
    assert [event["seq"] for event in events] == list(range(1, len(events) + 1)), read.stderr
    return events


async def test_the_mixed_team_example_runs_with_no_keys_through_a_queue_a_board_and_messages(cli: Cli):
    """The person's job reaches the lead, the lead's task reaches the worker by the queue, the worker's note goes on the
    board and its report back by message, each write citing what it rests on, and the session settles."""
    job = (EXAMPLE / "job.md").read_text().strip()
    [command] = shown(README, where="stand_ins:lead")

    done = await cli.as_shown(command)

    assert done.code == 0, done.stderr
    assert done.stdout.endswith(expected(README, "settled")), done.stdout[-400:]
    events = await journal(cli, "dns")
    cited = {ref(event): event["based_on"] for event in events if event["based_on"]}
    sent = [event for event in events if event["type"] == "message.sent"]
    assert [(event["stream"], event["gist"]) for event in sent if event["actor"] == "human:you"] == [
        ("inbox/lead", job)
    ]
    assert [event["stream"] for event in sent if event["data"]["subject"] == "w"] == ["inbox/lead"]
    assert [event["type"] for event in events if event["stream"] == "task/tasks/1"] == [
        "task.added",
        "task.claimed",
        "task.completed",
    ]
    note = STAND_INS.NOTE
    assert cited["task/tasks/1@1"] == ["inbox/lead@1"] and cited[note] == ["task/tasks/1@1"]
    assert cited["task/tasks/1@3"] == [note]
    finished = {event["agent"]: ref(event) for event in events if event["type"] == "agent.finished"}
    assert cited[finished["w"]] == [note] and cited[finished["lead"]] == [note]


async def test_the_mixed_team_example_says_who_contributed_to_the_lead_s_answer(cli: Cli):
    """Walked back from the lead's finish along its citations, the record reaches the worker's note, the lead's own task
    and the person's job, and names each maker once, in the order reached, weighing nobody."""
    [command] = shown(README, where="stand_ins:lead")
    await cli.as_shown(command)
    used = await cli.run("uses", "dns", "--ref", STAND_INS.NOTE)
    citing = [row for row in json.loads(used.stdout)["rows"] if row["kind"] == "declared"]
    answer = next(row["ref"] for row in citing if (row["maker"], row["type"]) == ("agent:lead", "agent.finished"))

    reached = await cli.run("contributors", "dns", "--ref", answer)

    rows = [(row["maker"], row["kinds"]) for row in json.loads(reached.stdout)["rows"]]
    assert rows == [(maker, ["declared"]) for maker in ("agent:lead", "agent:w", "human:you")], reached.stdout


async def test_the_readme_s_first_steps_run_the_mixed_team_with_no_keys_and_read_it_back(cli: Cli):
    """The README's quickstart runs the example's own no-key command, then reads the closed session: the sessions
    there are, the task on its queue, the note on its board, and what cites the note, the lead's finish among it."""
    run, *reads = shown(ROOT / "README.md", where="stand_ins:lead")

    done = [await cli.as_shown(command) for command in [run, *reads]]

    assert run == shown(README, where="stand_ins:lead")[0]
    assert [step.code for step in done] == [0] * len(done), [step.stderr for step in done]
    listed, queued, posted, cited = (step.stdout for step in done[1:])
    assert re.search(r"^dns\s.*closed$", listed, re.MULTILINE), listed
    assert [task["state"] for task in json.loads(queued)["tasks"]] == ["done"]
    assert json.loads(posted)["ref"] == STAND_INS.NOTE
    assert ("agent:lead", "agent.finished") in {
        (row.get("maker"), row.get("type")) for row in json.loads(cited)["rows"]
    }


async def test_the_first_session_s_steps_run_with_no_keys_and_read_the_record_back(cli: Cli):
    """The guide's first three steps as it shows them: the run with no keys and how it ends, the reads of the closed
    session with what `session show` says, and whose work reached the lead's answer, by the ref `uses` names."""
    [run] = shown(FIRST, where="stand_ins:lead")
    reads = shown(FIRST, where="session show")
    uses, contributors = shown(FIRST, where="contributors")

    ran = await cli.as_shown(run)
    done = {command: await cli.as_shown(command) for command in reads}

    assert ran.code == 0 and ran.stdout.endswith(expected(FIRST, "settled")), ran.stderr
    assert [step.code for step in done.values()] == [0] * len(reads)
    assert next(step.stdout for command, step in done.items() if "session show" in command) == expected(
        FIRST, "no runtime"
    )
    rows = json.loads((await cli.as_shown(uses)).stdout)["rows"]
    answer = next(row["ref"] for row in rows if (row.get("maker"), row.get("type")) == ("agent:lead", "agent.finished"))
    reached = await cli.as_shown(contributors.replace("REF", answer))
    assert [row["maker"] for row in json.loads(reached.stdout)["rows"]] == ["agent:lead", "agent:w", "human:you"]


def prefixed(tool: str, id: str, arguments: dict[str, Any]) -> ToolCall:
    return ToolCall(f"mcp__ph__{tool}", arguments, id=id)


def namespaced(tool: str, id: str, arguments: dict[str, Any]) -> ToolCall:
    return ToolCall(tool, arguments, id=id, namespace="mcp__ph")


def bare(tool: str, id: str, arguments: dict[str, Any]) -> ToolCall:
    return ToolCall(tool, arguments, id=id)


type Calling = Callable[[str, str, dict[str, Any]], ToolCall]
"""A call of our tool as a harness shows it to its model."""

WORKERS: dict[str, tuple[Any, Calling]] = {
    "codex": (test_codex, namespaced),
    "pi": (test_pi, prefixed),
    "openhands": (test_openhands, bare),
}


def said(turns: Sequence[Sequence[Call]], calling: Calling) -> list[ToolCall | str]:
    """What a model replies to do a stand-in's turns: each of its calls of ours, then a word that ends the turn."""
    replies: list[ToolCall | str] = []
    for steps in turns:
        replies += [calling(step.tool, f"call_{len(replies)}", dict(step.arguments)) for step in steps]
        replies.append("done")
    return replies


@pytest.mark.slow
@pytest.mark.timeout(300)
@pytest.mark.parametrize("worker", WORKERS)
async def test_the_mixed_team_example_runs_on_real_binaries_against_fake_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, worker: str
):
    """A Claude Code lead and a worker on another real binary in one session, each on a FakeModel of its own saying
    what the stand-ins do. Codex, pi and OpenHands read one variable for where their model is, so a session mixes Claude
    Code with one of them at a time."""
    module, calling = WORKERS[worker]
    for needed in ("claude", worker):
        if needed != "openhands" and shutil.which(needed) is None:
            pytest.skip(f"{needed} is not installed, so the example met no real {needed} here")
    async with FakeModel(*said(STAND_INS.LEAD, prefixed)) as led, FakeModel(*said(STAND_INS.WORKER, calling)) as worked:
        home = tmp_path / "home"
        leading = test_claude.keyed(home, led, monkeypatch).auth["fake"].env
        working = module.keyed(home, worked, monkeypatch).auth["fake"].env
        settings = [
            f'roles.lead.model = "{test_claude.MODEL}"',
            'roles.lead.auth = "anthropic"',
            f"auth.anthropic.env = {json.dumps(leading)}",
            f'roles.worker.harness = "{worker}"',
            f'roles.worker.model = "{module.MODEL}"',
            'roles.worker.auth = "openai"',
            f"auth.openai.env = {json.dumps(working)}",
        ]
        team = load_team(EXAMPLE / "team.toml", sets=settings)

        async with Session.start(team, root=tmp_path, cwd=tmp_path) as session:
            await session.send("@lead", (EXAMPLE / "job.md").read_text().strip())
            ending = await session.settled(timeout="4m")
            events = [event async for event in session.events()]
            started = await of_type(session, "agent.started")
            answer = next(event for event in events if event.type == "agent.finished" and event.agent == "lead")
            reached = await session.contributors(f"{answer.stream}@{answer.version}")

    assert ending.reason == "settled"
    assert {event.agent: event.data["verified"]["driver"] for event in started} == {"lead": "claude", "w": worker}
    assert [event.type for event in events if event.stream == "task/tasks/1"] == [
        "task.added",
        "task.claimed",
        "task.completed",
    ]
    assert [event.based_on for event in events if event.type == "board.posted"] == [("task/tasks/1@1",)]
    assert [(row.maker, row.kinds) for row in reached.rows] == [
        (maker, ("declared",)) for maker in ("agent:lead", "agent:w", "human:you")
    ]
