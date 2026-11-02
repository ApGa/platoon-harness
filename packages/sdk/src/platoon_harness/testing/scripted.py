"""ScriptedDriver: a deterministic harness for tests and demos, with no model unless a step asks for one.

Its tool calls are real MCP over `ToolBinding.url`, and an `AskModel` step is a real model call, so a scripted team
exercises the real tool plane, and conformance can read what it did from the model's log.
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

from platoon_harness.drivers import (
    AgentSpec,
    ApprovalRequested,
    Capabilities,
    Delivery,
    Delta,
    DriverError,
    DriverInfo,
    Exited,
    InputDelivered,
    Item,
    ModelCall,
    Ready,
    Receipt,
    Reconciled,
    Reporter,
    Started,
    TurnEnded,
    TurnStarted,
    Usage,
)
from platoon_harness.kernel import GIST_LIMIT
from platoon_harness.primitives import Verdict

from .loopback import post

BASE_URL = "OPENAI_BASE_URL"
API_KEY = "OPENAI_API_KEY"

_REASON_LIMIT = 256
_DEFAULT = Capabilities(
    persistent=True,
    resume=True,
    boundaries={"turn", "tool"},
    tool_paths={"mcp-http"},
    interrupt="turn",
    approvals="native",
    call_ids="call",
    dialects={"chat"},
    measures={"tokens"},
    coverage={"prompt": "observed", "tool_results": "observed"},
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
    """Call one of our tools, as real MCP. Its result lands in `ScriptedDriver.results`."""

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
    that is not ours is gated, as a harness gates its shell."""


type Step = Say | Think | Call | Wait | EndTurn | Fail | Exit | Ask | Hang | AskModel


class _Exiting(Exception):
    """A step that ends the harness, not only the turn."""


class ScriptedDriver:
    """A harness made of `turns`, each a list of steps: the first runs on the goal if it has one, and each next on a
    delivery. A turn with no steps left ends, and turns run out into empty ones.

    Its capabilities are data, and it holds to them: one that is not `persistent` exits after its first turn, one with
    no `resume` refuses to resume, and a boundary it does not declare is refused.
    """

    def __init__(
        self,
        turns: Iterable[Sequence[Step]] = (),
        *,
        capabilities: Capabilities = _DEFAULT,
        name: str = "scripted",
        version: str = "1",
    ) -> None:
        self.results: list[Any] = []
        self._turns: Iterator[Sequence[Step]] = iter(turns)
        self._capabilities = capabilities
        self._info = DriverInfo(name=name, version=version, capabilities=capabilities)
        self._messages: list[dict[str, Any]] = []
        self._pending: deque[Delivery] = deque()
        self._landed: set[str] = set()
        self._arrival = asyncio.Event()
        self._heard_this_turn = False
        self._approvals: dict[str, asyncio.Future[Verdict]] = {}
        self._tools: list[dict[str, Any]] = []
        self._turn_count = 0
        self._steps: asyncio.Task[str] | None = None
        self._interrupted = False
        self._work: asyncio.Task[None] | None = None
        self._exited = False

    def describe(self) -> DriverInfo:
        return self._info

    async def start(self, spec: AgentSpec, report: Reporter) -> Started:
        if spec.resume is not None and not self._capabilities.resume:
            raise DriverError("this harness cannot resume")
        if spec.effort is not None:
            raise DriverError("a scripted harness has no effort to set")
        self._spec, self._report = spec, report
        self._native = spec.resume or f"scripted-{spec.agent}"
        if spec.resume is not None and self._transcript.exists():
            self._messages = json.loads(self._transcript.read_text())
        tools = await self._list_tools() if spec.tools is not None else None
        await report(
            Ready(native=self._native, version=self._info.version, effective_model=spec.model, tools_visible=tools)
        )
        self._work = asyncio.create_task(self._run())
        return Started(native=self._native)

    @property
    def _transcript(self) -> Path:
        return self._spec.folder / f"{self._native}.json"

    async def _run(self) -> None:
        try:
            if self._spec.goal and self._spec.resume is None:
                await self._turn(self._spec.goal)
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
        await self._report(TurnStarted(turn=f"t{self._turn_count}"))
        self._interrupted = False
        self._steps = asyncio.create_task(self._walk(next(self._turns, ())))
        try:
            reason = await self._steps
        except asyncio.CancelledError:
            if not self._interrupted:
                raise
            reason = "interrupted"
        except DriverError as error:
            reason = f"failed: {error}"[:_REASON_LIMIT]
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
        return "stopped"

    async def _say(self, text: str, call_id: str | None = None) -> None:
        await self._report(Delta(text=text))
        await self._report(Item(kind="message", phase="final", gist=text[:GIST_LIMIT], body=text, call_id=call_id))

    async def _ask(self, gist: str) -> Verdict:
        id = f"approval-{uuid.uuid4().hex[:8]}"  # A resumed harness must not ask under an id it has used.
        answered: asyncio.Future[Verdict] = asyncio.get_running_loop().create_future()
        self._approvals[id] = answered
        await self._report(ApprovalRequested(id=id, gist=gist[:GIST_LIMIT]))
        verdict = await answered
        await self._report(Item(kind="tool", phase="decided", gist=gist[:GIST_LIMIT], approval=id, outcome=verdict))
        return verdict

    async def _mcp(self, method: str, params: Mapping[str, Any]) -> Any:
        binding = self._spec.tools
        if binding is None:
            raise DriverError("this agent has no tools")
        frame = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
        bearer = {"authorization": f"Bearer {binding.token.reveal()}"}
        status, body = await post(binding.url, frame, bearer)
        if status != 200:
            raise DriverError(f"{method} answered {status}")
        answer = json.loads(body)
        if "error" in answer:
            raise DriverError(f"{method} refused: {answer['error']}")
        return answer["result"]

    async def _list_tools(self) -> tuple[str, ...]:
        tools = (await self._mcp("tools/list", {}))["tools"]
        self._tools = [
            {"type": "function", "function": {"name": tool["name"], "parameters": tool["inputSchema"]}}
            for tool in tools
        ]
        return tuple(tool["name"] for tool in tools)

    async def _call(
        self, tool: str, arguments: Mapping[str, Any], *, native_id: str | None = None, call_id: str | None = None
    ) -> Any:
        started = Item(kind="tool", phase="started", gist=f"{tool} called"[:GIST_LIMIT])
        await self._report(started.model_copy(update={"native_id": native_id, "call_id": call_id}))
        result = await self._mcp("tools/call", {"name": tool, "arguments": dict(arguments)})
        self.results.append(result)
        outcome = "failed" if result.get("isError") else "completed"
        done = Item(kind="tool", phase="completed", gist=f"{tool} {outcome}"[:GIST_LIMIT], outcome=outcome)
        await self._report(done.model_copy(update={"native_id": native_id, "call_id": call_id}))
        return result

    async def _ask_model(self) -> None:
        while True:
            reply = await self._complete()
            message = reply["choices"][0]["message"]
            self._messages.append(message)
            if message.get("content"):
                await self._say(message["content"], reply["id"])
            if not message.get("tool_calls"):
                return
            for call in message["tool_calls"]:
                self._messages.append(await self._run_call(call, reply["id"]))
            await self._land_steers()

    async def _run_call(self, call: Mapping[str, Any], call_id: str) -> dict[str, Any]:
        function = call["function"]
        name, arguments = function["name"], json.loads(function["arguments"] or "{}")
        ours = any(tool["function"]["name"] == name for tool in self._tools)
        if ours:
            result = await self._call(name, arguments, native_id=call["id"], call_id=call_id)
            output = json.dumps(result)
        else:
            output = await self._gate(name)
        return {"role": "tool", "tool_call_id": call["id"], "content": output}

    async def _gate(self, name: str) -> str:
        if self._capabilities.approvals == "none":
            return f"{name} needs an approval this harness cannot ask for"
        return f"{name} {await self._ask(f'run {name}?')}"

    async def _complete(self) -> Any:
        spec = self._spec
        if spec.model is None:
            raise DriverError("no model was set, and this harness will not pick one")
        url, key = spec.access[BASE_URL].reveal(), spec.access[API_KEY].reveal()
        system = [{"role": "system", "content": spec.instructions}] if spec.instructions else []
        body = {"model": spec.model, "messages": [*system, *self._messages], "stream": False}
        status, answer = await post(
            f"{url}/chat/completions", {**body, "tools": self._tools}, {"authorization": f"Bearer {key}"}
        )
        if status != 200:
            raise DriverError(f"the model answered {status}")
        reply = json.loads(answer)
        await self._report(ModelCall(call_id=reply["id"], model=reply["model"]))
        usage = Usage(tokens=reply["usage"]["total_tokens"], label="provider", scope="call", call_id=reply["id"])
        await self._report(usage)
        return reply

    async def deliver(self, delivery: Delivery) -> Receipt:
        if self._exited:
            raise DriverError("this harness has exited")
        if not self._capabilities.persistent:
            raise DriverError("a one-shot harness takes nothing after its goal")
        if delivery.boundary not in self._capabilities.boundaries:
            raise DriverError(f"this harness has no {delivery.boundary} boundary")
        self._pending.append(delivery)
        self._heard_this_turn = True
        self._arrival.set()
        return Receipt(boundary=delivery.boundary, queued=(delivery.input,))

    async def interrupt(self) -> Receipt:
        if self._capabilities.interrupt == "none":
            raise DriverError("this harness cannot be interrupted")
        queued = tuple(delivery.input for delivery in self._pending)
        if self._steps is not None:
            self._interrupted = True
            self._steps.cancel()
        return Receipt(boundary="turn", queued=queued)

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
        await asyncio.gather(self._work, return_exceptions=True)
        await self._exit("stopped")


def every_turn_asks_the_model() -> Iterable[Sequence[Step]]:
    """The script conformance uses, so the model's replies decide everything, as they do for a real harness."""
    return itertools.repeat((AskModel(),))
