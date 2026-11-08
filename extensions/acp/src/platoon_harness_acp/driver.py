"""The ACP driver: an agent that speaks the Agent Client Protocol on stdio, at protocol 1 alone, over the SDK's own
JSON-RPC peer (RFC 0072).

A turn is one `session/prompt`, from its request to its answer, and that is the one boundary there is, as protocol 1
says nothing of a second prompt during a turn. The agent keeps its own tools, as it is offered no file system and no
terminal, and reaches ours as one MCP server over HTTP. An update nothing here maps keeps its raw frame, with a gap.
"""

import asyncio
import json
from collections import deque
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from importlib import metadata
from typing import Any
from uuid import uuid4

from platoon_harness.drivers import (
    UNREADABLE,
    AgentSpec,
    ApprovalRequested,
    Capabilities,
    Compacted,
    Delivery,
    Delta,
    DriverError,
    DriverInfo,
    InputDelivered,
    Item,
    Ready,
    Reconciled,
    Reporter,
    TurnEnded,
    TurnStarted,
    Verdict,
    keys_of,
    refuse_unset_model,
)
from platoon_harness.drivers.env import harness_env, on_path
from platoon_harness.drivers.process import LOG, Process
from platoon_harness.rpc import METHOD_NOT_FOUND, Closed, Peer, RpcError, strict_loads

PROTOCOL = 1
"""The one version of ACP this driver speaks: an agent that answers with another is refused."""

CAPABILITIES = Capabilities(
    persistent=True,
    resume=True,
    boundaries=frozenset({"turn"}),
    tool_paths=frozenset({"mcp-http"}),
    interrupt=True,
    approvals="native",
    native_children="opaque",
    coverage={"prompt": "partial", "tool_results": "partial", "compaction": "partial"},
)
"""What an ACP agent is driven with. ACP names no model call and says no spend of one, so there are no call ids and no
measures, and stable ACP neither shows an agent's own agents nor turns them off."""

_GRACE = 2.0
_CLIENT = {"fs": {"readTextFile": False, "writeTextFile": False}, "terminal": False, "session": {"compaction": {}}}
"""What the client offers: no file system and no terminal, so the agent keeps its own tools, and compaction updates."""
_AMBIENT = frozenset(
    {
        "available_commands_update",
        "current_mode_update",
        "config_option_update",
        "session_info_update",
        "usage_update",
        "notice",
    }
)
"""Updates of the session's state, which come at any time and say nothing of what the agent did. `usage_update` is the
context's size and a running cost, neither of which is the spend of a model call."""
_CHUNKS = frozenset({"agent_message_chunk", "agent_thought_chunk"})
_ENDED = frozenset({"completed", "failed"})
_NOT_ASKED = frozenset({"toolCallId", "status", "_meta"})
"""What a tool call holds that is no part of what it asks: its id, how far it has got, and what is the agent's own."""
_ONCE: Mapping[Verdict, str] = {"allow": "allow_once", "deny": "reject_once"}

__all__ = ["CAPABILITIES", "PROTOCOL", "AcpDriver"]


@dataclass
class _Asked:
    """A permission request the agent waits on: the tool call it names, and the verdict, None for one cut short."""

    call: str
    verdict: asyncio.Future[Verdict | None]


@dataclass
class _Text:
    """A run of one message's or one thought's chunks, as they came."""

    kind: str
    id: str | None
    chunks: list[str] = field(default_factory=list)


def _servers(spec: AgentSpec, agent: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Our tools, as one MCP server over HTTP under the agent's bearer, which ACP has an agent keep out of everything it
    says. An agent that reaches no server over HTTP cannot reach them."""
    tools = spec.tools
    if tools is None:
        return []
    if not (agent.get("mcpCapabilities") or {}).get("http"):
        raise DriverError("it reaches no MCP server over HTTP, which is how our tools are served")
    header = {"name": "Authorization", "value": f"Bearer {tools.token.reveal()}"}
    return [{"type": "http", "name": tools.namespace, "url": tools.url, "headers": [header]}]


def _text(block: Mapping[str, Any]) -> str:
    """What a content block says. Anything but text is a frame nothing here maps."""
    match block:
        case {"type": "text", "text": str(text)}:
            return text
        case _:
            raise ValueError(f"a content block of type {block.get('type')} is no text")


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _called(call: Mapping[str, Any]) -> str:
    """A tool call in a line: what the agent calls it, and its input."""
    title = call.get("title") or call.get("name") or "a tool call"
    return f"{title} {_json(call['rawInput'])}" if "rawInput" in call else str(title)


def _ask(call: Mapping[str, Any]) -> str | None:
    """The whole of what a tool call asks to do: the call as the agent gave it, as JSON, but for what asks nothing. A
    call that gives no input and no content says nothing of what it would do, which is unknown."""
    if "rawInput" not in call and not call.get("content"):
        return None
    return json.dumps(
        {key: value for key, value in call.items() if key not in _NOT_ASKED}, ensure_ascii=False, indent=2
    )


def _shown(entry: Mapping[str, Any]) -> str:
    """One entry of a tool call's content: text as it is, a diff as its path and new text, and anything else as JSON."""
    match entry:
        case {"type": "content", "content": {"type": "text", "text": str(text)}}:
            return text
        case {"type": "diff", "path": str(path), "newText": str(text)}:
            return f"{path}\n{text}"
        case _:
            return _json(entry)


def _output(call: Mapping[str, Any]) -> str | None:
    """What a finished tool call came to, in its content and its raw output, or None where it says nothing."""
    said = [_shown(entry) for entry in call.get("content") or ()]
    if "rawOutput" in call:
        said.append(_json(call["rawOutput"]))
    return "\n".join(said) or None


def _outcome(options: Sequence[Mapping[str, Any]], verdict: Verdict | None) -> dict[str, Any]:
    """A verdict as the request's option of its kind for this once. An `always` option would decide more than a person
    was asked, so where none is of that kind, and for a request an interrupt cut short, the answer is `cancelled`."""
    kind = None if verdict is None else _ONCE[verdict]
    chosen = next((option["optionId"] for option in options if option.get("kind") == kind), None)
    return {"outcome": "cancelled"} if chosen is None else {"outcome": "selected", "optionId": chosen}


def _kind(line: bytes) -> str:
    """What a frame says it is: an update's kind, or its method, or `frame` where it says neither."""
    try:
        frame = strict_loads(line)
    except (ValueError, RecursionError):
        return "frame"
    match frame:
        case {"method": "session/update", "params": {"update": {"sessionUpdate": str(kind)}}}:
            return f"session/update {kind}"
        case {"method": str(method)}:
            return method
        case _:
            return "frame"


class AcpDriver:
    """One agent that speaks ACP, run as `command`, with one session of its own.

    A delivery that comes during a turn waits for its end and goes as the next prompt, and one for any other boundary
    is refused, as no fixture has shown an agent taking one. Frames are taken on the read loop, which never waits, so
    the pipe drains, and a permission request waits for its verdict in a task of its own, which is what `Peer` gives a
    request.
    """

    name = "acp"
    inherits: tuple[str, ...] = ()
    """What the agent takes from the shell, by name, beyond what every harness does."""

    def __init__(self, command: Sequence[str]) -> None:
        self._command = tuple(command)
        self._launched: Process | None = None
        self._peer: Peer | None = None
        self._session = ""
        self._log = ""
        self._unsaid: str | None = None
        self._waiting: deque[Delivery] = deque()
        self._turn: asyncio.Task[None] | None = None
        self._landing: Delivery | None = None
        self._prompted = False
        self._landed: set[str] = set()
        self._interrupted = False
        self._calls: dict[str, dict[str, Any]] = {}
        self._asking: dict[str, _Asked] = {}
        self._deciding: dict[str, str] = {}
        self._text: _Text | None = None
        self._summaries: dict[str, list[str]] = {}

    def describe(self) -> DriverInfo:
        found = on_path(self._command[0])
        installed = tuple(dict.fromkeys((*found, *(path.resolve() for path in found))))
        return DriverInfo(name=self.name, capabilities=CAPABILITIES, installed=installed)

    async def start(self, spec: AgentSpec, report: Reporter) -> None:
        refuse_unset_model(spec)
        keys_of(spec)  # Which refuses a gateway, as there is no sealed launch.
        if spec.effort is not None:
            raise DriverError("this driver sets no effort, as ACP gives no field for one")
        self._log = str(spec.folder / LOG)
        env = harness_env(spec, *self.inherits)
        self._launched = await Process.launch(self._command, spec, report, read=self._read, env=env)
        try:
            await self._open(spec)
        except UNREADABLE as error:
            await self._launched.stop(_GRACE)
            raise DriverError(f"{self.name} answered what cannot be read: {error}") from error
        except DriverError:
            await self._launched.stop(_GRACE)  # ACP has a client disconnect from what it cannot speak to.
            raise
        if spec.goal is not None and spec.resume is None:
            await self.deliver(spec.goal)

    async def _open(self, spec: AgentSpec) -> None:
        """Agree on protocol 1, then open the session, or take it up again on a resume, with the role's instructions and
        model, which calls no model."""
        version = metadata.version("platoon-harness-acp")
        hello = {"protocolVersion": PROTOCOL, "clientCapabilities": _CLIENT}
        said = await self._call(
            "initialize", {**hello, "clientInfo": {"name": "platoon-harness-acp", "version": version}}
        )
        if said.get("protocolVersion") != PROTOCOL:
            raise DriverError(f"it speaks ACP protocol {said.get('protocolVersion')}, and this driver {PROTOCOL} alone")
        agent = said.get("agentCapabilities") or {}
        offered = agent.get("sessionCapabilities") or {}
        setup: dict[str, Any] = {"cwd": str(spec.cwd), "mcpServers": _servers(spec, agent)}
        if spec.instructions and offered.get("systemPrompt") is not None:
            setup["systemPrompt"] = {"mode": "append", "content": [{"type": "text", "text": spec.instructions}]}
        elif spec.resume is None:
            self._unsaid = spec.instructions  # Said once, before the first prompt, which the session then holds.
        if spec.resume is None:
            opened = await self._call("session/new", setup)
            self._session = opened["sessionId"]
        elif offered.get("resume") is None:
            raise DriverError("it offers no session/resume, so it cannot take its session up again")
        else:
            self._session = spec.resume
            opened = await self._call("session/resume", {"sessionId": spec.resume, **setup})
        model = await self._model(spec, (opened or {}).get("configOptions") or ())
        agent_version = (said.get("agentInfo") or {}).get("version")
        self._process.put(Ready(native=self._session, version=agent_version, effective_model=model))

    async def _model(self, spec: AgentSpec, options: Sequence[Mapping[str, Any]]) -> str | None:
        """The model the session's config option of category `model` holds, once set to the role's. An agent that offers
        none would run on a model nobody named, so a start that names one is refused."""
        option = next((option for option in options if option.get("category") == "model"), None)
        if option is None:
            if spec.model is not None:
                raise DriverError(f"it offers no model to choose, so it cannot be held to {spec.model}")
            return None
        if spec.model is not None and option.get("currentValue") != spec.model:
            params = {"sessionId": self._session, "configId": option["id"], "value": spec.model}
            options = (await self._call("session/set_config_option", params) or {}).get("configOptions") or ()
            option = next((each for each in options if each.get("id") == option["id"]), {})
        return option.get("currentValue")

    # What the agent is sent.

    def _lost(self) -> DriverError:
        return DriverError(f"{self.name} is gone: see {self._log}")

    async def _call(self, method: str, params: Any) -> Any:
        if self._peer is None:
            raise DriverError("this driver has not started")
        try:
            return await self._peer.call(method, params)
        except RpcError as error:
            raise DriverError(self._process.redact(error.message)) from error
        except Closed as error:
            raise self._lost() from error

    async def deliver(self, delivery: Delivery) -> None:
        if delivery.boundary != "turn":
            raise DriverError(
                f"ACP's protocol 1 has no {delivery.boundary} boundary, and no fixture has shown an agent taking a "
                "prompt during a turn, so a delivery waits for the turn's end"
            )
        if self._process.returncode is not None:
            raise self._lost()
        self._waiting.append(delivery)
        if self._turn is None:
            self._next()

    def _next(self) -> None:
        """Begin the next turn on what waits, if anything does."""
        self._turn = asyncio.create_task(self._prompt(self._waiting.popleft())) if self._waiting else None

    async def _prompt(self, delivery: Delivery) -> None:
        """One turn: a prompt, from its request to its answer, and then the next, if a delivery waits for it."""
        text = delivery.text if self._unsaid is None else f"{self._unsaid}\n\n{delivery.text}"
        self._landing, self._prompted = delivery, True
        self._process.put(TurnStarted(turn=uuid4().hex))
        try:
            answer = await self._call(
                "session/prompt", {"sessionId": self._session, "prompt": [{"type": "text", "text": text}]}
            )
            self._land("session/prompt answered")
            reason = self._reason(answer.get("stopReason") if isinstance(answer, dict) else None)
        except DriverError as error:
            reason = self._process.reason(f"failed: {error}")
        self._said()
        for asked in self._asking.values():
            asked.verdict.cancel()  # Moot with the turn that asked: the agent asks nothing of a prompt it has answered.
        self._asking.clear()
        self._process.put(TurnEnded(reason=reason))
        self._landing, self._prompted, self._interrupted = None, False, False
        self._next()

    def _reason(self, stop: Any) -> str:
        """`end_turn` is a turn that stopped on its own, and `cancelled` one an interrupt stopped, or that the agent cut
        short itself where nobody interrupted it. Any other stop reason is what went wrong."""
        match stop:
            case "end_turn":
                return "stopped"
            case "cancelled":
                return "interrupted" if self._interrupted else "aborted"
            case _:
                return self._process.reason(str(stop))

    async def interrupt(self) -> None:
        """Cancel the prompt under way, and answer each permission request it waits on `cancelled`, as ACP asks of a
        client. What waits for the next turn never reached the agent, and the runtime offers it again."""
        self._waiting.clear()
        if self._turn is None:
            return
        if not self._prompted:  # Its prompt has not gone, so nothing reached the agent, and no turn began.
            self._turn.cancel()
            self._turn = None
            return
        self._interrupted = True
        for asked in self._asking.values():
            if not asked.verdict.done():
                asked.verdict.set_result(None)
        self._asking.clear()
        assert self._peer is not None
        try:
            await self._peer.notify("session/cancel", {"sessionId": self._session})
        except Closed as error:
            self._interrupted = False
            raise self._lost() from error

    async def answer(self, approval: str, verdict: Verdict) -> None:
        asked = self._asking.pop(approval, None)
        if asked is None:
            raise DriverError(f"no approval {approval} is waiting")
        if asked.verdict.done():
            raise self._lost()
        self._deciding[asked.call] = approval
        asked.verdict.set_result(verdict)

    async def reconcile(self, input_id: str) -> Reconciled:
        """ACP keeps no id of a prompt, so what is known is what this driver saw land, or holds still."""
        if input_id in self._landed:
            return "landed"
        return "not_landed" if any(delivery.input == input_id for delivery in self._waiting) else "unknown"

    async def stop(self, grace: float) -> None:
        """End of stdin ends the agent, and whatever it has running with it."""
        if self._launched is not None:
            await self._launched.stop(grace)

    # What the agent says.

    @property
    def _process(self) -> Process:
        if self._launched is None:
            raise DriverError("this driver has not started")
        return self._launched

    def _read(self, process: Process) -> Any:
        self._peer = Peer(process.stdout, process.stdin, self._inbound, stray=self._stray)
        return self._peer.run()

    def _stray(self, line: bytes) -> None:
        self._process.unknown(_kind(line), line.decode(errors="replace"))

    async def _inbound(self, method: str, params: Any) -> Any:
        """One frame. Whatever cannot be read is refused, which answers a request the agent waits on and keeps the frame
        raw, with a gap."""
        try:
            return await self._take(method, params)
        except UNREADABLE as error:
            raise RpcError(METHOD_NOT_FOUND, f"{method} cannot be read: {error}") from error

    def _ours(self, session: Any) -> bool:
        """Whether a frame is of this driver's session. One that comes as the session opens, before its id is known, is
        of the one session the agent has."""
        return session == self._session or not self._session

    async def _take(self, method: str, params: Any) -> Any:
        match method, params:
            case "session/update", {"sessionId": session, "update": {"sessionUpdate": str(kind)} as update}:
                if not self._ours(session):
                    raise RpcError(METHOD_NOT_FOUND, f"session {session} is not this agent's")
                self._updated(kind, update)
            case "session/request_permission", {"sessionId": session, "toolCall": dict(call), "options": list(options)}:
                if not self._ours(session):
                    raise RpcError(METHOD_NOT_FOUND, f"session {session} is not this agent's")
                return await self._permission(call, options)
            case _:
                raise RpcError(METHOD_NOT_FOUND, f"nothing here takes {method}")

    def _land(self, evidence: str) -> None:
        """The prompt under way reached the agent, as what it said of it first shows."""
        if self._landing is not None:
            delivery, self._landing, self._unsaid = self._landing, None, None
            self._landed.add(delivery.input)
            self._process.put(InputDelivered(input=delivery.input, boundary="turn", evidence=evidence))

    def _updated(self, kind: str, update: Mapping[str, Any]) -> None:
        """One update. Any but one of the session's state shows the prompt landed, and a run of text ends at one of
        another kind. One nothing here maps keeps its raw frame, with a gap."""
        if kind in _AMBIENT:
            return
        self._land("session/update")
        if kind in _CHUNKS:
            self._chunk(kind, update)
            return
        self._said()
        match kind:
            case "user_message_chunk":
                pass  # The prompt, said back.
            case "tool_call" | "tool_call_update":
                self._tool(kind, update)
            case "plan":
                said = "\n".join(f"{entry.get('status')}: {entry['content']}" for entry in update["entries"])
                self._process.put(Item(kind="thought", gist=self._process.gist(said), body=said))
            case "compaction_summary_chunk":
                self._summaries.setdefault(update["compactionId"], []).append(_text(update["content"]))
            case "compaction_update":
                self._compaction(update)
            case _:
                raise RpcError(METHOD_NOT_FOUND, f"nothing here takes an update of kind {kind}")

    def _chunk(self, kind: str, update: Mapping[str, Any]) -> None:
        """Live text, kept until another message, another kind of text or update, or the turn's end closes it."""
        text, id = _text(update["content"]), update.get("messageId")
        if self._text is not None and (self._text.kind, self._text.id) != (kind, id):
            self._said()
        if self._text is None:
            self._text = _Text(kind, id)
        self._text.chunks.append(text)
        if kind == "agent_message_chunk":
            self._process.put(Delta(text=text))

    def _said(self) -> None:
        """Close the run of text under way, as one message or thought."""
        if self._text is None:
            return
        text, self._text = self._text, None
        body = "".join(text.chunks)
        kind = "message" if text.kind == "agent_message_chunk" else "thought"
        self._process.put(Item(kind=kind, gist=self._process.gist(body), native_id=text.id, body=body))

    def _tool(self, kind: str, update: Mapping[str, Any]) -> None:
        """A tool call as the agent last updated it: begun at its `tool_call`, ended at the status that ends it, with
        the approval that let it through, whose observed outcome that is."""
        id = update["toolCallId"]
        call = self._calls.setdefault(id, {})
        call.update({key: value for key, value in update.items() if key != "sessionUpdate" and value is not None})
        if kind == "tool_call":
            body = _json(call["rawInput"]) if "rawInput" in call else None
            self._process.put(
                Item(kind="tool", phase="started", gist=self._process.gist(_called(call)), native_id=id, body=body)
            )
        if call.get("status") in _ENDED:
            del self._calls[id]
            ended = Item(
                kind="tool",
                phase="completed",
                gist=self._process.gist(f"{_called(call)} {call['status']}"),
                native_id=id,
                body=_output(call),
                approval=self._deciding.pop(id, None),
                outcome=call["status"],
            )
            self._process.put(ended)

    def _compaction(self, update: Mapping[str, Any]) -> None:
        """A compaction that completed, and what took the place of what it forgot, which it does not name, so that stays
        unknown. One that failed or was cancelled forgot nothing."""
        status, chunks = update["status"], self._summaries.get(update["compactionId"], [])
        if status == "completed":
            summary = "".join(map(_text, update.get("summary") or ())) or "".join(chunks)
            self._process.put(Compacted(forgotten=None, summary=summary or None))
        if status in ("completed", "failed", "cancelled"):
            self._summaries.pop(update["compactionId"], None)

    async def _permission(self, call: Mapping[str, Any], options: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        """A permission request, waiting in its own task for the runtime's word: an approval whose whole ask is the tool
        call it names, as the agent last updated it, as the request's fields left out are."""
        self._land("session/request_permission")
        self._said()
        id = call["toolCallId"]
        known = self._calls.setdefault(id, {})
        known.update({key: value for key, value in call.items() if value is not None})
        approval = uuid4().hex
        asked = _Asked(id, asyncio.get_running_loop().create_future())
        self._asking[approval] = asked
        whole = _ask(known)
        said = _called(known) if whole is not None else f"{_called(known)}, which says nothing more of what it would do"
        self._process.put(ApprovalRequested(id=approval, gist=self._process.gist(said), body=whole))
        return {"outcome": _outcome(options, await asked.verdict)}
