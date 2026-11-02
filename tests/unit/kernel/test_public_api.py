"""The kernel's public names are written down."""

from pathlib import Path

from platoon_harness import kernel


def test_public_names_match_the_list():
    recorded = (Path(__file__).parents[2] / "public_api.txt").read_text().split()
    prefix = "platoon_harness.kernel."
    assert {name.removeprefix(prefix) for name in recorded if name.startswith(prefix)} == set(kernel.__all__)


def test_every_public_name_exists_and_is_in_the_docstring():
    for name in kernel.__all__:
        assert hasattr(kernel, name)
        assert name in (kernel.__doc__ or "")
