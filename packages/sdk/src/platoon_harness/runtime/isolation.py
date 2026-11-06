"""Isolated workspaces: snapshots whose harness, and the runtime's own git in their tree, an extension's isolation
confines. The core says what an isolated agent may write and read, and the isolation makes it so. See architecture
section 13."""

import contextlib
import os
import pwd
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Protocol

from platoon_harness.drivers import DriverInfo
from platoon_harness.kernel import Extension
from platoon_harness.schema import Problem
from platoon_harness.team import Team

from .paths import root_of

__all__ = ["Isolation", "hidden", "isolation_of", "problems"]


class Isolation(Protocol):
    """What confines an isolated agent, which an extension gives as its `isolation`."""

    def refusal(self) -> str | None:
        """Why it cannot confine anything on this machine now, or None when it can."""
        ...

    def wrap(self, writable: Path, readable: Sequence[Path], hidden: Sequence[Path]) -> tuple[str, ...]:
        """The argv that runs a command after it so that it writes only in `writable` and a /tmp of its own, finds each
        of `hidden` empty but for the `readable` paths in it, each as it resolves outside, and sees only the processes
        it starts, which all end when it does. It keeps the network."""
        ...


def isolation_of(extensions: Iterable[Extension]) -> Isolation | None:
    """The isolation of the one extension among `extensions` that gives one, or None where none does or several do,
    which a check before any cost refuses."""
    given = [extension.isolation for extension in extensions if extension.isolation is not None]
    return given[0] if len(given) == 1 else None


def problems(
    team: Team, known: Mapping[str, DriverInfo], extensions: Sequence[Extension], *, trainable: bool
) -> list[Problem]:
    """What stops a team's isolated roles before any cost: no extension the team names gives an isolation, or several
    do; its isolation cannot confine here; a harness declares no installed path, so it would not run; or a harness
    would sign itself in, as its login is in your home, which an isolated harness never sees. `known` is what each
    role's driver says of itself, and `trainable` that a training system's gateway is every agent's access."""
    isolated = [name for name, role in team.roles.items() if role.workspace == "isolated"]
    if not isolated:
        return []
    givers = [extension for extension in extensions if extension.isolation is not None]
    if not givers:
        what = "`isolated` needs an extension the team names whose isolation confines a harness, such as `bwrap`"
        return [Problem(f"roles.{name}.workspace", what) for name in isolated]
    if len(givers) > 1:
        names = " and ".join(f"`{extension.name}`" for extension in givers)
        return [Problem("extensions", f"{names} each give an isolation, and an isolated agent runs in one: name one")]
    found = []
    if (why := givers[0].isolation.refusal()) is not None:
        found.append(Problem(f"extensions.{givers[0].name}", why))
    for name in isolated:
        if (info := known.get(name)) is None:
            continue  # Its harness is named already.
        if not info.installed:
            what = (
                f"`{info.name}` declares no path its harness is installed at, so an isolation could not show it: a "
                "harness in the runtime's own process cannot be confined, and one `PATH` does not find cannot run"
            )
            found.append(Problem(f"roles.{name}.harness", what))
        if team.roles[name].auth is None and not trainable and info.login is not None:
            what = (
                f"`isolated` gives `{info.name}` a home of its own, where the {info.login} login it signs in with in "
                "yours is not: give the role an auth profile"
            )
            found.append(Problem(f"roles.{name}.auth", what))
    return found


def hidden(session: Path) -> tuple[Path, ...]:
    """What an isolated agent of `session` sees nothing of, of what is there: your home, as `HOME` names it and as your
    account does, every session under its root, and the runtime directory sockets are made in."""
    places = [Path.home(), root_of(session)]
    with contextlib.suppress(KeyError):
        places.append(Path(pwd.getpwuid(os.getuid()).pw_dir))
    if runtime := os.environ.get("XDG_RUNTIME_DIR"):
        places.append(Path(runtime))
    return tuple(place for place in dict.fromkeys(places) if place.is_dir())
