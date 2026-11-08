"""Spans: each turn of an agent cut after each model call that chose a write of content, as the record joins them, and
the `spans` query of architecture section 11."""

import asyncio
import shutil
from typing import Any, Literal

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from platoon_harness import Session, Team
from platoon_harness.kernel import Kernel, ManualClock, Principal
from platoon_harness.primitives import PRIMITIVES, Spans
from platoon_harness.testing import AskModel, FakeModel, ToolCall

from ..runtime import support as running
from .support import (
    ROLES,
    agent,
    channel,
    end_turn,
    enroll,
    grant,
    of_type,
    refusal,
    report,
    result_of,
    settle_effects,
    spawn,
    start,
    start_turn,
)
from .test_lifecycle import written_at_v1

Write = Literal["joined", "unanchored", "unnamed"]
"""How a write's tool call reaches the model call that chose it: `joined` by its op's id and a tool item that holds it
and names the call, `unanchored` with no id on its op, and `unnamed` with a tool item that names no call."""


def spans(kernel: Kernel, name: str = "w", after: str | None = None) -> Spans:
    return Spans.model_validate(result_of(kernel.query(kernel.runtime, "spans", {"agent": name, "after": after})))


def ref_of(event: Any) -> str:
    return f"{event.stream}@{event.version}"


def rows(found: Spans) -> list[tuple[str, str, tuple[str, ...]]]:
    return [(span.first, span.ref, span.writes) for span in found.spans]


async def team(kernel: Kernel) -> Principal:
    """`w`, whose turns are cut, and a peer it writes to."""
    await spawn(kernel, "peer")
    return await spawn(kernel, "w")


async def called(kernel: Kernel, call_id: str | None = None, purpose: str | None = None) -> str:
    """A model call `w`'s harness reports, by the ref of its `model.called`."""
    await report(kernel, "w", "model.call", call_id=call_id, purpose=purpose)
    return ref_of(of_type(kernel, "model.called")[-1])


async def ran(
    kernel: Kernel, call_id: str | None, tool: str, op: str, args: dict[str, Any], how: Write = "joined"
) -> Any:
    """An op `w` runs by the tool call `tool` of the model call `call_id`, after the tool item its harness reports of
    that tool call: the op's result."""
    item = {"kind": "tool", "phase": "started", "gist": op, "native_id": tool}
    await report(kernel, "w", "item", **item, call_id=None if how == "unnamed" else call_id)
    native = None if how == "unanchored" else {"claudecode/toolUseId": tool}
    return result_of(await kernel.submit(agent("w"), op, args, native=native))


async def wrote(kernel: Kernel, call_id: str | None, gist: str, how: Write = "joined") -> str:
    """A message `w` sends by a tool call of the model call `call_id`: the message's ref."""
    return (await ran(kernel, call_id, f"tool-{gist}", "message.send", {"to": "@peer", "gist": gist}, how))["ref"]


async def test_a_turn_is_cut_after_each_call_that_chose_a_write_and_a_trailing_piece_joins_the_span_before_it(kernel):
    await team(kernel)
    await start_turn(kernel, "w")
    c1, c2 = await called(kernel, "c1"), await called(kernel, "c2")
    one = await wrote(kernel, "c2", "one")
    c3 = await called(kernel, "c3")
    await called(kernel, "c4")
    two = await wrote(kernel, "c4", "two")
    c5 = await called(kernel, "c5")
    await end_turn(kernel, "w")

    assert rows(spans(kernel)) == [(c1, c2, (one,)), (c3, c5, (two,))]


async def test_a_turn_with_writes_from_one_call_or_none_is_one_span(kernel):
    await team(kernel)
    await start_turn(kernel, "w", "t1")
    c1, c2 = await called(kernel, "c1"), await called(kernel, "c2")
    await end_turn(kernel, "w")
    await start_turn(kernel, "w", "t2")
    c3 = await called(kernel, "c3")
    one, two = await wrote(kernel, "c3", "one"), await wrote(kernel, "c3", "two")
    c4 = await called(kernel, "c4")
    await end_turn(kernel, "w")

    assert rows(spans(kernel)) == [(c1, c2, ()), (c3, c4, (one, two))]


async def test_only_a_write_the_record_joins_to_its_call_cuts_a_turn(kernel):
    """A write whose op names no tool call, or whose tool item names no model call, is tied to no call, so it cuts
    nothing and no span lists it: nothing places it by order."""
    await team(kernel)
    await start_turn(kernel, "w")
    c1 = await called(kernel, "c1")
    one = await wrote(kernel, "c1", "one")
    c2 = await called(kernel, "c2")
    await wrote(kernel, "c2", "unanchored", how="unanchored")
    await called(kernel, "c3")
    await wrote(kernel, "c3", "unnamed", how="unnamed")
    await called(kernel, "c4")
    four = await wrote(kernel, "c4", "four")
    c5 = await called(kernel, "c5")
    await end_turn(kernel, "w")

    assert rows(spans(kernel)) == [(c1, c1, (one,)), (c2, c5, (four,))]


async def test_only_the_eight_writes_of_content_an_agent_makes_itself_cut_a_turn(kernel):
    """A claim or a read makes no product, an announce of a write carries that write and is none of its own, and a
    finish out of a turn is its agent's end."""
    await team(kernel)
    await channel(kernel, "notes", kind="board", delivery="wake")
    await channel(kernel, "tasks", kind="queue", delivery="wake")
    result_of(await kernel.submit(kernel.runtime, "task.add", {"queue": "tasks", "gist": "do it"}))
    await start_turn(kernel, "w")
    c1 = await called(kernel, "c1")
    await ran(kernel, "c1", "claim", "task.claim", {"queue": "tasks"})
    await ran(kernel, "c1", "read", "message.read", {"channel": "@w"})
    c2 = await called(kernel, "c2")
    posted = await ran(kernel, "c2", "post", "board.post", {"board": "notes", "name": "spec", "gist": "v1"})
    added = await ran(kernel, "c2", "add", "task.add", {"queue": "tasks", "gist": "more"})
    c3 = await called(kernel, "c3")
    await end_turn(kernel, "w")
    ended = await ran(kernel, "c3", "finish", "agent.finish", {"gist": "all done"})

    assert len([event for event in of_type(kernel, "message.sent") if event.actor == "agent:w"]) == 2
    assert rows(spans(kernel)) == [(c1, c2, (posted["ref"], added["ref"])), (c3, c3, (ended["ref"],))]


steps = st.lists(
    st.tuples(
        st.booleans(),
        st.lists(st.lists(st.sampled_from(["joined", "unanchored", "unnamed"]), max_size=2), max_size=4),
    ),
    max_size=4,
)
"""A harness's reports: stretches of model calls, each in a turn of its own or out of any, and each call with the
writes it chose."""


def brute(turns: list[tuple[list[str], list[list[tuple[str, Write]]]]]) -> list[tuple[str, str, tuple[str, ...]]]:
    """The spans read straight off the reports: a turn's calls run on until a call that chose a joined write, unless no
    later call of its turn chose one."""
    found = []
    for calls, writes in turns:
        joined = [index for index, chose in enumerate(writes) if any(how == "joined" for _, how in chose)]
        ends = [*joined[:-1], len(calls) - 1] if calls else []
        first = 0
        for last in ends:
            held = tuple(ref for chose in writes[first : last + 1] for ref, how in chose if how == "joined")
            found.append((calls[first], calls[last], held))
            first = last + 1
    return found


@settings(max_examples=40, deadline=None)
@given(script=steps)
def test_every_call_reported_in_a_turn_lies_in_exactly_one_span(tmp_path_factory, script) -> None:
    """Whatever a harness reports, the spans cover each call it reported in a turn once, in order, cut only at calls
    that chose a joined write, and hold no call it reported out of a turn."""
    folder = tmp_path_factory.mktemp("spans") / "session"

    async def body() -> None:
        kernel = Kernel.open(folder, clock=ManualClock(1000.0), extensions=PRIMITIVES)
        result_of(await kernel.submit(kernel.runtime, "session.open", {"roles": ROLES}))
        await grant(kernel, "agent")
        await team(kernel)
        turns, outside = [], []
        for number, (in_turn, chosen) in enumerate(script):
            if in_turn:
                await start_turn(kernel, "w", f"t{number}")
            calls, writes = [], []
            for index, kinds in enumerate(chosen):
                call_id = f"c{number}-{index}"
                calls.append(await called(kernel, call_id))
                writes.append(
                    [(await wrote(kernel, call_id, f"{call_id}-{n}", how), how) for n, how in enumerate(kinds)]
                )
            if in_turn:
                await end_turn(kernel, "w")
                turns.append((calls, writes))
            else:
                outside += calls
        try:
            found, pages = spans(kernel), []
            pages.append(found)
            while pages[-1].cursor is not None:
                pages.append(spans(kernel, after=pages[-1].cursor))
            listed = [row for page in pages for row in rows(page)]
            assert listed == brute(turns)
            assert found.total == len(listed)
            assert not {ref for row in listed for ref in row[:2]} & set(outside)
        finally:
            kernel.close()

    asyncio.run(body())


async def test_a_compaction_call_lies_in_the_span_its_report_places_it_in(kernel):
    """A harness reports each call where it made it, a compaction's too, with or without an id, and a span holds the
    calls between its first and its last on that stream."""
    await team(kernel)
    await start_turn(kernel, "w")
    c1 = await called(kernel, "c1")
    one = await wrote(kernel, "c1", "one")
    compacted = await called(kernel, None, "compaction")
    await called(kernel, "c2")
    two = await wrote(kernel, "c2", "two")
    c3 = await called(kernel, "c3")
    await end_turn(kernel, "w")

    assert rows(spans(kernel)) == [(c1, c1, (one,)), (compacted, c3, (two,))]


async def test_one_call_that_chose_two_writes_ends_one_span_holding_both(kernel):
    await team(kernel)
    await start_turn(kernel, "w")
    c1 = await called(kernel, "c1")
    one, two = await wrote(kernel, "c1", "one"), await wrote(kernel, "c1", "two")
    c2 = await called(kernel, "c2")
    three = await wrote(kernel, "c2", "three")
    c3 = await called(kernel, "c3")
    await end_turn(kernel, "w")

    assert rows(spans(kernel)) == [(c1, c1, (one, two)), (c2, c3, (three,))]


async def test_a_span_never_crosses_a_turn_and_a_lost_turn_ends_its_spans(kernel):
    """A crash loses the turn it cut, which ends that turn's spans, and a call its harness reported after, out of any
    turn, lies in none."""
    await team(kernel)
    await start_turn(kernel, "w", "t1")
    c1 = await called(kernel, "c1")
    one = await wrote(kernel, "c1", "one")
    c2 = await called(kernel, "c2")
    two = await wrote(kernel, "c2", "two")
    result_of(await kernel.submit(kernel.runtime, "runtime.start", {"drift": []}))
    late = await called(kernel, "late")
    await start_turn(kernel, "w", "t2")
    c3 = await called(kernel, "c3")
    three = await wrote(kernel, "c3", "three")
    c4 = await called(kernel, "c4")
    await end_turn(kernel, "w")

    found = spans(kernel)
    assert [(span.turn, span.first, span.ref, span.writes) for span in found.spans] == [
        ("t1", c1, c1, (one,)),
        ("t1", c2, c2, (two,)),
        ("t2", c3, c4, (three,)),
    ]
    assert late not in {ref for span in found.spans for ref in (span.first, span.ref)}


async def test_a_span_is_named_by_its_last_calls_model_called(kernel):
    await team(kernel)
    await start_turn(kernel, "w", "t1")
    await called(kernel, "c1")
    await wrote(kernel, "c1", "one")
    await called(kernel, "c2")
    await end_turn(kernel, "w")

    [span] = spans(kernel).spans
    named = result_of(kernel.query(kernel.runtime, "lineage", {"ref": span.ref}))["event"]
    first = result_of(kernel.query(kernel.runtime, "lineage", {"ref": span.first}))["event"]
    assert (named["type"], named["turn"], first["type"]) == ("model.called", "t1", "model.called")
    assert span.ref == ref_of(of_type(kernel, "model.called")[-1]) and span.turn == "t1"


async def test_a_harness_that_reports_no_call_has_no_span(kernel):
    """A turn with no `model.called` has no call to lie in a span, as `exec` reports none, whatever its writes."""
    await team(kernel)
    await start_turn(kernel, "w")
    await wrote(kernel, None, "one", how="unnamed")
    await end_turn(kernel, "w")
    await start_turn(kernel, "w", "t2")
    await end_turn(kernel, "w")

    found = spans(kernel)
    assert (found.spans, found.total, found.cursor) == ((), 0, None)


async def test_spans_say_open_while_the_latest_turn_has_not_ended(kernel):
    """A write's tool item can be reported after its op commits, and then cuts its turn anew, so an answer says it is
    open until that turn ends."""
    await team(kernel)
    await start_turn(kernel, "w")
    c1 = await called(kernel, "c1")
    sent = await kernel.submit(
        agent("w"), "message.send", {"to": "@peer", "gist": "one"}, native={"claudecode/toolUseId": "late"}
    )
    one = result_of(sent)["ref"]
    c2 = await called(kernel, "c2")
    two = await wrote(kernel, "c2", "two")
    before = spans(kernel)
    await report(kernel, "w", "item", kind="tool", phase="started", gist="one", native_id="late", call_id="c1")
    joined = spans(kernel)
    await end_turn(kernel, "w")

    assert (rows(before), before.open) == ([(c1, c2, (two,))], True)
    assert (rows(joined), joined.open) == ([(c1, c1, (one,)), (c2, c2, (two,))], True)
    assert spans(kernel).open is False


async def test_spans_page_oldest_first_with_their_true_total(kernel):
    await team(kernel)
    for number in range(40):
        await start_turn(kernel, "w", f"t{number}")
        await called(kernel, f"c{number}")
        await end_turn(kernel, "w")

    first = spans(kernel)
    rest = spans(kernel, after=first.cursor)

    assert (len(first.spans), first.total, len(rest.spans), rest.cursor) == (32, 40, 8, None)
    assert [span.turn for span in (*first.spans, *rest.spans)] == [f"t{number}" for number in range(40)]


async def test_spans_answer_alike_after_a_rebuild_and_on_a_closed_copy(kernel, folder, tmp_path):
    await team(kernel)
    await start_turn(kernel, "w")
    await called(kernel, "c1")
    await wrote(kernel, "c1", "one")
    await called(kernel, "c2")
    await wrote(kernel, "c2", "two")
    await end_turn(kernel, "w")

    live = spans(kernel)
    await kernel.rebuild_all()
    rebuilt = spans(kernel)
    kernel.close()
    shutil.copytree(folder, tmp_path / "copy")
    closed = Kernel.open(tmp_path / "copy", extensions=PRIMITIVES, read_only=True)
    copied = spans(closed)
    closed.close()
    assert len(live.spans) == 2 and live == rebuilt == copied


async def test_the_spans_query_refuses_a_person_or_a_program(kernel, ada):
    await team(kernel)
    await enroll(kernel, Principal(id="program:trainer"))
    asked = ("@ada", "trainer", "@nobody")

    found = [refusal(kernel.query(kernel.runtime, "spans", {"agent": name})) for name in asked]
    malformed = refusal(kernel.query(kernel.runtime, "spans", {"agent": "w", "after": "w@1"}))

    assert [refused.code for refused in found] == ["invalid", "invalid", "not_found"]
    assert malformed.code == "invalid"


async def test_a_worker_that_does_three_tasks_in_one_turn_has_a_span_for_each(tmp_path):
    """The owner's case on a scripted harness: one persistent worker claims and completes three tasks in one turn, a
    call for each, and the record cuts that turn at each completion, the last span holding its last words."""
    queue = {"kind": "queue", "writers": "all", "readers": "all", "delivery": "pull"}
    roles = {"w": {"harness": running.scripted([AskModel()])}}
    queued = Team.model_validate({"roles": roles, "topology": {"channels": {"tasks": queue}}})
    replies: list[Any] = []
    for number in (1, 2, 3):
        claim = ToolCall("task_claim", {"queue": "tasks"}, id=f"claim-{number}")
        done = ToolCall("task_complete", {"queue": "tasks", "gist": f"task {number} done"}, id=f"done-{number}")
        replies += [claim, done]
    model = FakeModel(*replies, "all three are done")
    async with model, Session.start(queued, root=tmp_path, authority=running.Gateways(model)) as session:
        await running.in_state(session, "w", "idle")
        for number in (1, 2, 3):
            await session.task_add("tasks", f"task {number}")
        await session.send("@w", "three tasks are open")
        await running.until(lambda: running.of_type(session, "task.completed"), session, lambda found: len(found) == 3)
        await running.in_state(session, "w", "idle")
        found = await session.spans("@w")
        calls = [ref_of(event) for event in await running.of_type(session, "model.called")]
        completed = [ref_of(event) for event in await running.of_type(session, "task.completed")]

    assert len(calls) == 7
    assert rows(found) == [
        (calls[0], calls[1], (completed[0],)),
        (calls[2], calls[3], (completed[1],)),
        (calls[4], calls[6], (completed[2],)),
    ]


# The labels of the work a span was done for.

CRAFT = {"difficulty": "hard", "kind": "craft"}
SEARCH = {"difficulty": "easy", "kind": "search"}


@pytest.fixture
def labels() -> dict[str, list[str]]:
    return {"difficulty": ["easy", "hard"], "kind": ["craft", "design", "search"]}


async def tasks(kernel: Kernel, *each: dict[str, str], max_inflight: int = 1) -> None:
    """A queue, `tasks`, holding a task for each of `each`, given those labels, numbered from 1."""
    await channel(kernel, "tasks", kind="queue", max_inflight=max_inflight, lease=60.0)
    for number, labels in enumerate(each, 1):
        args = {"queue": "tasks", "gist": f"task {number}", "labels": labels}
        result_of(await kernel.submit(kernel.runtime, "task.add", args))


MADE = {"task.claim": "task.claimed", "task.complete": "task.completed", "task.fail": "task.failed"}


async def did(kernel: Kernel, call_id: str | None, op: str, number: int, how: Write = "joined") -> str:
    """`w` claims, completes, fails or releases task `number` by a tool call of the model call `call_id`: the ref of
    the event it made."""
    await ran(kernel, call_id, f"{op}-{number}", op, {"queue": "tasks", "task": str(number)}, how)
    return ref_of(of_type(kernel, MADE.get(op, "task.released"))[-1])


def labelled(found: Spans) -> list[tuple[str, tuple[str, ...], dict[str, str] | None]]:
    return [(span.first, span.claims, span.labels) for span in found.spans]


async def test_a_span_carries_the_labels_of_the_task_its_agent_held_from_its_claim_to_its_completion(kernel):
    """`w` claims a task, crafts, says how far it has come, which cuts its turn, and completes it: both spans were made
    while it held the task, from the call after the one that claimed it through the one that completed it."""
    await team(kernel)
    await tasks(kernel, CRAFT)
    await start_turn(kernel, "w")
    c1 = await called(kernel, "c1")
    claim = await did(kernel, "c1", "task.claim", 1)
    await called(kernel, "c2")
    await wrote(kernel, "c2", "half crafted")
    c3 = await called(kernel, "c3")
    await did(kernel, "c3", "task.complete", 1)
    await called(kernel, "c4")
    await end_turn(kernel, "w")

    assert labelled(spans(kernel)) == [(c1, (claim,), CRAFT), (c3, (claim,), CRAFT)]


async def test_a_claim_made_by_the_call_that_completed_the_task_before_is_held_from_the_span_after(kernel):
    """The call that completes the first task and claims the second ends the first's span, which held only the first,
    as no call of it was made while the second was held."""
    await team(kernel)
    await tasks(kernel, CRAFT, SEARCH)
    await start_turn(kernel, "w")
    c1 = await called(kernel, "c1")
    first = await did(kernel, "c1", "task.claim", 1)
    await called(kernel, "c2")
    await did(kernel, "c2", "task.complete", 1)
    second = await did(kernel, "c2", "task.claim", 2)
    c3 = await called(kernel, "c3")
    await did(kernel, "c3", "task.complete", 2)
    await called(kernel, "c4")
    await end_turn(kernel, "w")

    assert labelled(spans(kernel)) == [(c1, (first,), CRAFT), (c3, (second,), SEARCH)]


async def test_a_span_that_held_no_task_carries_the_labels_its_agent_was_spawned_with_else_none(kernel):
    await spawn(kernel, "peer")
    args = {"name": "w", "child_role": "worker", "goal": "design it", "labels": {"kind": "design"}}
    result_of(await kernel.submit(kernel.runtime, "agent.spawn", args))
    await settle_effects(kernel, "w")
    await start(kernel, "w")
    found = {}
    for name in ("w", "peer"):
        await start_turn(kernel, name)
        await report(kernel, name, "model.call", call_id=f"{name}-1")
        await end_turn(kernel, name)
        found[name] = [(span.claims, span.labels) for span in spans(kernel, name).spans]

    assert found == {"w": [((), {"kind": "design"})], "peer": [((), {})]}


async def test_a_task_given_no_labels_or_work_recorded_before_labels_carries_none(kernel, folder, clock):
    """A task with no labels is work with none, so a span that held it carries none, not its agent's; and a journal
    from before labels were recorded reads as one whose work had none."""
    args = {"name": "w", "child_role": "worker", "goal": "design it", "labels": {"kind": "design"}}
    result_of(await kernel.submit(kernel.runtime, "agent.spawn", args))
    await settle_effects(kernel, "w")
    await start(kernel, "w")
    await tasks(kernel, {}, CRAFT)
    await start_turn(kernel, "w", "t1")
    await called(kernel, "c1")
    await did(kernel, "c1", "task.claim", 1)
    await called(kernel, "c2")
    await did(kernel, "c2", "task.complete", 1)
    await did(kernel, "c2", "task.claim", 2)
    await called(kernel, "c3")
    await did(kernel, "c3", "task.complete", 2)
    await called(kernel, "c4")
    await end_turn(kernel, "w")
    await start_turn(kernel, "w", "t2")
    await called(kernel, "c5")
    await end_turn(kernel, "w")
    now = [span.labels for span in spans(kernel).spans]
    kernel.close()
    unlabelled = "json_remove(data, '$.labels')"
    written_at_v1(folder, {"task.added": unlabelled, "agent.spawned": unlabelled})
    reopened = Kernel.open(folder, clock=clock, extensions=PRIMITIVES)
    before = [span.labels for span in spans(reopened).spans]
    reopened.close()

    assert (now, before) == ([{}, CRAFT, {"kind": "design"}], [{}, {}, {}])


async def test_a_span_made_under_claims_of_different_labels_has_unknown_labels_and_of_alike_ones_carries_them(kernel):
    """Two claims held at once: of a crafting task and a search, the span's labels are unknown, never merged or one
    of them; of two crafting tasks, it carries theirs."""
    await team(kernel)
    await tasks(kernel, CRAFT, SEARCH, CRAFT, CRAFT, max_inflight=2)
    await start_turn(kernel, "w")
    c1 = await called(kernel, "c1")
    one, two = await did(kernel, "c1", "task.claim", 1), await did(kernel, "c1", "task.claim", 2)
    await called(kernel, "c2")
    await did(kernel, "c2", "task.complete", 1)
    c3 = await called(kernel, "c3")
    await did(kernel, "c3", "task.complete", 2)
    c4 = await called(kernel, "c4")
    three, four = await did(kernel, "c4", "task.claim", 3), await did(kernel, "c4", "task.claim", 4)
    await called(kernel, "c5")
    await did(kernel, "c5", "task.complete", 3)
    c6 = await called(kernel, "c6")
    await did(kernel, "c6", "task.complete", 4)
    await called(kernel, "c7")
    await end_turn(kernel, "w")

    assert labelled(spans(kernel)) == [
        (c1, (one, two), None),
        (c3, (two,), SEARCH),
        (c4, (three, four), CRAFT),
        (c6, (four,), CRAFT),
    ]


async def test_a_release_or_a_failure_ends_a_hold_as_a_completion_does(kernel):
    await team(kernel)
    await tasks(kernel, CRAFT, SEARCH)
    await start_turn(kernel, "w", "t1")
    c1 = await called(kernel, "c1")
    first = await did(kernel, "c1", "task.claim", 1)
    await called(kernel, "c2")
    await did(kernel, "c2", "task.release", 1)
    await wrote(kernel, "c2", "gave the first back")
    c3 = await called(kernel, "c3")
    second = await did(kernel, "c3", "task.claim", 2)
    await called(kernel, "c4")
    await did(kernel, "c4", "task.fail", 2)
    await called(kernel, "c5")
    await end_turn(kernel, "w")
    await start_turn(kernel, "w", "t2")
    c6 = await called(kernel, "c6")
    await end_turn(kernel, "w")

    assert labelled(spans(kernel)) == [(c1, (first,), CRAFT), (c3, (second,), SEARCH), (c6, (), {})]


async def test_a_claim_held_still_or_as_its_agent_ended_is_held_through_its_last_call(kernel):
    await team(kernel)
    await tasks(kernel, CRAFT)
    await start_turn(kernel, "w", "t1")
    await called(kernel, "c1")
    claim = await did(kernel, "c1", "task.claim", 1)
    await called(kernel, "c2")
    await end_turn(kernel, "w")
    await start_turn(kernel, "w", "t2")
    await called(kernel, "c3")
    await end_turn(kernel, "w")
    holding = labelled(spans(kernel))
    result_of(await kernel.submit(kernel.runtime, "agent.cancel", {"agent": "w"}))

    assert [held[1:] for held in holding] == [((claim,), CRAFT)] * 2
    assert labelled(spans(kernel)) == holding


async def test_a_claim_tied_to_no_call_lies_at_its_turn_s_start_where_that_turn_is_one_span_and_else_anywhere_in_it(
    kernel,
):
    """As OpenHands and Codex join no tool call to a model call, a turn that is one span holds the task claimed in it;
    in a turn that is cut, a claim tied to no call may have been made by any of its calls, so each span it may lie in
    has unknown labels."""
    await team(kernel)
    await tasks(kernel, CRAFT, SEARCH)
    await start_turn(kernel, "w", "t1")
    c1 = await called(kernel, "c1")
    first = await did(kernel, None, "task.claim", 1, how="unanchored")
    await called(kernel, "c2")
    await did(kernel, None, "task.complete", 1, how="unanchored")
    await called(kernel, "c3")
    await end_turn(kernel, "w")
    await start_turn(kernel, "w", "t2")
    c4 = await called(kernel, "c4")
    await wrote(kernel, "c4", "on to the next")
    await did(kernel, None, "task.claim", 2, how="unanchored")
    c5 = await called(kernel, "c5")
    await did(kernel, "c5", "task.complete", 2)
    await called(kernel, "c6")
    await end_turn(kernel, "w")

    assert labelled(spans(kernel)) == [(c1, (first,), CRAFT), (c4, (), None), (c5, (), None)]


async def test_a_lapse_between_turns_ends_a_hold_there_and_one_within_a_turn_leaves_its_spans_unknown(kernel, clock):
    """A lapse is the runtime's, made by no call of the claimant's, so commit order places it among the claimant's
    turns: between two exactly, as no call is made between turns, and within one anywhere in it."""
    await team(kernel)
    await tasks(kernel, CRAFT, SEARCH)
    await start_turn(kernel, "w", "t1")
    c1 = await called(kernel, "c1")
    first = await did(kernel, "c1", "task.claim", 1)
    await called(kernel, "c2")
    await end_turn(kernel, "w")
    clock.advance(61.0)
    fence = of_type(kernel, "task.claimed")[-1].seq
    result_of(await kernel.submit(kernel.runtime, "lease.expire", {"queue": "tasks", "task": "1", "fence": fence}))
    await start_turn(kernel, "w", "t2")
    c3 = await called(kernel, "c3")
    await did(kernel, "c3", "task.claim", 2)
    await called(kernel, "c4")
    clock.advance(61.0)
    fence = of_type(kernel, "task.claimed")[-1].seq
    result_of(await kernel.submit(kernel.runtime, "lease.expire", {"queue": "tasks", "task": "2", "fence": fence}))
    await called(kernel, "c5")
    await end_turn(kernel, "w")

    assert [event.type for event in of_type(kernel, "lease.expired")] == ["lease.expired"] * 2
    assert labelled(spans(kernel)) == [(c1, (first,), CRAFT), (c3, (), None)]
