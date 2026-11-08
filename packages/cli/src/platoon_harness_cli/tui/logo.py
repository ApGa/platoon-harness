"""The Platoon logo as a sprite: its round-headed agents in their blue-to-green gradient, drawn by hand as pixels from
the Platoon project's icon (MIT, Apurva Gandhi) and shown two pixels to a cell with half blocks."""

from collections.abc import Mapping, Sequence

from textual.content import Content

SMALL = (
    ".............ddd.",
    ".......bbb..d.d.d",
    ".aaa..b.b.b..ddd.",
    "a.a.a..bbb..ddddd",
    ".aaa..bbbbb..ddd.",
    "aaaaa..bbb...d.d.",
    ".aaa...b.b.......",
    ".a.a.............",
)
"""Three agents marching up, blue to green, for where a session's name stands: 17 cells by 4."""
LARGE = (
    "....................ddddd..",
    "............bbbbb..dd.d.dd.",
    "...........bb.b.bb.ddddddd.",
    "...........bbbbbbb..ddddd..",
    "............bbbbb..d.ddd.d.",
    "...........b.bbb.b..ddddd..",
    "..aaaaa.....bbbbb....d.d...",
    ".aaaaaaa.....b.b....dd.dd..",
    "aa..a..aa...bb.bb..........",
    "aa..a..aa...........eeeee..",
    "aaaaaaaaa...ccccc..ee.e.ee.",
    ".aaaaaaa...cc.c.cc.eeeeeee.",
    "..aaaaa....ccccccc..eeeee..",
    "a..aaa..a...ccccc..e.eee.e.",
    ".aaaaaaa...c.ccc.c..eeeee..",
    "...aaa......ccccc....e.e...",
    "..aa.aa......c.c....ee.ee..",
    ".aa...aa....cc.cc..........",
)
"""The logo's five agents, the lead large and four beside it, for beside the wordmark: 27 cells by 9."""
TRUECOLOUR = {"a": "#1862a7", "b": "#389cc3", "c": "#50be74", "d": "#60c664", "e": "#4ece60"}
"""Each pixel's colour, as the icon has it, blue to green. `.` is clear."""
ANSI = {"a": "ansi_blue", "b": "ansi_cyan", "c": "ansi_green", "d": "ansi_bright_green", "e": "ansi_bright_green"}
"""The same gradient in the terminal's own colours, for a theme that keeps to them."""


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
