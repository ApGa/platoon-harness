"""The transcript: one agent's or one channel's journal, a line per event and a line opens on demand, read from the
journal a page at a time and drawn a line at a time, with what an agent is saying now below it."""

import time
from collections.abc import Iterable
from dataclasses import dataclass
from fnmatch import fnmatchcase
from typing import Any

from rich.console import Console
from rich.markdown import Markdown
from rich.segment import Segment
from textual import events
from textual.cache import LRUCache
from textual.content import Content
from textual.geometry import Region, Size
from textual.message import Message
from textual.scroll_view import ScrollView
from textual.strip import Strip

from platoon_harness import Refused, Session
from platoon_harness.kernel import Delta, Event, Page

from .keymap import bindings
from .rows import CHOSEN, strip_of
from .safe import SafeText, note

PAGE = 256
WINDOW = 10_000
"""The most lines a transcript holds. Past it the far end goes, and is read back from the journal when it comes near."""
BODY_LIMIT = 256 * 1024
_CACHE = 4096
_LINKS = ("http://", "https://")
_HIDDEN = frozenset(
    {
        "usage.reported",
        "model.called",
        "agent.instructed",
        "native.recorded",
        "agent.parked",
        "agent.finished",
        "agent.woken",
    }
)
"""What a transcript leaves out: telemetry, and what another line says already."""


@dataclass(frozen=True)
class Focus:
    """What the focus pane shows: an agent or a channel, read from the journal as the events on the streams it names
    and on those its glob takes. `marks` are the streams a person's mark moves on as they read it, `agent` the one whose
    live text shows below it, `children` the agents it had spawned when it was shown, and `to` the address a message
    goes to, or None for a place that takes none."""

    title: str
    streams: tuple[str, ...] = ()
    match: str | None = None
    marks: tuple[str, ...] = ()
    agent: str | None = None
    children: frozenset[str] = frozenset()
    to: str | None = None

    @classmethod
    def of_agent(cls, name: str, children: Iterable[str] = ()) -> "Focus":
        """An agent, and how each child it spawned began and ended, read from every agent's stream, so a child it
        spawns later is in it too, however many it spawns."""
        streams = (f"inbox/{name}", f"turn/{name}", f"agent/{name}")
        return cls(
            f"@{name}", streams, "agent/*", marks=streams, agent=name, children=frozenset(children), to=f"@{name}"
        )

    @classmethod
    def of_channel(cls, address: str, kind: str) -> "Focus":
        """A channel as `channel.list` names it: `#topic`, `+group`, or a queue's or board's bare name."""
        if kind == "queue":
            return cls(address, match=f"task/{address}/*", marks=(f"queue/{address}",))
        if kind == "board":
            return cls(address, match=f"board/{address}/*", marks=(f"board/{address}",))
        stream = f"channel/{address.removeprefix('#')}"
        return cls(address, streams=(stream,), marks=(stream,), to=address)

    @classmethod
    def of_person(cls, principal: str) -> "Focus":
        """What was sent to the person: their own inbox, which takes no message from them."""
        stream = f"inbox/{principal.partition(':')[2]}"
        return cls(f"@{principal.partition(':')[2]}", streams=(stream,), marks=(stream,))

    @property
    def key(self) -> str:
        return self.title

    def holds(self, event: Event) -> bool:
        return event.stream in self.streams or (self.match is not None and fnmatchcase(event.stream, self.match))


def _address(stream: str) -> str:
    kind, _, name = stream.partition("/")
    return {"inbox": f"@{name}", "channel": name if name.startswith("+") else f"#{name}"}.get(kind, name)


def _who(said: str) -> Content:
    """A sender as a person reads it: `@lead`, `@you`, or the runtime."""
    return SafeText(said if said.startswith("@") or said == "runtime" else f"@{said.partition(':')[2] or said}", "bold")


def line_of(event: Event) -> Content | None:
    """An event as one line, or None for one a transcript leaves out. Any event has a line: its gist, at least."""
    data: dict[str, Any] = event.data if isinstance(event.data, dict) else {}
    gist = SafeText(" ".join(event.gist.split()))
    more = (" ▸", "dim") if data.get("body") else ""
    match event.type:
        case "message.sent":
            sender = data.get("sender", event.actor)
            subject = data.get("subject")
            about = SafeText(f"@{subject} ", "bold") if subject else Content("")
            if sender == "runtime" and subject:
                return Content.assemble(("↩ ", "dim"), about, gist, more)
            return Content.assemble(_who(sender), (" → ", "dim"), SafeText(_address(event.stream)), "  ", gist, more)
        case "item.recorded":
            return _item(event.agent or "", data, gist, more)
        case "turn.started":
            return Content.styled("── turn ──", "dim")
        case "turn.ended":
            reason = data.get("reason", "")
            return None if reason == "stopped" else Content.assemble(("■ turn ", "yellow"), SafeText(reason, "yellow"))
        case "turn.lost":
            return Content.styled("■ turn lost: the runtime went in the middle of it", "red")
        case "agent.ended":
            failed = data.get("status") in ("failed", "lost")
            return Content.assemble(("✗ " if failed else "✓ ", "red" if failed else "green"), gist)
        case "gap.recorded":
            return Content.assemble(("gap ", "yellow"), gist)
        case _ if event.type in _HIDDEN:
            return None
    return Content.assemble(("· ", "dim"), gist, more)


def _item(agent: str, data: dict[str, Any], gist: Content, more: Any) -> Content:
    name = SafeText(f"@{agent}", "bold")
    match data.get("kind"):
        case "message":
            return Content.assemble(name, "  ", gist, more)
        case "thought":
            return Content.assemble(name, (" thinks  ", "dim"), gist.stylize("dim italic"), more)
        case "patch":
            return Content.assemble(("± ", "cyan"), gist, more)
    if data.get("phase") == "started":
        return Content.assemble(("▸ ", "cyan"), gist, more)
    failed = data.get("outcome") not in (None, "completed", "allow")
    return Content.assemble(("✗ " if failed else "✓ ", "red" if failed else "green"), gist, more)


@dataclass(eq=False)
class Block:
    """One line: `first`, the seq of the event that began it, which is where it stands; the event it shows, which a
    tool call's end takes over from its start; and what opening it shows: its body, read when first opened, or its
    gist whole."""

    first: int
    event: Event
    line: Content
    open: bool = False
    text: str | None = None


class Tail:
    """What an agent is saying now: live text the journal does not yet show as an item. A piece the journal holds
    through some seq is dropped once the transcript has drawn that seq, so nothing is shown twice or goes missing. Text
    lost on the way is marked until the journal next takes what was said."""

    def __init__(self) -> None:
        self._held: list[tuple[int | None, str]] = []
        self.lost = False

    def take(self, delta: Delta) -> None:
        if delta.ended is not None:
            self._held = [(delta.ended if end is None else end, text) for end, text in self._held]
        self.lost = delta.lag > 0 or (self.lost and delta.ended is None)
        if delta.text:
            if self._held and self._held[-1][0] is None:
                self._held[-1] = (None, self._held[-1][1] + delta.text)
            else:
                self._held.append((None, delta.text))

    def text(self, through: int) -> str:
        self._held = [(end, text) for end, text in self._held if end is None or end > through]
        said = "".join(text for _, text in self._held)
        return f"… {said}" if said and self.lost else said


def followable(line: Iterable[Segment]) -> list[Segment]:
    """A rendered line whose links are kept only where they go to `http` or `https`."""
    return [
        Segment(text, style.update_link(None))
        if style is not None and style.link and not style.link.startswith(_LINKS)
        else Segment(text, style, control)
        for text, style, control in line
    ]


def markdown(text: str, width: int, console: Console) -> list[Strip]:
    """Markdown and code, readable, as lines at `width`. The text is safe already, and is never read as markup."""
    options = console.options.update(width=max(width, 1), height=None)
    rendered = console.render_lines(Markdown(text, hyperlinks=True), options, pad=False)
    return [Strip(followable(line)) for line in rendered]


class Transcript(ScrollView, can_focus=True):
    """A focus's journal: a window of frozen lines read from the journal a page at a time as the person scrolls, either
    way, drawn through an LRU of strips keyed by width, and below them `tail`, what the agent in view is saying now,
    which the screen keeps. Following is one state, kept here: reading up stops it, and the newest line or the follow
    key starts it again."""

    BINDINGS = [*bindings("transcript"), *bindings("panel")]
    DEFAULT_CSS = "Transcript { overflow-x: hidden; }"

    class Moved(Message):
        """Following started or stopped."""

    def __init__(self, *, id: str | None = None) -> None:
        super().__init__(id=id)
        self.focus_on: Focus | None = None
        self.following = True
        self.unseen = 0
        self.through = 0
        self.tail = Tail()
        self._session: Session | None = None
        self._shown = 0
        self._blocks: list[Block] = []
        self._rows: list[tuple[Block, int]] = []
        self._tools: dict[str, Block] = {}
        self._children: set[str] = set()
        self._before = 0
        self._after: int | None = None
        self._paging = False
        self._placing = False
        self._chosen: Block | None = None
        self._tail_text = ""
        self._tail_lines: list[Strip] = []
        self._lines: LRUCache[tuple[int, int], Strip] = LRUCache(_CACHE)
        self._bodies: LRUCache[tuple[int, int], list[Strip]] = LRUCache(_CACHE // 16)
        self._width = 0

    @property
    def blocks(self) -> list[Block]:
        return self._blocks

    @property
    def chosen(self) -> Block | None:
        """The chosen line: the newest while following, or the one the person chose, or None with no line held."""
        return self._chosen

    async def show(self, focus: Focus, session: Session, through: int) -> None:
        """Show a focus as the journal holds it through `through`, newest first, and follow from there."""
        self.focus_on, self._session, self.through = focus, session, through
        self._begin(before=through + 1, after=None)
        await self.page_back()

    def _begin(self, *, before: int, after: int | None) -> None:
        """Hold no lines, and read them from the journal again: back from `before`, and on from `after` unless it is
        None, which is following. A page read for an earlier beginning is not put in."""
        self._shown += 1
        self._blocks, self._rows, self._tools, self._chosen = [], [], {}, None
        self._children = set(self.focus_on.children) if self.focus_on else set()
        self._before, self._after = before, after
        self.following, self.unseen = after is None, 0
        self._layout()

    def take(self, events: Iterable[Event]) -> int:
        """Add what the follower read past `through`, and say how many lines that drew."""
        added = []
        for event in events:
            if event.seq <= self.through:
                continue
            self.through = event.seq
            if self.focus_on is None or not self.focus_on.holds(event):
                continue
            if self._after is not None:  # The newest lines were let go, and are read again as the person comes down.
                self.unseen += self._line(event) is not None
            elif (block := self._block(event)) is not None:
                added.append(block)
        self._blocks += added
        if added:
            self._rows += [row for block in added for row in self._lines_of(block)]
            if self.following:
                self._chosen = added[-1]
            else:
                self.unseen += len(added)
            self._let_oldest_go()
        self._layout()
        return len(added)

    def _let_oldest_go(self) -> None:
        """Keep the window: past it the oldest lines go, to be read back later, and what is on screen stays. A line goes
        with what lies between its first event and its last, so a tool's line read back finds its end."""
        excess = len(self._blocks) - WINDOW
        if excess <= 0:
            return
        reach = max(block.event.seq for block in self._blocks[:excess])
        while excess < len(self._blocks) - 1 and self._blocks[excess].first < reach:
            reach = max(reach, self._blocks[excess].event.seq)
            excess += 1
        kept = self._blocks[excess]
        rows = next(index for index, (block, _) in enumerate(self._rows) if block is kept)
        del self._blocks[:excess], self._rows[:rows]
        self._before = kept.first
        self._keep_tools()
        if not self.following:
            self._place(max(self.scroll_y - rows, 0))

    def _let_newest_go(self) -> None:
        """Keep the window while reading back: past it the newest lines go, read again when the person comes down."""
        excess = len(self._blocks) - WINDOW
        if excess <= 0:
            return
        gone = self._blocks[-excess:]
        del self._blocks[-excess:]
        self._rows = self._rows[: len(self._rows) - sum(len(self._lines_of(block)) for block in gone)]
        self._keep_tools()
        self._after, self.following = self._blocks[-1].first, False

    def _keep_tools(self) -> None:
        held = set(map(id, self._blocks))
        self._tools = {native: block for native, block in self._tools.items() if id(block) in held}

    def draw(self, tail: Tail) -> None:
        """Lay out again after `take`, with what the agent in view is saying now, at most once a frame."""
        self.tail = tail
        self._layout()

    def _line(self, event: Event) -> Content | None:
        """The line an event makes here, or None: for one a transcript leaves out, and for another agent's own but a
        spawn of this agent's and the end of a child of its."""
        focus = self.focus_on
        if event.type == "agent.spawned" and focus is not None and focus.agent is not None:
            child = event.data.get("name")
            if event.data.get("parent") == f"agent:{focus.agent}":
                self._children.add(child or "")
                return Content.assemble(("  ↳ ", "dim"), SafeText(" ".join(event.gist.split())))
            return line_of(event) if child == focus.agent else None
        theirs = focus is not None and focus.agent is not None and event.agent not in (focus.agent, None)
        if not (theirs and event.stream.startswith("agent/")):
            return line_of(event)
        return line_of(event) if event.type == "agent.ended" and event.agent in self._children else None

    def _block(self, event: Event) -> Block | None:
        """A new line for an event, or None: for one with no line, and for a tool call's end, which its start's line
        becomes when the two name one call. A start read again is the line it began already."""
        line = self._line(event)
        if line is None:
            return None
        native = event.data.get("native_id") if event.type == "item.recorded" else None
        if native and (started := self._tools.get(native)) is not None:
            if event.seq > started.first:
                self._forget(started)
                started.event, started.line = event, line
            return None
        block = Block(event.seq, event, line)
        if native and event.data.get("phase") == "started":
            self._tools[native] = block
        return block

    async def _page(self, *, after: int = 0, before: int | None = None) -> Page | None:
        """A page of the focus's events, or None if it could not be read, which the person is told they missed."""
        focus, session = self.focus_on, self._session
        assert focus is not None and session is not None
        try:
            return await session.page(
                after=after, before=before, streams=focus.streams or None, match=focus.match, limit=PAGE
            )
        except Refused as refused:
            note(self, f"missed lines of {focus.title}: {refused}", severity="error")
            return None

    def _read_again(self) -> None:
        """Read the first page of a beginning whose read a page for an earlier one held up."""
        self.call_later(self.page_forward if self._after is not None else self.page_back)

    async def page_back(self) -> None:
        """Read the page before the oldest line held, and put it above without moving what is on screen."""
        if self._paging or self._before == 0 or self._session is None or self.focus_on is None:
            return
        self._paging, shown = True, self._shown
        try:
            page = await self._page(before=self._before)
        finally:
            self._paging = False
        if shown != self._shown:
            self._read_again()
            return
        if page is None:
            return
        self._before = page.cursor
        older = [block for event in page.events if (block := self._block(event)) is not None]
        self._blocks[:0] = older
        rows = [row for block in older for row in self._lines_of(block)]
        self._rows[:0] = rows
        if self._chosen is None and older:
            self._chosen = older[-1]
        if self.following:
            self._let_oldest_go()
        else:
            self._let_newest_go()
        self._layout()
        if self.following:
            self._place(None)
        elif rows:
            self._place(self.scroll_y + len(rows))
        if (
            self._before
            and len(self._blocks) < WINDOW
            and self.virtual_size.height <= self.scrollable_content_region.height
        ):
            self.call_later(self.page_back)
        self._read_near()

    async def page_forward(self) -> None:
        """Read the page after the newest line held, when newer ones were let go, until it reaches the follower."""
        if self._paging or self._after is None or self._session is None or self.focus_on is None:
            return
        self._paging, shown, after = True, self._shown, self._after
        try:
            page = await self._page(after=after)
        finally:
            self._paging = False
        if shown != self._shown:
            self._read_again()
            return
        if page is None or after != self._after:
            return
        events = [event for event in page.events if event.seq <= self.through]
        newer = [block for event in events if (block := self._block(event)) is not None]
        self._blocks += newer
        self._rows += [row for block in newer for row in self._lines_of(block)]
        self._after = page.cursor if page.cursor < self.through else None
        self._let_oldest_go()
        self._layout()
        self._read_near()

    def _lines_of(self, block: Block) -> list[tuple[Block, int]]:
        return [(block, line) for line in range(1 + (len(self._body(block)) if block.open else 0))]

    def _body(self, block: Block) -> list[Strip]:
        """What an open line shows at this width: its body as Markdown, else its gist whole, then where it came from."""
        key = (block.first, self._width)
        found = self._bodies.get(key)
        if found is None:
            event = block.event
            said = block.text if block.text is not None else SafeText(event.gist).plain
            when = time.strftime("%H:%M:%S", time.localtime(event.wall_time))
            where = SafeText(f"{event.type} · {event.actor} · seq {event.seq} · {when}", "dim")
            lines = [
                *markdown(said, max(self._width - 2, 1), self.app.console),
                Strip(where.render_segments(), where.cell_length),
            ]
            found = self._bodies[key] = [Strip.join([Strip.blank(2), line]) for line in lines]
        return found

    def _forget(self, block: Block) -> None:
        self._lines.discard((block.first, self._width))
        self._bodies.discard((block.first, self._width))

    def toggle(self, block: Block | None = None) -> None:
        """Open or close a line: the chosen one, unless another is named. A body is read when first opened."""
        block = block or self._chosen
        if block is None:
            return
        self._chosen = block
        block.open = not block.open
        ref = block.event.data.get("body") if isinstance(block.event.data, dict) else None
        if block.open and block.text is None and isinstance(ref, str):
            self.run_worker(self._read_body(block, ref), exclusive=False)
        self._relayout()

    async def _read_body(self, block: Block, ref: str) -> None:
        assert self._session is not None
        try:
            found = await self._session.get_body(ref, limit=BODY_LIMIT)
        except Refused as refused:
            block.text = SafeText(f"{block.event.gist}\n\n(the body cannot be read: {refused})").plain
        else:
            cut = "\n\n(cut at 256 KiB)" if len(found) >= BODY_LIMIT else ""
            block.text = SafeText(found.decode(errors="replace") + cut).plain
        self._forget(block)
        self._relayout()

    def _relayout(self) -> None:
        """Lay every line out again, keeping the line at the top of the screen where it is."""
        top = self._rows[int(self.scroll_y)] if self._rows and int(self.scroll_y) < len(self._rows) else None
        self._rows = [row for block in self._blocks for row in self._lines_of(block)]
        self._layout()
        if self.following:
            self._place(None)
        elif top is not None and top in self._rows:
            self._place(self._rows.index(top))

    def _layout(self) -> None:
        width = self.scrollable_content_region.width
        if self._width and width and width != self._width:
            self._width = width
            self._relayout()
            return
        self._width = width or self._width
        text = self.tail.text(self.through) if self._after is None else ""
        if text != self._tail_text:
            self._tail_text = text
            self._tail_lines = markdown(SafeText(text).plain, self._width, self.app.console) if text else []
        self.virtual_size = Size(0, len(self._rows) + len(self._tail_lines))
        if self.following:
            self._place(None)
        self.refresh()

    def _place(self, y: float | None) -> None:
        """Keep the place: move to row `y`, or to the end, as the transcript's own act, which reads no page."""
        self._placing = True
        try:
            if y is None:
                self.scroll_end(animate=False, immediate=True, force=True)
            else:
                self.scroll_to(y=y, animate=False, immediate=True, force=True)
        finally:
            self._placing = False

    def on_resize(self, event: events.Resize) -> None:
        self._layout()

    def watch_show_vertical_scrollbar(self, shown: bool) -> None:
        """Draw a scrollbar that appears where the lines are, as Textual moves one only when they move."""
        if shown:
            self.vertical_scrollbar.position = self.scroll_y

    def watch_scroll_y(self, old_value: float, new_value: float) -> None:
        super().watch_scroll_y(old_value, new_value)
        old, new = old_value, new_value
        if self._placing:
            return
        at_end = new >= self.max_scroll_y
        if new < old and not at_end and self.following:
            self.following = False
            self.post_message(self.Moved())
        elif at_end and not self.following and self._after is None:
            self.following, self.unseen = True, 0
            self.post_message(self.Moved())
        self._read_near()

    def _read_near(self) -> None:
        """Read the next page toward an end the screen is within a screen of, as the person reads toward it."""
        height = self.scrollable_content_region.height
        if self.scroll_y < height and self._before and not self.following:
            self.call_later(self.page_back)
        if self.scroll_y > self.max_scroll_y - height and self._after is not None:
            self.call_later(self.page_forward)

    async def action_follow(self) -> None:
        if self._after is not None and self.focus_on is not None and self._session is not None:
            await self.show(self.focus_on, self._session, self.through)
        self.following, self.unseen = True, 0
        if self._blocks:
            self._chosen = self._blocks[-1]
        self.scroll_end(animate=False, immediate=True, force=True)
        self.post_message(self.Moved())
        self.refresh()

    async def action_oldest(self) -> None:
        """Go to the start of the transcript: the journal's first page, from which newer lines are read again as the
        person comes down."""
        if self._before and self.focus_on is not None and self._session is not None:
            self._begin(before=0, after=0)
            await self.page_forward()
        self.following = False
        if self._blocks:
            self._chosen = self._blocks[0]
        self._place(0)
        self.post_message(self.Moved())
        self.refresh()

    def action_cursor_up(self) -> None:
        self._choose(-1)

    def action_cursor_down(self) -> None:
        self._choose(1)

    def action_open_line(self) -> None:
        self.toggle()

    def _choose(self, by: int) -> None:
        if not self._blocks:
            return
        at = self._blocks.index(self._chosen) if self._chosen in self._blocks else len(self._blocks) - 1
        self._chosen = self._blocks[min(max(at + by, 0), len(self._blocks) - 1)]
        row = self._rows.index((self._chosen, 0))
        if by < 0 and self.following:
            self.following = False
            self.post_message(self.Moved())
        self.scroll_to_region(Region(0, row, 1, 1), animate=False, immediate=True, force=True)
        self.refresh()

    def on_click(self, event: events.Click) -> None:
        index = event.y + int(self.scroll_y)
        if 0 <= index < len(self._rows):
            self.toggle(self._rows[index][0])

    def render_line(self, y: int) -> Strip:
        index = y + int(self.scroll_y)
        width = self.scrollable_content_region.width
        style = self.rich_style
        if index < len(self._rows):
            block, line = self._rows[index]
            if line == 0:
                strip = self._lines.get((block.first, width))
                if strip is None:
                    strip = self._lines[(block.first, width)] = strip_of(block.line, width, style)
                if block is self._chosen and self.has_focus:
                    strip = Strip(Segment.apply_style(strip, post_style=CHOSEN), width)
                return strip
            return self._body(block)[line - 1].crop_extend(0, width, style)
        tail = index - len(self._rows)
        if tail < len(self._tail_lines):
            return self._tail_lines[tail].crop_extend(0, width, style)
        return Strip.blank(width, style)
