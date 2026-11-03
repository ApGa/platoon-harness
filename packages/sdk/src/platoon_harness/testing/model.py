"""FakeModel: a loopback server in the three dialects harnesses speak, so a real binary runs on a dummy key for free.

It replies from a script and logs every request exactly as it arrived, which makes the log ground truth: "our tool in
the first request" is read from what the harness sent, and never from what it claimed.
"""

import asyncio
import json
from collections import deque
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from functools import cached_property
from typing import Any, Literal, Self

from .loopback import Loopback, Message, answer, stream_head

INPUT_TOKENS = 11
OUTPUT_TOKENS = 3

_DEFAULT_REPLY = "ok"

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


type Block = Text | Thought | ToolCall | Stall
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

    def says(self, text: str) -> bool:
        """Whether this text is anywhere in what the harness sent."""
        return text in self.message.body.decode(errors="replace")

    def offers(self, tool: str) -> bool:
        """Whether the model is shown this tool, in any dialect's shape: a harness prefixes or nests the name."""
        return tool in json.dumps(self.json.get("tools", []))


def _blocks(reply: Reply) -> tuple[Block, ...]:
    if isinstance(reply, str):
        return (Text(reply),)
    return (reply,) if isinstance(reply, Text | Thought | ToolCall | Stall) else tuple(reply)


def _pieces(text: str) -> list[str]:
    """Text as a stream arrives, a word at a time."""
    words = text.split(" ")
    return [f"{word} " for word in words[:-1]] + words[-1:]


class _Chat:
    """OpenAI Chat Completions."""

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
    everything that arrived, and `model.calls` what was a model call. `await model.call(0)` waits for one.
    """

    def __init__(self, *replies: Reply) -> None:
        self.requests: list[Request] = []
        self._script: deque[Reply] = deque(replies)
        self._next_id = 0
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
            for suffix, dialect in _ROUTES:
                if path.endswith(suffix):
                    return await self._complete(message, dialect, reader, writer)
        self._log(Request(message))
        if message.method == "GET" and path.endswith("/models"):
            models = {"object": "list", "data": [{"id": "fake-model", "object": "model"}], "models": []}
            writer.write(answer(200, json.dumps(models).encode()))
        else:
            writer.write(answer(200 if message.method == "HEAD" else 404))
        return True

    async def _complete(
        self, message: Message, dialect: Dialect, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> bool:
        self._next_id += 1
        id = f"resp_{self._next_id}"
        request = self._log(Request(message, dialect, id))
        blocks = _blocks(self._script.popleft() if self._script else _DEFAULT_REPLY)
        if blocks and isinstance(blocks[0], Stall):
            if not await self._held(reader):
                return False
            blocks = blocks[1:] or _blocks(_DEFAULT_REPLY)
        form, model = _DIALECTS[dialect], request.model or "fake-model"
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
