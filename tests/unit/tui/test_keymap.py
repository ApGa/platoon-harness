"""One keymap table: every binding, the help, the footer, the palette and the guide's keymap are made from it."""

from pathlib import Path

from rich.cells import cell_len
from textual.binding import Binding

from platoon_harness import Session, Team
from platoon_harness.testing import ScriptedDriver
from platoon_harness_cli.tui.app import TerminalUI
from platoon_harness_cli.tui.dialogs import Confirm, Form, Help
from platoon_harness_cli.tui.keymap import KEYMAP, keys, regenerate
from platoon_harness_cli.tui.rows import Rows
from platoon_harness_cli.tui.sessions import Sessions
from platoon_harness_cli.tui.transcript import Transcript
from platoon_harness_cli.tui.workspace import Workspace

from ..runtime.support import harness, in_state
from .support import drawn

GUIDE = Path(__file__).parents[3] / "docs" / "tui.md"
PLACES = {
    "everywhere": (TerminalUI,),
    "sessions": (Sessions,),
    "workspace": (Workspace,),
    "transcript": (Transcript,),
    "list": (Rows,),
    "question": (Confirm,),
    "dialog": (Form, Help),
}


def test_every_binding_comes_from_the_table_and_runs_an_action_of_its_place():
    """The composer reads its keys from the table itself, and every other place binds them."""
    assert set(PLACES) | {"composer"} == {key.where for key in KEYMAP}
    for where, places in PLACES.items():
        for place in places:
            bound = [(binding.key, binding.action) for binding in place.BINDINGS if isinstance(binding, Binding)]

            assert bound == [(key.keys, key.runs) for key in keys(where)], place
            for key in keys(where):
                runs = f"action_{key.action}" if not key.planned else "action_planned"
                assert hasattr(Workspace if key.planned else place, runs) or key.action == "command_palette", key


async def test_a_key_not_built_yet_says_why_and_does_nothing_else(tmp_path, monkeypatch):
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
            app.screen.query_one(Transcript).focus()
            for key in planned:
                said = f"{key.does}: not built yet, as {key.planned}"
                await pilot.press(key.keys.split(",")[0])
                await drawn(pilot, lambda _, said=said: any(notice.message == said for notice in app._notifications))

        moved = [(event.type, event.gist) async for event in owner.events(head) if event.actor == "human:you"]
        assert moved == [], "a key not built yet did something"


async def test_the_help_shows_every_key_of_the_table_and_why_one_is_not_built_at_80_columns(tmp_path, monkeypatch):
    monkeypatch.setenv("PLATOON_HARNESS_HOME", str(tmp_path))
    app = TerminalUI()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.press("f1")
        await pilot.pause()

        assert isinstance(app.screen, Help)
        help = app.screen.query_one(Rows)
        lines = [row.line.plain for row in help.rows]
        said = " ".join(" ".join(line.split()) for line in lines)
        for key in KEYMAP:
            assert key.shown in said and " ".join(key.does.split()) in said, key
            assert not key.planned or " ".join(f"Not built yet: {key.planned}".split()) in said, key
        assert all(cell_len(line) <= help.scrollable_content_region.width for line in lines)
        await pilot.press("down", "down")
        assert help.scroll_y == 2

        await pilot.press("f1")
        await pilot.pause()
        assert not any(isinstance(screen, Help) for screen in app.screen_stack), "F1 in the help opened another"


def test_a_letter_is_shown_as_it_is_typed():
    assert [key.shown for key in keys("sessions") if len(key.keys) == 1] == ["n", "r", "s"]


def test_the_guide_s_keymap_is_the_table_s():
    guide = GUIDE.read_text()

    assert guide == regenerate(guide), "run `uv run python -m platoon_harness_cli.tui.keymap docs/tui.md`"
