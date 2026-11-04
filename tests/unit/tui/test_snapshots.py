"""The workspace's layout at each size the guide names, as snapshots, on a session's history so nothing moves."""

import asyncio
from pathlib import Path

import pytest

from platoon_harness import Session, Team
from platoon_harness.testing import Call, Say, ScriptedDriver
from platoon_harness_cli.tui.app import TerminalUI

from ..runtime.gitting import commit, repository, working
from ..runtime.support import in_state, of_type, until
from .support import drawn

SIZES = {"wide": (120, 32), "medium": (90, 28), "narrow": (70, 24), "slim": (52, 20), "short": (100, 14)}
LEAD = [
    Say("kestrel: I will split the work"),
    Call("agent_spawn", {"name": "w", "child_role": "worker", "goal": "fix the parser"}),
    Say("**Done.** The parser is fixed:\n\n```python\ndef parse(text):\n    return text.split()\n```"),
]


def scripted_lead() -> ScriptedDriver:
    return ScriptedDriver([LEAD])


def scripted_worker() -> ScriptedDriver:
    return ScriptedDriver([[Say("parser fixed, 3 tests pass")]])


def team() -> Team:
    """A lead and a worker on harnesses named the same in every run, as a snapshot draws their names."""
    lead = {"harness": f"{__name__}:scripted_lead", "may_spawn": ["worker"]}
    worker = {"harness": f"{__name__}:scripted_worker", "count": 0}
    return Team.model_validate({"roles": {"lead": lead, "worker": worker}, "topology": {"limits": {"max_depth": 1}}})


async def _history(root: Path) -> None:
    async with Session.start(team(), name="s", root=root, cwd=root) as owner:
        await in_state(owner, "lead", "idle")
        await owner.send("@lead", "fix the parser, with a worker")
        await until(lambda: of_type(owner, "turn.ended"), owner, lambda ended: len(ended) == 2)
        await in_state(owner, "lead", "idle")


@pytest.fixture
def history(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PLATOON_HARNESS_HOME", str(tmp_path))
    asyncio.run(_history(tmp_path))


@pytest.mark.parametrize("size", SIZES)
def test_the_workspace_s_layout_at_each_size(snap_compare, history, size):
    async def ready(pilot) -> None:
        await drawn(pilot, lambda text: "kestrel" in text and "Done" in text)

    assert snap_compare(TerminalUI("s"), terminal_size=SIZES[size], run_before=ready)


WHEN = 1_700_000_000
"""When every commit of the review's history is made, so that each is the same commit in every run."""


def worked(cwd: Path) -> None:
    commit(cwd, "parser.py", "def parse(text):\n    return text.split()\n", "Fix the parser", when=WHEN)
    (cwd / "notes.txt").write_text("unfinished\n")
    (cwd / "README").write_text("hello, edited\n")


async def _reviewed(root: Path, repo: Path) -> None:
    team = Team.model_validate({"roles": {"lead": {"harness": working(worked), "workspace": "worktree"}}})
    async with Session.start(team, name="s", root=root, cwd=repo) as owner:
        await in_state(owner, "lead", "idle")
        await owner.send("@lead", "fix the parser")

        async def probes() -> list:
            return [event for event in await of_type(owner, "effect.finished") if event.data["kind"] == "probe"]

        await until(probes, owner)


@pytest.fixture
def reviewed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PLATOON_HARNESS_HOME", str(tmp_path / "home"))
    repo = repository(tmp_path / "repo", monkeypatch, when=WHEN)
    asyncio.run(_reviewed(tmp_path / "home", repo))


def test_review_lists_what_changed(snap_compare, reviewed):
    async def opened(pilot) -> None:
        await drawn(pilot, lambda text: "1 commit, 2 paths uncommitted" in text)
        await pilot.press("alt+d")
        await drawn(pilot, lambda text: "What changed" in text and "notes.txt" in text)

    assert snap_compare(TerminalUI("s"), terminal_size=(120, 32), run_before=opened)
