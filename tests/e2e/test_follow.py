"""SwarmChat's page following a session through what goes wrong, in a real browser: an act through an offline window,
a lost answer and a reload taking effect once, browsing that writes nothing and receipts from delivery evidence alone,
and a session that is history followed as a runtime takes it up again."""

import asyncio
import json
import re
import sqlite3
from pathlib import Path

import pytest
from playwright.async_api import Browser, Route, expect

from platoon_harness import Session
from platoon_harness.testing import Ask, Say

from ..unit.runtime.support import in_state, of_type, solo, until
from .support import SECONDS, chat, opened, said, serving

pytestmark = [pytest.mark.e2e, pytest.mark.timeout(120)]

COMPOSER = "#main .x-composer textarea"
OFFLINE = ("ERR_INTERNET_DISCONNECTED", "ERR_FAILED")
"""What a browser logs for a request it could not make, which these tests cause."""


@pytest.fixture
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("PLATOON_HARNESS_HOME", str(tmp_path))
    return tmp_path


class Losing:
    """One route for every command a page sends. Told an op to lose, it lets the next command of that op reach web
    and keeps its answer from the page, and while `holding`, keeps each later one of that op from web too. It says
    the keys of that op it saw, and when one came again."""

    def __init__(self) -> None:
        self.op: str | None = None

    def lose(self, op: str, *, holding: bool = False) -> None:
        self.op, self.holding, self.keys = op, holding, []
        self.lost, self.again = asyncio.Event(), asyncio.Event()

    async def __call__(self, route: Route) -> None:
        command = json.loads(route.request.post_data or "{}")
        if command.get("op") != self.op:
            return await route.continue_()
        self.keys.append(command["key"])
        if len(self.keys) > 1:
            self.again.set()
        if not self.lost.is_set():
            await route.fetch()
            self.lost.set()
            return await route.abort()
        if self.holding:
            return await route.abort()
        await route.continue_()


async def test_an_act_through_an_offline_window_a_lost_answer_and_a_reload_is_one_operation(
    chromium: Browser, root: Path
):
    team = solo([Ask("Ship the fix?"), Say("shipped")], *[[Say("heard you")]] * 3)
    async with Session.start(team, name="s", root=root, cwd=root) as session, serving("s", root) as web:
        await in_state(session, "bob", "idle")
        await session.send("@bob", "go")
        await until(session.approvals, session)
        page, errors = await opened(chromium, web.link("control"), *OFFLINE)
        await chat(page, "bob & you")

        await page.context.set_offline(True)
        await page.locator(COMPOSER).fill("sent while offline")
        await page.keyboard.press("Enter")
        await expect(page.locator("#live")).to_have_text("Offline", timeout=SECONDS)
        await expect(page.locator("#main .x-why")).to_have_text("Sending…")
        unsent = [event for event in await of_type(session, "message.sent") if event.gist == "sent while offline"]
        await page.context.set_offline(False)
        await expect(said(page, "sent while offline")).to_have_count(1, timeout=SECONDS)

        losing = Losing()
        await page.route("**/x/command", losing)
        losing.lose("approval.resolve")
        await page.locator('[data-x-decide="allow"]').click()
        await expect(page.locator(".x-card.x-done")).to_have_text("Allowed by you via browser", timeout=SECONDS)
        await asyncio.wait_for(losing.again.wait(), SECONDS / 1000)
        decided = losing.keys

        losing.lose("message.send", holding=True)
        await page.locator(COMPOSER).fill("its answer was lost")
        await page.keyboard.press("Enter")
        await losing.lost.wait()
        await page.reload()
        await chat(page, "bob & you")
        losing.holding = False
        await expect(page.locator("#tip")).to_have_text(
            "message.send, sent before the page was reloaded: done.", timeout=SECONDS
        )
        for text in ("sent while offline", "its answer was lost", "shipped"):
            await expect(said(page, text)).to_have_count(1)
        messages = [event.gist for event in await of_type(session, "message.sent") if event.actor == "human:you"]
        resolved = await of_type(session, "approval.resolved")
        refused = await of_type(session, "op.refused")
        await page.context.close()

    assert unsent == []
    assert messages == ["go", "sent while offline", "its answer was lost"]
    assert len(decided) == 2 and len(set(decided)) == 1
    assert len(losing.keys) >= 2 and len(set(losing.keys)) == 1
    assert len(resolved) == 1 and refused == []
    assert errors == []


async def test_browsing_writes_nothing_moves_no_cursor_or_mark_and_receipts_say_delivered(
    chromium: Browser, root: Path
):
    async with Session.start(solo([Say("on it")]), name="s", root=root, cwd=root) as session, serving("s", root) as web:
        await in_state(session, "bob", "idle")
        await session.send("@bob", "go")
        await until(lambda: of_type(session, "turn.ended"), session)
        journal = sqlite3.connect(f"{(session.folder / 'journal.sqlite').as_uri()}?mode=ro", uri=True)
        cursors = journal.execute("SELECT * FROM v_deliveries_cursors").fetchall()
        head = await session.head()
        page, errors = await opened(chromium, web.link("control"))

        await chat(page, "bob & you")
        await page.mouse.wheel(0, -2000)
        await page.mouse.wheel(0, 2000)
        go = page.locator("#main .msg", has_text="go")
        await go.hover()
        await go.locator("[data-receipts]").click()
        receipts = page.locator(".pop")
        await expect(receipts.locator(".ph").first).to_have_text(
            "Delivered to 1 of 1 agent it was for", timeout=SECONDS
        )
        await expect(receipts.locator(".it")).to_contain_text("bob")
        await expect(receipts.locator(".note")).to_contain_text("never that it was understood")
        await page.keyboard.press("Escape")
        await go.hover()
        await go.locator("[data-thread]").click()
        await expect(page.locator("#pane .msg")).to_have_count(1, timeout=SECONDS)
        reply = page.locator("#main .msg", has_text="on it")
        await reply.hover()
        await reply.locator("[data-knew]").click()
        await expect(page.locator("#pane h2")).to_have_text("What had reached bob", timeout=SECONDS)
        await page.locator("[data-tab=people]").click()
        await page.locator("#list .row", has_text="bob").first.click()
        await page.locator("[data-see-as]").click()
        await expect(page.locator("#as")).to_contain_text("As bob", timeout=SECONDS)
        await page.reload()
        await expect(page.locator("#list .row").first).to_be_visible(timeout=SECONDS)

        assert await session.head() == head
        assert journal.execute("SELECT * FROM v_deliveries_cursors").fetchall() == cursors
        journal.close()
        await page.context.close()

    assert not (session.folder / "marks.sqlite").exists()
    assert errors == []


async def test_on_history_every_act_says_how_to_resume_and_a_runtime_coming_back_is_followed(
    chromium: Browser, root: Path
):
    team = solo(*[[Say("heard you")]] * 3)
    async with Session.start(team, name="s", root=root, cwd=root) as owner:
        await in_state(owner, "bob", "idle")
        await owner.send("@bob", "before the stop")
        await until(lambda: of_type(owner, "turn.ended"), owner)
    async with serving("s", root) as web:
        page, errors = await opened(chromium, web.link("control"))
        await chat(page, "bob & you")
        await expect(said(page, "before the stop")).to_have_count(1)
        await expect(page.locator("#live")).to_have_text("Read-only")
        composer = page.locator(COMPOSER)
        await expect(composer).to_be_disabled()
        await expect(composer).to_have_attribute("title", re.compile("`platoon-harness session resume s` resumes it"))
        await expect(page.locator("[data-x-needs]")).to_have_attribute("aria-disabled", "true")
        await page.goto(web.link("control").partition("#")[0] + "#person=bob")
        for act in await page.locator("[data-x-act]").all():
            await expect(act).to_have_attribute("title", re.compile("platoon-harness session resume s"))
        await chat(page, "bob & you")

        async with Session.resume("s", root=root) as owner:
            await in_state(owner, "bob", "idle")
            await expect(composer).to_be_enabled(timeout=SECONDS)
            await expect(page.locator("#live")).to_have_text("Live")
            await composer.fill("after the resume")
            await composer.press("Enter")
            await expect(said(page, "heard you")).to_have_count(2, timeout=SECONDS)
            await page.context.close()

    assert errors == []
