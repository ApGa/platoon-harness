"""Rows: a list of one-line rows drawn a line at a time, with a cursor on the rows that can be chosen."""

from dataclasses import dataclass

from rich.segment import Segment
from rich.style import Style
from textual import events
from textual.content import Content
from textual.geometry import Region, Size
from textual.message import Message
from textual.scroll_view import ScrollView
from textual.strip import Strip
from textual.timer import Timer

from .keymap import bindings

SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
"""The frames a working agent's glyph turns through while animation is on, eight a second."""
SPIN = 1 / 8


@dataclass(frozen=True)
class Row:
    """One line. A row with no `key` is a heading, which the cursor passes over, and rows that share a key are one
    choice, as a long line wrapped is. Its first `lead` characters decorate it, as a glyph does. A row that `spins`
    turns the character before its lead's last through the spinner's frames."""

    line: Content
    key: str | None = None
    lead: int = 0
    spins: bool = False


def strip_of(line: Content, width: int, style: Style) -> Strip:
    """One line at exactly `width` cells, over `style`: tabs expanded, cut with an ellipsis or padded."""
    fitted = line.expand_tabs().truncate(width, ellipsis=True)
    return Strip(fitted.render_segments(), fitted.cell_length).crop_extend(0, width, style).apply_style(style)


class Rows(ScrollView, can_focus=True):
    """Rows, of which one may be chosen by the keys, a click or the program. Choosing posts `Chosen`."""

    BINDINGS = bindings("list")
    COMPONENT_CLASSES = {"rows--chosen"}
    DEFAULT_CSS = """
    Rows { overflow-x: hidden; scrollbar-size-vertical: 1; }
    Rows > .rows--chosen { background: $accent 25%; text-style: bold; }
    """

    class Chosen(Message):
        def __init__(self, rows: "Rows", key: str) -> None:
            super().__init__()
            self.rows = rows
            self.key = key

    def __init__(self, *, id: str | None = None) -> None:
        super().__init__(id=id)
        self.rows: list[Row] = []
        self.cursor: str | None = None
        self._frame = 0
        self._spinning: Timer | None = None

    def show(self, rows: list[Row]) -> None:
        """Draw these rows, keeping the cursor on its key while that key is shown. The same rows draw nothing."""
        if rows == self.rows:
            return
        self.rows = rows
        keys = self.keys
        if self.cursor not in keys:
            self.cursor = keys[0] if keys else None
        self.virtual_size = Size(0, len(rows))
        self._spin_while(any(row.spins for row in rows) and self.app.animation_level != "none")
        self.refresh()

    def _spin_while(self, spinning: bool) -> None:
        """Turn the spinner while a row spins, and let its timer go once none does. It decides nothing."""
        if spinning and self._spinning is None:
            self._spinning = self.set_interval(SPIN, self._turn)
        elif not spinning and self._spinning is not None:
            self._spinning.stop()
            self._spinning = None

    def _turn(self) -> None:
        self._frame += 1
        self.refresh()

    @property
    def keys(self) -> list[str]:
        return list(dict.fromkeys(row.key for row in self.rows if row.key is not None))

    def move_to(self, key: str) -> None:
        self.cursor = key
        index = next(index for index, row in enumerate(self.rows) if row.key == key)
        self.scroll_to_region(Region(0, index, 1, 1), animate=False, immediate=True, force=True)
        self.refresh()

    def watch_show_vertical_scrollbar(self, shown: bool) -> None:
        """Draw a scrollbar that appears where the rows are, as Textual moves one only when they move."""
        if shown:
            self.vertical_scrollbar.position = self.scroll_y

    def step(self, by: int) -> str | None:
        """The key `by` rows from the cursor, round the ends, or None with nothing to choose."""
        keys = self.keys
        if not keys:
            return None
        at = keys.index(self.cursor) if self.cursor in keys else -by
        return keys[(at + by) % len(keys)]

    def action_cursor_up(self) -> None:
        self._move(-1)

    def action_cursor_down(self) -> None:
        self._move(1)

    def _move(self, by: int) -> None:
        """Choose the row `by` rows on, or scroll rows with none to choose, as the help's are."""
        if (key := self.step(by)) is not None:
            self.move_to(key)
        else:
            self.scroll_relative(y=by, animate=False, immediate=True)

    def action_choose(self) -> None:
        if self.cursor is not None:
            self.post_message(self.Chosen(self, self.cursor))

    def on_click(self, event: events.Click) -> None:
        index = event.get_content_offset_capture(self).y + self.scroll_offset.y
        if 0 <= index < len(self.rows) and (key := self.rows[index].key) is not None:
            self.cursor = key
            self.refresh()
            self.post_message(self.Chosen(self, key))

    def render_line(self, y: int) -> Strip:
        index = y + self.scroll_offset.y
        width = self.scrollable_content_region.width
        if index >= len(self.rows):
            return Strip.blank(width, self.rich_style)
        row = self.rows[index]
        line = row.line
        if row.spins and self._spinning is not None:
            at = row.lead - 2
            line = (
                line[:at] + Content(SPINNER[self._frame % len(SPINNER)], list(line[at : at + 1].spans)) + line[at + 1 :]
            )
        strip = strip_of(line, width, self.rich_style)
        if row.key is not None and row.key == self.cursor:
            strip = Strip(Segment.apply_style(strip, post_style=self.get_component_rich_style("rows--chosen")), width)
        return strip
