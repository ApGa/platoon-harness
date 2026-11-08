"""SwarmChat's page for the keyboard, a screen reader and a phone, in a real browser, over a session on scripted
harnesses whose worker waits on an approval. A disabled control: the keyboard reaches it, its reason shows beside it,
and a press does nothing else; and in every place the page draws one, from a view link and from a control link, it takes
focus and its reason is its accessible description, as Playwright computes it by the accessible name and description
spec. No screen reader is driven. On a phone's screen, emulated with touch, the page scrolls no wider than the screen
and every act lies within it, and a resize keeps where a chat is read, focus and the composer's target."""

import re
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from playwright.async_api import Browser, Page, expect

from platoon_harness import Session
from platoon_harness_cli.web.server import Web

from ..unit.runtime.support import in_state, of_type, until
from ..unit.web.support import QUIET, caught_up, team
from .support import SECONDS, chat, opened, said, serving, watched

pytestmark = [pytest.mark.e2e, pytest.mark.timeout(120)]

VIEW = "This is a view link: it shows the session and acts on nothing."
STEP = """() => {
    const at = window.at ||= el =>
        el.parentElement ? `${at(el.parentElement)}/${[...el.parentElement.children].indexOf(el)}` : '';
    const walked = window.walked ||= new Set(), el = document.activeElement, again = walked.has(at(el));
    walked.add(at(el));
    return {again, why: el.getAttribute('aria-disabled') === 'true' ? el.title : null};
}"""
"""Note where Tab took focus, saying whether it was there before and, for a disabled control, its reason. A place is
where it stands in the page, which a control drawn again as the session moves keeps, where the element is a new one."""
UNREACHED = """() => [...document.querySelectorAll('[aria-disabled="true"]')]
    .filter(el => el.checkVisibility() && !window.walked.has(window.at(el))).map(el => el.outerHTML)"""
"""Each disabled control shown whose place Tab never reached."""
PLACES = {
    "a chat with an approval": ("#layout=chat", "w1 & you", "#main .msg:has([data-x-card]) [data-x-reply]"),
    "a chat with a person's message": (
        "#layout=chat",
        "lead & you",
        "#main .msg button:has-text('What had reached you?')",
    ),
    "a chat between agents": ("#layout=chat", "lead & w1", "#main .msg [data-x-reply]"),
    "a queue's chat": ("#layout=chat", "#tasks", "#main .x-composer button:has-text('Send')"),
    "a board": ("#layout=board", "#general", "#main .post .votes"),
    "an agent's page": ("#person=lead", "lead", ".person .msg [data-x-reply]"),
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

    assert len(reasons) >= 6 and set(reasons) == {VIEW}
    assert unreached == []
    assert errors == []


async def test_needs_you_takes_focus_and_gives_it_back_and_a_decided_request_keeps_it(
    browser: Browser, web: tuple[Session, Web]
):
    """From the keyboard alone, on a control link: Needs you takes focus as it opens, so Tab reaches its actions first,
    and Escape gives focus back to its row; Allow pressed on a request's card leaves focus on what the card says came of
    it, where it dropped to the page before."""
    _, served = web
    page, errors = await opened(browser, served.link("control"))
    needs = page.locator("[data-x-needs]")
    await expect(needs.locator(".badge")).to_be_visible(timeout=SECONDS)

    await needs.focus()
    await page.keyboard.press("Enter")
    box = page.locator(".x-needs")
    await expect(box).to_be_focused()
    await expect(box).to_have_accessible_name("Needs you")
    await page.keyboard.press("Tab")
    await expect(box.locator("button").first).to_be_focused()
    await page.keyboard.press("Escape")
    await expect(box).to_have_count(0)
    await expect(needs).to_be_focused()
    await chat(page, "w1 & you")
    allow = page.locator('[data-x-decide="allow"]')
    await expect(allow).to_be_enabled(timeout=SECONDS)
    await allow.focus()
    await page.keyboard.press("Enter")
    done = page.locator(".x-card.x-done")
    await expect(done).to_have_text(re.compile(r"^Allowed by you"), timeout=SECONDS)
    await expect(done).to_be_focused()
    await page.context.close()

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


PHONE = {"width": 390, "height": 844}
"""A phone's screen held upright, in CSS pixels, as an iPhone 12, 13 or 14 gives it."""
WIDE = {"width": 1280, "height": 800}
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
PANES = {
    "who reached whom": ("#layout=chat&interactions=1", "#pane .x-provenance button"),
    "tool activity": ("#person=lead&tools=lead", "#pane .x-provenance button"),
    "a queue's tasks": ("#layout=chat&tasks=tasks", "#pane .x-channel .x-change"),
    "the map": ("#layout=map", "#pane .prow[data-person=lead]"),
}
"""More places, at an address alone, with what shows once each is drawn."""


async def reached(page: Page) -> dict[str, object]:
    """What `REACHED` finds, once nothing shown is loading."""
    await expect(page.locator(".loading:visible")).to_have_count(0, timeout=SECONDS)
    return await page.evaluate(REACHED)


async def test_at_390_px_the_page_scrolls_no_wider_reaches_every_act_and_shows_the_composer(
    browser: Browser, web: tuple[Session, Web]
):
    """On a phone's screen with touch, from a control link, in every place that draws a disabled control, in panes and
    on the map: the page scrolls no wider than the screen, and every act, scrolled into view, lies within its sides with
    nothing over it, Needs you's among them. A tap on a message gives it focus, which shows its actions, and the
    composer shows whole at the foot of a chat as a press on its row opens it, and as a reload opens it."""
    _, served = web
    page = await (await browser.new_context(viewport=PHONE, has_touch=True)).new_page()
    errors = watched(page)
    await page.goto(served.link("control"))
    await expect(page.locator("#list .row").first).to_be_visible(timeout=SECONDS)
    base = page.url.partition("#")[0]
    found: dict[str, dict[str, object]] = {}
    for place, (route, heading, _) in PLACES.items():
        await page.goto(base + route)
        if "person=" not in route:
            await page.locator("#list .row", has_text=heading.removeprefix("#")).first.click()
        await expect(page.locator("#main h1")).to_have_text(heading, timeout=SECONDS)
        found[place] = await reached(page)
    for place, (route, drawn) in PANES.items():
        await page.goto(base + route)
        await expect(page.locator(drawn).first).to_be_visible(timeout=SECONDS)
        found[place] = await reached(page)
    await page.goto(base + "#layout=chat")
    await page.locator("[data-x-needs]").click()
    await expect(page.locator(".x-needs [data-x-action]").first).to_be_visible(timeout=SECONDS)
    found["needs you"] = await reached(page)
    await page.keyboard.press("Escape")

    await chat(page, "w1 & you")
    composer = page.locator("#main .x-composer")
    await expect(composer).to_be_in_viewport(ratio=0.99)
    message = page.locator("#main .msg", has_text="Ship the fix?")
    await message.locator(".text").tap()
    await expect(message).to_be_focused()
    await expect(message.locator(".actions")).to_have_css("opacity", "1")
    await page.reload()
    await expect(page.locator("#main .msg", has_text="Ship the fix?")).to_be_visible(timeout=SECONDS)
    await expect(composer).to_be_in_viewport(ratio=0.99)
    await page.context.close()

    assert {place: (it["missed"], it["wider"]) for place, it in found.items()} == {place: ([], 0) for place in found}
    assert all(it["acts"] for it in found.values())
    assert errors == []


@pytest.fixture
async def chatty(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[Web]:
    """A session whose lead hangs in its first turn while forty messages from the person wait for it, each two lines
    long or more on a phone, and `web` serving it."""
    monkeypatch.setenv("PLATOON_HARNESS_HOME", str(tmp_path))
    async with Session.start(QUIET, name="s", root=tmp_path, cwd=tmp_path) as session:
        for n in range(1, 41):
            await session.send("@lead", f"Message {n}: the parser splits on whitespace, so a quoted name breaks it")
        async with serving("s", tmp_path) as served:
            await caught_up(served, session)
            yield served


FRAME = "() => new Promise(done => requestAnimationFrame(() => done()))"
"""A frame of the page's, which runs after any resize the frame began with has been handled."""
FOOT = "el => el.scrollHeight - el.scrollTop - el.clientHeight"
"""How far a list is from its foot."""
TOP = """box => {
    const edge = box.getBoundingClientRect().top;
    const first = [...box.querySelectorAll('.msg')].find(m => m.getBoundingClientRect().top >= edge);
    return [first.querySelector('.text').textContent, Math.round(first.getBoundingClientRect().top - edge)];
}"""
"""The first message whose top is in view, by its words, and how far below the list's top it is."""


async def resized(page: Page, size: dict[str, int]) -> None:
    """Resize the page, and wait until it has handled the resize."""
    await page.set_viewport_size(size)
    await page.wait_for_function(f"() => innerWidth === {size['width']}")
    await page.evaluate(FRAME)


async def test_a_resize_keeps_scroll_focus_and_the_composer_s_target(browser: Browser, chatty: Web):
    """Between a wide window and a phone's screen, and back: a chat at its foot stays at its foot, so it goes on
    following, and one read higher up keeps the message at its top where it was; focus stays in the composer, which
    shows, with its draft, and its target stays the chat's."""
    page, errors = await opened(browser, chatty.link("control"))
    await chat(page, "lead & you")
    await expect(said(page, "Message 40:")).to_be_visible(timeout=SECONDS)
    box, composer = page.locator("#main .scroll"), page.locator("#main .x-composer textarea")
    await composer.fill("a draft")
    feet = []
    for size in (PHONE, WIDE):
        await resized(page, size)
        feet.append(await box.evaluate(FOOT))
        await expect(composer).to_be_focused()
        await expect(composer).to_be_in_viewport(ratio=0.99)

    await said(page, "Message 10:").evaluate(
        "el => { const box = el.closest('.scroll'), m = el.closest('.msg');"
        " box.scrollTop += m.getBoundingClientRect().top - box.getBoundingClientRect().top - 10; }"
    )
    await page.evaluate(FRAME)
    above = await box.evaluate(FOOT)
    read = [await box.evaluate(TOP)]
    for size in (PHONE, WIDE):
        await resized(page, size)
        read.append(await box.evaluate(TOP))
        await expect(composer).to_be_focused()
        await expect(composer).to_have_value("a draft")
        await expect(composer).to_be_in_viewport(ratio=0.99)
        await expect(page.locator("#main .x-composer .x-to")).to_have_text("To @lead")
    await page.context.close()

    assert [foot <= 1 for foot in feet] == [True, True]
    assert above > 80 and read[0][0].startswith("Message 10:") and read == [read[0]] * 3
    assert errors == []
