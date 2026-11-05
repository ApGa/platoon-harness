"""A read right after a wake, on a real Codex model and its native login, through the public `Session`. Set
`PLATOON_HARNESS_LIVE=1` to run it, and say what ran.

Budget: at most 25 model calls, counted from the journal, `gpt-6-luna` at low effort, under a `turns` limit and a wall
limit, so a runaway stops itself.
"""

import os
import shutil
from pathlib import Path
from typing import Any

import pytest

from platoon_harness import Role, Session, Team
from platoon_harness.team import Budget
from platoon_harness.topology import Topic, Topology

from ..unit.runtime.support import journal
from .support import CODEX, EFFORT, rereads, seeded, seen, spent

pytestmark = [
    pytest.mark.live,
    pytest.mark.timeout(540),
    pytest.mark.skipif(os.environ.get("PLATOON_HARNESS_LIVE") != "1", reason="needs PLATOON_HARNESS_LIVE=1"),
    pytest.mark.skipif(shutil.which("codex") is None, reason="codex is not installed"),
]

WORDS = ("heliotrope", "marigold", "verbena")
MEMO = "Memo {number}: the code word is {word}. Read #memo, then reply with the code word and nothing else."


def team() -> Team:
    """One Codex agent the session starts, so it stays, woken by each memo a person posts."""
    worker = Role(harness="codex", model=CODEX, effort=EFFORT, approvals="deny", sandbox="read-only")
    memo = Topic(writers="human", readers="all", delivery="wake")
    return Team(roles={"w": worker}, topology=Topology(channels={"memo": memo}), budget=Budget(turns=6, wall="5m"))


def empty_reads(events: list[Any]) -> list[dict[str, Any]]:
    """What each of the agent's reads that showed no entry answered, from the outcome its command ended on."""
    return [
        event.outcome.result
        for event in events
        if event.outcome is not None
        and event.outcome.op == "message.read"
        and event.outcome.result is not None
        and event.outcome.result["entries"] == []
    ]


def answers(events: list[Any]) -> list[str]:
    """The last thing the agent said in each of its turns, which is its answer."""
    said: dict[str, str] = {}
    for event in events:
        if event.type == "item.recorded" and event.data["kind"] == "message" and event.turn is not None:
            said[event.turn] = event.gist
    return list(said.values())


async def test_a_codex_agent_woken_by_a_memo_answers_from_it_whatever_a_read_after_the_wake_shows(tmp_path):
    """Budget: at most 25 model calls, counted from the journal. Three memos, each waking the agent and asking it to
    read `#memo`, which its wake has already moved past: each answer is that memo's code word, and every read that found
    nothing new and said so named a memo."""
    work = seeded(tmp_path / "work")
    root = tmp_path / "root"
    async with Session.start(team(), name="live-reads", root=root, cwd=work, plan_login=True) as session:
        for number, word in enumerate(WORDS, start=1):
            await session.send("#memo", MEMO.format(number=number, word=word))
            await seen(session, "turn.ended", count=number, within=150)
        events = await journal(session)
        used = await spent(session)
    keep = Path(os.environ.get("PLATOON_HARNESS_KEEP", tmp_path / "kept"))
    keep.mkdir(parents=True, exist_ok=True)
    for kept in ("journal.sqlite", "manifest.json"):
        shutil.copy(root / "sessions" / "live-reads" / kept, keep / kept)

    found = empty_reads(events)
    said = answers(events)
    print({"spent": used, "rereads": rereads(events), "empty reads": found, "answers": said}, flush=True)

    assert len(said) == len(WORDS) and all(word in answer.lower() for word, answer in zip(WORDS, said, strict=True))
    assert all("channel/memo@" in read["next"] for read in found if "next" in read)
    assert used["total"] <= 25
