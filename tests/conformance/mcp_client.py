"""The official MCP client against a running tool server. Run by the contract test, in an environment of its own."""

import asyncio
import json
import sys
from typing import Any

import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client


def text_of(result: Any) -> str:
    return result.content[0].text


async def exercise(url: str, token: str, mode: str) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {token}"}
    async with (
        httpx2.AsyncClient(headers=headers) as http,
        Client(streamable_http_client(url, http_client=http), mode=mode) as client,
    ):
        await client.send_ping()
        tools = (await client.list_tools()).tools
        added = await client.call_tool("task_add", {"queue": "tasks", "gist": f"from {mode}"})
        spoof = await client.call_tool("task_add", {"queue": "tasks", "gist": "x", "caller": "root"})
        listed = await client.call_tool("task_list", {"queue": "tasks"})
        return {
            "protocol": client.protocol_version,
            "server": client.server_info.name,
            "tools": {tool.name: tool.annotations.read_only_hint for tool in tools},
            "closed": all(tool.input_schema["additionalProperties"] is False for tool in tools),
            "added": json.loads(text_of(added)),
            "spoof": {"isError": spoof.is_error, "text": text_of(spoof)},
            "listed": json.loads(text_of(listed)),
            "descriptions": {tool.name: tool.description for tool in tools},
        }


async def main(url: str, token: str, *modes: str) -> None:
    print(json.dumps({mode: await exercise(url, token, mode) for mode in modes}))


if __name__ == "__main__":
    asyncio.run(main(*sys.argv[1:]))
