"""journal.sqlite: the events, bodies and meta tables, and who may open them.

The pragmas, the checkpoint thread and the filesystem rules come from docs/research/spikes/journal-performance.md.
"""

import ctypes
import fcntl
import json
import logging
import os
import platform
import sqlite3
import sys
import threading
import time
from fnmatch import fnmatchcase
from pathlib import Path
from typing import NamedTuple
from uuid import uuid4

from .model import Event, ModelRef, Outcome, Refused

log = logging.getLogger("platoon_harness.kernel")

SCHEMA_VERSION = 1
CHECKPOINT_SECONDS = 1.0
WAL_ALARM_FRAMES = 16000

_LOCK_PAUSES = (0.001, 0.01, 0.0)
_TRUNCATE_WAIT_MS = 250
_READ_PRAGMAS = ("cache_size=-8192", "mmap_size=0", "temp_store=MEMORY")
_WRITE_PRAGMAS = (
    "synchronous=FULL",
    "fullfsync=ON",
    "checkpoint_fullfsync=ON",
    "wal_autocheckpoint=16000",
    "journal_size_limit=67108864",
    "secure_delete=ON",
)

_SCHEMA = """
CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT NOT NULL) WITHOUT ROWID, STRICT;

CREATE TABLE events(
    seq INTEGER PRIMARY KEY,
    stream TEXT NOT NULL,
    version INTEGER NOT NULL CHECK (version > 0),
    type TEXT NOT NULL,
    v INTEGER NOT NULL,
    actor TEXT NOT NULL,
    agent TEXT,
    turn TEXT,
    context_version INTEGER,
    episode TEXT,
    topology_rev INTEGER NOT NULL,
    correlation TEXT,
    cause TEXT NOT NULL,
    based_on TEXT NOT NULL,
    native TEXT NOT NULL,
    model TEXT,
    wall_time REAL NOT NULL,
    gist TEXT NOT NULL,
    data TEXT NOT NULL,
    outcome TEXT,
    UNIQUE (stream, version)
) STRICT;

CREATE INDEX events_command ON events(actor, outcome ->> '$.key') WHERE outcome ->> '$.key' IS NOT NULL;

CREATE TABLE bodies(sha256 TEXT PRIMARY KEY, size INTEGER NOT NULL, data BLOB) WITHOUT ROWID, STRICT;

CREATE TABLE v_folds(
    view TEXT PRIMARY KEY,
    version INTEGER NOT NULL,
    high_water INTEGER NOT NULL
) WITHOUT ROWID, STRICT;

CREATE TRIGGER events_no_replace BEFORE INSERT ON events
WHEN EXISTS (SELECT 1 FROM events WHERE seq = NEW.seq OR (stream = NEW.stream AND version = NEW.version))
BEGIN SELECT RAISE(ABORT, 'events are immutable'); END;

CREATE TRIGGER events_no_update BEFORE UPDATE ON events
BEGIN SELECT RAISE(ABORT, 'events are immutable'); END;

CREATE TRIGGER events_no_delete BEFORE DELETE ON events
BEGIN SELECT RAISE(ABORT, 'events are immutable'); END;

CREATE TRIGGER meta_no_update BEFORE UPDATE ON meta
BEGIN SELECT RAISE(ABORT, 'meta is written once'); END;

CREATE TRIGGER meta_no_delete BEFORE DELETE ON meta
BEGIN SELECT RAISE(ABORT, 'meta is written once'); END;
"""

# fmt: off
_NETWORK_MAGIC = {
    0x0BD00BD0: "lustre", 0x6969: "nfs", 0xFF534D42: "cifs", 0xFE534D42: "smb2", 0x517B: "smb", 0x47504653: "gpfs",
    0x19830326: "beegfs", 0x00C36400: "ceph", 0xAAD7AAEA: "panfs", 0x01161970: "gfs2", 0x7461636F: "ocfs2",
    0x5346414F: "afs", 0x6B414653: "kafs", 0x01021997: "9p", 0x786F4256: "vboxsf", 0x61636673: "acfs",
}
_LOCAL_MAGIC = {
    0x58465342: "xfs", 0xEF53: "ext4", 0x9123683E: "btrfs", 0x2FC12FC1: "zfs", 0x794C7630: "overlay",
    0xF2F52010: "f2fs", 0xCA451A4E: "bcachefs",
}
# fmt: on
_TMPFS_MAGIC = 0x01021994
_FUSE_MAGIC = 0x65735546
_NETWORK_FUSE = frozenset({"fuse.gcsfuse", "fuse.glusterfs", "fuse.rclone", "fuse.s3fs", "fuse.sshfs"})
_MNT_LOCAL = 0x1000
_PLAIN_COLUMNS = (
    "seq", "stream", "version", "type", "v", "actor", "agent", "turn", "context_version", "episode", "topology_rev",
    "correlation", "wall_time", "gist",
)  # fmt: skip
_INSERT = (
    f"INSERT INTO events ({', '.join(_PLAIN_COLUMNS)}, cause, based_on, native, model, data, outcome)"
    f" VALUES ({', '.join('?' * (len(_PLAIN_COLUMNS) + 6))})"
)


class Filesystem(NamedTuple):
    """What holds a path. `kind` is local, network, memory or unknown."""

    name: str
    kind: str


def _statfs(path: Path, size: int, symbol: str = "statfs") -> bytes:
    buffer = ctypes.create_string_buffer(size)
    if getattr(ctypes.CDLL(None, use_errno=True), symbol)(os.fsencode(path), buffer) != 0:
        raise OSError(ctypes.get_errno(), "statfs failed", str(path))
    return buffer.raw


def fuse_type(device: int, mountinfo: str) -> Filesystem:
    """Name a FUSE mount from its mountinfo line, matched on the device and not on a path prefix."""
    wanted = f"{os.major(device)}:{os.minor(device)}"
    for line in mountinfo.splitlines():
        before, _, after = line.partition(" - ")
        if before.split()[2] == wanted:
            name = after.split()[0]
            return Filesystem(name, "network" if name in _NETWORK_FUSE else "unknown")
    return Filesystem("fuse", "unknown")


def _linux_filesystem(path: Path) -> Filesystem:
    magic = int.from_bytes(_statfs(path, 256)[:8], sys.byteorder) & 0xFFFFFFFF  # f_type is the first long.
    if magic in _NETWORK_MAGIC:
        return Filesystem(_NETWORK_MAGIC[magic], "network")
    if magic in _LOCAL_MAGIC:
        return Filesystem(_LOCAL_MAGIC[magic], "local")
    if magic == _TMPFS_MAGIC:
        return Filesystem("tmpfs", "memory")
    if magic == _FUSE_MAGIC:
        return fuse_type(os.stat(path).st_dev, Path("/proc/self/mountinfo").read_text())
    return Filesystem(hex(magic), "unknown")


def _darwin_filesystem(path: Path) -> Filesystem:
    symbol = "statfs$INODE64" if platform.machine() == "x86_64" else "statfs"
    raw = _statfs(path, 2168, symbol)
    name = raw[72:88].partition(b"\0")[0].decode()
    return Filesystem(name, "local" if int.from_bytes(raw[64:68], sys.byteorder) & _MNT_LOCAL else "network")


def filesystem(path: str | os.PathLike[str]) -> Filesystem:
    """Say what holds `path`, or its nearest existing ancestor. The kernel resolves links and bind mounts."""
    existing = Path(path).absolute()
    while not existing.exists():
        existing = existing.parent
    return _darwin_filesystem(existing) if sys.platform == "darwin" else _linux_filesystem(existing)


def require_local(path: Path) -> None:
    """Refuse a live journal on a network filesystem, and warn where an ack promises less than usual."""
    found = filesystem(path)
    if found.kind == "network":
        raise Refused(
            "unsupported",
            f"{path} is on {found.name}, a network filesystem, and SQLite does not support WAL across hosts. "
            "Use a local directory, for example /var/tmp/platoon-harness-$UID, through $PLATOON_HARNESS_HOME.",
        )
    if found.kind == "memory":
        log.warning("%s is on %s: a session there survives a process crash but not a reboot", path, found.name)
    if found.kind == "unknown":
        log.warning("%s is on %s, which is not known to be local", path, found.name)


def take_lock(path: Path) -> int:
    """Become the one live writer, or refuse. The lock dies with the process.

    A first refusal may be `is_live` holding the lock for an instant, so only a lasting one counts.
    """
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    for pause in _LOCK_PAUSES:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return fd
        except BlockingIOError:
            time.sleep(pause)
    os.close(fd)
    raise Refused("unavailable", f"another runtime holds {path}")


def is_live(folder: Path) -> bool:
    """Whether the journal has a writer or unfinished WAL, and so cannot be read as immutable."""
    wal = folder / "journal.sqlite-wal"
    return (wal.exists() and wal.stat().st_size > 0) or is_held(folder)


def is_held(folder: Path) -> bool:
    """Whether a live runtime holds this folder's lock, which is how anyone can tell a session is live."""
    try:
        fd = os.open(folder / "lock", os.O_RDONLY)
    except FileNotFoundError:
        return False
    try:
        fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
    except BlockingIOError:
        return True
    finally:
        os.close(fd)
    return False


def fingerprint(folder: Path) -> tuple[int, int, int]:
    """What a writer changes. `immutable=1` tells SQLite not to look, so a reader of a closed journal must."""
    journal = (folder / "journal.sqlite").stat()
    wal = folder / "journal.sqlite-wal"
    return journal.st_mtime_ns, journal.st_size, wal.stat().st_size if wal.exists() else 0


def reader_uri(folder: Path, *, immutable: bool = False) -> str:
    uri = (folder / "journal.sqlite").resolve().as_uri()
    return f"{uri}?immutable=1" if immutable else f"{uri}?mode=ro"


def open_reader(uri: str) -> sqlite3.Connection:
    db = sqlite3.connect(uri, uri=True, autocommit=True, check_same_thread=False)
    db.row_factory = sqlite3.Row
    db.create_function("matches", 2, fnmatchcase, deterministic=True)
    for pragma in (*_READ_PRAGMAS, "query_only=ON"):
        db.execute(f"PRAGMA {pragma}")
    return db


def _connect_writable(path: Path) -> sqlite3.Connection:
    db = sqlite3.connect(path, autocommit=True, check_same_thread=False)
    db.row_factory = sqlite3.Row
    mode = db.execute("PRAGMA journal_mode=WAL").fetchone()[0]
    if mode != "wal":
        raise Refused("unsupported", f"journal mode is {mode}, not WAL")
    for pragma in (*_READ_PRAGMAS, *_WRITE_PRAGMAS):
        db.execute(f"PRAGMA {pragma}")
    return db


def open_writer(path: Path, created: float) -> sqlite3.Connection:
    """Open the one write connection, creating the schema if this is a new journal."""
    db = _connect_writable(path)
    if db.execute("SELECT 1 FROM sqlite_master WHERE name = 'meta'").fetchone() is None:
        db.execute("BEGIN IMMEDIATE")
        db.executescript(_SCHEMA)
        db.executemany(
            "INSERT INTO meta VALUES (?, ?)",
            [("schema_version", str(SCHEMA_VERSION)), ("session_id", uuid4().hex), ("created", repr(created))],
        )
        db.execute("COMMIT")
    return db


def check_schema(db: sqlite3.Connection) -> None:
    """Refuse a journal this kernel cannot read."""
    found = int(db.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()[0])
    if found != SCHEMA_VERSION:
        raise Refused("unsupported", f"journal schema {found}; this kernel reads {SCHEMA_VERSION}")


def checkpoint(db: sqlite3.Connection) -> None:
    """Move what it can of the WAL into the database, and say so if a reader is pinning the rest."""
    _, logged, moved = db.execute("PRAGMA wal_checkpoint(PASSIVE)").fetchone()
    if logged - moved > WAL_ALARM_FRAMES:
        log.warning("%d WAL frames cannot be checkpointed: a reader is holding a snapshot", logged - moved)


def truncate_wal(db: sqlite3.Connection) -> bool:
    """Checkpoint the WAL to empty. False means a reader kept it from emptying."""
    db.execute(f"PRAGMA busy_timeout={_TRUNCATE_WAIT_MS}")
    return db.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()[0] == 0


def scrub_wal(path: Path) -> bool:
    """Truncate the WAL beside a working writer, on a connection of its own."""
    db = _connect_writable(path)
    try:
        return truncate_wal(db)
    finally:
        db.close()


class Checkpointer:
    """Checkpoints on its own connection, so a commit rarely absorbs the syncs. `wal_autocheckpoint` stays the cap."""

    def __init__(self, path: Path) -> None:
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, args=(path,), name="journal-checkpoint", daemon=True)
        self._thread.start()

    def _run(self, path: Path) -> None:
        db = _connect_writable(path)
        while not self._stop.wait(CHECKPOINT_SECONDS):
            try:
                checkpoint(db)
            except sqlite3.Error:
                log.exception("a checkpoint failed")
        db.close()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join()


def last_seq(db: sqlite3.Connection) -> int:
    return db.execute("SELECT coalesce(max(seq), 0) FROM events").fetchone()[0]


def stream_version(db: sqlite3.Connection, stream: str) -> int:
    return db.execute("SELECT coalesce(max(version), 0) FROM events WHERE stream = ?", (stream,)).fetchone()[0]


def insert(db: sqlite3.Connection, event: Event, data: str) -> None:
    db.execute(
        _INSERT,
        (
            *(getattr(event, column) for column in _PLAIN_COLUMNS),
            json.dumps(event.cause),
            json.dumps(event.based_on),
            json.dumps(dict(event.native), sort_keys=True),
            None if event.model is None else event.model.model_dump_json(),
            data,
            None if event.outcome is None else event.outcome.model_dump_json(),
        ),
    )


def prior_outcome(db: sqlite3.Connection, actor: str, key: str) -> Outcome | None:
    """The first answer given under a key, so a retry receives it, refusals included."""
    row = db.execute(
        "SELECT outcome FROM events WHERE actor = ? AND outcome ->> '$.key' = ? ORDER BY seq LIMIT 1", (actor, key)
    ).fetchone()
    return None if row is None else Outcome.model_validate_json(row["outcome"])


def decode(row: sqlite3.Row, *, with_outcome: bool = True) -> Event:
    """Rebuild an event from its row. Rows are ours, so nothing is revalidated."""
    outcome = None
    if with_outcome and row["outcome"] is not None:
        outcome = Outcome.model_validate_json(row["outcome"])
    return Event.model_construct(
        **{column: row[column] for column in _PLAIN_COLUMNS},
        cause=tuple(json.loads(row["cause"])),
        based_on=tuple(json.loads(row["based_on"])),
        native=json.loads(row["native"]),
        model=None if row["model"] is None else ModelRef.model_validate_json(row["model"]),
        data=json.loads(row["data"]),
        outcome=outcome,
    )
