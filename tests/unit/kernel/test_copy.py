"""A copy of a journal through a seq: its source's events as they were committed there, folded as they were, with the
bodies they name, which takes no command."""

import sqlite3
from pathlib import Path

import pytest

from platoon_harness.kernel import Kernel, Refused

from .support import HUMAN, dump, enroll, grant, notes, refusal_of, refused_code, result_of

SMALL = b"small body"
LARGE = b"x" * (64 * 1024 + 1)


def rows(folder: Path) -> list[tuple[object, ...]]:
    """Every event of a journal, each column as its row holds it."""
    db = sqlite3.connect(f"{(folder / 'journal.sqlite').as_uri()}?mode=ro", uri=True)
    try:
        return db.execute("SELECT * FROM events ORDER BY seq").fetchall()
    finally:
        db.close()


@pytest.fixture
async def source(kernel: Kernel) -> Kernel:
    """A journal commands wrote: a person, their grant, notes, and two bodies, one in `blobs/`, each an event names."""
    await enroll(kernel, HUMAN)
    await grant(kernel, "human")
    for text in ("one", "two", "three"):
        result_of(await kernel.submit(HUMAN, "note.add", {"text": text}))
    for body in (SMALL, LARGE):
        named = await kernel.put_body(body)
        args = {"type": "note.attached", "stream": "note/a", "data": {"body": f"sha256:{named}"}}
        result_of(await kernel.submit(kernel.runtime, "note.mark", args))
    return kernel


def copy_in(tmp_path: Path, name: str = "copy") -> Kernel:
    return Kernel.open(tmp_path / name, extensions=[notes])


async def test_a_copy_through_a_seq_holds_its_source_s_events_as_committed_and_folds_them_as_it_did(
    source, folder, tmp_path
):
    copy = copy_in(tmp_path)
    try:
        await copy.copy(source, through=4)
        assert rows(tmp_path / "copy") == rows(folder)[:4]
        assert result_of(copy.query(HUMAN, "note.list", {})) == ["one", "two"]

        await copy.copy(source, through=source.head)
        copy.close()
        assert rows(tmp_path / "copy") == rows(folder)
        assert dump(tmp_path / "copy") == dump(folder)
    finally:
        copy.close()


async def test_a_copy_carries_the_bodies_its_events_name_and_no_other(source, tmp_path):
    copy = copy_in(tmp_path)
    try:
        await copy.copy(source, through=source.head - 1)
        named = [event.data["body"].removeprefix("sha256:") for event in source.read(source.runtime).events[-2:]]
        assert copy.get_body(named[0]) == SMALL
        with pytest.raises(Refused) as error:
            copy.get_body(named[1])
        assert refused_code(error) == "not_found"

        await copy.copy(source, through=source.head)
        assert copy.get_body(named[1]) == LARGE
    finally:
        copy.close()


async def test_a_copy_takes_no_command_and_runs_no_daemon(source, tmp_path):
    copy = copy_in(tmp_path)
    try:
        await copy.copy(source, through=source.head)
        head = copy.head

        assert refusal_of(await copy.submit(HUMAN, "note.add", {"text": "four"})) == "unsupported"
        assert refusal_of(await copy.recover()) == "unsupported"
        with pytest.raises(Refused) as error:
            await copy.put_body(b"another")
        assert refused_code(error) == "unsupported"
        with pytest.raises(Refused) as error:
            await copy.supervise()
        assert refused_code(error) == "unsupported"
        assert copy.head == head
        assert result_of(copy.query(HUMAN, "note.list", {})) == ["one", "two", "three"]
    finally:
        copy.close()


async def test_a_copy_is_still_one_once_it_is_opened_again(source, tmp_path):
    copy = copy_in(tmp_path)
    await copy.copy(source, through=4)
    copy.close()
    copy = copy_in(tmp_path)
    try:
        assert refusal_of(await copy.submit(HUMAN, "note.add", {"text": "four"})) == "unsupported"
        await copy.copy(source, through=source.head)
        assert copy.head == source.head
    finally:
        copy.close()


async def test_a_copy_only_grows_and_only_from_the_journal_it_was_first_copied_from(source, tmp_path):
    other = copy_in(tmp_path, "other")
    copy = copy_in(tmp_path)
    try:
        result_of(await other.submit(other.runtime, "note.add", {"text": "elsewhere"}))
        await copy.copy(source, through=4)

        for through in (3, source.head + 1):
            with pytest.raises(Refused) as error:
                await copy.copy(source, through=through)
            assert refused_code(error) == "invalid"
        with pytest.raises(Refused) as error:
            await copy.copy(other, through=other.head)
        assert refused_code(error) in ("invalid", "conflict")
        with pytest.raises(Refused) as error:
            await other.copy(source, through=source.head)
        assert refused_code(error) == "unsupported", "a journal commands wrote became a copy"
        assert copy.head == 4
    finally:
        copy.close()
        other.close()


async def test_a_copy_of_another_session_s_journal_is_refused_having_written_none_of_it(source, tmp_path):
    another = copy_in(tmp_path, "another")
    copy = copy_in(tmp_path)
    try:
        for text in ("a", "b", "c", "d", "e", "f"):
            result_of(await another.submit(another.runtime, "note.add", {"text": text}))
        await copy.copy(source, through=2)

        with pytest.raises(Refused) as error:
            await copy.copy(another, through=4)
        assert refused_code(error) == "conflict"
        assert len(rows(tmp_path / "copy")) == copy.head == 2
    finally:
        copy.close()
        another.close()
