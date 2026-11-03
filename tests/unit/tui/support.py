"""What the terminal UI's tests share: the screen as text, and waiting for what it shows, change by change."""

import asyncio
from collections.abc import Callable

from textual.pilot import Pilot

from platoon_harness.kernel import first
from platoon_harness_cli.tui.app import Harness
from platoon_harness_cli.tui.workspace import Workspace

SECONDS = 20.0


def screen_text(app: Harness) -> str:
    """What the screen shows, a line per row, as a person would read it."""
    update = app.screen._compositor.render_full_update()
    return "\n".join("".join(strip.text for strip in line) for line in update.strips)


def workspace(app: Harness) -> Workspace:
    screen = app.screen
    assert isinstance(screen, Workspace), type(screen)
    return screen


def _frames(app: Harness) -> int | None:
    live = app.screen.live if isinstance(app.screen, Workspace) else None
    return None if live is None else live.frames


async def _change(app: Harness, seen: int | None) -> None:
    """Return once something that could change the screen has: a frame past `seen` drawn, a worker done, or a screen
    pushed. A worker is watched and never awaited, since a task that awaits one and is cancelled cancels it too."""
    live = app.screen.live if isinstance(app.screen, Workspace) else None
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
