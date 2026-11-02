"""Teams made in a test. A role's harness is a name, so a driver built here is reached as an attribute of this file."""

import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from platoon_harness import Session, Team
from platoon_harness.drivers import Driver
from platoon_harness.kernel import Kernel
from platoon_harness.primitives import PRIMITIVES
from platoon_harness.testing import ScriptedDriver

from ..kernel.support import dump

SECONDS = 15.0

_HARNESSES: dict[str, Callable[[], Driver]] = {}


def __getattr__(name: str) -> Callable[[], Driver]:
    try:
        return _HARNESSES[name]
    except KeyError:
        raise AttributeError(name) from None


def harness(make: Callable[[], Driver]) -> str:
    """The `harness` of a role whose driver `make` builds, one per agent."""
    key = f"driver_{len(_HARNESSES)}"
    _HARNESSES[key] = make
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
