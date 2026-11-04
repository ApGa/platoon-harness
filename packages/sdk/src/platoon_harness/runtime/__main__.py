"""`python -m platoon_harness.runtime <folder>`: a detached runtime, leading its own session, its log in the folder.

Signals are handled here and nowhere else, so that several runtimes can share a process that is not this one.
"""

import asyncio
import contextlib
import logging
import os
import signal
import sys
from pathlib import Path

from platoon_harness.kernel import JournalError

from . import Runtime
from .paths import open_log


def _detach(folder: Path) -> None:
    """Lead a session of our own, and keep every word in the folder: nobody is left to read a terminal."""
    with contextlib.suppress(PermissionError):
        os.setsid()
    log = open_log(folder)
    nothing = os.open(os.devnull, os.O_RDONLY)
    os.dup2(nothing, sys.stdin.fileno())
    os.dup2(log, sys.stdout.fileno())
    os.dup2(log, sys.stderr.fileno())
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")


async def _serve(folder: Path) -> None:
    runtime = Runtime(folder)
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(signum, runtime.ask_to_stop)
    await runtime.start()
    try:
        await runtime.run()
    finally:
        await runtime.stop()


def main() -> None:
    """Exit 74 when a commit fails, which ends the runtime as a kill would, as the command line's owners do."""
    folder = Path(sys.argv[1])
    _detach(folder)
    try:
        asyncio.run(_serve(folder))
    except JournalError as error:
        logging.getLogger("platoon_harness.runtime").error("%s", error)
        sys.exit(os.EX_IOERR)


if __name__ == "__main__":
    main()
