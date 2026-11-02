"""Fixtures: an open session on a manual clock, compared with a full rebuild when each test ends."""

from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from platoon_harness.kernel import Kernel, ManualClock, Principal
from platoon_harness.primitives import PRIMITIVES

from ..kernel.support import enroll, grant, result_of
from .support import ROLES, logical_dump


@pytest.fixture
def clock() -> ManualClock:
    return ManualClock(1000.0)


@pytest.fixture
def folder(tmp_path: Path) -> Path:
    return tmp_path / "session"


@pytest.fixture
def limits() -> dict[str, int]:
    return {}


@pytest.fixture
async def kernel(folder: Path, clock: ManualClock, limits: dict[str, int]) -> AsyncIterator[Kernel]:
    opened = Kernel.open(folder, clock=clock, extensions=PRIMITIVES)
    result_of(await opened.submit(opened.runtime, "session.open", {"roles": ROLES, "limits": limits}))
    await grant(opened, "agent")
    await grant(opened, "human")
    yield opened
    if not opened.closed:
        before = logical_dump(folder)
        await opened.rebuild_all()
        assert logical_dump(folder) == before
        opened.close()


@pytest.fixture
async def ada(kernel: Kernel) -> Principal:
    human = Principal(id="human:ada")
    await enroll(kernel, human)
    return human
