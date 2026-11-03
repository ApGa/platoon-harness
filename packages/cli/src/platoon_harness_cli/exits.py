"""What `platoon-harness` exits with: an Ending's code, as architecture section 12 lists them, and the codes every
command shares."""

ENDINGS = {"settled": 0, "agent_failed": 1, "budget_exhausted": 2, "timed_out": 3, "needs_human": 4, "cancelled": 130}

REFUSED = 1
USAGE = 64
CONFIGURATION = 78
INTERRUPTED = 130

SHARED = {
    REFUSED: "A command other than `run` and `session resume` was refused, and nothing it asked for happened",
    USAGE: "A command line that cannot run as it was given. `run` and `session resume` exit this for a refusal before "
    "the session is theirs, such as a name that is taken or no session of that name, so they never exit 1 for one",
    CONFIGURATION: "A team, a root or a machine that cannot be used as it is. `team check` and `doctor` print each "
    "problem on stdout, as what they say, and every other command on stderr",
    INTERRUPTED: "Ctrl+C, where no session's ending says more",
}
"""What each code every command shares means, as the reference says it."""


class Usage(Exception):
    """A command line that cannot run as it was given."""
