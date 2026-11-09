"""A replay's page: the page `web` serves for a session, over the replay's copy, which says it is a replay, takes its
controls from a control link alone, folds the copy as it grows, is heard as a reset where a copy starts anew, and
refuses every act of the session's, saying why."""

import asyncio
import contextlib
from collections.abc import AsyncIterator
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from platoon_harness import Session
from platoon_harness.kernel import ManualClock
from platoon_harness_cli.replay import nothing_acts
from platoon_harness_cli.web import serve
from platoon_harness_cli.web.server import REPLAYED, WATCHES, Web
from platoon_harness_cli.web.sessions import Sessions

from ...integration.test_web import call, opened
from ..runtime.support import of_type
from .support import Browser, scenario, team

pytestmark = pytest.mark.timeout(60)

CREDIT = {"kind": "credit", "producer": "even-split", "producer_version": "1", "scope": "local"}


def key(n: int) -> str:
    return f"{n:032x}"


@pytest.fixture(autouse=True)
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("PLATOON_HARNESS_HOME", str(tmp_path))
    return tmp_path


@pytest.fixture
async def head(root: Path) -> int:
    """A closed session `s`, run through the web tests' scenario, and its head."""
    async with Session.start(team(), name="s", root=root, cwd=root) as session:
        await scenario(session)
    async with Session.attach("s", root=root) as history:
        return await history.head()


@contextlib.asynccontextmanager
async def replayed() -> AsyncIterator[Web]:
    """A replay of `s`, served as `web s --replay` serves one, in this process."""
    stop, opened_at = asyncio.Event(), asyncio.get_running_loop().create_future()
    options = {"host": "127.0.0.1", "port": 0, "tls": None, "clock": ManualClock(1_000_000.0)}
    serving = asyncio.ensure_future(serve("s", stop, **options, opened=opened_at, replay=True))
    try:
        yield await opened_at
    finally:
        stop.set()
        await serving


@pytest.fixture
async def web(head: int) -> AsyncIterator[Web]:
    async with replayed() as web:
        yield web


async def control(browser: Browser, name: str, where: str | None = None) -> dict:
    reply = await browser.request("POST", "/x/replay", {"control": name, "where": where})
    assert reply.status == 200, reply.body
    return reply.json()


async def test_a_replay_s_page_says_it_is_one_and_refuses_every_act_saying_why(web, head, root):
    browser = await Browser(web).opened("control")
    await control(browser, "jump", str(head))
    info = await browser.view("view_info")
    command = {"op": "message.send", "args": {"to": "#general", "gist": "again"}, "key": key(1)}
    refused = (await browser.request("POST", "/x/command", command)).json()["refusal"]
    stored = (await browser.request("POST", "/x/body", b"a body")).json()
    diff = await browser.request("POST", "/v1/x_read", {"pane": "diff", "effect": 1})
    saying = await browser.view("x_read", {"pane": "saying", "agent": "lead"})

    why = nothing_acts("s")
    assert info["read_only"] is True and info["x"]["live"] is False and info["x"]["may"] == info["x"]["forms"] == []
    assert info["x"]["cannot"] == why
    assert info["x"]["replay"]["banner"].startswith(f"Replay of s, at event {head:,} of {head:,}")
    assert [one["name"] for one in info["x"]["replay"]["controls"]] == [
        "play", "speed", "step", "back", "turn", "turn-back", "jump"
    ]  # fmt: skip
    assert refused == {**refused, "code": "unsupported", "detail": why}
    assert stored["refusal"]["detail"] == why
    assert diff.status == 403 and why in diff.json()["error"]
    assert saying == {"version": 0, "text": "", "about": REPLAYED, "over": True}
    async with Session.attach("s", root=root) as history:
        assert await history.head() == head


async def test_a_control_link_moves_a_replay_and_a_view_link_watches_it(web):
    moving = await Browser(web).opened("control")
    watching = await Browser(web).opened("view")

    stepped = await control(moving, "step")
    refused = await watching.request("POST", "/x/replay", {"control": "step"})
    seen = (await watching.view("view_info"))["x"]["replay"]
    unknown = await moving.request("POST", "/x/replay", {"control": "rewind"})
    nowhere = await control(moving, "jump", "soon")

    assert stepped["at"] == 1 and stepped["cannot"] is None and "at event 1 of" in stepped["banner"]
    assert refused.status == 403 and refused.json()["error"] == WATCHES
    assert seen["at"] == 1 and seen["cannot"] == WATCHES
    assert unknown.status == 400
    assert nowhere["at"] == 1 and "is no place in the replay" in nowhere["said"]


async def test_a_replay_moved_on_folds_its_copy_and_one_started_anew_is_heard_as_a_reset(web, head):
    browser = await Browser(web).opened("control")
    start = await browser.view("view_snapshot")
    assert start["chats"] == []

    await control(browser, "jump", str(head))
    fed = await browser.view("view_feed", {"after": 0, "feed_id": start["server"]["feed_id"], "timeout": 0})
    whole = await browser.view("view_snapshot")
    assert not fed.get("reset") and fed["feed"] == whole["feed"] > 0 and whole["chats"]
    assert whole["server"]["feed_id"] == start["server"]["feed_id"]

    back = await control(browser, "jump", "30")
    again = await browser.view(
        "view_feed", {"after": whole["feed"], "feed_id": whole["server"]["feed_id"], "timeout": 0}
    )
    then = await browser.view("view_snapshot")

    assert back["at"] == 30 and again["reset"] is True
    assert then["server"]["feed_id"] != whole["server"]["feed_id"] and then["feed"] < whole["feed"]


async def test_a_page_waiting_for_news_hears_the_replay_move_and_how_it_plays(web):
    browser = await Browser(web).opened("control")
    snapshot = await browser.view("view_snapshot")
    after, feed_id = snapshot["feed"], snapshot["server"]["feed_id"]
    waiting = asyncio.ensure_future(browser.view("view_feed", {"after": after, "feed_id": feed_id}))
    await asyncio.sleep(0)

    await control(browser, "speed")
    heard = await waiting

    assert heard["x"]["replay"]["speed"] == "4x" and heard["x"]["replay"]["playing"] is False


async def test_a_replay_s_provenance_says_when_each_estimate_was_written(root, head):
    async with Session.attach("s", root=root) as history:
        said = (await of_type(history, "message.sent"))[0]
        target = f"{said.stream}@{said.version}"
        await history.annotate(target, status="scored", value=0.5, head_seq=head, **CREDIT)
    async with replayed() as web:
        browser = await Browser(web).opened("control")
        await control(browser, "jump", str(said.seq))
        lines = (await browser.view("x_read", {"pane": "provenance", "ref": target}))["lines"]

    credit = next(line for line in lines if line["kind"] == "credit")
    assert credit["text"].startswith("0.5 by even-split") and credit["warn"] is True
    assert "after this point of the replay, so it was not known here" in credit["text"]


async def test_the_sessions_page_serves_a_replay_on_a_control_link_of_its_own(head, root, monkeypatch):
    monkeypatch.chdir(root)
    page = Sessions(ManualClock(1_000_000.0))
    await page.listen("127.0.0.1")
    try:
        ours = await Browser(page).opened()
        link = (await ours.request("POST", "/x/replay", {"name": "s"})).json()["link"]
        again = (await ours.request("POST", "/x/replay", {"name": "s"})).json()["link"]
        opened_link = (await ours.request("POST", "/x/open", {"name": "s"})).json()["link"]
        token = await asyncio.to_thread(opened, link)
        _, info = await asyncio.to_thread(call, link, "POST", "/v1/view_info", {}, token)
        missing = (await ours.request("POST", "/x/replay", {"name": "nobody"})).json()
    finally:
        await page.stop()

    assert urlsplit(link).port == urlsplit(again).port != urlsplit(opened_link).port
    assert info["x"]["replay"]["banner"].startswith("Replay of s, before its first event")
    assert info["x"]["cannot"] == nothing_acts("s")
    assert missing == {"refused": f"refused not_found: no session nobody under {root}"}
    assert list((root / "replays").iterdir()) == []
