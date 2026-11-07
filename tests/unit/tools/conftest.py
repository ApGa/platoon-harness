"""A compiled team on a real kernel on a manual clock, and a real server on port 0."""

from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from platoon_harness.kernel import Kernel, ManualClock, Principal
from platoon_harness.tools import ToolServer

from .support import Client, enrolled, opened


@pytest.fixture
def clock() -> ManualClock:
    return ManualClock(1000.0)


@pytest.fixture
async def kernel(tmp_path: Path, clock: ManualClock) -> AsyncIterator[Kernel]:
    made = await opened(tmp_path / "session", clock)
    yield made
    made.close()


@pytest.fixture
async def server(kernel: Kernel) -> AsyncIterator[ToolServer]:
    started = ToolServer(kernel)
    await started.start()
    yield started
    await started.stop()


@pytest.fixture
async def lead(kernel: Kernel, server: ToolServer) -> tuple[Principal, Client]:
    return await enrolled(kernel, server, "lead", role="lead")


@pytest.fixture
async def worker(kernel: Kernel, server: ToolServer, lead: tuple[Principal, Client]) -> tuple[Principal, Client]:
    return await enrolled(kernel, server, "w1", by=lead[0])
