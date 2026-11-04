"""The stdio shim as a harness runs it: a real process, a pipe each way, and a real server behind it."""

import asyncio
import json
import os
import shutil
import sys
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import pytest

from platoon_harness.tools import SHIM
from platoon_harness.tools.shim import TOKEN_VARIABLE, URL_VARIABLE

from ..primitives.support import of_type, send, start_turn
from .support import SECONDS, Client, check_stands_alone, finished, slept_until, text_of

OTHER_PYTHON = shutil.which("python3", path=os.defpath)


class Pipe:
    """A harness's end of the shim."""

    def __init__(self, process: asyncio.subprocess.Process) -> None:
        self.process = process

    def send(self, message: Any) -> None:
        assert self.process.stdin is not None
        self.process.stdin.write(json.dumps(message).encode() + b"\n")

    async def line(self) -> dict[str, Any]:
        assert self.process.stdout is not None
        async with asyncio.timeout(SECONDS):
            return json.loads(await self.process.stdout.readline())

    async def request(self, method: str, params: dict[str, Any] | None = None, *, id: int = 1) -> dict[str, Any]:
        self.send({"jsonrpc": "2.0", "id": id, "method": method, "params": params or {}})
        return await self.line()


@asynccontextmanager
async def shim(client: Client, *, script: Path = SHIM, python: str = sys.executable) -> AsyncIterator[Pipe]:
    env = {URL_VARIABLE: client.url, TOKEN_VARIABLE: client.token}
    process = await asyncio.create_subprocess_exec(
        python, str(script), env=env, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE
    )
    try:
        yield Pipe(process)
    finally:
        await finished(process)


def test_the_shim_stands_alone():
    check_stands_alone(SHIM)


async def test_it_forwards_what_a_client_says_first(lead):
    async with shim(lead[1]) as pipe:
        hello = await pipe.request("initialize", {"protocolVersion": "2025-06-18"})
        pipe.send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        tools = await pipe.request("tools/list", id=2)

    assert hello["result"]["protocolVersion"] == "2025-06-18"
    assert "task_add" in {tool["name"] for tool in tools["result"]["tools"]}


async def test_identity_is_the_bearer_from_its_environment(kernel, lead):
    params = {"name": "task_add", "arguments": {"queue": "tasks", "gist": "from a pipe"}}

    async with shim(lead[1]) as pipe:
        await pipe.request("tools/call", params)

    assert of_type(kernel, "task.added")[-1].actor == "agent:lead"


async def test_a_notification_gets_no_line(lead):
    async with shim(lead[1]) as pipe:
        pipe.send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        assert (await pipe.request("ping"))["id"] == 1


async def test_blank_lines_are_ignored(lead):
    async with shim(lead[1]) as pipe:
        assert pipe.process.stdin is not None
        pipe.process.stdin.write(b"\n\n")
        assert (await pipe.request("ping"))["result"] == {}


async def test_a_line_that_is_not_json_is_answered_by_the_server(lead):
    async with shim(lead[1]) as pipe:
        assert pipe.process.stdin is not None
        pipe.process.stdin.write(b"not json\n")
        assert (await pipe.line())["error"]["code"] == -32700


async def test_a_refusal_comes_back_as_a_tool_result(lead):
    async with shim(lead[1]) as pipe:
        answer = await pipe.request("tools/call", {"name": "peers", "arguments": {"caller": "root"}})

    assert answer["result"]["isError"] and "invalid" in text_of(answer["result"])


async def test_a_held_wait_does_not_stop_the_next_call(kernel, lead, worker, clock):
    await start_turn(kernel, "w1")
    params = {"name": "wait", "arguments": {"from": ["lead"], "hold": 20.0}}

    async with shim(worker[1]) as pipe:
        pipe.send({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": params})
        await slept_until(clock, 1020.0)
        assert (await pipe.request("ping", id=2))["id"] == 2
        await send(kernel, lead[0], "@w1", "go on")
        held = await pipe.line()

    assert held["id"] == 1 and json.loads(text_of(held["result"]))["state"] == "released"


async def test_a_second_identical_call_is_a_second_call(kernel, lead, worker):
    await start_turn(kernel, "w1")
    params = {"name": "message_send", "arguments": {"to": "@lead", "gist": "same words"}}

    async with shim(worker[1]) as pipe:
        await pipe.request("tools/call", params, id=1)
        await pipe.request("tools/call", params, id=2)

    assert len(of_type(kernel, "message.sent")) == 2


async def test_its_own_id_cannot_pass_for_a_harnesss(kernel, lead, worker):
    params = {"name": "message_send", "arguments": {"to": "@lead", "gist": "words"}}

    async with shim(worker[1]) as pipe:
        await pipe.request("tools/call", params)

    assert [*of_type(kernel, "message.sent")[-1].native] == ["platoon-harness/callId"]


async def test_an_id_the_harness_sent_goes_through(kernel, lead, worker):
    await start_turn(kernel, "w1")
    params = {
        "name": "message_send",
        "arguments": {"to": "@lead", "gist": "same words"},
        "_meta": {"claudecode/toolUseId": "toolu_1"},
    }

    async with shim(worker[1]) as pipe:
        await pipe.request("tools/call", params, id=1)
        await pipe.request("tools/call", params, id=2)

    sent = of_type(kernel, "message.sent")
    assert [event.native for event in sent] == [{"claudecode/toolUseId": "toolu_1"}]


async def test_an_id_a_harness_put_among_the_arguments_goes_where_mcp_keeps_it(kernel, lead, worker):
    """Pi's MCP client sends no `_meta`, so our extension puts pi's tool call id among the arguments, and the server,
    which refuses an argument nobody declared, sees it where MCP keeps it."""
    await start_turn(kernel, "w1")
    arguments = {"to": "@lead", "gist": "words", "_meta": {"pi/toolCallId": "call_1"}}
    params = {"name": "message_send", "arguments": arguments, "_meta": {"progressToken": 7}}

    async with shim(worker[1]) as pipe:
        answer = await pipe.request("tools/call", params)

    assert answer["result"]["isError"] is False
    assert of_type(kernel, "message.sent")[-1].native == {"pi/toolCallId": "call_1"}


async def test_a_surface_in_the_url_goes_through(lead):
    client = Client(f"{lead[1].url}?surface=mcp__coord", lead[1].token)

    async with shim(client) as pipe:
        tools = (await pipe.request("tools/list"))["result"]["tools"]

    assert any("`mcp__coord__" in tool["description"] for tool in tools)


@pytest.mark.parametrize(
    "error", [lambda client: Client("http://127.0.0.1:1/mcp", "x"), lambda client: Client(client.url, "x")]
)
async def test_a_request_that_cannot_be_answered_is_told_so(lead, error: Callable[[Client], Client]):
    async with shim(error(lead[1])) as pipe:
        answer = await pipe.request("tools/list", id=7)

    assert (answer["id"], answer["error"]["code"]) == (7, -32603)


async def test_a_bad_token_leaves_a_notification_unanswered(lead):
    async with shim(Client(lead[1].url, "x")) as pipe:
        pipe.send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        answer = await pipe.request("ping", id=9)

    assert answer["id"] == 9


async def test_spawned_with_no_token_it_says_so():
    process = await asyncio.create_subprocess_exec(
        sys.executable, str(SHIM), env={}, stdin=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE
    )
    _, err = await finished(process)

    assert process.returncode == 78
    assert b"no token" in err


@pytest.mark.skipif(OTHER_PYTHON is None, reason="this host has no system python3")
async def test_it_runs_on_the_system_python(lead):
    assert OTHER_PYTHON is not None

    async with shim(lead[1], python=OTHER_PYTHON) as pipe:
        assert (await pipe.request("ping"))["result"] == {}
