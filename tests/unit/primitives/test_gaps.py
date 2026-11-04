"""Gaps: each incident is one `gap.recorded` of the closed set, on its member's plane, and says where it began:
architecture section 11, Coverage."""

import re
from pathlib import Path
from typing import get_args

from platoon_harness import primitives
from platoon_harness.primitives import GAPS, Gap

from .support import end_turn, of_type, report, result_of, spawn, start_turn

SDK = Path(primitives.__file__).parents[1]


def _sources(*folders: str) -> str:
    return "\n".join(path.read_text() for folder in folders for path in (SDK / folder).rglob("*.py"))


def test_every_incident_gap_is_one_gap_recorded():
    """Each member has the writer the table names, and nothing else names a gap: a `turn.lost` carries none."""
    drivers, runtime = _sources("drivers"), _sources("primitives", "kernel", "runtime")
    reported = set(re.findall(r'GapReport\(what="([a-z_]+)"\)', drivers)) | {"unknown_update"}
    recorded = set(re.findall(r'record_gap\([^)]*?"([a-z_]+)"', runtime))
    recorded |= set(re.findall(r'"what": "([a-z_]+)"', _sources("kernel")))

    assert set(GAPS) == set(get_args(Gap))
    assert "exposure_unconfirmed" not in GAPS
    for what, kind in GAPS.items():
        assert ("driver" in kind.writers) <= (what in reported), what
        assert ("runtime" in kind.writers) <= (what in recorded or what in reported), what
    assert [what for what in GAPS if not GAPS[what].carries] == ["compaction_opaque", "usage_lower_bound"]
    assert '"gap":' not in _sources("kernel")


async def test_a_lost_turn_leaves_one_gap_naming_where_its_turn_began(kernel):
    await spawn(kernel, "bob")
    await start_turn(kernel, "bob", "t9")
    began = of_type(kernel, "turn.started")[-1].seq

    result_of(await kernel.submit(kernel.runtime, "runtime.start", {"drift": []}))

    gap = of_type(kernel, "gap.recorded")[-1]
    lost = of_type(kernel, "turn.lost")[-1]
    assert (gap.v, gap.data) == (2, {"plane": "control", "what": "crash_window", "since": began})
    assert (lost.v, lost.data) == (2, None)
    assert gap.seq < lost.seq
    ending = result_of(kernel.query(kernel.runtime, "session.ending", {}))
    assert ending["gaps"] == [{"agent": "bob", "what": "crash_window", "plane": "control", "count": 1}]


async def test_a_harness_that_exits_in_a_turn_leaves_a_gap_naming_where_it_began(kernel):
    await spawn(kernel, "bob")
    await start_turn(kernel, "bob")
    began = of_type(kernel, "turn.started")[-1].seq

    await report(kernel, "bob", "exited", reason="gone")

    assert of_type(kernel, "gap.recorded")[-1].data["since"] == began


async def test_a_takeover_records_its_gap_where_the_hold_begins(kernel, ada):
    await spawn(kernel, "bob", ready={"resume": True})

    result_of(await kernel.submit(ada, "agent.takeover", {"agent": "@bob"}))
    held = of_type(kernel, "agent.held")[-1]
    gap = of_type(kernel, "gap.recorded")[-1]
    result_of(await kernel.submit(ada, "agent.release", {"agent": "@bob"}))

    assert gap.seq > held.seq and gap.data == {"plane": "control", "what": "takeover", "since": None}
    assert [event.data["what"] for event in of_type(kernel, "gap.recorded")] == ["takeover"]


async def test_every_gap_is_on_its_member_s_plane(kernel):
    await spawn(kernel, "bob")
    await start_turn(kernel, "bob")
    for what in ("stream_lost", "usage_lower_bound", "hidden_call", "native_child_unattributed", "unknown_update"):
        await report(kernel, "bob", "gap", what=what)
    await report(kernel, "bob", "compacted")
    await end_turn(kernel, "bob")

    gaps = of_type(kernel, "gap.recorded")
    assert {gap.data["what"] for gap in gaps} == {
        "stream_lost",
        "usage_lower_bound",
        "hidden_call",
        "native_child_unattributed",
        "unknown_update",
        "compaction_opaque",
    }
    assert all(gap.data["plane"] == GAPS[gap.data["what"]].plane and gap.v == 2 for gap in gaps)
