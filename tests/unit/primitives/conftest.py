"""Fixtures: an open session on a manual clock, compared with a full rebuild when each test ends."""

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

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
def repo() -> dict[str, Any] | None:
    """The repository the session opens on, all but its tips, or None for a session that observes none."""
    return None


@pytest.fixture
def checks() -> list[str] | None:
    """The command a runtime test of a commit runs, or None for a team that names none."""
    return None


@pytest.fixture
async def kernel(
    folder: Path, clock: ManualClock, limits: dict[str, int], repo: dict[str, Any] | None, checks: list[str] | None
) -> AsyncIterator[Kernel]:
    opened = Kernel.open(folder, clock=clock, extensions=PRIMITIVES)
    settings: dict[str, Any] = {"roles": ROLES, "limits": limits, "test": checks}
    if repo is not None:
        settings["repo"] = {**repo, "tips": f"sha256:{await opened.put_body(b'')}"}
    result_of(await opened.submit(opened.runtime, "session.open", settings))
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
