"""What an agent is launched with, on real models and native logins, through the public `Session`. Set
`PLATOON_HARNESS_LIVE=1` to run these, and say what ran.

Budget: at most 28 model calls in all, each test stating its own, `claude-haiku-5-5` or `gpt-6-luna` at low effort.
Every session has a `Budget`, so that a runaway stops itself.
"""

import os
import shutil

import pytest

from platoon_harness import Role, Session, Team
from platoon_harness.team import Budget
from platoon_harness.tools import PREAMBLE

from ..unit.runtime.support import in_state, journal
from .support import CLAUDE, CODEX, EFFORT, empty_waits, rereads, seeded, seen, spent, tools_called

pytestmark = [
    pytest.mark.live,
    pytest.mark.timeout(240),
    pytest.mark.skipif(os.environ.get("PLATOON_HARNESS_LIVE") != "1", reason="needs PLATOON_HARNESS_LIVE=1"),
    pytest.mark.skipif(shutil.which("claude") is None, reason="claude is not installed"),
    pytest.mark.skipif(shutil.which("codex") is None, reason="codex is not installed"),
]

LIMIT = Budget(turns=3, wall="3m")
ROLES = {
    "claude": Role(harness="claude", model=CLAUDE, effort=EFFORT, approvals="allow"),
    "codex": Role(harness="codex", model=CODEX, effort=EFFORT, approvals="allow", sandbox="read-only"),
}
DELEGATED = (
    "Use a sub-agent of your own for this if you have one: find which file in this repository defines the function "
    "`clamp`, then reply with only that file's name."
)
TOLD = "Begin every reply with the word Kestrel."


async def ran(session: Session, asked: str) -> tuple[list, dict]:
    """Ask the one agent something, and what the journal says of the turn it took."""
    await in_state(session, "ada", "idle")
    await session.send("@ada", asked)
    await seen(session, "turn.ended")
    events = await journal(session)
    used = await spent(session)
    print(used, sorted((await tools_called(session)).items()))
    print("empty waits:", empty_waits(events), "rereads:", rereads(events))
    return events, used


@pytest.mark.parametrize("harness", ROLES)
async def test_a_job_an_agent_would_hand_to_its_own_sub_agent_starts_none(harness, tmp_path):
    """Budget: at most 8 model calls, counted from the journal. A harness's own agents are off unless a role allows
    them, so asked to hand a search to a sub-agent of its own, the agent starts none, which `child.seen` would say."""
    team = Team(roles={"ada": ROLES[harness]}, budget=LIMIT)

    async with Session.start(team, root=tmp_path / "root", cwd=seeded(tmp_path / "work"), plan_login=True) as session:
        events, used = await ran(session, DELEGATED)

    words = [event.gist for event in events if event.type == "item.recorded" and event.data["kind"] == "message"]
    print("words:", words)
    assert not [event for event in events if event.type == "child.seen"]
    assert used["total"] <= 8


@pytest.mark.parametrize("harness", ROLES)
async def test_a_team_s_template_is_what_its_agent_is_told_and_acts_on(harness, tmp_path):
    """Budget: at most 6 model calls, counted from the journal. A team's template is the default with one sentence more,
    which the journal records as told, and which the agent's reply shows it read."""
    team = Team(preamble=f"{PREAMBLE}\n{TOLD}", roles={"ada": ROLES[harness]}, budget=LIMIT)

    async with Session.start(team, root=tmp_path / "root", cwd=seeded(tmp_path / "work"), plan_login=True) as session:
        events, used = await ran(session, "What is two plus two? Reply in one short sentence.")
        instructed = next(event for event in events if event.type == "agent.instructed")
        told = (await session.get_body(instructed.data["body"])).decode()

    words = [event.gist for event in events if event.type == "item.recorded" and event.data["kind"] == "message"]
    print("words:", words)
    assert told.endswith(TOLD)
    assert words and words[-1].lstrip("*_ ").lower().startswith("kestrel")
    assert used["total"] <= 6
