"""Daemons: restartable tasks that keep nothing that must survive a restart."""

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .kernel import Kernel

log = logging.getLogger("platoon_harness.kernel")

_FIRST_BACKOFF = 0.1
_MAX_BACKOFF = 30.0
_STABLE_AFTER = 60.0


@dataclass(frozen=True)
class Daemon:
    """A named task. `run` reads views, touches the world and reports through ops."""

    name: str
    run: Callable[["Kernel"], Awaitable[None]]


async def keep_running(daemon: Daemon, kernel: "Kernel") -> None:
    """Restart one daemon with backoff until it returns. A run that lasted forgives earlier failures."""
    failures = 0
    while True:
        started = kernel.clock.now()
        try:
            return await daemon.run(kernel)
        except Exception:
            if kernel.closed:
                return
            log.exception("daemon %s failed", daemon.name)
        if kernel.clock.now() - started >= _STABLE_AFTER:
            failures = 0
        await kernel.clock.sleep(min(_MAX_BACKOFF, _FIRST_BACKOFF * 2**failures))
        failures += 1
