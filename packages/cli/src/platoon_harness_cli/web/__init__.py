"""The browser client: SwarmChat's page over one session's journal, which `platoon-harness web SESSION` serves. The
command line imports it only then, as it does the terminal UI.

`web` is a guest of the session's runtime, on the owner's control credential, as every client of this user's is. It
starts and resumes nothing, so on history the page does nothing and names the command that resumes it, and leaving it
changes nothing in the session. One `web` serves a session at a time, as its projection has one writer.
"""

import asyncio
import contextlib
import fcntl
import os
import ssl
from pathlib import Path

from platoon_harness import Refused, Session
from platoon_harness.config import Manifest
from platoon_harness.kernel import Clock, Event, Refusal, SystemClock, first, is_held
from platoon_harness.runtime.control import BODY_LIMIT
from platoon_harness.runtime.paths import MANIFEST

from ..exits import Usage
from ..output import note
from .page import load
from .projection import Projection, name_of
from .server import Web

LOOK = 1.0
"""How often a session that is history is looked at for a runtime that took it up again."""
LOCK = "swarmchat.lock"
"""What the one `web` serving a session holds, beside its projection, and where it says it serves."""


async def bodies(session: Session, event: Event) -> dict[str, bytes | Refusal]:
    """What the fold of `event` shows of the bodies it cites: their bytes, or why they could not be read."""
    found: dict[str, bytes | Refusal] = {}
    for ref in Projection.cited(event):
        try:
            found[ref] = await session.get_body(ref, limit=BODY_LIMIT)
        except Refused as refused:
            found[ref] = refused.refusal
    return found


async def follow(session: Session, projection: Projection, moved: asyncio.Condition, clock: Clock) -> None:
    """Fold the journal as it grows, across a runtime that goes and one that comes back, and tell whoever waits on
    `moved`. While no runtime holds the session it looks every `LOOK` seconds for one, or for what one wrote and left,
    which decides nothing."""
    while True:
        with contextlib.suppress(Refused):
            async for event in session.events(projection.through, follow=True):
                projection.fold(event, await bodies(session, event))
                async with moved:
                    moved.notify_all()
        while not is_held(session.folder) and await session.head() <= projection.through:
            await clock.sleep(LOOK)


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
    name: str, stop: asyncio.Event, *, host: str, port: int, tls: ssl.SSLContext | None, clock: Clock | None = None
) -> None:
    """Serve a session's page on `host` and `port` until `stop` is set, and say one view link and one control link on
    stderr. A page file that is not the one pinned refuses this before anything is served."""
    page, clock = load(), clock or SystemClock()
    async with Session.attach(name) as session:
        lock = hold(session.folder, name)
        try:
            person = name_of(Manifest.model_validate_json((session.folder / MANIFEST).read_bytes()).human)
            projection = Projection(session.folder, name, person)
            web = Web(session, projection, page, clock, host=host, scheme="https" if tls else "http")
            try:
                await web.listen(host, port, tls=tls)
                os.write(lock, f", at {web.authorities[0]} in process {os.getpid()}".encode())
                note(f"web: session {name} on {web.authorities[0]}. Each link opens once, within ten minutes")
                note(f"web: view link, which shows the session and acts on nothing: {web.link('view')}")
                note(f"web: control link, which acts as you: {web.link('control')}")
                await first(follow(session, projection, web.moved, clock), stop.wait())
            finally:
                await web.stop()
                projection.close()
        finally:
            os.close(lock)
