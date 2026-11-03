"""The terminal UI's budgets, from section 7.9 of tui-expectations.md: event-loop lag at 100 agents with one live
stream, an append at a large history, and resident memory. Short runs on a loaded shared host, so the numbers are
printed and the bounds are the research's own."""

import asyncio
import statistics
import time
from pathlib import Path

import pytest
from textual.app import App, ComposeResult

from platoon_harness import Session, Team
from platoon_harness.kernel import Event
from platoon_harness_cli.tui.app import TerminalUI
from platoon_harness_cli.tui.transcript import WINDOW, Focus, Transcript

from ..unit.runtime.support import in_state, of_type, until
from ..unit.tui.support import drawn, workspace
from .scripts import inside

pytestmark = [pytest.mark.slow, pytest.mark.timeout(180)]

LAG = 0.050
APPEND = 0.060


@pytest.fixture(autouse=True)
def importable(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("PYTHONPATH", str(Path(__file__).parents[2]))
    monkeypatch.setenv("PLATOON_HARNESS_HOME", str(tmp_path))


def resident() -> int:
    """This process's resident memory, in bytes."""
    for line in Path("/proc/self/status").read_text().splitlines():
        if line.startswith("VmRSS:"):
            return int(line.split()[1]) * 1024
    raise AssertionError("no VmRSS")


def p99(values: list[float]) -> float:
    return statistics.quantiles(values, n=100)[98]


async def test_the_event_loop_keeps_up_at_100_agents_with_one_live_stream(tmp_path):
    team = Team.model_validate(
        {
            "roles": {
                "idle": {"harness": inside("saying"), "count": 99},
                "streamer": {"harness": inside("streaming")},
            }
        }
    )
    guest = await Session.start(team, name="s", root=tmp_path, detach=True)
    await in_state(guest, "streamer", "idle")
    app = TerminalUI("s")
    async with app.run_test(size=(120, 40)) as pilot:
        await drawn(pilot, lambda text: "Idle (100)" in text)
        screen = workspace(app)
        await screen.show(Focus.of_agent("streamer"))
        live = screen.live
        assert live is not None
        lags: list[float] = []
        loop = asyncio.get_running_loop()
        streaming = True

        async def probe() -> None:
            while streaming:
                began = loop.time()
                await asyncio.sleep(0.01)
                lags.append(loop.time() - began - 0.01)

        frames, began = live.frames, time.monotonic()
        probing = asyncio.ensure_future(probe())
        await guest.send("@streamer", "tell me a long story")
        await until(lambda: of_type(guest, "turn.ended"), guest)
        streaming = False
        await probing
        spent = time.monotonic() - began
        drawn_frames = live.frames - frames

    await guest.leave()
    print(
        f"lag over {len(lags)} probes in {spent:.1f} s: p50 {statistics.median(lags) * 1000:.1f} ms, "
        f"p99 {p99(lags) * 1000:.1f} ms, max {max(lags) * 1000:.1f} ms; {drawn_frames} frames, "
        f"{drawn_frames / spent:.1f} a second"
    )
    assert drawn_frames <= spent * 15 + 2
    assert p99(lags) < LAG


class One(App[None]):
    """A transcript alone, at a size a person would read it."""

    def compose(self) -> ComposeResult:
        yield Transcript()


def note(seq: int) -> Event:
    envelope = {"agent": None, "turn": None, "context_version": None, "episode": None, "correlation": None}
    return Event(
        **envelope, v=2, seq=seq, stream="channel/notes", version=seq, type="message.sent", actor="human:you",
        topology_rev=0, cause=(), based_on=(), native={}, model=None, wall_time=0.0, gist=f"note {seq}", outcome=None,
        data={"sender": "@you", "body": None, "subject": None},
    )  # fmt: skip


async def test_an_append_at_a_large_history_stays_in_budget_and_memory_stays_bounded():
    app = One()
    async with app.run_test(size=(120, 40)) as pilot:
        transcript = app.query_one(Transcript)
        transcript.focus_on, transcript.through = Focus.of_channel("#notes", "topic"), 0
        before = resident()
        for first in range(1, 100_001, 1000):
            transcript.take([note(seq) for seq in range(first, first + 1000)])
            if first == 1 + WINDOW:
                at_window = resident()
        await pilot.pause()
        held = resident()

        appends = []
        for seq in range(100_001, 100_201):
            began = time.perf_counter()
            transcript.take([note(seq)])
            transcript.draw(transcript.tail)
            for y in range(transcript.size.height):
                transcript.render_line(y)
            appends.append(time.perf_counter() - began)

    print(
        f"{len(transcript.blocks)} lines held of 100,200; append and draw p50 {statistics.median(appends) * 1000:.2f} "
        f"ms, p99 {p99(appends) * 1000:.2f} ms; resident {before / 2**20:.0f} MiB before, "
        f"{at_window / 2**20:.0f} MiB at the window, {held / 2**20:.0f} MiB at 100,000"
    )
    assert len(transcript.blocks) == WINDOW
    assert p99(appends) < APPEND
    assert held - at_window < (at_window - before) / 2, "memory grew past the window"
