"""The browser client: SwarmChat's page over one session's journal, which `platoon-harness web SESSION` serves, and a
page of your sessions, which `web` with no session serves (`sessions`). The command line imports it only then, as it
does the terminal UI.

`web SESSION` is a guest of the session's runtime, on the owner's control credential, as every client of this user's
is. It starts and resumes nothing, so on history the page does nothing and names the command that resumes it, and
leaving it changes nothing in the session. One `web` serves a session at a time, as its projection has one writer. A
session on a plan login it serves on loopback alone, as a control link acts as you, on your login.

`web SESSION --replay` serves a replay of it instead, over the replay's own copy, whose projection it alone writes, and
whose links act on nothing in the session, so it serves one past loopback whatever login its agents ran on.
"""

import asyncio
import contextlib
import fcntl
import ipaddress
import os
import socket
import ssl
from pathlib import Path

from platoon_harness import ConfigError, Refused, Session, Team
from platoon_harness.config import Manifest
from platoon_harness.drivers import DriverError
from platoon_harness.kernel import Clock, Event, Refusal, SystemClock, first, is_held
from platoon_harness.runtime.control import BODY_LIMIT
from platoon_harness.runtime.opening import make_driver
from platoon_harness.runtime.paths import MANIFEST
from platoon_harness.schema import Problem

from ..exits import Usage
from ..output import note
from ..replay import Player
from .page import Page, load
from .projection import Projection, name_of
from .server import Web

LOOK = 1.0
"""How often a session that is history is looked at for a runtime that took it up again."""
LOCK = "swarmchat.lock"
"""What the one `web` serving a session holds, beside its projection, and where it says it serves."""
UP = frozenset({"agent.started", "agent.resumed"})
"""What says an agent's harness came up, and on which login."""


def loopback(host: str) -> bool:
    """Whether `host` is this machine alone: `localhost`, or an address of loopback."""
    try:
        return host == "localhost" or ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def wildcard(host: str) -> bool:
    """Whether `host` is a wildcard address, or a name that resolves to one, as `0` does. A name that resolves to
    nothing is left to the listen, which says so."""
    try:
        found = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except (OSError, UnicodeError):
        return False
    return any(ipaddress.ip_address(info[4][0]).is_unspecified for info in found)


def tls_for(host: str, certificate: Path | None, key: Path | None) -> ssl.SSLContext | None:
    """TLS for `host`, which any address but loopback needs."""
    if (certificate is None) != (key is None):
        raise Usage("give --certificate and --key together")
    if wildcard(host):
        raise Usage(f"--host {host} names no one address that a browser's requests could name: name the one to serve")
    if certificate is None or key is None:
        if not loopback(host):
            raise Usage(f"serving {host}, which is not loopback, needs TLS: give --certificate and --key")
        return None
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    try:
        context.load_cert_chain(certificate, key)
    except (OSError, ssl.SSLError) as error:
        raise Usage(f"--certificate and --key: {error}") from None
    return context


def past_loopback(name: str, why: str) -> ConfigError:
    """Why a session on a plan login is served on loopback alone, and what to do instead."""
    what = (
        f"session {name} runs on a plan login, as {why}, so web serves it on loopback alone: a control link acts as "
        "you, and on a plan login another person may not. Serve loopback and forward its port from another machine, or "
        "give each role an auth profile"
    )
    return ConfigError([Problem("--host", what)])


async def refuse_a_plan_login(session: Session) -> None:
    """Refuse a session one of whose agents' harnesses came up last on a plan login, as the roster says. A harness that
    cannot tell is not counted, as the runtime does not count it for its own refusal."""
    roster = await session.submit("view.watch", name="roster")
    if roster.refusal is not None:
        raise Refused.of(roster.refusal)
    if on := [row["agent"] for row in roster.result["rows"] if row["login"] == "plan"]:
        raise past_loopback(session.name, f"{', '.join(on)} came up on one")


def plan_roles(manifest: Manifest) -> list[str]:
    """The roles of a session's team whose agents would start on a plan login: each names no auth profile, and its
    harness says now that it is signed in on one. A trainable session's agents run on its authority's gateway, and a
    harness that cannot say runs nothing, so the runtime counts neither, nor does this. It blocks, as a harness may say
    it by running."""
    if manifest.trainable:
        return []
    team, cwd, found = Team.loads(manifest.team), Path(manifest.cwd), []
    for name, role in team.roles.items():
        with contextlib.suppress(ConfigError, DriverError):
            if role.auth is None and make_driver(role, cwd).describe().login == "plan":
                found.append(name)
    return found


async def bodies(session: Session, event: Event) -> dict[str, bytes | Refusal]:
    """What the fold of `event` shows of the bodies it cites: their bytes, or why they could not be read."""
    found: dict[str, bytes | Refusal] = {}
    for ref in Projection.cited(event):
        try:
            found[ref] = await session.get_body(ref, limit=BODY_LIMIT)
        except Refused as refused:
            found[ref] = refused.refusal
    return found


async def follow(
    session: Session, projection: Projection, moved: asyncio.Condition, clock: Clock, *, on_loopback: bool = True
) -> None:
    """Fold the journal as it grows, across a runtime that goes and one that comes back, and tell whoever waits on
    `moved`. While no runtime holds the session it looks every `LOOK` seconds for one, or for what one wrote and left,
    which decides nothing. Served past loopback, it ends when an agent's harness comes up on a plan login, as `serve`
    refuses to start then."""
    while True:
        with contextlib.suppress(Refused):
            async for event in session.events(projection.through, follow=True):
                if not on_loopback and event.type in UP:
                    await refuse_a_plan_login(session)
                projection.fold(event, await bodies(session, event))
                async with moved:
                    moved.notify_all()
        while not is_held(session.folder) and await session.head() <= projection.through:
            await clock.sleep(LOOK)


async def _replay(
    name: str,
    stop: asyncio.Event,
    page: Page,
    clock: Clock,
    *,
    host: str,
    port: int,
    tls: ssl.SSLContext | None,
    opened: asyncio.Future[Web] | None,
) -> None:
    """Serve a replay of a session's page as `serve` serves the session's, until `stop` is set, and close the replay,
    which takes its copies back."""
    player = await Player.open(name, clock=clock)
    try:
        session = player.replay.session
        person = name_of(Manifest.model_validate_json((session.folder / MANIFEST).read_bytes()).principal)
        projection = Projection(session.folder, name, person)
        web = Web(session, projection, page, clock, host=host, scheme="https" if tls else "http", player=player)
        try:
            await web.listen(host, port, tls=tls)
            if opened is None:
                note(
                    f"web: a replay of session {name} on {web.authorities[0]}. Each link opens once, within ten minutes"
                )
                note(f"web: view link, which watches the replay: {web.link('view')}")
                note(f"web: control link, which plays and moves the replay, and acts on nothing: {web.link('control')}")
            else:
                note(f"web: a replay of session {name} on {web.authorities[0]}, opened from your sessions page")
                opened.set_result(web)
            if tls is None:
                forward(host, web.port)

            async def folding(followed: Session, projected: Projection) -> None:
                await follow(followed, projected, web.moved, clock)

            await first(web.replaying(folding), stop.wait())
        finally:
            await web.stop()
            web.projection.close()
    finally:
        await player.close()


def forward(host: str, port: int) -> None:
    """Say how another machine reaches a page served on loopback without TLS: through a forward of its port."""
    target = f"[{host}]" if ":" in host else host
    note(
        "web: from another machine, forward this port under the same number, which the page's requests must name: "
        f"ssh -N -L {port}:{target}:{port} {socket.gethostname()}"
    )


def hold(folder: Path, name: str) -> int:
    """Be the one `web` serving the session in `folder` until the lock this gives is closed, or refuse, saying where the
    one that is serves it."""
    lock = os.open(folder / LOCK, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        where = os.read(lock, 512).decode(errors="replace")
        os.close(lock)
        raise Usage(
            f"web serves session {name} already{where}, and one serves a session at a time: your own page there makes "
            "new links, or stop that one first"
        ) from None
    os.ftruncate(lock, 0)
    return lock


async def serve(
    name: str,
    stop: asyncio.Event,
    *,
    host: str,
    port: int,
    tls: ssl.SSLContext | None,
    clock: Clock | None = None,
    opened: asyncio.Future[Web] | None = None,
    replay: bool = False,
) -> None:
    """Serve a session's page on `host` and `port` until `stop` is set, and say one view link and one control link on
    stderr, or with `opened`, which the sessions page passes, give it the server once it listens, to make the links.
    With `replay`, serve a replay of it. A page file that is not the one pinned, or a session on a plan login past
    loopback, refuses this before anything is served."""
    page, clock = load(), clock or SystemClock()
    if replay:
        await _replay(name, stop, page, clock, host=host, port=port, tls=tls, opened=opened)
        return
    async with Session.attach(name) as session:
        lock = hold(session.folder, name)
        try:
            manifest = Manifest.model_validate_json((session.folder / MANIFEST).read_bytes())
            if not loopback(host):
                if manifest.plan_login:
                    raise past_loopback(name, "its owner said several agents may run on one")
                await refuse_a_plan_login(session)
                if roles := await asyncio.to_thread(plan_roles, manifest):
                    raise past_loopback(name, f"{', '.join(roles)} would start on one")
            projection = Projection(session.folder, name, name_of(manifest.principal))
            web = Web(session, projection, page, clock, host=host, scheme="https" if tls else "http")
            try:
                await web.listen(host, port, tls=tls)
                os.write(lock, f", at {web.authorities[0]} in process {os.getpid()}".encode())
                if opened is None:
                    note(f"web: session {name} on {web.authorities[0]}. Each link opens once, within ten minutes")
                    note(f"web: view link, which shows the session and acts on nothing: {web.link('view')}")
                    note(f"web: control link, which acts as you: {web.link('control')}")
                else:
                    note(f"web: session {name} on {web.authorities[0]}, opened from your sessions page")
                    opened.set_result(web)
                if tls is None:  # So it serves loopback, which another machine reaches only through a forward.
                    forward(host, web.port)
                await first(follow(session, projection, web.moved, clock, on_loopback=loopback(host)), stop.wait())
            finally:
                await web.stop()
                projection.close()
        finally:
            os.close(lock)
