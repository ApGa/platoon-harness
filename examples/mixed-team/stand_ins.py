"""Scripted stand-ins for the mixed team's harnesses, which do what job.md asks with no model at all. With this folder
on `PYTHONPATH`, a role whose harness is `stand_ins:lead` or `stand_ins:worker` runs one."""

from platoon_harness.testing import Call, ScriptedDriver

NOTE = "board/notes/risks@1"
"""The ref of the worker's note: the first version of `risks` on the board `notes`."""
TASK = {"queue": "tasks", "gist": "list three risks of caching DNS answers", "based_on": ["inbox/lead@1"]}
LEAD = [
    [
        Call("task_add", TASK),
        Call("agent_spawn", {"name": "w", "child_role": "worker", "goal": "Take the task on the queue tasks."}),
    ],
    [
        Call("board_get", {"board": "notes", "name": "risks"}),
        Call("agent_finish", {"gist": "Three risks of caching DNS answers are on the board.", "based_on": [NOTE]}),
    ],
]
"""What the lead does in place of a model, a list per turn: the job's task, a worker, a finish citing a note."""
WORKER = [
    [
        Call("task_claim", {"queue": "tasks"}),
        Call(
            "board_post", {"board": "notes", "name": "risks", "gist": "stale, poisoned", "based_on": ["task/tasks/1@1"]}
        ),
        Call("task_complete", {"queue": "tasks", "gist": "noted as risks", "based_on": [NOTE]}),
        Call("agent_finish", {"gist": "The risks are on the board as risks.", "based_on": [NOTE]}),
    ],
]
"""What its worker does: the task claimed, a note citing it, and a result and a report citing the note."""


def lead() -> ScriptedDriver:
    return ScriptedDriver(LEAD)


def worker() -> ScriptedDriver:
    return ScriptedDriver(WORKER)
