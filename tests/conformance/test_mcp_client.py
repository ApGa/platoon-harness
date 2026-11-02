"""The contract with the official MCP client, which must stay out of the workspace lock: `mcp>=2.3` cannot be satisfied
beside `platoon[ors]`, so it runs in an environment of its own."""

import asyncio
import json
import shutil
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest

from platoon_harness.kernel import Kernel
from platoon_harness.primitives import PRIMITIVES
from platoon_harness.tools import ToolServer
from platoon_harness.topology.compile import compile, scopes

from ..unit.primitives.support import channel, of_type, result_of
from ..unit.tools.support import BUILT, enrolled, finished

pytestmark = pytest.mark.slow

CLIENT = Path(__file__).with_name("mcp_client.py")
BOUND_SECONDS = 180.0


@pytest.fixture
async def session(tmp_path: Path) -> AsyncIterator[tuple[Kernel, ToolServer]]:
    kernel = Kernel.open(tmp_path / "session", extensions=PRIMITIVES)
    roles = {name: {"tools": scopes(role), "delivery": role.delivery} for name, role in BUILT.roles.items()}
    result_of(await kernel.submit(kernel.runtime, "session.open", {"roles": roles}))
    for grant in compile(BUILT):
        result_of(await kernel.submit(kernel.runtime, "grant.add", grant.model_dump()))
    await channel(kernel, "tasks", kind="queue")
    server = ToolServer(kernel)
    await server.start()
    yield kernel, server
    await server.stop()
    kernel.close()


async def official_client(url: str, token: str, *modes: str) -> dict[str, Any]:
    uv = shutil.which("uv")
    assert uv is not None, "the contract runs through uv"
    command = (uv, "run", "--isolated", "--no-project", "--python", "3.12", "--with", "mcp>=2.3,<3", "python")
    process = await asyncio.create_subprocess_exec(
        *command,
        str(CLIENT),
        url,
        token,
        *modes,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out, err = await finished(process, BOUND_SECONDS)
    assert process.returncode == 0, err.decode()
    return json.loads(out)


async def test_the_official_client_works_in_each_era_it_speaks(session):
    kernel, server = session
    _, client = await enrolled(kernel, server, "lead", role="lead")

    reports = await official_client(server.url, client.token, "auto", "legacy")

    for mode, report in reports.items():
        assert report["protocol"] == "2025-11-25", mode
        assert report["server"] == "platoon-harness", mode
        assert report["closed"] is True, mode
        assert report["tools"]["peers"] is True and report["tools"]["task_add"] is False, mode
        assert report["spoof"]["isError"] is True, mode
        assert "caller" in report["spoof"]["text"], mode
    assert reports["legacy"]["listed"]["total"] == 2
    assert [event.actor for event in of_type(kernel, "task.added")] == ["agent:lead", "agent:lead"]
    assert [event.data["code"] for event in of_type(kernel, "op.refused")] == ["invalid", "invalid"]


async def test_the_official_client_keeps_a_surface_in_its_url(session):
    kernel, server = session
    _, client = await enrolled(kernel, server, "lead", role="lead")

    reports = await official_client(f"{server.url}?surface=mcp__coord", client.token, "legacy")

    assert "`mcp__coord__peers`" in reports["legacy"]["descriptions"]["message_send"]
