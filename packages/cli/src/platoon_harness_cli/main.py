"""The `platoon-harness` command: its commands, and the one place where what went wrong becomes an exit code."""

import asyncio
import logging
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

from cyclopts import App, CycloptsError, Group, Parameter
from rich.console import Console

from platoon_harness import ConfigError, JournalError, Refused
from platoon_harness.runtime.paths import find_root, session_folder
from platoon_harness.version import __version__ as sdk_version

from . import __version__, annotations, machine, running, sessions, teams
from .exits import CONFIGURATION, INTERRUPTED, JOURNAL, REFUSED, USAGE, Usage
from .ops import groups
from .output import note, refused
from .running import stopping

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
    only `/resume`, which resumes a session with no runtime, can spend money. `/detach` detaches, and the session runs
    on. It needs a terminal: `events --follow` follows a session as text.

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


async def web(
    session: str,
    /,
    *,
    host: str = "127.0.0.1",
    port: int = 0,
    certificate: Path | None = None,
    key: Path | None = None,
) -> int:
    """Open a session in the browser: SwarmChat's page, served over the session's journal.

    It says two links on stderr, each of which opens once, within ten minutes, for a session in the browser that lasts
    twelve hours: a view link, which shows the session and acts on nothing, and a control link, which acts as you,
    through the same ops as the terminal. A page that acts can make more links of either kind. Stopping `web` ends
    every browser's session, and leaving it changes nothing in the session, which runs on. It starts and resumes
    nothing: on a session no runtime holds, the page shows its history and names `session resume`, which can spend
    money. Ctrl+C or SIGTERM stops it.

    It serves loopback alone unless --host names another address, which needs --certificate and --key, as TLS. On
    loopback it also says how to reach it from another machine: forward its port under the same number. A session on a
    plan login, one whose owner said several agents may run on one or one of whose agents' harnesses came up last on
    one, it serves on loopback alone, as a control link acts as you: another address exits 78, as it starts or once
    such an agent comes up.

    For example:

        platoon-harness web fix-auth
        platoon-harness web fix-auth --port 8484
        platoon-harness web fix-auth --host 192.0.2.7 --certificate cert.pem --key key.pem

    Parameters
    ----------
    session
        A session, by name. `platoon-harness session list` shows them.
    host
        The address or name to serve, which a browser's requests must name.
    port
        The port to serve, or 0 for any free one, which stderr says.
    certificate
        A certificate chain, in PEM, to serve TLS with.
    key
        The certificate's private key, in PEM.
    """
    session_folder(find_root(), session)
    from .web import serve, tls_for
    from .web.page import Unpinned

    tls = tls_for(host, certificate, key)

    stop = asyncio.Event()
    with stopping(stop.set):
        try:
            await serve(session, stop, host=host, port=port, tls=tls)
        except Unpinned as unpinned:
            note(f"web: {unpinned}")
            return CONFIGURATION
        except OSError as error:
            raise Usage(f"web cannot serve {host} on port {port}: {error}") from None
    return 0


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
    app.command(web)
    app.command(running.run)
    app.command(running.serve)
    app.command(running.events)
    session = App(name="session", help=SESSION)
    session.command(sessions.list_sessions, name="list")
    session.command(sessions.show)
    session.command(sessions.stop)
    session.command(running.resume)
    session.command(sessions.refold)
    app.command(session)
    app.command(teams.group)
    app.command(machine.init)
    app.command(machine.doctor)
    app.command(machine.extension)
    app.command(annotations.annotate, name="annotate")
    app.command(annotations.annotations)
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
    except JournalError as error:
        note(str(error))
        return JOURNAL
    except KeyboardInterrupt:
        return INTERRUPTED
    return code if isinstance(code, int) else 0
