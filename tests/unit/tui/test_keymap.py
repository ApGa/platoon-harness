"""One keymap table: every binding, the typed commands, the help, the footer, the palette and the guide's keymap are
made from it."""

import re
from pathlib import Path

from rich.cells import cell_len
from textual.actions import parse
from textual.binding import Binding

from platoon_harness import Session, Team
from platoon_harness.testing import ScriptedDriver
from platoon_harness_cli.tui.app import TerminalUI
from platoon_harness_cli.tui.composer import Composer
from platoon_harness_cli.tui.dialogs import Confirm, Form, Help
from platoon_harness_cli.tui.keymap import KEYMAP, TYPED, command, keys, reference, regenerate
from platoon_harness_cli.tui.rows import Rows
from platoon_harness_cli.tui.sessions import Sessions
from platoon_harness_cli.tui.transcript import Transcript
from platoon_harness_cli.tui.workspace import Workspace

from ..runtime.support import harness, in_state
from .support import drawn

GUIDE = Path(__file__).parents[3] / "docs" / "tui.md"
PLACES = {
    TerminalUI: ("everywhere",),
    Sessions: ("sessions",),
    Workspace: ("workspace",),
    Transcript: ("transcript",),
    Rows: ("list",),
    Confirm: ("question",),
    Form: ("dialog",),
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
    """The composer reads its keys from the table itself, and every other place binds them. An action names `app` or
    `screen` when it runs on one, and otherwise runs on the place that binds it."""
    assert {where for wheres in PLACES.values() for where in wheres} | {"composer"} == {key.where for key in KEYMAP}
    for place, wheres in PLACES.items():
        bound = [(binding.key, binding.action) for binding in place.BINDINGS if isinstance(binding, Binding)]

        assert bound == [(key.keys, key.runs) for where in wheres for key in keys(where)], place
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
    """In a session, by its typed command. Where nothing is typed, the sessions screen, a question, a form and the
    help, each act has a plain key, quitting included, and so does a list."""
    for where in ("sessions", "list", "question", "dialog"):
        for key in keys(where):
            assert plain(key.keys.split(",")[0]), key
    for key in keys("everywhere"):
        assert any(other.action == key.action for other in keys("sessions")), key


def test_the_guide_s_keymap_is_the_table_s_with_each_typed_command_beside_its_key():
    guide = GUIDE.read_text()

    assert guide == regenerate(guide), "run `uv run python -m platoon_harness_cli.tui.keymap docs/tui.md`"
    for key in acts():
        first = key.keys.split(",")[0]
        assert re.search(rf"\| `{re.escape(first)}`[^|]* \| `{re.escape(key.typed)}` \|", reference()), key


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
                app.screen.query_one(Composer).focus()
                await pilot.press(*key.typed, "enter")
                await drawn(pilot, lambda _, said=said: told(said) == 2)
                assert app.focused is app.screen.query_one(Composer)

        moved = [(event.type, event.gist) async for event in owner.events(head) if event.actor == "human:you"]
        assert moved == [], "a key not built yet did something"


async def test_the_help_shows_every_key_of_the_table_its_typed_command_and_why_one_is_not_built_at_80_columns(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("PLATOON_HARNESS_HOME", str(tmp_path))
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
            assert any(line.split()[:2] == [key.shown, key.typed] for line in lines if line.strip()), key
        assert all(cell_len(line) <= help.scrollable_content_region.width for line in lines)
        await pilot.press("down", "down")
        assert help.scroll_y == 2

        await pilot.press("f1")
        await pilot.pause()
        assert not any(isinstance(screen, Help) for screen in app.screen_stack), "F1 in the help opened another"


def test_a_key_is_shown_as_it_is_typed():
    assert [key.shown for key in keys("sessions")] == ["Enter", "n", "r", "s", "l", "?", "p", "q"]
