"""`bwrap`: an isolation on Linux's bubblewrap, which an isolated agent's harness, and the runtime's own git in its
tree, run in. It needs unprivileged user namespaces, and keeps the network. Nothing in the SDK imports this module: a
team that names `bwrap` among its extensions loads it."""

import errno
import os
import shutil
import subprocess
from collections.abc import Sequence
from pathlib import Path

from platoon_harness.kernel import Extension

_PROBE_SECONDS = 10.0
_TMP = Path("/tmp")
_LINKS = 40
"""How many links a path may pass through, as the kernel allows."""
_OWN = ("--unshare-user", "--unshare-pid", "--unshare-ipc", "--new-session", "--die-with-parent")
"""Users, processes and IPC of its own, a terminal session of its own, and its end with whoever started it."""
_SEEN = ("--ro-bind", "/", "/", "--proc", "/proc", "--dev", "/dev")
"""Everything you can read, read-only, a /proc that shows only its own processes, and a /dev of its own."""

__all__ = ["Bubblewrap", "extension"]


def _walked(path: Path) -> tuple[list[tuple[str, Path]], Path]:
    """Each link on the way to `path`, as it is written and where it is, and the path that is not a link it comes to."""
    links: list[tuple[str, Path]] = []
    at, rest = Path("/"), list(path.parts[1:])
    while rest:
        part = rest.pop(0)
        at = at.parent if part == ".." else at / part
        if at.is_symlink():
            if len(links) == _LINKS:
                raise OSError(errno.ELOOP, os.strerror(errno.ELOOP), str(path))
            written = Path(os.readlink(at))
            links.append((str(written), at))
            at = Path("/") if written.is_absolute() else at.parent
            rest = [*written.parts[written.is_absolute() :], *rest]
    return links, at


def _outermost(paths: Sequence[Path]) -> list[Path]:
    """Each of `paths` that lies in none of the others, once."""
    return [
        path
        for path in dict.fromkeys(paths)
        if not any(path != other and path.is_relative_to(other) for other in paths)
    ]


def _within(path: Path, places: Sequence[Path]) -> bool:
    return any(path.is_relative_to(place) for place in places)


class Bubblewrap:
    """An isolation on `bwrap`. The probe and every wrap make the same namespaces and the same view of the system."""

    def refusal(self) -> str | None:
        """Why bwrap cannot confine here: it is not on `PATH`, or it fails to confine `true`, as where user namespaces
        are blocked, by a kernel setting, AppArmor or a container's seccomp."""
        if shutil.which("bwrap") is None:
            return "`bwrap` is not on PATH: install bubblewrap"
        try:
            done = subprocess.run(
                ["bwrap", *_OWN, *_SEEN, "true"], capture_output=True, text=True, timeout=_PROBE_SECONDS, check=False
            )
        except subprocess.TimeoutExpired:
            return f"`bwrap` did not confine `true` within {_PROBE_SECONDS:.0f} s"
        if done.returncode != 0:
            said = done.stderr.strip() or f"exit {done.returncode}"
            return f"`bwrap` cannot confine anything here, as where user namespaces are blocked: {said}"
        return None

    def wrap(self, writable: Path, readable: Sequence[Path], hidden: Sequence[Path]) -> tuple[str, ...]:
        """`bwrap`'s argv: an empty tmpfs over /tmp, then over each of `hidden`; each link a `readable` path or
        `writable` passes through in those, made again as it is written, but in a folder bound whole, which holds it
        already; what each readable path comes to there, bound read-only at its own path; what `writable` comes to,
        bound where it can be written; and each hidden folder made read-only, so that only what is bound in it shows."""
        tops = _outermost(hidden)
        covered = [_TMP, *tops]
        reads, (passed, mine) = [_walked(path) for path in readable], _walked(writable)
        ends = _outermost([end for _, end in reads if _within(end, covered)])
        whole = [*ends, mine]
        links = dict.fromkeys(
            (written, where)
            for made in (*(made for made, _ in reads), passed)
            for written, where in made
            if _within(where, covered) and not any(where != end and where.is_relative_to(end) for end in whole)
        )
        argv = ["bwrap", *_OWN, *_SEEN]
        argv += [part for top in covered for part in ("--tmpfs", str(top))]
        argv += [part for written, where in links for part in ("--symlink", written, str(where))]
        argv += [part for end in ends for part in ("--ro-bind", str(end), str(end))]
        argv += ["--bind", str(mine), str(mine)]
        argv += [part for top in tops for part in ("--remount-ro", str(top))]
        return (*argv, "--")


extension = Extension("bwrap", isolation=Bubblewrap())
