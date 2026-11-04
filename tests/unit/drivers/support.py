"""Helpers: a spec under `tmp_path`, and a reporter a test can await."""

import asyncio
import os
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

from platoon_harness.drivers import AgentSpec, Report
from platoon_harness.testing import goal


class Heard:
    """A `Reporter` that keeps everything, so a test can await a report rather than sleep for it."""

    def __init__(self) -> None:
        self.reports: list[Report] = []
        self._arrived = asyncio.Event()

    async def __call__(self, report: Report) -> None:
        self.reports.append(report)
        self._arrived.set()

    async def until[T](self, kind: type[T], where: Callable[[T], bool] = lambda _: True) -> T:
        """The first report of `kind` that holds, when it has arrived."""
        while True:
            for report in self.reports:
                if isinstance(report, kind) and where(report):
                    return report
            self._arrived.clear()
            await self._arrived.wait()

    def of(self, kind: type) -> list[Any]:
        return [report for report in self.reports if isinstance(report, kind)]


def make_spec(tmp_path: Path, **fields: Any) -> AgentSpec:
    """A spec whose `goal`, given as text, is handed over as the runtime hands one."""
    return AgentSpec.model_validate(
        {
            "agent": "ada",
            "role": "worker",
            "cwd": tmp_path,
            "folder": tmp_path / "agents" / "ada",
            **fields,
            "goal": goal(fields.get("goal", "do the thing")),
        }
    )


def group_of(pid: int) -> int | None:
    try:
        return os.getpgid(pid)
    except ProcessLookupError:
        return None


def running(pid: int) -> bool:
    """Whether a pid holds a process that is not a zombie."""
    state = subprocess.run(["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True, check=False)
    return bool(state.stdout.strip()) and not state.stdout.startswith("Z")


def spawn_group(*command: str) -> subprocess.Popen:
    """A process nobody here owns: its own session, its own group."""
    return subprocess.Popen(command, start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
