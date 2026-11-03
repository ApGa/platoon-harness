"""The terminal UI on real models and native logins, driven by Pilot, on a session it starts from its sessions screen: a
Claude Code lead and a Codex worker. Set `PLATOON_HARNESS_LIVE=1` to run it, and say what ran.

Budget: at most 30 model calls in all, counted from the journal, `claude-haiku-5-5` and `gpt-6-luna` at low effort,
under a `turns` limit and a wall limit, so a runaway stops itself.
"""

import asyncio
import json
import os
import shutil
from pathlib import Path

import pytest

from platoon_harness import Session
from platoon_harness.kernel import GIST_LIMIT
from platoon_harness_cli.sessions import ask_to_stop
from platoon_harness_cli.tui.app import TerminalUI
from platoon_harness_cli.tui.sessions import Sessions
from platoon_harness_cli.tui.transcript import Transcript
from platoon_harness_cli.tui.workspace import Dock

from ..unit.runtime.support import journal
from ..unit.tui.support import drawn, workspace
from .support import CLAUDE, CODEX, EFFORT, seeded, spent

pytestmark = [
    pytest.mark.live,
    pytest.mark.timeout(900),
    pytest.mark.skipif(os.environ.get("PLATOON_HARNESS_LIVE") != "1", reason="needs PLATOON_HARNESS_LIVE=1"),
    pytest.mark.skipif(not (shutil.which("claude") and shutil.which("codex")), reason="needs claude and codex"),
]

WITHIN = 240.0
TEAM = f"""
[roles.lead]
harness = "claude"
model = "{CLAUDE}"
effort = "{EFFORT}"
approvals = "deny"
may_spawn = ["worker"]

[roles.worker]
harness = "codex"
model = "{CODEX}"
effort = "{EFFORT}"
approvals = "ask"
sandbox = "read-only"

[topology.manager-worker]
manager = "lead"
workers = "worker"

[topology.channels.memo]
kind = "topic"
writers = "all"
readers = "role:worker"
delivery = "wake"

[budget]
turns = 8
wall = "10m"
"""
JOB = (
    "Spawn one worker named w with this task: run `echo hello > out.txt` yourself, which waits for a person to "
    "approve it, as expected, then reply with a 1,500-word story about a lighthouse keeper. Then wait for w's answer, "
    "and finish."
)


def chosen(app: TerminalUI) -> dict:
    screen = workspace(app)
    assert screen.live is not None
    return screen.live.attention.get(screen.query_one(Dock).cursor or "", {})


async def test_a_person_runs_a_team_from_the_tui_and_comes_back_to_it(tmp_path, monkeypatch):
    """Budget: at most 30 model calls, counted from the journal. Started from the sessions screen, with the plan login
    asked about once; the job sent from the composer; the worker's approval answered from the dock; its live text seen;
    a memo queued for it, then the worker interrupted mid-turn, the memo staying quiet; then a detach back to the
    sessions screen, an attach from a new app, and the session seen to settle. Each act is in the journal once."""
    assert len(JOB) <= GIST_LIMIT, "the job must go as one gist, which the checks below compare, before any cost"
    monkeypatch.setenv("PLATOON_HARNESS_HOME", str(tmp_path / "root"))
    work = seeded(tmp_path / "work")
    (work / "crew.toml").write_text(TEAM)
    monkeypatch.chdir(work)

    app = TerminalUI()
    async with app.run_test(size=(140, 40)) as pilot:
        await drawn(pilot, lambda text: "No sessions yet" in text)
        await pilot.press("n")
        await pilot.pause()
        await pilot.press(*"crew.toml", "enter", *"live-tui", "enter", "enter")
        await drawn(pilot, lambda text: "your own work?" in text, within=60)
        await pilot.press("y")
        await drawn(pilot, lambda text: "@lead" in text and " live " in text, within=WITHIN)
        name = workspace(app).session_name
        print("session", name, flush=True)

        await pilot.press(*JOB, "enter")
        await drawn(pilot, lambda text: "@w " in text, within=WITHIN)
        screen = workspace(app)
        await screen.show(screen._agent("w"))

        await drawn(pilot, lambda text: "⚠ approval" in text, within=WITHIN)
        for _ in range(len(live_places(app))):
            await pilot.press("alt+a")
            if chosen(app).get("kind") == "approval":
                break
        await pilot.press("alt+y")
        live = screen.live
        assert live is not None
        await drawn(pilot, lambda text: all(row["kind"] != "approval" for row in live.attention.values()), within=60)

        await pilot.press(*"#memo ", *"a memo for later", "enter")
        transcript = screen.query_one(Transcript)
        await drawn(pilot, lambda text: len(transcript._tail_text) > 40, within=WITHIN)
        print("live text seen:", transcript._tail_text[:120].replace("\n", " "), flush=True)
        await pilot.press("escape")
        row = await _quiet(pilot, app)
        print("after the interrupt:", row["state"], "unread", row["unread"], flush=True)

        if row["group"] != "done":
            await pilot.press(*"@w ", *"Finish the story in one sentence, and end your turn.", "enter")
            await drawn(pilot, lambda text: "Finish the story" in text, within=30)
        await pilot.press("ctrl+d")
        await drawn(pilot, lambda text: isinstance(app.screen, Sessions) and name in text, within=30)
        await pilot.press("ctrl+q")

    again = TerminalUI(name)
    async with again.run_test(size=(140, 40)) as pilot:
        header = await drawn(pilot, lambda text: "settled" in text.splitlines()[0], within=WITHIN)
        print("attached again:", header.splitlines()[0].strip(), flush=True)

    async with Session.attach(name) as session:
        events = await journal(session)
        used = await spent(session)
        await ask_to_stop(session)
        async for _ in session.events(await session.head(), follow=True):
            pass
    keep = Path(os.environ.get("PLATOON_HARNESS_KEEP", tmp_path / "kept"))
    keep.mkdir(parents=True, exist_ok=True)
    for kept in ("journal.sqlite", "manifest.json"):
        shutil.copy(tmp_path / "root" / "sessions" / name / kept, keep / kept)

    sent = [event.gist for event in events if event.type == "message.sent" and event.actor == "human:you"]
    resolved = [event.data for event in events if event.type == "approval.resolved"]
    quieted = [event.agent for event in events if event.type == "wake.quieted"]
    interrupted = [event for event in events if event.type == "turn.ended" and event.data["reason"] == "interrupted"]
    after = interrupted[0].seq if interrupted else 0
    woken = [event for event in events if event.type == "turn.started" and event.agent == "w" and event.seq > after]
    print(json.dumps({"sent": sent, "resolved": resolved, "quieted": quieted, "spent": used}, indent=1), flush=True)

    assert sent[:2] == [JOB, "a memo for later"]
    assert len(resolved) == 1 and (resolved[0]["verdict"], resolved[0]["via"]) == ("allow", "tui")
    assert quieted == ["w"] and len(interrupted) == 1
    assert not woken or woken[0].seq > next(event.seq for event in events if event.gist.startswith("Finish the story"))
    assert used["total"] <= 30


def live_places(app: TerminalUI) -> list[dict]:
    screen = workspace(app)
    assert screen.live is not None
    return screen._places(screen.live)


async def _quiet(pilot, app: TerminalUI) -> dict:
    """The worker's row once its interrupted turn has ended: idle, with the memo still waiting for it. A worker that
    ended its turn before the interrupt reached it has ended, which the journal's checks below then say."""
    screen = workspace(app)
    assert screen.live is not None
    async with asyncio.timeout(WITHIN):
        while True:
            row = screen._row("w") or {}
            if row.get("state") == "ended" or (row.get("state") == "idle" and row.get("stopped") == "interrupted"):
                return row
            await drawn(pilot, lambda text: True)
            await screen.live.next_frame(screen.live.frames)
