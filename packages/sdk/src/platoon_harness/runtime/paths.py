"""Where a session lives: its root, its folder, its socket, and what a live runtime leaves beside its journal."""

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

from platoon_harness.kernel import NAME, Refused, filesystem, is_held
from platoon_harness.schema import ConfigError, Model, Problem

HOME_VARIABLE = "PLATOON_HARNESS_HOME"
MANIFEST = "manifest.json"
RUNNING = "runtime.json"
OWNER_TOKEN = "owner.token"
VIEW_TOKEN = "view.token"
LOG = "runtime.log"

_SOCKET_LIMIT = 103
_HASH_LENGTH = 16

log = logging.getLogger("platoon_harness.runtime")

__all__ = [
    "HOME_VARIABLE",
    "LOG",
    "MANIFEST",
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
    "read_running",
    "session_folder",
    "socket_path",
    "write_private",
]


def find_root(
    chosen: str | os.PathLike[str] | None = None, environ: Mapping[str, str] = os.environ, *, writing: bool = False
) -> Path:
    """Where sessions live: `chosen`, then `$PLATOON_HARNESS_HOME`, then `$XDG_STATE_HOME/platoon-harness`.

    A default on a network filesystem falls back to a local directory, with a notice. A root someone chose stays theirs,
    so `writing` there is refused: a closed session is portable, and a live journal is not.
    """
    explicit = chosen or environ.get(HOME_VARIABLE)
    if explicit:
        root = Path(explicit)
        found = filesystem(root)
        if writing and found.kind == "network":
            what = f"{root} is on {found.name}, a network filesystem, where a live journal is not safe"
            raise ConfigError([Problem(HOME_VARIABLE, f"{what}. Choose a local directory")])
        return root
    root = Path(environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state") / "platoon-harness"
    if filesystem(root).kind != "network":
        return root
    fallback = Path(f"/var/tmp/platoon-harness-{os.getuid()}")
    log.warning("%s is on a network filesystem, so sessions live in %s", root, fallback)
    return fallback


def _sessions_of(root: Path) -> Path:
    return root / "sessions"


def new_folder(root: Path, name: str | None = None) -> Path:
    """Make a session's folder. Creating it is what claims the name, so no two sessions can share one."""
    sessions = _sessions_of(root)
    sessions.mkdir(mode=0o700, parents=True, exist_ok=True)
    if name is not None and re.fullmatch(NAME, name) is None:
        raise Refused("invalid", f"{name!r} cannot name a session: it must be safe as a part of a path")
    folder = sessions / (name or f"{time.strftime('%Y%m%d-%H%M%S')}-{secrets.token_hex(2)}")
    try:
        folder.mkdir(mode=0o700)
    except FileExistsError:
        raise Refused("conflict", f"session {folder.name} exists: resume it, or choose another name") from None
    return folder


def session_folder(root: Path, name: str) -> Path:
    """The folder of an existing session, or refuse."""
    folder = _sessions_of(root) / name
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
    sessions = _sessions_of(root)
    folders = sorted(sessions.iterdir()) if sessions.exists() else []
    return [Listed(folder.name, folder, is_held(folder)) for folder in folders if (folder / MANIFEST).exists()]


def _make_private(folder: Path) -> None:
    """Make a directory only this user can reach. An old one must be ours, and then it is ours to tighten."""
    folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    found = folder.lstat()
    if not stat.S_ISDIR(found.st_mode) or found.st_uid != os.getuid():
        raise Refused("unsupported", f"{folder} must be a directory of this user's")
    folder.chmod(0o700)


def socket_path(session_id: str, environ: Mapping[str, str] = os.environ) -> Path:
    """Where a session's socket goes: a short hash in a private directory, never inside a folder of any depth, since a
    `bind` takes 107 bytes on Linux and 103 on macOS."""
    name = f"{hashlib.sha256(session_id.encode()).hexdigest()[:_HASH_LENGTH]}.sock"
    runtime_dir = environ.get("XDG_RUNTIME_DIR")
    folders = [Path(runtime_dir) / "platoon-harness"] if runtime_dir else []
    for folder in (*folders, Path(f"/tmp/platoon-harness-{os.getuid()}")):
        if len(os.fsencode(folder / name)) <= _SOCKET_LIMIT:
            _make_private(folder)
            return folder / name
    raise Refused("unsupported", f"no socket path fits in {_SOCKET_LIMIT} bytes")


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
