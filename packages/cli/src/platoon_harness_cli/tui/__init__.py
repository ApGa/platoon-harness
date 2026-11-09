"""The terminal UI, which `platoon-harness` opens on a terminal. The command line imports it only then, so a headless
`run` never imports Textual."""

from ..output import note


def run(session: str | None = None, *, replay: bool = False) -> int:
    """Run the terminal UI on the sessions screen, or on one session, or with `replay` a replay of it, and say how to
    come back to a session left running. A UI that failed, which Textual has shown, exits 1."""
    from .app import TerminalUI

    app = TerminalUI(session, replay=replay)
    left = app.run()
    if app.return_code:
        return 1
    if left:
        note(f"detached from session {left}, which runs on: `platoon-harness attach {left}` comes back to it")
    return 0
