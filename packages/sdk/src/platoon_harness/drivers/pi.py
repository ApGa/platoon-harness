"""The `pi` driver: `pi --mode rpc`, JSON records on stdio, with a response to each command and events between.

A role runs in the user's own setup: pi keeps its own agent directory, so their login, settings and extensions stay
theirs, and what we add comes in beside them, by the one extension `-e` loads. Pi asks for no approval of its own, so
that extension asks, and every approval comes to the runtime. A role's budget is what limits it.
"""

import asyncio
import contextlib
import json
import subprocess
import sys
from collections.abc import Coroutine, Mapping, Sequence
from pathlib import Path
from typing import Any
from uuid import uuid4

from platoon_harness.kernel import GIST_LIMIT
from platoon_harness.primitives import Verdict
from platoon_harness.rpc import read_lines
from platoon_harness.tools import SHIM, delivery_heading

from . import (
    AgentSpec,
    ApprovalRequested,
    Boundary,
    Capabilities,
    Compacted,
    Delivery,
    Delta,
    DriverError,
    DriverInfo,
    InputDelivered,
    Item,
    Login,
    ModelCall,
    Ready,
    Receipt,
    Reconciled,
    Report,
    Reporter,
    Started,
    TurnEnded,
    TurnStarted,
    Usage,
    unknown_frame,
)
from .env import harness_env, inherited, private, refuse_unset_model, signed_in
from .process import LOG, Process

_PI = "pi"
_EXTENSION = Path(__file__).with_name("pi_extension.js")
_EXTENSION_CONFIG = "PLATOON_HARNESS_PI"
_ENVIRONMENT = {"PI_OFFLINE": "1", "PI_TELEMETRY": "0", "PI_SKIP_VERSION_CHECK": "1"}
_SIGN_IN = (
    "PI_CODING_AGENT_DIR",
    "PI_CODING_AGENT_SESSION_DIR",
    "HTTPS_PROXY",
    "HTTP_PROXY",
    "ALL_PROXY",
    "NO_PROXY",
    "https_proxy",
    "http_proxy",
    "all_proxy",
    "no_proxy",
    "NODE_EXTRA_CA_CERTS",
)
_BASE_URL = "OPENAI_BASE_URL"
_KEY = "OPENAI_API_KEY"
_PROVIDER = "platoon-harness"
_LOGINS: Mapping[str, Login] = {"oauth": "plan", "api_key": "key"}
_STATUS_SECONDS = 5.0
_TOOL_TIMEOUT_S = 600.0
_NO_PRICE = {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0}
_INSTRUCTIONS = "instructions.md"
_REASON_LIMIT = 256
_DIALOGS = frozenset({"select", "input", "editor"})
_IN_CONTEXT = frozenset({"message", "custom_message", "branch_summary"})
_SAYS_NOTHING = frozenset(
    {
        "agent_end",
        "auto_retry_end",
        "auto_retry_start",
        "bash_execution_update",
        "compaction_start",
        "entry_appended",
        "extension_ui_request",
        "message_end",
        "message_start",
        "message_update",
        "queue_update",
        "session_info_changed",
        "summarization_retry_attempt_start",
        "summarization_retry_finished",
        "summarization_retry_scheduled",
        "thinking_level_changed",
        "tool_execution_update",
        "turn_end",
        "turn_start",
    }
)
_CAPABILITIES = Capabilities(
    persistent=True,
    resume=True,
    boundaries={"turn", "model_call"},
    tool_paths={"mcp-stdio"},
    tool_timeout_s=_TOOL_TIMEOUT_S,
    interrupt="turn",
    approvals="gated",
    call_ids="call",
    dialects={"chat"},
    coverage={"prompt": "partial", "tool_results": "observed", "compaction": "observed"},
    measures={"tokens", "usd"},
)

__all__ = ["PiDriver"]


def _login() -> Login | None:
    """Which kind of login pi holds for the provider its settings name, or None if it cannot tell. Asking takes a
    provider. Only that field is read, and it fetches no credential and refreshes none."""
    env = {**inherited(), **signed_in(_SIGN_IN), **_ENVIRONMENT}
    home = env.get("PI_CODING_AGENT_DIR") or Path(env.get("HOME", "")) / ".pi" / "agent"
    try:
        provider = json.loads((Path(home).expanduser() / "settings.json").read_text())["defaultProvider"]
        command = (_PI, "auth", "check", "--provider", provider, "--json", "--no-refresh")
        done = subprocess.run(command, capture_output=True, env=env, timeout=_STATUS_SECONDS, check=False)
        return _LOGINS.get(json.loads(done.stdout).get("authType"))
    except (OSError, subprocess.TimeoutExpired, ValueError, KeyError, AttributeError, TypeError):
        return None


def _version(env: Mapping[str, str]) -> str | None:
    """What pi says of itself, since no record does."""
    try:
        done = subprocess.run((_PI, "--version"), capture_output=True, env=env, timeout=_STATUS_SECONDS, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return done.stdout.decode(errors="replace").strip() or None


def _extension_config(spec: AgentSpec) -> str:
    """What the extension adds for this agent, with the file of instructions it reads. Our tools go through the stdio
    shim on this very interpreter, so that each call has an id of its own, and the token stays in the environment."""
    config: dict[str, Any] = {}
    if spec.instructions is not None:
        config["instructions"] = private(spec.folder / _INSTRUCTIONS, spec.instructions)
    if spec.tools is not None:
        config["namespace"] = spec.tools.namespace
        config["server"] = {
            "command": sys.executable,
            "args": ["-I", str(SHIM)],
            "exposure": "direct",
            "timeout": _TOOL_TIMEOUT_S,
        }
    if _BASE_URL in spec.access:
        model = {"id": spec.model, "reasoning": spec.effort is not None, "input": ["text"], "cost": _NO_PRICE}
        url = spec.access[_BASE_URL].reveal()
        settings = {"baseUrl": url, "apiKey": f"${_KEY}", "api": "openai-completions", "models": [model]}
        config["provider"] = [_PROVIDER, settings]
    return json.dumps(config)


def _kind(frame: Any) -> str:
    """How a frame is known, whatever it is."""
    kind = frame.get("type") if isinstance(frame, dict) else None
    return kind if isinstance(kind, str) else "frame"


def _text(content: str | Sequence[Mapping[str, Any]]) -> str:
    """What a message or a tool's result says, in either of its shapes."""
    if isinstance(content, str):
        return content
    return "\n".join(block["text"] for block in content if "text" in block)


def _forgotten(entries: Sequence[Mapping[str, Any]], leaf: str, first_kept: str) -> tuple[str, ...] | None:
    """What a compaction took out of the context, which names only what it kept: on the branch that ended at `leaf`,
    the messages from the one before's first kept entry up to this one's."""
    entry_of = {entry["id"]: entry for entry in entries}
    path = [entry_of[leaf]]
    while (parent := path[-1].get("parentId")) is not None:
        path.append(entry_of[parent])
    path.reverse()
    ids = [entry["id"] for entry in path]
    kept = [entry["firstKeptEntryId"] for entry in path if entry["type"] == "compaction"]
    if first_kept not in ids or first_kept not in kept:
        return None
    earlier = kept[: kept.index(first_kept)]
    span = path[ids.index(earlier[-1]) if earlier else 0 : ids.index(first_kept)]
    left = (entry for entry in span if entry["type"] in _IN_CONTEXT)
    return tuple(entry["id"] for entry in left if entry.get("message", {}).get("role") != "system")


class PiDriver:
    """One `pi --mode rpc` process. A turn runs from the first `agent_start` to `agent_settled`, since retries, a
    compaction and queued input can each follow an `agent_end`.

    Frames are translated on the read loop, which never waits, so the pipe drains. An agent is parked at turn end, which
    is the runtime's to do.
    """

    def __init__(self) -> None:
        self._info: DriverInfo | None = None
        self._process: Process | None = None
        self._native = ""
        self._folder = Path()
        self._gone: DriverError | None = None
        self._answers: dict[str, asyncio.Future[Mapping[str, Any]]] = {}
        self._turn: str | None = None
        self._opening = False
        self._failure: str | None = None
        self._unlanded: dict[str, str] = {}
        self._calls: dict[str, str | None] = {}
        self._tools: dict[str, str] = {}
        self._asking: dict[str, str | None] = {}
        self._deciding: dict[str, str] = {}
        self._later: set[asyncio.Task[None]] = set()

    def describe(self) -> DriverInfo:
        if self._info is None:
            self._info = DriverInfo(name=_PI, login=_login(), capabilities=_CAPABILITIES)
        return self._info

    async def start(self, spec: AgentSpec, report: Reporter) -> Started:
        refuse_unset_model(spec)
        if _BASE_URL in spec.access and _KEY not in spec.access:
            raise DriverError(f"{_BASE_URL} with no {_KEY} would reach nobody's model: name one too")
        self._native = spec.resume or str(uuid4())
        self._folder = spec.folder
        spec.folder.mkdir(mode=0o700, parents=True, exist_ok=True)
        own = {**signed_in(_SIGN_IN), **_ENVIRONMENT, _EXTENSION_CONFIG: _extension_config(spec), **spec.env}
        launched = spec.model_copy(update={"env": own})
        await Process.launch(self._command(spec), launched, report, read=self._read)
        await self._handshake(spec, await asyncio.to_thread(_version, harness_env(launched)))
        if spec.goal and spec.resume is None:
            await self._hand_over(spec.goal, "turn")
        return Started(native=self._native)

    def _command(self, spec: AgentSpec) -> list[str]:
        """How this agent launches. `--session-id` makes a session under an id we chose, so `native` is known before
        launch, and `--session` finds one or exits. Pi writes the session down at its first prompt, so one that took no
        turn cannot be found. A provider of the agent's own is named, or `--model` would pick among the user's."""
        command = [_PI, "--mode", "rpc", "--session" if spec.resume else "--session-id", self._native]
        command += ["-e", str(_EXTENSION)]
        if _BASE_URL in spec.access:
            command += ["--provider", _PROVIDER]
        if spec.model is not None:
            command += ["--model", spec.model]
        if spec.effort is not None:
            command += ["--thinking", spec.effort]
        return command

    async def _handshake(self, spec: AgentSpec, version: str | None) -> None:
        """Ask what no record says before the first turn, none of which calls a model. Pi warns of an effort a model
        cannot honor and runs on, and a provider it has no login for fails only at a prompt, so both are refused now."""
        state = await self._ask("get_state")
        model = state.get("model") or {}
        provider, id = model.get("provider"), model.get("id")
        available = (await self._ask("get_available_models")).get("models", ())
        if not any(known.get("provider") == provider for known in available):
            raise DriverError(f"{_PI} has no login for {provider}: sign in with `pi`, or give the role an auth profile")
        if spec.effort not in (None, state.get("thinkingLevel")):
            raise DriverError(f"it runs at effort {state.get('thinkingLevel')}, and {spec.effort} was asked for")
        effective = f"{provider}/{id}" if spec.model == f"{provider}/{id}" else id
        self._report(Ready(native=self._native, version=version, effective_model=effective))

    # What the harness is sent.

    def _lost(self) -> DriverError:
        return DriverError(f"{_PI} is gone: see {self._folder / LOG}")

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

    async def _ask(self, command: str, **fields: Any) -> Mapping[str, Any]:
        """Send a command and wait for the response to its id."""
        id = uuid4().hex
        answer: asyncio.Future[Mapping[str, Any]] = asyncio.get_running_loop().create_future()
        self._answers[id] = answer
        try:
            await self._send({"id": id, "type": command, **fields})
            return await answer
        finally:
            del self._answers[id]

    async def _hand_over(self, text: str, boundary: Boundary) -> None:
        """`prompt` begins a turn, and with a `streamingBehavior` it queues in one under way, so no turn can end between
        a look and a send, as it could for `steer` and `follow_up`. A steer lands before the next model call."""
        behavior = "followUp" if boundary == "turn" else "steer"
        answer = await self._ask("prompt", message=text, streamingBehavior=behavior)
        if answer.get("disposition") == "handled":
            raise DriverError("an extension took this input, so it reached no model")

    async def deliver(self, delivery: Delivery) -> Receipt:
        if delivery.boundary not in _CAPABILITIES.boundaries:
            raise DriverError(f"this harness has no {delivery.boundary} boundary")
        self._unlanded[delivery.input] = delivery.text
        try:
            await self._hand_over(delivery.text, delivery.boundary)
        except DriverError:
            del self._unlanded[delivery.input]
            raise
        return Receipt(boundary=delivery.boundary, queued=(delivery.input,))

    async def interrupt(self) -> Receipt:
        """Stop the turn. A dialog open on a gate of the user's would hold up `abort`, so it is cancelled first. What
        pi queued stays behind in its queue, where no run takes it, so `_ended` sends that again."""
        for id in tuple(self._asking):
            await self._send({"type": "extension_ui_response", "id": id, "cancelled": True})
        await self._ask("abort")
        return Receipt(boundary="turn", queued=tuple(self._unlanded))

    async def answer(self, approval: str, verdict: Verdict) -> None:
        if approval not in self._asking:
            raise DriverError(f"no approval {approval} is waiting")
        tool = self._asking.pop(approval)
        if tool is not None:
            self._deciding[tool] = approval
        await self._send({"type": "extension_ui_response", "id": approval, "confirmed": verdict == "allow"})

    async def reconcile(self, input_id: str) -> Reconciled:
        """What came of an input after a crash is in the session's entries, whole and on disk, and the text of each
        names its input. Pi loses what it had only queued, so an input not there will not land."""
        heading = delivery_heading(input_id)
        entries = (await self._ask("get_entries")).get("entries", ())
        said = (entry["message"] for entry in entries if entry.get("message", {}).get("role") == "user")
        return "landed" if any(_text(message["content"]).startswith(heading) for message in said) else "not_landed"

    async def stop(self, grace: float) -> None:
        """End of stdin ends pi and the tool it has running, which leads a group of its own, as a `SIGTERM` does and a
        `SIGKILL` does not."""
        if self._process is None:
            return
        with contextlib.suppress(TimeoutError):
            async with asyncio.timeout(grace):
                self._process.stdin.close()
                await self._process.exited()
        await self._process.stop(grace)

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

    def _soon(self, work: Coroutine[Any, Any, None]) -> None:
        """Run what must ask pi something, which the read loop cannot wait for."""
        task = asyncio.create_task(work)
        self._later.add(task)
        task.add_done_callback(self._later.discard)

    async def _read(self, process: Process) -> None:
        """Translate every line, and when none are left, tell whoever waits on an answer."""
        self._process = process
        try:
            async for line in read_lines(process.stdout):
                self._heard(line)
        finally:
            self._gone = self._lost()
            for answer in self._answers.values():
                if not answer.done():
                    answer.set_exception(self._gone)

    def _heard(self, line: bytes) -> None:
        """One line. Whatever cannot be read is an unknown frame, whichever part of it would not read."""
        if not line.strip():
            return
        frame = None
        try:
            frame = json.loads(line)
            self._take(frame)
        except (AttributeError, KeyError, TypeError, ValueError, RecursionError):
            self._unknown(_kind(frame), line.decode(errors="replace"))

    def _take(self, frame: Any) -> None:
        match frame:
            case {"type": "response", "id": str(id)}:
                self._answered(id, frame)
            case {"type": "extension_ui_request", "method": "confirm", "id": id}:
                self._asked(id, frame.get("title") or "", frame.get("message") or "")
            case {"type": "extension_ui_request", "method": method, "id": id} if method in _DIALOGS:
                self._cancel(id)
                self._unknown(f"extension_ui_request/{method}", json.dumps(frame))
            case {"type": "extension_ui_request", "method": "notify", "notifyType": "warning" | "error" as level}:
                self._unknown("notify", f"{level}: {frame.get('message')}")
            case {"type": "agent_start"}:
                self._begin()
            case {"type": "agent_settled"}:
                self._ended(aborted=bool(frame.get("aborted")))
            case {"type": "message_start", "message": {"role": "user", "content": content}}:
                self._landed(_text(content))
            case {"type": "message_update", "assistantMessageEvent": {"type": "text_delta", "delta": text}}:
                self._report(Delta(text=text))
            case {"type": "message_end", "message": {"role": "assistant", "content": list(blocks)} as message}:
                self._said(message, blocks)
            case {"type": "tool_execution_start", "toolCallId": id, "toolName": name}:
                self._tool_began(id, name, frame.get("args"))
            case {"type": "tool_execution_end", "toolCallId": id, "result": result}:
                self._tool_ended(id, result, frame.get("isError"))
            case {"type": "compaction_end"}:
                self._compaction(frame.get("result"))
            case {"type": str(kind)} if kind in _SAYS_NOTHING:
                pass
            case _:
                raise ValueError("nothing here takes this")

    def _answered(self, id: str, frame: Mapping[str, Any]) -> None:
        """An answer to a command of ours. One nobody waits for any more has nobody to reach."""
        answer = self._answers.get(id)
        if answer is None or answer.done():
            return
        if frame.get("success"):
            answer.set_result(frame.get("data") or {})
        else:
            assert self._process is not None
            answer.set_exception(DriverError(self._process.redact(str(frame.get("error")))))

    def _asked(self, id: str, title: str, said: str) -> None:
        """A `confirm` is an approval, the gate's or one a user's extension wants. Our gate's title is its tool call."""
        tool = title if title in self._tools else None
        self._asking[id] = tool
        self._report(ApprovalRequested(id=id, gist=self._gist(said if tool else f"{title} {said}".strip())))

    def _cancel(self, id: str) -> None:
        """Answer what nobody here can, since an extension is waiting on it. This writes and does not wait."""
        assert self._process is not None
        answer = {"type": "extension_ui_response", "id": id, "cancelled": True}
        self._process.stdin.write(json.dumps(answer).encode() + b"\n")

    def _begin(self) -> None:
        if self._turn is None:
            self._turn = uuid4().hex
            self._opening = True
            self._report(TurnStarted(turn=self._turn))

    def _landed(self, text: str) -> None:
        """An input reached the context: as what began a turn, or inside one. No frame names it, so its text does."""
        boundary: Boundary = "turn" if self._opening else "model_call"
        self._opening = False
        input = next((input for input, sent in self._unlanded.items() if sent == text), None)
        if input is not None:
            del self._unlanded[input]
            self._report(InputDelivered(input=input, boundary=boundary, evidence="message_start"))

    def _said(self, message: Mapping[str, Any], blocks: Sequence[Any]) -> None:
        """A model call has ended. Only now is its id known, and a call the harness stopped hearing may have none."""
        call_id = message.get("responseId")
        failed = message.get("stopReason") == "error"
        self._failure = self._reason(message.get("errorMessage")) if failed else None
        self._report(ModelCall(call_id=call_id, model=message.get("model")))
        self._spent(message.get("usage") or {}, call_id)
        for block in blocks:
            match block:
                case {"type": "text", "text": text}:
                    self._report(Item(kind="message", phase="final", gist=self._gist(text), body=text, call_id=call_id))
                case {"type": "thinking", "thinking": text}:
                    if text:
                        self._report(Item(kind="thought", gist=self._gist(text), body=text, call_id=call_id))
                case {"type": "toolCall", "id": id}:
                    self._calls[id] = call_id
                case _:
                    self._unknown("assistant", json.dumps(block))

    def _spent(self, usage: Mapping[str, Any], call_id: str | None) -> None:
        """What a call spent. Zero tokens means nobody heard, and dollars with no price behind them are no measurement:
        `totalFromProvider` says the provider billed them, and otherwise pi worked them out."""
        tokens = usage.get("totalTokens") or None
        self._report(Usage(tokens=tokens, label="provider" if tokens else "unavailable", scope="call", call_id=call_id))
        cost = usage.get("cost") or {}
        billed = cost.get("totalFromProvider", False)
        if cost.get("total") or billed:
            usd, label = cost.get("total"), "provider" if billed else "estimated"
            self._report(Usage(usd=usd, label=label, scope="call", call_id=call_id))

    def _tool_began(self, id: str, name: str, arguments: Any) -> None:
        self._tools[id] = name
        said = json.dumps(arguments)
        gist = self._gist(f"{name} {said}")
        call_id = self._calls.pop(id, None)
        self._report(Item(kind="tool", phase="started", gist=gist, native_id=id, call_id=call_id, body=said))

    def _tool_ended(self, id: str, result: Mapping[str, Any], failed: Any) -> None:
        """A tool's end. One an approval let through is that approval's observed outcome."""
        outcome = "failed" if failed else "completed"
        approval = self._deciding.pop(id, None)
        item = Item(
            kind="tool",
            phase="decided" if approval else "completed",
            gist=self._gist(f"{self._tools.pop(id, 'tool')} {outcome}"),
            native_id=id,
            body=_text(result.get("content") or ""),
            approval=approval,
            outcome=outcome,
        )
        self._report(item)

    def _compaction(self, result: Mapping[str, Any] | None) -> None:
        """One or two model calls whose usage comes as one, with no id. One that came to nothing says what it spent."""
        self._report(ModelCall(purpose="compaction"))
        self._spent((result or {}).get("usage") or {}, None)
        if result is not None:
            self._soon(self._compacted(result))

    async def _compacted(self, result: Mapping[str, Any]) -> None:
        """Name what left the context, by asking. So this can follow the turn's end, and it says nothing of the turn."""
        forgotten = None
        with contextlib.suppress(DriverError, KeyError):
            listing = await self._ask("get_entries")
            forgotten = _forgotten(listing["entries"], listing["leafId"], result["firstKeptEntryId"])
        self._report(Compacted(forgotten=forgotten, summary=result.get("summary")))

    def _ended(self, *, aborted: bool) -> None:
        """Pi will do nothing more on its own. Approvals of the turn go moot with it. No run takes what a turn that
        stopped short left in pi's queue, so that goes again: the first begins a turn, and the rest steer it."""
        if self._turn is None:
            return
        reason = "interrupted" if aborted else self._failure or "stopped"
        self._report(TurnEnded(reason=reason))
        self._turn, self._failure = None, None
        self._asking.clear()
        self._deciding.clear()
        if self._unlanded and reason != "stopped":
            self._soon(self._send_again(tuple(self._unlanded.values())))

    async def _send_again(self, texts: Sequence[str]) -> None:
        with contextlib.suppress(DriverError):
            await self._ask("clear_queue")
            for text in texts:
                await self._hand_over(text, "model_call")

    def _reason(self, said: Any) -> str:
        assert self._process is not None
        return self._process.redact(str(said))[:_REASON_LIMIT]
