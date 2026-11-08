"""A queue's tasks or a board's entries, as a list a person reads, in the words both clients say, read again whenever
the channel moves, each act a row of its own that opens its op's form filled in with what its line knows, or that is
drawn disabled, saying why, where the person cannot run its op now."""

from collections.abc import Callable, Iterable

from textual import work
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.content import Content
from textual.screen import ModalScreen
from textual.widgets import Static

from platoon_harness import Refused, Session
from platoon_harness.kernel import Event

from .. import channels
from ..channels import Act, View
from .keymap import bindings
from .review import STYLES
from .rows import Row, Rows
from .safe import SafeText, note

UNDER = "  ↳ "
"""What leads an act's row, under the line it acts on."""


def rows_of(view: View, cannot: Callable[[str], str | None]) -> tuple[list[Row], dict[str, Act]]:
    """A view's rows, every part made safe: the acts on the channel itself first, then each line, keyed by its ref,
    with each of its acts a row under it, dim with the reason where `cannot` says why the person cannot run its op now;
    and the act each act's row takes, by its key."""
    rows: list[Row] = []
    acts: dict[str, Act] = {}

    def offer(on: str, offered: Iterable[Act], lead: str) -> None:
        for index, act in enumerate(offered):
            key = f"{on}#{index}"
            acts[key] = act
            why = cannot(act.op)
            label = SafeText(act.label, "bold") if why is None else SafeText(f"{act.label} · {why}", "dim")
            rows.append(Row(Content.assemble((lead, "dim"), label), key))

    offer("", view.acts, "")
    for line in view.lines:
        rows.append(Row(Content.assemble(*(SafeText(text, STYLES[tone]) for text, tone in line.parts)), line.key))
        offer(line.key or "", line.acts, UNDER)
    return rows, acts


class Tasks(ModalScreen[None]):
    """The view of `channel`, a queue's or a board's stream, as `channels.read` says it to `person`, read as it opens
    and again by `moved` whenever a frame holds an event that moves it, which the workspace's one reader of the
    journal hands it: no timer here decides anything. Enter on an act's row opens its op's form, through `act`, or
    where `cannot` says why the person cannot run its op now, says that, as its row does, drawn again each frame."""

    BINDINGS = bindings("dialog")

    def __init__(
        self,
        session: Session,
        channel: str,
        person: str,
        act: Callable[[Act], object],
        cannot: Callable[[str], str | None],
    ) -> None:
        super().__init__()
        self._session = session
        self.channel = channel
        self._person = person
        self._act = act
        self._cannot = cannot
        self.view: View | None = None
        self._acts: dict[str, Act] = {}

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog wide"):
            yield Static(SafeText(f"Reading {self.channel}…", "bold"), id="title")
            yield Rows(id="lines")
            yield Static(Content.styled("Enter on an act: its form, filled in    Esc: leave", "dim"))

    def on_mount(self) -> None:
        self._read()

    def moved(self, events: Iterable[Event]) -> None:
        """Read the view again when one of `events` moves it, and else draw its acts again, as whether the person can
        run each may have changed. Before the view is mounted, its first read, which mounting it begins, reads what
        they moved."""
        if not self.is_mounted:
            return
        if any(channels.moves(self.channel, event) for event in events):
            self._read()
        elif self.view is not None:
            self._show(self.view)

    @work(exclusive=True, group="tasks")
    async def _read(self) -> None:
        title = self.query_one("#title", Static)
        try:
            self.view = await channels.read(self._session, self.channel, self._person)
        except Refused as refused:
            title.update(SafeText(f"{self.channel}: {refused}", "$error"))
            return
        title.update(SafeText(self.view.title, "bold"))
        self._show(self.view)

    def _show(self, view: View) -> None:
        rows, self._acts = rows_of(view, self._cannot)
        self.query_one(Rows).show(rows)

    def on_rows_chosen(self, chosen: Rows.Chosen) -> None:
        if (act := self._acts.get(chosen.key)) is None:
            return
        if (why := self._cannot(act.op)) is not None:
            note(self, f"{act.label}: {why}", severity="warning")
        else:
            self._act(act)

    def action_leave(self) -> None:
        self.dismiss(None)
