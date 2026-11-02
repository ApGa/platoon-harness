"""The primitives as a whole: on the public kernel, and complete against the op table."""

import re
from itertools import takewhile
from pathlib import Path

from platoon_harness import primitives
from platoon_harness.kernel import Kernel, ManualClock
from platoon_harness.primitives import PRIMITIVES

ARCHITECTURE = Path(__file__).parents[3] / "docs" / "architecture.md"
OUT_OF_SCOPE = {"topology.patch", "topology.show", "lineage", "exposure"}


def table_rows() -> list[str]:
    text = ARCHITECTURE.read_text().partition("| Area | Commands | Queries |")[2]
    return list(takewhile(lambda line: line.startswith("|"), text.splitlines()[2:]))


def documented_ops() -> set[str]:
    return {name for row in table_rows() for name in re.findall(r"`([a-z.]+)`", row)}


def test_every_op_in_the_table_exists(tmp_path):
    kernel = Kernel.open(tmp_path / "session", clock=ManualClock(1.0), extensions=PRIMITIVES)
    loaded = set(kernel.ops)
    kernel.close()

    assert documented_ops() - OUT_OF_SCOPE <= loaded


def test_every_primitive_op_is_in_the_table():
    defined = {operation.name for extension in PRIMITIVES for operation in extension.ops}

    assert defined <= documented_ops()


def test_every_public_primitive_name_is_written_down():
    recorded = (Path(__file__).parents[2] / "public_api.txt").read_text().split()
    prefix = "platoon_harness.primitives."

    assert {name.removeprefix(prefix) for name in recorded if name.startswith(prefix)} == set(primitives.__all__)
