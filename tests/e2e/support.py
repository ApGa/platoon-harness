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


def watched(page: Page, *expected: str) -> list[str]:
    """What went wrong on a page: an exception, or an error or a warning on its console that matches none of
    `expected`, such as the line a browser logs for a request the test refused on purpose."""
    errors: list[str] = []
    page.on(
        "pageerror", lambda error: errors.append(f"pageerror: {error}") if _unexpected(str(error), expected) else None
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
