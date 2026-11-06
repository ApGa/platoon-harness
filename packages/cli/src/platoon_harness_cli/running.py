"""The commands that own a session in the foreground, `run`, `serve` and `session resume`, and `events`, which follows
one as a guest. Signal handlers live here, in the entry point, and nowhere in the SDK."""

import asyncio
import contextlib
import signal
import sys
from collections.abc import Callable, Generator
from pathlib import Path
from typing import Annotated

from cyclopts import Parameter

from platoon_harness import ConfigError, Refused, Session, Team
from platoon_harness.extensions import Installed
from platoon_harness.kernel import GIST_LIMIT, first
from platoon_harness.primitives import Policy
from platoon_harness.runtime import Runtime
from platoon_harness.runtime.opening import prepare
from platoon_harness.runtime.paths import find_root, session_folder
from platoon_harness.schema import seconds
from platoon_harness.session import Reason

from .exits import ENDINGS, INTERRUPTED, Usage
from .output import ending_line, event_line, note, readable, readable_ending, refused, say
from .teams import Source


@contextlib.contextmanager
def stopping(stop: Callable[[], None]) -> Generator[None]:
    """Ctrl+C and SIGTERM call `stop` while this holds, in place of what they would do."""
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(signum, stop)
    try:
        yield
    finally:
        for signum in (signal.SIGINT, signal.SIGTERM):
            loop.remove_signal_handler(signum)


@contextlib.contextmanager
def as_given() -> Generator[None]:
    """A refusal before a session is owned names what the command line asked for and cannot be, such as a name that is
    taken or no session of that name, so it is a command line that cannot run as it was given."""
    try:
        yield
    except Refused as error:
        raise Usage(refused(error.refusal)) from None


def _stdin() -> str:
    if sys.stdin is None:
        raise Usage("stdin is closed, so there is no prompt to read")
    try:
        return sys.stdin.read()
    except UnicodeDecodeError as error:
        raise Usage(f"stdin: {error}") from None


def _prompt(prompt: str | None, prompt_file: Path | None) -> str:
    """The prompt, with no space at its ends: the argument, a file's text, or stdin read to its end, for `-` or when it
    is no terminal. One word that starts with `-` is an option nobody knows."""
    if prompt is not None and prompt_file is not None:
        raise Usage("give a prompt or --prompt-file, not both")
    if prompt_file is not None:
        try:
            text = prompt_file.read_text()
        except (OSError, UnicodeDecodeError) as error:
            raise Usage(f"--prompt-file: {error}") from None
    elif prompt == "-" or (prompt is None and sys.stdin is not None and not sys.stdin.isatty()):
        text = _stdin()
    elif prompt is None:
        raise Usage('give a prompt: `platoon-harness run "..."`, `-` for stdin, or --prompt-file')
    elif prompt.startswith("-") and len(prompt.split()) == 1:
        raise Usage(f"no option {prompt}: a prompt that starts with `-` goes on stdin or in --prompt-file")
    else:
        text = prompt
    if not text.strip():
        raise Usage("the prompt is empty")
    return text.strip()


def _span(timeout: str | None) -> float | None:
    try:
        return None if timeout is None else seconds(timeout)
    except ValueError as error:
        raise Usage(f"--timeout: {error}") from None


def _recipients(team: Team, to: str | None) -> tuple[str, ...]:
    """Whom a prompt is for, decided before any cost, as `Team.recipients` says: `to`, which must name an agent the
    session starts, or else every agent it starts."""
    try:
        found = team.resolved(Installed()).recipients(to)
    except ConfigError as error:
        raise Usage(f"--to {error.problems[0].what}") from None
    if not found:
        raise Usage("this session starts no agent, so the prompt would reach nobody")
    return found


async def printing(name: str, after: int, *, json: bool, follow: bool = True) -> None:
    """Print a session's events past `after`, and with `follow` until nothing more can come, as a guest with a view
    credential, which writes nothing and is nobody who could act. It stops once nobody reads them."""
    async with Session.attach(name, view=True) as watching:
        async for event in watching.events(after, follow=follow):
            if not say(event_line(event) if json else readable(event)):
                break


async def _incarnation(session: Session) -> int:
    """Where what this runtime did begins: just before its `runtime.started`, the last, as nobody else's can follow."""
    started = [event.seq async for event in session.events(match="runtime") if event.type == "runtime.started"]
    return started[-1] - 1


async def _ending(name: str, reason: Reason, json: bool) -> int:
    async with Session.attach(name, view=True) as history:
        ending = (await history.ending()).model_copy(update={"reason": reason})
    code = ENDINGS[reason]
    say(ending_line(ending, code) if json else readable_ending(ending, code))
    return code


async def own(
    session: Session, *, span: float | None, json: bool, message: tuple[tuple[str, ...], str] | None = None
) -> int:
    """Own a session in the foreground: enter it, print what its runtime does, send `message`, a person's, as `(to,
    text)`, to each of `to`, wait for it to settle, then run the owner's shutdown and print how it ended, last. Ctrl+C
    or SIGTERM at any point cancels what is under way, and the shutdown still runs, so it ends `cancelled` and stays
    resumable. One stopped while its runtime starts has printed nothing yet, so it prints its ending alone.

    The events print from a thread of their own, as a guest of this runtime, so a reader of stdout that falls behind
    holds up nothing here: the runtime drops a guest that stops reading, and it comes back where it was."""
    stop = asyncio.Event()
    reason: Reason = "cancelled"
    with stopping(stop.set):
        with as_given():
            entered = await first(session, stop.wait())
        if not session.name:
            note("stopped before a session was made")
            return INTERRUPTED
        note(f"session {session.name}: follow it with `platoon-harness events {session.name} --follow`")
        if entered:
            printed = None
            try:
                follow = printing(session.name, await _incarnation(session), json=json)
                printed = asyncio.ensure_future(asyncio.to_thread(asyncio.run, follow))
                if message is None or await first(_send(session, *message), stop.wait()):
                    settling = asyncio.ensure_future(session.settled(span))
                    if await first(settling, stop.wait()):
                        reason = settling.result().reason
            finally:
                await session.leave()
                if printed is not None:
                    try:
                        await printed
                    except Refused as error:  # the printer's, which never takes the place of what ended the run
                        note(refused(error.refusal))
        try:
            return await _ending(session.name, reason, json)
        except Refused as error:
            note(refused(error.refusal))
            return INTERRUPTED


async def _send(session: Session, to: tuple[str, ...], text: str) -> None:
    """A prompt as a person's message to each of `to`: the whole of it when it fits a gist, else its start and the whole
    as the body. A refusal is said, and the session's ending says what came of it."""
    gist, body = (text, None) if len(text) <= GIST_LIMIT else (f"{text[: GIST_LIMIT - 1]}…", text)
    for recipient in to:
        try:
            await session.send(recipient, gist, body=body)
        except Refused as error:
            note(refused(error.refusal))


async def run(
    prompt: Annotated[str | None, Parameter(allow_leading_hyphen=True)] = None,
    /,
    *,
    team: Path | None = None,
    source: Source = Source(),
    to: str | None = None,
    prompt_file: Path | None = None,
    name: str | None = None,
    approvals: Policy | None = None,
    plan_login: bool = False,
    timeout: str | None = None,  # noqa: ASYNC109  It is how long `settled` waits, which the exit code says.
    json: bool = False,
) -> int:
    """Start a session, give it a prompt, and own it in the foreground until it settles.

    It exits with how the session ended: 0 settled, 1 an agent failed, 2 the budget ran out, 3 timed out, 4 it needs a
    person, and 130 cancelled, by Ctrl+C or `session stop` too. Ctrl+C runs the owner's shutdown first, which keeps the
    session resumable. What it cannot run as given, a name that is taken among it, exits 64 before any cost, and a
    commit to its journal that fails ends it with exit 74, as a kill would, leaving it to `session resume`.

    The team is the project file, `platoon-harness.toml`, or the file --team names over it, and --harness adds a role
    on that harness. The prompt goes to every agent the session starts, or to --to alone. A person's message steers:
    it lands at the earliest boundary the harness has. The session's name is on stderr at the start, so another shell
    can reach it.

    With --json, stdout holds one JSON line per event of the session's journal, then one for its ending, and nothing
    else. An approval left to ask, with nobody attached to answer, ends the run at once with exit 4, and never prompts:
    --approvals answers every one.

    For example:

        platoon-harness run "Fix the flaky test in tests/test_cart.py"
        git diff | platoon-harness run - --json --harness codex --approvals deny > events.jsonl
        platoon-harness run --team crew.toml --to @lead --prompt-file task.md --plan-login --timeout 30m

    Parameters
    ----------
    prompt
        What to ask. `-`, or none when stdin is no terminal, reads stdin to its end.
    team
        A team file, over the project file.
    to
        The one agent the prompt is for, as `@agent`. Left out, it goes to every agent the session starts.
    prompt_file
        A file whose text is the prompt.
    name
        The session's name. Left out, one is made from the time.
    approvals
        Answer every approval this way, over each role's own policy. The manifest keeps it.
    plan_login
        Several agents may run headless on one plan login: say so to say this is your own work.
    timeout
        How long to wait for it to settle, such as 90s, 30m or 2h. Past it the run ends with exit 3.
    json
        Print JSONL on stdout.
    """
    text, span = _prompt(prompt, prompt_file), _span(timeout)
    loaded = source.load(team)
    recipients = _recipients(loaded, to)
    session = Session.start(loaded, name=name, approvals=approvals, plan_login=plan_login, cwd=Path.cwd())
    return await own(session, span=span, json=json, message=(recipients, text))


async def resume(
    session: str,
    /,
    *,
    timeout: str | None = None,  # noqa: ASYNC109  It is how long `settled` waits, which the exit code says.
    json: bool = False,
) -> int:
    """Restart a session whose runtime has gone, and own it in the foreground until it settles.

    Its harnesses come back, and a turn they were cut off in is told and woken, which can spend money. It prints what
    its runtime does, from its start, and exits as `run` does.

    For example:

        platoon-harness session resume fix-auth
        platoon-harness session resume fix-auth --json --timeout 10m

    Parameters
    ----------
    session
        A session, by name. `platoon-harness session list` shows them.
    timeout
        How long to wait for it to settle, such as 90s, 30m or 2h.
    json
        Print JSONL on stdout.
    """
    span = _span(timeout)
    with as_given():
        session_folder(find_root(), session)
    note(f"resuming session {session}: its harnesses come back, and can spend money")
    return await own(Session.resume(session), span=span, json=json)


async def serve(
    *,
    team: Path | None = None,
    source: Source = Source(),
    name: str | None = None,
    approvals: Policy | None = None,
    plan_login: bool = False,
) -> int:
    """Start a session and keep its runtime in the foreground, with no client attached, for a supervisor.

    Clients attach as guests by its name, which is on stderr. SIGTERM, or Ctrl+C, runs the owner's shutdown, which
    keeps it resumable. It exits 0 once that is done or once the session has closed and drained, 74 when a commit to its
    journal fails, which ends it as a kill would, and 78 when the team cannot run.

    For example:

        platoon-harness serve --team crew.toml --name nightly
        platoon-harness message send nightly --to @lead --gist "Start on the backlog"

    Parameters
    ----------
    team
        A team file, over the project file.
    name
        The session's name. Left out, one is made from the time.
    approvals
        Answer every approval this way, over each role's own policy.
    plan_login
        Several agents may run headless on one plan login: say so to say this is your own work.
    """
    loaded = source.load(team)
    with as_given():
        folder = await asyncio.to_thread(
            prepare, loaded, name=name, approvals=approvals, plan_login=plan_login, cwd=Path.cwd()
        )
    runtime = Runtime(folder)
    with stopping(runtime.ask_to_stop):
        await runtime.start()
        name = folder.name
        note(
            f"serving session {name}: `platoon-harness session stop {name}` stops it, and "
            f"`platoon-harness session resume {name}` restarts it"
        )
        try:
            await runtime.run()
        finally:
            await runtime.stop()
    return 0


async def events(session: str, /, *, after: int = 0, follow: bool = False, json: bool = False) -> int:
    """Print a session's events past a cursor, live or closed, writing nothing.

    With --json each line is one event's JSON, carrying its `seq`: pass the last one as --after to go on exactly where
    you stopped, across a runtime that stopped and resumed. It ends once nobody reads what it prints, and Ctrl+C ends it
    with exit 130.

    For example:

        platoon-harness events fix-auth
        platoon-harness events fix-auth --follow --json | jq -c 'select(.type == "message.sent")'
        platoon-harness events fix-auth --after 140 --follow

    Parameters
    ----------
    session
        A session, by name. `platoon-harness session list` shows them.
    after
        A `seq`: print only what came after it.
    follow
        Keep printing as the journal grows, until the session's runtime has gone and nothing more can come.
    json
        Print JSONL on stdout.
    """
    stop = asyncio.Event()
    with stopping(stop.set):
        if await first(printing(session, after, json=json, follow=follow), stop.wait()):
            return 0
    return INTERRUPTED
