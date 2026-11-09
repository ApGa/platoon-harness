"""The team editor on a terminal: the project's team as the fields `team_editor` makes from the team's schema, by
section, a row each, every problem under its field, beside `team show`'s sentences and the diff a save makes, in the
words the browser's editor says. Each change is checked as it is made, Save asks first what a save asks, and Start
saves first."""

import asyncio
from collections.abc import Mapping, Sequence
from dataclasses import replace
from functools import partial
from pathlib import Path
from typing import Any

from textual import events, work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.content import Content
from textual.geometry import Region
from textual.message import Message
from textual.screen import ModalScreen, Screen
from textual.widget import Widget
from textual.widgets import Input, Static

from platoon_harness import ConfigError
from platoon_harness.config import PROJECT_FILE
from platoon_harness.schema import Problem

from .. import team_editor
from ..output import safe
from ..team_editor import Adding, Asked, Choice, Draft, Edit, Field, Group, Harness
from .composer import Composer
from .dialogs import Confirm, Keys, hint
from .keymap import bindings, footer, keys
from .rows import Row, Rows
from .safe import SafeText, note

READING = f"Reading {PROJECT_FILE} and what `doctor` finds of this machine's harnesses."
SAVING = f"Saving {PROJECT_FILE}."
LEAVE = "Go back to the sessions screen, dropping your changes?"
LEVELS = {"error": "$error", "warning": "$warning"}
"""How a problem is drawn at its level."""
LABEL = 16
"""How wide a field's key may make the column before the values of its table."""
ABOUT = 3
"""How many lines the words of the chosen row take below the fields, one fewer with the preview below them: a field's
whole words are in its form."""
STACKED = 100
"""Under how many columns the preview stands below the fields rather than beside them."""
ESCAPED = (
    "It holds a character this terminal would act on, which it shows as its escape, and a field here would not keep "
    "it: edit it in the file."
)
"""Why a field that is typed in cannot be changed here where its text holds such a character."""

type Act = Field | Adding | Group
"""What a row acts on: a field it changes, an entry it adds, or a table it removes."""


def prose(text: str, style: str = "") -> Content:
    """Words that name keys and values between backticks, as the reference writes them, each name in the accent with
    its backticks gone, as the browser draws one as code, every part made safe."""
    parts = text.split("`")
    return Content.assemble(*(SafeText(part, f"{style} $accent" if at % 2 else style) for at, part in enumerate(parts)))


def _wrapped(line: Content, width: int, indent: int, key: str | None = None) -> list[Row]:
    lines = line.wrap(max(width - indent, 20)) or [Content("")]
    return [Row(Content.assemble(" " * indent, part), key, lead=indent) for part in lines]


def _problems(problems: Sequence[Problem], width: int, indent: int, key: str | None) -> list[Row]:
    return [
        row
        for problem in problems
        for row in _wrapped(prose(team_editor.said(problem), LEVELS.get(problem.level, "")), width, indent, key)
    ]


def _shown(field: Field, text: str) -> Content:
    """A field's value on its row: the choice it is, as its choice says it, the first of several lines, or what stands
    left empty."""
    if not text:
        return Content.styled(field.empty, "dim")
    choice = next((choice for choice in field.choices if choice.value == text), None)
    if choice is not None:
        return SafeText(choice.said)
    first, _, more = text.partition("\n")
    return Content.assemble(SafeText(first), (" …" if more.strip() else "", "dim"))


def _typable(field: Field, text: str) -> Field:
    """A field as the terminal takes it: one typed in, whose text holds a character `SafeText` shows as its escape, is
    one that cannot be changed here, as a form would draw that character to the terminal itself."""
    if field.kind in ("choice", "yes-no") or field.fixed is not None or safe(text) == text:
        return field
    return replace(field, fixed=ESCAPED)


def _field_rows(field: Field, label: str, column: int, text: str, width: int) -> list[Row]:
    key = f"field:{field.where}"
    named = SafeText(f"{label:<{column}}", "dim" if field.fixed else "")
    value = _shown(field, text)
    rows = [Row(Content.assemble("   ", named, value.stylize("dim") if field.fixed else value), key, lead=3)]
    return rows + _problems(field.problems, width, 5, key)


def rows_of(found: Draft, typed: Mapping[team_editor.Keys, str], width: int) -> tuple[list[Row], dict[str, Act]]:
    """A draft's rows at `width`: at the top what the file alone sets and each problem no table takes, then each
    section, its tables and each table's fields, a row each, showing the text typed in it last where `typed` holds
    some, each problem at it under it, what of the table is the file's alone, and the act that removes it; then the
    entries the section adds. Every part is made safe, and each row a person acts on is keyed, with what it acts on."""
    rows: list[Row] = []
    acts: dict[str, Act] = {}
    if (kept := team_editor.keeping(found.kept)) is not None:
        rows += _wrapped(prose(kept, "dim"), width, 0)
    rows += _problems(found.problems, width, 0, None)
    for section in found.sections:
        rows += [Row(Content(""))] if rows else []
        heading = len(rows)
        rows.append(Row(Content.styled(section.title, "bold $accent")))
        for group in section.groups:
            about = Content.assemble(" · ", prose(group.about)).stylize("dim") if group.about else Content("")
            if group.title == section.title:  # A table that is its section, as the budget is, is headed by it.
                rows[heading] = Row(Content.assemble(rows[heading].line, about))
            else:
                rows.append(Row(Content.assemble(" ", SafeText(group.title, "bold"), about), lead=1))
            rows += _problems(group.problems, width, 3, None)
            labels = [".".join(field.path[len(group.path) :]) for field in group.fields]
            column = min(max((len(label) for label in labels), default=0), LABEL) + 2
            for field, label in zip(group.fields, labels, strict=True):
                text = typed.get(field.path, field.text)
                acts[f"field:{field.where}"] = field = _typable(field, text)
                rows += _field_rows(field, label, column, text, width)
            if (kept := team_editor.keeping(group.kept)) is not None:
                rows += _wrapped(prose(kept, "dim"), width, 3)
            if group.removable:
                key = f"remove:{group.where}"
                acts[key] = group
                removing = Content.assemble("   ", ("- ", "$error"), SafeText(f"Remove {group.title}"))
                rows.append(Row(removing, key, lead=5))
        for adding in section.adding:
            key = f"add:{'.'.join(adding.under)}"
            acts[key] = adding
            rows.append(Row(Content.assemble(" ", ("+ ", "$accent"), adding.title), key, lead=3))
    return rows, acts


def preview_rows(found: Draft, width: int) -> tuple[list[Row], int | None]:
    """What a draft allows, in `team show`'s sentences, and the diff a save makes, its lines added and removed told
    apart, every part made safe and wrapped at `width`; and the row of the first line it adds or removes, if any."""
    rows = [Row(Content.styled(team_editor.ALLOWS, "bold $accent"))]
    if found.shown is None:
        rows += _wrapped(Content.styled(team_editor.UNSHOWN, "dim"), width, 0)
    for line in (found.shown or "").splitlines():
        rows += _wrapped(SafeText(line), width, 0)
    rows += [Row(Content("")), Row(Content.styled(team_editor.CHANGES, "bold $accent"))]
    if not found.diff:
        rows += _wrapped(Content.styled(team_editor.UNCHANGED, "dim"), width, 0)
    changed = None
    for line in found.diff.splitlines():
        added = line.startswith("+") and not line.startswith("+++ ")
        removed = line.startswith("-") and not line.startswith("--- ")
        if (added or removed) and changed is None:
            changed = len(rows)
        style = "$success" if added else "$error" if removed else "dim" if line.startswith("@@") else ""
        rows += _wrapped(SafeText(line, style), width, 0)
    return rows, changed


def about(act: Act | None) -> Content:
    """The words of what a row acts on: a field's, why it cannot be changed here first; an entry's to add, those of the
    field it needs, if it needs one; and a table's."""
    match act:
        case Field():
            return prose(f"{act.fixed} {act.help}" if act.fixed else act.help, "dim")
        case Adding(first=Field() as first):
            return prose(first.help, "dim")
        case Group():
            return prose(act.about, "dim")
    return Content("")


def clamped(said: Content, width: int, lines: int) -> Content:
    """Words wrapped at `width`, in `lines` at most, the last ending `…` where more are left out."""
    wrapped = said.wrap(max(width, 20))
    if len(wrapped) > lines:
        wrapped = [*wrapped[: lines - 1], Content.assemble(wrapped[lines - 1].truncate(max(width, 20) - 2), " …")]
    return Content("\n").join(wrapped)


def shortened(folder: Path) -> str:
    """A folder as a person reads it, under `~` where it is in their home."""
    home = Path.home()
    if folder == home:
        return "~"
    return f"~/{folder.relative_to(home)}" if folder.is_relative_to(home) else str(folder)


class Fields(Rows):
    """The team editor's rows, which say when the cursor moves, so the words of the chosen row follow it, and keep the
    chosen row in view as they are drawn again or made shorter."""

    class Moved(Message):
        """The cursor moved."""

    def move_to(self, key: str) -> None:
        super().move_to(key)
        self.post_message(self.Moved())

    def show(self, rows: list[Row]) -> None:
        super().show(rows)
        self.call_after_refresh(self.keep)

    def on_resize(self) -> None:
        self.call_after_refresh(self.keep)

    def keep(self) -> None:
        """Scroll as little as brings the chosen rows into view, a field's problems under it among them."""
        chosen = [index for index, row in enumerate(self.rows) if row.key is not None and row.key == self.cursor]
        if chosen:
            self.scroll_to_region(Region(0, chosen[0], 1, len(chosen)), animate=False, immediate=True)


class TeamEditor(Screen[bool]):
    """The project's team where the terminal runs, as `team_editor` drafts it, read as it opens with what `doctor` finds
    of this machine's harnesses, which each check after keeps. A person's edits are kept here and drafted whole at each
    change, and only the newest check is drawn. It answers whether to start a session from the team it saved."""

    BINDINGS = bindings("team")

    def __init__(self) -> None:
        super().__init__()
        self.edits: list[Edit] = []
        self.found: Draft | None = None
        self.refused: str | None = None
        self.harnesses: tuple[Harness, ...] = ()
        self.acts: dict[str, Act] = {}
        self._asked = self._drawn = 0
        self._saving = False

    def compose(self) -> ComposeResult:
        yield Static(id="header")
        with Horizontal(id="editing"):
            yield Fields(id="fields")
            yield Rows(id="preview")
        yield Static(id="about")
        yield Static(Content(team_editor.UNSAVED), id="unsaved")
        yield Keys(id="footer")

    def on_mount(self) -> None:
        self.query_one(Fields).border_title = Content(PROJECT_FILE)
        self.query_one("#preview", Rows).border_title = Content("preview")
        self.query_one(Fields).focus()
        self._lay_out(self.size.width)
        self._read()

    def on_resize(self, event: events.Resize) -> None:
        self._lay_out(event.size.width)
        self.call_after_refresh(self._draw)

    def _lay_out(self, width: int) -> None:
        """The preview beside the fields, or below them where the screen is too narrow, with a line less of words."""
        self.set_class(width < STACKED, "stacked")
        self.query_one("#about").styles.height = ABOUT - (width < STACKED)

    # What the person did, and what is drawn of it.

    def _read(self) -> None:
        """Read the file and this machine's harnesses again, drawing nothing of the draft until both are read."""
        self.found = None
        self._asked += 1
        self._draw()
        self._reading(self._asked)

    @work(exclusive=True, group="check")
    async def _reading(self, asked: int) -> None:
        self.harnesses = await asyncio.to_thread(team_editor.harnesses)
        await self._drafted(asked, ())

    def _check(self) -> None:
        """Check the draft the edits make, as a change asks: only the newest check is drawn."""
        self._asked += 1
        self._draw_state()
        self._checking(self._asked, tuple(self.edits))

    @work(exclusive=True, group="check")
    async def _checking(self, asked: int, sent: tuple[Edit, ...]) -> None:
        await self._drafted(asked, sent)

    async def _drafted(self, asked: int, sent: tuple[Edit, ...]) -> None:
        """Draw the draft of `sent`, unless a newer check was asked for. An add or a removal that could not be made is
        said there once, at its place, and dropped; a field keeps what was typed in it until it is changed again."""
        try:
            found = await asyncio.to_thread(team_editor.draft, Path.cwd(), sent, self.harnesses)
        except ConfigError as error:
            if asked == self._asked:
                self._drawn = asked
                self.refused = str(error)
                note(self, self.refused, severity="error")
                self._draw()
            return
        if asked != self._asked:
            return
        self._drawn = asked
        unmade = [sent[index] for index in found.unmade if sent[index].verb != "set"]
        self.edits = [edit for edit in self.edits if not any(edit is gone for gone in unmade)]
        self.found, self.refused = found, None
        self._draw()

    def _change(self, edit: Edit) -> None:
        if edit.verb == "set":
            self.edits = [old for old in self.edits if not (old.verb == "set" and old.path == edit.path)]
        self.edits.append(edit)
        self._check()

    def _typed(self) -> dict[team_editor.Keys, str]:
        """The text typed last in each field, which it shows until a save or a read takes it."""
        return {edit.path: edit.text for edit in self.edits if edit.verb == "set"}

    def _changes(self) -> bool:
        return bool(self.edits and self.found is not None and self.found.diff)

    def _draw(self) -> None:
        fields, preview = self.query_one(Fields), self.query_one("#preview", Rows)
        if self.found is None:
            width = fields.scrollable_content_region.width or 60
            said = prose(self.refused, "$error") if self.refused else prose(READING, "dim")
            fields.show(_wrapped(said, width, 0))
            preview.show([])
            self.acts = {}
        else:
            rows, self.acts = rows_of(self.found, self._typed(), fields.scrollable_content_region.width or 60)
            fields.show(rows)
            shown, changed = preview_rows(self.found, preview.scrollable_content_region.width or 60)
            preview.show(shown)
            if changed is not None and not preview.has_focus:  # So a preview too short for the diff shows its change.
                region = Region(0, changed, 1, 1)
                self.call_after_refresh(preview.scroll_to_region, region, animate=False, immediate=True)
        self._draw_state()

    def _draw_state(self) -> None:
        """Draw what changes with no new draft: the words of the chosen row, what was said, whether a check is waited
        for, and which acts can be taken now."""
        if not self.is_mounted:
            return
        here = shortened(Path.cwd())
        header = Content.assemble(("The project's team", "bold"), SafeText(f" · {PROJECT_FILE}, in {here}", "dim"))
        self.query_one("#header", Static).update(header.truncate(max(self.size.width - 2, 1), ellipsis=True))
        fields, said = self.query_one(Fields), self.query_one("#about", Static)
        waiting = "saving…" if self._saving else "checking your last change…" if self._asked != self._drawn else ""
        fields.border_subtitle = Content(waiting)
        lines = ABOUT - self.has_class("stacked")
        said.update(clamped(about(self.acts.get(fields.cursor or "")), said.size.width or self.size.width - 4, lines))
        self.query_one("#unsaved").set_class(self._changes(), "-shown")
        disabled = {key.action for key in keys("team") if self._cannot(key.action) is not None}
        self.query_one("#footer", Static).update(footer("team", disabled))

    def _cannot(self, action: str) -> str | None:
        """Why the act `action` cannot be taken now, or None where it can."""
        if action == "save":
            if self._saving:
                return SAVING
            if self.found is None:
                return self.refused or READING
            return team_editor.CHECKING if self._asked != self._drawn else self.found.blocked
        if action == "start":
            if self._saving:
                return SAVING
            if self.found is None:
                return None if self.refused else READING
            if self.edits and self._asked != self._drawn:
                return team_editor.CHECKING
            return self.found.blocked if self._changes() else None
        if action == "edit" and self.found is None:
            return self.refused or READING
        return None

    def on_fields_moved(self) -> None:
        self._draw_state()

    # Acts.

    def on_rows_chosen(self, chosen: Rows.Chosen) -> None:
        if isinstance(chosen.rows, Fields):
            self._draw_state()
            self._act(chosen.key)

    def action_edit(self) -> None:
        if (key := self.query_one(Fields).cursor) is not None:
            self._act(key)

    @work(group="act")
    async def _act(self, key: str) -> None:
        """Take what the row `key` acts on: change a field in its form, add an entry from its form, or remove one."""
        act = self.acts.get(key)
        if act is None:
            note(self, self._cannot("edit") or "Choose a field, or an entry to add or remove.", severity="warning")
            return
        if isinstance(act, Group):
            self._change(Edit("remove", act.path))
            return
        if isinstance(act, Field):
            if act.fixed is not None:
                note(self, act.fixed, severity="warning")
                return
            text = self._typed().get(act.path, act.text)
            given = await self.app.push_screen_wait(FieldForm(SafeText(act.where, "bold"), [("", act, text)]))
            if given is not None and given[0] != text:
                self._change(Edit("set", act.path, given[0]))
            return
        asked = [("preset" if act.names else "name", _naming(act), "")]
        if act.first is not None:
            asked.append((".".join(act.first.path) or "values", act.first, ""))
        given = await self.app.push_screen_wait(FieldForm(Content.styled(act.title, "bold"), asked))
        if given is not None:
            self._change(Edit("add", (*act.under, given[0]), given[1] if act.first is not None else ""))

    @work(group="act")
    async def action_save(self) -> None:
        if (why := self._cannot("save")) is not None:
            note(self, why, severity="warning")
            return
        await self._save()

    async def _save(self) -> bool:
        """Save the draft of the edits as they stand, over the file as it was last read, asking first what the save
        asks; and say whether it was saved. A file found changed since is refused, and the check after shows the edits
        on what it holds now."""
        assert self.found is not None
        base, sent, trust = self.found.base, tuple(self.edits), None
        while True:
            self._saving = True
            self._draw_state()
            try:
                saved = await asyncio.to_thread(team_editor.save, Path.cwd(), base, sent, self.harnesses, trust)
            except ConfigError as error:
                note(self, str(error), severity="error")
                self._check()
                return False
            finally:
                self._saving = False
                self._draw_state()
            if not isinstance(saved, Asked):
                break
            if not await self.app.push_screen_wait(Confirm(SafeText(saved.question), saved.yes)):
                note(self, team_editor.NOT_SAVED, severity="warning")
                return False
            trust = saved.trust
        self.edits = [edit for edit in self.edits if not any(edit is gone for gone in sent)]
        note(self, team_editor.saved(Path.cwd()))
        self._check()
        return True

    @work(group="act")
    async def action_start(self) -> None:
        """Answer that a session is to start from the project's team, saving the editor's changes first."""
        if (why := self._cannot("start")) is not None:
            note(self, why, severity="warning")
            return
        if self._changes() and not await self._save():
            return
        self.dismiss(True)

    @work(group="act")
    async def action_read(self) -> None:
        if self.edits and not await self.app.push_screen_wait(Confirm(SafeText(team_editor.again(PROJECT_FILE)))):
            return
        self.edits = []
        self._read()

    @work(group="act")
    async def action_leave(self) -> None:
        if self.edits and not await self.app.push_screen_wait(Confirm(SafeText(LEAVE))):
            return
        self.dismiss(False)

    def commands(self) -> list[tuple[str, str, Any]]:
        return [(key.name.capitalize(), key.does, partial(self.run_action, key.runs)) for key in keys("team")]


def _naming(adding: Adding) -> Field:
    """The field that names an entry to add: one of `names`, or typed."""
    if adding.names:
        return Field((), "choice", "", "", "choose one", tuple(Choice(name, name) for name in adding.names))
    return Field((), "text", "", "", "a name")


class Choices(Rows):
    """A field's choices, a row each, wrapped at the form's width: first what stands left empty, then each choice as it
    says itself, the one the field holds marked, which the cursor starts on."""

    def __init__(self, field: Field, text: str, *, id: str | None = None) -> None:
        super().__init__(id=id)
        self.field = field
        self.held = self.cursor = text

    def on_resize(self) -> None:
        width = self.scrollable_content_region.width or 60
        rows = []
        for choice in (Choice("", self.field.empty), *self.field.choices):
            held = choice.value == self.held
            said = SafeText(choice.said, "" if choice.value else "dim")
            for at, line in enumerate(said.wrap(max(width - 2, 20)) or [Content("")]):
                mark = "● " if held and not at else "  "
                rows.append(Row(Content.assemble((mark, "$accent"), line), choice.value, lead=2))
        tall = len(rows) != len(self.rows)
        self.show(rows)
        if self.cursor is not None:
            self.move_to(self.cursor)
        if tall:
            self.refresh(layout=True)

    @property
    def value(self) -> str:
        return self.cursor or ""


class FieldForm(ModalScreen[tuple[str, ...] | None]):
    """A form of the team editor's fields, each labelled, with its words and each problem at it, and taken as its kind
    takes it: one of its choices, several lines, where Enter sends as the composer's does, or a line of text. Enter goes
    to the next field, and from the last sends them, and Esc leaves, changing nothing."""

    BINDINGS = bindings("dialog")

    def __init__(self, title: Content, fields: Sequence[tuple[str, Field, str]]) -> None:
        """`fields` are each a label, the field, and the text it holds at first."""
        super().__init__()
        self._title = title
        self._fields = fields

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog"):
            yield Static(self._title)
            for at, (label, field, text) in enumerate(self._fields):
                if label:
                    yield Static(SafeText(label, "bold"), classes="about")
                if field.help:
                    yield Static(prose(field.help, "dim"), classes="about")
                for problem in field.problems:
                    yield Static(prose(team_editor.said(problem), LEVELS.get(problem.level, "")))
                if field.kind in ("choice", "yes-no"):
                    yield Choices(field, text, id=f"value-{at}")
                elif field.kind == "lines":
                    yield Composer(id=f"value-{at}")
                else:
                    yield Input(value=text, placeholder=field.empty, id=f"value-{at}", compact=True)
            sends = "Enter: next, and from the last, go" if len(self._fields) > 1 else "Enter: set it"
            said = [(sends, "send"), ("Esc: leave", "leave")]
            if any(field.kind == "lines" for _, field, _ in self._fields):
                newline = next(key for key in keys("composer") if key.action == "newline")
                said.insert(1, (f"{newline.shown}: a new line", "newline"))
            yield Keys(hint(*said), classes="keys")

    def on_mount(self) -> None:
        for at, (_, field, text) in enumerate(self._fields):
            if field.kind == "lines":
                composer = self.query_one(f"#value-{at}", Composer)
                composer.load_text(text)
                composer.move_cursor(composer.document.end)
        self.query_one("#value-0").focus()

    def _value(self, at: int) -> str:
        control = self.query_one(f"#value-{at}")
        if isinstance(control, Choices):
            return control.value
        if isinstance(control, Composer):
            return control.text
        assert isinstance(control, Input)
        return control.value.strip()

    def _next(self, control: Widget | None) -> None:
        """Go from a field to the next, and from the last, send them."""
        controls = [self.query_one(f"#value-{at}") for at in range(len(self._fields))]
        at = controls.index(control) if control in controls else len(controls) - 1
        if at + 1 < len(controls):
            controls[at + 1].focus()
        else:
            self.action_send()

    def on_input_submitted(self, submitted: Input.Submitted) -> None:
        submitted.stop()
        self._next(submitted.input)

    def on_composer_send(self, sent: Composer.Send) -> None:
        sent.stop()
        self._next(self.focused)

    def on_rows_chosen(self, chosen: Rows.Chosen) -> None:
        chosen.stop()
        self._next(chosen.rows)

    def action_send(self) -> None:
        self.dismiss(tuple(self._value(at) for at in range(len(self._fields))))

    def action_newline(self) -> None:
        """Start a new line in the field of several lines that has focus, as its key does."""
        if isinstance(self.focused, Composer):
            self.focused.insert("\n")

    def action_leave(self) -> None:
        self.dismiss(None)
