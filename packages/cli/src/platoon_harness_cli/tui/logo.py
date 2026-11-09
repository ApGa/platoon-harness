"""The Platoon logo as sprites: its round-headed, big-eyed agents in their blue-to-green gradient, drawn by hand as
pixels from the Platoon project's icon (MIT, Apurva Gandhi) and shown two pixels to a cell with half blocks."""

from collections.abc import Mapping, Sequence

from textual.content import Content

AGENT = (
    ".xxx.",
    "x.x.x",
    ".xxx.",
    "xxxxx",
    ".xxx.",
    ".x.x.",
)
"""One of the small sprite's agents, five pixels by six: a round head with its eyes open on the background, arms out,
and its legs."""
SMALL_AT = ((0, 2, "a"), (6, 1, "b"), (12, 0, "d"))
"""Where each of the small sprite's three agents stands, its left and its top, and its colour: marching up, blue to
green, with a clear column right of the last, which its raised hand takes as it waves."""
SMALL_SIZE = (18, 8)
FIGURE = (
    ".xxxxx.",
    "xxxxxxx",
    "xeexeex",
    "xeexeex",
    "xxxxxxx",
    ".xxxxx.",
    "..xxx..",
    "xxxxxxx",
    "x.xxx.x",
    "..xxx..",
    ".x...x.",
    "xx...xx",
)
"""One of the large sprite's agents, seven pixels by twelve: a round head with two big white eyes, arms down at its
sides, and its feet."""
LARGE_AT = ((0, 2, "a"), (8, 0, "b"), (16, 2, "c"))
"""The large sprite's three agents, of one size, the middle one a step ahead: blue, sky and green, mirrored about the
middle."""
LARGE_SIZE = (23, 14)
TRUECOLOUR = {"a": "#1862a7", "b": "#389cc3", "c": "#50be74", "d": "#60c664", "e": "#eef4fb", "w": "#e0a46c"}
"""Each pixel's colour, as the icon has it, blue to green, its eyes white, and `w`, the eyes of an agent that looks up
at you, in the notice tone. `.` is clear."""
ANSI = {
    "a": "ansi_blue",
    "b": "ansi_cyan",
    "c": "ansi_green",
    "d": "ansi_bright_green",
    "e": "ansi_bright_white",
    "w": "ansi_yellow",
}
"""The same colours in the terminal's own, for a theme that keeps to them."""


def composed(
    figure: Sequence[str],
    at: Sequence[tuple[int, int, str]],
    size: tuple[int, int],
    changed: Mapping[int, Sequence[str]],
) -> tuple[str, ...]:
    """Agents drawn as `figure` where `at` places each, its `x` pixels taking its colour, on a clear canvas of `size`,
    an agent `changed` names drawn as the figure it gives instead, which may reach a column past its own."""
    width, height = size
    canvas = [["."] * width for _ in range(height)]
    for index, (left, top, colour) in enumerate(at):
        for y, row in enumerate(changed.get(index, figure)):
            for x, pixel in enumerate(row):
                if pixel != ".":
                    canvas[top + y][left + x] = colour if pixel == "x" else pixel
    return tuple("".join(row) for row in canvas)


SMALL = composed(AGENT, SMALL_AT, SMALL_SIZE, {})
"""Three agents marching up, for the navigator's top: 18 cells by 4."""
LARGE = composed(FIGURE, LARGE_AT, LARGE_SIZE, {})
"""Three agents of one size, the middle one a step ahead, for beside the wordmark: 23 cells by 7."""


def sprite(pixels: Sequence[str], colours: Mapping[str, str]) -> list[Content]:
    """`pixels` as lines of cells, two rows to a line: `▀` in the upper pixel's colour on the lower's, `▄` or `▀` alone
    where one of the two is clear, so the background shows through, and a space where both are."""
    lines = []
    for top, bottom in zip(pixels[::2], pixels[1::2], strict=True):
        cells = []
        for upper, lower in zip(top, bottom, strict=True):
            if upper == lower == ".":
                cells.append(" ")
            elif upper == ".":
                cells.append(("▄", colours[lower]))
            elif lower == "." or upper == lower:
                cells.append(("▀" if lower == "." else "█", colours[upper]))
            else:
                cells.append(("▀", f"{colours[upper]} on {colours[lower]}"))
        lines.append(Content.assemble(*cells))
    return lines
