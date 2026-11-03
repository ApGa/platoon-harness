"""Real teams on real models, on native logins, through the public `Session`. Set `PLATOON_HARNESS_LIVE=1` to run these,
and say what ran.

Budget: at most 219 model calls in all, each test stating its own, all `claude-haiku-5-5` or `gpt-6-luna` at low effort.
Every session has a `Budget`, so that a runaway stops itself.
"""

import asyncio
import os
import shutil
import time

import pytest

from platoon_harness import Role, Session, Team
from platoon_harness.config import Secret
from platoon_harness.drivers.process import Record
from platoon_harness.team import Budget
from platoon_harness.topology import manager_worker

from ..unit.runtime.support import journal, of_type
from .support import (
    CLAUDE,
    CODEX,
    EFFORT,
    Recording,
    gone,
    leaks,
    running_in,
    seeded,
    seen,
    spent,
    tests_pass,
    tools_called,
    touched,
)

pytestmark = [
    pytest.mark.live,
    pytest.mark.timeout(540),
    pytest.mark.skipif(os.environ.get("PLATOON_HARNESS_LIVE") != "1", reason="needs PLATOON_HARNESS_LIVE=1"),
    pytest.mark.skipif(shutil.which("claude") is None, reason="claude is not installed"),
]

LIMIT = Budget(turns=30, tokens=6_000_000, wall="4m", estimate={"tokens": 500_000})
SETTLE = "60s"


def claude(**fields) -> Role:
    return Role(harness="claude", model=CLAUDE, effort=EFFORT, **{"approvals": "allow", **fields})


def codex(**fields) -> Role:
    return Role(
        harness="codex", model=CODEX, effort=EFFORT, **{"approvals": "allow", "sandbox": "workspace-write", **fields}
    )


async def test_a_lead_and_two_workers_fix_a_seeded_bug(tmp_path):
    """Budget: at most 60 model calls, counted from the journal. The lead is given the job in plain words, by a human
    message, with nothing beyond the preamble on how to coordinate, and a second message while they work."""
    work = seeded(tmp_path / "work")
    team = Team(
        roles={"lead": claude(may_spawn=("worker",)), "worker": claude()},
        topology=manager_worker("lead", "worker"),
        budget=LIMIT,
    )

    async with Session.start(team, name="m1", root=tmp_path / "root", cwd=work, plan_login=True) as session:
        await session.send(
            "@lead",
            "`python3 -m unittest` fails in this repository, which has two bugs. Put one task per bug on the queue "
            "`tasks`, start two workers to claim them, and finish when both are fixed.",
        )
        await seen(session, "task.claimed")
        await session.send("@lead", "When it is fixed, leave a one-line summary as `summary` on the board `notes`.")
        ending = await session.settled(timeout=SETTLE)
        used = await spent(session)
        tools = await tools_called(session)
        claimed = await of_type(session, "task.claimed")
        completed = await of_type(session, "task.completed")
        posted = await of_type(session, "board.posted")
        print(ending.reason, used, sorted(tools.items()))

    assert ending.reason == "settled", ending
    assert tests_pass(work)
    assert len(claimed) == 2 and len(completed) == 2
    assert [event.gist for event in posted if "summary" in str(event.data)]
    assert used["total"] <= 60


async def test_a_claude_lead_and_a_codex_worker_fix_a_seeded_bug(tmp_path):
    """Budget: at most 45 model calls, counted from the journal. As above, with one worker on another harness."""
    work = seeded(tmp_path / "work")
    team = Team(
        roles={"lead": claude(may_spawn=("worker",)), "worker": codex()},
        topology=manager_worker("lead", "worker"),
        budget=LIMIT,
    )

    async with Session.start(team, name="mixed", root=tmp_path / "root", cwd=work, plan_login=True) as session:
        await session.send(
            "@lead",
            "`python3 -m unittest` fails in this repository, which has two bugs. Put one task per bug on the queue "
            "`tasks`, start one worker to claim and fix them both, and finish when both are fixed.",
        )
        await seen(session, "task.claimed")
        await session.send("@lead", "When it is fixed, leave a one-line summary as `summary` on the board `notes`.")
        ending = await session.settled(timeout=SETTLE)
        used = await spent(session)
        tools = await tools_called(session)
        completed = await of_type(session, "task.completed")
        print(ending.reason, used, sorted(tools.items()))

    assert ending.reason == "settled", ending
    assert tests_pass(work)
    assert len(completed) == 2
    assert used["total"] <= 45


async def test_a_lead_waits_on_three_workers_in_one_turn(tmp_path):
    """Budget: at most 30 model calls, counted from the journal. What it states is how many turns the lead took."""
    work = seeded(tmp_path / "work")
    team = Team(
        roles={"lead": claude(may_spawn=("worker",)), "worker": claude()},
        topology=manager_worker("lead", "worker"),
        budget=LIMIT,
    )

    async with Session.start(team, name="join", root=tmp_path / "root", cwd=work, plan_login=True) as session:
        await session.send(
            "@lead",
            "Start three workers. Each must create one empty file named after itself, and do nothing else. When all "
            "three have ended, say which files exist, and finish.",
        )
        ending = await session.settled(timeout=SETTLE)
        used = await spent(session)
        tools = await tools_called(session)
        parked = await of_type(session, "agent.parked")
        print(ending.reason, used, sorted(tools.items()), len(parked))

    assert ending.reason == "settled", ending
    assert used["turns"]["lead"] == 2, "one turn to start them, and one wake for all three"
    assert used["total"] <= 30


async def test_a_refused_finish_is_understood(tmp_path):
    """Budget: at most 20 model calls, counted from the journal. The lead is told to finish over a child at work, which
    the runtime refuses, naming the child and what to do."""
    work = seeded(tmp_path / "work")
    team = Team(
        roles={"lead": claude(may_spawn=("worker",)), "worker": claude()},
        topology=manager_worker("lead", "worker"),
        budget=LIMIT,
    )

    async with Session.start(team, name="refused", root=tmp_path / "root", cwd=work, plan_login=True) as session:
        await session.send(
            "@lead",
            "Start one worker whose goal is to run `sleep 20 && touch slow.txt` in the shell. Do not wait for it: "
            "as soon as it is started, finish.",
        )
        ending = await session.settled(timeout=SETTLE)
        events = await journal(session)
        used = await spent(session)
        tools = await tools_called(session)
        refused = [event for event in events if event.type == "op.refused" and "agent.finish" in event.gist]
        print(ending.reason, used, sorted(tools.items()), [event.data for event in refused])

    assert refused, "the finish was never refused"
    assert (work / "slow.txt").exists(), "the worker was cut off"
    assert used["total"] <= 20


async def test_an_agent_the_session_started_stays_unless_told_to_finish(tmp_path):
    """Budget: at most 8 model calls, counted from the journal. The preamble says two things to an agent nobody spawned,
    and each has cost something when a model read it otherwise."""
    work = seeded(tmp_path / "work")
    team = Team(roles={"stays": claude(), "goes": claude()}, budget=LIMIT)

    async with Session.start(team, name="roots", root=tmp_path / "root", cwd=work, plan_login=True) as session:
        await session.send("@stays", "Use the Bash tool to run this once: touch stays.txt")
        await session.send("@goes", "Use the Bash tool to run this once: touch goes.txt. Then finish.")
        await seen(session, "turn.ended", count=2)
        ended = await of_type(session, "agent.ended")
        used = await spent(session)
        tools = await tools_called(session)
        print(used, sorted(tools.items()), [event.gist for event in ended])

    assert [event.agent for event in ended] == ["goes"]
    assert used["total"] <= 8


async def test_an_approval_on_ask_runs_and_one_on_deny_does_not(tmp_path):
    """Budget: at most 25 model calls, counted from the journal, across three agents, one on `ask` and two on `deny`."""
    work = seeded(tmp_path / "work")
    roles = {
        "asks": claude(approvals="ask"),
        "denied": claude(approvals="deny"),
        "codex_denied": codex(approvals="deny", sandbox="read-only"),
    }
    team = Team(roles=roles, budget=LIMIT)

    async with Session.start(team, name="approve", root=tmp_path / "root", cwd=work, plan_login=True) as session:
        await session.send("@asks", "Use the Bash tool to run exactly this command, once: touch asked.txt")
        asked = (await seen(session, "approval.requested"))[0]
        rows = await session.approvals()
        await session.resolve(rows[0]["id"], "allow", expected_version=rows[0]["version"])
        await seen(session, "turn.ended")

        await session.send("@denied", "Use the Bash tool to run exactly this command, once: touch denied.txt")
        await seen(session, "turn.ended", count=2)

        await session.send(
            "@codex_denied",
            "Your shell tool can run this if you ask for it: run it once, with sandbox_permissions set to "
            "require_escalated and a one-word justification, then reply: gamma. The command: touch codex_denied.txt",
        )
        await seen(session, "turn.ended", count=3)
        events = await journal(session)
        used = await spent(session)
        tools = await tools_called(session)
        print(used, sorted(tools.items()))
        print([(event.agent, event.type, event.gist[:80]) for event in events if event.type.startswith("approval.")])
        print([(event.agent, event.gist[:200]) for event in events if event.type == "item.recorded"])

    assert asked.agent == "asks"
    assert (work / "asked.txt").exists()
    assert not (work / "denied.txt").exists()
    assert not (work / "codex_denied.txt").exists()
    assert used["total"] <= 25


async def test_a_native_child_runs_inside_the_turn_that_started_it(tmp_path):
    """Budget: at most 15 model calls, counted from the journal, with a child's own calls on top, which reach us only as
    a total. The child runs on the parent's model."""
    work = seeded(tmp_path / "work")
    team = Team(roles={"ada": claude().model_copy(update={"allow_native_children": True})}, budget=LIMIT)

    async with Session.start(team, name="child", root=tmp_path / "root", cwd=work, plan_login=True) as session:
        await session.send(
            "@ada",
            "Use your Agent tool once, with subagent_type general-purpose, to have a subagent run `sleep 8 && touch "
            "child.txt` in the shell and say it is done. Do nothing else yourself, then reply: done",
        )
        seen_child = (await seen(session, "child.seen"))[0]
        during = await session.status()
        await seen(session, "turn.ended")
        ending = await session.ending()
        events = await journal(session)
        used = await spent(session)
        tools = await tools_called(session)
        print(used, sorted(tools.items()), during, ending.gaps)
        print([(event.type, event.gist[:120]) for event in events if event.type in ("child.seen", "gap.recorded")])

    assert "open_turn" in during["blockers"], "a live child sits inside an open turn"
    assert seen_child.agent == "ada"
    assert (work / "child.txt").exists()
    assert used["total"] <= 15


async def test_an_interrupt_stops_a_native_child(tmp_path):
    """Budget: at most 8 model calls, counted from the journal, with a child's own on top. An open turn covers a child
    only if a child cannot outlive that turn, so this interrupts one during its shell tool, and looks for what it would
    have done."""
    work = seeded(tmp_path / "work")
    team = Team(roles={"ada": claude().model_copy(update={"allow_native_children": True})}, budget=LIMIT)

    async with (
        Session.start(team, name="cut", root=tmp_path / "root", cwd=work, plan_login=True) as session,
        touched(work / "begun.txt") as begun,
    ):
        await session.send(
            "@ada",
            "Use your Agent tool once, with subagent_type general-purpose, to have a subagent run `touch begun.txt && "
            "sleep 12 && touch child.txt` in the shell. Do nothing else yourself, then reply: done",
        )
        await begun.read()
        await session.interrupt("@ada")
        ended = (await seen(session, "turn.ended"))[0]
        record = Record.read(session.folder / "agents" / "ada")
        assert record is not None
        interrupted = time.monotonic()
        async with asyncio.timeout(10.0):
            await gone(*(pid for pid in running_in(work) if pid != record.pid))
        print(f"the tool had gone {time.monotonic() - interrupted:.2f} s after the turn ended")
        used = await spent(session)
        await session.send("@ada", "Say which files you can see in this directory, by `ls`.")
        await seen(session, "turn.ended", count=2)
        used = await spent(session)
        print(used, sorted(path.name for path in work.iterdir()))

    assert ended.data["reason"] == "interrupted"
    assert not (work / "child.txt").exists()
    assert used["total"] <= 8


async def test_nothing_a_session_held_is_left_in_its_folder(tmp_path):
    """Budget: at most 8 model calls, counted from the journal. A script in the repository prints the agent's token,
    plain and in base64, so the masks are met by what a real harness reports. Asked outright, a model declines."""
    work = seeded(tmp_path / "work")
    team = Team(roles={"ada": claude()}, budget=LIMIT)
    authority, root = Recording(team), tmp_path / "root"
    async with Session.start(team, name="leak", root=root, cwd=work, plan_login=True, authority=authority) as session:
        owner = Secret((session.folder / "owner.token").read_text())
        view = Secret((session.folder / "view.token").read_text())
        await session.send("@ada", "Run `sh report.sh` once in the shell. Then reply: done")
        await seen(session, "turn.ended")
        used = await spent(session)
        folder = session.folder

    found = leaks(folder, owner, view, *authority.tokens)
    print(used, found)
    assert authority.tokens
    assert found == []
    assert used["total"] <= 8
