"""The primitives as a whole: on the public kernel, and complete against the op table."""

import re
from hashlib import sha256
from itertools import takewhile
from pathlib import Path

from platoon_harness import primitives
from platoon_harness.kernel import Kernel, ManualClock
from platoon_harness.primitives import PRIMITIVES

ARCHITECTURE = Path(__file__).parents[3] / "docs" / "architecture.md"
OUT_OF_SCOPE = {"topology.patch", "topology.show", "lineage", "exposure"}
VIEWS = {
    "stamps": (1, "7caa58b4f618"),
    "principals": (1, "4ee2a56cedb6"),
    "grants": (1, "c042b6064492"),
    "effects": (1, "d490ea98cdf6"),
    "timers": (1, "8b7ee8f23867"),
    "tombstones": (1, "4aad641385d8"),
    "session": (2, "47824e611e3a"),
    "budgets": (1, "90243faf21f4"),
    "agents": (7, "04d54b82f4bb"),
    "channels": (1, "385abe8c30d1"),
    "groups": (1, "8989bb29c3c8"),
    "deliveries": (7, "0eafdf0c2e3d"),
    "waits": (1, "745fdf295b54"),
    "boards": (1, "0d20dc5d4414"),
    "tasks": (1, "0f9ee7057d2b"),
    "approvals": (1, "62d28b8408f1"),
    "attention": (2, "5facc571cc2b"),
    "changes": (1, "0bd106b56a2b"),
    "gaps": (1, "0851cd5dd6fd"),
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
    recorded = (Path(__file__).parents[2] / "public_api.txt").read_text().split()
    prefix = "platoon_harness.primitives."

    assert {name.removeprefix(prefix) for name in recorded if name.startswith(prefix)} == set(primitives.__all__)


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
