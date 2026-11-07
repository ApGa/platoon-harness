"""Teams made in a test. A role's harness and a team's extension are names, so a driver or an extension built here is
reached as an attribute of this file."""

import asyncio
import os
import sqlite3
from collections.abc import Awaitable, Callable, Mapping
from pathlib import Path
from typing import Annotated, Any, Literal

import pytest
from pydantic import Field

from platoon_harness import Refused, Session, Team
from platoon_harness.bwrap import Bubblewrap
from platoon_harness.config import Secret
from platoon_harness.drivers import Driver
from platoon_harness.kernel import Args, Extension, Kernel, Txn, op
from platoon_harness.primitives import PRIMITIVES
from platoon_harness.runtime import Admission, AgentOutcome, AgentRef, SpawnRequest
from platoon_harness.testing import FakeModel, ScriptedDriver

from ..kernel.support import dump

REQUIRE_BWRAP = "PLATOON_HARNESS_REQUIRE_BWRAP"
"""Set to 1 where bubblewrap must confine, as CI's test job sets it, so a test that needs it fails there, not skips."""

# How long a wait here may take before it fails as a hang: it bounds no claim, so it is sized for the slowest machine
# that runs the suite, GitHub's runners, whose disks made one git-heavy wait outlast 15 s.
SECONDS = 60.0

_NAMED: dict[str, Callable[[], Driver] | Extension] = {}


def __getattr__(name: str) -> Callable[[], Driver] | Extension:
    try:
        return _NAMED[name]
    except KeyError:
        raise AttributeError(name) from None


def harness(make: Callable[[], Driver]) -> str:
    """The `harness` of a role whose driver `make` builds, one per agent."""
    key = f"driver_{len(_NAMED)}"
    _NAMED[key] = make
    return f"{__name__}:{key}"


def extension(made: Extension) -> str:
    """How a team names `made` among its extensions."""
    key = f"extension_{len(_NAMED)}"
    _NAMED[key] = made
    return f"{__name__}:{key}"


class Vote(Args):
    agent: Annotated[str, Field(pattern=r"^@[a-z]+$", description="The agent whose work it is on, as `@agent`.")]
    choice: Annotated[Literal["yes", "no"], Field(description="Yes or no.")]


@op("ballot.cast", on=lambda a: f"agent/{a.agent[1:]}")
def _cast(txn: Txn, a: Vote) -> dict[str, str]:
    """Cast a vote on an agent's work, kept among that agent's own events."""
    txn.emit("ballot.voted", f"agent/{a.agent[1:]}", gist=f"a vote on {a.agent}'s work: {a.choice}", data=a)
    return {"choice": a.choice}


BALLOT = Extension("ballot", ops=[_cast])
"""An extension as a team's own would be, which no core code knows: one op, which records its event on the agent's
stream, where a client that shows the agent draws it by its gist."""


def scripted(*turns: Any, **options: Any) -> str:
    return harness(lambda: ScriptedDriver(turns, **options))


def solo(*turns: Any, **role: Any) -> Team:
    """One role that starts one agent, `bob`, with nothing to wake it but a message."""
    return Team.model_validate({"roles": {"bob": {"harness": scripted(*turns), **role}}})


class Gateways:
    """An authority that admits each agent through FakeModel acting as its gateway, on a bearer and a backend id of its
    own, so a scripted harness's `AskModel` steps ask it: one model for every agent, or each agent's own by its name, so
    each agent's replies come in its own order however the agents' turns interleave."""

    def __init__(self, models: FakeModel | Mapping[str, FakeModel]) -> None:
        self.models = models

    async def admit(self, spawn: SpawnRequest) -> Admission:
        model = self.models if isinstance(self.models, FakeModel) else self.models[spawn.agent]
        access = model.gateway(f"bearer-of-{spawn.agent}")
        return Admission(token=Secret(f"token-of-{spawn.agent}"), access=access, backend={"agent_id": spawn.agent})

    async def finish(self, agent: AgentRef, outcome: AgentOutcome) -> None:
        return None


async def rebuilt_equals_live(folder: Path) -> None:
    """The acceptance law of views: rebuild them all, and nothing differs."""
    shadows = ("_data", "_idx", "_content", "_docsize", "_config")

    def rows() -> dict[str, list[tuple[Any, ...]]]:
        return {name: found for name, found in dump(folder).items() if not name.endswith(shadows)}

    before = rows()
    kernel = Kernel.open(folder, extensions=PRIMITIVES)
    await kernel.rebuild_all()
    kernel.close()
    assert rows() == before


def boundaries(folder: Path) -> list[int]:
    """Where a journal can be cut: each command ends on one event, and one writer commits them in order."""
    db = sqlite3.connect(folder / "journal.sqlite")
    found = [row[0] for row in db.execute("SELECT seq FROM events WHERE outcome IS NOT NULL ORDER BY seq")]
    db.close()
    return found


def cut(folder: Path, seq: int) -> None:
    """Leave a journal as a crash just past `seq` would, for the journal only: blobs and agent folders stay as they are.
    Law 1 aborts this, so the triggers that enforce it step aside."""
    db = sqlite3.connect(folder / "journal.sqlite")
    triggers = db.execute(
        "SELECT name, sql FROM sqlite_master WHERE type = 'trigger' AND tbl_name = 'events'"
    ).fetchall()
    for name, _ in triggers:
        db.execute(f"DROP TRIGGER {name}")
    db.execute("DELETE FROM events WHERE seq > ?", (seq,))
    for _, sql in triggers:
        db.execute(sql)
    db.commit()
    db.close()


async def until[T](ask: Callable[[], Awaitable[T]], session: Session, holds: Callable[[T], Any] = bool) -> T:
    """Ask again each time the journal moves, until the answer holds."""
    async with asyncio.timeout(SECONDS):
        async for _ in session._moves():
            answer = await ask()
            if holds(answer):
                return answer
    raise AssertionError("the session ended first")


async def state_of(session: Session, agent: str) -> str:
    return (await session.status(agent))["state"]


async def in_state(session: Session, agent: str, *states: str) -> None:
    """Until `agent` exists and is in one of `states`: one its parent has yet to spawn is not there yet."""

    async def state() -> str | None:
        try:
            return await state_of(session, agent)
        except Refused as error:
            if error.refusal.code != "not_found":
                raise
            return None

    await until(state, session, lambda state: state in states)


async def journal(session: Session, match: str | None = None) -> list[Any]:
    return [event async for event in session.events(match=match)]


async def of_type(session: Session, *types: str) -> list[Any]:
    return [event for event in await journal(session) if event.type in types]


async def offers(session: Session) -> list[Any]:
    """What was offered past each launch: handovers, notices and reads, and not the launch's own offer."""
    return [event for event in await of_type(session, "context.offered") if event.data["how"] != "launch"]


def bubblewrap() -> Bubblewrap:
    """Bubblewrap, where it confines here. Elsewhere the test skips, saying why, or fails where `REQUIRE_BWRAP` is 1."""
    isolation = Bubblewrap()
    if (why := isolation.refusal()) is not None:
        reason = f"bubblewrap cannot confine here, so nothing was confined: {why}"
        if os.environ.get(REQUIRE_BWRAP) == "1":
            pytest.fail(f"{reason}, and {REQUIRE_BWRAP}=1 says it must", pytrace=False)
        pytest.skip(reason)
    return isolation
