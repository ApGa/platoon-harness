"""Provenance, as a panel a person reads: one event at a time, what it rests on, what came of it and whose work it
reaches, in the words both clients say, with each link labelled by how it is known."""

from textual import events, work
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.content import Content
from textual.screen import ModalScreen
from textual.widgets import Static

from platoon_harness import Refused, Session

from ..provenance import Line, no_provenance, read
from .keymap import bindings
from .rows import Row, Rows
from .safe import SafeText

KIND = 11
"""How wide the column is that names how a link is known, `declared` or `ancestry`."""
FOLLOW = "Enter: follow the chosen link    Esc: back one hop, and from the first, leave"


def rows_of(lines: list[Line], width: int, keyed: str) -> tuple[list[Row], dict[str, str]]:
    """The lines as rows at `width`, each wrapped under its kind, and the ref each link opens, by its key, which begins
    `keyed`. A line that follows nowhere is no choice, and its words say why."""
    rows: list[Row] = []
    refs: dict[str, str] = {}
    for index, line in enumerate(lines):
        if line.kind == "heading":
            rows.append(Row(SafeText(line.text, "bold")))
            continue
        key = None
        if line.ref is not None:
            key = f"{keyed}{index}"
            refs[key] = line.ref
        text = SafeText(line.text, "yellow" if line.warn else "").wrap(max(width - KIND, 20))
        for at, part in enumerate(text):
            label = (f"{line.kind if at == 0 else '':<{KIND}}", "dim")
            rows.append(Row(Content.assemble(label, part), key))
    return rows, refs


class Provenance(ModalScreen[None]):
    """The provenance of the event `ref`, opened `from_text` where a text named it, then of each event a link of it is
    followed into: Enter on a link follows it, and Esc goes back one hop, and from the first leaves. Each hop is read
    again when it is shown, at the head then, and `lines` is what it says."""

    BINDINGS = bindings("provenance")

    def __init__(self, session: Session, ref: str, *, from_text: bool = False) -> None:
        super().__init__()
        self._session = session
        self._from_text = from_text
        self._trail: list[tuple[str, str | None]] = [(ref, None)]
        self.lines: list[Line] = []
        self._refs: dict[str, str] = {}
        self._reads = 0

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog wide"):
            yield Static(id="asked")
            yield Rows(id="provenance")
            yield Static(Content.styled(FOLLOW, "dim"))

    def on_mount(self) -> None:
        self._read()

    @work(exclusive=True, group="provenance")
    async def _read(self) -> None:
        ref = self._trail[-1][0]
        hops = len(self._trail) - 1
        back = f", {hops} hop{'' if hops == 1 else 's'} from where you began" if hops else ""
        self.query_one("#asked", Static).update(SafeText(f"Provenance of {ref}{back}", "bold"))
        from_text = self._from_text and not hops
        try:
            self.lines = (await read(self._session, ref, from_text=from_text)).lines
        except Refused as refused:
            self.lines = [Line("", no_provenance(ref, refused, from_text=from_text), warn=True)]
        self._reads += 1
        self._draw()
        listing = self.query_one(Rows)
        chosen = self._trail[-1][1]
        if chosen is not None and chosen in self._refs.values():
            listing.move_to(next(key for key, found in self._refs.items() if found == chosen))

    def _draw(self) -> None:
        listing = self.query_one(Rows)
        rows, self._refs = rows_of(self.lines, listing.scrollable_content_region.width or 80, f"{self._reads}:")
        listing.show(rows)

    def on_resize(self, event: events.Resize) -> None:
        self.call_after_refresh(self._draw)

    def on_rows_chosen(self, chosen: Rows.Chosen) -> None:
        """Follow a link: its event is the next hop, and coming back chooses the link again."""
        ref = self._refs[chosen.key]
        self._trail[-1] = (self._trail[-1][0], ref)
        self._trail.append((ref, None))
        self._read()

    def action_back(self) -> None:
        self._trail.pop()
        if self._trail:
            self._read()
        else:
            self.dismiss(None)
