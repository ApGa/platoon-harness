"""The SDK stands alone."""

import ast
import importlib
import subprocess
import sys
from pathlib import Path

import pytest

from platoon_harness.testing.extension import private_reaches

ROOT = Path(__file__).parents[3]
SDK = ROOT / "packages" / "sdk" / "src" / "platoon_harness"
FIRST_PARTY = {path.name for path in ROOT.glob("extensions/*/src/*") if path.is_dir()}
"""The import package of each first-party extension, a distribution of its own under `extensions/`."""
ACP = ROOT / "extensions" / "acp" / "src" / "platoon_harness_acp"
ALLOWED = set(sys.stdlib_module_names) | {"pydantic", "pydantic_core", "platoon_harness"}
OPENHANDS = {"openhands", "litellm"}
"""What the SDK's `openhands` extra brings, which only the OpenHands worker loads, in its own process."""
WORKER = SDK / "drivers" / "openhands" / "agent.py"


def roots_of(path: Path) -> set[str]:
    roots: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            roots |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            roots.add((node.module or "").split(".")[0])
    return roots


@pytest.mark.parametrize("path", sorted(SDK.rglob("*.py")), ids=lambda path: str(path.relative_to(SDK)))
def test_the_sdk_imports_nothing_but_the_standard_library_and_pydantic(path):
    """But for the OpenHands worker's own module, which imports what the `openhands` extra brings."""
    assert roots_of(path) <= ALLOWED | (OPENHANDS if path == WORKER else set())


def test_the_sdk_never_imports_a_first_party_extension():
    """Nor does the command line: an extension is installed beside them, and found by its entry point alone."""
    ours = sorted(ROOT.glob("packages/*/src/**/*.py"))

    assert "platoon_harness_acp" in FIRST_PARTY
    assert [path.relative_to(ROOT) for path in ours if roots_of(path) & FIRST_PARTY] == []


@pytest.mark.parametrize("path", sorted(ACP.rglob("*.py")), ids=lambda path: str(path.relative_to(ACP)))
def test_the_acp_extension_uses_only_public_names(path):
    """As any third party's driver would: the standard library, pydantic and the SDK, and of the SDK only the names a
    module publishes in `__all__`, reaching no underscored name on anything."""
    tree = ast.parse(path.read_text())
    imported = [node for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.level == 0]
    modules = [alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names]

    assert roots_of(path) <= ALLOWED | {"platoon_harness_acp"}
    assert private_reaches(tree) == []
    for module in [*modules, *(node.module or "" for node in imported)]:
        assert not any(part.startswith("_") for part in module.split(".")), module
    for node in imported:
        if (node.module or "").split(".")[0] == "platoon_harness":
            published = set(importlib.import_module(node.module or "").__all__)
            assert {alias.name for alias in node.names} <= published, node.module


def test_only_the_openhands_worker_imports_openhands():
    ours = (*ROOT.glob("packages/*/src/**/*.py"), *ROOT.glob("tests/**/*.py"))

    assert [path for path in ours if roots_of(path) & OPENHANDS] == [WORKER]


LOADED = """
import importlib
import pkgutil
import sys

import platoon_harness
import platoon_harness_cli
from platoon_harness.extensions import DRIVERS, Installed, load

for package in (platoon_harness, platoon_harness_cli):
    for module in pkgutil.walk_packages(package.__path__, f"{package.__name__}."):
        if module.name != sys.argv[1] and not module.name.endswith(".__main__"):
            importlib.import_module(module.name)
for name in Installed(DRIVERS):
    load(DRIVERS, name)
print(sorted(name for name in sys.modules if any(name == root or name.startswith(f"{root}.") for root in sys.argv[2:])))
"""
"""A program for a fresh interpreter: which modules of the roots it is given are loaded once every module of the SDK
and the command line is, but the one it is given first, and every driver class."""


def test_nothing_but_the_openhands_worker_loads_openhands():
    """Importing the SDK, any module the runtime or a driver class imports, or the command line loads no OpenHands."""
    worker = "platoon_harness.drivers.openhands.agent"
    command = [sys.executable, "-P", "-c", LOADED, worker, *OPENHANDS]
    done = subprocess.run(command, capture_output=True, text=True, timeout=120, check=False)

    assert done.returncode == 0, done.stderr
    assert done.stdout.split() == ["[]"]


def test_nothing_but_a_team_that_names_it_loads_bwrap():
    """The `bwrap` extension ships in the SDK, and only `Installed()["bwrap"]`, for a team that names it, imports it."""
    command = [sys.executable, "-P", "-c", LOADED, "platoon_harness.bwrap", "platoon_harness.bwrap"]
    done = subprocess.run(command, capture_output=True, text=True, timeout=120, check=False)

    assert done.returncode == 0, done.stderr
    assert done.stdout.split() == ["[]"]
