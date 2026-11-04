"""Agents asked to cite by the default template, on real models and native logins, through the public `Session`. Set
`PLATOON_HARNESS_LIVE=1` to run these, and say what ran.

Budget: at most 40 model calls in all, 20 on `claude-haiku-5-5` and 20 on `gpt-6-luna` at low effort, counted from the
journal. Every session has a `Budget`, so that a runaway stops itself.
"""

import os
import re
import shutil

import pytest

from platoon_harness import Session, Team
from platoon_harness.primitives import Seen, Unknown
from platoon_harness.team import Budget
from platoon_harness.topology import manager_worker

from ..unit.runtime.support import journal
from .support import CLAUDE, CODEX, EFFORT, spent, tools_called

pytestmark = [
    pytest.mark.live,
    pytest.mark.timeout(420),
    pytest.mark.skipif(os.environ.get("PLATOON_HARNESS_LIVE") != "1", reason="needs PLATOON_HARNESS_LIVE=1"),
]

LIMIT = Budget(turns=8, wall="5m")
ROLES = {
    "claude": {"harness": "claude", "model": CLAUDE},
    "codex": {"harness": "codex", "model": CODEX, "sandbox": "read-only"},
}
SPEC = """# Release checklist

1. Freeze the branch.
2. Run the slow tests.
3. Write the release notes.
"""
ASKED = (
    "The board `notes` holds a checklist named `spec`. Start one worker to read it and report which step comes second, "
    "then tell me that step."
)
WRITES = {
    "message.sent",
    "board.posted",
    "board.revised",
    "task.added",
    "task.completed",
    "task.failed",
    "agent.spawned",
    "agent.finished",
    "agent.ended",
}
"""What the eight writes of content record, each of which takes `based_on`."""
REFUSED_FOR_A_CITATION = re.compile(r"no ref|nothing is|names no lines|names lines|cite it whole|cite fewer refs")
"""What `cited` says when it refuses a write for its citation."""


@pytest.mark.parametrize("harness", ROLES)
async def test_agents_told_by_the_default_template_cite_what_they_were_handed(harness, tmp_path):
    """Budget: at most 20 model calls, counted from the journal. A person posts a checklist, and a lead on the default
    template starts a worker to read it and report, then answers: each citation resolves, at least one names what its
    citer was handed, and the shares of writes that cite, of writes refused for a citation and of citations its citer
    was shown are said."""
    if shutil.which(harness) is None:
        pytest.skip(f"{harness} is not installed")
    role = {**ROLES[harness], "effort": EFFORT, "approvals": "allow"}
    team = Team.model_validate(
        {
            "roles": {"lead": {**role, "may_spawn": ["worker"]}, "worker": role},
            "topology": manager_worker("lead", "worker").model_dump(mode="json"),
            "budget": LIMIT,
        }
    )

    async with Session.start(team, root=tmp_path / "root", cwd=tmp_path, plan_login=True) as session:
        await session.board_post("notes", "spec", "the release checklist", body=SPEC)
        await session.send("@lead", ASKED)
        ending = await session.settled(timeout="4m")
        events = await journal(session)
        writes = [event for event in events if event.type in WRITES and event.actor.startswith("agent:")]
        traced = {
            f"{event.stream}@{event.version}": await session.lineage(f"{event.stream}@{event.version}")
            for event in writes
        }
        used = await spent(session)
        print(session.folder, ending.reason, used, sorted((await tools_called(session)).items()))

    refused = [
        event
        for event in events
        if event.type == "op.refused"
        and event.actor.startswith("agent:")
        and REFUSED_FOR_A_CITATION.search(str(event.outcome and event.outcome.refusal and event.outcome.refusal.detail))
    ]
    citations = [(ref, cited) for ref, found in traced.items() for cited in found.declared]
    shown = [cited for _, cited in citations if isinstance(cited.exposure, Seen)]
    handed = [
        cited
        for _, cited in citations
        if isinstance(cited.exposure, Seen) or (isinstance(cited.exposure, Unknown) and cited.exposure.handed)
    ]
    for ref, cited in citations:
        print("cites:", ref, "->", cited.ref, cited.maker, cited.exposure and cited.exposure.answer)
    citing = [event for event in writes if event.based_on]
    print(
        f"writes {len(writes)}, citing {len(citing)}, refused for a citation {len(refused)} of "
        f"{len(writes) + len(refused)} attempts, citations {len(citations)}, seen {len(shown)}, handed {len(handed)}"
    )

    assert all(
        len(found.declared) == len(event.based_on)
        for event in writes
        for found in [traced[f"{event.stream}@{event.version}"]]
    )
    assert handed, "no write cited what its agent was handed"
    assert used["total"] <= 20
