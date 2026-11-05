"""Where a session lives: its root, its folder, its socket, and what a live runtime leaves beside its journal."""

import errno
import hashlib
import logging
import os
import re
import secrets
import stat
import tempfile
import time
from collections.abc import Mapping
from pathlib import Path
from typing import NamedTuple

from platoon_harness.drivers.levels import Conformance
from platoon_harness.kernel import NAME, Refused, filesystem, is_held
from platoon_harness.schema import ConfigError, Model, Problem

HOME_VARIABLE = "PLATOON_HARNESS_HOME"
MANIFEST = "manifest.json"
RUNNING = "runtime.json"
OWNER_TOKEN = "owner.token"
VIEW_TOKEN = "view.token"
LOG = "runtime.log"
MARKS = "marks.sqlite"
CONFORMANCE = "conformance"

_SOCKET_LIMIT = 103
_HASH_LENGTH = 16

log = logging.getLogger("platoon_harness.runtime")

__all__ = [
    "CONFORMANCE",
    "HOME_VARIABLE",
    "LOG",
    "MANIFEST",
    "MARKS",
    "OWNER_TOKEN",
    "RUNNING",
    "VIEW_TOKEN",
    "Listed",
    "Running",
    "agent_folder",
    "find_root",
    "listing",
    "new_folder",
    "open_log",
    "read_conformance",
    "read_running",
    "root_of",
    "session_folder",
    "sessions_of",
    "socket_path",
    "write_conformance",
    "write_private",
]


def find_root(
    chosen: str | os.PathLike[str] | None = None, environ: Mapping[str, str] = os.environ, *, writing: bool = False
) -> Path:
    """Where sessions live: `chosen`, then `$PLATOON_HARNESS_HOME`, then `$XDG_STATE_HOME/platoon-harness`.

    A default on a network filesystem falls back to a local directory, with a notice. A root someone chose stays theirs,
    so `writing` there is refused: a closed session is portable, and a live journal is not. To write, a root must be
    this user's and nobody else's to change, since what its folders say can run as this user on a resume.
    """
    explicit = chosen or environ.get(HOME_VARIABLE)
    if explicit:
        root = Path(explicit)
        found = filesystem(root)
        if writing and found.kind == "network":
            what = f"{root} is on {found.name}, a network filesystem, where a live journal is not safe"
            raise ConfigError([Problem(HOME_VARIABLE, f"{what}. Choose a local directory")])
        return _writable(root) if writing else root
    root = Path(environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state") / "platoon-harness"
    if filesystem(root).kind != "network":
        return _writable(root) if writing else root
    fallback = Path(f"/var/tmp/platoon-harness-{os.getuid()}")
    log.warning("%s is on a network filesystem, so sessions live in %s", root, fallback)
    if writing:
        _make_private(fallback)
    return fallback


def _writable(root: Path) -> Path:
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    found = root.stat()
    if found.st_uid != os.getuid() or found.st_mode & stat.S_IWOTH:
        raise ConfigError([Problem(str(root), "must be a directory of this user's that nobody else can write")])
    return root


def sessions_of(root: Path) -> Path:
    """The folder every session under a root lives in."""
    return root / "sessions"


def new_folder(root: Path, manifest: str, name: str | None = None) -> Path:
    """Make a session's folder with its manifest in it. The folder is built aside and renamed into place, so a name is
    claimed whole or not at all: no two sessions can share one, and a crash here burns none."""
    if name is not None and re.fullmatch(NAME, name) is None:
        raise Refused("invalid", f"{name!r} cannot name a session: it must be safe as a part of a path")
    sessions = sessions_of(root)
    _make_private(sessions)
    folder = sessions / (name or f"{time.strftime('%Y%m%d-%H%M%S')}-{secrets.token_hex(4)}")
    built = Path(tempfile.mkdtemp(dir=root, prefix=".new-"))
    write_private(built / MANIFEST, manifest)
    try:
        built.rename(folder)
    except OSError as error:
        (built / MANIFEST).unlink()
        built.rmdir()
        if error.errno not in (errno.EEXIST, errno.ENOTEMPTY):
            raise
        raise Refused("conflict", f"session {folder.name} exists: resume it, or choose another name") from None
    return folder


def root_of(session: Path) -> Path:
    """The root a session's folder lives under, as `sessions_of` places it."""
    return session.parent.parent


def write_conformance(root: Path, result: Conformance) -> Path:
    """Keep what `check_driver` found of a driver's harness under a root, replacing what was kept for that driver, as
    one result speaks for the binary that runs. A driver's name is a path part."""
    if re.fullmatch(NAME, result.driver) is None:
        raise Refused("invalid", f"{result.driver!r} cannot name a file: a driver's name is a part of a path")
    folder = root / CONFORMANCE
    _make_private(folder)
    path = folder / f"{result.driver}.json"
    write_private(path, result.model_dump_json(indent=2))
    return path


def read_conformance(root: Path, driver: str) -> Conformance | None:
    """What was kept under a root of a driver's harness, or None when nothing was, or what was no longer reads, as
    after an upgrade of the SDK, since then nothing vouches for it."""
    if re.fullmatch(NAME, driver) is None:
        return None
    try:
        return Conformance.model_validate_json((root / CONFORMANCE / f"{driver}.json").read_bytes())
    except (OSError, ValueError):
        return None


def session_folder(root: Path, name: str) -> Path:
    """The folder of an existing session, or refuse. One made before names were held to git's grammar is named as no
    longer valid, with the way to rename it."""
    folder = sessions_of(root) / name
    one_part = name not in (".", "..") and "/" not in name
    if re.fullmatch(NAME, name) is None and one_part and (folder / MANIFEST).exists():
        what = (
            f"{name} no longer names a session, since a name may not hold `..` or end in `.` or `.lock`: rename its "
            f"folder {folder} while no runtime holds it"
        )
        raise Refused("invalid", what)
    if re.fullmatch(NAME, name) is None or not (folder / MANIFEST).exists():
        raise Refused("not_found", f"no session {name} under {root}")
    return folder


def agent_folder(session: Path, agent: str) -> Path:
    """An agent's own directory: its process record, its log, its native home, its `ph`."""
    return session / "agents" / agent


class Listed(NamedTuple):
    """One session on disk. `live` is whether a runtime holds it now."""

    name: str
    folder: Path
    live: bool


def listing(root: Path) -> list[Listed]:
    """Every session under a root. There is no registry: a scan finds them, and `flock` says which are live."""
    sessions = sessions_of(root)
    folders = sorted(sessions.iterdir()) if sessions.exists() else []
    return [Listed(folder.name, folder, is_held(folder)) for folder in folders if (folder / MANIFEST).exists()]


def _make_private(folder: Path) -> None:
    """Make a directory only this user can reach. An old one must be ours, and then it is ours to tighten."""
    folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    found = folder.lstat()
    if not stat.S_ISDIR(found.st_mode) or found.st_uid != os.getuid():
        raise ConfigError([Problem(str(folder), "must be a directory of this user's")])
    folder.chmod(0o700)


def socket_path(session: Path, environ: Mapping[str, str] = os.environ) -> Path:
    """Where a session's socket goes: a hash of its folder, since a copy of a closed session keeps its journal and has a
    folder of its own, in a private directory, never inside a folder of any depth, since a `bind` takes 107 bytes on
    Linux and 103 on macOS. A runtime directory that cannot be used falls through to the next."""
    name = f"{hashlib.sha256(str(session.resolve()).encode()).hexdigest()[:_HASH_LENGTH]}.sock"
    runtime_dir = environ.get("XDG_RUNTIME_DIR")
    folders = [Path(runtime_dir) / "platoon-harness"] if runtime_dir else []
    for folder in (*folders, Path(f"/tmp/platoon-harness-{os.getuid()}")):
        if len(os.fsencode(folder / name)) <= _SOCKET_LIMIT:
            try:
                _make_private(folder)
            except OSError:
                continue
            return folder / name
    raise ConfigError([Problem("sockets", f"no private directory holds a socket path in {_SOCKET_LIMIT} bytes")])


class Running(Model):
    """What a live runtime says of itself in `runtime.json`. Only the lock proves it is true."""

    pid: int
    started: float
    socket: str
    incarnation: int


def read_running(folder: Path) -> Running | None:
    """The runtime a folder names, which may be a dead one's until the next takes over."""
    try:
        return Running.model_validate_json((folder / RUNNING).read_bytes())
    except FileNotFoundError:
        return None


def open_log(folder: Path) -> int:
    """A descriptor on a runtime's log, for whichever side has to point stderr at it first."""
    return os.open(folder / LOG, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)


def write_private(path: Path, text: str) -> None:
    """Replace a file in one step, readable by this user alone, and on disk before this returns."""
    descriptor, scratch = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    with os.fdopen(descriptor, "w") as file:
        file.write(text)
        file.flush()
        os.fsync(file.fileno())
    os.replace(scratch, path)
    folder = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(folder)
    finally:
        os.close(folder)
