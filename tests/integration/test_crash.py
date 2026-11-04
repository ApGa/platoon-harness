"""`kill -9` of a runtime mid-turn, then an owner's resume: architecture section 5.4, on real processes."""

import os
import signal
from pathlib import Path
from typing import Any

import pytest

from platoon_harness import Session
from platoon_harness.drivers.process import Record
from platoon_harness.kernel import Event, Refused
from platoon_harness.runtime.paths import OWNER_TOKEN, read_running

from ..unit.drivers.support import group_of
from ..unit.runtime.support import in_state, of_type, rebuilt_equals_live, until
from .scripts import manager_worker, wire

pytestmark = pytest.mark.timeout(120)

WORKERS = {"w1", "w2"}


def team():
    return manager_worker(
        wire("lead"),
        wire("hanging"),
        stuck={"harness": wire("stuck")},
        fragile={"harness": wire("fragile")},
    )


async def kill_the_runtime(session: Session) -> tuple[int, ...]:
    """SIGKILL the runtime, leaving its harnesses, and wait for the lock it held. Returns their groups."""
    found = read_running(session.folder)
    assert found is not None
    records = [Record.read(path.parent) for path in session.folder.rglob("proc.json")]
    groups = tuple(record.pid for record in records if record is not None)
    os.kill(found.pid, signal.SIGKILL)
    return groups


async def crashed(tmp_path: Path) -> tuple[Session, tuple[int, ...], dict[str, Any]]:
    """A detached session with a turn in flight, a lease held and a handover hanging, killed."""
    guest = await Session.start(team(), name="s", root=tmp_path, detach=True)
    await guest.send("@lead", "Fix the flaky test")
    await until(lambda: of_type(guest, "task.claimed"), guest, lambda claims: len(claims) == 2)
    await in_state(guest, "w1", "running")
    await in_state(guest, "fragile", "idle")
    await in_state(guest, "stuck", "idle")
    await guest.send("@stuck", "this handover will hang")
    await until(
        lambda: of_type(guest, "effect.started"),
        guest,
        lambda found: any(event.data["kind"] == "deliver" and event.agent == "stuck" for event in found),
    )
    sent = (await guest.submit("message.send", key="once", to="@fragile", gist="before the crash")).model_dump()
    return guest, await kill_the_runtime(guest), sent


async def test_a_killed_runtime_is_resumed_with_nothing_lost_and_nothing_done_twice(tmp_path: Path):
    guest, groups, sent = await crashed(tmp_path)

    # With no runtime a guest reads history, and starts nothing.
    assert (await guest.status("@w1"))["state"] == "running"
    with pytest.raises(Refused) as refused:
        await guest.send("@lead", "are you there?")
    assert 'Session.resume("s")' in str(refused.value)
    old = (guest.folder / OWNER_TOKEN).read_text()

    async with Session.resume("s", root=tmp_path) as owner:
        await assert_what_a_crash_leaves(owner, guest, groups, sent)
        with pytest.raises(Refused):
            owner._runtime.kernel.authenticate(old)
        ending = await settled_after_the_crash(owner)
        folder = owner.folder

    await guest.leave()
    assert ending.reason == "agent_failed"  # `fragile` could not come back.
    assert {"agent": "w1", "what": "crash_window", "plane": "control", "count": 1} in ending.gaps
    await rebuilt_equals_live(folder)
    assert list(folder.rglob("proc.json")) == []


async def assert_what_a_crash_leaves(
    owner: Session, guest: Session, groups: tuple[int, ...], sent: dict[str, Any]
) -> None:
    assert [group for group in groups if group_of(group) is not None] == []
    events = [event async for event in owner.events()]
    types = [event.type for event in events]

    assert types.count("runtime.started") == 2

    # The turn in flight is lost with a gap, and was shown until its agent was back in a turn.
    lost = {event.agent: event for event in events if event.type == "turn.lost"}
    gaps = {event.agent: event for event in events if event.type == "gap.recorded"}
    assert lost["w1"].data is None
    assert gaps["w1"].data["what"] == "crash_window" and gaps["w1"].seq < lost["w1"].seq
    attention = await owner._ask("view.watch", name="attention", after=0)
    assert "turn/w1" in {row["id"] for row in attention["rows"]} | {*attention["removed"]}

    # Nothing logical happened twice: each task claimed once, and the lease survives the crash.
    assert types.count("task.claimed") == 2
    tasks = (await owner.task_list("tasks"))["tasks"]
    assert {task["state"] for task in tasks} == {"claimed"}
    assert {task["owner"] for task in tasks} == {"@w1", "@w2"}

    # A guest's retry under its key is one operation, answered from the journal.
    retried = await guest.submit("message.send", key="once", to="@fragile", gist="before the crash")
    assert retried.seq == sent["seq"]
    assert len([event for event in await of_type(owner, "message.sent") if event.gist == "before the crash"]) == 1

    # An effect nobody can vouch for was surfaced, then settled by its policy: at-least-once, with a new input.
    assert uncertain_kinds(events) >= {"deliver"}
    await until(lambda: of_type(owner, "turn.started"), owner, lambda found: stuck_turn(found))
    offered = await of_type(owner, "context.offered")
    offers = [event for event in offered if event.agent == "stuck" and event.data["how"] != "launch"]
    assert len(offers) == 2
    assert [item["ref"] for item in offers[0].data["items"]] == [item["ref"] for item in offers[1].data["items"]]
    assert offers[0].seq != offers[1].seq

    # A harness that cannot resume is lost, with a gap, through the normal ended transition.
    assert (await owner.status("@fragile"))["status"] == "lost"
    assert any(row["agent"] == "fragile" and row["what"] == "crash_window" for row in (await owner.ending()).gaps)

    # What could resume did, on a fresh credential.
    resumed = {event.agent for event in await of_type(owner, "agent.resumed")}
    assert {"lead", "w1", "w2", "stuck"} <= resumed


async def every_task_done(owner: Session) -> None:
    await until(
        lambda: owner.task_list("tasks"), owner, lambda listed: {t["state"] for t in listed["tasks"]} == {"done"}
    )


def uncertain_kinds(events: list[Event]) -> set[str]:
    return {event.data["kind"] for event in events if event.type == "effect.uncertain"}


def stuck_turn(found: list[Event]) -> bool:
    return any(event.agent == "stuck" for event in found)


async def settled_after_the_crash(owner: Session) -> Any:
    """The workers are told their turns were cut off, come back to their leases, and the work ends as it should have.
    Nobody has to say anything."""
    await every_task_done(owner)
    return await owner.settled(timeout="30s")


async def told(session: Session) -> set[str]:
    """Who has been told a turn was cut off."""
    sent = await of_type(session, "message.sent")
    return {event.stream.removeprefix("inbox/") for event in sent if "cut off" in event.gist}


@pytest.mark.slow
async def test_a_second_crash_during_recovery_loses_nothing_more(tmp_path: Path):
    guest, _, sent = await crashed(tmp_path)
    await guest.status()
    await guest.leave()

    first = await Session.resume("s", root=tmp_path, detach=True)
    await until(lambda: told(first), first, lambda names: names >= WORKERS)
    await kill_the_runtime(first)
    await first.status()
    await first.leave()

    async with Session.resume("s", root=tmp_path) as owner:
        await every_task_done(owner)
        assert len(await of_type(owner, "runtime.started")) == 3
        assert len(await of_type(owner, "task.claimed")) == 2
        folder = owner.folder
    await rebuilt_equals_live(folder)
    assert sent["seq"] > 0
