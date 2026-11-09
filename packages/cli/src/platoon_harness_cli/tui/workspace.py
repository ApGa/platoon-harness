"""The workspace: one session, as a person works with it every day."""

import json
import re
from collections import Counter, defaultdict
from collections.abc import Mapping
from functools import partial
from pathlib import Path
from typing import Any

from textual import events, work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.content import Content
from textual.css.query import NoMatches
from textual.message import Message
from textual.screen import Screen
from textual.style import Style
from textual.timer import Timer
from textual.widget import Widget
from textual.widgets import Static

from platoon_harness import ConfigError, Refused, Session
from platoon_harness.config import Manifest
from platoon_harness.kernel import Event, is_held
from platoon_harness.runtime.paths import MANIFEST

from .. import ops
from ..channels import Act
from ..ops import CONFIRMED, Flag, cut, forms
from ..provenance import shows
from ..replay import JUMP, Player, nothing_acts
from ..review import snapshots_of
from ..roster import GROUPS, detail_of, why_said
from . import logo
from .approvals import Approval
from .composer import ADDRESS, Composer
from .dialogs import Confirm, Form
from .keymap import KEYMAP, action_of, bindings, command, keys, reach
from .live import Live
from .motion import GLYPHS, TICK, Motion, allowed
from .provenance import Provenance
from .review import Review
from .rows import Row, Rows
from .safe import SafeText, note
from .tasks import Tasks
from .transcript import Focus, Fold, Transcript, inline, page_of, replying_to

STATES = {
    "needs_you": ("◉", "$warning"),
    "working": ("●", "$success"),
    "blocked": ("◌", "$warning"),
    "idle": ("○", "dim"),
    "done": ("✓", "$success"),
    "failed": ("✗", "$error"),
    "lost": ("⊘", "$error"),
    "unknown": ("?", "dim"),
}
"""Each state an agent is shown in, by its glyph and colour, the roster's groups in their order first, then an agent the
runtime lost and a group this client does not know, which is said as unknown. A glyph says each, as colour alone does
not."""
NEEDS_YOU = STATES["needs_you"][0]
UNREAD = 100
"""The most unread lines a badge counts: past it, it says `99+`."""
CHOOSE = f"{next(key.shown for key in keys('list') if key.action == 'cursor_down')} chooses a place"
"""How a place is chosen in the dock once it has focus."""


class Dock(Rows):
    """Where a person must act, a row each. Only the person moves its cursor: a row that goes takes the cursor with it,
    so an act never lands on a row they did not choose. Only Tab or Shift+Tab gives it focus, since a click chooses a
    place and gives none. It reads its own letters, in the order they come, and they act only on a place chosen there
    with the arrows: it takes focus with none chosen, and a character it does not take lets go of the one chosen, so
    what is typed for the composer answers nothing."""

    BINDINGS = bindings("panel")
    FOCUS_ON_CLICK = False

    class Moved(Message):
        """The cursor moved, so which row shows the keys that take its actions changed."""

    def on_focus(self) -> None:
        self._let_go()

    async def on_key(self, event: events.Key) -> None:
        if (action := action_of("dock", event.key)) is not None:
            event.stop()
            event.prevent_default()
            await self.run_action(action)
        elif event.is_printable:
            self._let_go()

    def _let_go(self) -> None:
        self.cursor = None
        self.refresh()
        self.post_message(self.Moved())

    def show(self, rows: list[Row]) -> None:
        chosen = self.cursor
        super().show(rows)
        self.cursor = chosen if chosen in self.keys else None

    def move_to(self, key: str) -> None:
        super().move_to(key)
        self.post_message(self.Moved())


class Navigator(Rows):
    """The agents and channels, a row each, of which Enter shows the chosen one, under the logo's agents. What of its
    rows moves, the logo and the glyphs of agents working or resting, moves as `Motion` draws it, a few frames a second
    while it says to and motion is on, each frame drawing again only the rows whose frame changed. Its timer decides
    nothing."""

    BINDINGS = bindings("panel")

    def __init__(self, *, id: str | None = None) -> None:
        super().__init__(id=id)
        self.motion = Motion()
        self._ticking: Timer | None = None
        self._art: tuple[tuple[tuple[str, ...], bool], list[Content]] | None = None

    def follow(self, states: Mapping[str, str], *, live: bool, settled: bool) -> None:
        """Take each agent's state and whether the session settled, as the record says them now, and move while they
        say to."""
        self.motion.follow(states, live=live, settled=settled)
        self._tick_while(self.motion.moving and allowed(self.app))

    def _tick_while(self, moving: bool) -> None:
        if moving and self._ticking is None:
            self._ticking = self.set_interval(TICK, self.advance)
        elif not moving and self._ticking is not None:
            self._ticking.stop()
            self._ticking = None
            self.refresh()

    def advance(self) -> None:
        """Move a frame on, drawing again each row whose frame changed, and only those, and stop where nothing moves."""
        before = self._frames()
        self.motion.advance()
        after = self._frames()
        for index, row in enumerate(self.rows):
            if row.moves and before[row.moves] != after[row.moves]:
                self.refresh_lines(index)
        self._tick_while(self.motion.moving and allowed(self.app))

    def _frames(self) -> dict[str, object]:
        return {"logo": self.motion.sprite(), **{state: self.motion.glyph(state) for state in GLYPHS}}

    def moving(self, row: Row, index: int) -> Content | None:
        """The logo's row at `index` as this frame draws it, the logo's rows being the first, or an agent's row with its
        glyph as this frame draws it; None while nothing moves, or for a glyph that stands still."""
        if self._ticking is None:
            return None
        if row.moves == "logo":
            pixels, ansi = self.motion.sprite(), self.app.current_theme.ansi
            if self._art is None or self._art[0] != (pixels, ansi):
                self._art = ((pixels, ansi), logo.sprite(pixels, logo.ANSI if ansi else logo.TRUECOLOUR))
            return self._art[1][index]
        if (glyph := self.motion.glyph(row.moves)) is None:
            return None
        at = row.lead - 2
        return row.line[:at] + Content(glyph, list(row.line[at : at + 1].spans)) + row.line[at + 1 :]


class Edge(Static):
    """The navigator's edge, which dragging widens or narrows it."""

    ALLOW_SELECT = False

    class Dragged(Message):
        def __init__(self, x: int) -> None:
            super().__init__()
            self.x = x

    def on_mouse_down(self, event: events.MouseDown) -> None:
        self.capture_mouse()
        self.add_class("-dragged")

    def on_mouse_move(self, event: events.MouseMove) -> None:
        if self.app.mouse_captured is self:
            self.post_message(self.Dragged(event.screen_x))

    def on_mouse_up(self, event: events.MouseUp) -> None:
        self.release_mouse()
        self.remove_class("-dragged")


NARROWEST, WIDEST = 24, 64
"""How narrow and how wide the navigator may be made."""


def _named(action: str) -> str:
    """An action as a person calls it, by the keymap's name for it."""
    return next(key.name for key in KEYMAP if key.action == action)


def _state(row: dict[str, Any]) -> str:
    """The state an agent is shown in: its group, but lost for one the runtime lost, and unknown for a group this client
    does not know."""
    if row["group"] == "failed" and (row["why"] or {}).get("kind") == "lost":
        return "lost"
    return row["group"] if row["group"] in GROUPS else "unknown"


def _said(state: str) -> str:
    return GROUPS.get(state, state)


def _harness(row: dict[str, Any]) -> str:
    """A harness as a row names it: its command, or the last part of a program's reference."""
    harness = row["harness"]
    return harness.rpartition(":")[2] if isinstance(harness, str) else harness.get("mode", "program")


def _quantity(unit: str, amount: float) -> str:
    if unit == "usd":
        return f"${amount:,.2f}"
    if unit == "wall":
        minutes = int(amount // 60)
        if minutes < 60:
            return f"{minutes}m" if minutes else f"{int(amount)}s"
        return f"{minutes // 60}h{minutes % 60:02}m"
    return f"{amount:,.0f}"


def _spend(unit: str, amount: float | None, label: str, limit: float | None) -> str:
    """A unit's spend in a few characters: `?` for an amount nobody could state, `≥` for a bound, then any limit."""
    said = "?" if amount is None else ("≥" if label == "lower_bound" else "") + _quantity(unit, amount)
    return f"{unit} {said}" + ("" if limit is None else f"/{_quantity(unit, limit)}")


def _some(count: int, what: str) -> str:
    return f"{count} {what}{'' if count == 1 else 's'}"


def _unmeasured(count: int) -> str:
    return f"{_some(count, 'turn')} unmeasured"


METER = 4
"""How many cells a limit's meter takes."""
METERED = ("tokens", "usd")
"""The units spent by what a harness measures, which a turn nobody measured whole leaves short."""


def _meter(spent: float, limit: float) -> Content:
    """How much of a limit is spent, as a thin bar: the accent, then the warning colour from four fifths of it, and the
    error's once it is spent."""
    filled = min(round(METER * spent / limit), METER) if limit > 0 else METER
    style = "$error" if spent >= limit else "$warning" if spent >= 0.8 * limit else "$accent"
    return Content.assemble(("━" * filled, style), ("─" * (METER - filled), "dim"))


class Workspace(Screen[None]):
    """One session: who is working, on what, what is blocked, what changed, and where you must act. With `replay`, a
    replay of it, drawn as the session is from a copy of its record that grows as it plays, in which nothing acts: its
    banner says so, and every act and form says why it does nothing. A copy started anew from a checkpoint is drawn as a
    session joined anew, keeping what is in view and how far you have read."""

    BINDINGS = [*bindings("workspace"), *bindings("replay"), *bindings("parts")]

    def __init__(self, name: str, session: Session | None = None, *, replay: bool = False) -> None:
        super().__init__()
        self.session_name = name
        self.replaying = replay
        self.player: Player | None = None
        self._kept: str | None = None
        self._defaulted = False
        self.live: Live | None = None
        self.focus_on: Focus | None = None
        self.target: str | None = None
        self.attached: tuple[str, bytes] | None = None
        self.marks: dict[str, int] = {}
        self.unread: dict[str, int] = {}
        self._unwritten: dict[str, int] = {}
        self.human = "human:you"
        self._given = session
        self._refused: dict[tuple[str, str], tuple[str, str]] = {}
        self._shown: dict[str, Content] = {}
        self._queued: dict[str, Any] | None = None
        self._inspected: dict[str, Any] | None = None
        self._unmarked = False
        self._needing: set[str] | None = None
        self.forms: list[ops.Form] = []
        self.words = ""

    def compose(self) -> ComposeResult:
        yield Static(id="header")
        yield Static(id="banner")
        with Horizontal(id="body"):
            yield Navigator(id="navigator")
            yield Edge(id="edge")
            with Vertical(id="focus"):
                yield Static(id="strip")
                yield Transcript(id="transcript")
                yield Static(id="behind")
            yield Static(id="inspector")
        yield Dock(id="dock")
        yield Static(id="chip")
        yield Composer(id="composer")
        yield Static(id="footer")

    async def on_mount(self) -> None:
        composer = self.query_one(Composer)
        composer.known = self._known
        (self.query_one(Transcript) if self.replaying else composer).focus()
        self.set_class(self.replaying, "replaying")
        self._lay_out(self.size.width, self.size.height)
        opening = "opening a replay of it" if self.replaying else "attaching"
        self.query_one("#header", Static).update(SafeText(f"{self.session_name}  {opening}…", "bold"))
        self.query_one("#inspector").border_title = Content("inspector")
        self.app.theme_changed_signal.subscribe(self, lambda _: self._redraw())
        self._join()

    @work(exclusive=True, group="attach")
    async def _join(self) -> None:
        try:
            if self.replaying:
                self.player = await Player.open(self.session_name)
                self.player.changed = self._played
                session = self.player.replay.session
            else:
                session = self._given or await Session.attach(self.session_name)
            self.human = Manifest.model_validate_json((session.folder / MANIFEST).read_bytes()).principal
            through = await session.head()
            self.forms = [] if self.replaying else forms(await session.ops())
        except (Refused, ConfigError) as refusal:
            self.query_one("#header", Static).update(SafeText(f"{self.session_name}: {refusal}", "$error"))
            return
        try:
            self.marks = await session.marks()
        except Refused as refused:
            self._lose_marks(refused)
        self.query_one(Transcript).through = through
        self.live = Live(session, self._draw, partial(self.run_worker, group="live"), replay=self.replaying)
        self.live.start(through)

    def _played(self) -> None:
        """The replay moved, or how it plays changed: its banner is drawn again, and a copy started anew is joined."""
        live, player = self.live, self.player
        if live is None or player is None or not self.is_mounted:
            return
        if player.replay.session is not live.session:
            self.run_worker(self._rejoin(), group="rejoin")
        else:
            self._redraw()

    async def _rejoin(self) -> None:
        """Draw the replay's copy as it now stands as a session joined anew, as a copy started from a checkpoint
        holds none of what was drawn of the one before: the same agent or channel in view where it holds one, and how
        far you have read, which a replay keeps here alone."""
        live, player = self.live, self.player
        if live is None or player is None or (session := player.replay.session) is live.session:
            return
        live.stop()
        if self.focus_on is not None:
            self._kept = None if self._defaulted else self.focus_on.key
        self.focus_on, self.unread, self._needing, self._queued, self._inspected = None, {}, None, None, None
        through = await session.head()
        self.query_one(Transcript).through = through
        self.live = Live(session, self._draw, partial(self.run_worker, group="live"), replay=True)
        self.live.start(through)

    async def on_unmount(self) -> None:
        """Leave as a guest leaves: the session, and its runtime, run on. Taking the screen down cancels its workers, so
        each mark still being written is written first, and what you read stays read. A replay closes, which takes its
        copies back."""
        if self.live is not None:
            self.live.stop()
            for stream, seq in list(self._unwritten.items()):
                await self._mark_one(self.live.session, stream, seq)
            await self.live.session.leave()
        if self.player is not None:
            await self.player.close()

    def left(self) -> str | None:
        """The session that runs on once you leave it, or None when no runtime holds it, or in a replay."""
        return self.session_name if self.live is not None and self.live.runtime == "live" else None

    def on_descendant_focus(self) -> None:
        self._redraw()

    def on_descendant_blur(self, blurred: events.DescendantBlur) -> None:
        """A part hidden while it has focus, by a resize, `/navigator` or a dock left empty, gives it back to the
        composer."""
        if not blurred.widget.display:
            self.query_one(Composer).focus()

    def on_dock_moved(self) -> None:
        self._redraw()

    # Drawing, once a frame.

    async def _draw(self, events: list[Event], said: bool) -> None:
        """Draw a frame. Taking this screen down removes its widgets before it cancels its workers, so a frame cut short
        by that, and only by that, is dropped."""
        try:
            await self._frame(events, said)
        except NoMatches:
            if self.is_running:
                raise

    async def _frame(self, events: list[Event], said: bool) -> None:
        live = self.live
        assert live is not None
        transcript = self.query_one(Transcript)
        focus = self.focus_on
        transcript.held(live.runtime != "history")
        added = transcript.take(events)
        for screen in self.app.screen_stack:
            if isinstance(screen, Tasks):
                screen.moved(events)
        transcript.draw(live.tail)
        if said and not events:  # Live text alone moves nothing but the transcript.
            return
        await self._count(events, live, transcript.through)
        if (focus is None and (live.roster or live.frames == 0)) or self._first_agent_came(live):
            await self.show(self._first_focus(live))
            self._defaulted = True
        elif focus is not None and (added or transcript.following):
            self._mark(transcript)
        await self._read_queue(live)
        await self._inspect(live)
        self._toast(live)
        states = {row["agent"]: _state(row) for row in live.roster}
        settled = bool(live.status.get("settled"))
        self.query_one(Navigator).follow(states, live=live.runtime != "history", settled=settled)
        self._redraw()

    def _toast(self, live: Live) -> None:
        """Say in a toast that an agent has come to need you while another is in view: one that needed you as the
        screen first drew it has not come to."""
        needing = {row["agent"] for row in live.roster if row["group"] == "needs_you"}
        came, self._needing = needing - (self._needing if self._needing is not None else needing), needing
        shown = self.focus_on.agent if self.focus_on else None
        for agent in sorted(came - {shown}):
            row = self._row(agent)
            why = f": it {why_said(row['why'])}" if row and row["why"] else ""
            goes = f"{reach('next_place')} goes to each place you must act, in turn"
            note(self, f"@{agent} needs you{why}. {goes}.", severity="warning")

    def _first_agent_came(self, live: Live) -> bool:
        """Whether a replay that showed what was sent to you, as it held no agent, now holds the one the session
        started first, while you have chosen nothing to show."""
        focus = self.focus_on
        unchosen = self.replaying and self._defaulted and focus is not None and focus.agent is None
        return unchosen and any(row["parent"] is None for row in live.roster)

    def _first_focus(self, live: Live) -> Focus:
        """The agent the session started first, or what was sent to you when it started none. In a replay drawn anew,
        what was in view before, where the copy holds it."""
        kept = self._kept
        if kept is not None and (self._row(kept.removeprefix("@")) or any(f.key == kept for f in self._foci(live))):
            return self._focus_of(kept)
        roots = [row["agent"] for row in live.roster if row["parent"] is None]
        return self._agent(roots[0]) if roots else Focus.of_person(self.human)

    def _agent(self, name: str) -> Focus:
        live = self.live
        children = [row["agent"] for row in live.roster if row["parent"] == name] if live else []
        return Focus.of_agent(name, children)

    def _foci(self, live: Live) -> list[Focus]:
        """Every channel, as a focus, and what was sent to you."""
        return [Focus.of_person(self.human), *(Focus.of_channel(row["name"], row["kind"]) for row in live.channels)]

    def _unread(self, focus: Focus, event: Event, mark: int) -> bool:
        return event.seq > mark and event.actor != self.human and focus.holds(event)

    async def _count(self, events: list[Event], live: Live, through: int) -> None:
        """How many lines past your mark each channel holds that you did not write: from the journal through `through`,
        the newest line drawn, when a channel is first seen, and from what comes after."""
        for focus in self._foci(live):
            mark = self.marks.get(focus.marks[0], 0)
            if focus.key not in self.unread:
                self.unread[focus.key] = await self._past_mark(live.session, focus, mark, through)
            else:
                self.unread[focus.key] += sum(self._unread(focus, event, mark) for event in events)

    async def _past_mark(self, session: Session, focus: Focus, mark: int, through: int) -> int:
        """The lines past `mark` through `through`, up to what a badge counts, read back a page at a time, since a page
        that scanned its most can hold none with more to come."""
        count, before = 0, through + 1
        while count < UNREAD and before > mark + 1:
            page = await page_of(session, focus, after=mark, before=before)
            count += sum(self._unread(focus, event, mark) for event in page.events)
            before = page.cursor
        return count

    def _mark(self, transcript: Transcript) -> None:
        """Mark what you have read: the focus in view, through the newest line it shows, while it follows."""
        focus = self.focus_on
        live = self.live
        if focus is None or live is None or not transcript.following:
            return
        for stream in focus.marks:
            if self.marks.get(stream, 0) < transcript.through:
                self.marks[stream] = transcript.through
                self._write_mark(live.session, stream, transcript.through)
        self.unread[focus.key] = 0

    def _write_mark(self, session: Session, stream: str, seq: int) -> None:
        """Write a mark off the screen's loop, as a worker; until it is written, leaving writes it. A replay writes
        none, as nothing in it is the session's: it keeps its marks here."""
        if self.replaying:
            return
        self._unwritten[stream] = seq
        self.run_worker(self._mark_one(session, stream, seq), group="marks")

    async def _mark_one(self, session: Session, stream: str, seq: int) -> None:
        try:
            await session.mark(stream, seq)
        except Refused as refused:
            self._lose_marks(refused)
        if self._unwritten.get(stream) == seq:
            del self._unwritten[stream]

    def _lose_marks(self, refused: Refused) -> None:
        """Say once that your marks cannot be kept, which loses only badges."""
        if not self._unmarked:
            self._unmarked = True
            note(self, f"Your read marks cannot be kept, which loses only badges: {refused}", severity="warning")

    async def _read_queue(self, live: Live) -> None:
        """What waits for the target's next handover, read when the roster says something does."""
        row = self._row(self.target.removeprefix("@")) if self.target else None
        if row is None or not row["unread"]:
            self._queued = None
        elif self._queued is None or self._queued["total"] != row["unread"]:
            try:
                self._queued = await live.session.unread(row["agent"])
            except Refused:
                self._queued = None

    async def _inspect(self, live: Live) -> None:
        """What `agent.status` says of the agent in view, which the inspector shows of its workspace."""
        agent = self.focus_on.agent if self.focus_on else None
        try:
            self._inspected = None if agent is None else await live.session.status(agent)
        except Refused:
            self._inspected = None

    def _row(self, agent: str | None) -> dict[str, Any] | None:
        if self.live is None or agent is None:
            return None
        return next((row for row in self.live.roster if row["agent"] == agent), None)

    def _redraw(self) -> None:
        live = self.live
        if live is None:
            return
        for found, refusal in list(self._refused.items()):
            if self._fingerprint(found[1]) != refusal[1]:
                del self._refused[found]
        self._set("#header", self._header(live))
        self._set("#banner", self._banner(live))
        self.query_one("#banner").set_class(live.runtime != "live", "-shown")
        self.query_one("#navigator", Rows).show(self._navigator(live))
        self._set("#strip", self._strip(live))
        focus = self.query_one("#focus")
        title: Content = self._title()
        behind: Content = self._behind()
        if self._shown.get("title") != title:
            self._shown["title"] = focus.border_title = title
        if self._shown.get("behind") != behind:
            self._shown["behind"] = focus.border_subtitle = behind
        self._set("#behind", behind)
        self.query_one("#behind").set_class(bool(behind), "-shown")
        self._set("#inspector", self._inspector(live))
        dock = self.query_one(Dock)
        dock.show(self._dock(live))
        dock.set_class(bool(dock.rows), "-shown")
        self._set("#chip", self._chip(live))
        self._set("#footer", self._footer(live))

    def _set(self, selector: str, content: Content) -> None:
        """Show `content` in a static, which repaints only when it differs from what it shows."""
        if self._shown.get(selector) != content:
            self._shown[selector] = content
            self.query_one(selector, Static).update(content)

    def _header(self, live: Live) -> Content:
        """The session in segments: its name, how it stands, who is working, how many places need you, and how many
        agents are blocked, failed or lost, then what changed and what is spent against each limit. Where they do not
        fit, what decorates them goes first, the meters, then the amounts spent with no limit, then all that is spent,
        then what changed, and under 60 columns the name and the counts stay, in glyphs."""
        counts = Counter(_state(row) for row in live.roster)
        acting = len(self._places(live))
        busy = "$success" if counts["working"] else "dim"
        working = Content.styled(f"{STATES['working'][0]} {counts['working']}", busy)
        needing = Content.styled(f"{NEEDS_YOU} {acting}", "bold $warning" if acting else "dim")
        stuck = [(state, *STATES[state]) for state in ("blocked", "failed", "lost") if counts[state]]
        name = SafeText(self.session_name, "bold")
        if self.size.width < 60:
            glyphs = [Content.styled(f"{glyph} {counts[state]}", style) for state, glyph, style in stuck]
            return Content("  ").join([name, working, needing, *glyphs])
        runtime = {"live": ("live", "$success"), "history": ("history", "$warning")}.get(
            live.runtime, ("replay", "$accent")
        )
        standing = "waiting for you" if live.status.get("stalled") else "settled" if live.status.get("settled") else ""
        state = " · ".join(said for said in (live.status.get("state", ""), standing) if said)
        segments: list[Content] = [
            name,
            Content.assemble(runtime, (f" · {state}" if state else "", "dim")),
            Content.assemble(working, " working"),
            Content.assemble(needing, " need you"),
            *(Content.styled(f"{glyph} {counts[state]} {state}", style) for state, glyph, style in stuck),
        ]
        changed = self._changed(live)
        ways = [
            [*segments, changed, *self._spent(live, meters=True, amounts=True)],
            [*segments, changed, *self._spent(live, meters=False, amounts=True)],
            [*segments, changed, *self._spent(live, meters=False, amounts=False)],
            [*segments, changed],
        ]
        width = self.size.width - 2
        shown = next((way for way in ways if sum(part.cell_length + 2 for part in way) - 2 <= width), segments)
        return Content("  ").join(shown)

    def _changed(self, live: Live) -> Content:
        """What changed, as the looks found it: not observed in a session whose cwd is in no git repository, and not
        measured until the first look."""
        if live.status.get("repo") is None:
            return Content.styled("changes not observed", "dim")
        if not live.changes:
            return Content.styled("changes not measured", "dim")
        rows = live.changes.values()
        commits = sum(row["kind"] == "commit" and not row["dropped"] for row in rows)
        paths = sum(row["total"] or 0 for row in rows if row["kind"] == "workspace")
        return Content(f"{_some(commits, 'commit')}, {_some(paths, 'path')} uncommitted")

    def _spent(self, live: Live, *, meters: bool, amounts: bool) -> list[Content]:
        """Each shared limit and what is spent against it, with a meter, if `meters`, where the amount is known, and if
        `amounts`, any metered amount with no limit, or `spent ?` where none would show, then how many turns nobody
        measured whole, which goes with each metered amount shown, tokens or dollars, as none is whole without it."""
        limits = {row["unit"]: row for row in live.budgets if row["scope"] == "shared"}
        usage = live.ending.usage if live.ending else {}
        said: list[Content] = []
        for unit, row in limits.items():
            spent = None if row["label"] == "unavailable" else row["spent"]
            measured = meters and spent is not None and row["limit"] is not None
            meter = [" ", _meter(spent, row["limit"])] if measured else []
            words = _spend(unit, spent, row["label"], row["limit"]).partition(" ")
            said.append(Content.assemble(words[0], *meter, " ", words[2]))
        metered = {unit for unit in limits if unit in METERED}
        for unit, used in usage.items():
            if amounts and unit in METERED and unit not in limits and used["amount"] is not None:
                said.append(Content(_spend(unit, used["amount"], used["label"], None)))
                metered.add(unit)
        unmeasured = max((used["unmeasured"] for used in usage.values()), default=0)
        if not unmeasured or not (metered or amounts):
            return said
        return [*(said if metered else [*said, Content("spent ?")]), Content.styled(_unmeasured(unmeasured), "dim")]

    def _banner(self, live: Live) -> Content:
        """Why this is history, from the session's state: its runtime stopped as its owner asked, went without its
        shutdown, or the session has ended. In a replay, that it is one, of which session, where it stands and how it
        plays, and why it could not move, where it could not."""
        if self.player is not None:
            return SafeText(self.player.banner(), "bold $accent")
        state = live.status.get("state")
        resume = f" {reach('resume')} resumes it, which can spend money."
        if state in ("closed", "cancelled"):
            return Content.styled(f"The session is {state}: this is its history.", "$warning")
        if state == "stopped":
            return Content.styled(f"Its runtime stopped, as its owner asked: this is its history.{resume}", "$warning")
        if state in ("open", "closing"):
            went = f"Its runtime went without its shutdown, killed or crashed: this is its history.{resume}"
            return Content.styled(went, "$error")
        return Content.styled(f"No runtime holds this session, so this is its history.{resume}", "$warning")

    def _places(self, live: Live) -> list[dict[str, Any]]:
        """Where you must act, oldest first: every row of `attention` but a mention you have read past."""
        rows = sorted(live.attention.values(), key=lambda row: row["since_seq"])
        return [row for row in rows if row["kind"] != "mention" or not self._read(row)]

    def _read(self, mention: dict[str, Any]) -> bool:
        return self.marks.get(mention["id"].partition("@")[0], 0) >= mention["since_seq"]

    def _mentions(self, live: Live) -> set[str]:
        """The keys of the rows an unread mention names: its sender's and the stream it is on."""
        named = set()
        for row in live.attention.values():
            if row["kind"] == "mention" and not self._read(row):
                stream = row["id"].partition("@")[0]
                named |= {f"@{row['agent']}", f"@{stream.partition('/')[2]}" if stream.startswith("inbox/") else ""}
                named.add(f"#{stream.partition('/')[2]}" if stream.startswith("channel/") else "")
        return named - {""}

    def _navigator(self, live: Live) -> list[Row]:
        """The session's mark, then the agents in the roster's groups, each a tree by parent of two lines, its glyph and
        name over its state, harness and what it is doing, then the channels."""
        mentioned = self._mentions(live)
        rows = self._brand()
        members: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in live.roster:
            members[_state(row) if _state(row) in ("lost", "unknown") else row["group"]].append(row)
        for state in STATES:
            if not members[state]:
                continue
            rows.append(Row(Content.assemble((_said(state), "dim"), (f"  {len(members[state])}", "dim"))))
            names = {row["agent"] for row in members[state]}
            under: dict[str | None, list[dict[str, Any]]] = defaultdict(list)
            for row in members[state]:
                under[row["parent"] if row["parent"] in names else None].append(row)
            rows += self._tree(under, None, 0, mentioned)
            rows.append(Row(Content("")))
        if not live.roster:
            rows += [Row(Content.styled("no agents yet", "dim")), Row(Content(""))]
        rows.append(Row(Content.styled("channels", "dim")))
        for focus in self._foci(live):
            unread = self.unread.get(focus.key, 0)
            count = (f"{UNREAD - 1}+" if unread >= UNREAD else str(unread)) if unread else ""
            mark = ("@", "$warning") if focus.key in mentioned else ""
            line = Content.assemble("  ", SafeText(focus.title), (f" {count}", "bold $accent"), " ", mark)
            rows.append(Row(line, focus.key, lead=2))
        return rows

    def _brand(self) -> list[Row]:
        """The logo's agents, which move as `Motion` draws them, where the screen is tall enough to give them the rows.
        The header says the session's name and how it stands."""
        if self.size.height < 16:
            return []
        art: list[Content] = logo.sprite(logo.SMALL, logo.ANSI if self.app.current_theme.ansi else logo.TRUECOLOUR)
        rows = []
        for cells in art:
            rows.append(Row(cells, lead=cells.cell_length, moves="logo"))
        return [*rows, Row(Content(""))]

    def _tree(
        self, under: dict[str | None, list[dict[str, Any]]], parent: str | None, depth: int, mentioned: set[str]
    ) -> list[Row]:
        """An agent and those below it, two lines each: its glyph, which moves as motion draws it, and its name, with
        any mention of you unread and how many entries wait for its next handover; then its state, its harness, and
        what it waits on or is doing, where the record says."""
        rows = []
        for row in sorted(under[parent], key=lambda found: found["agent"]):
            state = _state(row)
            glyph, style = STATES[state]
            indent = "  " * depth
            key = f"@{row['agent']}"
            named = Content.assemble(
                indent,
                (f"{glyph} ", style),
                SafeText(key, "bold"),
                ("@" if key in mentioned else "", "$warning"),
                (f" ↧{row['unread']}" if row["unread"] else "", "$accent"),
            )
            stopped = f"turn {row['stopped']}" if row["stopped"] and row["group"] == "idle" else ""
            doing = " ".join((stopped or detail_of(row)).split())
            how = Content.assemble(
                indent + "  ",
                SafeText(f"{_said(state)} · {_harness(row)}", style),
                (" · " if doing else "", "dim"),
                inline(doing).stylize("dim"),
            )
            moves = state if state in GLYPHS else ""
            rows += [Row(named, key, lead=len(indent) + 2, moves=moves), Row(how, key, lead=len(indent) + 2)]
            rows += self._tree(under, row["agent"], depth + 1, mentioned)
        return rows

    def _strip(self, live: Live) -> Content:
        """The team as tabs, for a screen too narrow for the navigator: each agent's glyph and name, the one in view
        filled with the accent, a click on one showing it."""
        shown = self.focus_on.key if self.focus_on else None
        tabs = []
        for row in live.roster:
            glyph, style = STATES[_state(row)]
            key = f"@{row['agent']}"
            chosen = Style.from_meta({"@click": f"screen.show_row({key!r})"})
            if key == shown:
                tab = SafeText(f" {glyph} {key} ", "bold $background on $accent")
            else:
                tab = Content.assemble(" ", (glyph, style), SafeText(f" {key} "))
            tabs.append(tab.stylize(chosen))
        return Content(" ").join(tabs)

    def _title(self) -> Content:
        """What is in view, and for an agent its role and harness, its state, and why it waits."""
        focus = self.focus_on
        if focus is None:
            return Content("")
        row = self._row(focus.agent)
        if row is None:
            return SafeText(f" {focus.title} ", "bold")
        glyph, style = STATES[_state(row)]
        why = why_said(row["why"])
        return Content.assemble(
            SafeText(f" {focus.title}", "bold"),
            SafeText(f" · {row['role']} on {_harness(row)} · ", "dim"),
            SafeText(f"{glyph} {_said(_state(row))}", style),
            SafeText(f" · {why}" if why else "", "dim"),
            " ",
        )

    def _behind(self) -> Content:
        """Under the transcript while it does not follow: how many lines came since, and how to follow again."""
        transcript = self.query_one(Transcript)
        if transcript.following:
            return Content("")
        follow = reach("follow")
        said = f"↓ {transcript.unseen} new, {follow} to follow" if transcript.unseen else f"{follow} to follow"
        return Content.styled(f" {said} ", "bold")

    def _inspector(self, live: Live) -> Content:
        focus = self.focus_on
        row = self._row(focus.agent if focus else None)
        if row is None:
            return Content.styled("Choose an agent to see why it waits, what it runs on and what it spent.", "dim")
        lines: list[Content] = [
            SafeText(f"@{row['agent']}", "bold"),
            SafeText(f"role {row['role']}, parent {('@' + row['parent']) if row['parent'] else 'none'}"),
            SafeText(f"harness {_harness(row)}, model {row['model'] or 'its default'}"),
            SafeText(
                f"state {row['state']}"
                + (f", {row['group'].replace('_', ' ')}" if row["group"] != row["state"] else "")
            ),
        ]
        if row["resting"]:
            lines.append(SafeText("resting: its harness has no process, and its next message brings it back"))
        if row["why"] is not None:
            lines.append(SafeText(f"why {why_said(row['why'])}", "$warning"))
        if row["held_by"]:
            lines.append(SafeText(f"held by @{row['held_by']}"))
        lines += self._workspace(row)
        lines.append(SafeText(f"login {row['login'] or 'unknown'}"))
        for level, said in (row["levels"] or {}).items():
            reasons = "; ".join(said.get("reasons", ()))
            lines.append(SafeText(f"{level} {said.get('state')}" + (f": {reasons}" if reasons else "")))
        for unit, usage in row["usage"].items():
            unmeasured = f", {_unmeasured(usage['unmeasured'])}" if usage.get("unmeasured") else ""
            label = f" ({usage.get('label', 'unavailable')}{unmeasured})"
            lines.append(Content.assemble(_spend(unit, usage.get("amount"), "", None), (label, "dim")))
        gaps = [gap for gap in (live.ending.gaps if live.ending else ()) if gap["agent"] == row["agent"]]
        lines += [
            SafeText(f"gap {gap['what']}, {gap['count']} on the {gap['plane']} plane", "$warning") for gap in gaps
        ]
        lines += [
            SafeText(f"{_named(action)}: {reason}", "dim")
            for (action, agent), (reason, _) in self._refused.items()
            if agent == row["agent"]
        ]
        return Content("\n").join(lines)

    def _workspace(self, row: dict[str, Any]) -> list[Content]:
        """Where the agent in view works: the mode, branch and folder of its workspace, the commit it started from and
        how well what runs there is tied to its credential, and why its stop kept it, once its stop has."""
        workspace = row["workspace"]
        if workspace is None:
            return []
        status = self._inspected if self._inspected and self._inspected["agent"] == row["agent"] else {}
        made = status.get("workspace") or {}
        assurance = made.get("assurance")
        said = f", {assurance}" if assurance and assurance != workspace["mode"] else ""
        lines: list[Content] = [SafeText(f"workspace {workspace['mode']}{said}")]
        if workspace["mode"] == "isolated":
            reaches = "  still reaches the network, loopback and what you can read outside your home"
            lines.append(SafeText(reaches, "dim"))
        lines += [SafeText(f"  branch {workspace['branch']}")] if workspace["branch"] else []
        lines += [SafeText(f"  from {made['base'][:12]}")] if made.get("base") else []
        lines.append(SafeText(f"  {workspace['path']}", "dim"))
        if kept := status.get("kept"):
            lines.append(SafeText(f"kept: {'; '.join(kept['why'])}", "$warning"))
        return lines

    def _dock(self, live: Live) -> list[Row]:
        """A row per place you must act, and on the one you are at, the keys that take its actions from where the focus
        is, the dock's own letters or a session's typed commands, and on an approval the one that reads its whole ask.
        A dock with focus and no place chosen says how to choose one on its first row. Hints come before the gist, so a
        narrow screen cuts the gist and never a hint."""
        dock = self.query_one(Dock)
        chosen = dock.cursor
        rows = []
        acts = ("first_action", "second_action", "ask")
        first, second, ask = [key.shown for key in keys("dock")] if dock.has_focus else [reach(act) for act in acts]
        for index, place in enumerate(self._places(live)):
            actions = place["actions"]
            hints: list[Any] = []
            if place["id"] == chosen:
                hints = [
                    (f"{hint} {action['label']}  ", "bold")
                    for hint, action in zip((first, second), actions, strict=False)
                ]
                hints += [(f"{ask} Read it whole  ", "bold")] if place["kind"] == "approval" else []
            elif chosen is None and dock.has_focus and index == 0:
                hints = [(f"{CHOOSE}  ", "bold")]
            line = Content.assemble(
                (f"{NEEDS_YOU} ", "$warning"),
                (f"{place['kind']} ", "bold"),
                SafeText(f"@{place['agent']} " if place["agent"] else ""),
                *hints,
                SafeText(" ".join(place["gist"].split())),
            )
            rows.append(Row(line, place["id"]))
        return rows

    def _unsendable(self, live: Live) -> str | None:
        """Why the composer cannot send now, or None when it can."""
        if live.runtime == "replay":
            return nothing_acts(self.session_name)
        if live.runtime != "live":
            return f"history: {reach('resume')} resumes it to send"
        if self.target is None and self.focus_on is not None and self.focus_on.thread is not None:
            return "this thread is between others, and you are not in it, so it takes no message from you"
        if self.target is None:
            return f"{self.focus_on.title if self.focus_on else 'this'} takes no message: choose an agent or a topic"
        return None

    def _replying(self) -> Event | None:
        """The message what the composer sends answers: the one the thread in view was opened on, while the target is
        that thread's."""
        focus = self.focus_on
        return focus.reply_to if focus is not None and focus.to is not None and self.target == focus.to else None

    def _chip(self, live: Live) -> Content:
        cannot = self._unsendable(live)
        if cannot is not None:
            return SafeText(cannot, "dim")
        parts: list[Any] = [("to: ", "dim"), SafeText(self.target or "", "bold $accent")]
        if (replying := self._replying()) is not None:
            parts += [("  replying to ", "dim"), SafeText(replying_to(replying), "bold")]
        if self._queued is not None:
            ways = sorted({entry["delivery"] for entry in self._queued["entries"]})
            parts += [(f"  queued {self._queued['total']}: {', '.join(ways)}", "$accent")]
        if self.attached is not None:
            parts += [SafeText(f"  + {self.attached[0]} ({len(self.attached[1]):,} bytes)", "$secondary")]
        return Content.assemble(*parts)

    def _footer(self, live: Live) -> Content:
        """How to reach the typed commands, which every terminal delivers, then the footer's keys, each named by what it
        runs from the part with focus, which may take it for its own, and dim while the runtime refuses that for the
        agent in view, then how many places need you. In a replay, its controls and the keys that work everywhere, and
        no act of the session's, as none does anything there."""
        agent = self.focus_on.agent if self.focus_on else None
        active = self.active_bindings
        parts: list[Any] = [("/", "bold $accent"), (" commands", "dim"), "  "]
        shown = (*keys("replay"), *keys("everywhere")) if self.replaying else (*keys("everywhere"), *keys("workspace"))
        for key in shown:
            pressed = key.keys.split(",")[0]
            if not key.footer or (pressed not in active and key.where != "replay"):
                continue
            runs = active[pressed].binding.action if pressed in active else key.runs
            now = next((other for other in KEYMAP if other.runs == runs), key)
            off = (now.action, agent or "") in self._refused
            label = "" if self.size.width < 60 else f" {now.name}"
            parts += [(key.shown, "dim" if off else "bold $accent"), (label, "dim strike" if off else "dim"), "  "]
        if places := len(self._places(live)):
            parts.append((f" {NEEDS_YOU} {places} need you ", "bold $background on $warning"))
        return Content.assemble(*parts)

    # What a person does.

    def _known(self, address: str) -> bool:
        live = self.live
        if live is None:
            return False
        agents = {f"@{row['agent']}" for row in live.roster}
        topics = {row["name"] for row in live.channels if row["kind"] == "topic"}
        return address in agents | topics

    async def show(self, focus: Focus) -> None:
        """Show a focus in the focus pane. The composer's target follows it while the draft is empty."""
        live = self.live
        if live is None:
            return
        self.focus_on, self._defaulted = focus, False
        live.follow_tail(focus.agent)
        transcript = self.query_one(Transcript)
        transcript.tail = live.tail
        await transcript.show(focus, live.session, transcript.through)
        if not self.query_one(Composer).text.strip():
            self.target = focus.to
        navigator = self.query_one("#navigator", Rows)
        navigator.show(self._navigator(live))
        if focus.key in navigator.keys:
            navigator.move_to(focus.key)
        self._mark(transcript)
        await self._read_queue(live)
        self._redraw()

    def _focus_of(self, key: str) -> Focus:
        live = self.live
        assert live is not None
        if key.startswith("@") and self._row(key.removeprefix("@")) is not None:
            return self._agent(key.removeprefix("@"))
        return next((focus for focus in self._foci(live) if focus.key == key), Focus.of_person(self.human))

    async def on_rows_chosen(self, chosen: Rows.Chosen) -> None:
        if chosen.rows.id == "navigator":
            self.remove_class("navigator-shown")
            await self.show(self._focus_of(chosen.key))
        elif isinstance(chosen.rows, Dock):
            await self._go_to(chosen.key)

    async def _go_to(self, place: str) -> None:
        live = self.live
        row = live.attention.get(place) if live else None
        if row is None:
            return
        stream = row["id"].partition("@")[0]
        if stream.startswith("channel/"):
            await self.show(self._focus_of(f"#{stream.partition('/')[2]}"))
        elif stream.startswith("inbox/") and row["kind"] == "mention":
            await self.show(Focus.of_person(self.human))
        elif row["agent"]:
            await self.show(self._agent(row["agent"]))
        self._redraw()

    def on_transcript_moved(self) -> None:
        self._redraw()

    async def on_composer_retarget(self, retarget: Composer.Retarget) -> None:
        self.target = retarget.to
        if self.live is not None:
            await self._read_queue(self.live)
        self._redraw()

    def on_composer_empty(self) -> None:
        self.action_detach()

    async def on_composer_send(self) -> None:
        """Run what the composer holds when it is a typed command, which goes to no agent, or else send it."""
        composer = self.query_one(Composer)
        if (key := command(composer.text)) is None:
            self._send()
            return
        composer.remember()
        await self.run_action(key.runs)

    def on_resize(self, event: events.Resize) -> None:
        self._lay_out(event.size.width, event.size.height)
        self._redraw()

    def _lay_out(self, width: int, height: int) -> None:
        """The layout by size: a resize changes which panes show, and never what is in view or the target, nor focus
        but by hiding the part that has it."""
        self.set_class(width < 120, "medium")
        self.set_class(width < 80, "narrow")
        self.set_class(width < 60, "slim")
        self.set_class(height < 16, "short")

    @work(group="act")
    async def _send(self) -> None:
        live = self.live
        composer = self.query_one(Composer)
        if live is None or (cannot := self._unsendable(live)) is not None:
            note(self, cannot or "not attached yet", severity="warning")
            return
        text = composer.text.strip()
        if not text and self.attached is None:
            return
        target, replying = self.target, self._replying()
        assert target is not None
        if text.startswith("/"):
            question = SafeText(
                f"This begins with / and is none of our commands, which / alone lists. A harness's own are not built "
                f"yet, so it goes to {target} as a message, which its harness may still read as a command. Send it?"
            )
            if not await self.app.push_screen_wait(Confirm(question)):
                return
        if (found := ADDRESS.match(composer.text)) is not None and found[1] != target:
            question = SafeText(f"This begins with {found[1]}, and goes to {target}, as shown. Send it to {target}?")
            if not await self.app.push_screen_wait(Confirm(question)):
                return
        try:
            gist, body = cut(text, file=None if self.attached is None else self.attached[0])
        except ValueError as error:
            note(self, str(error), severity="warning")
            return
        if self.attached is not None:
            body = self.attached[1]
        try:
            await live.session.send(target, gist, body=body, reply_to=None if replying is None else shows(replying))
        except Refused as refused:
            note(self, str(refused), severity="error")
            return
        composer.remember()
        self.attached = None
        self._redraw()

    def _fingerprint(self, agent: str) -> str:
        row = self._row(agent)
        return json.dumps([row[name] for name in ("state", "group", "why", "unread")] if row else None)

    def _refusing(self, action: str, agent: str, refused: Refused) -> None:
        """Keep a refusal the runtime gave, which disables that act on that agent until its row moves."""
        detail = refused.refusal.detail
        reason = detail if isinstance(detail, str) else json.dumps(detail)
        self._refused[(action, agent)] = (reason, self._fingerprint(agent))
        note(self, f"{_named(action)} @{agent}: {reason}", severity="warning")
        self._redraw()

    @work(group="act")
    async def action_interrupt(self) -> None:
        await self._interrupt(below=False)

    @work(group="act")
    async def action_stop_below(self) -> None:
        await self._interrupt(below=True)

    async def _interrupt(self, *, below: bool) -> None:
        live, focus = self.live, self.focus_on
        action = "stop_below" if below else "interrupt"
        if self._refused_in_replay(action):
            return
        if live is None or focus is None or focus.agent is None:
            note(self, f"{_named(action)} needs an agent in view", severity="warning")
            return
        if (kept := self._refused.get((action, focus.agent))) is not None:
            note(self, f"{_named(action)} @{focus.agent}: {kept[0]}", severity="warning")
            return
        try:
            stopped = await live.session.interrupt(focus.agent, below=below)
        except Refused as refused:
            self._refusing(action, focus.agent, refused)
            return
        said = ", ".join(stopped["stopped"])
        note(self, f"Stopped the turns of {said}. It stops turns, not waits: one parked on a wait is left to it.")

    async def action_next_place(self) -> None:
        dock = self.query_one(Dock)
        if (place := dock.step(1)) is None:
            note(self, "Nothing needs you now.")
            return
        dock.move_to(place)
        await self._go_to(place)

    def action_first_action(self) -> None:
        self._act(0, self.query_one(Dock).cursor)

    def action_second_action(self) -> None:
        self._act(1, self.query_one(Dock).cursor)

    def action_ask(self) -> None:
        """Read the whole of what the approval you are at asks, which answers nothing."""
        live = self.live
        place = live.attention.get(self.query_one(Dock).cursor or "") if live else None
        if live is None or place is None or place["kind"] != "approval":
            how = CHOOSE if self.query_one(Dock).has_focus else f"{reach('next_place')} goes to where you must act"
            note(self, f"Only an approval has an ask to read whole: {how}.", severity="warning")
            return
        self.app.push_screen(Approval(live.session, place["id"].removeprefix("approval/"), place["since_seq"]))

    @work(group="act")
    async def _act(self, index: int, chosen: str | None) -> None:
        """Take an action of the place you were at when you asked, as its row offers it, with the version it was drawn
        from, or open its op's form filled in with what it fixes, where it leaves the rest to the form."""
        live = self.live
        place = live.attention.get(chosen or "") if live else None
        if self._refused_in_replay("first_action" if index == 0 else "second_action"):
            return
        if live is None or place is None or index >= len(place["actions"]):
            how = CHOOSE if self.query_one(Dock).has_focus else f"{reach('next_place')} goes to where you must act"
            note(self, f"Nothing here takes that action: {how}.", severity="warning")
            return
        action = place["actions"][index]
        if action["form"]:
            form = next((form for form in self.forms if form.op == action["op"]), None)
            if form is None:
                note(self, f"{action['label']}: your grants hold no {action['op']}.", severity="warning")
            else:
                self._run_op(form, action["args"])
            return
        args = {**action["args"], **({"via": "tui"} if action["op"] == "approval.resolve" else {})}
        outcome = await live.session.submit(action["op"], **args)
        refusal = outcome.refusal
        if refusal is None:
            note(self, f"{action['label']}: {place['gist']}")
        elif refusal.code == "conflict" and isinstance(refusal.detail, dict) and refusal.detail.get("resolved_by"):
            detail = refusal.detail
            via = f" via {detail['via']}" if detail.get("via") else ""
            note(self, f"Already decided, {detail['state']}, by {detail['resolved_by']}{via}")
        else:
            note(self, f"{refusal.code}: {refusal.detail}", severity="warning")

    async def action_next_row(self) -> None:
        await self._step(1)

    async def action_previous_row(self) -> None:
        await self._step(-1)

    async def _step(self, by: int) -> None:
        navigator = self.query_one("#navigator", Rows)
        if (key := navigator.step(by)) is not None:
            await self.show(self._focus_of(key))

    def action_back(self) -> None:
        """Go back to the composer, closing the navigator where it lies over the focus pane."""
        self.remove_class("navigator-shown")
        self.query_one(Composer).focus()

    def action_command(self) -> None:
        composer = self.query_one(Composer)
        composer.focus()
        composer.insert("/")

    def action_navigator(self) -> None:
        self.toggle_class("navigator-shown" if self.size.width < 80 else "navigator-hidden")

    def action_wider(self) -> None:
        self._widen(4)

    def action_narrower(self) -> None:
        self._widen(-4)

    def on_edge_dragged(self, dragged: Edge.Dragged) -> None:
        """Make the navigator end where its edge is dragged to."""
        navigator = self.query_one("#navigator")
        self._set_width(navigator, dragged.x - navigator.region.x)

    def _widen(self, by: int) -> None:
        navigator = self.query_one("#navigator")
        width = navigator.styles.width
        self._set_width(navigator, (int(width.value) if width is not None else navigator.outer_size.width) + by)

    def _set_width(self, navigator: Widget, width: int) -> None:
        """Make the navigator `width` cells wide, within what it may be."""
        navigator.styles.width = min(max(width, NARROWEST), WIDEST)

    async def action_show_row(self, key: str) -> None:
        """Show the agent or channel a tab names, as choosing its row in the navigator does."""
        if self.live is not None:
            await self.show(self._focus_of(key))

    def action_inspector(self) -> None:
        self.toggle_class("inspector-shown")

    def action_open_line(self) -> None:
        self.query_one(Transcript).toggle()

    def action_folds(self) -> None:
        self.query_one(Transcript).unfold()

    def copy_line(self) -> None:
        """Send the chosen line's text to the terminal as OSC 52, each control shown as its escape, so pasting it acts
        on no terminal. Whether it reaches the clipboard is the terminal's."""
        chosen = self.query_one(Transcript).chosen
        if chosen is None:
            said = "No line is chosen, so nothing is copied: choose a line of the transcript, which Tab reaches."
            note(self, said, severity="warning")
            return
        text = self.query_one(Transcript).copied(chosen)
        self.app.copy_to_clipboard(text)
        said = (
            f"Sent the chosen line's {len(text):,} characters as OSC 52: whether they reach your clipboard is your "
            "terminal's."
        )
        if chosen.reading:
            said += " What it opens on is still being read, so its gist went in its place: /copy again once that shows."
        note(self, said)

    def action_page_up(self) -> None:
        self.query_one(Transcript).scroll_page_up(animate=False)

    def action_page_down(self) -> None:
        self.query_one(Transcript).scroll_page_down(animate=False)

    async def action_oldest(self) -> None:
        await self.query_one(Transcript).action_oldest()

    async def action_follow(self) -> None:
        await self.query_one(Transcript).action_follow()

    @work(group="act")
    async def action_find(self) -> None:
        """Find a line by the words its form takes, filled in with the last ones found, which decides nothing until it
        is sent. Sent, the transcript takes focus, so the line found shows as chosen there."""
        about = SafeText("words: what the line you look for shows, whatever its case, found back from the chosen one.")
        answer = await self.app.push_screen_wait(Form(SafeText("Find", "bold"), [("words", about, self.words)]))
        if answer is None:
            return
        if "words" not in answer:
            note(self, "No words were given, so no line is found.", severity="warning")
            return
        self.words = answer["words"]
        transcript = self.query_one(Transcript)
        transcript.focus()
        transcript.find(self.words)

    @work(group="act")
    async def action_attach_file(self) -> None:
        if self._refused_in_replay("attach_file"):
            return
        about = SafeText("A file to send as the message's body. The message's text is its gist.")
        given = await self.app.push_screen_wait(Form(Content.styled("Attach a file", "bold"), [("path", about, "")]))
        if not given or "path" not in given:
            return
        path = Path(given["path"]).expanduser()
        try:
            self.attached = (path.name, path.read_bytes())
        except OSError as error:
            note(self, f"{path}: {error}", severity="error")
            return
        self._redraw()

    @work(group="act")
    async def action_resume(self) -> None:
        live = self.live
        if self._refused_in_replay("resume"):
            return
        if live is None or live.runtime == "live" or is_held(live.session.folder):
            note(self, "A runtime holds this session already.")
            return
        if live.status.get("state") in ("closed", "cancelled"):
            note(self, "The session has ended, so nothing would come back.")
            return
        question = SafeText(f"Resume {self.session_name}? Its harnesses come back, which can spend money.")
        if not await self.app.push_screen_wait(Confirm(question)):
            return
        try:
            resumed = await Session.resume(self.session_name, detach=True)
        except Refused as refused:
            note(self, str(refused), severity="error")
            return
        await resumed.leave()

    def action_review(self) -> None:
        """List what changed, each commit and workspace opening its diff. Reading the list to its end moves your mark on
        the repository's stream."""
        live = self.live
        if live is None:
            return
        if (repo := live.status.get("repo")) is None:
            note(self, "Nothing is observed: the session's cwd is in no git repository.", severity="warning")
            return
        stream = f"repo/{repo}"

        def read(seq: int) -> None:
            self.marks[stream] = seq
            self._write_mark(live.session, stream, seq)

        mark = self.marks.get(stream, 0)
        self.app.push_screen(Review(live.session, live.changes, mark, read, self._test, snapshots_of(live.roster)))

    def action_tasks(self) -> None:
        """Show the tasks of the queue in view, or the entries of the board in view, read again as it moves, each act
        opening its op's form filled in."""
        live, focus = self.live, self.focus_on
        if live is None:
            return
        kinds = ("queue", "board")
        row = next(
            (row for row in live.channels if focus and row["name"] == focus.title and row["kind"] in kinds), None
        )
        if row is None:
            said = "Only a queue has tasks to show, and a board entries: choose one in the navigator first."
            note(self, said, severity="warning")
            return
        person = self.human.partition(":")[2]
        channel = f"{row['kind']}/{row['name']}"
        self.app.push_screen(Tasks(live.session, channel, person, self._open, self._cannot))

    def _cannot(self, op: str) -> str | None:
        """Why the person cannot run `op` now, or None when they can: in a replay, on history, and where their grants
        hold no `op`, as the page's acts say."""
        live = self.live
        if self.replaying:
            return nothing_acts(self.session_name)
        if live is None or live.runtime != "live":
            return f"history: {reach('resume')} resumes it to act"
        if all(form.op != op for form in self.forms):
            return f"your grants hold no {op}"
        return None

    def _open(self, act: Act) -> None:
        """Open the form of an act's op, which the person's grants hold, filled in with what its line knows."""
        self._run_op(next(form for form in self.forms if form.op == act.op), act.args)

    @work(group="act")
    async def _test(self, action: dict[str, Any]) -> None:
        """Test a commit, once the person says yes, since it runs that commit's code as them, unconfined."""
        live = self.live
        if self._refused_in_replay("test"):
            return
        if live is None or not await self.app.push_screen_wait(Confirm(SafeText(f"{action['label']}. Run it?"))):
            return
        outcome = await live.session.submit(action["op"], **action["args"])
        if outcome.refusal is not None:
            note(self, f"{outcome.refusal.code}: {outcome.refusal.detail}", severity="warning")
        else:
            note(self, f"Testing {action['args']['commit'][:12]}: open the changes again to see what it comes to.")

    def action_provenance(self) -> None:
        """Show the chosen line's provenance. Every line is an event, and one that carries another's words opens on what
        it carries. What an agent is saying now is no line, until the journal holds it."""
        live = self.live
        chosen = self.query_one(Transcript).chosen
        if live is None:
            return
        if chosen is None:
            said = (
                "No line is chosen, so no event has a provenance to show: choose a line of the transcript, which Tab "
                "reaches, with its arrows. What an agent is saying now is no event until the journal holds it."
            )
            note(self, said, severity="warning")
            return
        if isinstance(chosen, Fold):
            said = (
                "This line counts what an agent did in its turn, and is no event: open it, with Enter, and choose "
                "one of the lines it opens on, each of which is."
            )
            note(self, said, severity="warning")
            return
        self.app.push_screen(Provenance(live.session, shows(chosen.event), replay=self.player))

    @work(group="act")
    async def action_provenance_of(self) -> None:
        """Show the provenance of the event a ref given by hand names: its form is filled in with the chosen line's
        ref, which opens as the transcript's key opens it, and takes any other. One that names no event opens a panel
        that says why, as following one does."""
        live = self.live
        if live is None:
            return
        chosen = self.query_one(Transcript).chosen
        about = SafeText("ref: an event's ref, `stream@version`, the chosen line's unless you give another.")
        asked = [("ref", about, "" if chosen is None or isinstance(chosen, Fold) else shows(chosen.event))]
        answer = await self.app.push_screen_wait(Form(SafeText("Provenance", "bold"), asked))
        if answer is None:
            return
        if "ref" not in answer:
            said = (
                "No ref was given, so no event has a provenance to show: give one, or choose a line of the "
                "transcript, which Tab reaches, with its arrows. What an agent is saying now is no event until the "
                "journal holds it."
            )
            note(self, said, severity="warning")
            return
        self.app.push_screen(Provenance(live.session, answer["ref"], replay=self.player))

    async def action_thread(self) -> None:
        """Show the thread of the chosen line's message in the focus pane, where the composer replies to it."""
        chosen = self.query_one(Transcript).chosen
        if self.live is None:
            return
        if chosen is None or chosen.event.type != "message.sent":
            said = (
                "Only a message has a thread: choose a message's line of the transcript, which Tab reaches, with its "
                "arrows. What an agent says in its turn is no message, nor is an approval."
            )
            note(self, said, severity="warning")
            return
        await self.show(Focus.of_thread(chosen.event, self.human))

    def action_who_reached_whom(self) -> None:
        """Show who reached whom in the session, in the provenance panel, each link following into its event's."""
        if (live := self.live) is not None:
            self.app.push_screen(Provenance(live.session, None))

    def on_transcript_named(self, named: Transcript.Named) -> None:
        """Show the provenance of a ref a line's text names, saying it was opened from text, which records no link."""
        if (live := self.live) is not None:
            self.app.push_screen(Provenance(live.session, named.ref, from_text=True, replay=self.player))

    def _refused_in_replay(self, act: str) -> bool:
        """Say, in a replay, that `act`, an act's name or a form's title, does nothing there, and why."""
        if self.replaying:
            named = next((key.name for key in KEYMAP if key.action == act), act)
            note(self, f"{named}: {nothing_acts(self.session_name)}", severity="warning")
        return self.replaying

    def _playing(self) -> Player | None:
        """The replay's player, or None, saying what replays a session, in a session's workspace or before the replay
        has opened."""
        if self.player is None:
            said = (
                f"This is no replay, so nothing here plays: `platoon-harness attach {self.session_name} --replay` "
                "replays the session"
                if not self.replaying
                else "The replay is still opening."
            )
            note(self, said, severity="warning")
        return self.player

    def action_play(self) -> None:
        if (player := self._playing()) is not None:
            player.play()

    def action_speed(self) -> None:
        if (player := self._playing()) is not None:
            player.faster()

    @work(group="replay")
    async def action_step(self) -> None:
        if (player := self._playing()) is not None:
            await player.step(1)

    @work(group="replay")
    async def action_step_back(self) -> None:
        if (player := self._playing()) is not None:
            await player.step(-1)

    @work(group="replay")
    async def action_turn(self) -> None:
        if (player := self._playing()) is not None:
            await player.turn(1)

    @work(group="replay")
    async def action_turn_back(self) -> None:
        if (player := self._playing()) is not None:
            await player.turn(-1)

    @work(group="replay")
    async def action_jump(self) -> None:
        """Jump to an event or a time through a form, which decides nothing until it is sent."""
        if (player := self._playing()) is None:
            return
        about = SafeText(f"where: {JUMP}, from 0 to {player.total:,}.")
        answer = await self.app.push_screen_wait(Form(SafeText("Jump", "bold"), [("where", about, "")]))
        if not answer or "where" not in answer:
            return
        try:
            await player.jump(answer["where"])
        except ValueError as error:
            note(self, str(error), severity="warning")

    def action_planned(self, action: str) -> None:
        key = next(key for key in KEYMAP if key.action == action and key.planned)
        note(self, f"{key.does}: not built yet, as {key.planned}", severity="warning")

    def action_detach(self) -> None:
        """Leave the session to run on: back to the sessions screen when it is under this one, or out."""
        if self.query_one(Composer).text:
            said = f"{reach('detach')} detaches on an empty composer, and this one holds a draft."
            note(self, said, severity="warning")
            return
        if len(self.app.screen_stack) > 2:
            if (left := self.left()) is not None:
                note(self, f"Detached from {left}, which runs on.")
            self.app.pop_screen()
        else:
            self.app.exit(self.left())

    # The palette: the acts of a session, each by its typed command, then the write ops the person holds, each by its
    # form, worded as the command line words them.

    def commands(self) -> list[tuple[str, str, Any]]:
        acts = (*keys("everywhere"), *keys("workspace"), *keys("replay"))
        found: list[tuple[str, str, Any]] = [(key.typed, key.said, partial(self.run_action, key.runs)) for key in acts]
        for form in self.forms:
            found.append((form.title, form.summary, partial(self._run_op, form)))
        return found

    @work(group="act")
    async def _run_op(self, form: ops.Form, fixed: Mapping[str, Any] | None = None) -> None:
        """Run an op through its form, filled in from where you are, and with what a place's action fixes."""
        live = self.live
        if live is None or self._refused_in_replay(form.title):
            return
        given = {
            "agent": f"@{self.focus_on.agent}" if self.focus_on and self.focus_on.agent else "",
            "to": self.target or "",
            **{name: _shown(value) for name, value in (fixed or {}).items()},
        }
        asked = [(field.name, SafeText(_asked(field)), given.get(field.name, "")) for field in form.fields]
        title = SafeText(form.title, "bold")
        answer = await self.app.push_screen_wait(Form(title, asked)) if asked else {}
        if answer is None:
            return
        try:
            args = {field.name: _value(field, answer[field.name]) for field in form.fields if field.name in answer}
        except ValueError as error:
            note(self, str(error), severity="error")
            return
        for field in form.fields:
            if field.body and field.name in args:
                args[field.name] = await ops.body_ref(live.session, args[field.name])
        if form.op in CONFIRMED:
            question = SafeText(f"{form.title} {' '.join(map(str, args.values()))}? It cannot be taken back.")
            if not await self.app.push_screen_wait(Confirm(question)):
                return
        outcome = await live.session.submit(form.op, **args, **({"via": "tui"} if form.via else {}))
        if outcome.refusal is not None:
            note(self, f"{outcome.refusal.code}: {outcome.refusal.detail}", severity="warning")
        else:
            shown = json.dumps(outcome.result, ensure_ascii=False, separators=(",", ":"))
            note(self, f"{form.title}: done." + ("" if outcome.result is None else f" {shown}"))


def _asked(field: Flag) -> str:
    """What a form's field asks for, as the page's form shows it: its flag, whether it is needed, its help, what it
    takes where it takes one of a few, and what stands when it is left empty."""
    said = f"{field.flag[2:]}{' (needed)' if field.required else ''}: {field.help}"
    if field.kind in ("choice", "yes-no"):
        said += f" One of {', '.join(map(_shown, field.choices or (True, False)))}."
    if not field.required and (default := _shown(field.default)):
        said += f" Left empty: {default}."
    return said


def _shown(value: Any) -> str:
    """A value as a form shows it: yes or no, several separated by commas, JSON as its text, and nothing for none."""
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, list | tuple):
        return ", ".join(map(_shown, value))
    if isinstance(value, dict):
        return json.dumps(value)
    return "" if value is None else str(value)


def _value(field: Flag, text: str) -> Any:
    """A form's text as the value an op's field takes, by its kind, or a `ValueError` saying what it takes."""
    match field.kind:
        case "json":
            try:
                return json.loads(text)
            except ValueError as error:
                raise ValueError(f"{field.flag} takes JSON: {error}") from None
        case "yes-no":
            said = text.lower()
            if said not in ("y", "yes", "true", "1", "n", "no", "false", "0"):
                raise ValueError(f"{field.flag} is yes or no")
            return said in ("y", "yes", "true", "1")
        case "integer":
            if not re.fullmatch(r"-?\d+", text):
                raise ValueError(f"{field.flag} is a whole number")
            return int(text)
        case "number":
            try:
                return float(text)
            except ValueError:
                raise ValueError(f"{field.flag} is a number") from None
        case "choice":
            found = [choice for choice in field.choices if str(choice) == text]
            if not found:
                raise ValueError(f"{field.flag} is one of {', '.join(map(str, field.choices))}")
            return found[0]
        case "list":
            return [part.strip() for part in text.split(",") if part.strip()]
    return text
