"""What asks a person something: one confirmation, a form, and the help, which is the keymap table."""

from collections.abc import Sequence

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.content import Content
from textual.screen import ModalScreen
from textual.widgets import Input, Static

from .keymap import WHERE, keys
from .rows import Row, Rows


class Confirm(ModalScreen[bool]):
    """One confirmation of an act that cannot be taken back, or that can spend money. Only `y` says yes, so a key
    pressed for something else never does."""

    BINDINGS = [
        Binding("y", "answer(True)", "Yes", show=False),
        Binding("n,escape", "answer(False)", "No", show=False),
    ]

    def __init__(self, question: Content) -> None:
        super().__init__()
        self._question = question

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog"):
            yield Static(self._question)
            yield Static(Content.styled("y: yes    n or Esc: no", "dim"))

    def action_answer(self, yes: bool) -> None:
        self.dismiss(yes)


class Form(ModalScreen[dict[str, str] | None]):
    """A few fields, each a line of text, sent with Enter and left with Esc. A field left empty is left out."""

    BINDINGS = [Binding("escape", "leave", "Leave", show=False)]

    def __init__(self, title: Content, fields: Sequence[tuple[str, Content, str]], said: Content | None = None) -> None:
        """`fields` are each a name, what it is, and what it holds at first."""
        super().__init__()
        self._title = title
        self._fields = fields
        self._said = said

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog"):
            yield Static(self._title)
            for name, about, value in self._fields:
                yield Static(about, classes="about")
                yield Input(value=value, id=f"field-{name}", compact=True)
            yield Static(self._said or Content(""), id="said")
            yield Static(Content.styled("Enter: go    Esc: leave", "dim"))

    def say(self, said: Content) -> None:
        self.query_one("#said", Static).update(said)

    def on_input_submitted(self) -> None:
        values = {name: self.query_one(f"#field-{name}", Input).value.strip() for name, _, _ in self._fields}
        self.dismiss({name: value for name, value in values.items() if value})

    def action_leave(self) -> None:
        self.dismiss(None)


class Help(ModalScreen[None]):
    """Every key, from the keymap table."""

    BINDINGS = [Binding("escape,f1,q", "leave", "Leave", show=False)]

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog wide"):
            yield Rows(id="help")
            yield Static(Content.styled("Esc: leave", "dim"))

    def on_mount(self) -> None:
        rows: list[Row] = []
        for where, title in WHERE.items():
            rows.append(Row(Content.styled(title, "bold")))
            rows += [
                Row(
                    Content.assemble(
                        (f"  {key.shown:<12} ", "bold"), key.does, (f"  not built yet: {key.planned}", "dim")
                    )
                )
                if key.planned
                else Row(Content.assemble((f"  {key.shown:<12} ", "bold"), key.does))
                for key in keys(where)
            ]
        self.query_one(Rows).show(rows)

    def action_leave(self) -> None:
        self.dismiss(None)
