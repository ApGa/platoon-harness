"""One report vocabulary: what `agent.report` does with each, and how each crosses the wire."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from platoon_harness import drivers, team
from platoon_harness.primitives import (
    RAW_LIMIT,
    REPORTS,
    ApprovalRequested,
    Capabilities,
    Changed,
    ChildSeen,
    Compacted,
    Delta,
    Exited,
    GapReport,
    InputDelivered,
    Item,
    ModelCall,
    Native,
    Ready,
    TurnEnded,
    TurnStarted,
    Usage,
)

from .support import (
    agent,
    of_type,
    refusal,
    report,
    result_of,
    send,
    settle_effects,
    spawn,
    start_turn,
)

EVERY_REPORT = [
    Ready(native="s-1", version="1.0", effective_model="m", tools_visible=("wait",)),
    TurnStarted(turn="t1"),
    TurnEnded(reason="stopped"),
    Delta(text="live"),
    Item(
        kind="tool",
        gist="ran it",
        phase="completed",
        native_id="i1",
        call_id="c1",
        body="all of it",
        approval="a1",
        outcome="ok",
    ),
    InputDelivered(input="12", boundary="tool", evidence="message_start", native_id="entry-3"),
    ApprovalRequested(id="a1", gist="run it?"),
    ModelCall(call_id="c1", model="m", purpose="compaction"),
    Usage(tokens=14, usd=0.5, label="provider", scope="tree", call_id="c1"),
    Compacted(forgotten=("e1", "e2"), summary="what it kept"),
    ChildSeen(native="thread-2", parent="thread-1", attribution="inferred"),
    GapReport(plane="model", what="hidden_call"),
    Native(kind="frame", raw="???", cut=3),
    Exited(reason="gone"),
    Changed(path="src/a.py", added=1, removed=2, tests="passed"),
]


@pytest.mark.parametrize("sent", EVERY_REPORT, ids=lambda report: report.type)
def test_every_report_survives_the_wire(sent):
    frame = json.dumps(sent.model_dump(mode="json"))

    assert REPORTS.validate_json(frame) == sent


def test_the_vocabulary_is_written_in_the_architecture_in_full():
    text = (Path(__file__).parents[3] / "docs" / "architecture.md").read_text()
    section = text[text.index("`Reporter` is a plain async callable") : text.index("### 9.1 Wire")]

    for sent in EVERY_REPORT:
        assert f"`{sent.type}{{" in section or f"`{sent.type}`" in section, sent.type


@pytest.mark.parametrize(
    "frame",
    [
        '{"type": "dreamed"}',
        '{"type": "turn.ended", "reason": 1, "extra": true}',
        '{"type": "ready", "levels": {"trainable": true}}',
        '{"type": "ready", "persistent": true}',
        '{"type": "usage"}',
        '{"type": "gap", "plane": "nowhere", "what": "stream_lost"}',
        '{"type": "gap", "plane": "control", "what": "a word nobody knows"}',
        '{"type": "child.seen", "native": "c", "attribution": "guessed"}',
        '{"text": "no type"}',
    ],
)
def test_what_the_vocabulary_does_not_hold_is_refused(frame):
    with pytest.raises(ValueError):
        REPORTS.validate_json(frame)


def test_a_report_cannot_be_coerced():
    with pytest.raises(ValueError):
        REPORTS.validate_json('{"type": "usage", "tokens": "12", "label": "provider"}')


def test_a_raw_frame_is_bounded():
    assert Native(kind="k", raw="x" * RAW_LIMIT).raw
    with pytest.raises(ValueError):
        Native(kind="k", raw="x" * (RAW_LIMIT + 1))


def test_the_worst_raw_frame_fits_one_event():
    native = Native(kind="k" * 256, raw="\x00" * RAW_LIMIT, cut=1)

    assert len(json.dumps(native.model_dump(exclude={"type"}))) <= 16 * 1024


def test_one_capabilities_class_serves_teams_and_drivers():
    assert team.Capabilities is drivers.Capabilities is Capabilities


def test_capabilities_cross_the_wire_and_absence_means_unsupported():
    full = Capabilities(
        persistent=True,
        resume=True,
        boundaries={"turn", "tool", "model_call"},
        tool_paths={"mcp-http", "mcp-stdio", "shell"},
        tool_timeout_s=300.0,
        interrupt=True,
        approvals="gated",
        native_children="observed",
        call_ids="agent",
        dialects={"chat", "responses", "messages"},
        coverage={"prompt": "observed", "shell_reads": "none", "files": "partial"},
        measures={"tokens", "usd"},
        sandboxes={"read-only"},
    )

    assert Capabilities.model_validate_json(full.model_dump_json()) == full
    empty = Capabilities()
    assert (empty.persistent, empty.interrupt, empty.approvals, empty.call_ids) == (False, False, "none", "none")
    assert empty.coverage == {} and empty.boundaries == frozenset()


async def test_a_started_agent_keeps_what_was_declared_beside_what_was_verified(kernel):
    args = {"name": "bob", "child_role": "worker", "goal": "be bob"}
    result_of(await kernel.submit(kernel.runtime, "agent.spawn", args))
    await settle_effects(kernel, "bob")
    start = {
        "agent": "bob",
        "ready": {"version": "1.0", "effective_model": "exact"},
        "declared": {"persistent": True, "boundaries": ["turn"], "tool_timeout_s": 60.0},
        "verified": {"driver": "x", "version": "1.0", "checks": []},
        "levels": {"operational": {"state": "met"}},
    }

    result_of(await kernel.submit(kernel.runtime, "agent.start", start))

    data = of_type(kernel, "agent.started")[-1].data
    assert data["declared"]["tool_timeout_s"] == 60.0
    assert data["verified"]["driver"] == "x"
    assert data["levels"] == {"operational": {"state": "met"}}
    assert data["version"] == "1.0"
    roster = result_of(kernel.query(kernel.runtime, "agent.status", {"agent": "bob"}))
    assert roster["state"] == "idle"


async def test_a_start_for_nobody_is_refused(kernel):
    args = {"agent": "nobody", "ready": {}, "declared": {}}

    assert refusal(await kernel.submit(kernel.runtime, "agent.start", args)).code == "not_found"


async def test_an_input_delivered_confirms_the_offer(kernel):
    await spawn(kernel, "bob")
    await send(kernel, kernel.runtime, "@bob", "hello")
    handed = result_of(await kernel.submit(kernel.runtime, "delivery.offer", {"agent": "bob"}))

    await report(kernel, "bob", "input.delivered", input=str(handed["input"]), boundary="turn", evidence="prompt")

    delivered = of_type(kernel, "context.delivered")[-1]
    assert (delivered.data["input"], delivered.data["evidence"]) == (handed["input"], "prompt")


@pytest.mark.parametrize("input", ["99999", "not-a-number"])
async def test_an_input_nobody_offered_is_refused(kernel, input):
    await spawn(kernel, "bob")
    args = {"agent": "bob", "report": {"type": "input.delivered", "input": input, "boundary": "turn"}}

    assert refusal(await kernel.submit(kernel.runtime, "agent.report", args)).code == "not_found"


async def test_an_approval_requested_is_the_same_approval(kernel):
    await spawn(kernel, "bob")

    await report(kernel, "bob", "approval.requested", id="a1", gist="run it?")

    event = of_type(kernel, "approval.requested")[-1]
    assert (event.agent, event.gist, event.data["id"]) == ("bob", "run it?", "a1")
    version = 1
    args = {"id": "a1", "verdict": "allow", "expected_version": version}
    assert result_of(await kernel.submit(kernel.runtime, "approval.resolve", args))["verdict"] == "allow"


async def test_a_model_call_with_an_id_stamps_the_envelope(kernel):
    await spawn(kernel, "bob")

    await report(kernel, "bob", "model.call", call_id="c1", model="m")

    event = of_type(kernel, "model.called")[-1]
    assert event.model.call_id == "c1"
    assert event.data == {"call_id": "c1", "model": "m", "purpose": None}


async def test_a_model_call_with_no_id_fabricates_none(kernel):
    await spawn(kernel, "bob")

    await report(kernel, "bob", "model.call")

    assert of_type(kernel, "model.called")[-1].model is None


async def test_a_model_call_keeps_the_harness_word_for_why_it_was_made(kernel):
    await spawn(kernel, "bob")

    await report(kernel, "bob", "model.call", purpose="compaction")

    assert of_type(kernel, "model.called")[-1].data["purpose"] == "compaction"


async def test_an_item_names_the_model_call_that_made_it(kernel):
    await spawn(kernel, "bob")
    await start_turn(kernel, "bob")

    await report(kernel, "bob", "item", kind="tool", gist="ran it", call_id="c1")

    assert of_type(kernel, "item.recorded")[-1].model.call_id == "c1"


async def test_usage_names_the_model_call_it_paid_for(kernel):
    await spawn(kernel, "bob")
    await start_turn(kernel, "bob")

    await report(kernel, "bob", "usage", tokens=14, label="provider", scope="call", call_id="c1")

    assert of_type(kernel, "usage.reported")[-1].model.call_id == "c1"


async def test_a_report_with_no_call_id_fabricates_no_link(kernel):
    await spawn(kernel, "bob")
    await start_turn(kernel, "bob")

    await report(kernel, "bob", "item", kind="tool", gist="ran it")
    await report(kernel, "bob", "usage", tokens=14, label="provider")

    assert of_type(kernel, "item.recorded")[-1].model is None
    assert of_type(kernel, "usage.reported")[-1].model is None


@pytest.mark.parametrize("phase", ["started", "completed", None])
def test_a_phase_is_one_of_four(phase):
    assert Item(kind="tool", gist="x", phase=phase).phase == phase


def test_a_phase_nobody_knows_is_an_unknown_frame():
    with pytest.raises(ValidationError):
        REPORTS.validate_python({"type": "item", "kind": "tool", "gist": "x", "phase": "running"})


async def test_a_delivery_keeps_the_harness_id_for_what_landed(kernel):
    await spawn(kernel, "bob")
    await send(kernel, kernel.runtime, "@bob", "go")
    handed = result_of(await kernel.submit(kernel.runtime, "delivery.offer", {"agent": "bob"}))

    await report(kernel, "bob", "input.delivered", input=str(handed["input"]), boundary="turn", native_id="entry-3")

    assert of_type(kernel, "context.delivered")[-1].data["native_id"] == "entry-3"


async def test_a_compaction_cites_what_it_stored(kernel):
    await spawn(kernel, "bob")
    forgotten = await kernel.put_body(b'["e1", "e2"]')
    summary = await kernel.put_body(b"what it kept")

    await report(kernel, "bob", "compacted", forgotten=f"sha256:{forgotten}", summary=f"sha256:{summary}")

    assert of_type(kernel, "context.compacted")[-1].data == {
        "forgotten": f"sha256:{forgotten}",
        "summary": f"sha256:{summary}",
    }
    assert of_type(kernel, "gap.recorded") == []


async def test_a_compaction_that_forgot_nobody_knows_what_is_a_gap_by_itself(kernel):
    await spawn(kernel, "bob")

    await report(kernel, "bob", "compacted")

    assert [event.data["what"] for event in of_type(kernel, "gap.recorded")] == ["compaction_opaque"]
    ending = result_of(kernel.query(kernel.runtime, "session.ending", {}))
    assert [gap["what"] for gap in ending["gaps"]] == ["compaction_opaque"]


async def test_a_compaction_cannot_cite_what_nobody_stored(kernel):
    await spawn(kernel, "bob")

    outcome = await kernel.submit(
        kernel.runtime, "agent.report", {"agent": "bob", "report": {"type": "compacted", "forgotten": ["e1"]}}
    )

    assert refusal(outcome).code == "invalid"


async def test_usage_keeps_its_scope_and_label(kernel):
    await spawn(kernel, "bob")

    await report(kernel, "bob", "usage", tokens=14, label="lower_bound", scope="tree")

    data = of_type(kernel, "usage.reported")[-1].data
    assert (data["scope"], data["label"]) == ("tree", "lower_bound")


async def test_a_native_child_is_recorded_and_stays_on_its_parent(kernel):
    await spawn(kernel, "bob")

    await report(kernel, "bob", "child.seen", native="thread-2", parent="thread-1", attribution="inferred")

    event = of_type(kernel, "child.seen")[-1]
    assert event.data == {"native": "thread-2", "parent": "thread-1", "attribution": "inferred"}
    assert [row["agent"] for row in result_of(kernel.query(agent("bob"), "agent.list", {}))] == ["bob"]


async def test_a_native_frame_is_recorded_as_it_came(kernel):
    await spawn(kernel, "bob")

    await report(kernel, "bob", "native", kind="frame", raw="{]", cut=0)
    await report(kernel, "bob", "gap", plane="control", what="unknown_update")

    assert of_type(kernel, "native.recorded")[-1].data == {"kind": "frame", "raw": "{]", "cut": 0}
    assert of_type(kernel, "gap.recorded")[-1].data == {"plane": "control", "what": "unknown_update"}
