"""A command for each op a person may run, made from the op registry and its schemas, so that the command line cannot
drift from the ops. An agent's `ph task.claim --queue tasks` is a person's `platoon-harness task claim SESSION --queue
tasks`: the op's name split at its dot, then the session, then a flag per argument."""

import inspect
import json
import re
import shlex
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any, Literal

from cyclopts import App, Parameter

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


def person_ops() -> dict[str, Op]:
    """The ops a person may run: every op the SDK holds that is kept to neither the runtime nor an agent, but `wait` and
    the ops on a wait, as a wait parks a turn and a person has none."""
    return {
        name: operation
        for name, operation in _OPS.items()
        if not (operation.runtime or operation.agent or name.partition(".")[0] == "wait")
    }


_PERSON = frozenset(person_ops())
CONFIRMED = frozenset({"agent.cancel", "agent.retire", "body.tombstone", "session.cancel", "session.close"})
"""The ops a person is asked about once before they run, in the terminal and in the browser alike: each ends an agent or
the session, or erases a body, which nothing takes back."""


def cut(text: str, *, file: bool = False) -> tuple[str, str | None]:
    """A person's text as a message's gist and body, in the terminal and in the browser alike: the text itself when it
    fits in a gist, and otherwise its first characters and an ellipsis, with the whole as the body. A file is a body of
    its own, so beside one a text too long for a gist is refused."""
    if len(text) <= GIST_LIMIT:
        return text, None
    if file:
        raise ValueError("a long message and a file are two bodies: send them one at a time")
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
            found[namespace] = App(
                name=namespace,
                help=f"The `{namespace}` ops, each on one session, with the arguments an agent's `ph {namespace}.<op>` "
                "takes as flags.",
            )
        command = _command(operation)
        if verb:
            found[namespace].command(command, name=verb)
        else:
            found[namespace].default(command)
            found[namespace].help = command.__doc__
    return found


@dataclass(frozen=True)
class Flag:
    """One argument of an op, as a flag. `json` takes JSON text, and `body` stored text, or a file's with `-file`."""

    name: str
    annotation: Any
    default: Any
    json: bool
    body: bool

    @property
    def flag(self) -> str:
        return f"--{self.name.replace('_', '-')}"


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


def flags(operation: Op) -> list[Flag]:
    """The flags an op's command takes, a flag per argument."""
    return _fields(operation.input.model_json_schema())


def described(operation: Op) -> str:
    """An op's description in a person's words, as its command's help says it."""
    return _described(operation.fn.__doc__ or "", flags(operation))


def _fields(schema: Mapping[str, Any]) -> list[Flag]:
    required = set(schema.get("required", ()))
    fields = []
    for name, field in schema.get("properties", {}).items():
        body = any(branch.get("pattern") == BODY_REF for branch in field.get("anyOf", [field]))
        annotation, is_json = (str | None, False) if body else _type_of(field)
        annotation = str | None if is_json else annotation
        default = field.get("default")
        if name in required:
            default = inspect.Parameter.empty
        elif is_json or isinstance(default, list | dict):
            default = None if is_json else tuple(default)
        fields.append(Flag(name, annotation, default, is_json, body))
    return fields


def _described(text: str, fields: list[Flag]) -> str:
    """An op's own words as a person reads them at a command line: each op it names as the command that runs it, with a
    sentence that names one with no command left out, as an agent's are, and each of its arguments as a flag."""
    flags = {field.name: field.flag for field in fields}
    said = taught(text, command_of, _OPS, _PERSON)
    return OP_NAMED.sub(lambda named: f"`{flags[named[1]]}`" if named[1] in flags else named[0], said)


def _help(field: Mapping[str, Any], found: Flag, fields: list[Flag]) -> str:
    said = _described(field.get("description", ""), fields)
    if found.json:
        said = f"{said} As JSON.".strip()
    if found.body:
        said = f"{said} {found.flag}-file reads it from a file.".strip()
    return said


def _parameters(schema: Mapping[str, Any], fields: list[Flag]) -> list[inspect.Parameter]:
    properties = schema.get("properties", {})
    parameters = []
    for found in fields:
        flag = bool in (found.annotation, *getattr(found.annotation, "__args__", ()))
        option = Parameter(
            name=found.flag,
            help=_help(properties[found.name], found, fields),
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


def _example(name: str, fields: list[Flag]) -> str:
    """The command with what it needs, each value named for what it is."""
    needed = [field for field in fields if field.default is inspect.Parameter.empty]
    flags = (field.flag if field.annotation is bool else f"{field.flag} {field.name.upper()}" for field in needed)
    return " ".join(["platoon-harness", *name.split("."), "SESSION", *flags])


async def _arguments(session: Session, fields: list[Flag], given: Mapping[str, Any]) -> dict[str, Any]:
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
    """A body as a ref: text stored, or a file's bytes, or a ref as it stands."""
    if text is not None and path is not None:
        raise Usage(f"give {field.flag} or {field.flag}-file, not both")
    if path is not None:
        try:
            return await session.put_body(path.read_bytes())
        except OSError as error:
            raise Usage(f"{field.flag}-file: {error}") from None
    if text is None or re.fullmatch(BODY_REF, text):
        return text
    return await session.put_body(text.encode())


def _command(operation: Op) -> Callable[..., Awaitable[int]]:
    """One op as a command: a read on a view credential, which writes nothing, and anything else on a control one."""
    schema = operation.input.model_json_schema()
    fields = _fields(schema)
    reads = operation.query or operation.exposes

    async def run_op(*named: str, **given: Any) -> int:
        async with Session.attach(named[0], view=reads) as attached:
            args = await _arguments(attached, fields, given)
            outcome = await attached.submit(operation.name, key=given.get("key"), **args)
        return said(outcome)

    first, _, rest = _described(operation.fn.__doc__ or "", fields).partition(". ")
    described = f"{first.rstrip('.')}.\n\n{rest}".rstrip()
    command: Any = run_op
    command.__signature__ = inspect.Signature([_SESSION, *_parameters(schema, fields), *(() if reads else (_KEY,))])
    command.__doc__ = (
        f"{described}\n\nFor example:\n\n    {_example(operation.name, fields)}\n\n"
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
