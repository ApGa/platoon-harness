"""The transcript: one agent's, one channel's or one thread's journal, a line per event under a heading for each run of
lines one speaker says, what an agent did in a turn besides what it said folded into one line that counts it, and a line
opening on demand, read from the journal a page at a time and drawn a line at a time, with what an agent is saying now
below it."""

import asyncio
import bisect
import contextlib
import json
import time
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
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
GUTTER = 1
"""The column left of every row, where `▌` marks the chosen line while the transcript has focus."""
SHUT, OPENED = "▸", "▾"
"""What a line that opens on more than it shows is led by, or ends with, closed and open; a click on it opens or
closes it."""
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
_STEPS = frozenset({"tool", "thought", "patch"})
"""The items that are what an agent did in a turn, as opposed to what it said."""
_ENDED = ("turn.ended", "turn.lost")
_DONE = (None, "completed", "allow")
"""A tool's outcomes that are no failure."""


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
    """One line of Markdown as it reads, its emphasis, code and strikethrough styled and their marks gone, made safe
    once read, so that what an escape or an entity decodes to is shown as its escape too, and never read as markup."""
    parts: list[tuple[str, str]] = []
    held: list[str] = []
    for token in _INLINE.parseInline(text)[0].children or ():
        kind = token.type.removesuffix("_open").removesuffix("_close")
        if token.type.endswith("_open") and kind in _STYLES:
            held.append(_STYLES[kind])
        elif token.type.endswith("_close") and kind in _STYLES and held:
            held.pop()
        elif token.type == "code_inline":
            parts.append((safe(token.content), " ".join([*held, "$accent"])))
        else:
            parts.append((safe(token.content), " ".join(held)))
    return Content.assemble(*parts)


def _gist(event: Event, style: str = "") -> Content:
    """An event's gist on one line, each ref it names a link."""
    return _linked(SafeText(" ".join(event.gist.split()), style))


def _told(event: Event) -> Content:
    """What an event says, as Markdown read on one line, each ref it names a link."""
    return _linked(inline(" ".join(event.gist.split())))


SURFACE = f"mcp__{NAMESPACE}__"
"""What our tools' names begin with on a harness that shows them by MCP, which a line leaves out."""


def tool_named(gist: str) -> tuple[str | None, str]:
    """A tool item's gist as the name of the tool its model called, but for our surface's prefix, and its input, where
    its first word is followed by its input as JSON, as a model's call is reported. Any other gist, such as a command a
    harness ran, names no tool, and is its words whole."""
    said = " ".join(gist.split())
    name, _, rest = said.partition(" ")
    return (name.removeprefix(SURFACE), rest) if rest.startswith("{") else (None, said)


def summary(given: str) -> str:
    """A tool's input in short: the values of its JSON object, a string as it reads, or the input as it is given
    where it is no whole JSON object, as a gist cut short is not."""
    try:
        found = json.loads(given)
    except ValueError:
        return given
    if not isinstance(found, dict):
        return given

    def flat(value: Any) -> str:
        if isinstance(value, str):
            return " ".join(value.split())
        if isinstance(value, list):
            return ", ".join(map(flat, value))
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))

    return "  ".join(flat(value) for value in found.values())


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


NO_MARK = Content("")


def line_of(event: Event, started: Event | None = None) -> Said | None:
    """An event as one line, or None for one a transcript leaves out. Any event has a line: its gist, at least, with
    each ref it names a link. A tool call's end takes the input its start, `started`, shows."""
    data: dict[str, Any] = event.data if isinstance(event.data, dict) else {}
    agent = SafeText(f"@{event.agent}", "bold")
    match event.type:
        case "message.sent":
            sender = data.get("sender", event.actor)
            subject = data.get("subject")
            who = Content.assemble(_who(sender), (" → ", "dim"), SafeText(_address(event.stream), "dim"))
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
    return Said(None, _mark("·", "dim"), _gist(event, "dim"))


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
        return Said(under.who, _mark("↳", "dim"), _gist(event, "dim"))
    return Said(None, _mark("·", "dim"), Content.assemble(_gist(event, "dim"), (f" · {UNJOINED}", "dim")))


def _item(agent: Content, data: dict[str, Any], event: Event, started: Event | None) -> Said:
    """What an agent said, or did: a tool call or a patch by the tool's name and its input in short where its gist names
    one, or else its words whole, and how it ended where that is no success, or a thought, dim."""
    match data.get("kind"):
        case "message":
            return Said(agent, NO_MARK, _told(event))
        case "thought":
            return Said(agent, NO_MARK, Content.assemble(("∴ ", "dim"), _told(event).stylize("dim italic")))
    name, given = tool_named((started or event).gist)
    outcome = data.get("outcome") if data.get("phase") == "completed" else None
    if name is not None:
        called = Content.assemble(SafeText(name), "  ", SafeText(summary(given), "dim"))
    else:
        called = SafeText(given.removesuffix(f" {outcome}") if started is None and outcome else given)
    if data.get("kind") == "patch":
        called = Content.assemble(("± ", "dim"), called)
    if outcome in _DONE:
        return Said(agent, NO_MARK, _linked(called))
    return Said(agent, NO_MARK, Content.assemble(_linked(called), SafeText(f"  ✗ {outcome}", "$error")))


def blank(event: Event) -> bool:
    """Whether an event is what an agent says in its turn with a gist of whitespace alone, which says nothing if its
    body, where it has one, is blank too."""
    data = event.data if isinstance(event.data, dict) else {}
    return event.type == "item.recorded" and data.get("kind") == "message" and not event.gist.strip()


def _step(event: Event, children: set[str], agent: str | None) -> str | None:
    """The turn whose fold an event is a step of, or None: a tool call, a patch or a thought of an agent's, a spawn of
    a child of `agent`'s, or a turn's end that says it finished, each in the turn the record names."""
    data = event.data if isinstance(event.data, dict) else {}
    if event.turn is None:
        return None
    if event.type == "item.recorded" and data.get("kind") in _STEPS:
        return event.turn
    if event.type == "agent.spawned" and agent is not None and data.get("parent") == f"agent:{agent}":
        return event.turn
    if event.type == "turn.ended" and data.get("reason") == "finished":
        return event.turn
    return None


@dataclass(eq=False)
class Block:
    """One line: `first`, the seq of the event that began it, which is where it stands; the event it shows, which a
    tool call's end takes over from its start, `start`, and a cut, standing at the next span's first call, is the last
    call of the span it ends; how it reads; and what opening it shows: its body, read when first opened, or its gist
    whole, or for an approval's request, its `ask`, read when first opened, or for a call its input and what it gave
    back. A step of an agent's turn stands in that turn's `fold`."""

    first: int
    event: Event
    said: Said
    open: bool = False
    text: str | None = None
    ask: Ask | None = None
    start: Event | None = None
    fold: "Fold | None" = None

    @property
    def line(self) -> Content:
        """The line as its words read, with who says them: what `/find` looks in and `/copy` sends."""
        return self.said.text

    @property
    def reading(self) -> bool:
        """Whether it is open on what is still being read: an approval's ask, or a body."""
        if not self.open or isinstance(self, Fold):
            return False
        if self.event.type == "approval.requested":
            return self.ask is None
        return self.text is None and (_called(self) or bool(_refs(self)))


@dataclass(eq=False)
class Fold(Block):
    """What an agent did in one turn besides what it said, as one line that counts it: its `steps`, the tool calls,
    patches, thoughts and spawns of the turn the transcript holds, and the cuts and the end drawn among them, which are
    drawn only while it is open."""

    turn: str = ""
    steps: list[Block] = field(default_factory=list)


def _counted(step: Block) -> bool:
    """Whether a fold counts a step: a call, a patch, a thought or a spawn, and not a cut or a turn's end."""
    return step.event.type in ("item.recorded", "agent.spawned") and not step.said.rule


def _refs(block: Block) -> list[str]:
    """The body opening a line reads, where its event has one."""
    data = block.event.data if isinstance(block.event.data, dict) else {}
    return [data["body"]] if isinstance(data.get("body"), str) else []


def _phase(event: Event | None) -> str | None:
    return event.data.get("phase") if event is not None and isinstance(event.data, dict) else None


def _did(block: Block) -> bool:
    """Whether a line is of what an agent did rather than what it said: a call, a patch, a thought or a spawn."""
    data = block.event.data if isinstance(block.event.data, dict) else {}
    return block.event.type == "agent.spawned" or (block.event.type == "item.recorded" and data.get("kind") in _STEPS)


def _called(block: Block) -> bool:
    data = block.event.data if isinstance(block.event.data, dict) else {}
    return block.event.type == "item.recorded" and data.get("kind") in ("tool", "patch")


def text_of(block: Block, line: Content | None = None) -> str:
    """A line's text, as `/copy` sends it: what it shows, `line` where it is drawn, and while it is open, the text it
    opens on, or its gist while that is being read, as text and never as Markdown, each control shown as its escape."""
    shown = block.line if line is None else line
    said = [shown.plain]
    if block.open and block.ask is not None:
        said += [block.ask.gist if block.ask.text is None else block.ask.text]
        said += [] if block.ask.below is None else [block.ask.below]
    elif block.open and not isinstance(block, Fold):
        said += [block.event.gist if block.text is None else block.text]
    return safe("\n".join(said))


def _read_as(found: bytes) -> str:
    """A body as read, saying where it was cut."""
    return found.decode(errors="replace") + ("\n\n(cut at 256 KiB)" if len(found) >= BODY_LIMIT else "")


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


def plain(text: str, width: int) -> list[Strip]:
    """Text as it is, each line wrapped at `width`, a line that is exactly `input` or `output` dim as a label. The text
    is safe already, and is never read as markup or as Markdown."""
    lines = []
    for said in text.split("\n"):
        content = Content.styled(said, "dim") if said in ("input", "output") else Content(said)
        lines += [Strip(row.render_segments(), row.cell_length) for row in content.wrap(max(width, 1)) or [content]]
    return lines


class Transcript(ScrollView, can_focus=True):
    """A focus's journal: a window of frozen lines read from the journal a page at a time as the person scrolls, either
    way, drawn through an LRU of strips keyed by width, and below them `tail`, what the agent in view is saying now,
    which the screen keeps. Following is one state, kept here: reading up stops it, and the newest line or the follow
    key starts it again. What an agent did in a turn besides what it said, its calls, patches, thoughts and spawns,
    is a fold of the turn, drawn as one line that counts them, which opens on them, each a line that opens on its
    whole; a turn under way while the session is live shows its latest step too, and `unfolded` opens every fold. A
    line is laid out again alone, or with the lines of its fold, when it opens or closes, and so is a fold that takes
    a step. An agent's turns are cut where `spans` says, read as the agent is shown and again as each of its turns
    ends, and each cut is drawn once the window holds both calls it stands between. What an agent says in its turn
    with a gist of whitespace alone is read, and drawn as no line once its body is known to be blank too, as one with
    no body is. Text selected with the mouse is copied as its words, without what decorates them."""

    BINDINGS = [*bindings("transcript"), *bindings("panel")]
    """The transcript's own keys first, so its Esc closes a line before it goes back to the composer."""
    COMPONENT_CLASSES = {"transcript--chosen", "transcript--marker"}
    DEFAULT_CSS = """
    Transcript { overflow-x: hidden; scrollbar-size-vertical: 1; }
    Transcript > .transcript--chosen { background: $accent 18%; }
    Transcript > .transcript--marker { color: $accent; }
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
        self.live = False
        """Whether a runtime holds the session, so that a turn whose end the window does not hold is under way."""
        self.unfolded = False
        """Whether every fold of the focus is open, as the one key opens them all, and each new one too."""
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
        self._folds: dict[str, Fold] = {}
        self._began: dict[str, int] = {}
        self._ended: dict[str, int] = {}
        self._before = 0
        self._after: int | None = None
        self._reading = asyncio.Lock()
        self._placing = False
        self._chosen: Block | None = None
        self._tail_text = ""
        self._tail_lines: list[Strip] = []
        self._strips: LRUCache[tuple[Block, int], tuple[list[Strip], int]] = LRUCache(_CACHE)
        self._heads: LRUCache[tuple[Block, int], Strip] = LRUCache(_CACHE)
        self._heights: dict[Block, int] = {}
        self._blank: LRUCache[str, bool] = LRUCache(_CACHE)
        self.reading_bodies: dict[str, list[Block]] = {}
        """The bodies being read to learn whether the lines waiting on them say anything."""
        self._width = 0

    def on_mount(self) -> None:
        self.app.theme_changed_signal.subscribe(self, self._themed)

    def _themed(self, _: object) -> None:
        """Draw every line again in the theme's colours, which a strip drawn holds."""
        self._strips.clear()
        self._heads.clear()
        self.refresh()

    @property
    def blocks(self) -> list[Block]:
        """The lines held, in the journal's order, which is the order they are drawn in but for a spawn drawn under its
        call, and for a fold's line, which is drawn where its first step stands and is held by its fold."""
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
        self._folds, self._began, self._ended, self._heights = {}, {}, {}, {}
        self._children = set(self.focus_on.children) if self.focus_on else set()
        self._before, self._after = before, after
        self.following, self.unseen = after is None, 0
        self._layout()

    def take(self, events: Iterable[Event]) -> int:
        """Add what the follower read past `through`, and say how many lines that drew. A turn of the agent in view
        that ends has its cuts read."""
        added, ended = [], False
        ends: set[str] = set()
        for event in events:
            if event.seq <= self.through:
                continue
            self.through = event.seq
            if self.focus_on is None or not self.focus_on.holds(event):
                continue
            if event.type in _ENDED and event.stream == f"turn/{self.focus_on.agent}":
                ended = True
                ends.add(event.turn or "")
            if self._after is not None:  # The newest lines were let go, and are read again as the person comes down.
                self.unseen += self._line(event) is not None
            elif (block := self._block(event)) is not None:
                added.append(block)
        if ended:
            self._read_spans()
        self._blocks += added
        folded = [self._folds[turn] for turn in ends if turn in self._folds]
        if added or folded:
            self._draw(added, folded)
            if self.following and self._rows:
                self._chosen = self._newest()
            elif added:
                self.unseen += len(added)
            self._let_oldest_go()
        self._layout()
        return len(added)

    def _newest(self) -> Block | None:
        """The newest line drawn."""
        return next((block for block, line in reversed(self._rows) if line >= 0), None)

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
        self._before = self._blocks[excess].first
        del self._blocks[:excess]
        above = self._let_go(gone, oldest=True)
        if not self.following:
            self._place(max(self.scroll_y - above, 0))

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
        self._after, self.following = self._blocks[-1].first, False
        self._let_go(gone, oldest=False)

    def _let_go(self, gone: set[Block], *, oldest: bool) -> int:
        """Forget the lines the window let go, the oldest or the newest, and the rows they were drawn in, with the line
        of a fold all of whose steps went, and say how many rows went above the top of the screen. The rows of the
        oldest lines lie before the first row of a line held that began after them, but for a fold's line, which stays
        while its fold holds a step, and the rows of the newest from the first row of one that went. A call is read
        again with the lines about it, and a fold that lost a step counts again."""
        top = int(self.scroll_y)
        for fold in {block.fold for block in gone if block.fold is not None}:
            fold.steps = [step for step in fold.steps if step not in gone]
            if fold.steps:
                self._refold(fold)
            else:
                gone.add(fold)
                self._folds.pop(fold.turn, None)
        rows = self._rows
        if oldest:
            reach = max((block.first for block in gone if not isinstance(block, Fold)), default=0)
            end = next(
                (
                    at
                    for at, (block, _) in enumerate(rows)
                    if block not in gone and not isinstance(block, Fold) and block.first > reach
                ),
                len(rows),
            )
            above = sum(1 for block, _ in rows[: min(top, end)] if block in gone)
            rows[:end] = [row for row in rows[:end] if row[0] not in gone]
        else:
            above = 0
            del rows[next((at for at, (block, _) in enumerate(rows) if block in gone), len(rows)) :]
        self._keep_held(gone)
        return above

    def _keep_held(self, gone: set[Block]) -> None:
        """Forget what the window let go, `gone`: a call is read again with the lines about it, and a turn's start or
        end that went is no longer known."""
        held = set(self._blocks)
        self._tools = {native: block for native, block in self._tools.items() if block in held}
        self._join.keep(held)
        self._cut_at = {start: block for start, block in self._cut_at.items() if block in held}
        self._resumed -= gone
        newest = self.through if self._after is None else self._after
        self._calls = {ref: call for ref, call in self._calls.items() if self._before <= call.seq <= newest}
        self._began = {turn: seq for turn, seq in self._began.items() if self._before <= seq <= newest}
        self._ended = {turn: seq for turn, seq in self._ended.items() if self._before <= seq <= newest}
        for block in gone:
            self._heights.pop(block, None)

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
        and the first of a span is where the span before it ends, cut once that span's last call is held too. A step of
        the agent in view's turn goes in that turn's fold, and a turn's start and end are kept, as a fold says whether
        it holds all of its turn and whether the turn is under way."""
        agent = self.focus_on.agent if self.focus_on is not None else None
        if event.stream == f"turn/{agent}" and event.turn is not None:
            if event.type == "turn.started":
                self._began[event.turn] = event.seq
            elif event.type in _ENDED:
                self._ended[event.turn] = event.seq
            if (fold := self._folds.get(event.turn)) is not None:
                self._refold(fold)
        if event.type == "model.called":
            return self._cut_before(event)
        line = self._line(event)
        if line is None:
            return None
        native = event.data.get("native_id") if event.type == "item.recorded" else None
        if native and (started := self._tools.get(native)) is not None:
            if event.seq > started.first:
                self._forget(started)
                started.start, started.event = started.event, event
                started.said = line_of(event, started.start) or line
                if started.fold is not None:
                    self._refold(started.fold)
            return None
        block = Block(event.seq, event, line)
        if native and event.data.get("phase") == "started":
            self._tools[native] = block
        if blank(event):
            self._learn(block, event.data["body"])
        if (turn := _step(event, self._children, agent)) is not None:
            self._fold_in(block, turn)
        self._join.take(event, block)
        joined = self._join.spawns_of(block)
        if self._join.call_of(block) is not None:
            joined.append(block)
        for spawn in joined:
            self._forget(spawn)
            spawn.said = _spawned(spawn.event, call.said if (call := self._join.call_of(spawn)) else None)
        return block

    def _fold_in(self, block: Block, turn: str) -> None:
        """Put a step in its turn's fold, made as its first step comes, open where every fold is."""
        fold = self._folds.get(turn)
        if fold is None:
            fold = self._folds[turn] = Fold(block.first, block.event, block.said, open=self.unfolded, turn=turn)
        block.fold = fold
        bisect.insort(fold.steps, block, key=lambda step: step.first)
        self._refold(fold)

    def _refold(self, fold: Fold) -> None:
        """Count a fold's steps again, as one came or went, its turn began or ended, or a call it holds ended."""
        first = fold.steps[0]
        fold.first, fold.event = first.first, first.event
        who = first.said.who or SafeText(f"@{first.event.agent or first.event.actor.partition(':')[2]}", "bold")
        fold.said = Said(who, NO_MARK, Content(""))
        self._forget(fold)

    def _under_way(self, fold: Fold) -> bool:
        """Whether a fold's turn is under way: a runtime holds the session, and the window holds its newest lines and
        not the turn's end."""
        return self.live and self._after is None and fold.turn not in self._ended

    def _latest(self, fold: Fold) -> Block | None:
        """The step a fold's turn took last, which shows while the turn is under way: its newest call, patch or thought,
        or a spawn that joins no call it holds."""
        return next(
            (step for step in reversed(fold.steps) if _counted(step) and self._join.call_of(step) is None), None
        )

    def _shows(self, block: Block) -> bool:
        """Whether a line is drawn: any but a step of a closed fold that counts something, which shows only as its
        turn's latest while the turn is under way, with the spawns under it."""
        fold = block.fold
        if fold is None or fold.open or not any(map(_counted, fold.steps)):
            return True
        if not self._under_way(fold):
            return False
        latest = self._latest(fold)
        return latest is not None and latest in (block, self._join.call_of(block))

    def _counts(self, fold: Fold) -> Content:
        """What a fold holds, counted exactly: its calls, with how many failed, are running or ended unknown, its
        thoughts, patches and spawns, and where the window does not hold its turn's start, that more came before."""
        calls = failed = running = unknown = thoughts = patches = spawns = 0
        under_way = self._under_way(fold)
        for step in fold.steps:
            data = step.event.data if isinstance(step.event.data, dict) else {}
            if not _counted(step):
                continue
            if step.event.type == "agent.spawned":
                spawns += 1
                continue
            if data.get("kind") == "thought":
                thoughts += 1
                continue
            calls += data.get("kind") == "tool"
            patches += data.get("kind") == "patch"
            if data.get("phase") == "started":
                running += under_way
                unknown += not under_way
            elif data.get("outcome") not in _DONE:
                failed += 1
        parts: list[Content] = []
        if calls:
            parts.append(Content(_some(calls, "tool call")))
        if patches:
            parts.append(Content(_some(patches, "patch", "patches")))
        if failed:
            parts.append(Content.styled(f"✗ {failed} failed", "$error"))
        if running:
            parts.append(Content.styled(f"{running} running", "$accent"))
        if unknown:
            parts.append(Content.styled(f"? {unknown} ended unknown", "$warning"))
        if thoughts:
            parts.append(Content(_some(thoughts, "thought")))
        if spawns:
            parts.append(Content(_some(spawns, "spawn")))
        if fold.turn not in self._began and self._before:
            parts.append(Content.styled("more before, not read yet", "$warning"))
        return Content.styled(" · ", "dim").join(parts).stylize_before("dim")

    def _learn(self, block: Block, ref: str) -> None:
        """Read the body of a line whose gist is whitespace alone, once for every line that cites it, to learn whether
        it says anything."""
        waiting = self.reading_bodies.setdefault(ref, [])
        waiting.append(block)
        if len(waiting) == 1:
            self.run_worker(self._read_blank(ref), exclusive=False)

    async def _read_blank(self, ref: str) -> None:
        """Let go of the lines whose body is blank too, which say nothing. A body that cannot be read, or that is cut
        where it is read, is not known to be blank, and its lines stay, opening on what was read, said cut."""
        assert self._session is not None
        try:
            found = await self._session.get_body(ref, limit=BODY_LIMIT)
        except Refused:
            self.reading_bodies.pop(ref, None)
            return
        self._blank[ref] = not found.decode(errors="replace").strip() and len(found) < BODY_LIMIT
        waiting = self.reading_bodies.pop(ref, [])
        if not self._blank[ref]:
            for block in waiting:
                block.text = SafeText(_read_as(found)).plain
            return
        gone = set(waiting)
        after = [self._blocks[self._blocks.index(block) + 1] for block in waiting if block in self._blocks[:-1]]
        self._blocks = [block for block in self._blocks if block not in gone]
        if self._chosen in gone:
            self._chosen = self._newest() if self.following else None
        self._rows = [row for row in self._rows if row[0] not in gone]
        for block in after:
            if block not in gone:
                self._respan(block, block)
        self._layout()

    def _cut_before(self, call: Event) -> Block | None:
        """The cut a model call of the agent in view stands at, when it begins a span after another of its turn and
        that span's last call is held, as a new line in its turn's fold, or None."""
        if self.focus_on is None or call.stream != f"turn/{self.focus_on.agent}":
            return None
        ref = f"{call.stream}@{call.version}"
        self._calls[ref] = call
        end = self._calls.get(self._cuts.get(ref, ""))
        if end is None or ref in self._cut_at:
            return None
        block = self._cut_at[ref] = Block(call.seq, end, _cut(f"{end.stream}@{end.version}"))
        if call.turn is not None:
            self._fold_in(block, call.turn)
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

    def _order(self, blocks: Iterable[Block], emitted: set[Fold]) -> Iterator[Block]:
        """The lines as they are drawn with every fold open: each where its first event stands, but a spawn joined to a
        call, drawn under it, and a fold's line, drawn before its first step drawn, unless it is in `emitted`, and only
        for a fold that counts something."""
        for block in blocks:
            if self._join.call_of(block) is not None:
                continue
            fold = block.fold
            if fold is not None and fold not in emitted and any(map(_counted, fold.steps)):
                emitted.add(fold)
                yield fold
            yield block
            yield from self._join.spawns_of(block)

    def _rows_of(
        self, blocks: Iterable[Block], before: Block | None = None, emitted: set[Fold] | None = None
    ) -> list[tuple[Block, int]]:
        """The rows lines are drawn in, below the line `before`, each led by the rows that lead it: the lines `_order`
        gives, but a step a closed fold hides."""
        rows = []
        for line in self._order(blocks, set() if emitted is None else emitted):
            if self._shows(line):
                rows += self._head(line, before) + self._lines_of(line)
                before = line
        return rows

    def _head(self, block: Block, before: Block | None) -> list[tuple[Block, int]]:
        """The rows that lead a line below `before`: a blank row before a rule, or a line whose speaker the line above
        is not, but at the top and under a rule, then the heading, for a line with a speaker the line above is not, and
        for one a page was read back above, which keeps the heading it had, so what is on screen does not move."""
        said, above = block.said, None if before is None else before.said
        if said.rule:
            return [] if above is None else [(block, SPACE)]
        who = None if said.who is None else said.who.plain
        goes_on = above is not None and (None if above.who is None else above.who.plain) == who
        space = [] if above is None or above.rule or goes_on else [(block, SPACE)]
        if said.who is None or (goes_on and block not in self._resumed):
            return space
        return [*space, (block, HEAD)]

    def _draw(self, new: list[Block], folded: list[Fold] | None = None, *, above: bool = False) -> int:
        """Draw new lines below those held, or `above` them, and say how many rows went above. A spawn joined to a
        call moves the lines it joins, so then all are laid out again, keeping the line at the top of the screen. A
        line that goes in a fold, and a fold whose turn ended, lay out that fold's lines again, with all that follows
        it below, or for lines read above, all above it. Lines read above keep the heading the line below them has, so
        what is on screen does not move."""
        if any(self._join.call_of(block) is not None or self._join.spawns_of(block) for block in new):
            self._relayout()
            return 0
        folds = {*(block.fold for block in new if block.fold is not None), *(folded or ())}
        if above:
            if self._rows:
                self._resumed.add(self._rows[0][0])
            if not new:
                return 0
            last = max((fold.steps[-1] for fold in folds), key=lambda step: step.first, default=new[-1])
            return self._respan(new[0], last if last.first > new[-1].first else new[-1])
        firsts = [step for fold in folds if (step := self._first_drawn(fold)) is not None and step not in new]
        if firsts:
            self._respan(min(firsts, key=lambda step: step.first))
            return 0
        if new:  # No line held before them is of a fold any of them is in, so each fold of theirs is drawn among them.
            self._rows += self._rows_of(new, self._rows[-1][0] if self._rows else None)
        return 0

    def _first_drawn(self, fold: Fold) -> Block | None:
        """The step a fold's line is drawn before: its first that is drawn where it stands."""
        return next((step for step in fold.steps if self._join.call_of(step) is None), None)

    def _emitted(self, span: list[Block], first: Block) -> set[Fold]:
        """The folds of the lines in `span` whose line is drawn before `first`, as their first step drawn is."""
        return {
            fold
            for fold in {block.fold for block in span if block.fold is not None}
            if (step := self._first_drawn(fold)) is not None and step.first < first.first
        }

    def _respan(self, first: Block, last: Block | None = None) -> int:
        """Lay out again the lines held from `first` to `last`, or to the end, with the fold's lines whose first step
        drawn is among them and the spawns drawn under their calls, and the rows that lead the line after them, keeping
        the line at the top of the screen where it is. Say how many rows it adds."""
        start_at = self._index(first)
        end_at = len(self._blocks) if last is None else self._index(last) + 1
        span = self._blocks[start_at:end_at]
        held = set(span)
        region: set[Block] = {block for block in span if (call := self._join.call_of(block)) is None or call in held}
        region |= {spawn for block in span for spawn in self._join.spawns_of(block)}
        emitted = self._emitted(span, first)
        region |= {fold for fold in {block.fold for block in span if block.fold} if fold not in emitted}
        indices = [index for index, (block, _) in enumerate(self._rows) if block in region]
        if indices:
            start, stop = indices[0], indices[-1] + 1
        else:
            after = set(self._blocks[end_at:]) | {block.fold for block in self._blocks[end_at:] if block.fold}
            start = stop = next(
                (index for index, (block, _) in enumerate(self._rows) if block in after), len(self._rows)
            )
        before = self._rows[start - 1][0] if start else None
        rows = self._rows_of(span, before, emitted)
        lead = stop
        if stop < len(self._rows):
            following = self._rows[stop][0]
            while lead < len(self._rows) and self._rows[lead][0] is following and self._rows[lead][1] < 0:
                lead += 1
            rows += self._head(following, rows[-1][0] if rows else before)
        top = self._rows[int(self.scroll_y)] if int(self.scroll_y) < len(self._rows) else None
        added = len(rows) - (lead - start)
        self._rows[start:lead] = rows
        self._layout()
        if self.following:
            self._place(None)
        elif top is not None and top in self._rows:
            self._place(self._rows.index(top))
        elif top is not None:
            self._place(start)
        return added

    def _index(self, block: Block) -> int:
        """Where a line stands among the lines held, which are in the order of their first seq."""
        at = bisect.bisect_left(self._blocks, block.first, key=lambda held: held.first)
        while self._blocks[at] is not block:
            at += 1
        return at

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
        top = int(self.scroll_y)
        rows = self._draw(older, above=True)
        if self._chosen is None and older:
            self._chosen = self._newest()
        if self.following:
            self._let_oldest_go()
        else:
            self._let_newest_go()
        self._layout()
        if self.following:
            self._place(None)
        elif rows:
            self._place(top + rows)
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
        self._after = page.cursor if page.cursor < self.through else None
        if self._after is None:  # Each fold's turn under way is now known as the window holds its newest lines.
            self._relayout()
        else:
            self._draw(newer)
        self._let_oldest_go()
        self._layout()
        self._read_near()

    def _lines_of(self, block: Block) -> list[tuple[Block, int]]:
        return [(block, line) for line in range(self._height(block))]

    def _height(self, block: Block) -> int:
        """How many rows a line takes at this width: its words, wrapped, and while it is open what it opens on."""
        height = self._heights.get(block)
        if height is None:
            inner = self._inner()
            words = len(self._words_rows(block, inner)) if self._wraps(block) else 1
            height = self._heights[block] = words + (len(self._body(block, inner)) if block.open else 0)
        return height

    def _inner(self) -> int:
        return max(self._width - GUTTER, 1)

    def _indent(self, block: Block) -> int:
        """How far a line stands in: under its speaker's heading, a step under its fold's line, where its fold counts
        something and so has one, and a spawn under its call further."""
        indent = 2 if block.said.who is not None else 0
        if block.fold is not None and not isinstance(block, Fold) and any(map(_counted, block.fold.steps)):
            indent = 4
        return indent + (2 if self._join.call_of(block) is not None else 0)

    def _opens_on_more(self, block: Block) -> bool:
        """Whether opening a line shows more than its words: a fold's steps, a call's input and what it gave back, a
        body, or an approval's ask."""
        return (
            isinstance(block, Fold) or _called(block) or bool(_refs(block)) or block.event.type == "approval.requested"
        )

    def _wraps(self, block: Block) -> bool:
        """Whether a line's words wrap, as what is said does: anything but a fold's line, a line of what an agent did
        and a rule, which are one row each, cut at the edge."""
        return not isinstance(block, Fold) and not _did(block) and not block.said.rule

    def _shown_words(self, block: Block) -> Content:
        """A line's words as drawn: a fold's counts, and a call with no end, said running while its turn is under way
        and ended unknown once it is not."""
        if isinstance(block, Fold):
            return self._counts(block)
        data = block.event.data if isinstance(block.event.data, dict) else {}
        if _called(block) and data.get("phase") == "started" and block.fold is not None:
            if self._under_way(block.fold):
                return Content.assemble(block.said.words, ("  running", "$accent"))
            return Content.assemble(block.said.words, ("  ? ended unknown", "$warning"))
        return block.said.words

    def _words_rows(self, block: Block, inner: int) -> list[Content]:
        """A line's words as rows at `inner` cells: in from the left, led by its mark, or for a line that opens on more
        than it shows and is no line of what is said, `▸` or `▾`, and its words, wrapped where it is what is said, with
        `▸` or `▾` after them where it opens on more, or else one row, cut at the edge; or a rule across the width."""
        said, indent = block.said, " " * self._indent(block)
        if said.rule:
            run = "─" * max(inner - len(indent) - said.words.cell_length - 4, 0)
            return [Content.assemble(indent, ("── ", "dim"), said.words, " ", (run, "dim"))]
        toggle = Style.from_meta({"toggle": True})
        glyph = OPENED if block.open else SHUT
        words = self._shown_words(block)
        if not self._wraps(block):
            mark = _mark(glyph, "dim").stylize(toggle) if self._opens_on_more(block) else said.mark
            return [Content.assemble(indent, mark, words)]
        more = Content.styled(f" {glyph}", "dim").stylize(toggle, 1) if self._opens_on_more(block) else Content("")
        width = inner - len(indent) - said.mark.cell_length - more.cell_length
        lines = [words] if words.cell_length <= width else words.wrap(max(width, 1))
        lines[-1] = Content.assemble(lines[-1], more)
        pad = " " * said.mark.cell_length
        return [Content.assemble(indent, said.mark if at == 0 else pad, line) for at, line in enumerate(lines)]

    def _body(self, block: Block, inner: int) -> list[Strip]:
        """What an open line shows at this width, under its words: its body as Markdown, else its gist whole, or an
        approval's ask as it was asked, or a call's input and what it gave back as text, then where it came from, with
        a tool's whole name. A fold opens on its steps, which are lines of their own."""
        if isinstance(block, Fold):
            return []
        event, indent = block.event, self._indent(block) + 2
        width = max(inner - indent, 1)
        if block.ask is not None:
            lines = [Strip(row.line.render_segments(), row.line.cell_length) for row in rows_of(block.ask, width)]
        elif _called(block):
            lines = plain(block.text if block.text is not None else SafeText(event.gist).plain, width)
        else:
            said = block.text if block.text is not None else SafeText(event.gist).plain
            lines = markdown(said, width, self.app.console)
        when = time.strftime("%H:%M:%S", time.localtime(event.wall_time))
        data = event.data if isinstance(event.data, dict) else {}
        tool = f" · tool {event.gist.split()[0]}" if data.get("kind") == "tool" and event.gist.split() else ""
        where = SafeText(f"{event.type}{tool} · {event.actor} · seq {event.seq} · {when}", "dim")
        lines.append(Strip(where.render_segments(), where.cell_length))
        return [Strip.join([Strip.blank(indent), line]) for line in lines]

    def _drawn_rows(self, block: Block, inner: int) -> tuple[list[Strip], int]:
        """A line's rows as strips at `inner` cells, over the transcript's style, and how many of them are its words:
        its words, then while it is open what it opens on."""
        found = self._strips.get((block, inner))
        if found is None:
            style = self.rich_style
            strips = [strip_of(row, inner, style) for row in self._words_rows(block, inner)]
            words = len(strips)
            if block.open:
                strips += [line.crop_extend(0, inner, style).apply_style(style) for line in self._body(block, inner)]
            found = self._strips[(block, inner)] = (strips, words)
        return found

    def _forget(self, block: Block) -> None:
        """Draw a line again, as it reads, opens or counts anew."""
        self._strips.discard((block, self._inner()))
        self._heads.discard((block, self._inner()))
        self._heights.pop(block, None)

    def toggle(self, block: Block | None = None) -> None:
        """Open or close a line: the chosen one, unless another is named. A body, a call's input and what it gave back,
        or an approval's ask, is read when first opened. A fold opens on its steps, and closing it chooses it where one
        of its steps was chosen."""
        block = block or self._chosen
        if block is None:
            return
        self._chosen = block
        block.open = not block.open
        self._forget(block)
        if isinstance(block, Fold):
            if not block.open and self._chosen in block.steps:
                self._chosen = block
            self._respan_fold(block)
            return
        if block.open and block.event.type == "approval.requested" and block.ask is None:
            self.run_worker(self._read_ask(block), exclusive=False)
        elif block.open and block.text is None and (_called(block) or _refs(block)):
            self.run_worker(self._read_body(block), exclusive=False)
        self._respan(block, block)

    def _respan_fold(self, fold: Fold) -> None:
        if (first := self._first_drawn(fold)) is not None:
            self._respan(first, max(fold.steps, key=lambda step: step.first))

    def unfold(self) -> None:
        """Open every fold of the focus, and each that comes, or close them all where all are open."""
        self.unfolded = not self.unfolded
        for fold in self._folds.values():
            fold.open = self.unfolded
            self._forget(fold)
        if self._chosen is not None and self._chosen.fold is not None and not self.unfolded:
            self._chosen = self._chosen.fold
        self._relayout()

    async def _read_ask(self, block: Block) -> None:
        assert self._session is not None
        block.ask = await approvals.read(self._session, block.event)
        self._forget(block)
        self._respan(block, block)

    async def _read_body(self, block: Block) -> None:
        """Read what a line opens on: its body, or a call's input and what it gave back, each said cut where it is, and
        a body that cannot be read said so under its gist."""
        if _called(block):
            start = block.start or (block.event if _phase(block.event) == "started" else None)
            end = block.event if _phase(block.event) == "completed" else None
            given = None if start is None else await self._read(start)
            back = None if end is None else await self._read(end)
            block.text = SafeText(self._call_text(block, start, end, given, back)).plain
        else:
            read = await self._read(block.event)
            block.text = SafeText(block.event.gist if read is None else read).plain
        self._forget(block)
        if block in self._blocks:
            self._respan(block, block)

    async def _read(self, event: Event) -> str | None:
        """An event's body as read, said cut where it was cut, or under its gist that it cannot be read, or None for an
        event with no body."""
        data = event.data if isinstance(event.data, dict) else {}
        if not isinstance(ref := data.get("body"), str):
            return None
        assert self._session is not None
        try:
            return _read_as(await self._session.get_body(ref, limit=BODY_LIMIT))
        except Refused as refused:
            return f"{event.gist}\n\n(the body cannot be read: {refused})"

    def _call_text(
        self, block: Block, start: Event | None, end: Event | None, given: str | None, back: str | None
    ) -> str:
        """What a call opens on: its input, as JSON laid out where it is JSON, and what it gave back, or why either is
        not said."""
        if start is None:
            given = "(unknown: the window holds no start of this call)"
        elif given is None:
            given = tool_named(start.gist)[1]
        with contextlib.suppress(ValueError):
            given = json.dumps(json.loads(given), indent=2, ensure_ascii=False)
        if end is not None:
            back = end.gist if back is None else back
        elif block.fold is not None and self._under_way(block.fold):
            back = "(nothing yet: it is running)"
        else:
            back = "(unknown: the window holds no end of this call)"
        return f"input\n{given}\n\noutput\n{back}"

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
            self._heights = {}
            self._relayout()
            return
        self._width = width or self._width
        text = self.tail.text(self.through) if self._after is None else ""
        if text != self._tail_text:
            self._tail_text = text
            self._tail_lines = markdown(SafeText(text).plain, self._inner(), self.app.console) if text else []
        self.virtual_size = Size(0, len(self._rows) + len(self._tail_lines))
        if self.following:
            self._place(None)
        self.refresh()

    def held(self, live: bool) -> None:
        """Say whether a runtime holds the session, laying out again where that changed, as a turn under way shows its
        latest step."""
        if live != self.live:
            self.live = live
            for fold in self._folds.values():
                self._forget(fold)
            self._relayout()

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
            self._chosen = self._newest()
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
        if drawn := self._drawn():
            self._chosen = drawn[0]
        self._place(0)
        self.post_message(self.Moved())
        self.refresh()

    def action_cursor_up(self) -> None:
        self._choose(-1)

    def action_cursor_down(self) -> None:
        self._choose(1)

    def action_open_line(self) -> None:
        self.toggle()

    def action_open(self) -> None:
        """Open the chosen line one level, or, where it is open, choose the first line it opened on."""
        chosen = self._chosen
        if chosen is None:
            return
        if not chosen.open:
            self.toggle(chosen)
        elif isinstance(chosen, Fold):
            self._choose(1)

    def action_shut(self) -> bool:
        """Close the chosen line one level: an open line closes, and a step of an open fold chooses that fold's line.
        Say whether there was a level to close."""
        chosen = self._chosen
        if chosen is not None and chosen.open:
            self.toggle(chosen)
        elif chosen is not None and chosen.fold is not None and chosen.fold.open:
            self._go_to(chosen.fold)
        else:
            return False
        return True

    async def action_close(self) -> None:
        """Close the chosen line one level, as Left does, or with nothing open there, go back to the composer, as Esc
        does from any other part."""
        if not self.action_shut():
            await self.run_action("screen.back")

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
        """The lines drawn, in order."""
        return [block for block, line in self._rows if line == 0]

    def _every(self) -> list[Block]:
        """Every line held, in the order they are drawn with every fold open: what `/find` looks through."""
        return list(self._order(self._blocks, set()))

    def _go_to(self, block: Block) -> None:
        """Choose a line, opening the fold it stands in where that hides it, and scroll it into view."""
        if (fold := block.fold) is not None and not self._shows(block) and not fold.open:
            fold.open = True
            self._forget(fold)
            self._respan_fold(fold)
        self._chosen = block
        if (block, 0) in self._rows:
            row = self._rows.index((block, 0))
            self.scroll_to_region(Region(0, row, 1, 1), animate=False, immediate=True, force=True)
        self.refresh()

    def _stop_following(self) -> None:
        if self.following:
            self.following = False
            self.post_message(self.Moved())

    @work(group="find", exclusive=True)
    async def find(self, words: str) -> None:
        """Choose the line before the chosen one whose words hold `words`, whatever their case and spacing, in the order
        the lines are drawn with every fold open, opening the fold of a step it finds, and reading back from the journal
        a page at a time, as scrolling up does, until one does. A line's words are what it shows, and not a body it
        opens on. Each line is looked at once, and a read under way puts its page in first. Where none does back to the
        focus's first line it says so, and goes back to following, or else to the line it began from, or where reading
        back let that go from the window, to the oldest line held. Reading the focus anew stops it, saying nothing, and
        a page the journal would not give, which is said as lines missed."""
        said, start, last = _words(words), self._chosen, None
        followed, shown = self.following, self._shown
        while True:
            lines = self._every()
            at = next((lines.index(block) for block in (last, start) if block in lines), len(lines))
            for block in reversed(lines[:at]):
                last = block
                if said in _words(self._line_text(block).plain):
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

    def _line_text(self, block: Block) -> Content:
        """A line as it reads where it is drawn, with who says it."""
        words = self._shown_words(block)
        return words if block.said.who is None else Content.assemble(block.said.who, "  ", words)

    def copied(self, block: Block) -> str:
        """A line's text as `/copy` sends it: what it shows where it is drawn, and while it is open what it opens on."""
        return text_of(block, self._line_text(block))

    def on_click(self, event: events.Click) -> None:
        """Choose the line clicked, open or close it on its `▸` or `▾`, or on a ref its text names, open that ref's
        provenance. A click that ends a drag selecting text does none of these."""
        if self.text_selection is not None:
            return
        if (ref := event.style.meta.get("ref")) is not None:
            self.post_message(self.Named(ref))
            return
        index = event.get_content_offset_capture(self).y + int(self.scroll_y)
        if not 0 <= index < len(self._rows) or self._rows[index][1] == SPACE:
            return
        block = self._rows[index][0]
        if event.style.meta.get("toggle"):
            self._stop_following()
            self.toggle(block)
            self.post_message(self.Moved())
            return
        self._stop_following()
        self._chosen = block
        self.refresh()
        self.post_message(self.Moved())

    def _strip(self, block: Block, line: int, width: int) -> Strip:
        """A row at `width` cells: the gutter, `▌` where it is a row of the chosen line's words while the transcript has
        focus, then the row."""
        style = self.rich_style
        if line == SPACE:
            return Strip.blank(width, style)
        inner = max(width - GUTTER, 1)
        gutter = Strip.blank(GUTTER, style)
        if line == HEAD:
            strip = self._heads.get((block, inner))
            if strip is None:
                assert block.said.who is not None
                who = block.said.who.stylize("$accent", 0, len(block.said.who.plain.split(" ")[0]))
                strip = self._heads[(block, inner)] = strip_of(who, inner, style)
            return Strip.join([gutter, strip])
        rows, words = self._drawn_rows(block, inner)
        strip = rows[line] if line < len(rows) else Strip.blank(inner, style)
        if block is self._chosen and self.has_focus and line < words:
            chosen = self.get_component_rich_style("transcript--chosen")
            strip = Strip(Segment.apply_style(strip, post_style=chosen), inner)
            gutter = Strip([Segment("▌", style + self.get_component_rich_style("transcript--marker"))], GUTTER)
        return Strip.join([gutter, strip])

    def _words_of(self, index: int) -> tuple[str, int, bool]:
        """A row's words, how many characters of what decorates them lead them, and whether it goes on from the row
        above as one line wrapped: its speaker, its line's words past its mark, all of them where it is one row cut at
        the edge, its body past its indent, or what is being said now."""
        if index >= len(self._rows):
            tail = index - len(self._rows)
            return (self._tail_lines[tail].text, GUTTER, False) if tail < len(self._tail_lines) else ("", 0, False)
        block, line = self._rows[index]
        said = block.said
        if line == SPACE:
            return "", 0, False
        if line == HEAD:
            return (said.who.plain if said.who else ""), GUTTER, False
        inner = self._inner()
        rows = self._words_rows(block, inner)
        if line >= len(rows):
            indent = GUTTER + self._indent(block) + 2
            return self._drawn_rows(block, inner)[0][line].text[indent - GUTTER :], indent, False
        if said.rule:
            return said.words.plain, GUTTER + self._indent(block) + 3, False
        marked = 2 if self._opens_on_more(block) and not self._wraps(block) else said.mark.cell_length
        lead = GUTTER + self._indent(block) + marked
        if len(rows) == 1 and not self._wraps(block):
            return self._shown_words(block).plain, lead, False
        words = rows[line].plain[lead - GUTTER :]
        if line == len(rows) - 1 and self._opens_on_more(block):
            words = words.removesuffix(f" {OPENED if block.open else SHUT}")
        return words, lead, line > 0

    def get_selection(self, selection: Selection) -> tuple[str, str] | None:
        """The words of the rows selected, without the marks, rules and indents that decorate them, a line wrapped on
        one line."""
        return selected(selection, len(self._rows) + len(self._tail_lines), self._words_of), "\n"

    def selection_updated(self, selection: Selection | None) -> None:
        self.refresh()

    def render_line(self, y: int) -> Strip:
        index = y + int(self.scroll_y)
        width = self.scrollable_content_region.width
        if index < len(self._rows):
            strip = self._strip(*self._rows[index], width)
        elif (tail := index - len(self._rows)) < len(self._tail_lines):
            line = self._tail_lines[tail].crop_extend(0, max(width - GUTTER, 1), self.rich_style)
            strip = Strip.join([Strip.blank(GUTTER, self.rich_style), line]).apply_style(self.rich_style)
        else:
            return Strip.blank(width, self.rich_style)
        if (selection := self.text_selection) is not None:
            screen = self.screen.get_component_rich_style("screen--selection")
            strip = highlighted(strip, selection.get_span(index), screen)
        return strip.apply_offsets(0, index)


def _some(count: int, what: str, many: str | None = None) -> str:
    return f"{count} {what if count == 1 else many or what + 's'}"
