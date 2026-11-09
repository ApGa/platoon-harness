"""`python -m platoon_harness_cli.team_file > docs/reference/team-file.md`: the team file's reference, made from its
schema."""

import inspect
import json
import re
import sys
from collections.abc import Iterator, Mapping, Sequence
from types import NoneType, UnionType
from typing import Annotated, Any, Literal, TypeAliasType, Union, get_args, get_origin, get_type_hints

from pydantic import BaseModel, JsonValue
from pydantic.fields import FieldInfo

from platoon_harness.config import ENVIRONMENT_VARIABLE, PROJECT_FILE
from platoon_harness.kernel import NAME
from platoon_harness.schema import Duration, either
from platoon_harness.team import Team
from platoon_harness.tools import PREAMBLE
from platoon_harness.topology import PRESETS, Topology

HIDDEN = {(Topology, "unexpanded")}
"""Fields no file sets: `expand` reads an `unexpanded` key of `[topology]` as a preset's name."""
WORDS = {str: "string", int: "integer", float: "number", bool: "boolean"}
PLURAL = ("string", "integer", "number", "boolean", "name", "duration", "list", "table")


def _plural(kind: str) -> str:
    first, _, rest = kind.partition(" ")
    if first.rstrip(",") in PLURAL:
        return f"{first.rstrip(',')}s{',' if first.endswith(',') else ''} {rest}".rstrip()
    if kind == "any value":
        return "any values"
    return f"{kind} tables" if kind.startswith("[") else kind


def _pattern(pattern: str) -> str:
    text = pattern.removeprefix("^").removesuffix("$").replace(NAME, "<name>")
    if text == "<name>":
        return "name"
    if match := re.fullmatch(r"\(([^()]*)\)(.*)", text):
        return either(f"`{choice}{match[2]}`" for choice in match[1].split("|"))
    return f"string matching `{text}`"


def _limits(item: Any) -> Iterator[str]:
    if isinstance(item, FieldInfo):
        for inner in item.metadata:
            yield from _limits(inner)
        return
    if (above := getattr(item, "gt", None)) is not None:
        yield f"above {above}"
    if (least := getattr(item, "ge", None)) is not None:
        yield f"at least {least}"
    if least := getattr(item, "min_length", None):
        yield f"at least {least}"


def type_said(hint: Any) -> str:
    """A value's type in a file's words, as the reference and the team editor say it."""
    if hint == Duration:
        return "duration, such as `30m`"
    if isinstance(hint, TypeAliasType):
        return type_said(hint.__value__)
    origin, args = get_origin(hint), get_args(hint)
    if origin is Annotated:
        base, *metadata = args
        patterns = [item.pattern for item in metadata if getattr(item, "pattern", None)]
        kind = _pattern(patterns[0]) if patterns else type_said(base)
        return ", ".join([kind, *(limit for item in metadata for limit in _limits(item))])
    if origin in (Union, UnionType):
        kinds = list(dict.fromkeys(type_said(arg) for arg in args if arg is not NoneType))
        return "number" if kinds == ["integer", "number"] else either(kinds)
    if origin is Literal:
        return either(f"`{json.dumps(value)}`" for value in args)
    if origin in (tuple, Sequence):
        return f"list of {_plural(type_said(args[0]))}"
    if origin is Mapping:
        key, value = args
        keys = type_said(key).replace('"', "")
        return f"{_plural(type_said(value))}, by {'key' if keys == 'string' else keys}"
    if hint is JsonValue:
        return "any value"
    if isinstance(hint, type) and issubclass(hint, BaseModel):
        return f"[{hint.__name__}](#{hint.__name__.lower()})"
    return WORDS[hint]


def default_said(value: Any) -> str:
    """A default in a file's words: `required` where there is none."""
    if value is inspect.Parameter.empty:
        return "required"
    if value is None:
        return "none"
    if value == PREAMBLE:
        return "the SDK's `PREAMBLE`, which `platoon-harness team told` shows filled in for each role"
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json", exclude_defaults=True)
    return f"`{json.dumps(value)}`"


def _models(hint: Any) -> Iterator[tuple[type[BaseModel], str, str | None]]:
    """Each model a field's type holds, with how it nests in a file, `.<name>` in a table by name or `[]` in a list,
    and the field that picks it from a union, if one does."""
    origin, args = get_origin(hint), get_args(hint)
    if origin is Annotated:
        picked = next((item.discriminator for item in args[1:] if getattr(item, "discriminator", None)), None)
        for model, nesting, discriminator in _models(args[0]):
            yield model, nesting, discriminator or picked
    elif origin is Mapping:
        for model, nesting, discriminator in _models(args[1]):
            yield model, ".<name>" + nesting, discriminator
    elif origin in (tuple, Sequence):
        for model, nesting, discriminator in _models(args[0]):
            yield model, "[]" + nesting, discriminator
    elif args:
        for arg in args:
            yield from _models(arg)
    elif isinstance(hint, type) and issubclass(hint, BaseModel):
        yield hint, "", None


def _tables(top: type[BaseModel]) -> dict[type[BaseModel], tuple[list[str], str | None]]:
    """Each model of the file, depth first from `top`, with where its tables go and the field that picks it, if any."""
    found: dict[type[BaseModel], tuple[list[str], str | None]] = {}

    def walk(model: type[BaseModel], path: str) -> None:
        for name, hint in get_type_hints(model, include_extras=True).items():
            if name not in model.model_fields or (model, name) in HIDDEN:
                continue
            for inner, nesting, discriminator in _models(hint):
                where = ".".join(filter(None, (path, name))) + nesting.replace("[]", "")
                where = f"[[{where}]]" if "[]" in nesting else f"[{where}]"
                if inner in found:
                    found[inner][0].append(where)
                else:
                    found[inner] = ([where], discriminator)
                    walk(inner, where.strip("[]"))

    found[top] = (["the top level"], None)
    walk(top, "")
    return found


def _section(model: type[BaseModel], places: list[str], discriminator: str | None) -> str:
    hints = get_type_hints(model, include_extras=True)
    required = {name for name, field in model.model_fields.items() if field.is_required()} | {discriminator}
    rows = [
        f"| `{name}` | {type_said(hints[name])} | {'required' if name in required else default_said(field.default)} |"
        for name, field in model.model_fields.items()
        if (model, name) not in HIDDEN
    ]
    where = ", ".join(place if place == "the top level" else f"`{place}`" for place in places)
    if discriminator:
        where += f", with `{discriminator} = {json.dumps(model.model_fields[discriminator].default)}`"
    return "\n".join(
        [
            f"## {model.__name__}",
            "",
            f"At {where}.",
            "",
            inspect.cleandoc(model.__doc__ or ""),
            "",
            "| Key | Type | Default |",
            "|---|---|---|",
            *rows,
        ]
    )


def _preset(name: str) -> str:
    preset = PRESETS[name]
    parameters = inspect.signature(preset).parameters.values()
    rows = [f"| `{item.name}` | {type_said(item.annotation)} | {default_said(item.default)} |" for item in parameters]
    lines = [f"### {name}", "", f"At `[topology.{name}]`.", "", inspect.cleandoc(preset.__doc__ or "")]
    return "\n".join([*lines, "", "| Key | Type | Default |", "|---|---|---|", *rows])


def reference() -> str:
    """The reference: every table a team file holds, its keys, their types and defaults, and every preset."""
    tables = _tables(Team)
    contents = "\n".join(f"- [`{model.__name__}`](#{model.__name__.lower()})" for model in tables)
    sections = "\n\n".join(_section(model, *found) for model, found in tables.items())
    presets = "\n\n".join(_preset(name) for name in PRESETS)
    return f"""# Team file reference

<!-- Made from the schema by `uv run python -m platoon_harness_cli.team_file > docs/reference/team-file.md`.
Do not edit: change the schema, and make it again. A test holds it to the schema. -->

A team file is TOML, and its tables are the models below, from `Team` at the top level down. `--team` names one on the
command line, `load_team` in Python, and the project file, `{PROJECT_FILE}`, has the same form.
[Architecture section 17](../architecture.md#17-extensions-and-configuration) says how the layers combine: the user's
config, the project file, a team file, `{ENVIRONMENT_VARIABLE}` and each `--set` line.
[Topologies](../how-to/topologies.md) has a worked team for each preset, and [Workspaces](../how-to/workspaces.md) what
each `workspace` promises. The sessions page of `platoon-harness web` edits the project file in place, keeping its
comments, and [Edit a team in the browser](../how-to/edit-a-team.md) says which keys it sets.

Each section is one model: where its tables go, what its docstring says, and a row for each key, with its type and its
default, `required` where it has none. A table refuses a key its model does not declare.

## Contents

{contents}
- [Presets](#presets)

{sections}

## Presets

A preset is a table under `[topology]` named after it, whose keys are its arguments, and a list of such tables uses it
more than once. Each makes a topology fragment, merged with the rest of `[topology]` by union.

{presets}
"""


if __name__ == "__main__":
    sys.stdout.write(reference())
