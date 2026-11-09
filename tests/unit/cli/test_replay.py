"""A replay as both clients play it: paced by its record at a speed, moved an event or a turn at a time or to an event
or a time, and said in a banner that names it a replay, of which session, where it stands and how it plays."""

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from platoon_harness import Refused, Replay, Session
from platoon_harness.kernel import ManualClock, first
from platoon_harness.testing import Say
from platoon_harness_cli.replay import CONTROLS, IDLE, JUMP, SPEEDS, Player, Record, elapsed, moment, nothing_acts

from ..runtime.support import in_state, of_type, solo, until

pytestmark = pytest.mark.timeout(60)

START = 1_000_000.0
"""When the made-up record begins: its events come ten at a time, each ten more seconds after the last."""


@pytest.fixture(autouse=True)
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("PLATOON_HARNESS_HOME", str(tmp_path))
    return tmp_path


@pytest.fixture
async def replay(root: Path) -> AsyncIterator[Replay]:
    async with Session.start(solo([Say("on it")]), name="s", root=root) as session:
        await in_state(session, "bob", "idle")
        await session.send("@bob", "go")
        await until(lambda: of_type(session, "turn.ended"), session, lambda ended: len(ended) == 1)
    async with Replay.open("s", root=root) as opened:
        yield opened


def made_up(total: int, ends: list[int]) -> Record:
    """A record of `total` events that come ten at a time, ten seconds apart, whose turns end at `ends`."""
    times = [START + 10 * ((seq - 1) // 10) for seq in range(1, total + 1)]
    return Record(times, times, ends)


async def test_a_replay_plays_its_events_at_their_recorded_pace_scaled_by_its_speed(replay):
    """Events within a frame of each other come at once, and the wait before the next is its recorded gap at the speed,
    or at most `IDLE` with idle skipped."""
    for speed, gap in enumerate((10.0, 2.5, 0.625, IDLE)):
        clock = ManualClock(0.0)
        player = Player(replay, made_up(replay.total, []), clock=clock)
        player.speed = speed
        await player.go(0)
        player.play()

        await clock.slept_until(gap)
        assert (player.at, clock.wakes) == (10, [gap]), SPEEDS[speed]
        clock.advance(gap)
        await clock.slept_until(2 * gap)
        assert (player.at, clock.wakes) == (20, [2 * gap]), SPEEDS[speed]
        player.play()
        assert not player.playing


async def test_a_replay_pauses_at_its_end_having_told_its_client_of_each_move(replay):
    clock = ManualClock(0.0)
    player = Player(replay, made_up(replay.total, []), clock=clock)
    moves: list[tuple[int, bool]] = []
    ended = asyncio.Event()

    def changed() -> None:
        moves.append((player.at, player.playing))
        if not player.playing:
            ended.set()

    player.changed = changed
    player.speed = SPEEDS.index("idle skipped")
    player.play()
    while not ended.is_set():
        await first(clock.slept_until(clock.now() + IDLE), ended.wait())
        clock.advance(IDLE)

    assert moves[-1] == (replay.total, False)
    assert [at for at, _ in moves] == sorted(at for at, _ in moves)
    assert [at for at, playing in moves if playing][1:] == [*range(10, replay.total, 10), replay.total]


async def test_a_step_or_a_turn_moves_one_event_or_to_where_a_turn_ends_either_way_and_pauses(replay):
    player = Player(replay, made_up(replay.total, [5, 12]), clock=ManualClock(0.0))
    player.play()

    await player.step(1)
    assert (player.at, player.playing) == (1, False)
    await player.turn(1)
    assert player.at == 5
    await player.turn(1)
    assert player.at == 12
    await player.turn(1)
    assert player.at == replay.total
    await player.turn(-1)
    assert player.at == 12
    await player.turn(-1)
    assert player.at == 5
    await player.turn(-1)
    assert player.at == 0
    await player.step(-1)
    assert player.at == 0
    await player.go(replay.total + 9)
    assert player.at == replay.total


async def test_a_jump_goes_to_an_event_by_its_number_or_to_the_last_by_a_time_into_the_session(replay):
    player = Player(replay, made_up(replay.total, []), clock=ManualClock(0.0))

    await player.jump("7")
    assert player.at == 7
    await player.jump("#3")
    assert player.at == 3
    await player.jump("0:20")
    assert player.at == 30
    await player.jump("0:00:15")
    assert player.at == 20
    with pytest.raises(ValueError, match=r"is no place in the replay: an event's number"):
        await player.jump("soon")
    for no_time in ("9:99", "1:75:00", "0:60"):
        with pytest.raises(ValueError, match=r"is no time into the session: an event's number"):
            await player.jump(no_time)
    assert player.at == 20
    assert JUMP.startswith("An event's number")


async def test_the_banner_says_it_is_a_replay_of_which_session_at_what_time_and_event_of_how_many(replay):
    player = Player(replay, made_up(replay.total, []), clock=ManualClock(0.0))
    total = f"{replay.total:,}"

    nothing = "Nothing here acts on the session."
    assert player.banner() == f"Replay of s, before its first event, of {total}: paused. {nothing}"
    await player.go(25)
    player.play()
    player.faster()
    at = f"at event 25 of {total}, {elapsed(20)} into it, {moment(START + 20)}"
    assert player.banner() == f"Replay of s, {at}: playing at 4x. {nothing}"
    drawn = f"at event 5 of {total}, {elapsed(0)} into it, {moment(START)}"
    assert player.banner(5) == f"Replay of s, {drawn}: playing at 4x. {nothing}"
    assert player.playhead == (25, START + 20)
    assert moment(START) == "1970-01-12 13:46:40 UTC" and elapsed(3725) == "1:02:05"
    await player.close()


async def test_playing_on_from_the_end_starts_again_from_the_start(replay):
    clock = ManualClock(0.0)
    player = Player(replay, made_up(replay.total, []), clock=clock)
    await player.go(replay.total)
    player.play()
    await clock.sleeping()
    assert player.playing and player.at == 10


async def test_a_move_the_replay_refuses_pauses_it_and_the_banner_says_why(replay, monkeypatch):
    player = Player(replay, made_up(replay.total, []), clock=ManualClock(0.0))

    async def refused(seq: int) -> None:
        raise Refused("unavailable", "a writer changed this journal; open it again")

    monkeypatch.setattr(replay, "seek", refused)
    player.play()
    await player.step(1)

    assert (player.at, player.playing) == (0, False)
    assert player.banner().endswith("It could not move: unavailable: a writer changed this journal; open it again")
    monkeypatch.undo()
    await player.step(1)
    assert player.refusal is None and "could not move" not in player.banner()


def test_every_control_is_named_as_both_clients_name_it_and_nothing_acts_says_why():
    assert list(CONTROLS) == ["play", "speed", "step", "back", "turn", "turn-back", "jump"]
    assert all(control.does and control.name == name for name, control in CONTROLS.items())
    assert nothing_acts("s") == (
        "A replay acts on nothing, as it is a read-only copy of s's record: open the session itself to act."
    )
