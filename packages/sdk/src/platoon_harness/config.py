"""Where a team comes from: layered configuration, credentials by name, and the reproducibility manifest."""

import os
import tomllib
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, NoReturn, Self

from pydantic import GetCoreSchemaHandler, ValidationError
from pydantic_core import CoreSchema, core_schema

from platoon_harness import __version__
from platoon_harness.extensions import DRIVERS, EXTENSIONS, Component, find
from platoon_harness.schema import ConfigError, Model, Problem, problems_in
from platoon_harness.team import Command, Team

ENVIRONMENT_VARIABLE = "PLATOON_HARNESS_CONFIG"
PROJECT_FILE = "platoon-harness.toml"
TEAM_SCHEMA = 1
WIRE_PROTOCOL = 1

__all__ = [
    "ENVIRONMENT_VARIABLE",
    "PROJECT_FILE",
    "TEAM_SCHEMA",
    "WIRE_PROTOCOL",
    "Manifest",
    "Secret",
    "credentials",
    "load_team",
    "merge",
    "sanitized",
]


class Secret:
    """A credential value. It prints as a mask, leaves only through `reveal`, and refuses every serialization."""

    __slots__ = ("_value",)

    def __init__(self, value: str) -> None:
        self._value = value

    def reveal(self) -> str:
        return self._value

    def __repr__(self) -> str:
        return "Secret(***)"

    def _refuse(self, *_: Any) -> NoReturn:
        raise TypeError("a Secret refuses serialization")

    __reduce_ex__ = _refuse

    @classmethod
    def __get_pydantic_core_schema__(cls, source: Any, handler: GetCoreSchemaHandler) -> CoreSchema:
        return core_schema.is_instance_schema(
            cls, serialization=core_schema.plain_serializer_function_ser_schema(cls._refuse)
        )


def merge(low: Mapping[str, Any], high: Mapping[str, Any]) -> dict[str, Any]:
    """Overlay `high` on `low`. Mappings merge and everything else, lists included, is replaced."""
    merged = dict(low)
    for key, value in high.items():
        below = merged.get(key)
        merged[key] = merge(below, value) if isinstance(below, Mapping) and isinstance(value, Mapping) else value
    return merged


def _parse(text: str, source: str, problems: list[Problem]) -> dict[str, Any]:
    try:
        return tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        problems.append(Problem(source, f"not TOML: {error}"))
        return {}


def _file(path: Path, problems: list[Problem], *, required: bool = False) -> dict[str, Any]:
    try:
        return _parse(path.read_text(), str(path), problems)
    except FileNotFoundError:
        problems += [Problem(str(path), "no such file")] if required else []
    except (OSError, UnicodeDecodeError) as error:
        problems.append(Problem(str(path), f"unreadable: {error}"))
    return {}


def _dig(data: Any, *path: str) -> Any:
    for key in path:
        data = data.get(key) if isinstance(data, Mapping) else None
    return data


def load_team(
    path: Path | None = None,
    *,
    cwd: Path | None = None,
    environ: Mapping[str, str] = os.environ,
    sets: Sequence[str] = (),
    trust_commands: bool = False,
) -> Team:
    """Layer config, low to high: defaults, user, project, team file, environment, command line.

    The environment and each of `sets` are TOML text, such as `budget.usd = 5`. A `command` harness in a project
    file is refused without `trust_commands`, since a project is untrusted. Every problem is reported at once.
    """
    problems: list[Problem] = []
    config_home = Path(environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    user = _file(config_home / "platoon-harness" / "config.toml", problems)
    project = _file((cwd or Path.cwd()) / PROJECT_FILE, problems)
    team_file = _file(path, problems, required=True) if path else {}
    environment = _parse(environ.get(ENVIRONMENT_VARIABLE, ""), ENVIRONMENT_VARIABLE, problems)

    merged: dict[str, Any] = {}
    for layer in (user, project, team_file, environment):
        merged = merge(merged, layer)
    for text in sets:
        merged = merge(merged, _parse(text, f"--set {text}", problems))

    try:
        team = Team.model_validate(merged)
    except ValidationError as error:
        raise ConfigError([*problems, *problems_in(error, Team)]) from error
    if not trust_commands:
        for name, role in team.roles.items():
            untrusted = [_dig(layer, "roles", name, "harness") for layer in (project, team_file)]
            if isinstance(role.harness, Command) and _dig(merged, "roles", name, "harness") in untrusted:
                problems.append(Problem(f"roles.{name}.harness", "a command in a project file needs explicit trust"))
    if problems:
        raise ConfigError(problems)
    return team


def credentials(team: Team, role: str, environ: Mapping[str, str] = os.environ) -> dict[str, Secret]:
    """The values a role's auth profile names, read from `environ`. A missing variable is a problem, not a blank."""
    profile = team.roles[role].auth
    names = team.auth[profile].env if profile else ()
    missing = [Problem(f"auth.{profile}.env", f"`{name}` is not set") for name in names if name not in environ]
    if missing:
        raise ConfigError(missing)
    return {name: Secret(environ[name]) for name in names}


def sanitized(team: Team, environ: Mapping[str, str] = os.environ) -> str:
    """The resolved form, refused if it holds the value of a variable an auth profile names."""
    text = team.show(resolved=True)
    names = sorted({name for profile in team.auth.values() for name in profile.env})
    leaks = [
        Problem("auth", f"the value of `{name}` is in this config") for name in names if environ.get(name, "\0") in text
    ]
    if leaks:
        raise ConfigError(leaks)
    return text


class Manifest(Model):
    """What reproduces a session. `team` is the sanitized resolved form, which reloads alone."""

    team: str
    topology_hash: str
    components: tuple[Component, ...]
    sdk_version: str = __version__
    team_schema: int = TEAM_SCHEMA
    wire_protocol: int = WIRE_PROTOCOL

    @classmethod
    def of(cls, team: Team, environ: Mapping[str, str] = os.environ) -> Self:
        """The manifest of a resolved team, with versions from metadata. Nothing is imported."""
        harnesses = sorted({role.driver for role in team.roles.values()})
        components = (
            *(find(DRIVERS, name) for name in harnesses),
            *(find(EXTENSIONS, name) for name in team.extensions),
        )
        return cls(team=sanitized(team, environ), topology_hash=team.topology.hash, components=components)
