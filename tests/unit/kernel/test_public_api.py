"""The kernel's public names are written down."""

from pathlib import Path

from platoon_harness import kernel


def test_public_names_match_the_list():
    recorded = [
        line.partition("(")[0].partition("[")[0]
        for line in (Path(__file__).parents[2] / "public_api.txt").read_text().split()
    ]
    prefix = "platoon_harness.kernel."
    listed = {name.removeprefix(prefix) for name in recorded if name.startswith(prefix)}
    assert {name for name in listed if "." not in name} == set(kernel.__all__)


def test_every_public_name_exists():
    assert all(hasattr(kernel, name) for name in kernel.__all__)
