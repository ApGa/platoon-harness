"""The team editor, which the browser's sessions page shows and the terminal's is to show: the keys of the project's
team file a person may set from a client, as fields made from the team's schema; a draft, the file as it is with a
person's edits, written as the file's own text, keeping its comments, order and layout; the draft checked by the loader
and by `team check`, each problem at its field, with `team show`'s sentences of it and the diff saving it makes; and the
save, over nothing changed since the file was read and never through a link (RFC 0079)."""

import difflib
import hashlib
import inspect
import json
import math
import os
import re
import secrets
import shlex
import stat
import tempfile
import tomllib
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from types import NoneType, UnionType
from typing import Annotated, Any, Literal, TypeAliasType, Union, cast, get_args, get_origin, get_type_hints

import tomlkit
from pydantic import BaseModel
from tomlkit.container import Container
from tomlkit.exceptions import TOMLKitError
from tomlkit.items import AoT, Comment, InlineTable, Item, Table, Whitespace
from tomlkit.toml_document import TOMLDocument

from platoon_harness import ConfigError, Team
from platoon_harness.config import PROJECT_FILE, load_trusted
from platoon_harness.drivers import Driver, DriverError
from platoon_harness.extensions import Installed
from platoon_harness.kernel import NAME
from platoon_harness.runtime.opening import check
from platoon_harness.runtime.paths import find_root
from platoon_harness.schema import Problem, either
from platoon_harness.team import AuthProfile, Budget, Role, Test
from platoon_harness.topology import PRESETS, Board, Limits, Queue, Topic, Topology
from platoon_harness.topology.spec import SELECTORS

from . import machine
from .ops import SEVERAL
from .team_file import default_said, type_said

ROLE = (
    "harness",
    "model",
    "effort",
    "approvals",
    "workspace",
    "sandbox",
    "instructions",
    "auth",
    "count",
    "stays",
    "may_spawn",
)
"""A role's keys a person sets from a client, in the order its form shows them. The rest of a role's keys are the file's
alone."""
CHANNELS: dict[str, type[Topic | Queue | Board]] = {"topic": Topic, "queue": Queue, "board": Board}
LINES = {(Role, "instructions")}
"""Text a person writes over several lines."""
COMMAND = {(Test, "command")}
"""A command line, which a person types as at a shell."""
WORDS = "Words as a shell splits them."
TRUSTED = "Saving a change to it asks you first: it is what would run as you, or a credential to pass on."
SAVING = (
    "Saving writes into the project's team what would run as you, or a credential to pass on, which a start then asks "
    "you to trust:"
)
"""What a save asks first of a draft that writes a value only trust may take, above each such value."""
KIND_FIXED = "A channel's kind is chosen as it is added: remove it and add it again as another."
KIND = Literal["topic", "queue", "board"]
"""A channel's kind, as its table names it."""
CHANGED = "read it again, and your changes are made on what it holds now, in a diff you see before you save"

type Keys = tuple[str, ...]
"""A place in the file, as the keys that lead to it."""


@dataclass(frozen=True)
class Harness:
    """A harness this machine has a driver for, `said` what `doctor` finds of it after its name, and `sandboxes` the
    sandboxes its driver declares, None where it could not say."""

    name: str
    said: str
    sandboxes: tuple[str, ...] | None


@dataclass(frozen=True)
class Choice:
    """A value a choice takes, and how a person reads it."""

    value: str
    said: str


@dataclass(frozen=True)
class Field:
    """A key of the team file a person may set from a client: its place, what it takes and what stands left out, in the
    reference's words, the text its value shows as in the draft, the choices it takes, whether a value of it from a
    project file needs trust, why it cannot be changed here, if it cannot, and every problem at it.

    `kind` is what it takes: `text`, `lines`, `command`, `list`, `integer`, `number`, `yes-no` or `choice`, and `empty`
    what stands when it is left empty."""

    path: Keys
    kind: str
    help: str
    text: str
    empty: str
    choices: tuple[Choice, ...] = ()
    trust: bool = False
    fixed: str | None = None
    problems: tuple[Problem, ...] = ()

    @property
    def where(self) -> str:
        """Its place, as a problem names it."""
        return ".".join(self.path)


@dataclass(frozen=True)
class Group:
    """The fields of one table, such as a role or the budget, with what the file holds there that is the file's alone,
    `kept`, whether a person may remove it, and each problem at it that no field of it takes."""

    title: str
    path: Keys
    about: str
    fields: tuple[Field, ...]
    kept: tuple[str, ...] = ()
    removable: bool = False
    problems: tuple[Problem, ...] = ()

    @property
    def where(self) -> str:
        return ".".join(self.path)


@dataclass(frozen=True)
class Adding:
    """An entry a person may add under `under`: named as they type it, or as one of `names`, and given `first`, its
    field the entry needs, as it is added. A `first` of no path is the entry itself."""

    title: str
    under: Keys
    names: tuple[str, ...] = ()
    first: Field | None = None


@dataclass(frozen=True)
class Section:
    title: str
    groups: tuple[Group, ...]
    adding: tuple[Adding, ...] = ()


@dataclass(frozen=True)
class Edit:
    """One change a person makes: `set` a field to `text`, where empty text leaves its key out, `add` an entry, its
    first field given `text`, or `remove` one."""

    verb: Literal["set", "add", "remove"]
    path: Keys
    text: str = ""


@dataclass(frozen=True)
class Draft:
    """The project's team file as read, `base` the digest of its bytes, None where there is none, with a person's edits:
    its text, its sections, the keys of the file's alone at its top, every problem the edits, the loader and `team
    check` find, each at its field or table or else in `problems`, `team show`'s sentences of it, None where it cannot
    be shown, the diff saving it makes, each value it writes that only trust may take, why it cannot be saved, None when
    it can, and `unmade`, the edits that could not be made, by their place among the edits, each named by a problem."""

    base: str | None
    text: str
    sections: tuple[Section, ...]
    kept: tuple[str, ...]
    problems: tuple[Problem, ...]
    shown: str | None
    diff: str
    trusting: tuple[str, ...]
    blocked: str | None
    unmade: tuple[int, ...]


@dataclass(frozen=True)
class Asked:
    """A question a save asks before it writes, and the answer that says yes to what it showed."""

    question: str
    yes: str
    trust: str


def harnesses() -> tuple[Harness, ...]:
    """Each harness this machine has a driver for, as `doctor` finds it. It blocks, as `doctor` runs each to ask."""
    root = find_root()
    return tuple(
        Harness(name, machine.found(name, driver, root), _sandboxes(driver)) for name, driver in machine.harnesses()
    )


def _sandboxes(driver: Driver) -> tuple[str, ...] | None:
    try:
        return tuple(sorted(driver.describe().capabilities.sandboxes))
    except DriverError:
        return None


def edits_of(given: Any) -> tuple[Edit, ...]:
    """Edits from JSON: a list of `{"set": path, "to": text}`, `{"add": path, "to": text}` and `{"remove": path}`, each
    path a list of keys. Anything else raises `ValueError`."""
    if not isinstance(given, list):
        raise ValueError("edits are a list")
    return tuple(map(_edit, given))


def _edit(given: Any) -> Edit:
    verbs = [verb for verb in ("set", "add", "remove") if isinstance(given, dict) and verb in given]
    if len(verbs) != 1 or set(given) - {*verbs, "to"} or (verbs == ["remove"] and "to" in given):
        raise ValueError("an edit is one of set, add or remove, with `to` beside a set or an add")
    path, text = given[verbs[0]], given.get("to", "")
    if not (isinstance(path, list) and path and all(isinstance(key, str) for key in path) and isinstance(text, str)):
        raise ValueError("an edit's path is a list of keys, and its `to` is text")
    return Edit(cast(Literal["set", "add", "remove"], verbs[0]), tuple(path), text)


def draft(folder: Path, edits: Sequence[Edit], harnesses: Sequence[Harness]) -> Draft:
    """The project's team file in `folder` with `edits`, checked as `run` would load it there and as `team check` checks
    it, with `harnesses` this machine's. It blocks, as `team check` asks each role's driver what it is, and git."""
    path = folder / PROJECT_FILE
    raw = _read(path)
    before = _text_of(raw)
    document, read = _parsed(before)
    data = read
    failed: dict[int, Problem] = {}
    for index, edit in enumerate(edits):
        try:
            document, data = _edited(document, data, edit, harnesses)
        except ValueError as error:
            failed[index] = Problem(".".join(edit.path), str(error))
    text = before if data == read else _ended(document.as_string(), before)
    team, needing, refused = _loaded(text)
    problems = [*failed.values(), *refused]
    shown = None
    if team is not None:
        try:
            problems += check(team, cwd=folder)
            shown = team.resolved(Installed()).show()
        except ConfigError as error:
            problems += error.problems
    sections, rest = _placed(_sections(data, harnesses), problems)
    now = _trusted_now(before) if team is not None else ()
    diff = difflib.unified_diff(before.splitlines(True), text.splitlines(True), PROJECT_FILE, PROJECT_FILE)
    return Draft(
        base=_digest(raw),
        text=text,
        sections=sections,
        kept=_kept(data),
        problems=rest,
        shown=shown,
        diff="".join(line if line.endswith("\n") else f"{line}\n" for line in diff),
        trusting=tuple(line for line in trusted(needing, team) if line not in now),
        blocked=_blocked(before, text, team, bool(failed)),
        unmade=tuple(failed),
    )


def save(
    folder: Path, base: str | None, edits: Sequence[Edit], harnesses: Sequence[Harness], trust: str | None
) -> Asked | Draft:
    """Write the draft of `edits` as the project's team file in `folder`, if the file is as it was when `base` was read
    and the draft can be saved, after asking once, where it writes a value only trust may take, naming each as the team
    would hold it: `trust` is the answer to that question, which covers what it showed alone. It answers the question,
    or the draft it wrote; and raises `ConfigError` saying why it wrote nothing. It blocks, as `draft` does."""
    drafted = draft(folder, edits, harnesses)
    if drafted.base != base:
        raise ConfigError([Problem(PROJECT_FILE, f"changed since it was read, so nothing was saved: {CHANGED}")])
    if drafted.blocked is not None:
        raise ConfigError([Problem(PROJECT_FILE, drafted.blocked)])
    if drafted.trusting:
        question = "\n".join([SAVING, *drafted.trusting, "Save it, as shown here?"])
        if trust != (shown := hashlib.sha256(question.encode()).hexdigest()):
            return Asked(question, "Save it", shown)
    _write(folder / PROJECT_FILE, base, drafted.text)
    return drafted


def keeping(keys: Sequence[str]) -> str | None:
    """What a client says of keys the file holds that are the file's alone, or None where there are none."""
    if not keys:
        return None
    return f"Kept as the file has it, as only the file sets it: {', '.join(f'`{key}`' for key in keys)}."


def trusted(needing: Sequence[Problem], team: Team | None) -> tuple[str, ...]:
    """Each value a project or team file gives that only trust may take, `needing`, by its place and as `team` holds it,
    defaults filled in, in JSON that escapes all but ASCII, or the problem where it holds none there."""
    data: Any = {} if team is None else team.model_dump(mode="json")
    lines = []
    for problem in needing:
        value = data
        for key in problem.where.split("."):
            value = value.get(key) if isinstance(value, dict) else None
        lines.append(f"{problem.where} = {json.dumps(value)}" if value is not None else str(problem))
    return tuple(lines)


# Reading, loading and writing.


def _read(path: Path) -> bytes | None:
    """The file's bytes, or None where there is none. One the editor could not write in place is refused: a link, which
    it would replace, or anything but a file."""
    try:
        found = os.lstat(path)
    except FileNotFoundError:
        return None
    if stat.S_ISLNK(found.st_mode):
        raise ConfigError(
            [Problem(PROJECT_FILE, "is a link, and the editor writes through none: edit the file it names")]
        )
    if not stat.S_ISREG(found.st_mode):
        raise ConfigError([Problem(PROJECT_FILE, "is no file: move it away, or edit the team as a file elsewhere")])
    try:
        return path.read_bytes()
    except OSError as error:
        raise ConfigError([Problem(PROJECT_FILE, f"unreadable: {error}")]) from None


def _text_of(raw: bytes | None) -> str:
    try:
        return "" if raw is None else raw.decode()
    except UnicodeDecodeError:
        raise ConfigError([Problem(PROJECT_FILE, "is not UTF-8 text: edit it in the file")]) from None


def _parsed(text: str) -> tuple[TOMLDocument, dict[str, Any]]:
    """The file as a document that keeps its layout, and as the data it means, by the loader's own parser."""
    try:
        return tomlkit.parse(text), tomllib.loads(text)
    except (TOMLKitError, tomllib.TOMLDecodeError) as error:
        raise ConfigError([Problem(PROJECT_FILE, f"not TOML: {error}: edit it in the file")]) from None


def _loaded(text: str) -> tuple[Team | None, tuple[Problem, ...], tuple[Problem, ...]]:
    """The team `run` would load with `text` as the project's file, each value of it only trust may take, and the
    problems that keep it from loading: the loader itself reads the layers, with the draft in a folder of its own."""
    with tempfile.TemporaryDirectory() as folder:
        (Path(folder) / PROJECT_FILE).write_text(text)
        try:
            team, needing = load_trusted(cwd=Path(folder))
        except ConfigError as error:
            return None, (), error.problems
    return team, needing, ()


def _trusted_now(text: str) -> tuple[str, ...]:
    """What only trust may take from the file as it is, as `trusted` says it, or nothing where it does not load."""
    team, needing, _ = _loaded(text)
    return trusted(needing, team)


def _ended(text: str, before: str) -> str:
    """`text` ending in as many line ends as the file did, or in one where there was none, so a table removed from the
    end leaves no blank line of its own behind."""
    if not text.strip():
        return ""
    ends = len(before) - len(before.rstrip("\n")) if before.strip() else 1
    return text.rstrip("\n") + "\n" * ends


def _blocked(before: str, text: str, team: Team | None, failed: bool) -> str | None:
    """Why a draft cannot be saved: it changes nothing, an edit could not be made, or the loader refuses it. A problem
    `team check` finds is said and does not stop a save, as a team may name a harness this machine lacks."""
    if failed:
        return "Fix each change marked first: the editor could not make it."
    if text == before:
        return "Nothing to save: the draft is the file as it stands."
    if team is None:
        return "Fix each problem marked first: the loader refuses this draft, as `run` would."
    return None


def _digest(raw: bytes | None) -> str | None:
    return None if raw is None else hashlib.sha256(raw).hexdigest()


def _write(path: Path, base: str | None, text: str) -> None:
    """Write `text` to `path` as a whole, through a file beside it renamed over it, never through a link, and only over
    the file `base` is the digest of, or over nothing where it is None. What changed it after the last look is the one
    race this leaves open: a rename cannot compare."""
    changed = ConfigError([Problem(PROJECT_FILE, f"changed as it was saved, so nothing was saved: {CHANGED}")])
    temporary = path.with_name(f".{path.name}.{secrets.token_hex(8)}")
    try:
        mode = 0o666 if base is None else stat.S_IMODE(os.lstat(path).st_mode)
        with os.fdopen(os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode), "wb") as file:
            if base is not None:
                os.fchmod(file.fileno(), mode)
            file.write(text.encode())
            file.flush()
            os.fsync(file.fileno())
        if _digest(_read(path)) != base:
            raise changed
        if base is None:
            os.link(temporary, path)  # Over nothing: a file that came to be since stops it.
        else:
            os.replace(temporary, path)
        folder = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(folder)
        finally:
            os.close(folder)
    except (FileNotFoundError, FileExistsError):
        raise changed from None
    except OSError as error:
        raise ConfigError([Problem(PROJECT_FILE, f"could not be written: {error}")]) from None
    finally:
        temporary.unlink(missing_ok=True)


# Edits, made on the file's own text.


def _edited(
    document: TOMLDocument, data: dict[str, Any], edit: Edit, harnesses: Sequence[Harness]
) -> tuple[TOMLDocument, dict[str, Any]]:
    """The document and its data with one edit made, if it is one a person may make on this draft and the document
    still means what the edit says once written. Otherwise it raises `ValueError`, saying why."""
    sections = _sections(data, harnesses)
    groups = [group for section in sections for group in section.groups]
    fields = {field.path: field for group in groups for field in group.fields}
    addings = [adding for section in sections for adding in section.adding]
    removable = {group.path for group in groups if group.removable}
    path, expected = edit.path, json.loads(json.dumps(data))
    document = tomlkit.parse(document.as_string())  # A copy, so an edit that fails leaves the draft as it was.
    if edit.verb == "set":
        if (field := fields.get(path)) is None:
            raise ValueError("is no key a person sets from here: edit it in the file")
        if field.fixed is not None:
            raise ValueError(field.fixed)
        if edit.text.strip() == field.text.strip():
            return document, data
        value = _value(field, edit.text)
        if value is None:
            document = _emptied(_drop(document, path, expected), path[:-1], expected, removable - {("test",)})
        else:
            document = _put(document, path, value, expected)
    elif edit.verb == "add":
        adding = next((adding for adding in addings if adding.under == path[:-1]), None)
        if adding is None or (adding.names and path[-1] not in adding.names):
            raise ValueError("is nothing a person adds from here: add it in the file")
        if not re.fullmatch(NAME, path[-1]):
            raise ValueError("is no name: letters, digits, `_` and `-`, joined by single dots")
        if _dig(data, *path) is not None:
            raise ValueError("is there already")
        first = adding.first
        value = None if first is None else _value(first, edit.text)
        if first is not None and not first.path and value is None:
            raise ValueError("needs a value as it is added: give one")
        entry = value if first is not None and not first.path else {}
        if first is not None and first.path and value is not None:
            entry = {first.path[0]: value}
        document = _put(document, path, entry, expected)
    else:
        if path not in removable:
            raise ValueError("is nothing a person removes from here: remove it in the file")
        document = _emptied(_drop(document, path, expected), path[:-1], expected, removable)
    if tomllib.loads(document.as_string()) != expected:
        raise ValueError("the editor cannot make this change and keep this file's layout: make it in the file")
    return document, expected


def _value(field: Field, text: str) -> Any:
    """What a field's text means, None where it is left empty, or `ValueError` saying what the field takes."""
    text = text if field.kind == "lines" else text.strip()
    if not text.strip():
        return None
    match field.kind:
        case "list":
            return [part.strip() for part in text.split(",") if part.strip()]
        case "command":
            try:
                return shlex.split(text)
            except ValueError as error:
                raise ValueError(f"is no command line: {error}") from None
        case "integer":
            if not re.fullmatch(r"-?\d+", text):
                raise ValueError("is a whole number")
            return int(text)
        case "number":
            if re.fullmatch(r"-?\d+", text):
                return int(text)
            try:
                number = float(text)
            except ValueError:
                raise ValueError("is a number") from None
            if not math.isfinite(number):
                raise ValueError("is a number")
            return number
        case "yes-no" | "choice":
            values = [choice.value for choice in field.choices]
            if text not in values:
                raise ValueError(f"is {either(f'`{value}`' for value in values)}" if values else "takes no value here")
            return {"yes": True, "no": False}[text] if field.kind == "yes-no" else text
    return text


def _dig(data: Any, *path: str) -> Any:
    for key in path:
        data = data.get(key) if isinstance(data, Mapping) else None
    return data


def _emptied(document: TOMLDocument, path: Keys, data: dict[str, Any], entries: set[Keys]) -> TOMLDocument:
    """Remove each table on `path`, deepest first, that a removal left empty, but an entry a person named, in `entries`,
    which stays until it is removed."""
    while path and path not in entries and _dig(data, *path) == {}:
        document = _drop(document, path, data)
        path = path[:-1]
    return document


def _holds(node: Any, key: str) -> bool:
    """Whether a table of the document holds `key`: text holds no key, whatever its letters."""
    return isinstance(node, Mapping) and key in node


def _body(node: Any) -> list[tuple[Any, Item]]:
    return node.body if isinstance(node, Container) else node.value.body


def _trivia(entry: tuple[Any, Item]) -> bool:
    return entry[0] is None and isinstance(entry[1], Whitespace | Comment)


def _headed(entry: tuple[Any, Item]) -> bool:
    """Whether a body's entry is a table under a header, or one holding such tables, and not a key and its value, as a
    dotted key and an inline table are."""
    name, item = entry
    return isinstance(item, AoT) or (isinstance(item, Table) and not (name is not None and name.is_dotted()))


def _last(node: Any) -> Any:
    """The table rendered last within `node`, which may be `node`, under whose body what follows it is kept."""
    body = _body(node)
    if body and isinstance(body[-1][1], AoT) and body[-1][1].body:
        return _last(body[-1][1].body[-1])
    if body and isinstance(body[-1][1], Table) and _headed(body[-1]):
        return _last(body[-1][1])
    return node


def _tail(node: Any) -> list[tuple[Any, Item]]:
    """Take the blank lines and comments that end a table's body, which belong before what follows it."""
    body, tail = _body(node), []
    while body and _trivia(body[-1]):
        tail.insert(0, body.pop())
    return tail


def _put(document: TOMLDocument, path: Keys, value: Any, data: dict[str, Any]) -> TOMLDocument:
    """Set the key at `path` in the document and in its data, making each table on the way. A new key goes after the
    last key of its table and before the comments that end it, which are about what follows, and a new table goes last
    in its parent, those comments after it."""
    leaf: Any = data
    for key in path[:-1]:
        leaf = leaf.setdefault(key, {}) if isinstance(leaf, dict) else None
    if not isinstance(leaf, dict):
        raise ValueError("is under a key that holds no table: edit it in the file")
    leaf[path[-1]] = value
    node: Any = document
    depth = 0
    while depth < len(path) - 1 and _holds(node, path[depth]):
        node, depth = node[path[depth]], depth + 1
    for key in reversed(path[depth + 1 :]):
        value = {key: value}
    key = path[depth]
    item = _item(value, inline=isinstance(node, InlineTable))
    if _holds(node, key) or not isinstance(node, Container | Table | InlineTable):
        node[key] = item  # In place, or in a table the file writes in parts, which keeps its order.
    elif isinstance(node, InlineTable):
        body = _body(node)
        closing = []  # The space before the closing brace, which stays there.
        while body and body[-1][0] is None and isinstance(body[-1][1], Whitespace) and "," not in body[-1][1].s:
            closing.insert(0, body.pop())
        node.append(key, item)
        body.extend(closing)
    elif isinstance(item, Table):
        last = _last(node)
        tail = _tail(last)
        if _body(last):
            _body(last).append((None, Whitespace("\n")))
        node.append(key, item)
        _body(_last(item)).extend(tail)
    else:
        body = _body(node)
        at = max((index + 1 for index, entry in enumerate(body) if entry[0] and not _headed(entry)), default=0)
        rest = body[at:]
        del body[at:]
        node.append(key, item)
        if rest and rest[0][0] is not None:
            body.append((None, Whitespace("\n")))
        body.extend(rest)
    return tomlkit.parse(document.as_string())


def _item(value: Any, *, inline: bool) -> Any:
    """A value as the document holds it: a table that holds only tables is one no header names, as `[roles.lead]`
    makes `roles`, and text of several lines is written over them."""
    if isinstance(value, dict):
        table: Any = (
            tomlkit.inline_table()
            if inline
            else tomlkit.table(bool(value) and all(isinstance(inner, dict) for inner in value.values()))
        )
        for key, inner in value.items():
            table.append(key, _item(inner, inline=inline))
        return table
    if isinstance(value, str) and "\n" in value:
        return tomlkit.string(value, multiline=True)
    return tomlkit.item(value)


def _drop(document: TOMLDocument, path: Keys, data: dict[str, Any]) -> TOMLDocument:
    """Remove the key at `path` from the document and from its data, if there is one. A table goes with the comments
    right above its header, and those that end it, which are about what follows it, are kept where it was."""
    for key in path[:-1]:
        data = data.get(key, {}) if isinstance(data, dict) else {}
    data.pop(path[-1], None)
    node: Any = document
    for key in path[:-1]:
        if not _holds(node, key):
            return document
        node = node[key]
    if not _holds(node, path[-1]):
        return document
    item = node[path[-1]]
    if isinstance(item, InlineTable) or not isinstance(item, Table) or item.is_super_table():
        del node[path[-1]]
        return tomlkit.parse(document.as_string())
    tail = _tail(_last(item))
    tables = list(_tables(document))
    at = next(index for index, table in enumerate(tables) if table is item)
    # What is right above its header ends the body of the table written before it, or of the file, or else comes right
    # before what holds it there.
    body = _body(tables[at - 1] if at else document)
    at = next((index for index, (_, held) in enumerate(body) if _within(held, item)), len(body))
    del node[path[-1]]
    above = _above(body[:at])
    del body[at - above : at]
    body[at - above : at - above] = _joined(body[: at - above], tail)
    return tomlkit.parse(document.as_string())


def _within(node: Any, item: Any) -> bool:
    """Whether `node` is `item`, or a table with no header of its own that holds it, as `roles` holds `[roles.lead]`."""
    if node is item:
        return True
    return isinstance(node, Table) and node.is_super_table() and any(_within(held, item) for _, held in _body(node))


def _above(body: list[tuple[Any, Item]]) -> int:
    """How many comments end `body` with no blank line after them: those right above the header that follows."""
    count = 0
    while count < len(body) and body[-1 - count][0] is None and isinstance(body[-1 - count][1], Comment):
        count += 1
    return count


def _joined(before: list[tuple[Any, Item]], tail: list[tuple[Any, Item]]) -> list[tuple[Any, Item]]:
    """A removed table's tail, after what came before it, with one blank line between them and not two, and none at
    the start of the file."""
    blank = not before or (_trivia(before[-1]) and isinstance(before[-1][1], Whitespace))
    return tail[1:] if blank and tail and isinstance(tail[0][1], Whitespace) else tail


def _tables(node: Any) -> Iterator[Any]:
    """Every table written under a header of its own, in the order the file has them."""
    for _, item in _body(node):
        if isinstance(item, AoT):
            for table in item.body:
                yield table
                yield from _tables(table)
        elif isinstance(item, Table) and not isinstance(item, InlineTable):
            if not item.is_super_table():
                yield item
            yield from _tables(item)


# Fields, made from the schema.


def _sentences(model: type[BaseModel], key: str) -> list[str]:
    """The sentences of a model's docstring about `key`, the first of the model's keys each names, but the first
    sentence, which its table says."""
    text = " ".join(inspect.cleandoc(model.__doc__ or "").split())
    return [
        sentence
        for sentence in re.split(r"(?<=\.)\s+(?=[A-Z`])", text)[1:]
        if [name for name in re.findall(r"`([^`]+)`", sentence) if name in model.model_fields][:1] == [key]
    ]


def _first(model: Any) -> str:
    """The first sentence of a docstring."""
    text = " ".join(inspect.cleandoc(model.__doc__ or "").split())
    return re.split(r"(?<=\.)\s+(?=[A-Z`])", text)[0]


def _form(hint: Any) -> tuple[str, tuple[Any, ...]]:
    """What a form takes for a type, and its choices."""
    if isinstance(hint, TypeAliasType):
        return _form(hint.__value__)
    origin, args = get_origin(hint), get_args(hint)
    if origin is Annotated:
        return _form(args[0])
    if origin in (Union, UnionType):
        kinds = {_form(arg)[0] for arg in args if arg is not NoneType}
        if kinds == {"integer", "number"}:
            return "number", ()
        return ("list", ()) if "list" in kinds else _form(next(arg for arg in args if arg is not NoneType))
    if origin is Literal:
        return "choice", args
    if origin in (tuple, Sequence):
        return "list", ()
    return {bool: "yes-no", int: "integer", float: "number"}.get(hint, "text"), ()


def _text(kind: str, value: Any) -> str:
    """The text a value shows as in a field of `kind`."""
    if value is None:
        return ""
    if kind == "yes-no" and isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return shlex.join(value) if kind == "command" else ", ".join(value)
    return value if isinstance(value, str) else json.dumps(value)


def _field(
    path: Keys,
    hint: Any,
    value: Any,
    *,
    said: Sequence[str] = (),
    default: Any = inspect.Parameter.empty,
    kind: str | None = None,
    choices: Sequence[Choice] | None = None,
    trust: bool = False,
    fixed: str | None = None,
) -> Field:
    """A field of a value of type `hint`, with `said` before what the reference says of its type and default."""
    found, literal = _form(hint)
    kind = kind or found
    if choices is None:
        choices = [Choice(str(item), str(item)) for item in (("yes", "no") if kind == "yes-no" else literal)]
    text = _text(kind, value)
    if text and kind in ("choice", "yes-no") and text not in {choice.value for choice in choices}:
        choices = [Choice(text, f"{text}, as the file has it"), *choices]
    needed = default is inspect.Parameter.empty
    more = " ".join(filter(None, ({"list": SEVERAL, "command": WORDS}.get(kind), TRUSTED if trust else None)))
    typed = re.sub(r"\[(\w+)\]\(#\w+\)", "table", type_said(hint))  # The reference links a table to its section.
    # A default of None is the key left out, which its words say the meaning of: never `none`, which reads as nothing.
    stands = "left out" if default is None else default_said(default)
    words = [*said, f"Type: {typed}.", "Needed." if needed else f"Default: {stands}.", more]
    empty = "needed" if needed else "left out" if default is None else f"left out: {stands.strip('`')}"
    return Field(
        path, kind, " ".join(filter(None, words)), text, empty, tuple(choices), trust, fixed if not text else None
    )


def _model_field(model: type[BaseModel], key: str, path: Keys, data: Any, **more: Any) -> Field:
    """A field of a key of a model of the schema, its value from `data`, with its docstring's sentences that name
    it."""
    info = model.model_fields[key]
    default = inspect.Parameter.empty if info.is_required() else info.default
    kind = more.pop("kind", "lines" if (model, key) in LINES else "command" if (model, key) in COMMAND else None)
    hint = get_type_hints(model, include_extras=True)[key]
    said = [*_sentences(model, key), *more.pop("said", ())]
    return _field(path, hint, _dig(data, key), said=said, default=default, kind=kind, **more)


def _table(data: Any, *path: str) -> Mapping[str, Any]:
    """The table at `path`, or an empty one where the file holds none there or something else, which the loader
    names."""
    found = _dig(data, *path)
    return found if isinstance(found, Mapping) else {}


def _sections(data: Mapping[str, Any], harnesses: Sequence[Harness]) -> tuple[Section, ...]:
    """The fields of a draft's data, by section."""
    roles = _table(data, "roles")
    return (
        Section(
            "Roles",
            tuple(_role(name, _table(roles, name), data, harnesses) for name in roles),
            (_adding_role(harnesses),),
        ),
        _topology(data, [*roles]),
        Section("Budget", (_budget(data),)),
        _labels(data),
        _auth(data),
        Section("Test", (_test(data),)),
    )


HARNESS = (
    "The harness its agents run on, of those this machine has a driver for, with what `doctor` finds of each. A "
    "command or a `module:attr` is the file's alone, as either runs code as you."
)
MODEL = "No list of models is offered: no driver says which models its harness takes."
PROFILE = "The auth profile whose variables its harness receives."
NO_DRIVER = (
    "Unknown here: its harness is none this machine has a driver for, which would say which sandboxes it declares. "
    "Choose such a harness, or set one in the file."
)


def _harnessed(harnesses: Sequence[Harness]) -> dict[str, Any]:
    """What a harness field says and takes."""
    choices = [Choice(item.name, f"{item.name}: {item.said}") for item in harnesses]
    return {"said": [HARNESS], "kind": "choice", "choices": choices}


def _role(name: str, role: Mapping[str, Any], data: Mapping[str, Any], harnesses: Sequence[Harness]) -> Group:
    path = ("roles", name)
    harness = next((item for item in harnesses if item.name == role.get("harness")), None)
    profiles = [*_table(data, "auth")]
    fields = []
    for key in ROLE:
        more: dict[str, Any] = {}
        if key == "harness":
            more = _harnessed(harnesses)
        elif key == "model":
            more = {"said": [MODEL]}
        elif key == "sandbox":
            more = _sandboxing(harness)
        elif key == "auth":
            why = None if profiles else "The file has no auth profile: add one under Auth profiles first."
            choices = [Choice(profile, profile) for profile in profiles]
            more = {"said": [PROFILE], "kind": "choice", "choices": choices, "fixed": why}
        fields.append(_model_field(Role, key, (*path, key), role, **more))
    kept = tuple(key for key in role if key not in ROLE)
    return Group(name, path, _first(Role), tuple(fields), kept, removable=True)


def _sandboxing(harness: Harness | None) -> dict[str, Any]:
    """What a sandbox field says and takes: one of those its harness's driver declares, or none, saying why, where it
    declares none, could not say, or there is no such driver."""
    if harness is None:
        return {"kind": "choice", "choices": [], "fixed": NO_DRIVER}
    if harness.sandboxes is None:
        why = f"Unknown here: `{harness.name}`'s driver could not say which sandboxes it declares. Set one in the file."
        return {"kind": "choice", "choices": [], "fixed": why}
    if not harness.sandboxes:
        return {"kind": "choice", "choices": [], "fixed": f"`{harness.name}` declares no sandbox, so none can be set."}
    choices = [Choice(sandbox, sandbox) for sandbox in harness.sandboxes]
    return {"said": [f"A sandbox `{harness.name}` declares."], "kind": "choice", "choices": choices}


def _adding_role(harnesses: Sequence[Harness]) -> Adding:
    first = _model_field(Role, "harness", ("harness",), {}, **_harnessed(harnesses))
    return Adding("Add a role", ("roles",), first=first)


SELECTING = either(f"`{selector}`" for selector in (*SELECTORS, "role:<name>", "group:<name>"))
EDGES = "Whom agents of each role may reach, beside what a preset grants."
PROGRAM = "program: left to the program that owns the session, which a script starts, so a start from here is refused"


def _topology(data: Mapping[str, Any], roles: Sequence[str]) -> Section:
    topology = _table(data, "topology")
    values = ("settled", "program", *(f"role:{role}" for role in roles))
    until = [Choice(value, PROGRAM if value == "program" else value) for value in values]
    own = _model_field(Topology, "until", ("topology", "until"), topology, kind="choice", choices=until)
    groups = [Group("Topology", ("topology",), _first(Topology), (own,))]
    groups += [_preset(name, params) for name, params in topology.items() if _used_once(name, params)]
    channels = _table(topology, "channels")
    groups += [_channel(name, _table(channels, name)) for name in channels]
    edges = _table(topology, "edges")
    fields = tuple(
        _field(("topology", "edges", role), tuple[str, ...], edges.get(role), said=[_reaching(role)], default=())
        for role in dict.fromkeys([*roles, *edges, "all"])
    )
    groups.append(Group("Edges", ("topology", "edges"), EDGES, fields))
    limits = tuple(
        _model_field(Limits, key, ("topology", "limits", key), topology.get("limits")) for key in Limits.model_fields
    )
    groups.append(Group("Limits", ("topology", "limits"), _first(Limits), limits))
    kinds = [Choice(name, f"{name}: {_first(model)}") for name, model in CHANNELS.items()]
    adding = (
        Adding("Use a preset", ("topology",), names=tuple(name for name in PRESETS if name not in topology)),
        Adding(
            "Add a channel",
            ("topology", "channels"),
            first=_field(("kind",), KIND, None, said=[KIND_FIXED], choices=kinds),
        ),
    )
    return Section("Topology", tuple(groups), adding)


def _used_once(name: str, params: Any) -> bool:
    """Whether a key of `[topology]` is a preset of the SDK's used once, which the editor shows: one an extension
    gives, or one used several times, is the file's alone."""
    return name in PRESETS and isinstance(params, Mapping)


def _reaching(role: str) -> str:
    who = "every role's agents" if role == "all" else f"agents of `{role}`"
    return f"Whom {who} may reach: {SELECTING}."


def _preset(name: str, params: Mapping[str, Any]) -> Group:
    preset = PRESETS[name]
    path = ("topology", name)
    signature = inspect.signature(preset).parameters
    fields = tuple(
        _field((*path, key), parameter.annotation, params.get(key), default=parameter.default)
        for key, parameter in signature.items()
    )
    kept = tuple(key for key in params if key not in signature)
    return Group(name, path, _first(preset), fields, kept, removable=True)


def _channel(name: str, channel: Mapping[str, Any]) -> Group:
    path = ("topology", "channels", name)
    model = CHANNELS.get(str(channel.get("kind")))
    if model is None:
        kind = _field((*path, "kind"), KIND, channel.get("kind"))
        return Group(name, path, "", (kind,), tuple(key for key in channel if key != "kind"), removable=True)
    fields = [_model_field(model, key, (*path, key), channel) for key in model.model_fields]
    fields[0] = replace(fields[0], fixed=KIND_FIXED)
    kept = tuple(key for key in channel if key not in model.model_fields)
    return Group(name, path, _first(model), tuple(fields), kept, removable=True)


def _budget(data: Mapping[str, Any]) -> Group:
    budget = _table(data, "budget")
    fields = [_model_field(Budget, key, ("budget", key), budget) for key in Budget.model_fields if key != "estimate"]
    units, amount = get_args(get_args(get_type_hints(Budget, include_extras=True)["estimate"])[0])
    said = _sentences(Budget, "estimate")
    estimate = _table(budget, "estimate")
    fields += [
        _field(("budget", "estimate", unit), amount, estimate.get(unit), said=said, default=None)
        for unit in get_args(units)
    ]
    return Group(
        "Budget",
        ("budget",),
        _first(Budget),
        tuple(fields),
        tuple(key for key in budget if key not in Budget.model_fields),
    )


def _labels(data: Mapping[str, Any]) -> Section:
    labels = _table(data, "labels")
    values = get_args(get_args(get_type_hints(Team, include_extras=True)["labels"])[0])[1]
    said = _sentences(Team, "labels")
    fields = tuple(_field(("labels", name), values, labels[name], said=said) for name in labels)
    group = Group("Labels", ("labels",), said[0], fields)
    return Section("Labels", (group,), (Adding("Add a label", ("labels",), first=_field((), values, None, said=said)),))


def _auth(data: Mapping[str, Any]) -> Section:
    profiles = _table(data, "auth")
    groups = tuple(
        Group(
            name,
            ("auth", name),
            _first(AuthProfile),
            (_model_field(AuthProfile, "env", ("auth", name, "env"), _table(profiles, name), trust=True),),
            tuple(key for key in _table(profiles, name) if key != "env"),
            removable=True,
        )
        for name in profiles
    )
    first = _model_field(AuthProfile, "env", ("env",), {}, trust=True)
    return Section("Auth profiles", groups, (Adding("Add an auth profile", ("auth",), first=first),))


def _test(data: Mapping[str, Any]) -> Group:
    test = _dig(data, "test")
    fields = tuple(_model_field(Test, key, ("test", key), test, trust=key == "command") for key in Test.model_fields)
    return Group("Test", ("test",), _first(Test), fields, removable=test is not None)


def _kept(data: Mapping[str, Any]) -> tuple[str, ...]:
    """The keys at the top of a team, and of its topology, that are the file's alone."""
    kept = [key for key in data if key not in ("roles", "topology", "budget", "labels", "auth", "test")]
    shown = ("until", "edges", "limits", "channels")
    kept += [
        f"topology.{key}"
        for key, value in _table(data, "topology").items()
        if key not in shown and not _used_once(key, value)
    ]
    return tuple(kept)


def _placed(
    sections: Sequence[Section], problems: Sequence[Problem]
) -> tuple[tuple[Section, ...], tuple[Problem, ...]]:
    """Each problem at the field it names, or at the deepest table that holds its place, or else at none. A tagged
    table, such as a channel, is named in a problem with its tag after it, which is no key of the file."""
    groups = sorted((group for section in sections for group in section.groups), key=lambda group: -len(group.where))
    fields = {field.where for group in groups for field in group.fields}
    at: dict[str, list[Problem]] = {}
    rest = []
    for problem in problems:
        holding = [group.where for group in groups if f"{problem.where}.".startswith(f"{group.where}.")]
        untagged = [f"{held}.{problem.where.removeprefix(held).split('.', 2)[-1]}" for held in holding]
        where = next((found for found in (problem.where, *untagged, *holding) if found in fields), None)
        where = where or next(iter(holding), None)
        if where is None:
            rest.append(problem)
        else:
            at.setdefault(where, []).append(problem)

    def placed(group: Group) -> Group:
        fields = tuple(replace(field, problems=tuple(at.get(field.where, ()))) for field in group.fields)
        return replace(group, fields=fields, problems=tuple(at.get(group.where, ())))

    return tuple(replace(section, groups=tuple(map(placed, section.groups))) for section in sections), tuple(rest)
