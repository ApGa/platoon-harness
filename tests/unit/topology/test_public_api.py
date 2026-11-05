"""The public names of topology, team and config are written down."""

from pathlib import Path

import pytest

from platoon_harness import config, extensions, schema, team, topology

MODULES = {"topology": topology, "team": team, "config": config, "extensions": extensions, "schema": schema}


@pytest.mark.parametrize("name", MODULES)
def test_public_names_match_the_list(name):
    recorded = [
        line.partition("(")[0].partition("[")[0]
        for line in (Path(__file__).parents[2] / "public_api.txt").read_text().split()
    ]
    prefix = f"platoon_harness.{name}."
    listed = {line.removeprefix(prefix) for line in recorded if line.startswith(prefix)}
    assert {line for line in listed if "." not in line} == set(MODULES[name].__all__)


@pytest.mark.parametrize("name", MODULES)
def test_every_public_name_exists(name):
    assert all(hasattr(MODULES[name], public) for public in MODULES[name].__all__)
