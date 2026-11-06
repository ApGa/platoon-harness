"""The team file's reference, made from its schema: every key of every table, and every preset with its arguments."""

import inspect
from pathlib import Path

import pytest

from platoon_harness import ConfigError, Team
from platoon_harness.topology import PRESETS
from platoon_harness_cli.team_file import reference

PAGE = Path(__file__).parents[3] / "docs" / "reference" / "team-file.md"
UNSET = {"Topology": {"unexpanded"}, "Unexpanded": {"preset", "params"}}
"""What no file sets, by model: `[topology]` reads an `unexpanded` key as a preset's name."""


def section(heading: str) -> str:
    return PAGE.read_text().split(f"\n{heading}\n", 1)[1].split("\n#", 1)[0]


def test_the_reference_is_made_from_the_schema():
    """On a failure, run `uv run python -m platoon_harness_cli.team_file > docs/reference/team-file.md`."""
    assert PAGE.read_text() == reference()


def test_every_key_of_every_table_has_a_row_in_its_model_s_section():
    """The models are pydantic's own walk of the schema, so one the generator missed fails here too."""
    schema = Team.model_json_schema()
    models = {name: model for name, model in {"Team": schema, **schema["$defs"]}.items() if "properties" in model}

    assert {"Role", "Command", "Budget", "AuthProfile", "Topology", "Queue", "Grant", "Test"} <= set(models)
    for name, model in models.items():
        keys = set(model["properties"]) - UNSET.get(name, set())
        rows = section(f"## {name}") if keys else ""
        assert sorted(key for key in keys if f"\n| `{key}` |" not in rows) == [], name


def test_every_preset_has_a_row_for_each_argument():
    for name, preset in PRESETS.items():
        rows = section(f"### {name}")
        assert [item for item in inspect.signature(preset).parameters if f"\n| `{item}` |" not in rows] == [], name


def test_a_topology_key_no_file_sets_has_no_row():
    team = "[roles.a]\nharness = 'claude'\n[topology.unexpanded]\npreset = 'tree'\n"

    assert "| `unexpanded` |" not in PAGE.read_text()
    with pytest.raises(ConfigError, match="unknown preset `unexpanded`"):
        Team.loads(team)
