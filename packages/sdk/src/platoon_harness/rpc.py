"""One line-delimited JSON-RPC 2.0 peer on asyncio streams, split on LF only."""

import asyncio
import json
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from typing import Any, NoReturn

LINE_LIMIT = 16 * 1024 * 1024
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603
BUSY = -32000

_CHUNK = 64 * 1024
_SERVING = 256

Handler = Callable[[str, Any], Awaitable[Any]]
Stray = Callable[[bytes], None]

__all__ = [
    "BUSY",
    "INVALID_PARAMS",
    "LINE_LIMIT",
    "METHOD_NOT_FOUND",
    "Closed",
    "Handler",
    "LineTooLong",
    "Lines",
    "Peer",
    "RpcError",
    "Stray",
    "read_lines",
    "strict_loads",
]


class RpcError(Exception):
    """A JSON-RPC error: a handler raises one to answer with it, and `call` raises what the other side answered."""

    def __init__(self, code: int, message: str, data: Any = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data

    def frame(self) -> dict[str, Any]:
        error = {"code": self.code, "message": self.message}
        return error if self.data is None else {**error, "data": self.data}


class Closed(ConnectionError):
    """The connection ended, so a call will never be answered."""


class LineTooLong(Closed):
    """A line passed the limit, which ends the connection, since what it held may have been the answer to a call."""


async def read_lines(reader: asyncio.StreamReader, limit: int = LINE_LIMIT) -> AsyncIterator[bytes]:
    """Each line of a stream, split on LF and nothing else, so U+2028 stays inside a string. A last line needs no LF.

    Raises `LineTooLong` past `limit`, having held no more than that.
    """
    held = bytearray()
    while chunk := await reader.read(_CHUNK):
        start = 0
        while (end := chunk.find(b"\n", start)) != -1:
            if len(held) + end - start > limit:
                raise LineTooLong(f"a line passed {limit} bytes")
            yield bytes(held) + chunk[start:end]
            held.clear()
            start = end + 1
        if len(held) + len(chunk) - start > limit:
            raise LineTooLong(f"a line passed {limit} bytes")
        held += chunk[start:]
    if held:
        yield bytes(held)


class Lines:
    """JSON lines on one stream, with answers arriving among the other end's events, for a protocol that is no JSON-RPC.
    `lost` makes what a frame with nowhere to go raises, and `settle` is how a reader gives an answer to its waiter."""

    def __init__(self, lost: Callable[[], Exception]) -> None:
        self._lost = lost
        self._writer: asyncio.StreamWriter | None = None
        self._waiting: dict[str, asyncio.Future[Any]] = {}

    def open(self, writer: asyncio.StreamWriter) -> None:
        self._writer = writer

    async def run(self, reader: asyncio.StreamReader, heard: Callable[[bytes], None]) -> None:
        """Hear every line that holds anything. When none are left, nothing can be answered, so every waiter is told."""
        try:
            async for line in read_lines(reader):
                if line.strip():
                    heard(line)
        finally:
            self._writer = None
            for id in self._waiting:
                self.settle(id, self._lost())

    def write(self, frame: Mapping[str, Any]) -> None:
        """Send a frame and do not wait, as a reader must not. With nowhere to go, it goes nowhere."""
        if self._writer is not None:
            self._writer.write(json.dumps(frame).encode() + b"\n")

    async def send(self, frame: Mapping[str, Any]) -> None:
        """Send a frame, and wait until it has left."""
        if self._writer is None:
            raise self._lost()
        self.write(frame)
        try:
            await self._writer.drain()
        except ConnectionError as error:
            raise self._lost() from error

    async def exchange(self, id: str, frame: Mapping[str, Any]) -> Any:
        """Send a frame and wait for the answer to its id."""
        answer = asyncio.get_running_loop().create_future()
        self._waiting[id] = answer
        try:
            await self.send(frame)
            return await answer
        finally:
            del self._waiting[id]

    def settle(self, id: str, answer: Any) -> None:
        """Give a waiter its answer, or an `Exception` to raise. One nobody waits for any more has nobody to reach."""
        waiting = self._waiting.get(id)
        if waiting is None or waiting.done():
            return
        if isinstance(answer, Exception):
            waiting.set_exception(answer)
        else:
            waiting.set_result(answer)


async def _unknown_method(method: str, params: Any) -> NoReturn:
    raise RpcError(METHOD_NOT_FOUND, f"no method {method}")


def _not_a_number(constant: str) -> NoReturn:
    raise ValueError(f"{constant} is not JSON")


def strict_loads(text: str | bytes) -> Any:
    """JSON as JSON is, which has no NaN and no Infinity, whatever Python's parser lets through."""
    return json.loads(text, parse_constant=_not_a_number)


class Peer:
    """Both ends of JSON-RPC on one connection. Nothing moves until `run` reads.

    `handler` takes `(method, params)`. Each request runs in its own task, so a slow one holds up no other, and
    notifications run in order on the read loop, so that handler must not wait on the world: it would stop the reads.
    `stray` hears the raw line of what no method took and no call awaits.
    `jsonrpc=False` drops the `jsonrpc` member, which Codex omits.
    """

    def __init__(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        handler: Handler = _unknown_method,
        *,
        stray: Stray | None = None,
        jsonrpc: bool = True,
    ) -> None:
        self._reader = reader
        self._writer = writer
        self._handler = handler
        self._stray = stray or (lambda line: None)
        self._jsonrpc = jsonrpc
        self._last_id = 0
        self._pending: dict[int, asyncio.Future[Any]] = {}
        self._abandoned: set[int] = set()
        self._serving: dict[int | str, asyncio.Task[None]] = {}
        self._ended: Closed | None = None

    async def run(self) -> None:
        """Read until the stream ends, however it ends, then fail every pending call. Past the line limit it raises
        `LineTooLong`."""
        ended = Closed("the connection closed")
        try:
            async for line in read_lines(self._reader, LINE_LIMIT):
                await self._receive(line)
        except LineTooLong as error:
            ended = error
            raise
        except ConnectionError as error:
            ended = Closed(f"the connection was lost: {error}")
        finally:
            await self._end(ended)

    async def call(self, method: str, params: Any = None) -> Any:
        """Send a request and await its result. Raises `RpcError` if refused, `Closed` if it can never be answered."""
        self._last_id += 1
        id = self._last_id
        answer = asyncio.get_running_loop().create_future()
        self._pending[id] = answer
        try:
            self._send(self._message(method, params) | {"id": id})
            await self._writer.drain()
            return await answer
        except ConnectionError as error:
            raise self._ended or Closed(str(error)) from error
        except asyncio.CancelledError:
            self._abandoned.add(id)
            raise
        finally:
            del self._pending[id]

    async def notify(self, method: str, params: Any = None) -> None:
        """Send a notification, which nothing answers. Raises `Closed` once the connection has ended."""
        try:
            self._send(self._message(method, params))
            await self._writer.drain()
        except ConnectionError as error:
            raise self._ended or Closed(str(error)) from error

    def close(self) -> None:
        """Close this end. The other reads EOF, and `run` returns when the transport has gone."""
        self._writer.close()

    def _message(self, method: str, params: Any) -> dict[str, Any]:
        return {"method": method} if params is None else {"method": method, "params": params}

    def _send(self, frame: dict[str, Any]) -> None:
        """Queue one frame without waiting, so that a reply cannot stall the read loop. A peer that stops reading is
        dropped once a line's worth of bytes wait for it, since a client must not hold memory here."""
        if self._ended is not None:
            raise self._ended
        if self._writer.is_closing():
            raise Closed("the connection is closed")
        if self._writer.transport.get_write_buffer_size() > LINE_LIMIT:
            self._writer.transport.abort()
            raise Closed("the peer stopped reading")
        frame = {"jsonrpc": "2.0", **frame} if self._jsonrpc else frame
        self._writer.write(json.dumps(frame, separators=(",", ":")).encode() + b"\n")

    def _answer(self, frame: dict[str, Any]) -> None:
        """Send a reply nobody awaits. A reply to a connection already gone has nobody to reach."""
        try:
            self._send(frame)
        except Closed:
            return

    async def _receive(self, line: bytes) -> None:
        if not line.strip():
            return
        try:
            frame = strict_loads(line.decode())
        except (ValueError, RecursionError) as error:
            self._reject(line, PARSE_ERROR, f"not JSON: {error}")
            return
        if not isinstance(frame, dict) or (self._jsonrpc and frame.get("jsonrpc") != "2.0"):
            self._reject(line, INVALID_REQUEST, "not a JSON-RPC 2.0 frame")
            return
        match frame:
            case {"method": str(method), "id": id}:
                self._request(line, id, method, frame.get("params"))
            case {"method": str(method)}:
                await self._notified(line, method, frame.get("params"))
            case {"id": id, "result": result} if "error" not in frame and self._awaits(id):
                self._pending[id].set_result(result)
            case {"id": id, "error": dict(error)} if "result" not in frame and self._awaits(id):
                code, message = error.get("code", INTERNAL_ERROR), str(error.get("message", ""))
                self._pending[id].set_exception(RpcError(code, message, error.get("data")))
            case {"id": id, "result": _} | {"id": id, "error": _} if type(id) is int and id in self._abandoned:
                self._abandoned.discard(id)  # Whoever asked gave up, so nobody is left to hear it.
            case {"id": _, "result": _} | {"id": _, "error": _}:
                self._stray(line)
            case _:
                self._reject(line, INVALID_REQUEST, "neither a request nor an answer")

    def _awaits(self, id: Any) -> bool:
        return type(id) is int and id in self._pending and not self._pending[id].done()

    def _reject(self, line: bytes, code: int, why: str) -> None:
        """Answer what could not be read. An answer with a null id is stray at the other end, so peers cannot echo."""
        self._answer({"id": None, "error": {"code": code, "message": why}})
        self._stray(line)

    def _request(self, line: bytes, id: Any, method: str, params: Any) -> None:
        if type(id) not in (int, str):
            self._reject(line, INVALID_REQUEST, "an id is a string or an integer")
        elif id in self._serving:
            self._stray(line)
        elif len(self._serving) >= _SERVING:
            self._answer({"id": id, "error": {"code": BUSY, "message": "too many requests in flight"}})
        else:
            task = asyncio.create_task(self._serve(line, id, method, params))
            self._serving[id] = task
            task.add_done_callback(lambda _: self._serving.pop(id))

    async def _serve(self, line: bytes, id: int | str, method: str, params: Any) -> None:
        try:
            self._answer({"id": id, "result": await self._handler(method, params)})
        except RpcError as error:
            self._answer({"id": id, "error": error.frame()})
            self._stray(line)
        except Exception as error:
            message = f"{type(error).__name__}: {error}"
            self._answer({"id": id, "error": {"code": INTERNAL_ERROR, "message": message}})

    async def _notified(self, line: bytes, method: str, params: Any) -> None:
        try:
            await self._handler(method, params)
        except RpcError:
            self._stray(line)

    async def _end(self, why: Closed) -> None:
        self._ended = why
        for answer in self._pending.values():
            if not answer.done():
                answer.set_exception(why)
        serving = list(self._serving.values())
        for task in serving:
            task.cancel()
        await asyncio.gather(*serving, return_exceptions=True)
        self._writer.close()
