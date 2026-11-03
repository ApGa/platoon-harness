"""The `platoon-harness` command: its commands, and the one place where what went wrong becomes an exit code."""

import logging
import sys
from collections.abc import Sequence

from cyclopts import App, CycloptsError, Group, Parameter
from rich.console import Console

from platoon_harness import ConfigError, Refused
from platoon_harness.version import __version__ as sdk_version

from . import __version__, machine, running, sessions, teams
from .exits import CONFIGURATION, INTERRUPTED, REFUSED, USAGE, Usage
from .ops import groups
from .output import note, refused

HELP = """Bring the agent harnesses you already use together as a team, from a terminal or from CI.

A session is a folder holding a journal. `run` starts one and owns it until it settles, and `serve` keeps one for
clients to attach to. Every other command acts on a session by its name, as a guest, and runs one op there, as an
agent's `ph` does.

For example:

    platoon-harness init
    platoon-harness run "Fix the flaky test" --name fix-auth
    platoon-harness events fix-auth --follow
    platoon-harness message send fix-auth --to @lead --gist "Keep the public API stable"
    platoon-harness session show fix-auth"""

SESSION = """Sessions, from their folders, and what can be done to one as a whole.

For example:

    platoon-harness session list
    platoon-harness session show fix-auth
    platoon-harness session stop fix-auth
    platoon-harness session resume fix-auth"""

_OPS = Group("Ops on a session", sort_key=1)


def build() -> App:
    """The whole command line. Commands that act on a session come from the op registry, so they cannot drift."""
    app = App(
        name="platoon-harness",
        help=HELP,
        version=f"platoon-harness {__version__}, SDK {sdk_version}",
        default_parameter=Parameter(negative=(), show_default=False),
        console=Console(),
        error_console=Console(stderr=True),
    )
    app.command(running.run)
    app.command(running.serve)
    app.command(running.events)
    session = App(name="session", help=SESSION)
    session.command(sessions.list_sessions, name="list")
    session.command(sessions.show)
    session.command(sessions.stop)
    session.command(running.resume)
    app.command(session)
    app.command(teams.group)
    app.command(machine.init)
    app.command(machine.doctor)
    app.command(machine.extension)
    for name, group in groups({"session": session}).items():
        if name != "session":
            group.group = (_OPS,)
            app.command(group)
    return app


def main(tokens: Sequence[str] | None = None) -> int:
    """Run one command line and return its exit code. Logs, refusals and problems go to stderr, and nothing prompts."""
    logging.basicConfig(stream=sys.stderr, level=logging.WARNING, format="platoon-harness: %(message)s")
    try:
        code = build()(sys.argv[1:] if tokens is None else tokens, exit_on_error=False, result_action="return_value")
    except CycloptsError:
        return USAGE
    except Usage as usage:
        note(str(usage))
        return USAGE
    except ConfigError as error:
        for problem in error.problems:
            note(str(problem))
        return CONFIGURATION
    except Refused as error:
        note(refused(error.refusal))
        return REFUSED
    except KeyboardInterrupt:
        return INTERRUPTED
    return code if isinstance(code, int) else 0
