"""An approval's whole ask, as a person reads it before answering it, in the words both clients say, each line drawn as
it was asked."""

from textual import events, work
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.content import Content
from textual.screen import ModalScreen
from textual.widgets import Static

from platoon_harness import Refused, Session

from .. import approvals
from ..approvals import Ask
from .keymap import bindings
from .rows import Row, Rows
from .safe import SafeText


def rows_of(ask: Ask, width: int) -> list[Row]:
    """An ask's lines wrapped at `width`, each made safe and never read as markup or Markdown, so what it asks is
    drawn as it was asked, or its gist where it has no text, then the words below it."""
    lines = [SafeText(line) for line in (ask.gist if ask.text is None else ask.text).split("\n")]
    lines += [] if ask.below is None else [SafeText(ask.below, "yellow")]
    rows: list[Row] = []
    for line in lines:
        parts: list[Content] = line.wrap(max(width, 20)) or [Content("")]
        for part in parts:
            rows.append(Row(part))
    return rows


class Approval(ModalScreen[None]):
    """The whole of what the approval `id` asks, whose request the journal holds at `seq`, read as it opens. It answers
    nothing: Esc goes back to where its place's actions answer it."""

    BINDINGS = bindings("dialog")

    def __init__(self, session: Session, id: str, seq: int) -> None:
        super().__init__()
        self._session = session
        self._approval = id
        self._at = seq
        self.ask: Ask | None = None

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog wide"):
            yield Static(id="asked")
            yield Rows(id="ask")
            yield Static(Content.styled("Esc: back, to answer it", "dim"))

    def on_mount(self) -> None:
        self._read()

    @work(exclusive=True, group="ask")
    async def _read(self) -> None:
        asked = self.query_one("#asked", Static)
        asked.update(SafeText(f"Reading what approval {self._approval} asks…", "bold"))
        try:
            request = await approvals.request(self._session, self._approval, self._at)
            self.ask = await approvals.read(self._session, request)
        except Refused as refused:
            asked.update(SafeText(f"What approval {self._approval} asks: {refused}", "red"))
            return
        asked.update(SafeText(f"What @{self.ask.agent} asks", "bold"))
        self._draw()

    def _draw(self) -> None:
        if self.ask is not None:
            listing = self.query_one(Rows)
            listing.show(rows_of(self.ask, listing.scrollable_content_region.width or 80))

    def on_resize(self, event: events.Resize) -> None:
        self.call_after_refresh(self._draw)

    def action_leave(self) -> None:
        self.dismiss(None)
