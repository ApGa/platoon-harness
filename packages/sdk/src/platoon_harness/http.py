"""HTTP/1.1 as the SDK's servers speak it: one request per connection, each bounded before it is believed.

A head of at most 16 KiB comes first, then whatever names who is asking, and only then a body of a stated length, never
chunked. A request has `SECONDS` on the server's clock to arrive and its answer as long again to leave, and past
`CONNECTIONS` open at once the server answers 503. So an idle client holds no task, socket or state here.
"""

import asyncio
import contextlib
import logging
import ssl
from collections.abc import Awaitable, Coroutine, Mapping
from http import HTTPStatus
from typing import Any, NamedTuple

from platoon_harness.kernel import Clock, first

HEAD_LIMIT = 16 * 1024
SECONDS = 10.0
CONNECTIONS = 1024
_ONCE = frozenset({"authorization", "content-length", "host", "origin"})
_CHUNK = 64 * 1024

log = logging.getLogger("platoon_harness.http")

__all__ = [
    "CONNECTIONS",
    "HEAD_LIMIT",
    "SECONDS",
    "Cut",
    "Head",
    "Rejected",
    "Server",
    "bearer",
    "check_site",
    "length",
    "response",
    "unless",
]


def response(status: int, body: bytes = b"", *headers: str) -> bytes:
    """A whole answer, which closes its connection."""
    lines = (
        f"HTTP/1.1 {status} {HTTPStatus(status).phrase}",
        f"Content-Length: {len(body)}",
        "Connection: close",
        *headers,
    )
    return "\r\n".join((*lines, "", "")).encode() + body


class Rejected(Exception):
    """A request refused at the HTTP layer: its status, any headers that say how to ask again, and why."""

    def __init__(self, status: int, *headers: str, why: str = "") -> None:
        super().__init__(status)
        self.status = status
        self.headers = headers
        self.why = why or HTTPStatus(status).phrase


class Cut(Exception):
    """What was being awaited lost its race, and has been dropped."""


class Head(NamedTuple):
    """A request's line and headers. A header that decides anything may appear once."""

    method: str
    path: str
    query: str
    headers: Mapping[str, str]


async def unless[T](rival: Awaitable[Any], work: Coroutine[Any, Any, T]) -> T:
    """`work`'s result, unless `rival` finishes first, which drops the work and raises `Cut`."""
    task = asyncio.ensure_future(work)
    if not await first(task, rival):
        raise Cut
    return task.result()


def _parsed(head: bytes) -> Head:
    request, *lines = head[: -len(b"\r\n\r\n")].decode("latin-1").split("\r\n")
    words = request.split(" ")
    if len(words) != 3 or not words[2].startswith("HTTP/1."):
        raise Rejected(400)
    headers: dict[str, str] = {}
    for line in lines:
        name, colon, value = line.partition(":")
        name = name.lower()
        if not colon or not name or " " in name or (name in _ONCE and name in headers):
            raise Rejected(400)
        headers[name] = value.strip()
    path, _, query = words[1].partition("?")
    return Head(words[0], path, query, headers)


def length(head: Head, limit: int) -> int:
    """The length of a request's body, which it must state, up to `limit`."""
    value = head.headers.get("content-length")
    if value is None or "transfer-encoding" in head.headers:
        raise Rejected(411)
    if not (value.isascii() and value.isdecimal()):
        raise Rejected(400)
    if len(value) > len(str(limit)) or int(value) > limit:
        raise Rejected(413)
    return int(value)


def check_site(head: Head, authorities: tuple[str, ...], *, scheme: str = "http", origin: bool = False) -> None:
    """Refuse what a browser could be tricked into sending. `Host` must name an authority this server serves, which
    defeats DNS rebinding, and `Origin`, which `origin` requires, must be the origin of that same authority."""
    host = head.headers.get("host")
    if host not in authorities:
        raise Rejected(421, why="this server does not serve that host")
    if (origin or "origin" in head.headers) and head.headers.get("origin") != f"{scheme}://{host}":
        raise Rejected(403, why="a request from another origin is refused")


def bearer(head: Head) -> str:
    """The bearer token of a request. Nothing else is a credential."""
    scheme, _, token = head.headers.get("authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise Rejected(401, "WWW-Authenticate: Bearer")
    return token.strip()


async def _hung_up(reader: asyncio.StreamReader) -> None:
    """Return when the client goes. Anything else it sends is thrown away, so it cannot pile up here."""
    with contextlib.suppress(ConnectionError, ssl.SSLError):
        while await reader.read(_CHUNK):
            pass


async def _send(writer: asyncio.StreamWriter, reply: bytes) -> None:
    writer.write(reply)
    await writer.drain()
    writer.close()
    await writer.wait_closed()


class Server[R]:
    """One request per connection. A subclass says how a request is `received` once its head is in, within the
    deadline, how it is `answered`, unless the client goes first, how a refusal is said, and what follows once an answer
    has left, which is when anyone is told of it."""

    def __init__(self, clock: Clock, *, connections: int = CONNECTIONS) -> None:
        self.clock = clock
        self.connections = connections
        self._server: asyncio.Server | None = None
        self._serving: set[asyncio.Task[None]] = set()

    async def listen(self, host: str, port: int = 0, *, tls: ssl.SSLContext | None = None) -> None:
        """Bind `host` and `port`, 0 for any free one, and start answering, over TLS with a context."""
        self._server = await asyncio.start_server(
            self._serve, host, port, limit=HEAD_LIMIT, ssl=tls, ssl_handshake_timeout=SECONDS if tls else None
        )

    @property
    def port(self) -> int:
        if self._server is None:
            raise RuntimeError("this server has not started")
        return self._server.sockets[0].getsockname()[1]

    async def stop(self) -> None:
        """Stop listening and drop every request under way."""
        server, self._server = self._server, None
        if server is not None:
            server.close()
            for task in self._serving:
                task.cancel()
            await asyncio.gather(*self._serving, return_exceptions=True)
            await server.wait_closed()

    async def receive(self, head: Head, reader: asyncio.StreamReader) -> R:
        """Check a request whose head is in, and read the rest of it."""
        raise NotImplementedError

    async def answer(self, request: R) -> bytes:
        raise NotImplementedError

    def refuse(self, rejected: Rejected) -> bytes:
        return response(rejected.status, b"", *rejected.headers)

    async def sent(self, request: R) -> None:
        """What follows once the answer to `request` has left."""

    async def _serve(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        task = asyncio.current_task()
        assert task is not None
        self._serving.add(task)
        try:
            request, reply = await self._reply(reader)
            await unless(self.clock.sleep(SECONDS), _send(writer, reply))
            if request is not None:
                await self.sent(request)
        except (Cut, ConnectionError, ssl.SSLError, asyncio.IncompleteReadError):
            pass  # A client that stalled or left is owed nothing.
        finally:
            writer.transport.abort()
            self._serving.discard(task)

    async def _reply(self, reader: asyncio.StreamReader) -> tuple[R | None, bytes]:
        if self._server is None or len(self._serving) > self.connections:
            return None, self.refuse(Rejected(503, why="too many connections are open: try again shortly"))
        try:
            request = await unless(self.clock.sleep(SECONDS), self._received(reader))
            return request, await unless(_hung_up(reader), self.answer(request))
        except Rejected as rejected:
            return None, self.refuse(rejected)
        except (Cut, ConnectionError, ssl.SSLError, asyncio.IncompleteReadError):
            raise
        except Exception:
            log.exception("a request failed")
            return None, self.refuse(Rejected(500))

    async def _received(self, reader: asyncio.StreamReader) -> R:
        try:
            head = await reader.readuntil(b"\r\n\r\n")
        except asyncio.LimitOverrunError:
            raise Rejected(431) from None
        return await self.receive(_parsed(head), reader)
