"""A person acting from SwarmChat's page, in a real browser, over a session on scripted harnesses: a message in the
agent's input path once, a reply drawn in the browser and the terminal at once, an approval that takes effect once
whichever client answers first, a reply in a thread, a file as a body, and an agent's and the session's acts, asked
about first where they are marked so."""

import asyncio
import json
import re
from pathlib import Path

import pytest
from playwright.async_api import Browser, expect

from platoon_harness import Session, Team
from platoon_harness.runtime.control import BODY_LIMIT
from platoon_harness.testing import Ask, Call, Hang, Say
from platoon_harness_cli.ops import cut
from platoon_harness_cli.tui.app import TerminalUI
from platoon_harness_cli.tui.transcript import Transcript

from ..integration.scripts import wire
from ..unit.runtime.support import in_state, of_type, scripted, solo, until
from ..unit.tui.support import drawn, workspace
from .support import SECONDS, chat, opened, said, serving

pytestmark = [pytest.mark.e2e, pytest.mark.timeout(120)]

COMPOSER = "#main .x-composer textarea"
PANE = "#pane .x-composer textarea"


@pytest.fixture
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("PLATOON_HARNESS_HOME", str(tmp_path))
    return tmp_path


async def test_a_person_s_message_from_the_browser_enters_a_wire_harness_s_input_once(chromium: Browser, root: Path):
    team = Team.model_validate({"roles": {"bob": {"harness": wire("saying")}}})
    async with Session.start(team, name="s", root=root, cwd=root) as session, serving("s", root) as web:
        await in_state(session, "bob", "idle")
        page, errors = await opened(chromium, web.link("control"))
        await chat(page, "bob & you")
        await expect(page.locator("#main .x-to")).to_have_text("To @bob")

        await page.locator(COMPOSER).fill("Fix the flaky test")
        await page.keyboard.press("Enter")

        await expect(said(page, "done")).to_have_count(1, timeout=SECONDS)
        await until(lambda: of_type(session, "turn.ended"), session)
        sent = [event for event in await of_type(session, "message.sent") if event.actor == "human:you"]
        delivered = await of_type(session, "context.delivered")
        await expect(said(page, "Fix the flaky test")).to_have_count(1)
        await expect(page.locator(COMPOSER)).to_have_value("")
        await page.context.close()
    transcript = json.loads(next(root.rglob("scripted-bob.json")).read_text())
    told = [message["content"] for message in transcript if message["role"] == "user"]

    assert [event.gist for event in sent] == ["Fix the flaky test"]
    assert [event.agent for event in delivered] == ["bob"]
    assert sum("Fix the flaky test" in text for text in told) == 1
    assert errors == []


async def test_the_composer_keeps_shift_enter_lines_and_cuts_a_long_text_as_the_terminal_does(
    chromium: Browser, root: Path
):
    long = "every word of a long note " * 20
    async with Session.start(solo([Hang()]), name="s", root=root, cwd=root) as session, serving("s", root) as web:
        await in_state(session, "bob", "idle")
        page, errors = await opened(chromium, web.link("control"))
        await chat(page, "bob & you")

        composer = page.locator(COMPOSER)
        await composer.press_sequentially("line one")
        await composer.press("Shift+Enter")
        await composer.press_sequentially("line two")
        await composer.press("Enter")
        await expect(said(page, "line two")).to_have_count(1, timeout=SECONDS)
        await composer.fill(long)
        await composer.press("Enter")
        await expect(said(page, long.strip())).to_have_count(1, timeout=SECONDS)
        sent = [event for event in await of_type(session, "message.sent") if event.actor == "human:you"]
        body = await session.get_body(sent[1].data["body"])
        await page.context.close()

    assert sent[0].gist == "line one\nline two" and sent[0].data["body"] is None
    assert (sent[1].gist, body) == (cut(long.strip())[0], long.strip().encode())
    assert errors == []


async def test_a_file_goes_as_a_message_s_body_its_limit_said_before_it_is_sent(chromium: Browser, root: Path):
    notes = ("# Notes\n" + "a line of the notes\n" * 2000).encode()
    async with Session.start(solo([Hang()]), name="s", root=root, cwd=root) as session, serving("s", root) as web:
        await in_state(session, "bob", "idle")
        page, errors = await opened(chromium, web.link("control"))
        await chat(page, "bob & you")
        attach = page.locator("#main [data-x-attach]")
        files = page.locator("#main [data-x-file]")

        await expect(attach).to_have_attribute("title", re.compile(r"of at most 12\.6 MB$"))
        await files.set_input_files(
            {"name": "big.bin", "mimeType": "application/octet-stream", "buffer": b"\0" * (BODY_LIMIT + 1)}
        )
        await expect(page.locator("#main .x-why")).to_have_text(
            f"big.bin is {BODY_LIMIT + 1:,} bytes, more than the {BODY_LIMIT:,} a body may be."
        )
        await files.set_input_files({"name": "notes.md", "mimeType": "text/markdown", "buffer": notes})
        await expect(page.locator("#main .x-file")).to_have_text(re.compile(r"^With notes\.md, .* as its body\.$"))
        held = asyncio.Event()

        async def hold(route):
            await held.wait()
            await route.continue_()

        await page.route("**/x/body", hold)
        await page.locator(COMPOSER).fill("the notes")
        await page.locator(COMPOSER).press("Enter")
        await expect(page.locator("#main .x-why")).to_have_text(re.compile(r"^Sending notes\.md: \d+%$"))
        held.set()
        await expect(said(page, "the notes (file notes.md)")).to_have_count(1, timeout=SECONDS)
        sent = [event for event in await of_type(session, "message.sent") if event.actor == "human:you"]
        body = await session.get_body(sent[0].data["body"])
        await page.context.close()

    assert [event.gist for event in sent] == ["the notes (file notes.md)"] and body == notes
    assert errors == []


async def test_a_message_and_its_reply_appear_in_the_browser_and_the_terminal_at_once_with_none_twice(
    chromium: Browser, root: Path
):
    team = solo([Say("heard the browser")], [Say("heard the terminal")])
    async with Session.start(team, name="s", root=root, cwd=root) as session, serving("s", root) as web:
        await in_state(session, "bob", "idle")
        page, errors = await opened(chromium, web.link("control"))
        await chat(page, "bob & you")
        app = TerminalUI("s")
        async with app.run_test(size=(120, 30)) as pilot:
            await drawn(pilot, lambda text: "@bob" in text)

            await page.locator(COMPOSER).fill("from the browser")
            await page.keyboard.press("Enter")
            await drawn(pilot, lambda text: "heard the browser" in text and "from the browser" in text)
            await pilot.press(*"from the terminal", "enter")
            await drawn(pilot, lambda text: "heard the terminal" in text)
            await expect(said(page, "heard the terminal")).to_have_count(1, timeout=SECONDS)
            lines = [block.line.plain for block in workspace(app).query_one(Transcript).blocks]
        for text in ("from the browser", "heard the browser", "from the terminal"):
            await expect(said(page, text)).to_have_count(1)
        sent = [event.gist for event in await of_type(session, "message.sent") if event.actor == "human:you"]
        await page.context.close()

    assert sent == ["from the browser", "from the terminal"]
    for text in ("from the browser", "heard the browser", "from the terminal", "heard the terminal"):
        assert sum(text in line for line in lines) == 1, (text, lines)
    assert errors == []


async def asked(session: Session) -> dict:
    """The approval bob asks for once told to go."""
    await in_state(session, "bob", "idle")
    await session.send("@bob", "go")
    return (await until(session.approvals, session))[0]


async def test_an_approval_answered_from_the_browser_and_the_terminal_at_once_takes_effect_once(
    chromium: Browser, root: Path
):
    team = solo([Ask("Ship the fix?"), Say("shipped")])
    async with Session.start(team, name="s", root=root, cwd=root) as session, serving("s", root) as web:
        await asked(session)
        page, errors = await opened(chromium, web.link("control"))
        await chat(page, "bob & you")
        await expect(page.locator("[data-x-needs] .badge")).to_have_text("1", timeout=SECONDS)
        allow = page.locator('[data-x-decide="allow"]')
        await expect(allow).to_be_enabled(timeout=SECONDS)
        app = TerminalUI("s")
        async with app.run_test(size=(120, 30)) as pilot:
            await drawn(pilot, lambda text: "⚠ approval" in text)
            await pilot.press("alt+a", *"/yes")

            await asyncio.gather(pilot.press("enter"), allow.evaluate("button => button.click()"))

            resolved = await until(lambda: of_type(session, "approval.resolved"), session)
            winner = resolved[0].data["via"]
            await expect(page.locator(".x-card.x-done")).to_have_text(f"Allowed by you via {winner}", timeout=SECONDS)
            live = workspace(app).live
            assert live is not None
            await drawn(pilot, lambda text: all(row["kind"] != "approval" for row in live.attention.values()))
            if winner == "tui":
                await expect(page.locator("#tip")).to_have_text("Already decided by you via tui.", timeout=SECONDS)
            else:
                await drawn(pilot, lambda text: "Already decided, resolved, by human:you via browser" in text)
        await expect(page.locator("[data-x-needs] .badge")).to_have_count(0, timeout=SECONDS)
        await until(lambda: of_type(session, "turn.ended"), session)
        resolved = await of_type(session, "approval.resolved")
        refused = [event for event in await of_type(session, "op.refused") if event.outcome.op == "approval.resolve"]
        await page.context.close()

    assert len(resolved) == 1 and resolved[0].data["verdict"] == "allow"
    assert len(refused) == 1 and refused[0].outcome.refusal.code == "conflict"
    assert errors == []


async def test_needs_you_counts_where_the_person_must_act_and_its_actions_settle_it(chromium: Browser, root: Path):
    team = solo([Ask("Ship the fix?"), Say("shipped")])
    async with Session.start(team, name="s", root=root, cwd=root) as session, serving("s", root) as web:
        await asked(session)
        page, errors = await opened(chromium, web.link("control"))
        needs = page.locator("[data-x-needs]")
        await expect(needs.locator(".badge")).to_have_text("1", timeout=SECONDS)

        await chat(page, "bob & you")
        card, question = page.locator(".msg .body > .x-card"), said(page, "Ship the fix?")
        await expect(card).to_have_count(1, timeout=SECONDS)
        under = (await card.bounding_box() or {})["y"] - (await question.bounding_box() or {})["y"]
        await needs.click()
        place = page.locator(".x-needs .x-need")
        await expect(place).to_have_text(re.compile(r"⚠ approval .*bob: Ship the fix\?AllowDeny$"))
        await place.locator(".t").click()
        await expect(page.locator("#main .x-to")).to_have_text("To @bob", timeout=SECONDS)
        await needs.click()
        await place.get_by_role("button", name="Allow").click()

        await expect(page.locator("#tip")).to_have_text("Allow: Ship the fix?", timeout=SECONDS)
        await expect(page.locator(".x-card.x-done")).to_have_text("Allowed by you via browser", timeout=SECONDS)
        await expect(needs.locator(".badge")).to_have_count(0, timeout=SECONDS)
        resolved = await of_type(session, "approval.resolved")
        await page.context.close()

    assert [(event.data["verdict"], event.data["via"]) for event in resolved] == [("allow", "browser")]
    assert under > 0
    assert errors == []


async def test_an_approval_answered_from_two_browsers_at_once_takes_effect_once(chromium: Browser, root: Path):
    team = solo([Ask("Ship the fix?"), Say("shipped")])
    async with Session.start(team, name="s", root=root, cwd=root) as session, serving("s", root) as web:
        await asked(session)
        pages = [await opened(chromium, web.link("control")) for _ in range(2)]
        for page, _ in pages:
            await chat(page, "bob & you")
            await expect(page.locator('[data-x-decide="deny"]')).to_be_enabled(timeout=SECONDS)

        await asyncio.gather(
            *(page.locator('[data-x-decide="deny"]').evaluate("button => button.click()") for page, _ in pages)
        )

        for page, _ in pages:
            await expect(page.locator(".x-card.x-done")).to_have_text("Denied by you via browser", timeout=SECONDS)
        told = [await page.locator("#tip").text_content() for page, _ in pages]
        resolved = await of_type(session, "approval.resolved")
        refused = [event for event in await of_type(session, "op.refused") if event.outcome.op == "approval.resolve"]
        for page, _ in pages:
            await page.context.close()

    assert len(resolved) == 1 and resolved[0].data["verdict"] == "deny"
    assert len(refused) == 1 and told.count("Already decided by you via browser.") == 1
    assert [errors for _, errors in pages] == [[], []]


async def test_a_reply_in_a_thread_cites_the_message_it_answers(chromium: Browser, root: Path):
    turn = [Say("a thought aloud"), Call("message_send", {"to": "@you", "gist": "Which branch?"})]
    team = Team.model_validate(
        {"roles": {"bob": {"harness": scripted(turn)}}, "topology": {"edges": {"bob": ["human"]}}}
    )
    async with Session.start(team, name="s", root=root, cwd=root) as session, serving("s", root) as web:
        await in_state(session, "bob", "idle")
        await session.send("@bob", "go")
        page, errors = await opened(chromium, web.link("control"))
        await chat(page, "bob & you")
        question = page.locator("#main .msg", has_text="Which branch?")
        await expect(question).to_have_count(1, timeout=SECONDS)
        aloud = page.locator("#main .msg", has_text="a thought aloud").locator("[data-x-reply]")
        await expect(aloud).to_be_disabled()
        await expect(aloud).to_have_attribute("title", re.compile("is no message a reply can cite"))
        provenance = question.locator(".actions button", has_text="Provenance")
        await expect(provenance).to_be_disabled()
        await expect(provenance).to_have_attribute("title", re.compile("^Not built yet: "))

        await question.hover()
        await question.locator("[data-x-reply]").click()
        await expect(page.locator("#pane .x-to")).to_have_text("Reply to bob, to @bob", timeout=SECONDS)
        await page.locator(PANE).fill("main, please")
        await page.locator(PANE).press("Enter")

        await expect(page.locator("#pane .msg .text", has_text="main, please")).to_have_count(1, timeout=SECONDS)
        sent = [event for event in await of_type(session, "message.sent") if event.gist == "main, please"]
        asked = next(event for event in await of_type(session, "message.sent") if event.gist == "Which branch?")
        await page.context.close()

    assert [event.data["reply_to"] for event in sent] == [f"{asked.stream}@{asked.version}"]
    assert errors == []


def lead_and_child() -> Team:
    """A lead that starts `w` and works on, and `w` working on its goal."""
    roles = {
        "lead": {
            "harness": scripted([Call("agent_spawn", {"name": "w", "child_role": "worker", "goal": "go"}), Hang()]),
            "may_spawn": ["worker"],
        },
        "worker": {"harness": scripted([Hang()]), "count": 0},
    }
    topology = {"edges": {"lead": ["children"], "worker": ["parent"]}, "limits": {"max_depth": 2}}
    return Team.model_validate({"roles": roles, "topology": topology})


async def test_an_agent_s_acts_ask_first_where_marked_and_say_what_came_of_them(chromium: Browser, root: Path):
    async with Session.start(lead_and_child(), name="s", root=root, cwd=root) as session, serving("s", root) as web:
        await in_state(session, "lead", "idle")
        await session.send("@lead", "go")
        await until(session.agents, session, lambda agents: len(agents) == 2)
        await in_state(session, "w", "running")
        page, errors = await opened(chromium, web.link("control"))
        said_here = page.locator(".person .x-said")

        await page.goto(web.link("control").partition("#")[0] + "#person=lead")
        await page.locator('[data-x-act="stop-below"]').click()
        await expect(said_here).to_have_text(re.compile(r"^Stopped the turns of @lead, @w\. "), timeout=SECONDS)
        await until(lambda: of_type(session, "turn.ended"), session, lambda found: len(found) == 2)
        await page.locator('[data-x-act="interrupt"]').click()
        await expect(said_here).to_have_text(re.compile(r"^Interrupt @lead: conflict: "), timeout=SECONDS)

        await page.goto(web.link("control").partition("#")[0] + "#person=w")
        await page.locator('[data-x-act="retire"]').click()
        await expect(page.locator(".x-ask .ph")).to_have_text("Retire @w? It cannot be taken back.")
        await page.locator(".x-ask [data-x-no]").click()
        await page.locator('[data-x-act="retire"]').click()
        await page.locator(".x-ask [data-x-yes]").click()
        await expect(said_here).to_have_text("Retire @w: done.", timeout=SECONDS)

        await page.goto(web.link("control").partition("#")[0] + "#person=you")
        await page.locator('[data-x-link="view"]').click()
        await expect(said_here).to_have_text(re.compile(r"^A view link, which opens once, within ten minutes: "))
        made = (await said_here.text_content() or "").rpartition(" ")[2]
        served = f"http://127.0.0.1:{web.port}/view#link="
        viewer, viewer_errors = await opened(chromium, made)
        credential = await viewer.evaluate("X.caps.credential")
        await viewer.context.close()
        await page.locator('[data-x-act="close"]').click()
        await page.locator(".x-ask [data-x-yes]").click()
        await expect(said_here).to_have_text("Close the session: done.", timeout=SECONDS)
        ended = await of_type(session, "agent.ended")
        closing = (await session.status())["state"]
        commands = [event.outcome.op for event in await of_type(session, "op.refused")]
        await page.context.close()

    assert [(event.agent, event.data["status"]) for event in ended] == [("w", "retired")]
    assert closing in ("closing", "closed")
    assert commands == ["agent.interrupt"]
    assert made.startswith(served) and credential == "view"
    assert errors == [] and viewer_errors == []
