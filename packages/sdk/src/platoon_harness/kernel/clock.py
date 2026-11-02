"""Time as the kernel sees it."""

import asyncio
import time
from collections.abc import Callable
from typing import Protocol


class Clock(Protocol):
    """A source of time. Time decides timers and leases; it never orders events."""

    def now(self) -> float: ...

    async def sleep(self, seconds: float) -> None: ...


class SystemClock:
    """The operating system's clock."""

    def now(self) -> float:
        return time.time()

    async def sleep(self, seconds: float) -> None:
        await asyncio.sleep(seconds)


class ManualClock:
    """A clock that moves only when told to."""

    def __init__(self, now: float = 0.0) -> None:
        self._now = now
        self._sleepers: dict[asyncio.Future[None], float] = {}
        self._parked = asyncio.Event()

    def now(self) -> float:
        return self._now

    async def sleep(self, seconds: float) -> None:
        if seconds <= 0:
            return await asyncio.sleep(0)
        sleeper = asyncio.get_running_loop().create_future()
        self._sleepers[sleeper] = self._now + seconds
        self._parked.set()
        try:
            await sleeper
        finally:
            self._sleepers.pop(sleeper, None)

    def advance(self, seconds: float) -> None:
        """Move time forward and wake whoever is due."""
        self._now += seconds
        for sleeper, due in tuple(self._sleepers.items()):
            if due <= self._now:
                del self._sleepers[sleeper]
                sleeper.set_result(None)

    async def sleeping(self) -> None:
        """Wait until a task is asleep, so that `advance` cannot race it."""
        await self._parked_until(lambda: bool(self._sleepers))

    async def slept_until(self, due: float) -> None:
        """Wait until a task sleeps until `due`."""
        await self._parked_until(lambda: due in self.wakes)

    async def _parked_until(self, condition: Callable[[], bool]) -> None:
        while not condition():
            self._parked.clear()
            await self._parked.wait()

    @property
    def wakes(self) -> list[float]:
        """When each sleeper is due."""
        return sorted(self._sleepers.values())
