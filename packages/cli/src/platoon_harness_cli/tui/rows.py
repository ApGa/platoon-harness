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

from .keymap import bindings

CHOSEN = Style(reverse=True)


@dataclass(frozen=True)
class Row:
    """One line. A row with no `key` is a heading, which the cursor passes over."""

    line: Content
    key: str | None = None


def strip_of(line: Content, width: int, style: Style) -> Strip:
    """One line at exactly `width` cells: tabs expanded, cut with an ellipsis or padded."""
    fitted = line.expand_tabs().truncate(width, ellipsis=True)
    return Strip(fitted.render_segments(), fitted.cell_length).crop_extend(0, width, style)


class Rows(ScrollView, can_focus=True):
    """Rows, of which one may be chosen by the keys, a click or the program. Choosing posts `Chosen`."""

    BINDINGS = bindings("list")
    DEFAULT_CSS = "Rows { overflow-x: hidden; }"

    class Chosen(Message):
        def __init__(self, rows: "Rows", key: str) -> None:
            super().__init__()
            self.rows = rows
            self.key = key

    def __init__(self, *, id: str | None = None) -> None:
        super().__init__(id=id)
        self.rows: list[Row] = []
        self.cursor: str | None = None

    def show(self, rows: list[Row]) -> None:
        """Draw these rows, keeping the cursor on its key while that key is shown. The same rows draw nothing."""
        if rows == self.rows:
            return
        self.rows = rows
        keys = [row.key for row in rows if row.key is not None]
        if self.cursor not in keys:
            self.cursor = keys[0] if keys else None
        self.virtual_size = Size(0, len(rows))
        self.refresh()

    @property
    def keys(self) -> list[str]:
        return [row.key for row in self.rows if row.key is not None]

    def move_to(self, key: str) -> None:
        self.cursor = key
        index = next(index for index, row in enumerate(self.rows) if row.key == key)
        self.scroll_to_region(Region(0, index, 1, 1), animate=False, immediate=True, force=True)
        self.refresh()

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
        index = event.y + self.scroll_offset.y
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
        strip = strip_of(row.line, width, self.rich_style)
        if row.key is not None and row.key == self.cursor:
            strip = Strip(Segment.apply_style(strip, post_style=CHOSEN), width)
        return strip
