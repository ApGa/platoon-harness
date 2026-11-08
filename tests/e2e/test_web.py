"""SwarmChat's page in a real browser, served by `platoon-harness web` over a session on scripted harnesses: it opens
from its link, shows the channels, the direct chats and the messages, follows the session live, survives a reload with
nothing twice, and on a view link shows every act disabled, saying why."""

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from playwright.async_api import Browser, expect

from ..integration.cli import Cli, crew, finished, said
from ..integration.test_web import links
from .support import SECONDS, opened

pytestmark = [pytest.mark.e2e, pytest.mark.timeout(120)]


@pytest.fixture
async def cli(tmp_path: Path) -> AsyncIterator[Cli]:
    made = Cli(tmp_path)
    yield made
    await asyncio.to_thread(made.end)


@pytest.fixture
async def served(cli: Cli) -> AsyncIterator[dict[str, str]]:
    """A session whose lead waits on two workers that hang, so its runtime stays, and `web` serving it."""
    team = cli.write("crew.toml", crew(worker="hanging"))
    serving = await cli.start("serve", "--team", team, "--trust", "--name", "s")
    await said(serving, "serving session s")
    await cli.run("message", "send", "s", "--to", "@lead", "--gist", "Fix the flaky test")
    web = await cli.start("web", "s")
    yield await links(web)
    web.terminate()
    assert (await finished(web)).code == 0
    await cli.run("session", "stop", "s")
    await finished(serving)


async def test_the_page_opens_from_its_link_shows_the_session_follows_it_and_survives_a_reload(
    browser: Browser, cli: Cli, served: dict[str, str]
):
    page, errors = await opened(browser, served["control"])

    assert "#link=" not in page.url and "token=" not in page.url
    await expect(page.locator("#list")).to_contain_text("tasks")
    await expect(page.locator("#list")).to_contain_text("notes")
    await expect(page.locator("#list")).to_contain_text("lead & you")
    await expect(page.locator("#stats")).to_contain_text("1 person")
    await page.locator("#list .row", has_text="lead & you").click()
    await expect(page.locator(".msg .text", has_text="Fix the flaky test")).to_have_count(1, timeout=SECONDS)
    await expect(page.locator(".msg .text", has_text="On it.")).to_have_count(1, timeout=SECONDS)

    await cli.run("message", "send", "s", "--to", "@lead", "--gist", "live from another shell")
    await expect(page.locator(".msg .text", has_text="live from another shell")).to_have_count(1, timeout=SECONDS)

    await page.reload()
    await expect(page.locator(".msg .text", has_text="live from another shell")).to_have_count(1, timeout=SECONDS)
    await expect(page.locator(".msg .text", has_text="Fix the flaky test")).to_have_count(1)
    await expect(page.locator(".av.x-human").first).to_be_visible()
    assert errors == []


async def test_the_people_list_says_what_each_agent_is_doing_and_only_an_agent_can_be_seen_as(
    browser: Browser, served: dict[str, str]
):
    page, errors = await opened(browser, served["control"])
    only = "Only an agent leaves evidence of what reached it, so only an agent can be seen as."

    await page.locator("[data-tab=people]").click()
    statuses = await page.evaluate("Object.fromEntries([...S.users.values()].map(u => [u.id, u.status]))")
    for agent in ("lead", "w1"):
        row = page.locator(f'#list .row[title^="{agent} ({agent})"]')
        await expect(row.locator(".t .n")).to_have_text(statuses[agent], timeout=SECONDS)
    await page.locator("#as").click()
    you = page.locator(".pop .it", has_text="you")
    await expect(you).to_be_disabled()
    await expect(you).to_have_accessible_description(only)
    await you.click(force=True)
    await expect(page.locator("#tip")).to_have_text(only)
    await expect(page.locator("#as")).to_contain_text("As everyone")
    await page.locator('.pop .it[data-as="w1"]').focus()
    await page.keyboard.press("Enter")
    await expect(page.locator("#as")).to_contain_text("As w1")
    await page.goto(served["control"].partition("#")[0] + "#as=you")
    await expect(page.locator("#tip")).to_have_text(only, timeout=SECONDS)
    await expect(page.locator("#as")).to_contain_text("As everyone")

    assert statuses["lead"] and statuses["w1"] and "agent" not in statuses.values()
    assert errors == []


async def test_a_view_link_shows_every_act_disabled_saying_why(browser: Browser, served: dict[str, str]):
    page, errors = await opened(browser, served["view"])
    why = "This is a view link: it shows the session and acts on nothing."

    await page.locator("#list .row", has_text="lead & you").click()
    composer = page.locator(".x-composer textarea")
    await expect(composer).to_be_disabled(timeout=SECONDS)
    await expect(composer).to_have_accessible_description(why)
    for button in await page.locator(".x-composer button").all():
        await expect(button).to_be_disabled()
    await expect(page.locator(".x-composer .x-why")).to_have_text(why)
    replies = page.locator("[data-x-reply]")
    await expect(replies.first).to_be_attached()
    for reply in await replies.all():
        await expect(reply).to_be_disabled()
        await expect(reply).to_have_accessible_description(why)

    await page.goto(served["view"].partition("#")[0] + "#person=lead")
    acts = page.locator("[data-x-act]")
    await expect(acts).to_have_count(4, timeout=SECONDS)
    for act in await acts.all():
        await expect(act).to_be_disabled()
        await expect(act).to_have_accessible_description(why)
    await expect(page.locator(".person .x-acts [data-x-tools]")).to_be_enabled()
    await expect(page.locator(".person .x-acts [data-x-review]")).to_be_enabled()
    await page.goto(served["view"].partition("#")[0] + "#person=you")
    links = page.locator("[data-x-link]")
    await expect(links).to_have_count(2, timeout=SECONDS)
    for link in await links.all():
        await expect(link).to_be_disabled()
        await expect(link).to_have_accessible_description(why)
    assert errors == []
