"""The sessions page in a real browser, served by `platoon-harness web` with no session: it opens from its one link,
lists every session under the root, and opens one on a control link of the page `web` serves it on, its token kept in
the tab for the page to come back to. It starts one, saying first that it can spend money and asking what the server
asks, resumes one after saying it can spend money, and stops one after one question."""

import asyncio
import re
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


async def test_the_sessions_page_starts_a_session_asking_trust_once_and_opens_it(browser: Browser, cli: Cli):
    """The money it can spend is said before Start. Then each question the server asks comes once: trust, naming what
    the team runs as you as written, and several agents on one plan login. Declined, nothing starts; taken, the session
    starts and its own page opens."""
    cli.write("platoon-harness.toml", solo("planned", count="2"))
    web = await cli.start("web")
    link = await sessions_link(web)

    page, errors = await opened(browser, link)
    await expect(page.locator("#none")).to_be_visible(timeout=SECONDS)
    await expect(page.locator("#cost")).to_contain_text(f"here, in {cli.folder}, which can spend money")
    await expect(page.locator("#team-about")).to_contain_text("Left empty, the project's own, platoon-harness.toml.")
    await page.get_by_label("Name").fill("s")
    start = page.get_by_role("button", name="Start")
    await start.click()
    dialog = page.get_by_role("dialog")
    await expect(dialog).to_contain_text('roles.bob.harness = "tests.integration.scripts:planned"', timeout=SECONDS)
    await expect(dialog.get_by_role("button", name="Cancel")).to_be_focused()
    await dialog.get_by_role("button", name="Cancel").click()
    await expect(page.locator("#said")).to_have_text("Nothing was started.")
    nothing = (cli.folder / "home" / "sessions" / "s").exists()
    await start.click()
    await dialog.get_by_role("button", name="Trust and start").click()
    await expect(dialog).to_contain_text("bob would run several agents headless on one plan login.", timeout=SECONDS)
    await dialog.get_by_role("button", name="It is my own work").click()
    await expect(page.locator("#list .row").first).to_be_visible(timeout=SECONDS)
    await expect(page.locator("#list")).to_contain_text("bob-2 & you")
    await page.goto(link.partition("#")[0])
    await expect(page.locator('tr[data-session="s"]')).to_contain_text("live", timeout=SECONDS)

    web.terminate()
    done = await finished(web)
    stopped = await cli.run("session", "stop", "s")

    assert not nothing and done.code == 0, done.stderr
    assert stopped.code == 0, stopped.stderr
    assert errors == []


async def test_the_sessions_page_resumes_after_saying_it_can_spend_money_and_stops_after_one_question(
    browser: Browser, cli: Cli
):
    """Resume is disabled while a runtime holds the session, and Stop while none does, each saying why. A question
    declined does nothing."""
    team = cli.write("solo.toml", solo("listening"))
    serving = await cli.start("serve", "--team", team, "--trust", "--name", "s")
    await said(serving, "serving session s")
    web = await cli.start("web")
    link = await sessions_link(web)

    page, errors = await opened(browser, link)
    row = page.locator('tr[data-session="s"]')
    resume, stop = row.get_by_role("button", name="Resume"), row.get_by_role("button", name="Stop")
    dialog = page.get_by_role("dialog")
    await expect(resume).to_have_accessible_description("A runtime holds this session: Open opens it.", timeout=SECONDS)
    await resume.click(force=True)
    await expect(page.locator("#tip")).to_have_text("A runtime holds this session: Open opens it.")
    await expect(dialog).to_be_hidden()
    await stop.click()
    await expect(dialog).to_have_text(
        re.compile(r"Stop s\? Its turns are interrupted and its harnesses end; it stays resumable\.")
    )
    await dialog.get_by_role("button", name="Cancel").click()
    await expect(row).to_contain_text("live")
    await stop.click()
    await dialog.get_by_role("button", name="Stop").click()
    await expect(page.locator("#said")).to_have_text(
        "Stopped s. Resume restarts it, which can spend money.", timeout=SECONDS
    )
    await expect(row).to_contain_text("stopped")
    served = await finished(serving)
    await expect(stop).to_have_accessible_description("No runtime holds this session, so there is nothing to stop.")
    await resume.click()
    await expect(dialog).to_contain_text("Resume s? Its harnesses come back, which can spend money.")
    await dialog.get_by_role("button", name="Resume").click()
    await expect(page.locator("#list .row").first).to_be_visible(timeout=SECONDS)
    await expect(page.locator("#list")).to_contain_text("bob & you")
    await page.goto(link.partition("#")[0])
    await expect(row).to_contain_text("live", timeout=SECONDS)

    web.terminate()
    done = await finished(web)
    stopped = await cli.run("session", "stop", "s")

    assert served.code == 0 and done.code == 0, done.stderr
    assert stopped.code == 0, stopped.stderr
    assert errors == []


async def test_what_the_sessions_page_is_told_stays_text_under_its_policy(browser: Browser, cli: Cli):
    """A refusal that repeats what was typed, markup and all, is drawn as that text, and nothing in it runs or loads."""
    hostile = '<img src=x onerror="document.title=1">.toml'
    web = await cli.start("web")
    link = await sessions_link(web)

    page, errors = await opened(browser, link)
    await page.get_by_label("Team file").fill(hostile)
    await page.get_by_role("button", name="Start").click()
    await expect(page.locator("#said")).to_have_text(f"{hostile}: no such file\nroles: Field required", timeout=SECONDS)
    found = await page.evaluate("[document.title, document.querySelectorAll('img').length]")

    web.terminate()
    done = await finished(web)

    assert found == ["Sessions · platoon-harness", 0]
    assert done.code == 0, done.stderr
    assert errors == []
