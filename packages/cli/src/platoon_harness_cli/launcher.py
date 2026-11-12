"""The `platoon-harness` command. It imports nothing outside the standard library before the command line, so where the
`cli` extra is not installed it says what to install, rather than failing on an import."""

import re
import sys
from importlib import metadata

from .exits import CONFIGURATION

_EXTRA = re.compile(r"""^(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)[^;]*;.*\bextra\s*==\s*["']cli["']""")
"""A requirement of the `cli` extra, as installed metadata spells it, and the distribution it names."""


def missing() -> list[str]:
    """Each distribution the `cli` extra requires that is not installed, as the installed platoon-harness says."""
    named = [found["name"] for line in metadata.requires("platoon-harness") or () if (found := _EXTRA.match(line))]
    absent = []
    for name in named:
        try:
            metadata.distribution(name)
        except metadata.PackageNotFoundError:
            absent.append(name)
    return absent


def hint(absent: list[str]) -> str:
    """What the command says where the distributions `absent` of the `cli` extra are not installed."""
    return (
        f"platoon-harness: the command line needs its cli extra, and {sys.executable} has no {', '.join(absent)}: "
        'uv tool install "platoon-harness[cli]", naming again every extra and --with the tool has, '
        'uv add "platoon-harness[cli]" in a project, or pip install "platoon-harness[cli]"'
    )


def main() -> int:
    """Run the command line, or, where the `cli` extra is not installed, say what to install and exit 78."""
    if absent := missing():
        print(hint(absent), file=sys.stderr)
        return CONFIGURATION
    from .main import main as command_line

    return command_line()
