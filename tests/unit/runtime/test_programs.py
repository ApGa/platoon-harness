"""A program is a script that owns its session as `program:<name>`: it keeps nothing that must survive a restart, and is
run again on the session after a crash, where the keys of its commands make each one op."""

import json
from collections.abc import Iterable, Iterator, Sequence
from typing import Any

import pytest

from platoon_harness import Refused, Session, Team
from platoon_harness.testing import ScriptedDriver

from .support import harness, of_type
from .test_recovery import abandon

pytestmark = pytest.mark.timeout(30)

PATHS = ["src/cart.py", "src/auth.py", "src/pay.py"]


class Reviewer(ScriptedDriver):
    """A reviewer: its one turn claims each open task on `reviews` by its id and completes it, saying it read the
    path."""

    def __init__(self) -> None:
        super().__init__([[]])

    async def _walk(self, steps: Sequence[Any]) -> str:
        listed = await self._call("task_list", {"queue": "reviews", "state": "open"})
        for task in json.loads(listed["content"][0]["text"])["tasks"]:
            path = task["gist"].removeprefix("review ")
            await self._call("task_claim", {"queue": "reviews", "task": task["id"]})
            await self._call("task_complete", {"queue": "reviews", "task": task["id"], "gist": f"read {path}"})
        return "stopped"


def reviews() -> Team:
    """A queue only the program adds to, and a role nothing starts but the program, under `until = "program"`."""
    queue = {"kind": "queue", "writers": "program", "readers": "role:reviewer"}
    topology = {"until": "program", "channels": {"reviews": queue}}
    return Team.model_validate({"roles": {"reviewer": {"harness": harness(Reviewer), "count": 0}}, "topology": topology})


async def review(session: Session, paths: Iterable[str]) -> dict[str, str]:
    """A program: a task on `reviews` for each path, a reviewer to do them, and the session closed once each is done,
    giving what each came to. Each command's key says what it is for, so run again it acts once."""

    async def once(key: str, op: str, **args: Any) -> Any:
        outcome = await session.submit(op, key=key, **args)
        if outcome.refusal is not None:
            raise Refused.of(outcome.refusal)
        return outcome.result

    added = [await once(f"add {path}", "task.add", queue="reviews", gist=f"review {path}") for path in paths]
    await once("spawn", "agent.spawn", name="reviewer", child_role="reviewer", goal="Review each task on `reviews`.")
    await session.wait(tasks=[f"reviews/{task['task']}" for task in added])
    done = await session.task_list("reviews")
    await once("close", "session.close")
    return {task["gist"]: task["result"] for task in done["tasks"]}


class Crashed(Exception):
    """The program's process, gone."""


def crashing(paths: Sequence[str], after: int) -> Iterator[str]:
    """`paths`, until the program asks for the one past `after`, where its process dies."""
    yield from paths[:after]
    raise Crashed


async def test_a_program_run_again_after_a_crash_adds_nothing_twice(tmp_path):
    session = await Session.start(reviews(), name="s", principal="program:reviews", root=tmp_path)
    with pytest.raises(Crashed):
        await review(session, crashing(PATHS, after=2))
    before = [event.gist for event in await of_type(session, "task.added")]
    await abandon(session)

    async with Session.resume("s", root=tmp_path) as session:
        came_to = await review(session, PATHS)
        added = [event.gist for event in await of_type(session, "task.added")]
        spawned = await of_type(session, "agent.spawned")
        closed = await of_type(session, "session.closed")

    assert before == ["review src/cart.py", "review src/auth.py"]
    assert added == [f"review {path}" for path in PATHS]
    assert came_to == {f"review {path}": f"read {path}" for path in PATHS}
    assert len(spawned) == 1 and len(closed) == 1
    assert {event.actor for event in closed} == {"program:reviews"}
