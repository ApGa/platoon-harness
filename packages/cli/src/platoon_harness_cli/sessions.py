"""Sessions as folders: which there are, how one stands, and the owner's stop from another shell."""

import asyncio
import json
import os
import signal
from typing import Any

from platoon_harness import Refused, Session
from platoon_harness.kernel import Kernel, is_held
from platoon_harness.primitives import PRIMITIVES
from platoon_harness.runtime.paths import find_root, listing, read_running, session_folder

from .ops import command_line
from .output import note, refused, safe, say, shown


async def list_sessions(*, json: bool = False) -> int:
    """List the sessions under the state root, from their folders.

    Each has its name, whether a runtime holds it now, and its state, which is unknown for one whose journal cannot be
    read, and stderr says why.

    For example:

        platoon-harness session list
        platoon-harness session list --json | jq -r '.[] | select(.live) | .name'

    Parameters
    ----------
    json
        Say it as JSON.
    """
    rows = []
    for found in listing(find_root()):
        state = None
        try:
            async with Session.attach(found.name, view=True) as attached:
                state = (await attached.status())["state"]
        except Refused as error:
            note(f"session {found.name}: {refused(error.refusal)}")
        rows.append({"name": found.name, "live": found.live, "state": state})
    if json:
        say(shown(rows))
        return 0
    for row in rows:
        say(safe(f"{row['name']:<32} {'live' if row['live'] else '-':<5} {row['state'] or 'unknown'}"))
    return 0


async def show(session: str, /) -> int:
    """Say how a session stands: who is working, on what, what is blocked, and where you must act.

    Each place you must act comes with the command that would settle it. `session status`, `view watch` and `attention
    list` say the same as JSON.

    For example:

        platoon-harness session show fix-auth

    Parameters
    ----------
    session
        A session, by name.
    """
    async with Session.attach(session, view=True) as attached:
        status = await attached.status()
        roster = (await anext(attached.watch("roster")))["rows"]
        attention = await attached.attention()
    live = "live" if is_held(attached.folder) else "no runtime"
    lines = [f"{session}  {live}, {status['state']}, until {status['until']}"]
    for row in roster:
        harness = row["harness"] if isinstance(row["harness"], str) else row["harness"]["mode"]
        why = f"  {_compact(row['why'])}" if row["why"] else ""
        doing = " ".join((row["activity"] or "").split())
        lines.append(f"  @{row['agent']:<15} {row['role']:<10} {harness:<8} {row['state']:<8} {doing}{why}")
    for row in attention:
        lines.append(f"  needs you: {row['kind']} {row['id']}, {row['gist']}")
        lines += [
            f"    {action['label']}: {command_line(session, action['op'], action['args'])}" for action in row["actions"]
        ]
    say(safe("\n".join(lines)))
    return 0


async def refold(session: str, /) -> int:
    """Bring a session's views up to its journal while no runtime holds it, as a runtime does as it opens, writing no
    event, so that its history and the provenance queries answer again after an upgrade changed a view.

    Refused `unavailable` while a runtime holds the session, whose views are current.

    For example:

        platoon-harness session refold fix-auth

    Parameters
    ----------
    session
        A session, by name.
    """
    folder = session_folder(find_root(), session)
    if not (folder / "journal.sqlite").exists():
        raise Refused("unavailable", f"session {session} never opened, so it has no views")
    await asyncio.to_thread(lambda: Kernel.open(folder, extensions=PRIMITIVES).close())
    note(f"session {session}'s views are up to its journal")
    return 0


def _compact(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"))


async def stop(session: str, /) -> int:
    """Stop a session's runtime as its owner would, keeping the session resumable.

    Turns are interrupted and harnesses end. It sends SIGTERM to the runtime, which `run`, `serve`, `session resume` and
    a detached runtime take as the owner's stop, and follows the session until the runtime has let go.

    For example:

        platoon-harness session stop fix-auth
        platoon-harness session resume fix-auth

    Parameters
    ----------
    session
        A session, by name.
    """
    async with Session.attach(session, view=True) as attached:
        await ask_to_stop(attached)
        async for _ in attached.events(await attached.head(), follow=True):
            pass
    note(f"stopped session {session}: `platoon-harness session resume {session}` restarts it")
    return 0


async def ask_to_stop(attached: Session) -> None:
    """Send a session's runtime the owner's stop, SIGTERM, if it is the one the journal last saw start. It returns at
    once: the runtime lets go of the session once its shutdown is done."""
    incarnation = max([event.version async for event in attached.events(match="runtime")], default=None)
    running = read_running(attached.folder)
    if not is_held(attached.folder) or running is None:
        raise Refused("conflict", f"no runtime holds session {attached.name}: it has stopped")
    if running.incarnation != incarnation:
        raise Refused("busy", f"the runtime of session {attached.name} is starting: try again once it is up")
    os.kill(running.pid, signal.SIGTERM)
