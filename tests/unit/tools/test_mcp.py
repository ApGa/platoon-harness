"""The server against a harness's side of a real socket: transport first, then what only this layer can do."""

import asyncio
import json
import random
from typing import Annotated

import pytest
from pydantic import Field

from platoon_harness import __version__
from platoon_harness.kernel import Args, Extension, Kernel, ManualClock, Outcome, Principal, Refusal, Refused, Txn, op
from platoon_harness.primitives import PRIMITIVES
from platoon_harness.tools import ToolServer, delivery_text
from platoon_harness.tools import mcp as tool_server
from platoon_harness.tools.surface import harness_name

from ..primitives.support import end_turn, events_of, grant, of_type, result_of, send, spawn, start_turn
from .support import (
    Client,
    connect,
    drained,
    enrolled,
    exchange,
    opened,
    request,
    slept_until,
    text_of,
    tool_call,
    value_of,
)

INITIALIZE = {"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {"protocolVersion": "2025-11-25"}}


# Transport.


@pytest.mark.parametrize(
    ("asked", "answered"),
    [("2025-11-25", "2025-11-25"), ("2025-06-18", "2025-06-18"), ("2026-07-28", "2025-11-25"), (None, "2025-11-25")],
)
async def test_initialize_answers_the_revision_the_client_speaks(lead, asked, answered):
    _, client = lead

    hello = (await client.rpc("initialize", {"protocolVersion": asked}))["result"]

    assert hello["protocolVersion"] == answered
    assert hello["capabilities"] == {"tools": {}}
    assert hello["serverInfo"] == {"name": "platoon-harness", "version": __version__}


async def test_a_reply_is_json_with_no_session(lead):
    reply = await lead[1].post(INITIALIZE)

    assert "content-type: application/json" in reply.head.lower()
    assert "mcp-session-id" not in reply.head.lower()


async def test_server_discover_is_not_implemented(lead):
    assert (await lead[1].rpc("server/discover"))["error"]["code"] == -32601


@pytest.mark.parametrize("method", ["GET", "DELETE"])
async def test_only_post_is_served(server, lead, method):
    reply = await exchange(server.url, request(server.url, method=method, token=lead[1].token))

    assert reply.status == 405
    assert "allow: post" in reply.head.lower()


async def test_a_notification_is_accepted_and_answered_with_nothing(lead):
    reply = await lead[1].post({"jsonrpc": "2.0", "method": "notifications/initialized"})

    assert (reply.status, reply.body) == (202, b"")


async def test_a_batch_is_refused(lead):
    reply = await lead[1].post([INITIALIZE, INITIALIZE])

    assert reply.status == 200
    assert reply.json()["error"]["code"] == -32600


async def test_an_unknown_method_is_refused(lead):
    assert (await lead[1].rpc("resources/list"))["error"]["code"] == -32601


async def test_ping_is_answered(lead):
    assert (await lead[1].rpc("ping"))["result"] == {}


@pytest.mark.parametrize(
    "message",
    [
        {"id": 1, "method": "ping"},
        {"jsonrpc": "1.0", "id": 1, "method": "ping"},
        {"jsonrpc": "2.0", "id": 1},
        {"jsonrpc": "2.0", "id": 1, "method": 7},
        {"jsonrpc": "2.0", "id": None, "method": "ping"},
        {"jsonrpc": "2.0", "id": True, "method": "ping"},
        {"jsonrpc": "2.0", "id": [1], "method": "ping"},
        {"jsonrpc": "2.0", "id": 1.5, "method": "ping"},
        "ping",
        7,
        None,
    ],
)
async def test_what_is_no_request_is_refused(lead, message):
    answer = (await lead[1].post(message)).json()

    assert (answer["id"], answer["error"]["code"]) == (None, -32600)


async def test_params_must_be_an_object(lead):
    answer = (await lead[1].post({"jsonrpc": "2.0", "id": 1, "method": "ping", "params": [1]})).json()

    assert answer["error"]["code"] == -32602


@pytest.mark.parametrize("token", [None, "", "wrong"])
async def test_a_missing_or_bad_bearer_is_refused(server, token):
    reply = await exchange(server.url, request(server.url, b"{}", token=token))

    assert reply.status == 401
    assert "www-authenticate: bearer" in reply.head.lower()


async def test_only_bearer_is_a_credential(server, lead):
    data = request(server.url, b"{}", Authorization=f"Basic {lead[1].token}")

    assert (await exchange(server.url, data)).status == 401


async def test_a_foreign_origin_is_refused(server, lead):
    data = request(server.url, b"{}", token=lead[1].token, Origin="http://evil.example")

    assert (await exchange(server.url, data)).status == 403


async def test_an_origin_on_this_address_is_allowed(server, lead):
    origin = server.url.removesuffix("/mcp")
    data = request(server.url, json.dumps(INITIALIZE).encode(), token=lead[1].token, Origin=origin)

    assert (await exchange(server.url, data)).status == 200


async def test_a_foreign_host_is_refused(server, lead):
    data = request(server.url, b"{}", token=lead[1].token).replace(b"Host: 127.0.0.1", b"Host: evil.example")

    assert (await exchange(server.url, data)).status == 421


async def test_nothing_is_served_on_another_path(server, lead):
    url = server.url.replace("/mcp", "/other")

    assert (await exchange(server.url, request(url, b"{}", token=lead[1].token))).status == 404


async def test_a_token_of_an_ended_agent_is_refused(kernel, server, lead, worker):
    _, client = worker
    assert not (await client.call("agent_finish", {"gist": "done"}))["isError"]

    reply = await client.post(INITIALIZE)

    assert reply.status == 401


@pytest.mark.parametrize(
    "body",
    [
        b"{",
        b"not json",
        b"\xff\xfe\x00",
        b'{"jsonrpc":"2.0","id":1,"method":"ping","x":NaN}',
        b'{"jsonrpc":"2.0","id":1,"method":"ping","x":Infinity}',
        b"[" * 200_000,
    ],
    ids=["cut", "words", "bytes", "nan", "infinity", "deep"],
)
async def test_malformed_json_is_a_parse_error(server, lead, body):
    reply = await exchange(server.url, request(server.url, body, token=lead[1].token))

    assert reply.status == 200
    assert (reply.json()["id"], reply.json()["error"]["code"]) == (None, -32700)


async def test_arguments_nested_deep_cannot_crash_the_server(server, lead):
    _, client = lead
    deep = b'{"a":' * 500 + b"1" + b"}" * 500
    params = b'{"name":"task_add","arguments":' + deep + b"}"
    body = b'{"jsonrpc":"2.0","id":1,"method":"tools/call","params":' + params + b"}"

    reply = await exchange(server.url, request(server.url, body, token=client.token))

    assert reply.status == 200
    assert reply.json()["result"]["isError"]
    assert "invalid" in text_of(reply.json()["result"])


async def test_a_head_too_large_is_refused(server, lead):
    data = request(server.url, token=lead[1].token, Padding="x" * 32 * 1024)

    assert (await exchange(server.url, data)).status == 431


async def test_an_oversized_body_is_refused_before_it_is_read(server, lead):
    data = request(server.url, token=lead[1].token).replace(b"Content-Length: 0", b"Content-Length: 104857600")

    assert (await exchange(server.url, data)).status == 413


async def test_a_length_past_any_integer_is_refused(server, lead):
    data = request(server.url, token=lead[1].token).replace(b"Content-Length: 0", b"Content-Length: " + b"9" * 5000)

    assert (await exchange(server.url, data)).status == 413


@pytest.mark.parametrize(
    ("change", "status"),
    [
        ((b"Content-Length: 0", b"Content-Length: -1"), 400),
        ((b"Content-Length: 0", b"Content-Length: 1e3"), 400),
        ((b"Content-Length: 0", b"Content-Length: 0\r\nContent-Length: 5"), 400),
        ((b"Content-Length: 0\r\n", b""), 411),
        ((b"Content-Length: 0", b"Transfer-Encoding: chunked"), 411),
        ((b"Content-Type: application/json", b"no colon here"), 400),
        ((b"Content-Type: application/json", b"Bad Name: x"), 400),
        ((b"POST /mcp HTTP/1.1", b"POST /mcp"), 400),
        ((b"POST /mcp HTTP/1.1", b"POST  /mcp HTTP/1.1"), 400),
        ((b"POST /mcp HTTP/1.1", b"POST /mcp SPDY/3"), 400),
    ],
)
async def test_a_request_that_is_not_plain_is_refused(server, lead, change, status):
    data = request(server.url, token=lead[1].token).replace(*change)

    assert (await exchange(server.url, data)).status == status


async def test_a_surface_nobody_knows_is_refused(server, lead):
    data = request(f"{server.url}?surface=nonsense", token=lead[1].token)

    assert (await exchange(server.url, data)).status == 400


async def test_a_surface_changes_words_and_not_what_a_token_may_do(lead):
    plain = {tool["name"] for tool in await lead[1].list_tools()}
    shell = await Client(f"{lead[1].url}?surface=ph", lead[1].token).list_tools()

    assert {tool["name"] for tool in shell} == plain
    assert any("`ph peers`" in tool["description"] for tool in shell)


async def test_a_stranger_cannot_make_the_server_read_a_body(server):
    head = request(server.url).replace(b"Content-Length: 0", b"Content-Length: 1000")

    assert (await exchange(server.url, head)).status == 401


async def test_a_slow_client_is_dropped_at_the_deadline(server, lead, clock):
    reader, writer = await connect(server.url)
    writer.write(request(server.url, token=lead[1].token)[:20])
    await writer.drain()
    await slept_until(clock, clock.now() + 10.0)

    clock.advance(10.0)

    async with asyncio.timeout(10):
        assert await reader.read() == b""
    writer.close()


async def test_a_client_that_stops_mid_body_is_dropped_at_the_deadline(server, lead, clock):
    """Each part has the deadline from the part before, so the clock moves between parts to tell their waits apart."""
    head, _, _ = request(server.url, b"x" * 100, token=lead[1].token).partition(b"\r\n\r\n")
    reader, writer = await connect(server.url)
    start = clock.now()
    for n, part in enumerate((head + b"\r\n\r\n", b"x" * 50)):
        await slept_until(clock, start + n + 10.0)
        clock.advance(1.0)
        writer.write(part)
        await writer.drain()
    await slept_until(clock, start + 12.0)

    clock.advance(10.0)

    async with asyncio.timeout(10):
        assert await reader.read() == b""
    writer.close()


async def test_a_client_that_leaves_mid_request_costs_nothing(server, lead):
    _, writer = await connect(server.url)
    writer.write(request(server.url, b"x" * 100, token=lead[1].token)[:-50])
    await writer.drain()
    writer.close()

    assert (await lead[1].rpc("ping"))["result"] == {}


async def test_an_idle_client_costs_nothing(kernel, server, lead):
    _, client = lead
    await client.list_tools()
    head = kernel.head
    tasks = asyncio.all_tasks()

    reply = await client.post(INITIALIZE)
    await client.rpc("tools/list")
    await drained(server)

    assert "connection: close" in reply.head.lower()
    assert kernel.head == head
    assert asyncio.all_tasks() <= tasks


async def test_connections_past_the_limit_are_refused(server, clock, monkeypatch):
    monkeypatch.setattr(server, "connections", 1)
    _, held = await connect(server.url)
    await slept_until(clock, 1010.0)

    reply = await exchange(server.url, b"")

    assert reply.status == 503
    held.close()


async def test_hostile_bytes_cannot_stop_the_server(server, lead):
    rng = random.Random(7)
    good = request(server.url, json.dumps(INITIALIZE).encode(), token=lead[1].token)
    for _ in range(64):
        data = bytearray(good)
        for _ in range(rng.randrange(1, 16)):
            data[rng.randrange(len(data))] = rng.randrange(256)
        reader, writer = await connect(server.url)
        writer.write(bytes(data[: rng.randrange(len(data))]) + b"\r\n\r\n")
        writer.write_eof()
        async with asyncio.timeout(10):
            await reader.read()
        writer.close()

    await drained(server)
    assert (await lead[1].post(INITIALIZE)).status == 200


async def test_a_fault_in_the_server_is_a_500_and_the_server_lives(kernel, server, lead, monkeypatch, caplog):
    def fault(token: str) -> None:
        raise RuntimeError("a bug")

    with monkeypatch.context() as patch:
        patch.setattr(kernel, "authenticate", fault)
        reply = await lead[1].post(INITIALIZE)

    assert reply.status == 500
    assert "a request failed" in caplog.text
    assert (await lead[1].post(INITIALIZE)).status == 200


async def test_a_closed_kernel_is_503(kernel, server, lead):
    kernel.close()

    assert (await lead[1].post(INITIALIZE)).status == 503


async def test_a_connection_that_starts_as_the_server_stops_is_turned_away(kernel, lead):
    server = ToolServer(kernel)
    await server.start()
    url = server.url
    server._servers, started = [], server._servers

    assert (await exchange(url, b"")).status == 503

    server._servers = started
    await server.stop()


async def test_url_needs_a_started_server(kernel):
    with pytest.raises(RuntimeError, match="started"):
        _ = ToolServer(kernel).url


async def test_stop_twice_is_harmless(kernel):
    server = ToolServer(kernel)
    await server.start()

    await server.stop()
    await server.stop()


async def test_two_ops_that_read_as_one_tool_are_refused(tmp_path):
    @op("a.b_c", tool=True)
    def first(txn: Txn, a: Args) -> None:
        """First."""

    @op("a_b.c", tool=True)
    def second(txn: Txn, a: Args) -> None:
        """Second."""

    extensions = (Extension("a", ops=[first]), Extension("a_b", ops=[second]))

    with pytest.raises(Refused, match=r"a_b_c is defined by both a\.b_c and a_b\.c"):
        Kernel.open(tmp_path / "session", clock=ManualClock(1.0), extensions=extensions)


async def test_an_extensions_op_is_a_tool_with_no_core_edit(tmp_path):
    class Cast(Args):
        choice: Annotated[str, Field(description="What you vote for.")]

    @op("ballot.cast", on=lambda a: "ballot", tool=True)
    def cast(txn: Txn, a: Cast) -> dict[str, str]:
        """Cast a vote, then call `peers`. Refused never."""
        txn.emit("ballot.voted", "ballot", gist=a.choice)
        return {"choice": a.choice}

    extensions = (*PRIMITIVES, Extension("ballot", ops=[cast]))
    kernel = Kernel.open(tmp_path / "session", clock=ManualClock(1.0), extensions=extensions)
    server = ToolServer(kernel)
    await server.start()
    result_of(await kernel.submit(kernel.runtime, "session.open", {"roles": {"worker": {}}}))
    await grant(kernel, "all", "ops.list")
    await grant(kernel, "agent", "ballot.*")
    await grant(kernel, "agent", "peers")
    _, client = await enrolled(kernel, server, "voter")

    listed = {tool["name"]: tool for tool in await client.list_tools()}

    assert "`peers`" in listed["ballot_cast"]["description"]
    assert value_of(await client.call("ballot_cast", {"choice": "yes"})) == {"choice": "yes"}
    await server.stop()
    kernel.close()


# Identity.


async def test_a_forced_caller_is_refused_and_journaled(kernel, lead):
    _, client = lead
    head = kernel.head

    result = await client.call("message_send", {"to": "@lead", "gist": "hi", "caller": "root"})

    assert result["isError"]
    assert "invalid" in text_of(result) and "caller" in text_of(result)
    refused = of_type(kernel, "op.refused", after=head)
    assert [(event.actor, event.outcome.refusal.code) for event in refused] == [("agent:lead", "invalid")]


async def test_identity_comes_only_from_the_token(kernel, lead):
    _, client = lead
    params = {
        "name": "peers",
        "arguments": {},
        "clientInfo": {"name": "human:root"},
        "_meta": {"caller": "human:root", "principal": "runtime", "callId": "x"},
    }

    await client.rpc("tools/call", params)
    result = await client.rpc(
        "tools/call", {**params, "name": "task_add", "arguments": {"queue": "tasks", "gist": "x"}}
    )

    assert not result["result"]["isError"]
    assert of_type(kernel, "task.added")[-1].actor == "agent:lead"


async def test_one_session_s_agent_token_is_refused_by_another_session_s_tool_plane(server, lead, tmp_path, clock):
    """Identity: run isolation. A token's hash is journaled in its own session alone, so an agent of the same name and
    role in another session is another principal, on a token of its own, and neither token opens the other's plane."""
    other = await opened(tmp_path / "other", clock)
    elsewhere = ToolServer(other)
    await elsewhere.start()
    try:
        _, theirs = await enrolled(other, elsewhere, "lead", role="lead")
        head = other.head
        ours_there = Client(elsewhere.url, lead[1].token)
        theirs_here = Client(server.url, theirs.token)

        refused = [await client.post(INITIALIZE) for client in (ours_there, theirs_here)]
        called = await ours_there.post(tool_call("task_add", {"queue": "tasks", "gist": "from another session"}))
        answered = [await client.rpc("ping") for client in (lead[1], theirs)]
    finally:
        await elsewhere.stop()
        other.close()

    assert [reply.status for reply in (*refused, called)] == [401, 401, 401]
    assert all("result" in answer for answer in answered)
    assert other.head == head


async def test_a_query_that_decoding_refuses_is_journaled(kernel, lead):
    _, client = lead
    head = kernel.head

    result = await client.call("peers", {"caller": "root"})

    assert result["isError"] and "invalid" in text_of(result)
    refused = of_type(kernel, "op.refused", after=head)
    assert [(event.actor, event.data["op"], event.data["code"]) for event in refused] == [
        ("agent:lead", "peers", "invalid")
    ]


async def test_a_query_that_passes_decoding_journals_nothing(kernel, lead):
    head = kernel.head

    assert value_of(await lead[1].call("peers"))["peers"] == []
    assert kernel.head == head


async def test_tools_list_is_what_the_token_may_do(lead, worker):
    led = {tool["name"] for tool in await lead[1].list_tools()}
    works = {tool["name"] for tool in await worker[1].list_tools()}

    assert {"task_add", "agent_spawn"} <= led - works
    assert {"task_claim", "task_complete"} <= works - led
    assert "wait" in led & works


async def test_tools_list_journals_nothing(kernel, lead):
    head = kernel.head

    await lead[1].list_tools()

    assert kernel.head == head


async def test_a_role_whose_tools_narrow_its_grants(kernel, server, lead):
    _, client = await enrolled(kernel, server, "n1", role="narrow", by=lead[0])

    assert {tool["name"] for tool in await client.list_tools()} == {
        "blob_get",
        "message_read",
        "message_send",
        "wait",
    }


async def test_a_call_past_the_list_is_refused_at_call_time_and_journaled(kernel, server, lead):
    _, client = await enrolled(kernel, server, "n1", role="narrow", by=lead[0])
    head = kernel.head

    result = await client.call("agent_finish", {})

    assert result["isError"] and "not_permitted" in text_of(result)
    assert [event.data["op"] for event in of_type(kernel, "op.refused", after=head)] == ["agent.finish"]


@pytest.mark.parametrize(
    "name", ["no_such_tool", "agent_report", "session_close", "ops_list", "session.close", 7, None]
)
async def test_what_is_no_tool_cannot_be_called(kernel, lead, name):
    head = kernel.head

    answer = await lead[1].rpc("tools/call", {"name": name, "arguments": {}})

    assert answer["error"]["code"] == -32602
    assert kernel.head == head


@pytest.mark.parametrize("arguments", [[1], "x", 7])
async def test_arguments_must_be_an_object(lead, arguments):
    answer = await lead[1].rpc("tools/call", {"name": "peers", "arguments": arguments})

    assert answer["error"]["code"] == -32602


# The idempotency key.


@pytest.mark.parametrize(
    "anchor", [{"claudecode__toolUseId": "toolu_1"}, {"callId": "exec-1"}], ids=["claude", "codex"]
)
async def test_a_retry_after_a_timeout_is_one_logical_operation(kernel, lead, worker, anchor):
    await lead[1].call("task_add", {"queue": "tasks", "gist": "one"})
    await lead[1].call("task_add", {"queue": "tasks", "gist": "two"})
    arguments = {"queue": "tasks"}

    first = await worker[1].call("task_claim", arguments, **anchor)
    second = await worker[1].call("task_claim", arguments, **anchor)

    assert value_of(first)["task"] == value_of(second)["task"] == "1"
    assert len(of_type(kernel, "task.claimed")) == 1


async def test_a_new_id_is_a_new_call(kernel, lead, worker):
    message = {"to": "@lead", "gist": "same words"}

    await worker[1].call("message_send", message, callId="exec-1")
    await worker[1].call("message_send", message, callId="exec-2")

    assert len(of_type(kernel, "message.sent")) == 2


async def test_one_id_can_cover_several_calls_of_a_script(kernel, lead, worker):
    await worker[1].call("message_send", {"to": "@lead", "gist": "one"}, callId="exec-1")
    await worker[1].call("message_send", {"to": "@lead", "gist": "two"}, callId="exec-1")
    result = await worker[1].call("peers", callId="exec-1")

    assert not result["isError"]
    assert [event.gist for event in of_type(kernel, "message.sent")] == ["one", "two"]


async def test_one_id_from_two_agents_is_two_calls(kernel, server, lead, worker):
    await lead[1].call("task_add", {"queue": "tasks", "gist": "one"}, callId="exec-1")
    await lead[1].call("task_add", {"queue": "tasks", "gist": "two"}, callId="exec-2")
    _, other = await enrolled(kernel, server, "w2", by=lead[0])

    first = await worker[1].call("task_claim", {"queue": "tasks"}, callId="exec-1")
    second = await other.call("task_claim", {"queue": "tasks"}, callId="exec-1")

    assert value_of(first)["task"] != value_of(second)["task"]


async def test_the_turn_anchors_a_call_with_no_id(kernel, lead, worker):
    await lead[1].call("task_add", {"queue": "tasks", "gist": "one"})
    await lead[1].call("task_add", {"queue": "tasks", "gist": "two"})
    await start_turn(kernel, "w1")

    first = await worker[1].call("task_claim", {"queue": "tasks"})
    retry = await worker[1].call("task_claim", {"queue": "tasks"})

    assert value_of(first) == value_of(retry)
    assert len(of_type(kernel, "task.claimed")) == 1


async def test_a_call_repeated_with_no_id_says_it_is_a_repeat(kernel, lead, worker):
    await lead[1].call("task_add", {"queue": "tasks", "gist": "one"})
    await start_turn(kernel, "w1")

    first = await worker[1].call("task_claim", {"queue": "tasks"})
    repeat = await worker[1].call("task_claim", {"queue": "tasks"})

    assert len(first["content"]) == 1
    assert "nothing ran" in repeat["content"][1]["text"]


async def test_a_call_repeated_under_one_id_is_no_repeat_to_the_model(kernel, lead, worker):
    await lead[1].call("task_add", {"queue": "tasks", "gist": "one"})

    await worker[1].call("task_claim", {"queue": "tasks"}, callId="exec-1")
    retry = await worker[1].call("task_claim", {"queue": "tasks"}, callId="exec-1")

    assert len(retry["content"]) == 1


async def test_a_new_turn_is_a_new_call(kernel, server, lead):
    _, keeper = await enrolled(kernel, server, "w2", by=lead[0], stays=True)
    await start_turn(kernel, "w2", "t1")
    await keeper.call("message_send", {"to": "@lead", "gist": "same words"})
    await end_turn(kernel, "w2")
    await start_turn(kernel, "w2", "t2")
    await keeper.call("message_send", {"to": "@lead", "gist": "same words"})

    assert [event.turn for event in of_type(kernel, "message.sent") if event.actor == "agent:w2"] == ["t1", "t2"]


async def test_out_of_a_turn_a_call_with_no_id_has_no_key(kernel, lead, worker):
    await worker[1].call("message_send", {"to": "@lead", "gist": "same words"})
    await worker[1].call("message_send", {"to": "@lead", "gist": "same words"})

    assert len(of_type(kernel, "message.sent")) == 2


async def test_anchors_are_correlation_evidence_only(kernel, lead):
    await lead[1].call("task_add", {"queue": "tasks", "gist": "one"}, claudecode__toolUseId="toolu_1")
    await lead[1].call("peers", {"caller": "x"}, callId="exec-2")

    added = of_type(kernel, "task.added")[-1]
    refused = of_type(kernel, "op.refused")[-1]

    assert (added.actor, added.native) == ("agent:lead", {"claudecode/toolUseId": "toolu_1"})
    assert (refused.actor, refused.native) == ("agent:lead", {"callId": "exec-2"})
    assert all(event.model is None for event in (added, refused))


@pytest.mark.parametrize("anchor", ["", "x" * 257, "line\nbreak"], ids=["empty", "long", "control"])
async def test_an_id_that_could_not_be_journaled_is_no_anchor(kernel, lead, anchor):
    await lead[1].call("task_add", {"queue": "tasks", "gist": "one"}, callId=anchor)
    await lead[1].call("task_add", {"queue": "tasks", "gist": "one"}, callId=anchor)

    assert [event.native for event in of_type(kernel, "task.added")] == [{}, {}]


async def test_concurrent_calls_on_one_token_all_land(kernel, lead):
    _, client = lead
    calls = [client.call("task_add", {"queue": "tasks", "gist": f"task {n}"}, callId=str(n)) for n in range(16)]

    results = await asyncio.gather(*calls)

    assert sorted(int(value_of(result)["task"]) for result in results) == list(range(1, 17))


async def test_concurrent_retries_of_one_call_are_one_operation(kernel, lead, worker):
    await lead[1].call("task_add", {"queue": "tasks", "gist": "one"})
    calls = [worker[1].call("task_claim", {"queue": "tasks"}, callId="exec-1") for _ in range(8)]

    results = await asyncio.gather(*calls)

    assert {value_of(result)["fence"] for result in results} == {of_type(kernel, "task.claimed")[0].seq}


async def test_too_many_calls_at_once_are_told_to_retry(kernel, lead):
    _, client = lead
    calls = [client.call("task_add", {"queue": "tasks", "gist": f"task {n}"}, callId=str(n)) for n in range(200)]

    results = await asyncio.gather(*calls)

    assert all(not result["isError"] or "busy" in text_of(result) for result in results)


# Bodies.


async def test_a_body_argument_is_offered_as_text(kernel, lead):
    await lead[1].call("task_add", {"queue": "tasks", "gist": "see body", "body": "all the detail"})

    cited = of_type(kernel, "task.added")[-1].data["body"]

    assert cited.startswith("sha256:")
    assert kernel.get_body(cited.removeprefix("sha256:")) == b"all the detail"


async def test_a_body_that_is_null_stays_null(kernel, lead):
    await lead[1].call("task_add", {"queue": "tasks", "gist": "no body", "body": None})

    assert of_type(kernel, "task.added")[-1].data["body"] is None


async def test_a_body_that_is_no_text_is_refused(kernel, lead):
    result = await lead[1].call("task_add", {"queue": "tasks", "gist": "x", "body": 7})

    assert result["isError"] and "invalid" in text_of(result)


async def test_a_lone_surrogate_in_a_body_is_refused(kernel, lead):
    result = await lead[1].call("task_add", {"queue": "tasks", "gist": "x", "body": "\ud800"})

    assert result["isError"] and "invalid" in text_of(result)


async def test_a_retried_body_is_one_operation(kernel, lead):
    arguments = {"queue": "tasks", "gist": "x", "body": "the same text"}

    await lead[1].call("task_add", arguments, callId="exec-1")
    await lead[1].call("task_add", arguments, callId="exec-1")

    assert len(of_type(kernel, "task.added")) == 1


async def test_a_claim_shows_its_task_body_as_text(kernel, lead, worker):
    await lead[1].call("task_add", {"queue": "tasks", "gist": "see body", "body": "what to do"})
    head = kernel.head

    claimed = value_of(await worker[1].call("task_claim", {"queue": "tasks"}))

    assert (claimed["ref"], claimed["body"], claimed["text"]) == ("task/tasks/1@1", True, "what to do")
    offered = [
        event for event in of_type(kernel, "context.offered", after=head) if event.data["items"][0]["form"] == "body"
    ]
    assert offered[0].data["items"][0]["ref"] == "task/tasks/1@1"


async def test_a_body_in_blobs_is_fetched_so_a_model_sees_text(kernel, tmp_path, lead):
    text = "x" * 100 + "\n"
    await lead[1].call("board_post", {"board": "notes", "name": "big", "gist": "big", "body": text * 800})
    assert any((tmp_path / "session" / "blobs").rglob("*"))

    shown = value_of(await lead[1].call("board_get", {"board": "notes", "name": "big"}))

    assert shown["text"].startswith(text)
    assert shown["lines"] == 800


async def test_what_the_surface_fetched_is_recorded_as_exposure(kernel, lead):
    body = "line\n" * 20_000
    await lead[1].call("board_post", {"board": "notes", "name": "big", "gist": "big", "body": body})
    head = kernel.head

    shown = value_of(await lead[1].call("board_get", {"board": "notes", "name": "big"}))

    items = [item for event in of_type(kernel, "context.offered", after=head) for item in event.data["items"]]
    assert [item["form"] for item in items] == ["gist", "body"]
    assert items[1]["ref"].startswith(shown["ref"] + "#L1-")


async def test_a_long_body_is_cut_with_a_ref_saying_where_the_rest_is(kernel, lead):
    body = "".join(f"line {number}\n" for number in range(40_000))
    await lead[1].call("board_post", {"board": "notes", "name": "big", "gist": "big", "body": body})

    result = await lead[1].call("board_get", {"board": "notes", "name": "big"})

    assert len(text_of(result).encode()) <= tool_server._RESULT_LIMIT
    shown = value_of(result)
    assert shown["rest"].startswith(shown["ref"] + "#L")
    assert shown["lines"] == 40_000


async def test_reading_on_from_rest_reaches_the_end_of_a_body(kernel, lead):
    body = "".join(f"line {number}\n" for number in range(40_000))
    await lead[1].call("board_post", {"board": "notes", "name": "big", "gist": "big", "body": body})

    shown = value_of(await lead[1].call("board_get", {"board": "notes", "name": "big"}))
    read = shown["text"]
    while shown["rest"]:
        asked = shown["rest"]
        shown = value_of(await lead[1].call("blob_get", {"ref": asked}))
        assert shown["ref"].partition("-")[0] == asked.partition("-")[0], "a ref names exactly what it gave"
        read += shown["text"]

    assert read == body


async def test_a_range_past_the_end_of_a_fetched_body_is_refused_with_how_many_there_are(lead):
    body = "line\n" * 20_000
    await lead[1].call("board_post", {"board": "notes", "name": "big", "gist": "big", "body": body})

    result = await lead[1].call("board_get", {"board": "notes", "name": "big", "range": "L90000-90001"})

    assert result["isError"] and "20000" in text_of(result)


async def test_a_range_of_a_fetched_body_is_honored(lead):
    body = "".join(f"line {number}\n" for number in range(20_000))
    await lead[1].call("board_post", {"board": "notes", "name": "big", "gist": "big", "body": body})

    shown = value_of(await lead[1].call("board_get", {"board": "notes", "name": "big", "range": "L3-4"}))

    assert shown["text"] == "line 2\nline 3\n"


async def test_a_read_with_bodies_gets_those_in_blobs_too(kernel, lead, worker):
    body = "line\n" * 20_000
    await lead[1].call("message_send", {"to": "@w1", "gist": "big", "body": body})

    read = value_of(await worker[1].call("message_read", {"bodies": True}))

    assert read["entries"][0]["text"].startswith("line\n")
    assert read["entries"][0]["rest"]


async def test_a_read_without_bodies_fetches_none(kernel, lead, worker):
    await lead[1].call("message_send", {"to": "@w1", "gist": "big", "body": "line\n" * 20_000})

    read = value_of(await worker[1].call("message_read"))

    assert "text" not in read["entries"][0]


async def posted(kernel: Kernel, lead: tuple[Principal, Client], data: bytes) -> tuple[str, str]:
    """A board object of `lead`'s whose body is `data`, by its ref, and that body's hash."""
    sha256 = await kernel.put_body(data)
    post = {"board": "notes", "name": "it", "gist": "it", "body": f"sha256:{sha256}"}
    return result_of(await kernel.submit(lead[0], "board.post", post))["ref"], sha256


async def test_a_binary_body_stays_null(kernel, lead):
    ref, _ = await posted(kernel, lead, b"\xff\xfe" * 100)

    shown = value_of(await lead[1].call("blob_get", {"ref": ref}))

    assert shown["text"] is None


async def test_a_redacted_body_stays_null(kernel, lead):
    ref, sha256 = await posted(kernel, lead, b"x" * 100_000)
    result_of(await kernel.submit(kernel.runtime, "body.tombstone", {"sha256": sha256}))

    result = await lead[1].call("blob_get", {"ref": ref})

    assert result["isError"] and "not_found" in text_of(result)


async def test_a_body_too_large_to_read_stays_null(kernel, lead, monkeypatch):
    monkeypatch.setattr(tool_server, "_BODY_READ_LIMIT", 70_000)
    ref, _ = await posted(kernel, lead, b"x" * 100_000)

    assert value_of(await lead[1].call("blob_get", {"ref": ref}))["text"] is None


async def test_one_line_too_long_for_a_result_stays_null_and_says_how_many(kernel, lead):
    ref, _ = await posted(kernel, lead, b"x" * 100_000)

    assert value_of(await lead[1].call("blob_get", {"ref": ref}))["text"] is None


async def test_a_result_with_no_body_is_left_alone(lead):
    await lead[1].call("board_post", {"board": "notes", "name": "small", "gist": "small"})

    assert "text" not in value_of(await lead[1].call("board_get", {"board": "notes", "name": "small"}))


# Hold.


async def test_hold_keeps_the_call_open_until_the_wait_holds(kernel, lead, worker, clock):
    await start_turn(kernel, "w1")
    held = asyncio.create_task(worker[1].call("wait", {"from": ["lead"], "hold": 20.0}))
    await slept_until(clock, 1020.0)

    await send(kernel, lead[0], "@w1", "go on")

    assert value_of(await held)["state"] == "released"


async def test_hold_runs_out_as_pending_and_the_wait_stays(kernel, lead, worker, clock):
    await start_turn(kernel, "w1")
    held = asyncio.create_task(worker[1].call("wait", {"from": ["lead"], "hold": 20.0}))
    await slept_until(clock, 1020.0)

    clock.advance(20.0)

    shown = value_of(await held)
    assert shown["state"] == "pending"
    assert value_of(await worker[1].call("wait_progress", {"id": shown["id"]}))["state"] == "open"


async def test_hold_stays_below_the_harness_tool_timeout(kernel, server, lead):
    _, client = await enrolled(kernel, server, "w2", by=lead[0], tool_timeout_s=60.0)

    result = await client.call("wait", {"from": ["lead"], "hold": 60.0})

    assert result["isError"] and "unsupported" in text_of(result)


async def test_hold_works_for_a_role_that_cannot_ask_how_a_wait_stands(kernel, server, lead, clock):
    _, client = await enrolled(kernel, server, "n1", role="narrow", by=lead[0])
    assert "wait_progress" not in {tool["name"] for tool in await client.list_tools()}
    held = asyncio.create_task(client.call("wait", {"from": ["lead"], "hold": 20.0}))
    await slept_until(clock, 1020.0)

    await send(kernel, lead[0], "@n1", "go on")

    assert value_of(await held)["state"] == "released"


async def test_a_retried_held_wait_is_one_wait(kernel, lead, worker, clock):
    await start_turn(kernel, "w1")
    arguments = {"from": ["lead"], "hold": 20.0}
    first = asyncio.create_task(worker[1].call("wait", arguments, callId="exec-1"))
    await slept_until(clock, 1020.0)
    clock.advance(20.0)
    await first

    second = asyncio.create_task(worker[1].call("wait", arguments, callId="exec-1"))
    await slept_until(clock, 1040.0)
    clock.advance(20.0)
    await second

    assert len(of_type(kernel, "wait.registered")) == 1
    assert of_type(kernel, "wait.cancelled") == []


async def test_a_client_that_vanishes_during_a_held_wait_frees_its_task(kernel, server, lead, worker, clock):
    await start_turn(kernel, "w1")
    message = tool_call("wait", {"from": ["lead"], "hold": 20.0})
    _, writer = await connect(server.url)
    writer.write(request(server.url, json.dumps(message).encode(), token=worker[1].token))
    await writer.drain()
    await slept_until(clock, 1020.0)
    assert server._serving

    writer.close()

    await drained(server)
    assert 1020.0 not in clock.wakes
    wait = of_type(kernel, "wait.registered")[-1].seq
    assert result_of(kernel.query(kernel.runtime, "wait.progress", {"id": wait}))["state"] == "open"


async def test_stop_drops_a_held_call_and_keeps_its_wait(kernel, server, lead, worker, clock):
    await start_turn(kernel, "w1")
    held = asyncio.create_task(worker[1].post(tool_call("wait", {"from": ["lead"], "hold": 20.0})))
    await slept_until(clock, 1020.0)

    await server.stop()

    assert (await held).status == 0, "the socket closed with no answer"
    wait = of_type(kernel, "wait.registered")[-1].seq
    assert result_of(kernel.query(kernel.runtime, "wait.progress", {"id": wait}))["state"] == "open"


async def test_a_wait_that_needs_no_hold_returns_at_once(kernel, lead, worker):
    await start_turn(kernel, "w1")

    assert value_of(await worker[1].call("wait", {"from": ["lead"]}))["state"] == "parked"


async def test_a_wait_that_closes_under_a_hold_says_how(kernel, lead, worker, clock):
    await start_turn(kernel, "w1")
    held = asyncio.create_task(worker[1].call("wait", {"from": ["lead"], "hold": 20.0}))
    await slept_until(clock, 1020.0)

    result_of(await kernel.submit(worker[0], "wait.cancel", {}))

    assert value_of(await held)["state"] == "cancelled"


async def test_a_kernel_closing_under_a_hold_is_a_refusal(kernel, lead, worker, clock):
    await start_turn(kernel, "w1")
    held = asyncio.create_task(worker[1].call("wait", {"from": ["lead"], "hold": 20.0}))
    await slept_until(clock, 1020.0)

    kernel.close()

    result = await held
    assert result["isError"] and "unavailable" in text_of(result)


# Steer notices.


async def test_a_tool_result_carries_pending_steer_notices(kernel, server, lead):
    _, client = await enrolled(kernel, server, "s1", role="steered", by=lead[0])
    await start_turn(kernel, "s1")
    await send(kernel, lead[0], "@s1", "stop that")
    head = kernel.head

    result = await client.call("peers")

    assert "stop that" in result["content"][1]["text"]
    assert of_type(kernel, "context.offered", after=head)[0].data["how"] == "notice"
    assert result_of(kernel.query(kernel.runtime, "effect.ready", {"kind": "deliver"})) == []


async def test_a_notice_is_carried_once(kernel, server, lead):
    _, client = await enrolled(kernel, server, "s1", role="steered", by=lead[0])
    await start_turn(kernel, "s1")
    await send(kernel, lead[0], "@s1", "stop that")

    await client.call("peers")
    again = await client.call("peers")

    assert len(again["content"]) == 1


async def test_a_refused_call_carries_notices_too(kernel, server, lead):
    _, client = await enrolled(kernel, server, "s1", role="steered", by=lead[0])
    await start_turn(kernel, "s1")
    await send(kernel, lead[0], "@s1", "stop that")

    result = await client.call("peers", {"caller": "root"})

    assert result["isError"] and "stop that" in result["content"][1]["text"]


async def test_a_held_wait_carries_notices_too(kernel, server, lead, clock):
    _, client = await enrolled(kernel, server, "s1", role="steered", by=lead[0])
    await start_turn(kernel, "s1")
    held = asyncio.create_task(client.call("wait", {"from": ["w9"], "hold": 20.0}))
    await slept_until(clock, 1020.0)
    await send(kernel, lead[0], "@s1", "stop that")
    clock.advance(20.0)

    result = await held

    assert "stop that" in result["content"][1]["text"]


async def test_a_call_with_no_notices_journals_only_itself(kernel, lead):
    await lead[1].call("task_add", {"queue": "tasks", "gist": "one"})
    before = kernel.head

    await lead[1].call("task_add", {"queue": "tasks", "gist": "two"}, callId="exec-1")

    assert [event.type for event in events_of(kernel, after=before)] == ["task.added"]


async def test_notices_past_what_one_result_holds_say_how_many_wait(kernel, server, lead):
    _, client = await enrolled(kernel, server, "s1", role="steered", by=lead[0])
    await start_turn(kernel, "s1")
    for number in range(40):
        await send(kernel, lead[0], "@s1", f"entry {number}")

    result = await client.call("peers")

    assert "8 more are waiting" in result["content"][1]["text"]
    assert "`message_read`" in result["content"][1]["text"]


# Refusals.


async def test_a_refusal_says_what_it_means_and_what_to_do_next(lead, worker):
    result = await worker[1].call("task_claim", {"queue": "tasks"})

    assert result["isError"]
    assert text_of(result).splitlines() == [
        "Refused queue_empty on queue/tasks: Nothing is open on that queue.",
        "Why: nothing is open on tasks",
        "Next: Call `wait` with `queue` and end your turn.",
    ]


async def test_a_refusal_names_tools_as_its_surface_does(lead, worker):
    shell = Client(f"{worker[1].url}?surface=ph", worker[1].token)
    prefixed = Client(f"{worker[1].url}?surface=mcp__coord", worker[1].token)

    assert "`ph wait`" in text_of(await shell.call("task_claim", {"queue": "tasks"}))
    assert "`mcp__coord__wait`" in text_of(await prefixed.call("task_claim", {"queue": "tasks"}))


async def test_a_result_s_next_step_names_tools_as_its_surface_does(lead):
    shell = Client(f"{lead[1].url}?surface=ph", lead[1].token)
    prefixed = Client(f"{lead[1].url}?surface=mcp__coord", lead[1].token)

    said = value_of(await shell.call("agent_spawn", {"name": "kid", "child_role": "worker", "stays": True}))["next"]
    also = value_of(await prefixed.call("agent_spawn", {"name": "kin", "child_role": "worker", "stays": True}))["next"]

    assert "`ph agent.retire`" in said and "`mcp__coord__agent_retire`" in also


@pytest.mark.parametrize(
    ("surface", "named"),
    [("mcp", "`message_read`"), ("mcp__coord", "`mcp__coord__message_read`"), ("ph", "`ph message.read`")],
)
async def test_an_empty_read_after_a_wake_names_what_it_handed_over_as_its_surface_does(
    kernel, server, lead, worker, surface, named
):
    await lead[1].call("message_send", {"to": "@w1", "gist": "the code word is heliotrope"})
    result_of(await kernel.submit(kernel.runtime, "delivery.offer", {"agent": "w1"}))
    reader = Client(f"{server.url}?surface={surface}", worker[1].token)

    said = value_of(await reader.call("message_read"))

    assert said["entries"] == []
    assert said["next"] == (
        "Nothing is new here past what was already handed to you: inbox/w1@1. To read that again here, call "
        f"{named} with `after` 0."
    )


async def test_a_refusal_with_structure_shows_it(lead, worker):
    await lead[1].call("board_post", {"board": "notes", "name": "spec", "gist": "v1"})

    result = await lead[1].call("board_revise", {"board": "notes", "name": "spec", "gist": "v2", "expected_version": 9})

    assert '"current": 1' in text_of(result)


async def test_a_busy_refusal_says_when_to_retry(kernel, lead, monkeypatch):
    async def busy(*args, **kwargs):
        return Outcome(op="task.add", args_hash="", refusal=Refusal(code="busy", retry_after=0.25))

    monkeypatch.setattr(kernel, "submit", busy)

    assert "Retry after 0.250 seconds." in text_of(await lead[1].call("task_add", {"queue": "tasks", "gist": "x"}))


# What a held wait owes, and what a result may hold.


async def test_a_held_wait_closes_once_its_answer_has_left(kernel, server, lead, worker, clock):
    await start_turn(kernel, "w1")
    held = asyncio.create_task(worker[1].call("wait", {"from": ["lead"], "hold": 20.0}))
    await slept_until(clock, 1020.0)

    await send(kernel, lead[0], "@w1", "in time")

    assert value_of(await held)["state"] == "released"
    await drained(server)
    assert len(of_type(kernel, "wait.released")) == 1
    assert [event.gist for event in of_type(kernel, "message.sent")] == ["in time"]


async def test_an_answer_that_cannot_be_sent_costs_no_wake(kernel, server, lead, worker, clock, monkeypatch):
    async def lost(self: ToolServer, writer: asyncio.StreamWriter, reply: bytes) -> None:
        raise ConnectionResetError

    monkeypatch.setattr(ToolServer, "_send", lost)
    await start_turn(kernel, "w1")
    message = tool_call("wait", {"from": ["lead"], "hold": 20.0})
    _, writer = await connect(server.url)
    writer.write(request(server.url, json.dumps(message).encode(), token=worker[1].token))
    await writer.drain()
    await slept_until(clock, 1020.0)

    await send(kernel, lead[0], "@w1", "in time")
    await drained(server)
    writer.close()

    wait = of_type(kernel, "wait.registered")[-1].seq
    assert result_of(kernel.query(kernel.runtime, "wait.progress", {"id": wait}))["state"] == "open"
    await end_turn(kernel, "w1")
    result_of(await kernel.submit(kernel.runtime, "wait.release", {"id": wait}))
    assert [event.gist for event in of_type(kernel, "message.sent")][-1] == "Your wait holds."


async def test_an_answer_too_big_for_a_result_is_refused_and_says_so(lead, monkeypatch):
    monkeypatch.setattr(tool_server, "_RESULT_LIMIT", 1)

    result = await lead[1].call("peers")

    assert result["isError"] and "Refused unsupported" in text_of(result)
    assert "a result holds 1:" in text_of(result)


async def test_a_team_too_long_for_one_result_can_still_be_read_to_its_end(kernel, server, lead):
    """A refusal over the limit would leave a model with no way to find anyone, so `peers` goes a page at a time."""
    names = [f"worker-{number:03}" for number in range(600)]
    for name in names:
        await spawn(kernel, name, by=lead[0])

    found, after = [], None
    while True:
        page = value_of(await lead[1].call("peers", {"after": after} if after else {}))
        found += page["peers"]
        after = page["cursor"]
        if after is None:
            break

    assert sorted(row["address"] for row in found) == [f"@{name}" for name in names]
    assert page["total"] == len(names)


async def test_a_query_past_the_limit_is_refused_saying_what_is_left(kernel, lead, monkeypatch):
    monkeypatch.setattr(tool_server, "_RESULT_LIMIT", 1)

    result = await lead[1].call("session_status")

    assert result["isError"] and "ask for less" in text_of(result)


async def test_a_refusal_names_only_tools_the_token_holds(kernel, server, lead):
    _, client = await enrolled(kernel, server, "n1", role="narrow", by=lead[0])

    result = await client.call("message_send", {"to": "@nobody", "gist": "hello"})

    assert result["isError"] and "agent_list" not in text_of(result) and "channel_list" not in text_of(result)


# What a model is shown names everything by an event's ref.


@pytest.mark.parametrize("surface", ["mcp", "mcp__ph", "ph"])
async def test_every_ref_a_model_is_shown_is_an_event_ref(kernel, server, lead, worker, surface):
    """Results, refusals, notices and handovers, on each surface, hold no body's hash: a body is read by the ref of the
    event that carries it."""
    as_surface = [Client(f"{server.url}?surface={surface}", client.token) for client in (lead[1], worker[1])]
    boss, w1 = as_surface
    _, steered = await enrolled(kernel, server, "s1", role="steered", by=lead[0])
    steered = Client(f"{server.url}?surface={surface}", steered.token)
    long = "".join(f"line {number}\n" for number in range(20_000))
    hash_of_body = f"sha256:{await kernel.put_body(b'held apart')}"
    shown: list[dict] = [
        await boss.call("board_post", {"board": "notes", "name": "spec", "gist": "v1", "body": long}),
        await boss.call("message_send", {"to": "@w1", "gist": "read this", "body": "short words"}),
        await boss.call("task_add", {"queue": "tasks", "gist": "do it", "body": "how to do it"}),
    ]
    handed = result_of(await kernel.submit(kernel.runtime, "delivery.offer", {"agent": "w1"}))
    await start_turn(kernel, "s1")
    await send(kernel, lead[0], "@s1", "change course", body=f"sha256:{await kernel.put_body(b'the new course')}")
    shown += [
        await steered.call("peers"),
        await w1.call("message_read", {"bodies": True, "after": 0}),
        await w1.call("board_get", {"board": "notes", "name": "spec"}),
        await w1.call("board_query", {"board": "notes"}),
        await w1.call("task_claim", {"queue": "tasks"}),
        await w1.call("task_list", {"queue": "tasks"}),
        await w1.call("task_complete", {"queue": "tasks", "gist": "done", "body": "what was done"}),
        await w1.call("message_send", {"to": "@lead", "gist": "x", "based_on": [hash_of_body]}),
        await w1.call("blob_get", {"ref": hash_of_body}),
    ]
    rest = value_of(shown[5])["rest"]
    shown.append(await w1.call("blob_get", {"ref": rest}))

    texts = [block["text"] for result in shown for block in result["content"]]
    words = delivery_text(handed, harness_name("ph"), kernel.ops, kernel.ops)
    assert [text for text in [*texts, words] if "sha256:" in text] == []
    assert any("change course" in text for text in texts), "a steer notice was carried"
    assert any("Refused invalid" in text for text in texts)
    assert value_of(shown[4])["entries"][0]["ref"] == "inbox/w1@1"


async def test_a_notice_and_a_blob_offer_are_confirmed_by_the_tool_item_that_carried_them(kernel, server, lead):
    """What the surface hands over beside a result, a steer notice and a body only it could read, goes under the call's
    anchor, so the tool item that holds that call's result confirms it, as it confirms the read itself."""
    _, client = await enrolled(kernel, server, "s1", role="steered", by=lead[0])
    await lead[1].call("board_post", {"board": "notes", "name": "big", "gist": "big", "body": "line\n" * 20_000})
    await start_turn(kernel, "s1")
    await send(kernel, lead[0], "@s1", "change course")
    head = kernel.head

    result = await client.call("board_get", {"board": "notes", "name": "big"}, claudecode__toolUseId="toolu_9")
    offered = of_type(kernel, "context.offered", after=head)
    unconfirmed = of_type(kernel, "context.delivered", after=head)
    item = {
        "type": "item",
        "kind": "tool",
        "phase": "completed",
        "gist": "board_get",
        "native_id": "toolu_9",
        "outcome": "completed",
    }
    result_of(await kernel.submit(kernel.runtime, "agent.report", {"agent": "s1", "report": item}))

    assert "change course" in result["content"][-1]["text"]
    assert sorted(offer.data["how"] for offer in offered) == ["notice", "read", "read"]
    assert {offer.native["claudecode/toolUseId"] for offer in offered} == {"toolu_9"}
    assert unconfirmed == []
    confirmations = of_type(kernel, "context.delivered", after=head)
    assert sorted(event.data["input"] for event in confirmations) == sorted(offer.seq for offer in offered)
    assert {event.data["evidence"] for event in confirmations} == {"tool_item"}
