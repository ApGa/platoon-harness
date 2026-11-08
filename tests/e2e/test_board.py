"""SwarmChat's Board and Map in a real browser, over a session on scripted harnesses: a channel's posts and one opened
with its replies, the sorts by votes disabled, saying why, and no vote counted, a queue's tasks and a board's entries in
the pane, read again as they move, and the map of everyone with its timeline, from a control link and from a view
link."""

import re
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from playwright.async_api import Browser, Page, expect

from platoon_harness import Session
from platoon_harness_cli.web.server import Web

from ..unit.runtime.support import of_type
from ..unit.web.support import caught_up, scenario, team
from .support import SECONDS, chat, opened, serving

pytestmark = [pytest.mark.e2e, pytest.mark.timeout(120)]

UNVOTED = "A session's messages take no reactions, so there are no votes to count or to rank by."
SEEN_AS_W1 = """() => S.as && S.as.user === 'w1'
    && S.view.act.counts.reduce((a, b) => a + b, 0)
        === [...S.as.chats.keys()].reduce((n, id) => n + S.chats.get(id).messages, 0)
    && Object.keys(S.view.winData).every(id => S.as.chats.has(id))"""
"""The map seeing as w1: its timeline counts the messages of w1's chats, and its window holds none of any other. Each
wait is a function, since Playwright polls a bare expression with `eval`, which the page's policy refuses."""


@pytest.fixture
async def web(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[Web]:
    """The scenario's session, settled, with the person's reply to the lead's `plan` in #general, and `web` serving
    it."""
    monkeypatch.setenv("PLATOON_HARNESS_HOME", str(tmp_path))
    async with Session.start(team(), name="s", root=tmp_path, cwd=tmp_path) as session:
        await scenario(session)
        plan = next(event for event in await of_type(session, "message.sent") if event.gist == "plan")
        await session.send("#general", "a reply", reply_to=f"{plan.stream}@{plan.version}")
        async with serving("s", tmp_path) as web:
            await caught_up(web, session)
            yield web


def address(page: Page, route: str) -> str:
    return page.url.partition("#")[0] + route


async def test_the_board_lists_a_channel_s_posts_and_opens_one_with_its_replies_counting_no_votes(
    browser: Browser, web: Web
):
    page, errors = await opened(browser, web.link("control"))

    await chat(page, "general")
    await page.locator("#main [data-goto=board]").click()
    post = page.locator("#main .post", has_text="plan")
    await expect(post).to_have_count(1, timeout=SECONDS)
    await expect(post.locator(".pmeta")).to_contain_text("1 comment")
    await expect(page.locator("#main [data-sort=new]")).to_have_class(re.compile(r"\bon\b"))
    for sort in ("hot", "top"):
        await expect(page.locator(f"#main [data-sort={sort}]")).to_be_disabled()
        await expect(page.locator(f"#main [data-sort={sort}]")).to_have_accessible_description(UNVOTED)
    votes = post.locator(".votes")
    await expect(votes).to_be_disabled()
    await expect(votes).to_have_accessible_description(UNVOTED)
    await expect(votes.locator("span")).to_have_count(0)

    await post.locator(".ptitle").click()
    await expect(page.locator("#main .comments .msg .text", has_text="a reply")).to_have_count(1, timeout=SECONDS)
    await expect(page.locator("#main .post .votes")).to_have_accessible_description(UNVOTED)

    await page.goto(address(page, "#layout=board&sort=hot"))
    await expect(page.locator("#tip")).to_have_text(UNVOTED, timeout=SECONDS)
    await expect(page.locator("#main [data-sort=new]")).to_have_class(re.compile(r"\bon\b"))
    await expect(page.locator("#main .post", has_text="plan")).to_have_count(1, timeout=SECONDS)
    await expect(page.locator("#main .post", has_text="I started a worker.")).to_have_count(0)
    assert errors == []


@pytest.fixture
async def worked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[tuple[Session, Web]]:
    """The scenario's session, settled, its worker gone with the task it claimed, which is open again, a board `notes`
    with `plan` revised once, and `web` serving it."""
    monkeypatch.setenv("PLATOON_HARNESS_HOME", str(tmp_path))
    async with Session.start(team(), name="s", root=tmp_path, cwd=tmp_path) as session:
        await scenario(session)
        await session.create_channel("notes", "board", readers=["all"], writers=["all"])
        await session.board_post("notes", "plan", "first", fields={"step": 1})
        await session.board_revise("notes", "plan", "second", 1, fields={"step": 2})
        async with serving("s", tmp_path) as web:
            await caught_up(web, session)
            yield session, web


def pane(page: Page, text: str):
    """The lines of the pane of ours that hold `text`."""
    return page.locator("#pane .x-channel .x-change", has_text=text)


async def test_tasks_and_entries_show_in_a_queue_s_and_a_board_s_chat(browser: Browser, worked: tuple[Session, Web]):
    """Tasks, in a queue's chat as a chat and as a board, opens its tasks in the pane, each with its state, which a
    claim the chat never hears of moves, as the feed says the queue's view moved; and Entries, in a board's chat, its
    entries, each with every version."""
    session, web = worked
    page, errors = await opened(browser, web.link("control"))

    await chat(page, "tasks")
    await page.locator("#main [data-goto=board]").click()
    await expect(page.locator("#main [data-x-channel=queue]")).to_have_text("Tasks", timeout=SECONDS)
    await page.locator("#main [data-goto=chat]").click()
    await page.locator("#main [data-x-channel=queue]").click()
    await expect(page.locator("#pane h2")).to_have_text("Tasks on tasks", timeout=SECONDS)
    await expect(pane(page, "task 1")).to_contain_text("open, 1 attempt  fix the flaky test", timeout=SECONDS)
    assert "tasks=tasks" in page.url
    await session.task_claim("tasks", task="1")
    await expect(pane(page, "task 1")).to_contain_text("claimed by @you, attempt 2, lease until ", timeout=SECONDS)

    await chat(page, "notes")
    await page.locator("#main [data-x-channel=board]").click()
    await expect(page.locator("#pane h2")).to_have_text("Entries on notes", timeout=SECONDS)
    await expect(pane(page, "plan")).to_have_text("plan  2 versions", timeout=SECONDS)
    await expect(pane(page, "v1")).to_have_text('v1  @you  first  {"step":1}')
    await expect(pane(page, "v2")).to_have_text('v2  @you  second  {"step":2}')
    await page.keyboard.press("Escape")
    await expect(page.locator("#pane .x-channel")).to_have_count(0, timeout=SECONDS)
    assert errors == []


async def test_the_map_draws_the_session_s_agents_the_person_and_their_chats_with_the_timeline(
    browser: Browser, web: Web
):
    page, errors = await opened(browser, web.link("control"))

    await page.locator("#layouts [data-layout=map]").click()
    await expect(page.locator(".mapwrap canvas.graph")).to_be_visible(timeout=SECONDS)
    await expect(page.locator(".strip .when span").first).to_have_text(re.compile(r"\d"), timeout=SECONDS)
    await page.wait_for_function(
        "() => S.view.autoFit === false && MAP.pos.size === S.view.nodes.length", timeout=SECONDS
    )
    drawn = await page.evaluate("S.view.nodes.map(n => n.user || S.chats.get(n.chat).name)")
    counted = await page.evaluate("[S.view.act.counts.reduce((a, b) => a + b, 0), S.total]")
    await expect(page.locator("#pane .prow[data-person=lead]")).to_be_visible()
    await expect(page.locator("#pane .ph3").first).to_have_text("Who writes")
    await page.evaluate("S.view.hover = S.view.index.get('u:you'); S.view.showPane()")
    see = page.locator("#pane [data-see-as=you]")
    await expect(see).to_be_disabled()
    await expect(see).to_have_accessible_description(re.compile("^Only an agent leaves evidence"))

    await page.evaluate("S.view.setWindow([S.view.act.start, S.view.act.end])")
    await page.wait_for_function("() => S.view.winData !== null", timeout=SECONDS)
    await page.evaluate("S.view.hover = S.view.index.get('u:w1'); S.view.showPane()")
    await page.locator("#pane [data-see-as=w1]").click()
    await page.wait_for_function(SEEN_AS_W1, timeout=SECONDS)
    seen = await page.evaluate("[S.view.act.counts.reduce((a, b) => a + b, 0), Object.keys(S.view.winData).length]")

    assert {"lead", "w1", "you", "general", "tasks"} <= set(drawn)
    assert counted[0] == counted[1] > 0
    assert 0 < seen[0] < counted[1] and seen[1] > 0
    assert errors == []


async def test_a_view_link_reaches_the_board_and_the_map(browser: Browser, web: Web):
    page, errors = await opened(browser, web.link("view"))

    await page.locator("#layouts [data-layout=board]").click()
    await expect(page.locator("#main .post", has_text="plan")).to_have_count(1, timeout=SECONDS)
    await page.locator("#layouts [data-layout=map]").click()
    await expect(page.locator(".strip .when span").first).to_have_text(re.compile(r"\d"), timeout=SECONDS)
    await expect(page.locator("#pane .prow[data-person=lead]")).to_be_visible()
    assert errors == []
