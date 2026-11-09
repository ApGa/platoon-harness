"""The Platoon logo's agents as sprites, two pixels to a cell."""

from pathlib import Path

import pytest

from platoon_harness.config import PROJECT_FILE
from platoon_harness_cli.tui.app import TerminalUI
from platoon_harness_cli.tui.logo import AGENT, ANSI, FIGURE, LARGE, LARGE_AT, SMALL, TRUECOLOUR, sprite
from platoon_harness_cli.tui.sessions import Sessions

from .support import drawn


@pytest.mark.parametrize("pixels", [SMALL, LARGE], ids=["small", "large"])
def test_the_logo_is_drawn_two_pixels_to_a_cell_in_its_colours_or_the_terminal_s(pixels):
    """Every row of pixels as wide as the others and in pairs, each colour the icon's, or the terminal's own for a theme
    that keeps to them, and a clear pixel shows the background."""
    assert len(pixels) % 2 == 0 and len({len(row) for row in pixels}) == 1
    assert {pixel for row in pixels for pixel in row} <= {".", *TRUECOLOUR}
    assert set(TRUECOLOUR) == set(ANSI)
    for colours in (TRUECOLOUR, ANSI):
        lines = sprite(pixels, colours)
        assert len(lines) == len(pixels) // 2
        assert all(line.cell_length == len(pixels[0]) for line in lines)
        assert {span.style for line in lines for span in line.spans} <= {
            *colours.values(),
            *(f"{upper} on {lower}" for upper in colours.values() for lower in colours.values()),
        }


def test_a_cell_is_the_upper_pixel_over_the_lower_or_a_half_block_over_the_background():
    lines = sprite(("ab..", "a.b."), {"a": "#111111", "b": "#222222"})

    assert lines[0].plain == "█▀▄ "
    assert [span.style for span in lines[0].spans] == ["#111111", "#222222", "#222222"]


def test_the_large_logo_s_agents_are_of_one_size_and_style_and_it_is_symmetric():
    """Three agents drawn from one figure, round-headed with two big white eyes, the middle one a step ahead, so the
    logo reads the same mirrored, but for the colour of each."""
    shapes = ["".join("x" if pixel != "." else "." for pixel in row) for row in LARGE]

    assert shapes == [row[::-1] for row in shapes]
    assert len({len(row) for row in FIGURE}) == 1 and FIGURE[2] == FIGURE[3] == "xeexeex"
    assert [colour for *_, colour in LARGE_AT] == ["a", "b", "c"] and len(AGENT[0]) == 5


@pytest.mark.parametrize("width", [80, 81, 100, 64])
async def test_the_sessions_screen_s_logo_is_never_torn(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, width):
    """At any width, each of the logo's rows stands under the one before it, its words beside it cut at the edge, never
    wrapped onto the next row: large where it has the room, and small where it does not."""
    monkeypatch.setenv("PLATOON_HARNESS_HOME", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    (tmp_path / PROJECT_FILE).write_text("")
    app = TerminalUI()
    async with app.run_test(size=(width, 24)) as pilot:
        text = await drawn(pilot, lambda text: "platoon-harness" in text and isinstance(app.screen, Sessions))
        brand = app.screen.query_one("#brand").region

    art = sprite(LARGE if width >= 80 else SMALL, TRUECOLOUR)
    rows = text.splitlines()[brand.y + 1 : brand.y + 1 + len(art)]
    assert [row[2 : 2 + art[0].cell_length] for row in rows] == [line.plain for line in art]
    assert brand.height == len(art) + 2
