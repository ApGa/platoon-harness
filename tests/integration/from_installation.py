"""A harness run from the installation this program runs from, in a sandbox its caller makes, as
`from_installation.py <case> <harness> <folder>`: `make` makes the harness's conformance result there and places it in
`<folder>/root`, as a training system does once for each build, and `start` checks a trainable team of one agent on that
root and starts it, through a gateway FakeModel acts as, until its agent has started or ended. Each case prints what it
found as one JSON object, and the program imports only the SDK."""

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from platoon_harness import Session, Team
from platoon_harness.config import Secret
from platoon_harness.runtime import Admission, AgentOutcome, AgentRef, SpawnRequest
from platoon_harness.runtime.opening import check
from platoon_harness.runtime.paths import write_conformance
from platoon_harness.testing import FakeModel, check_harness


class Training:
    """A training system's authority: each agent through `model` acting as its gateway, on a bearer and a backend id of
    its own."""

    def __init__(self, model: FakeModel) -> None:
        self.model = model

    async def admit(self, spawn: SpawnRequest) -> Admission:
        gateway = self.model.gateway(f"bearer-of-{spawn.agent}")
        return Admission(token=Secret(f"token-of-{spawn.agent}"), access=gateway, backend={"agent_id": spawn.agent})

    async def finish(self, agent: AgentRef, outcome: AgentOutcome) -> None:
        return None


async def make(harness: str, folder: Path) -> dict[str, Any]:
    """The result `check_harness` makes here, as `write_conformance` placed it in the root."""
    result = await check_harness(harness, folder / "check")
    write_conformance(folder / "root", result)
    return result.model_dump(mode="json")


async def start(harness: str, folder: Path) -> dict[str, Any]:
    """What `check` finds in the way of a trainable session on the root, and what its agent's start, or its end, if it
    ended first, recorded."""
    root, cwd = folder / "root", folder / "work"
    cwd.mkdir(exist_ok=True)
    team = Team.model_validate({"roles": {"bob": {"harness": harness, "approvals": "allow"}}})
    problems = [problem.what for problem in check(team, trainable=True, root=root, cwd=cwd) if problem.level == "error"]
    async with FakeModel() as model:
        given: dict[str, Any] = {"principal": "program:trainer", "authority": Training(model), "trainable": True}
        async with Session.start(team, root=root, cwd=cwd, **given) as session:
            ends = ("agent.started", "agent.ended")
            recorded = await anext(event async for event in session.events(follow=True) if event.type in ends)
    return {"problems": problems, recorded.type: recorded.data}


CASES = {"make": make, "start": start}

if __name__ == "__main__":
    print(json.dumps(asyncio.run(CASES[sys.argv[1]](sys.argv[2], Path(sys.argv[3])))))
