"""FakeModel: each dialect, whole and streamed, and a log that holds what arrived."""

import asyncio
import json

import pytest

from platoon_harness.testing import FakeModel, Stall, Text, Thought, ToolCall
from platoon_harness.testing.loopback import post
from platoon_harness.testing.model import INPUT_TOKENS, OUTPUT_TOKENS

pytestmark = pytest.mark.timeout(30)

CHAT = "/v1/chat/completions"
MESSAGES = "/v1/messages"
RESPONSES = "/v1/responses"


async def ask(model: FakeModel, path: str, **body) -> dict:
    status, reply = await post(f"{model.url}{path}", {"model": "m", **body})
    assert status == 200
    return json.loads(reply)


def events_of(body: bytes) -> list[tuple[str | None, str]]:
    found = []
    for block in body.decode().split("\n\n"):
        if block:
            lines = dict(line.split(": ", 1) for line in block.split("\n"))
            found.append((lines.get("event"), lines["data"]))
    return found


async def stream(model: FakeModel, path: str) -> list[tuple[str | None, str]]:
    status, body = await post(f"{model.url}{path}", {"model": "m", "stream": True})
    assert status == 200
    return events_of(body)


@pytest.mark.parametrize(("path", "dialect"), [(CHAT, "chat"), (MESSAGES, "messages"), (RESPONSES, "responses")])
async def test_each_dialect_has_its_route(path, dialect):
    async with FakeModel() as model:
        await ask(model, path)

        assert model.calls[0].dialect == dialect


@pytest.mark.parametrize(
    "path",
    [
        "/chat/completions",
        "/anything/v1/chat/completions",
        "/v1/messages?beta=true",
        "/responses",
        "/openai/v1/responses",
    ],
)
async def test_a_route_is_known_by_how_its_path_ends(path):
    async with FakeModel() as model:
        await ask(model, path)

        assert model.calls[0].dialect is not None


async def test_chat_answers_text_and_tool_calls():
    call = ToolCall("ping", {"note": "hi"}, id="call_9")
    async with FakeModel("hello", [Text("look"), call]) as model:
        first = await ask(model, CHAT)
        second = await ask(model, CHAT)

    assert first["choices"][0]["message"]["content"] == "hello"
    assert first["choices"][0]["finish_reason"] == "stop"
    assert first["usage"] == {
        "prompt_tokens": INPUT_TOKENS,
        "completion_tokens": OUTPUT_TOKENS,
        "total_tokens": INPUT_TOKENS + OUTPUT_TOKENS,
    }
    message = second["choices"][0]["message"]
    assert second["choices"][0]["finish_reason"] == "tool_calls"
    assert message["content"] == "look"
    assert message["tool_calls"][0]["id"] == "call_9"
    assert json.loads(message["tool_calls"][0]["function"]["arguments"]) == {"note": "hi"}


async def test_chat_streams_deltas_a_finish_usage_and_done():
    async with FakeModel("one two", ToolCall("ping", {"a": 1})) as model:
        text = await stream(model, CHAT)
        tool = await stream(model, CHAT)

    assert text[-1] == (None, "[DONE]")
    chunks = [json.loads(data) for _, data in text[:-1]]
    said = "".join(chunk["choices"][0]["delta"].get("content", "") for chunk in chunks if chunk["choices"])
    assert said == "one two"
    assert chunks[-1]["usage"]["total_tokens"] == INPUT_TOKENS + OUTPUT_TOKENS
    assert chunks[-2]["choices"][0]["finish_reason"] == "stop"
    calls = [
        call
        for _, data in tool[:-1]
        for choice in json.loads(data)["choices"]
        for call in choice["delta"].get("tool_calls", [])
    ]
    assert calls[0]["function"]["name"] == "ping"
    assert json.loads(calls[1]["function"]["arguments"]) == {"a": 1}


async def test_messages_answers_text_thinking_and_tool_use():
    blocks = [Thought("hmm"), Text("look"), ToolCall("ping", {"a": 1}, id="toolu_1")]
    async with FakeModel(blocks) as model:
        reply = await ask(model, MESSAGES)

    assert [block["type"] for block in reply["content"]] == ["thinking", "text", "tool_use"]
    assert reply["content"][2] == {"type": "tool_use", "id": "toolu_1", "name": "ping", "input": {"a": 1}}
    assert reply["stop_reason"] == "tool_use"


async def test_messages_streams_the_named_events_in_order():
    blocks = [Thought("hmm"), Text("look here"), ToolCall("ping", {"a": 1})]
    async with FakeModel(blocks) as model:
        events = await stream(model, MESSAGES)

    names = [name for name, _ in events]
    assert names[0] == "message_start" and names[-2:] == ["message_delta", "message_stop"]
    assert names.count("content_block_start") == names.count("content_block_stop") == 3
    deltas = [json.loads(data)["delta"] for name, data in events if name == "content_block_delta"]
    assert [delta["type"] for delta in deltas] == [
        "thinking_delta",
        "signature_delta",
        "text_delta",
        "text_delta",
        "input_json_delta",
    ]
    assert json.loads(events[-2][1])["delta"]["stop_reason"] == "tool_use"


async def test_responses_answers_text_and_function_calls():
    call = ToolCall("ping", {"a": 1}, id="call_1", namespace="mcp__coord")
    async with FakeModel([Text("look"), call]) as model:
        reply = await ask(model, RESPONSES)

    message, function = reply["output"]
    assert message["content"][0]["text"] == "look"
    assert (function["call_id"], function["namespace"]) == ("call_1", "mcp__coord")
    assert reply["usage"]["input_tokens_details"] == {"cached_tokens": 0}


async def test_responses_streams_created_items_and_completed():
    async with FakeModel("look here") as model:
        events = await stream(model, RESPONSES)

    names = [name for name, _ in events]
    assert names[0] == "response.created" and names[-1] == "response.completed"
    assert "response.output_item.done" in names
    said = "".join(json.loads(data)["delta"] for name, data in events if name == "response.output_text.delta")
    assert said == "look here"
    assert json.loads(events[-1][1])["response"]["id"] == model.calls[0].response_id


async def test_the_log_holds_a_request_exactly_as_it_arrived():
    async with FakeModel() as model:
        await post(f"{model.url}{CHAT}", {"b": 1, "a": "é"}, {"X-Custom": "Value", "Authorization": "Bearer dummy"})

    message = model.requests[0].message
    assert (message.method, message.target) == ("POST", CHAT)
    assert ("X-Custom", "Value") in message.headers
    assert message.header("authorization") == "Bearer dummy"
    assert message.body == json.dumps({"b": 1, "a": "é"}).encode()


async def test_a_request_shows_tools_in_any_dialect_s_shape():
    tools = {
        "chat": [{"type": "function", "function": {"name": "mcp__ph__wait"}}],
        "messages": [{"name": "mcp__ph__wait"}],
        "responses": [{"type": "namespace", "name": "mcp__ph", "tools": [{"name": "wait"}]}],
    }
    async with FakeModel() as model:
        for shape in tools.values():
            await ask(model, CHAT, tools=shape, messages=[{"role": "user", "content": "the prompt"}])

    assert all(call.offers("wait") and not call.offers("claim") for call in model.calls)
    assert model.calls[0].says("the prompt") and not model.calls[0].says("nothing like it")
    assert model.calls[0].model == "m"


async def test_past_the_script_the_model_says_ok():
    async with FakeModel("scripted") as model:
        first, second = await ask(model, CHAT), await ask(model, CHAT)

    assert first["choices"][0]["message"]["content"] == "scripted"
    assert second["choices"][0]["message"]["content"] == "ok"


async def test_a_stall_holds_the_reply_until_released():
    async with FakeModel([Stall(), Text("released")]) as model:
        reply = asyncio.create_task(ask(model, CHAT))
        await model.call(0)

        assert not reply.done()
        model.release()

        assert (await reply)["choices"][0]["message"]["content"] == "released"


async def test_a_client_that_gives_up_on_a_stall_goes_unanswered():
    async with FakeModel(Stall(), "next") as model:
        reply = asyncio.create_task(ask(model, CHAT))
        await model.call(0)
        reply.cancel()
        await asyncio.gather(reply, return_exceptions=True)

        assert (await ask(model, CHAT))["choices"][0]["message"]["content"] == "next"


async def test_side_requests_are_logged_and_answered_but_are_no_calls():
    async with FakeModel() as model:
        status, body = await post(f"{model.url}/v1/messages/count_tokens", {"model": "m"})
        reader, writer = await asyncio.open_connection("127.0.0.1", int(model.url.rpartition(":")[2]))
        writer.write(b"GET /v1/models HTTP/1.1\r\nhost: x\r\ncontent-length: 0\r\n\r\n")
        await writer.drain()
        head = await reader.readuntil(b"\r\n\r\n")
        writer.close()

    assert status == 200 and json.loads(body) == {"input_tokens": INPUT_TOKENS}
    assert b"200" in head
    assert model.calls == []
    assert len(model.requests) == 2


async def test_a_chunked_request_is_logged_whole():
    async with FakeModel() as model:
        reader, writer = await asyncio.open_connection("127.0.0.1", int(model.url.rpartition(":")[2]))
        body = b'{"model": "m"}'
        writer.write(
            b"POST /v1/chat/completions HTTP/1.1\r\nhost: x\r\ntransfer-encoding: chunked\r\n\r\n"
            + hex(len(body))[2:].encode()
            + b"\r\n"
            + body
            + b"\r\n0\r\n\r\n"
        )
        await writer.drain()
        await reader.readuntil(b"\r\n\r\n")
        writer.close()

    assert model.calls[0].message.body == body


async def test_a_script_can_grow_while_it_runs():
    async with FakeModel() as model:
        model.script(["later"])

        assert (await ask(model, CHAT))["choices"][0]["message"]["content"] == "later"
