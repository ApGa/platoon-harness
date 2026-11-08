"""The mixed-team example in a real browser with the terminal UI attached at once, on its real `pi` and OpenHands
against FakeModel, which plays each agent: the job sent from the page, the lead's answer drawn in both, and the
browser's Provenance pane naming everyone the record ties to that answer. The session is then recorded, as a live run
records one, and the page's images are drawn from the recording, which nothing keeps, as no real model made it."""

import os
import shutil
import socket
from pathlib import Path

import pytest
from playwright.async_api import Browser, expect

from platoon_harness import Session, load_team
from platoon_harness.testing import FakeModel
from platoon_harness_cli.tui.app import TerminalUI

from ..integration import plays
from ..integration.cli import ROOT, shown
from ..integration.plays import MODEL, OFFLINE, cast, copied, provider
from ..recorded import IMAGES, record, restored
from ..unit.runtime.support import in_state, of_type, until
from ..unit.tui.support import drawn
from .support import SECONDS, chat, opened, serving
from .test_page_images import page_images

pytestmark = [pytest.mark.e2e, pytest.mark.timeout(300)]

EXAMPLE = ROOT / "examples" / "mixed-team"
SETS = [f'roles.lead.model = "{MODEL}"', f'roles.worker.model = "{MODEL}"', OFFLINE]
"""What the page's `--set` lines say on FakeModel."""


async def test_the_mixed_team_runs_from_the_page_with_the_terminal_attached_and_shows_who_contributed(
    browser: Browser, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    if shutil.which("pi") is None:
        pytest.skip("pi is not installed, so the page met no real pi here")
    root = tmp_path / "state"
    monkeypatch.setenv("PLATOON_HARNESS_HOME", str(root))
    job = (EXAMPLE / "job.md").read_text().strip()

    async with FakeModel() as model:
        cast(model, **plays.MIXED)
        env = provider(model, tmp_path / "home")
        copy = copied(shown(EXAMPLE / "README.md", where="cp -r"), tmp_path, {**os.environ, **env})
        for name, value in env.items():
            monkeypatch.setenv(name, value)
        team = load_team(EXAMPLE / "team.toml", sets=SETS, trust_project=True)
        async with (
            Session.start(team, name="tally", root=root, cwd=copy) as session,
            serving("tally", root) as web,
        ):
            await in_state(session, "lead", "idle")
            page, errors = await opened(browser, web.link("control"))
            app = TerminalUI("tally")
            async with app.run_test(size=(140, 40)) as pilot:
                await drawn(pilot, lambda text: "@lead" in text)
                await chat(page, "lead & you")
                await page.locator("#main .x-composer textarea").fill(job)
                await page.keyboard.press("Enter")

                await until(lambda: of_type(session, "agent.ended"), session, lambda found: len(found) == 2)
                finished = next(event for event in await of_type(session, "agent.finished") if event.agent == "lead")
                answer = finished.data["gist"]
                await expect(page.locator("#main .sys", has_text=answer)).to_have_count(1, timeout=SECONDS)
                await drawn(pilot, lambda text: answer[:40] in " ".join(text.split()))
            cited = f"{finished.stream}@{finished.version}"
            await page.goto(web.link("control").partition("#")[0] + f"#provenance={cited}")

            pane = page.locator("#pane .x-provenance")
            await expect(page.locator("#pane h2")).to_have_text(f"Provenance of {cited}", timeout=SECONDS)
            await expect(pane).to_contain_text(f"{plays.NOTE} by @fixer")
            await expect(pane).to_contain_text("@fixer: declared")
            await expect(pane).to_contain_text("@you: declared")
            await page.context.close()
            sent = [event.gist for event in await of_type(session, "message.sent") if event.actor == "human:you"]

    private = {str(tmp_path): "/path/to/run", str(ROOT): "/path/to/platoon-harness", socket.gethostname(): "host"}
    record(root / "sessions" / "tally", tmp_path / "recorded", private)
    again = tmp_path / "again"
    monkeypatch.setenv("PLATOON_HARNESS_HOME", str(again))
    drawn_images = await page_images(browser, again, restored(tmp_path / "recorded", again), cited, tmp_path / "images")

    assert sent == [job]
    assert errors == []
    assert [path.name for path in drawn_images if path.stat().st_size] == list(IMAGES)
