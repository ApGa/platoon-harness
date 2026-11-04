"""SwarmChat's page, pinned: read from the installed package alone, held to its hashes, and run under a policy that
names every script by hash."""

import ast
import base64
import hashlib
import re
from importlib import resources
from pathlib import Path

import pytest

from platoon_harness_cli.web import page as page_module
from platoon_harness_cli.web.page import BANNER, PINNED, Unpinned, edited, load

ROOT = Path(__file__).parents[3]
PRODUCT = sorted(ROOT.glob("packages/*/src/**/*.py"))
SDK = ROOT / "packages" / "sdk" / "src"


def digest(script: str) -> str:
    return f"'sha256-{base64.b64encode(hashlib.sha256(script.encode()).digest()).decode()}'"


def scripts(html: str) -> list[str]:
    return re.findall(r"<script>(.*?)</script>", html, re.S)


def test_each_page_file_is_the_one_pinned():
    for name, sha256 in PINNED.items():
        data = resources.files("swarmchat").joinpath("page", name).read_bytes()
        assert hashlib.sha256(data).hexdigest() == sha256, name


def test_a_page_file_that_is_not_the_one_pinned_is_refused_with_the_reason(monkeypatch):
    monkeypatch.setitem(PINNED, "app.js", "0" * 64)

    with pytest.raises(Unpinned, match=r"app\.js is not the one pinned"):
        load()


def test_an_edit_whose_text_is_not_there_once_fails_closed():
    assert edited("x.html", "a <!--JS--> b", "<!--JS-->", "c") == "a c b"
    with pytest.raises(Unpinned, match="0 times"):
        edited("x.html", "a b", "<!--JS-->", "c")
    with pytest.raises(Unpinned, match="2 times"):
        edited("x.html", "<!--JS--><!--JS-->", "<!--JS-->", "c")


def test_the_policy_names_every_script_by_hash_and_no_other_source():
    page = load()
    gate = page.gate.decode()
    inline = scripts(gate)

    assert len(inline) == 2
    assert {digest(script) for script in [*inline, page.js]} == set(re.findall(r"'sha256-[^']+'", page.policy))
    assert "script-src 'sha256-" in page.policy and "'unsafe-inline'" not in page.policy.split("style-src")[0]
    assert "default-src 'none'" in page.policy and "connect-src 'self'" in page.policy
    assert "frame-ancestors 'none'" in page.policy and "form-action 'none'" in page.policy


def test_each_swarmchat_script_served_carries_its_notice():
    page = load()
    gate_js = scripts(page.gate.decode())[1]

    assert page.js.startswith(BANNER) and gate_js.startswith(BANNER)
    assert "Copyright (c) 2026 The SwarmChat Authors" in BANNER and "MIT License" in BANNER
    pinned = resources.files("swarmchat").joinpath("page", "app.js").read_text()
    assert page.js.startswith(BANNER + pinned + "\n"), "the pinned script is served whole, with the overlay after it"


def test_the_viewer_is_put_together_as_upstream_puts_it():
    html = load().html

    assert "<!--CSS-->" not in html and "<!--JS-->" not in html and "<style>" in html and "<script" not in html


def test_product_code_never_imports_swarmchat():
    """The page is read as files, through `importlib.resources`, and nothing of SwarmChat's server runs."""
    for path in PRODUCT:
        for node in ast.walk(ast.parse(path.read_text())):
            names = [alias.name for alias in node.names] if isinstance(node, ast.Import) else []
            names += [node.module or ""] if isinstance(node, ast.ImportFrom) else []
            assert not [name for name in names if name.split(".")[0] == "swarmchat"], path


def test_the_sdk_never_imports_the_browser_client():
    for path in SDK.rglob("*.py"):
        assert "platoon_harness_cli" not in path.read_text(), path


def test_the_pinned_version_is_the_installed_one():
    from importlib.metadata import version

    assert version("swarmchat") == page_module.VERSION
