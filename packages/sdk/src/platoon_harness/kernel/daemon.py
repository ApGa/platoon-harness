"""Daemons: restartable tasks that keep nothing that must survive a restart."""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from .model import GIST_LIMIT, NAME_LIMIT
from .op import Args, op
from .pulse import first
from .txn import Txn

if TYPE_CHECKING:
    from .kernel import Kernel

log = logging.getLogger("platoon_harness.kernel")

_FIRST_BACKOFF = 0.1
_MAX_BACKOFF = 30.0
_STABLE_AFTER = 60.0
_ERROR_LIMIT = 2048
_RETRY_SECONDS = 1.0
_FAILING = (
    "failed and is restarted with backoff, its traceback in the session folder's runtime.log, and `session stop` then "
    "`session resume` start it anew"
)


@dataclass(frozen=True)
class Daemon:
    """A named task. `run` reads views, touches the world and reports through ops."""

    name: str
    run: Callable[["Kernel"], Awaitable[None]]


async def keep_running(daemon: Daemon, kernel: "Kernel") -> None:
    """Restart one daemon with backoff until it returns. A run that lasted forgives earlier failures. The journal hears
    a failure when it begins a run of them or says another error than the last, and the next run that lasts, so a
    daemon that fails on every pass stands in `attention` with its latest error and never passes for a quiet session."""
    failures, said = 0, None
    while True:
        started = kernel.clock.now()
        try:
            return await _run(daemon, kernel, failing=failures > 0)
        except Exception as error:
            if kernel.closed:
                return
            log.exception("daemon %s failed", daemon.name)
            if kernel.clock.now() - started >= _STABLE_AFTER:
                failures = 0
            latest = f"{type(error).__name__}: {error}"
            if not failures or latest != said:
                said = latest
                await _say(kernel, "daemon.fail", {"daemon": daemon.name, "error": said})
        await kernel.clock.sleep(min(_MAX_BACKOFF, _FIRST_BACKOFF * 2**failures))
        failures += 1


async def _run(daemon: Daemon, kernel: "Kernel", *, failing: bool) -> None:
    """Run a daemon once. A run of one that has failed says so once it has lasted."""
    if not failing:
        return await daemon.run(kernel)
    running = asyncio.ensure_future(daemon.run(kernel))
    try:
        if not await first(asyncio.shield(running), kernel.clock.sleep(_STABLE_AFTER)):
            await _say(kernel, "daemon.recover", {"daemon": daemon.name})
        return await running
    finally:
        running.cancel()


async def _say(kernel: "Kernel", op: str, args: dict[str, Any]) -> None:
    """Tell the journal as the runtime, waiting out a busy writer, while it can still be told."""
    while not kernel.closed:
        outcome = await kernel.submit(kernel.runtime, op, args)
        if outcome.refusal is None or outcome.refusal.code != "busy":
            return
        await kernel.clock.sleep(outcome.refusal.retry_after or _RETRY_SECONDS)


class Failed(Args):
    daemon: str
    error: str


class Lasted(Args):
    daemon: str


def _stream(daemon: str) -> str:
    return f"daemon/{daemon[:NAME_LIMIT]}"


@op("daemon.fail", on=lambda a: _stream(a.daemon), runtime=True)
def fail_daemon(txn: Txn, a: Failed) -> None:
    """Record that a daemon failed and is restarted with backoff, which needs a person until a run of it lasts a minute:
    where its traceback is, what starts it anew, and its error. A long error is cut, so that a failure can always be
    said."""
    error = a.error if len(a.error) <= _ERROR_LIMIT else f"{a.error[:_ERROR_LIMIT]} [cut]"
    gist = f"{a.daemon} {_FAILING}: {error}"[:GIST_LIMIT]
    txn.emit("daemon.failed", _stream(a.daemon), gist=gist, data={"daemon": a.daemon, "error": error})


@op("daemon.recover", on=lambda a: _stream(a.daemon), runtime=True)
def recover_daemon(txn: Txn, a: Lasted) -> None:
    """Record that a run of a daemon that had failed has lasted a minute."""
    gist = f"{a.daemon} has run a minute since it failed"[:GIST_LIMIT]
    txn.emit("daemon.recovered", _stream(a.daemon), gist=gist, data={"daemon": a.daemon})
