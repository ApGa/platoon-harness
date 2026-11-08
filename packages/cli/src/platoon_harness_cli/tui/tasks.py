"""A queue's tasks or a board's entries, as a list a person reads, in the words both clients say, read again whenever
the channel moves."""

from collections.abc import Iterable

from textual import work
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.content import Content
from textual.screen import ModalScreen
from textual.widgets import Static

from platoon_harness import Refused, Session
from platoon_harness.kernel import Event

from .. import channels
from ..channels import View
from .keymap import bindings
from .review import STYLES
from .rows import Row, Rows
from .safe import SafeText


def rows_of(view: View) -> list[Row]:
    """A view's lines, a row each, every part made safe, each keyed by its ref."""
    return [
        Row(Content.assemble(*(SafeText(text, STYLES[tone]) for text, tone in line.parts)), line.key)
        for line in view.lines
    ]


class Tasks(ModalScreen[None]):
    """The view of `channel`, a queue's or a board's stream, as `channels.read` says it to `person`, read as it opens
    and again by `moved` whenever a frame holds an event that moves it, which the workspace's one reader of the
    journal hands it: no timer here decides anything."""

    BINDINGS = bindings("dialog")

    def __init__(self, session: Session, channel: str, person: str) -> None:
        super().__init__()
        self._session = session
        self.channel = channel
        self._person = person
        self.view: View | None = None

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog wide"):
            yield Static(SafeText(f"Reading {self.channel}…", "bold"), id="title")
            yield Rows(id="lines")
            yield Static(Content.styled("Esc: leave", "dim"))

    def on_mount(self) -> None:
        self._read()

    def moved(self, events: Iterable[Event]) -> None:
        """Read the view again when one of `events` moves it. Before the view is mounted, its first read, which mounting
        it begins, reads what they moved."""
        if self.is_mounted and any(channels.moves(self.channel, event) for event in events):
            self._read()

    @work(exclusive=True, group="tasks")
    async def _read(self) -> None:
        title = self.query_one("#title", Static)
        try:
            self.view = await channels.read(self._session, self.channel, self._person)
        except Refused as refused:
            title.update(SafeText(f"{self.channel}: {refused}", "red"))
            return
        title.update(SafeText(self.view.title, "bold"))
        self.query_one(Rows).show(rows_of(self.view))

    def action_leave(self) -> None:
        self.dismiss(None)
