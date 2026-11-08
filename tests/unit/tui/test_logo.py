"""The Platoon logo's agents as a sprite, two pixels to a cell."""

import pytest

from platoon_harness_cli.tui.logo import ANSI, LARGE, SMALL, TRUECOLOUR, sprite


@pytest.mark.parametrize("pixels", [SMALL, LARGE], ids=["small", "large"])
def test_the_logo_is_drawn_two_pixels_to_a_cell_in_its_colours_or_the_terminal_s(pixels):
    """Every row of pixels as wide as the others and in pairs, each colour the icon's, or the terminal's own for a theme
    that keeps to them, and a clear pixel shows the background."""
    assert len(pixels) % 2 == 0 and len({len(row) for row in pixels}) == 1
    assert {pixel for row in pixels for pixel in row} <= {".", *TRUECOLOUR}
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
