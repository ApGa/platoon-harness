"""Views: tables folded from events, droppable and rebuilt to identical contents."""

import sqlite3
from collections.abc import Callable
from functools import cache
from typing import ClassVar

from .journal import decode
from .model import Event, Refused

_PAGE = 512
_TABLE_ACTIONS = frozenset({sqlite3.SQLITE_READ, sqlite3.SQLITE_INSERT, sqlite3.SQLITE_UPDATE, sqlite3.SQLITE_DELETE})


def fold[F: Callable[..., None]](*types: str) -> Callable[[F], F]:
    """Mark a view method as the fold for these event types."""

    def mark(method: F) -> F:
        method.__dict__["_fold_types"] = types
        return method

    return mark


class View:
    """A class with a schema, `@fold` methods and typed query methods.

    Tables are named `v_<name>`, or start with `v_<name>_`. Bumping `version` drops and refolds the view.
    """

    name: ClassVar[str]
    version: ClassVar[int] = 1
    schema: ClassVar[str] = ""
    _folds: ClassVar[dict[str, list[str]]]

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        cls.name = cls.__dict__.get("name", cls.__name__.lower())
        cls._folds = {}
        for attribute, method in vars(cls).items():
            for event_type in getattr(method, "_fold_types", ()):
                cls._folds.setdefault(event_type, []).append(attribute)

    def __init__(self, db: sqlite3.Connection) -> None:
        self.db = db

    def bound_folds(self) -> dict[str, list[Callable[[Event], None]]]:
        """This instance's folds, by event type."""
        return {kind: [getattr(self, name) for name in names] for kind, names in self._folds.items()}


@cache
def tables_of(view: type[View]) -> tuple[str, ...]:
    """The tables a view's schema creates. Any other name is refused."""
    scratch = sqlite3.connect(":memory:")
    scratch.executescript(view.schema)
    rows = scratch.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    scratch.close()
    tables = tuple(row[0] for row in rows)
    prefix = f"v_{view.name}"
    for table in tables:
        if table != prefix and not table.startswith(f"{prefix}_"):
            raise Refused("invalid", f"view {view.name} may not create table {table}")
    return tables


def _only(tables: tuple[str, ...]) -> Callable[..., int]:
    """An authorizer that keeps SQL inside `tables`."""

    def guard(action: int, table: str | None, *_: object) -> int:
        outside = action in _TABLE_ACTIONS and table not in tables
        return sqlite3.SQLITE_DENY if outside else sqlite3.SQLITE_OK

    return guard


def refold(db: sqlite3.Connection, view: type[View]) -> None:
    """Drop one view and refold it from the journal, inside the caller's transaction.

    The authorizer makes law 2 checkable: a fold that reaches outside its own tables fails here, loudly.
    """
    tables = tables_of(view)
    folds = view(db).bound_folds()
    db.execute("SAVEPOINT rebuild")
    try:
        for table in tables:
            db.execute(f"DROP TABLE IF EXISTS {table}")
        db.executescript(view.schema)
        after = 0
        while rows := db.execute("SELECT * FROM events WHERE seq > ? ORDER BY seq LIMIT ?", (after, _PAGE)).fetchall():
            after = rows[-1]["seq"]
            db.set_authorizer(_only(tables))
            try:
                for row in rows:
                    if applying := folds.get(row["type"]):
                        event = decode(row, with_outcome=False)
                        for apply in applying:
                            apply(event)
            finally:
                db.set_authorizer(None)
        db.execute(
            "INSERT OR REPLACE INTO v_folds VALUES (?, ?, (SELECT coalesce(max(seq), 0) FROM events))",
            (view.name, view.version),
        )
    except BaseException:
        db.execute("ROLLBACK TO rebuild")
        raise
    finally:
        db.execute("RELEASE rebuild")
