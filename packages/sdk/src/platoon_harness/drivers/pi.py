"""The `pi` driver: `pi --mode rpc`, JSON records on stdio, with a response to each command and events between.

A role runs in the user's own setup: pi keeps its own agent directory, so their login, settings and extensions stay
theirs, and what we add comes in beside them, by the one extension `-e` loads. Pi asks for no approval of its own, so
that extension asks, and every approval comes to the runtime. A role's budget is what limits it.

On a gateway the launch is sealed: an agent directory of the agent's own, holding settings that retry nothing and warm
no cache, none of the user's extensions, skills, templates, themes or project instructions, no built-in tool, and the
gateway's model, our tools and the environment's beside them. Pi still compacts, through our extension, which runs pi's
own `compact` with the gateway's compaction headers and keeps the id the model gave each of its calls.
"""

import asyncio
import contextlib
import json
import sys
from collections import deque
from collections.abc import Coroutine, Mapping, Sequence
from pathlib import Path
from typing import Any
from uuid import uuid4

from platoon_harness.primitives import Verdict
from platoon_harness.rpc import Lines
from platoon_harness.tools import SHIM, delivery_heading

from . import (
    BEARER_VARIABLE,
    ENVIRONMENT,
    UNREADABLE,
    AgentSpec,
    ApprovalRequested,
    Boundary,
    Capabilities,
    Compacted,
    Delivery,
    Delta,
    DriverError,
    DriverInfo,
    Gateway,
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
    refuse_other_effort,
    refuse_unset_model,
    text_of,
    unknown_frame,
)
from .env import PYTHON, harness_env, inherited, on_path, private
from .process import LOG, Process, status

_PI = "pi"
_EXTENSION = Path(__file__).with_name("pi_extension.js")
_EXTENSION_CONFIG = "PLATOON_HARNESS_PI"
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
_TOOL_TIMEOUT_S = 600.0
_NO_PRICE = {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0}
_UNREACHED = 2**53 - 1
"""The context window a sealed launch states, which no context reaches. A gateway names none, and pi takes one unstated
as none at all, which would have it compact after every turn: so it compacts once its gateway refuses a request as too
long, and retries that request once."""
_TOOLS_STATUS = "platoon_harness.tools"
"""The status our extension says the tools pi declares under, once ours have connected."""
_COMPACTION_STATUS = "platoon_harness.compaction"
"""The status our extension says the calls of a compaction it ran under, each by its id or null, before pi says the
compaction ended."""
_INSTRUCTIONS = "instructions.md"
_AGENT_DIR = "PI_CODING_AGENT_DIR"
_SEALED = (
    "--no-skills",
    "--no-prompt-templates",
    "--no-themes",
    "--no-context-files",
    "--no-approve",
    "--no-builtin-tools",
    "--offline",
)
"""What a sealed launch keeps out: whatever pi would find of the user's or the project's, and pi's own tools."""
_SEALED_SETTINGS = {"retry": {"enabled": False}, "cacheWarming": "off"}
"""A sealed agent's settings: a retry is a second call a gateway records, and a warmed cache one nobody asked for."""
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
    interrupt=True,
    approvals="gated",
    call_ids="call",
    dialects={"chat"},
    coverage={"prompt": "partial", "tool_results": "observed", "compaction": "observed"},
    measures={"tokens", "usd"},
    sealed=True,
)

__all__ = ["PiDriver"]


def _login() -> Login | None:
    """Which kind of login pi holds for the provider its settings name, or None if it cannot tell. Asking takes a
    provider. Only that field is read, and it fetches no credential and refreshes none."""
    env = inherited(*_SIGN_IN)
    home = env.get("PI_CODING_AGENT_DIR") or Path(env.get("HOME", "")) / ".pi" / "agent"
    try:
        provider = json.loads((Path(home).expanduser() / "settings.json").read_text())["defaultProvider"]
        done = status((_PI, "auth", "check", "--provider", provider, "--json", "--no-refresh"), env)
        return None if done is None else _LOGINS.get(json.loads(done.stdout).get("authType"))
    except (OSError, *UNREADABLE):
        return None


def _installed() -> tuple[Path, ...]:
    """Pi and node as `PATH` finds them, the `node_modules` pi's package is in, which holds what it and our extension
    import, and the Python our shim runs on."""
    pi = on_path(_PI)
    modules = [folder for found in pi for folder in found.resolve().parents if folder.name == "node_modules"][:1]
    return (*pi, *modules, *on_path("node"), *PYTHON)


def _version(env: Mapping[str, str]) -> str | None:
    """What pi says of itself, since no record does."""
    done = status((_PI, "--version"), env)
    return None if done is None else done.stdout.decode(errors="replace").strip() or None


def _extension_config(spec: AgentSpec) -> str:
    """What the extension adds for this agent, with the file of instructions it reads. Our tools go through the stdio
    shim on this very interpreter, so that each call has an id of its own, and the token stays in the environment. A
    provider of the agent's own reaches its access, and on a gateway the environment's server and its compaction headers
    come too, each naming the variable the bearer is in, never its value."""
    config: dict[str, Any] = {}
    if spec.instructions is not None:
        config["instructions"] = private(spec.folder, spec.folder / _INSTRUCTIONS, spec.instructions)
    if spec.tools is not None:
        config["namespace"] = spec.tools.namespace
        config["server"] = {
            "command": sys.executable,
            "args": ["-I", str(SHIM)],
            "exposure": "direct",
            "timeout": _TOOL_TIMEOUT_S,
        }
    model = {"id": spec.model, "reasoning": spec.effort is not None, "input": ["text"], "cost": _NO_PRICE}
    if isinstance(access := spec.access, Gateway):
        bearer = f"${{{BEARER_VARIABLE}}}"
        config["provider"] = [
            _PROVIDER,
            _provider(f"{access.origin}/v1", bearer, {**model, "contextWindow": _UNREACHED}),
        ]
        config["compaction"] = {"bearer": BEARER_VARIABLE, "headers": dict(access.compaction_headers)}
        if access.tools is not None:
            headers = {"Authorization": f"Bearer {bearer}"}
            config["environment"] = [ENVIRONMENT, {"url": access.tools, "headers": headers, "exposure": "direct"}]
    elif _BASE_URL in access:
        config["provider"] = [_PROVIDER, _provider(access[_BASE_URL].reveal(), f"${_KEY}", model)]
    return json.dumps(config)


def _provider(url: str, key: str, model: Mapping[str, Any]) -> dict[str, Any]:
    """A provider that speaks Chat Completions at `url`, with `key` naming the variable its key is in."""
    return {"baseUrl": url, "apiKey": key, "api": "openai-completions", "models": [model]}


def _kind(frame: Any) -> str:
    """How a frame is known, whatever it is."""
    kind = frame.get("type") if isinstance(frame, dict) else None
    return kind if isinstance(kind, str) else "frame"


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


class _Place:
    """Where a report goes among pi's while it waits on pi's answer to an ask, holding what is known of it so far,
    which is what goes on if pi never answers."""

    def __init__(self, report: Report) -> None:
        self.report = report
        self.waiting = True

    def fill(self, report: Report) -> None:
        self.report, self.waiting = report, False


class PiDriver:
    """One `pi --mode rpc` process. A turn runs from the first `agent_start` to `agent_settled`, since retries, a
    compaction and queued input can each follow an `agent_end`.

    Frames are translated on the read loop, which never waits, so the pipe drains. An agent is parked at turn end, which
    is the runtime's to do. An input that lands is reported under the id of the entry pi wrote it down as, and a
    compaction with what it forgot, which pi gives only when asked, so whatever pi says after either waits behind it:
    the reports keep pi's order.
    """

    def __init__(self) -> None:
        self._info: DriverInfo | None = None
        self._launched: Process | None = None
        self._lines = Lines(self._lost)
        self._native = ""
        self._folder = Path()
        self._turn: str | None = None
        self._interrupted = False
        self._opening = False
        self._failure: str | None = None
        self._inputs: dict[str, str] = {}
        self._landed_as: dict[str, _Place] = {}
        self._written: list[str] = []
        self._behind: deque[Report | _Place] = deque()
        self._naming: str | None = None
        self._last_entry: str | None = None
        self._calls: dict[str, str | None] = {}
        self._tools: dict[str, str] = {}
        self._asking: dict[str, str | None] = {}
        self._deciding: dict[str, str] = {}
        self._later: set[asyncio.Task[None]] = set()
        self._declared: tuple[str, ...] | None = None
        self._declaring = asyncio.Event()
        self._compacting: list[str | None] | None = None

    def describe(self) -> DriverInfo:
        if self._info is None:
            version = _version(inherited(*_SIGN_IN))
            self._info = DriverInfo(
                name=_PI, login=_login(), version=version, capabilities=_CAPABILITIES, installed=_installed()
            )
        return self._info

    async def start(self, spec: AgentSpec, report: Reporter) -> None:
        refuse_unset_model(spec)
        access = spec.access
        if not isinstance(access, Gateway) and _BASE_URL in access and _KEY not in access:
            raise DriverError(f"{_BASE_URL} with no {_KEY} would reach nobody's model: name one too")
        self._native = spec.resume or str(uuid4())
        self._folder = spec.folder
        spec.folder.mkdir(mode=0o700, parents=True, exist_ok=True)
        env = {**self._env(spec), _EXTENSION_CONFIG: _extension_config(spec)}
        self._launched = await Process.launch(self._command(spec), spec, report, read=self._read, env=env)
        self._lines.open(self._launched.stdin)
        await self._handshake(spec, await asyncio.to_thread(_version, env))
        if spec.goal is not None and spec.resume is None:
            await self.deliver(spec.goal)

    def _env(self, spec: AgentSpec) -> dict[str, str]:
        """The harness's environment: what signs it in as in the user's shell, or for a sealed launch nothing of the
        user's, and an agent directory of its own, in the agent's folder, whose settings are a sealed agent's."""
        if not isinstance(spec.access, Gateway):
            return harness_env(spec, *_SIGN_IN)
        home = spec.folder / "pi"
        home.mkdir(mode=0o700, exist_ok=True)
        private(spec.folder, home / "settings.json", json.dumps(_SEALED_SETTINGS))
        return {**harness_env(spec), _AGENT_DIR: str(home)}

    def _command(self, spec: AgentSpec) -> list[str]:
        """How this agent launches. `--session-id` makes a session under an id we chose, so `native` is known before
        launch, and `--session` finds one or exits. Pi writes the session down at its first prompt, so one that took no
        turn cannot be found. A provider of the agent's own is named, or `--model` would pick among the user's."""
        command = [_PI, "--mode", "rpc", "--session" if spec.resume else "--session-id", self._native]
        command += ["-e", str(_EXTENSION)]
        if isinstance(spec.access, Gateway):
            command += [*_SEALED, "--provider", _PROVIDER]
        elif _BASE_URL in spec.access:
            command += ["--provider", _PROVIDER]
        if spec.model is not None:
            command += ["--model", spec.model]
        if spec.effort is not None:
            command += ["--thinking", spec.effort]
        return command

    async def _handshake(self, spec: AgentSpec, version: str | None) -> None:
        """Ask what no record says before the first turn, none of which calls a model. Pi warns of an effort a model
        cannot honor and runs on, and a provider it has no login for fails only at a prompt, so both are refused now.
        With our tools, it waits for our extension to say which tools pi declares, once they have connected."""
        state = await self._ask("get_state")
        model = state.get("model") or {}
        provider, id = model.get("provider"), model.get("id")
        available = (await self._ask("get_available_models")).get("models", ())
        if not any(known.get("provider") == provider for known in available):
            raise DriverError(f"{_PI} has no login for {provider}: sign in with `pi`, or give the role an auth profile")
        refuse_other_effort(spec, state.get("thinkingLevel"))
        effective = f"{provider}/{id}" if spec.model == f"{provider}/{id}" else id
        if spec.tools is not None:
            await self._declaring.wait()
        declared = self._declared
        self._report(Ready(native=self._native, version=version, effective_model=effective, tools_visible=declared))

    # What the harness is sent.

    def _lost(self) -> DriverError:
        return DriverError(f"{_PI} is gone: see {self._folder / LOG}")

    async def _ask(self, command: str, **fields: Any) -> Mapping[str, Any]:
        id = uuid4().hex
        return await self._lines.exchange(id, {"id": id, "type": command, **fields})

    async def _hand_over(self, text: str) -> None:
        """`prompt` begins a turn, and with a `streamingBehavior` it queues in one under way, so no turn can end between
        a look and a send, as it could for `steer` and `follow_up`. A steer lands before the next model call."""
        answer = await self._ask("prompt", message=text, streamingBehavior="steer")
        if answer.get("disposition") == "handled":
            raise DriverError("an extension took this input, so it reached no model")

    async def deliver(self, delivery: Delivery) -> None:
        self._inputs[delivery.text] = delivery.input
        try:
            await self._hand_over(delivery.text)
        except DriverError:
            self._inputs.pop(delivery.text, None)
            raise

    async def interrupt(self) -> None:
        """Stop the turn. A dialog open on a gate of the user's would hold up `abort`, so it is cancelled first. What
        pi queued stays behind in its queue, where no run takes it, so `_ended` clears that, and the runtime offers it
        again."""
        self._interrupted = True
        try:
            for id in tuple(self._asking):
                await self._lines.send({"type": "extension_ui_response", "id": id, "cancelled": True})
            await self._ask("abort")
        finally:
            self._interrupted = self._turn is not None

    async def answer(self, approval: str, verdict: Verdict) -> None:
        if approval not in self._asking:
            raise DriverError(f"no approval {approval} is waiting")
        tool = self._asking.pop(approval)
        if tool is not None:
            self._deciding[tool] = approval
        await self._lines.send({"type": "extension_ui_response", "id": approval, "confirmed": verdict == "allow"})

    async def reconcile(self, input_id: str) -> Reconciled:
        """What came of an input after a crash is in the session's entries, whole and on disk, and the text of each
        names its input. A miss proves nothing, as the id may be an approval's, so this never says `not_landed`."""
        heading = delivery_heading(input_id)
        entries = (await self._ask("get_entries")).get("entries", ())
        said = (entry["message"] for entry in entries if entry.get("message", {}).get("role") == "user")
        return "landed" if any(text_of(message["content"]).startswith(heading) for message in said) else "unknown"

    async def stop(self, grace: float) -> None:
        """End of stdin ends pi and the tool it has running, which leads a group of its own, as a `SIGTERM` does and a
        `SIGKILL` does not."""
        if self._launched is not None:
            await self._launched.stop(grace)

    # What the harness says.

    @property
    def _process(self) -> Process:
        if self._launched is None:
            raise DriverError("this driver has not started")
        return self._launched

    def _soon(self, work: Coroutine[Any, Any, None]) -> None:
        """Run what must ask pi something, which the read loop cannot wait for."""
        task = asyncio.create_task(work)
        self._later.add(task)
        task.add_done_callback(self._later.discard)

    async def _read(self, process: Process) -> None:
        """Hear pi until it stops. What waits on an answer pi never gave goes on as it is known, before the exit after
        it: an input with no id, and a compaction naming nothing."""
        try:
            await self._lines.run(process.stdout, self._heard)
        finally:
            self._naming = None
            self._landed_as.clear()
            self._written.clear()
            for held in self._behind:
                if isinstance(held, _Place):
                    held.waiting = False
            self._pass_on()

    def _report(self, *reports: Report | _Place) -> None:
        """Pass reports on in pi's order: behind one waiting on pi's answer, they wait too."""
        self._behind.extend(reports)
        self._pass_on()

    def _pass_on(self) -> None:
        """Pass on what waited, up to a report still waiting on pi."""
        while self._behind and not (isinstance(head := self._behind[0], _Place) and head.waiting):
            self._behind.popleft()
            self._process.put(head.report if isinstance(head, _Place) else head)

    def _unknown(self, kind: str, raw: str) -> None:
        self._report(*unknown_frame(self._process.reason(kind), self._process.redact(raw)))

    def _heard(self, line: bytes) -> None:
        """One line. Whatever cannot be read is an unknown frame, whichever part of it would not read."""
        frame = None
        try:
            frame = json.loads(line)
            self._take(frame)
        except UNREADABLE:
            self._unknown(_kind(frame), line.decode(errors="replace"))

    def _take(self, frame: Any) -> None:
        match frame:
            case {"type": "response", "id": str(id)} if id == self._naming:
                self._named(frame)
            case {"type": "response", "id": str(id)}:
                self._answered(id, frame)
            case {"type": "extension_ui_request", "method": "setStatus", "statusKey": key, "statusText": str(text)} if (
                key == _TOOLS_STATUS
            ):
                self._declared = tuple(json.loads(text))
                self._declaring.set()
            case {"type": "extension_ui_request", "method": "setStatus", "statusKey": key, "statusText": str(text)} if (
                key == _COMPACTION_STATUS
            ):
                self._compacting = [call if isinstance(call, str) else None for call in json.loads(text)]
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
                self._landed(text_of(content))
            case {"type": "message_end", "message": {"role": "user"}}:
                self._written_down()
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
        """An answer to a command of ours."""
        if frame.get("success"):
            self._lines.settle(id, frame.get("data") or {})
        else:
            self._lines.settle(id, DriverError(self._process.redact(str(frame.get("error")))))

    def _asked(self, id: str, title: str, said: str) -> None:
        """A `confirm` is an approval, the gate's or one a user's extension wants. Our gate's title is its tool call."""
        tool = title if title in self._tools else None
        self._asking[id] = tool
        self._report(ApprovalRequested(id=id, gist=self._process.gist(said if tool else f"{title} {said}".strip())))

    def _cancel(self, id: str) -> None:
        """Answer what nobody here can, since an extension is waiting on it."""
        self._lines.write({"type": "extension_ui_response", "id": id, "cancelled": True})

    def _begin(self) -> None:
        if self._turn is None:
            self._turn = uuid4().hex
            self._opening = True
            self._report(TurnStarted(turn=self._turn))

    def _landed(self, text: str) -> None:
        """An input reached the context: as what began a turn, or inside one. No frame names it, so its text does, and
        it waits at its place, as its text, for the id of the entry pi writes it down as."""
        boundary: Boundary = "turn" if self._opening else "model_call"
        self._opening = False
        if (input := self._inputs.pop(text, None)) is not None:
            self._landed_as[text] = _Place(InputDelivered(input=input, boundary=boundary, evidence="message_start"))
            self._report(self._landed_as[text])

    def _written_down(self) -> None:
        """A user message has ended, and its end follows its start, so pi has written down each input that landed, as an
        entry, before it reads another command: ask for the entries since the last one seen. One ask is out at a time:
        pi answers after what it said before, so an answer holds every entry whose message ended before it."""
        landed = [text for text in self._landed_as if text not in self._written]
        if not landed:
            return
        self._written += landed
        if self._naming is None:
            self._naming = uuid4().hex
            since = {} if self._last_entry is None else {"since": self._last_entry}
            self._lines.write({"id": self._naming, "type": "get_entries", **since})

    def _named(self, frame: Mapping[str, Any]) -> None:
        """Say each written-down input landed as the entry that holds its text, or with no id where pi names none, and
        pass on what waited behind them, up to an input still to be written down."""
        self._naming, ids = None, {}
        try:
            entries = frame["data"]["entries"] if frame.get("success") else ()
            if not frame.get("success"):
                self._last_entry = None  # A cursor pi did not take names nothing, so the next ask starts over.
            elif entries:
                self._last_entry = entries[-1]["id"]
            ids = {
                text_of(entry["message"]["content"]): entry["id"]
                for entry in entries
                if entry["type"] == "message" and entry["message"]["role"] == "user"
            }
        finally:
            for text in self._written:
                place = self._landed_as.pop(text)
                place.fill(place.report.model_copy(update={"native_id": ids.get(text)}))
            self._written.clear()
            self._pass_on()

    def _said(self, message: Mapping[str, Any], blocks: Sequence[Any]) -> None:
        """A model call has ended. Only now is its id known, and a call the harness stopped hearing may have none."""
        call_id = message.get("responseId")
        failed = message.get("stopReason") == "error"
        self._failure = self._process.reason(str(message.get("errorMessage"))) if failed else None
        self._report(ModelCall(call_id=call_id, model=message.get("model")))
        self._spent(message.get("usage") or {}, call_id)
        for block in blocks:
            match block:
                case {"type": "text", "text": text}:
                    self._report(Item(kind="message", gist=self._process.gist(text), body=text, call_id=call_id))
                case {"type": "thinking", "thinking": text}:
                    if text:
                        self._report(Item(kind="thought", gist=self._process.gist(text), body=text, call_id=call_id))
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
        gist = self._process.gist(f"{name} {said}")
        call_id = self._calls.pop(id, None)
        self._report(Item(kind="tool", phase="started", gist=gist, native_id=id, call_id=call_id, body=said))

    def _tool_ended(self, id: str, result: Mapping[str, Any], failed: Any) -> None:
        """A tool's end. One an approval let through is that approval's observed outcome."""
        outcome = "failed" if failed else "completed"
        approval = self._deciding.pop(id, None)
        item = Item(
            kind="tool",
            phase="completed",
            gist=self._process.gist(f"{self._tools.pop(id, 'tool')} {outcome}"),
            native_id=id,
            body=text_of(result.get("content") or ""),
            approval=approval,
            outcome=outcome,
        )
        self._report(item)

    def _compaction(self, result: Mapping[str, Any] | None) -> None:
        """One or two model calls whose usage comes as one. Through our extension each call it made is reported, by the
        id the model gave it or none where it never answered, and pi's own compaction is one call that names none. One
        that came to nothing says what it spent, and one that came to something waits in its place for what it
        forgot."""
        calls, self._compacting = [None] if self._compacting is None else self._compacting, None
        self._report(*(ModelCall(call_id=call, purpose="compaction") for call in calls))
        self._spent((result or {}).get("usage") or {}, calls[0] if len(calls) == 1 else None)
        if result is not None:
            place = _Place(Compacted(forgotten=None, summary=result.get("summary")))
            self._report(place)
            self._soon(self._compacted(result, place))

    async def _compacted(self, result: Mapping[str, Any], place: _Place) -> None:
        """Name what left the context, by asking, and pass on what waited behind it."""
        forgotten = None
        with contextlib.suppress(DriverError, *UNREADABLE):
            listing = await self._ask("get_entries")
            forgotten = _forgotten(listing["entries"], listing["leafId"], result["firstKeptEntryId"])
        if place.waiting:
            place.fill(Compacted(forgotten=forgotten, summary=result.get("summary")))
            self._pass_on()

    def _ended(self, *, aborted: bool) -> None:
        """Pi will do nothing more on its own. Approvals of the turn go moot with it. No run takes what a turn that
        stopped short left in pi's queue, so that is cleared, as the runtime offers it again."""
        if self._turn is None:
            return
        cut = "interrupted" if self._interrupted else "aborted"  # Pi or an extension of the user's may abort a run.
        reason = cut if aborted else self._failure or "stopped"
        self._report(TurnEnded(reason=reason))
        self._turn, self._failure, self._interrupted = None, None, False
        self._asking.clear()
        self._deciding.clear()
        if self._inputs and reason != "stopped":
            self._inputs.clear()
            self._soon(self._clear_queue())

    async def _clear_queue(self) -> None:
        with contextlib.suppress(DriverError):
            await self._ask("clear_queue")
