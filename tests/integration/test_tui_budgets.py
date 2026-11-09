"""The terminal UI's budgets, from section 7.9 of tui-expectations.md: event-loop lag at 100 agents with one live
stream, an append at a large history, and resident memory. Short runs on a loaded shared host, so the numbers are
printed and the bounds are the research's own. Opening and closing a line at a full window is held to the append's,
every fold at once to the event loop's lag, and the motion of a live session at rest to a small share of a core, which
is ours. And an attach to the journal of the Scale case, held to a budget twice what docs/reference/scale.md
publishes."""

import asyncio
import gc
import statistics
import time
from pathlib import Path

import pytest
from textual.app import App, ComposeResult

from platoon_harness import Session, Team
from platoon_harness.kernel import Event
from platoon_harness_cli.tui.app import TerminalUI
from platoon_harness_cli.tui.motion import FPS
from platoon_harness_cli.tui.transcript import WINDOW, Focus, Transcript
from platoon_harness_cli.tui.workspace import Navigator

from ..unit.runtime.support import in_state, of_type, until
from ..unit.tui.support import drawn, workspace
from . import scale
from .scripts import MEMBERS, inside

pytestmark = pytest.mark.timeout(180)

LAG = 0.050
APPEND = 0.060
IDLE = 0.02
"""The most of a core a live session at rest may take to move its agents: two percent, ours."""
ATTACH = 0.86
"""The longest an attach may take to draw a session of 100,000 events, the roster and the first agent's transcript:
twice the most docs/reference/scale.md says was measured."""


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


@pytest.mark.slow
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
        await drawn(pilot, lambda text: "idle  100" in text)
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


@pytest.mark.slow
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
        transcript.draw(transcript.tail)  # The first draw at this history lays it out once, as opening it does.
        for y in range(transcript.size.height):
            transcript.render_line(y)

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


def step(seq: int, turn: int, gist: str, data: dict) -> Event:
    envelope = {"agent": "lead", "context_version": None, "episode": None, "correlation": None}
    return Event(
        **envelope, v=2, seq=seq, stream="turn/lead", version=seq, type="item.recorded", actor="agent:lead",
        turn=f"t{turn}", topology_rev=0, cause=(), based_on=(), native={}, model=None, wall_time=0.0, gist=gist,
        outcome=None, data=data,
    )  # fmt: skip


def turns(count: int) -> list[Event]:
    """`count` turns of the lead's, each a rule, four calls, two thoughts and what it said: eight lines, six of them in
    its fold."""
    events, seq = [], 0
    for turn in range(count):
        said = [("turn", None), *((f'read {{"path": "f{n}.py"}}', "tool") for n in range(4)), ("think", "thought")]
        for gist, kind in [*said, ("think again", "thought"), (f"turn {turn} is done", "message")]:
            seq += 1
            if kind is None:
                data = {"turn": f"t{turn}"}
                events.append(step(seq, turn, gist, data).model_copy(update={"type": "turn.started"}))
            elif kind == "tool":
                ended = {"kind": kind, "phase": "completed", "native_id": f"c{seq}", "outcome": "completed"}
                events.append(step(seq, turn, gist, ended))
            else:
                events.append(step(seq, turn, gist, {"kind": kind}))
    return events


@pytest.mark.slow
async def test_opening_and_closing_a_line_at_a_full_window_stays_in_budget():
    """At a window of 10,000 lines of an agent's turns, each turn folded, opening and closing a fold, a thought in it,
    and every fold of the focus at once, each laid out and drawn: a fold or a line within the append's budget, as each
    lays out its own lines alone, and every fold at once, which lays out the window, within the event loop's lag budget,
    as one act. Each kind is measured from a heap the collector has just swept, so none pays for the garbage of the one
    before."""
    app = One()
    async with app.run_test(size=(120, 40)) as pilot:
        transcript = app.query_one(Transcript)
        transcript.focus_on, transcript.through = Focus.of_agent("lead"), 0
        events = turns(1300)
        for first in range(0, len(events), 1000):
            transcript.take(events[first : first + 1000])
        await pilot.pause()
        transcript.draw(transcript.tail)  # Laid out at the width its scrollbar leaves, as a person first sees it.
        folds = list(transcript._folds.values())

        def drawn() -> None:
            for y in range(transcript.size.height):
                transcript.render_line(y)

        toggles = []
        gc.collect()  # So the garbage of taking the window lands on none of what is measured.
        for fold in [*folds[:: max(len(folds) // 250, 1)], folds[-1]]:
            for _ in range(2):
                began = time.perf_counter()
                transcript.toggle(fold)
                drawn()
                toggles.append(time.perf_counter() - began)
            began = time.perf_counter()
            transcript.toggle(fold)
            transcript.toggle(fold.steps[4])
            drawn()
            toggles.append(time.perf_counter() - began)
            transcript.toggle(fold.steps[4])
            transcript.toggle(fold)
        every = []
        gc.collect()  # And the garbage of the toggles on none of every fold's.
        for _ in range(4):
            began = time.perf_counter()
            transcript.unfold()
            drawn()
            every.append(time.perf_counter() - began)
        held = len(transcript.blocks)

    print(
        f"{held} lines held in {len(folds)} folds; a fold or a line opened or closed p50 "
        f"{statistics.median(toggles) * 1000:.2f} ms, p99 {p99(toggles) * 1000:.2f} ms; every fold at once "
        f"{max(every) * 1000:.1f} ms at most"
    )
    assert held == WINDOW
    assert p99(toggles) < APPEND
    assert max(every) < LAG


@pytest.mark.slow
async def test_an_animated_live_session_at_rest_costs_a_little_each_frame_and_draws_only_what_moves(tmp_path):
    """A live session of 20 agents, every one resting: the logo blinks now and then and each agent's ring breathes, at
    four frames a second. A minute of frames, stepped by hand: each frame's cost, its own and the drawing it asks for,
    and the rows it draws again, which are only those whose frame changed."""
    team = Team.model_validate({"roles": {"idle": {"harness": inside("saying"), "count": 20}}})
    guest = await Session.start(team, name="s", root=tmp_path, detach=True)
    app = TerminalUI("s")
    async with app.run_test(size=(120, 60)) as pilot:
        await drawn(pilot, lambda text: "idle  20" in text)
        screen = workspace(app)
        navigator = screen.query_one(Navigator)
        await drawn(pilot, lambda _: navigator.motion.idle == 20 and navigator._ticking is not None)
        navigator._ticking.stop()  # type: ignore[union-attr]
        refreshed: list[int] = []
        refresh = navigator.refresh_lines

        def counted(y: int, count: int = 1) -> None:
            refreshed.append(y)
            refresh(y, count)

        navigator.refresh_lines = counted  # type: ignore[method-assign]
        costs, rows = [], []
        for _ in range(60 * FPS):
            refreshed.clear()
            began = time.process_time()
            navigator.advance()
            await pilot.pause()
            costs.append(time.process_time() - began)
            rows.append(len(refreshed))
        moving = {index for index, row in enumerate(navigator.rows) if row.moves}

    await guest.leave()
    busy = sum(costs) / 60
    print(
        f"a minute of motion at rest: {busy * 100:.2f}% of a core, a frame p50 {statistics.median(costs) * 1000:.2f} "
        f"ms, p99 {p99(costs) * 1000:.2f} ms, max {max(costs) * 1000:.2f} ms; {sum(rows)} rows drawn again in "
        f"{len(rows)} frames, {max(rows)} at most, of {len(moving)} that move"
    )
    assert max(rows) <= len(moving) and sum(1 for count in rows if count) < len(rows) / 2
    assert p99(costs) < LAG and busy < IDLE


@pytest.mark.scale
@pytest.mark.timeout(1800)
async def test_the_tui_attaches_to_a_100000_event_journal_within_its_budget(tmp_path):
    """The Scale case's run, then the terminal UI attached to it, until it draws every member idle and the first one's
    transcript to its last turn."""
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    guest = await Session.start(scale.team(), name="s", root=tmp_path, cwd=cwd, detach=True)
    rounds = await scale.drive(guest)
    app = TerminalUI("s")
    began = time.monotonic()
    async with app.run_test(size=(120, 40)) as pilot:
        last = f"round {len(rounds)} is under way"
        await drawn(pilot, lambda text: f"idle  {MEMBERS}" in text and last in text)
        attached = time.monotonic() - began
    await guest.leave()
    print(f"attached to {rounds[-1].metrics.head} events in {attached:.2f} s")
    assert attached < ATTACH
