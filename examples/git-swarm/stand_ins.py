"""Scripted stand-ins for the GitSwarm workers, which do what run.py's goal asks with git and no model at all. A role
whose harness is `stand_ins:worker` runs one: a `ScriptedDriver` whose every turn is one `Do` step, the code its
worker's name picks, as the population names its workers `worker-1`, `worker-2` and on. They show the flow: a
contribution, a second built on it by the SHA its outcome records, a nomination of that commit by the ref `repo.commit`
gives for it, and an abstention, each waiting on the entry of `outcomes` it rests on. Each runs in the runtime's own
process, so none shows what a harness's sandbox or approvals stop, or what a real model would choose."""

import asyncio
import itertools
import json
import subprocess
from collections.abc import Awaitable, Callable, Mapping
from pathlib import Path
from typing import Any

from platoon_harness.drivers import AgentSpec
from platoon_harness.testing import Do, ScriptedDriver

type Caller = Callable[[str, Mapping[str, Any]], Awaitable[Any]]
"""What a `Do` step's code calls a tool with: its name and arguments, for its MCP result."""

FIZZBUZZ = """\
def fizzbuzz(n: int) -> str:
    return "Fizz" * (n % 3 == 0) + "Buzz" * (n % 5 == 0) or str(n)
"""
TEST = """\
import unittest

from fizzbuzz import fizzbuzz


class FizzBuzzTest(unittest.TestCase):
    def test_it_says_fizz_buzz_or_the_number(self):
        self.assertEqual([fizzbuzz(n) for n in (3, 5, 15, 16)], ["Fizz", "Buzz", "FizzBuzz", "16"])
"""


def answer(result: Any) -> Any:
    """What one of our tools answered, from its MCP result."""
    return json.loads(result["content"][0]["text"])


async def git(*args: str, cwd: Path) -> None:
    await asyncio.to_thread(subprocess.run, ["git", *args], cwd=cwd, check=True, capture_output=True)


async def commit(cwd: Path, name: str, text: str, message: str) -> None:
    """Write a file and commit it on the worker's own branch, as its own git would."""
    (cwd / name).write_text(text)
    await git("add", name, cwd=cwd)
    await git("commit", "-q", "-m", message, cwd=cwd)


async def recorded(call: Caller, peer: str) -> dict[str, Any] | None:
    """A peer's entry on `outcomes`, once the program has recorded it. Until then None, with a wait for it parked, so
    the turn ends and the runtime starts the next once the entry is there."""
    if answer(await call("wait", {"board": [f"outcomes/{peer}"], "after": 0}))["state"] != "released":
        return None
    return answer(await call("board_get", {"board": "outcomes", "name": peer}))


async def contribute(spec: AgentSpec, call: Caller) -> None:
    """`fizzbuzz.py`, committed with no test."""
    await commit(spec.cwd, "fizzbuzz.py", FIZZBUZZ, "Add fizzbuzz.py")
    await call("agent_finish", {"gist": "Committed fizzbuzz.py, with no test yet."})


async def build_on(spec: AgentSpec, call: Caller) -> None:
    """worker-1's contribution, checked out on this worker's own branch by the SHA its outcome records, and a test
    committed on it."""
    if (entry := await recorded(call, "worker-1")) is None:
        return
    await git("reset", "-q", "--hard", entry["fields"]["sha"], cwd=spec.cwd)
    await commit(spec.cwd, "test_fizzbuzz.py", TEST, "Test fizzbuzz.py")
    gist = "Committed a test of fizzbuzz.py on worker-1's commit."
    await call("agent_finish", {"gist": gist, "based_on": [entry["ref"]]})


async def nominate(spec: AgentSpec, call: Caller) -> None:
    """worker-2's commit, which does all the goal asks, nominated by the ref `repo.commit` gives for the SHA its outcome
    records."""
    if (entry := await recorded(call, "worker-2")) is None:
        return
    made = answer(await call("repo_commit", {"sha": entry["fields"]["sha"]}))
    await call("message_send", {"to": "#nominations", "gist": "fizzbuzz.py and its test", "based_on": [made["ref"]]})
    gist = "Nominated worker-2's commit, which does all the goal asks."
    await call("agent_finish", {"gist": gist, "based_on": [made["ref"]]})


async def abstain(spec: AgentSpec, call: Caller) -> None:
    """Nothing, once worker-3's nomination is recorded, as it does all the goal asks."""
    if (entry := await recorded(call, "worker-3")) is None:
        return
    gist = "Nothing to add: worker-3 nominated a commit that does all the goal asks."
    await call("agent_finish", {"gist": gist, "based_on": [entry["ref"]]})


PLANS = {"worker-1": contribute, "worker-2": build_on, "worker-3": nominate}
"""What each worker does, by its name. Any other abstains."""


async def turn(spec: AgentSpec, call: Caller) -> None:
    await PLANS.get(spec.agent, abstain)(spec, call)


def worker() -> ScriptedDriver:
    return ScriptedDriver(itertools.repeat([Do(turn)]))
