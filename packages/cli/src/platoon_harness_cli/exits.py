"""What `platoon-harness` exits with: an Ending's code, as architecture section 12 lists them, and the codes every
command shares."""

from platoon_harness import Ending

REFUSED = 1
"""A command was refused, and nothing it asked for happened. The refusal is on stderr."""
USAGE = 64
"""A command line that cannot run as it was given."""
CONFIGURATION = 78
"""A team, a root or a machine that cannot be used as it is. Every problem is on stderr."""
INTERRUPTED = 130
"""Ctrl+C, where nothing owned a session that could say how it ended."""

ENDINGS = {"settled": 0, "agent_failed": 1, "budget_exhausted": 2, "timed_out": 3, "needs_human": 4, "cancelled": 130}


class Usage(Exception):
    """A command line that cannot run as it was given."""


def code_of(ending: Ending) -> int:
    return ENDINGS[ending.reason]
