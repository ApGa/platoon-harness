"""The terminal's team editor, from the sessions screen: the project's team as the shared module's fields, by
section, each problem under its field, beside `team show`'s sentences and the diff a save makes, in the words the
browser's editor says; each change checked as it is made, only the newest check drawn; Save asking trust as the browser
does and refused over a file changed since it was read; entries added and removed; each disabled act saying why; a click
for each act; every width from 52 columns to 120; and what the file holds drawn as text."""

import asyncio
import threading
from pathlib import Path

import pytest
from textual.content import Content
from textual.pilot import Pilot
from textual.widgets import Static

from platoon_harness.config import PROJECT_FILE
from platoon_harness_cli import team_editor
from platoon_harness_cli.team_editor import SAVING, Edit, Field, Harness
from platoon_harness_cli.tui.app import TerminalUI
from platoon_harness_cli.tui.dialogs import Confirm
from platoon_harness_cli.tui.editor import ESCAPED, LEAVE, Choices, FieldForm, Fields, TeamEditor, rows_of
from platoon_harness_cli.tui.keymap import footer, keys
from platoon_harness_cli.tui.rows import Rows
from platoon_harness_cli.tui.sessions import Sessions
from platoon_harness_cli.web import sessions as page

from ...integration.cli import solo
from .support import SECONDS, click_on, drawn, screen_text
from .test_workspace import UNSAFE

HARNESSES = (Harness("claude", "not on PATH", ()),)
"""What `doctor` finds of this machine's harnesses, as the editor is told it."""
TEAM = f"# Bob, alone.\n{solo('saying')}"
WIDTHS = (52, 70, 99, 100, 120)


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A project folder of its own, which is the home too, with no harness on PATH, a config and a root of its own,
    holding Bob's team, and this machine's harnesses as the editor is told them."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    monkeypatch.setenv("PLATOON_HARNESS_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.delenv("PLATOON_HARNESS_CONFIG", raising=False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(team_editor, "harnesses", lambda: HARNESSES)
    (tmp_path / PROJECT_FILE).write_text(TEAM)
    return tmp_path


def editor(app: TerminalUI) -> TeamEditor:
    screen = app.screen
    assert isinstance(screen, TeamEditor), type(screen)
    return screen


def checked(app: TerminalUI) -> bool:
    """Whether the editor shows, with the newest check it asked for drawn and nothing it set going under way."""
    screen = app.screen
    return (
        isinstance(screen, TeamEditor)
        and screen.found is not None
        and screen._asked == screen._drawn
        and all(worker.is_finished for worker in app.workers if worker.node is screen)
    )


def told(app: TerminalUI) -> list[str]:
    return [str(notice.message) for notice in app._notifications]


async def opened(pilot: Pilot) -> TeamEditor:
    """The editor, opened from the sessions screen by its key, its first check drawn."""
    await drawn(pilot, lambda text: "sessions under" in text)
    await pilot.press("e")
    await drawn(pilot, lambda _: checked(pilot.app))
    return editor(pilot.app)


async def typing(pilot: Pilot, where: str, *typed: str) -> None:
    """Change the field at `where` from its form, typed over what it holds."""
    pilot.app.screen.query_one(Fields).move_to(f"field:{where}")
    await pilot.press("enter")
    await drawn(pilot, lambda _: isinstance(pilot.app.screen, FieldForm))
    await pilot.press("ctrl+u", *typed, "enter")
    await drawn(pilot, lambda _: isinstance(pilot.app.screen, TeamEditor))


async def setting(pilot: Pilot, where: str, *typed: str) -> None:
    """Change the field at `where` from its form, and wait for its check."""
    await typing(pilot, where, *typed)
    await drawn(pilot, lambda _: checked(pilot.app))


async def choosing(pilot: Pilot, where: str, value: str) -> None:
    """Choose `value` for the field at `where` in its form, and wait for its check."""
    pilot.app.screen.query_one(Fields).move_to(f"field:{where}")
    await pilot.press("enter")
    await drawn(pilot, lambda _: isinstance(pilot.app.screen, FieldForm))
    pilot.app.screen.query_one(Choices).move_to(value)
    await pilot.press("enter")
    await drawn(pilot, lambda _: checked(pilot.app))


def words(text: str) -> str:
    """Text as a person reads it, however it is wrapped or spaced."""
    return " ".join(text.split())


def row_text(screen: TeamEditor, key: str) -> str:
    """The words of a row of the fields, and of the rows that go on from it, as one line."""
    return words(" ".join(row.line.plain for row in screen.query_one(Fields).rows if row.key == key))


def diff_of(screen: TeamEditor) -> str:
    return screen.found.diff if screen.found is not None else ""


def plain(rows: Rows) -> str:
    return words(" ".join(row.line.plain for row in rows.rows))


async def click_row(pilot: Pilot, rows: Rows, key: str) -> None:
    """Click the first row of `key` in `rows`, scrolled into view first."""
    rows.move_to(key)
    await pilot.pause()
    at = next(index for index, row in enumerate(rows.rows) if row.key == key)
    region = rows.content_region
    await pilot.click(offset=(region.x + 2, region.y + at - round(rows.scroll_offset.y)))


async def test_e_on_the_sessions_screen_and_a_click_on_its_footer_each_open_the_project_s_team_in_the_editor(project):
    app = TerminalUI()
    async with app.run_test(size=(120, 32)) as pilot:
        pressed = await opened(pilot)
        await pilot.press("escape")
        await drawn(pilot, lambda _: isinstance(app.screen, Sessions))
        await click_on(pilot, "#footer", "e edit team")
        await drawn(pilot, lambda _: checked(app))
        clicked = editor(app)
        header = screen_text(app).splitlines()[0]
        preview = plain(clicked.query_one("#preview", Rows))

    assert pressed is not clicked
    assert words(header) == f"The project's team · {PROJECT_FILE}, in ~"
    assert preview.startswith(f"{team_editor.ALLOWS} bob (tests.integration.scripts:saying) may message no one.")


async def test_the_editor_draws_the_shared_module_s_fields_by_section_each_problem_under_its_field(project):
    """Every field, entry to add and table to remove that the shared draft holds is a row a person acts on, and every
    problem it places is said under its field or table, or at the top, in the words the page says it."""
    (project / PROJECT_FILE).write_text(TEAM + 'preamble = "hi"\n')
    found = team_editor.draft(project, (Edit("set", ("roles", "bob", "count"), "two"),), HARNESSES)
    rows, acts = rows_of(found, {("roles", "bob", "count"): "two"}, 80)
    text = "\n".join(row.line.plain for row in rows)
    groups = [group for section in found.sections for group in section.groups]
    fields = {field.where: field for group in groups for field in group.fields}
    problems = [*found.problems, *(problem for group in groups for problem in group.problems)]
    problems += [problem for field in fields.values() for problem in field.problems]
    titles = [section.title for section in found.sections]
    count = words(" ".join(row.line.plain for row in rows if row.key == "field:roles.bob.count"))

    assert {key for key in acts if key.startswith("field:")} == {f"field:{where}" for where in fields}
    assert all(acts[f"field:{where}"] == field for where, field in fields.items())
    assert {key for key in acts if key.startswith("remove:")} == {"remove:roles.bob"}
    assert [key for key in acts if key.startswith("add:")] == [
        "add:roles",
        "add:topology",
        "add:topology.channels",
        "add:labels",
        "add:auth",
    ]
    assert [line.split(" · ")[0] for line in text.splitlines() if line.split(" · ")[0] in titles] == titles
    drawn_as = [words(team_editor.said(problem).replace("`", "")) for problem in problems]  # Code, as on the page.
    assert len(problems) == 3 and all(said in words(text) for said in drawn_as)
    assert count == "count two error: roles.bob.count: is a whole number"
    assert "Kept as the file has it, as only the file sets it: preamble." in words(text)
    assert page._said(fields["roles.bob.count"].problems) == [
        {"level": "error", "said": "error: roles.bob.count: is a whole number"}
    ]


async def test_a_change_is_checked_as_it_is_made_its_diff_and_its_problem_shown_beside_team_show_s_sentences(project):
    """A field's form takes its text, and once it is sent the draft is checked: the diff a save makes, a problem under
    the field that has it, the text typed kept in it, and Save disabled saying why."""
    app = TerminalUI()
    async with app.run_test(size=(120, 32)) as pilot:
        screen = await opened(pilot)
        await setting(pilot, "roles.bob.model", *"m1")
        await setting(pilot, "roles.bob.count", *"two")
        text = screen_text(app)
        preview = plain(screen.query_one("#preview", Rows))
        count, model = row_text(screen, "field:roles.bob.count"), row_text(screen, "field:roles.bob.model")
        await pilot.press("s")
        await drawn(pilot, lambda _: "Fix each change marked first: the editor could not make it." in told(app))

    assert '+model = "m1"' in preview and "bob (tests.integration.scripts:saying) may message no one." in preview
    assert count == "count two error: roles.bob.count: is a whole number"
    assert model == "model m1"
    assert team_editor.UNSAVED in words(text)
    assert screen._cannot("save") == "Fix each change marked first: the editor could not make it."
    assert (project / PROJECT_FILE).read_text() == TEAM


async def test_only_the_newest_check_is_drawn(project, monkeypatch):
    """A check that answers after a newer one was asked for is never drawn, and Save waits for the newest."""
    first, done = threading.Event(), threading.Event()
    draft = team_editor.draft

    def slow(folder, edits, harnesses):
        if [edit.text for edit in edits] == ["m1"]:
            first.wait(SECONDS)
            try:
                return draft(folder, edits, harnesses)
            finally:
                done.set()
        return draft(folder, edits, harnesses)

    app = TerminalUI()
    async with app.run_test(size=(120, 32)) as pilot:
        screen = await opened(pilot)
        monkeypatch.setattr(team_editor, "draft", slow)
        await typing(pilot, "roles.bob.model", *"m1")
        waiting = screen._cannot("save")
        await pilot.press("s")
        await drawn(pilot, lambda _: team_editor.CHECKING in told(app))
        await typing(pilot, "roles.bob.model", *"m2")
        await drawn(pilot, lambda _: checked(app))
        first.set()
        assert await asyncio.to_thread(done.wait, SECONDS)
        await pilot.pause()
        preview = plain(screen.query_one("#preview", Rows))
        model = row_text(screen, "field:roles.bob.model")

    assert waiting == team_editor.CHECKING
    assert '+model = "m2"' in preview and "m1" not in preview
    assert model == "model m2"


async def test_save_writes_the_diff_keeping_comments_and_asks_trust_once_naming_each_value_as_the_browser_does(project):
    """A save that writes what would run as you asks first, in the question the page asks, and a no writes nothing.
    A yes writes what the diff showed, the comment kept, and says so in the page's words."""
    app = TerminalUI()
    async with app.run_test(size=(120, 32)) as pilot:
        screen = await opened(pilot)
        await setting(pilot, "test.command", *"make test")
        await setting(pilot, "test.timeout", *"5m")
        diff = diff_of(screen)
        await pilot.press("s")
        await drawn(pilot, lambda _: isinstance(app.screen, Confirm))
        question = app.screen.query(Static).first().content
        await pilot.press("n")
        await drawn(pilot, lambda _: team_editor.NOT_SAVED in told(app) and checked(app))
        untouched = (project / PROJECT_FILE).read_text()
        await pilot.press("s")
        await drawn(pilot, lambda _: isinstance(app.screen, Confirm))
        await pilot.press("y")
        await drawn(pilot, lambda _: team_editor.saved(project) in told(app) and checked(app))
        after = screen.found

    assert (
        isinstance(question, Content)
        and question.plain == f'{SAVING}\ntest.command = ["make", "test"]\nSave it, as shown here?'
    )
    assert untouched == TEAM
    assert (project / PROJECT_FILE).read_text() == f'{TEAM}\n[test]\ncommand = ["make", "test"]\ntimeout = "5m"\n'
    assert '+command = ["make", "test"]' in diff
    assert after is not None and after.diff == "" and screen.edits == []
    assert screen._cannot("save") == "Nothing to save: the draft is the file as it stands."


async def test_a_save_over_a_file_changed_since_it_was_read_is_refused_and_shows_the_edits_on_what_it_holds_now(
    project,
):
    app = TerminalUI()
    async with app.run_test(size=(120, 32)) as pilot:
        screen = await opened(pilot)
        await setting(pilot, "roles.bob.model", *"m1")
        (project / PROJECT_FILE).write_text(solo("listening"))
        await pilot.press("s")
        await drawn(pilot, lambda _: any("changed since it was read" in said for said in told(app)) and checked(app))
        harness = row_text(screen, "field:roles.bob.harness")
        diff = diff_of(screen)

    assert (project / PROJECT_FILE).read_text() == solo("listening")
    assert harness.startswith("harness tests.integration.scripts:listening")
    assert '+model = "m1"' in diff and "# Bob, alone." not in diff


async def test_entries_are_added_with_their_first_field_and_removed_whole_and_one_not_made_is_said_once(project):
    """An add names its entry and gives the field it needs in one form; one that could not be made is said at its place
    in the check that follows and dropped, so the next says nothing of it; a removal takes the table whole."""
    app = TerminalUI()
    async with app.run_test(size=(120, 32)) as pilot:
        screen = await opened(pilot)
        screen.query_one(Fields).move_to("add:roles")
        await pilot.press("enter")
        await drawn(pilot, lambda _: isinstance(app.screen, FieldForm))
        await pilot.press(*"bob", "enter")
        app.screen.query_one(Choices).move_to("claude")
        await pilot.press("enter")
        await drawn(pilot, lambda _: checked(app))
        there = plain(screen.query_one(Fields))
        unmade = list(screen.edits)
        await setting(pilot, "roles.bob.model", *"m1")
        later = plain(screen.query_one(Fields))

        screen.query_one(Fields).move_to("add:roles")
        await pilot.press("enter")
        await drawn(pilot, lambda _: isinstance(app.screen, FieldForm))
        await pilot.press(*"critic", "enter")
        app.screen.query_one(Choices).move_to("claude")
        await pilot.press("enter")
        await drawn(pilot, lambda _: checked(app) and "remove:roles.critic" in screen.acts)
        added = diff_of(screen)
        screen.query_one(Fields).move_to("remove:roles.critic")
        await pilot.press("enter")
        await drawn(pilot, lambda _: checked(app) and "remove:roles.critic" not in screen.acts)
        removed = diff_of(screen)

    assert "error: roles.bob: is there already" in there and unmade == []
    assert "is there already" not in later
    assert '+[roles.critic]\n+harness = "claude"' in added
    assert "critic" not in removed and '+model = "m1"' in removed


async def test_each_disabled_act_says_why_and_does_nothing_else(project):
    """Save with nothing to save, a field that cannot be changed here, and Start while the loader refuses the changes
    each say why, in a toast and as the footer draws them dim, and open and write nothing."""
    app = TerminalUI()
    async with app.run_test(size=(120, 32)) as pilot:
        screen = await opened(pilot)
        await pilot.press("s")
        await drawn(pilot, lambda _: "Nothing to save: the draft is the file as it stands." in told(app))
        drawn_footer = screen.query_one("#footer", Static).content
        sandbox = screen.acts["field:roles.bob.sandbox"]
        assert isinstance(sandbox, Field) and sandbox.fixed is not None
        screen.query_one(Fields).move_to("field:roles.bob.sandbox")
        await pilot.press("enter")
        await drawn(pilot, lambda _: sandbox.fixed in told(app))
        stayed = app.screen
        await choosing(pilot, "roles.bob.harness", "")
        refused = screen._cannot("start")
        await pilot.press("n")
        await drawn(pilot, lambda _: refused in told(app))
        await pilot.pause()
        last = app.screen

    assert isinstance(drawn_footer, Content) and drawn_footer.markup == footer("team", {"save"}).markup
    assert sandbox.fixed.startswith("Unknown here: its harness is none this machine has a driver for")
    assert stayed is screen
    assert refused == "Fix each problem marked first: the loader refuses this draft, as `run` would."
    assert last is screen and (project / PROJECT_FILE).read_text() == TEAM


async def test_read_again_and_going_back_each_ask_first_where_they_drop_changes(project):
    app = TerminalUI()
    async with app.run_test(size=(120, 32)) as pilot:
        screen = await opened(pilot)
        await setting(pilot, "roles.bob.model", *"m1")
        await pilot.press("r")
        await drawn(pilot, lambda _: isinstance(app.screen, Confirm))
        reading = app.screen.query(Static).first().content
        await pilot.press("n")
        await drawn(pilot, lambda _: isinstance(app.screen, TeamEditor))
        kept = list(screen.edits)
        await pilot.press("escape")
        await drawn(pilot, lambda _: isinstance(app.screen, Confirm))
        leaving = app.screen.query(Static).first().content
        await pilot.press("n")
        await drawn(pilot, lambda _: isinstance(app.screen, TeamEditor))
        await pilot.press("r")
        await drawn(pilot, lambda _: isinstance(app.screen, Confirm))
        await pilot.press("y")
        await drawn(pilot, lambda _: checked(app))
        dropped = list(screen.edits)
        await pilot.press("escape")
        await drawn(pilot, lambda _: isinstance(app.screen, Sessions))

    assert isinstance(reading, Content) and reading.plain == team_editor.again(PROJECT_FILE)
    assert isinstance(leaving, Content) and leaving.plain == LEAVE
    assert [edit.text for edit in kept] == ["m1"] and dropped == []


async def test_every_act_of_the_editor_has_a_click_that_takes_it_as_its_key_does(project):
    """A click on a field's row opens its form, on a choice chooses it, on the form's keys sends or leaves it, on the
    footer's keys saves and goes back, and on a question's yes answers it."""
    app = TerminalUI()
    async with app.run_test(size=(120, 32)) as pilot:
        screen = await opened(pilot)
        fields = screen.query_one(Fields)
        await click_row(pilot, fields, "field:roles.bob.approvals")
        await drawn(pilot, lambda _: isinstance(app.screen, FieldForm))
        await click_row(pilot, app.screen.query_one(Choices), "allow")
        await drawn(pilot, lambda _: checked(app) and '+approvals = "allow"' in diff_of(screen))
        await click_row(pilot, fields, "field:roles.bob.model")
        await drawn(pilot, lambda _: isinstance(app.screen, FieldForm))
        await click_on(pilot, "Keys", "Esc: leave")
        await drawn(pilot, lambda _: isinstance(app.screen, TeamEditor))
        await click_row(pilot, fields, "field:roles.bob.model")
        await drawn(pilot, lambda _: isinstance(app.screen, FieldForm))
        await pilot.press(*"m1")
        await click_on(pilot, "Keys", "Enter: set it")
        await drawn(pilot, lambda _: checked(app) and row_text(screen, "field:roles.bob.model") == "model m1")
        await click_on(pilot, "#footer", "s save")
        await drawn(pilot, lambda _: team_editor.saved(project) in told(app) and checked(app))
        await setting(pilot, "roles.bob.effort", *"high")
        await click_on(pilot, "#footer", "Esc back")
        await drawn(pilot, lambda _: isinstance(app.screen, Confirm))
        await click_on(pilot, "Keys", "y: yes")
        await drawn(pilot, lambda _: isinstance(app.screen, Sessions))

    assert (project / PROJECT_FILE).read_text() == f'{TEAM}approvals = "allow"\nmodel = "m1"\n'
    assert [key.action for key in keys("team") if key.footer] == ["edit", "save", "start", "leave"]


@pytest.mark.parametrize("width", WIDTHS)
async def test_at_every_width_from_52_to_120_columns_every_act_and_problem_is_whole_on_screen(project, width):
    """The preview stands beside the fields from 100 columns and below them under that; the footer names every act
    whole, each problem is wrapped and never cut, and a field's form lies within the screen."""
    (project / PROJECT_FILE).write_text(TEAM + 'count = "two"\n')
    app = TerminalUI()
    async with app.run_test(size=(width, 24)) as pilot:
        screen = await opened(pilot)
        fields, preview = screen.query_one(Fields).region, screen.query_one("#preview").region
        footer = screen_text(app).splitlines()[-1]
        problem = row_text(screen, "field:roles.bob.count")
        screen.query_one(Fields).move_to("field:roles.bob.count")
        await pilot.press("enter")
        await drawn(pilot, lambda _: isinstance(app.screen, FieldForm))
        dialog = app.screen.query_one(".dialog").region
        lines = screen_text(app).splitlines()

    beside = fields.x + fields.width <= preview.x and fields.y == preview.y
    below = fields.y + fields.height <= preview.y and fields.x == preview.x
    assert beside if width >= 100 else below
    assert all(f"{key.shown} {key.name}" in footer for key in keys("team") if key.footer)
    assert problem == "count two error: roles.bob.count: Input should be a valid integer"
    assert dialog.x >= 0 and dialog.x + dialog.width <= width and all(len(line) <= width for line in lines)


async def test_what_the_file_holds_is_drawn_as_text_and_a_control_in_it_is_never_put_in_a_form(project):
    """A value holding markup and controls a terminal would act on is drawn as that text, each control as its
    escape, in its row and the diff, and nothing in it runs. A field typed in whose text holds such a control cannot
    be changed here, saying why, as its form would draw the control to the terminal itself; markup typed stays text."""
    hostile = "[@click=app.quit]x[/] \\u001b]0;owned\\u0007 \\u202eevil"
    (project / PROJECT_FILE).write_text(f'{TEAM}instructions = "{hostile}"\n')
    app = TerminalUI()
    async with app.run_test(size=(120, 32)) as pilot:
        screen = await opened(pilot)
        row = row_text(screen, "field:roles.bob.instructions")
        await setting(pilot, "roles.bob.model", *"[b]m1[/b]")
        shown = screen_text(app)
        screen.query_one(Fields).move_to("field:roles.bob.instructions")
        await pilot.press("enter")
        await drawn(pilot, lambda _: ESCAPED in told(app))
        stayed = app.screen
        running = app.is_running

    assert running and "[@click=app.quit]x[/]" in row and "\\x1b]0;owned\\x07" in row and "\\u202eevil" in row
    assert '+model = "[b]m1[/b]"' in shown and stayed is screen
    assert not [char for char in UNSAFE if char in shown]


async def test_start_from_the_editor_opens_the_start_form_once_the_editor_s_changes_are_saved(project, monkeypatch):
    """Start saves the changes first, then goes back to the sessions screen, which asks what a start asks."""
    started: list[bool] = []
    monkeypatch.setattr(Sessions, "action_new", lambda self: started.append(True))
    app = TerminalUI()
    async with app.run_test(size=(120, 32)) as pilot:
        await opened(pilot)
        await choosing(pilot, "roles.bob.approvals", "allow")
        await pilot.press("n")
        await drawn(pilot, lambda _: isinstance(app.screen, Sessions) and started)

    assert (project / PROJECT_FILE).read_text() == f'{TEAM}approvals = "allow"\n'
    assert started == [True]
