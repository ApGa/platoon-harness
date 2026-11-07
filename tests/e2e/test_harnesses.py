"""SwarmChat's page in front of a real harness: the `claude` binary against FakeModel, on a dummy key, with an isolated
home and loopback only, so it is free."""

import shutil
from pathlib import Path

import pytest
from playwright.async_api import Browser, expect

from platoon_harness import Session
from platoon_harness.testing import FakeModel

from ..integration import clients
from ..integration.test_claude import keyed
from ..unit.runtime.support import in_state, of_type, until
from .support import SECONDS, chat, opened, said, serving

pytestmark = [pytest.mark.e2e, pytest.mark.timeout(120)]

TOLD = "Fix the flaky test in tests/test_cart.py"


async def test_a_person_s_message_from_the_browser_reaches_the_real_claude_binary_s_model_once(
    browser: Browser, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    if shutil.which("claude") is None:
        pytest.skip("claude is not installed, so the page met no real harness here")
    monkeypatch.setenv("PLATOON_HARNESS_HOME", str(tmp_path))
    async with FakeModel(clients.SAID) as model:
        team = keyed(tmp_path / "home", model, monkeypatch)
        async with Session.start(team, name="s", root=tmp_path, cwd=tmp_path) as session, serving("s", tmp_path) as web:
            await in_state(session, "bob", "idle")
            page, errors = await opened(browser, web.link("control"))
            await chat(page, "bob & you")

            await page.locator("#main .x-composer textarea").fill(TOLD)
            await page.keyboard.press("Enter")

            await expect(said(page, clients.SAID)).to_have_count(1, timeout=SECONDS)
            await until(lambda: of_type(session, "turn.ended"), session)
            await expect(said(page, TOLD)).to_have_count(1)
            sent = [event.gist for event in await of_type(session, "message.sent") if event.actor == "human:you"]
            await page.context.close()

    assert sent == [TOLD]
    assert model.calls and all(call.message.body.decode().count(TOLD) == 1 for call in model.calls)
    assert errors == []
