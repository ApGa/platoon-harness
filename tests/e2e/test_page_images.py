"""The page's images for the docs, drawn from the mixed team's session as a live run of it recorded it: the chat with
the lead, and the Provenance pane of the lead's answer. Each is written where `PLATOON_HARNESS_IMAGES` names, else in
the test's own folder, where it only shows that it draws. No live run has recorded the session yet, so this skips, and
`test_examples.py` draws the images of a session of the real harnesses against FakeModel, recorded as a live run
records one."""

import os
from pathlib import Path

import pytest
from playwright.async_api import Browser, expect

from ..recorded import IMAGES, RECORDED, finish_of, restored
from .support import SECONDS, chat, opened, serving

pytestmark = [pytest.mark.e2e, pytest.mark.timeout(120)]


async def page_images(browser: Browser, root: Path, name: str, answer: str, into: Path) -> list[Path]:
    """The page of a closed session drawn into `into`: the chat with the lead, its answer among it, and the Provenance
    pane of `answer`, the ref of the lead's finish."""
    into.mkdir(parents=True, exist_ok=True)
    chatting, tracing = (into / image for image in IMAGES)
    async with serving(name, root) as web:
        page, errors = await opened(browser, web.link("control"))
        await chat(page, "lead & you")
        await expect(page.locator("#main .sys").last).to_be_visible(timeout=SECONDS)
        await page.screenshot(path=chatting)
        await page.goto(web.link("control").partition("#")[0] + f"#provenance={answer}")
        await expect(page.locator("#pane h2")).to_have_text(f"Provenance of {answer}", timeout=SECONDS)
        await page.screenshot(path=tracing)
        await page.context.close()
    assert errors == []
    return [chatting, tracing]


async def test_the_page_images_draw_the_mixed_team_as_a_live_run_recorded_it(
    browser: Browser, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    if not RECORDED.exists():
        pytest.skip("no live run has recorded the mixed team yet, so the docs show no page image")
    monkeypatch.setenv("PLATOON_HARNESS_HOME", str(tmp_path / "state"))
    name = restored(RECORDED, tmp_path / "state")
    finish = finish_of(RECORDED, "lead")
    answer = f"{finish['stream']}@{finish['version']}"
    into = Path(os.environ.get("PLATOON_HARNESS_IMAGES") or tmp_path / "images")

    written = await page_images(browser, tmp_path / "state", name, answer, into)

    assert [path.name for path in written if path.stat().st_size] == list(IMAGES)
