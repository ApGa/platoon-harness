"""A headless script on the Python SDK alone, with no key and no model: a team of one role on a command that runs once
per agent, two agents spawned with a goal each, the session waited on until it settles, and what each agent said read
back from the journal."""

import asyncio
import sys

from platoon_harness import Role, Session, Team
from platoon_harness.team import Command

COUNT = Command(command=[sys.executable, "-c", "import sys; print(len(sys.argv[1].split()), 'words')", "{goal}"])
"""A one-shot harness, which the `exec` driver runs once per agent, with the agent's goal in place of `{goal}`."""
TEAM = Team(roles={"counter": Role(harness=COUNT, count=0)})
"""One role, of which the session starts no agent, as the script spawns each with a goal."""
GOALS = ["Count the words of this goal", "And of this one"]


async def main() -> None:
    async with Session.start(TEAM) as session:
        for number, goal in enumerate(GOALS, 1):
            await session.spawn(f"counter-{number}", "counter", goal)
        ending = await session.settled(timeout="30s")
        said = [f"{event.agent}: {event.gist}" async for event in session.events() if event.type == "item.recorded"]
    print(f"session {session.name}: {ending.reason}")
    print(*sorted(said), sep="\n")


if __name__ == "__main__":
    asyncio.run(main())
