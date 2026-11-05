"""What each agent was handed: the view of what the runtime offered it and what its harness said it took, and the one
rule of what an agent may read by a ref, which a read of a body and a commit's citation both keep."""

import json
import sqlite3

from platoon_harness.kernel import Event, Txn, View, fold

from .common import DIGEST_ITEMS, maker, parts_of

_PAGE = DIGEST_ITEMS
_OFFER = "o.*, c.ref AS confirmed, c.seq AS confirmed_seq, c.turn, c.boundary, c.evidence, c.native_id"


def _ref(event: Event) -> str:
    return f"{event.stream}@{event.version}"


class Exposures(View):
    """What the runtime offered each agent, item by item, what its harness said it took, its compactions and its starts.
    A fold sees one event, so an offered event's maker is found by its ref when an answer needs it."""

    schema = """
    CREATE TABLE v_exposures(
        offer INTEGER NOT NULL,
        item INTEGER NOT NULL,
        agent TEXT NOT NULL,
        stream TEXT,
        version INTEGER,
        ref TEXT NOT NULL,
        form TEXT NOT NULL,
        PRIMARY KEY (offer, item)
    ) WITHOUT ROWID, STRICT;
    CREATE INDEX v_exposures_event ON v_exposures(stream, version, agent, offer);
    CREATE TABLE v_exposures_offers(
        offer INTEGER PRIMARY KEY,
        ref TEXT NOT NULL,
        agent TEXT NOT NULL,
        how TEXT NOT NULL,
        key TEXT,
        anchor TEXT,
        v INTEGER NOT NULL
    ) STRICT;
    CREATE INDEX v_exposures_offers_agent ON v_exposures_offers(agent, offer);
    CREATE TABLE v_exposures_confirmed(
        offer INTEGER PRIMARY KEY,
        ref TEXT NOT NULL,
        agent TEXT NOT NULL,
        seq INTEGER NOT NULL,
        turn TEXT,
        boundary TEXT,
        evidence TEXT,
        native_id TEXT
    ) STRICT;
    CREATE INDEX v_exposures_confirmed_agent ON v_exposures_confirmed(agent, seq);
    CREATE TABLE v_exposures_compactions(
        seq INTEGER PRIMARY KEY,
        ref TEXT NOT NULL,
        agent TEXT NOT NULL,
        forgotten TEXT
    ) STRICT;
    CREATE INDEX v_exposures_compactions_agent ON v_exposures_compactions(agent, seq);
    CREATE TABLE v_exposures_starts(
        seq INTEGER PRIMARY KEY,
        agent TEXT NOT NULL,
        coverage TEXT NOT NULL,
        levels TEXT NOT NULL,
        assurance TEXT
    ) STRICT;
    CREATE INDEX v_exposures_starts_agent ON v_exposures_starts(agent, seq);
    """

    @fold("context.offered")
    def offered(self, event: Event) -> None:
        """An offer before payload 3 named a body by its hash, which names no event, so that item has no stream."""
        key, anchor = next(iter(event.native.items()), (None, None))
        self.db.execute(
            "INSERT INTO v_exposures_offers VALUES (?, ?, ?, ?, ?, ?, ?)",
            (event.seq, _ref(event), event.agent, event.data["how"], key, anchor, event.v),
        )
        for index, item in enumerate(event.data["items"]):
            stream, version, _ = parts_of(item["ref"]) or (None, None, None)
            self.db.execute(
                "INSERT INTO v_exposures VALUES (?, ?, ?, ?, ?, ?, ?)",
                (event.seq, index, event.agent, stream, version, item["ref"], item["form"]),
            )

    @fold("context.delivered")
    def delivered(self, event: Event) -> None:
        """The first confirmation of an offer is the one: a repeat is never written now, and a v1 one changed nothing.
        One before payload 3 may name less, and what it does not name stays unknown."""
        data = event.data
        self.db.execute(
            "INSERT OR IGNORE INTO v_exposures_confirmed VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                data["input"],
                _ref(event),
                event.agent,
                event.seq,
                event.turn,
                data.get("boundary"),
                data.get("evidence"),
                data.get("native_id"),
            ),
        )

    @fold("context.compacted")
    def compacted(self, event: Event) -> None:
        self.db.execute(
            "INSERT INTO v_exposures_compactions VALUES (?, ?, ?, ?)",
            (event.seq, _ref(event), event.agent, event.data["forgotten"]),
        )

    @fold("agent.started", "agent.resumed")
    def started(self, event: Event) -> None:
        """A start before assurance was recorded names none."""
        data = event.data
        self.db.execute(
            "INSERT INTO v_exposures_starts VALUES (?, ?, ?, ?, ?)",
            (
                event.seq,
                event.agent,
                json.dumps(data["declared"].get("coverage", {}), sort_keys=True),
                json.dumps(data.get("levels", {}), sort_keys=True),
                data.get("assurance"),
            ),
        )

    def handed(self, agent: str, stream: str, version: int) -> bool:
        """Whether an event was ever offered to an agent, whatever an offer showed of it."""
        row = self.db.execute(
            "SELECT 1 FROM v_exposures WHERE stream = ? AND version = ? AND agent = ? LIMIT 1", (stream, version, agent)
        ).fetchone()
        return row is not None

    def offers_of(
        self, agent: str, stream: str, version: int, bound: int, *, confirmed: bool
    ) -> tuple[list[sqlite3.Row], int]:
        """The offers of one event to an agent made below `bound` that its harness said it took below it, each with that
        report, or those it did not, oldest first and as many as a page holds, and how many there are in all."""
        found = """
            FROM v_exposures_offers AS o
            LEFT JOIN v_exposures_confirmed AS c ON c.offer = o.offer AND c.seq < ?4
            WHERE o.offer IN (
                SELECT offer FROM v_exposures WHERE stream = ?1 AND version = ?2 AND agent = ?3 AND offer < ?4
            ) AND (c.offer IS NOT NULL) = ?5
        """
        args = (stream, version, agent, bound, confirmed)
        rows = self.db.execute(f"SELECT {_OFFER} {found} ORDER BY o.offer LIMIT {_PAGE}", args).fetchall()
        return rows, self.db.execute(f"SELECT count(*) AS n {found}", args).fetchone()["n"]

    def shown(self, offer: int, stream: str | None = None, version: int | None = None) -> list[sqlite3.Row]:
        """What an offer showed, of one event or of all it named."""
        return self.db.execute(
            "SELECT ref, form FROM v_exposures WHERE offer = ?1 AND (?2 IS NULL OR stream = ?2 AND version = ?3) "
            "ORDER BY item",
            (offer, stream, version),
        ).fetchall()

    def history(self, agent: str, bound: int, before: int) -> list[sqlite3.Row]:
        """An agent's offers below `bound` and `before`, newest first, as many as a page holds and one more, each with
        its confirmation when that was reported below `bound`."""
        return self.db.execute(
            f"""
            SELECT {_OFFER}
            FROM v_exposures_offers AS o
            LEFT JOIN v_exposures_confirmed AS c ON c.offer = o.offer AND c.seq < ?2
            WHERE o.agent = ?1 AND o.offer < ?2 AND o.offer < ?3
            ORDER BY o.offer DESC LIMIT ?4
            """,
            (agent, bound, before, _PAGE + 1),
        ).fetchall()

    def counts(self, agent: str, bound: int) -> tuple[int, int]:
        """How many offers were made to an agent below `bound`, and how many its harness said it took there."""

        def count(table: str, column: str) -> int:
            row = self.db.execute(f"SELECT count(*) AS n FROM {table} WHERE agent = ? AND {column} < ?", (agent, bound))
            return row.fetchone()["n"]

        return count("v_exposures_offers", "offer"), count("v_exposures_confirmed", "seq")

    def older(self, agent: str, bound: int) -> int:
        """How many offers below `bound` came before offer payload 3."""
        row = self.db.execute(
            "SELECT count(*) AS n FROM v_exposures_offers WHERE agent = ? AND v < 3 AND offer < ?", (agent, bound)
        ).fetchone()
        return row["n"]

    def compactions(self, agent: str, after: int, before: int) -> tuple[list[sqlite3.Row], int]:
        """An agent's compactions between two seqs, oldest first and as many as a page holds, and how many in all."""
        found = "FROM v_exposures_compactions WHERE agent = ? AND seq > ? AND seq < ?"
        rows = self.db.execute(f"SELECT * {found} ORDER BY seq LIMIT {_PAGE}", (agent, after, before)).fetchall()
        return rows, self.db.execute(f"SELECT count(*) AS n {found}", (agent, after, before)).fetchone()["n"]

    def start(self, agent: str, bound: int) -> sqlite3.Row | None:
        """An agent's latest start or resume below `bound`."""
        return self.db.execute(
            "SELECT * FROM v_exposures_starts WHERE agent = ? AND seq < ? ORDER BY seq DESC LIMIT 1", (agent, bound)
        ).fetchone()

    def readers(self, stream: str, version: int) -> list[sqlite3.Row]:
        """Each agent an event was offered to, by its first offer, and whether its harness said it took any."""
        return self.db.execute(
            """
            SELECT i.agent, min(i.offer) AS offer, max(c.offer IS NOT NULL) AS confirmed
            FROM v_exposures AS i LEFT JOIN v_exposures_confirmed AS c ON c.offer = i.offer
            WHERE i.stream = ? AND i.version = ? GROUP BY i.agent ORDER BY offer
            """,
            (stream, version),
        ).fetchall()

    def events_offered(self, agent: str, bound: int) -> list[sqlite3.Row]:
        """Each event offered to an agent below `bound`, by its first offer, oldest first."""
        return self.db.execute(
            """
            SELECT i.stream, i.version, min(i.offer) AS offer
            FROM v_exposures_offers AS o JOIN v_exposures AS i ON i.offer = o.offer
            WHERE o.agent = ? AND o.offer < ? AND i.stream IS NOT NULL GROUP BY i.stream, i.version ORDER BY offer
            """,
            (agent, bound),
        ).fetchall()

    def ref_of(self, offer: int) -> str:
        return self.db.execute("SELECT ref FROM v_exposures_offers WHERE offer = ?", (offer,)).fetchone()["ref"]


def readable(txn: Txn, agent: str, event: Event) -> bool:
    """Whether an agent may read an event by its ref: one it made or was handed, whatever an offer showed of it."""
    return maker(event) == f"agent:{agent}" or txn.view(Exposures).handed(agent, event.stream, event.version)
