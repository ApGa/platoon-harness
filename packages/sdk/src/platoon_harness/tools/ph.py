#!/usr/bin/env python3
"""ph: an agent's coordination tools as a command, on its PATH only.

    ph --help                    what this agent may do
    ph task.claim --help         the arguments of one op
    ph task.claim --queue tasks  do it

Arguments are `--name value` or `--name=value`. Repeat a flag to build a list. A flag that takes true or false can stand
alone for true. Numbers and objects are JSON. The result is JSON on stdout. Messages that reach the agent go to stderr.

Exit codes:

    0   done
    1   refused: the refusal, and what to do next, is on stderr
    2   not something ph can send: usage is on stderr
    69  the runtime cannot be reached
    78  no url or token: ph works only inside an agent the runtime spawned

This file runs on any python3, imports only the standard library, and decides nothing: argv and help come from what the
runtime says this token may do, and even what it does not list goes to the runtime, which refuses and journals it.
"""

from __future__ import annotations

import http.client
import json
import os
import sys
import textwrap
import uuid
from typing import Any
from urllib.parse import urlsplit

URL_VARIABLE = "PLATOON_HARNESS_URL"
TOKEN_VARIABLE = "PLATOON_HARNESS_TOKEN"

_REFUSED = 1
_USAGE = 2
_UNREACHABLE = 69
_UNCONFIGURED = 78


def _say(stream: Any, text: str) -> None:
    stream.buffer.write(text.encode() + b"\n")
    stream.flush()


def _die(code: int, text: str) -> None:
    _say(sys.stderr, text)
    raise SystemExit(code)


def _rpc(url: str, token: str, method: str, params: dict[str, Any]) -> Any:
    """One call to the tool server, whose answer is the same for `ph` as for any client, in the words of a shell."""
    parts = urlsplit(url)
    message = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    connection = http.client.HTTPConnection(parts.netloc)
    try:
        connection.request("POST", f"{parts.path}?surface=ph", json.dumps(message), headers)
        response = connection.getresponse()
        status, body = response.status, response.read()
    except (OSError, http.client.HTTPException) as error:
        _die(_UNREACHABLE, f"ph: the runtime cannot be reached at {url}: {error}")
    finally:
        connection.close()
    if status == 401:
        _die(_REFUSED, "ph: this token is not valid: the agent has ended, or it was never issued one")
    if status != 200:
        _die(_UNREACHABLE, f"ph: the runtime answered HTTP {status}")
    reply = json.loads(body)
    if "error" in reply:
        _die(_USAGE, f"ph: {reply['error']['message']}: run `ph --help`")
    return reply["result"]


def _kind(field: dict[str, Any]) -> str:
    """A field's JSON type, past any `null` it allows."""
    types = [branch.get("type") for branch in field.get("anyOf", ())]
    return next((kind for kind in [field.get("type"), *types] if kind not in (None, "null")), "string")


def _typed(field: dict[str, Any], text: str) -> Any:
    """A flag's text as its field's type. What will not parse goes as text, for the runtime to refuse."""
    if _kind(field) == "string":
        return text
    try:
        return json.loads(text)
    except ValueError:
        return text


def _arguments(flags: list[str], schema: dict[str, Any]) -> dict[str, Any]:
    """Arguments from flags, typed by the schema. A flag it does not declare goes through for the runtime to refuse."""
    fields = schema.get("properties", {})
    arguments: dict[str, Any] = {}
    flags = list(flags)
    while flags:
        flag = flags.pop(0)
        if not flag.startswith("--") or flag == "--":
            _die(_USAGE, f"ph: expected a --flag, not {flag!r}: run `ph --help`")
        name, equals, text = flag[2:].partition("=")
        field = fields.get(name, {})
        if not equals:
            alone = not flags or flags[0].startswith("--")
            if alone and _kind(field) != "boolean":
                _die(_USAGE, f"ph: --{name} needs a value")
            text = "true" if alone else flags.pop(0)
        if _kind(field) == "array":
            arguments.setdefault(name, []).append(_typed(field.get("items", {}), text))
        else:
            arguments[name] = _typed(field, text)
    return arguments


def _summary(tool: dict[str, Any]) -> str:
    return tool["description"].split(". ")[0].rstrip(".")


def _overview(held: dict[str, dict[str, Any]]) -> str:
    width = max((len(name) for name in held), default=0)
    rows = [f"  {name:<{width}}  {_summary(tool)}" for name, tool in sorted(held.items())]
    return "\n".join(["usage: ph <op> [--flag value ...]", "", "What this agent may do:", *rows, "", __doc__ or ""])


def _details(name: str, tool: dict[str, Any]) -> str:
    lines = [f"usage: ph {name} [--flag value ...]", "", textwrap.fill(tool["description"], 100), ""]
    schema = tool["inputSchema"]
    required = schema.get("required", ())
    for field, shown in schema.get("properties", {}).items():
        kind = f"{_kind(shown)}, required" if field in required else _kind(shown)
        lines.append(f"  --{field} ({kind})  {shown.get('description', '')}")
    return "\n".join(lines)


def main(argv: list[str]) -> None:
    url, token = os.environ.get(URL_VARIABLE), os.environ.get(TOKEN_VARIABLE)
    if not url or not token:
        return _die(_UNCONFIGURED, f"ph: no token: the runtime sets {URL_VARIABLE} and {TOKEN_VARIABLE} for its agents")
    listed = _rpc(url, token, "tools/list", {})["tools"]
    held = {tool["title"]: tool for tool in listed}
    if not argv or argv[0] in ("-h", "--help"):
        _say(sys.stdout, _overview(held))
        raise SystemExit(0 if argv else _USAGE)
    name, flags = argv[0], argv[1:]
    tool = held.get(name)
    if tool is not None and ("-h" in flags or "--help" in flags):
        _say(sys.stdout, _details(name, tool))
        return
    schema = {} if tool is None else tool["inputSchema"]
    params = {
        "name": name.replace(".", "_") if tool is None else tool["name"],
        "arguments": _arguments(flags, schema),
        "_meta": {"platoon-harness/callId": uuid.uuid4().hex},  # A second `ph task.claim` is no retry of the first.
    }
    result = _rpc(url, token, "tools/call", params)
    first, *notes = [block["text"] for block in result["content"]]
    for note in notes:
        _say(sys.stderr, note)
    if result.get("isError"):
        _die(_REFUSED, first)
    _say(sys.stdout, first)


if __name__ == "__main__":
    main(sys.argv[1:])
