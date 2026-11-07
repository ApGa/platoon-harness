"""Browser tests, in each browser `PLATOON_HARNESS_BROWSERS` names, comma-separated, of chromium, firefox and webkit,
and in Chromium's headless shell where it names none, each test once in each, its id naming the browser. Selecting them
where a browser is not installed fails, saying how to install it, and never skips: a skipped browser test is no passing
one."""

import os
from collections.abc import AsyncIterator

import pytest
from playwright.async_api import Browser, Error, async_playwright

INSTALL = {"chromium": "chromium-headless-shell", "firefox": "firefox", "webkit": "webkit"}
"""What `playwright install` installs for each browser the tests may run in."""


@pytest.fixture(params=os.environ.get("PLATOON_HARNESS_BROWSERS", "chromium").split(","))
async def browser(request: pytest.FixtureRequest) -> AsyncIterator[Browser]:
    name = request.param
    if name not in INSTALL:
        pytest.fail(f"PLATOON_HARNESS_BROWSERS names {name!r}, which is none of {', '.join(INSTALL)}")
    async with async_playwright() as playwright:
        try:
            launched = await getattr(playwright, name).launch()
        except Error as error:
            install = f"`uv run playwright install {INSTALL[name]}`"
            pytest.fail(
                f"{name} did not start. {install} installs it, or PLAYWRIGHT_BROWSERS_PATH names where it is. "
                f"Playwright said: {error.message}"
            )
        try:
            yield launched
        finally:
            await launched.close()
