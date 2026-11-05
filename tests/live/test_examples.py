"""The mixed-team example on real models and native logins: its own team file and job, a Claude Code lead and a Codex
worker, the job sent from SwarmChat's page with the terminal UI attached at once, as live run 58 had it. Set
`PLATOON_HARNESS_LIVE=1` to run it, and say what ran.

Budget: at most 15 model calls in all, counted from the journal, `claude-haiku-5-5` and `gpt-6-luna` at low effort,
under the example's `turns` and wall limits, so a runaway stops itself.
"""

import asyncio
import json
import os
import shutil
from pathlib import Path

import pytest
from playwright.async_api import async_playwright, expect

from platoon_harness import Session, load_team
from platoon_harness.kernel import GIST_LIMIT
from platoon_harness_cli.tui.app import TerminalUI

from ..e2e.support import chat, opened, serving
from ..integration.cli import ROOT
from ..unit.runtime.support import journal
from ..unit.tui.support import drawn
from .support import CLAUDE, CODEX, EFFORT, seeded, spent

pytestmark = [
    pytest.mark.live,
    pytest.mark.timeout(900),
    pytest.mark.skipif(os.environ.get("PLATOON_HARNESS_LIVE") != "1", reason="needs PLATOON_HARNESS_LIVE=1"),
    pytest.mark.skipif(not (shutil.which("claude") and shutil.which("codex")), reason="needs claude and codex"),
]

EXAMPLE = ROOT / "examples" / "mixed-team"
WITHIN = 300.0
MODELS = [
    f'roles.lead.model = "{CLAUDE}"',
    f'roles.lead.effort = "{EFFORT}"',
    'roles.lead.approvals = "deny"',
    f'roles.worker.model = "{CODEX}"',
    f'roles.worker.effort = "{EFFORT}"',
    'roles.worker.approvals = "deny"',
    'roles.worker.sandbox = "read-only"',
]


async def test_the_mixed_team_example_runs_from_the_browser_on_real_models_and_says_who_contributed(
    tmp_path, monkeypatch
):
    """Budget: at most 15 model calls, counted from the journal. The example's job sent from the page's composer, a task
    through the queue, a note on the board, the worker's report back by message, and the lead's answer drawn in the page
    and in the terminal UI attached at once; then what the record ties to that answer, which the test prints."""
    job = (EXAMPLE / "job.md").read_text().strip()
    assert len(job) <= GIST_LIMIT, "the job must go as one gist, which the checks below compare, before any cost"
    root = tmp_path / "root"
    monkeypatch.setenv("PLATOON_HARNESS_HOME", str(root))
    work = seeded(tmp_path / "work")
    team = load_team(EXAMPLE / "team.toml", sets=MODELS)

    async with (
        Session.start(team, name="live-mixed", root=root, cwd=work, plan_login=True) as session,
        serving("live-mixed", root) as web,
        async_playwright() as playwright,
    ):
        chromium = await playwright.chromium.launch()
        page, errors = await opened(chromium, web.link("control"))
        app = TerminalUI("live-mixed")
        async with app.run_test(size=(140, 40)) as pilot:
            await drawn(pilot, lambda text: "@lead" in text and " live " in text, within=WITHIN)
            await chat(page, "lead & you")
            await page.locator("#main .x-composer textarea").fill(job)
            await page.keyboard.press("Enter")

            async with asyncio.timeout(WITHIN):
                async for event in session.events(follow=True):
                    if event.type == "agent.ended" and event.agent == "lead":
                        break
            answer = " ".join(event.gist.split())
            print("the lead's answer:", answer, flush=True)
            await expect(page.locator("#main .sys", has_text=answer[:60])).to_have_count(1, timeout=60_000)
            await drawn(pilot, lambda text: answer[:40] in " ".join(text.split()), within=60)
        await chromium.close()
        ending = await session.settled(timeout="5m")
        events = await journal(session)
        used = await spent(session)
        finished = [event for event in events if event.type == "agent.finished" and event.agent == "lead"]
        reached = await session.contributors(f"{finished[0].stream}@{finished[0].version}") if finished else None
    keep = Path(os.environ.get("PLATOON_HARNESS_KEEP", tmp_path / "kept"))
    keep.mkdir(parents=True, exist_ok=True)
    for kept in ("journal.sqlite", "manifest.json"):
        shutil.copy(root / "sessions" / "live-mixed" / kept, keep / kept)

    sent = [event.gist for event in events if event.type == "message.sent" and event.actor == "human:you"]
    tasks = [event.type for event in events if event.stream.startswith("task/tasks/")]
    notes = [f"{event.stream}@{event.version}" for event in events if event.type in ("board.posted", "board.revised")]
    cited = {f"{event.stream}@{event.version}": event.based_on for event in events if event.based_on}
    print(
        json.dumps({"ending": ending.reason, "spent": used, "tasks": tasks, "notes": notes, "cited": cited}), flush=True
    )
    print("contributors:", reached and [(row.maker, row.kinds) for row in reached.rows], flush=True)

    assert sent == [job]
    assert ending.reason == "settled" and finished
    assert "task.completed" in tasks and "board/notes/risks@1" in notes
    assert used["total"] <= 15
    assert errors == []
