"""Who may do what: principals, grants and the one authorize function."""

import json
import re
import sqlite3
from fnmatch import fnmatchcase
from functools import lru_cache

from pydantic import Field

from .model import ENROLLED_ID, GIST_LIMIT, Event, Principal, Refused
from .op import Args, Op, op
from .txn import Txn
from .view import View, fold

_RELATIONS = {
    "self": "id = :me",
    "parent": "id = :parent",
    "children": "parent = :me",
    "siblings": "parent = :parent AND id != :me",
    "ancestors": "substr(:path, 1, length(path)) = path AND id != :me",
    "descendants": "substr(path, 1, length(:path)) = :path AND id != :me",
    "all": "TRUE",
    "human": "kind = 'human'",
    "program": "kind = 'program'",
}


def _condition(relation: str) -> str | None:
    return "role = :role" if relation.startswith("role:") else _RELATIONS.get(relation)


def _values(me: Principal, relation: str) -> dict[str, str | None]:
    return {"role": relation.removeprefix("role:"), "me": me.id, "parent": me.parent, "path": me.path}


class Principals(View):
    """The live graph: `authorize` reads it inside the transaction, and `path` makes `descendants` a prefix test."""

    schema = """
    CREATE TABLE v_principals(
        id TEXT PRIMARY KEY,
        kind TEXT NOT NULL,
        role TEXT,
        parent TEXT,
        path TEXT NOT NULL,
        state TEXT NOT NULL,
        token_hash TEXT,
        scopes TEXT NOT NULL
    ) WITHOUT ROWID, STRICT;
    CREATE INDEX v_principals_parent ON v_principals(parent);
    CREATE UNIQUE INDEX v_principals_token ON v_principals(token_hash);
    """

    @fold("principal.added")
    def added(self, event: Event) -> None:
        data = event.data
        principal = Principal(id=data["id"], role=data["role"], parent=data["parent"], scopes=data["scopes"])
        parent = self.get(principal.parent) if principal.parent else None
        self.db.execute(
            "INSERT INTO v_principals VALUES (?, ?, ?, ?, ?, 'live', ?, ?)",
            (
                principal.id,
                principal.kind,
                principal.role,
                principal.parent,
                f"{parent.path if parent else '/'}{principal.id}/",
                data["token_hash"],
                json.dumps(principal.scopes),
            ),
        )

    @fold("principal.revoked")
    def revoked(self, event: Event) -> None:
        self._revoke(event.data["id"])

    @fold("agent.ended")
    def agent_ended(self, event: Event) -> None:
        self._revoke(f"agent:{event.agent}")

    def _revoke(self, id: str) -> None:
        self.db.execute("UPDATE v_principals SET state = 'revoked', token_hash = NULL WHERE id = ?", (id,))

    def _load(self, row: sqlite3.Row | None) -> Principal | None:
        if row is None:
            return None
        return Principal(
            id=row["id"],
            role=row["role"],
            parent=row["parent"],
            path=row["path"],
            state=row["state"],
            scopes=tuple(json.loads(row["scopes"])),
        )

    def get(self, id: str) -> Principal | None:
        return self._load(self.db.execute("SELECT * FROM v_principals WHERE id = ?", (id,)).fetchone())

    def live(self, id: str) -> Principal:
        """The principal with this id, or refuse if it is unknown or revoked."""
        principal = self.get(id)
        if principal is None or principal.state != "live":
            raise Refused("not_permitted", "unknown or revoked principal")
        return principal

    def by_token(self, token_hash: str) -> Principal | None:
        row = self.db.execute("SELECT * FROM v_principals WHERE token_hash = ?", (token_hash,)).fetchone()
        return self._load(row)

    def related(self, me: Principal, relation: str, name: str) -> bool:
        """Whether a live principal called `name` stands in `relation` to `me`."""
        condition = _condition(relation)
        if condition is None:
            return False
        row = self.db.execute(
            "SELECT 1 FROM v_principals WHERE state = 'live' AND substr(id, instr(id, ':') + 1) = :name "
            f"AND {condition}",
            _values(me, relation) | {"name": name},
        ).fetchone()
        return row is not None

    def select(self, me: Principal, relation: str) -> list[Principal]:
        """The live principals standing in `relation` to `me`, or refuse a relation with no evaluator."""
        condition = _condition(relation)
        if condition is None:
            raise Refused("unsupported", f"no relation {relation}")
        rows = self.db.execute(
            f"SELECT * FROM v_principals WHERE state = 'live' AND {condition} ORDER BY id", _values(me, relation)
        )
        return [principal for row in rows if (principal := self._load(row)) is not None]


class Grant(Args):
    """Who may run which ops on what. Absence means deny."""

    who: str
    ops: str
    on: str = "*"


class Grants(View):
    """The compiled topology: `(who, ops, on)`, the only authorization input."""

    schema = """
    CREATE TABLE v_grants(
        who TEXT NOT NULL,
        ops TEXT NOT NULL,
        "on" TEXT NOT NULL,
        rev INTEGER NOT NULL,
        PRIMARY KEY (who, ops, "on")
    ) WITHOUT ROWID, STRICT;
    """

    @fold("grant.added")
    def added(self, event: Event) -> None:
        data = event.data
        self.db.execute(
            "INSERT OR REPLACE INTO v_grants VALUES (?, ?, ?, ?)",
            (data["who"], data["ops"], data["on"], event.topology_rev),
        )

    @fold("grant.removed")
    def removed(self, event: Event) -> None:
        data = event.data
        self.db.execute(
            'DELETE FROM v_grants WHERE who = ? AND ops = ? AND "on" = ?',
            (data["who"], data["ops"], data["on"]),
        )

    def held_by(self, me: Principal) -> list[Grant]:
        """Every grant naming `me` by id, by kind, by role or as `all`."""
        rows = self.db.execute(
            'SELECT who, ops, "on" FROM v_grants WHERE who IN (?, ?, ?, ?)',
            (me.id, me.kind, f"role:{me.role}", "all"),
        )
        return [Grant(who=row["who"], ops=row["ops"], on=row["on"]) for row in rows]

    def authorize(self, principal: Principal, operation: Op, target: str | None = None) -> Principal:
        """Return the live principal if it may run `operation` on `target`, or refuse.

        With no target this asks about any object. The runtime is trusted and takes no grant; runtime-only ops are
        excluded by principal kind, so no glob reaches them. Scopes only attenuate.
        """
        if principal.kind == "runtime":
            return principal
        if operation.runtime:
            raise Refused("not_permitted", "a runtime-only op")
        me = Principals(self.db).live(principal.id)
        if not any(fnmatchcase(operation.name, scope) for scope in me.scopes):
            raise Refused("not_permitted", "outside this credential's scopes")
        if self._covered(me, operation.name, target):
            return me
        raise Refused("not_permitted", "no grant covers this")

    def _covered(self, me: Principal, name: str, target: str | None) -> bool:
        principals = Principals(self.db)
        for grant in self.held_by(me):
            if fnmatchcase(name, grant.ops) and (target is None or _covers(grant.on, target, me, principals)):
                return True
        return False

    def permits(self, principal: Principal, name: str, target: str) -> bool:
        """Whether the op called `name` is open to this principal on `target`: a question, where `authorize` refuses."""
        if principal.kind == "runtime":
            return True
        me = Principals(self.db).get(principal.id)
        if me is None or me.state != "live" or not any(fnmatchcase(name, scope) for scope in me.scopes):
            return False
        return self._covered(me, name, target)


@lru_cache(maxsize=1024)
def _compile(pattern: str) -> tuple[re.Pattern[str], tuple[str, ...]]:
    """Turn an `on` pattern into a regex with one group per `{relation}`."""
    parts = re.split(r"\{([^{}]+)\}", pattern)
    regex = "".join(
        "([^/]+)" if index % 2 else re.escape(part).replace(r"\*", ".*") for index, part in enumerate(parts)
    )
    return re.compile(regex), tuple(parts[1::2])


def _covers(pattern: str, target: str, me: Principal, principals: Principals) -> bool:
    regex, relations = _compile(pattern)
    match = regex.fullmatch(target)
    if match is None:
        return False
    return all(principals.related(me, *pair) for pair in zip(relations, match.groups(), strict=True))


class AddPrincipal(Args):
    id: str = Field(pattern=f"^{ENROLLED_ID}$")
    role: str | None = None
    parent: str | None = None
    scopes: tuple[str, ...] = ("*",)
    token_hash: str | None = None


class RevokePrincipal(Args):
    id: str


@op("principal.add", on=lambda a: f"principal/{a.id}", runtime=True)
def add_principal(txn: Txn, a: AddPrincipal) -> None:
    """Add a principal to the live graph."""
    principals = txn.view(Principals)
    if principals.get(a.id) is not None:
        raise Refused("conflict", f"{a.id} exists")
    if a.parent is not None and principals.get(a.parent) is None:
        raise Refused("not_found", f"no parent {a.parent}")
    if a.token_hash is not None and principals.by_token(a.token_hash) is not None:
        raise Refused("conflict", "this token is in use")
    txn.emit("principal.added", f"principal/{a.id}", gist=f"{a.id} added", data=a)


@op("principal.revoke", on=lambda a: f"principal/{a.id}", runtime=True)
def revoke_principal(txn: Txn, a: RevokePrincipal) -> None:
    """Take a principal out of the live graph. Its history stays."""
    if txn.view(Principals).get(a.id) is None:
        raise Refused("not_found", f"no principal {a.id}")
    txn.emit("principal.revoked", f"principal/{a.id}", gist=f"{a.id} revoked", data=a)


@op("grant.add", on=lambda a: "topology", runtime=True)
def add_grant(txn: Txn, a: Grant) -> None:
    """Add a grant. Each change is a topology revision."""
    for relation in _compile(a.on)[1]:
        if relation not in _RELATIONS and not relation.startswith("role:"):
            raise Refused("unsupported", f"no relation {relation}")
    txn.emit("grant.added", "topology", gist=f"{a.who} may {a.ops} on {a.on}"[:GIST_LIMIT], data=a)


@op("grant.remove", on=lambda a: "topology", runtime=True)
def remove_grant(txn: Txn, a: Grant) -> None:
    """Remove a grant. Each change is a topology revision."""
    txn.emit("grant.removed", "topology", gist=f"{a.who} may no longer {a.ops} on {a.on}"[:GIST_LIMIT], data=a)
