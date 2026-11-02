"""Boards: named objects with immutable versions, found by structured query."""

import json
import sqlite3
from typing import Annotated, Any

from pydantic import Field, JsonValue

from platoon_harness.kernel import Args, Event, Refused, Txn, View, fold, op

from .channels import Channel, Channels
from .common import (
    LINE_RANGE,
    RESULT_LIMIT,
    AgentName,
    BasedOn,
    Body,
    Exposed,
    Gist,
    Name,
    Seq,
    address,
    decoded,
    expose_read,
    fitted,
    inline_body,
    lines_of,
    size_of,
)
from .messages import announce

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


class Boards(View):
    """One row per version. Text search covers names, gists and fields, never a body: a fold cannot read one, and a
    tombstoned body must leave nothing behind."""

    schema = """
    CREATE TABLE v_boards(
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
    CREATE UNIQUE INDEX v_boards_version ON v_boards(board, name, version);
    CREATE INDEX v_boards_latest ON v_boards(board, latest, seq);
    """ + ("CREATE VIRTUAL TABLE v_boards_text USING fts5(name, gist, fields);" if FTS5 else "")

    @fold("board.posted", "board.revised")
    def versioned(self, event: Event) -> None:
        data = event.data
        fields = json.dumps(data["fields"], sort_keys=True)
        self.db.execute("UPDATE v_boards SET latest = 0 WHERE board = ? AND name = ?", (data["board"], data["name"]))
        self.db.execute(
            "INSERT INTO v_boards VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)",
            (event.seq, data["board"], data["name"], event.version, event.actor, event.gist, data["body"], fields),
        )
        if FTS5:
            self.db.execute(
                "INSERT INTO v_boards_text(rowid, name, gist, fields) VALUES (?, ?, ?, ?)",
                (event.seq, data["name"], event.gist, fields),
            )

    def get(self, board: str, name: str, version: int | None = None) -> sqlite3.Row | None:
        """One version, the latest if none is named."""
        pick = "latest = 1" if version is None else "version = :version"
        return self.db.execute(
            f"SELECT * FROM v_boards WHERE board = :board AND name = :name AND {pick}",
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
            terms.append("substr(b.actor, instr(b.actor, ':') + 1) = ?")
            values.append(author)
        for key, value in where.items():
            terms.append("b.fields ->> ? IS ?")
            values += [f'$."{key}"', value]
        if text is not None:
            terms.append("b.seq IN (SELECT rowid FROM v_boards_text WHERE v_boards_text MATCH ?)")
            values.append(" ".join(f'"{word.replace(chr(34), chr(34) * 2)}"' for word in text.split()))
        clause = " AND ".join(terms)
        total = self.db.execute(f"SELECT count(*) AS n FROM v_boards AS b WHERE {clause}", values).fetchone()["n"]
        rows = self.db.execute(
            f"SELECT * FROM v_boards AS b WHERE {clause} AND b.seq > ? ORDER BY b.seq LIMIT ?", (*values, after, limit)
        ).fetchall()
        return rows, total


def _ref(row: sqlite3.Row) -> str:
    return f"board/{row['board']}/{row['name']}@{row['version']}"


def _board(txn: Txn, name: str) -> Channel:
    return txn.view(Channels).require(f"board/{name}")


ObjectName = Annotated[str, Field(pattern=r"^[\w.-]+(/[\w.-]+)*$", max_length=256, description="The object's name.")]
BoardName = Annotated[Name, Field(description="The board. `channel.list` names them.")]


class Post(Args):
    board: BoardName
    name: ObjectName
    gist: Gist
    body: Body = None
    fields: Annotated[
        dict[Name, JsonValue], Field(description="Short JSON values. `board.query` can match them with `where`.")
    ] = {}
    based_on: BasedOn = ()


class Revise(Post):
    expected_version: Annotated[int, Field(description="The version you read.")]


def _write(txn: Txn, event_type: str, a: Post) -> dict[str, Any]:
    channel = _board(txn, a.board)
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
    announce(txn, channel, f"{a.name}: {a.gist}", event.seq)
    return {"ref": f"{event.stream}@{event.version}", "version": event.version}


@op("board.post", on=lambda a: f"board/{a.board}/{a.name}", tool=True)
def post(txn: Txn, a: Post) -> dict[str, Any]:
    """Create an object on a board, at version 1. Put anything longer than `gist` in `body`. Refused `conflict`, with
    the current version, when the name exists. Read it, then `board.revise`. `not_found` when no such board exists."""
    found = txn.view(Boards).get(a.board, a.name)
    if found is not None:
        raise Refused("conflict", {"current": found["version"], "ref": _ref(found)})
    return _write(txn, "board.posted", a)


@op("board.revise", on=lambda a: f"board/{a.board}/{a.name}", tool=True)
def revise(txn: Txn, a: Revise) -> dict[str, Any]:
    """Add a version to an object. `expected_version` is the version you read. Refused `conflict`, with the current
    version, when someone got there first and nothing was overwritten: read it, then revise again. `not_found` when no
    such object exists."""
    found = txn.view(Boards).get(a.board, a.name)
    if found is None:
        raise Refused("not_found", f"no object {a.name} on {a.board}")
    if found["version"] != a.expected_version:
        raise Refused("conflict", {"expected": a.expected_version, "current": found["version"], "ref": _ref(found)})
    return _write(txn, "board.revised", a)


class Get(Args):
    board: BoardName
    name: ObjectName
    version: Annotated[Seq | None, Field(ge=1, description="A version; the latest if left out.")] = None
    range: Annotated[str | None, Field(pattern=LINE_RANGE, description="Lines of the body, as `L10-40`.")] = None


@op("board.get", on=lambda a: f"board/{a.board}/{a.name}", exposes=True, tool=True)
def get(txn: Txn, a: Get) -> dict[str, Any]:
    """Read one object, its latest version or `version`, and of a text body the lines of `range`, written `L10-40`. A
    long body comes back cut: `lines` says how many exist and `rest` is a ref. Pass it to `blob.get` to read on. Cite
    `ref`. `text` is null for a binary body. Refused `invalid`, with `lines`, for a range past the end. `not_found` when
    the board, object or version does not exist."""
    _board(txn, a.board)
    row = txn.view(Boards).get(a.board, a.name, a.version)
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
    if row["body"] is not None:
        shown["text"] = None  # A surface fetches what an op may not read.
        data = inline_body(txn, row["body"])
        text = None if data is None else decoded(data)
        if text is not None:
            cut = lines_of(row["body"], text, a.range, RESULT_LIMIT - size_of(shown))
            shown |= cut.shown()
            if cut.text is not None:
                ref = shown["ref"] = f"{ref}{cut.span}"
                exposed.append(Exposed.of(ref, "body", cut.text))
    expose_read(txn, exposed, positions={f"board/{a.board}/{a.name}": row["seq"]})
    return shown


class Query(Args):
    board: BoardName
    prefix: Annotated[str | None, Field(description="Only names starting with this.")] = None
    author: Annotated[AgentName | None, Field(description="Only what this author wrote.")] = None
    where: Annotated[dict[Name, Scalar], Field(description="Exact matches on `fields`.")] = {}
    text: Annotated[
        str | None,
        Field(pattern=r"^[^\x00]*\S[^\x00]*$", max_length=512, description="Words to find in names, gists and fields."),
    ] = None
    history: Annotated[bool, Field(description="Include old versions.")] = False
    after: Annotated[Seq, Field(description="A `cursor` from an earlier query.")] = 0
    limit: Annotated[int, Field(ge=1, le=32, description="The most results to return.")] = 20


@op("board.query", on=lambda a: f"board/{a.board}/*", exposes=True, tool=True)
def query(txn: Txn, a: Query) -> dict[str, Any]:
    """Find objects by `prefix` of name, `author`, exact `where` on fields, or `text` over names, gists and fields,
    never bodies. Results are gists with exact refs, the true `total`, and a `cursor` to pass as `after`. `history`
    includes old versions. Refused `unsupported` for `text` when this SQLite has no FTS5: use structured filters.
    `not_found` when no such board exists."""
    _board(txn, a.board)
    if a.text is not None and not FTS5:
        raise Refused("unsupported", "this SQLite has no FTS5, so use structured filters")
    rows, total = txn.view(Boards).find(
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
            "author": address(row["actor"]),
            "gist": row["gist"],
            "fields": json.loads(row["fields"]),
        }

    kept = fitted(rows, show=shown)
    positions = {f"board/{a.board}/{row['name']}": row["seq"] for row in kept}
    expose_read(txn, [Exposed.of(_ref(row), "gist", row["gist"]) for row in kept], positions=positions)
    more = len(kept) < len(rows) or len(rows) == a.limit
    return {
        "results": [shown(row) for row in kept],
        "total": total,
        "cursor": kept[-1]["seq"] if kept and more else None,
    }
