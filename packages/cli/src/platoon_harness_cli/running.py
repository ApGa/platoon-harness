"""The commands that own a session in the foreground, `run`, `serve` and `session resume`, and `events`, which follows
one as a guest. Signal handlers live here, in the entry point, and nowhere in the SDK."""

import asyncio
import contextlib
import signal
import sys
from collections.abc import Awaitable, Callable, Generator
from pathlib import Path

from platoon_harness import Session
from platoon_harness.kernel import GIST_LIMIT, first
from platoon_harness.primitives import Policy
from platoon_harness.runtime import Runtime
from platoon_harness.runtime.opening import prepare
from platoon_harness.schema import seconds

from .exits import ENDINGS, INTERRUPTED, Usage
from .output import ending_line, event_line, note, readable, readable_ending, say
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


def _prompt(prompt: str | None, prompt_file: Path | None) -> str:
    """The prompt, with no space at its ends: the argument, a file's text, or stdin read to its end, for `-` or when it
    is no terminal."""
    if prompt is not None and prompt_file is not None:
        raise Usage("give a prompt or --prompt-file, not both")
    if prompt_file is not None:
        try:
            text = prompt_file.read_text()
        except (OSError, UnicodeDecodeError) as error:
            raise Usage(f"--prompt-file: {error}") from None
    elif prompt == "-" or (prompt is None and not sys.stdin.isatty()):
        text = sys.stdin.read()
    elif prompt is None:
        raise Usage('give a prompt: `platoon-harness run "..."`, `-` for stdin, or --prompt-file')
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


async def _only_agent(session: Session) -> str:
    """The one agent the session started, which is who a prompt goes to when nobody is named."""
    names = [f"@{row['agent']}" for row in await session.agents()]
    if len(names) != 1:
        raise Usage(f"say which agent the prompt is for, with --to: this session started {', '.join(names) or 'none'}")
    return names[0]


async def printing(name: str, after: int, *, json: bool, follow: bool = True) -> None:
    """Print a session's events past `after`, and with `follow` until nothing more can come, as a guest with a view
    credential, which writes nothing and is nobody who could act."""
    async with Session.attach(name, view=True) as watching:
        async for event in watching.events(after, follow=follow):
            say(event_line(event) if json else readable(event))


async def own(
    session: Session, *, after: int, span: float | None, json: bool, begin: Callable[[], Awaitable[None]]
) -> int:
    """Own a session in the foreground: print its events past `after`, `begin`, wait for it to settle, then run the
    owner's shutdown and print how it ended, last. Ctrl+C or SIGTERM cancels the wait, and the shutdown still runs.

    The events print from a thread of their own, as a guest of this runtime, so a reader of stdout that falls behind
    holds up nothing here: the runtime drops a guest that stops reading, and it comes back where it was."""
    stop = asyncio.Event()
    printed = asyncio.ensure_future(asyncio.to_thread(asyncio.run, printing(session.name, after, json=json)))
    try:
        with stopping(stop.set):
            await begin()
            settling = asyncio.ensure_future(session.settled(span))
            reason = settling.result().reason if await first(settling, stop.wait()) else "cancelled"
    finally:
        await session.leave()
        await printed
    async with Session.attach(session.name, view=True) as history:
        ending = (await history.ending()).model_copy(update={"reason": reason})
    code = ENDINGS[reason]
    say(ending_line(ending, code) if json else readable_ending(ending, code))
    return code


def _gist(text: str) -> tuple[str, str | None]:
    """A prompt as a message: the whole of it when it fits a gist, else its start and the whole as the body."""
    if len(text) <= GIST_LIMIT:
        return text, None
    return f"{text[: GIST_LIMIT - 1]}…", text


async def run(
    prompt: str | None = None,
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
    session resumable.

    The team is the project file, `platoon-harness.toml`, or the file --team names over it, or a team of one on
    --harness. The prompt goes to the one agent the session starts, or to --to. A person's message steers: it lands at
    the earliest boundary the harness has. The session's name is on stderr at the start, so another shell can reach it.

    With --json, stdout holds one JSON line per event of the session's journal, then one for its ending, and nothing
    else. An approval left to ask, with nobody attached to answer, ends the run at once with exit 4, and never prompts:
    --approvals answers every one.

    For example:

        platoon-harness run "Fix the flaky test in tests/test_cart.py"
        git diff | platoon-harness run --json --harness codex --approvals deny > events.jsonl
        platoon-harness run --team crew.toml --to @lead --prompt-file task.md --plan-login --timeout 30m

    Parameters
    ----------
    prompt
        What to ask. `-`, or none when stdin is no terminal, reads stdin to its end.
    team
        A team file, over the project file.
    to
        Who the prompt is for, as `@agent`, when the session starts more than one.
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
    session = await Session.start(loaded, name=name, approvals=approvals, plan_login=plan_login, cwd=Path.cwd())
    note(f"session {session.name}: follow it with `platoon-harness events {session.name} --follow`")
    try:
        target = to or await _only_agent(session)
    except BaseException:
        await session.leave()
        raise

    async def begin() -> None:
        gist, body = _gist(text)
        await session.send(target, gist, body=body)

    return await own(session, after=0, span=span, json=json, begin=begin)


async def resume(
    session: str,
    /,
    *,
    timeout: str | None = None,  # noqa: ASYNC109  It is how long `settled` waits, which the exit code says.
    json: bool = False,
) -> int:
    """Restart a session whose runtime has gone, and own it in the foreground until it settles.

    Its harnesses come back, and a turn they were cut off in is told and woken, which can spend money. It prints what
    happens from now, and exits as `run` does.

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
    async with Session.attach(session, view=True) as history:
        after = await history.head()
    note(f"resuming session {session}: its harnesses come back, and can spend money")
    owner = await Session.resume(session)

    async def begin() -> None:
        return None

    return await own(owner, after=after, span=span, json=json, begin=begin)


async def serve(
    team: Path | None = None,
    /,
    *,
    source: Source = Source(),
    name: str | None = None,
    approvals: Policy | None = None,
    plan_login: bool = False,
) -> int:
    """Start a session and keep its runtime in the foreground, with no client attached, for a supervisor.

    Clients attach as guests by its name, which is on stderr. SIGTERM, or Ctrl+C, runs the owner's shutdown, which
    keeps it resumable. It exits 0 once that is done or once the session has closed and drained, and 78 when the team
    cannot run.

    For example:

        platoon-harness serve crew.toml --name nightly
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
    folder = await asyncio.to_thread(
        prepare, loaded, name=name, approvals=approvals, plan_login=plan_login, cwd=Path.cwd()
    )
    runtime = Runtime(folder)
    with stopping(runtime.ask_to_stop):
        await runtime.start()
        note(f"serving session {folder.name}: SIGTERM stops it, and `platoon-harness session resume` restarts it")
        await runtime.run()
        await runtime.stop()
    return 0


async def events(session: str, /, *, after: int = 0, follow: bool = False, json: bool = False) -> int:
    """Print a session's events past a cursor, live or closed, writing nothing.

    With --json each line is one event's JSON, carrying its `seq`: pass the last one as --after to go on exactly where
    you stopped, across a runtime that stopped and resumed. Ctrl+C ends it with exit 130.

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
