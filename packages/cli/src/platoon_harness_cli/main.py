"""The `platoon-harness` command: its commands, and the one place where what went wrong becomes an exit code."""

import logging
import sys
from collections.abc import Callable, Sequence

from cyclopts import App, CycloptsError, Group, Parameter
from rich.console import Console

from platoon_harness import ConfigError, Refused
from platoon_harness.runtime.paths import find_root, session_folder
from platoon_harness.version import __version__ as sdk_version

from . import __version__, machine, running, sessions, teams
from .exits import CONFIGURATION, INTERRUPTED, REFUSED, USAGE, Usage
from .ops import groups
from .output import note, refused

HELP = """Bring the agent harnesses you already use together as a team, from a terminal or from CI.

On a terminal, `platoon-harness` alone opens the terminal UI, and `attach` opens one session there. A session is a
folder holding a journal. `run` starts one and owns it until it settles, and `serve` keeps one for clients to attach
to. Each command under Ops on a session runs one op there as a guest, as an agent's `ph` does.

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
_FLAGS = Parameter(negative=(), show_default=False)
"""A flag as a person types it: no `--no-` form, and no default shown, as each command's help says what it is."""


def _flags(app: App) -> None:
    """Give every command under `app` the same flags, which the reference is made from as `--help` is."""
    for name in app:
        if not name.startswith("-"):
            app[name].default_parameter = _FLAGS
            _flags(app[name])


def _terminal() -> bool:
    return sys.stdin is not None and sys.stdin.isatty() and sys.stdout.isatty()


def attach(session: str, /) -> int:
    """Open a session in the terminal UI: live, as a guest of its runtime, or as its history when no runtime holds it.

    Attaching changes nothing in the session, and reading it moves only your own marks of how far you have read:
    only Alt+R, which resumes a session with no runtime, can spend money. Ctrl+D detaches, and the session runs on. It
    needs a terminal: `events --follow` follows a session as text.

    For example:

        platoon-harness attach fix-auth

    Parameters
    ----------
    session
        A session, by name. `platoon-harness session list` shows them.
    """
    if not _terminal():
        raise Usage(f"attach draws on a terminal, and none is here: `platoon-harness events {session} --follow`")
    session_folder(find_root(), session)
    from .tui import run as tui

    return tui(session)


def build() -> App:
    """The whole command line. Commands that act on a session come from the op registry, so they cannot drift."""
    app = App(
        name="platoon-harness",
        help=HELP,
        version=f"platoon-harness {__version__}, SDK {sdk_version}",
        default_parameter=_FLAGS,
        console=Console(),
        error_console=Console(stderr=True),
    )
    app.default(_opened(app))
    app.command(attach)
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
    _flags(app)
    return app


def _opened(app: App) -> Callable[[], int]:
    def opened() -> int:
        """Open the terminal UI on a terminal, and say this help anywhere else, as nothing prompts with none."""
        if not _terminal():
            app.help_print()
            return 0
        from .tui import run as tui

        return tui()

    return opened


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
