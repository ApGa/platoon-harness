"""Boards: named objects with immutable versions, found by structured query."""

import json
import re
import sqlite3
from typing import Annotated, Any

from pydantic import Field, JsonValue

from platoon_harness.kernel import Args, Event, Refused, Txn, View, fold, op

from .channels import Channels
from .common import RESULT_LIMIT, BodyRef, Exposed, Gist, Name, decoded, expose_read, fitted, inline_body, size_of

_RANGE = re.compile(r"L([1-9]\d*)-([1-9]\d*)")
_FIELDS_LIMIT = 4096

Scalar = str | int | float | bool | None


def _has_fts5() -> bool:
    probe = sqlite3.connect(":memory:")
    try:
        probe.execute("CREATE VIRTUAL TABLE probe USING fts5(text)")
    except sqlite3.OperationalError:
        return False
    finally:
        probe.close()
    return True


FTS5 = _has_fts5()


class Board(View):
    """One row per version. Text search covers names, gists and fields, never a body: a fold cannot read one, and a
    tombstoned body must leave nothing behind."""

    schema = """
    CREATE TABLE v_board(
        seq INTEGER PRIMARY KEY,
        board TEXT NOT NULL,
        name TEXT NOT NULL,
        version INTEGER NOT NULL,
        actor TEXT NOT NULL,
        gist TEXT NOT NULL,
        body TEXT,
        fields TEXT NOT NULL,
        latest INTEGER NOT NULL
    ) STRICT;
    CREATE UNIQUE INDEX v_board_version ON v_board(board, name, version);
    CREATE INDEX v_board_latest ON v_board(board, latest, seq);
    """ + ("CREATE VIRTUAL TABLE v_board_text USING fts5(name, gist, fields);" if FTS5 else "")

    @fold("board.posted", "board.revised")
    def versioned(self, event: Event) -> None:
        data = event.data
        fields = json.dumps(data["fields"], sort_keys=True)
        self.db.execute("UPDATE v_board SET latest = 0 WHERE board = ? AND name = ?", (data["board"], data["name"]))
        self.db.execute(
            "INSERT INTO v_board VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)",
            (event.seq, data["board"], data["name"], event.version, event.actor, event.gist, data["body"], fields),
        )
        if FTS5:
            self.db.execute(
                "INSERT INTO v_board_text(rowid, name, gist, fields) VALUES (?, ?, ?, ?)",
                (event.seq, data["name"], event.gist, fields),
            )

    def get(self, board: str, name: str, version: int | None = None) -> sqlite3.Row | None:
        """One version, the latest if none is named."""
        pick = "latest = 1" if version is None else "version = :version"
        return self.db.execute(
            f"SELECT * FROM v_board WHERE board = :board AND name = :name AND {pick}",
            {"board": board, "name": name, "version": version},
        ).fetchone()

    def find(
        self,
        board: str,
        *,
        prefix: str | None,
        author: str | None,
        where: dict[str, Scalar],
        text: str | None,
        history: bool,
        after: int,
        limit: int,
    ) -> tuple[list[sqlite3.Row], int]:
        """A page past `after` in commit order, and the true total, which ignores paging."""
        terms = ["b.board = ?"]
        values: list[Any] = [board]
        if not history:
            terms.append("b.latest = 1")
        if prefix is not None:
            terms.append("substr(b.name, 1, length(?)) = ?")
            values += [prefix, prefix]
        if author is not None:
            terms.append("b.actor = ?")
            values.append(author)
        for key, value in where.items():
            terms.append("b.fields ->> ? IS ?")
            values += [f'$."{key}"', value]
        if text is not None:
            terms.append("b.seq IN (SELECT rowid FROM v_board_text WHERE v_board_text MATCH ?)")
            values.append(" ".join(f'"{word.replace(chr(34), chr(34) * 2)}"' for word in text.split()))
        clause = " AND ".join(terms)
        total = self.db.execute(f"SELECT count(*) AS n FROM v_board AS b WHERE {clause}", values).fetchone()["n"]
        rows = self.db.execute(
            f"SELECT * FROM v_board AS b WHERE {clause} AND b.seq > ? ORDER BY b.seq LIMIT ?", (*values, after, limit)
        ).fetchall()
        return rows, total


def _ref(row: sqlite3.Row) -> str:
    return f"board/{row['board']}/{row['name']}@{row['version']}"


ObjectName = Annotated[str, Field(pattern=r"^[\w.-]+(/[\w.-]+)*$", max_length=256)]


class Post(Args):
    board: Name
    name: ObjectName
    gist: Gist
    body: BodyRef | None = None
    fields: dict[Name, JsonValue] = {}
    based_on: tuple[str, ...] = ()


class Revise(Post):
    expected_version: int


def _write(txn: Txn, event_type: str, a: Post) -> dict[str, Any]:
    if txn.view(Channels).get(f"board/{a.board}") is None:
        raise Refused("not_found", f"no board {a.board}")
    if size_of(a.fields) > _FIELDS_LIMIT:
        raise Refused("invalid", f"fields exceed {_FIELDS_LIMIT} bytes; store a body and cite its hash")
    event = txn.emit(
        event_type,
        f"board/{a.board}/{a.name}",
        gist=a.gist,
        based_on=a.based_on,
        refs=[a.body] if a.body else (),
        data={"board": a.board, "name": a.name, "body": a.body, "fields": a.fields},
    )
    return {"ref": f"{event.stream}@{event.version}", "version": event.version}


@op("board.post", on=lambda a: f"board/{a.board}/{a.name}", tool=True)
def post(txn: Txn, a: Post) -> dict[str, Any]:
    """Create an object on a board, at version 1. Refused `conflict`, with the current version, when the name exists:
    read it, then `board.revise`."""
    found = txn.view(Board).get(a.board, a.name)
    if found is not None:
        raise Refused("conflict", {"current": found["version"], "ref": _ref(found)})
    return _write(txn, "board.posted", a)


@op("board.revise", on=lambda a: f"board/{a.board}/{a.name}", tool=True)
def revise(txn: Txn, a: Revise) -> dict[str, Any]:
    """Add a version to an object. `expected_version` is the version you read. Refused `conflict`, with the current
    version, when someone got there first and nothing was overwritten: read it, then revise again. `not_found` when no
    such object exists."""
    found = txn.view(Board).get(a.board, a.name)
    if found is None:
        raise Refused("not_found", f"no object {a.name} on {a.board}")
    if found["version"] != a.expected_version:
        raise Refused("conflict", {"expected": a.expected_version, "current": found["version"], "ref": _ref(found)})
    return _write(txn, "board.revised", a)


class Get(Args):
    board: Name
    name: ObjectName
    version: Annotated[int, Field(ge=1)] | None = None
    range: Annotated[str, Field(pattern=_RANGE.pattern)] | None = None


def _slice(text: str, wanted: str | None) -> tuple[str, int, int, int] | None:
    """The lines of `wanted` that fit a result: text, first, last and total. A line too long to fit gives nothing."""
    lines = text.splitlines(keepends=True)
    match = _RANGE.fullmatch(wanted) if wanted else None
    first = int(match[1]) if match else 1
    last = min(int(match[2]) if match else len(lines), len(lines))
    size = 0
    kept = first - 1
    for line in lines[first - 1 : last]:
        size += size_of(line)
        if size > RESULT_LIMIT:
            break
        kept += 1
    return None if kept < first else ("".join(lines[first - 1 : kept]), first, kept, len(lines))


@op("board.get", on=lambda a: f"board/{a.board}/{a.name}", exposes=True, tool=True)
def get(txn: Txn, a: Get) -> dict[str, Any]:
    """Read one object, its latest version or `version`, and of a text body the lines of `range`, written `L10-40`.
    `ref` names exactly what you got, so cite it. A body too large to return comes back as its hash. Refused `not_found`
    when the object or version does not exist."""
    row = txn.view(Board).get(a.board, a.name, a.version)
    if row is None:
        raise Refused("not_found", f"no such version of {a.name} on {a.board}")
    ref = _ref(row)
    shown = {
        "ref": ref,
        "version": row["version"],
        "gist": row["gist"],
        "fields": json.loads(row["fields"]),
        "body": row["body"],
    }
    exposed = [Exposed.of(ref, "gist", row["gist"])]
    data = None if row["body"] is None else inline_body(txn, row["body"])
    text = None if data is None else decoded(data)
    cut = None if text is None else _slice(text, a.range)
    if cut is not None:
        content, first, last, total = cut
        whole = first == 1 and last == total and a.range is None
        ref = ref if whole else f"{ref}#L{first}-{last}"
        shown |= {"ref": ref, "text": content, "lines": total}
        exposed.append(Exposed.of(ref, "body", content))
    expose_read(txn, exposed)
    return shown


class Query(Args):
    board: Name
    prefix: str | None = None
    author: str | None = None
    where: dict[Name, Scalar] = {}
    text: Annotated[str, Field(pattern=r"^[^\x00]*\S[^\x00]*$", max_length=512)] | None = None
    history: bool = False
    after: Annotated[int, Field(ge=0)] = 0
    limit: Annotated[int, Field(ge=1, le=32)] = 20


@op("board.query", on=lambda a: f"board/{a.board}/*", exposes=True, tool=True)
def query(txn: Txn, a: Query) -> dict[str, Any]:
    """Find objects by `prefix` of name, `author`, exact `where` on fields, or `text` over names, gists and fields,
    never bodies. Results are gists with exact refs, the true `total`, and a `cursor` to pass as `after`. `history`
    includes old versions. Refused `unsupported` for `text` when this SQLite has no FTS5: use structured filters."""
    if a.text is not None and not FTS5:
        raise Refused("unsupported", "this SQLite has no FTS5, so use structured filters")
    rows, total = txn.view(Board).find(
        a.board,
        prefix=a.prefix,
        author=a.author,
        where=a.where,
        text=a.text,
        history=a.history,
        after=a.after,
        limit=a.limit,
    )

    def shown(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "ref": _ref(row),
            "name": row["name"],
            "version": row["version"],
            "actor": row["actor"],
            "gist": row["gist"],
            "fields": json.loads(row["fields"]),
        }

    kept = fitted(rows, show=shown)
    expose_read(txn, [Exposed.of(_ref(row), "gist", row["gist"]) for row in kept])
    more = len(kept) < len(rows) or len(rows) == a.limit
    return {
        "results": [shown(row) for row in kept],
        "total": total,
        "cursor": kept[-1]["seq"] if kept and more else None,
    }
