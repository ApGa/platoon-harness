#!/usr/bin/env python3
"""A stdio MCP server for a harness without HTTP: each line goes to the runtime's tool server, with the bearer from the
environment, and each answer comes back as a line.

This file runs on any python3 and imports only the standard library. It keeps no state: the server decides everything.
"""

from __future__ import annotations

import http.client
import json
import os
import sys
import threading
import uuid
from typing import Any
from urllib.parse import urlsplit

URL_VARIABLE = "PLATOON_HARNESS_URL"
TOKEN_VARIABLE = "PLATOON_HARNESS_TOKEN"

_ANCHORS = ("claudecode/toolUseId", "callId", "pi/toolCallId", "platoon-harness/callId")
_UNCONFIGURED = 78

_stdout = threading.Lock()


def _write(reply: bytes) -> None:
    with _stdout:
        sys.stdout.buffer.write(reply + b"\n")
        sys.stdout.buffer.flush()


def _anchored(message: Any) -> Any:
    """Give a tool call the id its harness gave it, or one of its own. A harness whose MCP client keeps `_meta` to
    itself puts it among the call's arguments, and it moves to where MCP keeps it, beside what the client put there.
    Nothing here retries, and each line is one call, so a second identical call in a turn must not be taken for a
    retry of the first."""
    params = message.get("params") if isinstance(message, dict) and message.get("method") == "tools/call" else None
    if isinstance(params, dict):
        meta = params.setdefault("_meta", {})
        arguments = params.get("arguments")
        if isinstance(meta, dict) and isinstance(arguments, dict) and isinstance(arguments.get("_meta"), dict):
            for name, value in arguments.pop("_meta").items():
                meta.setdefault(name, value)
        if isinstance(meta, dict) and not any(anchor in meta for anchor in _ANCHORS):
            meta["platoon-harness/callId"] = uuid.uuid4().hex
    return message


def _post(url: str, token: str, line: bytes) -> tuple[int, bytes]:
    parts = urlsplit(url)
    target = f"{parts.path}?{parts.query}" if parts.query else parts.path
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    connection = http.client.HTTPConnection(parts.netloc)
    try:
        connection.request("POST", target, line, headers)
        response = connection.getresponse()
        return response.status, response.read()
    finally:
        connection.close()


def _relay(url: str, token: str, line: bytes) -> None:
    """Forward one line. A request that cannot get an answer is told so, because its harness is waiting for one."""
    try:
        message = json.loads(line)
    except ValueError:
        message = None
    outgoing = line if message is None else json.dumps(_anchored(message)).encode()
    try:
        status, body = _post(url, token, outgoing)
        problem = None if status in (200, 202) else f"the tool server answered HTTP {status}"
    except (OSError, http.client.HTTPException) as error:
        body, problem = b"", f"the tool server cannot be reached: {error}"
    if problem is None:
        if body:
            _write(body)
    elif isinstance(message, dict) and "id" in message:
        failure = {"code": -32603, "message": problem}
        _write(json.dumps({"jsonrpc": "2.0", "id": message["id"], "error": failure}).encode())
    else:
        print(f"shim: {problem}", file=sys.stderr, flush=True)


def main() -> None:
    url, token = os.environ.get(URL_VARIABLE), os.environ.get(TOKEN_VARIABLE)
    if not url or not token:
        print(f"shim: no token: {URL_VARIABLE} and {TOKEN_VARIABLE} are set by the runtime", file=sys.stderr)
        raise SystemExit(_UNCONFIGURED)
    for line in sys.stdin.buffer:
        if line.strip():
            threading.Thread(target=_relay, args=(url, token, line.strip()), daemon=True).start()


if __name__ == "__main__":
    main()
