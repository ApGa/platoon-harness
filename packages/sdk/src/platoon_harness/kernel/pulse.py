"""Wake-ups that cross threads and hold no per-subscriber queue."""

import asyncio
import contextlib
import threading
from collections import deque
from collections.abc import Awaitable, Callable, Iterable
from fnmatch import fnmatchcase
from itertools import takewhile
from typing import Any

from .model import Delta, Event, Page

_TAIL_SIZE = 1024
_TAIL_LIMIT = 256 * 1024
_FRAME_LIMIT = 64 * 1024


def _finish(outcomes: list[tuple[asyncio.Future[Any], Any]]) -> None:
    for future, result in outcomes:
        if future.done():
            continue
        if isinstance(result, BaseException):
            future.set_exception(result)
        else:
            future.set_result(result)


def settle(outcomes: Iterable[tuple[asyncio.Future[Any], Any]]) -> None:
    """Resolve futures from any thread, waking each loop once. A closed loop has nobody left to tell."""
    loops: dict[asyncio.AbstractEventLoop, list[tuple[asyncio.Future[Any], Any]]] = {}
    for future, result in outcomes:
        loops.setdefault(future.get_loop(), []).append((future, result))
    for loop, batch in loops.items():
        with contextlib.suppress(RuntimeError):
            loop.call_soon_threadsafe(_finish, batch)


async def first(work: Awaitable[Any], *rivals: Awaitable[Any]) -> bool:
    """Race `work` against `rivals` and drop whatever is left. True if `work` finished first, and if it failed this
    raises what it raised."""
    racers = [asyncio.ensure_future(racer) for racer in (work, *rivals)]
    try:
        await asyncio.wait(racers, return_when=asyncio.FIRST_COMPLETED)
        won = racers[0].done()
        if won:
            racers[0].result()
        return won
    finally:
        for racer in racers:
            racer.cancel()
        await asyncio.gather(*racers, return_exceptions=True)


class Pulse:
    """A rising number that waiters can sleep on."""

    def __init__(self, head: int = 0) -> None:
        self.head = head
        self.closed = False
        self._lock = threading.Lock()
        self._waiters: set[asyncio.Future[None]] = set()

    def publish(self, head: int) -> None:
        settle((waiter, None) for waiter in self.advance(head))

    def advance(self, head: int) -> set[asyncio.Future[None]]:
        """Move the head, and hand back whoever sleeps on it, to wake once what must come first has."""
        with self._lock:
            self.head = head
            waiters, self._waiters = self._waiters, set()
        return waiters

    def close(self) -> None:
        self.closed = True
        self.publish(self.head)

    async def wait(self, after: int) -> bool:
        """Sleep until the head passes `after`. False means closed. A publish that moves nothing, as a batch with no
        events does, puts it back to sleep."""
        while True:
            waiter = asyncio.get_running_loop().create_future()
            with self._lock:
                if self.closed:
                    return False
                if self.head > after:
                    return True
                self._waiters.add(waiter)
            try:
                await waiter
            finally:
                with self._lock:
                    self._waiters.discard(waiter)


class Tail:
    """The newest events, read once per head move and shared by every follower near the head."""

    def __init__(self, fetch: Callable[[int], tuple[Event, ...]], head: int) -> None:
        self._fetch = fetch
        self._events: deque[Event] = deque(maxlen=_TAIL_SIZE)
        self._end = head
        self._lock = threading.Lock()

    def _catch_up(self, head: int) -> None:
        if head - self._end > _TAIL_SIZE:
            self._events.clear()
            self._end = head - _TAIL_SIZE
        while self._end < head:
            events = self._fetch(self._end)
            self._events.extend(events)
            self._end = events[-1].seq

    def page(self, after: int, match: str | None, head: int) -> Page | None:
        """The events past `after`, or None if they need SQL: they left the tail, or one revokes a reader."""
        with self._lock:
            self._catch_up(head)
            if after < self._end - len(self._events):
                return None
            fresh = list(takewhile(lambda event: event.seq > after, reversed(self._events)))
            cursor = max(after, self._end)
        if any(event.type == "principal.revoked" for event in fresh):
            return None
        fresh.reverse()
        if match is not None:
            fresh = [event for event in fresh if fnmatchcase(event.stream, match)]
        return Page(events=tuple(fresh), cursor=cursor, head=head)


class Ring:
    """One agent's live text: what it is saying now, since the last event that replaced what it said before. It is
    bounded, lossy and apart from the journal, as the item that follows is the truth. A frame is cut at 64 KiB, and the
    oldest go past 256 KiB."""

    def __init__(self, agent: str) -> None:
        self._agent = agent
        self._held: deque[tuple[int, str]] = deque()
        self._size = 0
        self._begins = 1
        self._ended: int | None = None
        self._pulse = Pulse()

    def push(self, text: str) -> None:
        frame = self._pulse.head + 1
        self._held.append((frame, text[:_FRAME_LIMIT]))
        self._size += len(self._held[-1][1])
        while self._size > _TAIL_LIMIT:
            self._size -= len(self._held.popleft()[1])
        self._pulse.publish(frame)

    def end(self, seq: int) -> bool:
        """The event at `seq` replaced what was said so far: it is an item now, or gone with its turn or its agent.
        False for an end it has heard of, or an older one, which is no news."""
        if self._ended is not None and seq <= self._ended:
            return False
        frame = self._pulse.head + 1
        self._held.clear()
        self._size = 0
        self._begins, self._ended = frame + 1, seq
        self._pulse.publish(frame)
        return True

    def since(self, after: int | None) -> Delta | None:
        """What was said past frame `after`, joined, or None if nothing was. One that reads from before an end is told
        `ended` and given only what came after it, as is one that joins with no `after`, so nobody is shown text twice.
        A place past the head is an earlier incarnation's, so it joins too."""
        head = self._pulse.head
        if after is not None and after > head:
            after = None
        if after == head:
            return None
        within = after is not None and after >= self._begins - 1
        start = after + 1 if after is not None and within else self._begins
        shown = [(frame, text) for frame, text in self._held if frame >= start]
        if after is None and not shown:
            return None
        first = shown[0][0] if shown else head + 1
        text = "".join(text for _, text in shown)
        return Delta(agent=self._agent, frame=head, text=text, lag=first - start, ended=None if within else self._ended)

    @property
    def head(self) -> int:
        """The newest frame."""
        return self._pulse.head

    async def wait(self, after: int) -> bool:
        """Sleep until a frame past `after` comes. False means closed."""
        return await self._pulse.wait(after)

    def close(self) -> None:
        self._pulse.close()
