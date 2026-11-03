"""What a model sees: one derivation from `ops.list`, per token, in the words of each surface, fixed at launch."""

import json
import re
from collections.abc import Callable, Collection, Mapping
from string import Formatter
from typing import Any

from platoon_harness.kernel import Kernel, Principal, Refusal, Refused, tool_name
from platoon_harness.primitives import BODY_REF
from platoon_harness.schema import nearest

type Surface = Callable[[str], str]

NAMESPACE = "ph"
"""What our tools go by on a harness that shows a server's tools by MCP, as `mcp__ph__task_claim`, and as a command."""
_MCP = frozenset({"mcp-http", "mcp-stdio"})
_NAMESPACE_SHAPE = re.compile(r"[A-Za-z0-9_-]+")
_SENTENCE = re.compile(r"(?<=\.)\s+")
OP_NAMED = re.compile(r"`([a-z][a-z0-9_]*(?:\.[a-z0-9_]+)*)`")
_SLOTS = ("name", "tools", "help", "peers", "roles", "channels", "waiting", "ending")
"""What a preamble template's slots hold for one agent, on its harness's surface. `name` and `tools`, by their exact
names, are values. The rest are sentences of ours, empty where they would say nothing: how to ask `ph` for help, who it
can message, which roles it can start, its channels, how to wait and how to end."""
PREAMBLE = """\
You are @{name}. You coordinate with this session through these tools, by exactly these names: {tools}.
{help}
{peers}
{roles}
{channels}
{waiting}
{ending}"""
"""The template every agent's preamble fills unless its team or its role gives another. A slot is a word in braces, and
`{{` and `}}` write a brace. A line that holds a slot and comes out blank is left out, so no word of a template's is."""
_NO_NEXT_STEP = "Carry on without it, and say so."
_PARKING = (
    "To wait for something before you go on, call `wait` naming it and end your turn: the runtime starts the next when "
    "it holds."
)
_FINISHING = (
    "When your goal is done, make `agent.finish` your last call, with your report: a turn that only ends leaves you "
    "idle, and whoever waits on you still waiting."
)
_STAYING = (
    "When told to finish, make `agent.finish` your last call, or your session never closes. Told nothing of the kind, "
    "stay: it ends you for good, and a turn that only ends leaves you here for the next message."
)
_ANSWERING = (
    "Answer by ending your turn: what you say last in it goes to @{parent}, and a turn that only ends leaves you here "
    "for the next message. Make `agent.finish` your last call only when told to finish: it ends you for good."
)
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
        "Check the name: `peers` and `channel.list` show what does.",
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


def harness_name(namespace: str) -> Surface:
    """An op as a harness shows a server's tools to its model: `mcp__<namespace>__task_claim`."""
    return lambda op: f"mcp__{namespace}__{tool_name(op)}"


def shell_name(op: str) -> str:
    """An op as a command: `ph task.claim`."""
    return f"ph {op}"


def surface_of(paths: Collection[str]) -> Surface | None:
    """How a harness that reaches our tools by `paths` names them to its model: by MCP under `NAMESPACE`, by `ph`, or
    not at all."""
    if not paths:
        return None
    return shell_name if _MCP.isdisjoint(paths) else harness_name(NAMESPACE)


def named_surface(name: str) -> Surface:
    """The surface a client asks for: `mcp`, `ph` or `mcp__<namespace>`. It decides words, never what a token may do."""
    if name == "mcp":
        return tool_name
    if name == "ph":
        return shell_name
    namespace = name.removeprefix("mcp__")
    if namespace == name or _NAMESPACE_SHAPE.fullmatch(namespace) is None:
        raise ValueError(f"no surface {name[:64]!r}")
    return harness_name(namespace)


def worded(text: str, surface: Surface, ops: Collection[str]) -> str:
    """`text` in the words of one surface: each of `ops` it names in backticks becomes what that surface calls the
    tool, and nothing else changes."""

    def rendered(named: re.Match[str]) -> str:
        return f"`{surface(named[1])}`" if named[1] in ops else named[0]

    return OP_NAMED.sub(rendered, text)


def describe(text: str, surface: Surface, ops: Collection[str]) -> str:
    """`text` in the words of one surface, on one line, as a description reads."""
    return worded(" ".join(text.split()), surface, ops)


def _named(text: str, ops: Collection[str]) -> set[str]:
    return {name for name in OP_NAMED.findall(text) if name in ops}


def _teacher(surface: Surface, ops: Collection[str], held: Collection[str]) -> Callable[[str], str]:
    """How one reader is told a thing: `describe`, with no sentence that names a tool it does not hold, since that would
    send a model to something it cannot call."""

    def teach(text: str) -> str:
        sentences = _SENTENCE.split(" ".join(text.split()))
        return describe(" ".join(line for line in sentences if _named(line, ops) <= {*held}), surface, ops)

    return teach


def _takes_body(field: dict[str, Any]) -> bool:
    return any(branch.get("pattern") == BODY_REF for branch in (field, *field.get("anyOf", ())))


def body_fields(schema: dict[str, Any]) -> tuple[str, ...]:
    """The arguments of an op that cite a stored body. A surface offers each as plain text."""
    return tuple(name for name, field in schema.get("properties", {}).items() if _takes_body(field))


def _field(field: dict[str, Any], teach: Callable[[str], str]) -> dict[str, Any]:
    shown = {"type": "string"} if _takes_body(field) else {k: v for k, v in field.items() if k != "title"}
    if "description" in field:
        shown["description"] = teach(field["description"])
    return shown


def _input_schema(schema: dict[str, Any], teach: Callable[[str], str]) -> dict[str, Any]:
    """An op's schema as a model should see it: no titles or class text, and each body offered as text."""
    shown = {keyword: value for keyword, value in schema.items() if keyword not in ("title", "description")}
    fields = {name: _field(field, teach) for name, field in schema.get("properties", {}).items()}
    return {**shown, "properties": fields, "additionalProperties": False}


def held_tools(kernel: Kernel, principal: Principal) -> set[str]:
    """The tool ops this principal holds now. An ended agent holds none."""
    return {op["name"] for op in kernel.query(principal, "ops.list", {}).result or () if op["tool"]}


def _held(kernel: Kernel, principal: Principal) -> list[dict[str, Any]]:
    outcome = kernel.query(principal, "ops.list", {})
    if outcome.refusal is not None:
        raise Refused(outcome.refusal.code, outcome.refusal.detail)
    return [op for op in outcome.result if op["tool"]]


def list_tools(kernel: Kernel, principal: Principal, surface: Surface = tool_name) -> list[dict[str, Any]]:
    """What this principal holds, as MCP tools. `title` keeps the op's name, which is what `ph` goes by.

    `readOnlyHint` is true only for what journals nothing: an agent's read moves its cursor and records exposure.
    """
    tools = _held(kernel, principal)
    teach = _teacher(surface, kernel.ops, {op["name"] for op in tools})
    return [
        {
            "name": tool_name(op["name"]),
            "title": op["name"],
            "description": teach(op["description"]),
            "inputSchema": _input_schema(op["schema"], teach),
            "annotations": {"readOnlyHint": op["query"]},
        }
        for op in tools
    ]


def _listed(page: dict[str, Any], rows: str, show: Callable[[dict[str, Any]], str], tool: str) -> str:
    """A first page as words, saying where the rest is."""
    return ", ".join((*map(show, page[rows]), *(() if page["cursor"] is None else (f"and more: call `{tool}`",))))


def _ending(kernel: Kernel, agent: Principal) -> str:
    """How this agent is told to end, by whether it stays, which was settled at its spawn."""
    outcome = kernel.query(kernel.runtime, "agent.status", {"agent": agent.name})
    if outcome.refusal is not None:
        raise Refused(outcome.refusal.code, outcome.refusal.detail)
    status = outcome.result
    if not status["stays"]:
        return _FINISHING
    return _STAYING if status["parent"] is None else _ANSWERING.format(parent=status["parent"])


def slots(template: str) -> tuple[str, ...]:
    """The slots a preamble template fills, in order, or `ValueError` naming what is wrong with it."""
    try:
        parsed = list(Formatter().parse(template))
    except ValueError as error:
        raise ValueError(f"{error}: write a brace as `{{{{` or `}}}}`") from None
    found = []
    for _, slot, spec, conversion in parsed:
        if slot is None:
            continue
        if spec or conversion:
            raise ValueError(f"`{{{slot}}}` takes no `!` or `:`, as it is filled with text")
        if slot not in _SLOTS:
            raise ValueError(f"no slot `{{{slot}}}`.{nearest(slot, _SLOTS)}")
        found.append(slot)
    return tuple(found)


def _line(line: str, values: Mapping[str, str], surface: Surface, ops: Collection[str]) -> str | None:
    """One line of a template, its own words in the words of `surface`, or None when it holds a slot and comes out
    blank, which only a line with no words of its own can."""
    parsed = list(Formatter().parse(line))
    text = "".join(worded(words, surface, ops) + (values[slot] if slot else "") for words, slot, _, _ in parsed)
    if any(slot is not None for _, slot, _, _ in parsed) and not text.strip():
        return None
    return text


def preamble(kernel: Kernel, agent: Principal, surface: Surface = tool_name, template: str = PREAMBLE) -> str:
    """This agent's exact tools, and who it can reach, because no harness's tool discovery can be relied on and tool
    schemas never enumerate targets, filled into `template`. A harness has it once, at launch, so it is a snapshot:
    `peers` is what stays current."""
    slots(template)  # A slot nobody fills is refused here as it is when a team loads.
    held = sorted(op["name"] for op in _held(kernel, agent))
    values = dict.fromkeys(_SLOTS, "")
    values["name"] = agent.name
    values["tools"] = ", ".join(f"`{surface(op)}`" for op in held)
    if surface is shell_name:
        values["help"] = "Run `ph --help`, or `ph <tool> --help` for one tool's arguments."
    if "peers" in held and (peers := kernel.query(agent, "peers", {})).refusal is None:
        reach = _listed(peers.result, "peers", lambda peer: peer["address"], surface("peers"))
        values["peers"] = f"You can message: {reach or 'nobody yet'}."
        if peers.result["roles"]:
            values["roles"] = f"You can start agents in these roles: {', '.join(peers.result['roles'])}."
    if "channel.list" in held and (channels := kernel.query(agent, "channel.list", {})).refusal is None:
        shown = _listed(
            channels.result, "channels", lambda found: f"{found['name']} ({found['kind']})", surface("channel.list")
        )
        values["channels"] = f"Channels: {shown or 'none yet'}."
    teach = _teacher(surface, kernel.ops, held)
    values["waiting"] = teach(_PARKING)
    values["ending"] = teach(_ending(kernel, agent))
    lines = (_line(line, values, surface, _tools(kernel)) for line in template.split("\n"))
    return "\n".join(line for line in lines if line is not None)


def _tools(kernel: Kernel) -> set[str]:
    return {name for name, operation in kernel.ops.items() if operation.tool}


def instructions(
    kernel: Kernel, agent: Principal, surface: Surface | None, template: str, words: str | None
) -> str | None:
    """What the runtime adds to an agent's harness: its preamble filled into `template`, then `words`, its role's own,
    last, so that a role has the last word, or `words` alone on a harness that reaches none of our tools. A tool either
    names in backticks is named as `surface` names it. None is nothing to add."""
    if surface is None:
        return words or None
    told = preamble(kernel, agent, surface, template)
    return "\n\n".join(filter(None, (told, words and worded(words, surface, _tools(kernel))))) or None


def taught(text: str, surface: Surface, ops: Collection[str], held: Collection[str]) -> str:
    """What an op says to do next, in the words of a surface, with no sentence that names a tool outside `held`."""
    return _teacher(surface, ops, held)(text)


def refusal_text(refusal: Refusal, surface: Surface, ops: Collection[str], held: Collection[str]) -> str:
    """A refusal as a model can act on it: the code, what it means, why, and what to do next, each told as anything else
    is, so that it sends a model to no tool outside `held`."""
    teach = _teacher(surface, ops, held)
    meaning, next_step = _REFUSALS[refusal.code]
    detail = refusal.detail if isinstance(refusal.detail, str) else json.dumps(refusal.detail, ensure_ascii=False)
    lines = [f"Refused {refusal.code}{f' on {refusal.object}' if refusal.object else ''}: {meaning}"]
    if why := teach(detail):
        lines.append(f"Why: {why}")
    lines.append(f"Next: {teach(next_step) or _NO_NEXT_STEP}")
    if refusal.retry_after is not None:
        lines.append(f"Retry after {refusal.retry_after:.3f} seconds.")
    if refusal.reachable:
        lines.append(f"You can reach: {', '.join(refusal.reachable)}.")
    return "\n".join(lines)


def _entries(handed: dict[str, Any], teach: Callable[[str], str]) -> list[str]:
    """Each entry handed over, by the ref that dedupes a repeat, then how to read what did not come with it."""
    lines = []
    for item in handed["items"]:
        lines.append(f"- {item['ref']} from {item['sender']}: {item['gist']}")
        if item["body"] and (reading := teach(f"Its body is {item['body']}: pass that as `ref` to `blob.get`.")):
            lines.append(f"  {reading}")
    if handed["behind"] and (behind := teach(f"{handed['behind']} more are waiting: call `message.read`.")):
        lines.append(behind)
    return lines


def notices_text(handed: dict[str, Any], surface: Surface, ops: Collection[str], held: Collection[str]) -> str:
    """Steer notices handed over on a tool's result."""
    entries = _entries(handed, _teacher(surface, ops, held))
    return "\n".join(["Messages arrived, and they may change what you should do next:", *entries])


def delivery_heading(input: object) -> str:
    """The line a handover opens with, which holds its id, because a handover can come twice."""
    return f"New messages (delivery {input}):"


def delivery_text(handed: dict[str, Any], surface: Surface, ops: Collection[str], held: Collection[str]) -> str:
    """A handover as a harness's prompt reads it."""
    entries = _entries(handed, _teacher(surface, ops, held))
    return "\n".join([delivery_heading(handed["input"]), *entries])
