"""ScriptedDriver: a deterministic harness for tests and demos, with no model unless a step asks for one.

Its tool calls are real MCP over `ToolBinding.url`, and an `AskModel` step is a real model call, so a scripted team
exercises the real tool plane, and conformance can read what it did from the model's log. A tool call the model chose
goes under the id the model gave it, as `scripted/toolCallId`, so its op joins that model call as a harness's would,
and one under an id it has sent already fails its turn, as its op would join the call that sent it first; a `Call`
step, which no model chose, sends none. Given a gateway it launches
sealed, which is the reference a training system's tests run on with no binary: the gateway's model under its bearer,
the environment's tools beside ours, each named by the environment's server as `mcp__environment__<tool>`, and a
`Compact` step that carries the gateway's compaction headers.
"""

import asyncio
import itertools
import json
import uuid
from collections import deque
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from platoon_harness.config import Secret
from platoon_harness.drivers import (
    ENVIRONMENT,
    SHORT_LIMIT,
    AgentSpec,
    ApprovalRequested,
    Capabilities,
    Compacted,
    Delivery,
    Delta,
    DriverError,
    DriverInfo,
    Exited,
    GapReport,
    Gateway,
    InputDelivered,
    Item,
    ModelCall,
    Ready,
    Reconciled,
    Report,
    Reporter,
    TurnEnded,
    TurnStarted,
    Usage,
    keys_of,
    refuse_unset_model,
)
from platoon_harness.drivers.process import Process
from platoon_harness.kernel import GIST_LIMIT
from platoon_harness.primitives import Verdict

from .loopback import post

BASE_URL = "OPENAI_BASE_URL"
API_KEY = "OPENAI_API_KEY"
SHELL = "shell"
"""The one tool of a scripted harness's own, which runs its `command` once allowed."""
SUMMARIZE = "Summarize the conversation so far, so that it can go on from the summary alone."
"""What a `Compact` step asks the model."""

_SHELL_GRACE = 1.0
_ANCHOR = "scripted/toolCallId"
"""The key a tool call's id goes under, which says whose id it is, and the tool server takes as a harness's."""

_DEFAULT = Capabilities(
    persistent=True,
    resume=True,
    boundaries={"turn", "tool"},
    tool_paths={"mcp-http"},
    interrupt=True,
    approvals="native",
    call_ids="call",
    dialects={"chat"},
    measures={"tokens"},
    coverage={"prompt": "observed", "tool_results": "observed"},
    sealed=True,
)


@dataclass(frozen=True)
class Say:
    """Stream some text, then record it as a message."""

    text: str


@dataclass(frozen=True)
class Think:
    text: str


@dataclass(frozen=True)
class Call:
    """Call a tool by the name the model is shown, as real MCP: one of ours, or on a gateway one of the environment's.
    Its result lands in `ScriptedDriver.results`."""

    tool: str
    arguments: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Wait:
    """Hold the turn until a delivery comes in it, the way a harness sits blocked in a tool."""


@dataclass(frozen=True)
class EndTurn:
    """End the turn here, and drop its other steps."""

    reason: str = "stopped"


@dataclass(frozen=True)
class Fail:
    """End the turn on an error of the harness's own."""

    reason: str = "failed"


@dataclass(frozen=True)
class Exit:
    """The harness exits, in the middle of whatever it was doing."""

    reason: str = "the harness exited"


@dataclass(frozen=True)
class Ask:
    """Ask for an approval, and hold the turn until it is answered."""

    gist: str


@dataclass(frozen=True)
class Hang:
    """Do nothing, until interrupted."""


@dataclass(frozen=True)
class AskModel:
    """Behave like a harness: ask the model at `spec.access`, run what it calls, and go on until it only talks. A tool
    that is neither ours nor the environment's is gated, as a harness gates its shell, and on a gateway is no tool at
    all, as a sealed launch has none of its own."""


@dataclass(frozen=True)
class Compact:
    """Compact the context as a harness does: one model call asks for a summary, with the compaction headers a gateway
    gave, and what was said gives way to that summary."""


type Step = Say | Think | Call | Wait | EndTurn | Fail | Exit | Ask | Hang | AskModel | Compact


class _Exiting(Exception):
    """A step that ends the harness, not only the turn."""


class ScriptedDriver:
    """A harness made of `turns`, each a list of steps: the first runs on the goal if it has one, and each next on a
    delivery. A turn with no steps left ends, and turns run out into empty ones. A turn whose step raises ends failed,
    saying what was raised, as a harness's own error ends its turn.

    Its capabilities are data, and it holds to them: one that is not `persistent` exits after its first turn, one with
    no `resume` refuses to resume, and a boundary it does not declare is refused. A turn's name counts within one
    instance and carries that instance's own mark, so that no two of an agent's turns share one across a resume.
    """

    def __init__(
        self,
        turns: Iterable[Sequence[Step]] = (),
        *,
        capabilities: Capabilities = _DEFAULT,
        name: str = "scripted",
        version: str | None = "1",
    ) -> None:
        self.results: list[Any] = []
        self._turns: Iterator[Sequence[Step]] = iter(turns)
        self._capabilities = capabilities
        self._version = version
        self._info = DriverInfo(name=name, version=version, capabilities=capabilities)
        self._messages: list[dict[str, Any]] = []
        self._pending: deque[Delivery] = deque()
        self._landed: set[str] = set()
        self._arrival = asyncio.Event()
        self._heard_this_turn = False
        self._approvals: dict[str, asyncio.Future[Verdict]] = {}
        self._tools: list[dict[str, Any]] = []
        self._servers: dict[str, tuple[tuple[str, Secret], str]] = {}
        self._sent: set[str] = set()
        self._turn_count = 0
        self._incarnation = uuid.uuid4().hex[:8]
        self._steps: asyncio.Task[str] | None = None
        self._interrupted = False
        self._work: asyncio.Task[None] | None = None
        self._shells: set[Process] = set()
        self._exited = False

    def describe(self) -> DriverInfo:
        return self._info

    async def start(self, spec: AgentSpec, report: Reporter) -> None:
        if spec.resume is not None and not self._capabilities.resume:
            raise DriverError("this harness cannot resume")
        if spec.effort is not None:
            raise DriverError("a scripted harness has no effort to set")
        if not self._capabilities.sealed:
            keys_of(spec)  # Which refuses a gateway.
        refuse_unset_model(spec)
        self._spec, self._report = spec, report
        self._native = spec.resume or f"scripted-{spec.agent}"
        if spec.resume is not None and self._transcript.exists():
            self._messages = json.loads(self._transcript.read_text())
        tools = await self._list_tools()
        await report(Ready(native=self._native, version=self._version, effective_model=spec.model, tools_visible=tools))
        self._work = asyncio.create_task(self._run())

    @property
    def _transcript(self) -> Path:
        return self._spec.folder / f"{self._native}.json"

    async def _run(self) -> None:
        try:
            if self._spec.goal is not None and self._spec.resume is None:
                await self._land(self._spec.goal, "turn_start")
                await self._turn()
            while self._capabilities.persistent:
                delivery = await self._next_delivery()
                await self._land(delivery, "turn_start")
                await self._turn()
        except _Exiting as exiting:
            await self._exit(str(exiting))
            return
        await self._exit("a one-shot harness ends with its turn")

    async def _exit(self, reason: str) -> None:
        if not self._exited:
            self._exited = True
            await self._report(Exited(reason=reason))

    async def _next_delivery(self) -> Delivery:
        while not self._pending:
            self._arrival.clear()
            await self._arrival.wait()
        return self._pending.popleft()

    async def _land(self, delivery: Delivery, evidence: str) -> None:
        self._landed.add(delivery.input)
        self._messages.append({"role": "user", "content": delivery.text})
        report = InputDelivered(input=delivery.input, boundary=delivery.boundary, evidence=evidence)
        await self._report(report)

    async def _land_steers(self) -> None:
        """Land what waits for a boundary inside the turn. Between two steps is such a boundary."""
        for delivery in [delivery for delivery in self._pending if delivery.boundary != "turn"]:
            self._pending.remove(delivery)
            await self._land(delivery, "between_steps")

    async def _turn(self, prompt: str | None = None) -> None:
        if prompt is not None:
            self._messages.append({"role": "user", "content": prompt})
        self._turn_count += 1
        self._heard_this_turn = False
        await self._report(TurnStarted(turn=f"t{self._turn_count}-{self._incarnation}"))
        self._interrupted = False
        self._steps = asyncio.create_task(self._walk(next(self._turns, ())))
        try:
            reason = await self._steps
        except asyncio.CancelledError:
            if not self._interrupted:
                raise
            reason = "interrupted"
        except _Exiting:
            raise
        except DriverError as error:
            reason = f"failed: {error}"[:SHORT_LIMIT]
        except Exception as error:
            reason = f"failed: {type(error).__name__}: {error}"[:SHORT_LIMIT]
        self._steps = None
        self._transcript.parent.mkdir(parents=True, exist_ok=True)
        self._transcript.write_text(json.dumps(self._messages))
        await self._report(TurnEnded(reason=reason))

    async def _walk(self, steps: Sequence[Step]) -> str:
        for step in steps:
            await self._land_steers()
            match step:
                case Say(text=text):
                    await self._say(text)
                case Think(text=text):
                    await self._report(Item(kind="thought", gist=text[:GIST_LIMIT], body=text))
                case Call(tool=tool, arguments=arguments):
                    await self._call(tool, arguments)
                case Wait():
                    while not self._heard_this_turn:
                        self._arrival.clear()
                        await self._arrival.wait()
                case EndTurn(reason=reason):
                    return reason
                case Fail(reason=reason):
                    return f"failed: {reason}"
                case Exit(reason=reason):
                    raise _Exiting(reason)
                case Ask(gist=gist):
                    await self._ask(gist)
                case Hang():
                    await asyncio.Event().wait()
                case AskModel():
                    await self._ask_model()
                case Compact():
                    await self._compact()
        return "stopped"

    async def _say(self, text: str, call_id: str | None = None) -> None:
        await self._report(Delta(text=text))
        await self._report(Item(kind="message", gist=text[:GIST_LIMIT], body=text, call_id=call_id))

    async def _ask(self, gist: str) -> Verdict:
        id = f"approval-{uuid.uuid4().hex[:8]}"  # A resumed harness must not ask under an id it has used.
        answered: asyncio.Future[Verdict] = asyncio.get_running_loop().create_future()
        self._approvals[id] = answered
        await self._report(ApprovalRequested(id=id, gist=gist[:GIST_LIMIT]))
        verdict = await answered
        await self._report(Item(kind="tool", phase="completed", gist=gist[:GIST_LIMIT], approval=id, outcome=verdict))
        return verdict

    def _servers_given(self) -> Iterator[tuple[str, tuple[str, Secret]]]:
        """Each server of its tools, by its URL and the bearer it takes, after what the model is shown before each of
        its tools' names: nothing for ours, and the server's name for a gateway's environment's, so none of those
        collides with another tool."""
        if self._spec.tools is not None:
            yield "", (self._spec.tools.url, self._spec.tools.token)
        if isinstance(access := self._spec.access, Gateway) and access.tools is not None:
            yield f"mcp__{ENVIRONMENT}__", (access.tools, access.bearer)

    async def _mcp(self, server: tuple[str, Secret], method: str, params: Mapping[str, Any]) -> Any:
        url, bearer = server
        frame = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
        status, body = await post(url, frame, {"authorization": f"Bearer {bearer.reveal()}"})
        if status != 200:
            raise DriverError(f"{method} answered {status}")
        answer = json.loads(body)
        if "error" in answer:
            raise DriverError(f"{method} refused: {answer['error']}")
        return answer["result"]

    async def _list_tools(self) -> tuple[str, ...] | None:
        """The tools the model is shown, ours and the environment's, or None with neither."""
        for prefix, server in self._servers_given():
            for tool in (await self._mcp(server, "tools/list", {}))["tools"]:
                self._servers[prefix + tool["name"]] = server, tool["name"]
                function = {"name": prefix + tool["name"], "parameters": tool["inputSchema"]}
                self._tools.append({"type": "function", "function": function})
        return tuple(self._servers) if self._spec.tools is not None or self._servers else None

    async def _call(
        self, tool: str, arguments: Mapping[str, Any], *, native_id: str | None = None, call_id: str | None = None
    ) -> Any:
        """Call a tool of ours, or of the environment's, by the name the model is shown. A call the model chose goes
        under the id it gave that call, `native_id`, sent as MCP's `_meta` as a harness sends its own, so its op joins
        the model call that chose it. An id sent already is refused, since its op would join the call that sent it."""
        if native_id is not None:
            if native_id in self._sent:
                raise DriverError(f"the model gave tool call id {native_id} twice, and an op joins its call by its id")
            self._sent.add(native_id)
        binding = self._spec.tools
        found = self._servers.get(tool) or (None if binding is None else ((binding.url, binding.token), tool))
        if found is None:
            raise DriverError("this agent has no tools")
        server, listed = found
        started = Item(kind="tool", phase="started", gist=f"{tool} called"[:GIST_LIMIT])
        await self._report(started.model_copy(update={"native_id": native_id, "call_id": call_id}))
        params: dict[str, Any] = {"name": listed, "arguments": dict(arguments)}
        if native_id is not None:
            params["_meta"] = {_ANCHOR: native_id}
        result = await self._mcp(server, "tools/call", params)
        self.results.append(result)
        outcome = "failed" if result.get("isError") else "completed"
        done = Item(kind="tool", phase="completed", gist=f"{tool} {outcome}"[:GIST_LIMIT], outcome=outcome)
        await self._report(done.model_copy(update={"native_id": native_id, "call_id": call_id}))
        return result

    async def _ask_model(self) -> None:
        while True:
            reply = await self._complete(self._messages, tools=self._tools)
            message = reply["choices"][0]["message"]
            self._messages.append(message)
            if message.get("content"):
                await self._say(message["content"], reply["id"])
            if not message.get("tool_calls"):
                return
            for call in message["tool_calls"]:
                self._messages.append(await self._run_call(call, reply["id"]))
            await self._land_steers()

    async def _compact(self) -> None:
        """One model call for a summary, under the compaction headers its gateway gave, which then stands in for all
        that was said. It names no native id of what it forgot, as it keeps none."""
        asked = [*self._messages, {"role": "user", "content": SUMMARIZE}]
        reply = await self._complete(asked, compacting=True)
        summary = reply["choices"][0]["message"].get("content") or ""
        self._messages = [{"role": "user", "content": summary}]
        await self._report(Compacted(forgotten=None, summary=summary))

    async def _run_call(self, call: Mapping[str, Any], call_id: str) -> dict[str, Any]:
        function = call["function"]
        name, arguments = function["name"], json.loads(function["arguments"] or "{}")
        if name in self._servers:
            result = await self._call(name, arguments, native_id=call["id"], call_id=call_id)
            output = json.dumps(result)
        elif isinstance(self._spec.access, Gateway):
            output = f"there is no tool {name}"
        else:
            output = await self._gate(name, arguments)
        return {"role": "tool", "tool_call_id": call["id"], "content": output}

    async def _gate(self, name: str, arguments: Mapping[str, Any]) -> str:
        """A tool of its own needs an approval. Once allowed, `shell` runs its `command`."""
        if self._capabilities.approvals == "none":
            return f"{name} needs an approval this harness cannot ask for"
        verdict = await self._ask(f"run {name}?")
        if verdict == "allow" and name == SHELL and "command" in arguments:
            return await self._shell(str(arguments["command"]))
        return f"{name} {verdict}"

    async def _shell(self, command: str) -> str:
        """Run a command as a harness runs its shell tool: in `spec.cwd`, on this harness's own environment, in a group
        recorded before it can run, which `stop` ends with whatever it put in the background."""
        said: list[bytes] = []

        async def read(process: Process) -> None:
            said.append(await process.stdout.read())

        async def heard(report: Report) -> None:  # The tool's end is no end of the harness's, but a gap is a gap.
            if isinstance(report, GapReport):
                await self._report(report)

        process = await Process.launch(["/bin/sh", "-c", command], self._spec, heard, read=read)
        self._shells.add(process)
        try:
            await process.exited()
        finally:
            self._shells.discard(process)
            await process.stop(_SHELL_GRACE)
        return f"exit {process.returncode}\n{b''.join(said).decode(errors='replace')}"

    async def _complete(
        self, messages: Sequence[Mapping[str, Any]], *, tools: Sequence[Any] = (), compacting: bool = False
    ) -> Any:
        """One model call, at its gateway when it has one, and reported with the id the model gave it. One that compacts
        carries the gateway's compaction headers, and is reported for that purpose."""
        spec = self._spec
        if spec.model is None:
            raise DriverError("no model was set, and this harness will not pick one")
        access, headers = spec.access, {}
        if isinstance(access, Gateway):
            url, key = f"{access.origin}/v1", access.bearer.reveal()
            headers = dict(access.compaction_headers) if compacting else {}
        else:
            url, key = access[BASE_URL].reveal(), access[API_KEY].reveal()
        system = [{"role": "system", "content": spec.instructions}] if spec.instructions else []
        body = {"model": spec.model, "messages": [*system, *messages], "stream": False}
        status, answer = await post(
            f"{url}/chat/completions", {**body, "tools": list(tools)}, {"authorization": f"Bearer {key}", **headers}
        )
        if status != 200:
            raise DriverError(f"the model answered {status}")
        reply = json.loads(answer)
        purpose = "compaction" if compacting else None
        await self._report(ModelCall(call_id=reply["id"], model=reply["model"], purpose=purpose))
        usage = Usage(tokens=reply["usage"]["total_tokens"], label="provider", scope="call", call_id=reply["id"])
        await self._report(usage)
        return reply

    async def deliver(self, delivery: Delivery) -> None:
        if self._exited:
            raise DriverError("this harness has exited")
        if not self._capabilities.persistent:
            raise DriverError("a one-shot harness takes nothing after its goal")
        if delivery.boundary not in self._capabilities.boundaries:
            raise DriverError(f"this harness has no {delivery.boundary} boundary")
        self._pending.append(delivery)
        self._heard_this_turn = True
        self._arrival.set()

    async def interrupt(self) -> None:
        if not self._capabilities.interrupt:
            raise DriverError("this harness cannot be interrupted")
        if self._steps is not None:
            self._pending.clear()
            self._interrupted = True
            self._steps.cancel()

    async def answer(self, approval: str, verdict: Verdict) -> None:
        if approval not in self._approvals:
            raise DriverError(f"no approval {approval} is waiting")
        self._approvals.pop(approval).set_result(verdict)

    async def reconcile(self, input_id: str) -> Reconciled:
        if input_id in self._landed:
            return "landed"
        return "not_landed" if any(delivery.input == input_id for delivery in self._pending) else "unknown"

    async def stop(self, grace: float) -> None:
        if self._work is None:
            return
        self._work.cancel()
        await asyncio.gather(self._work, *(shell.stop(grace) for shell in tuple(self._shells)), return_exceptions=True)
        await self._exit("stopped")


def every_turn_asks_the_model() -> Iterable[Sequence[Step]]:
    """The script conformance uses, so the model's replies decide everything, as they do for a real harness."""
    return itertools.repeat((AskModel(),))
