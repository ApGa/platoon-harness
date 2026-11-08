"""The primitives as a whole: on the public kernel, and complete against the op table."""

import re
from hashlib import sha256
from itertools import takewhile
from pathlib import Path

from platoon_harness import primitives
from platoon_harness.kernel import Kernel, ManualClock
from platoon_harness.primitives import PRIMITIVES
from platoon_harness.primitives.clients import Changes

ARCHITECTURE = Path(__file__).parents[3] / "docs" / "architecture.md"
OUT_OF_SCOPE = {"topology.patch", "topology.show"}
VIEWS = {
    "stamps": (1, "7caa58b4f618"),
    "principals": (2, "8efbf0bd0ad6"),
    "grants": (1, "c042b6064492"),
    "effects": (1, "d490ea98cdf6"),
    "timers": (1, "8b7ee8f23867"),
    "tombstones": (1, "4aad641385d8"),
    "session": (2, "47824e611e3a"),
    "counters": (1, "431f295c4857"),
    "budgets": (4, "fc4a6126880f"),
    "agents": (14, "c7380a67ce66"),
    "channels": (1, "385abe8c30d1"),
    "groups": (1, "8989bb29c3c8"),
    "deliveries": (12, "7619c2dfbf0c"),
    "waits": (2, "13f9a8fa9801"),
    "boards": (1, "0d20dc5d4414"),
    "tasks": (2, "15965716a56b"),
    "approvals": (1, "62d28b8408f1"),
    "looks": (4, "4e3feea01245"),
    "attention": (6, "f49f59bcb946"),
    "changes": (3, "d0bd725d3230"),
    "gaps": (2, "81d2cf7fb55b"),
    "exposures": (1, "f1205ac4d018"),
    "calls": (1, "abc99d83af57"),
    "references": (1, "a09e00bc5ff2"),
}


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
    recorded = [
        line.partition("(")[0].partition("[")[0]
        for line in (Path(__file__).parents[2] / "public_api.txt").read_text().split()
    ]
    prefix = "platoon_harness.primitives."

    listed = {name.removeprefix(prefix) for name in recorded if name.startswith(prefix)}

    assert {name for name in listed if "." not in name} == set(primitives.__all__)


def test_a_view_that_changes_shape_changes_version(tmp_path):
    """A version is what refolds an older session's table, so a schema changed under an old one crashes that session's
    resume. On a failure, bump `version`, then pin the new pair here."""
    kernel = Kernel.open(tmp_path / "session", clock=ManualClock(1.0), extensions=PRIMITIVES)
    found = {
        view.name: (view.version, sha256(" ".join(view.schema.split()).encode()).hexdigest()[:12])
        for view in kernel._views
    }
    kernel.close()

    assert found == VIEWS


def test_changes_view_schema_is_pinned_to_its_version():
    """Clients read its rows, so a change of its table is a new version, as for every view above."""
    assert (Changes.version, sha256(" ".join(Changes.schema.split()).encode()).hexdigest()[:12]) == VIEWS["changes"]
