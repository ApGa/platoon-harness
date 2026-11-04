"""The tool plane's public names, and those of the HTTP it shares, are written down."""

from pathlib import Path

import pytest

from platoon_harness import http, tools

RECORDED = (Path(__file__).parents[2] / "public_api.txt").read_text().split()


@pytest.mark.parametrize("module", [tools, http], ids=lambda module: module.__name__)
def test_public_names_match_the_list(module):
    prefix = f"{module.__name__}."

    assert {name.removeprefix(prefix) for name in RECORDED if name.startswith(prefix)} == set(module.__all__)


@pytest.mark.parametrize("module", [tools, http], ids=lambda module: module.__name__)
def test_every_public_name_exists(module):
    assert all(hasattr(module, name) for name in module.__all__)
