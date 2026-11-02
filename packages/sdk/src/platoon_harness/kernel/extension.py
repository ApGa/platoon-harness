"""Extensions: what a kernel loads, core and third party alike."""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from .daemon import Daemon
from .model import Refused
from .naming import check_event_type, check_op_name
from .op import Op
from .view import View, tables_of


@dataclass(frozen=True)
class Extension:
    """A named set of ops, views, daemons and components. The name is the ops' namespace."""

    name: str
    ops: Sequence[Op] = ()
    views: Sequence[type[View]] = ()
    daemons: Sequence[Daemon] = ()
    presets: Mapping[str, Any] = field(default_factory=dict)
    workspaces: Mapping[str, Any] = field(default_factory=dict)
    exporters: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Loaded:
    """Several extensions with every collision and naming fault refused."""

    extensions: tuple[Extension, ...]
    ops: dict[str, Op]
    views: tuple[type[View], ...]
    daemons: tuple[Daemon, ...]


def load(extensions: Iterable[Extension]) -> Loaded:
    """Check extensions against each other and the naming law."""
    extensions = tuple(extensions)
    owners: dict[tuple[str, str], str] = {}

    def claim(kind: str, name: str, owner: str) -> None:
        if (kind, name) in owners:
            raise Refused("conflict", f"{kind} {name} is defined by both {owners[kind, name]} and {owner}")
        owners[kind, name] = owner

    ops: dict[str, Op] = {}
    views: list[type[View]] = []
    daemons: list[Daemon] = []
    for extension in extensions:
        owner = extension.name
        claim("extension", owner, owner)
        for operation in extension.ops:
            check_op_name(operation.name, owner)
            claim("op", operation.name, owner)
            ops[operation.name] = operation
        for view in extension.views:
            claim("view", view.name, owner)
            tables_of(view)
            for event_type in view._folds:
                if event_type != "*":
                    check_event_type(event_type)
            views.append(view)
        for daemon in extension.daemons:
            claim("daemon", daemon.name, owner)
            daemons.append(daemon)
        for kind in ("presets", "workspaces", "exporters"):
            for name in getattr(extension, kind):
                claim(kind, name, owner)
    return Loaded(extensions, ops, tuple(views), tuple(daemons))
