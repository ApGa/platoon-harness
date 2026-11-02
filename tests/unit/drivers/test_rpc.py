"""One JSON-RPC peer: framing, both directions, and everything a broken other end can send."""

import asyncio
import json
import socket

import pytest

from platoon_harness import rpc
from platoon_harness.rpc import (
    BUSY,
    INTERNAL_ERROR,
    INVALID_PARAMS,
    INVALID_REQUEST,
    METHOD_NOT_FOUND,
    PARSE_ERROR,
    Closed,
    LineTooLong,
    Peer,
    RpcError,
    read_lines,
)


class Wire:
    """A peer under test, with its other end held raw so a test can send and read exact bytes."""

    def __init__(self, handler=None, **options) -> None:
        self.handler = handler
        self.options = options
        self.strays = []

    async def __aenter__(self) -> "Wire":
        ours, theirs = socket.socketpair()
        reader, writer = await asyncio.open_connection(sock=ours)
        self.raw_reader, self.raw_writer = await asyncio.open_connection(sock=theirs)
        args = (self.handler,) if self.handler else ()
        self.peer = Peer(reader, writer, *args, stray=self.strays.append, **self.options)
        self.running = asyncio.create_task(self.peer.run())
        return self

    async def __aexit__(self, *_) -> None:
        self.raw_writer.close()
        await asyncio.gather(self.running, return_exceptions=True)

    async def send(self, *lines: bytes) -> None:
        self.raw_writer.write(b"".join(line + b"\n" for line in lines))
        await self.raw_writer.drain()

    async def frame(self) -> dict:
        return json.loads(await self.raw_reader.readline())

    async def strayed(self, count: int = 1) -> list:
        """Wait until the read loop has handled what was sent, by a call it must answer after."""
        await self.send(b'{"jsonrpc":"2.0","method":"no.such.method","id":"sync"}')
        while (await self.frame()).get("id") != "sync":
            pass
        strays = [stray for stray in self.strays if b"sync" not in stray]
        assert len(strays) == count
        return strays


async def echo(method: str, params):
    return {"method": method, "params": params}


async def lines_of(data: bytes, limit: int = 1024) -> list[bytes]:
    reader = asyncio.StreamReader()
    reader.feed_data(data)
    reader.feed_eof()
    return [line async for line in read_lines(reader, limit)]


async def test_lines_split_on_lf_and_nothing_else():
    text = b'{"a":"x\xe2\x80\xa8y\xe2\x80\xa9z\xc2\x85w\x0bv\x0cu"}\n'

    assert await lines_of(text + b"second\r\n") == [text[:-1], b"second\r"]


async def test_a_last_line_needs_no_lf():
    assert await lines_of(b"one\ntwo") == [b"one", b"two"]


async def test_lines_at_the_limit_pass_and_one_past_it_raises():
    assert await lines_of(b"x" * 8 + b"\n", limit=8) == [b"x" * 8]
    with pytest.raises(LineTooLong):
        await lines_of(b"x" * 9 + b"\n", limit=8)


async def test_a_line_with_no_end_raises_with_only_the_limit_held():
    reader = asyncio.StreamReader()
    reader.feed_data(b"x" * 1024 * 1024)

    with pytest.raises(LineTooLong):
        async for _ in read_lines(reader, 1024):
            pass


async def test_a_line_longer_than_a_read_arrives_whole():
    long = b"y" * 200_000

    assert await lines_of(long + b"\n" + long + b"\n", limit=200_000) == [long, long]


async def test_a_request_is_answered_with_its_result():
    async with Wire(echo) as wire:
        await wire.send(b'{"jsonrpc":"2.0","id":7,"method":"ping","params":{"a":1}}')

        assert await wire.frame() == {"jsonrpc": "2.0", "id": 7, "result": {"method": "ping", "params": {"a": 1}}}


async def test_a_string_id_comes_back_as_it_went():
    async with Wire(echo) as wire:
        await wire.send(b'{"jsonrpc":"2.0","id":"abc","method":"ping"}')

        assert (await wire.frame())["id"] == "abc"


async def test_a_call_gets_its_answer_by_id():
    async with Wire() as wire:
        first = asyncio.create_task(wire.peer.call("one", {"n": 1}))
        second = asyncio.create_task(wire.peer.call("two"))
        sent = [await wire.frame(), await wire.frame()]
        assert sent[0] == {"jsonrpc": "2.0", "method": "one", "params": {"n": 1}, "id": 1}
        assert sent[1] == {"jsonrpc": "2.0", "method": "two", "id": 2}

        await wire.send(b'{"jsonrpc":"2.0","id":2,"result":"second"}', b'{"jsonrpc":"2.0","id":1,"result":"first"}')

        assert (await first, await second) == ("first", "second")


async def test_an_error_answer_raises_what_was_said():
    async with Wire() as wire:
        call = asyncio.create_task(wire.peer.call("go"))
        await wire.frame()
        await wire.send(b'{"jsonrpc":"2.0","id":1,"error":{"code":-32001,"message":"no","data":{"why":"x"}}}')

        with pytest.raises(RpcError) as error:
            await call

    assert (error.value.code, error.value.message, error.value.data) == (-32001, "no", {"why": "x"})


async def test_a_notification_is_handled_in_order_and_never_answered():
    heard = []

    async def handler(method, params):
        heard.append(params)

    async with Wire(handler) as wire:
        await wire.send(*(json.dumps({"jsonrpc": "2.0", "method": "n", "params": i}).encode() for i in range(100)))
        await wire.send(b'{"jsonrpc":"2.0","id":1,"method":"sync"}')
        assert (await wire.frame())["id"] == 1

    assert heard[:100] == list(range(100))


async def test_a_slow_request_holds_up_no_other():
    release = asyncio.Event()

    async def handler(method, params):
        if method == "slow":
            await release.wait()
        return method

    async with Wire(handler) as wire:
        await wire.send(b'{"jsonrpc":"2.0","id":1,"method":"slow"}', b'{"jsonrpc":"2.0","id":2,"method":"fast"}')

        assert (await wire.frame())["id"] == 2
        release.set()
        assert (await wire.frame())["id"] == 1


async def test_a_handler_can_call_back_while_it_serves():
    async with Wire() as wire:

        async def handler(method, params):
            return await wire.peer.call("back")

        wire.peer._handler = handler
        await wire.send(b'{"jsonrpc":"2.0","id":"in","method":"go"}')
        assert (await wire.frame())["method"] == "back"
        await wire.send(b'{"jsonrpc":"2.0","id":1,"result":"answered"}')

        assert (await wire.frame()) == {"jsonrpc": "2.0", "id": "in", "result": "answered"}


async def test_a_refusal_keeps_its_code():
    async def handler(method, params):
        raise RpcError(-32050, "not today", {"retry": 1})

    async with Wire(handler) as wire:
        await wire.send(b'{"jsonrpc":"2.0","id":1,"method":"go"}')

        assert (await wire.frame())["error"] == {"code": -32050, "message": "not today", "data": {"retry": 1}}


async def test_a_handler_that_crashes_answers_an_internal_error():
    async def handler(method, params):
        raise ValueError("boom")

    async with Wire(handler) as wire:
        await wire.send(b'{"jsonrpc":"2.0","id":1,"method":"go"}')

        assert (await wire.frame())["error"] == {"code": INTERNAL_ERROR, "message": "ValueError: boom"}


async def test_a_result_that_is_not_json_answers_an_internal_error():
    async def handler(method, params):
        return object()

    async with Wire(handler) as wire:
        await wire.send(b'{"jsonrpc":"2.0","id":1,"method":"go"}')

        assert (await wire.frame())["error"]["code"] == INTERNAL_ERROR


async def test_a_method_nobody_knows_is_answered_and_is_stray():
    async with Wire() as wire:
        await wire.send(b'{"jsonrpc":"2.0","id":1,"method":"unknown"}')

        assert (await wire.frame())["error"]["code"] == METHOD_NOT_FOUND
        assert wire.strays[0] == b'{"jsonrpc":"2.0","id":1,"method":"unknown"}'


async def test_a_request_its_handler_refuses_is_answered_and_is_stray():
    async def handler(method, params):
        raise RpcError(INVALID_PARAMS, "not that")

    async with Wire(handler) as wire:
        await wire.send(b'{"jsonrpc":"2.0","id":1,"method":"report"}')

        assert (await wire.frame())["error"]["code"] == INVALID_PARAMS
        assert wire.strays == [b'{"jsonrpc":"2.0","id":1,"method":"report"}']


async def test_a_notification_nobody_knows_is_stray():
    async with Wire() as wire:
        await wire.send(b'{"jsonrpc":"2.0","method":"unknown"}')

        assert await wire.strayed(1)


@pytest.mark.parametrize(
    ("line", "code"),
    [
        (b"not json", PARSE_ERROR),
        (b"\xff\xfe", PARSE_ERROR),
        (b'{"truncated":', PARSE_ERROR),
        (b'{"jsonrpc":"2.0","id":1,"method":"x","params":NaN}', PARSE_ERROR),
        (b"[" * 200_000, PARSE_ERROR),
        (b"[]", INVALID_REQUEST),
        (b"1", INVALID_REQUEST),
        (b'"text"', INVALID_REQUEST),
        (b'[{"jsonrpc":"2.0","id":1,"method":"x"}]', INVALID_REQUEST),
        (b'{"jsonrpc":"1.0","id":1,"method":"x"}', INVALID_REQUEST),
        (b'{"id":1,"method":"x"}', INVALID_REQUEST),
        (b'{"jsonrpc":"2.0"}', INVALID_REQUEST),
        (b'{"jsonrpc":"2.0","method":1}', INVALID_REQUEST),
        (b'{"jsonrpc":"2.0","id":null,"method":"x"}', INVALID_REQUEST),
        (b'{"jsonrpc":"2.0","id":1.5,"method":"x"}', INVALID_REQUEST),
        (b'{"jsonrpc":"2.0","id":true,"method":"x"}', INVALID_REQUEST),
        (b'{"jsonrpc":"2.0","id":{},"method":"x"}', INVALID_REQUEST),
    ],
)
async def test_a_malformed_frame_is_answered_stray_and_survived(line, code):
    async with Wire(echo) as wire:
        await wire.send(line)
        answer = await wire.frame()
        assert (answer["id"], answer["error"]["code"]) == (None, code)
        assert wire.strays[0] == line

        await wire.send(b'{"jsonrpc":"2.0","id":1,"method":"still"}')
        assert (await wire.frame())["result"]["method"] == "still"


@pytest.mark.parametrize(
    "line",
    [
        b'{"jsonrpc":"2.0","id":99,"result":1}',
        b'{"jsonrpc":"2.0","id":null,"result":1}',
        b'{"jsonrpc":"2.0","id":null,"error":{"code":-32700,"message":"x"}}',
        b'{"jsonrpc":"2.0","id":"1","result":1}',
        b'{"jsonrpc":"2.0","id":true,"result":1}',
    ],
)
async def test_an_answer_to_nothing_is_stray_and_is_not_answered(line):
    async with Wire(echo) as wire:
        pending = asyncio.create_task(wire.peer.call("go"))
        await wire.frame()

        await wire.send(line)

        assert (await wire.strayed())[0] == line
        assert not pending.done()
        pending.cancel()


async def test_blank_lines_are_no_frames():
    async with Wire(echo) as wire:
        await wire.send(b"", b"   ", b'{"jsonrpc":"2.0","id":1,"method":"x"}')

        assert (await wire.frame())["id"] == 1
        assert wire.strays == []


async def test_two_answers_to_one_call_keep_the_first():
    async with Wire() as wire:
        call = asyncio.create_task(wire.peer.call("go"))
        await wire.frame()

        await wire.send(b'{"jsonrpc":"2.0","id":1,"result":"first"}', b'{"jsonrpc":"2.0","id":1,"result":"second"}')

        assert await call == "first"
        await wire.strayed()


async def test_a_duplicate_id_in_flight_runs_nothing_twice():
    ran = []
    release = asyncio.Event()

    async def handler(method, params):
        if method == "no.such.method":
            return None
        ran.append(method)
        await release.wait()
        return "done"

    async with Wire(handler) as wire:
        await wire.send(b'{"jsonrpc":"2.0","id":1,"method":"a"}', b'{"jsonrpc":"2.0","id":1,"method":"b"}')
        await wire.strayed()

        assert ran == ["a"]
        release.set()
        assert (await wire.frame()) == {"jsonrpc": "2.0", "id": 1, "result": "done"}


async def test_an_id_finished_with_can_come_again():
    async with Wire(echo) as wire:
        await wire.send(b'{"jsonrpc":"2.0","id":1,"method":"x"}')
        await wire.frame()
        await wire.send(b'{"jsonrpc":"2.0","id":1,"method":"x"}')

        assert (await wire.frame())["id"] == 1


async def test_too_many_requests_in_flight_are_refused_busy():
    release = asyncio.Event()

    async def handler(method, params):
        await release.wait()

    async with Wire(handler) as wire:
        await wire.send(*(json.dumps({"jsonrpc": "2.0", "id": i, "method": "x"}).encode() for i in range(257)))

        assert (await wire.frame()) == {
            "jsonrpc": "2.0",
            "id": 256,
            "error": {"code": BUSY, "message": "too many requests in flight"},
        }
        release.set()


async def test_a_reset_connection_ends_the_stream_and_fails_the_call():
    async with Wire() as wire:
        call = asyncio.create_task(wire.peer.call("go"))
        await wire.frame()

        wire.peer._reader.set_exception(ConnectionResetError("reset by peer"))

        with pytest.raises(Closed, match="reset by peer"):
            await call
        await wire.running


async def test_eof_mid_request_fails_the_call():
    async with Wire() as wire:
        call = asyncio.create_task(wire.peer.call("go"))
        await wire.frame()

        wire.raw_writer.close()

        with pytest.raises(Closed):
            await call
        await wire.running


async def test_a_call_after_the_end_fails_at_once():
    async with Wire() as wire:
        wire.raw_writer.close()
        await wire.running

        with pytest.raises(Closed):
            await wire.peer.call("go")
        with pytest.raises(Closed):
            await wire.peer.notify("go")


async def test_eof_cancels_what_was_being_served():
    started, cancelled = asyncio.Event(), asyncio.Event()

    async def handler(method, params):
        started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.set()
            raise

    async with Wire(handler) as wire:
        await wire.send(b'{"jsonrpc":"2.0","id":1,"method":"go"}')
        await started.wait()
        wire.raw_writer.close()
        await wire.running

    assert cancelled.is_set()


async def test_an_oversized_line_ends_the_connection_loudly(monkeypatch):
    monkeypatch.setattr(rpc, "LINE_LIMIT", 1024)
    async with Wire() as wire:
        call = asyncio.create_task(wire.peer.call("go"))
        await wire.frame()

        await wire.send(b'{"jsonrpc":"2.0","method":"' + b"x" * 2048 + b'"}')

        with pytest.raises(LineTooLong):
            await wire.running
        with pytest.raises(LineTooLong):
            await call


async def test_a_call_cancelled_by_a_timeout_leaves_a_stray_answer_harmless():
    async with Wire() as wire:
        with pytest.raises(TimeoutError):
            async with asyncio.timeout(0):
                await wire.peer.call("go")

        await wire.send(b'{"jsonrpc":"2.0","id":1,"result":"late"}')
        await wire.frame()
        await wire.strayed()


async def test_a_peer_that_stops_reading_is_dropped_rather_than_held_in_memory(monkeypatch):
    monkeypatch.setattr(rpc, "LINE_LIMIT", 4096)
    async with Wire() as wire:
        with pytest.raises(Closed):
            for _ in range(10_000):
                await asyncio.wait_for(wire.peer.notify("flood", "x" * 1024), 1)


async def test_two_peers_cannot_echo_errors_for_ever():
    left_sock, right_sock = socket.socketpair()
    left = Peer(*await asyncio.open_connection(sock=left_sock), stray=lambda line: strays.append(("left", line)))
    right = Peer(*await asyncio.open_connection(sock=right_sock), stray=lambda line: strays.append(("right", line)))
    strays = []
    running = [asyncio.create_task(left.run()), asyncio.create_task(right.run())]

    left._writer.write(b"garbage\n")
    await left._writer.drain()
    with pytest.raises(RpcError):
        await left.call("sync")

    assert sorted(side for side, _ in strays) == ["left", "right", "right"]
    left.close()
    right.close()
    await asyncio.gather(*running)


async def test_codex_framing_drops_the_jsonrpc_member():
    async with Wire(echo, jsonrpc=False) as wire:
        await wire.send(b'{"id":1,"method":"thread/start","params":{}}')
        assert await wire.frame() == {"id": 1, "result": {"method": "thread/start", "params": {}}}

        call = asyncio.create_task(wire.peer.call("turn/start", {"a": 1}))
        assert await wire.frame() == {"method": "turn/start", "params": {"a": 1}, "id": 1}
        await wire.send(b'{"id":1,"result":{}}')
        assert await call == {}

        await wire.peer.notify("initialized")
        assert await wire.frame() == {"method": "initialized"}
