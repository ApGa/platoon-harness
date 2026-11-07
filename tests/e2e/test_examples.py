"""The mixed-team example in a real browser with the terminal UI attached at once, on the scripted stand-ins of its
`stand_ins.py` swapped in for its harnesses by the settings its README's no-key command gives: the job sent from the
page, the lead's answer drawn in both, and the browser's Provenance pane naming everyone the record ties to that
answer."""

import shlex
from pathlib import Path

import pytest
from playwright.async_api import Browser, expect

from platoon_harness import Session, load_team
from platoon_harness_cli.tui.app import TerminalUI

from ..integration.cli import ROOT, shown
from ..unit.runtime.support import in_state, of_type, until
from ..unit.tui.support import drawn
from .support import SECONDS, chat, opened, serving

pytestmark = [pytest.mark.e2e, pytest.mark.timeout(120)]

EXAMPLE = ROOT / "examples" / "mixed-team"
[NO_KEYS] = shown(EXAMPLE / "README.md", where="stand_ins:lead")
WORDS = shlex.split(NO_KEYS)
STAND_INS = [WORDS[index + 1] for index, word in enumerate(WORDS) if word == "--set"]


async def test_the_mixed_team_runs_from_the_page_with_the_terminal_attached_and_shows_who_contributed(
    browser: Browser, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("PLATOON_HARNESS_HOME", str(tmp_path))
    monkeypatch.syspath_prepend(str(EXAMPLE))
    team = load_team(EXAMPLE / "team.toml", sets=STAND_INS)
    job = (EXAMPLE / "job.md").read_text().strip()

    async with (
        Session.start(team, name="mixed", root=tmp_path, cwd=tmp_path) as session,
        serving("mixed", tmp_path) as web,
    ):
        await in_state(session, "lead", "idle")
        page, errors = await opened(browser, web.link("control"))
        app = TerminalUI("mixed")
        async with app.run_test(size=(140, 40)) as pilot:
            await drawn(pilot, lambda text: "@lead" in text)
            await chat(page, "lead & you")
            await page.locator("#main .x-composer textarea").fill(job)
            await page.keyboard.press("Enter")

            ended = await until(lambda: of_type(session, "agent.ended"), session, lambda found: len(found) == 2)
            answer = next(event for event in ended if event.agent == "lead")
            await expect(page.locator("#main .sys", has_text=answer.gist)).to_have_count(1, timeout=SECONDS)
            await drawn(pilot, lambda text: answer.gist in " ".join(text.split()))
        finished = next(event for event in await of_type(session, "agent.finished") if event.agent == "lead")
        cited = f"{finished.stream}@{finished.version}"
        await page.goto(web.link("control").partition("#")[0] + f"#provenance={cited}")

        pane = page.locator("#pane .x-provenance")
        await expect(page.locator("#pane h2")).to_have_text(f"Provenance of {cited}", timeout=SECONDS)
        await expect(pane).to_contain_text("board/notes/risks@1 by @w")
        await expect(pane).to_contain_text("@w: declared")
        await expect(pane).to_contain_text("@you: declared")
        await page.context.close()
        sent = [event.gist for event in await of_type(session, "message.sent") if event.actor == "human:you"]

    assert sent == [job]
    assert errors == []
