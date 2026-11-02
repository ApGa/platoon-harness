"""One command: idempotency, refusals, outcomes and optimistic concurrency."""

import asyncio
import contextlib
import logging
import sqlite3

from platoon_harness.kernel import Args, Event, Extension, Kernel, Txn, View, fold, op

from .support import ALICE, BOB, HUMAN, dump, enroll, events_of, grant, notes, refusal_of, result_of


async def granted(kernel, *principals):
    for principal in principals:
        await enroll(kernel, principal)
    await grant(kernel, "all")


async def test_a_retry_receives_the_first_answer(kernel):
    await granted(kernel, HUMAN)
    first = await kernel.submit(HUMAN, "note.add", {"text": "once"}, key="k")
    head = kernel.head

    retry = await kernel.submit(HUMAN, "note.add", {"text": "once"}, key="k")

    assert retry == first
    assert kernel.head == head


async def test_a_retry_of_a_refusal_gets_the_same_refusal(kernel):
    await granted(kernel, HUMAN)
    first = await kernel.submit(HUMAN, "note.add", {"fail": True}, key="k")
    head = kernel.head

    retry = await kernel.submit(HUMAN, "note.add", {"fail": True}, key="k")

    assert refusal_of(first) == "conflict"
    assert retry == first
    assert kernel.head == head


async def test_a_reused_key_with_other_arguments_is_refused(kernel):
    await granted(kernel, HUMAN)
    first = await kernel.submit(HUMAN, "note.add", {"text": "one"}, key="k")

    reused = await kernel.submit(HUMAN, "note.add", {"text": "two"}, key="k")

    assert refusal_of(reused) == "key_reused"
    assert events_of(kernel)[-1].type == "op.refused"
    assert await kernel.submit(HUMAN, "note.add", {"text": "one"}, key="k") == first


async def test_keys_belong_to_their_actor(kernel):
    await granted(kernel, HUMAN, ALICE)
    mine = await kernel.submit(HUMAN, "note.add", {}, key="k")
    theirs = await kernel.submit(ALICE, "note.add", {}, key="k")
    assert mine.seq != theirs.seq


async def test_a_retry_in_the_same_batch_is_deduplicated(kernel):
    await granted(kernel, HUMAN)
    answers = await asyncio.gather(*(kernel.submit(HUMAN, "note.add", {}, key="k") for _ in range(8)))
    assert len({answer.seq for answer in answers}) == 1


async def test_a_command_ends_on_one_event_carrying_its_outcome(kernel):
    await granted(kernel, HUMAN)
    head = kernel.head
    outcome = await kernel.submit(HUMAN, "note.add", {"copies": 3}, key="k")

    events = events_of(kernel, after=head)

    assert [event.outcome is not None for event in events] == [False, False, True]
    assert events[-1].seq == outcome.seq
    assert events[-1].outcome == outcome


async def test_a_command_that_emits_nothing_still_ends_on_an_event(kernel):
    await granted(kernel, HUMAN)
    outcome = await kernel.submit(HUMAN, "note.silence", {})

    event = events_of(kernel)[-1]

    assert result_of(outcome) == "quiet"
    assert (event.type, event.stream, event.seq) == ("op.completed", "commands/human:ada", outcome.seq)
    assert event.outcome.result == "quiet"


async def test_a_refusal_rolls_back_and_commits_one_event(kernel):
    await granted(kernel, HUMAN)
    head = kernel.head
    outcome = await kernel.submit(HUMAN, "note.add", {"copies": 3, "fail": True})

    events = events_of(kernel, after=head)

    assert [event.type for event in events] == ["op.refused"]
    assert events[0].stream == "commands/human:ada"
    assert events[0].outcome.refusal.code == "conflict"
    assert outcome.refusal.op == "note.add"
    assert outcome.refusal.object == "note/a"
    assert result_of(kernel.query(HUMAN, "note.list", {})) == []


async def test_a_refusal_leaves_the_object_stream_alone(kernel):
    await granted(kernel, HUMAN, ALICE)
    result_of(await kernel.submit(HUMAN, "note.add", {}))
    assert refusal_of(await kernel.submit(HUMAN, "note.add", {"fail": True})) == "conflict"
    assert result_of(await kernel.submit(HUMAN, "note.add", {}, expected_version=1))


async def test_an_unknown_op_is_refused_and_journaled(kernel):
    outcome = await kernel.submit(HUMAN, "note.nope", {})
    assert refusal_of(outcome) == "not_found"
    assert events_of(kernel)[-1].outcome == outcome


async def test_expected_version_is_checked_against_the_object_stream(kernel):
    await granted(kernel, HUMAN)
    assert result_of(await kernel.submit(HUMAN, "note.add", {}, expected_version=0))
    assert result_of(await kernel.submit(HUMAN, "note.add", {}, expected_version=1))

    stale = await kernel.submit(HUMAN, "note.add", {}, expected_version=1)

    assert refusal_of(stale) == "conflict"
    assert stale.refusal.detail == {"expected": 1, "current": 2}


async def test_a_crashing_op_is_refused_and_the_writer_lives_on(folder, clock, caplog):
    @op("bug.crash")
    def crash(txn: Txn, a: Args) -> None:
        """Fail in a way no op should."""
        txn.emit("bug.happened", "bug", gist="half done")
        raise KeyError("oops")

    kernel = Kernel.open(folder, clock=clock, extensions=[Extension("bug", ops=[crash])])
    with caplog.at_level(logging.ERROR, "platoon_harness.kernel"):
        outcome = await kernel.submit(kernel.runtime, "bug.crash", {}, key="k")

    assert refusal_of(outcome) == "unavailable"
    assert "an op failed" in caplog.text
    assert [event.type for event in events_of(kernel)] == ["op.refused"]
    kernel.close()


async def test_a_crash_answers_nothing_so_its_key_can_retry(folder, clock):
    runs = []

    @op("bug.flaky")
    def flaky(txn: Txn, a: Args) -> str:
        """Fail the first time."""
        runs.append(1)
        if len(runs) == 1:
            raise sqlite3.OperationalError("database or disk is full")
        return "worked"

    kernel = Kernel.open(folder, clock=clock, extensions=[Extension("bug", ops=[flaky])])

    assert refusal_of(await kernel.submit(kernel.runtime, "bug.flaky", {}, key="k")) == "unavailable"
    assert result_of(await kernel.submit(kernel.runtime, "bug.flaky", {}, key="k")) == "worked"
    assert result_of(await kernel.submit(kernel.runtime, "bug.flaky", {}, key="k")) == "worked"
    assert len(runs) == 2
    kernel.close()


def half_folded(event_type: str) -> type[View]:
    """A view of two folds on one event: the first writes and the second fails."""

    class Half(View):
        schema = "CREATE TABLE v_half(seq INTEGER PRIMARY KEY) STRICT;"

        @fold(event_type)
        def first(self, event: Event) -> None:
            self.db.execute("INSERT INTO v_half VALUES (?)", (event.seq,))

        @fold(event_type)
        def second(self, event: Event) -> None:
            raise RuntimeError("a bug in a fold")

    return Half


async def test_a_fold_failure_on_the_refusal_path_leaves_nothing(folder, clock):
    half = Extension("half", views=[half_folded("op.refused")])
    kernel = Kernel.open(folder, clock=clock, extensions=[notes, half])

    outcome = await kernel.submit(kernel.runtime, "note.add", {"fail": True})

    assert refusal_of(outcome) == "unavailable"
    assert outcome.seq is None
    assert kernel.head == 0
    assert dump(folder)["v_half"] == []
    assert result_of(await kernel.submit(kernel.runtime, "note.add", {}))
    kernel.close()


async def test_an_op_cannot_swallow_a_fold_failure(folder, clock):
    @op("half.swallow")
    def swallow(txn: Txn, a: Args) -> str:
        """Catch a fold's failure and carry on."""
        with contextlib.suppress(RuntimeError):
            txn.emit("half.done", "half/a", gist="half")
        return "fine"

    half = Extension("half", ops=[swallow], views=[half_folded("half.done")])
    kernel = Kernel.open(folder, clock=clock, extensions=[half])

    outcome = await kernel.submit(kernel.runtime, "half.swallow", {})

    assert refusal_of(outcome) == "unavailable"
    assert [event.type for event in events_of(kernel)] == ["op.refused"]
    assert dump(folder)["v_half"] == []
    kernel.close()


async def test_a_denial_of_a_long_object_stays_evidence(kernel):
    await enroll(kernel, ALICE)
    head = kernel.head

    outcome = await kernel.submit(ALICE, "note.add", {"stream": "x" * 20000}, key="k")

    assert refusal_of(outcome) == "not_permitted"
    assert outcome.refusal.object == "x" * 256
    assert kernel.head == head + 1
    assert events_of(kernel)[-1].outcome == outcome
    assert await kernel.submit(ALICE, "note.add", {"stream": "x" * 20000}, key="k") == outcome


async def test_caller_text_cannot_grow_a_refusal_without_bound(kernel, folder):
    outcome = await kernel.submit(kernel.runtime, "note.add", {"refs": ["bad ref" + "z" * 1_000_000]})

    assert refusal_of(outcome) == "invalid"
    assert len(outcome.refusal.detail) == 512
    assert len(events_of(kernel)[-1].outcome.model_dump_json()) < 2048


async def test_structured_detail_survives_when_it_fits(kernel):
    args = {"stream": "note/a"}
    outcome = await kernel.submit(kernel.runtime, "note.add", args, expected_version=9)
    assert outcome.refusal.detail == {"expected": 9, "current": 0}


async def test_a_lone_surrogate_is_refused_and_journaled(kernel):
    outcome = await kernel.submit(kernel.runtime, "note.add", {"text": "\ud800"}, key="k")

    assert refusal_of(outcome) == "invalid"
    assert events_of(kernel)[-1].outcome == outcome
    assert refusal_of(kernel.query(kernel.runtime, "note.list", {"stream": "\ud800"})) == "invalid"


async def test_arguments_that_are_not_json_are_refused_and_journaled(kernel):
    looped: dict[str, object] = {}
    looped["self"] = looped
    for args in ({"text": object()}, {"text": float("nan")}, looped, {1: "a", "b": 2}):
        outcome = await kernel.submit(kernel.runtime, "ops.list", args)
        assert refusal_of(outcome) == "invalid"
        assert events_of(kernel)[-1].outcome == outcome
        assert refusal_of(kernel.query(kernel.runtime, "ops.list", args)) == "invalid"


async def test_decoding_coerces_nothing(kernel):
    assert refusal_of(await kernel.submit(kernel.runtime, "note.add", {"copies": "2"})) == "invalid"
    assert refusal_of(await kernel.submit(kernel.runtime, "note.add", {"fail": 1})) == "invalid"
    assert result_of(await kernel.submit(kernel.runtime, "note.add", {"cause": [], "copies": 1}))


async def test_a_version_expected_of_a_query_is_refused(kernel):
    outcome = await kernel.submit(HUMAN, "note.read", {}, expected_version=9)
    assert refusal_of(outcome) == "unsupported"


async def test_a_retry_after_key_reuse_still_gets_the_first_answer(kernel):
    first = await kernel.submit(kernel.runtime, "note.add", {"text": "one"}, key="k")
    assert refusal_of(await kernel.submit(kernel.runtime, "note.add", {"text": "two"}, key="k")) == "key_reused"
    assert refusal_of(await kernel.submit(kernel.runtime, "note.add", {"text": "two"}, key="k")) == "key_reused"
    assert await kernel.submit(kernel.runtime, "note.add", {"text": "one"}, key="k") == first


async def test_a_retry_finds_its_answer_through_the_index(kernel):
    with kernel._reading() as db:
        plan = db.execute(
            "EXPLAIN QUERY PLAN SELECT outcome FROM events WHERE actor = ? AND outcome ->> '$.key' = ? "
            "ORDER BY seq LIMIT 1",
            ("runtime", "k"),
        ).fetchall()
    assert "USING INDEX events_command" in plan[0]["detail"]
    assert all("TEMP B-TREE" not in row["detail"] for row in plan)


async def test_a_retry_outlives_a_rebuild(kernel):
    first = await kernel.submit(kernel.runtime, "note.add", {}, key="k")
    await kernel.rebuild_all()
    assert await kernel.submit(kernel.runtime, "note.add", {}, key="k") == first


async def test_a_result_too_large_for_the_journal_is_refused(folder, clock):
    @op("big.answer")
    def answer(txn: Txn, a: Args) -> str:
        """Answer at length."""
        return "x" * 20000

    kernel = Kernel.open(folder, clock=clock, extensions=[Extension("big", ops=[answer])])
    assert refusal_of(await kernel.submit(kernel.runtime, "big.answer", {})) == "invalid"
    kernel.close()


async def test_names_are_bounded_before_they_reach_the_journal(kernel):
    assert refusal_of(await kernel.submit(HUMAN, "x" * 300, {})) == "invalid"
    assert refusal_of(await kernel.submit(HUMAN, "note.silence", {}, key="k" * 300)) == "invalid"
    assert refusal_of(await kernel.submit(HUMAN, "note.\ud800", {})) == "invalid"
    assert refusal_of(await kernel.submit(HUMAN, "note.silence", {}, key="\ud800")) == "invalid"
    assert events_of(kernel) == []


async def test_a_query_has_no_command_form_and_a_command_no_query_form(kernel):
    await granted(kernel, HUMAN, BOB)
    assert refusal_of(await kernel.submit(HUMAN, "note.list", {})) == "unsupported"
    assert refusal_of(kernel.query(HUMAN, "note.add", {})) == "unsupported"


async def test_a_closed_kernel_refuses_commands(kernel):
    kernel.close()
    assert refusal_of(await kernel.submit(kernel.runtime, "note.silence", {})) == "unavailable"


async def test_native_ids_are_stamped_on_every_event_of_a_command(kernel):
    await granted(kernel, HUMAN)

    result_of(await kernel.submit(HUMAN, "note.add", {"copies": 2}, native={"callId": "exec-1"}))
    refused = await kernel.submit(HUMAN, "note.add", {"undeclared": 1}, native={"callId": "exec-2"})

    assert refusal_of(refused) == "invalid"
    assert [event.native for event in events_of(kernel)[-3:]] == [{"callId": "exec-1"}] * 2 + [{"callId": "exec-2"}]


async def test_native_ids_are_no_part_of_a_commands_identity(kernel):
    await granted(kernel, HUMAN)

    first = await kernel.submit(HUMAN, "note.add", {}, key="k", native={"callId": "exec-1"})
    again = await kernel.submit(HUMAN, "note.add", {}, key="k", native={"callId": "exec-2"})

    assert first.seq == again.seq
