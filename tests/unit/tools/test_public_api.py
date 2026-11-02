"""The tool plane's public names are written down."""

from pathlib import Path

from platoon_harness import tools


def test_public_names_match_the_list():
    recorded = (Path(__file__).parents[2] / "public_api.txt").read_text().split()
    prefix = "platoon_harness.tools."

    assert {name.removeprefix(prefix) for name in recorded if name.startswith(prefix)} == set(tools.__all__)


def test_every_public_name_exists():
    assert all(hasattr(tools, name) for name in tools.__all__)
