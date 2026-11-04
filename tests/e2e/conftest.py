"""Browser tests, on Playwright's Chromium headless shell. Selecting them where it is not installed fails, saying how to
install it, and never skips: a skipped browser test is no passing one. The browser resolves one name of its own to
loopback, as a name an attacker rebinds would, and no other."""

from collections.abc import AsyncIterator

import pytest
from playwright.async_api import Browser, Error, async_playwright

from .support import REBOUND


@pytest.fixture
async def chromium() -> AsyncIterator[Browser]:
    async with async_playwright() as playwright:
        try:
            browser = await playwright.chromium.launch(args=[f"--host-resolver-rules=MAP {REBOUND} 127.0.0.1"])
        except Error as error:
            install = "`uv run playwright install chromium-headless-shell`"
            pytest.fail(
                f"the browser tests need Chromium's headless shell: {install}, or PLAYWRIGHT_BROWSERS_PATH naming "
                f"where it is. {error.message.splitlines()[0]}"
            )
        try:
            yield browser
        finally:
            await browser.close()
