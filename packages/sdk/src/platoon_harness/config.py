"""Where a team comes from: layered configuration, credentials by name, and the reproducibility manifest."""

import os
import tomllib
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any, Literal, NoReturn, Self

from pydantic import GetCoreSchemaHandler, ValidationError
from pydantic_core import CoreSchema, core_schema

from platoon_harness.extensions import DRIVERS, EXTENSIONS, Component, discover, find
from platoon_harness.schema import ConfigError, Model, Problem, problems_in
from platoon_harness.team import Team
from platoon_harness.version import __version__

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
    __reduce__ = _refuse
    __getstate__ = _refuse

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


def _needing_trust(team: Team, merged: Mapping[str, Any], files: Sequence[Mapping[str, Any]]) -> Iterator[Problem]:
    """What only explicit trust may take from a project or team file: code to run, and credentials to pass on."""

    def from_a_file(*path: str) -> bool:
        value = _dig(merged, *path)
        return value is not None and any(_dig(file, *path) == value for file in files)

    for name, role in team.roles.items():
        if from_a_file("roles", name, "harness", "command"):
            yield Problem(f"roles.{name}.harness", "a command in a project file needs explicit trust")
        if isinstance(role.harness, str) and ":" in role.harness and from_a_file("roles", name, "harness"):
            yield Problem(f"roles.{name}.harness", "a `module:attr` in a project file needs explicit trust")
    if any(":" in reference for reference in team.extensions) and from_a_file("extensions"):
        yield Problem("extensions", "a `module:attr` in a project file needs explicit trust")
    for name in team.auth:
        if from_a_file("auth", name):
            yield Problem(f"auth.{name}", "an auth profile in a project file needs explicit trust")


def load_team(
    path: Path | None = None,
    *,
    cwd: Path | None = None,
    environ: Mapping[str, str] = os.environ,
    sets: Sequence[str] = (),
    trust_project: bool = False,
) -> Team:
    """Layer config, low to high: defaults, user, project, team file, environment, command line.

    The environment and each of `sets` are TOML text, such as `budget.usd = 5`. A project is untrusted, so what would
    run code or pass a credential is refused from a project or team file without `trust_project`. Every problem is
    reported at once.
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
    for index, text in enumerate(sets, 1):
        merged = merge(merged, _parse(text, f"--set line {index}", problems))

    try:
        team = Team.model_validate(merged)
    except ValidationError as error:
        raise ConfigError([*problems, *problems_in(error, Team)]) from None
    if not trust_project:
        problems.extend(_needing_trust(team, merged, (project, team_file)))
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


def _strings(value: Any) -> Iterator[str]:
    """Every string in plain data, keys too."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, Mapping):
        for key, item in value.items():
            yield key
            yield from _strings(item)
    elif isinstance(value, list | tuple):
        for item in value:
            yield from _strings(item)


def sanitized(team: Team, environ: Mapping[str, str] = os.environ) -> str:
    """The resolved form, refused if it holds the value of a variable an auth profile names. It looks at the strings
    themselves, since rendering escapes them, and an empty value holds no secret."""
    held = list(_strings(team.canonical()))
    names = sorted({name for profile in team.auth.values() for name in profile.env})
    leaks = [
        Problem("auth", f"the value of `{name}` is in this config")
        for name in names
        if (value := environ.get(name)) and any(value in text for text in held)
    ]
    if leaks:
        raise ConfigError(leaks)
    return team.show(resolved=True)


class Manifest(Model):
    """What reproduces a session, and all a runtime needs to take one up: `team` is the sanitized resolved form, which
    reloads alone, `human` the principal who started it, `approvals` a policy stated over every role's own, and `cwd`
    where a shared workspace is."""

    team: str
    topology_hash: str
    components: tuple[Component, ...]
    human: str = "human:you"
    approvals: Literal["ask", "deny", "allow"] | None = None
    cwd: str = "."
    sdk_version: str = __version__
    team_schema: int = TEAM_SCHEMA
    wire_protocol: int = WIRE_PROTOCOL

    @classmethod
    def of(cls, team: Team, environ: Mapping[str, str] = os.environ, **started: Any) -> Self:
        """The manifest of a resolved team, with versions from metadata. Nothing is imported."""
        harnesses = sorted({role.driver for role in team.roles.values()})
        components = (
            *(find(DRIVERS, name) for name in harnesses),
            *(find(EXTENSIONS, name) for name in team.extensions),
        )
        return cls(team=sanitized(team, environ), topology_hash=team.topology.hash, components=components, **started)

    def changed(self) -> tuple[str, ...]:
        """What is installed now that differs from what was recorded, in words. Nothing is imported. A resume is
        labelled with this and not refused, since a session survives an upgrade."""
        installed = {(component.group, component.name): component.version for component in discover()}
        changes = [] if self.sdk_version == __version__ else [f"the SDK {self.sdk_version} is now {__version__}"]
        for component in self.components:
            now = installed.get((component.group, component.name))
            if component.version is not None and now != component.version:
                changes.append(f"{component.name} {component.version} is now {now or 'gone'}")
        return tuple(changes)
