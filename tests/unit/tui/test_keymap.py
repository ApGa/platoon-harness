"""One keymap table: every binding, the help, the footer, the palette and the guide's keymap are made from it."""

from pathlib import Path

from textual.binding import Binding

from platoon_harness_cli.tui.app import TerminalUI
from platoon_harness_cli.tui.dialogs import Help
from platoon_harness_cli.tui.keymap import KEYMAP, keys, regenerate
from platoon_harness_cli.tui.rows import Rows
from platoon_harness_cli.tui.sessions import Sessions
from platoon_harness_cli.tui.transcript import Transcript
from platoon_harness_cli.tui.workspace import Workspace

GUIDE = Path(__file__).parents[3] / "docs" / "tui.md"
PLACES = {"everywhere": TerminalUI, "sessions": Sessions, "workspace": Workspace, "transcript": Transcript}


def test_every_binding_comes_from_the_table_and_runs_an_action_of_its_place():
    for where, place in PLACES.items():
        bound = [(binding.key, binding.action) for binding in place.BINDINGS if isinstance(binding, Binding)]

        assert bound == [(key.keys, key.runs) for key in keys(where)]
        for key in keys(where):
            runs = f"action_{key.action}" if not key.planned else "action_planned"
            assert hasattr(Workspace if key.planned else place, runs) or key.action == "command_palette", key.action


async def test_a_key_not_built_yet_says_why_and_does_nothing_else(tmp_path, monkeypatch):
    monkeypatch.setenv("PLATOON_HARNESS_HOME", str(tmp_path))
    planned = [key for key in KEYMAP if key.planned]
    assert planned
    for key in planned:
        assert keys(key.where) and f"Not built yet: {key.planned}" in regenerate(GUIDE.read_text())


async def test_the_help_shows_every_key_of_the_table(tmp_path, monkeypatch):
    monkeypatch.setenv("PLATOON_HARNESS_HOME", str(tmp_path))
    app = TerminalUI()
    async with app.run_test(size=(120, 60)) as pilot:
        await pilot.press("f1")
        await pilot.pause()

        assert isinstance(app.screen, Help)
        lines = [row.line.plain for row in app.screen.query_one(Rows).rows]
        assert all(any(key.shown in line and key.does in line for line in lines) for key in KEYMAP)


def test_the_guide_s_keymap_is_the_table_s():
    guide = GUIDE.read_text()

    assert guide == regenerate(guide), "run `uv run python -m platoon_harness_cli.tui.keymap docs/tui.md`"
