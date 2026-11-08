"""Rows: a list of one-line rows drawn a line at a time, with a cursor on the rows that can be chosen, and text a
person selects with the mouse copied as plain text."""

from collections.abc import Callable
from dataclasses import dataclass

from rich.cells import cell_len
from rich.segment import Segment
from rich.style import Style
from textual import events
from textual.cache import LRUCache
from textual.content import Content
from textual.geometry import Region, Size
from textual.message import Message
from textual.scroll_view import ScrollView
from textual.selection import Selection
from textual.strip import Strip
from textual.timer import Timer

from .keymap import bindings

SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
"""The frames a working agent's glyph turns through while animation is on, eight a second."""
SPIN = 1 / 8


@dataclass(frozen=True)
class Row:
    """One line. A row with no `key` is a heading, which the cursor passes over, and rows that share a key are one
    choice, as a long line wrapped is. Its first `lead` characters decorate it, as a glyph does, and a selection copies
    none of them. A row that `spins` turns the character before its lead's last through the spinner's frames."""

    line: Content
    key: str | None = None
    lead: int = 0
    spins: bool = False


def strip_of(line: Content, width: int, style: Style) -> Strip:
    """One line at exactly `width` cells, over `style`: tabs expanded, cut with an ellipsis or padded."""
    fitted = line.expand_tabs().truncate(width, ellipsis=True)
    return Strip(fitted.render_segments(), fitted.cell_length).crop_extend(0, width, style).apply_style(style)


def picked(words: str, lead: int, span: tuple[int, int]) -> str:
    """What a selection's span of a row takes of its words, which begin `lead` characters in: the span counts characters
    from the row's start, and to its end takes the words whole, past where a row cut short shows them."""
    start, end = span
    return words[max(start - lead, 0) :] if end == -1 else words[max(start - lead, 0) : max(end - lead, 0)]


def selected(selection: Selection, count: int, words: Callable[[int], tuple[str, int]]) -> str:
    """The text a selection takes of `count` rows, a line each, each row's words and lead as `words` gives them."""
    first = 0 if selection.start is None else selection.start.y
    last = count - 1 if selection.end is None else min(selection.end.y, count - 1)
    taken = []
    for y in range(first, last + 1):
        if (span := selection.get_span(y)) is not None:
            taken.append(picked(*words(y), span).rstrip())
    return "\n".join(taken)


def highlighted(strip: Strip, span: tuple[int, int] | None, style: Style) -> Strip:
    """A row with the characters a selection's span takes of it drawn in the selection's style."""
    if span is None:
        return strip
    text = strip.text
    start, end = span
    first, last = cell_len(text[:start]), cell_len(text if end == -1 else text[:end])
    if first >= last:
        return strip
    middle = Strip(Segment.apply_style(strip.crop(first, last), post_style=style), last - first)
    return Strip.join([strip.crop(0, first), middle, strip.crop(last, strip.cell_length)])


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
        self._drawn: LRUCache[tuple[int, int, bool, Style], Strip] = LRUCache(1024)

    def on_mount(self) -> None:
        self.app.theme_changed_signal.subscribe(self, self._themed)

    def _themed(self, _: object) -> None:
        """Draw every row again in the theme's colours, which a strip drawn holds."""
        self._drawn.clear()
        self.refresh()

    def show(self, rows: list[Row]) -> None:
        """Draw these rows, keeping the cursor on its key while that key is shown. The same rows draw nothing."""
        if rows == self.rows:
            return
        self.rows = rows
        self._drawn.clear()
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
        """Turn each spinning row's glyph a frame, drawing those rows alone."""
        self._frame += 1
        for index, row in enumerate(self.rows):
            if row.spins:
                self.refresh_lines(index)

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
        """Choose the row clicked, unless the mouse was dragged to select text."""
        if self.text_selection is not None:
            return
        index = event.get_content_offset_capture(self).y + self.scroll_offset.y
        if 0 <= index < len(self.rows) and (key := self.rows[index].key) is not None:
            self.cursor = key
            self.refresh()
            self.post_message(self.Chosen(self, key))

    def get_selection(self, selection: Selection) -> tuple[str, str] | None:
        """The words of the rows selected, without what decorates them."""

        def words(y: int) -> tuple[str, int]:
            row = self.rows[y]
            return row.line.plain[row.lead :], row.lead

        return selected(selection, len(self.rows), words), "\n"

    def selection_updated(self, selection: Selection | None) -> None:
        self.refresh()

    def render_line(self, y: int) -> Strip:
        index = y + self.scroll_offset.y
        width = self.scrollable_content_region.width
        if index >= len(self.rows):
            return Strip.blank(width, self.rich_style)
        row = self.rows[index]
        chosen = row.key is not None and row.key == self.cursor
        spinning = row.spins and self._spinning is not None
        key = (index, width, chosen, self.rich_style)
        strip = None if spinning else self._drawn.get(key)
        if strip is None:
            line = row.line
            if spinning:
                at = row.lead - 2
                frame = Content(SPINNER[self._frame % len(SPINNER)], list(line[at : at + 1].spans))
                line = line[:at] + frame + line[at + 1 :]
            strip = strip_of(line, width, self.rich_style)
            if chosen:
                strip = Strip(
                    Segment.apply_style(strip, post_style=self.get_component_rich_style("rows--chosen")), width
                )
            if not spinning:
                self._drawn[key] = strip
        if (selection := self.text_selection) is not None:
            strip = highlighted(
                strip, selection.get_span(index), self.screen.get_component_rich_style("screen--selection")
            )
        return strip.apply_offsets(0, index)
