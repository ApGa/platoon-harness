"""The workspace: one session, as a person works with it every day."""

import json
from collections import defaultdict
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
from textual.widgets import Static

from platoon_harness import Refused, Session
from platoon_harness.config import Manifest
from platoon_harness.kernel import GIST_LIMIT, Event, is_held
from platoon_harness.runtime.paths import MANIFEST

from ..ops import Flag, described, flags, person_ops
from .composer import ADDRESS, Composer
from .dialogs import Confirm, Form
from .keymap import KEYMAP, action_of, bindings, command, keys, reach
from .live import Live
from .rows import Row, Rows
from .safe import SafeText, note
from .transcript import PAGE, Focus, Transcript

GROUPS = (
    ("needs_you", "Needs you", "⚠", "yellow"),
    ("working", "Working", "●", "green"),
    ("blocked", "Blocked", "◌", "yellow"),
    ("idle", "Idle", "○", "dim"),
    ("done", "Done", "✓", "dim green"),
    ("failed", "Failed", "✗", "red"),
)
GLYPHS = {group: (glyph, style) for group, _, glyph, style in GROUPS}
UNREAD = 100
"""The most unread lines a badge counts: past it, it says `99+`."""
CONFIRMED = frozenset({"agent.cancel", "agent.retire", "body.tombstone", "session.cancel", "session.close"})
"""The commands the palette asks once about: each ends an agent or the session, or erases a body, which nothing takes
back."""
UNBUILT = {"agent.takeover": "take_over"}
"""Commands whose purpose the TUI cannot carry out yet, by the key that says why: a takeover holds an agent's deliveries
for a person to drive its own terminal, which is not built, so the palette says so rather than hold them."""
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
    """The agents and channels, a row each, of which Enter shows the chosen one."""

    BINDINGS = bindings("panel")


def _why(why: dict[str, Any] | None) -> str:
    """What an agent waits on, in words, from the roster's typed `why`."""
    if why is None:
        return ""
    match why["kind"]:
        case "approval":
            return "asks you to approve"
        case "wait":
            missing = ", ".join(why["missing"][:3]) + ("…" if len(why["missing"]) > 3 else "")
            return f"waits {why['have']} of {why['need']}" + (f", for {missing}" if missing else "")
        case "peer":
            return f"waits on @{why['id']}"
        case "budget":
            return f"held by the budget: {why['code']}"
        case "lease":
            return f"holds {why['id']}"
        case "timer":
            return "a wake is due"
        case "infra":
            return why["detail"]
        case "lost":
            return f"lost: {why['reason']}"
    return why["kind"]


def _named(action: str) -> str:
    """An action as a person calls it, by the keymap's name for it."""
    return next(key.name for key in KEYMAP if key.action == action)


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


def _unmeasured(count: int) -> str:
    return f"{count} turn{'' if count == 1 else 's'} unmeasured"


class Workspace(Screen[None]):
    """One session: who is working, on what, what is blocked, what changed, and where you must act."""

    BINDINGS = [*bindings("workspace"), *bindings("parts")]

    def __init__(self, name: str, session: Session | None = None) -> None:
        super().__init__()
        self.session_name = name
        self.live: Live | None = None
        self.focus_on: Focus | None = None
        self.target: str | None = None
        self.attached: tuple[str, bytes] | None = None
        self.marks: dict[str, int] = {}
        self.unread: dict[str, int] = {}
        self.human = "human:you"
        self._given = session
        self._refused: dict[tuple[str, str], tuple[str, str]] = {}
        self._shown: dict[str, Content] = {}
        self._queued: dict[str, Any] | None = None
        self._unmarked = False

    def compose(self) -> ComposeResult:
        yield Static(id="header")
        yield Static(id="banner")
        with Horizontal(id="body"):
            yield Navigator(id="navigator")
            with Vertical(id="focus"):
                yield Static(id="title")
                yield Transcript(id="transcript")
                yield Static(id="behind")
            yield Static(id="inspector")
        yield Static(id="strip")
        yield Dock(id="dock")
        yield Static(id="chip")
        yield Composer(id="composer")
        yield Static(id="footer")

    async def on_mount(self) -> None:
        composer = self.query_one(Composer)
        composer.known = self._known
        composer.focus()
        self._lay_out(self.size.width, self.size.height)
        self.query_one("#header", Static).update(SafeText(f"{self.session_name}  attaching…", "bold"))
        self._join()

    @work(exclusive=True, group="attach")
    async def _join(self) -> None:
        try:
            session = self._given or await Session.attach(self.session_name)
            self.human = Manifest.model_validate_json((session.folder / MANIFEST).read_bytes()).human
            through = await session.head()
        except Refused as refused:
            self.query_one("#header", Static).update(SafeText(f"{self.session_name}: {refused}", "red"))
            return
        try:
            self.marks = await session.marks()
        except Refused as refused:
            self._lose_marks(refused)
        self.query_one(Transcript).through = through
        self.live = Live(session, self._draw, partial(self.run_worker, group="live"))
        self.live.start(through)

    async def on_unmount(self) -> None:
        """Leave as a guest leaves: the session, and its runtime, run on."""
        if self.live is not None:
            self.live.stop()
            await self.live.session.leave()

    def left(self) -> str | None:
        """The session that runs on once you leave it, or None when no runtime holds it."""
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
        added = transcript.take(events)
        transcript.draw(live.tail)
        if said and not events:  # Live text alone moves nothing but the transcript.
            return
        await self._count(events, live, transcript.through)
        if focus is None and (live.roster or live.frames == 0):
            await self.show(self._first_focus(live))
        elif focus is not None and (added or transcript.following):
            self._mark(transcript)
        await self._read_queue(live)
        self._redraw()

    def _first_focus(self, live: Live) -> Focus:
        """The agent the session started first, or what was sent to you when it started none."""
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
            page = await session.page(
                after=mark, before=before, streams=focus.streams or None, match=focus.match, limit=PAGE
            )
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
                self.run_worker(self._mark_one(live.session, stream, transcript.through), group="marks")
        self.unread[focus.key] = 0

    async def _mark_one(self, session: Session, stream: str, seq: int) -> None:
        try:
            await session.mark(stream, seq)
        except Refused as refused:
            self._lose_marks(refused)

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
        self._set("#title", self._title())
        self.query_one("#title").set_class(self.query_one(Transcript).has_focus, "-focused")
        self._set("#behind", self._behind())
        self.query_one("#behind").set_class(not self.query_one(Transcript).following, "-shown")
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
        counts = defaultdict(int)
        for row in live.roster:
            counts[row["group"]] += 1
        acting = len(self._places(live))
        if self.size.width < 60:
            return Content.assemble(
                SafeText(self.session_name, "bold"),
                f" {counts['working']}● ",
                (f"{acting}⚠", "yellow" if acting else "dim"),
            )
        runtime = ("live", "green") if live.runtime == "live" else ("history", "yellow")
        standing = "waiting for you" if live.status.get("stalled") else "settled" if live.status.get("settled") else ""
        state = live.status.get("state", "") + (f", {standing}" if standing else "")
        parts: list[Any] = [SafeText(self.session_name, "bold"), "  ", runtime, (f" {state}   ", "dim")]
        parts += [(f"● {counts['working']} working  ", "green")]
        parts += [(f"⚠ {acting} need you  ", "yellow" if acting else "dim")]
        if counts["blocked"]:
            parts += [(f"◌ {counts['blocked']} blocked  ", "yellow")]
        if counts["failed"]:
            parts += [(f"✗ {counts['failed']} failed  ", "red")]
        return Content.assemble(*parts, self._changed(live), "  ", *self._spent(live))

    def _changed(self, live: Live) -> Content:
        """What changed, as the turn-end probe says it. Nothing measures it before workspaces land, and that is said."""
        if not live.changes:
            return Content.styled("changes not measured", "dim")
        added = sum(row["added"] or 0 for row in live.changes.values())
        removed = sum(row["removed"] or 0 for row in live.changes.values())
        return Content(f"changed {len(live.changes)} files +{added} -{removed}")

    def _spent(self, live: Live) -> list[Any]:
        """Each shared limit and what is spent against it, any metered amount with no limit, and once how many turns
        nobody measured whole, after `spent ?` when nothing else would show."""
        limits = {row["unit"]: row for row in live.budgets if row["scope"] == "shared"}
        usage = live.ending.usage if live.ending else {}
        said = [
            _spend(unit, None if row["label"] == "unavailable" else row["spent"], row["label"], row["limit"])
            for unit, row in limits.items()
        ]
        said += [
            _spend(unit, used["amount"], used["label"], None)
            for unit, used in usage.items()
            if unit in ("tokens", "usd") and unit not in limits and used["amount"] is not None
        ]
        unmeasured = max((used["unmeasured"] for used in usage.values()), default=0)
        if not unmeasured:
            return ["  ".join(said)]
        return ["  ".join(said or ["spent ?"]), (f" ({_unmeasured(unmeasured)})", "dim")]

    def _banner(self, live: Live) -> Content:
        """Why this is history, from the session's state: its runtime stopped as its owner asked, went without its
        shutdown, or the session has ended."""
        state = live.status.get("state")
        resume = f" {reach('resume')} resumes it, which can spend money."
        if state in ("closed", "cancelled"):
            return Content.styled(f"The session is {state}: this is its history.", "yellow")
        if state == "stopped":
            return Content.styled(f"Its runtime stopped, as its owner asked: this is its history.{resume}", "yellow")
        if state in ("open", "closing"):
            went = f"Its runtime went without its shutdown, killed or crashed: this is its history.{resume}"
            return Content.styled(went, "red")
        return Content.styled(f"No runtime holds this session, so this is its history.{resume}", "yellow")

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
        mentioned = self._mentions(live)
        rows: list[Row] = []
        members: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in live.roster:
            members[row["group"]].append(row)
        for group, title, glyph, style in GROUPS:
            if not members[group]:
                continue
            rows.append(Row(Content.styled(f"{title} ({len(members[group])})", "bold dim")))
            names = {row["agent"] for row in members[group]}
            under: dict[str | None, list[dict[str, Any]]] = defaultdict(list)
            for row in members[group]:
                under[row["parent"] if row["parent"] in names else None].append(row)
            rows += self._tree(under, None, 0, glyph, style, mentioned)
        if not live.roster:
            rows.append(Row(Content.styled("No agents yet", "dim")))
        rows.append(Row(Content.styled("Channels", "bold dim")))
        for focus in self._foci(live):
            unread = self.unread.get(focus.key, 0)
            count = (f"{UNREAD - 1}+" if unread >= UNREAD else str(unread)) if unread else ""
            mark = ("@", "yellow") if focus.key in mentioned else ""
            rows.append(Row(Content.assemble(SafeText(focus.title), (f" {count}", "bold"), " ", mark), focus.key))
        return rows

    def _tree(
        self,
        under: dict[str | None, list[dict[str, Any]]],
        parent: str | None,
        depth: int,
        glyph: str,
        style: str,
        mentioned: set[str],
    ) -> list[Row]:
        rows = []
        for row in sorted(under[parent], key=lambda found: found["agent"]):
            detail = _why(row["why"]) if row["group"] in ("blocked", "needs_you", "failed") else row["activity"] or ""
            stopped = f"turn {row['stopped']}" if row["stopped"] and row["group"] == "idle" else ""
            line = Content.assemble(
                "  " * depth,
                (f"{glyph} ", style),
                SafeText(f"@{row['agent']}", "bold"),
                ("@" if f"@{row['agent']}" in mentioned else "", "yellow"),
                SafeText(f" {_harness(row)} ", "dim"),
                (f"↧{row['unread']} " if row["unread"] else "", "cyan"),
                SafeText(" ".join((stopped or detail).split())),
            )
            rows.append(Row(line, f"@{row['agent']}"))
            rows += self._tree(under, row["agent"], depth + 1, glyph, style, mentioned)
        return rows

    def _strip(self, live: Live) -> Content:
        """The team on one line, for a screen too narrow for the navigator."""
        return Content.assemble(
            *(
                part
                for row in live.roster
                for part in (
                    (f"{GLYPHS[row['group']][0]}", GLYPHS[row["group"]][1]),
                    SafeText(f"{row['agent']}  "),
                )
            )
        )

    def _title(self) -> Content:
        focus = self.focus_on
        if focus is None:
            return Content("")
        row = self._row(focus.agent)
        if row is None:
            return SafeText(focus.title, "bold")
        return Content.assemble(
            SafeText(focus.title, "bold"),
            SafeText(f"  {row['role']} on {_harness(row)}", "dim"),
            SafeText(f"  {row['state']}", GLYPHS[row["group"]][1]),
            SafeText(f"  {_why(row['why'])}"),
        )

    def _behind(self) -> Content:
        unseen = self.query_one(Transcript).unseen
        follow = reach("follow")
        return Content.styled(f"↓ {unseen} new, {follow} to follow" if unseen else f"{follow} to follow", "reverse")

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
        if row["why"] is not None:
            lines.append(SafeText(f"why {_why(row['why'])}", "yellow"))
        if row["held_by"]:
            lines.append(SafeText(f"held by @{row['held_by']}"))
        for level, said in (row["levels"] or {}).items():
            reasons = "; ".join(said.get("reasons", ()))
            lines.append(SafeText(f"{level} {said.get('state')}" + (f": {reasons}" if reasons else "")))
        for unit, usage in row["usage"].items():
            unmeasured = f", {_unmeasured(usage['unmeasured'])}" if usage.get("unmeasured") else ""
            label = f" ({usage.get('label', 'unavailable')}{unmeasured})"
            lines.append(Content.assemble(_spend(unit, usage.get("amount"), "", None), (label, "dim")))
        gaps = [gap for gap in (live.ending.gaps if live.ending else ()) if gap["agent"] == row["agent"]]
        lines += [SafeText(f"gap {gap['what']}, {gap['count']} on the {gap['plane']} plane", "yellow") for gap in gaps]
        lines += [
            SafeText(f"{_named(action)}: {reason}", "dim")
            for (action, agent), (reason, _) in self._refused.items()
            if agent == row["agent"]
        ]
        return Content("\n").join(lines)

    def _dock(self, live: Live) -> list[Row]:
        """A row per place you must act, and on the one you are at, the keys that take its actions from where the focus
        is: the dock's own letters, or a session's typed commands. A dock with focus and no place chosen says how to
        choose one on its first row. Hints come before the gist, so a narrow screen cuts the gist and never a hint."""
        dock = self.query_one(Dock)
        chosen = dock.cursor
        rows = []
        acts = ("first_action", "second_action")
        first, second = [key.shown for key in keys("dock")] if dock.has_focus else [reach(act) for act in acts]
        for index, place in enumerate(self._places(live)):
            actions = place["actions"]
            hints: list[Any] = []
            if place["id"] == chosen:
                hints = [
                    (f"{hint} {action['label']}  ", "bold")
                    for hint, action in zip((first, second), actions, strict=False)
                ]
            elif chosen is None and dock.has_focus and index == 0:
                hints = [(f"{CHOOSE}  ", "bold")]
            line = Content.assemble(
                ("⚠ ", "yellow"),
                (f"{place['kind']} ", "bold"),
                SafeText(f"@{place['agent']} " if place["agent"] else ""),
                *hints,
                SafeText(" ".join(place["gist"].split())),
            )
            rows.append(Row(line, place["id"]))
        return rows

    def _unsendable(self, live: Live) -> str | None:
        """Why the composer cannot send now, or None when it can."""
        if live.runtime != "live":
            return f"history: {reach('resume')} resumes it to send"
        if self.target is None:
            return f"{self.focus_on.title if self.focus_on else 'this'} takes no message: choose an agent or a topic"
        return None

    def _chip(self, live: Live) -> Content:
        cannot = self._unsendable(live)
        if cannot is not None:
            return SafeText(cannot, "dim")
        parts: list[Any] = [("to: ", "dim"), SafeText(self.target or "", "bold reverse")]
        if self._queued is not None:
            ways = sorted({entry["delivery"] for entry in self._queued["entries"]})
            parts += [(f"  queued {self._queued['total']}: {', '.join(ways)}", "cyan")]
        if self.attached is not None:
            parts += [SafeText(f"  + {self.attached[0]} ({len(self.attached[1]):,} bytes)", "magenta")]
        return Content.assemble(*parts)

    def _footer(self, live: Live) -> Content:
        """How to reach the typed commands, which every terminal delivers, then the footer's keys, each named by what it
        runs from the part with focus, which may take it for its own, and dim while the runtime refuses that for the
        agent in view, then how many places need you."""
        agent = self.focus_on.agent if self.focus_on else None
        active = self.active_bindings
        parts: list[Any] = [("/", "bold"), (" commands", "dim"), "  "]
        for key in (*keys("everywhere"), *keys("workspace")):
            if not key.footer:
                continue
            runs = active[key.keys.split(",")[0]].binding.action
            now = next((other for other in KEYMAP if other.runs == runs), key)
            off = (now.action, agent or "") in self._refused
            label = "" if self.size.width < 60 else f" {now.name}"
            parts += [(key.shown, "dim" if off else "bold"), (label, "dim strike" if off else "dim"), "  "]
        if places := len(self._places(live)):
            parts.append((f" ⚠ {places} need you ", "bold reverse yellow"))
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
        self.focus_on = focus
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
        target = self.target
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
        if self.attached is not None and len(text) > GIST_LIMIT:
            note(self, "a long message and a file are two bodies: send them one at a time", severity="warning")
            return
        gist, body = text, None
        if self.attached is not None:
            gist, body = text or f"file {self.attached[0]}", self.attached[1]
        elif len(text) > GIST_LIMIT:
            gist, body = f"{text[: GIST_LIMIT - 1]}…", text
        try:
            await live.session.send(target, gist, body=body)
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

    @work(group="act")
    async def _act(self, index: int, chosen: str | None) -> None:
        """Take an action of the place you were at when you asked, as its row offers it, with the version it was drawn
        from."""
        live = self.live
        place = live.attention.get(chosen or "") if live else None
        if live is None or place is None or index >= len(place["actions"]):
            how = CHOOSE if self.query_one(Dock).has_focus else f"{reach('next_place')} goes to where you must act"
            note(self, f"Nothing here takes that action: {how}.", severity="warning")
            return
        action = place["actions"][index]
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

    def action_inspector(self) -> None:
        self.toggle_class("inspector-shown")

    def action_open_line(self) -> None:
        self.query_one(Transcript).toggle()

    def action_page_up(self) -> None:
        self.query_one(Transcript).scroll_page_up(animate=False)

    def action_page_down(self) -> None:
        self.query_one(Transcript).scroll_page_down(animate=False)

    async def action_oldest(self) -> None:
        await self.query_one(Transcript).action_oldest()

    async def action_follow(self) -> None:
        await self.query_one(Transcript).action_follow()

    @work(group="act")
    async def action_attach_file(self) -> None:
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

    # The palette: the acts of a session, each by its typed command, then the commands a person may run, worded as
    # the command line words them.

    def commands(self) -> list[tuple[str, str, Any]]:
        acts = (*keys("everywhere"), *keys("workspace"))
        found: list[tuple[str, str, Any]] = [(key.typed, key.said, partial(self.run_action, key.runs)) for key in acts]
        for name, operation in sorted(person_ops().items()):
            if operation.query or operation.exposes:  # A read is what the screen draws, and the command line prints.
                continue
            title = name.replace(".", " ")
            if (planned := UNBUILT.get(name)) is not None:
                key = next(key for key in KEYMAP if key.action == planned)
                found.append((title, f"Not built yet: {key.planned}", partial(self.action_planned, planned)))
            else:
                first = described(operation).partition(". ")[0].rstrip(".")
                found.append((title, f"{first}.", partial(self._run_op, name)))
        return found

    @work(group="act")
    async def _run_op(self, name: str) -> None:
        live = self.live
        if live is None:
            return
        operation = person_ops()[name]
        schema = operation.input.model_json_schema()
        fields = flags(operation)
        given = {
            "agent": f"@{self.focus_on.agent}" if self.focus_on and self.focus_on.agent else "",
            "to": self.target or "",
        }
        asked = [
            (
                field.name,
                SafeText(f"{field.flag[2:]}: {schema['properties'][field.name].get('description', '')}"),
                given.get(field.name, ""),
            )
            for field in fields
        ]
        answer = await self.app.push_screen_wait(Form(SafeText(name.replace(".", " "), "bold"), asked)) if asked else {}
        if answer is None:
            return
        try:
            args = {field.name: _value(field, answer[field.name]) for field in fields if field.name in answer}
        except ValueError as error:
            note(self, str(error), severity="error")
            return
        for field in fields:
            if field.body and field.name in args:
                args[field.name] = await live.session.put_body(args[field.name].encode())
        if name in CONFIRMED:
            question = SafeText(
                f"{name.replace('.', ' ')} {' '.join(map(str, args.values()))}? It cannot be taken back."
            )
            if not await self.app.push_screen_wait(Confirm(question)):
                return
        outcome = await live.session.submit(name, **args)
        if outcome.refusal is not None:
            note(self, f"{outcome.refusal.code}: {outcome.refusal.detail}", severity="warning")
        else:
            note(self, f"{name.replace('.', ' ')}: done")


def _value(field: Flag, text: str) -> Any:
    """A form's text as the value an op's field takes, or a `ValueError` saying what it takes."""
    if field.json:
        return json.loads(text)
    kinds = [
        kind for kind in (*getattr(field.annotation, "__args__", ()), field.annotation) if kind in (int, float, bool)
    ]
    if bool in kinds:
        said = text.lower()
        if said not in ("y", "yes", "true", "1", "n", "no", "false", "0"):
            raise ValueError(f"{field.name} is yes or no")
        return said in ("y", "yes", "true", "1")
    if kinds:
        return kinds[0](text)
    if "tuple" in str(field.annotation):
        return [part.strip() for part in text.split(",") if part.strip()]
    return text
