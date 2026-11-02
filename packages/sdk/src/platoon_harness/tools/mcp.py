"""The tools-only MCP server: Streamable HTTP on loopback, JSON replies, no sessions, one request per connection."""

import asyncio
import contextlib
import hashlib
import json
import logging
from collections.abc import Awaitable, Coroutine, Iterator, Mapping
from http import HTTPStatus
from typing import Any, NamedTuple
from urllib.parse import parse_qs

from platoon_harness.kernel import Kernel, Op, Outcome, Principal, Refusal, Refused, first, tool_name
from platoon_harness.primitives import hold_open, lines_of
from platoon_harness.rpc import strict_loads
from platoon_harness.version import __version__

from .surface import Surface, body_fields, held_tools, list_tools, named_surface, notices_text, refusal_text

log = logging.getLogger("platoon_harness.tools")

_HOST = "127.0.0.1"
_PATH = "/mcp"
_REVISIONS = ("2025-11-25", "2025-06-18")
HARNESS_ANCHORS = ("claudecode/toolUseId", "callId")
_ANCHORS = (*HARNESS_ANCHORS, "platoon-harness/callId")
_ANCHOR_LIMIT = 256
_ONCE = frozenset({"authorization", "content-length", "host", "origin"})
_HEAD_LIMIT = 16 * 1024
_REQUEST_LIMIT = 1024 * 1024
_CONNECTION_LIMIT = 1024
_IO_SECONDS = 10.0
_RESULT_LIMIT = 32 * 1024
_BODY_READ_LIMIT = 16 * 1024 * 1024
_CHUNK = 64 * 1024
_REPEATED = "This call repeats an earlier one of this turn exactly, so this is that call's answer and nothing ran."


def _response(status: int, body: bytes = b"", *headers: str) -> bytes:
    lines = (
        f"HTTP/1.1 {status} {HTTPStatus(status).phrase}",
        "Content-Type: application/json",
        f"Content-Length: {len(body)}",
        "Connection: close",
        *headers,
    )
    return "\r\n".join((*lines, "", "")).encode() + body


class _Rejected(Exception):
    """A request refused at the HTTP layer."""

    def __init__(self, status: int, *headers: str) -> None:
        super().__init__(status)
        self.reply = _response(status, b"", *headers)


class _Cut(Exception):
    """What was being awaited lost its race, and has been dropped."""


class _BadParams(Exception):
    """JSON-RPC -32602."""


async def _unless[T](rival: Awaitable[Any], work: Coroutine[Any, Any, T]) -> T:
    """`work`'s result, unless `rival` finishes first, which drops the work and raises `_Cut`."""
    task = asyncio.ensure_future(work)
    if not await first(task, rival):
        raise _Cut
    return task.result()


async def _hung_up(reader: asyncio.StreamReader) -> None:
    """Return when the client goes. Anything else it sends is thrown away, so it cannot pile up here."""
    with contextlib.suppress(ConnectionError):
        while await reader.read(_CHUNK):
            pass


async def _send(writer: asyncio.StreamWriter, reply: bytes) -> None:
    writer.write(reply)
    await writer.drain()
    writer.close()
    await writer.wait_closed()


def _parsed_head(head: bytes) -> tuple[str, str, dict[str, str]]:
    """The method, target and headers of a request. A header that decides anything may appear once."""
    first, *lines = head[: -len(b"\r\n\r\n")].decode("latin-1").split("\r\n")
    request = first.split(" ")
    if len(request) != 3 or not request[2].startswith("HTTP/1."):
        raise _Rejected(400)
    headers: dict[str, str] = {}
    for line in lines:
        name, colon, value = line.partition(":")
        name = name.lower()
        if not colon or not name or " " in name or (name in _ONCE and name in headers):
            raise _Rejected(400)
        headers[name] = value.strip()
    return request[0], request[1], headers


def _length(headers: Mapping[str, str]) -> int:
    value = headers.get("content-length")
    if value is None or "transfer-encoding" in headers:
        raise _Rejected(411)
    if not (value.isascii() and value.isdecimal()):
        raise _Rejected(400)
    if len(value) > len(str(_REQUEST_LIMIT)) or int(value) > _REQUEST_LIMIT:
        raise _Rejected(413)
    return int(value)


def _anchor(meta: Any) -> dict[str, str] | None:
    """The client's own id for this call, kept under its own name. It is correlation evidence and proves nothing."""
    if isinstance(meta, dict):
        for name in _ANCHORS:
            value = meta.get(name)
            if isinstance(value, str) and 0 < len(value) <= _ANCHOR_LIMIT and value.isprintable():
                return {name: value}
    return None


def _key(anchor: str, op: str, arguments: dict[str, Any]) -> str:
    """One logical call. `op` and its arguments stay in the key because a script can make several calls under one id."""
    return hashlib.sha256(json.dumps([anchor, op, arguments], sort_keys=True).encode()).hexdigest()


def _failure(id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": id, "error": {"code": code, "message": message}}


def _hello(params: dict[str, Any]) -> dict[str, Any]:
    asked = params.get("protocolVersion")
    return {
        "protocolVersion": asked if asked in _REVISIONS else _REVISIONS[0],
        "capabilities": {"tools": {}},
        "serverInfo": {"name": "platoon-harness", "version": __version__},
    }


def _rows(result: Any) -> Iterator[dict[str, Any]]:
    """Where a result can hold a body: itself, and each row of a list in it."""
    if isinstance(result, dict):
        yield result
        for value in result.values():
            if isinstance(value, list):
                yield from (row for row in value if isinstance(row, dict))


def _unread(row: dict[str, Any]) -> str | None:
    """The body an op could not read, which it marks by leaving `text` null beside the body's ref."""
    ref = row.get("body") or row.get("ref")
    unread = "text" in row and row["text"] is None and isinstance(ref, str) and ref.startswith("sha256:")
    return ref if unread else None


def _size(value: Any) -> int:
    return len(json.dumps(value, ensure_ascii=False).encode())


class _Tool(NamedTuple):
    """A tool op, and the arguments of it that a model gives as text and an op takes as a hash."""

    op: Op
    bodies: tuple[str, ...]


class _Request(NamedTuple):
    """One request. `told` collects the waits its answer says have closed."""

    principal: Principal
    surface: Surface
    body: bytes
    told: list[int]


class ToolServer:
    """A kernel's tool ops over loopback HTTP. Everything is per request, from a bearer token, so an idle client holds
    nothing here: not a session, not a task, not a socket."""

    def __init__(self, kernel: Kernel) -> None:
        self._kernel = kernel
        self._tools = {
            tool_name(operation.name): _Tool(operation, body_fields(operation.input.model_json_schema()))
            for operation in kernel.ops.values()
            if operation.tool
        }
        self._server: asyncio.Server | None = None
        self._port = 0
        self._serving: set[asyncio.Task[None]] = set()

    async def start(self) -> None:
        """Bind a free port on loopback and start answering."""
        self._server = await asyncio.start_server(self._serve, _HOST, 0, limit=_HEAD_LIMIT)
        self._port = self._server.sockets[0].getsockname()[1]

    @property
    def url(self) -> str:
        """Where to reach this server. A client may add `?surface=` for how tools are named to its model."""
        if self._server is None:
            raise RuntimeError("the tool server has not started")
        return f"http://{_HOST}:{self._port}{_PATH}"

    async def stop(self) -> None:
        """Stop listening and drop every open call. Waits stay registered: they live in the service, not in a call."""
        server, self._server = self._server, None
        if server is not None:
            server.close()
            for task in self._serving:
                task.cancel()
            await asyncio.gather(*self._serving, return_exceptions=True)
            await server.wait_closed()

    # HTTP.

    async def _serve(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        task = asyncio.current_task()
        assert task is not None
        self._serving.add(task)
        kernel, told = self._kernel, []
        try:
            reply = await self._reply(reader, told)
            await _unless(kernel.clock.sleep(_IO_SECONDS), _send(writer, reply))
            for id in told:  # Only now is anyone told. A wait left open closes with its turn, and wakes its agent.
                await kernel.submit(kernel.runtime, "wait.release", {"id": id, "told": True})
        except (_Cut, ConnectionError, asyncio.IncompleteReadError):
            pass  # A client that stalled or left is owed nothing.
        finally:
            writer.transport.abort()
            self._serving.discard(task)

    async def _reply(self, reader: asyncio.StreamReader, told: list[int]) -> bytes:
        if self._server is None or len(self._serving) > _CONNECTION_LIMIT:
            return _response(503)
        try:
            request = await _unless(self._kernel.clock.sleep(_IO_SECONDS), self._receive(reader, told))
            return await _unless(_hung_up(reader), self._answer(request))
        except _Rejected as rejected:
            return rejected.reply
        except (_Cut, ConnectionError, asyncio.IncompleteReadError):
            raise
        except Exception:
            log.exception("a tool request failed")
            return _response(500)

    async def _receive(self, reader: asyncio.StreamReader, told: list[int]) -> _Request:
        """Read one request. Nothing past the head is read for a client that has not proved who it is."""
        try:
            head = await reader.readuntil(b"\r\n\r\n")
        except asyncio.LimitOverrunError:
            raise _Rejected(431) from None
        method, target, headers = _parsed_head(head)
        path, _, query = target.partition("?")
        if path != _PATH:
            raise _Rejected(404)
        self._check_site(headers)
        principal = self._identify(headers)
        if method != "POST":
            raise _Rejected(405, "Allow: POST")
        try:
            surface = named_surface(parse_qs(query).get("surface", ["mcp"])[0])
        except ValueError:
            raise _Rejected(400) from None
        return _Request(principal, surface, await reader.readexactly(_length(headers)), told)

    def _check_site(self, headers: Mapping[str, str]) -> None:
        """Refuse what a browser could be tricked into sending: only this address may be named."""
        sites = (f"{_HOST}:{self._port}", f"localhost:{self._port}")
        if headers.get("host") not in sites:
            raise _Rejected(421)
        if "origin" in headers and headers["origin"] not in tuple(f"http://{site}" for site in sites):
            raise _Rejected(403)

    def _identify(self, headers: Mapping[str, str]) -> Principal:
        """Identity comes from the token alone, never from `clientInfo`, `_meta` or arguments."""
        scheme, _, token = headers.get("authorization", "").partition(" ")
        if scheme.lower() != "bearer" or not token:
            raise _Rejected(401, "WWW-Authenticate: Bearer")
        try:
            return self._kernel.authenticate(token.strip())
        except Refused as refused:
            if refused.refusal.code == "unavailable":
                raise _Rejected(503) from None
            raise _Rejected(401, "WWW-Authenticate: Bearer") from None

    # JSON-RPC.

    async def _answer(self, request: _Request) -> bytes:
        try:
            message = strict_loads(request.body)
        except (ValueError, RecursionError):
            reply = _failure(None, -32700, "Parse error")
        else:
            reply = await self._handle(message, request)
        return _response(202) if reply is None else _response(200, json.dumps(reply).encode())

    async def _handle(self, message: Any, request: _Request) -> dict[str, Any] | None:
        """Answer one message. A batch is refused, and a notification has no answer."""
        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
            return _failure(None, -32600, "Invalid Request")
        id = message.get("id")
        method = message.get("method")
        if not isinstance(method, str) or ("id" in message and type(id) not in (str, int)):
            return _failure(None, -32600, "Invalid Request")
        if "id" not in message:
            return None
        params = message.get("params", {})
        if not isinstance(params, dict):
            return _failure(id, -32602, "params must be an object")
        try:
            match method:
                case "initialize":
                    result = _hello(params)
                case "ping":
                    result = {}
                case "tools/list":
                    result = {"tools": list_tools(self._kernel, request.principal, request.surface)}
                case "tools/call":
                    result = await self._call(request, params)
                case _:
                    return _failure(id, -32601, "Method not found")
        except _BadParams as bad:
            return _failure(id, -32602, str(bad))
        except Refused as refused:
            return _failure(id, -32603, f"{refused.refusal.code}: {refused.refusal.detail}")
        return {"jsonrpc": "2.0", "id": id, "result": result}

    # Tools.

    def _anchor_of(self, principal: Principal, native: Mapping[str, str] | None) -> str | None:
        """What makes a retry the same call: the client's id, or with none its agent's open turn."""
        if native is not None:
            return next(iter(native.values()))
        if principal.kind != "agent":
            return None
        status = self._kernel.query(self._kernel.runtime, "agent.status", {"agent": principal.name})
        return None if status.refusal is not None else status.result["turn"]

    async def _call(self, request: _Request, params: dict[str, Any]) -> dict[str, Any]:
        kernel = self._kernel
        name, arguments = params.get("name"), params.get("arguments", {})
        tool = self._tools.get(name) if isinstance(name, str) else None
        if tool is None:
            raise _BadParams("no such tool")
        if not isinstance(arguments, dict):
            raise _BadParams("arguments must be an object")
        native = _anchor(params.get("_meta"))
        anchor = self._anchor_of(request.principal, native)
        key = None if anchor is None else _key(anchor, tool.op.name, arguments)

        head = kernel.head
        try:
            outcome = await self._run(request.principal, tool, arguments, key, native)
            if outcome.refusal is None:
                finished = await self._finish(request, tool, arguments, outcome.result)
                outcome = outcome.model_copy(update={"result": finished})
        except Refused as refused:
            outcome = Outcome(op=tool.op.name, args_hash="", refusal=refused.refusal)
        if outcome.refusal is None:
            blocks = [json.dumps(outcome.result, ensure_ascii=False)]
        else:
            held = held_tools(kernel, request.principal)
            blocks = [refusal_text(outcome.refusal, request.surface, kernel.ops, held)]
        if native is None and outcome.seq is not None and outcome.seq <= head:
            blocks.append(_REPEATED)
        if (notices := await self._notices(request)) is not None:
            blocks.append(notices)
        content = [{"type": "text", "text": block} for block in blocks]
        return {"content": content, "isError": outcome.refusal is not None}

    async def _run(
        self, principal: Principal, tool: _Tool, arguments: dict[str, Any], key: str | None, native: Any
    ) -> Outcome:
        """Run one call, through `submit` so enforcement happens here however the list was filtered. A query that
        decoding refuses leaves no event, so an agent's is submitted too: `submit` refuses it and journals that."""
        kernel = self._kernel
        name = tool.op.name
        if not tool.op.query:
            stored = await self._stored(tool, arguments)
            return await kernel.submit(principal, name, stored, key=key, native=native)
        outcome = kernel.query(principal, name, arguments)
        if principal.kind == "agent" and outcome.refusal is not None and outcome.refusal.code == "invalid":
            await kernel.submit(principal, name, arguments, key=key, native=native)
        if outcome.refusal is None and (size := _size(outcome.result)) > _RESULT_LIMIT:
            detail = (
                f"this answer is {size} bytes, and a result holds {_RESULT_LIMIT}: ask for less, or carry on without it"
            )
            return Outcome(op=name, args_hash="", refusal=Refusal(code="unsupported", detail=detail))
        return outcome

    async def _stored(self, tool: _Tool, arguments: dict[str, Any]) -> dict[str, Any]:
        """Each body argument, offered as text, stored and replaced by its hash. Text that cannot be stored stays, for
        decoding to refuse."""
        stored = dict(arguments)
        for field in tool.bodies:
            text = stored.get(field)
            if isinstance(text, str):
                try:
                    data = text.encode()
                except UnicodeEncodeError:
                    continue
                stored[field] = f"sha256:{await self._kernel.put_body(data)}"
        return stored

    async def _finish(self, request: _Request, tool: _Tool, arguments: dict[str, Any], result: Any) -> Any:
        """Do what only this layer can do with a result: hold a wait open, and read what no op may."""
        if tool.op.name == "wait" and result["state"] == "pending":
            held = await hold_open(self._kernel, result)
            if held["state"] == "released":
                request.told.append(held["id"])
            return held
        await self._fill(request.principal, result, arguments)
        return result

    async def _fill(self, principal: Principal, result: Any, arguments: dict[str, Any]) -> None:
        """Add the bodies an op could not read, as far as one result has room."""
        room = _RESULT_LIMIT - _size(result)
        for row in _rows(result):
            ref = _unread(row)
            if ref is None or room <= 0:
                continue
            body, _, span = ref.partition("#")
            try:
                text = self._kernel.get_body(body.removeprefix("sha256:"), limit=_BODY_READ_LIMIT).decode()
            except (Refused, UnicodeDecodeError):
                continue  # Binary, redacted or too large: `text` stays null, which is true.
            cut = lines_of(body, text, span or arguments.get("range"), room)
            if cut.text is None or await self._offered(principal, f"{body}{cut.span}", cut.text):
                row |= cut.shown()
                room -= _size(cut.text)
                if row.get("ref") == ref:
                    row["ref"] = f"{body}{cut.span}"

    async def _offered(self, principal: Principal, ref: str, text: str) -> bool:
        """Record what is about to be shown, because an agent's read is evidence and an ack follows its commit."""
        if principal.kind != "agent":
            return True
        kernel = self._kernel
        digest = hashlib.sha256(text.encode()).hexdigest()
        offer = {"agent": principal.name, "ref": ref, "digest": digest}
        return (await kernel.submit(kernel.runtime, "blob.offer", offer)).refusal is None

    async def _notices(self, request: _Request) -> str | None:
        """Hand over pending steer notices, which gives a tool boundary on any harness whose tools are visible. Asking
        first means a call with nothing to carry journals nothing."""
        kernel = self._kernel
        principal = request.principal
        if principal.kind != "agent":
            return None
        agent = {"agent": principal.name}
        if not kernel.query(kernel.runtime, "delivery.pending", agent).result:
            return None
        handed = (await kernel.submit(kernel.runtime, "delivery.offer", {**agent, "boundary": "tool"})).result
        return (
            None if handed is None else notices_text(handed, request.surface, kernel.ops, held_tools(kernel, principal))
        )
