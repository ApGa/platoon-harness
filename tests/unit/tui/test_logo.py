"""The Platoon logo's agents as sprites, two pixels to a cell."""

from pathlib import Path

import pytest

from platoon_harness.config import PROJECT_FILE
from platoon_harness_cli.tui.app import TerminalUI
from platoon_harness_cli.tui.logo import ANSI, SMALL, TRUECOLOUR, sprite
from platoon_harness_cli.tui.sessions import Sessions

from .support import drawn


def test_the_logo_is_drawn_two_pixels_to_a_cell_in_its_colours_or_the_terminal_s():
    """Every row of pixels as wide as the others and in pairs, each colour the icon's, or the terminal's own for a theme
    that keeps to them, and a clear pixel shows the background."""
    assert len(SMALL) % 2 == 0 and len({len(row) for row in SMALL}) == 1
    assert {pixel for row in SMALL for pixel in row} <= {".", *TRUECOLOUR}
    assert set(TRUECOLOUR) == set(ANSI)
    for colours in (TRUECOLOUR, ANSI):
        lines = sprite(SMALL, colours)
        assert len(lines) == len(SMALL) // 2
        assert all(line.cell_length == len(SMALL[0]) for line in lines)
        assert {span.style for line in lines for span in line.spans} <= {
            *colours.values(),
            *(f"{upper} on {lower}" for upper in colours.values() for lower in colours.values()),
        }


def test_a_cell_is_the_upper_pixel_over_the_lower_or_a_half_block_over_the_background():
    lines = sprite(("ab..", "a.b."), {"a": "#111111", "b": "#222222"})

    assert lines[0].plain == "█▀▄ "
    assert [span.style for span in lines[0].spans] == ["#111111", "#222222", "#222222"]


@pytest.mark.parametrize("width", [100, 80, 64])
async def test_the_sessions_screen_s_logo_is_never_torn(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, width):
    """At any width, each of the logo's rows stands under the one before it, its words beside it cut at the edge, never
    wrapped onto the next row."""
    monkeypatch.setenv("PLATOON_HARNESS_HOME", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    (tmp_path / PROJECT_FILE).write_text("")
    app = TerminalUI()
    async with app.run_test(size=(width, 24)) as pilot:
        text = await drawn(pilot, lambda text: "platoon-harness" in text and isinstance(app.screen, Sessions))
        brand = app.screen.query_one("#brand").region

    art = sprite(SMALL, TRUECOLOUR)
    rows = text.splitlines()[brand.y : brand.y + len(art)]
    assert [row[2 : 2 + art[0].cell_length] for row in rows] == [line.plain for line in art]
    assert brand.height == len(art) + 1
