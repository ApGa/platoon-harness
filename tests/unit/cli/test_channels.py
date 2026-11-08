"""A queue's tasks and a board's entries, in the words both clients say, over a session the test owns: a task in each
state, held by an agent or by the person, an entry revised, and what moves a view."""

import time
from pathlib import Path

import pytest

from platoon_harness import Session, Team
from platoon_harness.kernel import Event, ManualClock
from platoon_harness.testing import Call, ScriptedDriver
from platoon_harness_cli import channels
from platoon_harness_cli.channels import Act, read

from ..runtime.support import harness, in_state, until

pytestmark = pytest.mark.timeout(60)

QUEUE = {"kind": "queue", "writers": "all", "readers": "all", "max_attempts": 2, "max_inflight": 4}


@pytest.fixture
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("PLATOON_HARNESS_HOME", str(tmp_path))
    return tmp_path


def team() -> Team:
    """`lead`, which claims task 1 when told to, a queue `tasks` and a board `notes`."""
    lead = {"harness": harness(lambda: ScriptedDriver([[Call("task_claim", {"queue": "tasks", "task": "1"})]]))}
    board = {"kind": "board", "writers": "all", "readers": "all"}
    topology = {"edges": {"lead": ["human"]}, "channels": {"tasks": QUEUE, "notes": board}}
    return Team.model_validate({"roles": {"lead": lead}, "topology": topology})


def said(line: channels.Line) -> str:
    return "".join(text for text, _ in line.parts)


async def queued(session: Session) -> None:
    """Six tasks: the lead's, the person's, one done, one failed, one dead after both its attempts, and one open."""
    for gist in ("the lead's", "yours", "done", "failed", "dead", "open"):
        await session.task_add("tasks", gist)
    await session.send("@lead", "go")
    await until(lambda: session.task_list("tasks"), session, lambda found: found["tasks"][0]["state"] == "claimed")
    await session.task_claim("tasks", task="2")
    await session.task_claim("tasks", task="3")
    await session.task_complete("tasks", task="3", gist="it is done")
    for _ in range(2):
        await session.task_claim("tasks", task="5")
        await session.task_fail("tasks", task="5", gist="no luck")
    await session.task_claim("tasks", task="4")
    await session.task_fail("tasks", task="4", gist="not yet")


async def test_each_task_says_its_state_who_claimed_it_which_attempt_and_until_when_its_lease_holds(root):
    """As `task.list` gives it, oldest first, the lease's deadline on the session's clock and never judged by the
    reader's: a claim holds until its expiry is recorded."""
    async with Session.start(team(), name="s", root=root, cwd=root, clock=ManualClock(1000.0)) as session:
        await in_state(session, "lead", "idle")
        await queued(session)
        view = await read(session, "queue/tasks", "you")
        listed = (await session.task_list("tasks"))["tasks"]

    until_ = {task["id"]: time.strftime("%H:%M:%S", time.localtime(task["lease_until"])) for task in listed[:2]}
    assert view.title == "Tasks on tasks"
    assert [said(line) for line in view.lines] == [
        f"task 1  claimed by @lead, attempt 1, lease until {until_['1']}  the lead's",
        f"task 2  claimed by @you, attempt 1, lease until {until_['2']}  yours",
        "task 3  done  done  → it is done",
        "task 4  failed, 1 attempt  failed  → not yet",
        "task 5  dead after 2 attempts  dead  → no luck",
        "task 6  open  open",
    ]
    assert [line.parts[1][1] for line in view.lines] == ["warn", "warn", "good", "bad", "bad", ""]
    assert [line.key for line in view.lines] == [task["ref"] for task in listed]


async def test_a_task_offers_what_the_person_may_do_from_it_each_filled_in_with_what_its_line_knows(root):
    """Claim an open or failed one, complete, fail, release or renew one they hold, by its fence, add a dead one again
    citing it, and nothing on one another holds or one done; and on the queue itself, add a task."""
    async with Session.start(team(), name="s", root=root, cwd=root) as session:
        await in_state(session, "lead", "idle")
        await queued(session)
        view = await read(session, "queue/tasks", "you")
        fence = (await session.task_list("tasks"))["tasks"][1]["fence"]

    held = {"queue": "tasks", "task": "2", "fence": fence}
    assert view.acts == (Act("Add a task", "task.add", {"queue": "tasks"}),)
    assert [line.acts for line in view.lines] == [
        (),
        tuple(Act(label, f"task.{label.lower()}", held) for label in ("Complete", "Fail", "Release", "Renew")),
        (),
        (Act("Claim", "task.claim", {"queue": "tasks", "task": "4"}),),
        (Act("Add it again", "task.add", {"queue": "tasks", "based_on": ["task/tasks/5@1"]}),),
        (Act("Claim", "task.claim", {"queue": "tasks", "task": "6"}),),
    ]


async def test_each_entry_lists_every_version_and_revise_carries_the_version_it_revises_and_its_fields(root):
    async with Session.start(team(), name="s", root=root, cwd=root) as session:
        await in_state(session, "lead", "idle")
        empty = await read(session, "board/notes", "you")
        await session.board_post("notes", "plan", "first", fields={"step": 1})
        await session.board_post("notes", "risks", "none yet")
        await session.board_revise("notes", "plan", "second", 1, fields={"step": 2, "owner": "lead"})
        view = await read(session, "board/notes", "you")

    assert [(line.kind, said(line)) for line in empty.lines] == [("nothing", "No entries yet.")]
    assert view.title == "Entries on notes"
    assert view.acts == (Act("Post an entry", "board.post", {"board": "notes"}),)
    assert [(line.kind, said(line), line.key) for line in view.lines] == [
        ("entry", "plan  2 versions", "board/notes/plan"),
        ("version", 'v1  @you  first  {"step":1}', "board/notes/plan@1"),
        ("version", 'v2  @you  second  {"owner":"lead","step":2}', "board/notes/plan@2"),
        ("entry", "risks  1 version", "board/notes/risks"),
        ("version", "v1  @you  none yet", "board/notes/risks@1"),
    ]
    revise = {"board": "notes", "name": "plan", "expected_version": 2, "fields": {"owner": "lead", "step": 2}}
    assert view.lines[0].acts == (Act("Revise", "board.revise", revise),)
    assert view.lines[3].acts == (
        Act("Revise", "board.revise", {"board": "notes", "name": "risks", "expected_version": 1}),
    )


async def test_past_the_most_a_view_reads_it_says_how_many_more_and_what_reads_them(root, monkeypatch):
    monkeypatch.setattr(channels, "MOST", 40)
    async with Session.start(team(), name="s", root=root, cwd=root) as session:
        await in_state(session, "lead", "idle")
        empty = await read(session, "queue/tasks", "you")
        for number in range(70):
            await session.task_add("tasks", f"task number {number}")
        view = await read(session, "queue/tasks", "you")
        cursor = (await session.task_list("tasks", after=0, limit=32))["cursor"]
        second = (await session.task_list("tasks", after=cursor, limit=32))["cursor"]

    assert [(line.kind, said(line)) for line in empty.lines] == [("nothing", "No tasks yet.")]
    assert [line.kind for line in view.lines] == ["task"] * 64 + ["more"]
    assert (
        said(view.lines[-1])
        == f"6 more past these, which `platoon-harness task list s --queue tasks --after {second}` reads"
    )


async def test_where_a_board_s_view_stops_each_entry_says_it_may_have_more_and_offers_no_revise(root, monkeypatch):
    """Versions come in the order they were written, so where the view stops, a later version of any entry it read may
    lie past it: each says so, and offers no Revise, which would revise a version that may not be the latest."""
    monkeypatch.setattr(channels, "MOST", 32)
    async with Session.start(team(), name="s", root=root, cwd=root) as session:
        await in_state(session, "lead", "idle")
        await session.board_post("notes", "plan", "first")
        for number in range(31):
            await session.board_post("notes", f"note{number}", "a note")
        await session.board_revise("notes", "plan", "second", 1)
        view = await read(session, "board/notes", "you")
        cursor = (await session.board_query("notes", history=True, limit=32))["cursor"]

    command = f"platoon-harness board query s --board notes --history --after {cursor}"
    assert [(line.kind, said(line)) for line in view.lines[:2]] == [
        ("entry", "plan  1 version read before the view stopped, maybe not all, so no Revise is offered"),
        ("version", "v1  @you  first"),
    ]
    assert view.lines[0].parts[1][1] == "warn"
    assert [line.kind for line in view.lines] == ["entry", "version"] * 32 + ["more"]
    assert not any(line.acts for line in view.lines)
    assert said(view.lines[-1]) == f"1 more past these, which `{command}` reads"


def event(type: str, stream: str) -> Event:
    """An event of `type` on `stream`, and nothing else of it said, as `moves` reads nothing else."""
    return Event.model_construct(type=type, stream=stream)


def test_what_moves_a_view_is_an_event_on_its_own_streams_or_for_a_queue_an_agent_s_end():
    assert channels.moves("queue/tasks", event("lease.expired", "task/tasks/1"))
    assert channels.moves("queue/tasks", event("agent.ended", "agent/lead"))
    assert not channels.moves("queue/tasks", event("task.claimed", "task/tasks2/1"))
    assert not channels.moves("queue/tasks", event("message.sent", "queue/tasks"))
    assert channels.moves("board/notes", event("board.revised", "board/notes/plan/a"))
    assert not channels.moves("board/notes", event("agent.ended", "agent/lead"))
    assert not channels.moves("board/notes", event("board.posted", "board/notes2/plan"))
