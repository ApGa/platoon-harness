"""The Provenance pane in a real browser, over a session on scripted harnesses: a message's sources, its uses and its
contributors, each link by how it is known, followed into its chat or its own pane, on a control link and a view link
alike, saying what the record cannot know and showing credit only as what an estimator said."""

import re
from pathlib import Path

import pytest
from playwright.async_api import Browser, Page, expect

from platoon_harness import Session, Team
from platoon_harness.testing import Call

from ..unit.runtime.support import in_state, scripted, until
from .support import SECONDS, chat, opened, serving

pytestmark = [pytest.mark.e2e, pytest.mark.timeout(120)]

ASKED = "inbox/bob@1"
"""The person's message that wakes `bob`, which its answer replies to and cites."""
ANSWERED = "inbox/you@1"
PANE = "#pane .x-provenance"
RECORD = (
    "This is what the record holds: a citation is the agent's claim, being handed something is not using it, and what "
    "reached an agent through a file or a shell leaves nothing here. An estimate is its producer's, never a fact."
)


@pytest.fixture
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("PLATOON_HARNESS_HOME", str(tmp_path))
    return tmp_path


def team() -> Team:
    answer = {"to": "@you", "gist": "the tests pass", "reply_to": ASKED, "based_on": [ASKED]}
    bob = {"harness": scripted([Call("message_send", answer)])}
    return Team.model_validate({"roles": {"bob": bob}, "topology": {"edges": {"bob": ["human"]}}})


async def answered(session: Session) -> None:
    await in_state(session, "bob", "idle")
    await session.send("@bob", "check the tests")
    await until(session.status, session, lambda status: status["settled"])


def message_of(page: Page, said: str):
    """The message in view whose own text is `said`, and not one that answers it, which shows what it answers."""
    return page.locator("#main .msg", has=page.locator(".text", has_text=re.compile(f"^{re.escape(said)}$")))


async def provenance_of(page: Page, said: str) -> None:
    """Open the Provenance pane of the message in view that says `said`."""
    message = message_of(page, said)
    await expect(message).to_have_count(1, timeout=SECONDS)
    await message.hover()
    await message.locator("[data-x-provenance]").click()


async def tabbed_to(page: Page, focused: str) -> str:
    """Press Tab until what has focus says `focused`, as a person would, a few presses at most, and say what it said."""
    for _ in range(8):
        await page.keyboard.press("Tab")
        if said := await page.evaluate(f"{focused} || null"):
            return said
    raise AssertionError(f"Tab never reached {focused}")


def line(page: Page, kind: str, text: str):
    return page.locator(f"{PANE} .x-line", has=page.locator(".x-kind", has_text=kind), has_text=text)


async def test_provenance_on_a_message_shows_sources_uses_and_contributors(chromium: Browser, root: Path):
    """And asked again, the pane reads again: a second estimate shows beside the first, never summed."""
    async with Session.start(team(), name="s", root=root, cwd=root) as session, serving("s", root) as web:
        await answered(session)
        head = await session.head()
        estimate = {"kind": "credit", "scope": "team", "status": "scored", "head_seq": head}
        await session.annotate(ANSWERED, producer="even-split", producer_version="0", value=0.5, **estimate)
        page, errors = await opened(chromium, web.link("control"))
        await chat(page, "bob & you")

        await provenance_of(page, "the tests pass")

        pane = page.locator(PANE)
        await expect(page.locator("#pane h2")).to_have_text(f"Provenance of {ANSWERED}", timeout=SECONDS)
        await expect(pane.locator(".note")).to_have_text(RECORD)
        await expect(pane.locator(".x-part")).to_have_text(["Sources", "Uses", "Contributors", "Credit and rewards"])
        await expect(line(page, "declared", f"{ASKED} by @you: check the tests; seen: wake")).to_have_count(1)
        await expect(line(page, "cause", f"{ASKED} message.sent by @you: check the tests")).to_have_count(1)
        await expect(pane).to_contain_text("made by @bob in turn")
        await expect(pane).to_contain_text(f"lineage read at head {head:,}")
        await expect(pane).to_contain_text("@you: declared, cause, 1 event, the first inbox/bob@1, 1 hop back")
        await expect(pane).to_contain_text("weighing and ranking nobody")
        said = f"0.5 by even-split, version 0, params 44136fa3, team, of the trace at head {head:,}"
        await expect(line(page, "credit", said)).to_have_count(1)
        await session.annotate(ANSWERED, producer="judge", producer_version="2", **(estimate | {"status": "unscored"}))
        await provenance_of(page, "the tests pass")
        await expect(line(page, "credit", "no value, unscored, by judge, version 2")).to_have_count(1, timeout=SECONDS)
        await expect(line(page, "credit", "0.5 by even-split, version 0")).to_have_count(1)
        await page.context.close()

    assert errors == []


async def test_a_ref_in_the_pane_is_followed_into_its_chat_or_its_own_pane(chromium: Browser, root: Path):
    async with Session.start(team(), name="s", root=root, cwd=root) as session, serving("s", root) as web:
        await answered(session)
        page, errors = await opened(chromium, web.link("control"))
        await page.goto(web.link("control").partition("#")[0] + f"#provenance={ANSWERED}")
        heading = page.locator("#pane h2")
        await expect(heading).to_have_text(f"Provenance of {ANSWERED}", timeout=SECONDS)

        await line(page, "declared", ASKED).click()
        await expect(heading).to_have_text(f"Provenance of {ASKED}", timeout=SECONDS)
        await expect(message_of(page, "check the tests")).to_have_class(re.compile(r"\bflash\b"), timeout=SECONDS)
        await expect(page.locator("#main .mhead")).to_contain_text("bob")
        chat_shown = page.url

        offered = line(page, "observed", "@bob, first by context/bob@")
        await expect(offered).to_have_count(1, timeout=SECONDS)
        offer = (await offered.get_attribute("data-x-follow")) or ""
        await offered.click()
        await expect(heading).to_have_text(f"Provenance of {offer}", timeout=SECONDS)
        await expect(page.locator(PANE)).to_contain_text(f"context.offered {offer}")
        await expect(message_of(page, "check the tests")).to_have_count(1)
        shown_after = page.url

        await page.go_back()
        await expect(heading).to_have_text(f"Provenance of {ASKED}", timeout=SECONDS)
        back = page.url
        await page.keyboard.press("Escape")
        await expect(page.locator("#pane")).not_to_have_class(re.compile(r"\bopen\b"), timeout=SECONDS)
        await page.context.close()

    assert offer.startswith("context/bob@") and back == chat_shown
    assert shown_after.partition("&provenance=")[0] == chat_shown.partition("&provenance=")[0]
    assert errors == []


async def test_the_pane_says_what_the_record_cannot_know(chromium: Browser, root: Path):
    async with Session.start(team(), name="s", root=root, cwd=root) as session, serving("s", root) as web:
        await answered(session)
        page, errors = await opened(chromium, web.link("view"))
        await chat(page, "bob & you")

        await provenance_of(page, "check the tests")

        pane = page.locator(PANE)
        await expect(page.locator("#pane h2")).to_have_text(f"Provenance of {ASKED}", timeout=SECONDS)
        await expect(pane.locator(".note")).to_have_text(RECORD)
        await expect(pane).to_contain_text("no estimator has said anything of it")
        await expect(line(page, "observed", "its harness said it took an offer of it")).to_have_count(1)
        await expect(pane.locator(".x-line:not([data-x-follow])", has_text="made by @you")).to_have_count(1)
        await page.context.close()

    assert errors == []


async def test_the_pane_is_opened_and_followed_from_the_keyboard(chromium: Browser, root: Path):
    """A message's actions show while focus is in it, so Tab reaches Provenance, and each link in the pane is a button,
    which Tab reaches and Enter follows."""
    async with Session.start(team(), name="s", root=root, cwd=root) as session, serving("s", root) as web:
        await answered(session)
        page, errors = await opened(chromium, web.link("control"))
        await chat(page, "bob & you")
        message = message_of(page, "the tests pass")
        await expect(message).to_have_count(1, timeout=SECONDS)

        await message.locator("[data-x-reply]").focus()
        await expect(message.locator(".actions")).to_have_css("opacity", "1")
        await tabbed_to(page, "document.activeElement.dataset.xProvenance")
        await page.keyboard.press("Enter")
        heading = page.locator("#pane h2")
        await expect(heading).to_have_text(f"Provenance of {ANSWERED}", timeout=SECONDS)
        await expect(page.locator(f"{PANE} button.x-line").first).to_be_visible(timeout=SECONDS)
        await page.locator("#pane [data-close-pane]").focus()
        followed = await tabbed_to(page, "document.activeElement.dataset.xFollow")
        await page.keyboard.press("Enter")
        await expect(heading).to_have_text(f"Provenance of {followed}", timeout=SECONDS)
        await page.context.close()

    assert errors == []


async def test_a_message_s_actions_stay_within_it_beside_the_pane(chromium: Browser, root: Path):
    """With the pane open at 1024 pixels, the chat is narrow, and a message's actions wrap within it rather than cover
    what is beside it."""
    async with Session.start(team(), name="s", root=root, cwd=root) as session, serving("s", root) as web:
        await answered(session)
        page, errors = await opened(chromium, web.link("control"))
        await page.set_viewport_size({"width": 1024, "height": 768})
        await chat(page, "bob & you")
        await provenance_of(page, "the tests pass")
        await expect(page.locator("#pane h2")).to_have_text(f"Provenance of {ANSWERED}", timeout=SECONDS)
        message = message_of(page, "the tests pass")
        await message.hover()
        actions, whole = await message.locator(".actions").bounding_box(), await message.bounding_box()
        await page.context.close()

    assert actions is not None and whole is not None
    assert whole["x"] <= actions["x"] and actions["x"] + actions["width"] <= whole["x"] + whole["width"]
    assert errors == []
