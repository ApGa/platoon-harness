"""What the terminal UI's tests share: the screen as text, and waiting for what it shows, change by change."""

import asyncio
from collections.abc import Callable

from textual import events
from textual._xterm_parser import XTermParser
from textual.pilot import Pilot

from platoon_harness.kernel import first
from platoon_harness_cli.tui.app import TerminalUI
from platoon_harness_cli.tui.live import Live
from platoon_harness_cli.tui.workspace import Workspace

# How long a wait here may take before it fails as a hang: it bounds no claim, so it is sized for the slowest machine
# that runs the suite, GitHub's runners, where a diff read by git outlasted 20 s.
SECONDS = 60.0


def at_once(app: TerminalUI, sent: str) -> None:
    """What a terminal sends at once, within Textual's escape delay, as a quick typist or a remote link does, read as
    Textual reads it: Esc then a letter comes as Alt and that letter."""
    parser = XTermParser()
    for key in (*parser.feed(sent), *parser.feed("")):
        assert isinstance(key, events.Key)
        key.set_sender(app)
        app._driver.send_message(key)


def screen_text(app: TerminalUI) -> str:
    """What the screen shows, a line per row, as a person would read it."""
    update = app.screen._compositor.render_full_update()
    return "\n".join("".join(strip.text for strip in line) for line in update.strips)


async def click_on(pilot: Pilot, selector: str, words: str) -> None:
    """Click the first character of `words` where the widget `selector` draws them, as a person would."""
    region = pilot.app.screen.query_one(selector).region
    lines = screen_text(pilot.app).splitlines()
    y = next(y for y in range(region.y, region.y + region.height) if words in lines[y][region.x :])
    await pilot.click(offset=(lines[y].index(words, region.x), y))


def workspace(app: TerminalUI) -> Workspace:
    screen = app.screen
    assert isinstance(screen, Workspace), type(screen)
    return screen


def _live(app: TerminalUI) -> Live | None:
    """The live session of the workspace, whether it is the screen shown or under a dialog."""
    return next((screen.live for screen in app.screen_stack if isinstance(screen, Workspace)), None)


def _frames(app: TerminalUI) -> int | None:
    live = _live(app)
    return None if live is None else live.frames


async def _change(app: TerminalUI, seen: int | None) -> None:
    """Return once something that could change the screen has: a frame past `seen` drawn, a worker done, or a screen
    pushed. A worker is watched and never awaited, since a task that awaits one and is cancelled cancels it too."""
    live = _live(app)
    running = {worker._task for worker in app.workers if not worker.is_finished and worker._task is not None}
    rivals = [asyncio.wait(running)] if running else []
    if live is not None:
        rivals.append(live.next_frame(live.frames if seen is None else seen))
    pushed = asyncio.Event()
    push = app.push_screen

    def pushing(*args, **kwargs):
        pushed.set()
        return push(*args, **kwargs)

    app.push_screen = pushing
    try:
        await first(pushed.wait(), *rivals)
    finally:
        del app.push_screen


async def drawn(pilot: Pilot, holds: Callable[[str], object], *, within: float = SECONDS) -> str:
    """The screen, once it shows what `holds`, looked at again after each change that could move it."""
    text = ""
    try:
        async with asyncio.timeout(within):
            while True:
                seen = _frames(pilot.app)
                await pilot.pause()
                text = screen_text(pilot.app)
                if holds(text):
                    return text
                await _change(pilot.app, seen)
    except TimeoutError:
        raise AssertionError(f"the screen never showed it:\n{text}") from None
