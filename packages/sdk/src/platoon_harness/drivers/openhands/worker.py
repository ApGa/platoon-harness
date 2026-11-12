"""One OpenHands agent as a wire driver: a conversation of the OpenHands SDK, driven only through `arun()`.

A turn runs `arun()` until it returns with nothing it was handed left to run on. A delivery goes to the conversation
only between runs, with no action pending, as one that came during a model call would supersede what that call asks to
run, and one that came after it would sit between a call and its result. The SDK calls back on whichever thread it is
on, so what it says is heard on the event loop, in the order it said it, and every report goes out from there. Nothing
here loads the SDK until `start`, so a description takes no time.
"""

import asyncio
import contextlib
import json
import logging
import os
import sys
import tempfile
from collections import deque
from collections.abc import Callable, Iterable, Iterator, Mapping
from importlib.metadata import PackageNotFoundError, version
from typing import Any
from uuid import uuid4

from platoon_harness.config import Secret
from platoon_harness.kernel import GIST_LIMIT
from platoon_harness.tools import delivery_heading
from platoon_harness.tools.ph import TOKEN_VARIABLE, URL_VARIABLE

from .. import (
    BEARER_VARIABLE,
    AgentSpec,
    ApprovalRequested,
    Boundary,
    Capabilities,
    Compacted,
    Delivery,
    Delta,
    DriverError,
    DriverInfo,
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
    Verdict,
    refuse_unset_model,
    unknown_frame,
)
from ..env import PYTHON, Redactor, secrets_of

_NAME = "openhands"
_SDK = "openhands-sdk"
_TOOLS = "openhands-tools"
_KEY = "OPENAI_API_KEY"
_URL = "OPENAI_BASE_URL"
_TOOL_TIMEOUT_S = 300.0
"""The SDK's cap on one MCP tool call, which a server cannot change."""
_DENIED = "The runtime denied this."
_CUT = "The turn ended before this ran."
_LEFT = "The session stopped before this was decided or done, so it was not run again."
_SAYS_NOTHING = frozenset(
    {"CondensationRequest", "InterruptEvent", "PauseEvent", "SecurityAnalysisEvent", "SystemPromptEvent"}
)
_NOT_TOOLS = frozenset({"finish", "think"})
_PURPOSES = {"agent": None, "condenser": "compaction"}
"""What each of its LLMs calls the model for, by the LLM's usage id: the agent's for its turn, and the condenser's to
compact its context."""
_ENDS = frozenset({"stopped", "stuck", "interrupted"})
"""How a turn ends that no error ended."""
_CAPABILITIES = Capabilities(
    persistent=True,
    resume=True,
    boundaries={"turn", "model_call"},
    tool_paths={"mcp-stdio"},
    tool_names="bare",
    tool_timeout_s=_TOOL_TIMEOUT_S,
    interrupt=True,
    approvals="native",
    native_children="opaque",
    native_children_off=True,
    call_ids="call",
    dialects={"chat"},
    coverage={"prompt": "partial", "tool_results": "observed", "compaction": "observed"},
    measures={"tokens"},
    sealed=True,
)

log = logging.getLogger(__name__)

__all__ = ["Worker", "sdk_version"]


def sdk_version() -> str:
    """The version of the OpenHands SDK here, from its metadata, which loads nothing. Without it or its tools, which our
    `openhands` extra brings, the worker cannot run, and this names the interpreter to install them for."""
    try:
        sdk = version(_SDK)
        version(_TOOLS)
    except PackageNotFoundError as error:
        raise DriverError(
            f"{error.name} is not installed for {sys.executable}: install platoon-harness's `openhands` extra for it, "
            "beside any other extras it has, `platoon-harness[openhands]`"
        ) from error
    return sdk


def _access(spec: AgentSpec) -> tuple[Secret, Secret | None]:
    """The key and the endpoint the agent's model is reached by: its gateway's bearer and models, or its role's."""
    if isinstance(access := spec.access, Gateway):
        if spec.allow_native_children:
            raise DriverError("a sealed launch starts no agents of openhands' own, whose calls would go on its key")
        return access.bearer, Secret(f"{access.origin}/v1")
    if _KEY not in access:
        raise DriverError(
            f"openhands signs in with a key alone: name {_KEY} in the role's auth profile, with {_URL} for an "
            "endpoint other than OpenAI's, as a ChatGPT subscription or an OpenHands Cloud login needs a person"
        )
    return access[_KEY], access.get(_URL)


def _text(parts: Iterable[Any]) -> str:
    """What a message or an observation says, without its images."""
    return "\n".join(part.text for part in parts if part.type == "text")


def _user_texts(messages: Iterable[Mapping[str, Any]]) -> Iterator[str]:
    """What a request's user messages say, in either shape a content takes."""
    for message in messages:
        if message.get("role") != "user":
            continue
        content = message.get("content")
        if isinstance(content, str):
            yield content
        else:
            yield from (part["text"] for part in content or () if part.get("type") == "text")


class Worker:
    """One conversation, presented through the seven methods. What waits for the conversation goes between runs, and a
    run under way is asked to pause for it after its step."""

    def __init__(self) -> None:
        self._conversation: Any = None
        self._queue: asyncio.Queue[Report] = asyncio.Queue()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._forwarding: asyncio.Task[None] | None = None
        self._redact = Redactor(())
        self._model: str | None = None
        self._turn: asyncio.Task[None] | None = None
        self._running: asyncio.Task[None] | None = None
        self._outbox: deque[str] = deque()
        self._unheard: dict[str, tuple[str, Boundary]] = {}
        self._asking: tuple[str, asyncio.Future[Verdict | None]] | None = None
        self._decided: dict[str, str] = {}
        self._interrupted = False
        self._cut = False
        self._failure: str | None = None
        self._counted: dict[str, int] = {}
        self._environment: Any = None

    def describe(self) -> DriverInfo:
        with contextlib.suppress(DriverError):
            return DriverInfo(name=_NAME, version=sdk_version(), capabilities=_CAPABILITIES, installed=PYTHON)
        return DriverInfo(name=_NAME, capabilities=_CAPABILITIES, installed=PYTHON)

    async def start(self, spec: AgentSpec, report: Reporter) -> None:
        """Open the conversation, ready its agent, and say so. The key, the endpoint, a gateway's bearer and our token
        leave the worker's environment once read, so the agent's terminal cannot read them."""
        sdk = sdk_version()
        refuse_unset_model(spec)
        key, url = _access(spec)
        from . import agent  # The SDK, which takes seconds to load.

        shim = {"TMPDIR": tempfile.gettempdir()}
        if spec.tools is not None:
            shim |= {URL_VARIABLE: spec.tools.url, TOKEN_VARIABLE: spec.tools.token.reveal()}
        for name in (_KEY, _URL, BEARER_VARIABLE, TOKEN_VARIABLE):
            os.environ.pop(name, None)
        self._loop = asyncio.get_running_loop()
        self._forwarding = asyncio.create_task(self._forward(report))
        self._redact = Redactor(secrets_of(spec))
        self._model = spec.model
        spec.folder.mkdir(mode=0o700, parents=True, exist_ok=True)
        self._conversation = conversation = await asyncio.to_thread(
            agent.start,
            spec,
            key,
            url,
            shim,
            on_event=lambda event: self._soon(self._heard, event),
            on_token=lambda chunk: self._soon(self._spoke, chunk),
            on_request=lambda _, logged: self._soon(self._requested, logged),
            asked=self._child_asks,
        )
        if spec.resume is not None and not len(conversation.state.events):
            raise DriverError(f"no conversation {spec.resume} is here to resume, and the SDK would start one anew")
        self._counted = {name: len(metrics.token_usages) for name, metrics in self._usage().items()}
        tools, ours, self._environment = await asyncio.to_thread(agent.ready, conversation, spec, key)
        if spec.tools is not None and not ours:
            raise DriverError(
                "our tools did not reach openhands: their server failed to start, as the agent's log says"
            )
        self._put(Ready(native=str(conversation.id), version=sdk, effective_model=spec.model, tools_visible=tools))
        if agent.pending(conversation):
            await asyncio.to_thread(conversation.reject_pending_actions, _LEFT)
        if spec.goal is not None and spec.resume is None:
            await self.deliver(spec.goal)

    async def deliver(self, delivery: Delivery) -> None:
        """Take a delivery: it begins a turn, or goes to the one under way once its run pauses, landing at a later model
        call."""
        if self._conversation is None:
            raise DriverError("this driver has not started")
        opening = self._turn is None
        self._unheard[delivery.text] = (delivery.input, "turn" if opening else "model_call")
        self._outbox.append(delivery.text)
        if opening:
            self._begin()
        else:
            self._pause()

    async def interrupt(self) -> None:
        """Stop the turn. A run under way is cancelled, which abandons a model call in flight that a gateway may have
        recorded all the same, and the run itself before the SDK has begun it, and an approval left open is answered as
        cut off."""
        if self._turn is None:
            return
        self._interrupted = True
        self._outbox.clear()
        if self._asking is not None and not self._asking[1].done():
            self._asking[1].set_result(None)
        if self._running is not None:
            self._cut = True
            self._conversation.interrupt()
            self._running.cancel()

    async def answer(self, approval: str, verdict: Verdict) -> None:
        if self._asking is None or self._asking[0] != approval or self._asking[1].done():
            raise DriverError(f"no approval {approval} is waiting")
        self._asking[1].set_result(verdict)

    async def reconcile(self, input_id: str) -> Reconciled:
        """What came of an input after a crash is in the conversation, which is whole and on disk, and the text of each
        names its input. A miss proves nothing, as the id may be an approval's, so this never says `not_landed`."""
        heading = delivery_heading(input_id)
        said = (event for event in self._conversation.state.events if _is_users(event))
        return "landed" if any(_text(event.llm_message.content).startswith(heading) for event in said) else "unknown"

    async def stop(self, grace: float) -> None:
        """End the turn, then close the conversation, which ends its terminal and the shim to our tools, and the client
        of the environment's tools, and let every report go."""
        if self._conversation is not None:
            await self.interrupt()
            if self._turn is not None:
                await asyncio.wait({self._turn}, timeout=grace)
            await asyncio.wait({asyncio.ensure_future(asyncio.to_thread(self._conversation.close))}, timeout=grace)
            if self._environment is not None:
                await asyncio.wait(
                    {asyncio.ensure_future(asyncio.to_thread(self._environment.sync_close))}, timeout=grace
                )
            await asyncio.wait({asyncio.ensure_future(self._queue.join())}, timeout=grace)

    # The turn.

    def _begin(self) -> None:
        self._interrupted = False
        self._turn = asyncio.create_task(self._take_turn())

    def _pause(self) -> None:
        """Ask the run under way to stop after its step, so that what waits for the conversation can go. The SDK forgets
        a pause asked before its run begins, or while the run waits on an approval, so each thing the run says asks
        again."""
        if self._running is not None and self._outbox:
            assert self._loop is not None
            self._loop.run_in_executor(None, self._conversation.pause)

    async def _hand_over(self) -> None:
        """Hand the conversation what waits for it, in order, one message at a time."""
        while self._outbox:
            await asyncio.to_thread(self._conversation.send_message, self._outbox.popleft())

    async def _take_turn(self) -> None:
        cost = self._cost()
        try:
            reason = await self._runs()
        except Exception as error:
            log.exception("the turn failed")
            reason = self._failure or type(error).__name__
        self._ended("interrupted" if self._interrupted else reason, cost)

    async def _runs(self) -> str:
        """One turn: `arun()` again once an approval is answered, or while something waits for the conversation, and how
        the SDK's own status says it ended. It leaves no action pending, as the next run would run it unasked."""
        try:
            await self._hand_over()
            self._put(TurnStarted(turn=uuid4().hex))
            while not self._interrupted:
                await self._run()
                status = self._conversation.state.execution_status.value
                if status == "waiting_for_confirmation":
                    verdict = await self._ask()
                    if verdict == "allow":
                        continue
                    if verdict == "deny":
                        await asyncio.to_thread(self._conversation.reject_pending_actions, _DENIED)
                elif status in ("stuck", "error"):
                    return self._failure or status
                elif status == "finished" and not self._outbox:
                    return "stopped"
                await self._hand_over()
            return "interrupted"
        finally:
            if self._pending():
                await asyncio.to_thread(self._conversation.reject_pending_actions, _CUT)

    async def _run(self) -> None:
        """One `arun()`, which raises what the SDK raised. One an interrupt cancelled before the SDK began it says
        nothing."""
        running = self._running = asyncio.create_task(self._conversation.arun())
        try:
            await asyncio.wait({running})
        finally:
            self._running = None
        if not running.cancelled():
            running.result()

    def _pending(self) -> list[Any]:
        from .agent import pending

        return pending(self._conversation)

    async def _ask(self) -> Verdict | None:
        """One approval for every action a step holds, as the SDK confirms a step whole."""
        actions = self._pending()
        return await self._decide(_said(actions), [action.tool_call_id for action in actions])

    async def _decide(self, said: str, calls: Iterable[str] = ()) -> Verdict | None:
        """What the runtime answers an approval whose whole ask is `said`, which `calls` record as theirs, or None: for
        one an interrupt cut off, and at once, without asking, outside a turn that goes on."""
        if self._turn is None or self._interrupted:
            return None
        id, verdict = uuid4().hex, asyncio.get_running_loop().create_future()
        self._asking = (id, verdict)
        self._decided |= dict.fromkeys(calls, id)
        self._put(ApprovalRequested(id=id, gist=self._gist(said), body=said))
        try:
            return await verdict
        finally:
            self._asking = None

    def _child_asks(self, task: str, actions: list[Any]) -> bool | None:
        """Whether a native child's step may run, which the runtime decides under its parent's role, or None once its
        parent's turn is cut, which stops the child. This runs on the child's thread, and waits there."""
        assert self._loop is not None
        verdict = asyncio.run_coroutine_threadsafe(self._decide(f"{task}: {_said(actions)}"), self._loop).result()
        return None if verdict is None else verdict == "allow"

    def _ended(self, reason: str, cost: float) -> None:
        """A turn's end. One whose run an interrupt cut, or that an error ended, may have taken a call with it that
        nobody measured, and what one that did not stop on its own left unheard is the runtime's again. Dollars are
        litellm's estimate, where it prices the model."""
        self._spent()
        if self._cut or reason not in _ENDS:
            self._put(Usage(label="unavailable", scope="call"), GapReport(what="usage_lower_bound"))
        if reason != "stopped":
            self._unheard.clear()
            self._outbox.clear()
        if (usd := self._cost() - cost) > 0:
            self._put(Usage(usd=usd, label="estimated", scope="tree"))
        self._put(TurnEnded(reason=reason))
        self._decided.clear()
        self._cut = False
        self._failure = None
        self._turn = None

    # What the SDK says.

    def _soon(self, hear: Callable[[Any], None], said: Any) -> None:
        """Hear on the event loop, from whichever thread the SDK called."""
        assert self._loop is not None
        self._loop.call_soon_threadsafe(hear, said)

    def _put(self, *reports: Report) -> None:
        for report in reports:
            self._queue.put_nowait(report)

    async def _forward(self, report: Reporter) -> None:
        while True:
            await report(await self._queue.get())
            self._queue.task_done()

    def _gist(self, text: str) -> str:
        return self._redact(text)[:GIST_LIMIT]

    def _usage(self) -> Mapping[str, Any]:
        return self._conversation.conversation_stats.usage_to_metrics

    def _cost(self) -> float:
        return sum(metrics.accumulated_cost for metrics in self._usage().values())

    def _spent(self) -> None:
        """Each model call the SDK measured since, by its response id: the agent's own, and the condenser's, whose
        purpose is `compaction`. A native child's is its parent's spending and no call of the agent's."""
        for name, metrics in self._usage().items():
            calls = metrics.token_usages[self._counted.get(name, 0) :]
            self._counted[name] = len(metrics.token_usages)
            child = name.startswith("task:")
            for call in calls:
                tokens = call.prompt_tokens + call.completion_tokens
                if child:
                    self._put(Usage(tokens=tokens, label="provider", scope="tree"))
                    continue
                id = call.response_id or None
                self._put(
                    ModelCall(call_id=id, model=self._model, purpose=_PURPOSES.get(name, name)),
                    Usage(tokens=tokens, label="provider", scope="call", call_id=id),
                )
            if child and calls:
                self._put(GapReport(what="native_child_unattributed"))

    def _spoke(self, chunk: Any) -> None:
        for choice in chunk.choices:
            if text := choice.delta.content:
                self._put(Delta(text=text))

    def _requested(self, logged: str) -> None:
        """A request of the agent's LLM, from the SDK's completion log: a delivery whose text is in it has landed."""
        said = tuple(_user_texts(json.loads(logged).get("messages", ())))
        for text, (input, boundary) in tuple(self._unheard.items()):
            if any(text in message for message in said):
                del self._unheard[text]
                self._put(InputDelivered(input=input, boundary=boundary, evidence="request"))

    def _heard(self, event: Any) -> None:
        """One event. A message the SDK calls the user's says nothing of who wrote it, as a malformed call fed back to
        the model is one too, so of messages only the agent's own are reported."""
        self._spent()
        self._pause()
        match event.kind:
            case "ActionEvent":
                self._acted(event)
            case "ObservationEvent":
                outcome = "failed" if event.observation.is_error else "completed"
                self._answered(event, outcome, _text(event.observation.content))
            case "AgentErrorEvent":
                self._answered(event, "failed", event.error)
            case "UserRejectObservation":
                self._answered(event, "rejected", event.rejection_reason)
            case "MessageEvent":
                if event.source == "agent":
                    self._said(event.llm_message, event.llm_response_id)
            case "Condensation":
                self._condensed(event)
            case "ConversationErrorEvent":
                self._failure = event.code
            case kind if kind in _SAYS_NOTHING:
                pass
            case kind:
                self._put(*unknown_frame(kind, self._redact(event.model_dump_json())))

    def _item(self, kind: Any, text: str, call_id: str | None) -> Item:
        return Item(kind=kind, gist=self._gist(text), body=text, call_id=call_id)

    def _said(self, message: Any, call_id: str | None) -> None:
        if message.reasoning_content:
            self._put(self._item("thought", message.reasoning_content, call_id))
        if text := _text(message.content):
            self._put(self._item("message", text, call_id))

    def _acted(self, event: Any) -> None:
        """An action, with what the model said beside it. `finish` is its last message and `think` a thought, so neither
        is a tool."""
        call_id = event.llm_response_id
        if event.reasoning_content:
            self._put(self._item("thought", event.reasoning_content, call_id))
        if text := _text(event.thought):
            self._put(self._item("message", text, call_id))
        match event.tool_name:
            case "finish":
                self._put(self._item("message", event.action.message, call_id))
            case "think":
                self._put(self._item("thought", event.action.thought, call_id))
            case name:
                said = event.tool_call.arguments
                gist = self._gist(f"{name} {said}")
                self._put(
                    Item(
                        kind="tool",
                        phase="started",
                        gist=gist,
                        native_id=event.tool_call_id,
                        call_id=call_id,
                        body=said,
                    )
                )

    def _answered(self, event: Any, outcome: str, said: str) -> None:
        """A tool's end. One an approval decided is that approval's observed outcome."""
        if event.tool_name in _NOT_TOOLS:
            return
        item = Item(
            kind="tool",
            phase="completed",
            gist=self._gist(f"{event.tool_name} {outcome}"),
            native_id=event.tool_call_id,
            body=said,
            approval=self._decided.get(event.tool_call_id),
            outcome=outcome,
        )
        self._put(item)

    def _condensed(self, event: Any) -> None:
        """A condensation names what it forgot, which the conversation puts in order."""
        forgotten = event.forgotten_event_ids
        ordered = tuple(known.id for known in self._conversation.state.events if known.id in forgotten)
        self._put(Compacted(forgotten=ordered, summary=event.summary))


def _is_users(event: Any) -> bool:
    return event.kind == "MessageEvent" and event.source == "user"


def _said(actions: Iterable[Any]) -> str:
    """What actions would do, as the model asked for each: its tool's name and its arguments."""
    return "; ".join(f"{action.tool_name} {_unescaped(action.tool_call.arguments)}" for action in actions)


def _unescaped(arguments: str) -> str:
    """Arguments as JSON with their letters outside ASCII as themselves, which OpenHands escapes, or as they came if
    they are no JSON."""
    try:
        return json.dumps(json.loads(arguments), ensure_ascii=False)
    except ValueError:
        return arguments
