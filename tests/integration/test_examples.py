"""The mixed-team example as its README runs it, with no keys: its own team file and job, with scripted stand-ins
swapped in for its harnesses through `--set`, the no-key demo, and on the real binaries against FakeModel, each model
saying what a stand-in does. Real models run it in `tests/live/test_examples.py`."""

import asyncio
import json
import shutil
from collections.abc import AsyncIterator, Callable, Sequence
from pathlib import Path
from typing import Any

import pytest

from platoon_harness import Session, load_team
from platoon_harness.testing import Call, FakeModel, ToolCall

from ..unit.runtime.support import of_type
from . import test_claude, test_codex, test_openhands, test_pi
from .cli import ROOT, Cli, checked
from .scripts import MIXED_LEAD, MIXED_WORKER, NOTE

pytestmark = pytest.mark.timeout(120)

EXAMPLE = ROOT / "examples" / "mixed-team"
STAND_INS = (
    "--set",
    'roles.lead.harness = "tests.integration.scripts:mixed_lead"',
    "--set",
    'roles.worker.harness = "tests.integration.scripts:mixed_worker"',
)


@pytest.fixture
async def cli(tmp_path: Path) -> AsyncIterator[Cli]:
    made = Cli(tmp_path)
    yield made
    await asyncio.to_thread(made.end)


def ref(event: dict) -> str:
    return f"{event['stream']}@{event['version']}"


async def test_the_mixed_team_example_runs_with_no_keys_through_a_queue_a_board_and_messages(cli: Cli):
    """The person's job reaches the lead, the lead's task reaches the worker by the queue, the worker's note goes on the
    board and its report back by message, each write citing what it rests on, and the session settles."""
    job = (EXAMPLE / "job.md").read_text().strip()

    done = await cli.run(
        "run", "--team", str(EXAMPLE / "team.toml"), "--prompt-file", str(EXAMPLE / "job.md"), *STAND_INS, "--json"
    )

    events = checked(done)
    assert (done.code, done.lines()[-1]["reason"]) == (0, "settled"), done.stderr
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
    assert cited["task/tasks/1@1"] == ["inbox/lead@1"] and cited[NOTE] == ["task/tasks/1@1"]
    assert cited["task/tasks/1@3"] == [NOTE]
    finished = {event["agent"]: ref(event) for event in events if event["type"] == "agent.finished"}
    assert cited[finished["w"]] == [NOTE] and cited[finished["lead"]] == [NOTE]


async def test_the_mixed_team_example_says_who_contributed_to_the_lead_s_answer(cli: Cli):
    """Walked back from the lead's finish along its citations, the record reaches the worker's note, the lead's own task
    and the person's job, and names each maker once, in the order reached, weighing nobody."""
    await cli.run(
        "run", "--team", str(EXAMPLE / "team.toml"), "--prompt-file", str(EXAMPLE / "job.md"), *STAND_INS, "--name", "m"
    )
    used = await cli.run("uses", "m", "--ref", NOTE)
    citing = [row for row in json.loads(used.stdout)["rows"] if row["kind"] == "declared"]
    answer = next(row["ref"] for row in citing if (row["maker"], row["type"]) == ("agent:lead", "agent.finished"))

    reached = await cli.run("contributors", "m", "--ref", answer)

    rows = [(row["maker"], row["kinds"]) for row in json.loads(reached.stdout)["rows"]]
    assert rows == [(maker, ["declared"]) for maker in ("agent:lead", "agent:w", "human:you")], reached.stdout


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
    async with FakeModel(*said(MIXED_LEAD, prefixed)) as led, FakeModel(*said(MIXED_WORKER, calling)) as worked:
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
