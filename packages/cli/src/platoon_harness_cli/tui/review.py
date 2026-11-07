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
from ..review import Change, Diff, Page, Tone, changes_of
from .keymap import bindings, keys
from .rows import Row, Rows
from .safe import SafeText, note

STYLES: dict[Tone, str] = {"": "", "strong": "bold", "faint": "dim", "good": "green", "bad": "red", "warn": "yellow"}
"""How the terminal draws each tone of the shared wording."""
NUMBER = 6
"""How wide the column is that numbers a patch's lines."""
MORE = "more"
"""The key of the row that reads a patch's next page."""


def rows_of(changes: Mapping[str, Mapping[str, Any]], mark: int, snapshots: Collection[str] = ()) -> list[Row]:
    """The changes as `changes_of` words them, a row each, every part made safe: a commit or a path past `mark` marked
    new, and each under its workspace's heading."""
    return [_row(change) for change in changes_of(changes, mark, snapshots)]


def _row(change: Change) -> Row:
    lead = ("● " if change.new else "  ", "cyan") if change.kind in ("commit", "path", "more") else ""
    parts = [SafeText(text, STYLES[tone]) for text, tone in change.parts]
    return Row(Content.assemble(lead, *parts), change.key)


def patch_rows(diff: Diff, pages: list[Page], width: int) -> list[Row]:
    """A diff's lines read so far, each made safe and wrapped at `width` under its number, which its key is; then the
    row that reads on, while the patch has lines past these, or at its end, the words below it."""
    rows = []
    for line in (line for got in pages for line in got.lines):
        wrapped = SafeText(line.text, STYLES[line.tone]).wrap(max(width - NUMBER, 20)) or [Content("")]
        for at, part in enumerate(wrapped):
            number = (f"{line.number if at == 0 else '':>{NUMBER - 1}} ", "dim")
            rows.append(Row(Content.assemble(number, part), str(line.number)))
    last = pages[-1] if pages else None
    if last is not None and last.rest is not None:
        shown = last.lines[-1].number if last.lines else 0
        rows.append(Row(Content.styled(f"{last.total - shown} more lines: Enter reads on", "bold"), MORE))
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
    the runtime reads it, or gives the commit's patch it kept. Its lines are read a page at a time, as `blob.get` gives
    them, each drawn through `SafeText`, and Enter on the last row reads on."""

    BINDINGS = bindings("dialog")

    def __init__(self, session: Session, of: str) -> None:
        super().__init__()
        self._session = session
        self._of = of
        self.diff: Diff | None = None
        self.pages: list[Page] = []

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog wide"):
            yield Static(id="above")
            yield Rows(id="patch")
            yield Static(id="keys")

    def on_mount(self) -> None:
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
        self.pages = [] if self.diff.first is None else [self.diff.first]
        self._draw()

    @work(exclusive=True, group="patch")
    async def _read_on(self) -> None:
        rest = self.pages[-1].rest if self.pages else None
        if rest is None:
            return
        try:
            found = await review.page(self._session, rest)
        except Refused as refused:
            note(self, str(refused), severity="error")
            return
        if found is not None:
            self.pages.append(found)
        self._draw()
        if found is not None and found.lines:
            self.query_one(Rows).move_to(str(found.lines[0].number))

    def _draw(self) -> None:
        if self.diff is None:
            return
        listing = self.query_one(Rows)
        listing.show(patch_rows(self.diff, self.pages, listing.scrollable_content_region.width or 80))
        more = "Enter on the last row: read on    " if self.pages and self.pages[-1].rest else ""
        self.query_one("#keys", Static).update(Content.styled(f"{more}Esc: back to what changed", "dim"))

    def on_resize(self, event: events.Resize) -> None:
        self.call_after_refresh(self._draw)

    def on_rows_chosen(self, chosen: Rows.Chosen) -> None:
        if chosen.key == MORE:
            self._read_on()

    def action_leave(self) -> None:
        self.dismiss(None)
