"""The extending index names every entry-point group a package here declares and every field of an extension."""

import dataclasses
import re
import tomllib

from platoon_harness.extensions import DRIVERS, EXTENSIONS
from platoon_harness.kernel import Extension

from .support import ROOT, tracked

INDEX = ROOT / "docs" / "extending" / "index.md"


def test_the_index_names_every_entry_point_group_and_extension_field():
    """Each group discovery reads, which are every group a `pyproject.toml` here declares an entry point under, and a
    row of the parts table for each field of `Extension`, in its order."""
    text = INDEX.read_text()
    declared = {
        group
        for path in tracked("*pyproject.toml")
        for group in tomllib.loads(path.read_text()).get("project", {}).get("entry-points", {})
    }
    parts = text.partition("| Field | What it holds | What it becomes |")[2].partition("\n\n")[0]

    assert declared == {DRIVERS, EXTENSIONS}
    assert {f"`{DRIVERS}`", f"`{EXTENSIONS}`"} <= set(re.findall(r"`[^`]+`", text))
    assert re.findall(r"^\| `(\w+)` \|", parts, re.MULTILINE) == [field.name for field in dataclasses.fields(Extension)]
