"""A compiled team on a real kernel on a manual clock, and a real server on port 0."""

from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from platoon_harness.kernel import Kernel, ManualClock, Principal
from platoon_harness.primitives import PRIMITIVES
from platoon_harness.tools import ToolServer
from platoon_harness.topology.compile import compile, scopes

from ..primitives.support import channel, result_of
from .support import BUILT, Client, enrolled


@pytest.fixture
def clock() -> ManualClock:
    return ManualClock(1000.0)


@pytest.fixture
async def kernel(tmp_path: Path, clock: ManualClock) -> AsyncIterator[Kernel]:
    opened = Kernel.open(tmp_path / "session", clock=clock, extensions=PRIMITIVES)
    roles = {
        name: {"harness": role.driver, "tools": scopes(role), "delivery": role.delivery}
        for name, role in BUILT.roles.items()
    }
    result_of(await opened.submit(opened.runtime, "session.open", {"roles": roles}))
    for grant in compile(BUILT):
        result_of(await opened.submit(opened.runtime, "grant.add", grant.model_dump()))
    await channel(opened, "tasks", kind="queue")
    await channel(opened, "notes", kind="board")
    yield opened
    opened.close()


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
