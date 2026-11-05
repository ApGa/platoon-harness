"""Where a command's team comes from, and the commands about a team, which start nothing."""

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path

from cyclopts import App, Parameter

from platoon_harness import ConfigError, Team, load_team, told
from platoon_harness.config import PROJECT_FILE, sanitized
from platoon_harness.extensions import Installed
from platoon_harness.runtime.opening import check as problems_of
from platoon_harness.schema import Problem

from .exits import CONFIGURATION
from .output import safe, say


@Parameter(name="*")
@dataclass(frozen=True)
class Source:
    """What a team is made of besides its file, which layers over it as architecture section 17 says."""

    harness: str | None = None
    """A role on this harness, whose agent takes its name, over the rest: with no team file and no project file, a team
    of one."""

    set: tuple[str, ...] = ()
    """A line of TOML over the rest, such as `budget.usd = 5`. Give it again for more."""

    trust: bool = False
    """Run what the project file or the team file names to run: a command harness, a `module:attr` or an auth
    profile."""

    def load(self, path: Path | None) -> Team:
        """The team: the project file, the team file at `path` over it, then these."""
        lines = list(self.set)
        if self.harness is not None:
            name = json.dumps(self.harness)
            lines.insert(0, f"roles.{name}.harness = {name}")
        if path is None and not lines and not Path(PROJECT_FILE).exists():
            what = (
                f"no team here: name a team file, write {PROJECT_FILE} with `platoon-harness init`, or give --harness"
            )
            raise ConfigError([Problem("team", what)])
        return load_team(path, sets=lines, trust_project=self.trust)


group = App(
    name="team",
    help="""What a team allows and what its agents are told, before any cost.

Each reads the project file `platoon-harness.toml`, or the team file named over it, and starts nothing.

For example:

    platoon-harness team check crew.toml
    platoon-harness team show --resolved > resolved.toml
    platoon-harness team told --harness codex""",
)


@group.command
async def check(
    team: Path | None = None, /, *, source: Source = Source(), plan_login: bool = False, trainable: bool = False
) -> int:
    """Say every problem a session would meet in a team, at once, before any cost.

    It exits 78 when one is an error.

    Parameters
    ----------
    team
        A team file. Left out, the project file.
    plan_login
        Several agents may run headless on one plan login, as `run --plan-login` says.
    trainable
        Check it as a training system starts it, on this machine: what keeps the team from training, and each role's
        driver for a sealed launch and a result kept here that proves trainable.
    """
    loaded = source.load(team)
    problems = await asyncio.to_thread(problems_of, loaded, plan_login=plan_login, trainable=trainable)
    for problem in problems:
        say(safe(f"{problem.level}: {problem}"))
    if not problems:
        say("no problems")
    return CONFIGURATION if any(problem.level == "error" for problem in problems) else 0


@group.command
def show(team: Path | None = None, /, *, source: Source = Source(), resolved: bool = False) -> int:
    """Say what a team allows, in plain words or as TOML that loads back to the same team.

    Parameters
    ----------
    team
        A team file. Left out, the project file.
    resolved
        The expansion, which is what a session's manifest keeps, with no secret in it.
    """
    loaded = source.load(team).resolved(Installed())
    say(sanitized(loaded).rstrip("\n") if resolved else loaded.show())
    return 0


@group.command(name="told")
async def told_command(team: Path | None = None, /, *, source: Source = Source()) -> int:
    """Say what an agent of each role would be told at launch.

    That is all the runtime adds to its harness. No harness starts.

    Parameters
    ----------
    team
        A team file. Left out, the project file.
    """
    for role, text in (await told(source.load(team))).items():
        say(safe(f"# {role}\n\n{text or 'Nothing.'}\n"))
    return 0
