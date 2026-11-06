"""Teams made in a test. A role's harness and a team's extension are names, so a driver or an extension built here is
reached as an attribute of this file."""

import asyncio
import sqlite3
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from platoon_harness import Session, Team
from platoon_harness.drivers import Driver
from platoon_harness.kernel import Extension, Kernel
from platoon_harness.primitives import PRIMITIVES
from platoon_harness.testing import ScriptedDriver

from ..kernel.support import dump

SECONDS = 15.0

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


def scripted(*turns: Any, **options: Any) -> str:
    return harness(lambda: ScriptedDriver(turns, **options))


def solo(*turns: Any, **role: Any) -> Team:
    """One role that starts one agent, `bob`, with nothing to wake it but a message."""
    return Team.model_validate({"roles": {"bob": {"harness": scripted(*turns), **role}}})


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
    await until(lambda: state_of(session, agent), session, lambda state: state in states)


async def journal(session: Session, match: str | None = None) -> list[Any]:
    return [event async for event in session.events(match=match)]


async def of_type(session: Session, *types: str) -> list[Any]:
    return [event for event in await journal(session) if event.type in types]


async def offers(session: Session) -> list[Any]:
    """What was offered past each launch: handovers, notices and reads, and not the launch's own offer."""
    return [event for event in await of_type(session, "context.offered") if event.data["how"] != "launch"]
