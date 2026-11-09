"""A replay's budget: a seek on a session of more than 10,000 events, either way, from the nearest checkpoint of its
views, which keeps a seek quick however long the record. Each seek is held to half of what a copy made from nothing
takes to the record's end on the same machine, as a seek that refolds from the start would, and to `SEEK`, five times
the slowest measured on a shared login node, 91 ms, where a copy from nothing took 0.46 s. A seek before the
checkpoints are built copies from the start, which is timed and said. The page's seek, from its control to its
projection holding where the replay went, is held to `PAGE_SEEK` once the page has folded the record that far once,
and its first jump to the end, which folds the whole record into the page, is timed and said."""

import asyncio
import statistics
import time
from pathlib import Path

import pytest

from platoon_harness import Replay, Session, Team
from platoon_harness import session as session_module
from platoon_harness.kernel import SystemClock
from platoon_harness.testing import Say, ScriptedDriver
from platoon_harness_cli.web import serve

from ..unit.runtime.support import harness, in_state, of_type, until
from ..unit.web.support import Browser

pytestmark = [pytest.mark.slow, pytest.mark.timeout(300)]

EVENTS = 10_000
"""How many events the session holds at least."""
SEEK = 0.5
"""The longest a seek may take, in seconds."""
PAGE_SEEK = 1.5
"""The longest a page's seek may take, in seconds, once the page has folded the record that far: five times the
slowest measured on a shared login node, 310 ms, where its first jump to the end took 3 s."""


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
    async with Replay.open("s", root=tmp_path) as cold:
        began = time.perf_counter()
        await cold.seek(cold.total)
        before = time.perf_counter() - began
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
    print(f"and from nothing to the end {from_nothing * 1000:.0f} ms, {before * 1000:.0f} ms before checkpoints")
    assert max(took.values()) < min(SEEK, from_nothing / 2), took


async def test_a_seek_in_the_page_of_a_10000_event_replay_restores_what_the_page_folded_within_its_budget(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("PLATOON_HARNESS_HOME", str(tmp_path))
    await recorded(tmp_path)
    stop, opened = asyncio.Event(), asyncio.get_running_loop().create_future()
    options = {"host": "127.0.0.1", "port": 0, "tls": None, "clock": SystemClock()}
    serving = asyncio.ensure_future(serve("s", stop, **options, opened=opened, replay=True))
    try:
        web = await opened
        assert web.player is not None
        replay, browser = web.player.replay, await Browser(web).opened("control")

        async def jump(at: int) -> float:
            began = time.perf_counter()
            reply = await browser.request("POST", "/x/replay", {"control": "jump", "where": str(at)})
            took = time.perf_counter() - began
            assert reply.json()["at"] == web.projection.through == at, reply.json()
            return took

        first = await jump(replay.total)
        assert replay._building is not None
        await replay._building
        took = {
            name: await jump(at)
            for name, at in (
                ("back to the middle", replay.total // 2),
                ("on to the one before the end", replay.total - 1),
                ("back to the start", 1),
                ("to the end again", replay.total),
                ("back a step", replay.total - 1),
            )
        }
    finally:
        stop.set()
        await serving
    print(", ".join(f"{name} {seconds * 1000:.0f} ms" for name, seconds in took.items()))
    print(f"and the first jump to the end {first * 1000:.0f} ms, over {replay.total:,} events")
    assert max(took.values()) < PAGE_SEEK, took
