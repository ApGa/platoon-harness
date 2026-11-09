"""A replay: a read-only copy of a session, whose journal is the original's through the playhead, which a seek moves
either way, from a checkpoint of its views where one lies nearer."""

import asyncio
import contextlib
import sqlite3
import sys
from pathlib import Path

import pytest

from platoon_harness import Refused, Replay, Session
from platoon_harness import session as session_module
from platoon_harness.kernel import Kernel, ManualClock
from platoon_harness.kernel.journal import open_writer
from platoon_harness.primitives import PRIMITIVES
from platoon_harness.testing import Say

from ...recorded import RECORDED, restored
from .support import in_state, of_type, solo, until

pytestmark = pytest.mark.timeout(60)

CREDIT = {"kind": "credit", "producer": "even-split", "producer_version": "1", "scope": "local"}


def files(folder: Path) -> dict[str, int]:
    """Each file under a folder, by its path within it, with its size, but for what a reader of SQLite leaves."""
    return {
        str(path.relative_to(folder)): path.stat().st_size
        for path in folder.rglob("*")
        if path.is_file() and not path.name.endswith(("-shm", "-wal"))
    }


async def recorded(root: Path, *said: str) -> int:
    """A closed session `s` under `root`, whose `bob` heard and answered each of `said`, and its head."""
    async with Session.start(solo(*([Say(f"heard {words}")] for words in said)), name="s", root=root) as session:
        await in_state(session, "bob", "idle")
        for count, words in enumerate(said, 1):
            await session.send("@bob", words)
            await until(lambda: of_type(session, "turn.ended"), session, lambda ended, count=count: len(ended) == count)
        return await session.head()


def then(original: Path, journal: Path, at: int) -> Kernel:
    """A kernel over the original's events through `at` and their bodies, a journal written as a session's is and no
    copy, whose clock stands at the wall time of the event at `at`: the session as it stood then."""
    uri = f"{(original / 'journal.sqlite').as_uri()}?mode=ro"
    with (
        contextlib.closing(sqlite3.connect(uri, uri=True)) as read,
        contextlib.closing(open_writer(journal, 0.0)) as db,
    ):
        read.row_factory = sqlite3.Row
        events = read.execute("SELECT * FROM events WHERE seq <= ?", (at,)).fetchall()
        with db:
            db.executemany(f"INSERT INTO events VALUES ({', '.join('?' * len(events[0]))})", map(tuple, events))
            db.executemany("INSERT INTO bodies VALUES (?, ?, ?)", map(tuple, read.execute("SELECT * FROM bodies")))
    return Kernel.open(journal.parent, clock=ManualClock(events[-1]["wall_time"]), extensions=PRIMITIVES)


async def test_a_replay_reads_as_the_session_read_at_its_playhead(tmp_path):
    await recorded(tmp_path, "first", "second")
    async with Replay.open("s", root=tmp_path) as replay:
        spawned = next(event.seq for event in (await replay.page(limit=4096)).events if event.type == "agent.spawned")

        assert replay.at == 0 and await replay.session.head() == 0
        assert await replay.session.agents() == []
        await replay.seek(spawned)
        assert [row["agent"] for row in await replay.session.agents()] == ["bob"]
        assert [event.seq async for event in replay.session.events()] == list(range(1, spawned + 1))
        await replay.seek(replay.total)
        said = [event.gist for event in await of_type(replay.session, "item.recorded")]
        assert said == ["heard first", "heard second"]
        assert (await replay.session.status())["state"] == "stopped"


async def test_a_replay_works_out_what_was_due_spent_or_stalled_at_its_playhead_s_time_never_now(tmp_path):
    """The mixed team's recorded session stalled a second in, at event 45, waiting for its person, and had spent half a
    minute of its 20 by event 200: a replay at each says so, as a kernel over the same events at that event's wall time
    does, where today's clock would call it done, with a timer due and its wall time spent."""
    name = restored(RECORDED, tmp_path)
    original = tmp_path / "sessions" / name
    async with Replay.open(name, root=tmp_path) as replay:
        for at in (45, 200):
            await replay.seek(at)
            (tmp_path / str(at)).mkdir()
            kernel = then(original, tmp_path / str(at) / "journal.sqlite", at)
            try:
                assert await replay.session.status() == kernel.query(Kernel.runtime, "session.status", {}).result
                assert await replay.session.budgets() == kernel.query(Kernel.runtime, "budget.status", {}).result
            finally:
                kernel.close()
            if at == 45:
                assert (await replay.session.status())["stalled"] is True
        assert 0 < {row["unit"]: row["spent"] for row in await replay.session.budgets()}["wall"] < 60


async def test_nothing_in_a_replay_acts_on_its_session_and_each_write_says_why(tmp_path):
    head = await recorded(tmp_path, "first")
    before = files(tmp_path / "sessions" / "s")
    async with Replay.open("s", root=tmp_path) as replay:
        await replay.seek(replay.total)
        session = replay.session
        refusal = (await session.submit("message.send", to="@bob", gist="again")).refusal

        assert refusal is not None and refusal.code == "unsupported" and "replay of session s" in str(refusal.detail)
        for write in (
            session.put_body(b"a body"),
            session.mark("inbox/bob", 1),
            session.annotate("agent/bob@1", status="scored", value=1.0, head_seq=head, **CREDIT),
        ):
            with pytest.raises(Refused):
                await write
        assert await session.head() == replay.total

    async with Session.attach("s", root=tmp_path) as history:
        assert await history.head() == replay.total
    assert files(tmp_path / "sessions" / "s") == before


async def test_a_replay_s_copies_live_under_the_root_never_in_the_session_s_folder_and_go_when_it_closes(tmp_path):
    await recorded(tmp_path, "first")
    before = files(tmp_path / "sessions" / "s")
    replay = await Replay.open("s", root=tmp_path)
    try:
        await replay.seek(replay.total)
        assert replay.folder.parent == tmp_path / "replays"
        assert replay.session.folder.is_relative_to(replay.folder)
        assert files(tmp_path / "sessions" / "s") == before
    finally:
        await replay.close()

    assert list((tmp_path / "replays").iterdir()) == []
    assert files(tmp_path / "sessions" / "s") == before


async def test_a_seek_goes_on_from_the_copy_or_starts_a_new_one_from_the_nearest_checkpoint(tmp_path, monkeypatch):
    """With a checkpoint every 8 events, a seek forward goes on in the copy it has, and one back, or one forward to a
    checkpoint more than 8 events past the playhead, starts a copy anew from the nearest at or below where it goes,
    which a new session is a guest of; each reads as a copy made from nothing to there would."""
    monkeypatch.setattr(session_module, "CHECKPOINT_EVENTS", 8)
    head = await recorded(tmp_path, "first", "second", "third")
    async with Replay.open("s", root=tmp_path) as replay:
        building = replay._building
        assert building is not None
        await building
        checkpoints = sorted(replay._checkpoints)
        assert checkpoints and all(at % checkpoints[0] == 0 for at in checkpoints) and checkpoints[-1] < head

        first = replay.session
        await replay.seek(checkpoints[0] - 1)
        assert replay.session is first
        await replay.seek(checkpoints[-1] + 1)
        far = replay.session
        assert far is not first
        await replay.seek(checkpoints[-1] + 2)
        assert replay.session is far
        await replay.seek(3)
        back = replay.session
        assert back is not far and await back.head() == 3

        for at in (checkpoints[0], checkpoints[-1] + 2, head):
            await replay.seek(at)
            async with Replay.open("s", root=tmp_path) as fresh:
                await fresh.seek(at)
                assert await replay.session.agents() == await fresh.session.agents()
                assert await replay.session.status() == await fresh.session.status()
                assert [event.seq async for event in replay.session.events()] == list(range(1, at + 1))


async def test_a_replay_played_on_through_a_checkpoint_goes_on_in_the_copy_it_has(tmp_path, monkeypatch):
    """Stepping on an event at a time past two checkpoints never starts a copy anew, which a client would draw anew."""
    monkeypatch.setattr(session_module, "CHECKPOINT_EVENTS", 8)
    await recorded(tmp_path, "first", "second", "third")
    async with Replay.open("s", root=tmp_path) as replay:
        assert replay._building is not None
        await replay._building
        first, second = sorted(replay._checkpoints)[:2]
        await replay.seek(first - 2)
        session = replay.session

        for at in range(first - 1, second + 3):
            await replay.seek(at)
            assert replay.session is session and await session.head() == at


async def test_a_checkpoint_that_cannot_be_made_is_said_and_a_seek_goes_on_without_it(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(session_module, "CHECKPOINT_EVENTS", 8)
    await recorded(tmp_path, "first", "second")

    def full(*_: object, **__: object) -> None:
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(session_module.shutil, "copytree", full)
    async with Replay.open("s", root=tmp_path) as replay:
        assert replay._building is not None
        await replay._building
        await replay.seek(replay.total)

        assert replay._checkpoints == {} and await replay.session.head() == replay.total
    assert "replay of s keeps no more checkpoints: [Errno 28] No space left on device" in caplog.text


async def test_a_replay_whose_process_was_killed_leaves_a_folder_the_next_replay_takes_back(tmp_path):
    """A replay's folder is held by its process alone, so one killed before it closed it is taken back as another opens,
    and one still held stays."""
    await recorded(tmp_path, "first")
    opening = (
        "import asyncio, sys\n"
        "from platoon_harness import Replay\n"
        "async def main():\n"
        f"    replay = await Replay.open('s', root={str(tmp_path)!r})\n"
        "    print(replay.folder, flush=True)\n"
        "    await asyncio.to_thread(sys.stdin.read)\n"
        "asyncio.run(main())\n"
    )
    killed = await asyncio.create_subprocess_exec(
        sys.executable, "-c", opening, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE
    )
    assert killed.stdout is not None
    left = Path((await killed.stdout.readline()).decode().strip())
    killed.kill()
    await killed.wait()
    assert left.parent == tmp_path / "replays" and (left / "1" / "s" / "journal.sqlite").exists()

    async with Replay.open("s", root=tmp_path) as held:
        assert not left.exists()
        async with Replay.open("s", root=tmp_path) as other:
            assert held.folder.exists() and other.folder != held.folder
    assert list((tmp_path / "replays").iterdir()) == []


async def test_a_replay_of_a_live_session_replays_its_record_up_to_its_opening_and_stays_read_only(tmp_path):
    async with Session.start(solo([Say("on it")], [Say("again")]), name="s", root=tmp_path) as session:
        await in_state(session, "bob", "idle")
        async with Replay.open("s", root=tmp_path) as replay:
            total = replay.total
            assert 0 < total <= await session.head()

            await session.send("@bob", "go")
            await until(lambda: of_type(session, "turn.ended"), session, lambda ended: len(ended) == 1)
            await replay.seek(total)

            assert replay.total == total and await replay.session.head() == total
            with pytest.raises(Refused) as error:
                await replay.seek(total + 1)
            assert error.value.refusal.code == "invalid"
            assert (await replay.session.submit("session.close")).refusal is not None
        assert (await session.status())["state"] == "open"


async def test_a_replay_keeps_what_estimators_said_as_it_stood_when_it_opened(tmp_path):
    head = await recorded(tmp_path, "first")
    async with Session.attach("s", root=tmp_path) as history:
        said = await history.annotate("agent/bob@1", status="scored", value=0.5, head_seq=head, **CREDIT)
    async with Replay.open("s", root=tmp_path) as replay:
        async with Session.attach("s", root=tmp_path) as history:
            later = {**CREDIT, "producer_version": "2"}
            await history.annotate("agent/bob@1", status="scored", value=1.0, head_seq=head, **later)
        await replay.seek(replay.total)

        kept = await replay.session.annotations("agent/bob@1")
        assert [(row.id, row.value, row.head_seq, row.wall_time) for row in kept] == [
            (said.id, 0.5, head, said.wall_time)
        ]


async def test_a_replay_of_no_session_or_one_never_opened_is_refused(tmp_path):
    with pytest.raises(Refused) as error:
        await Replay.open("none", root=tmp_path)
    assert error.value.refusal.code == "not_found"
    assert not (tmp_path / "replays").exists() or list((tmp_path / "replays").iterdir()) == []


async def test_seeks_at_once_are_taken_one_after_another(tmp_path):
    await recorded(tmp_path, "first", "second")
    async with Replay.open("s", root=tmp_path) as replay:
        await asyncio.gather(replay.seek(replay.total), replay.seek(5), replay.seek(replay.total - 1))
        assert replay.at == replay.total - 1 and await replay.session.head() == replay.total - 1
