"""What changed, as a list a person reads: each workspace's commits and uncommitted paths, in the words both clients
say, on a commit the act that tests it, and a commit's patch or a workspace's uncommitted diff, a page at a time."""

from collections.abc import Callable, Collection, Mapping
from typing import Any

from textual import events, work
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.content import Content
from textual.screen import ModalScreen
from textual.widgets import Static

from platoon_harness import Refused, Session

from .. import review
from ..review import PAGE, Change, Diff, Tone, changes_of
from .composer import Composer
from .keymap import bindings, keys
from .rows import Row, Rows
from .safe import SafeText, note

STYLES: dict[Tone, str] = {"": "", "strong": "bold", "faint": "dim", "good": "green", "bad": "red", "warn": "yellow"}
"""How the terminal draws each tone of the shared wording."""
NUMBER = 6
"""How wide the column is that numbers a patch's lines."""
MORE = "more"
"""The key of the row that draws a patch's next page."""
GOES_ON = "↳ "
"""What leads a line that goes on git's line before it."""


def rows_of(changes: Mapping[str, Mapping[str, Any]], mark: int, snapshots: Collection[str] = ()) -> list[Row]:
    """The changes as `changes_of` words them, a row each, every part made safe: a commit or a path past `mark` marked
    new, and each under its workspace's heading."""
    return [_row(change) for change in changes_of(changes, mark, snapshots)]


def _row(change: Change) -> Row:
    lead = ("● " if change.new else "  ", "cyan") if change.kind in ("commit", "path", "more") else ""
    parts = [SafeText(text, STYLES[tone]) for text, tone in change.parts]
    return Row(Content.assemble(lead, *parts), change.key)


def patch_rows(diff: Diff, shown: int, width: int, chosen: tuple[int, int] | None = None) -> list[Row]:
    """A diff's first `shown` lines, each made safe and wrapped at `width` under its number, which its key is, marked
    where it is among the lines `chosen`, and led by `GOES_ON` where it continues the line before; then the row that
    draws on, while the patch has lines past these, or at its end, the words below it."""
    first, last = chosen or (0, -1)
    lines = diff.lines or ()
    rows = []
    for line in lines[:shown]:
        lead = GOES_ON if line.continues else ""
        wrapped = SafeText(line.text, STYLES[line.tone]).wrap(max(width - NUMBER - len(lead), 20)) or [Content("")]
        mark = ("┃", "cyan") if first <= line.number <= last else " "
        for at, part in enumerate(wrapped):
            number = (f"{line.number if at == 0 else '':>{NUMBER - 1}}", "dim")
            led = (lead if at == 0 else " " * len(lead), "dim")
            rows.append(Row(Content.assemble(number, mark, led, part), str(line.number)))
    if shown < len(lines):
        rows.append(Row(Content.styled(f"{len(lines) - shown} more lines: Enter reads on", "bold"), MORE))
    elif diff.below is not None:
        rows.append(Row(SafeText(diff.below, "yellow")))
    return rows


class Review(ModalScreen[None]):
    """What changed, as `rows_of` lists it. Reading to its end moves the person's mark on `repo/<name>`, through
    `read`. Choosing a commit opens its patch, and a workspace or one of its paths what it holds uncommitted. The key
    that tests takes the chosen commit's act, through `act`, or says why it is disabled."""

    BINDINGS = [*bindings("dialog"), *bindings("review")]

    def __init__(
        self,
        session: Session,
        changes: Mapping[str, Mapping[str, Any]],
        mark: int,
        read: Callable[[int], object],
        act: Callable[[Mapping[str, Any]], object],
        snapshots: Collection[str] = (),
    ) -> None:
        super().__init__()
        self._session = session
        self._changes = changes
        self._lines = {change.key: change for change in changes_of(changes, mark, snapshots) if change.key}
        self._rows = rows_of(changes, mark, snapshots)
        self._mark = mark
        self._newest = max((row["seq"] for row in changes.values()), default=0)
        self._read = read
        self._act = act

    def compose(self) -> ComposeResult:
        test = next(key.shown for key in keys("review") if key.action == "test")
        acted = any(row.get("actions") for row in self._changes.values())
        hint = (
            f"Enter: its diff    {test}: test the chosen commit    Esc: leave"
            if acted
            else "Enter: its diff    Esc: leave"
        )
        with Vertical(classes="dialog wide"):
            yield Static(Content.styled("What changed", "bold"))
            yield Rows(id="changes")
            yield Static(Content.styled(hint, "dim"))

    def on_mount(self) -> None:
        rows = self.query_one(Rows)
        rows.show(self._rows)
        self.watch(rows, "scroll_y", self._seen, init=False)
        self.call_after_refresh(self._seen)

    def _seen(self) -> None:
        """Move the mark through the newest row once the list's end is in view."""
        rows = self.query_one(Rows)
        if self._newest > self._mark and rows.scroll_offset.y + rows.size.height >= len(rows.rows):
            self._mark = self._newest
            self._read(self._newest)

    def on_rows_chosen(self, chosen: Rows.Chosen) -> None:
        change = self._lines.get(chosen.key)
        if change is not None and change.of is not None:
            self.app.push_screen(Patch(self._session, change.of))

    def action_test(self) -> None:
        change = self._lines.get(self.query_one(Rows).cursor or "")
        if change is None or change.kind != "commit":
            note(self, "Choose a commit to test.", severity="warning")
            return
        if not change.actions:
            note(self, "The team names no `test` command, so no commit can be tested.", severity="warning")
        for action in change.actions:
            if action["disabled"]:
                note(self, f"{action['label']}: {action['disabled']}", severity="warning")
            else:
                self._act(action)

    def action_leave(self) -> None:
        self.dismiss(None)


class Patch(ModalScreen[None]):
    """The diff of `of`, a commit's patch or what a workspace holds uncommitted, asked for with `repo.diff` as it opens:
    the runtime reads it, or gives the commit's patch it kept. Its lines are drawn `PAGE` at a time, each through
    `SafeText`, and Enter on the last row draws on. The key that chooses chooses `chosen` lines, and the key that
    comments opens a composer at the foot, whose words go to the change's maker citing them."""

    BINDINGS = [*bindings("dialog"), *bindings("patch")]

    def __init__(self, session: Session, of: str) -> None:
        super().__init__()
        self._session = session
        self._of = of
        self.diff: Diff | None = None
        self.shown = 0
        self.chosen: tuple[int, int] | None = None

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog wide"):
            yield Static(id="above")
            yield Rows(id="patch")
            yield Static(id="about")
            yield Composer(id="comment")
            yield Static(id="keys")

    def on_mount(self) -> None:
        self._composing(False)
        self._open()

    @work(exclusive=True, group="patch")
    async def _open(self) -> None:
        above = self.query_one("#above", Static)
        above.update(SafeText(f"Reading the diff of {self._of}…", "bold"))
        try:
            asked = await self._session.repo_diff(self._of)
            self.diff = await review.read(self._session, asked["effect"])
        except Refused as refused:
            above.update(SafeText(f"The diff of {self._of}: {refused}", "red"))
            return
        said = [SafeText(self.diff.above[0], "bold"), *(SafeText(line, "dim") for line in self.diff.above[1:])]
        above.update(Content("\n").join(said))
        self.shown = PAGE
        self._draw()

    def _draw_on(self) -> None:
        """Draw the patch's next page, the cursor on its first line."""
        lines = self.diff.lines if self.diff else None
        if lines is None or self.shown >= len(lines):
            return
        after, self.shown = self.shown, self.shown + PAGE
        self._draw()
        self.query_one(Rows).move_to(str(lines[after].number))

    def _draw(self) -> None:
        if self.diff is None:
            return
        listing = self.query_one(Rows)
        listing.show(patch_rows(self.diff, self.shown, listing.scrollable_content_region.width or 80, self.chosen))
        self._keys()

    def _keys(self) -> None:
        """The keys that do something here now."""
        if self.query_one(Composer).display:
            said = "Enter: send it    Esc: back to the patch, keeping what you wrote"
        else:
            choose, comment = (key.shown for key in keys("patch"))
            lines = self.diff.lines if self.diff else None
            more = "Enter on the last row: read on    " if lines and self.shown < len(lines) else ""
            said = f"{choose}: choose lines    {comment}: comment    {more}Esc: back to what changed"
        self.query_one("#keys", Static).update(Content.styled(said, "dim"))

    def action_choose(self) -> None:
        """Choose the line under the cursor; pressed on another, every line from the first to it; pressed again, or on
        the one line chosen alone, none."""
        cursor = self.query_one(Rows).cursor or ""
        if not cursor.isdigit():
            note(self, "Choose a line of the patch.", severity="warning")
            return
        line, chosen = int(cursor), self.chosen
        if chosen is None:
            self.chosen = (line, line)
        elif chosen[0] == chosen[1] != line:
            self.chosen = (min(chosen[0], line), max(chosen[0], line))
        else:
            self.chosen = None
        self._draw()
        self._about()

    def action_comment(self) -> None:
        diff = self.diff
        if diff is None:
            return
        if diff.to is None:
            note(self, diff.unsendable or "", severity="warning")
            return
        self._composing(True)

    def _composing(self, on: bool) -> None:
        """Show the composer a comment is written in, or hide it, keeping what it holds."""
        composer = self.query_one(Composer)
        self.query_one("#about", Static).display = composer.display = on
        self._about()
        if on:
            composer.focus()
        else:
            self.query_one(Rows).focus()
        if self.diff is not None:
            self._keys()

    def _about(self) -> None:
        if self.diff is not None and self.diff.to is not None:
            on = review.on(self.diff, self.chosen)
            said = Content.assemble("Comment to ", SafeText(self.diff.to, "bold"), " on ", SafeText(on))
            self.query_one("#about", Static).update(said)

    def on_composer_send(self) -> None:
        self._send()

    @work(group="comment")
    async def _send(self) -> None:
        composer, diff = self.query_one(Composer), self.diff
        text = composer.text.strip()
        if diff is None or not text:
            return
        try:
            cited = await review.comment(self._session, diff, self.chosen, text)
        except Refused as refused:
            note(self, str(refused), severity="error")
            return
        composer.remember()
        self.chosen = None
        self._composing(False)
        self._draw()
        note(self, f"Sent to {diff.to}, citing {cited}.")

    def on_resize(self, event: events.Resize) -> None:
        self.call_after_refresh(self._draw)

    def on_rows_chosen(self, chosen: Rows.Chosen) -> None:
        if chosen.key == MORE:
            self._draw_on()

    def action_leave(self) -> None:
        """Go back to the patch from the composer, keeping what it holds, and from the patch to what changed."""
        if self.query_one(Composer).display:
            self._composing(False)
        else:
            self.dismiss(None)
