"""Gaps: each incident is one `gap.recorded` of the closed set, on its member's plane, and says where it began:
architecture section 11, Coverage."""

import re
from dataclasses import replace
from pathlib import Path
from typing import get_args

from platoon_harness import primitives
from platoon_harness.kernel import Args, Kernel, Principal, Txn, op
from platoon_harness.primitives import GAPS, PRIMITIVES, Gap

from .support import ROLES, end_turn, enroll, grant, of_type, refusal, report, result_of, send, spawn, start_turn

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


async def test_a_crash_window_outside_a_turn_begins_at_the_work_it_could_not_prove(kernel):
    """An admission in flight when the runtime died is uncertain, and the gap said of it begins at its request."""
    spawn = {"name": "bob", "child_role": "worker", "goal": "be bob"}
    result_of(await kernel.submit(kernel.runtime, "agent.spawn", spawn))
    admit = result_of(kernel.query(kernel.runtime, "effect.ready", {}))[0]
    result_of(await kernel.submit(kernel.runtime, "effect.start", {"id": admit["id"]}))
    result_of(await kernel.submit(kernel.runtime, "runtime.start", {"drift": []}))

    await report(kernel, "bob", "gap", what="crash_window")

    assert admit["kind"] == "admit" and of_type(kernel, "gap.recorded")[-1].data["since"] == admit["id"]


async def test_a_hold_records_its_gap_where_it_begins(kernel, ada):
    await spawn(kernel, "bob", ready={"resume": True})

    result_of(await kernel.submit(ada, "agent.hold", {"agent": "@bob"}))
    held = of_type(kernel, "agent.held")[-1]
    gap = of_type(kernel, "gap.recorded")[-1]
    result_of(await kernel.submit(ada, "agent.release", {"agent": "@bob"}))

    assert gap.seq > held.seq and gap.data == {"plane": "control", "what": "hold", "since": None}
    assert [event.data["what"] for event in of_type(kernel, "gap.recorded")] == ["hold"]


@op("agent.takeover")
def takeover(txn: Txn, a: Args) -> None:
    """bob held, as `agent.takeover` recorded it before it was renamed `agent.hold`: its gap named `takeover`."""
    txn.emit("agent.held", "agent/bob", gist=f"bob held by {txn.me.id}", agent="bob", data={"by": txn.me.id})
    data = {"plane": "control", "what": "takeover", "since": None}
    txn.emit("gap.recorded", "agent/bob", gist="gap: takeover", agent="bob", data=data, v=2)


BEFORE = tuple(replace(found, ops=(*found.ops, takeover)) if found.name == "agent" else found for found in PRIMITIVES)
"""The primitives as they were before the rename, as far as a hold goes."""


async def test_a_journal_from_before_the_rename_keeps_its_gap_named_takeover(folder, clock):
    """A journal from before `agent.takeover` became `agent.hold` opens and folds as it is: its agent stays held until
    `agent.release`, and its gap keeps the name `takeover`, which `GAPS` no longer holds, so it is taken as a gap
    content could come through, as `hold` is. `agent.takeover` is refused `not_found`, but for a retry of a command the
    journal answered, which is answered from it, as any retry is."""
    ada = Principal(id="human:ada")
    before = Kernel.open(folder, clock=clock, extensions=BEFORE)
    result_of(await before.submit(before.runtime, "session.open", {"roles": ROLES, "limits": {}}))
    await grant(before, "agent")
    await grant(before, "human")
    await enroll(before, ada)
    alice = await spawn(before, "alice")
    await spawn(before, "bob", ready={"resume": True})
    sent = (await send(before, alice, "@bob", "while held"))["ref"]
    result_of(await before.submit(ada, "agent.takeover", {}, key="hold bob"))
    inside = (await send(before, alice, "@alice", "meanwhile"))["ref"]
    before.close()

    kernel = Kernel.open(folder, clock=clock, extensions=PRIMITIVES)
    try:
        await kernel.rebuild_all()
        held = result_of(kernel.query(kernel.runtime, "exposure", {"agent": "bob", "ref": sent, "before": inside}))
        ending = result_of(kernel.query(kernel.runtime, "session.ending", {}))

        assert held["answer"] == "unknown"
        assert [(incident["what"], incident["carries"]) for incident in held["incidents"]] == [("takeover", True)]
        assert ending["gaps"] == [{"agent": "bob", "what": "takeover", "plane": "control", "count": 1}]
        assert result_of(await kernel.submit(ada, "agent.takeover", {}, key="hold bob")) is None
        assert refusal(await kernel.submit(ada, "agent.takeover", {})).code == "not_found"
        assert refusal(await kernel.submit(ada, "agent.hold", {"agent": "@bob"})).code == "conflict"
        result_of(await kernel.submit(ada, "agent.release", {"agent": "@bob"}))
        result_of(await kernel.submit(ada, "agent.hold", {"agent": "@bob"}))
        assert [event.data["what"] for event in of_type(kernel, "gap.recorded")] == ["takeover", "hold"]
    finally:
        kernel.close()


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
