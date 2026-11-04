"""The one link a `Session` has, in its two forms, and the control socket that joins them.

`Local` is the kernel in-process and `Remote` is the socket, and the server is a `Local` per connection, so the methods
mirror by construction. Law 8 holds because a client only ever pulls: `read` is a page, `changed` and `delta` are
long-polls on the shared pulse, and there is no queue or subscription here for a client to fill.
"""

import asyncio
import base64
import contextlib
import hmac
import secrets
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, Protocol, Self

from platoon_harness.kernel import (
    Clock,
    Delta,
    Kernel,
    Outcome,
    Page,
    Principal,
    Refusal,
    Refused,
    SystemClock,
)
from platoon_harness.rpc import BUSY, INVALID_PARAMS, LINE_LIMIT, METHOD_NOT_FOUND, Closed, Peer, RpcError

from .paths import OWNER_TOKEN, VIEW_TOKEN, read_running, socket_path

PROTOCOL = 1
REFUSED = -32010

_CLIENT_LIMIT = 256
_HELLO_SECONDS = 10.0
_POLL_SECONDS = 25.0
_PAGE_LIMIT = 256
BODY_LIMIT = LINE_LIMIT // 4 * 3 - 1024
"""The largest body this socket carries, as base64 in one line."""

__all__ = ["BODY_LIMIT", "PROTOCOL", "REFUSED", "Control", "History", "Link", "Local", "Remote"]


class Link(Protocol):
    """Everything a `Session` does to a session, once. A method raises `Refused`, except that `submit` and `query`
    return an `Outcome`, and `Closed` means the runtime went, so the caller may try again under the same key."""

    @property
    def clock(self) -> Clock: ...

    @property
    def principal(self) -> str:
        """Who this link acts as."""
        ...

    async def submit(self, op: str, args: Mapping[str, Any], *, key: str | None = None) -> Outcome: ...

    async def query(self, op: str, args: Mapping[str, Any]) -> Outcome: ...

    async def read(
        self,
        after: int = 0,
        *,
        before: int | None = None,
        match: str | None = None,
        streams: Sequence[str] | None = None,
        limit: int = _PAGE_LIMIT,
    ) -> Page: ...

    async def put_body(self, body: bytes) -> str: ...

    async def get_body(self, sha256: str, limit: int | None = None) -> bytes: ...

    async def changed(self, after: int) -> int | None:
        """The head, once it passes `after`, or None if nothing more can come."""
        ...

    async def delta(self, agent: str, after: int | None) -> Delta | None:
        """The next frame of an agent's live text past `after`, or None if no more can come."""
        ...

    async def others(self) -> int:
        """How many other clients could act on this session now."""
        ...

    async def close(self) -> None: ...


class Local:
    """The link as the kernel in-process. `denied` is the refusal for every write, which a view credential and a session
    with no runtime have; a command otherwise cannot tell those apart from a mistake in its arguments."""

    def __init__(
        self,
        kernel: Kernel,
        principal: Principal,
        *,
        denied: Refusal | None = None,
        others: Callable[[], int] = lambda: 0,
    ) -> None:
        self._kernel = kernel
        self._principal = principal
        self._denied = denied
        self._others = others

    @property
    def clock(self) -> Clock:
        return self._kernel.clock

    @property
    def principal(self) -> str:
        return self._principal.id

    def _refuse_writes(self) -> None:
        if self._denied is not None:
            raise Refused(self._denied.code, self._denied.detail)

    async def submit(self, op: str, args: Mapping[str, Any], *, key: str | None = None) -> Outcome:
        """A read is answered as a query, since no client is an agent, so it writes nothing and a view may ask it."""
        kernel = self._kernel
        operation = kernel.ops.get(op)
        if operation is not None and (operation.query or operation.exposes):
            return kernel.query(self._principal, op, args)
        if self._denied is not None:
            return Outcome(op=op, args_hash="", refusal=self._denied.model_copy(update={"op": op}))
        return await kernel.submit(self._principal, op, args, key=key)

    async def query(self, op: str, args: Mapping[str, Any]) -> Outcome:
        return self._kernel.query(self._principal, op, args)

    async def read(
        self,
        after: int = 0,
        *,
        before: int | None = None,
        match: str | None = None,
        streams: Sequence[str] | None = None,
        limit: int = _PAGE_LIMIT,
    ) -> Page:
        principal = self._principal
        return self._kernel.read(principal, after=after, before=before, match=match, streams=streams, limit=limit)

    async def put_body(self, body: bytes) -> str:
        self._refuse_writes()
        return await self._kernel.put_body(body)

    async def get_body(self, sha256: str, limit: int | None = None) -> bytes:
        return self._kernel.get_body(sha256, limit=limit)

    async def changed(self, after: int) -> int | None:
        kernel = self._kernel
        if not kernel.read_only:
            await kernel.changed(after)
        return kernel.head if kernel.head > after else None

    async def delta(self, agent: str, after: int | None) -> Delta | None:
        """The next frame. A name nobody holds is refused, or asking for it would keep a ring for ever."""
        known = self._kernel.query(self._principal, "agent.status", {"agent": agent})
        if known.refusal is not None:
            raise Refused.of(known.refusal)
        if self._kernel.read_only:
            return None
        frames = self._kernel.deltas(known.result["agent"], after=after)
        try:
            return await anext(frames, None)
        finally:
            await frames.aclose()

    async def others(self) -> int:
        return self._others()

    async def close(self) -> None:
        return None


class History(Local):
    """The link with no runtime: a read-only kernel, closed along with the link."""

    def __init__(self, kernel: Kernel, principal: Principal, resume_with: str) -> None:
        detail = f"no runtime holds this session, so this is history: {resume_with} restarts it"
        super().__init__(kernel, principal, denied=Refusal(code="unavailable", detail=detail))

    async def submit(self, op: str, args: Mapping[str, Any], *, key: str | None = None) -> Outcome:
        """A command the journal answered under `key` gets that answer, as a retry would from a runtime, so one whose
        runtime went after it committed stays one operation. Any other write is refused, naming what restarts it."""
        operation = self._kernel.ops.get(op)
        if key is not None and operation is not None and not (operation.query or operation.exposes):
            answered = await self._kernel.submit(self._principal, op, args, key=key)
            if answered.seq is not None:
                return answered
        return await super().submit(op, args, key=key)

    def stale(self) -> bool:
        """Whether a writer has changed the journal, which an immutable reader cannot read past."""
        return self._kernel.query(self._principal, "session.status", {}).refusal is not None

    async def close(self) -> None:
        self._kernel.close()


def _encoded(body: bytes) -> str:
    return base64.b64encode(body).decode()


def _refused(error: RpcError) -> Refused:
    """What the other side said, as the one error a `Link` raises."""
    if error.code == REFUSED:
        return Refused.of(Refusal.model_validate(error.data))
    return Refused("busy" if error.code == BUSY else "unavailable", error.message)


class Remote:
    """The link as the control socket. The credential is said once, by `hello`, and binds the principal to this
    connection. A long-poll comes back empty now and then, and goes round again, so that a client that gave up frees the
    server's task within one poll."""

    def __init__(self, peer: Peer, running: asyncio.Task[None]) -> None:
        self._peer = peer
        self._running = running
        self._principal = ""

    @classmethod
    async def connect(cls, folder: Path, *, view: bool = False) -> Self:
        """Connect to the runtime a folder names. `Closed` means there is none to reach."""
        found = read_running(folder)
        if found is None:
            raise Closed("no runtime has said it is here")
        try:
            token = (folder / (VIEW_TOKEN if view else OWNER_TOKEN)).read_text()
            reader, writer = await asyncio.open_unix_connection(found.socket)
        except OSError as error:
            raise Closed(f"the runtime cannot be reached: {error}") from error
        peer = Peer(reader, writer)
        running = asyncio.create_task(peer.run())
        running.add_done_callback(lambda task: task.cancelled() or task.exception())
        link = cls(peer, running)
        try:
            await link.hello(token)
        except BaseException:
            await link.close()
            raise
        return link

    async def hello(self, token: str) -> None:
        """Say the credential that binds this connection. It is said once."""
        said = await self._call("hello", {"token": token, "protocol": PROTOCOL})
        self._principal = said["principal"]

    @property
    def clock(self) -> Clock:
        return SystemClock()

    @property
    def principal(self) -> str:
        return self._principal

    async def _call(self, method: str, params: Mapping[str, Any]) -> Any:
        try:
            return await self._peer.call(method, params)
        except RpcError as error:
            raise _refused(error) from None

    async def submit(self, op: str, args: Mapping[str, Any], *, key: str | None = None) -> Outcome:
        return Outcome.model_validate(await self._call("submit", {"op": op, "args": args, "key": key}))

    async def query(self, op: str, args: Mapping[str, Any]) -> Outcome:
        return Outcome.model_validate(await self._call("query", {"op": op, "args": args}))

    async def read(
        self,
        after: int = 0,
        *,
        before: int | None = None,
        match: str | None = None,
        streams: Sequence[str] | None = None,
        limit: int = _PAGE_LIMIT,
    ) -> Page:
        asked = {"after": after, "before": before, "match": match, "streams": streams, "limit": limit}
        return Page.model_validate(await self._call("read", asked))

    async def put_body(self, body: bytes) -> str:
        if len(body) > BODY_LIMIT:
            raise Refused("invalid", f"this socket carries bodies up to {BODY_LIMIT} bytes")
        return await self._call("put_body", {"body": _encoded(body)})

    async def get_body(self, sha256: str, limit: int | None = None) -> bytes:
        found = await self._call("get_body", {"sha256": sha256, "limit": limit})
        return base64.b64decode(found)

    async def changed(self, after: int) -> int | None:
        while True:
            polled = await self._call("changed", {"after": after})
            if not polled["again"]:
                return polled["head"]

    async def delta(self, agent: str, after: int | None) -> Delta | None:
        while True:
            polled = await self._call("delta", {"agent": agent, "after": after})
            if not polled["again"]:
                return None if polled["frame"] is None else Delta.model_validate(polled["frame"])

    async def others(self) -> int:
        return await self._call("others", {})

    async def close(self) -> None:
        self._peer.close()
        self._running.cancel()
        with contextlib.suppress(asyncio.CancelledError, Closed):
            await self._running


class _Connection:
    """One client: nothing but the link its credential bound."""

    def __init__(self, control: "Control") -> None:
        self._control = control
        self.link: Local | None = None
        self.writes = False

    async def handle(self, method: str, params: Any) -> Any:
        try:
            if method == "hello":
                return self._hello(params)
            if self.link is None:
                raise Refused("not_permitted", "say hello first")
            return await self._answer(self.link, method, params)
        except Refused as refused:
            error = refused.refusal.model_dump(mode="json")
            raise RpcError(REFUSED, str(refused), error) from None
        except (AttributeError, KeyError, TypeError, ValueError) as error:
            raise RpcError(INVALID_PARAMS, f"bad params for {method}: {error}") from error

    def _hello(self, params: Any) -> dict[str, Any]:
        if params["protocol"] != PROTOCOL:
            raise Refused("unsupported", f"this runtime speaks protocol {PROTOCOL}")
        if self.link is not None:
            raise Refused("conflict", "a credential is checked once per connection")
        self.link, self.writes, principal = self._control.bind(params["token"])
        return {"principal": principal, "writes": self.writes, "protocol": PROTOCOL}

    async def _answer(self, link: Local, method: str, params: Any) -> Any:
        match method:
            case "submit":
                return (await link.submit(params["op"], params["args"], key=params.get("key"))).model_dump()
            case "query":
                return (await link.query(params["op"], params["args"])).model_dump()
            case "read":
                limit = min(params.get("limit", _PAGE_LIMIT), _PAGE_LIMIT)
                asked = {name: params.get(name) for name in ("before", "match", "streams")}
                return (await link.read(params["after"], **asked, limit=limit)).model_dump(mode="json")
            case "put_body":
                return await link.put_body(base64.b64decode(params["body"]))
            case "get_body":
                limit = min(params.get("limit") or BODY_LIMIT, BODY_LIMIT)
                return _encoded(await link.get_body(params["sha256"], limit))
            case "changed":
                return await self._poll("head", link.changed(params["after"]))
            case "delta":
                polled = await self._poll("frame", link.delta(params["agent"], params.get("after")))
                frame = polled["frame"]
                return {**polled, "frame": None if frame is None else frame.model_dump(mode="json")}
            case "others":
                return await link.others()
            case _:
                raise RpcError(METHOD_NOT_FOUND, f"no method {method}")

    async def _poll(self, name: str, waiting: Any) -> dict[str, Any]:
        """A long-poll, bounded so that a client that left frees this task soon."""
        try:
            async with asyncio.timeout(_POLL_SECONDS):
                return {name: await waiting, "again": False}
        except TimeoutError:
            return {name: None, "again": True}


class Control:
    """The control socket of one runtime: JSON-RPC lines on a Unix socket in a private directory. A connection costs a
    task and a socket. Pages leave only when asked for, and a client that stops reading is dropped by its `Peer`, so it
    costs its own lag and can hold up nobody else."""

    def __init__(self, kernel: Kernel, human: Principal, folder: Path) -> None:
        self._kernel = kernel
        self._human = human
        self._folder = folder
        self.view_token = secrets.token_urlsafe(32)
        self._server: asyncio.Server | None = None
        self._serving: set[asyncio.Task[None]] = set()
        self._connections: set[_Connection] = set()

    async def start(self) -> None:
        self.path = socket_path(self._folder)
        self._server = await asyncio.start_unix_server(self._serve, path=self.path)
        self.path.chmod(0o600)

    async def stop(self) -> None:
        """Stop listening and drop every client. Each reads EOF, which is how it learns the runtime went."""
        server, self._server = self._server, None
        if server is not None:
            server.close()
            for task in self._serving:
                task.cancel()
            await asyncio.gather(*self._serving, return_exceptions=True)
            await server.wait_closed()
            self.path.unlink(missing_ok=True)

    def clients(self) -> int:
        """How many clients hold a credential that can act."""
        return sum(connection.writes for connection in self._connections)

    def bind(self, token: str) -> tuple[Local, bool, str]:
        """The link a credential earns. A view token reads and never writes. An agent's token is no client's: its reads
        are ops, and the tool plane is its way in."""
        if hmac.compare_digest(token, self.view_token):
            denied = Refusal(code="not_permitted", detail="a view credential reads and never writes")
            return Local(self._kernel, self._human, denied=denied), False, self._human.id
        principal = self._kernel.authenticate(token)
        if principal.kind == "agent":
            raise Refused("not_permitted", "an agent's token is for the tool plane")
        return Local(self._kernel, principal, others=lambda: self.clients() - 1), True, principal.id

    async def _serve(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        if self._server is None:  # It was accepted as this runtime stopped, which is too late.
            writer.transport.abort()
            return
        task = asyncio.current_task()
        assert task is not None
        self._serving.add(task)
        connection = _Connection(self)
        peer = Peer(reader, writer, connection.handle)
        expiry = asyncio.create_task(self._expire(connection, peer))
        self._connections.add(connection)
        try:
            if len(self._serving) <= _CLIENT_LIMIT:
                await peer.run()
        except Closed:
            pass  # A client past the line limit is simply gone.
        finally:
            self._connections.discard(connection)
            self._serving.discard(task)
            expiry.cancel()
            writer.transport.abort()  # A close waits to flush, and a client that stopped reading never lets it.

    async def _expire(self, connection: _Connection, peer: Peer) -> None:
        """Drop a connection that never says who it is."""
        await self._kernel.clock.sleep(_HELLO_SECONDS)
        if connection.link is None:
            peer.close()
