"""The public names of the driver layer are written down."""

from pathlib import Path

import pytest

from platoon_harness import drivers, primitives, rpc, testing
from platoon_harness.drivers import claude, codex, env, exec, levels, openhands, pi, process, wire

MODULES = {
    "rpc": rpc,
    "drivers": drivers,
    "drivers.claude": claude,
    "drivers.codex": codex,
    "drivers.env": env,
    "drivers.exec": exec,
    "drivers.levels": levels,
    "drivers.openhands": openhands,
    "drivers.pi": pi,
    "drivers.process": process,
    "drivers.wire": wire,
    "testing": testing,
    "primitives": primitives,
}
RECORDED = (Path(__file__).parents[2] / "public_api.txt").read_text().split()


@pytest.mark.parametrize("name", MODULES)
def test_public_names_match_the_list(name):
    prefix = f"platoon_harness.{name}."
    listed = {line.removeprefix(prefix) for line in RECORDED if line.startswith(prefix)}
    deeper = {line for line in listed if "." in line}

    assert listed - deeper == set(MODULES[name].__all__)


@pytest.mark.parametrize("name", MODULES)
def test_every_public_name_exists(name):
    assert all(hasattr(MODULES[name], public) for public in MODULES[name].__all__)
