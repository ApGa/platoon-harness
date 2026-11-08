"""The path the docs' images take from a live run, on a session of the mixed team on its real `pi` and OpenHands
against FakeModel, which nothing keeps, as no real model made it: recorded as the live run records one, it holds no
local path, host, account or key, and made again under a root of its own it reads back as it ran, in the terminal UI
too."""

import os
import shutil
import socket
from pathlib import Path

import pytest

from platoon_harness import Session, load_team
from platoon_harness.testing import FakeModel
from platoon_harness_cli.tui.app import TerminalUI

from ..recorded import finish_of, record, restored
from ..unit.tui.support import drawn
from . import plays
from .cli import ROOT, shown
from .plays import MODEL, OFFLINE, cast, copied, provider

pytestmark = [pytest.mark.slow, pytest.mark.timeout(400)]

EXAMPLE = ROOT / "examples" / "mixed-team"


async def test_a_recorded_example_holds_nothing_private_and_reads_back_as_it_ran(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    if shutil.which("pi") is None:
        pytest.skip("pi is not installed, so the example met no real pi here")
    root = tmp_path / "state"
    async with FakeModel() as model:
        cast(model, **plays.MIXED)
        env = provider(model, tmp_path / "home")
        copy = copied(shown(EXAMPLE / "README.md", where="cp -r"), tmp_path, {**os.environ, **env})
        for name, value in env.items():
            monkeypatch.setenv(name, value)
        sets = [f'roles.lead.model = "{MODEL}"', f'roles.worker.model = "{MODEL}"', OFFLINE]
        team = load_team(EXAMPLE / "team.toml", sets=sets, trust_project=True)
        async with Session.start(team, name="tally", root=root, cwd=copy) as session:
            await session.send("@lead", (EXAMPLE / "job.md").read_text().strip())
            await session.settled(timeout="4m")
    async with Session.attach("tally", root=root) as closed:
        ran = [event async for event in closed.events()]
    private = {
        str(copy): "/path/to/tally",
        str(tmp_path): "/path/to/run",
        str(ROOT): "/path/to/platoon-harness",
        str(Path.home()): "/path/to/home",
        socket.gethostname(): "host",
        "dummy-key": "<key>",
    }

    record(root / "sessions" / "tally", tmp_path / "recorded", private)
    monkeypatch.setenv("PLATOON_HARNESS_HOME", str(tmp_path / "again"))
    name = restored(tmp_path / "recorded", tmp_path / "again")
    async with Session.attach(name) as again:
        read = [event async for event in again.events()]
    app = TerminalUI(name)
    async with app.run_test(size=(140, 40)) as pilot:
        answer = finish_of(tmp_path / "recorded", "lead")["data"]["gist"]
        await drawn(pilot, lambda text: "@fixer" in text and answer[:40] in " ".join(text.split()))

    assert [(event.seq, event.type, event.stream) for event in read] == [
        (event.seq, event.type, event.stream) for event in ran
    ]
    assert answer == plays.SUMMARY
    recorded = "".join(path.read_text() for path in (tmp_path / "recorded").iterdir())
    assert "/path/to/tally" in recorded and str(tmp_path) not in recorded
