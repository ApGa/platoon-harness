"""The content store: small bodies in the journal, large ones in blobs/, either tombstoned for redaction."""

import fcntl
import os
import sqlite3
import sys
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import Field

from .daemon import Daemon
from .model import Event, Refused
from .op import Args, op
from .txn import Txn
from .view import View, fold

if TYPE_CHECKING:
    from .kernel import Kernel


def _sync(fd: int) -> None:
    if sys.platform == "darwin":
        fcntl.fcntl(fd, fcntl.F_FULLFSYNC)
    else:
        os.fsync(fd)


def _sync_folder(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


class Blobs:
    """Files named by their hash. A file and its folders are synced before anything can cite them."""

    def __init__(self, root: Path) -> None:
        self._root = root

    def _path(self, sha256: str) -> Path:
        return self._root / sha256[:2] / sha256

    def write(self, sha256: str, body: bytes) -> None:
        path = self._path(sha256)
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            fd, temporary = tempfile.mkstemp(dir=path.parent)
            with os.fdopen(fd, "wb") as file:
                file.write(body)
                file.flush()
                _sync(file.fileno())
            os.replace(temporary, path)
        for folder in (path.parent, self._root, self._root.parent):
            _sync_folder(folder)

    def read(self, sha256: str) -> bytes:
        return self._path(sha256).read_bytes()

    def erase(self, sha256: str) -> None:
        path = self._path(sha256)
        if path.exists():
            path.unlink()
            _sync_folder(path.parent)


class Tombstones(View):
    """Bodies redacted for good. The event and its hash survive; the bytes do not."""

    schema = "CREATE TABLE v_tombstones(sha256 TEXT PRIMARY KEY, seq INTEGER NOT NULL) WITHOUT ROWID, STRICT;"

    @fold("body.tombstoned")
    def tombstoned(self, event: Event) -> None:
        self.db.execute("INSERT OR IGNORE INTO v_tombstones VALUES (?, ?)", (event.data["sha256"], event.seq))

    def has(self, sha256: str) -> bool:
        return self.db.execute("SELECT 1 FROM v_tombstones WHERE sha256 = ?", (sha256,)).fetchone() is not None

    def inline(self, sha256: str) -> bytes | None:
        """A body's bytes if the journal holds them; None if they are in `blobs/`, which an op may not read."""
        return lookup(self.db, sha256)["data"]


def record(db: sqlite3.Connection, sha256: str, size: int, inline: bytes | None) -> None:
    """Enter a body in the journal. Redacted content does not come back."""
    if Tombstones(db).has(sha256):
        raise Refused("conflict", "this body was tombstoned")
    db.execute("INSERT OR IGNORE INTO bodies VALUES (?, ?, ?)", (sha256, size, inline))


def forget(db: sqlite3.Connection, sha256: str) -> None:
    """Remove a tombstoned body's row."""
    if not Tombstones(db).has(sha256):
        raise Refused("conflict", "only a tombstoned body can be erased")
    db.execute("DELETE FROM bodies WHERE sha256 = ?", (sha256,))


def lookup(db: sqlite3.Connection, sha256: str) -> sqlite3.Row:
    """Find a readable body's row, or say why there is none."""
    if Tombstones(db).has(sha256):
        raise Refused("not_found", "this body was tombstoned")
    row = db.execute("SELECT size, data FROM bodies WHERE sha256 = ?", (sha256,)).fetchone()
    if row is None:
        raise Refused("not_found", f"no body {sha256}")
    return row


class Tombstone(Args):
    sha256: str = Field(pattern="^[0-9a-f]{64}$")


@op("body.tombstone", on=lambda a: f"body/{a.sha256}")
def tombstone_body(txn: Txn, a: Tombstone) -> None:
    """Redact a body. Reads stop now; a daemon erases the bytes. Events citing the hash stay whole."""
    stream = f"body/{a.sha256}"
    txn.emit("body.tombstoned", stream, gist=f"body {a.sha256[:12]} tombstoned", data=a)
    txn.effect("erase", {"sha256": a.sha256}, on_uncertain="retry", timeout=60.0)


async def _erase_tombstoned(kernel: "Kernel") -> None:
    runtime = kernel.runtime
    while not kernel.closed:
        head = kernel.head
        for effect in kernel.query(runtime, "effect.ready", {"kind": "erase"}).result:
            started = await kernel.submit(runtime, "effect.start", {"id": effect["id"]})
            await kernel.erase_body(effect["data"]["sha256"])
            await kernel.submit(runtime, "effect.finish", {"id": effect["id"], "attempt": started.result})
        await kernel.changed(head)


eraser_daemon = Daemon("eraser", _erase_tombstoned)
