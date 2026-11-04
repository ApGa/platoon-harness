"""The public names of the runtime and the facade are written down, and a runtime keeps nothing global."""

import ast
from pathlib import Path

import pytest

import platoon_harness
from platoon_harness import runtime, session
from platoon_harness.runtime import authority, control, git, host, looks, opening, paths, recovery, workspaces

MODULES = {
    "session": session,
    "runtime": runtime,
    "runtime.authority": authority,
    "runtime.control": control,
    "runtime.git": git,
    "runtime.host": host,
    "runtime.looks": looks,
    "runtime.opening": opening,
    "runtime.paths": paths,
    "runtime.recovery": recovery,
    "runtime.workspaces": workspaces,
}
RECORDED = (Path(__file__).parents[2] / "public_api.txt").read_text().split()
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
