"""The guide runs: each TOML form builds the same team as its Python form, and prints what the page says."""

import re
from pathlib import Path
from typing import Any

from platoon_harness.team import Team
from platoon_harness.topology import PRESETS

GUIDE = Path(__file__).parents[3] / "docs" / "how-to" / "topologies.md"
BLOCK = re.compile(r"^```(\w+)\n(.*?)^```$", re.M | re.S)


def blocks() -> list[tuple[str, str]]:
    return [(match[1], match[2]) for match in BLOCK.finditer(GUIDE.read_text())]


def test_the_toml_and_python_forms_build_one_team_and_print_what_the_page_says():
    namespace: dict[str, Any] = {}
    written = None
    pairs = 0
    for language, text in blocks():
        if language == "toml":
            written = text
        elif language == "python":
            exec(text, namespace)
        elif language == "text":
            assert written is not None
            extensions = {"pairing": namespace["extension"]} if "extension" in namespace else {}
            assert Team.loads(written).resolved(extensions) == namespace["team"]
            assert namespace["team"].show() == text.strip()
            pairs += 1
            written = None
    assert pairs == len(PRESETS) + 4


def test_every_preset_has_a_section():
    headings = re.findall(r"^### (.+)$", GUIDE.read_text(), re.M)
    assert headings == list(PRESETS)


def test_the_resolved_form_of_every_example_is_valid_input():
    namespace: dict[str, Any] = {}
    for language, text in blocks():
        if language == "python":
            exec(text, namespace)
        if language == "text":
            team = namespace["team"]
            assert Team.loads(team.show(resolved=True)) == team
