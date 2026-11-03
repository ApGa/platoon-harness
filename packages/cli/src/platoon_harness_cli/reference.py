"""`python -m platoon_harness_cli.reference > docs/cli.md`: the command line's reference, made from its definitions."""

import sys

from platoon_harness import Ending
from platoon_harness.kernel import Event

from .exits import CONFIGURATION, ENDINGS, INTERRUPTED, REFUSED, USAGE
from .main import build
from .output import FORMAT

_SHARED = (
    (REFUSED, "A command other than `run` and `session resume` was refused, and nothing it asked for happened"),
    (USAGE, "A command line that cannot run as it was given"),
    (CONFIGURATION, "A team, a root or a machine that cannot be used as it is. `team check` and `doctor` say so too"),
    (INTERRUPTED, "Ctrl+C, where no session's ending says more"),
)


def reference() -> str:
    """The reference: exit codes, the JSONL shape and every command, from what defines them."""
    endings = "\n".join(f"| `{reason}` | {code} |" for reason, code in ENDINGS.items())
    shared = "\n".join(f"| {code} | {when} |" for code, when in _SHARED)
    envelope = ", ".join(f"`{name}`" for name in Event.model_fields)
    ending = ", ".join(f"`{name}`" for name in ("type", *Ending.model_fields, "code"))
    return f"""# Command line reference

<!-- Made from the command definitions by `uv run python -m platoon_harness_cli.reference > docs/cli.md`. Do not edit:
change the definitions, and make it again. A test holds it to them. -->

Every command that acts on a session takes the session's name first, and runs one op there as a guest, by the name and
with the arguments an agent's `ph` uses: `ph task.claim --queue tasks` is `platoon-harness task claim SESSION --queue
tasks`. A read runs on a view credential, which writes nothing, and anything else on a control credential. The
[headless quickstart](headless.md) shows them together.

## Exit codes

`run` and `session resume` exit with how their session ended, as architecture section 12 lists it:

| Reason | Code |
|---|---|
{endings}

Every command shares these, with what went wrong on stderr:

| Code | When |
|---|---|
{shared}

## JSONL

With `--json`, `run`, `session resume` and `events` print one JSON object per line on stdout, and nothing else reaches
it: logs, notes and refusals go to stderr. Each line has `format`, which is {FORMAT}, and holds ASCII alone, anything
else escaped.

An event's line is its envelope as the journal holds it, as architecture section 5.3 says, with these keys:

{envelope}

Its `v` is its payload's version. Its `seq` is a cursor: pass the last one as `--after` to go on exactly where you
stopped. The last line of `run` and `session resume` is the ending, with these keys, where `type` is `ending` and
`code` is what the command exits with:

{ending}

Without `--json` each event is one readable line, which is no contract.

{build().generate_docs(heading_level=2)}"""


if __name__ == "__main__":
    sys.stdout.write(reference())
