"""Readers: pages, cursors, a shared pulse and lossy live text."""

import asyncio
import sqlite3

import pytest

from platoon_harness.kernel import Args, Extension, Kernel, Refused, Txn, op

from .support import ALICE, HUMAN, events_of, notes, refusal_of, refused_code, result_of


async def add(kernel, count: int, stream: str = "note/a") -> None:
    for _ in range(count):
        result_of(await kernel.submit(kernel.runtime, "note.add", {"stream": stream}))


async def test_read_pages_through_the_journal(kernel):
    await add(kernel, 5)

    first = kernel.read(HUMAN, after=0, limit=2)
    second = kernel.read(HUMAN, after=first.cursor, limit=2)
    third = kernel.read(HUMAN, after=second.cursor, limit=2)

    assert [e.seq for e in first.events] == [1, 2]
    assert [e.seq for e in second.events] == [3, 4]
    assert [e.seq for e in third.events] == [5]
    assert (third.cursor, third.head) == (5, 5)


async def test_read_matches_stream_names(kernel):
    await add(kernel, 2, "note/a")
    await add(kernel, 1, "other/b")

    page = kernel.read(HUMAN, after=0, match="note/*")

    assert [e.stream for e in page.events] == ["note/a", "note/a"]
    assert page.cursor == 3


async def test_a_filtered_page_is_bounded_by_what_it_scans(kernel):
    await add(kernel, 3, "other/b")
    await add(kernel, 3, "note/a")

    page = kernel.read(HUMAN, after=0, match="note/*", limit=2)

    assert [e.seq for e in page.events] == [4, 5]
    assert page.cursor == 5
    assert kernel.read(HUMAN, after=page.cursor, match="note/*", limit=2).events[0].seq == 6


async def test_reading_past_the_head_is_empty(kernel):
    await add(kernel, 1)
    page = kernel.read(HUMAN, after=9)
    assert (page.events, page.cursor, page.head) == ((), 9, 1)


async def test_read_is_refused_for_agents(kernel):
    with pytest.raises(Refused) as error:
        kernel.read(ALICE, after=0)
    assert refused_code(error) == "not_permitted"
    with pytest.raises(Refused):
        await anext(aiter(kernel.follow(ALICE, after=0)))


async def test_follow_is_catch_up_then_live(kernel):
    await add(kernel, 2)
    follower = kernel.follow(HUMAN, after=0)

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
    follower = kernel.follow(HUMAN, after=0, match="note/*")
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
    followers = [kernel.follow(HUMAN, after=0) for _ in range(20)]
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
    async for page in kernel.follow(HUMAN, after=0):
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
        by_sql = kernel.read(HUMAN, after=0, match=pattern)
        assert [e.seq for e in by_tail.events] == [e.seq for e in by_sql.events]


async def test_read_connections_stay_few(kernel):
    with kernel._reading(), kernel._reading(), kernel._reading(), kernel._reading(), kernel._reading():
        pass
    assert kernel._idle.qsize() == 4


async def test_follow_ends_when_the_kernel_closes(kernel):
    await add(kernel, 1)
    pages = []

    async def collect() -> None:
        async for page in kernel.follow(HUMAN, after=0):
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
    pages = [page async for page in reader.follow(HUMAN, after=0)]
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


async def test_a_query_sees_one_snapshot(kernel):
    with kernel._reading() as db:
        db.execute("BEGIN")
        assert db.execute("SELECT count(*) FROM events").fetchone()[0] == 0
        await add(kernel, 1)
        assert db.execute("SELECT count(*) FROM events").fetchone()[0] == 0
        db.execute("COMMIT")
        assert db.execute("SELECT count(*) FROM events").fetchone()[0] == 1


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

    assert (frame.agent, frame.n, frame.text, frame.lag) == ("alice", 1, "hel", 0)
    assert events_of(kernel) == []
    await frames.aclose()


async def test_a_slow_reader_of_deltas_gets_a_lag_marker(kernel):
    frames = kernel.deltas("alice")
    pending = asyncio.ensure_future(anext(frames))
    await asyncio.sleep(0)
    kernel.push_delta("alice", "first")
    assert (await pending).text == "first"

    for n in range(300):
        kernel.push_delta("alice", str(n))

    frame = await anext(frames)
    assert (frame.text, frame.lag) == ("44", 44)
    assert (await anext(frames)).lag == 0
    await frames.aclose()


async def test_a_late_reader_of_deltas_starts_with_what_is_held(kernel):
    for n in range(300):
        kernel.push_delta("alice", str(n))

    frames = kernel.deltas("alice")
    frame = await anext(frames)

    assert (frame.text, frame.lag) == ("44", 0)
    await frames.aclose()


async def test_deltas_end_when_the_kernel_closes(kernel):
    frames = kernel.deltas("alice")
    pending = asyncio.ensure_future(anext(frames))
    await asyncio.sleep(0)
    kernel.close()
    with pytest.raises(StopAsyncIteration):
        await pending
