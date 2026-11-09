"""The session as SwarmChat's page reads it: the journal folded one way into `swarmchat.sqlite` in the session folder.

Nothing reads the projection back into the journal, so the page is no second authority and an echo has no path. The fold
is a function of the events and of the bodies they cite and of nothing else, so a rebuild from nothing gives every id
again. A chat's id is 16 hex of a hash of the session and what the chat is: a channel's stream, or the two people of a
direct chat, whose inboxes it merges in journal order. A line's seq is its place in its chat, in journal order. The feed
numbers what the page must hear, in the same order, and `feed_id` hashes the session, this version of the projection,
whose change drops the file and folds again, and the folder it is in, as a replay's copy started anew is a folder of its
own, either of which the page hears as a reset. A line shows one event, by its ref, which
its Provenance follows. The feed also tells the page that what a queue's or a board's view reads moved, `x_moved`,
naming its chat, so the page reads that view again.
"""

import contextlib
import hashlib
import json
import os
import sqlite3
from collections.abc import Callable, Iterator, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from platoon_harness import Refused, Session
from platoon_harness.kernel import Event, Refusal
from platoon_harness.primitives import IN_A_RESULT
from platoon_harness.runtime.control import BODY_LIMIT

from ..channels import moves
from ..provenance import shows

VERSION = 8
FILE = "swarmchat.sqlite"
SHOWN = 20_000
"""The most a message shows, in characters: SwarmChat's own longest message."""
PREVIEW_LINES = 8
PREVIEW_WIDTH = 200
STATUS = frozenset(
    {
        "agent.started",
        "agent.resumed",
        "agent.woken",
        "agent.parked",
        "agent.held",
        "agent.released",
        "agent.ended",
        "turn.started",
        "turn.ended",
        "turn.lost",
        "approval.requested",
        "approval.resolved",
        "wake.refused",
    }
)
"""What begins, ends, parks, wakes, holds up or asks for an agent's work. An agent's status is the roster's, read when
the page asks, and after one of these the feed tells the page to ask again."""

_SCHEMA = """
CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT NOT NULL) WITHOUT ROWID, STRICT;
CREATE TABLE users(id TEXT PRIMARY KEY, kind TEXT NOT NULL, fields TEXT NOT NULL) WITHOUT ROWID, STRICT;
CREATE TABLE chats(
    id TEXT PRIMARY KEY,
    key TEXT NOT NULL UNIQUE,
    kind TEXT NOT NULL,
    name TEXT,
    about TEXT NOT NULL,
    address TEXT,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    seq INTEGER NOT NULL
) WITHOUT ROWID, STRICT;
CREATE TABLE members(chat TEXT NOT NULL, user TEXT NOT NULL, PRIMARY KEY (chat, user)) WITHOUT ROWID, STRICT;
CREATE TABLE lines(
    chat TEXT NOT NULL,
    seq INTEGER NOT NULL,
    kind TEXT NOT NULL,
    sender TEXT NOT NULL,
    at TEXT NOT NULL,
    time REAL NOT NULL,
    event INTEGER NOT NULL,
    shows TEXT NOT NULL,
    stream TEXT,
    ref TEXT,
    gist TEXT NOT NULL,
    text TEXT NOT NULL,
    body TEXT,
    file TEXT,
    parent INTEGER,
    extra TEXT NOT NULL,
    PRIMARY KEY (chat, seq)
) WITHOUT ROWID, STRICT;
CREATE UNIQUE INDEX lines_ref ON lines(ref);
CREATE INDEX lines_shows ON lines(shows);
CREATE INDEX lines_event ON lines(event);
CREATE INDEX lines_body ON lines(body);
CREATE INDEX lines_time ON lines(kind, time);
CREATE INDEX lines_parent ON lines(chat, parent);
CREATE TABLE deliveries(
    chat TEXT NOT NULL,
    seq INTEGER NOT NULL,
    reader TEXT NOT NULL,
    event INTEGER,
    at TEXT,
    PRIMARY KEY (chat, seq, reader)
) WITHOUT ROWID, STRICT;
CREATE INDEX deliveries_reader ON deliveries(reader, event);
CREATE TABLE approvals(
    id TEXT PRIMARY KEY,
    agent TEXT NOT NULL,
    chat TEXT NOT NULL,
    seq INTEGER NOT NULL,
    state TEXT NOT NULL
) WITHOUT ROWID, STRICT;
CREATE TABLE feed(n INTEGER PRIMARY KEY, kind TEXT NOT NULL, chat TEXT, seq INTEGER, user TEXT, upto INTEGER) STRICT;
"""

Bodies = Mapping[str, bytes | Refusal]
"""What the follower read of each body an event cites: its bytes, or why it could not be read."""


def name_of(principal: str) -> str:
    """A principal as the page names it: `agent:lead` is `lead`, and `runtime` is `runtime`."""
    return principal.partition(":")[2] or principal


def iso(wall_time: float) -> str:
    """A time as SwarmChat writes one."""
    return datetime.fromtimestamp(wall_time, UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def hashed(*parts: str) -> str:
    return hashlib.sha256("\0".join(parts).encode()).hexdigest()[:16]


def preview(text: str) -> dict[str, Any]:
    """The first lines of a text file, as SwarmChat shows one under its message."""
    lines = text.removeprefix("﻿").replace("\r\n", "\n").split("\n")
    if lines[-1] == "" and len(lines) > 1:
        lines.pop()
    shown = lines[:PREVIEW_LINES]
    more = len(lines) > PREVIEW_LINES or any(len(line) > PREVIEW_WIDTH for line in shown)
    return {"preview": "\n".join(line[:PREVIEW_WIDTH] for line in shown), "more": more, "lines": len(lines)}


def unshown(gist: str, refusal: Refusal) -> str:
    detail = refusal.detail if isinstance(refusal.detail, str) else json.dumps(refusal.detail)
    return f"{gist}\n\n[Its body is not shown: {detail}.]"


def blank(event: Event, bodies: Bodies) -> bool:
    """Whether what `event` says is whitespace alone: its gist, and its body, read, if it has one. A body unread is
    not known to be blank."""
    body = bodies.get(event.data["body"]) if event.data.get("body") else b""
    return not event.gist.strip() and isinstance(body, bytes) and not body.strip()


def shown(gist: str, body: bytes | Refusal | None) -> tuple[str, dict[str, Any] | None]:
    """What a message shows, and the file it comes with. The body takes the gist's place when it is text that begins or
    ends with the gist, as a gist cut from it does. Text past what a message shows is cut, saying so, and a body the
    message does not show whole comes as a file, which SwarmChat's viewer opens whole."""
    if body is None:
        return gist, None
    if isinstance(body, Refusal):
        return unshown(gist, body), None
    try:
        text = body.decode()
    except UnicodeDecodeError:
        return gist, {"name": "body", "size": len(body), "type": "application/octet-stream"}
    file = {"name": "body.txt", "size": len(body), "type": "text/plain", "text": preview(text)}
    stem = gist.removesuffix("…")
    if not (text.startswith(stem) or text.endswith(stem)):
        return gist, file
    if len(text) <= SHOWN:
        return text, None
    cut = text[:SHOWN]
    cut = cut[: cut.rfind("\n") + 1] or cut
    return f"{cut}\n[Cut here: a message shows {SHOWN:,} characters, and the whole is attached.]", file


def _created(path: Path, *, schema: bool = True) -> sqlite3.Connection:
    """A projection file of this user's alone, 0600, with its schema, or empty for a copy of another."""
    os.close(os.open(path, os.O_CREAT | os.O_WRONLY | os.O_EXCL, 0o600))
    db = sqlite3.connect(path)
    if schema:
        db.executescript(_SCHEMA)
    return db


async def bodies(session: Session, event: Event) -> dict[str, bytes | Refusal]:
    """What the fold of `event` shows of the bodies it cites: their bytes, or why they could not be read."""
    found: dict[str, bytes | Refusal] = {}
    for ref in Projection.cited(event):
        try:
            found[ref] = await session.get_body(ref, limit=BODY_LIMIT)
        except Refused as refused:
            found[ref] = refused.refusal
    return found


class Projection:
    """`swarmchat.sqlite`, folded from the journal an event at a time, each in a transaction with how far it has got.
    `person` is the human the session started for, whose direct chats every agent has from its start."""

    def __init__(self, folder: Path, session: str, person: str) -> None:
        self.session, self.person, self.folder = session, person, folder
        path = folder / FILE
        mine = {"version": str(VERSION), "session": session, "person": person}
        self.db = sqlite3.connect(path) if path.exists() else _created(path)
        try:
            found = dict(self.db.execute("SELECT key, value FROM meta").fetchall())
        except sqlite3.DatabaseError:
            found = {}
        if any(found.get(key) != value for key, value in mine.items()):
            self.db.close()
            for stale in (path, path.with_name(f"{FILE}-wal"), path.with_name(f"{FILE}-shm")):
                stale.unlink(missing_ok=True)
            self.db = _created(path)
            with self.db:
                self.db.executemany("INSERT INTO meta VALUES (?, ?)", [*mine.items(), ("through", "0")])
                self._user(person, "human")
        self.db.row_factory = sqlite3.Row
        for pragma in ("journal_mode = WAL", "synchronous = NORMAL", "secure_delete = ON"):
            self.db.execute(f"PRAGMA {pragma}")
        self.feed_id = hashed(session, str(VERSION), str(folder.absolute()))
        self._folds: dict[str, Callable[[Event, Bodies], None]] = {
            "principal.added": self._principal_added,
            "agent.spawned": self._spawned,
            "channel.created": self._channel_created,
            "message.sent": self._sent,
            "item.recorded": self._said,
            "approval.requested": self._asked,
            "approval.resolved": self._decided,
            "turn.started": self._began,
            "turn.ended": self._turn_over,
            "turn.lost": self._turn_over,
            "agent.ended": self._ended,
            "context.delivered": self._delivered,
            "context.offered": self._delivered,
            "body.tombstoned": self._erased,
        }

    @property
    def through(self) -> int:
        """The journal's seq this projection has folded through."""
        return int(self.db.execute("SELECT value FROM meta WHERE key = 'through'").fetchone()[0])

    @property
    def count(self) -> int:
        """How many entries the feed holds."""
        return self.db.execute("SELECT coalesce(max(n), 0) FROM feed").fetchone()[0]

    def close(self) -> None:
        self.db.close()

    @staticmethod
    def cited(event: Event) -> list[str]:
        """The bodies the fold of `event` shows, which the follower reads first."""
        shows = event.type in ("message.sent", "agent.spawned") or (
            event.type == "item.recorded" and event.data["kind"] == "message"
        )
        body = event.data.get("body") if shows else None
        return [body] if body else []

    def fold(self, event: Event, bodies: Bodies) -> None:
        """Fold one event, given what was read of the bodies it cites, in a transaction with how far this has got. An
        event folded already is passed over, so folding it again changes nothing."""
        if event.seq <= self.through:
            return
        with self.db:
            if (fold := self._folds.get(event.type)) is not None:
                fold(event, bodies)
            if event.type in STATUS and event.agent is not None:
                self._feed("user", user=event.agent)
            self._moved(event)
            self.db.execute("UPDATE meta SET value = ? WHERE key = 'through'", (str(event.seq),))
        if event.type == "body.tombstoned":  # What held the erased text goes from the file and its log at once.
            self.db.execute("PRAGMA wal_checkpoint(TRUNCATE)")

    # Who.

    def _user(self, id: str, kind: str, **fields: Any) -> None:
        """Know someone, or what more is known of them. The kind comes first in `fields`, as the page shows the first
        field beside a name."""
        found = self.db.execute("SELECT fields FROM users WHERE id = ?", (id,)).fetchone()
        old = json.loads(found[0]) if found else {}
        known = {"kind": kind, **old, **{key: value for key, value in fields.items() if value}}
        known["kind"] = kind
        if known != old:
            self.db.execute("INSERT OR REPLACE INTO users VALUES (?, ?, ?)", (id, kind, json.dumps(known)))
            self._feed("user", user=id)

    def _known(self, id: str) -> str:
        """Someone's kind, knowing them first if they are new: the runtime, or someone nothing has introduced."""
        found = self.db.execute("SELECT kind FROM users WHERE id = ?", (id,)).fetchone()
        if found is not None:
            return found[0]
        kind = "runtime" if id == "runtime" else "unknown"
        self._user(id, kind)
        return kind

    def _principal_added(self, event: Event, bodies: Bodies) -> None:
        kind, _, name = event.data["id"].partition(":")
        self._user(name, kind, role=event.data.get("role"))

    def _spawned(self, event: Event, bodies: Bodies) -> None:
        """An agent's direct chat with the person begins with it. A goal is what its spawner asked of it, which awaits
        the agent's first turn."""
        data, name = event.data, event.data["name"]
        harness = data["harness"]
        said = harness.rpartition(":")[2] if isinstance(harness, str) else harness.get("mode", "program")
        self._user(name, "agent", role=data["role"], harness=said, model=data.get("model"))
        self._direct(self.person, name, event)
        if data["goal"] or data.get("body"):
            spawner = name_of(event.actor)
            chat = self._direct(spawner, name, event)
            seq = self._message(chat, spawner, event, data["goal"], data.get("body"), bodies, stream=event.stream)
            self.db.execute("INSERT INTO deliveries VALUES (?, ?, ?, NULL, NULL)", (chat, seq, name))

    # Chats.

    def _chat(
        self,
        key: str,
        kind: str,
        name: str | None,
        about: str,
        address: str | None,
        event: Event,
        members: list[str],
        creator: str | None = None,
    ) -> str:
        """The chat `key` names, made with its first line if it is new, by `creator` or else the event's actor."""
        id = hashed(self.session, key)
        creator = creator or name_of(event.actor)
        if self.db.execute("SELECT 1 FROM chats WHERE id = ?", (id,)).fetchone() is None:
            self._known(creator)
            row = (id, key, kind, name, about, address, creator, iso(event.wall_time), 0)
            self.db.execute("INSERT INTO chats VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", row)
            self._join(id, members)
            extra = (
                {"name": name, "members": sorted(members), "public": False} if name else {"members": sorted(members)}
            )
            self._line(id, "created", creator, event, extra=extra)
        return id

    def _join(self, chat: str, members: list[str]) -> None:
        for member in members:
            self._known(member)
            self.db.execute("INSERT OR IGNORE INTO members VALUES (?, ?)", (chat, member))

    def _direct(self, one: str, other: str, event: Event) -> str:
        """The direct chat of two people, whichever wrote first. A person's message goes to the agent in one with them,
        and one between two agents takes none from the person. The person's chat with an agent, which it has from its
        start, is the runtime's: nobody in it made it."""
        pair = sorted({one, other})
        agent = next((name for name in pair if name != self.person), None)
        mine = self.person in pair
        address = f"@{agent}" if mine and agent not in (None, "runtime") else None
        key = f"direct:{' '.join(pair)}"
        return self._chat(key, "direct", None, "", address, event, pair, "runtime" if mine else None)

    def _channel(self, stream: str, event: Event, kind: str | None = None) -> str:
        """A channel's chat, in which the person may always read. A person's message goes to a topic or a group."""
        prefix, _, name = stream.partition("/")
        kind = "group" if name.startswith("+") else kind or ("topic" if prefix == "channel" else prefix)
        address = name if kind == "group" else f"#{name}" if kind == "topic" else None
        members = sorted({self.person, name_of(event.actor)} - {"runtime"})
        return self._chat(stream, "channel", name, kind, address, event, members)

    def _channel_created(self, event: Event, bodies: Bodies) -> None:
        self._channel(event.data["stream"], event, event.data["kind"])

    # Lines.

    def _line(
        self,
        chat: str,
        kind: str,
        sender: str,
        event: Event,
        *,
        gist: str = "",
        text: str = "",
        file: dict[str, Any] | None = None,
        body: str | None = None,
        stream: str | None = None,
        parent: int | None = None,
        extra: dict[str, Any] | None = None,
        ref: str | None = None,
    ) -> int:
        """Add a line to a chat, at the next seq, and tell the feed: a message, or a line of the chat's own. It shows
        the event that made it, or what that event's words carry."""
        self._known(sender)
        seq = self.db.execute("UPDATE chats SET seq = seq + 1 WHERE id = ? RETURNING seq", (chat,)).fetchone()[0]
        if file is not None and body is not None:
            file = {"id": f"a{hashed(self.session, body)}", **file}
        self.db.execute(
            "INSERT INTO lines VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                chat,
                seq,
                kind,
                sender,
                iso(event.wall_time),
                event.wall_time,
                event.seq,
                shows(event),
                stream,
                ref,
                gist,
                text,
                body,
                None if file is None else json.dumps(file),
                parent,
                json.dumps(extra or {}),
            ),
        )
        self._feed("message" if kind == "message" else "chat", chat, seq)
        return seq

    def _message(
        self, chat: str, sender: str, event: Event, gist: str, body: str | None, bodies: Bodies, **options: Any
    ) -> int:
        """A message of `gist` and of the body `body` cites, shown as `shown` says."""
        text, file = shown(gist, bodies.get(body) if body else None)
        return self._line(chat, "message", sender, event, gist=gist, text=text, file=file, body=body, **options)

    def _parent(self, chat: str, *refs: str | None) -> int | None:
        """The line a message answers, by what it replies to or the thread it is in, when that is in its own chat."""
        for ref in filter(None, refs):
            row = self.db.execute("SELECT seq FROM lines WHERE ref = ? AND chat = ?", (ref, chat)).fetchone()
            if row is not None:
                return row[0]
        return None

    def _sent(self, event: Event, bodies: Bodies) -> None:
        """An entry on an inbox goes to the direct chat of its reader and its sender, or of its reader and the agent a
        runtime report is about, and an entry on any other stream to that channel's chat. Each agent it was for awaits
        evidence that it was delivered."""
        data, stream = event.data, event.stream
        sender = data["sender"].removeprefix("@")
        if stream.startswith("inbox/"):
            chat = self._direct(stream.removeprefix("inbox/"), data.get("subject") or sender, event)
        else:
            chat = self._channel(stream, event)
            self._join(chat, [sender, *data["audience"]])
        mention = data.get("mention")
        seq = self._message(
            chat,
            sender,
            event,
            event.gist,
            data["body"],
            bodies,
            stream=stream,
            ref=data.get("carries") or f"{stream}@{event.version}",
            parent=self._parent(chat, data.get("reply_to"), data.get("thread")),
            extra={"mentions": [name_of(mention)]} if mention else None,
        )
        for reader in data["audience"]:
            if self._known(reader) == "agent":
                self.db.execute("INSERT INTO deliveries VALUES (?, ?, ?, NULL, NULL)", (chat, seq, reader))

    def _said(self, event: Event, bodies: Bodies) -> None:
        """What an agent's harness says in a turn it says to whoever runs it, so it is the agent's message to the
        person. Thoughts and tools are no message, and nor is text of whitespace alone, as a model can say before a
        tool call: it says nothing, and the journal keeps it."""
        if event.data["kind"] == "message" and event.agent is not None and not blank(event, bodies):
            chat = self._direct(self.person, event.agent, event)
            self._message(chat, event.agent, event, event.gist, event.data["body"], bodies)

    def _asked(self, event: Event, bodies: Bodies) -> None:
        """An approval left for a person to decide is a card in the agent's chat with them."""
        if event.data["policy"] == "ask" and event.agent is not None:
            id = event.data["id"]
            chat = self._direct(self.person, event.agent, event)
            card = {"id": id, "version": event.version, "state": "pending"}
            seq = self._line(
                chat, "message", event.agent, event, gist=event.gist, text=event.gist, extra={"x_approval": card}
            )
            self.db.execute("INSERT INTO approvals VALUES (?, ?, ?, ?, 'pending')", (id, event.agent, chat, seq))

    def _card(self, id: str, **change: Any) -> None:
        row = self.db.execute("SELECT chat, seq FROM approvals WHERE id = ?", (id,)).fetchone()
        if row is None:
            return
        extra = json.loads(
            self.db.execute("SELECT extra FROM lines WHERE chat = ? AND seq = ?", tuple(row)).fetchone()[0]
        )
        extra["x_approval"] |= change
        self.db.execute("UPDATE lines SET extra = ? WHERE chat = ? AND seq = ?", (json.dumps(extra), *row))
        self.db.execute("UPDATE approvals SET state = ? WHERE id = ?", (change["state"], id))
        self._feed("change", row[0], row[1])

    def _decided(self, event: Event, bodies: Bodies) -> None:
        data = event.data
        self._card(
            data["id"], state="resolved", verdict=data["verdict"], by=name_of(data["resolved_by"]), via=data["via"]
        )

    def _turn_over(self, event: Event, bodies: Bodies) -> None:
        """An approval goes moot with the turn that asked, as the runtime's own view has it."""
        pending = self.db.execute(
            "SELECT id FROM approvals WHERE agent = ? AND state = 'pending' ORDER BY seq", (event.agent,)
        ).fetchall()
        for (id,) in pending:
            self._card(id, state="moot")

    def _ended(self, event: Event, bodies: Bodies) -> None:
        """An agent's end is one line in its chat with the person, saying what the terminal says of it: its report when
        it finished with one, and otherwise how it ended and why."""
        self._turn_over(event, bodies)
        if event.agent is not None:
            chat = self._direct(self.person, event.agent, event)
            end = {"status": event.data["status"], "gist": event.gist}
            self._line(chat, "ended", event.agent, event, extra={"x_end": end})

    def _moved(self, event: Event) -> None:
        """Tell the feed of each queue's or board's chat whose view `event` moves, as the page reads that view through
        `x_read` and never from here."""
        if not event.stream.startswith(("task/", "board/")) and event.type != "agent.ended":
            return
        chats = self.db.execute("SELECT id, key FROM chats WHERE key GLOB 'queue/*' OR key GLOB 'board/*' ORDER BY key")
        for id, key in chats.fetchall():
            if moves(key, event):
                self._feed("x_moved", id)

    # Evidence.

    def _delivered(self, event: Event, bodies: Bodies) -> None:
        """What a handover landed, or a tool's result showed, was delivered to that agent. Nothing a person reads is
        evidence, so it is never here."""
        if event.type != "context.offered" or event.data["how"] in IN_A_RESULT:
            self._reached(event, event.data.get("positions") or {})

    def _began(self, event: Event, bodies: Bodies) -> None:
        """A goal reached its agent when the agent's first turn began, which is the turn a goal begins."""
        self._reached(event, {f"agent/{event.agent}": event.seq})

    def _reached(self, event: Event, positions: Mapping[str, int]) -> None:
        """Each line awaiting `event`'s agent on a stream of `positions`, through the seq given, was delivered by it."""
        reader, at = event.agent, iso(event.wall_time)
        touched: set[str] = set()
        for stream, upto in sorted(positions.items()):
            found = self.db.execute(
                """
                UPDATE deliveries SET event = ?, at = ? WHERE reader = ? AND event IS NULL
                    AND (chat, seq) IN (SELECT chat, seq FROM lines WHERE stream = ? AND event <= ?)
                RETURNING chat
                """,
                (event.seq, at, reader, stream, upto),
            ).fetchall()
            touched |= {row[0] for row in found}
        for chat in sorted(touched):
            upto = self.db.execute(
                "SELECT max(seq) FROM deliveries WHERE chat = ? AND reader = ? AND event IS NOT NULL", (chat, reader)
            ).fetchone()[0]
            self._feed("read", chat, user=reader, upto=upto)

    def _erased(self, event: Event, bodies: Bodies) -> None:
        """A body erased in the journal is erased here too: its text and its file go, and the gist stays."""
        refusal = Refusal(code="not_found", detail="this body was tombstoned")
        rows = self.db.execute(
            "SELECT chat, seq, gist FROM lines WHERE body = ? ORDER BY event", (f"sha256:{event.data['sha256']}",)
        ).fetchall()
        for chat, seq, gist in rows:
            self.db.execute(
                "UPDATE lines SET text = ?, file = NULL WHERE chat = ? AND seq = ?", (unshown(gist, refusal), chat, seq)
            )
            self._feed("change", chat, seq)

    def _feed(
        self,
        kind: str,
        chat: str | None = None,
        seq: int | None = None,
        *,
        user: str | None = None,
        upto: int | None = None,
    ) -> None:
        self.db.execute(
            "INSERT INTO feed(kind, chat, seq, user, upto) VALUES (?, ?, ?, ?, ?)", (kind, chat, seq, user, upto)
        )

    def entries(self, after: int, limit: int) -> Iterator[sqlite3.Row]:
        """The feed past `after`, oldest first."""
        yield from self.db.execute("SELECT * FROM feed WHERE n > ? ORDER BY n LIMIT ?", (after, limit))


class Kept:
    """A replay's projections, each in a folder of its own under `folder`, and a copy of one each `spacing` events it
    folds through, as the replay keeps checkpoints of its views, so a projection started anew where the replay went
    back folds on from the nearest copy at or below there rather than from nothing."""

    def __init__(self, folder: Path, spacing: int) -> None:
        self.folder, self.spacing = folder, spacing
        self._made = 0
        self._kept: dict[int, Path] = {}

    def keep(self, projection: Projection) -> None:
        """Keep a copy of `projection` where it stands, if that is a multiple of `spacing` and none is kept there."""
        at = projection.through
        if at % self.spacing or at in self._kept:
            return
        (self.folder / "kept").mkdir(mode=0o700, parents=True, exist_ok=True)
        path = self.folder / "kept" / f"{at}.sqlite"
        with contextlib.closing(_created(path, schema=False)) as copy:
            projection.db.backup(copy)
        self._kept[at] = path

    def nearest(self, seq: int) -> int:
        """Where the nearest copy kept at or below `seq` stands, or 0 where none is."""
        return max((at for at in self._kept if at <= seq), default=0)

    def anew(self, seq: int, session: str, person: str) -> Projection:
        """A projection in a folder of its own, a copy of the nearest kept at or below `seq`, or folded from nothing."""
        self._made += 1
        folder = self.folder / str(self._made)
        folder.mkdir(mode=0o700, parents=True)
        if at := self.nearest(seq):
            kept, copy = sqlite3.connect(self._kept[at]), _created(folder / FILE, schema=False)
            with contextlib.closing(kept), contextlib.closing(copy):
                kept.backup(copy)
        return Projection(folder, session, person)
