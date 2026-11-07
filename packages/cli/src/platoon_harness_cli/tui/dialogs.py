"""What asks a person something: one confirmation, a form, and the help, which is the keymap table."""

import textwrap
from collections.abc import Sequence

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.content import Content
from textual.screen import ModalScreen
from textual.widgets import Input, Static

from .keymap import WHERE, bindings, keys
from .rows import Row, Rows

_SAID = 42
"""How wide what a key does is wrapped in the help, so it fits beside the key and its typed command in a dialog on 80
columns."""


class Confirm(ModalScreen[bool]):
    """One confirmation of an act that cannot be taken back, that can spend money, or that writes a file. Only `y` says
    yes, so a key pressed for something else never does."""

    BINDINGS = bindings("question")

    def __init__(self, question: Content) -> None:
        super().__init__()
        self._question = question

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog"):
            yield Static(self._question)
            yield Static(Content.styled("y: yes    n or Esc: no", "dim"))

    def action_yes(self) -> None:
        self.dismiss(True)

    def action_no(self) -> None:
        self.dismiss(False)


class Form(ModalScreen[dict[str, str] | None]):
    """A few fields, each a line of text. Enter goes to the next field, and from the last sends them, and Esc leaves. A
    field left empty is left out."""

    BINDINGS = bindings("dialog")

    def __init__(self, title: Content, fields: Sequence[tuple[str, Content, str]]) -> None:
        """`fields` are each a name, what it is, and what it holds at first."""
        super().__init__()
        self._title = title
        self._fields = fields

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog"):
            yield Static(self._title)
            for name, about, value in self._fields:
                yield Static(about, classes="about")
                yield Input(value=value, id=f"field-{name}", compact=True)
            yield Static(Content.styled("Enter: next, and from the last, go    Esc: leave", "dim"))

    def on_input_submitted(self, submitted: Input.Submitted) -> None:
        inputs = list(self.query(Input))
        if submitted.input is not inputs[-1]:
            inputs[inputs.index(submitted.input) + 1].focus()
            return
        values = {name: self.query_one(f"#field-{name}", Input).value.strip() for name, _, _ in self._fields}
        self.dismiss({name: value for name, value in values.items() if value})

    def action_leave(self) -> None:
        self.dismiss(None)


class Help(ModalScreen[None]):
    """Every key, from the keymap table, with an act's typed command beside it, and why one is not built yet on lines
    of its own."""

    BINDINGS = bindings("dialog")

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog wide"):
            yield Rows(id="help")
            yield Static(Content.styled("Esc or F1: leave", "dim"))

    def on_mount(self) -> None:
        rows: list[Row] = []
        for where, title in WHERE.items():
            rows.append(Row(Content.styled(title, "bold")))
            for key in keys(where):
                said = [Content(line) for line in textwrap.wrap(key.does, _SAID)]
                if key.planned:
                    said += [
                        Content.styled(line, "dim") for line in textwrap.wrap(f"Not built yet: {key.planned}", _SAID)
                    ]
                for index, line in enumerate(said):
                    shown, typed = (key.shown, key.typed) if index == 0 else ("", "")
                    rows.append(Row(Content.assemble((f"  {shown:<12} {typed:<12} ", "bold"), line)))
        self.query_one(Rows).show(rows)

    def action_leave(self) -> None:
        self.dismiss(None)
