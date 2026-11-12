"""Installed components: found from metadata alone, imported only by exact name, active only when named."""

import re
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from importlib import metadata
from typing import Any

from platoon_harness.kernel import Extension
from platoon_harness.schema import ConfigError, Problem, nearest
from platoon_harness.version import __version__

DRIVERS = "platoon_harness.drivers"
EXTENSIONS = "platoon_harness.extensions"

_SDK = "platoon-harness"
_LABELS = {DRIVERS: "driver", EXTENSIONS: "extension"}
_REQUIREMENT = re.compile(r"\s*([A-Za-z0-9][\w.-]*)\s*(?:\[[^]]*])?\s*\(?([^;)]*)\)?\s*(?:;(.*))?")
_CLAUSE = re.compile(r"(~=|==|!=|<=|>=|<|>)\s*(\d+(?:\.\d+)*)(\.\*)?")

__all__ = [
    "DRIVERS",
    "EXTENSIONS",
    "Component",
    "Installed",
    "NotInstalled",
    "check_installed",
    "discover",
    "find",
    "load",
]


class NotInstalled(ConfigError, KeyError):
    """No component has this name, which is also why `Installed` has no such key."""


@dataclass(frozen=True)
class Component:
    """An installed entry point as metadata states it. A `module:attr` reference has no distribution."""

    group: str
    name: str
    value: str
    distribution: str | None = None
    version: str | None = None
    requires: tuple[str, ...] = ()


def _normal(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _sdk_requirements(lines: Sequence[str] | None) -> tuple[str, ...]:
    """The specifier sets a distribution puts on the SDK. An extra's requirement binds only that extra."""
    matches = (_REQUIREMENT.fullmatch(line) for line in lines or ())
    return tuple(
        match[2].strip() for match in matches if match and _normal(match[1]) == _SDK and "extra" not in (match[3] or "")
    )


def discover() -> tuple[Component, ...]:
    """Every component the environment declares, read from metadata. Nothing is imported."""
    found = {
        Component(
            point.group,
            point.name,
            point.value,
            distribution.name,
            distribution.version,
            _sdk_requirements(distribution.requires),
        )
        for distribution in metadata.distributions()
        for point in distribution.entry_points
        if point.group in _LABELS
    }
    return tuple(sorted(found, key=lambda component: (component.group, component.name, str(component.distribution))))


def _release(version: str) -> tuple[int, ...] | None:
    match = re.match(r"\d+(?:\.\d+)*", version)
    return tuple(map(int, match[0].split("."))) if match else None


def _holds(operator: str, release: tuple[int, ...], target: tuple[int, ...], wildcard: bool) -> bool:
    length = max(len(release), len(target))
    left, right = (part + (0,) * (length - len(part)) for part in (release, target))
    prefix = release[: len(target)] == target
    match operator:
        case "==":
            return prefix if wildcard else left == right
        case "!=":
            return not prefix if wildcard else left != right
        case "<=":
            return left <= right
        case ">=":
            return left >= right
        case "<":
            return left < right
        case ">":
            return left > right
        case _:
            return left >= right and release[: len(target) - 1] == target[:-1]


def _admits(specifiers: str, version: str) -> bool | None:
    """Whether a version meets a specifier set, by release number. None when either cannot be read."""
    release = _release(version)
    for clause in filter(None, map(str.strip, specifiers.split(","))):
        match = _CLAUSE.fullmatch(clause)
        if match is None or release is None:
            return None
        if not _holds(match[1], release, tuple(map(int, match[2].split("."))), bool(match[3])):
            return False
    return True


def _incompatible(component: Component) -> Problem | None:
    """Why a component cannot run on this SDK, from metadata alone."""
    where = f"{_LABELS[component.group]}s.{component.name}"
    for specifiers in component.requires:
        admitted = _admits(specifiers, __version__)
        if admitted is None:
            return Problem(where, f"{component.distribution} states an unreadable SDK requirement `{specifiers}`")
        if not admitted:
            what = f"{component.distribution} needs {_SDK}{specifiers}, and this is {__version__}"
            return Problem(where, what)
    return None


def check_installed() -> tuple[Problem, ...]:
    """Duplicates and incompatible SDK requirements across everything installed, before any import."""
    components = discover()
    problems = [problem for component in components if (problem := _incompatible(component))]
    for group, label in _LABELS.items():
        names = [component.name for component in components if component.group == group]
        for name in sorted({name for name in names if names.count(name) > 1}):
            sources = _sources(
                component for component in components if (component.group, component.name) == (group, name)
            )
            problems.append(Problem(f"{label}s.{name}", f"defined by more than one distribution: {sources}"))
    return tuple(problems)


def _sources(components: Iterable[Component]) -> str:
    return ", ".join(f"{component.distribution} {component.version}" for component in components)


def find(group: str, reference: str) -> Component:
    """Resolve `name`, `name@version` or `module:attr` from metadata. Nothing is imported."""
    if ":" in reference:
        return Component(group, reference, reference)
    label = _LABELS[group]
    name, _, version = reference.partition("@")
    components = discover()
    same_group = [component for component in components if component.group == group]
    named = [component for component in same_group if component.name == name]
    matching = [component for component in named if _version_matches(component.version, version)]
    where = f"{label}s.{name}"
    if not matching:
        registered = sorted({f"{item.name} {item.version}" if named else item.name for item in named or same_group})
        installed = sorted({f"{item.distribution} {item.version}" for item in components})
        hint = nearest(name, {component.name for component in same_group})
        lists = f"Registered: {', '.join(registered) or 'none'}. Installed: {', '.join(installed) or 'none'}."
        raise NotInstalled([Problem(where, f"no {label} `{reference}`.{hint} {lists}")])
    if len(matching) > 1:
        what = f"defined by more than one distribution: {_sources(matching)}. Pin one with `{name}@version`"
        raise ConfigError([Problem(where, what)])
    component = matching[0]
    if problem := _incompatible(component):
        raise ConfigError([problem])
    return component


def _version_matches(version: str | None, wanted: str) -> bool:
    return not wanted or version == wanted or (version or "").startswith(f"{wanted}.")


def load(group: str, reference: str) -> Any:
    """Import one component by exact reference, and nothing else."""
    component = find(group, reference)
    try:
        loaded = metadata.EntryPoint(component.name, component.value, group).load()
    except Exception as error:
        where = f"{_LABELS[group]}s.{component.name}"
        raise ConfigError([Problem(where, f"could not import `{component.value}`: {error}")]) from error
    if group == EXTENSIONS and not isinstance(loaded, Extension):
        where = f"extensions.{component.name}"
        raise ConfigError([Problem(where, f"`{component.value}` is not an Extension")])
    return loaded


class Installed(Mapping[str, Any]):
    """One group's components. Listing reads metadata; indexing imports that one component and no other."""

    def __init__(self, group: str = EXTENSIONS) -> None:
        self.group = group

    def __getitem__(self, reference: str) -> Any:
        return load(self.group, reference)

    def __iter__(self) -> Iterator[str]:
        return iter(sorted({component.name for component in discover() if component.group == self.group}))

    def __len__(self) -> int:
        return sum(1 for _ in self)
