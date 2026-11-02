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
    *SDK.rglob("*.py"),
    *(ROOT / "docs").glob("*.md"),
    *(ROOT / "docs" / "adr").glob("*.md"),
    *(ROOT / "tests" / "conformance").glob("*.py"),
)
LOCAL = re.compile(r"/(home|groups|Users)/[a-z]|/gs/|gai\d{5}|aci\d{5}|\bR9920261300\b|ANTHROPIC_API_KEY=sk-|sk-ant-")


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


@pytest.mark.parametrize("path", PUBLIC, ids=lambda path: path.name)
def test_nothing_public_holds_a_local_path_or_an_account(path):
    assert [line for line in path.read_text().splitlines() if LOCAL.search(line)] == []
