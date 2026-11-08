"""The tools-only MCP server: Streamable HTTP on loopback, JSON replies, no sessions, one request per connection."""

import asyncio
import hashlib
import json
from collections.abc import Iterator, Mapping
from typing import Any, NamedTuple
from urllib.parse import parse_qs

from platoon_harness.http import Head, Rejected, Server, bearer, check_site, response
from platoon_harness.kernel import Kernel, Op, Outcome, Principal, Refusal, Refused, tool_name
from platoon_harness.primitives import hold_open, lines_of
from platoon_harness.rpc import strict_loads
from platoon_harness.version import __version__

from .surface import Surface, body_fields, held_tools, list_tools, named_surface, notices_text, refusal_text, taught

_HOST = "127.0.0.1"
_PATH = "/mcp"
_REVISIONS = ("2025-11-25", "2025-06-18")
HARNESS_ANCHORS = ("claudecode/toolUseId", "callId", "pi/toolCallId", "scripted/toolCallId")
_ANCHORS = (*HARNESS_ANCHORS, "platoon-harness/callId")
_ANCHOR_LIMIT = 256
_REQUEST_LIMIT = 1024 * 1024
_RESULT_LIMIT = 32 * 1024
_BODY_READ_LIMIT = 16 * 1024 * 1024
_JSON = "Content-Type: application/json"
_REPEATED = "This call repeats an earlier one of this turn exactly, so this is that call's answer and nothing ran."


class _BadParams(Exception):
    """JSON-RPC -32602."""


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
    """The ref of the event whose body an op could not read, which it marks by leaving `text` null beside the ref."""
    ref = row.get("ref")
    return ref if "text" in row and row["text"] is None and isinstance(ref, str) else None


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


class ToolServer(Server[_Request]):
    """A kernel's tool ops over loopback HTTP. Everything is per request, from a bearer token, so an idle client holds
    nothing here: not a session, not a task, not a socket."""

    def __init__(self, kernel: Kernel) -> None:
        super().__init__(kernel.clock)
        self._kernel = kernel
        self._tools = {
            tool_name(operation.name): _Tool(operation, body_fields(operation.input.model_json_schema()))
            for operation in kernel.ops.values()
            if operation.tool
        }

    async def start(self) -> None:
        """Bind a free port on loopback and start answering. Stopping drops every open call, and waits stay
        registered: they live in the service, not in a call."""
        await self.listen(_HOST)

    @property
    def url(self) -> str:
        """Where to reach this server. A client may add `?surface=` for how tools are named to its model."""
        return f"http://{_HOST}:{self.port}{_PATH}"

    # HTTP.

    async def receive(self, head: Head, reader: asyncio.StreamReader) -> _Request:
        """Nothing past the head is read for a client that has not proved who it is."""
        if head.path != _PATH:
            raise Rejected(404)
        check_site(head, (f"{_HOST}:{self.port}", f"localhost:{self.port}"))
        principal = self._identify(head)
        if head.method != "POST":
            raise Rejected(405, "Allow: POST")
        try:
            surface = named_surface(parse_qs(head.query).get("surface", ["mcp"])[0])
        except ValueError:
            raise Rejected(400) from None
        return _Request(principal, surface, await self.body(head, reader, _REQUEST_LIMIT), [])

    def refuse(self, rejected: Rejected) -> bytes:
        return response(rejected.status, b"", _JSON, *rejected.headers)

    async def sent(self, request: _Request) -> None:
        """Only now is anyone told. A wait left open closes with its turn, and wakes its agent."""
        kernel = self._kernel
        for id in request.told:
            await kernel.submit(kernel.runtime, "wait.release", {"id": id, "told": True})

    def _identify(self, head: Head) -> Principal:
        """Identity comes from the token alone, never from `clientInfo`, `_meta` or arguments."""
        token = bearer(head)
        try:
            return self._kernel.authenticate(token)
        except Refused as refused:
            if refused.refusal.code == "unavailable":
                raise Rejected(503) from None
            raise Rejected(401, "WWW-Authenticate: Bearer") from None

    # JSON-RPC.

    async def answer(self, request: _Request) -> bytes:
        try:
            message = strict_loads(request.body)
        except (ValueError, RecursionError):
            reply = _failure(None, -32700, "Parse error")
        else:
            reply = await self._handle(message, request)
        return response(202, b"", _JSON) if reply is None else response(200, json.dumps(reply).encode(), _JSON)

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
                finished = await self._finish(request, tool, arguments, outcome.result, native)
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
        if (notices := await self._notices(request, native)) is not None:
            blocks.append(notices)
        content = [{"type": "text", "text": block} for block in blocks]
        return {"content": content, "isError": outcome.refusal is not None}

    async def _run(
        self, principal: Principal, tool: _Tool, arguments: dict[str, Any], key: str | None, native: Any
    ) -> Outcome:
        """Run one call, through `submit` so enforcement happens here however the list was filtered. A query runs on a
        reader of its own off the event loop, so however long one takes, no other call waits behind it. A query that
        decoding refuses leaves no event, so an agent's is submitted too: `submit` refuses it and journals that."""
        kernel = self._kernel
        name = tool.op.name
        if not tool.op.query:
            stored = await self._stored(tool, arguments)
            return await kernel.submit(principal, name, stored, key=key, native=native)
        outcome = await asyncio.to_thread(kernel.query, principal, name, arguments)
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

    async def _finish(self, request: _Request, tool: _Tool, arguments: dict[str, Any], result: Any, native: Any) -> Any:
        """Do what only this layer can do with a result: hold a wait open, read what no op may, and say what to do
        `next` in the words of its surface, as a refusal says it."""
        if tool.op.name == "wait" and result["state"] == "pending":
            held = await hold_open(self._kernel, result)
            if held["state"] == "released":
                request.told.append(held["id"])
            return held
        await self._fill(request.principal, result, arguments, native)
        if isinstance(result, dict) and isinstance(step := result.get("next"), str):
            kernel = self._kernel
            result["next"] = taught(step, request.surface, kernel.ops, held_tools(kernel, request.principal))
        return result

    async def _fill(self, principal: Principal, result: Any, arguments: dict[str, Any], native: Any) -> None:
        """Add the bodies an op could not read, as far as one result has room. A row that is the body itself, with no
        `body` of its own to say it has one, then names the lines it shows."""
        kernel = self._kernel
        room = _RESULT_LIMIT - _size(result)
        for row in _rows(result):
            ref = _unread(row)
            if ref is None or room <= 0:
                continue
            event, _, wanted = ref.partition("#")
            body = kernel.query(kernel.runtime, "blob.hash", {"ref": event})
            if body.refusal is not None:
                continue
            try:
                text = kernel.get_body(body.result.removeprefix("sha256:"), limit=_BODY_READ_LIMIT).decode()
            except (Refused, UnicodeDecodeError):
                continue  # Binary, redacted or too large: `text` stays null, which is true.
            cut = lines_of(event, text, wanted or arguments.get("range"), room)
            if cut.text is None or await self._offered(principal, f"{event}{cut.range}", cut.text, native):
                row |= cut.shown()
                room -= _size(cut.text)
                if "body" not in row:
                    row["ref"] = f"{event}{cut.range}"

    async def _offered(self, principal: Principal, ref: str, text: str, native: Any) -> bool:
        """Record what is about to be shown, under the call that shows it, because an agent's read is evidence and an
        ack follows its commit."""
        if principal.kind != "agent":
            return True
        kernel = self._kernel
        digest = hashlib.sha256(text.encode()).hexdigest()
        offer = {"agent": principal.name, "ref": ref, "digest": digest}
        return (await kernel.submit(kernel.runtime, "blob.offer", offer, native=native)).refusal is None

    async def _notices(self, request: _Request, native: Any) -> str | None:
        """Hand over pending steer notices, under the call whose result carries them, which gives a tool boundary on
        any harness whose tools are visible. Asking first means a call with nothing to carry journals nothing."""
        kernel = self._kernel
        principal = request.principal
        if principal.kind != "agent":
            return None
        agent = {"agent": principal.name}
        if not kernel.query(kernel.runtime, "delivery.pending", agent).result:
            return None
        offer = {**agent, "boundary": "tool"}
        handed = (await kernel.submit(kernel.runtime, "delivery.offer", offer, native=native)).result
        return (
            None if handed is None else notices_text(handed, request.surface, kernel.ops, held_tools(kernel, principal))
        )
