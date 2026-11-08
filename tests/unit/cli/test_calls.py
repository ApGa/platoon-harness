"""The join both clients draw a spawn by, over what a kernel records as a session would: a lead's tool items, as its
harness reports them, and the spawns it makes, each under the anchor its harness gave the call, or under none."""

from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from platoon_harness.kernel import Event, Kernel
from platoon_harness_cli.calls import UNJOINED, Join

from ..kernel.support import events_of, result_of
from ..primitives.support import agent, report, spawn, start_turn
from ..primitives.test_provenance import tool
from .test_provenance import opened


@pytest.fixture
async def kernel(tmp_path: Path) -> AsyncIterator[Kernel]:
    found = await opened(tmp_path / "session")
    for name in ("lead", "other"):
        await spawn(found, name, role="lead")
        await start_turn(found, name)
    yield found
    found.close()


def last(kernel: Kernel) -> Event:
    return events_of(kernel)[-1]


async def called(kernel: Kernel, id: str, phase: str = "started", by: str = "lead") -> Event:
    """A tool item of the call `id`, as its agent's harness reports it."""
    await report(kernel, by, "item", kind="tool", phase=phase, gist="agent_spawn", native_id=id)
    return last(kernel)


async def spawned(kernel: Kernel, name: str, native: dict[str, str] | None, by: str = "lead") -> Event:
    """A child its spawner made under the call its anchor, `native`, names, or under none."""
    args = {"name": name, "child_role": "worker", "goal": f"be {name}"}
    result_of(await kernel.submit(agent(by), "agent.spawn", args, native=native))
    return next(event for event in events_of(kernel) if event.type == "agent.spawned" and event.data["name"] == name)


def joined(*events: Event) -> Join[int]:
    """A join of `events`, each held by its seq."""
    join: Join[int] = Join()
    for event in events:
        join.take(event, event.seq)
    return join


async def test_a_spawn_joins_the_call_whose_id_its_anchor_holds(kernel):
    """By its spawner's own tool item, the first of the call's held, and never another agent's under the same id."""
    first, second = await called(kernel, "toolu_1"), await called(kernel, "toolu_2")
    child = await spawned(kernel, "w", tool("toolu_2"))
    ended = await called(kernel, "toolu_2", phase="completed")
    theirs = await spawned(kernel, "x", tool("toolu_1"), by="other")

    join = joined(first, second, child, ended, theirs)

    assert join.call_of(child.seq) == second.seq
    assert join.spawns_of(second.seq) == [child.seq] and join.spawns_of(first.seq) == join.spawns_of(ended.seq) == []
    assert join.call_of(theirs.seq) is None


async def test_a_spawn_no_item_holds_joins_no_known_call_and_says_so(kernel):
    """OpenHands' calls come through the shim and an `exec` harness's through `ph`, each under an id of its own, which
    no item holds, and a call can come with no id at all, as a scripted `Call` step's does."""
    item = await called(kernel, "toolu_1")
    shimmed = await spawned(kernel, "oh", {"platoon-harness/callId": "9f1c2e"})
    unnamed = await spawned(kernel, "nameless", None)

    join = joined(item, shimmed, unnamed)

    assert unnamed.native == {}
    assert join.call_of(shimmed.seq) is None and join.call_of(unnamed.seq) is None
    assert join.spawns_of(item.seq) == []
    assert UNJOINED == "joins no known call"


async def test_a_spawn_recorded_before_its_call_s_item_joins_it_once_the_item_comes(kernel):
    """A harness's report of its item can land after the command it made under that call."""
    child = await spawned(kernel, "w", tool("toolu_1"))
    join = joined(child)
    before = join.call_of(child.seq)

    item = await called(kernel, "toolu_1")
    join.take(item, item.seq)

    assert before is None
    assert join.call_of(child.seq) == item.seq and join.spawns_of(item.seq) == [child.seq]
