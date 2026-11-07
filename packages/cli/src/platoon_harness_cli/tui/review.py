"""What changed, as a list a person reads: each workspace's commits and uncommitted paths, in the words both clients
say, and on a commit the act that tests it."""

from collections.abc import Callable, Collection, Mapping
from typing import Any

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.content import Content
from textual.screen import ModalScreen
from textual.widgets import Static

from ..review import Tone, changes_of
from .keymap import bindings
from .rows import Row, Rows
from .safe import SafeText, note

PLANNED = "Diffs come with review, which is planned."
STYLES: dict[Tone, str] = {"": "", "strong": "bold", "faint": "dim", "good": "green", "bad": "red", "warn": "yellow"}
"""How the terminal draws each tone of the shared wording."""


def rows_of(changes: Mapping[str, Mapping[str, Any]], mark: int, snapshots: Collection[str] = ()) -> list[Row]:
    """The changes as `changes_of` words them, a row each, every part made safe: a commit or a path past `mark` marked
    new, and each under its workspace's heading."""
    found = []
    for change in changes_of(changes, mark, snapshots):
        lead = ("● " if change.new else "  ", "cyan") if change.kind in ("commit", "path", "more") else ""
        parts = [SafeText(text, STYLES[tone]) for text, tone in change.parts]
        found.append(Row(Content.assemble(lead, *parts), change.key))
    return found


class Review(ModalScreen[None]):
    """What changed, as `rows_of` lists it. Reading to its end moves the person's mark on `repo/<name>`, through
    `read`. Choosing a commit takes its act, through `act`, or says why it is disabled. Diffs are drawn disabled, saying
    why."""

    BINDINGS = bindings("dialog")

    def __init__(
        self,
        changes: Mapping[str, Mapping[str, Any]],
        mark: int,
        read: Callable[[int], object],
        act: Callable[[Mapping[str, Any]], object],
        snapshots: Collection[str] = (),
    ) -> None:
        super().__init__()
        self._changes = changes
        self._rows = rows_of(changes, mark, snapshots)
        self._mark = mark
        self._newest = max((row["seq"] for row in changes.values()), default=0)
        self._read = read
        self._act = act

    def compose(self) -> ComposeResult:
        acted = any(row.get("actions") for row in self._changes.values())
        with Vertical(classes="dialog wide"):
            yield Static(Content.styled("What changed", "bold"))
            yield Rows(id="changes")
            yield Static(Content.styled(PLANNED, "dim"), id="diffs")
            yield Static(Content.styled("Enter on a commit: test it    Esc: leave" if acted else "Esc: leave", "dim"))

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
        actions = self._changes.get(chosen.key, {}).get("actions") or ()
        for action in actions:
            if action["disabled"]:
                note(self, f"{action['label']}: {action['disabled']}", severity="warning")
            else:
                self._act(action)

    def action_leave(self) -> None:
        self.dismiss(None)
