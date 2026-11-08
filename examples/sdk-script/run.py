"""A team run from a Python script on the SDK alone: two OpenHands agents on a model you name, each fixing one issue of
the sample project on a branch of its own, in a worktree of its own, the session waited on until it settles, and what
each reported read back. Run it from your copy of the sample project, with `OPENAI_BASE_URL` and `OPENAI_API_KEY`
naming your endpoint and key."""

import argparse
import asyncio

from platoon_harness import Role, Session, Team
from platoon_harness.team import AuthProfile, Budget

PROVIDER = AuthProfile(env=("OPENAI_BASE_URL", "OPENAI_API_KEY"))
"""The variables that name your endpoint and key, which each agent's harness is handed. Names only: a value never
enters a team."""
ASKED = "with a test that fails without your fix. Run `python3 -m unittest`, commit on your branch, and finish saying"
GOALS = {
    "cents": f"Fix issue 1 in ISSUES.md, {ASKED} what you changed.",
    "comments": f"Fix issue 3 in ISSUES.md, {ASKED} what you changed.",
}
"""Each agent's name and its goal, within a goal's 280 characters."""


def team(model: str) -> Team:
    """One role, `fixer`: OpenHands on your model, in a worktree of its own, whose approvals allow, as nobody is there
    to answer one, and of which the session starts none, as the script spawns each with a goal. A budget stops a
    runaway."""
    fixer = Role(harness="openhands", model=model, auth="provider", workspace="worktree", approvals="allow", count=0)
    return Team(roles={"fixer": fixer}, auth={"provider": PROVIDER}, budget=Budget(turns=8, wall="15m"))


async def main(model: str) -> None:
    async with Session.start(team(model)) as session:
        for name, goal in GOALS.items():
            await session.spawn(name, "fixer", goal)
        ending = await session.settled(timeout="15m")
    print(f"session {session.name}: {ending.reason}")
    for agent in ending.agents:
        print(f"{agent['agent']}: {agent['report']['gist'] if agent['report'] else 'no report'}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True, help="the model, as your endpoint names it")
    asyncio.run(main(parser.parse_args().model))
