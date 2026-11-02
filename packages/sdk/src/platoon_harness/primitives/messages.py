"""Inboxes and topics: entries, who each is for, and how far each reader has got."""

import json
from collections.abc import Iterator, Sequence
from itertools import islice
from typing import Annotated, Any, NamedTuple

from pydantic import BaseModel, Field

from platoon_harness.kernel import Args, Event, Grants, Principals, Refused, Stamps, Txn, View, fold, op

from .agents import Agents
from .channels import Channel, Channels, Groups
from .common import (
    DIGEST_ITEMS,
    RESULT_LIMIT,
    BodyRef,
    Exposed,
    Gist,
    decoded,
    expose_read,
    fitted,
    inline_body,
    stream_of,
)
from .sessions import Session

_SCAN_LIMIT = 4096
_WAKING = ("wake", "steer")
_QUEUED = """
    FROM v_deliveries_cursors AS c
    JOIN v_deliveries_audience AS a ON a.reader = c.reader AND a.stream = c.stream AND a.seq > c.offered
    JOIN v_deliveries AS e ON e.seq = a.seq
"""


class Entry(BaseModel, frozen=True):
    """One message as readers get it. `sender` is an address to reply to, or `runtime`."""

    seq: int
    ref: str
    sender: str
    gist: str
    body: str | None = None
    thread: str | None = None
    reply_to: str | None = None
    hops: int = 0
    subject: str | None = None
    monitored: bool = False

    def shown(self) -> dict[str, Any]:
        return self.model_dump(exclude={"monitored"})


class Cursor(NamedTuple):
    """A reader's place in one stream, as seqs. `offered` steps back only when a handover failed."""

    offered: int = 0
    delivered: int = 0
    acked: int = 0
    closed: bool = False

    def state_of(self, seq: int) -> str:
        """Where one entry stands for this reader. None of these means understood."""
        if seq <= self.acked:
            return "acked"
        if seq <= self.delivered:
            return "delivered"
        if seq <= self.offered:
            return "offered"
        return "undeliverable" if self.closed else "queued"


class Deliveries(View):
    """Entries, the audience each one recorded, and a cursor per `(reader, stream)`, held here and not by readers."""

    schema = """
    CREATE TABLE v_deliveries(
        seq INTEGER PRIMARY KEY,
        stream TEXT NOT NULL,
        version INTEGER NOT NULL,
        delivery TEXT NOT NULL,
        due REAL NOT NULL,
        entry TEXT NOT NULL
    ) STRICT;
    CREATE INDEX v_deliveries_stream ON v_deliveries(stream, seq);
    CREATE UNIQUE INDEX v_deliveries_ref ON v_deliveries(stream, version);
    CREATE TABLE v_deliveries_audience(
        reader TEXT NOT NULL,
        stream TEXT NOT NULL,
        seq INTEGER NOT NULL,
        PRIMARY KEY (reader, stream, seq)
    ) WITHOUT ROWID, STRICT;
    CREATE TABLE v_deliveries_cursors(
        reader TEXT NOT NULL,
        stream TEXT NOT NULL,
        offered INTEGER NOT NULL DEFAULT 0,
        delivered INTEGER NOT NULL DEFAULT 0,
        acked INTEGER NOT NULL DEFAULT 0,
        closed INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (reader, stream)
    ) WITHOUT ROWID, STRICT;
    CREATE TABLE v_deliveries_offers(
        input INTEGER PRIMARY KEY,
        reader TEXT NOT NULL,
        positions TEXT NOT NULL,
        before TEXT NOT NULL,
        effect INTEGER,
        delivered INTEGER NOT NULL
    ) STRICT;
    CREATE INDEX v_deliveries_offers_effect ON v_deliveries_offers(effect);
    CREATE TABLE v_deliveries_heard(
        agent TEXT PRIMARY KEY,
        hops INTEGER NOT NULL,
        monitored INTEGER NOT NULL
    ) WITHOUT ROWID, STRICT;
    CREATE TABLE v_deliveries_blocked(agent TEXT PRIMARY KEY, why TEXT NOT NULL) WITHOUT ROWID, STRICT;
    """

    @fold("message.sent")
    def sent(self, event: Event) -> None:
        data = event.data
        entry = Entry(
            seq=event.seq,
            ref=f"{event.stream}@{event.version}",
            gist=event.gist,
            **{
                field: data[field] for field in ("sender", "body", "thread", "reply_to", "hops", "subject", "monitored")
            },
        )
        self.db.execute(
            "INSERT INTO v_deliveries VALUES (?, ?, ?, ?, ?, ?)",
            (
                event.seq,
                event.stream,
                event.version,
                data["delivery"],
                event.wall_time + data["coalesce"],
                entry.model_dump_json(),
            ),
        )
        for reader in data["audience"]:
            self.db.execute("INSERT INTO v_deliveries_audience VALUES (?, ?, ?)", (reader, event.stream, event.seq))
            self._touch(reader, event.stream)

    def _touch(self, reader: str | None, stream: str) -> None:
        self.db.execute("INSERT OR IGNORE INTO v_deliveries_cursors(reader, stream) VALUES (?, ?)", (reader, stream))

    @fold("context.offered")
    def offered(self, event: Event) -> None:
        data = event.data
        before = {stream: self.cursor(event.agent, stream).offered for stream in data["positions"]}
        for stream, seq in data["positions"].items():
            self._touch(event.agent, stream)
            self.db.execute(
                "UPDATE v_deliveries_cursors SET offered = max(offered, ?) WHERE reader = ? AND stream = ?",
                (seq, event.agent, stream),
            )
        self.db.execute(
            "INSERT INTO v_deliveries_offers VALUES (?, ?, ?, ?, NULL, 0)",
            (event.seq, event.agent, json.dumps(data["positions"]), json.dumps(before)),
        )
        self.db.execute(
            "INSERT INTO v_deliveries_heard VALUES (?, ?, ?) ON CONFLICT DO UPDATE SET "
            "hops = max(hops, excluded.hops), monitored = max(monitored, excluded.monitored)",
            (event.agent, data["hops"], data["monitored"]),
        )

    @fold("effect.requested")
    def handing_over(self, event: Event) -> None:
        data = event.data
        if data["kind"] == "deliver":
            self.db.execute(
                "UPDATE v_deliveries_offers SET effect = ? WHERE input = ?", (data["id"], data["data"]["input"])
            )

    @fold("effect.failed")
    def handover_failed(self, event: Event) -> None:
        """What never reached the harness is queued again, unless a newer offer has moved past it."""
        row = self.db.execute("SELECT * FROM v_deliveries_offers WHERE effect = ?", (event.data["id"],)).fetchone()
        if row is None:
            return
        before = json.loads(row["before"])
        for stream, seq in json.loads(row["positions"]).items():
            self.db.execute(
                "UPDATE v_deliveries_cursors SET offered = ? WHERE reader = ? AND stream = ? AND offered = ?",
                (before[stream], row["reader"], stream, seq),
            )

    @fold("context.delivered")
    def delivered(self, event: Event) -> None:
        for stream, seq in event.data["positions"].items():
            self.db.execute(
                "UPDATE v_deliveries_cursors SET delivered = max(delivered, ?) WHERE reader = ? AND stream = ?",
                (seq, event.agent, stream),
            )
        self.db.execute("UPDATE v_deliveries_offers SET delivered = 1 WHERE input = ?", (event.data["input"],))

    @fold("message.acked")
    def acked(self, event: Event) -> None:
        self.db.execute(
            "UPDATE v_deliveries_cursors SET acked = max(acked, ?) WHERE reader = ? AND stream = ?",
            (event.data["upto"], event.agent, event.data["stream"]),
        )

    @fold("turn.ended", "turn.lost")
    def turn_over(self, event: Event) -> None:
        self.db.execute("DELETE FROM v_deliveries_heard WHERE agent = ?", (event.agent,))

    @fold("agent.ended")
    def reader_gone(self, event: Event) -> None:
        self.db.execute("UPDATE v_deliveries_cursors SET closed = 1 WHERE reader = ?", (event.agent,))
        self.db.execute("DELETE FROM v_deliveries_heard WHERE agent = ?", (event.agent,))

    @fold("wake.refused")
    def refused(self, event: Event) -> None:
        if event.data["why"] != "hops":
            self.db.execute(
                "INSERT OR REPLACE INTO v_deliveries_blocked VALUES (?, ?)", (event.agent, event.data["why"])
            )

    @fold("budget.set", "budget.reconciled", "agent.ended")
    def unblocked(self, event: Event) -> None:
        """Whatever moved the budget may have made room, so every refused wake gets one more try."""
        self.db.execute("DELETE FROM v_deliveries_blocked")

    def cursor(self, reader: str | None, stream: str) -> Cursor:
        row = self.db.execute(
            "SELECT offered, delivered, acked, closed FROM v_deliveries_cursors WHERE reader = ? AND stream = ?",
            (reader, stream),
        ).fetchone()
        return Cursor() if row is None else Cursor(row["offered"], row["delivered"], row["acked"], bool(row["closed"]))

    def entries(self, stream: str, reader: str | None, after: int, *, whole: bool) -> Iterator[Entry]:
        """What `reader` may see past `after`. `whole` is the stream, else only entries whose audience held it."""
        if whole:
            rows = self.db.execute(
                "SELECT entry FROM v_deliveries WHERE stream = ? AND seq > ? ORDER BY seq", (stream, after)
            )
        else:
            rows = self.db.execute(
                """
                SELECT e.entry FROM v_deliveries_audience AS a JOIN v_deliveries AS e ON e.seq = a.seq
                WHERE a.reader = ? AND a.stream = ? AND a.seq > ? ORDER BY a.seq
                """,
                (reader, stream, after),
            )
        return (Entry.model_validate_json(row["entry"]) for row in rows)

    def at(self, stream: str, version: int) -> Entry | None:
        row = self.db.execute(
            "SELECT entry FROM v_deliveries WHERE stream = ? AND version = ?", (stream, version)
        ).fetchone()
        return None if row is None else Entry.model_validate_json(row["entry"])

    def entries_at(self, seqs: Sequence[int]) -> list[Entry]:
        marks = ", ".join("?" * len(seqs))
        rows = self.db.execute(f"SELECT entry FROM v_deliveries WHERE seq IN ({marks})", seqs)
        return [Entry.model_validate_json(row["entry"]) for row in rows]

    def depth(self, reader: str, stream: str) -> int:
        """Entries the reader has not moved past, which is what an inbox cap counts."""
        row = self.db.execute(
            """
            SELECT count(*) AS n FROM v_deliveries_audience
            WHERE reader = ?1 AND stream = ?2 AND seq > (
                SELECT coalesce(max(acked), 0) FROM v_deliveries_cursors WHERE reader = ?1 AND stream = ?2
            )
            """,
            (reader, stream),
        ).fetchone()
        return row["n"]

    def queued(self, reader: str, modes: Sequence[str]) -> tuple[list[Entry], int]:
        """The oldest entries the runtime would hand over in these modes, and how many there are in all."""
        marks = ", ".join("?" * len(modes))
        where = f"WHERE c.reader = ? AND c.closed = 0 AND e.delivery IN ({marks})"
        rows = self.db.execute(
            f"SELECT e.entry {_QUEUED} {where} ORDER BY a.seq LIMIT ?", (reader, *modes, DIGEST_ITEMS)
        ).fetchall()
        total = self.db.execute(f"SELECT count(*) AS n {_QUEUED} {where}", (reader, *modes)).fetchone()["n"]
        return [Entry.model_validate_json(row["entry"]) for row in rows], total

    def waking(self) -> list[tuple[str, float, bool]]:
        """Readers with something that may wake them: when it falls due, and whether any of it may steer."""
        rows = self.db.execute(
            f"""
            SELECT c.reader, min(e.due) AS due, max(e.delivery = 'steer') AS steer {_QUEUED}
            WHERE c.closed = 0 AND e.delivery IN ('wake', 'steer')
                AND c.reader NOT IN (SELECT agent FROM v_deliveries_blocked)
            GROUP BY c.reader ORDER BY c.reader
            """
        )
        return [(row["reader"], row["due"], bool(row["steer"])) for row in rows]

    def unread(self, reader: str) -> int:
        return self.db.execute(
            f"SELECT count(*) AS n {_QUEUED} WHERE c.reader = ? AND c.closed = 0", (reader,)
        ).fetchone()["n"]

    def stops(self, reader: str, shown: Sequence[Entry], *, whole: bool = False) -> dict[str, int]:
        """How far each cursor may move for `shown`: up to the first entry left out, and never past it."""
        offered = {entry.seq for entry in shown}
        streams = {entry.ref.partition("@")[0] for entry in shown}
        positions = {}
        for stream in streams:
            for entry in self.entries(stream, reader, self.cursor(reader, stream).offered, whole=whole):
                if entry.seq not in offered:
                    break
                positions[stream] = entry.seq
        return positions

    def heard(self, agent: str | None) -> tuple[int, bool] | None:
        """The largest hops offered to this agent's turn, and whether a monitor has spent that chain's wake."""
        row = self.db.execute("SELECT * FROM v_deliveries_heard WHERE agent = ?", (agent,)).fetchone()
        return None if row is None else (row["hops"], bool(row["monitored"]))

    def blocked(self, agent: str) -> str | None:
        row = self.db.execute("SELECT why FROM v_deliveries_blocked WHERE agent = ?", (agent,)).fetchone()
        return None if row is None else row["why"]

    def offer(self, input: int) -> tuple[str, dict[str, int], bool] | None:
        row = self.db.execute("SELECT * FROM v_deliveries_offers WHERE input = ?", (input,)).fetchone()
        return None if row is None else (row["reader"], json.loads(row["positions"]), bool(row["delivered"]))


class _Reach(NamedTuple):
    """Where one message goes. `generation` is the group's, and `human` names a person to bring it to."""

    channel: Channel
    readers: tuple[str, ...]
    generation: int | None = None
    human: str | None = None


def _reach(txn: Txn, stream: str) -> _Reach:
    """A message's settings and its audience at this commit."""
    channel = txn.view(Channels).get(stream)
    if stream.startswith("inbox/"):
        name = stream.removeprefix("inbox/")
        agent = txn.view(Agents).get(name)
        if agent is not None and agent.ended:
            raise Refused("undeliverable", f"{name} has ended: {agent.status}")
        if channel is not None:
            return _Reach(channel, (name,))
        principals = txn.view(Principals)
        if principals.get(f"human:{name}") is not None:
            return _Reach(Channel(stream=stream, kind="inbox"), (name,), human=f"human:{name}")
        if principals.get(f"program:{name}") is not None:
            return _Reach(Channel(stream=stream, kind="inbox"), (name,))
        raise Refused("not_found", f"nobody is called {name}")
    if channel is None:
        raise Refused("not_found", f"no channel {stream}")
    if stream.startswith("channel/+"):
        group = stream.removeprefix("channel/+")
        generation = txn.view(Stamps).version_of(f"group/{group}")
        return _Reach(channel, txn.view(Groups).get(group).members, generation)
    grants = txn.view(Grants)
    live = txn.view(Principals).select(txn.me, "all")
    return _Reach(
        channel, tuple(p.name for p in live if p.kind == "agent" and grants.permits(p, "message.read", stream))
    )


def _chain(txn: Txn, cause: Sequence[int], subject: str | None) -> tuple[int, bool]:
    """One hop more than anything this followed from, and whether a monitor has spent that chain's wake."""
    if txn.me.kind == "human":
        return 0, False
    deliveries = txn.view(Deliveries)
    heard = deliveries.heard(subject or (txn.me.name if txn.me.kind == "agent" else None))
    behind = deliveries.entries_at(cause)
    hops = [entry.hops for entry in behind] + ([heard[0]] if heard else [])
    return max(hops, default=-1) + 1, any(entry.monitored for entry in behind) or bool(heard and heard[1])


def post(
    txn: Txn,
    stream: str,
    gist: str,
    *,
    body: str | None = None,
    thread: str | None = None,
    reply_to: str | None = None,
    cause: Sequence[int] = (),
    based_on: Sequence[str] = (),
    subject: str | None = None,
    wake: bool = False,
) -> Event:
    """Journal one entry for its audience. The runtime posts here too, about a `subject` or to `wake` the reader."""
    channel, readers, generation, human = _reach(txn, stream)
    by_runtime = subject is not None or wake
    audience = readers if channel.kind == "inbox" else tuple(reader for reader in readers if reader != txn.me.name)
    if channel.depth is not None and not by_runtime:
        depth = txn.view(Deliveries).depth(readers[0], stream)
        if depth >= channel.depth:
            raise Refused("queue_full", {"receipt": "full", "depth": depth, "cap": channel.depth})

    hops, monitored = _chain(txn, cause, subject)
    max_hops = txn.view(Session).settings().limits.max_hops
    past_hops = max_hops is not None and hops > max_hops
    setting = "wake" if wake else channel.delivery
    wakes = not past_hops and not (subject is not None and monitored)
    event = txn.emit(
        "message.sent",
        stream,
        gist=gist,
        agent=subject,
        cause=cause,
        based_on=based_on,
        refs=[ref for ref in (body, reply_to) if ref is not None],
        correlation=thread,
        runtime=by_runtime,
        data={
            "sender": "runtime" if by_runtime or txn.me.kind == "runtime" else f"@{txn.me.name}",
            "body": body,
            "thread": thread,
            "reply_to": reply_to,
            "hops": hops,
            "subject": subject,
            "monitored": monitored or subject is not None,
            "audience": audience,
            "generation": generation,
            "delivery": "next-turn" if setting in _WAKING and not wakes else setting,
            "coalesce": channel.coalesce,
            "mention": human,
        },
    )
    if setting in _WAKING and past_hops:
        ref = f"{event.stream}@{event.version}"
        for reader in audience:
            data = {"why": "hops", "hops": hops, "limit": max_hops, "ref": ref}
            txn.emit("wake.refused", f"wake/{reader}", gist=f"wake of {reader} past max_hops", agent=reader, data=data)
    return event


class Send(Args):
    to: str
    gist: Gist
    body: BodyRef | None = None
    thread: Annotated[str, Field(max_length=512)] | None = None
    reply_to: Annotated[str, Field(max_length=512)] | None = None
    cause: tuple[int, ...] = ()
    based_on: tuple[str, ...] = ()


def _replied(txn: Txn, ref: str) -> Entry:
    stream, _, version = ref.partition("@")
    entry = txn.view(Deliveries).at(stream, int(version)) if version.isdecimal() else None
    if entry is None:
        raise Refused("not_found", f"no message {ref}")
    return entry


@op("message.send", on=lambda a: stream_of(a.to), tool=True)
def send(txn: Txn, a: Send) -> dict[str, Any]:
    """Send to `@agent`, `#channel` or `+group`. `gist` is what readers see first; `body` is a stored body's hash. A
    reply names `reply_to`, a ref from `message.read`, and joins its thread. Refused `not_permitted` when no edge
    reaches the target: call `peers`. Refused `undeliverable` when the agent has ended, and `queue_full` when its inbox
    is full: try later or by another route."""
    thread, cause = a.thread, a.cause
    if a.reply_to is not None:
        replied = _replied(txn, a.reply_to)
        thread = thread or replied.thread or replied.ref
        cause = (*cause, replied.seq)
    stream = stream_of(a.to)
    event = post(txn, stream, a.gist, body=a.body, thread=thread, reply_to=a.reply_to, cause=cause, based_on=a.based_on)
    data = event.data
    return {
        "ref": f"{stream}@{event.version}",
        "seq": event.seq,
        "hops": data["hops"],
        "audience": len(data["audience"]),
    }


def ack(txn: Txn, reader: str, stream: str, upto: int) -> None:
    """Move past what was offered, clamped to the highest offered, so a made-up number acks nothing unshown."""
    cursor = txn.view(Deliveries).cursor(reader, stream)
    upto = min(upto, cursor.offered)
    if upto > cursor.acked:
        data = {"stream": stream, "upto": upto}
        txn.emit("message.acked", f"cursor/{reader}", gist=f"{stream} acked to {upto}", agent=reader, data=data)


class Read(Args):
    channel: str
    after: Annotated[int, Field(ge=0)] | None = None
    limit: Annotated[int, Field(ge=1, le=DIGEST_ITEMS)] = DIGEST_ITEMS
    sender: str | None = None
    thread: str | None = None
    bodies: bool = False


class _Shown(NamedTuple):
    """An entry as a reader gets it, and what showing it exposed."""

    entry: Entry
    row: dict[str, Any]
    exposed: list[Exposed]


def _show(txn: Txn, entry: Entry, *, bodies: bool) -> _Shown:
    row = entry.shown()
    exposed = [Exposed.of(entry.ref, "gist", entry.gist)]
    if bodies and entry.body is not None:
        data = inline_body(txn, entry.body)
        text = decoded(data) if data is not None and len(data) <= RESULT_LIMIT else None
        if data is not None and text is not None:
            row["text"] = text
            exposed.append(Exposed.of(entry.body, "body", data))
    return _Shown(entry, row, exposed)


@op("message.read", on=lambda a: stream_of(a.channel), exposes=True, tool=True)
def read(txn: Txn, a: Read) -> dict[str, Any]:
    """Read `@you`, `#channel` or `+group` from where you left off. Passing `after` acks up to it and reads past it.
    `sender` and `thread` filter, and a filtered read leaves unread what it skipped. `bodies` adds bodies, recorded
    apart from gists. `behind` counts what is left. Refused `not_permitted` when you do not read this channel: call
    `channel.list`."""
    stream = stream_of(a.channel)
    deliveries = txn.view(Deliveries)
    channel = txn.view(Channels).get(stream)
    reader = txn.me.name if txn.me.kind == "agent" else None
    whole = reader is None or (channel is not None and channel.history == "full")
    start = deliveries.cursor(reader, stream).offered if a.after is None else a.after
    if reader is not None:
        ack(txn, reader, stream, start)

    def wanted(entry: Entry) -> bool:
        in_thread = a.thread is None or a.thread in (entry.thread, entry.ref)
        return in_thread and (a.sender is None or entry.sender == a.sender)

    scanned = islice(deliveries.entries(stream, reader, start, whole=whole), _SCAN_LIMIT)
    matching = islice(filter(wanted, scanned), a.limit)
    shown = fitted((_show(txn, entry, bodies=a.bodies) for entry in matching), show=lambda item: item.row)
    entries = [item.entry for item in shown]
    expose_read(
        txn,
        [exposed for item in shown for exposed in item.exposed],
        positions=None if reader is None else deliveries.stops(reader, entries, whole=whole),
        hops=max((entry.hops for entry in entries), default=0),
        monitored=any(entry.monitored for entry in entries),
    )
    cursor = entries[-1].seq if entries else start
    behind = sum(1 for _ in islice(deliveries.entries(stream, reader, cursor, whole=whole), _SCAN_LIMIT))
    return {"entries": [item.row for item in shown], "cursor": cursor, "behind": behind}
