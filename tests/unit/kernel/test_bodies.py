"""The content store: bytes first, citations after, redaction without a hole in the graph."""

import hashlib
import os
import sqlite3

import pytest

from platoon_harness.kernel import Refused

from .support import events_of, refusal_of, refused_code, result_of, supervised, until

SMALL = b"small body"
LARGE = b"x" * (64 * 1024 + 1)


def blob_path(folder, sha256):
    return folder / "blobs" / sha256[:2] / sha256


async def test_a_small_body_stays_in_the_journal(kernel, folder):
    sha256 = await kernel.put_body(SMALL)
    assert sha256 == hashlib.sha256(SMALL).hexdigest()
    assert kernel.get_body(sha256) == SMALL
    assert not (folder / "blobs").exists()


async def test_a_body_of_exactly_64_kib_stays_in_the_journal(kernel, folder):
    assert kernel.get_body(await kernel.put_body(b"x" * (64 * 1024))) == b"x" * (64 * 1024)
    assert not (folder / "blobs").exists()


async def test_a_large_body_goes_to_blobs(kernel, folder):
    sha256 = await kernel.put_body(LARGE)
    assert blob_path(folder, sha256).read_bytes() == LARGE
    assert kernel.get_body(sha256) == LARGE


async def test_storing_a_body_twice_is_harmless(kernel):
    assert await kernel.put_body(LARGE) == await kernel.put_body(LARGE)
    assert await kernel.put_body(SMALL) == await kernel.put_body(SMALL)


async def test_blobs_are_fsynced_before_they_can_be_cited(kernel, folder, monkeypatch):
    synced = []
    real_fsync = os.fsync
    real_replace = os.replace

    def fsync(fd):
        synced.append("file" if os.path.isfile(f"/proc/self/fd/{fd}") else "folder")
        real_fsync(fd)

    def replace(source, target):
        synced.append("rename")
        real_replace(source, target)

    monkeypatch.setattr(os, "fsync", fsync)
    monkeypatch.setattr(os, "replace", replace)

    await kernel.put_body(LARGE)

    assert synced == ["file", "rename", "folder", "folder", "folder"]


async def test_storing_a_body_again_syncs_what_a_crash_left_unsynced(kernel, monkeypatch):
    await kernel.put_body(LARGE)
    synced = []
    monkeypatch.setattr(os, "fsync", synced.append)

    await kernel.put_body(LARGE)

    assert len(synced) == 3


async def test_a_cited_body_must_exist(kernel):
    sha256 = await kernel.put_body(SMALL)
    assert result_of(await kernel.submit(kernel.runtime, "note.add", {"refs": [f"sha256:{sha256}"]}))
    missing = {"refs": ["sha256:" + "0" * 64]}
    assert refusal_of(await kernel.submit(kernel.runtime, "note.add", missing)) == "not_found"


async def test_an_unknown_body_is_not_found(kernel):
    with pytest.raises(Refused) as error:
        kernel.get_body("0" * 64)
    assert refused_code(error) == "not_found"


async def test_a_blob_erased_during_a_read_is_not_found(kernel, folder):
    sha256 = await kernel.put_body(LARGE)
    blob_path(folder, sha256).unlink()
    with pytest.raises(Refused) as error:
        kernel.get_body(sha256)
    assert refused_code(error) == "not_found"


@pytest.mark.parametrize("body", [SMALL, LARGE], ids=["inline", "blob"])
async def test_a_tombstone_erases_bytes_and_keeps_the_event_and_hash(kernel, folder, clock, body):
    sha256 = await kernel.put_body(body)
    citing = await kernel.submit(kernel.runtime, "note.add", {"refs": [f"sha256:{sha256}"], "text": sha256})
    head = kernel.head

    async with supervised(kernel):
        result_of(await kernel.submit(kernel.runtime, "body.tombstone", {"sha256": sha256}))
        with pytest.raises(Refused) as error:
            kernel.get_body(sha256)
        assert "tombstoned" in str(error.value)
        await until(kernel, "effect.finished", after=head)

    assert not blob_path(folder, sha256).exists()
    with kernel._reading() as db:
        assert db.execute("SELECT count(*) FROM bodies").fetchone()[0] == 0
    assert result_of(kernel.query(kernel.runtime, "note.list", {})) == [sha256]
    assert events_of(kernel)[citing.seq - 1].gist == sha256


async def test_a_tombstone_names_a_hash_and_never_a_path(kernel):
    args = {"sha256": "../../journal.sqlite"}
    assert refusal_of(await kernel.submit(kernel.runtime, "body.tombstone", args)) == "invalid"


@pytest.mark.parametrize("body", [SMALL, LARGE], ids=["inline", "blob"])
async def test_tombstoned_content_does_not_come_back(kernel, folder, body):
    sha256 = await kernel.put_body(body)
    result_of(await kernel.submit(kernel.runtime, "body.tombstone", {"sha256": sha256}))
    await kernel.erase_body(sha256)

    with pytest.raises(Refused) as error:
        await kernel.put_body(body)

    assert refused_code(error) == "conflict"
    assert not blob_path(folder, sha256).exists()


async def test_a_busy_writer_leaves_a_stored_blob_alone(kernel, monkeypatch):
    sha256 = await kernel.put_body(LARGE)

    async def full(run, *, owner):
        raise Refused("busy", retry_after=1.0)

    with monkeypatch.context() as patched:
        patched.setattr(kernel._writer, "call", full)
        with pytest.raises(Refused):
            await kernel.put_body(LARGE)

    assert kernel.get_body(sha256) == LARGE


async def test_erased_bytes_leave_the_journal_and_the_wal_while_it_runs(kernel, folder):
    secret = b"TOPSECRET-" * 100
    sha256 = await kernel.put_body(secret)
    result_of(await kernel.submit(kernel.runtime, "body.tombstone", {"sha256": sha256}))

    await kernel.erase_body(sha256)

    stored = b"".join(path.read_bytes() for path in folder.glob("journal.sqlite*"))
    assert b"TOPSECRET-" not in stored


async def test_a_reader_holding_the_wal_keeps_the_erase_open(kernel, folder):
    sha256 = await kernel.put_body(SMALL)
    result_of(await kernel.submit(kernel.runtime, "body.tombstone", {"sha256": sha256}))
    reader = sqlite3.connect(folder / "journal.sqlite", autocommit=True)
    reader.execute("BEGIN")
    reader.execute("SELECT count(*) FROM events").fetchone()
    result_of(await kernel.submit(kernel.runtime, "note.add", {}))

    with pytest.raises(Refused) as error:
        await kernel.erase_body(sha256)

    assert refused_code(error) == "busy"
    reader.close()
    await kernel.erase_body(sha256)


async def test_only_a_tombstoned_body_can_be_erased(kernel):
    sha256 = await kernel.put_body(SMALL)
    with pytest.raises(Refused) as error:
        await kernel.erase_body(sha256)
    assert refused_code(error) == "conflict"
    assert kernel.get_body(sha256) == SMALL
