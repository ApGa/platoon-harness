"""A replay as both clients play it: its controls, how it is paced, where each control goes, and the words both clients
say of it, so the terminal and the browser play alike. A client draws the replay's session as it draws any session,
and acts on nothing in it: what it draws is the copy's record through the playhead, but for what estimators said,
which a panel shows labelled with when it was written."""

import asyncio
import contextlib
import re
from bisect import bisect_right
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import NamedTuple

from platoon_harness import Refused, Replay
from platoon_harness.kernel import Clock, SystemClock

SPEEDS = ("1x", "4x", "16x", "idle skipped")
"""How fast a replay plays: its events at their recorded pace, or four or sixteen times it, or at it with every gap
longer than `IDLE` cut to that."""
_FACTORS = (1.0, 4.0, 16.0, 1.0)
IDLE = 1.0
"""The longest gap between two events, in seconds, that a replay with idle skipped plays."""
FRAME = 1 / 15
"""The events a replay plays within this many seconds of each other come at once, as the clients draw no faster."""
ENDS = frozenset({"turn.ended", "turn.lost"})
"""What ends a turn, which a step of a turn goes to."""
_TIME = re.compile(r"(?:(\d+):)?(\d{1,2}):(\d{2})")


@dataclass(frozen=True)
class Control:
    """One control of a replay: its name, which the terminal types after `/` and the browser shows on its button, and
    what it does."""

    name: str
    does: str


CONTROLS = {
    control.name: control
    for control in (
        Control("play", "Play the replay from where it stands, at its speed, or pause it"),
        Control("speed", f"Play at the next speed: {', '.join(SPEEDS)}, then {SPEEDS[0]} again"),
        Control("step", "Step one event on"),
        Control("back", "Step one event back"),
        Control("turn", "Go on to where the next turn ends, of any agent"),
        Control("turn-back", "Go back to where the turn before ended, of any agent"),
        Control("jump", "Jump to an event, by its number, or to a time into the session, as m:ss or h:mm:ss"),
    )
}
"""The controls of a replay, the same in both clients."""

JUMP = "An event's number, or a time into the session as m:ss or h:mm:ss"
"""What the jump's field takes."""


def nothing_acts(name: str) -> str:
    """Why nothing in a replay acts, which every act and form of one says."""
    return f"A replay acts on nothing, as it is a read-only copy of {name}'s record: open the session itself to act."


def reads_no_diff(name: str) -> str:
    """Why a replay opens no diff, which both clients say before anything opens."""
    return f"A replay reads no diff, as asking for one is an act. {nothing_acts(name)}"


def elapsed(seconds: float) -> str:
    """A time into a session, as `h:mm:ss`."""
    whole = max(int(seconds), 0)
    return f"{whole // 3600}:{whole // 60 % 60:02}:{whole % 60:02}"


def moment(wall_time: float) -> str:
    """A wall time as both clients write one: in UTC, to the second."""
    return datetime.fromtimestamp(wall_time, UTC).strftime("%Y-%m-%d %H:%M:%S UTC")


class Playhead(NamedTuple):
    """Where a replay stands: the newest event its copy holds, and that event's wall time."""

    at: int
    wall_time: float


class Record(NamedTuple):
    """What a player reads of the record it plays, once: each event's wall time by seq, the latest wall time by then,
    which a jump to a time finds its place in, and the seqs where a turn ends."""

    times: list[float]
    reached: list[float]
    ends: list[int]


async def _record(replay: Replay) -> Record:
    record = Record([], [], [])
    after = 0
    while after < replay.total:
        page = await replay.page(after=after, limit=4096)
        for event in page.events:
            record.times.append(event.wall_time)
            record.reached.append(max([event.wall_time, *record.reached[-1:]]))
            if event.type in ENDS:
                record.ends.append(event.seq)
        after = page.cursor
    return record


class Player:
    """A replay as a person plays it: playing or paused, at one of `SPEEDS`, and moved by hand an event or a turn at a
    time or to an event or a time. `changed` is called after each move and each change of how it plays, so a client
    draws its banner again, and draws the session anew where `replay.session` is a new one. It reads the record's wall
    times and turn ends once, from the original through the replay's end, to pace itself and to find where a control
    goes, and draws nothing of them."""

    def __init__(self, replay: Replay, record: Record, *, clock: Clock | None = None) -> None:
        self.replay = replay
        self.playing = False
        self.speed = 0
        self.changed: Callable[[], object] = lambda: None
        self.refusal: str | None = None
        """Why the replay could not move, as when its record was written to since it opened, until it moves again."""
        self._clock = clock or SystemClock()
        self._times, self._reached, self._ends = record
        self._task: asyncio.Task[None] | None = None

    @classmethod
    async def open(cls, name: str, *, clock: Clock | None = None) -> "Player":
        """A replay of the session `name`, at its start and paused, with the record it plays read."""
        replay = await Replay.open(name)
        try:
            return cls(replay, await _record(replay), clock=clock)
        except BaseException:
            await replay.close()
            raise

    @property
    def at(self) -> int:
        return self.replay.at

    @property
    def total(self) -> int:
        return self.replay.total

    @property
    def playhead(self) -> Playhead | None:
        """Where the replay stands, or None before its first event."""
        return Playhead(self.at, self._times[self.at - 1]) if self.at > 0 else None

    def banner(self, at: int | None = None) -> str:
        """What a replay's banner says: that it is a replay, of which session, the event it stands at of how many, the
        time into the session and the wall time of that event, how it plays, and why it could not move, where it
        could not. A client that has not yet drawn where the replay stands names `at`, the event it has drawn
        through, so its banner never names a point before what it shows."""
        name, total = self.replay.name, self.total
        at = self.at if at is None else at
        how = f"playing at {SPEEDS[self.speed]}" if self.playing else "paused"
        if at == 0:
            where = f"before its first event, of {total:,}"
        else:
            into = elapsed(self._times[at - 1] - self._times[0])
            where = f"at event {at:,} of {total:,}, {into} into it, {moment(self._times[at - 1])}"
        said = f"Replay of {name}, {where}: {how}. Nothing here acts on the session."
        return said if self.refusal is None else f"{said} It could not move: {self.refusal}"

    def _gap(self, seq: int) -> float:
        """How long the replay waits, at its speed, before it plays the event at `seq`."""
        if seq <= 1:
            return 0.0
        gap = max(self._times[seq - 1] - self._times[seq - 2], 0.0) / _FACTORS[self.speed]
        return min(gap, IDLE) if SPEEDS[self.speed] == "idle skipped" else gap

    async def _play(self) -> None:
        """Play on from where the replay stands, the events that come within a frame of each other at once, until its
        end, where it pauses, or until a move is refused. A move that a pause cuts short is finished, so the copy stands
        where it says it does."""
        while self.playing and (at := self.at) < self.total:
            await self._clock.sleep(self._gap(at + 1))
            through, spent = at + 1, 0.0
            while through < self.total and spent + (gap := self._gap(through + 1)) < FRAME:
                spent, through = spent + gap, through + 1
            await asyncio.shield(self._seek(through))
            self.changed()
        self.playing = False
        self._task = None
        self.changed()

    async def _seek(self, seq: int) -> None:
        """Move the replay, or pause it, saying why it could not move."""
        try:
            await self.replay.seek(seq)
        except Refused as refused:
            self.refusal, self.playing = str(refused), False
        else:
            self.refusal = None

    def _stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            self._task = None

    def _start(self) -> None:
        self._stop()
        if self.playing:
            self._task = asyncio.ensure_future(self._play())

    def play(self) -> None:
        """Play from where the replay stands, from its start once it has ended, or pause it."""
        self.playing, self.refusal = not self.playing, None
        if self.playing and self.at >= self.total:
            self._task = asyncio.ensure_future(self._from_the_start())
        else:
            self._start()
        self.changed()

    async def _from_the_start(self) -> None:
        await self._seek(0)
        self.changed()
        await self._play()

    def faster(self) -> None:
        """Play at the next of `SPEEDS`, and from the first after the last."""
        self.speed = (self.speed + 1) % len(SPEEDS)
        self._start()
        self.changed()

    async def go(self, seq: int) -> None:
        """Move to the event at `seq`, kept within the replay, playing on from there if it was playing."""
        self._stop()
        await self._seek(min(max(seq, 0), self.total))
        self._start()
        self.changed()

    async def step(self, by: int) -> None:
        """Step `by` events, one on or one back, pausing."""
        self.playing = False
        await self.go(self.at + by)

    async def turn(self, by: int) -> None:
        """Go to where the next turn ends, with `by` 1, or where the one before ended, with -1, of any agent, pausing;
        or to the replay's end or start where none is left that way."""
        self.playing = False
        if by > 0:
            index = bisect_right(self._ends, self.at)
            await self.go(self._ends[index] if index < len(self._ends) else self.total)
        else:
            index = bisect_right(self._ends, self.at - 1) - 1
            await self.go(self._ends[index] if index >= 0 else 0)

    async def jump(self, where: str) -> None:
        """Jump to an event by its number, or to the last event by a time into the session, `m:ss` or `h:mm:ss`, or
        raise `ValueError` saying what it takes."""
        said = where.strip().removeprefix("#")
        if said.isdigit():
            await self.go(int(said))
            return
        found = _TIME.fullmatch(said)
        if found is None:
            raise ValueError(f"{where!r} is no place in the replay: {JUMP[0].lower()}{JUMP[1:]}.")
        hours, minutes, seconds = (int(part or 0) for part in found.groups())
        if seconds >= 60 or (found[1] is not None and minutes >= 60):
            raise ValueError(f"{where!r} is no time into the session: {JUMP[0].lower()}{JUMP[1:]}.")
        if not self._times:
            await self.go(0)
            return
        into = self._times[0] + hours * 3600 + minutes * 60 + seconds
        await self.go(bisect_right(self._reached, into))

    async def close(self) -> None:
        """Stop playing, and close the replay, which takes its copies back."""
        self._stop()
        with contextlib.suppress(Refused):
            await self.replay.close()
