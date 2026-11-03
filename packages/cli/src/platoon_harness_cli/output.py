"""What the command line prints: JSONL in a versioned shape, a readable line per event, and text a terminal shows as
text."""

import json
import os
import sys
import unicodedata
from typing import Any

from platoon_harness import Ending
from platoon_harness.kernel import Event, Refusal

FORMAT = 1
"""The shape of a JSONL line. Every line carries it, so a consumer that starts with `--after` knows it too."""

_CONTROLS = ("Cc", "Cf", "Zl", "Zp")


def event_line(event: Event) -> str:
    """An event as JSONL: its envelope, as the journal holds it, with `format`."""
    return json.dumps({"format": FORMAT, **event.model_dump(mode="json")}, ensure_ascii=True)


def ending_line(ending: Ending, code: int) -> str:
    """The last JSONL line: the Ending, and the code the command exits with."""
    return json.dumps(
        {"format": FORMAT, "type": "ending", **ending.model_dump(mode="json"), "code": code}, ensure_ascii=True
    )


def readable(event: Event) -> str:
    """An event as a person reads it, which is no contract: its seq, who it is about, and its gist."""
    about = f"@{event.agent}" if event.agent else event.actor
    return safe(f"{event.seq:>6}  {about:<16} {event.gist}")


def readable_ending(ending: Ending, code: int) -> str:
    lines = [f"{ending.reason}, exit {code}"]
    for agent in ending.agents:
        report = agent["report"]["gist"] if agent["report"] else ""
        lines.append(f"  @{agent['agent']:<15} {agent['status'] or agent['state']:<9} {report}".rstrip())
    return safe("\n".join(lines))


def safe(text: str) -> str:
    """Text as a terminal shows text: a control character, which could move the cursor or retitle the window, is shown
    as its escape. A line break stays one."""
    return "\n".join(
        "".join(c if unicodedata.category(c) not in _CONTROLS else c.encode("unicode_escape").decode() for c in line)
        for line in text.split("\n")
    )


def say(text: str) -> None:
    """Write a line to stdout now. A reader that has gone takes nothing more, and the command goes on without it."""
    try:
        sys.stdout.write(text + "\n")
        sys.stdout.flush()
    except BrokenPipeError:
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())


def note(text: str) -> None:
    """A line for the person at the terminal, on stderr, which never holds anything a program reads."""
    print(f"platoon-harness: {safe(text)}", file=sys.stderr, flush=True)


def shown(value: Any) -> str:
    """A result as JSON that a person and a program both read, with nothing but ASCII to reach a terminal."""
    return json.dumps(value, indent=2, ensure_ascii=True)


def refused(refusal: Refusal) -> str:
    """A refusal as one line: its code, on what, and why."""
    detail = refusal.detail if isinstance(refusal.detail, str) else json.dumps(refusal.detail)
    return f"refused {refusal.code}{f' on {refusal.object}' if refusal.object else ''}: {detail}"
