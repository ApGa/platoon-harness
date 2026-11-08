"""A queue's tasks and a board's entries in the terminal, `/tasks` or Ctrl+T on a queue's or a board's focus, over a
session the test owns: each task's state, claimant and lease deadline, each entry's versions, read again whenever the
channel moves and at no other time, and each act opening its op's form, filled in."""

import asyncio
import contextlib
import time
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from textual.widgets import Input

from platoon_harness import Session, Team
from platoon_harness.kernel import Clock, ManualClock
from platoon_harness.testing import Call, Say, ScriptedDriver
from platoon_harness_cli.tui.app import TerminalUI
from platoon_harness_cli.tui.dialogs import Form
from platoon_harness_cli.tui.rows import Rows
from platoon_harness_cli.tui.tasks import Tasks
from platoon_harness_cli.tui.transcript import Focus, Transcript

from ..runtime.support import harness, in_state, of_type, until
from .support import SECONDS, drawn, workspace
from .test_safe import links
from .test_workspace import HOSTILE, UNSAFE

pytestmark = pytest.mark.timeout(60)


@pytest.fixture
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("PLATOON_HARNESS_HOME", str(tmp_path))
    return tmp_path


def team(*turns: Any) -> Team:
    """`lead` on a scripted harness, a queue `tasks` and a board `notes`, each anyone's to read and write."""
    lead = {"harness": harness(lambda: ScriptedDriver(turns))}
    channels = {
        "tasks": {"kind": "queue", "writers": "all", "readers": "all"},
        "notes": {"kind": "board", "writers": "all", "readers": "all"},
    }
    return Team.model_validate(
        {"roles": {"lead": lead}, "topology": {"edges": {"lead": ["human"]}, "channels": channels}}
    )


CLAIMS = [Call("task_claim", {"queue": "tasks", "task": "1"})]
"""The lead's first turn: it claims task 1."""


@contextlib.asynccontextmanager
async def attached(team: Team, root: Path, clock: Clock | None = None) -> AsyncIterator[tuple[Session, Any, Any]]:
    """A session the test owns, with `lead` up, and the TUI attached to it."""
    async with Session.start(team, name="s", root=root, cwd=root, clock=clock) as owner:
        await in_state(owner, "lead", "idle")
        app = TerminalUI("s")
        async with app.run_test(size=(140, 32)) as pilot:
            await drawn(pilot, lambda text: "@lead" in text)
            yield owner, app, pilot


async def opened(app: Any, pilot: Any, name: str, kind: str) -> str:
    """The view of the channel `name` opened with Ctrl+T on its focus, once its first read is drawn."""
    await workspace(app).show(Focus.of_channel(name, kind))
    await pilot.press("ctrl+t")
    return await drawn(pilot, lambda _: isinstance(app.screen, Tasks) and app.screen.view is not None)


def lease(seconds: float) -> str:
    return time.strftime("%H:%M:%S", time.localtime(seconds))


async def test_a_queue_s_tasks_show_each_state_claimant_and_lease_deadline(root):
    clock = ManualClock(1000.0)
    async with attached(team(CLAIMS), root, clock) as (owner, app, pilot):
        for gist in ("fix the flaky test", "write the docs", "tidy up"):
            await owner.task_add("tasks", gist)
        await owner.task_claim("tasks", task="2")
        await owner.task_complete("tasks", task="2", gist="written")
        await owner.send("@lead", "go")
        await until(lambda: owner.task_list("tasks"), owner, lambda found: found["tasks"][0]["state"] == "claimed")
        await opened(app, pilot, "tasks", "queue")
        text = await drawn(pilot, lambda text: "task 3" in text)

    assert "Tasks on tasks" in text
    assert f"task 1  claimed by @lead, attempt 1, lease until {lease(1000.0 + 1800)}  fix the flaky test" in text
    assert "task 2  done  write the docs  → written" in text
    assert "task 3  open  tidy up" in text
    assert text.count("↳ Claim") == 1 and "Add a task" in text


async def test_the_view_is_read_again_when_its_channel_moves_and_no_timer_decides(root, monkeypatch):
    """The view reads `task.list` as it opens, and again only for a frame that holds an event on one of its tasks'
    streams. A lease the reader's clock is long past stands claimed until the runtime records its expiry, which its own
    timer fires on the session's clock."""
    reads: list[str] = []
    listed = Session.task_list

    async def counted(session: Session, queue: str, **given: Any) -> dict[str, Any]:
        reads.append(queue)
        return await listed(session, queue, **given)

    clock = ManualClock(1000.0)
    async with attached(team(CLAIMS, [Say("heard")]), root, clock) as (owner, app, pilot):
        await owner.task_add("tasks", "fix the flaky test")
        await owner.send("@lead", "go")
        claimed = await until(lambda: owner.task_list("tasks"), owner, lambda found: found["tasks"][0]["owner"])
        monkeypatch.setattr(Session, "task_list", counted)
        transcript, head = workspace(app).query_one(Transcript), await owner.head()
        await drawn(pilot, lambda _: transcript.through >= head)
        await opened(app, pilot, "tasks", "queue")
        first = len(reads)
        await owner.send("@lead", "nothing to do with the queue")
        await until(lambda: of_type(owner, "turn.ended"), owner, lambda ended: len(ended) == 2)
        head = await owner.head()
        unmoved = await drawn(pilot, lambda _: transcript.through >= head)
        quiet = len(reads)
        await asyncio.wait_for(clock.slept_until(claimed["tasks"][0]["lease_until"]), SECONDS)
        clock.advance(1800)
        expired = await drawn(pilot, lambda text: "task 1  open, 1 attempt" in text)

    assert first == 1
    assert f"claimed by @lead, attempt 1, lease until {lease(2800.0)}" in unmoved, "a reader's clock judged the lease"
    assert quiet == first, "an event on no task's stream read the view again"
    assert len(reads) == quiet + 1 and "↳ Claim" in expired


async def test_a_board_s_entries_show_each_version(root):
    async with attached(team(), root) as (owner, app, pilot):
        await owner.board_post("notes", "plan", "first", fields={"step": 1})
        await owner.board_revise("notes", "plan", "second", 1, fields={"step": 2})
        await owner.board_post("notes", "risks", "none yet")
        await opened(app, pilot, "notes", "board")
        text = await drawn(pilot, lambda text: "risks" in text)
        await owner.board_revise("notes", "plan", "third", 2)
        again = await drawn(pilot, lambda text: "plan  3 versions" in text)

    assert "Entries on notes" in text and "Post an entry" in text
    for said in ("plan  2 versions", 'v1  @you  first  {"step":1}', 'v2  @you  second  {"step":2}', "risks  1 version"):
        assert said in text
    assert text.count("↳ Revise") == 2
    assert "v3  @you  third" in again


async def test_a_task_act_opens_its_op_s_form_prefilled(root):
    """Claim opens `task claim`'s form with its queue and task, and once the claim is the person's, the view moves and
    Complete opens `task complete`'s with its fence too."""
    async with attached(team(), root) as (owner, app, pilot):
        await owner.task_add("tasks", "fix the flaky test")
        await opened(app, pilot, "tasks", "queue")
        await drawn(pilot, lambda text: "↳ Claim" in text)
        rows = app.screen.query_one(Rows)
        rows.move_to(next(key for key in rows.keys if key.endswith("#0") and key != "#0"))
        await pilot.press("enter")
        await drawn(pilot, lambda _: isinstance(app.screen, Form))
        claim = {name: app.screen.query_one(f"#field-{name}", Input).value for name in ("queue", "task")}
        await pilot.press("enter", "enter")
        await drawn(pilot, lambda text: "↳ Complete" in text)
        fence = (await owner.task_list("tasks"))["tasks"][0]["fence"]
        await pilot.press("enter")
        await drawn(pilot, lambda _: isinstance(app.screen, Form))
        complete = {name: app.screen.query_one(f"#field-{name}", Input).value for name in ("queue", "task", "fence")}
        await pilot.press("escape")
        await drawn(pilot, lambda _: isinstance(app.screen, Tasks))

    assert claim == {"queue": "tasks", "task": "1"}
    assert complete == {"queue": "tasks", "task": "1", "fence": str(fence)}


async def test_an_act_the_person_cannot_take_now_is_drawn_disabled_saying_why_and_opens_nothing(root):
    """Where the person's grants hold no op, its act says so, and on history every act says the session must be resumed
    first, as the page draws each disabled with its reason; Enter on one says why again and opens no form."""
    async with attached(team(), root) as (owner, app, pilot):
        await owner.task_add("tasks", "fix the flaky test")
        screen = workspace(app)
        screen.forms = [form for form in screen.forms if form.op != "task.claim"]
        await opened(app, pilot, "tasks", "queue")
        ungranted = await drawn(pilot, lambda text: "↳ Claim · your grants hold no task.claim" in text)
    app = TerminalUI("s")
    async with app.run_test(size=(140, 32)) as pilot:
        await drawn(pilot, lambda text: "this is its history" in text)
        await opened(app, pilot, "tasks", "queue")
        on_history = await drawn(pilot, lambda text: "↳ Claim · history" in text)
        rows = app.screen.query_one(Rows)
        rows.move_to(next(key for key in rows.keys if key.endswith("#0") and key != "#0"))
        await pilot.press("enter")
        await drawn(pilot, lambda _: any(notice.message.startswith("Claim: ") for notice in app._notifications))
        told = [notice.message for notice in app._notifications]
        still = app.screen

    assert "Add a task" in ungranted and "Add a task ·" not in ungranted
    assert "Add a task · history: /resume resumes it to act" in on_history
    assert "↳ Claim · history: /resume resumes it to act" in on_history
    assert "Claim: history: /resume resumes it to act" in told and isinstance(still, Tasks)


async def test_a_board_object_reaches_no_renderer_unescaped(root):
    """An entry's gist and fields are whatever an agent wrote, and the view draws them through `SafeText`, each control
    a terminal would act on as its escape, and none of it as markup, so no link is made of it."""
    async with attached(team(), root) as (owner, app, pilot):
        await owner.board_post("notes", "plan", HOSTILE, fields={"note": HOSTILE})
        await opened(app, pilot, "notes", "board")
        text = await drawn(pilot, lambda text: "\\u202eevil" in text)
        drawn_lines = [row.line.plain for row in app.screen.query_one(Rows).rows]
        linked = links(app)

    version = next(line for line in drawn_lines if line.startswith("v1"))
    assert not [char for char in UNSAFE if char in text + version]
    assert version.count("\\u202eevil") == version.count("[@click=app.quit]x[/]") == 2
    assert linked == []
