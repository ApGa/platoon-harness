"""The sample extension as a person installs it, run on the Python of an environment that holds its wheel beside a
rival's, as `installed_ballot.py <case>`: each case prints what it found as one JSON object. It imports only what that
environment holds, and its roles' harnesses are attributes of this file, named as `__main__:<attribute>`."""

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

from platoon_harness import ConfigError, Session, Team
from platoon_harness.extensions import EXTENSIONS, load
from platoon_harness.kernel import Kernel
from platoon_harness.team import Command
from platoon_harness.testing import Call, ScriptedDriver, check_extension

SAMPLE = "ballot@0.1.0"
"""The sample, pinned past its rival, which registers the same name at 1.0.0."""
CHECKER = Command(command=["sh", "-c", "ph ballot.cast --agent @author --choice no"])
"""A one-shot harness whose shell casts its vote through `ph`."""


def author() -> ScriptedDriver:
    """The agent whose work is voted on, which does nothing of its own."""
    return ScriptedDriver([])


def reviewer() -> ScriptedDriver:
    """An agent whose one turn casts its vote through MCP."""
    return ScriptedDriver([[Call("ballot_cast", {"agent": "@author", "choice": "yes"})]])


def alone(*extensions: str) -> Team:
    """The author alone, in a team that names `extensions`."""
    return Team.model_validate({"extensions": extensions, "roles": {"author": {"harness": "__main__:author"}}})


def voters() -> Team:
    """The author, the reviewer, and the checker, whom the session spawns, each voter paired with the author by the
    sample's preset, in a team that names the sample."""
    roles = {
        "author": {"harness": "__main__:author"},
        "reviewer": {"harness": "__main__:reviewer"},
        "checker": {"harness": CHECKER, "count": 0},
    }
    pairs = [{"author": "author", "reviewer": "reviewer"}, {"author": "author", "reviewer": "checker"}]
    return Team.model_validate({"extensions": [SAMPLE], "roles": roles, "topology": {"pair-review": pairs}})


def imported() -> list[str]:
    """Which of the sample and its rival this process has imported."""
    return sorted(name for name in sys.modules if name in ("ballot", "rival"))


async def held(session: Session) -> list[str]:
    """The ops of the sample's namespace that `ops.list` gives."""
    return [entry["name"] for entry in await session.ops() if entry["name"].startswith("ballot.")]


async def unnamed() -> dict[str, Any]:
    """A session whose team names no extension, then one whose team names the sample."""
    async with Session.start(alone()) as session:
        ops = await held(session)
        outcome = await session.submit("ballot.cast", agent="@author", choice="yes")
    refused = None if outcome.refusal is None else outcome.refusal.code
    found: dict[str, Any] = {"unnamed": {"ops": ops, "refused": refused, "imported": imported()}}
    async with Session.start(alone(SAMPLE)) as session:
        found["named"] = {"ops": await held(session), "imported": imported()}
    return found


async def rival() -> dict[str, Any]:
    """A team that names `ballot`, which the sample and its rival both register, then one that pins the rival's
    version."""
    try:
        async with Session.start(alone("ballot")):
            refused = None
    except ConfigError as error:
        refused = str(error)
    found: dict[str, Any] = {"refused": refused, "imported": imported()}
    async with Session.start(alone("ballot@1")) as session:
        found["pinned"] = {"ops": await held(session), "imported": imported()}
    return found


async def voted() -> dict[str, Any]:
    """Your vote through the SDK, and a second one, then the reviewer's through MCP in its turn and the checker's
    through `ph` in its shell, read once the session settles."""
    async with Session.start(voters()) as session:
        first = await session.submit("ballot.cast", agent="@author", choice="yes")
        again = await session.submit("ballot.cast", agent="@author", choice="no")
        await session.send("@reviewer", "vote on the author's work")
        await session.spawn("checker", "checker", "vote on the author's work")
        ending = await session.settled(timeout="60s")
        events = [event async for event in session.events()]
    return {
        "session": session.name,
        "ending": ending.reason,
        "sdk": [first.result, None if again.refusal is None else again.refusal.code],
        "votes": sorted([event.actor, event.stream, event.gist] for event in events if event.type == "ballot.voted"),
        "checker": [event.gist for event in events if event.type == "item.recorded" and event.agent == "checker"],
        "imported": imported(),
    }


async def command(*words: str) -> dict[str, Any]:
    """What this environment's `platoon-harness` did with `words`, as a terminal 200 columns wide shows it."""
    process = await asyncio.create_subprocess_exec(
        Path(sys.executable).with_name("platoon-harness"),
        *words,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env={**os.environ, "COLUMNS": "200"},
    )
    out, err = await process.communicate()
    return {"code": process.returncode, "out": out.decode(), "err": err.decode()}


async def commanded() -> dict[str, Any]:
    """The help that lists the sample, then your vote as a command on a session whose team names it, twice, and on one
    whose team names no extension, each a process of its own while this one owns both sessions."""
    vote = ("--agent", "@author", "--choice", "yes")
    async with Session.start(alone(SAMPLE), name="named") as named, Session.start(alone(), name="plain"):
        listed = await command("--help")
        ran = [await command("ballot", "cast", session, *vote) for session in ("named", "named", "plain")]
        events = [event async for event in named.events()]
    return {
        "help": listed,
        "commands": ran,
        "votes": [[event.actor, event.stream, event.gist] for event in events if event.type == "ballot.voted"],
    }


async def checked() -> dict[str, Any]:
    """`check_extension` on the sample as installed, with a vote on each of two agents' work cast on its kernel."""
    refused: list[str] = []

    async def vote(kernel: Kernel) -> None:
        for agent, choice in (("author", "yes"), ("reviewer", "no")):
            for name, args in (
                ("principal.add", {"id": f"agent:{agent}", "role": agent}),
                ("ballot.cast", {"agent": f"@{agent}", "choice": choice}),
            ):
                if (outcome := await kernel.submit(kernel.runtime, name, args)).refusal is not None:
                    refused.append(f"{name}: {outcome.refusal.detail}")

    result = await check_extension(load(EXTENSIONS, SAMPLE), folder=Path.cwd() / "check", scenario=vote)
    checks = {check.name: check.state for check in result.checks}
    return {"checks": checks, "unchecked": list(result.unchecked), "refused": refused}


CASES = {"unnamed": unnamed, "rival": rival, "voted": voted, "commanded": commanded, "checked": checked}

if __name__ == "__main__":
    print(json.dumps(asyncio.run(CASES[sys.argv[1]]())))
