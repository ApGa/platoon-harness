"""The public names of the runtime and the facade are written down, and a runtime keeps nothing global."""

import ast
import importlib
import inspect
from pathlib import Path
from typing import Any, get_args

import pytest

import platoon_harness
from platoon_harness import annotations, bwrap, credit, runtime, session
from platoon_harness.runtime import (
    authority,
    control,
    diffs,
    git,
    host,
    isolation,
    looks,
    opening,
    paths,
    recovery,
    workspaces,
)

MODULES = {
    "annotations": annotations,
    "bwrap": bwrap,
    "credit": credit,
    "session": session,
    "runtime": runtime,
    "runtime.authority": authority,
    "runtime.control": control,
    "runtime.diffs": diffs,
    "runtime.git": git,
    "runtime.host": host,
    "runtime.isolation": isolation,
    "runtime.looks": looks,
    "runtime.opening": opening,
    "runtime.paths": paths,
    "runtime.recovery": recovery,
    "runtime.workspaces": workspaces,
}
WRITTEN = (Path(__file__).parents[2] / "public_api.txt").read_text().split()
RECORDED = [line.partition("(")[0].partition("[")[0] for line in WRITTEN]
RUNTIME = Path(runtime.__file__).parent


@pytest.mark.parametrize("name", MODULES)
def test_public_names_match_the_list(name):
    prefix = f"platoon_harness.{name}."
    listed = {line.removeprefix(prefix) for line in RECORDED if line.startswith(prefix)}

    assert {line for line in listed if "." not in line} == set(MODULES[name].__all__)


def test_the_top_of_the_package_is_written_down():
    listed = {line.removeprefix("platoon_harness.") for line in RECORDED}

    assert set(platoon_harness.__all__) - {"__version__"} <= listed


def test_signals_are_handled_in_the_entry_point_and_nowhere_else():
    def handles_signals(path: Path) -> bool:
        names = {node.attr for node in ast.walk(ast.parse(path.read_text())) if isinstance(node, ast.Attribute)}
        return bool(names & {"add_signal_handler", "signal"})

    assert [path.name for path in RUNTIME.rglob("*.py") if handles_signals(path)] == ["__main__.py"]


def test_a_runtime_keeps_nothing_at_module_level_that_could_change():
    def mutable(node: ast.stmt) -> bool:
        named_all = isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == "__all__"
        value = node.value if isinstance(node, ast.Assign | ast.AnnAssign) else None
        return isinstance(value, ast.List | ast.Dict | ast.Set) and not named_all

    for path in RUNTIME.rglob("*.py"):
        assert not [node.lineno for node in ast.parse(path.read_text()).body if mutable(node)], path.name


def resolved(dotted: str) -> Any:
    """What a dotted name names: the longest module it begins with, then each attribute, where a model's field is the
    type it holds."""
    parts = dotted.split(".")
    for cut in range(len(parts), 0, -1):
        try:
            found = importlib.import_module(".".join(parts[:cut]))
        except ImportError:
            continue
        for part in parts[cut:]:
            fields = getattr(found, "model_fields", {})
            found = fields[part].annotation if part in fields else getattr(found, part)
        return found
    raise AssertionError(f"{dotted} names nothing")


@pytest.mark.parametrize("line", WRITTEN)
def test_every_recorded_name_names_something(line):
    resolved(line.partition("(")[0].partition("[")[0])


def signature_of(thing: Any) -> str:
    """A callable's parameters as the list writes them: each name, `*` before the first keyword-only one, and neither
    `self` nor `cls`."""
    shown, starred = [], False
    for parameter in inspect.signature(thing).parameters.values():
        if parameter.name in ("self", "cls"):
            continue
        if parameter.kind is parameter.VAR_POSITIONAL:
            shown.append(f"*{parameter.name}")
            starred = True
        elif parameter.kind is parameter.VAR_KEYWORD:
            shown.append(f"**{parameter.name}")
        elif parameter.kind is parameter.KEYWORD_ONLY and not starred:
            shown += ["*", parameter.name]
            starred = True
        else:
            shown.append(parameter.name)
    return f"({','.join(shown)})"


@pytest.mark.parametrize("line", [line for line in WRITTEN if line.endswith((")", "]"))])
def test_every_recorded_signature_is_the_one_it_has(line):
    """A member, as `name(parameters)`, and a closed set of words, as `name[words]`, are written down whole, so a
    change to either changes the list."""
    if line.endswith("]"):
        name, _, words = line[:-1].partition("[")
        assert ",".join(get_args(resolved(name))) == words
    else:
        name, _, _ = line.partition("(")
        assert f"{name}{signature_of(resolved(name))}" == line
