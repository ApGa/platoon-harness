"""The session folder: one writer, a versioned schema, and where a journal may live."""

import fcntl
import logging
import os
import sqlite3

import pytest

from platoon_harness.kernel import Filesystem, Kernel, Refused, filesystem, is_held, journal
from platoon_harness.kernel import writer as writer_module

from .support import dump, events_of, notes, refusal_of, refused_code, result_of


@pytest.mark.parametrize(
    ("pragma", "value"),
    [
        ("journal_mode", "wal"),
        ("synchronous", 2),
        ("fullfsync", 1),
        ("checkpoint_fullfsync", 1),
        ("cache_size", -8192),
        ("mmap_size", 0),
        ("temp_store", 2),
        ("wal_autocheckpoint", 16000),
        ("journal_size_limit", 67108864),
        ("secure_delete", 1),
    ],
)
async def test_journal_uses_the_pragmas_the_spike_chose(kernel, pragma, value):
    assert kernel._writer._db.execute(f"PRAGMA {pragma}").fetchone()[0] == value


async def test_a_checkpoint_moves_the_wal_off_the_commit_path(kernel, folder):
    result_of(await kernel.submit(kernel.runtime, "note.add", {}))
    db = sqlite3.connect(folder / "journal.sqlite", autocommit=True)
    assert db.execute("PRAGMA wal_checkpoint(NOOP)").fetchone()[2] == 0

    journal.checkpoint(db)

    _, logged, moved = db.execute("PRAGMA wal_checkpoint(NOOP)").fetchone()
    assert moved == logged > 0
    db.close()


async def test_a_pinned_wal_raises_an_alarm(kernel, folder, caplog, monkeypatch):
    monkeypatch.setattr(journal, "WAL_ALARM_FRAMES", 0)
    reader = sqlite3.connect(folder / "journal.sqlite", autocommit=True)
    reader.execute("BEGIN")
    reader.execute("SELECT count(*) FROM events").fetchone()
    result_of(await kernel.submit(kernel.runtime, "note.add", {}))
    db = sqlite3.connect(folder / "journal.sqlite", autocommit=True)

    with caplog.at_level(logging.WARNING, "platoon_harness.kernel"):
        journal.checkpoint(db)

    assert "holding a snapshot" in caplog.text
    reader.close()
    db.close()


async def test_closing_stops_the_checkpoint_thread(folder, clock):
    kernel = Kernel.open(folder, clock=clock)
    thread = kernel._writer._checkpointer._thread
    assert thread.is_alive()
    kernel.close()
    assert not thread.is_alive()


async def test_closing_with_a_reader_on_the_wal_says_so(folder, clock, caplog):
    kernel = Kernel.open(folder, clock=clock, extensions=[notes])
    result_of(await kernel.submit(kernel.runtime, "note.add", {}))
    reader = sqlite3.connect(folder / "journal.sqlite", autocommit=True)
    reader.execute("BEGIN")
    reader.execute("SELECT count(*) FROM events").fetchone()
    result_of(await kernel.submit(kernel.runtime, "note.add", {}))

    with caplog.at_level(logging.WARNING, "platoon_harness.kernel"):
        kernel.close()

    assert "keeps a WAL" in caplog.text
    reader.close()
    Kernel.open(folder, clock=clock, extensions=[notes]).close()


async def test_a_failing_close_still_lets_go_of_the_lock(folder, clock, monkeypatch):
    kernel = Kernel.open(folder, clock=clock)

    def failing(db):
        raise sqlite3.OperationalError("database table is locked")

    monkeypatch.setattr(writer_module, "truncate_wal", failing)
    with pytest.raises(sqlite3.OperationalError):
        kernel.close()
    monkeypatch.undo()

    assert kernel.closed
    Kernel.open(folder, clock=clock).close()


def test_one_writer_holds_the_lock(folder, clock):
    first = Kernel.open(folder, clock=clock)
    with pytest.raises(Refused) as error:
        Kernel.open(folder, clock=clock)
    assert refused_code(error) == "unavailable"
    first.close()
    Kernel.open(folder, clock=clock).close()


def test_a_reader_probing_the_lock_cannot_refuse_a_writer(folder, clock, monkeypatch):
    Kernel.open(folder, clock=clock).close()
    probe = os.open(folder / "lock", os.O_RDONLY)
    fcntl.flock(probe, fcntl.LOCK_SH)
    monkeypatch.setattr(journal.time, "sleep", lambda seconds: os.close(probe))

    Kernel.open(folder, clock=clock).close()


def test_the_session_id_is_a_constant_of_the_journal(folder, clock):
    kernel = Kernel.open(folder, clock=clock)
    session_id = kernel.session_id
    kernel.close()
    again = Kernel.open(folder, clock=clock)
    assert again.session_id == session_id
    again.close()


def test_schema_version_lives_in_meta(folder, clock):
    Kernel.open(folder, clock=clock).close()
    db = sqlite3.connect(folder / "journal.sqlite")
    assert db.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()[0] == "1"
    assert db.execute("SELECT value FROM meta WHERE key = 'created'").fetchone()[0] == "1000.0"
    with pytest.raises(sqlite3.IntegrityError, match="written once"):
        db.execute("UPDATE meta SET value = '2' WHERE key = 'schema_version'")
    db.executescript("DROP TRIGGER meta_no_update; UPDATE meta SET value = '2' WHERE key = 'schema_version';")
    db.close()
    with pytest.raises(Refused) as error:
        Kernel.open(folder, clock=clock)
    assert refused_code(error) == "unsupported"


def test_a_read_only_kernel_checks_the_schema_too(folder, clock):
    Kernel.open(folder, clock=clock).close()
    db = sqlite3.connect(folder / "journal.sqlite")
    db.executescript("DROP TRIGGER meta_no_update; UPDATE meta SET value = '2' WHERE key = 'schema_version';")
    db.close()
    with pytest.raises(Refused) as error:
        Kernel.open(folder, clock=clock, read_only=True)
    assert refused_code(error) == "unsupported"


def test_this_host_has_a_known_filesystem(tmp_path):
    assert filesystem(tmp_path).kind in {"local", "memory"}


def test_a_path_that_does_not_exist_yet_is_judged_by_its_ancestor(tmp_path):
    assert filesystem(tmp_path / "not" / "yet") == filesystem(tmp_path)


def test_fuse_subtypes_come_from_the_mount_table_by_device():
    device = os.makedev(0, 77)
    mountinfo = (
        "30 25 0:76 / /mnt/a rw - fuse.gcsfuse bucket rw\n"
        "31 25 0:77 / /mnt/b rw shared:1 - fuse.sshfs host:/x rw\n"
        "32 25 0:78 / /mnt/c rw - fuse.mine x rw\n"
    )
    assert journal.fuse_type(device, mountinfo) == Filesystem("fuse.sshfs", "network")
    assert journal.fuse_type(os.makedev(0, 78), mountinfo) == Filesystem("fuse.mine", "unknown")
    assert journal.fuse_type(os.makedev(0, 99), mountinfo) == Filesystem("fuse", "unknown")


def on(monkeypatch, name: str, kind: str) -> None:
    monkeypatch.setattr(journal, "filesystem", lambda path: Filesystem(name, kind))


def test_live_writers_are_refused_on_a_network_filesystem(monkeypatch, folder, clock):
    on(monkeypatch, "nfs", "network")
    with pytest.raises(Refused) as error:
        Kernel.open(folder, clock=clock)
    assert refused_code(error) == "unsupported"
    assert "network filesystem" in str(error.value)
    assert "/var/tmp/platoon-harness-$UID" in str(error.value)
    assert not folder.exists()


@pytest.mark.parametrize(
    ("name", "kind", "warning"), [("tmpfs", "memory", "not a reboot"), ("0x1234", "unknown", "known")]
)
def test_weaker_or_unknown_storage_is_said_out_loud(monkeypatch, caplog, folder, clock, name, kind, warning):
    on(monkeypatch, name, kind)
    with caplog.at_level(logging.WARNING, "platoon_harness.kernel"):
        Kernel.open(folder, clock=clock).close()
    assert warning in caplog.text


async def test_a_closed_journal_reads_from_anywhere(monkeypatch, folder, clock):
    kernel = Kernel.open(folder, clock=clock, extensions=[notes])
    result_of(await kernel.submit(kernel.runtime, "note.add", {"text": "kept"}))
    kernel.close()
    assert not (folder / "journal.sqlite-wal").exists()

    on(monkeypatch, "lustre", "network")
    closed = Kernel.open(folder, clock=clock, extensions=[notes], read_only=True)
    assert [event.gist for event in events_of(closed)] == ["kept"]
    assert result_of(closed.query(closed.runtime, "note.list", {})) == ["kept"]
    assert refusal_of(await closed.submit(closed.runtime, "note.add", {})) == "unsupported"
    closed.close()


async def test_a_copied_session_stays_readable(folder, clock, tmp_path):
    kernel = Kernel.open(folder, clock=clock, extensions=[notes])
    result_of(await kernel.submit(kernel.runtime, "note.add", {}))
    kernel.close()
    copy = tmp_path / "copy"
    copy.mkdir()
    (copy / "journal.sqlite").write_bytes((folder / "journal.sqlite").read_bytes())
    os.chmod(copy / "journal.sqlite", 0o400)

    reopened = Kernel.open(copy, clock=clock, extensions=[notes], read_only=True)
    assert len(events_of(reopened)) == 1
    reopened.close()


async def test_a_live_journal_on_a_network_filesystem_is_not_read(monkeypatch, kernel, folder, clock):
    result_of(await kernel.submit(kernel.runtime, "note.add", {}))
    on(monkeypatch, "nfs", "network")
    with pytest.raises(Refused):
        Kernel.open(folder, clock=clock, read_only=True)


async def test_a_live_journal_is_read_alongside_its_writer(kernel, folder, clock):
    result_of(await kernel.submit(kernel.runtime, "note.add", {}))
    reader = Kernel.open(folder, clock=clock, extensions=[notes], read_only=True)
    assert len(events_of(reader)) == 1
    result_of(await kernel.submit(kernel.runtime, "note.add", {}))
    assert len(events_of(reader)) == 2
    reader.close()


async def test_read_only_refuses_stale_views_loudly(folder, clock):
    kernel = Kernel.open(folder, clock=clock)
    result_of(await kernel.submit(kernel.runtime, "runtime.start", {}))
    kernel.close()

    reader = Kernel.open(folder, clock=clock, extensions=[notes], read_only=True)
    assert refusal_of(reader.query(reader.runtime, "note.list", {})) == "unavailable"
    assert len(events_of(reader)) == 1
    reader.close()


async def test_read_only_notices_a_view_falling_behind(kernel, folder, clock):
    result_of(await kernel.submit(kernel.runtime, "note.add", {}))
    reader = Kernel.open(folder, clock=clock, extensions=[notes], read_only=True)
    assert result_of(reader.query(reader.runtime, "note.list", {})) == ["hello"]
    kernel.close()

    other = Kernel.open(folder, clock=clock)
    result_of(await other.submit(other.runtime, "runtime.start", {}))

    assert refusal_of(reader.query(reader.runtime, "note.list", {})) == "unavailable"
    reader.close()
    other.close()


async def test_a_read_only_head_moves_with_the_journal(kernel, folder, clock):
    reader = Kernel.open(folder, clock=clock, extensions=[notes], read_only=True)
    assert reader.head == 0
    result_of(await kernel.submit(kernel.runtime, "note.add", {}))
    assert reader.head == 1
    reader.close()


async def test_a_reader_of_a_closed_journal_stops_when_a_writer_returns(folder, clock):
    kernel = Kernel.open(folder, clock=clock, extensions=[notes])
    result_of(await kernel.submit(kernel.runtime, "note.add", {}))
    kernel.close()
    reader = Kernel.open(folder, clock=clock, extensions=[notes], read_only=True)
    assert len(events_of(reader)) == 1

    again = Kernel.open(folder, clock=clock, extensions=[notes])
    result_of(await again.submit(again.runtime, "note.add", {}))
    again.close()

    with pytest.raises(Refused) as error:
        reader.read(reader.runtime, after=0)
    assert refused_code(error) == "unavailable"
    assert refusal_of(reader.query(reader.runtime, "note.list", {})) == "unavailable"
    reader.close()


async def test_reopening_keeps_everything(folder, clock):
    kernel = Kernel.open(folder, clock=clock, extensions=[notes])
    result_of(await kernel.submit(kernel.runtime, "note.add", {"text": "kept"}))
    before = dump(folder)
    kernel.close()

    again = Kernel.open(folder, clock=clock, extensions=[notes])
    assert dump(folder) == before
    assert again.head == 1
    again.close()


async def test_the_lock_alone_says_whether_a_runtime_is_live(kernel, folder, clock):
    assert is_held(folder)
    assert not kernel.read_only

    kernel.close()

    assert not is_held(folder)
    assert not is_held(folder.parent)
    reader = Kernel.open(folder, clock=clock, extensions=[notes], read_only=True)
    assert reader.read_only
    reader.close()
