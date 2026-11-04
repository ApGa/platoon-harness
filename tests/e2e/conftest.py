"""Browser tests, on Playwright's Chromium headless shell. Selecting them where it is not installed fails, saying how to
install it, and never skips: a skipped browser test is no passing one."""

from collections.abc import AsyncIterator

import pytest
from playwright.async_api import Browser, Error, async_playwright


@pytest.fixture
async def chromium() -> AsyncIterator[Browser]:
    async with async_playwright() as playwright:
        try:
            browser = await playwright.chromium.launch()
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
