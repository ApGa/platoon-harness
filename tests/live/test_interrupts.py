"""An interrupt during a model call under a `tokens` limit, on real models and native logins, through the public
`Session`. Set `PLATOON_HARNESS_LIVE=1` to run these, and say what ran.

Budget: at most 10 model calls in all, 5 a test, `claude-haiku-5-5` or `gpt-6-luna` at low effort, counted from the
journal. Every session has a `Budget`, so that a runaway stops itself.
"""

import os
import shutil

import pytest

from platoon_harness import Role, Session, Team
from platoon_harness.team import Budget

from ..unit.runtime.support import in_state
from .support import CLAUDE, CODEX, EFFORT, seeded, seen, spent

pytestmark = [
    pytest.mark.live,
    pytest.mark.timeout(240),
    pytest.mark.skipif(os.environ.get("PLATOON_HARNESS_LIVE") != "1", reason="needs PLATOON_HARNESS_LIVE=1"),
]

ESTIMATE = 200_000
LIMIT = Budget(tokens=2_000_000, estimate={"tokens": ESTIMATE}, turns=4, wall="3m")
ROLES = {
    "claude": Role(harness="claude", model=CLAUDE, effort=EFFORT, approvals="deny"),
    "codex": Role(harness="codex", model=CODEX, effort=EFFORT, approvals="deny", sandbox="read-only"),
}
LONG = "Write a story of about four hundred words about a lighthouse keeper. Use no tools."


@pytest.mark.parametrize("harness", ROLES)
async def test_an_interrupt_during_a_call_under_a_tokens_limit_leaves_the_session_to_go_on(harness, tmp_path):
    """Budget: at most 5 model calls, counted from the journal. The agent is interrupted as its turn begins, while its
    first call is under way, which no harness measures. The turn is charged its estimate, labelled `estimated`, the
    next message wakes it under the same limit, and the session settles."""
    if shutil.which(harness) is None:
        pytest.skip(f"{harness} is not installed")
    team = Team(roles={"ada": ROLES[harness]}, budget=LIMIT)

    async with Session.start(team, root=tmp_path / "root", cwd=seeded(tmp_path / "work"), plan_login=True) as session:
        print("session", session.folder)
        await in_state(session, "ada", "idle")
        await session.send("@ada", LONG)
        await seen(session, "turn.started")
        stopped = await session.interrupt("@ada")
        await seen(session, "turn.ended")
        cut = next(row for row in await session.budgets() if row["unit"] == "tokens")
        await session.send("@ada", "Reply with the single word ready, and nothing else.")
        ending = await session.settled(timeout="2m")
        ended = await seen(session, "turn.ended", count=2)
        refused = await seen(session, "wake.refused", count=0)
        used = await spent(session)

    print("stopped:", stopped, "cut:", cut, "usage:", ending.usage, "spent:", used)
    assert stopped == {"stopped": ["@ada"]}
    assert [event.data["reason"] for event in ended] == ["interrupted", "stopped"]
    assert (cut["label"], cut["unmeasured"]) == ("estimated", 1) and cut["spent"] >= ESTIMATE
    assert refused == []
    assert ending.reason == "settled"
    assert (ending.usage["tokens"]["label"], ending.usage["tokens"]["unmeasured"]) == ("estimated", 1)
    assert used["total"] <= 5
