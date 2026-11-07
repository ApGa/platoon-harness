"""A command for each op a person may run, made from the op registry and its schemas, so that the command line cannot
drift from the ops. An agent's `ph task.claim --queue tasks` is a person's `platoon-harness task claim SESSION --queue
tasks`: the op's name split at its dot, then the session, then a flag per argument. A form, in the terminal's palette
and in the page's, is made from the same flags."""

import inspect
import json
import re
import shlex
import types
from collections.abc import Awaitable, Callable, Iterable, Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Annotated, Any, Literal, Union, get_args, get_origin

from cyclopts import App, Parameter
from pydantic import BaseModel

from platoon_harness import Session
from platoon_harness.kernel import GIST_LIMIT, Op, Outcome, registry
from platoon_harness.primitives import BODY_REF, PRIMITIVES
from platoon_harness.tools import OP_NAMED, taught

from .exits import REFUSED, Usage
from .output import note, refused, say, shown

_KINDS = {"string": str, "integer": int, "number": float, "boolean": bool}
_LITERAL: Any = Literal  # A flag's type is made from a schema when the command line is, for cyclopts to parse by.
_TUPLE: Any = tuple
_SESSION_HELP = "A session, by name. `platoon-harness session list` shows them."
_SEVERAL = "Separate several with commas."
"""How a form takes a list, where a command line takes its flag again for each."""
_SESSION = inspect.Parameter("session", inspect.Parameter.POSITIONAL_ONLY, annotation=str)
_KEY = inspect.Parameter(
    "key",
    inspect.Parameter.KEYWORD_ONLY,
    default=None,
    annotation=Annotated[
        str | None, Parameter(help="Name this command, so that running it again with the same key is one operation.")
    ],
)
_OPS = registry(PRIMITIVES)
_PURPOSES = {
    "agent": "Agents: start one, interrupt a turn, hold one's deliveries and release it, cancel or retire one, and see "
    "how each stands.",
    "approval": "Approvals, the decisions harnesses wait on: resolve one.",
    "attention": "What needs a person now, each with the actions that would settle it.",
    "blob": "Bodies that events carry: read one by its ref.",
    "board": "Boards: post an object, revise it, read a version, and find objects by name, author, field or text.",
    "body": "Stored bodies: redact one, keeping whole the events that cite it.",
    "budget": "Budgets: set a scope's limits, and see what is spent and held against each.",
    "channel": "Channels: create a topic, queue or board, and list those you may use.",
    "context": "What agents were offered: show the text each item of an offer showed.",
    "effect": "Effects whose outcome is uncertain: say whether one happened, when nothing else can tell.",
    "episode": "Episodes: open and close a part of the session with one outcome, as only events inside one can become "
    "training data.",
    "message": "Messages: send one to `@agent`, `#channel` or `+group`, and read your inbox, a channel or a group.",
    "ops": "The ops you hold a grant for, with their schemas.",
    "repo": "Commits the session recorded and its workspaces: look a commit up by its SHA, run the team's test command "
    "on it, or read its patch or a workspace's uncommitted diff.",
    "task": "Tasks on a queue: add one, claim it, renew its lease, then complete it, fail it or release it, and list "
    "them.",
    "view": "What a client follows, the roster, attention or changes: watch one, as a snapshot then keyed changes.",
}
"""What each group of commands is for, as its help says first."""


def _parks(name: str) -> bool:
    """Whether an op is `wait` or one on a wait, which parks a turn: a person has none."""
    return name.partition(".")[0] == "wait"


def person_ops() -> dict[str, Op]:
    """The ops a person may run: every op the SDK holds that is kept to neither the runtime nor an agent, but `wait` and
    the ops on a wait, as a wait parks a turn and a person has none."""
    return {
        name: operation
        for name, operation in _OPS.items()
        if not (operation.runtime or operation.agent or _parks(name))
    }


_PERSON = frozenset(person_ops())
CONFIRMED = frozenset(
    {"agent.cancel", "agent.retire", "body.tombstone", "repo.test", "session.cancel", "session.close"}
)
"""The ops a person is asked about once before they run, in the terminal and in the browser alike: each ends an agent or
the session, erases a body, or runs a commit's code as you, which nothing takes back."""


def cut(text: str, *, file: str | None = None) -> tuple[str, str | None]:
    """A person's text as a message's gist and body, in the terminal and in the browser alike: the text itself when it
    fits in a gist, and otherwise its first characters and an ellipsis, with the whole as the body. A file, named by
    `file`, is a body of its own and keeps no name, so beside one the gist is the text and the file's name, and must
    fit."""
    if file is not None:
        gist = f"{text} (file {file})" if text else f"file {file}"
        if len(gist) > GIST_LIMIT:
            raise ValueError(
                f"the words beside a file and its name are the gist, of at most {GIST_LIMIT} characters, and these "
                f"make {len(gist)}: send long words alone, or name the file shorter"
            )
        return gist, None
    if len(text) <= GIST_LIMIT:
        return text, None
    return f"{text[: GIST_LIMIT - 1]}…", text


def command_of(op: str) -> str:
    """The command that runs an op: `task.claim` is `platoon-harness task claim`."""
    return f"platoon-harness {op.replace('.', ' ')}"


def groups(found: dict[str, App]) -> dict[str, App]:
    """A group of commands per namespace, beside those already in `found`. An op `task.claim` is the command `task
    claim`, and an op with no dot, `peers`, is the command of its own name."""
    for name, operation in sorted(person_ops().items()):
        namespace, _, verb = name.partition(".")
        if namespace not in found:
            found[namespace] = App(name=namespace, help=_PURPOSES[namespace] if verb else None)
        command = _command(operation)
        if verb:
            found[namespace].command(command, name=verb)
        else:
            found[namespace].default(command)
            found[namespace].help = command.__doc__
    return found


@dataclass(frozen=True)
class Flag:
    """One argument of an op, as a flag of its command and a field of its form. `json` takes JSON text, and `body`
    stored text, or at a command line a file's with `-file`. `help` is what it is in a person's words."""

    name: str
    annotation: Any
    default: Any
    json: bool
    body: bool
    help: str

    @property
    def flag(self) -> str:
        return f"--{self.name.replace('_', '-')}"

    @property
    def required(self) -> bool:
        return self.default is inspect.Parameter.empty

    @property
    def kind(self) -> str:
        """What a form takes for it: `body`, `json`, `yes-no`, `choice`, `list`, `integer`, `number` or `text`."""
        if self.body or self.json:
            return "body" if self.body else "json"
        found = _branch(self.annotation)
        if get_origin(found) is Literal:
            return "choice"
        if get_origin(found) is tuple:
            return "list"
        return {bool: "yes-no", int: "integer", float: "number"}.get(found, "text")

    @property
    def choices(self) -> tuple[Any, ...]:
        """What a `choice` takes, and nothing for any other kind."""
        return get_args(_branch(self.annotation)) if self.kind == "choice" else ()


def _branch(annotation: Any) -> Any:
    """A flag's type, None taken out of it."""
    if get_origin(annotation) in (Union, types.UnionType):
        return next(branch for branch in get_args(annotation) if branch is not type(None))
    return annotation


@dataclass(frozen=True)
class Form:
    """A write op as a person runs it from a form, in the terminal's palette and in the page's alike: the op, what it
    does as its command's help says it, and a field per flag of its command, in its help's words and for a list how a
    form takes several, but `via`, what an act was decided through, which each client says itself where `via` says the
    op takes one."""

    op: str
    said: str
    fields: tuple[Flag, ...]
    via: bool

    @property
    def title(self) -> str:
        """The op as a person reads its name: `agent spawn`."""
        return self.op.replace(".", " ")

    @property
    def summary(self) -> str:
        """What it does in its first sentence, as a palette lists it and as its command's help begins."""
        return f"{self.said.partition('. ')[0].rstrip('.')}."


def forms(held: Iterable[Mapping[str, Any]]) -> list[Form]:
    """The write ops a person may run, of those `ops.list` says they hold, each as its form, by the one rule both
    clients keep: every op but a query, which a pane draws, and but `wait` and the ops on a wait, as a wait parks a turn
    and a person has none. What a person holds no grant for, `ops.list` leaves out already."""
    found = []
    for entry in sorted(held, key=lambda entry: entry["name"]):
        if entry["query"] or entry["exposes"] or _parks(entry["name"]):
            continue
        schema = entry["schema"]
        fields = _fields(schema)
        asked = tuple(
            replace(field, help=f"{field.help} {_SEVERAL}".strip()) if field.kind == "list" else field
            for field in fields
            if field.name != "via"
        )
        said = _described(entry["description"] or "", schema.get("properties", {}))
        found.append(Form(entry["name"], said, asked, len(asked) < len(fields)))
    return found


def _type_of(field: Mapping[str, Any]) -> tuple[Any, bool]:
    """The Python type a flag takes for a field of a JSON schema, and whether its text is JSON: an object, or a value
    of no single type."""
    branches = field.get("anyOf", [field])
    nullable = any(branch.get("type") == "null" for branch in branches)
    branch = next((branch for branch in branches if branch.get("type") != "null"), {})
    kind = branch.get("type")
    if "enum" in branch or "const" in branch:
        found: Any = _LITERAL[tuple(branch.get("enum", [branch.get("const")]))]
    elif kind == "array":
        found = _TUPLE[_KINDS.get(branch.get("items", {}).get("type"), str), ...]
    else:
        found = _KINDS.get(kind, str)
    return (found | None if nullable else found), kind not in _KINDS and kind != "array" and "enum" not in branch


def _fields(schema: Mapping[str, Any]) -> tuple[Flag, ...]:
    """A flag per argument of a schema, each with its help: its description in a person's words, and as JSON where it
    takes JSON."""
    required = set(schema.get("required", ()))
    properties = schema.get("properties", {})
    fields = []
    for name, field in properties.items():
        body = any(branch.get("pattern") == BODY_REF for branch in field.get("anyOf", [field]))
        annotation, is_json = (str | None, False) if body else _type_of(field)
        annotation = str | None if is_json else annotation
        default = field.get("default")
        if name in required:
            default = inspect.Parameter.empty
        elif is_json or isinstance(default, list | dict):
            default = None if is_json else tuple(default)
        said = _described(field.get("description", ""), properties)
        fields.append(Flag(name, annotation, default, is_json, body, f"{said} As JSON.".strip() if is_json else said))
    return tuple(fields)


def _described(text: str, names: Iterable[str]) -> str:
    """An op's own words as a person reads them at a command line: each op it names as the command that runs it, with a
    sentence that names one with no command left out, as an agent's are, and each of its arguments, among `names`, as
    a flag."""
    flags = {name: f"--{name.replace('_', '-')}" for name in names}
    said = taught(text, command_of, _OPS, _PERSON)
    return OP_NAMED.sub(lambda named: f"`{flags[named[1]]}`" if named[1] in flags else named[0], said)


def _parameters(fields: tuple[Flag, ...]) -> list[inspect.Parameter]:
    parameters = []
    for found in fields:
        flag = bool in (found.annotation, *getattr(found.annotation, "__args__", ()))
        option = Parameter(
            name=found.flag,
            help=f"{found.help} {found.flag}-file reads it from a file.".strip() if found.body else found.help,
            negative=f"--no-{found.flag[2:]}" if flag else (),
            show_default=found.default not in (None, (), "", False),
        )
        annotation = Annotated[found.annotation, option]
        parameters.append(
            inspect.Parameter(found.name, inspect.Parameter.KEYWORD_ONLY, default=found.default, annotation=annotation)
        )
        if found.body:
            reads = Parameter(name=f"{found.flag}-file", help=f"A file whose bytes are the {found.name}.")
            parameters.append(
                inspect.Parameter(
                    f"{found.name}_file",
                    inspect.Parameter.KEYWORD_ONLY,
                    default=None,
                    annotation=Annotated[Path | None, reads],
                )
            )
    return parameters


def _example(name: str, fields: tuple[Flag, ...]) -> str:
    """The command with what it needs, each value named for what it is."""
    needed = [field for field in fields if field.default is inspect.Parameter.empty]
    flags = (field.flag if field.annotation is bool else f"{field.flag} {field.name.upper()}" for field in needed)
    return " ".join(["platoon-harness", *name.split("."), "SESSION", *flags])


async def _arguments(session: Session, fields: tuple[Flag, ...], given: Mapping[str, Any]) -> dict[str, Any]:
    """What the op takes from the flags given: a list for a repeated flag, JSON parsed, and a body stored first. A flag
    left out leaves the op its own default."""
    args: dict[str, Any] = {}
    for field in fields:
        file = given.get(f"{field.name}_file")
        if field.name not in given and file is None:
            continue
        value = given.get(field.name)
        if field.body:
            value = await _body(session, field, value, file)
        elif field.json and isinstance(value, str):
            try:
                value = json.loads(value)
            except ValueError as error:
                raise Usage(f"{field.flag} takes JSON: {error}") from None
        args[field.name] = list(value) if isinstance(value, tuple) else value
    return args


async def _body(session: Session, field: Flag, text: str | None, path: Path | None) -> str | None:
    """A body as a ref: a file's bytes stored, or its text as `body_ref` makes it one."""
    if text is not None and path is not None:
        raise Usage(f"give {field.flag} or {field.flag}-file, not both")
    if path is not None:
        try:
            return await session.put_body(path.read_bytes())
        except OSError as error:
            raise Usage(f"{field.flag}-file: {error}") from None
    return None if text is None else await body_ref(session, text)


async def body_ref(session: Session, text: str) -> str:
    """A body's text as the ref its op cites, at a command line and in either client's form alike: a ref as it stands,
    and any other text stored as a body."""
    return text if re.fullmatch(BODY_REF, text) else await session.put_body(text.encode())


def _command(operation: Op) -> Callable[..., Awaitable[int]]:
    """One op as a command: a read on a view credential, which writes nothing, and anything else on a control one,
    named by `--key`."""
    reads = operation.query or operation.exposes

    async def run(attached: Session, args: dict[str, Any], given: Mapping[str, Any]) -> int:
        return said(await attached.submit(operation.name, key=given.get("key"), **args))

    command: Any = derived(operation.name, operation.input, operation.fn.__doc__ or "", run, reads=reads)
    if not reads:
        signature = inspect.signature(command)
        command.__signature__ = signature.replace(parameters=[*signature.parameters.values(), _KEY])
    return command


def derived(
    name: str,
    input: type[BaseModel],
    doc: str,
    run: Callable[[Session, dict[str, Any], Mapping[str, Any]], Awaitable[int]],
    *,
    reads: bool,
) -> Callable[..., Awaitable[int]]:
    """A command made from a schema as an op's is: the session, then a flag per field, with `doc` in a person's words as
    its help. `run` takes the session, attached on a view credential if it `reads`, the arguments, and the flags as
    given."""
    schema = input.model_json_schema()
    fields = _fields(schema)

    async def run_command(*named: str, **given: Any) -> int:
        async with Session.attach(named[0], view=reads) as attached:
            return await run(attached, await _arguments(attached, fields, given), given)

    first, _, rest = _described(doc, schema.get("properties", {})).partition(". ")
    described = f"{first.rstrip('.')}.\n\n{rest}".rstrip()
    command: Any = run_command
    command.__signature__ = inspect.Signature([_SESSION, *_parameters(fields)])
    command.__doc__ = (
        f"{described}\n\nFor example:\n\n    {_example(name, fields)}\n\n"
        f"Parameters\n----------\nsession\n    {_SESSION_HELP}"
    )
    return command


def said(outcome: Outcome) -> int:
    """Print what an op answered on stdout, as JSON, or its refusal on stderr."""
    if outcome.refusal is not None:
        note(refused(outcome.refusal))
        return REFUSED
    if outcome.result is not None:
        say(shown(outcome.result))
    return 0


def command_line(session: str, op: str, args: Mapping[str, Any]) -> str:
    """The command that runs `op` with `args`, as a person would type it, which is how an action is shown."""
    words = [*command_of(op).split(), session]
    for name, value in args.items():
        flag = f"--{name.replace('_', '-')}"
        if isinstance(value, bool):
            words.append(flag if value else f"--no-{flag[2:]}")
        elif isinstance(value, list):
            for item in value:
                words += [flag, str(item)]
        else:
            words += [flag, json.dumps(value) if isinstance(value, dict) else str(value)]
    return shlex.join(words)
