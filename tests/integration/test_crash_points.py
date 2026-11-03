"""One writer means a journal lists its own crash points: every command boundary is a legal crash state, so cut one at
each and resume. A cut is legal for the journal only, since blobs and agent folders stay from a later time."""

import shutil
from pathlib import Path
from typing import Any

import pytest

from platoon_harness import Session
from platoon_harness.primitives import CUT_OFF

from ..unit.runtime.support import boundaries, cut, harness, of_type, rebuilt_equals_live, until
from .scripts import FIX_THE_TEST, WORK, Lead, Templated, manager_worker

pytestmark = [pytest.mark.slow, pytest.mark.timeout(300)]


def idling[Driver: Templated](kind: type[Driver]) -> type[Driver]:
    """A harness that runs its script fresh and once resumed only idles, so that no script can raise on a world cut
    short under it."""

    class Idling(kind):
        async def _walk(self, steps: Any) -> str:
            return "stopped" if self.back else await super()._walk(steps)

    return Idling


def team() -> Any:
    return manager_worker(
        harness(lambda: idling(Lead)([FIX_THE_TEST])),
        harness(lambda: idling(Templated)([WORK])),
    )


async def recorded(root: Path) -> Path:
    async with Session.start(team(), name="s", root=root) as session:
        await session.send("@lead", "Fix the flaky test")
        ending = await session.settled(timeout="30s")
    assert ending.reason == "settled"
    return session.folder


async def resumed_from(folder: Path, seq: int, root: Path) -> None:
    (root / "sessions").mkdir(parents=True)
    copy = shutil.copytree(folder, root / "sessions" / "s")
    cut(copy, seq)

    async with Session.resume("s", root=root) as owner:
        await until(owner.status, owner, lambda status: status["settled"])
        kernel = owner._runtime.kernel
        assert kernel.query(kernel.runtime, "effect.list", {"state": "started"}).result == [], seq
        records = kernel.query(kernel.runtime, "agent.records", {}).result
        owed = {record["name"] for record in records if record["stopped"] in CUT_OFF and record["status"] is None}
        sent = await of_type(owner, "message.sent")
        assert owed <= {event.stream.removeprefix("inbox/") for event in sent if "cut off" in event.gist}, seq

    await rebuilt_equals_live(copy)
    shutil.rmtree(root)


async def test_a_crash_at_any_command_boundary_resumes_and_leaves_nothing_behind(tmp_path):
    folder = await recorded(tmp_path / "whole")

    for seq in boundaries(folder):
        await resumed_from(folder, seq, tmp_path / f"cut-{seq}")
