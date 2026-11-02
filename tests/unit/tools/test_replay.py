"""The spike's log of real clients, replayed: every request gets the answer those clients were seen to get."""

import json
from pathlib import Path

import pytest

from .support import exchange, request

FIXTURE = Path(__file__).parents[3] / "docs/research/fixtures/mcp-http-probe.jsonl"
RECORDS = [json.loads(line) for line in FIXTURE.read_text().splitlines()[1:]]
REQUESTS = [record for record in RECORDS if record.get("rpc") != "tools/call"]


def _message(record: dict) -> bytes:
    if record["src"] == "selftest" and "rpc" not in record:
        return b"[]" if record.get("result_error") else b"{}"
    if "rpc" not in record:
        return b""
    message = {"jsonrpc": "2.0", "method": record["rpc"]}
    if "id" in record:
        message["id"] = record["id"]
    if "protocolVersion" in record:
        message["params"] = {"protocolVersion": record["protocolVersion"], "clientInfo": record["clientInfo"]}
    return json.dumps(message).encode()


def _headers(record: dict) -> dict[str, str]:
    kept = {"mcp-protocol-version", "accept", "origin", "user-agent"}
    return {name.replace("-", "_"): value for name, value in record["headers"].items() if name in kept}


@pytest.mark.parametrize("record", REQUESTS, ids=lambda record: f"{record['src']}-{record.get('rpc', record['verb'])}")
async def test_a_real_client_gets_what_the_spike_saw(server, lead, record):
    token = lead[1].token if record["auth"] == "ok" else "wrong"
    data = request(server.url, _message(record), method=record["verb"], token=token, **_headers(record))

    reply = await exchange(server.url, data)

    assert reply.status == record["status"]
    if "result_error" in record:
        assert reply.json()["error"]["code"] == record["result_error"]
    if record.get("rpc") == "initialize":
        assert reply.json()["result"]["protocolVersion"] == record["protocolVersion"]


@pytest.mark.parametrize(
    "record", [r for r in RECORDS if r.get("rpc") == "tools/call" and r["src"] in ("claude", "codex")]
)
async def test_a_real_client_sends_an_anchor_this_server_reads(kernel, lead, record):
    meta = {name.replace("/", "__"): value for name, value in record["meta"].items() if isinstance(value, str)}

    await lead[1].call("task_add", {"queue": "tasks", "gist": "from a real client's meta"}, **meta)

    assert list(kernel.read(kernel.runtime, after=0, limit=4096).events)[-1].native
