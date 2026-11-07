"""The installed `platoon-harness`, run as processes of its own, each leading a group that the test ends however it
ends, team files on the scripted harnesses of `scripts.py`, and the commands a page shows, run as it shows them."""

import asyncio
import json
import os
import re
import shlex
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

    async def start(
        self,
        *args: str,
        stdin: int = asyncio.subprocess.DEVNULL,
        stdout: int = PIPE,
        program: Path = EXECUTABLE,
        **env: str,
    ) -> asyncio.subprocess.Process:
        process = await asyncio.create_subprocess_exec(
            program,
            *args,
            cwd=self.folder,
            env={**self.env, **env},
            stdin=stdin,
            stdout=stdout,
            stderr=PIPE,
            start_new_session=True,
        )
        self.started.append(process)
        return process

    async def run(self, *args: str, input: bytes | None = None, **env: str) -> Done:
        process = await self.start(*args, stdin=asyncio.subprocess.DEVNULL if input is None else PIPE, **env)
        return await finished(process, input)

    async def as_shown(self, command: str) -> Done:
        """A `uv run` command as a page shows it, run here on this environment's program of its name, with the variables
        it sets in front."""
        words = shlex.split(command, comments=True)
        env = {}
        while re.fullmatch(r"[A-Z_]+=.*", words[0]):
            name, _, value = words.pop(0).partition("=")
            env[name] = value
        assert words[:2] == ["uv", "run"], command
        return await finished(await self.start(*words[3:], program=EXECUTABLE.with_name(words[2]), **env))

    def end(self) -> None:
        """End each process this started that is still there, with its group."""
        for process in self.started:
            if process.returncode is None:
                end_group(process.pid)


async def finished(process: asyncio.subprocess.Process, input: bytes | None = None, within: float = SECONDS) -> Done:
    stdout, stderr = await asyncio.wait_for(process.communicate(input), within)
    assert process.returncode is not None
    return Done(process.returncode, stdout.decode(), stderr.decode())


async def line_where(
    process: asyncio.subprocess.Process, seen: list[dict[str, Any]], key: str, value: Any, within: float = SECONDS
) -> None:
    """Read JSON lines from a process into `seen`, until one has `key` at `value`."""
    assert process.stdout is not None
    async with asyncio.timeout(within):
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


def shown(page: Path, *, where: str = "") -> list[str]:
    """Each command `page` shows after a `$ ` in a console block, its continued lines joined, of the first block that
    holds `where`."""
    blocks = re.findall(r"^```console\n(.*?)^```$", page.read_text(), re.MULTILINE | re.DOTALL)
    block = next(block for block in blocks if where in block)
    joined = re.sub(r"\\\n\s*", "", block)
    return [line.removeprefix("$ ") for line in joined.splitlines() if line.startswith("$ ")]


def checked(done: Done, *, first: int = 1) -> list[dict[str, Any]]:
    """The events of a run's JSONL, once its shape is held to what the reference documents: every line an object of
    format 1, the events in `seq` order with none missing, and the ending last, with the code the command exits with."""
    lines = done.lines()
    assert all(line["format"] == 1 for line in lines)
    *events, ending = lines
    assert [event["seq"] for event in events] == list(range(first, first + len(events)))
    assert (ending["type"], ending["code"]) == ("ending", done.code)
    return events
