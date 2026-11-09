"""One keymap table: every binding, the typed commands, the help, the footer, the palette and the guide's keymap are
made from it."""

import re
from pathlib import Path

from rich.cells import cell_len
from textual.actions import parse
from textual.binding import Binding
from textual.content import Content

from platoon_harness import Session, Team
from platoon_harness.config import PROJECT_FILE
from platoon_harness.testing import ScriptedDriver
from platoon_harness_cli.main import build
from platoon_harness_cli.tui.app import TerminalUI
from platoon_harness_cli.tui.approvals import Approval
from platoon_harness_cli.tui.composer import Composer
from platoon_harness_cli.tui.dialogs import Confirm, Form, Help
from platoon_harness_cli.tui.editor import FieldForm, TeamEditor
from platoon_harness_cli.tui.keymap import KEYMAP, TYPED, command, keys, reference, regenerate
from platoon_harness_cli.tui.provenance import Provenance
from platoon_harness_cli.tui.review import Patch, Review
from platoon_harness_cli.tui.rows import Rows
from platoon_harness_cli.tui.sessions import Sessions
from platoon_harness_cli.tui.tasks import Tasks
from platoon_harness_cli.tui.transcript import Focus, Transcript
from platoon_harness_cli.tui.workspace import Dock, Navigator, Workspace

from ..runtime.support import harness, in_state
from .support import click_on, drawn, workspace

GUIDE = Path(__file__).parents[3] / "docs" / "how-to" / "tui.md"
PLACES = {
    TerminalUI: ("everywhere",),
    Sessions: ("sessions",),
    TeamEditor: ("team",),
    Workspace: ("workspace", "replay", "parts"),
    Transcript: ("transcript", "panel"),
    Navigator: ("panel",),
    Dock: ("panel",),
    Rows: ("list",),
    Provenance: ("provenance",),
    Review: ("dialog", "review"),
    Patch: ("dialog", "patch"),
    Approval: ("dialog",),
    Tasks: ("dialog",),
    Confirm: ("question",),
    Form: ("dialog",),
    FieldForm: ("dialog",),
    Help: ("dialog",),
}
PLAIN = {"enter", "escape", "tab", "shift+tab", "up", "down", "backspace", "question_mark", "slash"}
"""The keys every terminal delivers, as Textual names them, besides a character typed alone."""


def plain(key: str) -> bool:
    return key in PLAIN or len(key) == 1


def acts() -> list:
    """The acts of a session: every key that has a typed command."""
    return [key for key in KEYMAP if key.where in TYPED]


def test_every_binding_comes_from_the_table_and_runs_an_action_of_its_place():
    """The composer and the dock read their keys from the table themselves, in the order they come, and every other
    place binds them, but an act with no keys. An action names `app` or `screen` when it runs on one, and otherwise runs
    on the place that binds it."""
    assert {where for wheres in PLACES.values() for where in wheres} | {"composer", "dock"} == {
        key.where for key in KEYMAP
    }
    assert all(hasattr(Workspace, f"action_{parse(key.runs)[1]}") for key in keys("dock"))
    assert not [key for key in KEYMAP if not key.keys and not key.typed]
    for place, wheres in PLACES.items():
        bound = [(binding.key, binding.action) for binding in place.BINDINGS if isinstance(binding, Binding)]

        assert bound == [(key.keys, key.runs) for where in wheres for key in keys(where) if key.keys], place
        for where in wheres:
            for key in keys(where):
                namespace, action, _ = parse(key.runs)
                runs_on = {"app": TerminalUI, "screen": Workspace}.get(namespace, place)
                assert hasattr(runs_on, f"action_{action}"), key


def test_every_act_of_a_session_has_one_typed_command_that_runs_it():
    """A typed command is `/` and an act's name, one per act and no other, and `/` alone is the help. A line that holds
    anything else is no command."""
    typed = [key.typed for key in acts()]

    assert all(re.fullmatch(r"/[a-z]+(-[a-z]+)*", said) for said in typed), typed
    assert len(set(typed)) == len(typed)
    assert all(command(key.typed) is key for key in acts())
    assert all(command(f"  {key.typed}\n") is key for key in acts())
    assert command("/") is command("/help") is next(key for key in acts() if key.action == "app.help")
    for said in ("/x", "/help me", "/help\n/quit", "help", "", "/ help", "//help", "/Help"):
        assert command(said) is None, said
    assert not [key for key in KEYMAP if key.where not in TYPED and key.typed]


def test_every_act_is_reached_with_keys_every_terminal_delivers():
    """In a session, by its typed command, and between its parts and in each list, by plain keys. Where nothing is
    typed, the sessions screen, the team editor, a question, a form and the help, each act has a plain key, quitting
    included."""
    for where in ("sessions", "team", "parts", "panel", "dock", "list", "provenance", "question", "dialog"):
        for key in keys(where):
            assert plain(key.keys.split(",")[0]), key
    for key in keys("everywhere"):
        assert any(other.action == key.action for other in keys("sessions")), key


def test_no_typed_command_is_named_as_a_command_of_the_command_line():
    """A reader takes a typed command for the command line's of that name: there `attach` opens a session, so beside
    `/detach` a typed `/attach` could not read as attaching a file."""
    commands = {name for name in build() if not name.startswith("-")}

    assert not commands & {key.name for key in acts()}


def test_the_guide_s_keymap_is_the_table_s_with_each_typed_command_beside_its_key():
    guide = GUIDE.read_text()

    assert guide == regenerate(guide), "run `uv run python -m platoon_harness_cli.tui.keymap docs/how-to/tui.md`"
    for key in acts():
        pressed = f"`{re.escape(key.shown)}`[^|]*" if key.keys else ""
        assert re.search(rf"\| {pressed} \| `{re.escape(key.typed)}` \|", reference()), key
    assert "question_mark" not in reference() and "slash" not in reference(), "a key shown as Textual names it"


def test_the_palette_offers_every_act_of_a_session_by_its_typed_command():
    titles = [title for title, _, _ in Workspace("s").commands()]

    assert titles[: len(acts())] == [key.typed for key in acts()]


async def test_a_key_not_built_yet_and_its_typed_command_each_say_why_and_do_nothing_else(tmp_path, monkeypatch):
    monkeypatch.setenv("PLATOON_HARNESS_HOME", str(tmp_path))
    lead = Team.model_validate({"roles": {"lead": {"harness": harness(lambda: ScriptedDriver([]))}}})
    planned = [key for key in KEYMAP if key.planned]
    assert planned
    async with Session.start(lead, name="s", root=tmp_path, cwd=tmp_path) as owner:
        await in_state(owner, "lead", "idle")
        head = await owner.head()
        app = TerminalUI("s")
        async with app.run_test(size=(120, 32)) as pilot:
            await drawn(pilot, lambda text: "@lead" in text)

            def told(said: str) -> int:
                return sum(notice.message == said for notice in app._notifications)

            for key in planned:
                said = f"{key.does}: not built yet, as {key.planned}"
                app.screen.query_one(Transcript).focus()
                await pilot.press(key.keys.split(",")[0])
                await drawn(pilot, lambda _, said=said: told(said) == 1)
                await pilot.press("escape", *key.typed, "enter")
                await drawn(pilot, lambda _, said=said: told(said) == 2)
                assert app.focused is app.screen.query_one(Composer)

        moved = [(event.type, event.gist) async for event in owner.events(head) if event.actor == "human:you"]
        assert moved == [], "a key not built yet did something"


async def test_ctrl_t_and_its_typed_command_open_the_tasks_view(tmp_path, monkeypatch):
    """On a queue's focus, and on an agent's they say that only a queue or a board has a view to show, and open none."""
    monkeypatch.setenv("PLATOON_HARNESS_HOME", str(tmp_path))
    channels = {"tasks": {"kind": "queue", "writers": "all", "readers": "all"}}
    lead = {"harness": harness(lambda: ScriptedDriver([]))}
    team = Team.model_validate({"roles": {"lead": lead}, "topology": {"channels": channels}})
    async with Session.start(team, name="s", root=tmp_path, cwd=tmp_path) as owner:
        await in_state(owner, "lead", "idle")
        app = TerminalUI("s")
        async with app.run_test(size=(120, 32)) as pilot:
            await drawn(pilot, lambda text: "@lead" in text)
            await pilot.press("ctrl+t")
            said = "Only a queue has tasks to show, and a board entries: choose one in the navigator first."
            await drawn(pilot, lambda _: any(notice.message == said for notice in app._notifications))
            on_agent = app.screen
            await workspace(app).show(Focus.of_channel("tasks", "queue"))
            await pilot.press("ctrl+t")
            pressed = await drawn(pilot, lambda _: isinstance(app.screen, Tasks))
            await pilot.press("escape")
            await drawn(pilot, lambda _: isinstance(app.screen, Workspace))
            await pilot.press(*"/tasks", "enter")
            await drawn(pilot, lambda _: isinstance(app.screen, Tasks))
            typed = app.screen

    assert isinstance(on_agent, Workspace)
    assert "Tasks on tasks" in pressed or "Reading queue/tasks" in pressed
    assert isinstance(typed, Tasks) and typed.channel == "queue/tasks"


async def test_find_has_a_typed_command_and_a_shortcut_that_decides_nothing(tmp_path, monkeypatch):
    """Ctrl+F opens `/find`'s form and does nothing more, from the composer, keeping its draft, and from another part.
    The form decides nothing until it is sent: Esc leaves it, and nothing is written."""
    find = command("/find")
    assert find is not None and find.keys == "ctrl+f"
    monkeypatch.setenv("PLATOON_HARNESS_HOME", str(tmp_path))
    lead = Team.model_validate({"roles": {"lead": {"harness": harness(lambda: ScriptedDriver([]))}}})
    async with Session.start(lead, name="s", root=tmp_path, cwd=tmp_path) as owner:
        await in_state(owner, "lead", "idle")
        head = await owner.head()
        app = TerminalUI("s")
        async with app.run_test(size=(120, 32)) as pilot:
            await drawn(pilot, lambda text: "@lead" in text)
            composer = app.screen.query_one(Composer)
            opened = []
            for typed in (("ctrl+f",), ("tab", "ctrl+f"), ("escape", *"/find", "enter")):
                await pilot.press(*typed)
                await drawn(pilot, lambda _: isinstance(app.screen, Form))
                opened.append(app.screen._title.plain)
                await pilot.press(*"yes", "escape")
                await drawn(pilot, lambda _: isinstance(app.screen, Workspace))
                if typed == ("ctrl+f",):
                    assert app.focused is composer and composer.text == ""
                    await pilot.press(*"a draft", "ctrl+f")
                    await drawn(pilot, lambda _: isinstance(app.screen, Form))
                    await pilot.press("escape")
                    await drawn(pilot, lambda _: isinstance(app.screen, Workspace))
                    assert app.focused is composer and composer.text == "a draft"
                    await pilot.press(*["backspace"] * 7)

        moved = [(event.type, event.gist) async for event in owner.events(head) if event.actor == "human:you"]
        assert opened == ["Find"] * 3
        assert moved == [], "a find did something"


async def test_the_help_shows_every_key_of_the_table_its_typed_command_and_why_one_is_not_built_at_80_columns(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("PLATOON_HARNESS_HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    (tmp_path / PROJECT_FILE).write_text('[roles.lead]\nharness = "claude"\n')
    app = TerminalUI()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.press("question_mark")
        await pilot.pause()

        assert isinstance(app.screen, Help)
        help = app.screen.query_one(Rows)
        lines = [row.line.plain for row in help.rows]
        said = " ".join(" ".join(line.split()) for line in lines)
        for key in KEYMAP:
            assert key.shown in said and " ".join(key.does.split()) in said, key
            assert not key.planned or " ".join(f"Not built yet: {key.planned}".split()) in said, key
        for key in acts():
            begins = [said for said in (key.shown, key.typed) if said]
            assert any(line.split()[: len(begins)] == begins for line in lines if line.strip()), key
        assert all(cell_len(line) <= help.scrollable_content_region.width for line in lines)
        await pilot.press("down", "down")
        assert help.scroll_y == 2

        await pilot.press("f1")
        await pilot.pause()
        assert not any(isinstance(screen, Help) for screen in app.screen_stack), "F1 in the help opened another"


async def test_a_click_on_a_key_in_the_footer_or_a_dialog_does_what_the_key_does(tmp_path, monkeypatch):
    """The sessions screen's footer, a form's keys and a question's each run, on a click, what their key runs."""
    monkeypatch.setenv("PLATOON_HARNESS_HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    (tmp_path / PROJECT_FILE).write_text("")
    answers: list[bool] = []
    app = TerminalUI()
    async with app.run_test(size=(120, 30)) as pilot:
        await drawn(pilot, lambda text: "No sessions yet" in text)
        await click_on(pilot, "#footer", "? help")
        await drawn(pilot, lambda _: isinstance(app.screen, Help))
        await pilot.press("escape")
        await drawn(pilot, lambda _: isinstance(app.screen, Sessions))
        await click_on(pilot, "#footer", "n new")
        await drawn(pilot, lambda _: isinstance(app.screen, Form))
        await click_on(pilot, "Keys", "Esc: leave")
        await drawn(pilot, lambda _: isinstance(app.screen, Sessions))
        app.push_screen(Confirm(Content("Sure?")), answers.append)
        await drawn(pilot, lambda _: isinstance(app.screen, Confirm))
        await click_on(pilot, "Keys", "y: yes")
        await drawn(pilot, lambda _: answers == [True])


def test_a_key_is_shown_as_it_is_typed():
    assert [key.shown for key in keys("sessions")] == ["Enter", "n", "e", "r", "s", "R", "l", "t", "c", "?", "p", "q"]
