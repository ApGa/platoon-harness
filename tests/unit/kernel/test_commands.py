"""One command: idempotency, refusals, outcomes and optimistic concurrency."""

import asyncio
import logging

from platoon_harness.kernel import Args, Extension, Kernel, Txn, op

from .support import ALICE, BOB, HUMAN, enroll, events_of, grant, refusal_of, result_of


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
    assert await kernel.submit(kernel.runtime, "bug.crash", {}, key="k") == outcome
    kernel.close()


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
    assert events_of(kernel) == []


async def test_a_query_has_no_command_form_and_a_command_no_query_form(kernel):
    await granted(kernel, HUMAN, BOB)
    assert refusal_of(await kernel.submit(HUMAN, "note.list", {})) == "unsupported"
    assert refusal_of(kernel.query(HUMAN, "note.add", {})) == "unsupported"


async def test_a_closed_kernel_refuses_commands(kernel):
    kernel.close()
    assert refusal_of(await kernel.submit(kernel.runtime, "note.silence", {})) == "unavailable"
