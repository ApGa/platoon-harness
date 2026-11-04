"""Annotations: what an estimator says of the record, a reward or a credit, kept in `annotations.sqlite` beside the
journal and never in it, as `git notes` attach to commits. Each is one producer's statement at one version about one
event at one head, never a fact. Nothing an agent can reach opens the file. See ADR 0011.
"""

import contextlib
import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, JsonValue, model_validator

from platoon_harness.kernel import Args, Refused
from platoon_harness.schema import Model

__all__ = ["ANNOTATIONS", "Annotate", "Annotation", "Status", "annotate", "annotations"]

ANNOTATIONS = "annotations.sqlite"

Status = Literal["scored", "invalid", "error", "cancelled", "unscored"]
"""How an estimate came out. Only `scored` has a value, so invalid, error, cancelled and unscored are never zero."""

EventRef = Annotated[str, Field(pattern=r"^[^\s@#]+@[1-9]\d{0,17}$", max_length=1024)]

_SECONDS = 5.0
_TABLE = """
CREATE TABLE IF NOT EXISTS annotations(
    id INTEGER PRIMARY KEY,
    target TEXT NOT NULL,
    kind TEXT NOT NULL,
    producer TEXT NOT NULL,
    producer_version TEXT NOT NULL,
    params_hash TEXT NOT NULL,
    scope TEXT NOT NULL,
    status TEXT NOT NULL,
    value REAL,
    evidence TEXT NOT NULL,
    head_seq INTEGER NOT NULL,
    wall_time REAL NOT NULL,
    UNIQUE (producer, producer_version, params_hash, target, kind)
) STRICT
"""


class Annotate(Args):
    """One statement about one event of the record, by a named estimator. It is unique on its producer, version, params,
    target and kind, so a second estimator, or a second version, writes beside the first."""

    target: Annotated[EventRef, Field(description="The event it is about, by its ref, `stream@version`.")]
    kind: Annotated[Literal["reward", "credit"], Field(description="`reward` or `credit`.")]
    producer: Annotated[str, Field(min_length=1, max_length=256, description="The estimator that made it, by name.")]
    producer_version: Annotated[str, Field(min_length=1, max_length=256, description="The estimator's version.")]
    params: Annotated[
        dict[str, JsonValue], Field(description="What the estimator was run with, kept as `params_hash`.")
    ] = {}
    scope: Annotated[
        Literal["local", "team"], Field(description="`local` for the target's own, `team` for what its team shares.")
    ]
    status: Annotated[Status, Field(description="`scored`, `invalid`, `error`, `cancelled` or `unscored`.")]
    value: Annotated[
        float | None, Field(allow_inf_nan=False, description="The estimate, given when `status` is `scored` alone.")
    ] = None
    evidence: Annotated[tuple[EventRef, ...], Field(description="The refs of the events it rests on.")] = ()
    head_seq: Annotated[
        int, Field(ge=1, lt=2**63, description="The head the estimator read at, which names the trace it is about.")
    ]

    @model_validator(mode="after")
    def _valued(self) -> "Annotate":
        if (self.value is not None) != (self.status == "scored"):
            raise ValueError("a value is given when the status is `scored`, and only then, as unscored is never zero")
        return self


class Annotation(Model):
    """A statement as `annotations.sqlite` holds it. A client shows its `value` only with its `producer` and
    `producer_version`, beside any other estimate of the same target, and never sums two into a fact."""

    id: int
    target: str
    kind: Literal["reward", "credit"]
    producer: str
    producer_version: str
    params_hash: str
    scope: Literal["local", "team"]
    status: Status
    value: float | None
    evidence: tuple[str, ...]
    head_seq: int
    wall_time: float


def _hashed(params: dict[str, JsonValue]) -> str:
    return hashlib.sha256(json.dumps(params, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _loaded(row: sqlite3.Row) -> Annotation:
    return Annotation.model_validate({**dict(row), "evidence": json.loads(row["evidence"])})


def annotate(folder: Path, statement: Annotate, wall_time: float) -> Annotation:
    """Write one statement beside a session's journal, with no runtime and no lock but the file's own, which it holds
    from its look for the key to its write. The same statement again is answered with the first, and another under the
    same producer, version, params, target and kind is refused `conflict`, naming the one there, as a key reused is."""
    said = {
        **statement.model_dump(include={"scope", "status", "value", "head_seq"}),
        "evidence": json.dumps(statement.evidence),
    }
    row = {**statement.model_dump(include={"target", "kind", "producer", "producer_version"}), **said}
    row |= {"params_hash": _hashed(statement.params), "wall_time": wall_time}
    try:
        with contextlib.closing(sqlite3.connect(folder / ANNOTATIONS, timeout=_SECONDS)) as db, db:
            db.row_factory = sqlite3.Row
            db.execute("BEGIN IMMEDIATE")
            db.execute(_TABLE)
            found = db.execute(
                """
                SELECT * FROM annotations WHERE producer = :producer AND producer_version = :producer_version
                    AND params_hash = :params_hash AND target = :target AND kind = :kind
                """,
                row,
            ).fetchone()
            if found is None:
                columns = ", ".join(row)
                found = db.execute(
                    f"INSERT INTO annotations ({columns}) VALUES ({', '.join(f':{key}' for key in row)}) RETURNING *",
                    row,
                ).fetchone()
            elif any(found[key] != value for key, value in said.items()):
                raise Refused("conflict", f"annotation {found['id']} says otherwise under this producer and version")
            return _loaded(found)
    except sqlite3.Error as error:
        raise Refused("unavailable", f"annotations cannot be written: {error}") from None


def annotations(folder: Path, target: str | None = None) -> list[Annotation]:
    """The statements about one event, or every one, oldest first. Reading writes nothing, so a folder with none stays
    as it was."""
    if not (folder / ANNOTATIONS).exists():
        return []
    try:
        uri = f"{(folder / ANNOTATIONS).as_uri()}?mode=ro"
        with contextlib.closing(sqlite3.connect(uri, uri=True, timeout=_SECONDS)) as db:
            db.row_factory = sqlite3.Row
            if db.execute("SELECT 1 FROM sqlite_schema WHERE name = 'annotations'").fetchone() is None:
                return []
            rows = db.execute(
                "SELECT * FROM annotations WHERE ?1 IS NULL OR target = ?1 ORDER BY id", (target,)
            ).fetchall()
            return [_loaded(row) for row in rows]
    except sqlite3.Error as error:
        raise Refused("unavailable", f"annotations cannot be read: {error}") from None
