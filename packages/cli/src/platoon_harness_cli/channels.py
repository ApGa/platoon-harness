"""A queue's tasks and a board's entries, which the terminal and the browser say alike: each task's state, who holds it
and until when its lease holds, and each entry with every version of it, as `task.list` and `board.query` give them,
read a page at a time, each line with the acts that open an op's form filled in with what the line knows. A channel is
named by its stream, `queue/<name>` or `board/<name>`."""

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

from platoon_harness import Session
from platoon_harness.kernel import Event

from .review import Part, Tone, clock

MOST = 256
"""The most tasks or versions a view reads, a page at a time: past them it says how many more there are, and what reads
them."""
STATES: dict[str, Tone] = {"open": "", "claimed": "warn", "done": "good", "failed": "bad", "dead": "bad"}
"""How each state of a task is drawn."""


@dataclass(frozen=True)
class Act:
    """What a person may do from a line: its `label`, the `op` it runs, and the `args` the line knows, with which that
    op's form opens filled in, the rest left to the person."""

    label: str
    op: str
    args: Mapping[str, Any]


@dataclass(frozen=True)
class Line:
    """One line of a channel's view: a `task`, an `entry`, one `version` of an entry, how many `more` there are than
    the view read, or `nothing` yet. Its words, in parts each with its tone; its `key`, the ref of the task or the
    version, or the entry's stream, or None; and the acts a person may take from it."""

    kind: Literal["task", "entry", "version", "more", "nothing"]
    parts: tuple[Part, ...]
    key: str | None = None
    acts: tuple[Act, ...] = ()


@dataclass(frozen=True)
class View:
    """A queue's tasks or a board's entries: its `title`, its `lines`, and the `acts` on the channel itself."""

    title: str
    lines: tuple[Line, ...]
    acts: tuple[Act, ...]


def moves(channel: str, event: Event) -> bool:
    """Whether `event` moves what the view of `channel` reads: an event on a stream of its tasks' or its entries', or
    for a queue an agent's end, which gives back each task the agent held with no event on that task's stream."""
    kind, _, name = channel.partition("/")
    if kind == "queue":
        return event.stream.startswith(f"task/{name}/") or event.type == "agent.ended"
    return event.stream.startswith(f"board/{name}/")


async def read(session: Session, channel: str, person: str) -> View:
    """The view of `channel`, oldest first, read a page at a time up to `MOST`, with the acts each line offers `person`,
    by name, who reads it: a task they hold takes what only its holder may do."""
    kind, _, name = channel.partition("/")
    if kind == "queue":
        return await _tasks(session, name, f"@{person}")
    return await _entries(session, name)


async def _tasks(session: Session, queue: str, holder: str) -> View:
    tasks: list[dict[str, Any]] = []
    total, cursor = 0, 0
    while cursor is not None and len(tasks) < MOST:
        page = await session.task_list(queue, after=cursor)
        tasks += page["tasks"]
        total, cursor = page["total"], page["cursor"]
    lines = [_task(queue, task, holder) for task in tasks]
    command = f"platoon-harness task list {session.name} --queue {queue}"
    lines += _more(total - len(tasks), cursor, command)
    nothing = Line("nothing", (("No tasks yet.", "faint"),))
    return View(f"Tasks on {queue}", tuple(lines or [nothing]), (Act("Add a task", "task.add", {"queue": queue}),))


def _task(queue: str, task: Mapping[str, Any], holder: str) -> Line:
    """A task's line: its id, its state, by whom it is claimed, which attempt that is and until when its lease holds,
    its gist and its result, with what a person may do from it."""
    state, attempts = task["state"], task["attempts"]
    if state == "claimed":
        said = f"claimed by {task['owner']}, attempt {attempts}, lease until {clock(task['lease_until'])}"
    elif state == "dead":
        said = f"dead after {_some(attempts, 'attempt')}"
    elif state != "done" and attempts:
        said = f"{state}, {_some(attempts, 'attempt')}"
    else:
        said = state
    parts: tuple[Part, ...] = (
        (f"task {task['id']}", "strong"),
        (f"  {said}", STATES[state]),
        (f"  {task['gist']}", ""),
        *(((f"  → {task['result']}", "faint"),) if task["result"] is not None else ()),
    )
    held = {"queue": queue, "task": task["id"], "fence": task["fence"]}
    acts: tuple[Act, ...] = ()
    if state in ("open", "failed"):
        acts = (Act("Claim", "task.claim", {"queue": queue, "task": task["id"]}),)
    elif state == "claimed" and task["owner"] == holder:
        acts = tuple(Act(label, f"task.{label.lower()}", held) for label in ("Complete", "Fail", "Release", "Renew"))
    elif state == "dead":
        acts = (Act("Add it again", "task.add", {"queue": queue, "based_on": [task["ref"]]}),)
    return Line("task", parts, task["ref"], acts)


async def _entries(session: Session, board: str) -> View:
    versions: list[dict[str, Any]] = []
    total, cursor = 0, 0
    while cursor is not None and len(versions) < MOST:
        page = await session.board_query(board, history=True, after=cursor, limit=32)
        versions += page["results"]
        total, cursor = page["total"], page["cursor"]
    entries: dict[str, list[dict[str, Any]]] = {}
    for version in versions:
        entries.setdefault(version["name"], []).append(version)
    command = f"platoon-harness board query {session.name} --board {board} --history"
    more = _more(total - len(versions), cursor, command)
    lines = [line for name, held in entries.items() for line in _entry(board, name, held, cut=bool(more))]
    lines += more
    nothing = Line("nothing", (("No entries yet.", "faint"),))
    return View(
        f"Entries on {board}", tuple(lines or [nothing]), (Act("Post an entry", "board.post", {"board": board}),)
    )


def _entry(board: str, name: str, versions: list[dict[str, Any]], *, cut: bool) -> list[Line]:
    """An entry's line, with how many versions it has, then a line for each, oldest first: who wrote it, its gist and
    its fields. Revise opens filled in with the version it revises and that version's fields, as a version replaces
    them whole, so a person who changes one keeps the others. Where the read was `cut`, a version of any entry may lie
    past where it stopped, as versions come in the order they were written, so the line says its versions may not be
    all and offers no Revise, which would revise one that may not be the latest."""
    key, count = f"board/{board}/{name}", f"  {_some(len(versions), 'version')}"
    if cut:
        said = f"{count} read before the view stopped, maybe not all, so no Revise is offered"
        lines = [Line("entry", ((name, "strong"), (said, "warn")), key)]
    else:
        latest = versions[-1]
        fields = {"fields": latest["fields"]} if latest["fields"] else {}
        revised = {"board": board, "name": name, "expected_version": latest["version"], **fields}
        lines = [Line("entry", ((name, "strong"), (count, "faint")), key, (Act("Revise", "board.revise", revised),))]
    for version in versions:
        parts: tuple[Part, ...] = (
            (f"v{version['version']}", "faint"),
            (f"  {version['author']}", ""),
            (f"  {version['gist']}", ""),
            *(((f"  {_json(version['fields'])}", "faint"),) if version["fields"] else ()),
        )
        lines.append(Line("version", parts, version["ref"]))
    return lines


def _more(more: int, cursor: int | None, command: str) -> list[Line]:
    """How many more there are than the view read, and the command that reads on from where it stopped."""
    if cursor is None or more <= 0:
        return []
    return [Line("more", ((f"{more} more past these, which `{command} --after {cursor}` reads", "faint"),))]


def _some(count: int, what: str) -> str:
    return f"{count} {what}{'' if count == 1 else 's'}"


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
