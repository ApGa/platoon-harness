"""A detached runtime that SIGKILLs itself at one exact step: `kill_at.py <folder> <op[:kind]> <before|after> <nth>`."""

import asyncio
import os
import signal
import sys
from pathlib import Path
from typing import Any

from platoon_harness.drivers.process import Process, Record
from platoon_harness.kernel import Kernel
from platoon_harness.runtime.__main__ import _detach, _serve


def die() -> None:
    os.kill(os.getpid(), signal.SIGKILL)


class Point:
    """One step of a runtime, counted, so that a test can name the second launch."""

    def __init__(self, name: str, when: str, nth: int) -> None:
        self.op, _, self.kind = name.partition(":")
        self.when = when
        self.nth = nth
        self.seen = 0

    def reached(self) -> bool:
        self.seen += 1
        return self.seen == self.nth

    def is_it(self, kernel: Kernel, op: str, args: Any) -> bool:
        if op != self.op:
            return False
        if op == "agent.report":
            report = args["report"]
            return (report["type"] if isinstance(report, dict) else report.type) == self.kind
        if op.startswith("effect."):
            rows = [
                row
                for state in ("requested", "started")
                for row in kernel.query(kernel.runtime, "effect.list", {"state": state}).result or ()
            ]
            return any(row["id"] == args["id"] and row["kind"] == self.kind for row in rows)
        return True


def arm(point: Point) -> None:
    submit = Kernel.submit

    async def submitting(self: Kernel, principal: Any, op: str, args: Any, **options: Any) -> Any:
        fires = point.is_it(self, op, args) and point.reached()
        if fires and point.when == "before":
            die()
        outcome = await submit(self, principal, op, args, **options)
        if fires and point.when == "after":
            die()
        return outcome

    Kernel.submit = submitting  # type: ignore[method-assign]

    if point.op == "record":
        write = Record.write

        def writing(self: Record, folder: Path) -> None:
            write(self, folder)
            if point.reached():
                die()

        Record.write = writing  # type: ignore[method-assign]

    if point.op == "go":
        init = Process.__init__

        def starting(self: Process, *arguments: Any, **options: Any) -> None:
            if point.reached():
                die()
            init(self, *arguments, **options)

        Process.__init__ = starting  # type: ignore[method-assign]


if __name__ == "__main__":
    folder = Path(sys.argv[1])
    arm(Point(sys.argv[2], sys.argv[3], int(sys.argv[4])))
    _detach(folder)
    asyncio.run(_serve(folder))
