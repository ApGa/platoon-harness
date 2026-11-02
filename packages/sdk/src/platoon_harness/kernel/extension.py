"""Extensions: what a kernel loads, core and third party alike."""

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from typing import Any

from .daemon import Daemon
from .model import Refused
from .naming import check_event_type, check_op_name
from .op import Op
from .view import View, tables_of


@dataclass(frozen=True)
class Extension:
    """A named set of ops, views, daemons and topology presets. The name is the ops' namespace."""

    name: str
    ops: Sequence[Op] = ()
    views: Sequence[type[View]] = ()
    daemons: Sequence[Daemon] = ()
    presets: Sequence[Callable[..., Any]] = ()


@dataclass(frozen=True)
class Loaded:
    """Several extensions with every collision and naming fault refused."""

    ops: dict[str, Op]
    views: tuple[type[View], ...]
    daemons: tuple[Daemon, ...]


def load(extensions: Iterable[Extension]) -> Loaded:
    """Check extensions against each other and the naming law."""
    owners = {("table", "v_folds"): "the kernel"}

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
            for table in tables_of(view):
                claim("table", table, owner)
            for event_type in view._folds:
                if event_type != "*":
                    check_event_type(event_type)
            views.append(view)
        for daemon in extension.daemons:
            claim("daemon", daemon.name, owner)
            daemons.append(daemon)
    return Loaded(ops, tuple(views), tuple(daemons))
