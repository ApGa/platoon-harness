"""What the browser tests share: a page that fails its test on any error it did not expect, opened from a link, and
`web` serving a session as a guest of its runtime, in the test's own process."""

import contextlib
import re
from collections.abc import AsyncIterator
from pathlib import Path

from playwright.async_api import Browser, ConsoleMessage, Page, expect

from platoon_harness import Session
from platoon_harness.kernel import SystemClock
from platoon_harness_cli.web.server import Web

from ..unit.web.support import served

SECONDS = 20_000
"""How long a locator waits for what it expects, in milliseconds."""
REBOUND = "rebound.localhost"
"""A name that reaches loopback, as a rebinding attacker's name would: Chromium and Firefox resolve a name under
`localhost` to loopback themselves, so neither needs a flag of its own. Whether WebKit does is unverified until CI's
WebKit job runs, as WebKit has run nowhere yet."""
PHONE = {"width": 390, "height": 844}
"""A phone's screen held upright, in CSS pixels, as an iPhone 12, 13 or 14 gives it."""
REACHED = """() => {
    const screen = document.documentElement, shown = el => el.checkVisibility({visibilityProperty: true});
    const pointed = el => getComputedStyle(el).cursor === 'pointer'
        && !(el.parentElement && getComputedStyle(el.parentElement).cursor === 'pointer');
    const controls = 'button, a[href], input, textarea, select, [role="button"], [tabindex]:not([tabindex="-1"])';
    const shows = document.querySelector('#overlay.on') || document.body;
    const acts = [...shows.querySelectorAll('*')].filter(el => shown(el) && (el.matches(controls) || pointed(el)));
    const missed = [];
    for (const act of acts) {
        act.closest('.msg')?.focus({preventScroll: true});
        act.scrollIntoView({block: 'nearest', inline: 'nearest'});
        const r = act.getBoundingClientRect(), x = r.left + r.width / 2;
        const hit = document.elementFromPoint(x, r.top + Math.min(r.height, screen.clientHeight) / 2);
        if (r.left < 0 || r.right > screen.clientWidth + 0.5 || !act.contains(hit)) missed.push(act.outerHTML);
    }
    return {acts: acts.length, missed, wider: screen.scrollWidth - screen.clientWidth};
}"""
"""Every act shown, a control or what the pointer presses, each scrolled into view, its message given focus first as a
press gives it: the count, each that lies past the screen's sides or under something else, and how much wider than
the screen the page scrolls."""


ABORTED = "due to access control checks"
"""What WebKit says, as an error of the page's, of a request of the page's own that a reload, a navigation or a cut
network ended, though the page catches it. Chromium and Firefox run every test too, and report a request the page fails
to catch in words of their own."""


def watched(page: Page, *expected: str) -> list[str]:
    """What went wrong on a page: an exception, or an error or a warning on its console that matches none of
    `expected`, such as the line a browser logs for a request the test refused on purpose."""
    errors: list[str] = []
    page.on(
        "pageerror",
        lambda error: errors.append(f"pageerror: {error}") if _unexpected(str(error), (*expected, ABORTED)) else None,
    )
    page.on("console", lambda message: errors.append(message.text) if _wrong(message, expected) else None)
    return errors


def _wrong(message: ConsoleMessage, expected: tuple[str, ...]) -> bool:
    return message.type in ("error", "warning") and _unexpected(message.text, expected)


def _unexpected(text: str, expected: tuple[str, ...]) -> bool:
    return not any(re.search(found, text) for found in expected)


async def opened(browser: Browser, link: str, *expected: str) -> tuple[Page, list[str]]:
    """A page in a context of its own, opened from `link` and drawn."""
    page = await (await browser.new_context(viewport={"width": 1280, "height": 800})).new_page()
    errors = watched(page, *expected)
    await page.goto(link)
    await expect(page.locator("#list .row").first).to_be_visible(timeout=SECONDS)
    return page, errors


@contextlib.asynccontextmanager
async def serving(name: str, root: Path) -> AsyncIterator[Web]:
    """`web` for session `name`, attached as a guest of its runtime on the owner's credential, as the command does."""
    async with Session.attach(name, root=root) as guest, served(guest, root, SystemClock()) as web:
        yield web


async def chat(page: Page, title: str) -> None:
    """Open a chat from the sidebar, and wait for its composer."""
    await page.locator("#list .row", has_text=title).first.click()
    await expect(page.locator("#main .x-composer")).to_be_attached(timeout=SECONDS)


def said(page: Page, text: str):
    """The messages a page shows whose text holds `text`."""
    return page.locator("#main .msg .text", has_text=text)
