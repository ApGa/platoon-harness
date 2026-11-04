"""The SDK stands alone, and what is public stays free of anything local or secret."""

import ast
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[3]
SDK = ROOT / "packages" / "sdk" / "src" / "platoon_harness"
ALLOWED = set(sys.stdlib_module_names) | {"pydantic", "pydantic_core", "platoon_harness"}
OPENHANDS = {"openhands", "litellm"}
"""What the SDK's `openhands` extra brings, which only the OpenHands worker loads, in its own process."""
WORKER = SDK / "drivers" / "openhands" / "agent.py"
PUBLIC = (
    *ROOT.glob("packages/*/src/**/*.py"),
    *ROOT.glob("*.md"),
    *ROOT.glob("packages/*/README.md"),
    *(path for path in (ROOT / "docs").rglob("*") if path.is_file()),
    *(ROOT / "tests" / "conformance").glob("*.py"),
)
LOCAL = re.compile(
    r"(?<![\w.-])/(home|groups|Users)/[A-Za-z]|/gs/|gai\d{5}|aci\d{5}|\bR9920261300\b|(?i:\babci\b)"
    r"|ANTHROPIC_API_KEY=sk-|sk-ant-"
    r"|[\w.+-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*\.(?!invalid\b)[A-Za-z]{2,}\b"
)
"""An absolute path under a home or a group, this cluster's names, a key, or an email address but one under `.invalid`,
which RFC 2606 keeps from ever naming an account."""


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
print(sorted(name for name in sys.modules if name.partition(".")[0] in sys.argv[2:]))
"""
"""A program for a fresh interpreter: what of OpenHands is loaded once every module of the SDK and the command line is,
but the worker's own, and every driver class."""


def test_nothing_but_the_openhands_worker_loads_openhands():
    """Importing the SDK, any module the runtime or a driver class imports, or the command line loads no OpenHands."""
    worker = "platoon_harness.drivers.openhands.agent"
    command = [sys.executable, "-P", "-c", LOADED, worker, *OPENHANDS]
    done = subprocess.run(command, capture_output=True, text=True, timeout=120, check=False)

    assert done.returncode == 0, done.stderr
    assert done.stdout.split() == ["[]"]


@pytest.mark.parametrize("path", PUBLIC, ids=lambda path: str(path.relative_to(ROOT)))
def test_nothing_public_holds_a_local_path_or_an_account(path):
    assert [line for line in path.read_text().splitlines() if LOCAL.search(line)] == []


@pytest.mark.parametrize(
    ("line", "caught"),
    [
        ("see /home/someone/notes", True),
        ("see /Users/Someone/notes", True),
        ("ssh login1.abci.ai", True),
        ("(/groups/somegroup/scratch)", True),
        ("write to someone@example.com", True),
        ("opencode@ff90ed91607c:packages/protocol/src/groups/event.ts:69", False),
        ("`claude-agent-acp@0.99.1`", False),
    ],
)
def test_the_scan_tells_a_local_path_from_a_path_in_a_repository(line, caught):
    assert bool(LOCAL.search(line)) == caught
