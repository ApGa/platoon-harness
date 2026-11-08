"""The transcript: one agent's, one channel's or one thread's journal, a line per event under a heading for each run of
lines one speaker says, and a line opens on demand, read from the journal a page at a time and drawn a line at a time,
with what an agent is saying now below it."""

import asyncio
import bisect
import time
from collections.abc import Iterable
from dataclasses import dataclass
from fnmatch import fnmatchcase
from typing import Any

from markdown_it import MarkdownIt
from rich.console import Console
from rich.markdown import Markdown
from rich.segment import Segment
from textual import events, work
from textual.cache import LRUCache
from textual.content import Content
from textual.geometry import Region, Size
from textual.message import Message
from textual.scroll_view import ScrollView
from textual.selection import Selection
from textual.strip import Strip
from textual.style import Style

from platoon_harness import Refused, Session
from platoon_harness.kernel import Delta, Event, Page
from platoon_harness.primitives import Span
from platoon_harness.tools import NAMESPACE

from .. import approvals
from ..approvals import Ask
from ..calls import UNJOINED, Join
from ..output import safe
from ..provenance import REF_IN_TEXT, shows
from .approvals import rows_of
from .keymap import bindings
from .rows import highlighted, selected, strip_of
from .safe import SafeText, note

PAGE = 256
WINDOW = 10_000
"""The most lines a transcript holds. Past it the far end goes, and is read back from the journal when it comes near."""
BODY_LIMIT = 256 * 1024
_CACHE = 4096
SPACE, HEAD = -2, -1
"""The rows before a line, by their place in a line's rows: a blank one before a new speaker's heading or a rule, and
the heading."""
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
    """What the focus pane shows: an agent, a channel or a thread, read from the journal as the events on the streams it
    names and on those its globs take, and in a thread only its messages. `marks` are the streams a person's mark moves
    on as they read it, `agent` the one whose live text shows below it, `children` the agents it had spawned when it
    was shown, `to` the address a message goes to, or None for a place that takes none, `thread` the thread it shows,
    and `reply_to` the message one sent from it answers."""

    title: str
    streams: tuple[str, ...] = ()
    matches: tuple[str, ...] = ()
    marks: tuple[str, ...] = ()
    agent: str | None = None
    children: frozenset[str] = frozenset()
    to: str | None = None
    thread: str | None = None
    reply_to: Event | None = None

    @classmethod
    def of_agent(cls, name: str, children: Iterable[str] = ()) -> "Focus":
        """An agent, how each child it spawned began, under the call that spawned it, and ended, read from every
        agent's stream, so a child it spawns later is in it too, however many it spawns, and what it asked approval for
        and who answered, read from every approval's stream, as an approval's id is its harness's."""
        streams = (f"inbox/{name}", f"turn/{name}", f"agent/{name}")
        matches = ("agent/*", "approval/*")
        children = frozenset(children)
        return cls(f"@{name}", streams, matches, marks=streams, agent=name, children=children, to=f"@{name}")

    @classmethod
    def of_channel(cls, address: str, kind: str) -> "Focus":
        """A channel as `channel.list` names it: `#topic`, `+group`, or a queue's or board's bare name."""
        if kind == "queue":
            return cls(address, matches=(f"task/{address}/*",), marks=(f"queue/{address}",))
        if kind == "board":
            return cls(address, matches=(f"board/{address}/*",), marks=(f"board/{address}",))
        stream = f"channel/{address.removeprefix('#')}"
        return cls(address, streams=(stream,), marks=(stream,), to=address)

    @classmethod
    def of_person(cls, principal: str) -> "Focus":
        """What was sent to the person: their own inbox, which takes no message from them."""
        stream = f"inbox/{principal.partition(':')[2]}"
        return cls(f"@{principal.partition(':')[2]}", streams=(stream,), marks=(stream,))

    @classmethod
    def of_thread(cls, message: Event, person: str) -> "Focus":
        """The thread `message` is in, or else begins: the message it began with and every message sent in it, on any
        inbox or channel. A message sent from it answers `message`, where the page's Reply sends one: to the topic or
        the group it is on, or to the other of a direct exchange `person` is in. One between others takes none."""
        thread = message.data.get("thread") or shows(message)
        to = _reply_address(message, person.partition(":")[2])
        return cls(f"Thread {thread}", matches=("inbox/*", "channel/*"), to=to, thread=thread, reply_to=message)

    @property
    def key(self) -> str:
        return self.title

    def holds(self, event: Event) -> bool:
        if event.stream not in self.streams and not any(fnmatchcase(event.stream, glob) for glob in self.matches):
            return False
        if self.thread is None:
            return True
        return event.type == "message.sent" and self.thread in (shows(event), event.data.get("thread"))


def replying_to(message: Event) -> str:
    """Whom a reply to `message` answers, as its line names them: its sender, or for a runtime's report, which a reply
    goes to the agent it is about, that report."""
    sender, subject = message.data.get("sender", message.actor), message.data.get("subject")
    return f"the runtime's report on @{subject}" if sender == "runtime" and subject else _who(sender).plain


def _reply_address(message: Event, person: str) -> str | None:
    """Where a reply to `message` goes, as the page's chats take one: the topic or the group it is on, or the other of a
    direct exchange `person` is in, which for a runtime's report is the agent it is about, and nowhere for one between
    others."""
    kind, _, name = message.stream.partition("/")
    if kind == "channel":
        return _address(message.stream)
    pair = {name, message.data.get("subject") or message.data.get("sender", "").removeprefix("@")}
    other = next(iter(pair - {person}), None)
    return f"@{other}" if kind == "inbox" and person in pair and other not in (None, "runtime") else None


async def page_of(session: Session, focus: Focus, *, after: int = 0, before: int | None = None) -> Page:
    """A page of the events a focus holds: a read for each of its globs, the first with its streams, as a read takes
    one glob, kept to what every read covered, so the next page, from its `cursor`, leaves nothing out, and to what the
    focus holds, as a thread holds only its messages."""
    pages = [
        await session.page(
            after=after, before=before, streams=(focus.streams or None) if at == 0 else None, match=glob, limit=PAGE
        )
        for at, glob in enumerate(focus.matches or (None,))
    ]
    if before is None:
        cursor = min(page.cursor for page in pages)
        covered = {event.seq: event for page in pages for event in page.events if event.seq <= cursor}
    else:
        cursor = max(page.cursor for page in pages)
        covered = {event.seq: event for page in pages for event in page.events if event.seq >= cursor}
    events = tuple(covered[seq] for seq in sorted(covered) if focus.holds(covered[seq]))
    return Page(events=events, cursor=cursor, head=max(page.head for page in pages))


def _address(stream: str) -> str:
    kind, _, name = stream.partition("/")
    return {"inbox": f"@{name}", "channel": name if name.startswith("+") else f"#{name}"}.get(kind, name)


def _who(said: str) -> Content:
    """A sender as a person reads it: `@lead`, `@you`, or the runtime."""
    return SafeText(said if said.startswith("@") or said == "runtime" else f"@{said.partition(':')[2] or said}", "bold")


def _words(text: str) -> str:
    """Text as `/find` compares it: its words, whatever their case and the spaces between them."""
    return " ".join(text.split()).casefold()


def _linked(text: Content) -> Content:
    """Text with each ref it names underlined, holding the event that ref names, which a click on it opens."""
    for found in REF_IN_TEXT.finditer(text.plain):
        text = text.stylize(Style(underline=True) + Style.from_meta({"ref": found[1]}), found.start(), found.end())
    return text


_INLINE = MarkdownIt("zero").enable(["emphasis", "backticks", "strikethrough", "escape", "entity"])
"""Markdown within a line: emphasis, code and strikethrough, and nothing that would make it more than one line."""
_STYLES = {"strong": "bold", "em": "italic", "s": "strike"}


def inline(text: str) -> Content:
    """One line of Markdown as it reads, its emphasis, code and strikethrough styled and their marks gone. The text is
    safe already, and is never read as markup."""
    parts: list[tuple[str, str]] = []
    held: list[str] = []
    for token in _INLINE.parseInline(text)[0].children or ():
        kind = token.type.removesuffix("_open").removesuffix("_close")
        if token.type.endswith("_open") and kind in _STYLES:
            held.append(_STYLES[kind])
        elif token.type.endswith("_close") and kind in _STYLES and held:
            held.pop()
        elif token.type == "code_inline":
            parts.append((token.content, " ".join([*held, "$accent"])))
        else:
            parts.append((token.content, " ".join(held)))
    return Content.assemble(*parts)


def _gist(event: Event, style: str = "") -> Content:
    """An event's gist on one line, each ref it names a link."""
    return _linked(SafeText(" ".join(event.gist.split()), style))


def _told(event: Event) -> Content:
    """What an event says, as Markdown read on one line, each ref it names a link."""
    return _linked(inline(SafeText(" ".join(event.gist.split())).plain))


SURFACE = f"mcp__{NAMESPACE}__"
"""What our tools' names begin with on a harness that shows them by MCP, which a line leaves out."""


def tool_named(gist: str) -> tuple[str, str]:
    """A tool item's gist as its name, as its model calls it but for our surface's prefix, and the rest, its input or
    how it ended."""
    name, _, rest = " ".join(gist.split()).partition(" ")
    return name.removeprefix(SURFACE), rest


@dataclass(frozen=True)
class Said:
    """An event as a line: who says it, which a run of lines shares under one heading, or None for a line of the
    runtime's own, which stands alone; the mark before its words, which decorates them; its words; and whether it is
    a rule across the transcript, as a turn's start is."""

    who: Content | None
    mark: Content
    words: Content
    rule: bool = False

    @property
    def text(self) -> Content:
        """The line as words, with who says it."""
        return self.words if self.who is None else Content.assemble(self.who, "  ", self.words)


def _mark(glyph: str, style: str = "") -> Content:
    return Content.styled(f"{glyph} ", style)


NO_MARK = Content("  ")


def line_of(event: Event, started: Event | None = None) -> Said | None:
    """An event as one line, or None for one a transcript leaves out. Any event has a line: its gist, at least, with
    each ref it names a link. A tool call's end takes the input its start, `started`, shows."""
    data: dict[str, Any] = event.data if isinstance(event.data, dict) else {}
    agent = SafeText(f"@{event.agent}", "bold")
    match event.type:
        case "message.sent":
            sender = data.get("sender", event.actor)
            subject = data.get("subject")
            who = Content.assemble(_who(sender), (" → ", "dim"), SafeText(_address(event.stream)))
            if sender == "runtime" and subject:
                return Said(
                    who, _mark("↩", "dim"), Content.assemble(SafeText(f"@{subject}", "bold"), "  ", _told(event))
                )
            return Said(who, NO_MARK, _told(event))
        case "item.recorded":
            return _item(agent, data, event, started)
        case "turn.started":
            return Said(None, Content(""), Content.styled("turn", "dim"), rule=True)
        case "turn.ended":
            reason = data.get("reason", "")
            style = "dim" if reason == "finished" else "$warning"
            return None if reason == "stopped" else Said(None, _mark("■", style), SafeText(f"turn {reason}", style))
        case "turn.lost":
            return Said(
                None, _mark("■", "$error"), Content.styled("turn lost: the runtime went in the middle of it", "$error")
            )
        case "agent.ended":
            failed = data.get("status") in ("failed", "lost")
            return Said(None, _mark("✗" if failed else "✓", "$error" if failed else "$success"), _gist(event))
        case "gap.recorded":
            return Said(None, _mark("!", "$warning"), Content.assemble(("gap ", "$warning"), _gist(event)))
        case "approval.requested":
            asks = Content.assemble(("asks for approval  ", "dim"), _gist(event))
            return Said(agent, _mark("◉", "$warning"), asks)
        case "approval.resolved":
            return _answered(data)
        case _ if event.type in _HIDDEN:
            return None
    return Said(None, _mark("·", "dim"), _gist(event))


def _answered(data: dict[str, Any]) -> Said:
    """Who answered an approval, and how: a person, through what they said, or the role's stated policy."""
    allowed = data.get("verdict") == "allow"
    by = data.get("resolved_by") or ""
    who = Content("policy") if by == "policy" else _who(by)
    via = SafeText(f" via {data['via']}", "dim") if data.get("via") and by != "policy" else Content("")
    said = Content.assemble("allowed by " if allowed else "denied by ", who, via)
    return Said(None, _mark("✓" if allowed else "✗", "$success" if allowed else "$error"), said)


def _cut(span: str) -> Said:
    """Where a span ends and the next of its turn begins, naming the span by its last call."""
    return Said(
        None, Content(""), Content.assemble(("span ", "dim"), SafeText(span, "dim"), (" ends", "dim")), rule=True
    )


def _spawned(event: Event, under: Said | None) -> Said:
    """A child's spawn: under the call that made it, in that call's run, or where the journal has it, led as the
    runtime's own lines are, saying it joins no known call."""
    if under is not None:
        return Said(under.who, _mark("↳", "dim"), _gist(event))
    return Said(None, _mark("·", "dim"), Content.assemble(_gist(event), (f" · {UNJOINED}", "dim")))


def _item(agent: Content, data: dict[str, Any], event: Event, started: Event | None) -> Said:
    match data.get("kind"):
        case "message":
            return Said(agent, NO_MARK, _told(event))
        case "thought":
            return Said(
                agent, _mark("∴", "dim"), Content.assemble(("thinks  ", "dim"), _told(event).stylize("dim italic"))
            )
        case "patch":
            return Said(agent, _mark("±", "$accent"), _gist(event))
    name, rest = tool_named((started or event).gist)
    given = rest and (started is not None or data.get("phase") == "started")
    called = Content.assemble(SafeText(name), *(("  ", SafeText(rest, "dim")) if given else ()))
    if data.get("phase") == "started":
        return Said(agent, _mark("▸", "$accent"), _linked(called))
    outcome = data.get("outcome")
    if outcome in (None, "completed", "allow"):
        return Said(agent, _mark("✓", "$success"), _linked(called))
    return Said(agent, _mark("✗", "$error"), Content.assemble(_linked(called), SafeText(f"  {outcome}", "$error")))


def blank(event: Event) -> bool:
    """Whether an event is what an agent says in its turn with a gist of whitespace alone, which says nothing if its
    body, where it has one, is blank too."""
    data = event.data if isinstance(event.data, dict) else {}
    return event.type == "item.recorded" and data.get("kind") == "message" and not event.gist.strip()


@dataclass(eq=False)
class Block:
    """One line: `first`, the seq of the event that began it, which is where it stands; the event it shows, which a
    tool call's end takes over from its start, and a cut, standing at the next span's first call, is the last call of
    the span it ends; how it reads; and what opening it shows: its body, read when first opened, or its gist whole, or
    for an approval's request, its `ask`, read when first opened."""

    first: int
    event: Event
    said: Said
    open: bool = False
    text: str | None = None
    ask: Ask | None = None

    @property
    def line(self) -> Content:
        """The line as its words read, with who says them: what `/find` looks in and `/copy` sends."""
        return self.said.text

    @property
    def reading(self) -> bool:
        """Whether it is open on what is still being read: an approval's ask, or a body."""
        if not self.open:
            return False
        if self.event.type == "approval.requested":
            return self.ask is None
        data = self.event.data if isinstance(self.event.data, dict) else {}
        return self.text is None and isinstance(data.get("body"), str)


def text_of(block: Block) -> str:
    """A line's text, as `/copy` sends it: what it shows and, while it is open, the text it opens on, or its gist while
    that is being read, as text and never as Markdown, each control shown as its escape."""
    said = [block.line.plain]
    if block.open and block.ask is not None:
        said += [block.ask.gist if block.ask.text is None else block.ask.text]
        said += [] if block.ask.below is None else [block.ask.below]
    elif block.open:
        said += [block.event.gist if block.text is None else block.text]
    return safe("\n".join(said))


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
    key starts it again. An agent's turns are cut where `spans` says, read as the agent is shown and again as each of
    its turns ends, and each cut is drawn once the window holds both calls it stands between. What an agent says in
    its turn with a gist of whitespace alone is read, and drawn as no line once its body is known to be blank too, as
    one with no body is. Text selected with the mouse is copied as its words, without what decorates them."""

    BINDINGS = [*bindings("transcript"), *bindings("panel")]
    COMPONENT_CLASSES = {"transcript--chosen"}
    DEFAULT_CSS = """
    Transcript { overflow-x: hidden; scrollbar-size-vertical: 1; }
    Transcript > .transcript--chosen { background: $accent 22%; }
    """

    class Moved(Message):
        """Following started or stopped."""

    class Named(Message):
        """A ref a line's text names was clicked, which opens that ref's own provenance."""

        def __init__(self, ref: str) -> None:
            super().__init__()
            self.ref = ref

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
        self._join: Join[Block] = Join()
        self._resumed: set[Block] = set()
        self._children: set[str] = set()
        self._calls: dict[str, Event] = {}
        self._cuts: dict[str, str] = {}
        self._cut_at: dict[str, Block] = {}
        self._spans_from: tuple[str | None, Span | None] = (None, None)
        self._before = 0
        self._after: int | None = None
        self._reading = asyncio.Lock()
        self._placing = False
        self._chosen: Block | None = None
        self._tail_text = ""
        self._tail_lines: list[Strip] = []
        self._lines: LRUCache[tuple[int, int], Strip] = LRUCache(_CACHE)
        self._bodies: LRUCache[tuple[int, int], list[Strip]] = LRUCache(_CACHE // 16)
        self._blank: LRUCache[str, bool] = LRUCache(_CACHE)
        self.reading_bodies: dict[str, list[Block]] = {}
        """The bodies being read to learn whether the lines waiting on them say anything."""
        self._width = 0

    def on_mount(self) -> None:
        self.app.theme_changed_signal.subscribe(self, self._themed)

    def _themed(self, _: object) -> None:
        """Draw every line again in the theme's colours, which a strip drawn holds."""
        self._lines.clear()
        self._bodies.clear()
        self.refresh()

    @property
    def blocks(self) -> list[Block]:
        """The lines held, in the journal's order, which is the order they are drawn in but for a spawn drawn under its
        call."""
        return self._blocks

    @property
    def chosen(self) -> Block | None:
        """The chosen line: the last drawn while following, or the one the person chose, or None with no line held."""
        return self._chosen

    async def show(self, focus: Focus, session: Session, through: int) -> None:
        """Show a focus as the journal holds it through `through`, newest first, and follow from there."""
        self.focus_on, self._session, self.through = focus, session, through
        self._cuts, self._spans_from = {}, (None, None)
        self._begin(before=through + 1, after=None)
        self._read_spans()
        await self.page_back()

    def _begin(self, *, before: int, after: int | None) -> None:
        """Hold no lines, and read them from the journal again: back from `before`, and on from `after` unless it is
        None, which is following. A page read for an earlier beginning is not put in."""
        self._shown += 1
        self._blocks, self._rows, self._tools, self._join, self._chosen = [], [], {}, Join(), None
        self._calls, self._cut_at, self._resumed = {}, {}, set()
        self._children = set(self.focus_on.children) if self.focus_on else set()
        self._before, self._after = before, after
        self.following, self.unseen = after is None, 0
        self._layout()

    def take(self, events: Iterable[Event]) -> int:
        """Add what the follower read past `through`, and say how many lines that drew. A turn of the agent in view
        that ends has its cuts read."""
        added, ended = [], False
        for event in events:
            if event.seq <= self.through:
                continue
            self.through = event.seq
            if self.focus_on is None or not self.focus_on.holds(event):
                continue
            ended |= event.type in ("turn.ended", "turn.lost") and event.stream == f"turn/{self.focus_on.agent}"
            if self._after is not None:  # The newest lines were let go, and are read again as the person comes down.
                self.unseen += self._line(event) is not None
            elif (block := self._block(event)) is not None:
                added.append(block)
        if ended:
            self._read_spans()
        self._blocks += added
        if added:
            self._draw(added)
            if self.following:
                self._chosen = self._rows[-1][0]
            else:
                self.unseen += len(added)
            self._let_oldest_go()
        self._layout()
        return len(added)

    def _extent(self, block: Block) -> tuple[int, int]:
        """The first and last seq of what a line goes with: from a tool's start to its end, a call with the spawns
        drawn under it, and a cut from the last call of the span it ends."""
        call = self._join.call_of(block) or block
        seqs = (call.first, call.event.seq, *(spawn.first for spawn in self._join.spawns_of(call)))
        return min(seqs), max(seqs)

    def _let_oldest_go(self) -> None:
        """Keep the window: past it the oldest lines go, to be read back later, and what is on screen stays. A line goes
        with what lies between its first event and its last, so a tool's line read back finds its end, and a call goes
        with the spawns drawn under it."""
        excess = len(self._blocks) - WINDOW
        if excess <= 0:
            return
        reach = max(self._extent(block)[1] for block in self._blocks[:excess])
        while excess < len(self._blocks) - 1 and self._blocks[excess].first <= reach:
            reach = max(reach, self._extent(self._blocks[excess])[1])
            excess += 1
        gone = set(self._blocks[:excess])
        rows = next(index for index, (block, _) in enumerate(self._rows) if block not in gone)
        self._before = self._blocks[excess].first
        del self._blocks[:excess], self._rows[:rows]
        self._keep_held()
        if not self.following:
            self._place(max(self.scroll_y - rows, 0))

    def _let_newest_go(self) -> None:
        """Keep the window while reading back: past it the newest lines go, read again when the person comes down, and
        a spawn drawn under a call goes with it."""
        excess = len(self._blocks) - WINDOW
        if excess <= 0:
            return
        cut = len(self._blocks) - excess
        reach = min(self._extent(block)[0] for block in self._blocks[cut:])
        while cut > 1 and self._blocks[cut - 1].first >= reach:
            cut -= 1
            reach = min(reach, self._extent(self._blocks[cut])[0])
        gone = set(self._blocks[cut:])
        del self._blocks[cut:]
        self._rows = self._rows[: next(index for index, (block, _) in enumerate(self._rows) if block in gone)]
        self._keep_held()
        self._after, self.following = self._blocks[-1].first, False

    def _keep_held(self) -> None:
        """Forget what the window let go: a call is read again with the lines about it."""
        held = set(self._blocks)
        self._tools = {native: block for native, block in self._tools.items() if block in held}
        self._join.keep(held)
        self._cut_at = {start: block for start, block in self._cut_at.items() if block in held}
        self._resumed &= held
        newest = self.through if self._after is None else self._after
        self._calls = {ref: call for ref, call in self._calls.items() if self._before <= call.seq <= newest}

    def draw(self, tail: Tail) -> None:
        """Lay out again after `take`, with what the agent in view is saying now, at most once a frame."""
        self.tail = tail
        self._layout()

    def _line(self, event: Event) -> Said | None:
        """The line an event makes here, or None: for one a transcript leaves out, for what an agent says that is known
        to say nothing, and for another agent's own but a spawn of this agent's, which says it joins no known call until
        it joins one, and the end of a child of its."""
        focus = self.focus_on
        if blank(event) and (not isinstance(body := event.data.get("body"), str) or self._blank.get(body)):
            return None
        if event.type == "agent.spawned" and focus is not None and focus.agent is not None:
            child = event.data.get("name")
            if event.data.get("parent") == f"agent:{focus.agent}":
                self._children.add(child or "")
                return _spawned(event, None)
            return line_of(event) if child == focus.agent else None
        theirs = focus is not None and focus.agent is not None and event.agent not in (focus.agent, None)
        if not (theirs and event.stream.startswith(("agent/", "approval/"))):
            return line_of(event)
        return line_of(event) if event.type == "agent.ended" and event.agent in self._children else None

    def _block(self, event: Event) -> Block | None:
        """A new line for an event, or None: for one with no line, and for a tool call's end, which its start's line
        becomes when the two name one call. A start read again is the line it began already. A spawn joins the call
        that made it, whichever of the two came first, and is drawn under it. A model call of the agent in view is kept,
        and the first of a span is where the span before it ends, cut once that span's last call is held too."""
        if event.type == "model.called":
            return self._cut_before(event)
        line = self._line(event)
        if line is None:
            return None
        native = event.data.get("native_id") if event.type == "item.recorded" else None
        if native and (started := self._tools.get(native)) is not None:
            if event.seq > started.first:
                self._forget(started)
                started.event, started.said = event, line_of(event, started.event) or line
            return None
        block = Block(event.seq, event, line)
        if native and event.data.get("phase") == "started":
            self._tools[native] = block
        if blank(event):
            self._learn(block, event.data["body"])
        self._join.take(event, block)
        joined = self._join.spawns_of(block)
        if self._join.call_of(block) is not None:
            joined.append(block)
        for spawn in joined:
            self._forget(spawn)
            spawn.said = _spawned(spawn.event, call.said if (call := self._join.call_of(spawn)) else None)
        return block

    def _learn(self, block: Block, ref: str) -> None:
        """Read the body of a line whose gist is whitespace alone, once for every line that cites it, to learn whether
        it says anything."""
        waiting = self.reading_bodies.setdefault(ref, [])
        waiting.append(block)
        if len(waiting) == 1:
            self.run_worker(self._read_blank(ref), exclusive=False)

    async def _read_blank(self, ref: str) -> None:
        """Let go of the lines whose body is blank too, which say nothing. A body that cannot be read, or that is cut
        where it is read, is not known to be blank, and its lines stay, opening on what was read."""
        assert self._session is not None
        try:
            found = await self._session.get_body(ref, limit=BODY_LIMIT)
        except Refused:
            self.reading_bodies.pop(ref, None)
            return
        said = found.decode(errors="replace")
        self._blank[ref] = not said.strip() and len(found) < BODY_LIMIT
        waiting = self.reading_bodies.pop(ref, [])
        if not self._blank[ref]:
            for block in waiting:
                block.text = SafeText(said).plain
            return
        gone = set(waiting)
        self._blocks = [block for block in self._blocks if block not in gone]
        if self._chosen in gone:
            self._chosen = self._blocks[-1] if self._blocks and self.following else None
        self._relayout()

    def _cut_before(self, call: Event) -> Block | None:
        """The cut a model call of the agent in view stands at, when it begins a span after another of its turn and
        that span's last call is held, as a new line, or None."""
        if self.focus_on is None or call.stream != f"turn/{self.focus_on.agent}":
            return None
        ref = f"{call.stream}@{call.version}"
        self._calls[ref] = call
        end = self._calls.get(self._cuts.get(ref, ""))
        if end is None or ref in self._cut_at:
            return None
        block = self._cut_at[ref] = Block(call.seq, end, _cut(f"{end.stream}@{end.version}"))
        return block

    def _cut_where_held(self) -> None:
        """Draw each cut whose calls the window holds and that is not drawn yet, as one read back or one `spans` said
        only now, where it stands."""
        drawn = False
        for start in self._cuts:
            if start in self._calls and (block := self._cut_before(self._calls[start])) is not None:
                bisect.insort(self._blocks, block, key=lambda held: held.first)
                drawn = True
        if drawn:
            self._relayout()

    @work(group="spans", exclusive=True)
    async def _read_spans(self) -> None:
        """Read where the agent in view's turns are cut, from the start of the last page read, as only its latest turn
        can be cut again, and draw each cut the window holds."""
        focus, session = self.focus_on, self._session
        if focus is None or focus.agent is None or session is None:
            return
        after, before = began = self._spans_from
        cuts: dict[str, str] = {}
        try:
            while True:
                page, began = await session.spans(f"@{focus.agent}", after=after), (after, before)
                for span in page.spans:
                    if before is not None and before.turn == span.turn:
                        cuts[span.first] = before.ref
                    before = span
                if page.cursor is None:
                    break
                after = page.cursor
        except Refused as refused:
            note(self, f"the cuts of {focus.title}'s turns are not drawn: {refused}", severity="warning")
            return
        if focus is not self.focus_on:
            return
        self._cuts |= cuts
        self._spans_from = began
        self._cut_where_held()

    def _rows_of(self, blocks: Iterable[Block], before: Block | None = None) -> list[tuple[Block, int]]:
        """The rows lines are drawn in, below the line `before`: each where its first event stands, but a spawn joined
        to a call, drawn under it, and each led by the rows that lead it."""
        rows = []
        for block in blocks:
            if self._join.call_of(block) is not None:
                continue
            for line in (block, *self._join.spawns_of(block)):
                rows += self._head(line, before) + self._lines_of(line)
                before = line
        return rows

    def _head(self, block: Block, before: Block | None) -> list[tuple[Block, int]]:
        """The rows that lead a line below `before`: a blank row before a rule or a new speaker's heading, but at the
        top and under a rule, then the heading, for a line whose speaker the line above is not, and for one a page was
        read back above, which keeps the heading it had, so what is on screen does not move."""
        said, above = block.said, None if before is None else before.said
        if said.rule:
            return [] if above is None else [(block, SPACE)]
        if said.who is None:
            return []
        goes_on = above is not None and above.who is not None and above.who.plain == said.who.plain
        if goes_on and block not in self._resumed:
            return []
        return ([] if above is None or above.rule or goes_on else [(block, SPACE)]) + [(block, HEAD)]

    def _draw(self, new: list[Block], *, above: bool = False) -> int:
        """Draw new lines below those held, or `above` them, and say how many rows went above. A spawn joined to a
        call moves the lines it joins, so then all are laid out again, keeping the line at the top of the screen. Lines
        read above keep the heading the line below them has, so what is on screen does not move."""
        if any(self._join.call_of(block) is not None or self._join.spawns_of(block) for block in new):
            self._relayout()
            return 0
        if above:
            rows = self._rows_of(new)
            if self._rows:
                self._resumed.add(self._rows[0][0])
            self._rows[:0] = rows
            return len(rows)
        self._rows += self._rows_of(new, self._rows[-1][0] if self._rows else None)
        return 0

    async def _page(self, *, after: int = 0, before: int | None = None) -> Page | None:
        """A page of the focus's events, or None if it could not be read, which the person is told they missed."""
        focus, session = self.focus_on, self._session
        assert focus is not None and session is not None
        try:
            return await page_of(session, focus, after=after, before=before)
        except Refused as refused:
            note(self, f"missed lines of {focus.title}: {refused}", severity="error")
            return None

    def _read_again(self) -> None:
        """Read the first page of a beginning whose read a page for an earlier one held up."""
        self.call_later(self.page_forward if self._after is not None else self.page_back)

    async def page_back(self) -> None:
        """Read the page before the oldest line held, and put it above without moving what is on screen."""
        if self._reading.locked() or self._before == 0 or self._session is None or self.focus_on is None:
            return
        shown = self._shown
        async with self._reading:
            page = await self._page(before=self._before)
        if shown != self._shown:
            self._read_again()
            return
        if page is None:
            return
        self._before = page.cursor
        older = [block for event in page.events if (block := self._block(event)) is not None]
        self._blocks[:0] = older
        rows = self._draw(older, above=True)
        if self._chosen is None and older:
            self._chosen = self._rows[-1][0]
        if self.following:
            self._let_oldest_go()
        else:
            self._let_newest_go()
        self._layout()
        if self.following:
            self._place(None)
        elif rows:
            self._place(self.scroll_y + rows)
        self._cut_where_held()
        if (
            self._before
            and len(self._blocks) < WINDOW
            and self.virtual_size.height <= self.scrollable_content_region.height
        ):
            self.call_later(self.page_back)
        self._read_near()

    async def page_forward(self) -> None:
        """Read the page after the newest line held, when newer ones were let go, until it reaches the follower."""
        if self._reading.locked() or self._after is None or self._session is None or self.focus_on is None:
            return
        shown, after = self._shown, self._after
        async with self._reading:
            page = await self._page(after=after)
        if shown != self._shown:
            self._read_again()
            return
        if page is None or after != self._after:
            return
        events = [event for event in page.events if event.seq <= self.through]
        newer = [block for event in events if (block := self._block(event)) is not None]
        self._blocks += newer
        self._draw(newer)
        self._after = page.cursor if page.cursor < self.through else None
        self._let_oldest_go()
        self._layout()
        self._read_near()

    def _lines_of(self, block: Block) -> list[tuple[Block, int]]:
        return [(block, line) for line in range(1 + (len(self._body(block)) if block.open else 0))]

    def _indent(self, block: Block) -> int:
        """How far a line stands in: under its speaker's heading, and a spawn under its call further."""
        return (2 if block.said.who is not None else 0) + (2 if self._join.call_of(block) is not None else 0)

    def _body(self, block: Block) -> list[Strip]:
        """What an open line shows at this width, under its words: its body as Markdown, else its gist whole, or an
        approval's ask as it was asked, then where it came from, with a tool's whole name."""
        key = (block.first, self._width)
        found = self._bodies.get(key)
        if found is None:
            event, indent = block.event, self._indent(block) + 2
            width = max(self._width - indent, 1)
            if block.ask is not None:
                lines = [Strip(row.line.render_segments(), row.line.cell_length) for row in rows_of(block.ask, width)]
            else:
                said = block.text if block.text is not None else SafeText(event.gist).plain
                lines = markdown(said, width, self.app.console)
            when = time.strftime("%H:%M:%S", time.localtime(event.wall_time))
            data = event.data if isinstance(event.data, dict) else {}
            tool = f" · tool {event.gist.split()[0]}" if data.get("kind") == "tool" and event.gist.split() else ""
            where = SafeText(f"{event.type}{tool} · {event.actor} · seq {event.seq} · {when}", "dim")
            lines.append(Strip(where.render_segments(), where.cell_length))
            found = self._bodies[key] = [Strip.join([Strip.blank(indent), line]) for line in lines]
        return found

    def _forget(self, block: Block) -> None:
        self._lines.discard((block.first, self._width))
        self._bodies.discard((block.first, self._width))

    def toggle(self, block: Block | None = None) -> None:
        """Open or close a line: the chosen one, unless another is named. A body, or an approval's ask, is read when
        first opened."""
        block = block or self._chosen
        if block is None:
            return
        self._chosen = block
        block.open = not block.open
        ref = block.event.data.get("body") if isinstance(block.event.data, dict) else None
        if block.open and block.event.type == "approval.requested" and block.ask is None:
            self.run_worker(self._read_ask(block), exclusive=False)
        elif block.open and block.text is None and isinstance(ref, str):
            self.run_worker(self._read_body(block, ref), exclusive=False)
        self._relayout()

    async def _read_ask(self, block: Block) -> None:
        assert self._session is not None
        block.ask = await approvals.read(self._session, block.event)
        self._forget(block)
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
        """Lay every line out again, keeping the line at the top of the screen where it is, or where the row above it
        went, the line it led."""
        top = self._rows[int(self.scroll_y)] if self._rows and int(self.scroll_y) < len(self._rows) else None
        self._rows = self._rows_of(self._blocks)
        self._layout()
        if self.following:
            self._place(None)
        elif top is not None and (kept := top if top in self._rows else (top[0], 0)) in self._rows:
            self._place(self._rows.index(kept))

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
        if self._rows:
            self._chosen = self._rows[-1][0]
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
        if self._rows:
            self._chosen = self._rows[0][0]
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
        """Choose the line `by` lines on, as they are drawn."""
        lines = self._drawn()
        if not lines:
            return
        at = lines.index(self._chosen) if self._chosen in lines else len(lines) - 1
        if by < 0:
            self._stop_following()
        self._go_to(lines[min(max(at + by, 0), len(lines) - 1)])

    def _drawn(self) -> list[Block]:
        """The lines held, as they are drawn."""
        return [block for block, line in self._rows if line == 0]

    def _go_to(self, block: Block) -> None:
        """Choose a line, and scroll it into view."""
        self._chosen = block
        row = self._rows.index((block, 0))
        self.scroll_to_region(Region(0, row, 1, 1), animate=False, immediate=True, force=True)
        self.refresh()

    def _stop_following(self) -> None:
        if self.following:
            self.following = False
            self.post_message(self.Moved())

    @work(group="find", exclusive=True)
    async def find(self, words: str) -> None:
        """Choose the line drawn before the chosen one whose words hold `words`, whatever their case and spacing,
        reading back from the journal a page at a time, as scrolling up does, until one does. A line's words are what it
        shows, and not a body it opens on. Each line is looked at once, and a read under way puts its page in first.
        Where none does back to the focus's first line it says so, and goes back to following, or else to the line it
        began from, or where reading back let that go from the window, to the oldest line held. Reading the focus anew
        stops it, saying nothing, and a page the journal would not give, which is said as lines missed."""
        said, start, last = _words(words), self._chosen, None
        followed, shown = self.following, self._shown
        while True:
            lines = self._drawn()
            at = next((lines.index(block) for block in (last, start) if block in lines), len(lines))
            for block in reversed(lines[:at]):
                last = block
                if said in _words(block.line.plain):
                    self._stop_following()
                    self._go_to(block)
                    return
            if not self._before:
                break
            self._stop_following()
            self._place(0)
            async with self._reading:  # A read under way puts its page in before this one reads on.
                pass
            before = self._before
            await self.page_back()
            if shown != self._shown or self._before == before:  # Read anew, or a page missed, which is said.
                return
        focus = self.focus_on.title if self.focus_on else "the focus"
        note(self, f"No line before the chosen one holds “{words}”, back to the first line of {focus}.")
        lines = self._drawn()
        if followed and not self.following:
            await self.action_follow()
        elif lines:
            self._go_to(start if start in lines else lines[0])

    def on_click(self, event: events.Click) -> None:
        """Choose the line clicked, open or close it when it is chosen already, or on a ref its text names, open that
        ref's provenance. A click that ends a drag selecting text does none of these."""
        if self.text_selection is not None:
            return
        if (ref := event.style.meta.get("ref")) is not None:
            self.post_message(self.Named(ref))
            return
        index = event.get_content_offset_capture(self).y + int(self.scroll_y)
        if not 0 <= index < len(self._rows) or self._rows[index][1] == SPACE:
            return
        block = self._rows[index][0]
        if block is self._chosen:
            self.toggle(block)
            return
        self._stop_following()
        self._chosen = block
        self.refresh()
        self.post_message(self.Moved())

    def _as_drawn(self, block: Block, width: int) -> Content:
        """A line as it is drawn: in from the left under its speaker, its mark, its words, and `▸` where it opens on a
        body, or a rule across the width."""
        said = block.said
        if said.rule:
            return Content.assemble(
                ("── ", "dim"), said.words, " ", ("─" * max(width - said.words.cell_length - 4, 0), "dim")
            )
        data = block.event.data if isinstance(block.event.data, dict) else {}
        more = (" ▸", "dim") if data.get("body") else ""
        return Content.assemble(" " * self._indent(block), said.mark, said.words, more)

    def _strip(self, block: Block, line: int, width: int) -> Strip:
        style = self.rich_style
        if line == SPACE:
            return Strip.blank(width, style)
        if line == HEAD:
            assert block.said.who is not None
            return strip_of(block.said.who, width, style)
        if line > 0:
            return self._body(block)[line - 1].crop_extend(0, width, style).apply_style(style)
        strip = self._lines.get((block.first, width))
        if strip is None:
            strip = self._lines[(block.first, width)] = strip_of(self._as_drawn(block, width), width, style)
        if block is self._chosen and self.has_focus:
            strip = Strip(
                Segment.apply_style(strip, post_style=self.get_component_rich_style("transcript--chosen")), width
            )
        return strip

    def _words_of(self, index: int) -> tuple[str, int]:
        """A row's words, and how many characters of what decorates them lead them: its speaker, its line's words past
        its mark, its body past its indent, or what is being said now."""
        if index >= len(self._rows):
            tail = index - len(self._rows)
            return (self._tail_lines[tail].text, 0) if tail < len(self._tail_lines) else ("", 0)
        block, line = self._rows[index]
        said = block.said
        if line == SPACE:
            return "", 0
        if line == HEAD:
            return (said.who.plain if said.who else ""), 0
        if line > 0:
            indent = self._indent(block) + 2
            return self._body(block)[line - 1].text[indent:], indent
        if said.rule:
            return said.words.plain, 3
        return said.words.plain, self._indent(block) + said.mark.cell_length

    def get_selection(self, selection: Selection) -> tuple[str, str] | None:
        """The words of the rows selected, without the marks, rules and indents that decorate them."""
        return selected(selection, len(self._rows) + len(self._tail_lines), self._words_of), "\n"

    def selection_updated(self, selection: Selection | None) -> None:
        self.refresh()

    def render_line(self, y: int) -> Strip:
        index = y + int(self.scroll_y)
        width = self.scrollable_content_region.width
        if index < len(self._rows):
            strip = self._strip(*self._rows[index], width)
        elif (tail := index - len(self._rows)) < len(self._tail_lines):
            strip = self._tail_lines[tail].crop_extend(0, width, self.rich_style).apply_style(self.rich_style)
        else:
            return Strip.blank(width, self.rich_style)
        if (selection := self.text_selection) is not None:
            screen = self.screen.get_component_rich_style("screen--selection")
            strip = highlighted(strip, selection.get_span(index), screen)
        return strip.apply_offsets(0, index)
