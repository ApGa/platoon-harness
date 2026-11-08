"""The join both clients draw a spawn by, over what a kernel records as a session would: a lead's tool items, as its
harness reports them, and the spawns it makes, each under the anchor its harness gave the call, or under none. And a
page of an agent's calls, in the words the page's Tool activity draws, over a session a scripted lead calls tools in."""

import re
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from pathlib import Path
from typing import Any

import pytest

from platoon_harness import Session, Team
from platoon_harness.drivers import AgentSpec
from platoon_harness.kernel import Event, Kernel
from platoon_harness.testing import Call, Do, Hang, ScriptedDriver
from platoon_harness_cli import calls
from platoon_harness_cli.calls import UNJOINED, Join, page
from platoon_harness_cli.provenance import Line

from ..kernel.support import events_of, result_of
from ..primitives.support import agent, report, spawn, start_turn
from ..primitives.test_provenance import tool
from ..runtime.support import harness, of_type, until
from .test_provenance import opened

type Caller = Callable[[str, Mapping[str, Any]], Awaitable[Any]]


@pytest.fixture
async def kernel(tmp_path: Path) -> AsyncIterator[Kernel]:
    found = await opened(tmp_path / "session")
    for name in ("lead", "other"):
        await spawn(found, name, role="lead")
        await start_turn(found, name)
    yield found
    found.close()


def last(kernel: Kernel) -> Event:
    return events_of(kernel)[-1]


async def called(kernel: Kernel, id: str, phase: str = "started", by: str = "lead") -> Event:
    """A tool item of the call `id`, as its agent's harness reports it."""
    await report(kernel, by, "item", kind="tool", phase=phase, gist="agent_spawn", native_id=id)
    return last(kernel)


async def spawned(kernel: Kernel, name: str, native: dict[str, str] | None, by: str = "lead") -> Event:
    """A child its spawner made under the call its anchor, `native`, names, or under none."""
    args = {"name": name, "child_role": "worker", "goal": f"be {name}"}
    result_of(await kernel.submit(agent(by), "agent.spawn", args, native=native))
    return next(event for event in events_of(kernel) if event.type == "agent.spawned" and event.data["name"] == name)


def joined(*events: Event) -> Join[int]:
    """A join of `events`, each held by its seq."""
    join: Join[int] = Join()
    for event in events:
        join.take(event, event.seq)
    return join


async def test_a_spawn_joins_the_call_whose_id_its_anchor_holds(kernel):
    """By its spawner's own tool item, the first of the call's held, and never another agent's under the same id."""
    first, second = await called(kernel, "toolu_1"), await called(kernel, "toolu_2")
    child = await spawned(kernel, "w", tool("toolu_2"))
    ended = await called(kernel, "toolu_2", phase="completed")
    theirs = await spawned(kernel, "x", tool("toolu_1"), by="other")

    join = joined(first, second, child, ended, theirs)

    assert join.call_of(child.seq) == second.seq
    assert join.spawns_of(second.seq) == [child.seq] and join.spawns_of(first.seq) == join.spawns_of(ended.seq) == []
    assert join.call_of(theirs.seq) is None


async def test_a_spawn_no_item_holds_joins_no_known_call_and_says_so(kernel):
    """OpenHands' calls come through the shim and an `exec` harness's through `ph`, each under an id of its own, which
    no item holds, and a call can come with no id at all, as a scripted `Call` step's does."""
    item = await called(kernel, "toolu_1")
    shimmed = await spawned(kernel, "oh", {"platoon-harness/callId": "9f1c2e"})
    unnamed = await spawned(kernel, "nameless", None)

    join = joined(item, shimmed, unnamed)

    assert unnamed.native == {}
    assert join.call_of(shimmed.seq) is None and join.call_of(unnamed.seq) is None
    assert join.spawns_of(item.seq) == []
    assert UNJOINED == "joins no known call"


async def test_a_spawn_recorded_before_its_call_s_item_joins_it_once_the_item_comes(kernel):
    """A harness's report of its item can land after the command it made under that call."""
    child = await spawned(kernel, "w", tool("toolu_1"))
    join = joined(child)
    before = join.call_of(child.seq)

    item = await called(kernel, "toolu_1")
    join.take(item, item.seq)

    assert before is None
    assert join.call_of(child.seq) == item.seq and join.spawns_of(item.seq) == [child.seq]


async def told(spec: AgentSpec, call: Caller) -> None:
    """Two calls of the lead's own, each under an id of its own, as a harness's are."""
    for gist in ("one", "two"):
        await call("message_send", {"to": "@you", "gist": gist})


async def spawning(spec: AgentSpec, call: Caller) -> None:
    """A call of the lead's own that spawns `w1`, under the id it gave it."""
    await call("agent_spawn", {"name": "w1", "child_role": "worker", "goal": "be w1"})


UNANCHORED = Call("agent_spawn", {"name": "w2", "child_role": "worker", "goal": "be w2"})
"""A call that spawns `w2` under no id, as a scripted `Call` step makes one."""


@pytest.fixture
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("PLATOON_HARNESS_HOME", str(tmp_path))
    return tmp_path


def team(*turns: list[Any]) -> Team:
    """`lead`, whose turns are `turns`, each woken by a message, and `worker`, which it may spawn."""
    roles = {
        "lead": {"harness": harness(lambda: ScriptedDriver(turns)), "may_spawn": ["worker"]},
        "worker": {"harness": harness(lambda: ScriptedDriver([[Hang()]])), "count": 0},
    }
    edges = {"lead": ["children", "human"], "worker": ["parent"]}
    return Team.model_validate({"roles": roles, "topology": {"edges": edges, "limits": {"max_hops": 4}}})


async def turned(session: Session, turns: int) -> None:
    """Wake the lead for each of its `turns`, one after another, until each has ended."""
    for turn in range(1, turns + 1):
        await session.send("@lead", f"turn {turn}")
        ended = lambda found, turn=turn: [event.agent for event in found].count("lead") == turn  # noqa: E731
        await until(lambda: of_type(session, "turn.ended"), session, ended)


NO_ID = "no id joins it to its call's other items"


def said(lines: list[Line]) -> list[tuple[str, str]]:
    return [(line.kind, line.text) for line in lines]


async def test_an_agent_s_calls_come_a_page_of_whole_turns_at_a_time_newest_first(root, monkeypatch):
    """A page takes whole turns, as many as `PAGE` calls take, so no call is split from its end or from what it spawned,
    and its cursor reads on from the oldest; the page past the first turn holds none."""
    monkeypatch.setattr(calls, "PAGE", 4)
    async with Session.start(team(*[[Do(told)]] * 3), name="s", root=root, cwd=root) as session:
        await turned(session, 3)
        newest = await page(session, "lead")
        oldest = await page(session, "lead", before=newest.cursor)
        none = await page(session, "lead", before=2)
        starts = [event.seq for event in await of_type(session, "turn.started") if event.agent == "lead"]

    headings = [line.text for line in newest.lines if line.kind == "heading"]
    assert [heading.partition("-")[0] for heading in headings] == ["turn t3", "turn t2"]
    assert all(heading.endswith(": stopped") for heading in headings)
    assert said(newest.lines)[2:4] == [("completed", "message_send called")] * 2
    assert all(line.ref and line.ref.startswith("turn/lead@") for line in newest.lines[1:] if line.kind != "heading")
    assert len(newest.lines) - 1 == len(oldest.lines) * 2 == 6
    assert newest.cursor == starts[1] and oldest.cursor is None
    assert oldest.lines[0].text.startswith("turn t1-")
    assert said(none.lines) == [("", "The journal holds no tool item of @lead's before these.")]


async def test_the_newest_page_says_the_head_it_was_read_at_and_no_tool_item_is_not_no_call(root):
    """What ended after the head a page was read at reads as it stood then, which the page says first; and a journal
    holding no tool item of an agent's is not said to mean it made no call, as a harness may report none."""
    async with Session.start(team([Hang()]), name="s", root=root, cwd=root) as session:
        await session.send("@lead", "turn 1")
        await until(lambda: of_type(session, "turn.started"), session, lambda found: len(found) == 1)
        head = await session.head()
        found = await page(session, "lead", before=head + 1)
        newest = await page(session, "lead")

    assert newest.lines[0].kind == "" and not newest.lines[0].warn
    assert re.fullmatch(
        r"@lead's tool calls read at head [0-9,]+: what ended since reads as it stood then\.", newest.lines[0].text
    )
    assert said(newest.lines)[1:] == [
        (
            "",
            "The journal holds no tool item of @lead's, which is not to say it made no call: a harness may report "
            "none, as `exec`'s does.",
        )
    ]
    assert said(found.lines) == [("", "The journal holds no tool item of @lead's before these.")]


async def test_a_spawn_is_listed_under_the_call_whose_id_its_anchor_holds_or_where_it_stands_joining_none(root):
    """A call is one line, from what its first item says it called with to how its last says it ended. A call that
    came under no id cannot be joined to its end, so each of its items is a line of its own, `unjoined`, saying its own
    phase and never that its call has no end, and what it spawned joins no known call, standing where the journal has
    it."""
    async with Session.start(team([Do(spawning), UNANCHORED]), name="s", root=root, cwd=root) as session:
        await turned(session, 1)
        found = await page(session, "lead")
        spawned = {event.data["name"]: event for event in await of_type(session, "agent.spawned")}

    assert said(found.lines)[2:] == [
        ("unjoined", f"completed: agent_spawn completed · {NO_ID}"),
        ("spawned", f"w2 spawned as worker · {UNJOINED}"),
        ("unjoined", f"started: agent_spawn called · {NO_ID}"),
        ("completed", "agent_spawn called"),
        ("spawned", "↳ w1 spawned as worker"),
    ]
    assert not any(line.warn for line in found.lines)
    assert [line.ref for line in found.lines if line.kind == "spawned"] == [
        f"{event.stream}@{event.version}" for event in (spawned["w2"], spawned["w1"])
    ]
    assert found.cursor is None


async def test_a_turn_of_more_calls_than_a_page_holds_is_listed_in_its_newest_saying_what_prints_the_rest(
    root, monkeypatch
):
    """The page goes on to the turn before it, and what the turn left out is said with the command that prints it."""
    monkeypatch.setattr(calls, "PAGE", 1)
    async with Session.start(team([Do(told)], [Do(spawning), UNANCHORED]), name="s", root=root, cwd=root) as session:
        await turned(session, 2)
        cut = await page(session, "lead")
        before = await page(session, "lead", before=cut.cursor)
        began = [event.seq for event in await of_type(session, "turn.started") if event.agent == "lead"][1]

    assert said(cut.lines)[2:] == [
        ("unjoined", f"completed: agent_spawn completed · {NO_ID}"),
        (
            "",
            "The rest of this turn, 1 call and 1 item under no id before these and what they spawned, is not listed: "
            f"`platoon-harness events s --after {began - 1}` prints it, among the session's other events.",
        ),
    ]
    assert cut.lines[-1].warn and cut.cursor == began
    assert said(before.lines)[1] == ("completed", "message_send called")
    assert before.lines[2].text.startswith("The rest of this turn, 1 call before these and what they spawned, is not")
