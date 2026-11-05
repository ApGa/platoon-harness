"""FakeModel: a loopback server in the three dialects harnesses speak, so a real binary runs on a dummy key for free.

It replies from a script and logs every request exactly as it arrived, which makes the log ground truth: "our tool in
the first request" is read from what the harness sent, and never from what it claimed. It can act as a training system's
gateway too: its models and the environment's tools, each under a bearer it gave.
"""

import asyncio
import json
from collections import deque
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from functools import cached_property
from typing import Any, Literal, Self

from platoon_harness.config import Secret
from platoon_harness.drivers import Gateway

from .loopback import Loopback, Message, answer, stream_head

INPUT_TOKENS = 11
OUTPUT_TOKENS = 3

ENVIRONMENT_TOOL = "environment_ping"
"""The one tool of the environment's own that FakeModel serves as a gateway, at `/mcp`."""
COMPACTION_HEADERS = {"X-Call-Purpose": "compaction"}
"""What FakeModel as a gateway asks each compaction call to carry."""

_MODEL = "fake-model"
_TOOLS = "/mcp"
_DEFAULT_REPLY = "ok"
_ENVIRONMENT_TOOL = {
    "name": ENVIRONMENT_TOOL,
    "description": "Answer with pong. It is the environment's own, which a training system's gateway serves.",
    "inputSchema": {"type": "object", "properties": {"note": {"type": "string"}}, "additionalProperties": False},
}

Dialect = Literal["chat", "responses", "messages"]
_ROUTES: tuple[tuple[str, Dialect], ...] = (
    ("/chat/completions", "chat"),
    ("/responses", "responses"),
    ("/messages", "messages"),
)


@dataclass(frozen=True)
class Text:
    """The model says this."""

    text: str


@dataclass(frozen=True)
class Thought:
    """The model thinks this, in dialects that carry thinking."""

    text: str


@dataclass(frozen=True)
class ToolCall:
    """The model calls a tool. `namespace` is how a Responses client names an MCP server's tools."""

    name: str
    arguments: Mapping[str, Any] = field(default_factory=dict)
    id: str = "call_1"
    namespace: str | None = None


@dataclass(frozen=True)
class Stall:
    """Hold the response until `FakeModel.release` or the client goes away. What follows it in a reply comes after."""


@dataclass(frozen=True)
class Overflow:
    """Refuse the request as longer than the model's context window, in the dialect's own error form, which names no
    response."""


type Block = Text | Thought | ToolCall | Stall | Overflow
type Reply = str | Block | Sequence[Block]


@dataclass(frozen=True)
class Request:
    """One request, logged exactly as it arrived. `dialect` is None for what is no model call."""

    message: Message
    dialect: Dialect | None = None
    response_id: str | None = None

    @cached_property
    def json(self) -> Any:
        return json.loads(self.message.body or b"null")

    @property
    def model(self) -> str | None:
        return self.json.get("model")

    @property
    def bearer(self) -> str | None:
        """The bearer it was sent under, if any."""
        scheme, _, bearer = (self.message.header("authorization") or "").partition(" ")
        return bearer if scheme.lower() == "bearer" and bearer else None

    def carries(self, headers: Mapping[str, str]) -> bool:
        """Whether it carries each of these headers with its value."""
        return all(self.message.header(name.lower()) == value for name, value in headers.items())

    @property
    def tool_method(self) -> str | None:
        """What it asked of the environment's MCP server, or None for a request of any other kind."""
        asked = self.json if self.message.target.partition("?")[0] == _TOOLS else None
        return asked.get("method") if isinstance(asked, dict) else None

    def says(self, text: str) -> bool:
        """Whether this text is anywhere in what the harness sent."""
        return text in self.message.body.decode(errors="replace")

    def offers(self, tool: str) -> bool:
        """Whether the model is shown this tool, in any dialect's shape: a harness prefixes or nests the name."""
        return tool in json.dumps(self.json.get("tools", []))

    @cached_property
    def tools(self) -> tuple[str, ...]:
        """The names of the tools the model is shown, exactly, in any dialect's shape. A namespace's tools go by their
        own names, and a Responses client can list tools in its input, as Codex does for a catalog model."""
        listed = list(self.json.get("tools") or ())
        for item in self.json.get("input") or ():
            if isinstance(item, dict) and item.get("type") == "additional_tools":
                listed += item.get("tools", ())
        return tuple(_names(listed))


def _names(tools: Sequence[Any]) -> Iterator[str]:
    for tool in tools:
        if tool.get("type") == "namespace":
            yield from _names(tool.get("tools", ()))
        elif name := tool.get("name") or tool.get("function", {}).get("name"):
            yield name


def _blocks(reply: Reply) -> tuple[Block, ...]:
    if isinstance(reply, str):
        return (Text(reply),)
    return (reply,) if isinstance(reply, Text | Thought | ToolCall | Stall | Overflow) else tuple(reply)


def _pieces(text: str) -> list[str]:
    """Text as a stream arrives, a word at a time."""
    words = text.split(" ")
    return [f"{word} " for word in words[:-1]] + words[-1:]


class _Chat:
    """OpenAI Chat Completions."""

    OVERFLOW = {
        "error": {
            "message": (
                "This model's maximum context length is 128000 tokens. However, your messages resulted in 128001 "
                "tokens. Please reduce the length of the messages."
            ),
            "type": "invalid_request_error",
            "param": "messages",
            "code": "context_length_exceeded",
        }
    }

    @staticmethod
    def whole(blocks: Sequence[Block], id: str, model: str) -> dict[str, Any]:
        text = "".join(block.text for block in blocks if isinstance(block, Text))
        calls = [block for block in blocks if isinstance(block, ToolCall)]
        message: dict[str, Any] = {"role": "assistant", "content": text or None}
        if calls:
            message["tool_calls"] = [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {"name": call.name, "arguments": json.dumps(call.arguments)},
                }
                for call in calls
            ]
        return {
            "id": id,
            "object": "chat.completion",
            "created": 0,
            "model": model,
            "choices": [{"index": 0, "message": message, "finish_reason": "tool_calls" if calls else "stop"}],
            "usage": _Chat.usage(),
        }

    @staticmethod
    def usage() -> dict[str, int]:
        return {
            "prompt_tokens": INPUT_TOKENS,
            "completion_tokens": OUTPUT_TOKENS,
            "total_tokens": INPUT_TOKENS + OUTPUT_TOKENS,
        }

    @staticmethod
    def stream(blocks: Sequence[Block], id: str, model: str) -> Iterator[tuple[str | None, Any]]:
        base = {"id": id, "object": "chat.completion.chunk", "created": 0, "model": model}

        def delta(content: dict[str, Any], finish: str | None = None) -> tuple[None, dict[str, Any]]:
            return None, {**base, "choices": [{"index": 0, "delta": content, "finish_reason": finish}]}

        yield delta({"role": "assistant", "content": ""})
        index = 0
        for block in blocks:
            if isinstance(block, Text):
                yield from (delta({"content": piece}) for piece in _pieces(block.text))
            elif isinstance(block, ToolCall):
                function = {"name": block.name, "arguments": ""}
                yield delta(
                    {"tool_calls": [{"index": index, "id": block.id, "type": "function", "function": function}]}
                )
                arguments = {"arguments": json.dumps(block.arguments)}
                yield delta({"tool_calls": [{"index": index, "function": arguments}]})
                index += 1
        yield delta({}, "tool_calls" if index else "stop")
        yield None, {**base, "choices": [], "usage": _Chat.usage()}
        yield None, "[DONE]"


class _Messages:
    """Anthropic Messages."""

    OVERFLOW = {
        "type": "error",
        "error": {"type": "invalid_request_error", "message": "prompt is too long: 200001 tokens > 200000 maximum"},
    }

    @staticmethod
    def block(block: Block, index: int) -> dict[str, Any]:
        match block:
            case Text():
                return {"type": "text", "text": block.text}
            case Thought():
                return {"type": "thinking", "thinking": block.text, "signature": "fake-signature"}
            case ToolCall():
                return {"type": "tool_use", "id": block.id, "name": block.name, "input": dict(block.arguments)}
            case _:
                raise AssertionError(f"block {index} is not content")

    @staticmethod
    def usage() -> dict[str, int]:
        return {
            "input_tokens": INPUT_TOKENS,
            "output_tokens": OUTPUT_TOKENS,
            "cache_read_input_tokens": 0,
            "cache_creation_input_tokens": 0,
        }

    @staticmethod
    def whole(blocks: Sequence[Block], id: str, model: str) -> dict[str, Any]:
        return {
            "id": id,
            "type": "message",
            "role": "assistant",
            "model": model,
            "content": [_Messages.block(block, index) for index, block in enumerate(blocks)],
            "stop_reason": "tool_use" if any(isinstance(block, ToolCall) for block in blocks) else "end_turn",
            "stop_sequence": None,
            "usage": _Messages.usage(),
        }

    @staticmethod
    def stream(blocks: Sequence[Block], id: str, model: str) -> Iterator[tuple[str | None, Any]]:
        start = {
            **_Messages.whole((), id, model),
            "stop_reason": None,
            "usage": {**_Messages.usage(), "output_tokens": 1},
        }

        def event(type: str, **fields: Any) -> tuple[str, dict[str, Any]]:
            return type, {"type": type, **fields}

        def delta(index: int, **fields: Any) -> tuple[str, dict[str, Any]]:
            return event("content_block_delta", index=index, delta=fields)

        yield event("message_start", message=start)
        for index, block in enumerate(blocks):
            match block:
                case Text(text=text):
                    yield event("content_block_start", index=index, content_block={"type": "text", "text": ""})
                    yield from (delta(index, type="text_delta", text=piece) for piece in _pieces(text))
                case Thought(text=text):
                    empty = {"type": "thinking", "thinking": "", "signature": ""}
                    yield event("content_block_start", index=index, content_block=empty)
                    yield delta(index, type="thinking_delta", thinking=text)
                    yield delta(index, type="signature_delta", signature="fake-signature")
                case ToolCall() as call:
                    empty = {"type": "tool_use", "id": call.id, "name": call.name, "input": {}}
                    yield event("content_block_start", index=index, content_block=empty)
                    yield delta(index, type="input_json_delta", partial_json=json.dumps(call.arguments))
            yield event("content_block_stop", index=index)
        stop = "tool_use" if any(isinstance(block, ToolCall) for block in blocks) else "end_turn"
        yield event(
            "message_delta",
            delta={"stop_reason": stop, "stop_sequence": None},
            usage={"output_tokens": OUTPUT_TOKENS},
        )
        yield event("message_stop")


class _Responses:
    """OpenAI Responses."""

    OVERFLOW = {
        "error": {
            "message": "Your input exceeds the context window of this model. Please adjust your input and try again.",
            "type": "invalid_request_error",
            "param": "input",
            "code": "context_length_exceeded",
        }
    }

    @staticmethod
    def items(blocks: Sequence[Block]) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for index, block in enumerate(blocks):
            match block:
                case Text(text=text):
                    content = [{"type": "output_text", "text": text, "annotations": []}]
                    items.append(
                        {
                            "type": "message",
                            "id": f"msg_{index}",
                            "role": "assistant",
                            "status": "completed",
                            "content": content,
                        }
                    )
                case Thought(text=text):
                    items.append(
                        {"type": "reasoning", "id": f"rs_{index}", "summary": [{"type": "summary_text", "text": text}]}
                    )
                case ToolCall() as call:
                    item = {
                        "type": "function_call",
                        "id": f"fc_{index}",
                        "status": "completed",
                        "name": call.name,
                        "arguments": json.dumps(call.arguments),
                        "call_id": call.id,
                    }
                    items.append(item if call.namespace is None else {**item, "namespace": call.namespace})
        return items

    @staticmethod
    def usage() -> dict[str, Any]:
        return {
            "input_tokens": INPUT_TOKENS,
            "input_tokens_details": {"cached_tokens": 0},
            "output_tokens": OUTPUT_TOKENS,
            "output_tokens_details": {"reasoning_tokens": 0},
            "total_tokens": INPUT_TOKENS + OUTPUT_TOKENS,
        }

    @staticmethod
    def whole(blocks: Sequence[Block], id: str, model: str) -> dict[str, Any]:
        return {
            "id": id,
            "object": "response",
            "created_at": 0,
            "status": "completed",
            "model": model,
            "output": _Responses.items(blocks),
            "usage": _Responses.usage(),
        }

    @staticmethod
    def stream(blocks: Sequence[Block], id: str, model: str) -> Iterator[tuple[str | None, Any]]:
        def event(type: str, **fields: Any) -> tuple[str, dict[str, Any]]:
            return type, {"type": type, **fields}

        started = {
            "id": id,
            "object": "response",
            "created_at": 0,
            "status": "in_progress",
            "model": model,
            "output": [],
        }
        yield event("response.created", response=started)
        for index, item in enumerate(_Responses.items(blocks)):
            yield event("response.output_item.added", output_index=index, item=item)
            if item["type"] == "message":
                for piece in _pieces(item["content"][0]["text"]):
                    yield event(
                        "response.output_text.delta",
                        output_index=index,
                        item_id=item["id"],
                        content_index=0,
                        delta=piece,
                    )
            yield event("response.output_item.done", output_index=index, item=item)
        yield event("response.completed", response=_Responses.whole(blocks, id, model))


_DIALECTS = {"chat": _Chat, "messages": _Messages, "responses": _Responses}


def _sse(event: str | None, data: Any) -> bytes:
    text = data if isinstance(data, str) else json.dumps(data)
    return f"{f'event: {event}{chr(10)}' if event else ''}data: {text}\n\n".encode()


class FakeModel:
    """A scripted model. Each model call takes the next reply, and past the script's end the model says "ok".

    `async with FakeModel("hello", ToolCall("ping")) as model:` serves on loopback at `model.url`. `model.requests` logs
    everything that arrived, with its bearer and headers, and `model.calls` what was a model call. `await model.call(0)`
    waits for one. `model.gateway(bearer)` is access to it as a training system's gateway gives it.
    """

    def __init__(self, *replies: Reply) -> None:
        self.requests: list[Request] = []
        self._script: deque[Reply] = deque(replies)
        self._next_id = 0
        self._bearers: set[str] = set()
        self._arrived = asyncio.Event()
        self._released = asyncio.Event()
        self._server = Loopback(self._handle)

    async def __aenter__(self) -> Self:
        await self._server.__aenter__()
        return self

    async def __aexit__(self, *_: object) -> None:
        self.release()
        await self._server.__aexit__()

    @property
    def url(self) -> str:
        """The server's origin. Clients differ on whether a base holds `/v1`, and a path that ends right routes."""
        return self._server.url

    @property
    def calls(self) -> list[Request]:
        return [request for request in self.requests if request.dialect is not None]

    @property
    def tool_calls(self) -> list[Request]:
        """Each call of the environment's tool its MCP server answered."""
        served = (request for request in self.requests if request.message.method == "POST")
        return [request for request in served if request.tool_method == "tools/call"]

    def gateway(self, bearer: str) -> Gateway:
        """Access to this model as a training system's gateway gives it, under `bearer`: its models at its origin, the
        environment's tools at `/mcp`, which answer only a bearer it gave, and `COMPACTION_HEADERS` for each call that
        compacts a context."""
        self._bearers.add(bearer)
        return Gateway(
            origin=self.url,
            bearer=Secret(bearer),
            model=_MODEL,
            tools=f"{self.url}{_TOOLS}",
            compaction_headers=COMPACTION_HEADERS,
        )

    def script(self, replies: Iterable[Reply]) -> None:
        """Add to what the model will say."""
        self._script.extend(replies)

    def release(self) -> None:
        """Let every stalled response go on, now and from now on."""
        self._released.set()

    async def call(self, index: int) -> Request:
        """The model call at `index`, once it has arrived."""
        while len(self.calls) <= index:
            self._arrived.clear()
            await self._arrived.wait()
        return self.calls[index]

    def _log(self, request: Request) -> Request:
        self.requests.append(request)
        self._arrived.set()
        return request

    async def _handle(self, message: Message, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> bool:
        path = message.target.partition("?")[0]
        if message.method == "POST":
            if path.endswith("/count_tokens"):
                self._log(Request(message))
                writer.write(answer(200, json.dumps({"input_tokens": INPUT_TOKENS}).encode()))
                return True
            if path == _TOOLS:
                writer.write(self._serve_tools(self._log(Request(message))))
                return True
            for suffix, dialect in _ROUTES:
                if path.endswith(suffix):
                    return await self._complete(message, dialect, reader, writer)
        self._log(Request(message))
        if message.method == "GET" and path.endswith("/models"):
            models = {"object": "list", "data": [{"id": _MODEL, "object": "model"}], "models": []}
            writer.write(answer(200, json.dumps(models).encode()))
        elif path == _TOOLS:
            writer.write(answer(405))
        else:
            writer.write(answer(200 if message.method == "HEAD" else 404))
        return True

    def _serve_tools(self, request: Request) -> bytes:
        """The environment's tools, as an MCP server serves them over Streamable HTTP, to a bearer it gave alone."""
        if request.bearer not in self._bearers:
            return answer(401)
        frame = request.json
        if "id" not in frame:
            return answer(202)
        match frame.get("method"):
            case "initialize":
                asked = (frame.get("params") or {}).get("protocolVersion", "2025-11-25")
                info = {"name": "fake-environment", "version": "1"}
                result = {"protocolVersion": asked, "capabilities": {"tools": {}}, "serverInfo": info}
            case "tools/list":
                result = {"tools": [_ENVIRONMENT_TOOL]}
            case "tools/call":
                called = (frame.get("params") or {}).get("name")
                result = {"content": [{"type": "text", "text": "pong"}], "isError": called != ENVIRONMENT_TOOL}
            case method:
                error = {"code": -32601, "message": f"no method {method}"}
                return answer(200, json.dumps({"jsonrpc": "2.0", "id": frame["id"], "error": error}).encode())
        return answer(200, json.dumps({"jsonrpc": "2.0", "id": frame["id"], "result": result}).encode())

    async def _complete(
        self, message: Message, dialect: Dialect, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> bool:
        blocks = _blocks(self._script.popleft() if self._script else _DEFAULT_REPLY)
        form = _DIALECTS[dialect]
        if blocks == (Overflow(),):
            self._log(Request(message, dialect))
            writer.write(answer(400, json.dumps(form.OVERFLOW).encode()))
            return True
        self._next_id += 1
        id = f"resp_{self._next_id}"
        request = self._log(Request(message, dialect, id))
        if blocks and isinstance(blocks[0], Stall):
            if not await self._held(reader):
                return False
            blocks = blocks[1:] or _blocks(_DEFAULT_REPLY)
        model = request.model or _MODEL
        if not request.json.get("stream"):
            writer.write(answer(200, json.dumps(form.whole(blocks, id, model)).encode()))
            return True
        writer.write(stream_head())
        for event, data in form.stream(blocks, id, model):
            writer.write(_sse(event, data))
            await writer.drain()
        return False

    async def _held(self, reader: asyncio.StreamReader) -> bool:
        """Wait for a release, and say whether the client stayed to hear it. The look for its leaving is over before the
        connection reads its next request."""
        gone = asyncio.ensure_future(reader.read(1))
        released = asyncio.ensure_future(self._released.wait())
        await asyncio.wait({gone, released}, return_when=asyncio.FIRST_COMPLETED)
        stayed = not gone.done()
        gone.cancel()
        released.cancel()
        await asyncio.gather(gone, released, return_exceptions=True)
        return stayed
