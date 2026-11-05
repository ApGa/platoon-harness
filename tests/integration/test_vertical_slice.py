"""The vertical slice: a lead adds tasks and spawns workers, who claim, post and report, the lead joins and finishes,
and `until` closes the session. Scripted harnesses, on the real tool plane, with one kind over a real wire process."""

import os
import signal
from pathlib import Path

import pytest

from platoon_harness import Session
from platoon_harness.drivers.process import Record

from ..unit.drivers.support import group_of
from ..unit.runtime.support import harness, journal, of_type, rebuilt_equals_live, until
from .scripts import HARNESSES, manager_worker, wire

pytestmark = pytest.mark.timeout(60)


def lead_harness() -> str:
    return harness(HARNESSES["lead"])


def in_order(found: list[str], *wanted: str) -> bool:
    """Whether `wanted` comes in this order, each after the one before."""
    place = iter(found)
    return all(any(item == want for item in place) for want in wanted)


async def test_the_slice_on_scripted_harnesses(tmp_path: Path):
    team = manager_worker(lead_harness(), harness(HARNESSES["worker"]))

    async with Session.start(team, name="fix-auth", root=tmp_path) as session:
        await session.send("@lead", "Fix the flaky test")
        ending = await session.settled(timeout="30s")

        assert (ending.state, ending.reason) == ("closing", "settled")
        assert {(row["agent"], row["status"]) for row in ending.agents} == {
            ("lead", "finished"),
            ("w1", "finished"),
            ("w2", "finished"),
        }
        assert ending.gaps == ()
        await assert_the_journal(session)
        await assert_the_views(session)
        folder = session.folder

    await rebuilt_equals_live(folder)


async def assert_the_journal(session: Session) -> None:
    events = await journal(session)
    types = [event.type for event in events]

    assert in_order(
        types,
        "runtime.started",
        "session.opened",
        "agent.spawned",  # The lead.
        "message.sent",  # The human's.
        "context.delivered",
        "turn.started",
        "task.added",
        "agent.spawned",
        "wait.registered",
    )
    assert in_order(
        types,
        "task.added",
        "task.claimed",
        "board.posted",
        "task.completed",
        "agent.ended",
        "wait.released",
        "agent.ended",
        "session.closed",
    )
    assert types.count("agent.spawned") == 3
    assert types.count("task.added") == 2
    assert types.count("task.claimed") == 2
    assert types.count("board.posted") == 2
    assert types.count("session.opened") == 1

    claims = [event for event in events if event.type == "task.claimed"]
    assert {event.actor for event in claims} == {"agent:w1", "agent:w2"}
    assert {event.data["task"] for event in claims} == {"1", "2"}

    first = next(event for event in events if event.type == "message.sent")
    assert (first.actor, first.gist) == ("human:you", "Fix the flaky test")
    spawned = [event for event in events if event.type == "agent.spawned" and event.data["parent"]]
    assert {event.data["parent"] for event in spawned} == {"agent:lead"}
    assert all(event.actor == "agent:lead" for event in spawned)
    reports = [event for event in events if event.type == "message.sent" and event.stream == "inbox/lead"]
    assert {event.data["sender"] for event in reports} >= {"@w1", "@w2"}
    assert not [event for event in events if event.type == "op.refused" and event.data["op"] != "agent.report"]


async def assert_the_views(session: Session) -> None:
    tasks = await session.task_list("tasks")
    assert [(task["state"], task["result"]) for task in tasks["tasks"]] == [
        ("done", tasks["tasks"][0]["result"]),
        ("done", tasks["tasks"][1]["result"]),
    ]
    assert {task["result"] for task in tasks["tasks"]} == {"done by w1", "done by w2"}

    found = await session.board_query("notes")
    assert sorted(row["name"] for row in found["results"]) == ["from-w1", "from-w2"]
    assert found["total"] == 2
    got = await session.board_get("notes", "from-w1")
    assert (got["text"], got["version"]) == ("All of it.", 1)

    inbox = await session.read()
    assert [entry["gist"] for entry in inbox["entries"]] == ["The test is fixed."]

    roster = (await anext(session.watch("roster")))["rows"]
    assert {row["agent"]: row["state"] for row in roster} == {"lead": "ended", "w1": "ended", "w2": "ended"}
    attention = await session.attention()
    assert [row["kind"] for row in attention] == ["mention", "mention"]
    assert attention[-1]["gist"] == "lead finished: Both tasks are done."  # A root's report waits for a human.


async def test_a_team_member_over_a_real_wire_process(tmp_path: Path):
    team = manager_worker(lead_harness(), wire("worker"))

    async with Session.start(team, name="wired", root=tmp_path) as session:
        await session.send("@lead", "Fix the flaky test")
        ending = await session.settled(timeout="30s")

        assert ending.reason == "settled"
        await assert_the_journal(session)
        started = [event for event in await of_type(session, "agent.started") if event.agent != "lead"]
        assert {event.data["native"] for event in started} == {"scripted-w1", "scripted-w2"}
        assert all(event.data["declared"]["persistent"] for event in started)
        folder = session.folder

    await rebuilt_equals_live(folder)
    assert list(folder.rglob("proc.json")) == []


async def test_an_owner_s_exit_leaves_no_process_behind(tmp_path: Path):
    team = manager_worker(lead_harness(), wire("hanging"))

    async with Session.start(team, name="left", root=tmp_path) as session:
        await session.send("@lead", "Fix the flaky test")
        await until(lambda: of_type(session, "task.claimed"), session, lambda claims: len(claims) == 2)
        records = [Record.read(path.parent) for path in session.folder.rglob("proc.json")]
        folder = session.folder

    assert len(records) == 2
    assert [record.pid for record in records if record is not None and group_of(record.pid) is not None] == []
    assert list(folder.rglob("proc.json")) == []
    assert (folder / "journal.sqlite").exists()


async def test_a_wire_process_that_is_killed_is_resumed_once_finishes_its_task_and_its_parent_hears(tmp_path: Path):
    """An agent's process is not its identity: `kill -9` of a wire program in a turn cuts that turn off, and the same
    agent comes back on a new process, told so, and finishes the task it held."""
    team = manager_worker(lead_harness(), wire("hanging"))

    async with Session.start(team, name="killed", root=tmp_path) as session:
        await session.send("@lead", "Fix the flaky test")
        group_kill(await running_harness(session, "w1"))
        await until(lambda: of_type(session, "agent.ended"), session)
        ended = {row["agent"]: (row["status"], row["report"]) for row in (await session.ending()).agents}
        lost, resumed = await of_type(session, "turn.lost"), await of_type(session, "agent.resumed")
        told = await until(
            lambda: of_type(session, "message.sent"),
            session,
            lambda sent: any(event.stream == "inbox/lead" and event.data["subject"] == "w1" for event in sent),
        )

    assert [event.agent for event in lost] == ["w1"] == [event.agent for event in resumed]
    assert ended["w1"][0] == "finished" and told[-1].actor == "runtime"


async def running_harness(session: Session, agent: str) -> Record:
    await until(
        lambda: of_type(session, "task.claimed"),
        session,
        lambda claims: any(event.actor == f"agent:{agent}" for event in claims),
    )
    record = Record.read(session.folder / "agents" / agent)
    assert record is not None
    return record


def group_kill(record: Record) -> None:
    assert group_of(record.pid) == record.pid
    os.killpg(record.pid, signal.SIGKILL)
