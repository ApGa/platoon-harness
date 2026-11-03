"""The `claude` driver: `claude -p` in stream-json, with the control protocol on the same pipes.

A role runs in the user's own setup: this writes none of their configuration, and what it adds goes in beside theirs.
Every approval the harness asks for comes to the runtime, and a role's budget is what limits it.
"""

import asyncio
import contextlib
import json
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4, uuid5

from platoon_harness.kernel import GIST_LIMIT
from platoon_harness.primitives import Verdict
from platoon_harness.rpc import read_lines

from . import (
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
    Report,
    Reporter,
    TurnEnded,
    TurnStarted,
    Usage,
    unknown_frame,
)
from .env import harness_env, inherited, private, refuse_unset_model, signed_in
from .process import LOG, Process

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
)
_ENVIRONMENT = {"CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1", "CLAUDE_CODE_DISABLE_BACKGROUND_TASKS": "1"}
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
_STATUS_SECONDS = 5.0
_SERVERS = "mcp.json"
_INSTRUCTIONS = "instructions.md"
_REASON_LIMIT = 256
_SYNTHETIC = "<synthetic>"
_DENIED = "The runtime denied this."
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
    command = (_CLAUDE, "auth", "status", "--json")
    env = {**inherited(), **signed_in(_SIGN_IN)}
    try:
        done = subprocess.run(command, capture_output=True, env=env, timeout=_STATUS_SECONDS, check=False)
        return _LOGINS.get(json.loads(done.stdout).get("authMethod"))
    except (OSError, subprocess.TimeoutExpired, ValueError, AttributeError, TypeError):
        return None


def _call_tokens(usage: Mapping[str, Any]) -> int:
    parts = ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens", "output_tokens")
    return sum(usage.get(part, 0) for part in parts)


def _tree_tokens(spent: Mapping[str, Any]) -> int:
    parts = ("inputTokens", "cacheReadInputTokens", "cacheCreationInputTokens", "outputTokens")
    return sum(model.get(part, 0) for model in spent.values() for part in parts)


def _text(content: str | Sequence[Mapping[str, Any]]) -> str:
    """What a tool result says, in either of its shapes."""
    if isinstance(content, str):
        return content
    return "\n".join(block["text"] for block in content if "text" in block)


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
        self._process: Process | None = None
        self._native = ""
        self._folder = Path()
        self._config = Path()
        self._gone: DriverError | None = None
        self._answers: dict[str, asyncio.Future[Mapping[str, Any]]] = {}
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
            self._info = DriverInfo(name=_CLAUDE, login=_login(), capabilities=_CAPABILITIES)
        return self._info

    async def start(self, spec: AgentSpec, report: Reporter) -> None:
        refuse_unset_model(spec)
        named = {*spec.env, *spec.access}
        if _GATEWAY_URL in named and not named.intersection(_GATEWAY_CREDENTIALS):
            raise DriverError(f"{_GATEWAY_URL} with no credential would send a saved login there: name one too")
        self._native = spec.resume or str(uuid4())
        self._folder = spec.folder
        spec.folder.mkdir(mode=0o700, parents=True, exist_ok=True)
        launched = spec.model_copy(update={"env": {**signed_in(_SIGN_IN), **_ENVIRONMENT, **spec.env}})
        env = harness_env(launched)
        self._config = Path(env.get("CLAUDE_CONFIG_DIR") or Path(env.get("HOME", "")) / ".claude")
        self._process = await Process.launch(self._command(spec), launched, report, read=self._read)
        await self._handshake(spec)
        if spec.goal and spec.resume is None:
            await self._send(self._user(spec.goal, str(uuid4())))

    def _command(self, spec: AgentSpec) -> list[str]:
        """How this agent launches: one path, and its files are written first. The server's token is in a file, and
        never in argv, where any process could read it."""
        command = [*_LAUNCH, "--resume" if spec.resume else "--session-id", self._native]
        if spec.model is not None:
            command += ["--model", spec.model]
        if spec.effort is not None:
            command += ["--effort", spec.effort]
        if (tools := spec.tools) is not None:
            headers = {"Authorization": f"Bearer {tools.token.reveal()}"}
            server = {"type": "http", "url": tools.url, "headers": headers, "alwaysLoad": True}
            servers = json.dumps({"mcpServers": {tools.namespace: server}})
            command += ["--mcp-config", private(spec.folder / _SERVERS, servers)]
            command += ["--allowedTools", f"mcp__{tools.namespace}__*"]
        if spec.instructions is not None:
            command += ["--append-system-prompt-file", private(spec.folder / _INSTRUCTIONS, spec.instructions)]
        return command

    async def _handshake(self, spec: AgentSpec) -> None:
        """Ask what no frame says before the first turn. `initialize` is the handshake, and none of this calls a model.
        The harness warns of an effort it does not know and runs on, so that is refused here."""
        version = (await self._ask("initialize")).get("claude_code_version")
        applied = (await self._ask("get_settings")).get("applied", {})
        if spec.effort not in (None, applied.get("effort")):
            raise DriverError(f"it runs at effort {applied.get('effort')}, and {spec.effort} was asked for")
        ready = Ready(
            native=self._native,
            version=version,
            effective_model=applied.get("model"),
            tools_visible=await self._tools_visible(spec),
        )
        self._report(ready)

    async def _tools_visible(self, spec: AgentSpec) -> tuple[str, ...] | None:
        """A connected server proves no model saw its tools, so that stays unknown. A failed one proves none did."""
        if spec.tools is None:
            return None
        servers = (await self._ask("mcp_status")).get("mcpServers", ())
        ours = (server.get("status") for server in servers if server.get("name") == spec.tools.namespace)
        return () if "failed" in ours else None

    # What the harness is sent.

    def _user(self, text: str, id: str) -> dict[str, Any]:
        message = {"role": "user", "content": text}
        return {"type": "user", "session_id": "", "parent_tool_use_id": None, "uuid": id, "message": message}

    def _input_id(self, input: str) -> str:
        """The harness's id for an input, the same from any instance, so `reconcile` can find one after a crash."""
        return str(uuid5(UUID(self._native), input))

    async def _send(self, frame: Mapping[str, Any]) -> None:
        if self._process is None:
            raise DriverError("this driver has not started")
        if self._gone is not None:
            raise self._gone
        try:
            self._process.stdin.write(json.dumps(frame).encode() + b"\n")
            await self._process.stdin.drain()
        except ConnectionError as error:
            raise self._lost() from error

    def _lost(self) -> DriverError:
        return DriverError(f"{_CLAUDE} is gone: see {self._folder / LOG}")

    async def _exchange(self, id: str, frame: Mapping[str, Any]) -> Mapping[str, Any]:
        """Send a frame and wait for the harness to answer to its id."""
        answer: asyncio.Future[Mapping[str, Any]] = asyncio.get_running_loop().create_future()
        self._answers[id] = answer
        try:
            await self._send(frame)
            return await answer
        finally:
            del self._answers[id]

    async def _ask(self, subtype: str) -> Mapping[str, Any]:
        id = uuid4().hex
        return await self._exchange(id, {"type": "control_request", "request_id": id, "request": {"subtype": subtype}})

    async def deliver(self, delivery: Delivery) -> None:
        """Hand the text over, and return when the harness says it is queued. It lands at the next tool boundary, or
        else as the next turn. A harness that has stopped reading holds this up until the host drops it, and what was
        written stays in the pipe, to land if it ever reads again."""
        id = self._input_id(delivery.input)
        self._inputs[id] = delivery.input
        await self._exchange(id, self._user(delivery.text, id))

    async def interrupt(self) -> None:
        """Stop the turn. What is queued stays queued, so nothing handed over is lost, and it begins the next turn."""
        self._interrupted = self._turn is not None
        await self._ask("interrupt")

    async def answer(self, approval: str, verdict: Verdict) -> None:
        if approval not in self._asking:
            raise DriverError(f"no approval {approval} is waiting")
        tool, input = self._asking.pop(approval)
        self._deciding[tool] = approval
        reply = {"behavior": "allow", "updatedInput": input}
        if verdict == "deny":
            reply = {"behavior": "deny", "message": _DENIED}
        response = {"subtype": "success", "request_id": approval, "response": reply}
        await self._send({"type": "control_response", "response": response})

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
        if self._process is None:
            return
        with contextlib.suppress(DriverError, TimeoutError):
            async with asyncio.timeout(grace):
                if self._turn is not None:
                    await self._ask("interrupt")
                self._process.stdin.close()
                await self._process.exited()
        await self._process.stop(grace)
        (self._folder / _SERVERS).unlink(missing_ok=True)

    # What the harness says.

    def _report(self, *reports: Report) -> None:
        assert self._process is not None
        for report in reports:
            self._process.put(report)

    def _gist(self, text: str) -> str:
        assert self._process is not None
        return self._process.redact(text)[:GIST_LIMIT]

    def _unknown(self, kind: str, raw: str) -> None:
        assert self._process is not None
        self._report(*unknown_frame(kind[:_REASON_LIMIT], self._process.redact(raw)))

    async def _read(self, process: Process) -> None:
        """Translate every line, and when none are left, tell whoever waits on an answer."""
        try:
            async for line in read_lines(process.stdout):
                self._heard(line)
        finally:
            self._gone = self._lost()
            for answer in self._answers.values():
                if not answer.done():
                    answer.set_exception(self._gone)

    def _heard(self, line: bytes) -> None:
        if not line.strip():
            return
        try:
            frame = json.loads(line)
        except (ValueError, RecursionError):
            self._unknown("frame", line.decode(errors="replace"))
            return
        match frame:
            case {"type": "control_response", "response": {"request_id": id} as response}:
                self._answered(id, response)
            case {
                "type": "control_request",
                "request_id": id,
                "request": {"subtype": "can_use_tool", "tool_name": name, "input": input, "tool_use_id": tool},
            }:
                self._asking[id] = (tool, input)
                self._report(ApprovalRequested(id=id, gist=self._gist(f"{name} {json.dumps(input)}")))
            case {"type": "control_request", "request_id": id}:
                self._refuse(id)
                self._unknown(_kind(frame), line.decode(errors="replace"))
            case {"type": "control_cancel_request", "request_id": id}:
                self._asking.pop(id, None)
            case {"parent_tool_use_id": str()}:
                pass  # A native child's own work, which its `task_started` and the usage at `result` stand for.
            case {"type": "command_lifecycle", "state": "queued", "command_uuid": id}:
                self._answered(id, {"subtype": "success"})
            case {"type": "command_lifecycle", "state": "started", "command_uuid": id}:
                self._landed(id)
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
                self._report(ModelCall(purpose="compaction"))
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
                self._report(
                    ChildSeen(native=id, parent=parent, attribution="inferred"),
                    GapReport(plane="model", what="native_child_unattributed"),
                )
            case _ if _kind(frame) not in _SAYS_NOTHING:
                self._unknown(_kind(frame), line.decode(errors="replace"))

    def _answered(self, id: str, response: Mapping[str, Any]) -> None:
        """An answer to a request of ours. One nobody waits for any more has nobody to reach."""
        answer = self._answers.get(id)
        if answer is None or answer.done():
            return
        if response.get("subtype") == "success":
            answer.set_result(response.get("response") or {})
        else:
            answer.set_exception(DriverError(str(response.get("error"))))

    def _refuse(self, id: str) -> None:
        """Answer what nobody here can, since the harness is waiting on it. This writes and does not wait."""
        assert self._process is not None
        response = {"subtype": "error", "request_id": id, "error": "nothing here answers this"}
        self._process.stdin.write(json.dumps({"type": "control_response", "response": response}).encode() + b"\n")

    def _landed(self, id: str) -> None:
        """An input left the harness's queue: at a tool boundary inside a turn, or as a new one."""
        input = self._inputs.pop(id, None)
        if input is not None:
            boundary = "turn" if self._turn is None else "tool"
            self._report(InputDelivered(input=input, boundary=boundary, evidence="command_lifecycle", native_id=id))
        self._begin(id)

    def _begin(self, id: str) -> None:
        """A turn began, whether an input began it or the harness did."""
        if self._turn is None:
            self._turn = id
            self._report(TurnStarted(turn=id))

    def _streamed(self, event: Mapping[str, Any]) -> None:
        match event:
            case {"type": "message_start", "message": {"id": id} as message}:
                self._call = _Call(id, message.get("usage", {}))
                self._report(ModelCall(call_id=id, model=message.get("model")))
            case {"type": "content_block_delta", "delta": {"type": "text_delta", "text": text}}:
                self._report(Delta(text=text))
            case {"type": "message_delta", "delta": {"stop_reason": str()}, "usage": usage} if self._call is not None:
                tokens = _call_tokens({**self._call.usage, **usage})
                self._counted += tokens
                self._report(Usage(tokens=tokens, label="provider", scope="call", call_id=self._call.id))
                self._call = None

    def _said(self, blocks: Sequence[Any], call_id: str | None) -> None:
        for block in blocks:
            match block:
                case {"type": "text", "text": text}:
                    item = Item(kind="message", gist=self._gist(text), body=text, call_id=call_id)
                    self._report(item)
                case {"type": "thinking", "thinking": text}:
                    if text:
                        self._report(Item(kind="thought", gist=self._gist(text), body=text, call_id=call_id))
                case {"type": "tool_use", "id": id, "name": name, "input": input}:
                    self._tools[id] = name
                    said = json.dumps(input)
                    gist = self._gist(f"{name} {said}")
                    self._report(
                        Item(kind="tool", phase="started", gist=gist, native_id=id, call_id=call_id, body=said)
                    )
                case _:
                    self._unknown("assistant", json.dumps(block))

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
                        gist=self._gist(f"{self._tools.pop(id, 'tool')} {outcome}"),
                        native_id=id,
                        body=_text(block.get("content") or ""),
                        approval=approval,
                        outcome=outcome,
                    )
                    self._report(item)

    def _compacted(self, summary: str | None) -> None:
        """What left the context is not named, so that stays unknown, and the runtime records the gap."""
        self._compacting = False
        self._report(Compacted(summary=summary))

    def _ended(self, frame: Mapping[str, Any]) -> None:
        """The end of a turn: the last of its cost, then why it stopped."""
        if self._turn is None:
            return
        if self._compacting:
            self._compacted(None)
        if (call := self._call) is not None:  # One the harness stopped hearing, so nobody can say what it spent.
            if call.id is None:
                self._report(ModelCall())
            self._report(Usage(label="unavailable", scope="call", call_id=call.id))
            self._call = None
        self._spent(frame.get("model_usage_since_last_result"))
        self._report(TurnEnded(reason=self._reason(frame)))
        self._turn = None
        self._interrupted = False
        self._counted = 0

    def _spent(self, spent: Mapping[str, Any] | None) -> None:
        """What no call said: a native child's, and a compaction's. Dollars are the harness's own estimate."""
        if spent is None:
            self._report(GapReport(plane="model", what="usage_lower_bound"))
            return
        if (tokens := _tree_tokens(spent) - self._counted) > 0:
            self._report(Usage(tokens=tokens, label="provider", scope="tree"))
        if usd := sum(model.get("costUSD", 0.0) for model in spent.values()):
            self._report(Usage(usd=usd, label="estimated", scope="tree"))

    def _reason(self, frame: Mapping[str, Any]) -> str:
        if not frame.get("is_error"):
            return "stopped"
        if self._interrupted:
            return "interrupted"
        assert self._process is not None
        said = frame.get("result") or next(iter(frame.get("errors", ())), None)
        reason = ": ".join(str(part) for part in (frame.get("terminal_reason"), said) if part)
        return self._process.redact(reason or str(frame.get("subtype")))[:_REASON_LIMIT]
