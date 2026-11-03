"""The SDK stands alone, and what is public stays free of anything local or secret."""

import ast
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[3]
SDK = ROOT / "packages" / "sdk" / "src" / "platoon_harness"
ALLOWED = set(sys.stdlib_module_names) | {"pydantic", "pydantic_core", "platoon_harness"}
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
    r"|[\w.+-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}\b"
)
"""An absolute path under a home or a group, this cluster's names, a key, or an email address."""


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
    assert roots_of(path) <= ALLOWED


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
