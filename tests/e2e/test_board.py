"""SwarmChat's Board and Map in a real browser, over a session on scripted harnesses: a channel's posts and one opened
with its replies, the sorts by votes disabled, saying why, and no vote counted, a queue's own view not built yet, and
the map of everyone with its timeline, from a control link and from a view link."""

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
UNBUILT = re.compile("^Not built yet: the tasks and board views are planned")


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
    chromium: Browser, web: Web
):
    page, errors = await opened(chromium, web.link("control"))

    await chat(page, "general")
    await page.locator("#main [data-goto=board]").click()
    post = page.locator("#main .post", has_text="plan")
    await expect(post).to_have_count(1, timeout=SECONDS)
    await expect(post.locator(".pmeta")).to_contain_text("1 comment")
    await expect(page.locator("#main [data-sort=new]")).to_have_class(re.compile(r"\bon\b"))
    for sort in ("hot", "top"):
        await expect(page.locator(f"#main [data-sort={sort}]")).to_be_disabled()
        await expect(page.locator(f"#main [data-sort={sort}]")).to_have_attribute("title", UNVOTED)
    votes = post.locator(".votes")
    await expect(votes).to_have_attribute("aria-disabled", "true")
    await expect(votes).to_have_attribute("title", UNVOTED)
    await expect(votes.locator("span")).to_have_count(0)

    await post.locator(".ptitle").click()
    await expect(page.locator("#main .comments .msg .text", has_text="a reply")).to_have_count(1, timeout=SECONDS)
    await expect(page.locator("#main .post .votes")).to_have_attribute("title", UNVOTED)

    await page.goto(address(page, "#layout=board&sort=hot"))
    await expect(page.locator("#tip")).to_have_text(UNVOTED, timeout=SECONDS)
    await expect(page.locator("#main [data-sort=new]")).to_have_class(re.compile(r"\bon\b"))
    await expect(page.locator("#main .post", has_text="plan")).to_have_count(1, timeout=SECONDS)
    await expect(page.locator("#main .post", has_text="I started a worker.")).to_have_count(0)

    await page.locator("#list .row", has_text="tasks").click()
    tasks = page.locator("#main button", has_text="Tasks")
    await expect(page.locator("#main [data-goto=chat]")).to_be_visible(timeout=SECONDS)
    await expect(tasks).to_be_disabled()
    await expect(tasks).to_have_attribute("title", UNBUILT)
    await page.locator("#main [data-goto=chat]").click()
    await expect(page.locator("#main [data-goto=board]")).to_be_visible(timeout=SECONDS)
    await expect(tasks).to_be_disabled()
    await expect(tasks).to_have_attribute("title", UNBUILT)
    assert errors == []


async def test_the_map_draws_the_session_s_agents_the_person_and_their_chats_with_the_timeline(
    chromium: Browser, web: Web
):
    page, errors = await opened(chromium, web.link("control"))

    await page.locator("#layouts [data-layout=map]").click()
    await expect(page.locator(".mapwrap canvas.graph")).to_be_visible(timeout=SECONDS)
    await expect(page.locator(".strip .when span").first).to_have_text(re.compile(r"\d"), timeout=SECONDS)
    await page.wait_for_function("S.view.autoFit === false && MAP.pos.size === S.view.nodes.length", timeout=SECONDS)
    drawn = await page.evaluate("S.view.nodes.map(n => n.user || S.chats.get(n.chat).name)")
    counted = await page.evaluate("[S.view.act.counts.reduce((a, b) => a + b, 0), S.total]")
    await expect(page.locator("#pane .prow[data-person=lead]")).to_be_visible()
    await page.evaluate("S.view.hover = S.view.index.get('u:you'); S.view.showPane()")
    see = page.locator("#pane [data-see-as=you]")
    await expect(see).to_be_disabled()
    await expect(see).to_have_attribute("title", re.compile("^Only an agent leaves evidence"))

    assert {"lead", "w1", "you", "general", "tasks"} <= set(drawn)
    assert counted[0] == counted[1] > 0
    assert errors == []


async def test_a_view_link_reaches_the_board_and_the_map(chromium: Browser, web: Web):
    page, errors = await opened(chromium, web.link("view"))

    await page.locator("#layouts [data-layout=board]").click()
    await expect(page.locator("#main .post", has_text="plan")).to_have_count(1, timeout=SECONDS)
    await page.locator("#layouts [data-layout=map]").click()
    await expect(page.locator(".strip .when span").first).to_have_text(re.compile(r"\d"), timeout=SECONDS)
    await expect(page.locator("#pane .prow[data-person=lead]")).to_be_visible()
    assert errors == []
