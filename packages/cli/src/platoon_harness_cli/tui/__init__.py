"""The terminal UI, which `platoon-harness` opens on a terminal. The command line imports it only then, so a headless
`run` never imports Textual."""

from ..output import note


def run(session: str | None = None) -> int:
    """Run the terminal UI on the sessions screen, or on one session, and say how to come back to a session left
    running."""
    from .app import Harness

    left = Harness(session).run()
    if left:
        note(f"detached from session {left}, which runs on: `platoon-harness attach {left}` comes back to it")
    return 0
