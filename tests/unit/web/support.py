"""What the browser client's tests share: a scripted team, its page served over a session, and a browser's side of a
real socket."""

import asyncio
import contextlib
import json
import sqlite3
from collections.abc import AsyncIterator, Mapping
from pathlib import Path
from typing import Any, NamedTuple

from platoon_harness import Session, Team
from platoon_harness.kernel import Clock, ManualClock
from platoon_harness.testing import Ask, Call, Hang, Say, ScriptedDriver, Think
from platoon_harness_cli.web import bodies, follow
from platoon_harness_cli.web.page import load
from platoon_harness_cli.web.projection import Projection
from platoon_harness_cli.web.server import Web
from platoon_harness_cli.web.sessions import Sessions

from ..runtime.support import harness, in_state, until

SECONDS = 15.0
LONG = "A long answer. " * 40
LEAD = [
    [
        Think("what to do"),
        Say(LONG),
        Call("task_add", {"queue": "tasks", "gist": "fix the flaky test", "body": "It fails one run in ten."}),
        Call("agent_spawn", {"name": "w1", "child_role": "worker", "goal": "take work from the queue"}),
        Call("message_send", {"to": "#general", "gist": "plan", "body": "Step one, then step two."}),
        Call("message_send", {"to": "@you", "gist": "I started a worker."}),
    ],
    [Say("heard you")],
]
WORKER = [
    [
        Call("task_claim", {"queue": "tasks"}),
        Call("message_send", {"to": "@lead", "gist": "w1 has the task"}),
        Ask("Ship the fix?"),
        Call("agent_finish", {"gist": "w1 finished"}),
    ]
]


def team(lead: Any = LEAD, worker: Any = WORKER) -> Team:
    """`lead`, which spawns `w1`, a topic `general` and a queue `tasks`."""
    roles = {
        "lead": {"harness": harness(lambda: ScriptedDriver(lead)), "may_spawn": ["worker"]},
        "worker": {"harness": harness(lambda: ScriptedDriver(worker)), "count": 0},
    }
    topology = {
        "edges": {"lead": ["children", "human"], "worker": ["parent"]},
        "channels": {
            "general": {"kind": "topic", "writers": "all", "readers": "all"},
            "tasks": {"kind": "queue", "writers": "role:lead", "readers": "role:worker"},
        },
        "limits": {"max_depth": 2},
    }
    return Team.model_validate({"roles": roles, "topology": topology})


QUIET = team([[Hang()]], [[Hang()]])


async def scenario(session: Session) -> None:
    """Run the team of `team()`, answering the worker's approval from the person, until the session settles."""
    await in_state(session, "lead", "idle")
    await session.send("@lead", "Fix the flaky test", body="Fix the flaky test in tests/test_cart.py.")
    approvals = await until(session.approvals, session)
    await session.resolve(approvals[0]["id"], "allow", expected_version=approvals[0]["version"], via="test")
    await in_state(session, "w1", "ended")
    await until(session.status, session, lambda status: status["settled"])


def tables(path: Path) -> dict[str, list[tuple[Any, ...]]]:
    """Every row of a projection, table by table."""
    db = sqlite3.connect(path)
    names = [row[0] for row in db.execute("SELECT name FROM sqlite_schema WHERE type = 'table' ORDER BY name")]
    found = {name: db.execute(f"SELECT * FROM {name} ORDER BY 1, 2").fetchall() for name in names}
    db.close()
    return found


async def rebuilt(session: Session, folder: Path, through: int) -> Projection:
    """A projection of what `session` holds through `through`, folded from nothing in `folder`."""
    projection = Projection(folder, session.name, "you")
    async for event in session.events():
        if event.seq > through:
            break
        projection.fold(event, await bodies(session, event))
    return projection


class Reply(NamedTuple):
    status: int
    headers: dict[str, str]
    body: bytes

    def json(self) -> Any:
        return json.loads(self.body)


class Browser:
    """A browser's side of a page's server, a session's or the sessions page's: what it would send, on a real socket."""

    def __init__(self, web: Web | Sessions) -> None:
        self.web = web
        self.token = ""

    @property
    def authority(self) -> str:
        return self.web.authorities[0]

    async def send(self, data: bytes) -> Reply:
        reader, writer = await asyncio.open_connection("127.0.0.1", self.web.port)
        try:
            writer.write(data)
            await writer.drain()
            async with asyncio.timeout(SECONDS):
                raw = await reader.read()
        finally:
            writer.close()
        head, _, body = raw.partition(b"\r\n\r\n")
        status, *lines = head.decode("latin-1").split("\r\n")
        headers = {name.lower(): value.strip() for name, _, value in (line.partition(":") for line in lines)}
        return Reply(int(status.split(" ")[1]), headers, body)

    async def request(
        self,
        method: str,
        path: str,
        body: bytes | Mapping[str, Any] | None = None,
        *,
        token: str | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> Reply:
        """A request as the page makes one: its own Host and Origin, and its session token, unless told otherwise."""
        data = body if isinstance(body, bytes) else b"" if body is None else json.dumps(body).encode()
        sent = {"Host": self.authority}
        if method == "POST":
            sent |= {"Origin": f"http://{self.authority}", "Content-Type": "application/json"}
            sent["Content-Length"] = str(len(data))
        token = self.token if token is None else token
        if token:
            sent["Authorization"] = f"Bearer {token}"
        sent |= dict(headers or {})
        lines = [
            f"{method} {path} HTTP/1.1",
            *(f"{name}: {value}" for name, value in sent.items() if value is not None),
        ]
        return await self.send("\r\n".join([*lines, "", ""]).encode() + data)

    async def view(self, name: str, params: Mapping[str, Any] | None = None, **options: Any) -> Any:
        reply = await self.request("POST", f"/v1/{name}", params or {}, **options)
        assert reply.status == 200, (reply.status, reply.body)
        return reply.json()

    async def exchange(self, link: str) -> Reply:
        secret = link.partition("#link=")[2]
        return await self.request("POST", "/x/exchange", {}, token=secret)

    async def opened(self, kind: str = "control") -> "Browser":
        """This browser, holding a session token of `kind`, spent from a link of its own: of either kind for a session's
        page, and for the sessions page the one it mints."""
        reply = await self.exchange(self.web.link() if isinstance(self.web, Sessions) else self.web.link(kind))
        assert reply.status == 200, reply.body
        self.token = reply.json()["token"]
        return self


@contextlib.asynccontextmanager
async def served(session: Session, root: Path, clock: Clock | None = None) -> AsyncIterator[Web]:
    """`session`'s page, served on loopback, its projection following the journal as `web` follows it."""
    projection = Projection(session.folder, session.name, "you")
    clock = clock or ManualClock(1_000_000.0)
    web = Web(session, projection, load(), clock)
    await web.listen("127.0.0.1")
    following = asyncio.ensure_future(follow(session, projection, web.moved, clock))
    try:
        yield web
    finally:
        following.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await following
        await web.stop()
        projection.close()


async def caught_up(web: Web, session: Session) -> int:
    """Wait until the projection has folded everything the journal holds now, and say how far that is."""
    head = await session.head()
    async with asyncio.timeout(SECONDS), web.moved:
        await web.moved.wait_for(lambda: web.projection.through >= head)
    return web.projection.through
