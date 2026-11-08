"""A person acting from SwarmChat's page, in a real browser, over a session on scripted harnesses: a message in the
agent's input path once, a reply drawn in the browser and the terminal at once, an approval that takes effect once
whichever client answers first, a reply in a thread, a file as a body, and an agent's and the session's acts, asked
about first where they are marked so."""

import asyncio
import contextlib
import json
import re
import subprocess
from pathlib import Path

import pytest
from playwright.async_api import Browser, Locator, Page, Route, expect

from platoon_harness import Session, Team
from platoon_harness.primitives import delivery
from platoon_harness.primitives.approvals import ASK_LIMIT
from platoon_harness.runtime.control import BODY_LIMIT
from platoon_harness.testing import Ask, Call, Hang, Say
from platoon_harness_cli.ops import CONFIRMED, cut
from platoon_harness_cli.tui.app import TerminalUI
from platoon_harness_cli.tui.transcript import Transcript

from ..integration.scripts import wire
from ..unit.runtime.gitting import commit, git, repository, working
from ..unit.runtime.support import BALLOT, extension, in_state, of_type, scripted, solo, until
from ..unit.tui.support import drawn, workspace
from .support import SECONDS, chat, opened, said, serving

pytestmark = [pytest.mark.e2e, pytest.mark.timeout(120)]

COMPOSER = "#main .x-composer textarea"
PANE = "#pane .x-composer textarea"


@pytest.fixture
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("PLATOON_HARNESS_HOME", str(tmp_path))
    return tmp_path


async def test_a_person_s_message_from_the_browser_enters_a_wire_harness_s_input_once(browser: Browser, root: Path):
    team = Team.model_validate({"roles": {"bob": {"harness": wire("saying")}}})
    async with Session.start(team, name="s", root=root, cwd=root) as session, serving("s", root) as web:
        await in_state(session, "bob", "idle")
        page, errors = await opened(browser, web.link("control"))
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
    assert [(event.agent, event.data["how"]) for event in delivered] == [("bob", "wake"), ("bob", "launch")]
    assert sum("Fix the flaky test" in text for text in told) == 1
    assert errors == []


async def test_the_composer_keeps_shift_enter_lines_and_cuts_a_long_text_as_the_terminal_does(
    browser: Browser, root: Path
):
    long = "every word of a long note " * 20
    async with Session.start(solo([Hang()]), name="s", root=root, cwd=root) as session, serving("s", root) as web:
        await in_state(session, "bob", "idle")
        page, errors = await opened(browser, web.link("control"))
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


async def test_a_file_goes_as_a_message_s_body_its_limit_said_before_it_is_sent(browser: Browser, root: Path):
    notes = ("# Notes\n" + "a line of the notes\n" * 2000).encode()
    async with Session.start(solo([Hang()]), name="s", root=root, cwd=root) as session, serving("s", root) as web:
        await in_state(session, "bob", "idle")
        page, errors = await opened(browser, web.link("control"))
        await chat(page, "bob & you")
        attach = page.locator("#main [data-x-attach]")
        files = page.locator("#main [data-x-file]")

        await expect(attach).to_have_accessible_description(re.compile(r"of at most 12\.6 MB$"))
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
    browser: Browser, root: Path
):
    team = solo([Say("heard the browser")], [Say("heard the terminal")])
    async with Session.start(team, name="s", root=root, cwd=root) as session, serving("s", root) as web:
        await in_state(session, "bob", "idle")
        page, errors = await opened(browser, web.link("control"))
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


@pytest.mark.parametrize("winner", ["tui", "browser"])
async def test_an_approval_answered_from_the_browser_and_the_terminal_at_once_takes_effect_once(
    browser: Browser, root: Path, winner: str
):
    """The loser's answer is held on its way until the winner's is in, so both are under way at once whatever the host's
    load: a press raced against the feed can find its place already gone, and then sends nothing."""
    team = solo([Ask("Ship the fix?"), Say("shipped")])
    async with Session.start(team, name="s", root=root, cwd=root) as session, serving("s", root) as web:
        await asked(session)
        page, errors = await opened(browser, web.link("control"))
        await chat(page, "bob & you")
        await expect(page.locator("[data-x-needs] .badge")).to_have_text("1", timeout=SECONDS)
        allow = page.locator('[data-x-decide="allow"]')
        await expect(allow).to_be_enabled(timeout=SECONDS)
        sent, answered = asyncio.Event(), asyncio.Event()

        async def held(route: Route) -> None:
            if winner == "tui" and json.loads(route.request.post_data or "{}").get("op") == "approval.resolve":
                sent.set()
                await answered.wait()
            await route.continue_()

        await page.route("**/x/command", held)
        app = TerminalUI("s")
        async with app.run_test(size=(120, 30)) as pilot:
            await drawn(pilot, lambda text: "⚠ approval" in text)
            live = workspace(app).live
            assert live is not None
            submit = live.session.submit

            async def slow(op: str, **args):
                if winner == "browser" and op == "approval.resolve":
                    sent.set()
                    await answered.wait()
                return await submit(op, **args)

            live.session.submit = slow
            first, then = (allow.click, lambda: pilot.press("alt+a", *"/yes", "enter"))[:: 1 if winner == "tui" else -1]
            await first()
            await asyncio.wait_for(sent.wait(), SECONDS / 1000)
            await then()

            await until(lambda: of_type(session, "approval.resolved"), session)
            answered.set()
            if winner == "tui":
                await expect(page.locator("#tip")).to_have_text("Already decided by you via tui.", timeout=SECONDS)
            else:
                told = "Already decided, resolved, by human:you via browser"
                await drawn(pilot, lambda _: any(notice.message == told for notice in app._notifications))
            await expect(page.locator(".x-card.x-done")).to_have_text(f"Allowed by you via {winner}", timeout=SECONDS)
            await drawn(pilot, lambda text: all(row["kind"] != "approval" for row in live.attention.values()))
        await expect(page.locator("[data-x-needs] .badge")).to_have_count(0, timeout=SECONDS)
        await until(lambda: of_type(session, "turn.ended"), session)
        resolved = await of_type(session, "approval.resolved")
        refused = [event for event in await of_type(session, "op.refused") if event.outcome.op == "approval.resolve"]
        await page.context.close()

    assert [(event.data["verdict"], event.data["via"]) for event in resolved] == [("allow", winner)]
    assert len(refused) == 1 and refused[0].outcome.refusal.code == "conflict"
    assert errors == []


async def test_an_approval_card_shows_its_whole_ask_as_text_under_the_page_s_policy(browser: Browser, root: Path):
    """Read it whole, on an approval's card, opens what it asks in the pane before anyone answers it: every character
    of it, a line longer than a `blob.get` result holds among them, as text under the page's policy, so markup in it is
    drawn and never made, and the address names it. It answers nothing, and Allow then does."""
    hostile = (
        '<img src=x onerror="window.__pwned=1"> <script>window.__pwned=1</script> [a](javascript:window.__pwned=1)'
    )
    ask = f"Bash\n{hostile} **not bold** " + "x" * 13_000 + " && rm -rf *_old_*"
    async with (
        Session.start(solo([Ask("Run the build?", body=ask), Say("built")]), name="s", root=root, cwd=root) as session,
        serving("s", root) as web,
    ):
        approval = await asked(session)
        page, errors = await opened(browser, web.link("control"))
        await chat(page, "bob & you")
        await page.locator("[data-x-ask]").click()
        await expect(page.locator("#pane h2")).to_have_text("What bob asks", timeout=SECONDS)
        shown = await page.locator("#pane .x-whole").evaluate("el => el.textContent")
        made = await page.evaluate("document.querySelectorAll('#pane img, #pane script, #pane .x-ask a').length")
        address = await page.evaluate("location.hash")
        answered = await of_type(session, "approval.resolved")
        await page.locator('[data-x-decide="allow"]').click()
        await expect(page.locator(".x-card.x-done")).to_have_text("Allowed by you via browser", timeout=SECONDS)
        pwned = await page.evaluate("window.__pwned")
        await page.context.close()

    assert shown == ask
    assert made == 0 and pwned is None
    assert f"ask={approval['id']}" in address
    assert answered == []
    assert errors == []


async def test_a_cut_ask_says_where_it_was_cut(browser: Browser, root: Path):
    """An ask past what the record keeps is drawn as far as it is kept, and below it how many bytes more it asks, which
    Allow allows too, in the words the terminal says."""
    team = solo([Ask("Write the big file?", body="y" * (ASK_LIMIT + 10)), Hang()])
    async with Session.start(team, name="s", root=root, cwd=root) as session, serving("s", root) as web:
        await asked(session)
        page, errors = await opened(browser, web.link("view"))
        await chat(page, "bob & you")
        await page.locator("[data-x-ask]").click()
        below = page.locator("#pane .x-below")
        await expect(below).to_have_text(
            "Cut here: it asks 10 bytes more, which the record does not keep, and Allow allows them too.",
            timeout=SECONDS,
        )
        shown = await page.locator("#pane .x-whole").evaluate("el => el.textContent")
        await page.context.close()

    assert shown == "y" * ASK_LIMIT
    assert errors == []


async def test_needs_you_lists_a_conflict_its_agent_rests_on(browser: Browser, root: Path, monkeypatch):
    """The runtime never resolves a conflict, so one an agent's merge stopped on needs a person, saying on which files,
    to tell its agent or resolve it in your own checkout, never in its worktree, naming its agent once, and offering to
    write to it, which opens `message send`'s form."""
    repo = repository(root / "repo", monkeypatch)
    git("checkout", "-q", "-b", "theirs", cwd=repo)
    commit(repo, "README", "theirs\n")
    git("checkout", "-q", "main", cwd=repo)

    def merged(cwd: Path) -> None:
        commit(cwd, "README", "ours\n")
        with contextlib.suppress(subprocess.CalledProcessError):
            git("merge", "-q", "theirs", cwd=cwd)

    team = Team.model_validate({"roles": {"bob": {"harness": working(merged), "workspace": "worktree"}}})
    async with Session.start(team, name="s", root=root / "home", cwd=repo) as session:
        await in_state(session, "bob", "idle")
        await session.send("@bob", "merge theirs")
        await until(lambda: session.attention(), session)
        async with serving("s", root / "home") as web:
            page, errors = await opened(browser, web.link("control"))
            needs = page.locator("[data-x-needs]")
            await expect(needs.locator(".badge")).to_have_text("1", timeout=SECONDS)
            await needs.click()
            place = page.locator(".x-needs .x-need")
            said = (
                "merge stopped on conflicts in 1 file, README: tell @bob, or resolve it in your own checkout, never in "
                "its workspace, where any commit is recorded as @bob'sWrite to it"
            )
            await expect(place).to_have_text(re.compile(rf"⚠ conflict .*bob: {re.escape(said)}$"), timeout=SECONDS)
            await place.get_by_role("button", name="Write to it").click()
            await expect(page.locator("#pane h2")).to_have_text("message send", timeout=SECONDS)
            await expect(field(page, "--to")).to_have_value("@bob")
            await page.context.close()

    assert errors == []


async def test_needs_you_names_a_daemon_that_keeps_failing(browser: Browser, root: Path, monkeypatch):
    """A courier that fails on every pass hands nothing over, which would look like a quiet session: Needs you says
    which daemon fails and why, with no action, as only a person can find out what broke it."""

    async def broken(kernel) -> float | None:
        raise RuntimeError("no luck")

    async with Session.start(solo([Say("hi")]), name="s", root=root, cwd=root) as session:
        await in_state(session, "bob", "idle")
        monkeypatch.setattr(delivery, "_pass", broken)
        await session.send("@bob", "go")
        await until(lambda: session.attention(), session)
        async with serving("s", root) as web:
            page, errors = await opened(browser, web.link("control"))
            needs = page.locator("[data-x-needs]")
            await expect(needs.locator(".badge")).to_have_text("1", timeout=SECONDS)
            await needs.click()
            place = page.locator(".x-needs .x-need")
            said = (
                "⚠ daemon: courier failed and is restarted with backoff, its traceback in the session folder's "
                "runtime.log, and `session stop` then `session resume` start it anew: RuntimeError: no luck"
            )
            await expect(place).to_have_text(said, timeout=SECONDS)
            await expect(place.get_by_role("button")).to_have_count(0)
            await page.context.close()

    assert errors == []


async def test_needs_you_counts_where_the_person_must_act_and_its_actions_settle_it(browser: Browser, root: Path):
    team = solo([Ask("Ship the fix?"), Say("shipped")])
    async with Session.start(team, name="s", root=root, cwd=root) as session, serving("s", root) as web:
        await asked(session)
        page, errors = await opened(browser, web.link("control"))
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
        await needs.focus()
        await page.keyboard.press("Enter")
        await place.get_by_role("button", name="Allow").click()

        await expect(page.locator("#tip")).to_have_text("Allow: Ship the fix?", timeout=SECONDS)
        await expect(page.locator(".x-card.x-done")).to_have_text("Allowed by you via browser", timeout=SECONDS)
        await expect(needs.locator(".badge")).to_have_count(0, timeout=SECONDS)
        resolved = await of_type(session, "approval.resolved")
        await page.context.close()

    assert [(event.data["verdict"], event.data["via"]) for event in resolved] == [("allow", "browser")]
    assert under > 0
    assert errors == []


async def test_needs_you_settles_a_budget_place_through_the_form(browser: Browser, root: Path):
    """A wake a spent budget refused is a place in Needs you, whose action opens `budget set`'s form in the pane, filled
    in with the scope it fixes and what that was set to, for the person to change, whose Run settles it."""
    limited = Team.model_validate({**solo([Say("done")], [Say("again")]).canonical(), "budget": {"turns": 1}})
    async with Session.start(limited, name="s", root=root, cwd=root) as session:
        await in_state(session, "bob", "idle")
        await session.send("@bob", "go")
        await until(lambda: of_type(session, "turn.ended"), session)
        await session.send("@bob", "more")
        await until(lambda: session.attention(), session)
        async with serving("s", root) as web:
            page, errors = await opened(browser, web.link("control"))
            needs = page.locator("[data-x-needs]")
            await expect(needs.locator(".badge")).to_have_text("1", timeout=SECONDS)
            await needs.click()
            place = page.locator(".x-needs .x-need")
            refused = r"⚠ budget .*bob: wake of bob refused: over_budgetSet the budget$"
            await expect(place).to_have_text(re.compile(refused), timeout=SECONDS)
            await place.get_by_role("button", name="Set the budget").click()
            await expect(page.locator("#pane h2")).to_have_text("budget set", timeout=SECONDS)
            filled = [await field(page, flag).input_value() for flag in ("--scope", "--limits", "--estimate")]
            await fill(page, {"--limits": '{"turns": 5}'})
            await page.locator("#pane [data-x-run]").click()
            await expect(page.locator("#pane .x-said")).to_have_text("budget set: done.", timeout=SECONDS)
            await expect(needs.locator(".badge")).to_have_count(0, timeout=SECONDS)
            set_it = (await of_type(session, "budget.set"))[-1]
            await page.context.close()

    assert filled == ["shared", '{"turns":1}', ""]
    assert (set_it.actor, set_it.data["scope"], set_it.data["limits"]) == ("human:you", "shared", {"turns": 5})
    assert errors == []


async def test_an_approval_answered_from_two_browsers_at_once_takes_effect_once(browser: Browser, root: Path):
    """Each answer is held on its way until both are, so both reach web at once, whatever the host's load."""
    team = solo([Ask("Ship the fix?"), Say("shipped")])
    async with Session.start(team, name="s", root=root, cwd=root) as session, serving("s", root) as web:
        await asked(session)
        pages = [await opened(browser, web.link("control")) for _ in range(2)]
        sent, both = [asyncio.Event() for _ in pages], asyncio.Event()

        def holding(here: asyncio.Event):
            async def held(route: Route) -> None:
                if json.loads(route.request.post_data or "{}").get("op") == "approval.resolve":
                    here.set()
                    await both.wait()
                await route.continue_()

            return held

        for (page, _), here in zip(pages, sent, strict=True):
            await chat(page, "bob & you")
            await expect(page.locator('[data-x-decide="deny"]')).to_be_enabled(timeout=SECONDS)
            await page.route("**/x/command", holding(here))

        for page, _ in pages:
            await page.locator('[data-x-decide="deny"]').click()
        await asyncio.wait_for(asyncio.gather(*(here.wait() for here in sent)), SECONDS / 1000)
        both.set()

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


async def test_a_reply_in_a_thread_cites_the_message_it_answers(browser: Browser, root: Path):
    turn = [Say("a thought aloud"), Call("message_send", {"to": "@you", "gist": "Which branch?"})]
    team = Team.model_validate(
        {"roles": {"bob": {"harness": scripted(turn)}}, "topology": {"edges": {"bob": ["human"]}}}
    )
    async with Session.start(team, name="s", root=root, cwd=root) as session, serving("s", root) as web:
        await in_state(session, "bob", "idle")
        await session.send("@bob", "go")
        page, errors = await opened(browser, web.link("control"))
        await chat(page, "bob & you")
        question = page.locator("#main .msg", has_text="Which branch?")
        await expect(question).to_have_count(1, timeout=SECONDS)
        aloud = page.locator("#main .msg", has_text="a thought aloud").locator("[data-x-reply]")
        await expect(aloud).to_be_disabled()
        await expect(aloud).to_have_accessible_description(re.compile("is no message a reply can cite"))
        provenance = question.locator(".actions button", has_text="Provenance")
        await expect(provenance).to_be_enabled()
        await expect(provenance).to_have_accessible_description(re.compile("^What inbox/you@1 rests on"))

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


async def test_an_agent_s_acts_ask_first_where_marked_and_say_what_came_of_them(browser: Browser, root: Path):
    async with Session.start(lead_and_child(), name="s", root=root, cwd=root) as session, serving("s", root) as web:
        await in_state(session, "lead", "idle")
        await session.send("@lead", "go")
        await until(session.agents, session, lambda agents: len(agents) == 2)
        await in_state(session, "w", "running")
        page, errors = await opened(browser, web.link("control"))
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
        answered = asyncio.Event()

        async def held(route: Route) -> None:
            await answered.wait()
            await route.continue_()

        await page.route("**/x/link", held)
        link = page.locator('[data-x-link="view"]')
        await link.click()
        await expect(link).to_be_disabled()
        await expect(link).to_have_accessible_description("Sent, and waiting for its answer.")
        answered.set()
        await expect(said_here).to_have_text(re.compile(r"^A view link, which opens once, within ten minutes: "))
        await expect(link).to_be_enabled()
        await expect(link).to_have_accessible_description("")
        await page.unroute("**/x/link", held)
        made = (await said_here.text_content() or "").rpartition(" ")[2]
        served = f"http://127.0.0.1:{web.port}/view#link="
        viewer, viewer_errors = await opened(browser, made)
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


def acting() -> Team:
    """`lead`, which may start a `worker` and works on, and a queue `jobs` and a board `notes` anyone may use."""
    roles = {
        "lead": {"harness": scripted([Hang()]), "may_spawn": ["worker"]},
        "worker": {"harness": scripted([Hang()]), "count": 0},
    }
    channels = {
        "jobs": {"kind": "queue", "writers": "all", "readers": "all"},
        "notes": {"kind": "board", "writers": "all", "readers": "all"},
    }
    topology = {"edges": {"lead": ["children", "human"], "worker": ["parent"]}, "channels": channels}
    return Team.model_validate({"roles": roles, "topology": {**topology, "limits": {"max_depth": 2}}})


async def form(page: Page, title: str) -> None:
    """Open an op's form from Commands, choosing it by its title, and wait for it in the pane."""
    await page.locator("[data-x-commands]").click()
    await page.locator(".palette .it", has=page.locator(".t", has_text=re.compile(rf"^{re.escape(title)}$"))).click()
    await expect(page.locator("#pane h2")).to_have_text(title, timeout=SECONDS)


def field(page: Page, flag: str) -> Locator:
    """A field of the form in the pane, by its flag."""
    return page.locator("#pane .x-form").get_by_label(re.compile(rf"^{re.escape(flag)}( \(needed\))?$"))


async def fill(page: Page, values: dict[str, str]) -> None:
    """Fill the form in the pane, a value per flag, a choice by the words it shows."""
    for flag, value in values.items():
        control = field(page, flag)
        if await control.evaluate("el => el.tagName") == "SELECT":
            await control.select_option(label=value)
        else:
            await control.fill(value)


async def test_the_page_runs_every_write_op_the_person_holds_through_one_form(browser: Browser, root: Path):
    """Commands lists a form for each op the person holds that writes, and each goes to the session through its form,
    under the page's key, answered done or refused, and said under it. An op that ends an agent or the session, erases
    a body or runs a commit's code is asked about once first."""
    async with Session.start(acting(), name="s", root=root, cwd=root) as session, serving("s", root) as web:
        await in_state(session, "lead", "idle")
        erased = (await session.put_body(b"something to erase")).removeprefix("sha256:")
        runs = {
            "channel.create": {"--name": "ideas", "--kind": "topic"},
            "message.send": {"--to": "@lead", "--gist": "from the form", "--body": "The whole of it."},
            "board.post": {
                "--board": "notes",
                "--name": "spec",
                "--gist": "the spec",
                "--body": "Step one.",
                "--fields": '{"owner": "you"}',
            },
            "board.revise": {
                "--board": "notes",
                "--name": "spec",
                "--gist": "the spec, revised",
                "--expected-version": "1",
            },
            "task.add": {"--queue": "jobs", "--gist": "fix the flaky test", "--body": "It fails one run in ten."},
            "task.claim": {"--queue": "jobs"},
            "task.renew": {"--queue": "jobs"},
            "task.complete": {"--queue": "jobs", "--gist": "fixed"},
            "task.fail": {"--queue": "jobs"},
            "task.release": {"--queue": "jobs"},
            "episode.open": {"--episode": "first"},
            "episode.close": {},
            "budget.set": {"--limits": '{"turns": 50}'},
            "approval.resolve": {"--id": "nothing", "--verdict": "allow", "--expected-version": "1"},
            "effect.settle": {"--id": "1", "--happened": "yes"},
            "body.tombstone": {"--sha256": erased},
            "agent.spawn": {"--name": "w9", "--child-role": "worker", "--goal": "take work", "--stays": "no"},
            "agent.interrupt": {"--agent": "@lead", "--below": "yes"},
            "agent.takeover": {"--agent": "@lead"},
            "agent.release": {"--agent": "@lead"},
            "agent.cancel": {"--agent": "@w9"},
            "repo.test": {"--commit": "0" * 40},
            "repo.diff": {"--of": "0" * 40},
            "agent.retire": {"--agent": "@lead"},
            "session.close": {"--if-done": "yes"},
            "session.cancel": {},
        }
        page, errors = await opened(browser, web.link("control"))
        offered = await page.evaluate("X.caps.forms.map(form => form.op)")
        answers = {}
        for op, values in runs.items():
            title = op.replace(".", " ")
            await form(page, title)
            await fill(page, values)
            await page.locator("#pane [data-x-run]").click()
            if op in CONFIRMED:
                await expect(page.locator(".x-ask .ph")).to_have_text(re.compile(r"\? It cannot be taken back\.$"))
                await page.locator(".x-ask [data-x-yes]").click()
            said = page.locator("#pane .x-said")
            await expect(said).to_have_text(re.compile(rf"^{re.escape(title)}: "), timeout=SECONDS)
            answers[op] = await said.text_content()
        keyed = [event.outcome async for event in session.events() if event.outcome is not None]
        sent = [event for event in await of_type(session, "message.sent") if event.gist == "from the form"]
        body = await session.get_body(sent[0].data["body"])
        await page.context.close()

    assert sorted(offered) == sorted(runs)
    assert sorted({outcome.op for outcome in keyed if (outcome.key or "").startswith("web/")}) == sorted(runs)
    refused = {op for op, answer in answers.items() if not answer.startswith(f"{op.replace('.', ' ')}: done.")}
    assert refused == {"task.fail", "task.release", "approval.resolve", "effect.settle", "repo.test", "repo.diff"}
    assert len(sent) == 1 and body == b"The whole of it."
    assert answers["task.fail"] == "task fail: stale_fence: you hold no live lease on jobs"
    assert answers["board.post"] == 'board post: done. {"ref":"board/notes/spec@1","version":1}'
    assert errors == []


async def test_an_op_that_ends_an_agent_or_erases_a_body_is_asked_about_once_in_the_page(browser: Browser, root: Path):
    """Run asks once, beside it, before an op the terminal asks about, saying the op and what was given it. Kept, it
    sends nothing and the form keeps what was typed; taken, the op runs once. An op the terminal does not ask about
    runs at once."""
    async with Session.start(acting(), name="s", root=root, cwd=root) as session, serving("s", root) as web:
        await in_state(session, "lead", "idle")
        erased = (await session.put_body(b"something to erase")).removeprefix("sha256:")
        page, errors = await opened(browser, web.link("control"))
        run, asked, said = page.locator("#pane [data-x-run]"), page.locator(".x-ask .ph"), page.locator("#pane .x-said")

        await form(page, "body tombstone")
        await fill(page, {"--sha256": erased})
        await run.click()
        await expect(asked).to_have_text(f"body tombstone {erased}? It cannot be taken back.")
        await page.locator(".x-ask [data-x-no]").click()
        await expect(asked).to_have_count(0)
        await expect(run).to_be_focused()
        await expect(field(page, "--sha256")).to_have_value(erased)
        kept = await of_type(session, "body.tombstoned")
        await run.click()
        await page.locator(".x-ask [data-x-yes]").click()
        await expect(said).to_have_text("body tombstone: done.", timeout=SECONDS)
        await form(page, "agent retire")
        await fill(page, {"--agent": "@lead"})
        await run.click()
        await expect(asked).to_have_text("agent retire @lead? It cannot be taken back.")
        await page.locator(".x-ask [data-x-yes]").click()
        await expect(said).to_have_text("agent retire: done.", timeout=SECONDS)
        await form(page, "message send")
        await fill(page, {"--to": "#jobs", "--gist": "not asked"})
        await run.click()
        await expect(said).to_have_text(re.compile(r"^message send: "), timeout=SECONDS)
        tombstoned = await of_type(session, "body.tombstoned")
        ended = await of_type(session, "agent.ended")
        await page.context.close()

    assert kept == [] and [event.data["sha256"] for event in tombstoned] == [erased]
    assert [(event.agent, event.data["status"]) for event in ended] == [("lead", "retired")]
    assert errors == []


async def test_a_json_field_takes_only_json_and_shows_it_as_text(browser: Browser, root: Path):
    """A JSON field takes JSON alone: anything else is refused before it is sent, saying why, with focus on the field.
    What it holds and what the op answered are shown as text, markup and all, and what was sent is the JSON's value."""
    hostile = '{"owner": "<img src=x onerror=window.__pwned=1>"}'
    async with Session.start(acting(), name="s", root=root, cwd=root) as session, serving("s", root) as web:
        await in_state(session, "lead", "idle")
        page, errors = await opened(browser, web.link("control"))
        said, fields = page.locator("#pane .x-said"), field(page, "--fields")
        await form(page, "board post")
        await fill(page, {"--board": "notes", "--name": "spec", "--gist": "the spec", "--fields": "{owner: you}"})
        head = await session.head()

        await page.locator("#pane [data-x-run]").click()
        await expect(said).to_have_text(re.compile(r"^--fields takes JSON: \S"))
        await expect(fields).to_be_focused()
        assert await session.head() == head
        await fields.fill(hostile)
        await page.locator("#pane [data-x-run]").click()
        await expect(said).to_have_text('board post: done. {"ref":"board/notes/spec@1","version":1}', timeout=SECONDS)
        await expect(fields).to_have_value(hostile)
        posted = await of_type(session, "board.posted")
        pwned = await page.evaluate("window.__pwned")
        images = await page.locator("#pane img").count()
        await page.context.close()

    assert [event.data["fields"] for event in posted] == [{"owner": "<img src=x onerror=window.__pwned=1>"}]
    assert pwned is None and images == 0
    assert errors == []


async def test_the_page_runs_an_extension_s_op_through_its_form_and_never_asks_about_it(browser: Browser, root: Path):
    """An op a team's extension adds is among Commands, worded by its own description, and runs through its form with
    no question, as what is asked about first is the command line's list."""
    team = acting().model_copy(update={"extensions": (extension(BALLOT),)})
    async with Session.start(team, name="s", root=root, cwd=root) as session, serving("s", root) as web:
        await in_state(session, "lead", "idle")
        page, errors = await opened(browser, web.link("control"))
        await form(page, "ballot cast")
        await expect(page.locator("#pane .x-about")).to_have_text(
            "Cast a vote on an agent's work, kept among that agent's own events."
        )
        await fill(page, {"--agent": "@lead", "--choice": "yes"})
        await page.locator("#pane [data-x-run]").click()
        await expect(page.locator("#pane .x-said")).to_have_text('ballot cast: done. {"choice":"yes"}', timeout=SECONDS)
        asked = await page.locator(".x-ask").count()
        voted = await of_type(session, "ballot.voted")
        await page.context.close()

    assert asked == 0
    assert [(event.actor, event.data) for event in voted] == [("human:you", {"agent": "@lead", "choice": "yes"})]
    assert errors == []
