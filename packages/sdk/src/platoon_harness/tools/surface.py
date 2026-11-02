"""What a model sees: one derivation from `ops.list`, per token, in the words of each surface."""

import json
import re
from collections.abc import Callable, Collection
from typing import Any

from platoon_harness.kernel import Kernel, Principal, Refusal, Refused
from platoon_harness.primitives import BODY_REF

type Surface = Callable[[str], str]

_NAMESPACE = re.compile(r"[A-Za-z0-9_-]+")
_OP_NAMED = re.compile(r"`([a-z][a-z0-9_]*(?:\.[a-z0-9_]+)*)`")
_REFUSALS = {
    "not_permitted": (
        "You may not do this.",
        "Call `peers` or `channel.list` to see what you can reach, or ask someone who can.",
    ),
    "invalid": (
        "The arguments are wrong, and nothing ran.",
        "Fix them, using only the arguments this tool declares.",
    ),
    "not_found": (
        "What you named does not exist.",
        "Check the name: `agent.list` and `channel.list` show what does.",
    ),
    "conflict": (
        "It clashes with where things stand now.",
        "Read the current state, then try again if it still makes sense.",
    ),
    "stale_fence": (
        "Your lease has gone, so someone else may have the task.",
        "Check it with `task.list`, and claim it again if it is open.",
    ),
    "queue_full": (
        "That inbox is full.",
        "Try later, or tell someone else.",
    ),
    "queue_empty": (
        "Nothing is open on that queue.",
        "Call `wait` with `queue` and end your turn.",
    ),
    "over_budget": (
        "The budget cannot cover this.",
        "Finish what you can with what you have, and say what is left.",
    ),
    "unsupported": (
        "This harness or session cannot do that.",
        "Do it another way: the detail says why.",
    ),
    "busy": (
        "The session is too busy to take this now, and nothing ran.",
        "Try the same call again shortly.",
    ),
    "unavailable": (
        "The runtime could not do this, which is no fault of the call.",
        "Try again; if it keeps failing, carry on without it and say so.",
    ),
    "key_reused": (
        "This call's key answered other arguments.",
        "Call again: a retry must carry the same arguments.",
    ),
    "undeliverable": (
        "That agent has ended.",
        "Tell someone else: `peers` shows who is here.",
    ),
}


def tool_name(op: str) -> str:
    """An op as an MCP server lists it: `task_claim`."""
    return op.replace(".", "_")


def harness_name(namespace: str) -> Surface:
    """An op as a harness shows a server's tools to its model: `mcp__<namespace>__task_claim`."""
    return lambda op: f"mcp__{namespace}__{tool_name(op)}"


def shell_name(op: str) -> str:
    """An op as a command: `ph task.claim`."""
    return f"ph {op}"


def named_surface(name: str) -> Surface:
    """The surface a client asks for: `mcp`, `ph` or `mcp__<namespace>`. It decides words, never what a token may do."""
    if name == "mcp":
        return tool_name
    if name == "ph":
        return shell_name
    namespace = name.removeprefix("mcp__")
    if namespace == name or _NAMESPACE.fullmatch(namespace) is None:
        raise ValueError(f"no surface {name[:64]!r}")
    return harness_name(namespace)


def describe(text: str, surface: Surface, ops: Collection[str]) -> str:
    """`text` in the words of one surface: each op it names in backticks becomes what that surface calls the tool."""

    def rendered(named: re.Match[str]) -> str:
        return f"`{surface(named[1])}`" if named[1] in ops else named[0]

    return _OP_NAMED.sub(rendered, " ".join(text.split()))


def _takes_body(field: dict[str, Any]) -> bool:
    return any(branch.get("pattern") == BODY_REF for branch in (field, *field.get("anyOf", ())))


def body_fields(schema: dict[str, Any]) -> tuple[str, ...]:
    """The arguments of an op that cite a stored body. A surface offers each as plain text."""
    return tuple(name for name, field in schema.get("properties", {}).items() if _takes_body(field))


def _field(field: dict[str, Any], surface: Surface, ops: Collection[str]) -> dict[str, Any]:
    shown = {"type": "string"} if _takes_body(field) else {k: v for k, v in field.items() if k != "title"}
    if "description" in field:
        shown["description"] = describe(field["description"], surface, ops)
    return shown


def _input_schema(schema: dict[str, Any], surface: Surface, ops: Collection[str]) -> dict[str, Any]:
    """An op's schema as a model should see it: no titles or class text, and each body offered as text."""
    shown = {keyword: value for keyword, value in schema.items() if keyword not in ("title", "description")}
    fields = {name: _field(field, surface, ops) for name, field in schema.get("properties", {}).items()}
    return {**shown, "properties": fields, "additionalProperties": False}


def _held(kernel: Kernel, principal: Principal) -> list[dict[str, Any]]:
    outcome = kernel.query(principal, "ops.list", {})
    if outcome.refusal is not None:
        raise Refused(outcome.refusal.code, outcome.refusal.detail)
    return [op for op in outcome.result if op["tool"]]


def list_tools(kernel: Kernel, principal: Principal, surface: Surface = tool_name) -> list[dict[str, Any]]:
    """What this principal holds, as MCP tools. `title` keeps the op's name, which is what `ph` goes by.

    `readOnlyHint` is true only for what journals nothing: an agent's read moves its cursor and records exposure.
    """
    return [
        {
            "name": tool_name(op["name"]),
            "title": op["name"],
            "description": describe(op["description"], surface, kernel.ops),
            "inputSchema": _input_schema(op["schema"], surface, kernel.ops),
            "annotations": {"readOnlyHint": op["query"]},
        }
        for op in _held(kernel, principal)
    ]


def preamble(kernel: Kernel, agent: Principal, surface: Surface = tool_name) -> str:
    """The turn preamble: this agent's exact tools, and who it can reach now, because no harness's tool discovery can be
    relied on and tool schemas never enumerate targets."""
    held = sorted(op["name"] for op in _held(kernel, agent))
    names = ", ".join(f"`{surface(op)}`" for op in held)
    lines = [
        f"You are @{agent.name}. You coordinate with this session through these tools, by exactly these names: {names}."
    ]
    if surface is shell_name:
        lines.append("Run `ph --help`, or `ph <tool> --help` for one tool's arguments.")
    if "peers" in held:
        peers = [peer["address"] for peer in kernel.query(agent, "peers", {}).result or ()]
        lines.append(f"You can message: {', '.join(peers) or 'nobody yet'}.")
    if "channel.list" in held:
        channels = [
            f"{found['name']} ({found['kind']})" for found in kernel.query(agent, "channel.list", {}).result or ()
        ]
        lines.append(f"Channels: {', '.join(channels) or 'none yet'}.")
    if "wait" in held:
        parking = (
            "With nothing to do until something changes, call `wait` and end your turn: the runtime starts the next."
        )
        lines.append(describe(parking, surface, kernel.ops))
    return "\n".join(lines)


def refusal_text(refusal: Refusal, surface: Surface, ops: Collection[str]) -> str:
    """A refusal as a model can act on it: the code, what it means, what to do next, and the reason given."""
    meaning, next_step = _REFUSALS[refusal.code]
    detail = refusal.detail if isinstance(refusal.detail, str) else json.dumps(refusal.detail, ensure_ascii=False)
    lines = [f"Refused {refusal.code}{f' on {refusal.object}' if refusal.object else ''}: {meaning}"]
    if detail:
        lines.append(f"Why: {detail}")
    lines.append(f"Next: {next_step}")
    if refusal.retry_after is not None:
        lines.append(f"Retry after {refusal.retry_after:.3f} seconds.")
    if refusal.reachable:
        lines.append(f"You can reach: {', '.join(refusal.reachable)}.")
    return "\n".join(describe(line, surface, ops) for line in lines)


def _entries(handed: dict[str, Any], surface: Surface, ops: Collection[str]) -> list[str]:
    """Each entry handed over, by the ref that dedupes a repeat, then how to read what did not come with it."""
    lines = []
    for item in handed["items"]:
        lines.append(f"- {item['ref']} from {item['sender']}: {item['gist']}")
        if item["body"]:
            reading = describe(f"Its body is {item['body']}: pass that as `ref` to `blob.get`.", surface, ops)
            lines.append(f"  {reading}")
    if handed["behind"]:
        lines.append(describe(f"{handed['behind']} more are waiting: call `message.read`.", surface, ops))
    return lines


def notices_text(handed: dict[str, Any], surface: Surface, ops: Collection[str]) -> str:
    """Steer notices handed over on a tool's result."""
    lines = ["Messages arrived, and they may change what you should do next:", *_entries(handed, surface, ops)]
    return "\n".join(lines)


def delivery_text(handed: dict[str, Any], surface: Surface, ops: Collection[str]) -> str:
    """A handover as a harness's prompt reads it. Its id goes with it, because a handover can come twice."""
    return "\n".join([f"New messages (delivery {handed['input']}):", *_entries(handed, surface, ops)])
