"""The `codex` driver: `codex app-server` on stdio, JSON-RPC with no `jsonrpc` member.

A role runs in the user's own setup: `thread/start.config` overlays their configuration for one thread and writes none
of it. Every approval the harness asks for comes to the runtime, and a role's budget is what limits it.
"""

import asyncio
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from platoon_harness.primitives import Verdict
from platoon_harness.rpc import METHOD_NOT_FOUND, Closed, Peer, RpcError
from platoon_harness.tools.ph import TOKEN_VARIABLE
from platoon_harness.version import __version__

from . import (
    UNREADABLE,
    AgentSpec,
    ApprovalRequested,
    Capabilities,
    ChildSeen,
    Compacted,
    Delivery,
    Delta,
    DriverError,
    DriverInfo,
    GapReport,
    InputDelivered,
    Item,
    Login,
    ModelCall,
    Ready,
    Reconciled,
    Reporter,
    TurnEnded,
    TurnStarted,
    Usage,
    refuse_other_effort,
    refuse_unset_model,
    text_of,
)
from .env import harness_env, inherited
from .process import LOG, Process, status

_CODEX = "codex"
_SIGN_IN = (
    "CODEX_HOME",
    "CODEX_CA_CERTIFICATE",
    "SSL_CERT_FILE",
    "HTTPS_PROXY",
    "HTTP_PROXY",
    "ALL_PROXY",
    "NO_PROXY",
    "https_proxy",
    "http_proxy",
    "all_proxy",
    "no_proxy",
    "DBUS_SESSION_BUS_ADDRESS",  # The session bus a keyring login sits behind.
)
_BASE_URL = "OPENAI_BASE_URL"
_KEY = "OPENAI_API_KEY"
_PROVIDER = "platoon-harness"
_LOGINS: Mapping[str, Login] = {"Logged in using ChatGPT": "plan", "API key configured": "key"}
_ASKS = "on-request"
_TOOL_TIMEOUT_S = 300.0
_TOOLS = frozenset(
    {
        "collabAgentToolCall",
        "commandExecution",
        "dynamicToolCall",
        "imageGeneration",
        "imageView",
        "mcpToolCall",
        "sleep",
        "subAgentActivity",
        "webSearch",
    }
)
_SAYS_NOTHING = frozenset(
    {
        "app/list/updated",
        "configWarning",
        "deprecationNotice",
        "error",
        "hook/completed",
        "hook/started",
        "item/commandExecution/outputDelta",
        "item/commandExecution/terminalInteraction",
        "item/fileChange/outputDelta",
        "item/fileChange/patchUpdated",
        "item/mcpToolCall/progress",
        "item/plan/delta",
        "item/reasoning/summaryPartAdded",
        "item/reasoning/summaryTextDelta",
        "item/reasoning/textDelta",
        "mcpServer/startupStatus/updated",
        "remoteControl/status/changed",
        "serverRequest/resolved",
        "skills/changed",
        "thread/compacted",
        "thread/goal/cleared",
        "thread/goal/updated",
        "thread/name/updated",
        "thread/readState/changed",
        "thread/settings/updated",
        "thread/started",
        "thread/status/changed",
        "turn/diff/updated",
        "turn/moderationMetadata",
        "turn/plan/updated",
        "warning",
    }
)
_CAPABILITIES = Capabilities(
    persistent=True,
    resume=True,
    boundaries={"turn", "model_call"},
    tool_paths={"mcp-http"},
    tool_timeout_s=_TOOL_TIMEOUT_S,
    interrupt=True,
    approvals="native",
    native_children="observed",
    call_ids="agent",
    dialects={"responses"},
    coverage={"prompt": "partial", "tool_results": "observed", "native_children": "partial", "compaction": "partial"},
    measures={"tokens"},
    sandboxes={"read-only", "workspace-write", "danger-full-access"},
)

__all__ = ["CodexDriver"]


def _login() -> Login | None:
    """Which kind of login `codex` says it has, or None if it cannot tell. Nothing else it said is kept."""
    done = status((_CODEX, "login", "status"), inherited(*_SIGN_IN))
    said = "" if done is None else done.stderr.decode(errors="replace")
    return next((login for phrase, login in _LOGINS.items() if phrase in said), None)


def _provider(spec: AgentSpec) -> dict[str, Any] | None:
    """A provider of this thread's own, when access was given, so that the key pays and no saved login does. Codex
    reads no base URL from its environment, so the URL goes here too."""
    if _KEY not in spec.access:
        return None
    provider = {"name": _PROVIDER, "env_key": _KEY, "wire_api": "responses"}
    return provider | ({"base_url": spec.access[_BASE_URL].reveal()} if _BASE_URL in spec.access else {})


def _thread(spec: AgentSpec, theirs: Mapping[str, Any]) -> dict[str, Any]:
    """How this agent's thread opens, sent again on a resume, where a thread keeps the instructions and the setting of
    its own agents it began with. `theirs` is the user's config: a field here replaces the one there, so what they wrote
    stays in what is sent."""
    config: dict[str, Any] = {}
    fields = {"cwd": str(spec.cwd), "approvalPolicy": _ASKS, "approvalsReviewer": "user", "config": config}
    if spec.model is not None:
        fields["model"] = spec.model
    if spec.sandbox is not None:
        fields["sandbox"] = spec.sandbox
    if spec.effort is not None:
        config["model_reasoning_effort"] = spec.effort
    if not spec.allow_native_children:
        # Takes away its own agents' tools of both generations, where `features.multi_agent` takes only the first.
        config["agents"] = {"enabled": False}
    if instructions := "\n\n".join(filter(None, (theirs.get("developer_instructions"), spec.instructions))):
        fields["developerInstructions"] = instructions
    if (tools := spec.tools) is not None:
        server = {
            "url": tools.url,
            "bearer_token_env_var": TOKEN_VARIABLE,
            "default_tools_approval_mode": "approve",
            "required": True,
            "omit_tools_from": ["deferred"],
        }
        excluded = (theirs.get("shell_environment_policy") or {}).get("exclude") or ()
        config["mcp_servers"] = {tools.namespace: server}
        config["shell_environment_policy"] = {"exclude": [*excluded, TOKEN_VARIABLE]}
    if (provider := _provider(spec)) is not None:
        fields["modelProvider"] = _PROVIDER
        config["model_providers"] = {_PROVIDER: provider}
    return fields


def _name(item: Mapping[str, Any]) -> str:
    """What a tool item is called, or for a command, what it runs."""
    match item:
        case {"type": "commandExecution", "command": command}:
            return command
        case {"type": "mcpToolCall", "server": server, "tool": tool}:
            return f"mcp__{server}__{tool}"
        case {"type": "fileChange", "changes": changes}:
            return " ".join(change["path"] for change in changes)
        case {"tool": tool}:
            return tool
        case _:
            return item["type"]


def _output(item: Mapping[str, Any]) -> str | None:
    """What a finished tool item came to, in whichever of its shapes."""
    match item:
        case {"aggregatedOutput": str(output)}:
            return output
        case {"result": {"content": list(blocks)}}:
            return text_of(blocks)
        case {"error": {"message": str(message)}}:
            return message
        case {"changes": list(changes)}:
            return "\n".join(change["diff"] for change in changes)
        case _:
            return None


def _reply(method: str, params: Mapping[str, Any], verdict: Verdict) -> Mapping[str, Any]:
    """A verdict in the shape each request takes. `decline` lets the model go on, as a denial does elsewhere, where
    `cancel` would stop its turn."""
    allowed = verdict == "allow"
    match method:
        case "mcpServer/elicitation/request":
            return {"action": "accept", "content": {}} if allowed else {"action": "decline"}
        case "item/permissions/requestApproval":
            return {"permissions": params["permissions"] if allowed else {}, "scope": "turn"}
        case _:
            return {"decision": "accept" if allowed else "decline"}


@dataclass
class _Asked:
    """An approval the harness waits on. `item` is the tool item it holds up, when it names one."""

    turn: str | None
    item: str | None
    verdict: asyncio.Future[Verdict]


class CodexDriver:
    """One `codex app-server` with one thread. Our turn runs from the input that began it until the thread and every
    native child of it have stopped, since a child can outlive its parent's turn, and nothing else says it is at work.

    Frames are translated on the read loop, which never waits, so the pipe drains. An approval waits in a task of its
    own, which is what `Peer` gives a request.
    """

    def __init__(self) -> None:
        self._info: DriverInfo | None = None
        self._launched: Process | None = None
        self._peer: Peer | None = None
        self._native = ""
        self._folder = Path()
        self._turns: dict[str, str] = {}
        self._cut: asyncio.Task[None] | None = None
        self._children: set[str] = set()
        self._opening = False
        self._ending = "stopped"
        self._interrupted = False
        self._totals: dict[str, int] = {}
        self._unlanded: set[str] = set()
        self._asking: dict[str, _Asked] = {}
        self._deciding: dict[str, str] = {}
        self._compacting = False
        self._measured = False

    def describe(self) -> DriverInfo:
        if self._info is None:
            self._info = DriverInfo(name=_CODEX, login=_login(), capabilities=_CAPABILITIES)
        return self._info

    async def start(self, spec: AgentSpec, report: Reporter) -> None:
        refuse_unset_model(spec)
        if _BASE_URL in spec.access and _KEY not in spec.access:
            raise DriverError(f"{_BASE_URL} with no {_KEY} would reach nobody's model: name one too")
        self._folder = spec.folder
        env = harness_env(spec, *_SIGN_IN)
        self._launched = await Process.launch((_CODEX, "app-server"), spec, report, read=self._read, env=env)
        await self._handshake(spec)
        if spec.goal is not None and spec.resume is None:
            await self.deliver(spec.goal)

    async def _handshake(self, spec: AgentSpec) -> None:
        """Open the thread, which answers with what `ready` needs and calls no model."""
        await self._call("initialize", {"clientInfo": {"name": "platoon_harness", "version": __version__}})
        await self._notify("initialized")
        theirs = (await self._call("config/read", {"cwd": str(spec.cwd)}))["config"]
        fields = _thread(spec, theirs)
        if spec.resume is None:
            opened = await self._call("thread/start", fields)
        else:
            opened = await self._call("thread/resume", {"threadId": spec.resume, "excludeTurns": True, **fields})
        if opened.get("cwd") is None or Path(opened["cwd"]).resolve() != spec.cwd.resolve():
            raise DriverError(f"its thread runs in {opened.get('cwd')}, and its workspace is {spec.cwd}")
        refuse_other_effort(spec, opened.get("reasoningEffort"))
        self._native = opened["thread"]["id"]
        version = opened["thread"].get("cliVersion")
        self._process.put(Ready(native=self._native, version=version, effective_model=opened.get("model")))

    # What the harness is sent.

    def _lost(self) -> DriverError:
        return DriverError(f"{_CODEX} is gone: see {self._folder / LOG}")

    async def _call(self, method: str, params: Any) -> Any:
        if self._peer is None:
            raise DriverError("this driver has not started")
        try:
            return await self._peer.call(method, params)
        except RpcError as error:
            raise DriverError(self._process.redact(error.message)) from error
        except Closed as error:
            raise self._lost() from error

    async def _notify(self, method: str) -> None:
        assert self._peer is not None
        try:
            await self._peer.notify(method)
        except Closed as error:
            raise self._lost() from error

    async def _hand_over(self, text: str, input: str) -> None:
        """`turn/start` steers a turn under way and otherwise begins one, so no turn can end between a look and a send.
        A steer lands at the next model call."""
        params = {"threadId": self._native, "input": [{"type": "text", "text": text}], "clientUserMessageId": input}
        await self._call("turn/start", params)

    async def deliver(self, delivery: Delivery) -> None:
        self._unlanded.add(delivery.input)
        try:
            await self._hand_over(delivery.text, delivery.input)
        except DriverError:
            self._unlanded.discard(delivery.input)
            self._interrupted &= bool(self._turns or self._unlanded)  # No turn is on its way for it to cut.
            raise

    async def interrupt(self) -> None:
        """Stop the turn, on this thread and on every child of it, as `turn/interrupt` stops one thread alone. A turn
        an input on its way is about to begin has no id yet, so it is cut as it starts. A tool may run on, as an exec
        session outlives a turn. What was steered and never landed is lost to the harness at this, and the runtime
        offers it again."""
        self._interrupted = bool(self._turns or self._unlanded)
        try:
            for thread, turn in tuple(self._turns.items()):
                await self._interrupt_turn(thread, turn)
        except DriverError:
            self._interrupted = False
            raise

    async def _interrupt_turn(self, thread: str, turn: str) -> None:
        try:
            await self._call("turn/interrupt", {"threadId": thread, "turnId": turn})
        except DriverError:
            if thread in self._turns:  # One that has ended since needs no interrupt.
                raise

    async def _interrupt_late(self, thread: str, turn: str) -> None:
        """Cut a turn an interrupt came before. A refusal has nobody to tell, so the turn ends as itself."""
        try:
            await self._interrupt_turn(thread, turn)
        except DriverError:
            self._interrupted = False

    async def answer(self, approval: str, verdict: Verdict) -> None:
        asked = self._asking.pop(approval, None)
        if asked is None:
            raise DriverError(f"no approval {approval} is waiting")
        if asked.verdict.done():
            raise self._lost()
        if asked.item is not None:
            self._deciding[asked.item] = approval
        asked.verdict.set_result(verdict)

    async def reconcile(self, input_id: str) -> Reconciled:
        """What came of an input after a crash is in the thread's newest turns, which carry the id it went out under. A
        miss proves nothing, as an older turn is on a later page, so this never says `not_landed`."""
        page = await self._call("thread/turns/list", {"threadId": self._native, "itemsView": "full"})
        said = {item.get("clientId") for turn in page["data"] for item in turn["items"]}
        return "landed" if input_id in said else "unknown"

    async def stop(self, grace: float) -> None:
        """End of stdin ends the app-server and whatever tool it has running, even one in a session of its own."""
        if self._launched is not None:
            await self._launched.stop(grace)

    # What the harness says.

    @property
    def _process(self) -> Process:
        if self._launched is None:
            raise DriverError("this driver has not started")
        return self._launched

    def _read(self, process: Process) -> Any:
        self._peer = Peer(process.stdout, process.stdin, self._inbound, stray=self._stray, jsonrpc=False)
        return self._peer.run()

    def _stray(self, line: bytes) -> None:
        self._process.unknown("frame", line.decode(errors="replace"))

    async def _inbound(self, method: str, params: Any) -> Any:
        """One frame. Whatever cannot be read is refused, which answers a request the harness waits on and makes a
        stray of the frame."""
        try:
            return await self._take(method, params)
        except UNREADABLE as error:
            raise RpcError(METHOD_NOT_FOUND, f"{method} cannot be read: {error}") from error

    async def _take(self, method: str, params: Any) -> Any:
        """`account/` frames name the account, so they never reach a report."""
        match method, params:
            case (
                "item/commandExecution/requestApproval"
                | "item/fileChange/requestApproval"
                | "item/permissions/requestApproval"
                | "mcpServer/elicitation/request",
                dict(),
            ):
                return await self._decided(method, params)
            case "turn/started", {"threadId": str(thread), "turn": {"id": str(turn)}}:
                self._begin(thread, turn)
            case "turn/completed", {"threadId": str(thread), "turn": {"id": str()} as turn}:
                self._ended(thread, turn)
            case "item/started" | "item/completed", {"threadId": thread} if thread != self._native:
                pass  # A native child's own work, which its turn and its usage stand for.
            case "item/started", {"item": {"type": str()} as item}:
                self._started(item)
            case "item/completed", {"item": {"type": str()} as item}:
                self._completed(item)
            case "item/agentMessage/delta", {"threadId": thread, "delta": text}:
                if thread == self._native:
                    self._process.put(Delta(text=text))
            case "thread/tokenUsage/updated", {
                "threadId": str(thread),
                "tokenUsage": {"total": {"totalTokens": total}},
            }:
                self._used(thread, total)
            case _ if method not in _SAYS_NOTHING and not method.startswith("account/"):
                raise RpcError(METHOD_NOT_FOUND, f"nothing here takes {method}")

    async def _decided(self, method: str, params: Mapping[str, Any]) -> Mapping[str, Any]:
        """Wait for the runtime's word, in this request's own task. A turn that ends first takes this with it, and the
        harness has dropped the request by then, so nothing answers."""
        id = uuid4().hex
        asked = _Asked(params.get("turnId"), params.get("itemId"), asyncio.get_running_loop().create_future())
        self._asking[id] = asked
        said = params.get("command") or params.get("message") or params.get("reason") or method
        self._process.put(ApprovalRequested(id=id, gist=self._process.gist(said)))
        return _reply(method, params, await asked.verdict)

    def _begin(self, thread: str, turn: str) -> None:
        if not self._turns:
            self._process.put(TurnStarted(turn=turn))
            if self._interrupted:  # An interrupt came while this turn had no id to name.
                self._cut = asyncio.create_task(self._interrupt_late(thread, turn))
        self._turns[thread] = turn
        if thread == self._native:
            self._opening = True
        elif thread not in self._children:
            self._children.add(thread)
            self._process.put(
                ChildSeen(native=thread),
                GapReport(what="native_child_unattributed"),
            )

    def _landed(self, item: Mapping[str, Any]) -> None:
        """An input reached the model's context: as what began a turn, or as a steer inside one."""
        boundary = "turn" if self._opening else "model_call"
        self._opening = False
        match item:
            case {"clientId": str(input), "id": id}:
                self._unlanded.discard(input)
                self._process.put(InputDelivered(input=input, boundary=boundary, evidence="userMessage", native_id=id))

    def _started(self, item: Mapping[str, Any]) -> None:
        match item:
            case {"type": "userMessage"}:
                self._landed(item)
            case {"type": "contextCompaction"}:
                self._compacting = True
                self._measured = False
            case {"type": "fileChange", "id": id}:
                self._process.put(
                    Item(kind="patch", phase="started", gist=self._process.gist(_name(item)), native_id=id)
                )
            case {"type": type, "id": id} if type in _TOOLS:
                said = json.dumps(item["arguments"]) if "arguments" in item else None
                gist = self._process.gist(" ".join(filter(None, (_name(item), said))))
                self._process.put(Item(kind="tool", phase="started", gist=gist, native_id=id, body=said))

    def _completed(self, item: Mapping[str, Any]) -> None:
        match item:
            case {"type": "agentMessage", "id": id, "text": text}:
                self._process.put(Item(kind="message", gist=self._process.gist(text), native_id=id, body=text))
            case {"type": "reasoning", "id": id}:
                if text := "\n".join((*item.get("summary", ()), *item.get("content", ()))):
                    self._process.put(Item(kind="thought", gist=self._process.gist(text), native_id=id, body=text))
            case {"type": "plan", "id": id, "text": text}:
                self._process.put(Item(kind="thought", gist=self._process.gist(text), native_id=id, body=text))
            case {"type": "userMessage"}:
                pass
            case {"type": "contextCompaction"}:
                self._compacted()
            case {"type": "fileChange", "id": _}:
                self._process.put(self._finished("patch", item))
            case {"type": type, "id": _} if type in _TOOLS:
                self._process.put(self._finished("tool", item))
            case _:
                raise RpcError(METHOD_NOT_FOUND, f"nothing here takes an item of type {item['type']}")

    def _finished(self, kind: Literal["tool", "patch"], item: Mapping[str, Any]) -> Item:
        """A tool's end, by the harness's own word for it. One an approval let through is that approval's observed
        outcome, since accepting a command does not fix what comes of it."""
        id, outcome = item["id"], item.get("status")
        approval = self._deciding.pop(id, None)
        return Item(
            kind=kind,
            phase="completed",
            gist=self._process.gist(" ".join(filter(None, (_name(item), outcome)))),
            native_id=id,
            body=_output(item),
            approval=approval,
            outcome=outcome,
        )

    def _compacted(self) -> None:
        """What left the context and what took its place are not said, so both stay unknown. A provider that compacts
        on its side reports no usage for it, which leaves a call nobody saw."""
        self._compacting = False
        if not self._measured:
            self._process.put(ModelCall(purpose="compaction"), GapReport(what="hidden_call"))
        self._process.put(Compacted())

    def _used(self, thread: str, total: int) -> None:
        """One model call's worth, as what `total` rose by, since `last` comes again at an interrupt. No id goes with
        it. Out of a turn nothing was spent: a resume sends the old total."""
        spent, self._totals[thread] = total - self._totals.get(thread, 0), total
        if spent <= 0 or not self._turns:
            return
        ours = thread == self._native
        self._measured |= ours and self._compacting
        purpose = "compaction" if ours and self._compacting else None
        usage = Usage(tokens=spent, label="provider", scope="call" if ours else "tree")
        self._process.put(ModelCall(purpose=purpose), usage)

    def _ended(self, thread: str, turn: Mapping[str, Any]) -> None:
        """An end. Approvals of that turn go moot with it, and ours ends with the last thread still at work."""
        for id, asked in tuple(self._asking.items()):
            if asked.turn == turn["id"]:
                del self._asking[id]
                asked.verdict.cancel()
        self._turns.pop(thread, None)
        if thread == self._native:
            self._ending = self._reason(turn)
            if self._ending != "stopped":  # One cut short may have taken a call with it, of which Codex says nothing.
                self._process.put(Usage(label="unavailable", scope="call"), GapReport(what="usage_lower_bound"))
        if self._turns:
            return
        reason = "interrupted" if self._interrupted and self._ending == "stopped" else self._ending
        self._process.put(TurnEnded(reason=reason))
        self._interrupted, self._ending = False, "stopped"
        if reason != "stopped":
            self._unlanded.clear()

    def _reason(self, turn: Mapping[str, Any]) -> str:
        """Why a turn stopped. One cut short that nobody interrupted was aborted by the harness, which nobody did on
        purpose."""
        match turn:
            case {"status": "completed"}:
                return "stopped"
            case {"status": "interrupted"}:
                return "interrupted" if self._interrupted else "aborted"
            case {"error": {"message": str(said)}}:
                return self._process.reason(said)
            case _:
                return self._process.reason(str(turn.get("status")))
