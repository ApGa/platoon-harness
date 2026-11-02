"""Wake-ups that cross threads and hold no per-subscriber queue."""

import asyncio
import contextlib
import threading
from collections import deque
from collections.abc import AsyncIterator, Callable, Iterable
from fnmatch import fnmatchcase
from itertools import takewhile
from typing import Any

from .model import Delta, Event, Page

_TAIL_SIZE = 1024
_RING_SIZE = 256


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


class Pulse:
    """A rising number that waiters can sleep on."""

    def __init__(self, head: int = 0) -> None:
        self.head = head
        self.closed = False
        self._lock = threading.Lock()
        self._waiters: set[asyncio.Future[None]] = set()

    def publish(self, head: int) -> None:
        with self._lock:
            self.head = head
            waiters, self._waiters = self._waiters, set()
        settle((waiter, None) for waiter in waiters)

    def close(self) -> None:
        self.closed = True
        self.publish(self.head)

    async def wait(self, after: int) -> bool:
        """Sleep until the head passes `after`. False means closed."""
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
        return not self.closed


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
    """A bounded lossy buffer of one agent's live text, separate from the journal."""

    def __init__(self, agent: str) -> None:
        self._agent = agent
        self._held: deque[Delta] = deque(maxlen=_RING_SIZE)
        self._pulse = Pulse()

    def push(self, text: str) -> None:
        frame = self._pulse.head + 1
        self._held.append(Delta(agent=self._agent, frame=frame, text=text))
        self._pulse.publish(frame)

    def close(self) -> None:
        self._pulse.close()

    async def frames(self) -> AsyncIterator[Delta]:
        """Yield frames from the oldest still held. Overflow shows up as `lag`."""
        seen = self._pulse.head - len(self._held)
        while await self._pulse.wait(seen):
            for delta in tuple(self._held):
                if delta.frame > seen:
                    yield delta.model_copy(update={"lag": delta.frame - seen - 1})
                    seen = delta.frame
