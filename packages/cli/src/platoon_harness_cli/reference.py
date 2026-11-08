"""`python -m platoon_harness_cli.reference > docs/reference/cli.md`: the command line's reference, made from its
definitions."""

import sys

from platoon_harness import Ending
from platoon_harness.kernel import Event

from .exits import ENDINGS, SHARED
from .main import build
from .output import FORMAT


def reference() -> str:
    """The reference: exit codes, the JSONL shape and every command, from what defines them."""
    endings = "\n".join(f"| `{reason}` | {code} |" for reason, code in ENDINGS.items())
    shared = "\n".join(f"| {code} | {when} |" for code, when in SHARED.items())
    envelope = ", ".join(f"`{name}`" for name in Event.model_fields)
    ending = ", ".join(f"`{name}`" for name in ("type", *Ending.model_fields, "code"))
    return f"""# Command line reference

<!-- Made from the command definitions by `uv run python -m platoon_harness_cli.reference > docs/reference/cli.md`.
Do not edit: change the definitions, and make it again. A test holds it to them. -->

Each command under Ops on a session takes the session's name first, and runs one op there as a guest, by the name and
with the arguments an agent's `ph` uses: `ph task.claim --queue tasks` is `platoon-harness task claim SESSION --queue
tasks`. A read runs on a view credential, which writes nothing, and anything else on a control credential. `wait` and
the ops on a wait have no command, as a wait parks a turn and a person has none: `events --follow` watches a session,
and a script has `Session.wait`. The [headless quickstart](../how-to/headless.md) shows them together.

An installed extension's op is a command too, made in the same way under the extension's name: `ph ballot.cast --agent
@author --choice yes`, the op of [the sample extension package](../../examples/extension-package/README.md), is
`platoon-harness ballot cast SESSION --agent @author --choice yes`. `--help` lists each installed extension under
Installed extensions, read from metadata with none imported, and a command line imports only the one it names first. Its
op runs only on a session whose team names that extension, and is refused, with exit 1, on any other, saying so. This
reference is made from the command line's own commands, so it lists no extension's.

## Exit codes

`run` and `session resume` exit with how their session ended, as architecture section 12 lists it:

| Reason | Code |
|---|---|
{endings}

Every command shares these:

| Code | When |
|---|---|
{shared}

## JSONL

With `--json`, `run`, `session resume` and `events` print one JSON object per line on stdout, and nothing else reaches
it: logs, notes and refusals go to stderr. Each line has `format`, which is {FORMAT}, and holds ASCII alone, anything
else escaped. `run` and `session resume` print each event the runtime they own journals, from its `runtime.started`,
and `events` each event past `--after`.

An event's line is its envelope as the journal holds it, as architecture section 5.3 says, with these keys:

{envelope}

Its `v` is its payload's version. Its `seq` is a cursor: pass the last one as `--after` to go on exactly where you
stopped. The last line of `run` and `session resume` is the ending, with these keys, where `type` is `ending` and
`code` is what the command exits with. One stopped while its runtime starts prints its ending alone:

{ending}

Without `--json` each event is one readable line, which is no contract. JSONL is the one versioned shape here: what
another command prints with `--json`, and what an op's command prints, is that op's result or that command's report,
whose shape follows it, with no `format`.

{build().generate_docs(heading_level=2)}"""


if __name__ == "__main__":
    sys.stdout.write(reference())
