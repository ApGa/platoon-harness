"""A population of workers, each in a worktree of its own, run from a script that owns its session as `program:swarm`:
it starts four workers with one goal, as many at once as the team's `live` allows, gives each one outcome, closes the
session and prints each worker's outcome. Choosing among the nominations is yours. Run it from your copy of the sample
project, with `OPENAI_BASE_URL` and `OPENAI_API_KEY` naming your endpoint and key, and a `--set` line naming your
model."""

import argparse
import asyncio
from pathlib import Path

from platoon_harness import Refused, Session, load_team
from platoon_harness.patterns import population

TEAM = Path(__file__).with_name("team.toml")
"""The team file beside the script, which it trusts as `--trust` trusts a team file: its auth profile hands your key to
each worker's harness."""
GOAL = (
    "Add the `--json` option that issue 4 in ISSUES.md asks for, with a test that `python3 -m unittest` runs. Build on "
    "a peer's commit that does part of this, nominate one that does all of it, and abstain once one is nominated."
)
"""What each worker is asked, within a goal's 280 characters. The population tells each beside it how its outcome is
read and how to build on a peer's commit."""
ATTEMPTS = 4
"""How many workers the population starts, each one attempt, whatever it comes to."""


async def main(sets: list[str]) -> None:
    team = load_team(TEAM, sets=sets, trust_project=True)
    async with Session.start(team, principal="program:swarm") as session:
        outcomes = await population(session, "worker", GOAL, attempts=ATTEMPTS)
        entries = [await session.board_get("outcomes", name) for name in outcomes]
        closed = await session.submit("session.close", key="close")
        if closed.refusal is not None:
            raise Refused.of(closed.refusal)
        ending = await session.settled()
    print(f"session {session.name}: {ending.reason}")
    print(*(f"{name}: {entry['gist']}" for name, entry in zip(outcomes, entries, strict=True)), sep="\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--set", action="append", default=[], dest="sets", metavar="LINE", help="a team file line")
    asyncio.run(main(parser.parse_args().sets))
