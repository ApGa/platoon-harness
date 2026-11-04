"""The board and the map's replies over a session whose clock the test moves: posts from a chat or from every channel
and group, sorted new or active, and never by votes, which a session has none of, and messages over time by the
journal's times."""

import contextlib
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest

from platoon_harness import Session, Team
from platoon_harness.kernel import ManualClock
from platoon_harness.testing import Hang, ScriptedDriver
from platoon_harness_cli.web import replies
from platoon_harness_cli.web.projection import Projection

from ..runtime.support import harness, in_state
from .support import Browser, caught_up, served

pytestmark = pytest.mark.timeout(60)

START = 1000.0
"""When the session's first message is sent, by the session's own clock. `web`'s clock reads a time far after it."""
STEP = 60.0


@pytest.fixture(autouse=True)
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("PLATOON_HARNESS_HOME", str(tmp_path))
    return tmp_path


def _team() -> Team:
    """`lead`, which waits, a topic `general` everyone reads, and a topic `aside` only workers read, of whom there are
    none."""
    roles = {
        "lead": {"harness": harness(lambda: ScriptedDriver([[Hang()]]))},
        "worker": {"harness": harness(lambda: ScriptedDriver([[Hang()]])), "count": 0},
    }
    channels = {
        "general": {"kind": "topic", "writers": "all", "readers": "all"},
        "aside": {"kind": "topic", "writers": "all", "readers": "role:worker"},
    }
    return Team.model_validate({"roles": roles, "topology": {"edges": {"lead": ["human"]}, "channels": channels}})


class Board:
    """A session, its page served, and a browser on a view link, with the chats by name."""

    def __init__(self, session: Session, browser: Browser, clock: ManualClock) -> None:
        self.session, self.browser, self.clock = session, browser, clock
        self.chats: dict[str, str] = {}

    async def send(self, to: str, gist: str, reply_to: str | None = None) -> str:
        """Send as the person, then move the session's clock on a step, and say the message's entry."""
        sent = await self.session.send(to, gist, reply_to=reply_to)
        self.clock.advance(STEP)
        return sent["ref"]

    async def view(self, name: str, params: dict[str, Any] | None = None) -> Any:
        """A reply, once the projection has folded all the journal holds, with the chats known by name."""
        await caught_up(self.browser.web, self.session)
        snapshot = await self.browser.view("view_snapshot")
        self.chats = {chat["name"] or " & ".join(chat["members"]): chat["id"] for chat in snapshot["chats"]}
        return await self.browser.view(name, params)

    async def refused(self, name: str, params: dict[str, Any]) -> tuple[int, str]:
        reply = await self.browser.request("POST", f"/v1/{name}", params)
        return reply.status, reply.json()["error"]


@contextlib.asynccontextmanager
async def board(root: Path) -> AsyncIterator[Board]:
    clock = ManualClock(START)
    async with Session.start(_team(), name="s", root=root, cwd=root, clock=clock) as session:
        await in_state(session, "lead", "idle")
        async with served(session, root, ManualClock(1_000_000.0)) as web:
            yield Board(session, await Browser(web).opened("view"), clock)


async def _threads(board: Board) -> None:
    """`first` in #general at the start, `second` a step later, a reply to `first` and one to that reply, `aside` in
    #aside, and `hello` to the lead."""
    first = await board.send("#general", "first")
    await board.send("#general", "second")
    reply = await board.send("#general", "a reply", reply_to=first)
    await board.send("#general", "and another", reply_to=reply)
    await board.send("#aside", "aside")
    await board.send("@lead", "hello")
    await board.view("view_info")


def _texts(reply: dict[str, Any]) -> list[str]:
    return [post["text"] for post in reply["posts"]]


async def test_posts_are_top_level_messages_newest_first_or_last_answered_first(root):
    async with board(root) as b:
        await _threads(b)
        new = await b.view("view_posts", {"chat": b.chats["general"], "sort": "new"})
        active = await b.view("view_posts", {"chat": b.chats["general"], "sort": "active"})
        unsorted = await b.view("view_posts", {"chat": b.chats["general"]})

    assert _texts(new) == ["second", "first"] and unsorted == new
    assert _texts(active) == ["first", "second"]
    first = active["posts"][0]
    assert first["comments"] == 2 and first["active_at"] == START + 3 * STEP
    assert active["posts"][1]["comments"] == 0 and active["posts"][1]["active_at"] == START + STEP
    assert first["at"] == "1970-01-01T00:16:40.000Z"


async def test_the_front_page_leaves_direct_chats_out_and_as_an_agent_holds_only_its_chats(root):
    async with board(root) as b:
        await _threads(b)
        front = await b.view("view_posts", {"sort": "new"})
        direct = await b.view("view_posts", {"chat": b.chats["lead & you"], "sort": "new"})
        as_lead = await b.view("view_posts", {"sort": "new", "as": "lead"})
        as_you = await b.refused("view_posts", {"sort": "new", "as": "you"})

    assert _texts(front) == ["aside", "second", "first"]
    assert _texts(direct) == ["hello"]
    assert _texts(as_lead) == ["second", "first"]
    assert as_you[0] == 400 and "no agent" in as_you[1]


async def test_no_post_has_a_vote_count_and_hot_and_top_are_refused_saying_why(root):
    async with board(root) as b:
        await _threads(b)
        posts = await b.view("view_posts", {"sort": "active"})
        refusals = [await b.refused("view_posts", {"sort": sort}) for sort in ("hot", "top")]
        unknown = await b.refused("view_posts", {"sort": "best"})

    assert posts["posts"] and all(post["votes"] is None for post in posts["posts"])
    assert all(status == 400 and "take no reactions" in why for status, why in refusals)
    assert unknown == (400, "sort is new or active")


async def test_an_offset_and_a_limit_page_through_posts_and_more_says_whether_any_follow(root):
    async with board(root) as b:
        await _threads(b)
        pages = [await b.view("view_posts", {"sort": "new", "limit": 2, "offset": offset}) for offset in (0, 2)]

    assert [_texts(page) for page in pages] == [["aside", "second"], ["first"]]
    assert [page["more"] for page in pages] == [True, False]


@pytest.mark.parametrize("sort", ["new", "active"])
def test_a_post_s_thread_is_followed_down_by_its_parent_s_index(tmp_path, sort):
    projection = Projection(tmp_path, "s", "you")
    asked: list[str] = []
    projection.db.set_trace_callback(asked.append)
    replies.posts(projection, {"sort": sort})
    projection.db.set_trace_callback(None)
    (thread,) = [sql for sql in asked if sql.lstrip().startswith("WITH RECURSIVE")]
    plan = [row["detail"] for row in projection.db.execute(f"EXPLAIN QUERY PLAN {thread}")]

    assert any("INDEX lines_parent (chat=? AND parent=?)" in detail for detail in plan)


async def test_activity_counts_messages_over_time_by_the_journal_s_times(root):
    async with board(root) as b:
        empty = await b.view("view_activity", {"buckets": 3})
        await _threads(b)
        whole = await b.view("view_activity", {"buckets": 3})
        window = await b.view("view_activity", {"buckets": 1, "from": START + STEP, "to": START + 3 * STEP})
        as_lead = await b.view("view_activity", {"buckets": 1, "as": "lead"})
        no_time = await b.refused("view_activity", {"from": "noon", "to": START})
        general = b.chats["general"]

    assert empty == {"start": None, "end": None, "width": None, "counts": [], "window": {}}
    assert (whole["start"], whole["end"], whole["width"]) == (START, START + 5 * STEP, 5 * STEP / 3)
    assert whole["counts"] == [2, 2, 2] and "window" not in whole
    assert window["window"] == {general: {"messages": 3, "sent": {"you": 3}}}
    assert as_lead["counts"] == [5] and as_lead["end"] == START + 5 * STEP
    assert no_time == (400, "from is a time in seconds since 1970")
