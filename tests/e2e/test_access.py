"""A disabled control in SwarmChat's page, in a real browser, over a session on scripted harnesses whose worker waits on
an approval: the keyboard reaches it, its reason shows beside it, and a press does nothing else; and in every place the
page draws one, from a view link and from a control link, it takes focus and its reason is its accessible description,
as Playwright computes it by the accessible name and description spec. No screen reader is driven."""

import re
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from playwright.async_api import Browser, Page, expect

from platoon_harness import Session
from platoon_harness_cli.web.server import Web

from ..unit.runtime.support import in_state, of_type, until
from ..unit.web.support import caught_up, team
from .support import SECONDS, chat, opened, serving

pytestmark = [pytest.mark.e2e, pytest.mark.timeout(120)]

VIEW = "This is a view link: it shows the session and acts on nothing."
STEP = """() => {
    const walked = window.walked ||= new Set(), el = document.activeElement, again = walked.has(el);
    walked.add(el);
    return {again, why: el.getAttribute('aria-disabled') === 'true' ? el.title : null};
}"""
"""Note where Tab took focus, saying whether it was there before and, for a disabled control, its reason."""
UNREACHED = """() => [...document.querySelectorAll('[aria-disabled="true"]')]
    .filter(el => el.checkVisibility() && !window.walked.has(el)).map(el => el.outerHTML)"""
"""Each disabled control shown that Tab never reached."""
PLACES = {
    "a chat with an approval": ("#layout=chat", "w1 & you", "#main .msg:has([data-x-card]) [data-x-reply]"),
    "a chat with a person's message": (
        "#layout=chat",
        "lead & you",
        "#main .msg button:has-text('What had reached you?')",
    ),
    "a chat between agents": ("#layout=chat", "lead & w1", "#main .msg [data-x-reply]"),
    "a queue's chat": ("#layout=chat", "#tasks", "#main button:has-text('Tasks')"),
    "a board": ("#layout=board", "#general", "#main .post .votes"),
    "an agent's page": ("#person=lead", "lead", ".person .x-acts button:has-text('Tool activity')"),
    "the person's own page": ("#person=you", "you", "[data-see-as=you]"),
    "an agent's page, seen as that agent": ("#as=lead&person=lead", "lead", "[data-x-act=interrupt]"),
}
"""Where the page draws disabled controls: an address, the heading of what it shows, opened from the address's list
where that is a chat, and a control disabled there from either link."""


@pytest.fixture
async def web(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[tuple[Session, Web]]:
    """The scenario's session, its worker's approval left waiting and its lead idle after both its turns, and `web`
    serving it."""
    monkeypatch.setenv("PLATOON_HARNESS_HOME", str(tmp_path))
    async with Session.start(team(), name="s", root=tmp_path, cwd=tmp_path) as session:
        await in_state(session, "lead", "idle")
        await session.send("@lead", "Fix the flaky test")
        await until(session.approvals, session)
        await until(
            lambda: of_type(session, "turn.ended"), session, lambda found: [e.agent for e in found].count("lead") == 2
        )
        async with serving("s", tmp_path) as served:
            await caught_up(served, session)
            yield session, served


async def test_a_disabled_control_takes_focus_and_its_reason_is_its_accessible_description(
    browser: Browser, web: tuple[Session, Web]
):
    session, served = web
    page, errors = await opened(browser, served.link("view"))
    await chat(page, "w1 & you")
    allow = page.locator('[data-x-decide="allow"]')
    await expect(allow).to_be_disabled(timeout=SECONDS)
    tip = page.locator("#tip")
    head = await session.head()

    reasons = []
    for _ in range(300):
        await page.keyboard.press("Tab")
        step = await page.evaluate(STEP)
        if step["again"]:
            break
        if step["why"]:
            reasons.append(step["why"])
            await expect(page.locator(":focus")).to_have_accessible_description(step["why"])
            await expect(tip).to_be_visible()
            await expect(tip).to_have_text(step["why"])
    unreached = await page.evaluate(UNREACHED)
    await allow.focus()
    await page.keyboard.press("Enter")
    await expect(tip).to_have_text(VIEW)
    composer = page.locator("#main .x-composer textarea")
    await composer.focus()
    await page.keyboard.type("x")
    await page.keyboard.press("Enter")
    await expect(composer).to_have_value("")
    await expect(composer).to_be_focused()
    await expect(page.locator("#main .x-composer .x-why")).to_have_text(VIEW)
    await expect(page.locator(".x-card")).to_have_count(1)
    assert await session.head() == head
    await page.context.close()

    assert len(reasons) >= 7 and set(reasons) == {VIEW}
    assert unreached == []
    assert errors == []


async def say_why(page: Page) -> int:
    """Hold every control shown disabled to taking focus, with a name of its own and its reason as its accessible
    description, which a browser makes of its title only where the title is not its name, and say how many there are.
    None is disabled by `disabled`, which takes a control out of the keyboard's order."""
    assert await page.locator(":disabled").count() == 0
    controls = await page.locator('[aria-disabled="true"]').filter(visible=True).all()
    for control in controls:
        why = await control.get_attribute("title")
        assert why, await control.evaluate("el => el.outerHTML")
        await expect(control).to_have_accessible_description(why)
        await expect(control).to_have_accessible_name(re.compile(r"\S"))
        await expect(control).not_to_have_accessible_name(why)
        assert await control.evaluate("el => el.tabIndex") >= 0
    return len(controls)


async def test_no_disabled_control_lacks_a_reason_a_screen_reader_reads(browser: Browser, web: tuple[Session, Web]):
    _, served = web
    held: dict[str, int] = {}
    for kind in ("view", "control"):
        page, errors = await opened(browser, served.link(kind))
        base = page.url.partition("#")[0]
        for place, (route, heading, disabled) in PLACES.items():
            await page.goto(base + route)
            if "person=" not in route:
                await page.locator("#list .row", has_text=heading.removeprefix("#")).first.click()
            await expect(page.locator("#main h1")).to_have_text(heading, timeout=SECONDS)
            await expect(page.locator("#main .loading:visible")).to_have_count(0, timeout=SECONDS)
            await expect(page.locator(disabled).first).to_be_disabled(timeout=SECONDS)
            held[f"{place}, {kind}"] = await say_why(page)
        await page.goto(base + "#layout=map")
        await expect(page.locator("#pane .prow[data-person=lead]")).to_be_visible(timeout=SECONDS)
        await page.evaluate("S.view.hover = S.view.index.get('u:you'); S.view.showPane()")
        await expect(page.locator("#pane [data-see-as=you]")).to_be_disabled()
        held[f"the map, {kind}"] = await say_why(page)
        await page.goto(base + "#layout=chat")
        await page.locator("#as").click()
        person = page.locator(".pop .it", has=page.locator('[data-kind="human"]'))
        await expect(person).to_be_disabled(timeout=SECONDS)
        held[f"seeing as someone, {kind}"] = await say_why(page)
        await page.context.close()
        assert errors == []

    assert [place for place, count in held.items() if not count] == []
