"""The projection: the journal folded one way into what SwarmChat's page reads, the same from nothing as live."""

import json
import sqlite3
from pathlib import Path

import pytest

from platoon_harness import Session
from platoon_harness.kernel import Refusal
from platoon_harness_cli.web import projection as projection_module
from platoon_harness_cli.web.projection import FILE, SHOWN, Projection, hashed, shown

from ..runtime.support import in_state, of_type
from .support import LONG, QUIET, caught_up, rebuilt, scenario, served, tables, team

pytestmark = pytest.mark.timeout(60)


@pytest.fixture(autouse=True)
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("PLATOON_HARNESS_HOME", str(tmp_path))
    return tmp_path


def rows(folder: Path, sql: str, *args) -> list[tuple]:
    db = sqlite3.connect(folder / FILE)
    found = db.execute(sql, args).fetchall()
    db.close()
    return found


async def test_a_rebuild_from_nothing_equals_the_projection_folded_live(root):
    async with Session.start(team(), name="s", root=root, cwd=root) as session:
        async with served(session, root) as web:
            await scenario(session)
            through, live = web.projection.through, tables(session.folder / FILE)  # One step of the loop: nothing folds
        again = root / "again"
        again.mkdir()
        (await rebuilt(session, again, through)).close()

    assert tables(again / FILE) == live
    assert len(live["lines"]) > 10 and len(live["feed"]) > 10


async def test_a_chat_s_id_is_a_hash_of_the_session_and_what_the_chat_is(root):
    async with Session.start(team(), name="s", root=root, cwd=root) as session, served(session, root) as web:
        await scenario(session)
        await caught_up(web, session)
        chats = dict(rows(session.folder, "SELECT key, id FROM chats"))

    assert chats["channel/general"] == hashed("s", "channel/general")
    assert chats["queue/tasks"] == hashed("s", "queue/tasks")
    assert chats["direct:lead you"] == hashed("s", "direct:lead you")
    assert chats["direct:lead w1"] == hashed("s", "direct:lead w1")
    assert {"direct:w1 you"} <= set(chats)


async def test_a_direct_chat_merges_both_inboxes_in_journal_order(root):
    async with Session.start(team(), name="s", root=root, cwd=root) as session, served(session, root) as web:
        await scenario(session)
        await caught_up(web, session)
        chat = hashed("s", "direct:lead you")
        lines = rows(session.folder, "SELECT sender, gist, event FROM lines WHERE chat = ? ORDER BY seq", chat)

    said = [(sender, gist) for sender, gist, _ in lines]
    assert ("you", "Fix the flaky test") in said and ("lead", "I started a worker.") in said
    assert [event for *_, event in lines] == sorted(event for *_, event in lines)


async def test_an_agent_s_own_words_are_its_message_to_the_person_and_nothing_else_of_a_turn_is(root):
    async with Session.start(team(), name="s", root=root, cwd=root) as session, served(session, root) as web:
        await scenario(session)
        await caught_up(web, session)
        lines = rows(session.folder, "SELECT kind, sender, text FROM lines")

    texts = [text for _, _, text in lines]
    assert ("message", "lead", LONG) in lines
    assert not any("what to do" in text for text in texts), "a thought reached a chat"
    assert not any("task_add" in text or "agent_spawn" in text or "usage" in text for text in texts)
    assert {kind for kind, _, _ in lines} <= {"message", "created", "ended"}


async def test_a_message_is_delivered_by_evidence_alone_and_a_person_s_reading_is_none(root):
    async with Session.start(team(), name="s", root=root, cwd=root) as session, served(session, root) as web:
        await scenario(session)
        await caught_up(web, session)
        delivered = rows(
            session.folder,
            "SELECT l.sender, d.reader, d.event IS NOT NULL FROM deliveries AS d "
            "JOIN lines AS l ON (l.chat, l.seq) = (d.chat, d.seq)",
        )
        readers = {reader for _, reader, _ in delivered}
        landed = await of_type(session, "context.delivered")

    assert landed, "nothing was delivered to an agent"
    assert ("you", "lead", 1) in delivered
    assert "you" not in readers, "a person's reading is no evidence"


async def test_an_approval_is_a_card_that_says_who_decided_and_through_what(root):
    async with Session.start(team(), name="s", root=root, cwd=root) as session, served(session, root) as web:
        await scenario(session)
        await caught_up(web, session)
        cards = [
            json.loads(extra)["x_approval"]
            for (extra,) in rows(session.folder, "SELECT extra FROM lines WHERE extra LIKE '%x_approval%'")
        ]

    assert len(cards) == 1
    assert cards[0] | {"id": "?"} == {
        "id": "?",
        "version": 1,
        "state": "resolved",
        "verdict": "allow",
        "by": "you",
        "via": "test",
    }


async def test_an_agent_s_end_is_one_line_in_its_chat_with_the_person(root):
    async with Session.start(team(), name="s", root=root, cwd=root) as session, served(session, root) as web:
        await scenario(session)
        await caught_up(web, session)
        ended = rows(session.folder, "SELECT chat, extra FROM lines WHERE kind = 'ended'")

    assert ended == [(hashed("s", "direct:w1 you"), json.dumps({"x_end": {"status": "finished", "reason": None}}))]


async def test_a_tombstoned_body_is_erased_from_the_projection_too(root):
    secret = "the body that must go 4f1d"
    async with Session.start(QUIET, name="s", root=root, cwd=root) as session:
        await in_state(session, "lead", "idle")
        async with served(session, root) as web:
            sent = await session.send("#general", "a note", body=f"a note, and {secret}")
            await caught_up(web, session)
            assert rows(session.folder, "SELECT count(*) FROM lines WHERE text LIKE ?", f"%{secret}%") == [(1,)]
            body = (await of_type(session, "message.sent"))[-1].data["body"]

            await session.tombstone(body)
            await caught_up(web, session)

            text, file = rows(session.folder, "SELECT text, file FROM lines WHERE ref = ?", sent["ref"])[0]
            files = [path for path in session.folder.iterdir() if path.name.startswith(FILE)]
            stored = b"".join(path.read_bytes() for path in files)

    assert text.startswith("a note") and "tombstoned" in text and file is None
    assert secret.encode() not in stored


async def test_a_new_version_of_the_projection_drops_it_and_folds_again(root, monkeypatch):
    async with Session.start(QUIET, name="s", root=root, cwd=root) as session:
        await in_state(session, "lead", "idle")
        async with served(session, root) as web:
            await session.send("#general", "before")
            await caught_up(web, session)
        old = Projection(session.folder, "s", "you")
        through, feed_id = old.through, old.feed_id
        old.close()

        monkeypatch.setattr(projection_module, "VERSION", projection_module.VERSION + 1)
        new = Projection(session.folder, "s", "you")

    assert through > 0 and new.through == 0
    assert new.feed_id != feed_id
    new.close()


async def test_feed_numbers_are_kept_across_a_restart_of_web(root):
    async with Session.start(QUIET, name="s", root=root, cwd=root) as session:
        await in_state(session, "lead", "idle")
        async with served(session, root) as web:
            await session.send("#general", "one")
            await caught_up(web, session)
            first = list(web.projection.entries(0, 100))
        async with served(session, root) as web:
            assert [tuple(row) for row in web.projection.entries(0, 100)] == [tuple(row) for row in first]
            await session.send("#general", "two")
            await caught_up(web, session)
            after = list(web.projection.entries(first[-1]["n"], 100))

    assert after and after[0]["n"] == first[-1]["n"] + 1


def test_a_body_holding_its_gist_shows_in_its_place_and_one_too_long_is_cut_saying_so():
    whole = "line\n" * (SHOWN // 4)
    text, file = shown("line", whole.encode())

    assert text.endswith("the whole is attached.]") and len(text) < SHOWN + 100
    assert file is not None and file["size"] == len(whole) and file["text"]["more"]
    assert shown("hi there…", b"hi there, all of it") == ("hi there, all of it", None)


def test_a_body_that_does_not_hold_its_gist_comes_as_a_file_and_one_unread_says_why():
    assert shown("the spec", b"something else")[1]["name"] == "body.txt"
    assert shown("bytes", b"\xff\xfe")[1] == {"name": "body", "size": 2, "type": "application/octet-stream"}
    text, file = shown("gone", Refusal(code="not_found", detail="this body was tombstoned"))
    assert text == "gone\n\n[Its body is not shown: this body was tombstoned.]" and file is None


def test_a_projection_is_its_user_s_alone(tmp_path):
    Projection(tmp_path, "s", "you").close()

    assert (tmp_path / FILE).stat().st_mode & 0o777 == 0o600
