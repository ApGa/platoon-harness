"""Tool-plane helpers: a compiled team on a real kernel, and a harness's side of a real socket."""

import ast
import asyncio
import json
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any, NamedTuple
from urllib.parse import urlsplit

from platoon_harness.kernel import Kernel, ManualClock, Principal, hash_token
from platoon_harness.team import Team
from platoon_harness.tools import ToolServer

from ..primitives.support import result_of, spawn

SECONDS = 10.0

TEAM = """
[roles.lead]
harness = "claude"
may_spawn = ["worker", "narrow", "steered"]

[roles.worker]
harness = "codex"

[roles.narrow]
harness = "codex"
tools = ["message.*", "wait", "blob.get"]

[roles.steered]
harness = "codex"
delivery = "steer"

[topology]
edges = { narrow = ["parent"], steered = ["parent"] }

[topology.manager-worker]
manager = "lead"
workers = "worker"
"""

BUILT = Team.loads(TEAM)


class Reply(NamedTuple):
    status: int
    head: str
    body: bytes

    def json(self) -> Any:
        return json.loads(self.body)


async def connect(url: str) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
    parts = urlsplit(url)
    return await asyncio.open_connection(parts.hostname, parts.port)


async def drained(server: ToolServer) -> None:
    """Wait for the server to let go of every connection."""
    async with asyncio.timeout(SECONDS):
        await asyncio.gather(*server._serving, return_exceptions=True)


async def slept_until(clock: ManualClock, due: float) -> None:
    """Wait for the server to sleep until `due`, which it may never do if something is wrong."""
    async with asyncio.timeout(SECONDS):
        await clock.slept_until(due)


async def exchange(url: str, data: bytes) -> Reply:
    """Write bytes to the server and read until it closes, which it must do on its own."""
    async with asyncio.timeout(SECONDS):
        reader, writer = await connect(url)
        try:
            writer.write(data)
            await writer.drain()
            answer = await reader.read()
        finally:
            writer.close()
    head, _, body = answer.partition(b"\r\n\r\n")
    status = int(head.split(b" ")[1]) if head else 0
    return Reply(status, head.decode("latin-1"), body)


def request(url: str, body: bytes = b"", *, method: str = "POST", token: str | None = None, **headers: str) -> bytes:
    """One HTTP request as bytes. A header given with underscores is sent with dashes."""
    parts = urlsplit(url)
    target = f"{parts.path}?{parts.query}" if parts.query else parts.path
    fields = {"Host": parts.netloc, "Content-Type": "application/json", "Content-Length": str(len(body))}
    if token is not None:
        fields["Authorization"] = f"Bearer {token}"
    lines = [f"{method} {target} HTTP/1.1", *(f"{name}: {value}" for name, value in fields.items())]
    lines += [f"{name.replace('_', '-')}: {value}" for name, value in headers.items()]
    return "\r\n".join((*lines, "", "")).encode() + body


def tool_call(tool: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """A `tools/call` message, for a test that holds the socket itself."""
    return {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": tool, "arguments": arguments},
    }


class Client:
    """What a harness's MCP client does: one POST per message, with the agent's bearer."""

    def __init__(self, url: str, token: str) -> None:
        self.url = url
        self.token = token
        self.ids = 0

    async def post(self, message: Any, **headers: str) -> Reply:
        body = json.dumps(message).encode()
        return await exchange(self.url, request(self.url, body, token=self.token, **headers))

    async def rpc(self, method: str, params: Mapping[str, Any] | None = None) -> dict[str, Any]:
        self.ids += 1
        message = {"jsonrpc": "2.0", "id": self.ids, "method": method, "params": params or {}}
        reply = await self.post(message)
        assert reply.status == 200, reply
        return reply.json()

    async def list_tools(self) -> list[dict[str, Any]]:
        return (await self.rpc("tools/list"))["result"]["tools"]

    async def call(self, tool: str, arguments: Mapping[str, Any] | None = None, **meta: str) -> dict[str, Any]:
        params = {
            "name": tool,
            "arguments": arguments or {},
            "_meta": {k.replace("__", "/"): v for k, v in meta.items()},
        }
        return (await self.rpc("tools/call", params))["result"]


def text_of(result: dict[str, Any]) -> str:
    return result["content"][0]["text"]


def value_of(result: dict[str, Any]) -> Any:
    assert not result["isError"], result
    return json.loads(text_of(result))


async def enrolled(
    kernel: Kernel, server: ToolServer, name: str, *, role: str = "worker", by: Principal | None = None, **ready: Any
) -> tuple[Principal, Client]:
    """Spawn an agent through to started, issue its token as the host does, and connect a client."""
    agent = await spawn(kernel, name, role=role, by=by, ready=ready)
    token = f"token-of-{name}"
    args = {"id": agent.id, "token_hash": hash_token(token)}
    result_of(await kernel.submit(kernel.runtime, "principal.issue", args))
    return kernel.authenticate(token), Client(server.url, token)


async def finished(process: asyncio.subprocess.Process, seconds: float = SECONDS) -> tuple[bytes, bytes]:
    """A process's output once it ends, within a bound, leaving nothing behind."""
    try:
        async with asyncio.timeout(seconds):
            return await process.communicate()
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()


def check_stands_alone(path: Path) -> None:
    """Hold a file to running by path on any python3, with nothing but the standard library."""
    source = path.read_text()
    tree = ast.parse(source, feature_version=(3, 8))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules |= {alias.name.partition(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0, f"{path.name} imports relatively"
            modules.add((node.module or "").partition(".")[0])
    assert source.startswith("#!/usr/bin/env python3\n")
    assert modules <= set(sys.stdlib_module_names)
