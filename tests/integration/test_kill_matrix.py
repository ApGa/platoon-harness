"""SIGKILL at each step of a spawn and a handover, then a resume: nothing wedges, and nothing is lost in silence."""

import asyncio
import os
import signal
import subprocess
import sys
from pathlib import Path

import pytest

from platoon_harness import Session, Team
from platoon_harness.kernel import is_held
from platoon_harness.runtime.opening import prepare
from platoon_harness.session import _pauses

from ..unit.runtime.support import journal, rebuilt_equals_live, until
from .scripts import wire

pytestmark = [pytest.mark.slow, pytest.mark.timeout(90)]

KILLER = str(Path(__file__).with_name("kill_at.py"))
ROOT = str(Path(__file__).parents[2])

SPAWN = {
    "effect.start:admit": (2, "before", "after"),
    "principal.issue": (3, "after"),
    "effect.finish:admit": (2, "before", "after"),
    "effect.start:workspace": (2, "after"),
    "effect.finish:workspace": (2, "before"),
    "effect.start:launch": (2, "before", "after"),
    "record": (2, "after"),
    "go": (2, "before"),
    "agent.start": (2, "before", "after"),
    "effect.finish:launch": (2, "before", "after"),
    "agent.report:turn.started": (1, "before", "after"),
    "agent.report:item": (1, "after"),
    "agent.report:turn.ended": (1, "before", "after"),
}
HANDOVER = {
    "delivery.offer": (1, "before", "after"),
    "effect.start:deliver": (1, "before", "after"),
    "agent.report:input.delivered": (1, "before", "after"),
    "effect.finish:deliver": (1, "before", "after"),
    "agent.report:turn.started": (1, "before", "after"),
    "agent.report:turn.ended": (1, "before", "after"),
}


def points(table: dict[str, tuple]) -> list[tuple[str, str, int]]:
    return [(point, when, nth) for point, (nth, *whens) in table.items() for when in whens]


def team() -> Team:
    says = wire("saying")
    return Team.model_validate({"roles": {"bob": {"harness": says}, "ada": {"harness": says, "count": 0}}})


def killable(folder: Path, point: str, when: str, nth: int) -> subprocess.Popen[bytes]:
    return subprocess.Popen(
        [sys.executable, KILLER, str(folder), point, when, str(nth)],
        start_new_session=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env={**os.environ, "PYTHONPATH": ROOT},
    )


async def died(process: subprocess.Popen[bytes]) -> None:
    """Wait for a runtime that is meant to kill itself. Its exit is the only thing to wait on."""
    async with asyncio.timeout(30):
        await asyncio.to_thread(process.wait)


async def attached(folder: Path, root: Path) -> Session:
    """A guest on a runtime that is coming up, which may die first."""
    async for _ in _pauses(30.0):
        if (folder / "runtime.json").exists() and is_held(folder):
            return await Session.attach(folder.name, root=root)
    raise AssertionError("no runtime came up")


async def resumed_and_settled(folder: Path, root: Path):
    async with Session.resume(folder.name, root=root) as owner:
        ending = await owner.settled(timeout="20s")
        events = await journal(owner)
    assert ending.reason != "timed_out", ending
    assert not list(folder.rglob("proc.json"))
    await rebuilt_equals_live(folder)
    return ending, events


@pytest.mark.parametrize(("point", "when", "nth"), points(SPAWN))
async def test_a_kill_during_a_spawn_leaves_a_goal_run_or_a_named_failure(tmp_path, point, when, nth):
    folder = await asyncio.to_thread(prepare, team(), name="s", root=tmp_path)
    runtime = killable(folder, point, when, nth)
    try:
        guest = await attached(folder, tmp_path)
        await guest.submit("agent.spawn", name="ada", child_role="ada", goal="the important thing")
        await died(runtime)
        await guest.leave()
    finally:
        runtime.kill()
        runtime.wait()

    ending, events = await resumed_and_settled(folder, tmp_path)

    ada = next((row for row in ending.agents if row["agent"] == "ada"), None)
    if ada is not None and ada["status"] not in ("failed", "lost"):
        assert any(event.type == "turn.started" and event.agent == "ada" for event in events), ending


@pytest.mark.parametrize(("point", "when", "nth"), points(HANDOVER))
async def test_a_kill_during_a_handover_leaves_it_delivered_or_a_named_failure(tmp_path, point, when, nth):
    folder = await asyncio.to_thread(prepare, team(), name="s", root=tmp_path)
    runtime = killable(folder, point, when, nth)
    try:
        guest = await attached(folder, tmp_path)
        await until(lambda: guest.status("@bob"), guest, lambda status: status["state"] == "idle")
        await guest.submit("message.send", to="@bob", gist="hello")
        await died(runtime)
        await guest.leave()
    finally:
        runtime.kill()
        runtime.wait()

    ending, events = await resumed_and_settled(folder, tmp_path)

    lost = any(row["status"] in ("failed", "lost") for row in ending.agents)
    assert lost or any(event.type == "context.delivered" for event in events), ending


async def test_a_killed_runtime_takes_nothing_else_down(tmp_path):
    folder = await asyncio.to_thread(prepare, team(), name="s", root=tmp_path)
    runtime = killable(folder, "agent.report:turn.started", "after", 1)
    try:
        guest = await attached(folder, tmp_path)
        await guest.submit("message.send", to="@bob", gist="hello")
        await died(runtime)
        await guest.leave()
    finally:
        runtime.kill()
        runtime.wait()

    assert runtime.returncode == -signal.SIGKILL
    assert not is_held(folder)
