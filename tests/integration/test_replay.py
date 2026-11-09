"""A replay's budget: a seek on a session of more than 10,000 events, either way, from the nearest checkpoint of its
views, which keeps a seek quick however long the record. Each seek is held to half of what a copy made from nothing
takes to the record's end on the same machine, as a seek that refolds from the start would, and to `SEEK`, five times
the slowest measured on a shared login node, 91 ms, where a copy from nothing took 0.46 s."""

import asyncio
import statistics
import time
from pathlib import Path

import pytest

from platoon_harness import Replay, Session, Team
from platoon_harness import session as session_module
from platoon_harness.testing import Say, ScriptedDriver

from ..unit.runtime.support import harness, in_state, of_type, until

pytestmark = [pytest.mark.slow, pytest.mark.timeout(300)]

EVENTS = 10_000
"""How many events the session holds at least."""
SEEK = 0.5
"""The longest a seek may take, in seconds."""


async def recorded(root: Path) -> int:
    """A closed session of more than `EVENTS` events: a person's notes on a topic its one agent pulls, and twenty
    messages it answers, each a turn of its own; and its head."""
    turns = [[Say(f"heard {at}")] for at in range(20)]
    topic = {"kind": "topic", "writers": "human", "readers": "role:lead", "delivery": "pull"}
    roles = {"lead": {"harness": harness(lambda: ScriptedDriver(turns))}}
    topology = {"edges": {"lead": ["human"]}, "channels": {"notes": topic}}
    team = Team.model_validate({"roles": roles, "topology": topology})
    async with Session.start(team, name="s", root=root, cwd=root) as session:
        await in_state(session, "lead", "idle")
        for at in range(20):
            await session.send("@lead", f"message {at}")
            await until(lambda: of_type(session, "turn.ended"), session, lambda ended, at=at: len(ended) == at + 1)
        while (head := await session.head()) < EVENTS:
            await asyncio.gather(*(session.send("#notes", f"note {head + at}") for at in range(32)))
    return head


async def test_a_seek_on_a_10000_event_session_goes_from_the_nearest_checkpoint_within_its_budget(
    tmp_path, monkeypatch
):
    await recorded(tmp_path)
    async with Replay.open("s", root=tmp_path) as replay:
        assert replay.total > EVENTS
        building = replay._building
        assert building is not None
        await building
        assert replay._checkpoints, "no checkpoint was kept"
        took: dict[str, float] = {}
        for name, at in (
            ("to the end", replay.total),
            ("back to the middle", replay.total // 2),
            ("on to the one before the end", replay.total - 1),
            ("back to the start", 1),
            ("on a step", 2),
            ("to the end again", replay.total),
        ):
            began = time.perf_counter()
            await replay.seek(at)
            took[name] = time.perf_counter() - began
            assert await replay.session.head() == at
    monkeypatch.setattr(session_module, "CHECKPOINTS", 1)
    async with Replay.open("s", root=tmp_path) as whole:
        began = time.perf_counter()
        await whole.seek(whole.total)
        from_nothing = time.perf_counter() - began
    print(", ".join(f"{name} {seconds * 1000:.0f} ms" for name, seconds in took.items()))
    print(f"median {statistics.median(took.values()) * 1000:.0f} ms over {replay.total:,} events, ", end="")
    print(f"and from nothing to the end {from_nothing * 1000:.0f} ms")
    assert max(took.values()) < min(SEEK, from_nothing / 2), took
