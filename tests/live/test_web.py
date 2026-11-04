"""SwarmChat's page on real models and native logins, in a real browser, with the terminal UI attached at once: a Claude
Code lead and a Codex worker. Set `PLATOON_HARNESS_LIVE=1` to run it, and say what ran.

Budget: at most 20 model calls in all, counted from the journal, `claude-haiku-5-5` and `gpt-6-luna` at low effort,
under a `turns` limit and a wall limit, so a runaway stops itself.
"""

import asyncio
import json
import os
import shutil
from pathlib import Path

import pytest
from playwright.async_api import async_playwright, expect

from platoon_harness import Session, Team
from platoon_harness.kernel import GIST_LIMIT
from platoon_harness_cli.tui.app import TerminalUI

from ..e2e.support import chat, opened, serving
from ..unit.runtime.support import journal
from ..unit.tui.support import drawn
from .support import CLAUDE, CODEX, EFFORT, seeded, spent

pytestmark = [
    pytest.mark.live,
    pytest.mark.timeout(900),
    pytest.mark.skipif(os.environ.get("PLATOON_HARNESS_LIVE") != "1", reason="needs PLATOON_HARNESS_LIVE=1"),
    pytest.mark.skipif(not (shutil.which("claude") and shutil.which("codex")), reason="needs claude and codex"),
]

WITHIN = 240.0
TEAM = {
    "roles": {
        "lead": {"harness": "claude", "model": CLAUDE, "effort": EFFORT, "approvals": "deny", "may_spawn": ["worker"]},
        "worker": {"harness": "codex", "model": CODEX, "effort": EFFORT, "approvals": "ask", "sandbox": "read-only"},
    },
    "topology": {"manager-worker": {"manager": "lead", "workers": "worker"}},
    "budget": {"turns": 8, "wall": "10m"},
}
JOB = (
    "Spawn one worker named w with this task: your sandbox is read-only, so run `echo hello > out.txt` yourself with "
    "escalated permissions, which waits for a person to approve it, then reply with a two-sentence story about a "
    "lighthouse keeper. Then wait for w's answer, and finish."
)


async def test_a_person_runs_a_team_from_the_browser_with_the_terminal_attached_at_once(tmp_path, monkeypatch):
    """Budget: at most 20 model calls, counted from the journal. The job sent from the browser's composer to the
    lead, the worker's escalation allowed on its card in the browser, and the lead's answer, its finish report, drawn in
    the browser and in the terminal UI attached at once. Each act is in the journal once."""
    assert len(JOB) <= GIST_LIMIT, "the job must go as one gist, which the checks below compare, before any cost"
    root = tmp_path / "root"
    monkeypatch.setenv("PLATOON_HARNESS_HOME", str(root))
    work = seeded(tmp_path / "work")
    team = Team.model_validate(TEAM)

    async with (
        Session.start(team, name="live-web", root=root, cwd=work, plan_login=True) as session,
        serving("live-web", root) as web,
        async_playwright() as playwright,
    ):
        chromium = await playwright.chromium.launch()
        page, errors = await opened(chromium, web.link("control"))
        app = TerminalUI("live-web")
        async with app.run_test(size=(140, 40)) as pilot:
            await drawn(pilot, lambda text: "@lead" in text and " live " in text, within=WITHIN)
            await chat(page, "lead & you")
            await page.locator("#main .x-composer textarea").fill(JOB)
            await page.keyboard.press("Enter")

            await expect(page.locator("[data-x-needs] .badge")).to_have_text("1", timeout=WITHIN * 1000)
            await chat(page, "w & you")
            await page.locator('[data-x-decide="allow"]').click()
            await expect(page.locator(".x-card.x-done")).to_have_text("Allowed by you via browser", timeout=60_000)

            async with asyncio.timeout(WITHIN):
                async for event in session.events(follow=True):
                    if event.type == "agent.ended" and event.agent == "lead":
                        break
            answer = " ".join(event.gist.split())
            print("the lead's answer:", answer, flush=True)
            await chat(page, "lead & you")
            await expect(page.locator("#main .sys", has_text=answer[:60])).to_have_count(1, timeout=60_000)
            await drawn(pilot, lambda text: answer[:40] in " ".join(text.split()), within=60)
        await chromium.close()
        ending = await session.settled(timeout="5m")
        events = await journal(session)
        used = await spent(session)
    keep = Path(os.environ.get("PLATOON_HARNESS_KEEP", tmp_path / "kept"))
    keep.mkdir(parents=True, exist_ok=True)
    for kept in ("journal.sqlite", "manifest.json"):
        shutil.copy(root / "sessions" / "live-web" / kept, keep / kept)

    sent = [event.gist for event in events if event.type == "message.sent" and event.actor == "human:you"]
    resolved = [event.data for event in events if event.type == "approval.resolved"]
    print(json.dumps({"ending": ending.reason, "spent": used}, indent=1), flush=True)

    assert sent == [JOB]
    assert len(resolved) == 1 and (resolved[0]["verdict"], resolved[0]["via"]) == ("allow", "browser")
    assert used["total"] <= 20
    assert errors == []
