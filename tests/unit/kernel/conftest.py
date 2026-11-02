"""Fixtures: a kernel on a manual clock, and a gate to hold its writer."""

from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from platoon_harness.kernel import Kernel, ManualClock

from .support import Gate, notes


@pytest.fixture
def clock() -> ManualClock:
    return ManualClock(1000.0)


@pytest.fixture
def folder(tmp_path: Path) -> Path:
    return tmp_path / "session"


@pytest.fixture
def gate() -> Gate:
    return Gate()


@pytest.fixture
async def kernel(folder: Path, clock: ManualClock, gate: Gate) -> AsyncIterator[Kernel]:
    opened = Kernel.open(folder, clock=clock, extensions=[notes, gate.extension()])
    yield opened
    gate.release.set()
    opened.close()
