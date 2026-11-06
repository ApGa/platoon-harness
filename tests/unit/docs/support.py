"""What the docs tests share: the repository's files, and Markdown's prose."""

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).parents[3]
FENCE = re.compile(r"^\s*(```|~~~)")


def tracked(*patterns: str) -> list[Path]:
    """Every file git tracks, or would track once added, that matches one of `patterns`, or every one with none."""
    listed = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z", "--", *patterns],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return sorted({ROOT / name for name in listed.split("\0") if name and (ROOT / name).is_file()})


def prose(path: Path) -> list[tuple[int, str]]:
    """The lines outside fenced code, with their numbers."""
    lines, fenced = [], False
    for number, line in enumerate(path.read_text().splitlines(), 1):
        if FENCE.match(line):
            fenced = not fenced
        elif not fenced:
            lines.append((number, line))
    return lines
