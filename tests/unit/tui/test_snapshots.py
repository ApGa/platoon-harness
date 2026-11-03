"""The workspace's layout at each size the guide names, as snapshots, on a session's history so nothing moves."""

import asyncio
from pathlib import Path

import pytest

from platoon_harness import Session, Team
from platoon_harness.testing import Call, Say, ScriptedDriver
from platoon_harness_cli.tui.app import Harness

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

    assert snap_compare(Harness("s"), terminal_size=SIZES[size], run_before=ready)
