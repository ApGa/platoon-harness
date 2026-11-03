"""The installed `platoon-harness`, run as processes of its own, each leading a group that the test ends however it
ends, and team files on the scripted harnesses of `scripts.py`."""

import asyncio
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..conftest import end_group

EXECUTABLE = Path(sys.executable).with_name("platoon-harness")
ROOT = Path(__file__).parents[2]
SECONDS = 60.0
PIPE = asyncio.subprocess.PIPE


def crew(lead: str = "lead", worker: str = "worker") -> str:
    """A team file: a lead on one scripted harness, which starts workers on another."""
    return f"""
[roles.lead]
harness = "tests.integration.scripts:{lead}"
may_spawn = ["worker"]

[roles.worker]
harness = "tests.integration.scripts:{worker}"

[topology.manager-worker]
manager = "lead"
workers = "worker"
"""


def solo(harness: str, **more: str) -> str:
    """A team file of one role, `bob`, which starts one agent of its name."""
    lines = [f"{key} = {value}" for key, value in more.items()]
    return "\n".join(["[roles.bob]", f'harness = "tests.integration.scripts:{harness}"', *lines]) + "\n"


@dataclass(frozen=True)
class Done:
    code: int
    stdout: str
    stderr: str

    def lines(self) -> list[dict[str, Any]]:
        """Stdout as JSONL, every line of which must be one object."""
        return [json.loads(line) for line in self.stdout.splitlines()]


class Cli:
    """The command line in a folder of its own, with its own state root, reaching the scripted harnesses."""

    def __init__(self, folder: Path) -> None:
        self.folder = folder
        self.env = {**os.environ, "PLATOON_HARNESS_HOME": str(folder / "home"), "PYTHONPATH": str(ROOT)}
        self.started: list[asyncio.subprocess.Process] = []

    def write(self, name: str, text: str) -> str:
        (self.folder / name).write_text(text)
        return name

    async def start(self, *args: str, stdin: int = asyncio.subprocess.DEVNULL) -> asyncio.subprocess.Process:
        process = await asyncio.create_subprocess_exec(
            EXECUTABLE,
            *args,
            cwd=self.folder,
            env=self.env,
            stdin=stdin,
            stdout=PIPE,
            stderr=PIPE,
            start_new_session=True,
        )
        self.started.append(process)
        return process

    async def run(self, *args: str, input: bytes | None = None) -> Done:
        process = await self.start(*args, stdin=asyncio.subprocess.DEVNULL if input is None else PIPE)
        return await finished(process, input)

    def end(self) -> None:
        """End each process this started that is still there, with its group."""
        for process in self.started:
            if process.returncode is None:
                end_group(process.pid)


async def finished(process: asyncio.subprocess.Process, input: bytes | None = None) -> Done:
    stdout, stderr = await asyncio.wait_for(process.communicate(input), SECONDS)
    assert process.returncode is not None
    return Done(process.returncode, stdout.decode(), stderr.decode())


async def line_where(process: asyncio.subprocess.Process, seen: list[dict[str, Any]], key: str, value: Any) -> None:
    """Read JSON lines from a process into `seen`, until one has `key` at `value`."""
    assert process.stdout is not None
    async with asyncio.timeout(SECONDS):
        while line := await process.stdout.readline():
            seen.append(json.loads(line))
            if seen[-1].get(key) == value:
                return
    raise AssertionError(f"no line had {key} {value}: {seen[-3:]}")


async def said(process: asyncio.subprocess.Process, words: str) -> None:
    """Read a process's stderr until a line holds `words`."""
    assert process.stderr is not None
    async with asyncio.timeout(SECONDS):
        while line := await process.stderr.readline():
            if words in line.decode():
                return
    raise AssertionError(f"nothing said {words!r}")


def checked(done: Done, *, first: int = 1) -> list[dict[str, Any]]:
    """The events of a run's JSONL, once its shape is held to what the reference documents: every line an object of
    format 1, the events in `seq` order with none missing, and the ending last, with the code the command exits with."""
    lines = done.lines()
    assert all(line["format"] == 1 for line in lines)
    *events, ending = lines
    assert [event["seq"] for event in events] == list(range(first, first + len(events)))
    assert (ending["type"], ending["code"]) == ("ending", done.code)
    return events
