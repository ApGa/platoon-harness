"""A population of workers, each in a worktree of its own, run from a script that owns its session as `program:swarm`:
it starts four workers with one goal, as many at once as the team's `live` allows, gives each one outcome, closes the
session and prints each worker's outcome. Choosing among the nominations is yours. Run it from a git repository with a
commit."""

import argparse
import asyncio
from pathlib import Path

from platoon_harness import Session, load_team
from platoon_harness.patterns import population

TEAM = Path(__file__).with_name("team.toml")
GOAL = (
    "Add `fizzbuzz.py`, whose `fizzbuzz(n)` gives Fizz for a multiple of 3, Buzz for one of 5, FizzBuzz for both and "
    "`n` as text otherwise, with a `unittest` test. Build on a peer's commit that does part of this, nominate one that "
    "does all of it, and abstain once one is nominated."
)
"""What each worker is asked, within a goal's 280 characters. The population tells each beside it how its outcome is
read and how to build on a peer's commit."""
ATTEMPTS = 4
"""How many workers the population starts, each one attempt, whatever it comes to."""


async def main(sets: list[str], plan_login: bool) -> None:
    team = load_team(TEAM, sets=sets)
    async with Session.start(team, principal="program:swarm", plan_login=plan_login) as session:
        outcomes = await population(session, "worker", GOAL, attempts=ATTEMPTS)
        entries = [await session.board_get("outcomes", name) for name in outcomes]
        await session.close()
        ending = await session.settled()
    print(f"session {session.name}: {ending.reason}")
    print(*(f"{name}: {entry['gist']}" for name, entry in zip(outcomes, entries, strict=True)), sep="\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--set", action="append", default=[], dest="sets", metavar="LINE", help="a team file line")
    parser.add_argument("--plan-login", action="store_true", help="say several agents may run on your plan login")
    arguments = parser.parse_args()
    asyncio.run(main(arguments.sets, arguments.plan_login))
