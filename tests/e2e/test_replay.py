"""A replay's page in a real browser: under a banner that says it is a replay, of which session and where it stands, it
draws what the record held up to there, moves on and back by its controls, draws a copy started anew as a page reset,
offers its controls to a control link alone, and disables every act of the session's, saying why. The sessions page's
Replay opens one."""

import asyncio
import contextlib
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from playwright.async_api import Browser, Page, expect

from platoon_harness import Session
from platoon_harness.kernel import SystemClock
from platoon_harness_cli.replay import nothing_acts
from platoon_harness_cli.web import serve
from platoon_harness_cli.web.server import WATCHES, Web
from platoon_harness_cli.web.sessions import Sessions

from ..unit.runtime.support import of_type
from ..unit.web.support import scenario, team
from .support import SECONDS, chat, said, watched

pytestmark = [pytest.mark.e2e, pytest.mark.timeout(120)]

BANNER = "#x-replay .x-banner"


@pytest.fixture
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("PLATOON_HARNESS_HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
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
    stop, opened = asyncio.Event(), asyncio.get_running_loop().create_future()
    options = {"host": "127.0.0.1", "port": 0, "tls": None, "clock": SystemClock()}
    serving = asyncio.ensure_future(serve("s", stop, **options, opened=opened, replay=True))
    try:
        yield await opened
    finally:
        stop.set()
        await serving


async def opened(browser: Browser, link: str) -> tuple[Page, list[str]]:
    """A replay's page in a context of its own, opened from `link`, its banner drawn."""
    page = await (await browser.new_context(viewport={"width": 1280, "height": 800})).new_page()
    errors = watched(page)
    await page.goto(link)
    await expect(page.locator(BANNER)).to_be_visible(timeout=SECONDS)
    return page, errors


async def jump(page: Page, where: str) -> None:
    await page.get_by_label("Jump to").fill(where)
    await page.get_by_role("button", name="Jump").click()


async def test_a_replay_s_page_draws_what_the_record_held_where_it_stands_and_moves_on_and_back(
    browser: Browser, root: Path, head: int
):
    async with Session.attach("s", root=root) as history:
        asked = next(event for event in await of_type(history, "message.sent") if event.actor == "human:you")
    async with replayed() as web:
        page, errors = await opened(browser, web.link("control"))
        await expect(page.locator(BANNER)).to_contain_text("Replay of s, before its first event")
        await expect(page.locator("#list .row", has_text="lead")).to_have_count(0)

        await jump(page, str(head))
        await expect(page.locator(BANNER)).to_contain_text(f"at event {head:,} of {head:,}", timeout=SECONDS)
        await chat(page, "lead & you")
        await expect(said(page, "Fix the flaky test")).to_have_count(1, timeout=SECONDS)
        send = page.locator("#main .x-composer button", has_text="Send")
        await expect(send).to_have_attribute("aria-disabled", "true")
        await expect(send).to_have_accessible_description(nothing_acts("s"))
        commands = page.get_by_role("button", name="Commands")
        await expect(commands).to_have_attribute("aria-disabled", "true")
        await expect(commands).to_have_accessible_description(nothing_acts("s"))

        await page.get_by_role("button", name="Back", exact=True).click()
        await expect(page.locator(BANNER)).to_contain_text(f"at event {head - 1:,} of", timeout=SECONDS)
        await jump(page, str(asked.seq - 1))
        await expect(page.locator(BANNER)).to_contain_text(f"at event {asked.seq - 1:,} of", timeout=SECONDS)
        await expect(said(page, "Fix the flaky test")).to_have_count(0, timeout=SECONDS)
        await page.get_by_role("button", name="Step", exact=True).click()
        await expect(page.locator(BANNER)).to_contain_text(f"at event {asked.seq:,} of", timeout=SECONDS)
        await expect(said(page, "Fix the flaky test")).to_have_count(1, timeout=SECONDS)

        await page.get_by_role("button", name="Speed 1x").click()
        await expect(page.get_by_role("button", name="Speed 4x")).to_be_visible(timeout=SECONDS)
        await page.get_by_role("button", name="Play").click()
        await expect(page.locator(BANNER)).to_contain_text(f"at event {head:,} of {head:,}", timeout=SECONDS)
        await expect(page.locator(BANNER)).to_contain_text("paused", timeout=SECONDS)
        await page.context.close()

    assert errors == []


async def test_a_jump_back_never_draws_what_came_after_under_a_banner_naming_where_it_went(
    browser: Browser, root: Path, head: int
):
    """Each change the page makes to itself is looked at as it makes it: none shows the message asked of the lead, sent
    at an event past where the replay jumped back to, under a banner naming that event."""
    async with Session.attach("s", root=root) as history:
        asked = next(event for event in await of_type(history, "message.sent") if event.actor == "human:you")
    went = f"at event {asked.seq - 1:,} of"
    async with replayed() as web:
        page, errors = await opened(browser, web.link("control"))
        await jump(page, str(head))
        await expect(page.locator(BANNER)).to_contain_text(f"at event {head:,} of {head:,}", timeout=SECONDS)
        await chat(page, "lead & you")
        await expect(said(page, "Fix the flaky test")).to_have_count(1, timeout=SECONDS)
        await page.evaluate(
            """() => {
              window.seen = [];
              const look = () => window.seen.push([
                document.querySelector('#x-replay .x-banner').textContent,
                document.querySelector('#main').textContent.includes('Fix the flaky test'),
              ]);
              new MutationObserver(look).observe(document.body, {childList: true, subtree: true, characterData: true});
            }"""
        )

        await jump(page, str(asked.seq - 1))
        await expect(said(page, "Fix the flaky test")).to_have_count(0, timeout=SECONDS)
        await expect(page.locator(BANNER)).to_contain_text(went, timeout=SECONDS)
        seen = await page.evaluate("window.seen")
        await page.context.close()

    assert any(went in banner for banner, _ in seen)
    assert [banner for banner, late in seen if late and went in banner] == []
    assert errors == []


async def test_a_view_link_watches_a_replay_whose_controls_say_why_they_are_disabled(
    browser: Browser, root: Path, head: int
):
    async with replayed() as web:
        page, errors = await opened(browser, web.link("view"))
        step = page.get_by_role("button", name="Step", exact=True)
        await expect(step).to_have_attribute("aria-disabled", "true")
        await expect(step).to_have_accessible_description(WATCHES)
        await step.click(force=True)
        await expect(page.locator("#tip")).to_have_text(WATCHES)

        moving, moved = await opened(browser, web.link("control"))
        await jump(moving, str(head))
        await expect(page.locator(BANNER)).to_contain_text(f"at event {head:,} of {head:,}", timeout=SECONDS)
        await moving.context.close()
        await page.context.close()

    assert errors == [] and moved == []


async def test_the_sessions_page_s_replay_opens_a_replay_of_the_session(browser: Browser, root: Path, head: int):
    server = Sessions(SystemClock())
    await server.listen("127.0.0.1")
    try:
        page = await (await browser.new_context(viewport={"width": 1280, "height": 800})).new_page()
        errors = watched(page)
        await page.goto(server.link())
        row = page.locator('tr[data-session="s"]')
        await expect(row).to_contain_text("stopped", timeout=SECONDS)
        await row.get_by_role("button", name="Replay").click()
        await expect(page.locator(BANNER)).to_contain_text("Replay of s, before its first event", timeout=SECONDS)
        await jump(page, str(head))
        await expect(page.locator(BANNER)).to_contain_text(f"at event {head:,} of {head:,}", timeout=SECONDS)
        await page.context.close()
    finally:
        await server.stop()

    assert errors == []
    assert list((root / "replays").iterdir()) == []
