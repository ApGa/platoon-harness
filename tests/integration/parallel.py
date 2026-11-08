"""Tool executions at once on a real binary against FakeModel. Several agents each run a shell command that ends only
once every agent's is running, so their tools run at once or none ends. One agent is given three responses of two calls
each, whose two end at once only if the harness runs them at once: two commands that run a script, two `cat`s of named
pipes, which a harness may take as read-only, and two calls of a query of ours. Each harness's test file runs these with
its own tool names and posture."""

import asyncio
import os
import sys
import threading
from collections.abc import Callable
from pathlib import Path
from typing import NamedTuple, Self

from platoon_harness import Session, Team
from platoon_harness.kernel import Args, Extension, Txn, op
from platoon_harness.testing import FakeModel, ToolCall

from ..unit.runtime.support import extension, in_state, of_type, until
from .scripts import strings

TIMEOUT = 60.0
TOGETHER = 15.0
"""How long each of the two calls of one response waits for the other before it says it ran alone."""
MET = '{"met": true}'
"""What a call of `meet.arrive` that met another answers."""

_MEET = """import socket, sys
port, name, seconds = int(sys.argv[1]), sys.argv[2], float(sys.argv[3])
with socket.create_connection(("127.0.0.1", port), timeout=seconds) as party:
    party.sendall(name.encode() + b"\\n")
    try:
        heard = party.recv(16)
    except OSError:
        heard = b""
print(name, "met" if heard == b"met\\n" else "alone")
"""


class Meeting:
    """A barrier on loopback: a party is a command that connects and names itself, and once `parties` are connected at
    once, each hears that they met and prints `<name> met`. One that waits `seconds` with fewer prints that it is
    alone."""

    def __init__(self, folder: Path, parties: int, seconds: float) -> None:
        self.script = folder / "meet.py"
        self.parties = parties
        self.seconds = seconds
        self.arrived = 0
        self.met = asyncio.Event()
        self._here: list[asyncio.StreamWriter] = []

    async def __aenter__(self) -> Self:
        self.script.write_text(_MEET)
        self._server = await asyncio.start_server(self._arrive, "127.0.0.1", 0)
        return self

    async def __aexit__(self, *_: object) -> None:
        self._server.close()
        for party in self._here:
            party.close()

    def command(self, name: str) -> str:
        """The shell command of the party `name`."""
        port = self._server.sockets[0].getsockname()[1]
        return f"{sys.executable} {self.script} {port} {name} {self.seconds}"

    async def _arrive(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        await reader.readline()
        self.arrived += 1
        self._here.append(writer)
        if len(self._here) == self.parties:
            for party in self._here:
                party.write(b"met\n")
            self.met.set()
        await reader.read()
        self._here.remove(writer)
        writer.close()


class Pipes:
    """Two named pipes, each read by a `cat`: a reader arrives when its `cat` opens its pipe, and once both have, each
    reads `met`. One left alone for `TOGETHER` seconds reads `alone`, and so does the other when it comes."""

    def __init__(self, folder: Path) -> None:
        self.paths = (folder / "first.pipe", folder / "second.pipe")
        self.met = False
        self._opening: list[asyncio.Future[int]] = []

    async def __aenter__(self) -> Self:
        for path in self.paths:
            os.mkfifo(path)
        return self

    async def __aexit__(self, *_: object) -> None:
        """Let go of any pipe no `cat` opened, whose opening for writing would otherwise wait for ever."""
        readers = [os.open(path, os.O_RDONLY | os.O_NONBLOCK) for path in self.paths]
        for writer in await asyncio.gather(*self._opening, return_exceptions=True):
            if isinstance(writer, int):
                os.close(writer)
        for reader in readers:
            os.close(reader)

    def commands(self) -> tuple[str, ...]:
        """The `cat` of each pipe, by its name in the folder its agent works in."""
        return tuple(f"cat {path.name}" for path in self.paths)

    async def meet(self) -> None:
        """Tell each reader whether the two met, once both have opened their pipes or one has waited alone."""
        opening = [asyncio.ensure_future(asyncio.to_thread(os.open, path, os.O_WRONLY)) for path in self.paths]
        self._opening = opening
        await asyncio.wait(opening, timeout=TIMEOUT, return_when=asyncio.FIRST_COMPLETED)
        both, _ = await asyncio.wait(opening, timeout=TOGETHER)
        self.met = len(both) == 2
        for opened in asyncio.as_completed(opening, timeout=TIMEOUT):
            writer = await opened
            os.write(writer, b"met\n" if self.met else b"alone\n")
            os.close(writer)
        self._opening = []


async def agents_run_their_shell_tools_at_once(
    team: Team, root: Path, model: FakeModel, shell: Callable[[str], ToolCall], agents: int = 3
) -> None:
    """`agents` agents of `team`'s one role, `bob`, each told to run one shell command, which ends only once every
    agent's is running: their tools run at once, or none ends before `TIMEOUT`."""
    bob = team.roles["bob"].model_copy(update={"count": agents})
    team = team.model_copy(update={"roles": {"bob": bob}})
    names = [f"bob-{number}" for number in range(1, agents + 1)]
    async with Meeting(root, agents, TIMEOUT) as meeting:
        model.script([shell(meeting.command(f"party-{number}")) for number in range(1, agents + 1)])
        model.script(["done"] * agents)
        async with Session.start(team, root=root, cwd=root) as session:
            for name in names:
                await in_state(session, name, "idle")
            await asyncio.gather(*(session.send(f"@{name}", "run your command") for name in names))
            await asyncio.wait_for(meeting.met.wait(), TIMEOUT)
            ended = await until(lambda: of_type(session, "turn.ended"), session, lambda found: len(found) == agents)

    assert sorted(event.agent for event in ended) == names
    assert [event.data["reason"] for event in ended] == ["stopped"] * agents
    for number in range(1, agents + 1):
        assert any(call.says(f"party-{number} met") for call in model.calls), f"party-{number} never met the others"


class Arrive(Args):
    pass


def meeting_of_two() -> Extension:
    """An extension whose one tool, `meet.arrive`, answers only once two calls are in it, or refuses both once one has
    waited `TOGETHER` seconds alone."""
    barrier = threading.Barrier(2, timeout=TOGETHER)

    @op("meet.arrive", query=True, tool=True)
    def arrive(txn: Txn, a: Arrive) -> dict[str, bool]:
        """Arrive, and hear back once another call has."""
        barrier.wait()
        return {"met": True}

    return Extension("meet", ops=[arrive])


class AtOnce(NamedTuple):
    """Whether a harness ran the two calls of one response at once, for each kind of call."""

    script: bool
    read: bool
    query: bool


async def what_one_response_runs_at_once(
    team: Team, root: Path, model: FakeModel, shell: Callable[[str], ToolCall], ours: Callable[[str], ToolCall]
) -> AtOnce:
    """Three turns of `team`'s one agent, `bob`, each a response of two calls that wait `TOGETHER` seconds for each
    other: shell commands that run a script, `cat`s of named pipes, and calls of our query `meet.arrive`, which `ours`
    names under a call's id. Two that meet ran at once; two that each waited alone ran in turn."""
    topology = {**team.topology.canonical(), "grants": [{"who": "role:bob", "ops": "meet.*"}]}
    team = Team.model_validate({**team.canonical(), "extensions": [extension(meeting_of_two())], "topology": topology})
    async with Meeting(root, 2, TOGETHER) as meeting, Pipes(root) as pipes:
        first, second = pipes.commands()
        model.script([[shell(meeting.command("first")), shell(meeting.command("second"))], "ran them"])
        model.script([[shell(first), shell(second)], "read them"])
        model.script([[ours("call_meet_1"), ours("call_meet_2")], "called it"])
        async with Session.start(team, root=root, cwd=root) as session:
            await in_state(session, "bob", "idle")
            await turn(session, "run both commands", 1)
            reading = asyncio.ensure_future(pipes.meet())
            await turn(session, "read both pipes", 2)
            await reading
            await turn(session, "call it twice", 3)

    met, refused = (max(counted(call.json, text) for call in model.calls) for text in (MET, "Refused unavailable"))
    assert meeting.arrived == 2, "a command that runs the script never reached the meeting"
    assert met == 2 or refused >= 2, "a call of ours neither met the other nor was refused"
    return AtOnce(script=meeting.met.is_set(), read=pipes.met, query=met == 2)


def counted(request: object, text: str) -> int:
    """How many times `text` is in a request's strings, as decoded."""
    return sum(found.count(text) for found in strings(request))


async def turn(session: Session, asked: str, count: int) -> None:
    """Ask `bob` something, and wait for its `count`th turn to end."""
    await session.send("@bob", asked)
    await until(lambda: of_type(session, "turn.ended"), session, lambda ended: len(ended) == count)
