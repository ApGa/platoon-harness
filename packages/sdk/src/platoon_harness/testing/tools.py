"""FakeTools: a small tools-only MCP server, for a test that needs a binding and no session behind it."""

import asyncio
import json
from pathlib import Path
from typing import Any, Self

from platoon_harness.config import Secret
from platoon_harness.drivers import ToolBinding

from .loopback import Loopback, Message, answer

TOOL = "conformance_ping"
NAMESPACE = "conformance"

_TOKEN = "conformance-token"
_DESCRIPTION = {
    "name": TOOL,
    "description": "Answer with pong. Conformance uses this tool to see whether a model was shown it.",
    "inputSchema": {"type": "object", "properties": {"note": {"type": "string"}}, "additionalProperties": False},
}


class FakeTools:
    """One tool over Streamable HTTP with a bearer, shaped as the tool plane serves. `calls` logs the arguments of each
    `tools/call`, and `binding` is how an agent reaches it."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self._server = Loopback(self._handle)

    async def __aenter__(self) -> Self:
        await self._server.__aenter__()
        return self

    async def __aexit__(self, *_: object) -> None:
        await self._server.__aexit__()

    def binding(self, bin: Path) -> ToolBinding:
        return ToolBinding(url=f"{self._server.url}/mcp", token=Secret(_TOKEN), namespace=NAMESPACE, bin=bin)

    async def _handle(self, message: Message, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> bool:
        if message.method != "POST":
            writer.write(answer(405))
        elif message.header("authorization") != f"Bearer {_TOKEN}":
            writer.write(answer(401))
        else:
            frame = json.loads(message.body)
            writer.write(self._reply(frame))
        return True

    def _reply(self, frame: dict[str, Any]) -> bytes:
        method, params = frame.get("method"), frame.get("params") or {}
        if "id" not in frame:
            return answer(202)
        match method:
            case "initialize":
                asked = params.get("protocolVersion", "2025-11-25")
                result = {
                    "protocolVersion": asked,
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "fake-tools", "version": "1"},
                }
            case "tools/list":
                result = {"tools": [_DESCRIPTION]}
            case "tools/call":
                self.calls.append(params)
                result = {"content": [{"type": "text", "text": "pong"}], "isError": params.get("name") != TOOL}
            case _:
                error = {"code": -32601, "message": f"no method {method}"}
                return answer(200, json.dumps({"jsonrpc": "2.0", "id": frame["id"], "error": error}).encode())
        return answer(200, json.dumps({"jsonrpc": "2.0", "id": frame["id"], "result": result}).encode())
