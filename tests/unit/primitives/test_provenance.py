"""What reached an agent, what an event rests on, what rests on it, and whose work an outcome reaches: the views and the
four queries of architecture section 11."""

import asyncio
import json
import shutil
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pydantic import TypeAdapter

from platoon_harness.kernel import Kernel, ManualClock, Principal
from platoon_harness.primitives import (
    PRIMITIVES,
    Contributors,
    Exposure,
    Lineage,
    NotSeen,
    Seen,
    Unknown,
    Uses,
)
from platoon_harness.primitives.provenance import Bound, Coverage, Facts, Incident, decide

from .support import (
    ROLES,
    channel,
    confirm,
    end_turn,
    events_of,
    grant,
    of_type,
    refusal,
    report,
    result_of,
    send,
    spawn,
    start_turn,
)

EXPOSURE: TypeAdapter[Seen | NotSeen | Unknown] = TypeAdapter(Exposure)
SURFACES = ("prompt", "tool_results", "shell_reads", "files", "native_children", "compaction", "external")
PROVENANCE = ("exposure", "lineage", "uses", "contributors")


def ask(kernel: Kernel, op: str, **args: Any) -> Any:
    return result_of(kernel.query(kernel.runtime, op, args))


def exposure(kernel: Kernel, agent: str, ref: str, before: str | None = None) -> Seen | NotSeen | Unknown:
    return EXPOSURE.validate_python(ask(kernel, "exposure", agent=agent, ref=ref, before=before))


def lineage(kernel: Kernel, ref: str, after: str | None = None) -> Lineage:
    return Lineage.model_validate(ask(kernel, "lineage", ref=ref, after=after))


def uses(kernel: Kernel, ref: str, after: str | None = None) -> Uses:
    return Uses.model_validate(ask(kernel, "uses", ref=ref, after=after))


def contributors(kernel: Kernel, ref: str, after: str | None = None) -> Contributors:
    return Contributors.model_validate(ask(kernel, "contributors", ref=ref, after=after))


async def stored(kernel: Kernel, text: str) -> str:
    return f"sha256:{await kernel.put_body(text.encode())}"


def ref_of(event: Any) -> str:
    return f"{event.stream}@{event.version}"


def tool(id: str) -> dict[str, str]:
    return {"claudecode/toolUseId": id}


async def call(kernel: Kernel, agent: str, call_id: str, *anchors: str) -> None:
    """A model call, as a Claude-shaped harness reports it: the call, then each tool item it chose, under its id."""
    await report(kernel, agent, "model.call", call_id=call_id)
    for anchor in anchors:
        item = {"kind": "tool", "phase": "started", "gist": "a tool", "native_id": anchor, "call_id": call_id}
        await report(kernel, agent, "item", **item)


async def done(kernel: Kernel, agent: str, *anchors: str) -> None:
    """Each tool item completed, which holds its call's result."""
    for anchor in anchors:
        await report(
            kernel, agent, "item", kind="tool", phase="completed", gist="a tool", native_id=anchor, outcome="completed"
        )


async def scenario(kernel: Kernel) -> dict[str, str]:
    """Architecture section 11's case: A posts v1 and B is woken by it, its handover confirmed under `n1`; B reads v1's
    body, confirmed by its tool item; B compacts, forgetting `n1`; then B sends a message citing v1."""
    await channel(kernel, "notes", kind="board", delivery="wake")
    alice, bob = await spawn(kernel, "alice"), await spawn(kernel, "bob")
    body = await stored(kernel, "line one\nline two\nline three\n")
    post = {"board": "notes", "name": "spec", "gist": "v1", "body": body}
    posted = result_of(await kernel.submit(alice, "board.post", post))["ref"]
    handed = result_of(await kernel.submit(kernel.runtime, "delivery.offer", {"agent": "bob"}))
    await start_turn(kernel, "bob")
    await confirm(kernel, "bob", handed["input"], evidence="command_lifecycle", native_id="n1")
    await call(kernel, "bob", "c1", "t1")
    result_of(await kernel.submit(bob, "board.get", {"board": "notes", "name": "spec"}, native=tool("t1")))
    await done(kernel, "bob", "t1")
    await report(kernel, "bob", "compacted", forgotten=await stored(kernel, json.dumps(["n1"])))
    await report(kernel, "bob", "gap", what="unknown_update")
    await call(kernel, "bob", "c2", "t2")
    sent = {"to": "@alice", "gist": "done, as the spec says", "based_on": [posted]}
    message = result_of(await kernel.submit(bob, "message.send", sent, native=tool("t2")))["ref"]
    await done(kernel, "bob", "t2")
    return {"posted": posted, "message": message, "c2": ref_of(of_type(kernel, "model.called")[-1])}


def answers(kernel: Kernel, refs: dict[str, str]) -> list[Any]:
    return [
        ask(kernel, "exposure", agent="bob", ref=refs["posted"], before=refs["message"]),
        ask(kernel, "lineage", ref=refs["message"]),
        ask(kernel, "uses", ref=refs["posted"]),
        ask(kernel, "contributors", ref=refs["message"]),
    ]


async def test_the_provenance_scenario(kernel, folder, tmp_path):
    refs = await scenario(kernel)

    seen = exposure(kernel, "bob", refs["posted"], before=refs["message"])
    found = lineage(kernel, refs["message"])
    reached = contributors(kernel, refs["message"])

    assert isinstance(seen, Seen) and seen.total == 2
    assert seen.bound == Bound(by="call", seq=found.bound.seq, call=refs["c2"])
    wake, read = seen.edges
    assert (wake.how, [shown.form for shown in wake.shown]) == ("wake", ["gist"])
    assert wake.confirmed is not None and (wake.confirmed.evidence, wake.confirmed.native_id) == (
        "command_lifecycle",
        "n1",
    )
    assert [mark.mark for mark in wake.compactions or ()] == ["forgot"]
    assert (read.how, [(shown.ref, shown.form) for shown in read.shown]) == (
        "read",
        [("board/notes/spec@1", "gist"), ("board/notes/spec@1", "body")],
    )
    assert read.confirmed is not None and read.confirmed.evidence == "tool_item"
    assert [mark.mark for mark in read.compactions or ()] == ["unsaid"]
    assert read.anchor is not None and (read.anchor.key, read.anchor.ops) == ("claudecode/toolUseId", 1)

    assert found.made.maker == "agent:bob" and found.made.call == refs["c2"]
    assert found.made.anchor is not None and found.made.anchor.id == "t2"
    (declared,) = found.declared
    assert declared.ref == refs["posted"] and declared.maker == "agent:alice"
    assert isinstance(declared.exposure, Seen) and declared.exposure.total == 2
    assert found.totals == {"handed": 2, "confirmed": 2, "unconfirmed": 0, "gaps": 1}
    assert [row.kind for row in found.history or ()] == ["gap", "observed", "observed"]

    assert [(row.maker, row.kinds, row.hops) for row in reached.rows] == [
        ("agent:bob", (), 0),
        ("agent:alice", ("declared",), 1),
    ]
    bob = reached.rows[0]
    assert bob.unproved == SURFACES and bob.incidents == {"unknown_update": 1}

    live = answers(kernel, refs)
    await kernel.rebuild_all()
    rebuilt = answers(kernel, refs)
    kernel.close()
    shutil.copytree(folder, tmp_path / "copy")
    closed = Kernel.open(tmp_path / "copy", extensions=PRIMITIVES, read_only=True)
    copied = answers(closed, refs)
    closed.close()
    assert live == rebuilt == copied


async def test_provenance_answers_alike_after_a_rebuild_and_on_a_closed_copy(kernel, folder, tmp_path):
    refs = await scenario(kernel)
    await end_turn(kernel, "bob")
    live = answers(kernel, refs)

    await kernel.rebuild_all()
    rebuilt = answers(kernel, refs)
    kernel.close()
    shutil.copytree(folder, tmp_path / "copy")
    closed = Kernel.open(tmp_path / "copy", extensions=PRIMITIVES, read_only=True)

    assert live == rebuilt == answers(closed, refs)
    closed.close()


async def test_a_closed_copy_with_stale_views_is_refused_naming_the_fix(tmp_path):
    older = [extension for extension in PRIMITIVES if extension.name not in PROVENANCE]
    folder = tmp_path / "session"
    kernel = Kernel.open(folder, clock=ManualClock(1.0), extensions=older)
    result_of(await kernel.submit(kernel.runtime, "session.open", {"roles": {}}))
    kernel.close()

    reader = Kernel.open(folder, extensions=PRIMITIVES, read_only=True)
    refused = refusal(reader.query(reader.runtime, "lineage", {"ref": "session@1"}))
    reader.close()
    Kernel.open(folder, extensions=PRIMITIVES).close()
    fixed = Kernel.open(folder, extensions=PRIMITIVES, read_only=True)
    answered = lineage(fixed, "session@1")
    fixed.close()

    assert refused.code == "unavailable"
    assert "exposures" in str(refused.detail) and "`Kernel.open` and the extensions" in str(refused.detail)
    assert answered.event.type == "session.opened" and answered.made.maker == "runtime"


# Exposure.


async def test_a_read_is_seen_only_when_its_harness_reports_the_result(kernel):
    """A read committed, then the stream lost: the read was handed over, and nothing says its harness took it."""
    alice, bob = await spawn(kernel, "alice"), await spawn(kernel, "bob")
    sent = (await send(kernel, alice, "@bob", "read me"))["ref"]
    await start_turn(kernel, "bob")
    result_of(await kernel.submit(bob, "message.read", {}, native=tool("t1")))
    await report(kernel, "bob", "gap", what="stream_lost")

    answer = exposure(kernel, "bob", sent)

    assert isinstance(answer, Unknown)
    assert [offer.how for offer in answer.handed] == ["read"] and answer.handed[0].confirmed is None
    assert [incident.what for incident in answer.incidents] == ["stream_lost"]
    assert answer.totals == {"handed": 1, "incidents": 1}
    assert answer.bound.by == "head" and answer.open


async def test_a_citation_of_what_its_citer_was_never_handed_is_kept_and_labelled(kernel):
    alice, bob = await spawn(kernel, "alice"), await spawn(kernel, "bob")
    unseen = (await send(kernel, alice, "@alice", "a note to self"))["ref"]
    cited = (await send(kernel, bob, "@alice", "I rest on that", based_on=[unseen]))["ref"]

    (declared,) = lineage(kernel, cited).declared

    assert declared.ref == unseen and isinstance(declared.exposure, Unknown)
    assert declared.exposure.handed == () and declared.exposure.totals["handed"] == 0
    assert declared.exposure.bound.by == "commit"


async def test_a_ranged_citation_says_whether_its_lines_were_shown(kernel):
    alice, bob = await spawn(kernel, "alice"), await spawn(kernel, "bob")
    body = await stored(kernel, "one\ntwo\nthree\n")
    sent = (await send(kernel, alice, "@bob", "see the body", body=body))["ref"]
    handed = result_of(await kernel.submit(kernel.runtime, "delivery.offer", {"agent": "bob"}))
    await start_turn(kernel, "bob")
    await confirm(kernel, "bob", handed["input"], evidence="command_lifecycle")
    gist_only = (await send(kernel, bob, "@alice", "lines two to three", based_on=[f"{sent}#L2-3"]))["ref"]
    read = await kernel.submit(bob, "message.read", {"bodies": True, "after": 0}, native=tool("t1"))
    result_of(read)
    await done(kernel, "bob", "t1")
    whole = (await send(kernel, bob, "@alice", "and again", based_on=[f"{sent}#L2-3"]))["ref"]

    (before,) = lineage(kernel, gist_only).declared
    (after,) = lineage(kernel, whole).declared

    assert isinstance(before.exposure, Seen) and before.lines_shown is False
    assert [shown.form for edge in before.exposure.edges for shown in edge.shown] == ["gist"]
    assert isinstance(after.exposure, Seen) and after.lines_shown is True


async def test_the_bound_compares_confirmations_and_calls_on_the_report_stream(kernel):
    """A read and a cited write chosen by one model call are siblings: the tool plane commits the read's offer before
    the harness's report of that call lands, and the read's result comes back to it only after."""
    alice, bob = await spawn(kernel, "alice"), await spawn(kernel, "bob")
    sent = (await send(kernel, alice, "@bob", "read me"))["ref"]
    await start_turn(kernel, "bob")
    result_of(await kernel.submit(bob, "message.read", {}, native=tool("t1")))
    await call(kernel, "bob", "c1", "t1", "t2")
    write = {"to": "@alice", "gist": "on it", "based_on": [sent]}
    cited = result_of(await kernel.submit(bob, "message.send", write, native=tool("t2")))["ref"]
    await done(kernel, "bob", "t1", "t2")

    by_call = exposure(kernel, "bob", sent, before=cited)
    by_head = exposure(kernel, "bob", sent)

    assert isinstance(by_call, Unknown) and by_call.bound.by == "call"
    assert [offer.how for offer in by_call.handed] == ["read"]
    assert isinstance(by_head, Seen)


async def test_a_shared_anchor_joins_the_script_and_counts_its_ops(kernel):
    alice, bob = await spawn(kernel, "alice"), await spawn(kernel, "bob")
    await send(kernel, alice, "@bob", "one")
    await start_turn(kernel, "bob")
    script = {"callId": "exec-1"}
    await report(kernel, "bob", "item", kind="tool", phase="started", gist="a script", native_id="exec-1")
    first = result_of(await kernel.submit(bob, "message.send", {"to": "@alice", "gist": "a"}, native=script))["ref"]
    second = result_of(await kernel.submit(bob, "message.send", {"to": "@alice", "gist": "b"}, native=script))["ref"]

    joined = [lineage(kernel, ref).made for ref in (first, second)]

    assert [(made.anchor and (made.anchor.key, made.anchor.ops), made.call) for made in joined] == [
        (("callId", 2), None),
        (("callId", 2), None),
    ]
    assert all(made.item is not None for made in joined)


async def test_a_tool_links_to_a_model_call_only_through_ids_both_hold(kernel):
    """Claude joins its call, Codex reaches the item only, our own id joins nothing, and nothing joins by order."""
    await spawn(kernel, "alice")
    bob = await spawn(kernel, "bob")
    await start_turn(kernel, "bob")
    await report(kernel, "bob", "model.call", call_id="c1")
    await report(kernel, "bob", "item", kind="tool", phase="started", gist="claude", native_id="t1", call_id="c1")
    await report(kernel, "bob", "item", kind="tool", phase="started", gist="codex", native_id="exec-1")
    sends = [
        ({"claudecode/toolUseId": "t1"}, "claude"),
        ({"callId": "exec-1"}, "codex"),
        ({"platoon-harness/callId": "ours"}, "ph"),
        (None, "none"),
    ]
    refs = [
        result_of(await kernel.submit(bob, "message.send", {"to": "@alice", "gist": gist}, native=native))["ref"]
        for native, gist in sends
    ]

    made = [lineage(kernel, ref).made for ref in refs]

    assert [(m.call is not None, m.item is not None, m.anchor and m.anchor.key) for m in made] == [
        (True, True, "claudecode/toolUseId"),
        (False, True, "callId"),
        (False, False, "platoon-harness/callId"),
        (False, False, None),
    ]
    assert [lineage(kernel, ref).bound.by for ref in refs] == ["call", "commit", "commit", "commit"]


async def test_seen_lists_each_compaction_since_as_forgot_kept_or_unsaid(kernel):
    alice, _ = await spawn(kernel, "alice"), await spawn(kernel, "bob")
    sent = (await send(kernel, alice, "@bob", "keep this"))["ref"]
    handed = result_of(await kernel.submit(kernel.runtime, "delivery.offer", {"agent": "bob"}))
    await start_turn(kernel, "bob")
    await confirm(kernel, "bob", handed["input"], evidence="message_start", native_id="entry-7")
    await report(kernel, "bob", "compacted", forgotten=await stored(kernel, json.dumps(["entry-3"])))
    await report(kernel, "bob", "compacted")
    await report(kernel, "bob", "compacted", forgotten=await stored(kernel, json.dumps(["entry-7"])))

    answer = exposure(kernel, "bob", sent)

    assert isinstance(answer, Seen)
    assert [mark.mark for mark in answer.edges[0].compactions or ()] == ["kept", "unsaid", "forgot"]


async def test_a_compaction_never_undoes_seen(kernel):
    alice, _ = await spawn(kernel, "alice"), await spawn(kernel, "bob")
    sent = (await send(kernel, alice, "@bob", "forget me"))["ref"]
    handed = result_of(await kernel.submit(kernel.runtime, "delivery.offer", {"agent": "bob"}))
    await start_turn(kernel, "bob")
    await confirm(kernel, "bob", handed["input"], evidence="message_start", native_id="e1")
    await report(kernel, "bob", "compacted", forgotten=await stored(kernel, json.dumps(["e1"])))

    answer = exposure(kernel, "bob", sent)

    assert isinstance(answer, Seen) and answer.total == 1
    assert [mark.mark for mark in answer.edges[0].compactions or ()] == ["forgot"]


async def test_a_gap_qualifies_answers_after_where_it_began(kernel, ada):
    """A takeover is recorded where its hold begins, and a crash_window names the start of the turn it cut."""
    alice = await spawn(kernel, "alice")
    await spawn(kernel, "bob", ready={"resume": True})
    sent = (await send(kernel, alice, "@bob", "while held"))["ref"]
    result_of(await kernel.submit(ada, "agent.takeover", {"agent": "@bob"}))
    inside = (await send(kernel, alice, "@alice", "meanwhile"))["ref"]
    await start_turn(kernel, "bob")
    began = of_type(kernel, "turn.started")[-1].seq
    await report(kernel, "bob", "exited", reason="it crashed")
    crashed = of_type(kernel, "gap.recorded")[-1]

    held = exposure(kernel, "bob", sent, before=inside)

    assert isinstance(held, Unknown) and [incident.what for incident in held.incidents] == ["takeover"]
    assert (crashed.data["what"], crashed.data["since"]) == ("crash_window", began)
    whole = exposure(kernel, "bob", sent)
    assert isinstance(whole, Unknown)
    assert [(incident.what, incident.began) for incident in whole.incidents] == [
        ("crash_window", began),
        ("takeover", held.incidents[0].began),
    ]


async def test_only_gaps_content_could_come_through_are_reasons_for_unknown(kernel):
    alice, _ = await spawn(kernel, "alice"), await spawn(kernel, "bob")
    sent = (await send(kernel, alice, "@alice", "never handed"))["ref"]
    await report(kernel, "bob", "compacted")
    await report(kernel, "bob", "gap", what="usage_lower_bound")
    await report(kernel, "bob", "gap", what="hidden_call")

    answer = exposure(kernel, "bob", sent)

    assert isinstance(answer, Unknown) and [incident.what for incident in answer.incidents] == ["hidden_call"]
    assert all(incident.carries for incident in answer.incidents)


def facts(**given: Any) -> Facts:
    standing = [Coverage(surface=surface, declared="observed") for surface in SURFACES]
    nothing = {"edges": [], "handed": [], "standing": standing, "incidents": [], "gaps": 0, "older_offers": 0}
    return Facts(**{**nothing, **given})


def test_not_seen_needs_proved_coverage_and_no_gap_below_the_bound():
    bound = Bound(by="commit", seq=9)
    gap = Incident(ref="agent/bob@3", what="stream_lost", plane="control", began=4, carries=True)

    def decided(proved: tuple[str, ...] = SURFACES, **given: Any) -> str:
        return decide(facts(**given), proved=proved, bound=bound, head=10, open=False).answer  # type: ignore[arg-type]

    assert decided() == "not_seen"
    assert decided(proved=SURFACES[1:]) == "unknown"
    assert decided(incidents=[gap], gaps=1) == "unknown"
    assert decided(older_offers=1) == "unknown"
    proved = decide(facts(), proved=SURFACES, bound=bound, head=10, open=False)  # type: ignore[arg-type]
    assert isinstance(proved, NotSeen) and proved.proved == SURFACES


async def test_no_agent_answers_not_seen_at_m2(kernel):
    """No check proves a surface yet, so even an agent whose driver declares every one observed is `unknown`."""
    declared = {"coverage": dict.fromkeys(SURFACES, "observed")}
    alice = await spawn(kernel, "alice")
    for name, ready in (("sure", declared), ("bare", {})):
        await spawn(kernel, name, ready=ready)
    sent = (await send(kernel, alice, "@alice", "to nobody else"))["ref"]

    answers = [exposure(kernel, name, sent) for name in ("sure", "bare")]

    assert all(isinstance(answer, Unknown) and answer.handed == () for answer in answers)
    assert [len(answer.standing) for answer in answers if isinstance(answer, Unknown)] == [7, 7]
    assert [coverage.declared for coverage in answers[0].standing] == ["observed"] * 7  # type: ignore[union-attr]
    assert [coverage.declared for coverage in answers[1].standing] == [None] * 7  # type: ignore[union-attr]


async def test_the_queries_ask_about_events_and_refuse_a_range_a_hash_or_a_person(kernel, ada):
    alice = await spawn(kernel, "alice")
    sent = (await send(kernel, alice, "@alice", "hi"))["ref"]
    body = await stored(kernel, "text")

    refused = [
        kernel.query(kernel.runtime, op, {"ref": ref, **({"agent": "alice"} if op == "exposure" else {})})
        for op in PROVENANCE
        for ref in (f"{sent}#L1-1", body, "nothing@9", "not a ref")
    ]
    person = kernel.query(kernel.runtime, "exposure", {"agent": "ada", "ref": sent})
    nobody = kernel.query(kernel.runtime, "exposure", {"agent": "zed", "ref": sent})

    assert [refusal(outcome).code for outcome in refused] == ["invalid", "invalid", "not_found", "invalid"] * 4
    assert f"ask by {sent}" in str(refusal(refused[0]).detail)
    assert "the event that carries it" in str(refusal(refused[1]).detail)
    assert (refusal(person).code, refusal(nobody).code) == ("invalid", "not_found")
    assert "no evidence" in str(refusal(person).detail)


async def test_an_answer_says_its_head_and_whether_its_turn_was_open(kernel):
    alice = await spawn(kernel, "alice")
    await start_turn(kernel, "alice")
    in_turn = (await send(kernel, alice, "@alice", "in a turn"))["ref"]
    open_now = lineage(kernel, in_turn)
    await end_turn(kernel, "alice")
    ended = lineage(kernel, in_turn)
    outside = lineage(kernel, (await send(kernel, alice, "@alice", "out of one"))["ref"])

    assert (open_now.open, ended.open, outside.open) == (True, False, False)
    assert open_now.head < ended.head < outside.head == kernel.head


# Lineage and uses.


async def test_lineage_labels_every_edge_by_its_kind(kernel):
    """Declared, cause and ancestry from the event itself, and observed in its maker's history."""
    lead = await spawn(kernel, "lead", role="lead")
    await channel(kernel, "notes", kind="board")
    first = result_of(await kernel.submit(lead, "board.post", {"board": "notes", "name": "spec", "gist": "v1"}))["ref"]
    asked = (await send(kernel, kernel.runtime, "@lead", "a question"))["ref"]
    revise = {"board": "notes", "name": "spec", "gist": "v2", "expected_version": 1, "based_on": [asked]}
    second = result_of(await kernel.submit(lead, "board.revise", revise))["ref"]
    reply = (await send(kernel, lead, "@lead", "answered", reply_to=asked))["ref"]

    revised = lineage(kernel, second)
    replied = lineage(kernel, reply)

    assert [(edge.kind, edge.ref) for edge in revised.declared] == [("declared", asked)]
    assert [(edge.kind, edge.ref, edge.maker) for edge in revised.ancestry] == [("ancestry", first, "agent:lead")]
    assert [(edge.kind, edge.ref) for edge in replied.cause] == [("cause", asked)]
    assert revised.made.maker == "agent:lead" and revised.made.call is None and revised.made.anchor is None


async def test_a_declared_edge_carries_its_citer_s_exposure(kernel):
    alice, bob = await spawn(kernel, "alice"), await spawn(kernel, "bob")
    sent = (await send(kernel, alice, "@bob", "the plan"))["ref"]
    handed = result_of(await kernel.submit(kernel.runtime, "delivery.offer", {"agent": "bob"}))
    await start_turn(kernel, "bob")
    await confirm(kernel, "bob", handed["input"], evidence="message_start")
    cited = (await send(kernel, bob, "@alice", "per the plan", based_on=[sent]))["ref"]
    person = (await send(kernel, kernel.runtime, "@alice", "also per the plan", based_on=[sent]))["ref"]

    (by_agent,) = lineage(kernel, cited).declared
    (by_runtime,) = lineage(kernel, person).declared

    assert isinstance(by_agent.exposure, Seen) and by_agent.exposure.edges[0].how == "wake"
    assert by_runtime.exposure is None and by_runtime.maker == "agent:alice"


async def test_lineage_pages_one_history_of_observed_edges_and_gaps_with_true_totals(kernel):
    alice, bob = await spawn(kernel, "alice"), await spawn(kernel, "bob")
    for n in range(40):
        await send(kernel, alice, "@bob", f"note {n}")
        result_of(await kernel.submit(bob, "message.read", {}, native=tool(f"t{n}")))
        if n % 2 == 0:
            await done(kernel, "bob", f"t{n}")
        if n % 10 == 0:
            await report(kernel, "bob", "gap", what="unknown_update")
    final = (await send(kernel, bob, "@alice", "read them all"))["ref"]

    first = lineage(kernel, final)
    second = lineage(kernel, final, after=first.cursor)

    assert first.totals == {"handed": 40, "confirmed": 20, "unconfirmed": 20, "gaps": 4}
    rows = [*(first.history or ()), *(second.history or ())]
    assert len(first.history or ()) == 32 and len(rows) == 44 and second.cursor is None
    positions = [row.seq if row.kind == "observed" else row.began for row in rows]
    assert positions == sorted(positions, reverse=True)
    assert len({row.ref for row in rows}) == 44


async def test_uses_finds_who_cited_it_what_followed_and_who_was_handed_it(kernel):
    lead = await spawn(kernel, "lead", role="lead")
    bob = await spawn(kernel, "bob", by=lead)
    await channel(kernel, "notes", kind="board", delivery="wake")
    posted = result_of(await kernel.submit(lead, "board.post", {"board": "notes", "name": "spec", "gist": "v1"}))
    handed = result_of(await kernel.submit(kernel.runtime, "delivery.offer", {"agent": "bob"}))
    await start_turn(kernel, "bob")
    await confirm(kernel, "bob", handed["input"], evidence="message_start")
    cited = (await send(kernel, bob, "@lead", "read it", based_on=[posted["ref"]]))["ref"]
    revise = {"board": "notes", "name": "spec", "gist": "v2", "expected_version": 1}
    second = result_of(await kernel.submit(lead, "board.revise", revise))["ref"]

    found = uses(kernel, posted["ref"])

    announce = next(event for event in of_type(kernel, "message.sent") if event.cause)
    assert [(row.kind, getattr(row, "ref", None)) for row in found.rows] == [
        ("cause", ref_of(announce)),
        ("observed", None),
        ("declared", cited),
        ("ancestry", second),
    ]
    observed = found.rows[1]
    assert observed.kind == "observed" and (observed.agent, observed.confirmed) == ("bob", True)  # type: ignore[union-attr]
    assert found.totals == {"declared": 1, "cause": 1, "ancestry": 1, "observed": 1}


async def test_uses_pages_oldest_first_with_a_cursor(kernel):
    alice = await spawn(kernel, "alice")
    sent = (await send(kernel, alice, "@alice", "cite me"))["ref"]
    for n in range(40):
        await send(kernel, alice, "@alice", f"citing {n}", based_on=[sent])

    first = uses(kernel, sent)
    second = uses(kernel, sent, after=first.cursor)

    assert len(first.rows) == 32 and len(second.rows) == 8 and second.cursor is None
    seqs = [row.seq for row in (*first.rows, *second.rows)]
    assert seqs == sorted(seqs) and len(set(seqs)) == 40
    assert first.totals["declared"] == 40


# Contributors.


async def test_contributors_name_each_maker_with_the_kinds_that_reached_it(kernel, ada):
    lead = await spawn(kernel, "lead", role="lead")
    worker = await spawn(kernel, "worker", by=lead)
    await channel(kernel, "work", kind="queue", delivery="pull")
    added = result_of(await kernel.submit(lead, "task.add", {"queue": "work", "gist": "do it"}))["ref"]
    asked = (await send(kernel, ada, "@worker", "how about this way"))["ref"]
    result_of(await kernel.submit(worker, "task.claim", {"queue": "work"}))
    done_task = {"queue": "work", "gist": "done", "based_on": [asked]}
    result = result_of(await kernel.submit(worker, "task.complete", done_task))["ref"]

    found = contributors(kernel, result)

    assert [(row.maker, row.kinds) for row in found.rows] == [
        ("agent:worker", ("cause", "ancestry")),
        ("human:ada", ("declared",)),
        ("agent:lead", ("ancestry",)),
    ]
    assert found.rows[1].unproved is None and found.rows[0].unproved == SURFACES
    assert found.rows[2].first == added and found.walked == 4 and not found.stopped_short


async def test_contributors_list_makers_only_handed_apart_and_walk_no_further(kernel):
    alice, bob, carol = await spawn(kernel, "alice"), await spawn(kernel, "bob"), await spawn(kernel, "carol")
    await send(kernel, carol, "@bob", "a hint nobody cites")
    result_of(await kernel.submit(kernel.runtime, "delivery.offer", {"agent": "bob"}))
    cited = (await send(kernel, alice, "@alice", "the cited one"))["ref"]
    outcome = (await send(kernel, bob, "@alice", "my answer", based_on=[cited]))["ref"]

    found = contributors(kernel, outcome)

    assert [row.maker for row in found.rows] == ["agent:bob", "agent:alice"]
    assert [(row.maker, row.to, row.first) for row in found.handed_only] == [
        ("agent:carol", ("agent:bob",), "context/bob@1")
    ]


async def test_contributors_stop_at_their_cap_and_say_so(kernel, monkeypatch):
    from platoon_harness.primitives import provenance

    monkeypatch.setattr(provenance, "WALK_LIMIT", 5)
    alice = await spawn(kernel, "alice")
    ref = (await send(kernel, alice, "@alice", "first"))["ref"]
    for n in range(8):
        ref = (await send(kernel, alice, "@alice", f"after {n}", based_on=[ref]))["ref"]

    found = contributors(kernel, ref)

    assert (found.walked, found.stopped_short) == (5, True)
    assert [(row.maker, row.reached) for row in found.rows] == [("agent:alice", 5)]


REPO = {"name": "app", "top": "/work/app", "prefix": "", "head": "f" * 40, "branch": "main", "repository": "/work/.git"}
ROOT, CHILD, CITED = "a" * 40, "b" * 40, "c" * 40


def commit(sha: str, parents: list[str], made_in: str | None, informed_by: list[dict[str, Any]]) -> dict[str, Any]:
    fields = {"subject": sha[:4], "author": "a", "branch": None, "added": 1, "removed": 0, "files": 1}
    return {"sha": sha, "parents": parents, "made_in": made_in, "informed_by": informed_by, **fields}


async def committed(kernel: Kernel, *looks: list[dict[str, Any]]) -> dict[str, str]:
    """Each look's commits recorded as `alice`'s look finds them, and the ref of each by its sha."""
    await spawn(kernel, "alice")
    for commits in looks:
        report = {"agent": "alice", "workspace": "@alice", "commits": commits}
        result_of(await kernel.submit(kernel.runtime, "repo.report", report))
    return {event.data["sha"]: ref_of(event) for event in of_type(kernel, "repo.committed")}


@pytest.mark.parametrize("repo", [REPO])
async def test_ancestry_is_an_object_s_previous_version_and_a_commit_s_parents(kernel):
    refs = await committed(kernel, [commit(ROOT, [], "@alice", [])], [commit(CHILD, [ROOT, "e" * 40], "@alice", [])])
    alice = Principal(id="agent:alice")
    await channel(kernel, "notes", kind="board")
    await channel(kernel, "work", kind="queue")
    first = result_of(await kernel.submit(alice, "board.post", {"board": "notes", "name": "spec", "gist": "v1"}))
    revise = {"board": "notes", "name": "spec", "gist": "v2", "expected_version": 1}
    second = result_of(await kernel.submit(alice, "board.revise", revise))
    result_of(await kernel.submit(alice, "task.add", {"queue": "work", "gist": "do it"}))
    claimed = result_of(await kernel.submit(alice, "task.claim", {"queue": "work"}))
    done_task = result_of(await kernel.submit(alice, "task.complete", {"queue": "work", "gist": "done"}))

    ancestors = {ref: lineage(kernel, ref).ancestry for ref in (second["ref"], done_task["ref"], refs[CHILD])}

    assert [step.ref for step in ancestors[second["ref"]]] == [first["ref"]]
    assert [step.ref for step in ancestors[done_task["ref"]]] == ["task/work/1@2"] and claimed["ref"] == "task/work/1@1"
    assert [(step.ref, step.sha) for step in ancestors[refs[CHILD]]] == [(refs[ROOT], ROOT), (None, "e" * 40)]
    assert all(step.kind == "ancestry" for steps in ancestors.values() for step in steps)
    assert lineage(kernel, first["ref"]).ancestry == ()


@pytest.mark.parametrize("repo", [REPO])
async def test_git_ancestry_is_its_own_kind_and_a_commit_is_its_workspace_s(kernel):
    """A commit's parents are ancestry and its `Informed-By` trailers its declaration, and the two never merge."""
    trailers = [{"written": CITED[:8], "sha": CITED}]
    first = [commit(ROOT, [], "@alice", []), commit(CITED, [], None, [])]
    refs = await committed(kernel, first, [commit(CHILD, [ROOT], "@alice", trailers)])

    found = lineage(kernel, refs[CHILD])
    reached = contributors(kernel, refs[CHILD])
    forward = uses(kernel, refs[ROOT])

    assert found.made.maker == "agent:alice" and found.made.call is None and found.made.anchor is None
    assert [(edge.kind, edge.ref, edge.sha) for edge in found.ancestry] == [("ancestry", refs[ROOT], ROOT)]
    assert [(edge.kind, edge.ref, edge.maker) for edge in found.declared] == [("declared", refs[CITED], None)]
    assert [(row.maker, row.kinds) for row in reached.rows] == [
        ("agent:alice", ("ancestry",)),
        (None, ("declared",)),
    ]
    assert [(row.kind, getattr(row, "sha", None)) for row in forward.rows] == [("ancestry", CHILD)]


@pytest.mark.parametrize("repo", [REPO])
async def test_an_unresolvable_trailer_is_kept_and_labelled_never_in_based_on(kernel):
    trailers = [
        {"written": CITED[:8], "sha": CITED},
        {"written": "the spec", "sha": None},
        {"written": "e" * 40, "sha": "e" * 40},
    ]
    many = commit(CHILD, [ROOT], "@alice", trailers) | {"informed_by_total": 20}
    refs = await committed(kernel, [commit(ROOT, [], "@alice", []), commit(CITED, [], None, [])], [many])

    found = lineage(kernel, refs[CHILD])

    assert of_type(kernel, "repo.committed")[-1].based_on == (refs[CITED],)
    assert [edge.ref for edge in found.declared] == [refs[CITED]]
    assert [(value.written, value.sha) for value in found.unresolved] == [("the spec", None), ("e" * 40, "e" * 40)]
    assert found.cut == 17


async def test_a_compaction_marks_only_by_the_delivered_native_id(kernel):
    """A read's offer is confirmed by its tool item, whose id names no input a compaction can forget, so it is unsaid,
    though the compaction names that very id."""
    alice, bob = await spawn(kernel, "alice"), await spawn(kernel, "bob")
    sent = (await send(kernel, alice, "@bob", "both ways"))["ref"]
    handed = result_of(await kernel.submit(kernel.runtime, "delivery.offer", {"agent": "bob"}))
    await start_turn(kernel, "bob")
    await confirm(kernel, "bob", handed["input"], evidence="message_start", native_id="entry-1")
    result_of(await kernel.submit(bob, "message.read", {"after": 0}, native=tool("t1")))
    await done(kernel, "bob", "t1")
    await report(kernel, "bob", "compacted", forgotten=await stored(kernel, json.dumps(["entry-1", "t1"])))

    answer = exposure(kernel, "bob", sent)

    assert isinstance(answer, Seen)
    assert [(edge.how, [mark.mark for mark in edge.compactions or ()]) for edge in answer.edges] == [
        ("wake", ["forgot"]),
        ("read", ["unsaid"]),
    ]


@pytest.mark.parametrize("op", PROVENANCE)
def test_the_provenance_queries_are_no_agent_s_tool(op):
    from platoon_harness.kernel import registry

    operation = registry(PRIMITIVES)[op]
    assert operation.query and not operation.tool


def test_provenance_reads_no_annotation():
    """Credit is an annotation, and no query, no view and nothing an agent can reach opens the file that holds them."""
    import platoon_harness

    sdk = Path(platoon_harness.__file__).parent
    for part in ("kernel", "primitives", "tools", "runtime", "drivers"):
        for path in (sdk / part).rglob("*.py"):
            text = path.read_text()
            assert "annotations.sqlite" not in text and "annotations import" not in text, path


# The property.

ANCHORS = ("t1", "t2", "t3")
CARRYING = {
    "stream_lost",
    "native_child_unattributed",
    "unknown_update",
    "hidden_call",
    "crash_window",
    "takeover",
    "workspace_unobserved",
}
steps = st.lists(
    st.one_of(
        st.tuples(st.just("send"), st.none()),
        st.tuples(st.just("wake"), st.none()),
        st.tuples(st.just("deliver"), st.sampled_from(["n1", "n2", None])),
        st.tuples(st.just("read"), st.sampled_from(ANCHORS)),
        st.tuples(st.just("item"), st.sampled_from(ANCHORS)),
        st.tuples(st.just("call"), st.tuples(st.sampled_from(["c1", "c2"]), st.sampled_from(ANCHORS))),
        st.tuples(st.just("compact"), st.sampled_from([None, ["n1"], ["n2", "n1"]])),
        st.tuples(st.just("gap"), st.sampled_from(["stream_lost", "usage_lower_bound", "hidden_call"])),
        st.tuples(st.just("cite"), st.sampled_from(ANCHORS)),
        st.tuples(st.just("turn"), st.none()),
    ),
    max_size=24,
)


def brute(kernel: Kernel, agent: str, ref: str, before: str | None) -> tuple[Any, ...]:
    """Exposure read off the whole journal by its rules alone, with no view."""
    events = events_of(kernel)
    by_ref = {ref_of(event): event for event in events}
    bound = ("head", events[-1].seq + 1)
    if before is not None:
        bounding = by_ref[before]
        bound = ("commit", bounding.seq)
        if bounding.actor == f"agent:{agent}" and bounding.native:
            anchor = next(iter(bounding.native.values()))
            ours = [event for event in events if event.agent == agent]
            items = [e for e in ours if e.type == "item.recorded" and e.data.get("native_id") == anchor]
            call_id = next((e.data["call_id"] for e in items if e.data["kind"] == "tool" and e.data["call_id"]), None)
            calls = [e for e in ours if e.type == "model.called" and e.model and e.model.call_id == call_id]
            bound = ("call", calls[0].seq) if call_id and calls else bound
    limit = bound[1]
    offers = [
        event
        for event in events
        if event.type == "context.offered"
        and event.agent == agent
        and event.seq < limit
        and any(item["ref"].partition("#")[0] == ref for item in event.data["items"])
    ]
    confirmed = {
        event.data["input"]: event
        for event in reversed(events)
        if event.type == "context.delivered" and event.agent == agent and event.seq < limit
    }
    seen = [offer for offer in offers if offer.seq in confirmed]
    if seen:
        marks = []
        for offer in seen:
            confirmation = confirmed[offer.seq]
            compactions = [
                event
                for event in events
                if event.type == "context.compacted" and event.agent == agent and confirmation.seq < event.seq < limit
            ]
            for compaction in compactions:
                held = compaction.data["forgotten"]
                forgotten = None if held is None else json.loads(kernel.get_body(held.removeprefix("sha256:")))
                native = confirmation.data["native_id"]
                by_id = confirmation.data["evidence"] != "tool_item" and native is not None and forgotten is not None
                marks.append((offer.seq, "unsaid" if not by_id else "forgot" if native in forgotten else "kept"))
        return ("seen", bound, [offer.seq for offer in seen], marks)
    gaps = [
        ref_of(event)
        for event in events
        if event.type == "gap.recorded"
        and event.agent == agent
        and (event.seq if event.data["since"] is None else event.data["since"]) < limit
        and event.data["what"] in CARRYING
    ]
    return ("unknown", bound, [offer.seq for offer in offers], sorted(gaps))


def answered(kernel: Kernel, agent: str, ref: str, before: str | None) -> tuple[Any, ...]:
    answer = exposure(kernel, agent, ref, before)
    bound = (answer.bound.by, answer.bound.seq)
    if isinstance(answer, Seen):
        marks = [(edge.seq, mark.mark) for edge in answer.edges for mark in edge.compactions or ()]
        return ("seen", bound, [edge.seq for edge in answer.edges], marks)
    assert isinstance(answer, Unknown)
    gaps = sorted(incident.ref for incident in answer.incidents)
    return ("unknown", bound, [offer.seq for offer in answer.handed], gaps)


@settings(max_examples=40, deadline=None)
@given(script=steps)
def test_exposure_agrees_with_a_brute_force_reading_of_the_journal(tmp_path_factory, script) -> None:
    folder = tmp_path_factory.mktemp("exposure") / "session"

    async def body() -> None:
        kernel = Kernel.open(folder, clock=ManualClock(1000.0), extensions=PRIMITIVES)
        result_of(await kernel.submit(kernel.runtime, "session.open", {"roles": ROLES}))
        await grant(kernel, "agent")
        alice, bob = await spawn(kernel, "alice"), await spawn(kernel, "bob")
        sent: list[str] = []
        cited: list[str] = []
        handed: list[int] = []
        for step, value in script:
            if step == "send":
                sent.append((await send(kernel, alice, "@bob", f"note {len(sent)}"))["ref"])
            elif step == "wake":
                offer = (await kernel.submit(kernel.runtime, "delivery.offer", {"agent": "bob"})).result
                handed += [offer["input"]] if offer else []
            elif step == "deliver" and handed:
                await confirm(kernel, "bob", handed.pop(0), evidence="message_start", native_id=value)
            elif step == "read":
                await kernel.submit(bob, "message.read", {"after": 0}, native=tool(value))
            elif step == "item":
                await done(kernel, "bob", value)
            elif step == "call":
                await call(kernel, "bob", *value)
            elif step == "compact":
                forgotten = None if value is None else await stored(kernel, json.dumps(value))
                await report(kernel, "bob", "compacted", forgotten=forgotten)
            elif step == "gap":
                await report(kernel, "bob", "gap", what=value)
            elif step == "cite" and sent:
                write = {"to": "@alice", "gist": "per that", "based_on": [sent[-1]]}
                cited.append(result_of(await kernel.submit(bob, "message.send", write, native=tool(value)))["ref"])
            elif step == "turn":
                in_turn = result_of(kernel.query(kernel.runtime, "agent.status", {"agent": "bob"}))["turn"]
                await (end_turn(kernel, "bob") if in_turn else start_turn(kernel, "bob", f"t{kernel.head}"))
        try:
            for ref in sent[-3:]:
                for before in (None, *cited[-2:]):
                    assert answered(kernel, "bob", ref, before) == brute(kernel, "bob", ref, before)
        finally:
            kernel.close()

    asyncio.run(body())
