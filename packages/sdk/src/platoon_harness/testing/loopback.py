"""The least HTTP/1.1 that works on loopback, both ways, from the standard library alone."""

import asyncio
import json
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any, Self
from urllib.parse import urlsplit

_HOST = "127.0.0.1"
_LIMIT = 16 * 1024 * 1024


@dataclass(frozen=True)
class Message:
    """One HTTP request as it arrived. Header names keep their case and order, and `body` its bytes."""

    method: str
    target: str
    headers: tuple[tuple[str, str], ...]
    body: bytes

    def header(self, name: str) -> str | None:
        return next((value for key, value in self.headers if key.lower() == name), None)


async def _read_chunked(reader: asyncio.StreamReader) -> bytes:
    body = bytearray()
    while size := int((await reader.readline()).strip() or b"0", 16):
        body += await reader.readexactly(size)
        await reader.readline()
    await reader.readline()
    return bytes(body)


async def read_message(reader: asyncio.StreamReader) -> Message | None:
    """The next request on a connection, or None when the client has gone."""
    try:
        head = await reader.readuntil(b"\r\n\r\n")
        line, *fields = head.decode("latin-1").split("\r\n")[:-2]
        method, target, _ = line.split(" ", 2)
        headers = tuple((key, value.strip()) for key, _, value in (field.partition(":") for field in fields))
        message = Message(method, target, headers, b"")
        if "chunked" in (message.header("transfer-encoding") or ""):
            body = await _read_chunked(reader)
        else:
            body = await reader.readexactly(int(message.header("content-length") or 0))
    except (asyncio.IncompleteReadError, ConnectionError):
        return None
    return Message(method, target, headers, body)


def answer(status: int, body: bytes = b"", content_type: str = "application/json") -> bytes:
    """A whole response, with its length."""
    head = f"HTTP/1.1 {status} OK\r\ncontent-type: {content_type}\r\ncontent-length: {len(body)}\r\n\r\n"
    return head.encode() + body


def stream_head() -> bytes:
    """The start of a server-sent stream, which ends when the connection does."""
    return b"HTTP/1.1 200 OK\r\ncontent-type: text/event-stream\r\ncache-control: no-cache\r\nconnection: close\r\n\r\n"


class Loopback:
    """A server on loopback and port 0. `handle` answers each request on the raw streams, returning False to hang up."""

    def __init__(
        self, handle: Callable[[Message, asyncio.StreamReader, asyncio.StreamWriter], Awaitable[bool]]
    ) -> None:
        self._handle = handle
        self._connections: set[asyncio.Task[None]] = set()
        self._port = 0

    @property
    def url(self) -> str:
        return f"http://{_HOST}:{self._port}"

    async def __aenter__(self) -> Self:
        self._server = await asyncio.start_server(self._accept, _HOST, 0, limit=_LIMIT)
        self._port = self._server.sockets[0].getsockname()[1]
        return self

    async def __aexit__(self, *_: object) -> None:
        self._server.close()
        for connection in self._connections:
            connection.cancel()
        await asyncio.gather(*self._connections, return_exceptions=True)

    async def _accept(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        task = asyncio.current_task()
        assert task is not None
        self._connections.add(task)
        try:
            while (message := await read_message(reader)) is not None:
                if not await self._handle(message, reader, writer):
                    break
                await writer.drain()
        except ConnectionError:
            return
        finally:
            self._connections.discard(task)
            writer.close()


async def post(url: str, payload: Any, headers: Mapping[str, str] | None = None) -> tuple[int, bytes]:
    """POST JSON and return the status and body."""
    parts = urlsplit(url)
    reader, writer = await asyncio.open_connection(parts.hostname, parts.port)
    body = json.dumps(payload).encode()
    fields = {
        "host": parts.netloc,
        "content-type": "application/json",
        "accept": "application/json",
        "content-length": str(len(body)),
        "connection": "close",
        **(headers or {}),
    }
    head = "".join(f"{key}: {value}\r\n" for key, value in fields.items())
    try:
        writer.write(f"POST {parts.path or '/'} HTTP/1.1\r\n{head}\r\n".encode() + body)
        await writer.drain()
        status = int((await reader.readline()).split()[1])
        length = None
        while (line := await reader.readline()) not in (b"\r\n", b""):
            key, _, value = line.decode("latin-1").partition(":")
            length = int(value) if key.lower() == "content-length" else length
        return status, await (reader.read() if length is None else reader.readexactly(length))
    finally:
        writer.close()
