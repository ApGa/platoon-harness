"""The sessions page, which `platoon-harness web` serves with no session, on loopback alone: every session under the
root and how each stands, and opening, starting, resuming or stopping one, as the terminal's sessions screen does on a
terminal. What only the person may allow is asked first, once each: the page asks before a resume, which can spend
money, and before a stop, and the server, which alone can tell, before a start whose team needs trust or runs several
agents on one plan login.

Its server mints one link, which the command says, and keeps credentials of its own, so no link of a session's page
opens it and its token opens no session's page. A session opened from it is served in this process, on a port of its
own on the same host, as `web SESSION` serves one, and the page goes to a control link of that server.
"""

import asyncio
import base64
import hashlib
import json
import ssl
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any

from platoon_harness import ConfigError, Refused, Session, Team
from platoon_harness.config import PROJECT_FILE
from platoon_harness.http import Head, Rejected, Server, bearer, check_site, response
from platoon_harness.kernel import Clock, SystemClock, is_held
from platoon_harness.runtime.paths import find_root, listing, session_folder
from platoon_harness.schema import Problem

from ..exits import Usage
from ..output import note, refused
from ..sessions import ask_to_stop
from ..teams import Source
from . import forward, loopback, serve
from .credentials import Credentials
from .page import Unpinned, load
from .server import HEADERS, JSON_LIMIT, Request, Web, authorities_of, json_answer, params_of, refusal_answer

ACTS = ("/x/sessions", "/x/open", "/x/start", "/x/resume", "/x/stop")
"""What the page asks of its server, each on the session token its link was spent for."""
TRUST = "The team names what would run as you, or a credential to pass on, which needs your trust:"
"""What a start asks first of a team that needs trust, above each value that needs it."""
SPENT = "this link was used already or has expired, and only `platoon-harness web` gives one: run it again"
EXPIRED = "this page's session has expired, and only `platoon-harness web` gives a link: run it again"


def on_loopback(host: str) -> None:
    """Refuse to serve the sessions page past loopback: its link acts as you on every session here."""
    if not loopback(host):
        raise Usage(
            f"web with no session serves loopback alone, as its link acts as you on every session here: serve one "
            f"session on {host} with `web SESSION --host {host}`, or forward this page's port from another machine"
        )


def _page() -> tuple[bytes, str]:
    """The page, its one script in it, and the policy that lets that script alone run."""
    script = resources.files(__package__).joinpath("sessions.js").read_text()
    html = resources.files(__package__).joinpath("sessions.html").read_text()
    digest = base64.b64encode(hashlib.sha256(script.encode()).digest()).decode()
    policy = (
        f"default-src 'none'; script-src 'sha256-{digest}'; style-src 'unsafe-inline'; img-src data:; "
        "connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
    )
    return html.replace("<!--JS-->", f"<script>{script}</script>").encode(), policy


@dataclass(frozen=True)
class Served:
    """A session this `web` serves for the page: its server, once it listens, what stops it, and what serves it."""

    opened: asyncio.Future[Web]
    stop: asyncio.Event
    task: asyncio.Task[None]


class Sessions(Server[Request]):
    """The sessions page's server. It says what is under the root, as the terminal's sessions screen says it, and
    serves each session the page opens as `serve` serves one, on a port of its own, until it stops."""

    def __init__(self, clock: Clock, *, host: str = "127.0.0.1", tls: ssl.SSLContext | None = None) -> None:
        super().__init__(clock)
        self.credentials = Credentials(clock)
        self.html, self.policy = _page()
        self._host, self._tls = host, tls
        self._scheme = "https" if tls else "http"
        self._served: dict[str, Served] = {}

    @property
    def authorities(self) -> tuple[str, ...]:
        return authorities_of(self._host, self.port, self._scheme)

    def link(self) -> str:
        """A link to the page, which opens once, within ten minutes, as only the command that serves it says one."""
        return f"{self._scheme}://{self.authorities[0]}/#link={self.credentials.mint('control')}"

    async def stop(self) -> None:
        """Stop serving the page, then every session opened from it, each of which runs on as it was."""
        await super().stop()
        for served in self._served.values():
            served.stop.set()
        await asyncio.gather(*(served.task for served in self._served.values()), return_exceptions=True)

    # HTTP.

    async def receive(self, head: Head, reader: asyncio.StreamReader) -> Request:
        check_site(head, self.authorities, scheme=self._scheme, origin=head.method == "POST")
        route = head.path
        if route == "/":
            if head.method != "GET":
                raise Rejected(405, "Allow: GET")
            return Request(route, head.headers["host"])
        if route != "/x/exchange" and route not in ACTS:
            raise Rejected(404, why=f"there is no route {route}")
        if head.method != "POST":
            raise Rejected(405, "Allow: POST")
        token, link = bearer(head), None
        if route == "/x/exchange":
            if not self.credentials.opens(token):
                raise Rejected(401, why=SPENT)
            held, link = None, token
        elif (held := self.credentials.check(token)) is None:
            raise Rejected(401, "WWW-Authenticate: Bearer", why=EXPIRED)
        body = await self.body(head, reader, JSON_LIMIT)
        return Request(route, head.headers["host"], held, link, body)

    def refuse(self, rejected: Rejected) -> bytes:
        return refusal_answer(rejected)

    async def answer(self, request: Request) -> bytes:
        route = request.route
        if route == "/":
            html = ("Content-Type: text/html; charset=utf-8", f"Content-Security-Policy: {self.policy}")
            return response(200, self.html, *html, *HEADERS)
        if route == "/x/exchange":  # A link is spent only here, in the answer that carries its token.
            if request.link is None or (spent := self.credentials.exchange(request.link)) is None:
                raise Rejected(401, why=SPENT)
            token, held = spent
            return json_answer({"token": token, "class": held.kind, "expires": held.expires})
        params = params_of(request.body)
        match route:
            case "/x/sessions":
                return json_answer(await self._list())
            case "/x/start":
                return json_answer(await self._start(params))
            case "/x/resume":
                return json_answer(await self._resume(_name(params)))
            case "/x/stop":
                return json_answer(await self._stop(_name(params)))
        return json_answer(await self._open(_name(params)))

    # The page's reads and acts.

    async def _list(self) -> dict[str, Any]:
        """Every session under the root, as the terminal's sessions screen lists them: whether a runtime holds it, and
        its state, unknown with the refusal where its journal cannot be read; and the root, and the folder `web` runs
        in, from which a session would start."""
        root, here = find_root(), Path.cwd()
        rows = []
        for listed in await asyncio.to_thread(listing, root):
            try:
                async with Session.attach(listed.name, view=True) as attached:
                    state = (await attached.status())["state"]
            except Refused as error:
                state = f"unknown: {refused(error.refusal)}"
            rows.append({"name": listed.name, "live": listed.live, "state": state})
        project = PROJECT_FILE if (here / PROJECT_FILE).exists() else None
        return {"root": str(root), "here": str(here), "project": project, "rows": rows}

    async def _open(self, name: str) -> dict[str, Any]:
        """Serve the session `name` here, on a port of its own, unless this `web` serves it already, and answer with a
        control link of its server; or refuse, saying why, as `web SESSION` would."""
        served = self._served.get(name)
        if served is None or served.task.done():
            opened: asyncio.Future[Web] = asyncio.get_running_loop().create_future()
            stop = asyncio.Event()
            serving = serve(name, stop, host=self._host, port=0, tls=self._tls, clock=self.clock, opened=opened)
            served = self._served[name] = Served(opened, stop, asyncio.ensure_future(serving))
        await asyncio.wait((served.opened, served.task), return_when=asyncio.FIRST_COMPLETED)
        if not served.opened.done():
            return {"refused": _why(served.task)}
        return {"link": served.opened.result().link("control")}

    async def _start(self, params: dict[str, Any]) -> dict[str, Any]:
        """Start a session from `team`, a team file read from where `web` runs, or the project's own, named `name` or
        from the time, on a runtime of its own, and open it. First ask, once each, what only the person may allow: to
        trust what the team's files name to run as them or a credential to pass on, which `trust`, the digest of what
        was shown, answers, and to run several agents on one plan login, which `plan_login` answers. Or refuse, saying
        why, as `run` would."""
        team, name, trust, plan_login = (params.get(key) for key in ("team", "name", "trust", "plan_login"))
        if not (isinstance(team, str) and isinstance(name, str) and isinstance(trust, str | None)):
            raise Rejected(400, why="a start is a team file and a name, each of them text, and trust what was shown")
        if not isinstance(plan_login, bool | None):
            raise Rejected(400, why="plan_login says yes or no")
        path = Path(team) if team else None
        try:
            loaded, needing = await asyncio.to_thread(Source().trusted, path)
        except ConfigError as error:
            return {"refused": _problems(error)}
        if needing:
            question = _trusting(needing, loaded)
            if trust != (shown := hashlib.sha256(question.encode()).hexdigest()):
                return {"ask": {"question": question, "yes": "Trust and start", "answer": {"trust": shown}}}
        try:
            session = await Session.start(
                loaded, name=name or None, detach=True, cwd=Path.cwd(), plan_login=bool(plan_login)
            )
        except ConfigError as error:
            if not plan_login and [problem.where for problem in error.problems] == ["plan_login"]:
                question = f"{error.problems[0].what.partition(':')[0]}. Is this your own work?"
                return {"ask": {"question": question, "yes": "It is my own work", "answer": {"plan_login": True}}}
            return {"refused": _problems(error)}
        except Refused as error:
            return {"refused": refused(error.refusal)}
        await session.leave()
        return await self._open(session.name)

    async def _resume(self, name: str) -> dict[str, Any]:
        """Resume a session no runtime holds, on a runtime of its own, and open it, the page having said first, once,
        that its harnesses come back, which can spend money; or refuse, saying why."""
        try:
            if is_held(session_folder(find_root(), name)):
                return {"refused": f"A runtime holds {name} already: Open opens it."}
            await (await Session.resume(name, detach=True)).leave()
        except ConfigError as error:
            return {"refused": _problems(error)}
        except Refused as error:
            return {"refused": refused(error.refusal)}
        return await self._open(name)

    async def _stop(self, name: str) -> dict[str, Any]:
        """Stop a session's runtime as its owner would, as `session stop` does, the page having asked first, once, and
        answer once the runtime has let go, so the session stays resumable; or refuse, saying why."""
        try:
            async with Session.attach(name, view=True) as attached:
                await ask_to_stop(attached)
                async for _ in attached.events(await attached.head(), follow=True):
                    pass
        except Refused as error:
            return {"refused": refused(error.refusal)}
        return {"said": f"Stopped {name}. Resume restarts it, which can spend money."}


async def sessions(
    stop: asyncio.Event, *, host: str, port: int, tls: ssl.SSLContext | None, clock: Clock | None = None
) -> None:
    """Serve the sessions page on `host`, which `on_loopback` holds to loopback, and `port` until `stop` is set, and say
    its one link on stderr. A page file of SwarmChat's that is not the one pinned refuses this before anything is
    served, as each session it opens serves that page."""
    load()
    server = Sessions(clock or SystemClock(), host=host, tls=tls)
    try:
        await server.listen(host, port, tls=tls)
        where = server.authorities[0]
        note(f"web: your sessions under {find_root()}, on {where}. Its link opens once, within ten minutes")
        note(f"web: sessions link, which lists, starts, resumes and stops your sessions, as you: {server.link()}")
        if tls is None:
            forward(host, server.port)
        await stop.wait()
    finally:
        await server.stop()


def _name(params: dict[str, Any]) -> str:
    name = params.get("name")
    if not isinstance(name, str):
        raise Rejected(400, why="name is a session's, as the list names it")
    return name


def _problems(error: ConfigError) -> str:
    return "\n".join(map(str, error.problems))


def _trusting(needing: tuple[Problem, ...], team: Team) -> str:
    """What trusting a team asks: each value its files give that would run code as the person or pass on a credential,
    `needing`, by its place and as the team that runs holds it, defaults filled in, in JSON that escapes all but
    ASCII."""
    data = team.model_dump(mode="json")
    lines = []
    for problem in needing:
        value: Any = data
        for key in problem.where.split("."):
            value = value.get(key) if isinstance(value, dict) else None
        lines.append(f"{problem.where} = {json.dumps(value)}" if value is not None else str(problem))
    named = "\n".join(lines)
    return f"{TRUST}\n{named}\nTrust it, as shown here, and start?"


def _why(task: asyncio.Task[None]) -> str:
    """Why serving a session ended before it listened, in the command line's words."""
    if task.cancelled():
        return "web is stopping"
    match error := task.exception():
        case Refused():
            return refused(error.refusal)
        case ConfigError():
            return _problems(error)
        case Usage() | Unpinned() | OSError():
            return str(error)
    raise AssertionError(f"serving a session ended with {error!r}")
