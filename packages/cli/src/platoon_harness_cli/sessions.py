"""Sessions as folders: which there are, how one stands, and the owner's stop from another shell."""

import asyncio
import json
import os
import signal
import time
from typing import Any

from platoon_harness import Refused, Session
from platoon_harness.kernel import is_held
from platoon_harness.runtime import GRACE
from platoon_harness.runtime.paths import find_root, listing, read_running, session_folder

from .ops import command_line
from .output import note, safe, say, shown

_STOP_SECONDS = GRACE + 30.0
_FIRST_PAUSE = 0.01
_LONGEST_PAUSE = 0.5


async def list_sessions(*, json: bool = False) -> int:
    """List the sessions under the state root, from their folders.

    Each has its name, whether a runtime holds it now, and its state.

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
        async with Session.attach(found.name, view=True) as attached:
            state = (await attached.status())["state"]
        rows.append({"name": found.name, "live": found.live, "state": state})
    if json:
        say(shown(rows))
        return 0
    for row in rows:
        say(safe(f"{row['name']:<32} {'live' if row['live'] else '-':<5} {row['state']}"))
    return 0


async def show(session: str, /, *, json: bool = False) -> int:
    """Say how a session stands: who is working, on what, what is blocked, and where you must act.

    Each place you must act comes with the command that would settle it.

    For example:

        platoon-harness session show fix-auth

    Parameters
    ----------
    session
        A session, by name.
    json
        Say it as JSON: `session.status`, the `roster` and `attention` rows.
    """
    async with Session.attach(session, view=True) as attached:
        status = await attached.status()
        watched = await attached.submit("view.watch", name="roster")
        attention = await attached.attention()
    if watched.refusal is not None:
        raise Refused.of(watched.refusal)
    roster = watched.result["rows"]
    live = is_held(attached.folder)
    if json:
        say(shown({"name": session, "live": live, "status": status, "roster": roster, "attention": attention}))
        return 0
    lines = [f"{session}  {'live' if live else 'no runtime'}, {status['state']}, until {status['until']}"]
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


def _compact(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"))


async def stop(session: str, /) -> int:
    """Stop a session's runtime as its owner would, keeping the session resumable.

    Turns are interrupted and harnesses end. It sends SIGTERM to the runtime, which `run`, `serve`, `session resume` and
    a detached runtime take as the owner's stop, and waits until it has let go.

    For example:

        platoon-harness session stop fix-auth
        platoon-harness session resume fix-auth

    Parameters
    ----------
    session
        A session, by name.
    """
    folder = session_folder(find_root(), session)
    async with Session.attach(session, view=True) as attached:
        incarnation = max([event.version async for event in attached.events(match="runtime")], default=None)
    running = read_running(folder)
    if not is_held(folder) or running is None:
        raise Refused("conflict", f"no runtime holds session {session}: it has stopped")
    if running.incarnation != incarnation:
        raise Refused("busy", f"the runtime of session {session} is starting: try again once it is up")
    os.kill(running.pid, signal.SIGTERM)
    deadline, pause = time.monotonic() + _STOP_SECONDS, _FIRST_PAUSE
    while is_held(folder):
        if time.monotonic() > deadline:
            raise Refused("unavailable", f"the runtime of session {session} has not let go after SIGTERM")
        await asyncio.sleep(pause)
        pause = min(pause * 2, _LONGEST_PAUSE)
    note(f"stopped session {session}: `platoon-harness session resume {session}` restarts it")
    return 0
