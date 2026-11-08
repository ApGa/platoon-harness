"""Tool activity on an agent's page in a real browser, over a session on scripted harnesses: its tool calls a page at a
time, whole turns of them, newest first, each spawn under the call that made it or saying it joins no known call, and
each line followed into its provenance; and what it is saying now, above them, apart from its messages, said not to be
in the journal yet, and gone with the runtime that said it."""

import re
from collections.abc import Awaitable, Callable, Mapping
from pathlib import Path
from typing import Any

import pytest
from playwright.async_api import Browser, Page, expect

from platoon_harness import Session, Team
from platoon_harness.drivers import AgentSpec
from platoon_harness.testing import Call, Do, Hang, Say, ScriptedDriver
from platoon_harness_cli import calls
from platoon_harness_cli.web import server

from ..unit.runtime.support import harness, in_state, of_type, until
from .support import SECONDS, chat, opened, said, serving

pytestmark = [pytest.mark.e2e, pytest.mark.timeout(120)]

type Caller = Callable[[str, Mapping[str, Any]], Awaitable[Any]]
PANE = "#pane .x-tools"
SAYING = f"{PANE} .x-saying"
ABOUT = "Not in the journal yet: what @lead is saying now, until the item it becomes replaces it."


@pytest.fixture
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("PLATOON_HARNESS_HOME", str(tmp_path))
    return tmp_path


async def told(spec: AgentSpec, call: Caller) -> None:
    """Two calls of the lead's own, each under an id of its own, as a harness's are."""
    for gist in ("one", "two"):
        await call("message_send", {"to": "@you", "gist": gist})


async def spawning(spec: AgentSpec, call: Caller) -> None:
    """A call of the lead's own that spawns `w1`, under the id it gave it."""
    await call("agent_spawn", {"name": "w1", "child_role": "worker", "goal": "be w1"})


def team(*turns: list[Any]) -> Team:
    """`lead`, whose turns are `turns`, each woken by a message, and `worker`, which it may spawn."""
    roles = {
        "lead": {"harness": harness(lambda: ScriptedDriver(turns)), "may_spawn": ["worker"]},
        "worker": {"harness": harness(lambda: ScriptedDriver([[Hang()]])), "count": 0},
    }
    edges = {"lead": ["children", "human"], "worker": ["parent"]}
    return Team.model_validate({"roles": roles, "topology": {"edges": edges, "limits": {"max_hops": 4}}})


async def turned(session: Session, turns: int) -> None:
    """Wake the lead for each of its `turns`, one after another, until each has ended."""
    await in_state(session, "lead", "idle")
    for turn in range(1, turns + 1):
        await session.send("@lead", f"turn {turn}")
        ended = lambda found, turn=turn: [event.agent for event in found].count("lead") == turn  # noqa: E731
        await until(lambda: of_type(session, "turn.ended"), session, ended)


async def tool_activity(page: Page, link: str) -> None:
    """Open the lead's page from `link` and press its Tool activity."""
    await page.goto(link.partition("#")[0] + "#person=lead")
    await page.locator(".person .x-acts [data-x-tools]").click()
    await expect(page.locator("#pane h2")).to_have_text("Tool activity of lead", timeout=SECONDS)


async def lines(page: Page) -> list[list[str]]:
    """Each line the pane draws, as its kind and its words, a heading's words alone."""
    return await page.locator(f"{PANE} .x-provenance > *").evaluate_all(
        "els => els.map(el => el.matches('.x-part') ? [el.textContent]"
        " : [...el.children].map(part => part.textContent))"
    )


async def test_an_agent_s_page_lists_its_tool_calls_a_page_at_a_time(
    browser: Browser, root: Path, monkeypatch: pytest.MonkeyPatch
):
    """Whole turns, newest first, as many as a page's calls take, and Read on draws the turns before them below them,
    on a view link too. A line follows into its event's provenance, and Back comes back."""
    monkeypatch.setattr(calls, "PAGE", 4)
    async with Session.start(team(*[[Do(told)]] * 3), name="s", root=root, cwd=root) as session:
        await turned(session, 3)
        async with serving("s", root) as web:
            page, errors = await opened(browser, web.link("view"))
            await tool_activity(page, web.link("view"))

            headings = page.locator(f"{PANE} .x-part")
            await expect(headings).to_have_text([re.compile(r"^turn t3-\w+: stopped$"), re.compile(r"^turn t2-")])
            first = await lines(page)
            more = page.locator(f"{PANE} [data-x-more]")
            await more.click()
            await expect(headings).to_have_count(3, timeout=SECONDS)
            await expect(more).to_have_count(0)
            await expect(page.locator(f"{PANE} .x-provenance > button").nth(4)).to_be_focused()
            drawn = await lines(page)

            call = page.locator(f"{PANE} [data-x-follow]").first
            ref = await call.get_attribute("data-x-follow")
            await call.click()
            await expect(page.locator("#pane h2")).to_have_text(f"Provenance of {ref}", timeout=SECONDS)
            await page.go_back()
            await expect(page.locator("#pane h2")).to_have_text("Tool activity of lead", timeout=SECONDS)
            await expect(headings).to_have_count(2, timeout=SECONDS)
            await page.context.close()

    assert first[1:3] == [["completed", "message_send called"]] * 2 and len(first) == 6
    assert drawn[:6] == first and drawn[6][0].startswith("turn t1-") and len(drawn) == 9
    assert ref is not None and ref.startswith("turn/lead@")
    assert errors == []


async def test_a_spawn_is_listed_under_the_call_whose_id_its_anchor_holds_or_says_it_joins_none(
    browser: Browser, root: Path
):
    """A child spawned under a call's id stands under that call, and one spawned under no id, as a scripted `Call` step
    makes one, stands where the journal has it, saying it joins no known call. Following a spawn opens its provenance
    and the chat that shows its goal."""
    unanchored = Call("agent_spawn", {"name": "w2", "child_role": "worker", "goal": "be w2"})
    async with Session.start(team([Do(spawning), unanchored]), name="s", root=root, cwd=root) as session:
        await turned(session, 1)
        async with serving("s", root) as web:
            page, errors = await opened(browser, web.link("control"))
            await tool_activity(page, web.link("control"))
            await expect(page.locator(f"{PANE} .x-part")).to_have_count(1, timeout=SECONDS)
            drawn = await lines(page)

            await page.locator(f"{PANE} [data-x-follow]", has_text="↳ w1 spawned as worker").click()
            await expect(page.locator("#pane h2")).to_have_text("Provenance of agent/w1@1", timeout=SECONDS)
            await expect(page.locator("#main .mhead")).to_contain_text("w1", timeout=SECONDS)
            await page.context.close()

    assert drawn[1:] == [
        ["completed", "agent_spawn completed"],
        ["spawned", f"w2 spawned as worker · {calls.UNJOINED}"],
        ["started", "agent_spawn called"],
        ["completed", "agent_spawn called"],
        ["spawned", "↳ w1 spawned as worker"],
    ]
    assert errors == []


async def beside_its_chat(page: Page) -> None:
    """Open the lead's chat with the person, and its Tool activity in the pane beside it."""
    await chat(page, "lead & you")
    await page.goto(f"{page.url}&tools=lead")
    await expect(page.locator("#pane h2")).to_have_text("Tool activity of lead", timeout=SECONDS)


async def test_live_text_is_drawn_apart_from_messages_and_said_not_yet_in_the_journal(browser: Browser, root: Path):
    """What the lead is saying shows above its calls, under words saying the journal does not hold it yet, and never in
    its chat. Once its turn records what it said, the message is in the chat and the pane holds none of it."""
    words = "I will now run the tests"
    async with Session.start(team([Say(words)]), name="s", root=root, cwd=root) as session:
        await in_state(session, "lead", "idle")
        async with serving("s", root) as web:
            page, errors = await opened(browser, web.link("control"))
            await beside_its_chat(page)
            session._runtime.kernel.push_delta("lead", "I will now run the te")

            text = page.locator(f"{SAYING} pre")
            await expect(text).to_have_text("I will now run the te", timeout=SECONDS)
            await expect(page.locator(f"{SAYING} .x-about")).to_have_text(ABOUT)
            await expect(said(page, "I will now run the te")).to_have_count(0)
            await session.send("@lead", "go")
            await expect(said(page, words)).to_have_count(1, timeout=SECONDS)
            await expect(text).to_have_text("", timeout=SECONDS)
            await expect(text).to_be_hidden()
            await page.context.close()

    assert errors == []


async def test_live_text_goes_with_the_runtime_that_said_it(browser: Browser, root: Path):
    """What the lead was saying when its runtime went is said no more, and the pane says why; the next runtime's text
    stands alone, read once that runtime takes the session up again."""
    async with Session.start(team([Hang()]), name="s", root=root, cwd=root) as owner:
        await in_state(owner, "lead", "idle")
        async with serving("s", root) as web:
            page, errors = await opened(browser, web.link("control"))
            await beside_its_chat(page)
            owner._runtime.kernel.push_delta("lead", "I will now run the te")
            text, about = page.locator(f"{SAYING} pre"), page.locator(f"{SAYING} .x-about")
            await expect(text).to_have_text("I will now run the te", timeout=SECONDS)

            await owner.leave()
            await expect(about).to_have_text(server._GONE, timeout=SECONDS)
            await expect(text).to_have_text("")
            async with Session.resume("s", root=root) as again:
                await in_state(again, "lead", "idle")
                again._runtime.kernel.push_delta("lead", "Resuming where I was.")
                await expect(text).to_have_text("Resuming where I was.", timeout=SECONDS)
                await expect(about).to_have_text(ABOUT)
                await page.context.close()

    assert errors == []
