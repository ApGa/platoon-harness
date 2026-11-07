"""The page's server: SwarmChat's gate and `view_*` replies over the projection, and our own routes under `/x/`.

Every request is bounded before it is believed, by the SDK's HTTP: its head, then `Host` against the authority served,
which defeats DNS rebinding, and on a POST `Origin` against the page's own origin, then its bearer, and only then a body
of a stated length. A view credential reaches the page's reads alone: `view_*`, and `x_read`, every pane of ours, which
answers from the session's query ops alone. Every mutation is `/x/command` into `Session.submit`, the op path the
terminal uses, and the kernel's grants decide what the person may do. Every answer says `no-store`.
"""

import asyncio
import json
import re
from collections.abc import Mapping
from dataclasses import asdict
from typing import Any, NamedTuple

from platoon_harness import Refused, Session
from platoon_harness.http import Head, Rejected, Server, bearer, check_site, response
from platoon_harness.kernel import Clock, Outcome, first, is_held
from platoon_harness.runtime.control import BODY_LIMIT

from .. import __version__
from ..ops import CONFIRMED, cut, person_ops
from ..provenance import read
from ..roster import status_of
from . import replies
from .credentials import Class, Credentials, Held
from .page import Page
from .projection import SHOWN, Projection

JSON_LIMIT = 1024 * 1024
HOLD = 25.0
"""The longest the feed holds a page's request, which asks for no longer."""
HOLDING = 64
"""The most requests the feed holds at once. One past it is refused, and the page asks again a little later."""
TEXT_LIMIT = 5_000_000
"""The most of a text file the viewer is given, as SwarmChat's own server gives it."""
_KEY = re.compile(r"[0-9a-f]{32}")
_PAGE = ("Cache-Control: no-store", "X-Content-Type-Options: nosniff", "Referrer-Policy: no-referrer")
_JSON = "Content-Type: application/json"
_ROUTES = ("/x/exchange", "/x/command", "/x/body", "/x/link")
_READS = ("/v1/x_read",)
"""The page's one read of our own, beside SwarmChat's `view_*`, which a view credential reaches as it reaches those."""
_SPENT = "this link was used already or has expired: ask for a new one"


class Request(NamedTuple):
    """A request that has been believed: its route, the authority it named, the session token's credential or the link
    it would spend, and its body."""

    route: str
    authority: str
    held: Held | None = None
    link: str | None = None
    body: bytes = b""


class Web(Server[Request]):
    """The page's server for one session, as a guest of its runtime. It decides nothing: what it says comes from the
    projection, and from the session's own ops."""

    def __init__(
        self,
        session: Session,
        projection: Projection,
        page: Page,
        clock: Clock,
        *,
        host: str = "127.0.0.1",
        scheme: str = "http",
    ) -> None:
        super().__init__(clock)
        self.session, self.projection, self.page = session, projection, page
        self.credentials = Credentials(clock)
        self.moved = asyncio.Condition()
        self._host, self._scheme = host, scheme
        self._holding = 0
        self._statuses: tuple[int, dict[str, str]] = (-1, {})

    @property
    def authorities(self) -> tuple[str, ...]:
        """What `Host` may say: the address served, and `localhost` beside a loopback one, with the port, unless it is
        the scheme's own, which a browser leaves out."""
        host = f"[{self._host}]" if ":" in self._host else self._host
        loopback = ("localhost",) if self._host in ("127.0.0.1", "::1") else ()
        port = "" if self.port == {"http": 80, "https": 443}[self._scheme] else f":{self.port}"
        return tuple(f"{name}{port}" for name in (host, *loopback))

    def link(self, kind: Class, authority: str | None = None) -> str:
        """A one-time link of `kind` to the page."""
        return f"{self._scheme}://{authority or self.authorities[0]}/view#link={self.credentials.mint(kind)}"

    def live(self) -> bool:
        """Whether a runtime holds the session, which only the kernel's own check says."""
        return is_held(self.session.folder)

    # HTTP.

    async def receive(self, head: Head, reader: asyncio.StreamReader) -> Request:
        check_site(head, self.authorities, scheme=self._scheme, origin=head.method == "POST")
        route = head.path
        if route in ("/", "/view", "/v1/health"):
            if head.method != "GET":
                raise Rejected(405, "Allow: GET")
            return Request(route, head.headers["host"])
        if not (route.startswith("/v1/view_") or route in _READS or route in _ROUTES):
            raise Rejected(404, why=f"there is no route {route}")
        if head.method != "POST":
            raise Rejected(405, "Allow: POST")
        token, link = bearer(head), None
        if route == "/x/exchange":
            if not self.credentials.opens(token):
                raise Rejected(401, why=_SPENT)
            held, link = None, token
        elif (held := self.credentials.check(token)) is None:
            raise Rejected(401, "WWW-Authenticate: Bearer", why="this page's session has expired: open a new link")
        elif route.startswith("/x/") and held.kind != "control":
            raise Rejected(403, why="a view link shows the session and acts on nothing")
        body = await self.body(head, reader, BODY_LIMIT if route == "/x/body" else JSON_LIMIT)
        return Request(route, head.headers["host"], held, link, body)

    def refuse(self, rejected: Rejected) -> bytes:
        return response(rejected.status, json.dumps({"error": rejected.why}).encode(), _JSON, *_PAGE, *rejected.headers)

    async def answer(self, request: Request) -> bytes:
        route = request.route
        if route == "/":  # SwarmChat's own server sends a browser on to its page, and a link's fragment goes with it.
            return response(302, b"", "Location: /view", *_PAGE)
        if route == "/view":
            html = ("Content-Type: text/html; charset=utf-8", f"Content-Security-Policy: {self.page.policy}")
            return response(200, self.page.gate, *html, *_PAGE)
        if route == "/v1/health":
            limits = {"max_text": SHOWN, "max_attachment": BODY_LIMIT, "max_attachments": 1}
            return _json({"ok": True, "name": "platoon-harness", "version": __version__, "limits": limits})
        if route == "/x/exchange":  # A link is spent only here, in the answer that carries its token.
            if request.link is None or (spent := self.credentials.exchange(request.link)) is None:
                raise Rejected(401, why=_SPENT)
            token, held = spent
            return _json({"token": token, "class": held.kind, "expires": held.expires})
        held = request.held
        assert held is not None
        if route == "/x/body":
            return _json(await self._stored(request.body))
        params = _params(request.body)
        if route == "/x/command":
            return _json(await self._command(params))
        if route == "/x/link":
            kind = params.get("class")
            if kind not in ("view", "control"):
                raise Rejected(400, why="a link's class is view or control")
            return _json({"link": self.link(kind, request.authority), "class": kind})
        return await self._view(route.removeprefix("/v1/"), params, held)

    # The page's reads.

    async def _view(self, name: str, params: dict[str, Any], held: Held) -> bytes:
        projection = self.projection
        try:
            match name:
                case "view_page":
                    return _json({"html": self.page.html, "js": self.page.js})
                case "view_info":
                    return _json(await self._info(held))
                case "view_snapshot":
                    statuses = await self._roster()
                    return _json(replies.snapshot(projection, self._server_info(), statuses, self.clock.now()))
                case "view_feed":
                    return _json(await self._feed(params))
                case "view_messages":
                    return _json(replies.messages(projection, params))
                case "view_thread":
                    return _json(replies.thread(projection, params))
                case "view_receipts":
                    return _json(replies.receipts(projection, params))
                case "view_posts":
                    return _json(replies.posts(projection, params))
                case "view_search":
                    return _json(replies.search(projection, params))
                case "view_activity":
                    return _json(replies.activity(projection, params))
                case "view_as":
                    return _json(replies.seen_as(projection, params, await self._roster()))
                case "view_knew":
                    return _json(replies.knew(projection, params))
                case "view_text":
                    return _json(await self._text(params))
                case "view_download":
                    return await self._download(params)
                case "x_read":
                    return _json(await self._read(params))
            raise replies.Error(404, f"There is no request named '{name}'.")
        except replies.Error as error:
            raise Rejected(error.status, why=str(error)) from None

    def _server_info(self) -> dict[str, Any]:
        """The server as SwarmChat's page knows one: read-only while no runtime holds the session, and `data` is the
        session's name."""
        projection = self.projection
        server = {"name": "platoon-harness", "version": __version__, "read_only": not self.live()}
        return server | {"data": self.session.name, "feed": projection.count, "feed_id": projection.feed_id}

    async def _info(self, held: Held) -> dict[str, Any]:
        """The server, and in `x` what this page may do: the credential's class, whether a runtime holds the session,
        who the person is, the ops their grants hold, the ops asked about before they run, the most bytes a body may
        be, and why the page may do nothing, when it may not."""
        live, name = self.live(), self.session.name
        may: list[str] = []
        cannot = None
        if held.kind == "view":
            cannot = "This is a view link: it shows the session and acts on nothing."
        elif not live:
            cannot = (
                f"No runtime holds this session, so this is its history: `platoon-harness session resume {name}` "
                "resumes it, which can spend money."
            )
        else:
            outcome = await self.session.submit("ops.list")
            may = sorted(op["name"] for op in outcome.result or ())
        x = {
            "credential": held.kind,
            "live": live,
            "person": self.projection.person,
            "session": name,
            "may": may,
            "confirmed": sorted(CONFIRMED),
            "body_limit": BODY_LIMIT,
            "cannot": cannot,
        }
        return self._server_info() | {"x": x}

    async def _roster(self) -> dict[str, str]:
        """Each agent's status, as the roster says it, read again once the projection has moved."""
        through = self.projection.through
        if self._statuses[0] != through:
            outcome = await self.session.submit("view.watch", name="roster")
            rows = [] if outcome.refusal is not None else outcome.result["rows"]
            self._statuses = (through, {row["agent"]: status_of(row) for row in rows})
        return self._statuses[1]

    async def _feed(self, params: Mapping[str, Any]) -> dict[str, Any]:
        """Everything past the feed number `after`, held until something comes or the page's `timeout` passes, at most
        `HOLD`. A page whose `feed_id` is not this projection's, or that is past its end, takes a new snapshot."""
        projection = self.projection
        try:
            after, timeout = int(params.get("after") or 0), float(params.get("timeout", HOLD))
        except (TypeError, ValueError, OverflowError):
            raise Rejected(400, why="after is a feed number and timeout is in seconds") from None
        if params.get("feed_id") not in (None, projection.feed_id) or after > projection.count:
            return {"feed": projection.count, "events": [], "reset": True}
        if projection.count <= after and timeout > 0:
            if self._holding >= HOLDING:
                raise Rejected(503, why="too many pages are waiting for news: try again shortly")
            self._holding += 1
            try:
                await first(self._past(after), self.clock.sleep(min(timeout, HOLD)))
            finally:
                self._holding -= 1
        return replies.feed(projection, after, await self._roster()) | {"x": {"live": self.live()}}

    async def _past(self, after: int) -> None:
        async with self.moved:
            await self.moved.wait_for(lambda: self.projection.count > after)

    async def _body(self, params: Mapping[str, Any]) -> tuple[dict[str, Any], bytes]:
        found, ref = replies.attachment(self.projection, params)
        try:
            return found, await self.session.get_body(ref, limit=BODY_LIMIT)
        except Refused as refused:
            raise replies.Error(404, str(refused.refusal.detail)) from None

    async def _text(self, params: Mapping[str, Any]) -> dict[str, Any]:
        """A text file, its first `TEXT_LIMIT` bytes at most, cut at the end of a line."""
        found, data = await self._body(params)
        cut = len(data) > TEXT_LIMIT
        if cut:
            data = data[:TEXT_LIMIT]
            data = data[: data.rfind(b"\n") + 1] or data
        text = data.decode(errors="replace").removeprefix("﻿").replace("\0", "�")
        return {"text": text, "size": found["size"], "shown": len(data), "cut": cut}

    async def _download(self, params: Mapping[str, Any]) -> bytes:
        found, data = await self._body(params)
        headers = (f"Content-Type: {found['type']}", f"X-Attachment: {json.dumps(found)}")
        return response(200, data, *headers, *_PAGE)

    async def _read(self, params: Mapping[str, Any]) -> dict[str, Any]:
        """One pane of the page, which `pane` names, in the words of the command line's package and from the session's
        query ops alone, so a view link reads it too and nothing is written through it."""
        match params.get("pane"):
            case "provenance":
                return await self._provenance(params)
            case "attention":
                return await self._attention()
        raise replies.Error(404, "there is no such pane: the page's panes are provenance and attention")

    async def _attention(self) -> dict[str, Any]:
        """Where the person must act: every row of the runtime's `attention` view but a mention, which is a message to
        read in its chat, as the page keeps no marks to say which were read."""
        outcome = await self.session.submit("attention.list")
        if (refusal := outcome.refusal) is not None:
            raise replies.Error(403 if refusal.code == "not_permitted" else 400, f"{refusal.code}: {refusal.detail}")
        return {"rows": [row for row in outcome.result if row["kind"] != "mention"]}

    async def _provenance(self, params: Mapping[str, Any]) -> dict[str, Any]:
        """What the session's provenance queries say of the event `ref`, in the lines the terminal draws, and `at`, the
        message it is in its chat, if one shows it, where following it opens."""
        ref = params.get("ref")
        if not isinstance(ref, str):
            raise replies.Error(400, "ref is an event's ref, `stream@version`")
        try:
            panel = await read(self.session, ref)
        except Refused as refused:
            status = 404 if refused.refusal.code == "not_found" else 400
            raise replies.Error(status, f"{refused.refusal.code}: {refused.refusal.detail}") from None
        event = panel.event
        return {
            "ref": event["ref"],
            "at": replies.at(self.projection, event["ref"], event["seq"]),
            "lines": [asdict(line) for line in panel.lines],
        }

    # The page's acts.

    async def _command(self, params: dict[str, Any]) -> dict[str, Any]:
        """One op, as `Session.submit` runs it, and its outcome, a refusal among them. `key` is 128 random bits the page
        made for one draft or press and keeps until the act is answered, under `web/`, so a retry is one operation from
        whichever link sends it, and no other client's key meets it. `expected_version` is the op's argument of that
        name, and `via` is said here. A message's text is made its gist as the terminal makes it: cut when it is too
        long for one, and beside the name of the file that is its body, which `file` says."""
        op, args, key = params.get("op"), params.get("args", {}), params.get("key")
        if not isinstance(op, str) or not isinstance(args, dict) or not isinstance(key, str) or not _KEY.fullmatch(key):
            raise Rejected(400, why="a command is an op, its args, and a key of 32 lowercase hex the page made for it")
        if "key" in args or "via" in args:
            raise Rejected(400, why="key and via are said beside an op's args, and via by this server")
        if (version := params.get("expected_version")) is not None:
            if "expected_version" in args:
                raise Rejected(400, why="expected_version is said once")
            args = {**args, "expected_version": version}
        if (operation := person_ops().get(op)) is not None and "via" in operation.input.model_fields:
            args = {**args, "via": "browser"}
        key = f"web/{key}"
        if op == "message.send" and isinstance(gist := args.get("gist"), str):
            file = params.get("file")
            if not isinstance(file, str | None) or (file is None) != (args.get("body") is None):
                raise Rejected(400, why="a body the page sends is a file, which `file` names")
            try:
                gist, body = cut(gist, file=file)
            except ValueError as error:
                raise Rejected(400, why=str(error)) from None
            args = {**args, "gist": gist}
            if body is not None:
                try:
                    args["body"] = await self.session.put_body(body.encode())
                except Refused as refused:
                    return Outcome(op=op, key=key, args_hash="", refusal=refused.refusal).model_dump(mode="json")
        outcome = await self.session.submit(op, key=key, **args)
        return outcome.model_dump(mode="json")

    async def _stored(self, body: bytes) -> dict[str, Any]:
        """A body stored as the session stores one, for a command to cite by its ref."""
        try:
            return {"ref": await self.session.put_body(body)}
        except Refused as refused:
            return {"refusal": refused.refusal.model_dump(mode="json")}


def _json(value: Any) -> bytes:
    return response(200, json.dumps(value, ensure_ascii=False).encode(), _JSON, *_PAGE)


def _params(body: bytes) -> dict[str, Any]:
    """A request's JSON object, Unicode throughout: JSON can escape half of a character, which no text holds."""
    try:
        params = json.loads(body or b"{}")
        json.dumps(params, ensure_ascii=False).encode()
    except (ValueError, RecursionError):
        raise Rejected(400, why="the body is JSON, of Unicode text") from None
    if not isinstance(params, dict):
        raise Rejected(400, why="the body is a JSON object")
    return params
