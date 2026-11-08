"""The sessions page in a real browser, served by `platoon-harness web` with no session: it opens from its one link,
lists every session under the root, and opens one on a control link of the page `web` serves it on, its token kept in
the tab for the page to come back to."""

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from playwright.async_api import Browser, Page, expect

from platoon_harness_cli.web.sessions import SPENT

from ..integration.cli import Cli, finished, said, solo
from ..integration.test_web import sessions_link
from .support import SECONDS, watched

pytestmark = [pytest.mark.e2e, pytest.mark.timeout(120)]


@pytest.fixture
async def cli(tmp_path: Path) -> AsyncIterator[Cli]:
    made = Cli(tmp_path)
    yield made
    await asyncio.to_thread(made.end)


async def opened(browser: Browser, link: str, *expected: str) -> tuple[Page, list[str]]:
    """The sessions page in a context of its own, opened from `link`, its list drawn."""
    page = await (await browser.new_context(viewport={"width": 1280, "height": 800})).new_page()
    errors = watched(page, *expected)
    await page.goto(link)
    await expect(page.locator("#look")).to_be_visible(timeout=SECONDS)
    return page, errors


async def test_the_sessions_page_lists_your_sessions_and_opens_one_on_its_own_control_link(browser: Browser, cli: Cli):
    team = cli.write("solo.toml", solo("listening"))
    serving = await cli.start("serve", "--team", team, "--trust", "--name", "s")
    await said(serving, "serving session s")
    web = await cli.start("web")
    link = await sessions_link(web)

    page, errors = await opened(browser, link)
    row = page.locator('tr[data-session="s"]')
    await expect(row).to_contain_text("live", timeout=SECONDS)
    await expect(row).to_contain_text("open")
    assert "#link=" not in page.url
    await row.get_by_role("button", name="Open").click()
    await expect(page.locator("#list .row").first).to_be_visible(timeout=SECONDS)
    session_page = urlsplit(page.url)
    await expect(page.locator("#list")).to_contain_text("bob & you")
    await page.goto(link.partition("#")[0])
    await expect(row).to_contain_text("live", timeout=SECONDS)
    again, refused = await opened(browser, link, "401")
    await expect(again.locator("#said")).to_have_text(SPENT, timeout=SECONDS)

    web.terminate()
    done = await finished(web)
    await cli.run("session", "stop", "s")
    await finished(serving)

    assert session_page.port != urlsplit(link).port and session_page.path == "/view"
    assert done.code == 0, done.stderr
    assert errors == [] and refused == []
