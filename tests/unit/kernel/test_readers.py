"""Readers: pages, cursors, a shared pulse and lossy live text."""

import asyncio
import sqlite3
from itertools import zip_longest

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from platoon_harness.kernel import Args, Extension, Kernel, Principal, Refused, Txn, first, op
from platoon_harness.kernel.pulse import Ring

from .support import ALICE, HUMAN, enroll, events_of, notes, refusal_of, refused_code, result_of

FRAME = 64 * 1024


async def add(kernel, count: int, stream: str = "note/a") -> None:
    for _ in range(count):
        result_of(await kernel.submit(kernel.runtime, "note.add", {"stream": stream}))


async def test_read_pages_through_the_journal(kernel):
    await add(kernel, 5)

    first = kernel.read(kernel.runtime, after=0, limit=2)
    second = kernel.read(kernel.runtime, after=first.cursor, limit=2)
    third = kernel.read(kernel.runtime, after=second.cursor, limit=2)

    assert [e.seq for e in first.events] == [1, 2]
    assert [e.seq for e in second.events] == [3, 4]
    assert [e.seq for e in third.events] == [5]
    assert (third.cursor, third.head) == (5, 5)


async def test_read_matches_stream_names(kernel):
    await add(kernel, 2, "note/a")
    await add(kernel, 1, "other/b")

    page = kernel.read(kernel.runtime, after=0, match="note/*")

    assert [e.stream for e in page.events] == ["note/a", "note/a"]
    assert page.cursor == 3


async def test_a_filtered_page_is_bounded_by_what_it_scans(kernel):
    await add(kernel, 3, "other/b")
    await add(kernel, 3, "note/a")

    page = kernel.read(kernel.runtime, after=0, match="note/*", limit=2)

    assert [e.seq for e in page.events] == [4, 5]
    assert page.cursor == 5
    assert kernel.read(kernel.runtime, after=page.cursor, match="note/*", limit=2).events[0].seq == 6


async def test_reading_past_the_head_is_empty(kernel):
    await add(kernel, 1)
    page = kernel.read(kernel.runtime, after=9)
    assert (page.events, page.cursor, page.head) == ((), 9, 1)


@pytest.mark.parametrize(
    "args",
    [
        {"after": 0, "limit": 0},
        {"after": 0, "limit": -1},
        {"after": 0, "limit": 4097},
        {"after": 0, "limit": 2**64},
        {"after": -1},
        {"after": 2**70},
        {"after": 0, "match": "\ud800"},
    ],
)
async def test_a_bad_page_is_refused_and_harms_no_reader(kernel, args):
    await add(kernel, 1)

    with pytest.raises(Refused) as error:
        kernel.read(kernel.runtime, **args)

    assert refused_code(error) == "invalid"
    assert len(kernel.read(kernel.runtime, after=0).events) == 1


async def test_a_failure_inside_a_read_leaves_no_transaction_behind(kernel):
    with pytest.raises(sqlite3.ProgrammingError), kernel._reading() as db:
        db.execute("SELECT ?", (object(),))

    assert not kernel._idle.get_nowait().in_transaction


async def test_a_connection_that_cannot_end_cleanly_does_not_go_back(kernel):
    with kernel._reading() as db:
        db.execute("COMMIT")

    assert kernel._idle.empty()


async def test_read_is_refused_for_agents(kernel):
    with pytest.raises(Refused) as error:
        kernel.read(ALICE, after=0)
    assert refused_code(error) == "not_permitted"
    with pytest.raises(Refused):
        await anext(aiter(kernel.follow(ALICE, after=0)))


async def test_read_is_for_live_principals(kernel):
    with pytest.raises(Refused) as error:
        kernel.read(Principal(id="human:ghost"), after=0)
    assert refused_code(error) == "not_permitted"
    with pytest.raises(Refused):
        await anext(aiter(kernel.follow(Principal(id="human:ghost"), after=0)))

    await enroll(kernel, HUMAN)
    assert kernel.read(HUMAN, after=0).head == 1
    result_of(await kernel.submit(kernel.runtime, "principal.revoke", {"id": HUMAN.id}))
    with pytest.raises(Refused):
        kernel.read(HUMAN, after=0)


async def test_a_follower_stops_at_its_revocation(kernel):
    await enroll(kernel, HUMAN)
    follower = kernel.follow(HUMAN, after=0)
    await anext(follower)

    result_of(await kernel.submit(kernel.runtime, "principal.revoke", {"id": HUMAN.id}))

    with pytest.raises(Refused) as error:
        await anext(follower)
    assert refused_code(error) == "not_permitted"


async def test_another_followers_revocation_changes_nothing(kernel):
    await enroll(kernel, HUMAN)
    await enroll(kernel, Principal(id="human:bo"))
    follower = kernel.follow(HUMAN, after=0)
    await anext(follower)

    result_of(await kernel.submit(kernel.runtime, "principal.revoke", {"id": "human:bo"}))

    assert [event.type for event in (await anext(follower)).events] == ["principal.revoked"]
    await follower.aclose()


async def test_follow_is_catch_up_then_live(kernel):
    await add(kernel, 2)
    follower = kernel.follow(kernel.runtime, after=0)

    caught_up = await anext(follower)
    pending = asyncio.ensure_future(anext(follower))
    await asyncio.sleep(0)
    assert not pending.done()
    await add(kernel, 1)
    live = await pending

    assert [e.seq for e in caught_up.events] == [1, 2]
    assert [e.seq for e in live.events] == [3]
    await follower.aclose()


async def test_follow_does_not_wake_for_events_it_filters_out(kernel):
    follower = kernel.follow(kernel.runtime, after=0, match="note/*")
    pending = asyncio.ensure_future(anext(follower))
    await add(kernel, 1, "other/b")
    await add(kernel, 1, "note/a")

    page = await pending

    assert [e.stream for e in page.events] == ["note/a"]
    await follower.aclose()


async def test_followers_at_the_tail_share_one_read(kernel):
    fetches = []
    fetch = kernel._tail._fetch
    kernel._tail._fetch = lambda after: fetches.append(after) or fetch(after)
    followers = [kernel.follow(kernel.runtime, after=0) for _ in range(20)]
    pending = [asyncio.ensure_future(anext(follower)) for follower in followers]
    await asyncio.sleep(0)

    await add(kernel, 1)
    pages = await asyncio.gather(*pending)

    assert fetches == [0]
    assert {page.events[0].seq for page in pages} == {1}
    for follower in followers:
        await follower.aclose()


async def test_a_follower_past_the_tail_pages_by_sql(kernel):
    await asyncio.gather(*(kernel.submit(kernel.runtime, "note.add", {}) for _ in range(1100)))
    seen = []
    async for page in kernel.follow(kernel.runtime, after=0):
        seen += [event.seq for event in page.events]
        if page.cursor >= page.head:
            break

    assert kernel._tail.page(0, None, kernel.head) is None
    assert seen == list(range(1, 1101))


async def test_the_tail_and_a_read_agree_on_what_matches(kernel):
    await add(kernel, 1, "note/a")
    await add(kernel, 1, "note/b")
    for pattern in ("note/*", "note/[!a]", "*/a", "note/?"):
        by_tail = kernel._tail.page(0, pattern, kernel.head)
        by_sql = kernel.read(kernel.runtime, after=0, match=pattern)
        assert [e.seq for e in by_tail.events] == [e.seq for e in by_sql.events]


async def test_read_connections_stay_few(kernel):
    with kernel._reading(), kernel._reading(), kernel._reading(), kernel._reading(), kernel._reading():
        pass
    assert kernel._idle.qsize() == 4


async def test_follow_ends_when_the_kernel_closes(kernel):
    await add(kernel, 1)
    pages = []

    async def collect() -> None:
        async for page in kernel.follow(kernel.runtime, after=0):
            pages.append(page)

    task = asyncio.create_task(collect())
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert pages
    kernel.close()
    await task

    assert len(pages) == 1


async def test_follow_of_a_closed_journal_ends_at_the_head(folder, clock):
    kernel = Kernel.open(folder, clock=clock, extensions=[notes])
    await add(kernel, 2)
    kernel.close()

    reader = Kernel.open(folder, clock=clock, read_only=True)
    pages = [page async for page in reader.follow(reader.runtime, after=0)]
    assert [len(page.events) for page in pages] == [2]
    reader.close()


async def test_queries_cannot_write(folder, clock):
    @op("sneak.write", query=True)
    def write(txn: Txn, a: Args) -> None:
        """Try to write from a query."""
        txn._db.execute("INSERT INTO v_stamps VALUES ('a', 'b')")

    @op("sneak.emit", query=True)
    def emit(txn: Txn, a: Args) -> None:
        """Try to emit from a query."""
        txn.emit("sneak.emitted", "sneak", gist="caught")

    @op("sneak.effect", query=True)
    def effect(txn: Txn, a: Args) -> None:
        """Try to request an effect from a query."""
        txn.effect("deliver", {})

    extension = Extension("sneak", ops=[write, emit, effect])
    kernel = Kernel.open(folder, clock=clock, extensions=[extension])
    runtime = kernel.runtime

    assert refusal_of(kernel.query(runtime, "sneak.write", {})) == "unavailable"
    assert refusal_of(kernel.query(runtime, "sneak.emit", {})) == "unsupported"
    assert refusal_of(kernel.query(runtime, "sneak.effect", {})) == "unsupported"
    assert kernel.head == 0
    kernel.close()


async def test_a_read_sees_one_snapshot(kernel):
    with kernel._reading() as db:
        assert db.execute("SELECT count(*) FROM events").fetchone()[0] == 0
        await add(kernel, 1)
        assert db.execute("SELECT count(*) FROM events").fetchone()[0] == 0
    with kernel._reading() as db:
        assert db.execute("SELECT count(*) FROM events").fetchone()[0] == 1


async def test_a_closed_kernel_refuses_queries_with_an_outcome(kernel):
    kernel.close()
    assert refusal_of(kernel.query(kernel.runtime, "note.list", {})) == "unavailable"
    assert refusal_of(await kernel.submit(HUMAN, "note.read", {})) == "unavailable"


def test_read_connections_are_read_only(folder, clock):
    Kernel.open(folder, clock=clock).close()
    kernel = Kernel.open(folder, clock=clock)
    with kernel._reading() as db, pytest.raises(sqlite3.OperationalError):
        db.execute("INSERT INTO v_stamps VALUES ('a', 'b')")
    kernel.close()


async def test_deltas_are_live_and_never_journaled(kernel):
    frames = kernel.deltas("alice")
    pending = asyncio.ensure_future(anext(frames))
    await asyncio.sleep(0)

    kernel.push_delta("alice", "hel")
    frame = await pending
    kernel.push_delta("bob", "other")

    assert (frame.agent, frame.frame, frame.text, frame.lag, frame.ended) == ("alice", 1, "hel", 0, None)
    assert events_of(kernel) == []
    await frames.aclose()


async def test_a_slow_reader_of_deltas_is_given_what_came_joined_with_its_true_lag(kernel):
    frames = kernel.deltas("alice")
    pending = asyncio.ensure_future(anext(frames))
    await asyncio.sleep(0)
    kernel.push_delta("alice", "first")
    assert (await pending).text == "first"

    for letter in "abcde":
        kernel.push_delta("alice", letter * FRAME)

    frame = await anext(frames)
    assert (frame.frame, frame.text, frame.lag) == (6, "".join(letter * FRAME for letter in "bcde"), 1)
    await frames.aclose()


async def test_a_late_joiner_is_shown_only_text_not_yet_committed_after_what_was(kernel):
    kernel.push_delta("alice", "said, ")
    kernel.push_delta("alice", "and committed")
    kernel.end_delta("alice", 7)
    kernel.push_delta("alice", "still ")
    kernel.push_delta("alice", "saying")

    frame = await anext(kernel.deltas("alice"))

    assert (frame.frame, frame.text, frame.lag, frame.ended) == (5, "still saying", 0, 7)


async def test_a_late_joiner_is_told_its_true_lag(kernel):
    for letter in "abcde":
        kernel.push_delta("alice", letter * FRAME)

    frame = await anext(kernel.deltas("alice"))

    assert (frame.text, frame.lag) == ("".join(letter * FRAME for letter in "bcde"), 1)


async def test_a_reader_part_way_through_is_told_what_replaced_its_text(kernel):
    kernel.push_delta("alice", "half")
    frames = kernel.deltas("alice", after=1)
    pending = asyncio.ensure_future(anext(frames))
    await asyncio.sleep(0)

    kernel.end_delta("alice", 9)
    kernel.push_delta("alice", "next")

    frame = await pending
    assert (frame.frame, frame.text, frame.ended) == (3, "next", 9)
    await frames.aclose()


async def test_live_text_of_an_agent_that_ended_says_so_once_and_ends(kernel):
    await enroll(kernel, ALICE)
    kernel.push_delta("alice", "last words")
    frames = kernel.deltas("alice", after=1)
    pending = asyncio.ensure_future(anext(frames))
    await asyncio.sleep(0)

    result_of(await kernel.submit(kernel.runtime, "principal.revoke", {"id": ALICE.id}))
    kernel.end_delta("alice", kernel.head)

    assert (await pending).ended == kernel.head
    assert [delta async for delta in frames] == []
    assert [delta async for delta in kernel.deltas("alice")] == []


async def test_deltas_asked_for_after_close_end_at_once(kernel):
    kernel.close()
    assert [delta async for delta in kernel.deltas("nobody-yet")] == []


async def test_deltas_end_when_the_kernel_closes(kernel):
    frames = kernel.deltas("alice")
    pending = asyncio.ensure_future(anext(frames))
    await asyncio.sleep(0)
    kernel.close()
    with pytest.raises(StopAsyncIteration):
        await pending


async def test_a_reader_of_deltas_can_go_on_from_a_frame(kernel):
    for text in ("one", "two", "three"):
        kernel.push_delta("alice", text)

    frames = kernel.deltas("alice", after=2)

    assert (await anext(frames)).text == "three"
    await frames.aclose()


async def test_a_place_past_the_head_of_deltas_is_an_earlier_incarnation_s_and_joins(kernel):
    kernel.push_delta("alice", "held")
    frames = kernel.deltas("alice", after=500)

    assert (await anext(frames)).text == "held"
    await frames.aclose()


async def test_a_commit_that_moves_no_head_wakes_no_one(kernel):
    await add(kernel, 1)
    head = kernel.head
    changed = asyncio.ensure_future(kernel.changed(head))
    await asyncio.sleep(0)

    await kernel.put_body(b"a body is no event")
    await asyncio.sleep(0)

    assert not changed.done()

    await add(kernel, 1)
    await changed


async def test_a_frame_of_live_text_is_cut_so_a_ring_is_bounded_in_bytes(kernel):
    kernel.push_delta("alice", "x" * (1024 * 1024))

    frame = await anext(kernel.deltas("alice"))

    assert len(frame.text) == 64 * 1024


async def test_first_says_whether_the_work_won_and_drops_what_lost():
    held = asyncio.Event()
    rival = asyncio.ensure_future(held.wait())

    assert await first(asyncio.sleep(0), rival)
    assert rival.cancelled()

    work = asyncio.ensure_future(held.wait())
    assert not await first(work, asyncio.sleep(0))
    assert work.cancelled()


async def test_first_raises_what_the_work_raised():
    async def fails() -> None:
        raise ValueError("no")

    with pytest.raises(ValueError, match="no"):
        await first(fails(), asyncio.Event().wait())


@settings(max_examples=200, deadline=None)
@given(steps=st.lists(st.text(max_size=6) | st.none(), max_size=40), reads=st.lists(st.booleans(), max_size=40))
def test_a_tail_joined_to_what_was_committed_is_the_text(steps, reads):
    """A `None` step ends what was said, as an item does: the journal holds it through that seq. A reader who follows,
    now and then, and one who joins at any point each see all that was said, and nothing twice."""
    ring = Ring("alice")
    committed: list[tuple[int, str]] = []
    saying = ""
    place, through, shown = 0, 0, ""

    def journal(upto: int) -> str:
        return "".join(text for seq, text in committed if seq <= upto)

    for step, read in zip_longest(steps, reads, fillvalue=False):
        if step is None:
            committed.append((len(committed) + 1, saying))
            saying = ""
            ring.end(len(committed))
        elif step:
            saying += step
            ring.push(step)
        if read and (delta := ring.since(place)) is not None:
            if delta.ended is not None:
                through, shown = delta.ended, ""
            place, shown = delta.frame, shown + delta.text
        joined = ring.since(None)
        assert (joined.text if joined else "") == saying
        assert joined is None or joined.ended == (len(committed) or None)

    if (delta := ring.since(place)) is not None:
        if delta.ended is not None:
            through, shown = delta.ended, ""
        shown += delta.text
    assert journal(through) + shown == journal(len(committed)) + saying
