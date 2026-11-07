"""The `claude` driver: `claude -p` in stream-json, with the control protocol on the same pipes.

A role runs in the user's own setup: this writes none of their configuration, and what it adds goes in beside theirs.
Every approval the harness asks for comes to the runtime, and a role's budget is what limits it.
"""

import asyncio
import json
from collections.abc import Coroutine, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4, uuid5

from platoon_harness.primitives import Verdict
from platoon_harness.rpc import Lines
from platoon_harness.tools.ph import TOKEN_VARIABLE

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
    keys_of,
    refuse_other_effort,
    refuse_unset_model,
    text_of,
)
from .env import harness_env, inherited, on_path, private
from .process import LOG, Process, status

_CLAUDE = "claude"
_LAUNCH = (
    _CLAUDE,
    "-p",
    "--input-format",
    "stream-json",
    "--output-format",
    "stream-json",
    "--verbose",
    "--include-partial-messages",
    "--permission-prompt-tool",
    "stdio",
    "--permission-mode",  # A user's `defaultMode` would answer before the runtime hears.
    "default",
)
_UNANSWERABLE = "AskUserQuestion"  # The prompt tool brings this in, and no verdict can answer it.
_OWN_WORKTREES = ("EnterWorktree", "ExitWorktree")  # Move the agent out of its workspace, where no look follows.
_NATIVE_CHILDREN = ("Agent", "Workflow", "ListAgents", "SendMessage")  # Start the harness's own agents, or reach them.
_ENVIRONMENT = {"CLAUDE_CODE_DISABLE_BACKGROUND_TASKS": "1"}
_SIGN_IN = (
    "CLAUDE_CONFIG_DIR",
    "HTTPS_PROXY",
    "HTTP_PROXY",
    "NO_PROXY",
    "https_proxy",
    "http_proxy",
    "no_proxy",
    "NODE_EXTRA_CA_CERTS",
)
_GATEWAY_URL = "ANTHROPIC_BASE_URL"
_GATEWAY_CREDENTIALS = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")
_LOGINS: Mapping[str, Login] = {"claude.ai": "plan", "api_key": "key"}
_INSTRUCTIONS = "instructions.md"
_SYNTHETIC = "<synthetic>"
_DENIED = "The runtime denied this."
_BESIDE = ("decision_reason", "blocked_path")
"""What a request for a tool says beside the tool's input, which a person allows too: why it asks, as a hook can say,
and the path that made it ask, such as one outside the folders it may reach."""
_SAYS_NOTHING = frozenset(
    {
        "rate_limit_event",
        "tool_progress",
        "system/api_retry",
        "system/task_notification",
        "system/task_progress",
        "system/task_updated",
        "system/thinking_tokens",
    }
)
_CAPABILITIES = Capabilities(
    persistent=True,
    resume=True,
    boundaries={"turn", "tool"},
    tool_paths={"mcp-http"},
    interrupt=True,
    approvals="native",
    native_children="observed",
    call_ids="call",
    dialects={"messages"},
    coverage={"prompt": "partial", "tool_results": "observed", "native_children": "partial", "compaction": "partial"},
    measures={"tokens", "usd"},
)

__all__ = ["ClaudeDriver"]


def _login() -> Login | None:
    """Which kind of login `claude` says it has, or None if it cannot tell. Only that field is read, since the rest
    of what it says can name an account."""
    done = status((_CLAUDE, "auth", "status", "--json"), inherited(*_SIGN_IN))
    if done is None:
        return None
    try:
        return _LOGINS.get(json.loads(done.stdout).get("authMethod"))
    except UNREADABLE:
        return None


def _call_tokens(usage: Mapping[str, Any]) -> int:
    """A call's tokens, from its parts. A part left out or null is not counted, and a whole of 0 is nobody's count."""
    parts = ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens", "output_tokens")
    return sum(usage.get(part) or 0 for part in parts)


def _tree_tokens(spent: Mapping[str, Any]) -> int:
    parts = ("inputTokens", "cacheReadInputTokens", "cacheCreationInputTokens", "outputTokens")
    return sum(model.get(part) or 0 for model in spent.values() for part in parts)


def _failed(server: Mapping[str, Any], namespace: str) -> bool:
    return server.get("name") == namespace and server.get("status") == "failed"


def _kind(frame: Any) -> str:
    """How a frame is known, whatever it is."""
    if not isinstance(frame, dict):
        return "frame"
    return "/".join(str(frame[key]) for key in ("type", "subtype") if key in frame) or "frame"


@dataclass
class _Call:
    """The model call under way: `id` once it streams, and what it has spent so far."""

    id: str | None = None
    usage: Mapping[str, Any] = field(default_factory=dict)


class ClaudeDriver:
    """One `claude -p` process. A turn runs from the input that began it to its `result`.

    Frames are translated on the read loop, which never waits, so the pipe drains. An agent is parked at turn end and
    never at its `wait` call, since Claude batches `wait` with sibling tools, and that is the runtime's to do.
    """

    def __init__(self) -> None:
        self._info: DriverInfo | None = None
        self._launched: Process | None = None
        self._lines = Lines(self._lost)
        self._native = ""
        self._folder = Path()
        self._config = Path()
        self._inputs: dict[str, str] = {}
        self._asking: dict[str, tuple[str, Any]] = {}
        self._deciding: dict[str, str] = {}
        self._tools: dict[str, str] = {}
        self._turn: str | None = None
        self._interrupted = False
        self._call: _Call | None = None
        self._counted = 0
        self._compacting = False

    def describe(self) -> DriverInfo:
        if self._info is None:
            self._info = DriverInfo(
                name=_CLAUDE, login=_login(), capabilities=_CAPABILITIES, installed=on_path(_CLAUDE)
            )
        return self._info

    async def start(self, spec: AgentSpec, report: Reporter) -> None:
        refuse_unset_model(spec)
        if spec.goal is not None and spec.goal.text.startswith("/"):
            raise DriverError("a goal that starts with `/` would run as a slash command: reword it")
        named = {*spec.env, *keys_of(spec)}
        if _GATEWAY_URL in named and not named.intersection(_GATEWAY_CREDENTIALS):
            raise DriverError(f"{_GATEWAY_URL} with no credential would send a saved login there: name one too")
        self._native = spec.resume or str(uuid4())
        self._folder = spec.folder
        spec.folder.mkdir(mode=0o700, parents=True, exist_ok=True)
        env = {**harness_env(spec, *_SIGN_IN), **_ENVIRONMENT}
        self._config = Path(env.get("CLAUDE_CONFIG_DIR") or Path(env.get("HOME", "")) / ".claude")
        self._launched = await Process.launch(self._command(spec), spec, report, read=self._read, env=env)
        self._lines.open(self._launched.stdin)
        await self._handshake(spec)
        if spec.goal is not None and spec.resume is None:
            await self.deliver(spec.goal)

    def _command(self, spec: AgentSpec) -> list[str]:
        """How this agent launches: one path, and its files are written first. The server's token stays in the
        environment, and argv, which any process can read, names only its variable."""
        disallowed = (_UNANSWERABLE, *_OWN_WORKTREES, *(() if spec.allow_native_children else _NATIVE_CHILDREN))
        command = [*_LAUNCH, "--disallowedTools", ",".join(disallowed)]
        command += ["--resume" if spec.resume else "--session-id", self._native]
        if spec.model is not None:
            command += ["--model", spec.model]
        if spec.effort is not None:
            command += ["--effort", spec.effort]
        if (tools := spec.tools) is not None:
            headers = {"Authorization": f"Bearer ${{{TOKEN_VARIABLE}}}"}
            server = {"type": "http", "url": tools.url, "headers": headers, "alwaysLoad": True}
            command += ["--mcp-config", json.dumps({"mcpServers": {tools.namespace: server}})]
            command += ["--allowedTools", f"mcp__{tools.namespace}__*"]
        if spec.instructions is not None:
            path = private(spec.folder, spec.folder / _INSTRUCTIONS, spec.instructions)
            command += ["--append-system-prompt-file", path]
        return command

    async def _handshake(self, spec: AgentSpec) -> None:
        """Ask what no frame says before the first turn. `initialize` is the handshake, and none of this calls a model.
        The harness warns of an effort it does not know and runs on, and of a server that failed, so both are refused
        here. A server that connected proves no model saw its tools, so what `ready` says of those stays unknown."""
        version = (await self._ask("initialize")).get("claude_code_version")
        applied = (await self._ask("get_settings")).get("applied", {})
        refuse_other_effort(spec, applied.get("effort"))
        if spec.tools is not None:
            servers = (await self._ask("mcp_status")).get("mcpServers", ())
            if any(_failed(server, spec.tools.namespace) for server in servers):
                raise DriverError(f"our tools did not connect, so it could reach nobody: see {self._folder / LOG}")
        self._process.put(Ready(native=self._native, version=version, effective_model=applied.get("model")))

    # What the harness is sent.

    def _user(self, text: str, id: str) -> dict[str, Any]:
        message = {"role": "user", "content": text}
        return {"type": "user", "session_id": "", "parent_tool_use_id": None, "uuid": id, "message": message}

    def _input_id(self, input: str) -> str:
        """The harness's id for an input, the same from any instance, so `reconcile` can find one after a crash."""
        return str(uuid5(UUID(self._native), input))

    def _lost(self) -> DriverError:
        return DriverError(f"{_CLAUDE} is gone: see {self._folder / LOG}")

    def _control(self, subtype: str, **fields: Any) -> dict[str, Any]:
        return {"type": "control_request", "request_id": uuid4().hex, "request": {"subtype": subtype, **fields}}

    async def _ask(self, subtype: str, **fields: Any) -> Mapping[str, Any]:
        frame = self._control(subtype, **fields)
        return await self._lines.exchange(frame["request_id"], frame)

    async def deliver(self, delivery: Delivery) -> None:
        """Hand the text over, and return when the harness says it is queued. It lands at the next tool boundary, or
        else as the next turn. A harness that has stopped reading holds this up until the host drops it, and what was
        written stays in the pipe, to land if it ever reads again."""
        id = self._input_id(delivery.input)
        self._inputs[id] = delivery.input
        await self._lines.exchange(id, self._user(delivery.text, id))

    async def interrupt(self) -> None:
        """Stop the turn, or the one an input on its way is about to begin. The harness drops what it has queued, which
        the runtime offers again, as it would begin a turn by itself otherwise, and it has done both by the time it
        answers, so a turn open then is the one cut, and one that ends with no turn open labels nothing."""
        self._interrupted = True
        try:
            await self._ask("interrupt", cancel_queued=True)
        finally:
            self._interrupted = self._turn is not None

    async def answer(self, approval: str, verdict: Verdict) -> None:
        if approval not in self._asking:
            raise DriverError(f"no approval {approval} is waiting")
        tool, input = self._asking.pop(approval)
        self._deciding[tool] = approval
        reply = {"behavior": "allow", "updatedInput": input}
        if verdict == "deny":
            reply = {"behavior": "deny", "message": _DENIED}
        response = {"subtype": "success", "request_id": approval, "response": reply}
        await self._lines.send({"type": "control_response", "response": response})

    async def reconcile(self, input_id: str) -> Reconciled:
        """What came of an input after a crash is in the harness's own transcript, the one record that survives it. Its
        format is internal, so a miss proves nothing, and this never says `not_landed`."""
        needle = f'"uuid":"{self._input_id(input_id)}"'

        def found() -> bool:
            paths = self._config.glob(f"projects/*/{self._native}.jsonl")
            return any(needle in path.read_text(errors="replace") for path in paths)

        return "landed" if await asyncio.to_thread(found) else "unknown"

    async def stop(self, grace: float) -> None:
        """Ask first, then end what is left: only the harness can end a tool that leads a group of its own, and stdin
        ending does not stop a running one. It exits 1 after this, which is normal."""
        if self._launched is None:
            return
        if self._turn is not None or self._inputs:
            self._lines.write(self._control("interrupt", cancel_queued=True))
        await self._launched.stop(grace)

    # What the harness says.

    @property
    def _process(self) -> Process:
        if self._launched is None:
            raise DriverError("this driver has not started")
        return self._launched

    def _read(self, process: Process) -> Coroutine[Any, Any, None]:
        return self._lines.run(process.stdout, self._heard)

    def _heard(self, line: bytes) -> None:
        """One line. Whatever cannot be read is an unknown frame, whichever part of it would not read, and still the
        harness's request gets its answer, and a turn's end ends the turn."""
        frame = None
        try:
            frame = json.loads(line)
            self._take(frame, line)
        except UNREADABLE:
            self._process.unknown(_kind(frame), line.decode(errors="replace"))
            match frame:
                case {"type": "control_request", "request_id": id}:
                    self._refuse(id)
                case {"type": "result"} if self._turn is not None:
                    self._turn_over("its end could not be read")

    def _take(self, frame: Any, line: bytes) -> None:
        match frame:
            case {"type": "control_response", "response": {"request_id": id} as response}:
                self._answered(id, response)
            case {
                "type": "control_request",
                "request_id": str(id),
                "request": {
                    "subtype": "can_use_tool",
                    "tool_name": str(name),
                    "input": input,
                    "tool_use_id": str(tool),
                } as request,
            }:
                self._asking[id] = (tool, input)
                said = f"{name} {json.dumps(input)}"
                beside = "".join(f"{key}: {request[key]}\n" for key in _BESIDE if request.get(key) is not None)
                self._process.put(ApprovalRequested(id=id, gist=self._process.gist(said), body=beside + said))
            case {"type": "control_request", "request_id": id}:
                self._refuse(id)
                self._process.unknown(_kind(frame), line.decode(errors="replace"))
            case {"type": "control_cancel_request", "request_id": id}:
                self._asking.pop(id, None)
            case {"parent_tool_use_id": str()}:
                pass  # A native child's own work, which its `task_started` and the usage at `result` stand for.
            case {"type": "command_lifecycle", "state": "queued", "command_uuid": id}:
                self._lines.settle(id, {})
            case {"type": "command_lifecycle", "state": "started", "command_uuid": id}:
                self._landed(id)
            case {"type": "command_lifecycle", "state": "cancelled", "command_uuid": id}:
                self._inputs.pop(id, None)
            case {"type": "command_lifecycle"}:
                pass
            case {"type": "stream_event", "event": event}:
                self._streamed(event)
            case {"type": "assistant", "message": {"id": id, "content": list(blocks)} as message}:
                self._said(blocks, None if message.get("model") == _SYNTHETIC else id)
            case {"type": "user", "isSynthetic": True, "message": {"content": str(summary)}} if self._compacting:
                self._compacted(summary)
            case {"type": "user", "message": {"content": list(blocks)}}:
                self._results(blocks)
            case {"type": "user"}:
                pass
            case {"type": "result"}:
                self._ended(frame)
            case {"type": "system", "subtype": "init", "uuid": id}:
                self._begin(id)
            case {"type": "system", "subtype": "status", "status": "requesting"}:
                self._call = _Call()
            case {"type": "system", "subtype": "status", "status": "compacting"}:
                self._process.put(ModelCall(purpose="compaction"))
            case {"type": "system", "subtype": "status"}:
                pass
            case {"type": "system", "subtype": "compact_boundary"}:
                self._compacting = True
            case {
                "type": "system",
                "subtype": "task_started",
                "task_type": "local_agent",
                "is_backgrounded": False,
                "task_id": id,
                "tool_use_id": parent,
            }:
                self._process.put(
                    ChildSeen(native=id, parent=parent),
                    GapReport(what="native_child_unattributed"),
                )
            case _ if _kind(frame) not in _SAYS_NOTHING:
                self._process.unknown(_kind(frame), line.decode(errors="replace"))

    def _answered(self, id: str, response: Mapping[str, Any]) -> None:
        """An answer to a request of ours."""
        if response.get("subtype") == "success":
            self._lines.settle(id, response.get("response") or {})
        else:
            self._lines.settle(id, DriverError(str(response.get("error"))))

    def _refuse(self, id: str) -> None:
        """Answer what nobody here can, since the harness is waiting on it."""
        response = {"subtype": "error", "request_id": id, "error": "nothing here answers this"}
        self._lines.write({"type": "control_response", "response": response})

    def _landed(self, id: str) -> None:
        """An input left the harness's queue: at a tool boundary inside a turn, or as a new one."""
        input = self._inputs.pop(id, None)
        if input is not None:
            boundary = "turn" if self._turn is None else "tool"
            self._process.put(
                InputDelivered(input=input, boundary=boundary, evidence="command_lifecycle", native_id=id)
            )
        self._begin(id)

    def _begin(self, id: str) -> None:
        """A turn began, whether an input began it or the harness did."""
        if self._turn is None:
            self._turn = id
            self._process.put(TurnStarted(turn=id))

    def _streamed(self, event: Mapping[str, Any]) -> None:
        match event:
            case {"type": "message_start", "message": {"id": id} as message}:
                self._call = _Call(id, message.get("usage", {}))
                self._process.put(ModelCall(call_id=id, model=message.get("model")))
            case {"type": "content_block_delta", "delta": {"type": "text_delta", "text": text}}:
                self._process.put(Delta(text=text))
            case {"type": "message_delta", "delta": {"stop_reason": str()}, "usage": usage} if self._call is not None:
                tokens = _call_tokens({**self._call.usage, **usage})
                self._counted += tokens
                label = "provider" if tokens else "unavailable"
                self._process.put(Usage(tokens=tokens or None, label=label, scope="call", call_id=self._call.id))
                self._call = None

    def _said(self, blocks: Sequence[Any], call_id: str | None) -> None:
        for block in blocks:
            match block:
                case {"type": "text", "text": text}:
                    item = Item(kind="message", gist=self._process.gist(text), body=text, call_id=call_id)
                    self._process.put(item)
                case {"type": "thinking", "thinking": text}:
                    if text:
                        self._process.put(
                            Item(kind="thought", gist=self._process.gist(text), body=text, call_id=call_id)
                        )
                case {"type": "tool_use", "id": id, "name": name, "input": input}:
                    self._tools[id] = name
                    said = json.dumps(input)
                    gist = self._process.gist(f"{name} {said}")
                    self._process.put(
                        Item(kind="tool", phase="started", gist=gist, native_id=id, call_id=call_id, body=said)
                    )
                case _:
                    self._process.unknown("assistant", json.dumps(block))

    def _results(self, blocks: Sequence[Any]) -> None:
        """A tool's end. One an approval let through is that approval's observed outcome."""
        for block in blocks:
            match block:
                case {"type": "tool_result", "tool_use_id": id}:
                    outcome = "failed" if block.get("is_error") else "completed"
                    approval = self._deciding.pop(id, None)
                    item = Item(
                        kind="tool",
                        phase="completed",
                        gist=self._process.gist(f"{self._tools.pop(id, 'tool')} {outcome}"),
                        native_id=id,
                        body=text_of(block.get("content") or ""),
                        approval=approval,
                        outcome=outcome,
                    )
                    self._process.put(item)

    def _compacted(self, summary: str | None) -> None:
        """What left the context is not named, so that stays unknown, and the runtime records the gap."""
        self._compacting = False
        self._process.put(Compacted(summary=summary))

    def _ended(self, frame: Mapping[str, Any]) -> None:
        """The end of a turn: the last of its cost, then why it stopped."""
        if self._turn is None:
            return
        if self._compacting:
            self._compacted(None)
        if (call := self._call) is not None:  # One the harness stopped hearing, so nobody can say what it spent.
            if call.id is None:
                self._process.put(ModelCall())
            self._process.put(Usage(label="unavailable", scope="call", call_id=call.id))
            self._call = None
        self._spent(frame.get("model_usage_since_last_result"))
        self._turn_over(self._reason(frame))

    def _turn_over(self, reason: str) -> None:
        self._process.put(TurnEnded(reason=reason))
        self._turn = None
        self._interrupted = False
        self._counted = 0

    def _spent(self, spent: Mapping[str, Any] | None) -> None:
        """What no call said: a native child's, and a compaction's. Dollars are the harness's own estimate. With none of
        it said, what the calls said is a lower bound on the turn."""
        if spent is None:
            self._process.put(Usage(label="lower_bound", scope="tree"))
            self._process.put(GapReport(what="usage_lower_bound"))
            return
        if (tokens := _tree_tokens(spent) - self._counted) > 0:
            self._process.put(Usage(tokens=tokens, label="provider", scope="tree"))
        if usd := sum(model.get("costUSD", 0.0) for model in spent.values()):
            self._process.put(Usage(usd=usd, label="estimated", scope="tree"))

    def _reason(self, frame: Mapping[str, Any]) -> str:
        if not frame.get("is_error"):
            return "stopped"
        if self._interrupted:
            return "interrupted"
        said = frame.get("result") or next(iter(frame.get("errors", ())), None)
        reason = ": ".join(str(part) for part in (frame.get("terminal_reason"), said) if part)
        return self._process.reason(reason or str(frame.get("subtype")))
