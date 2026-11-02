"""A scripted harness on the real tool plane: real MCP over a real socket, into a real kernel."""

import sys
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from platoon_harness.config import Secret
from platoon_harness.drivers import AgentSpec, Exited, Ready, ToolBinding, TurnEnded
from platoon_harness.drivers.wire import WireDriver
from platoon_harness.kernel import Kernel, ManualClock, hash_token
from platoon_harness.primitives import PRIMITIVES
from platoon_harness.testing import Call, Say, ScriptedDriver
from platoon_harness.tools import ToolServer

from ..unit.drivers.support import Heard
from ..unit.kernel.support import result_of

pytestmark = pytest.mark.timeout(30)

TOKEN = "bob-token"


@pytest.fixture
async def kernel(tmp_path: Path) -> AsyncIterator[Kernel]:
    opened = Kernel.open(tmp_path / "session", clock=ManualClock(1000.0), extensions=PRIMITIVES)
    roles = {"worker": {"harness": "scripted", "model": "m"}}
    result_of(await opened.submit(opened.runtime, "session.open", {"roles": roles}))
    result_of(await opened.submit(opened.runtime, "grant.add", {"who": "agent", "ops": "*", "on": "*"}))
    args = {"name": "bob", "child_role": "worker", "goal": "be bob"}
    result_of(await opened.submit(opened.runtime, "agent.spawn", args))
    issue = {"id": "agent:bob", "token_hash": hash_token(TOKEN)}
    result_of(await opened.submit(opened.runtime, "principal.issue", issue))
    yield opened
    opened.close()


@pytest.fixture
async def server(kernel: Kernel) -> AsyncIterator[ToolServer]:
    started = ToolServer(kernel)
    await started.start()
    yield started
    await started.stop()


def spec(tmp_path: Path, server: ToolServer) -> AgentSpec:
    binding = ToolBinding(url=server.url, token=Secret(TOKEN), namespace="ph", bin=tmp_path)
    return AgentSpec(agent="bob", role="worker", goal="be bob", cwd=tmp_path, folder=tmp_path / "agent", tools=binding)


async def test_a_scripted_call_reaches_a_real_op(tmp_path, kernel, server):
    driver, heard = (
        ScriptedDriver([[Call("message_send", {"to": "@bob", "gist": "note to self"}), Say("done")]]),
        Heard(),
    )

    await driver.start(spec(tmp_path, server), heard)
    await heard.until(TurnEnded)
    await driver.stop(1)

    assert driver.results[0].get("isError") is not True, driver.results[0]
    sent = [event for event in kernel.read(kernel.runtime, after=0, limit=4096).events if event.type == "message.sent"]
    assert (sent[0].actor, sent[0].gist) == ("agent:bob", "note to self")


async def test_tools_visible_is_what_the_server_listed_for_this_token(tmp_path, kernel, server):
    driver, heard = ScriptedDriver(), Heard()

    await driver.start(spec(tmp_path, server), heard)
    ready = await heard.until(Ready)
    await driver.stop(1)

    assert "message_send" in ready.tools_visible
    assert "agent_report" not in ready.tools_visible


async def test_a_wire_driver_reaches_the_tool_plane_with_a_token_from_its_environment(tmp_path, kernel, server):
    program = tmp_path / "program.py"
    program.write_text(
        "from platoon_harness.drivers.wire import serve\n"
        "from platoon_harness.testing import Call, ScriptedDriver\n"
        "serve(ScriptedDriver([[Call('message_send', {'to': '@bob', 'gist': 'through the wire'})]]))\n"
    )
    driver, heard = WireDriver([sys.executable, str(program)]), Heard()

    await driver.start(spec(tmp_path, server), heard)
    await heard.until(TurnEnded)
    await driver.stop(2)
    await heard.until(Exited)

    sent = [event for event in kernel.read(kernel.runtime, after=0, limit=4096).events if event.type == "message.sent"]
    assert sent[0].gist == "through the wire"
