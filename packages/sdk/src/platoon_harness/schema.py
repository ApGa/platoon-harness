"""What all configuration shares: frozen models, problems that name their place, and a TOML writer."""

import difflib
import json
import re
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from typing import Annotated, Any, Literal, get_args

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StrictInt, StringConstraints, ValidationError

from platoon_harness.kernel import NAME

_UNITS = {"d": 86400, "h": 3600, "m": 60, "s": 1}

__all__ = [
    "ConfigError",
    "Duration",
    "Model",
    "Name",
    "Positive",
    "Problem",
    "Sorted",
    "dumps",
    "nearest",
    "problems_in",
    "seconds",
]

Name = Annotated[str, StringConstraints(pattern=f"^{NAME}$")]
Positive = Annotated[StrictInt, Field(gt=0)]


def _sorted(mapping: Mapping[str, Any]) -> dict[str, Any]:
    return dict(sorted(mapping.items()))


def _duration(text: str) -> str:
    match = re.fullmatch(r"([1-9]\d*)([dhms])", text)
    if match is None:
        raise ValueError("a duration looks like 90s, 30m or 2h")
    seconds = int(match[1]) * _UNITS[match[2]]
    unit = next(unit for unit, size in _UNITS.items() if seconds % size == 0)
    return f"{seconds // _UNITS[unit]}{unit}"


def seconds(span: str | float) -> float:
    """A duration as seconds. A number already is one."""
    if isinstance(span, str):
        _duration(span)
        return float(int(span[:-1]) * _UNITS[span[-1]])
    return float(span)


Sorted = AfterValidator(_sorted)
"""Keeps a mapping in key order, so that equal configurations print alike."""

Duration = Annotated[str, AfterValidator(_duration)]
"""A span such as `30m`, held in its largest exact unit, so `60m` and `1h` are one value."""


class Model(BaseModel):
    """A configuration object: immutable, and refusing keys it does not declare. Input stays out of an error, even a
    chained one, since a mistaken key may hold a secret."""

    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

    def canonical(self) -> dict[str, Any]:
        """Plain data with defaults left out, so a new default never disturbs an old form."""
        return self.model_dump(mode="json", exclude_defaults=True)


@dataclass(frozen=True)
class Problem:
    """One thing wrong, at a dotted path into the configuration."""

    where: str
    what: str
    level: Literal["error", "warning"] = "error"

    def __str__(self) -> str:
        return f"{self.where}: {self.what}"


class ConfigError(ValueError):
    """Configuration that cannot be used, with every problem found."""

    def __init__(self, problems: Collection[Problem]) -> None:
        super().__init__(*problems)
        self.problems = tuple(problems)

    def __str__(self) -> str:
        return "\n".join(map(str, self.problems))


def nearest(name: str, known: Collection[str]) -> str:
    """A did-you-mean clause, or nothing when no known name is close."""
    close = difflib.get_close_matches(name, sorted(known), n=1)
    return f" Did you mean `{close[0]}`?" if close else ""


def _models_in(annotation: Any) -> set[type[BaseModel]]:
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return {annotation}
    return {model for argument in get_args(annotation) for model in _models_in(argument)}


def _keys_at(model: type[BaseModel], path: Sequence[Any]) -> set[str]:
    """The field names a model tree allows at `path`. A step that is no field, such as a role's name, stays put."""
    models = {model}
    for step in path:
        fields = [found.model_fields[step] for found in models if step in found.model_fields]
        models = {inner for field in fields for inner in _models_in(field.annotation)} if fields else models
    return {key for found in models for key in found.model_fields}


def problems_in(
    error: ValidationError, model: type[BaseModel] | None = None, *, where: str = "", keys: Collection[str] = ()
) -> list[Problem]:
    """A validation error as problems. Input values stay out, since a mistaken key may hold a secret."""
    problems: list[Problem] = []
    for detail in error.errors(include_url=False, include_input=False):
        nested = detail.get("ctx", {}).get("error")
        if isinstance(nested, ConfigError):
            problems.extend(nested.problems)
            continue
        path = ".".join(filter(None, (where, *map(str, detail["loc"]))))
        if detail["type"] in ("extra_forbidden", "unexpected_keyword_argument"):
            key = str(detail["loc"][-1])
            known = _keys_at(model, detail["loc"][:-1]) if model else keys
            what = f"`{key}` is not a key here.{nearest(key, known)}"
        else:
            what = detail["msg"].removeprefix("Value error, ")
        problems.append(Problem(path, what))
    return problems


def dumps(data: Mapping[str, Any]) -> str:
    """TOML for nested mappings of strings, numbers, booleans and lists. A mapping of lists stays on one line."""
    lines: list[str] = []
    _table(lines, (), data)
    return "\n".join(lines).strip() + "\n"


def _is_table(value: Any) -> bool:
    return isinstance(value, Mapping) and not all(isinstance(item, list) for item in value.values())


def _table(lines: list[str], path: tuple[str, ...], table: Mapping[str, Any]) -> None:
    values = {key: value for key, value in table.items() if not _is_table(value)}
    if path and values:
        lines += ["", f"[{'.'.join(map(_key, path))}]"]
    lines += [f"{_key(key)} = {_value(value)}" for key, value in values.items()]
    for key, value in table.items():
        if _is_table(value):
            _table(lines, (*path, key), value)


def _key(key: str) -> str:
    return key if re.fullmatch(r"[A-Za-z0-9_-]+", key) else _value(key)


def _value(value: Any) -> str:
    match value:
        case bool():
            return "true" if value else "false"
        case str():
            return json.dumps(value, ensure_ascii=False).replace("\x7f", "\\u007f")
        case Mapping():
            items = ", ".join(f"{_key(key)} = {_value(item)}" for key, item in value.items())
            return f"{{ {items} }}" if items else "{}"
        case list():
            return f"[{', '.join(map(_value, value))}]"
        case _:
            return repr(value)
