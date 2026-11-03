"""Inboxes and topics: entries, who each is for, and how far each reader has got."""

import json
from collections.abc import Iterator, Sequence
from itertools import islice
from typing import Annotated, Any, NamedTuple

from pydantic import BaseModel, Field

from platoon_harness.kernel import GIST_LIMIT, Args, Event, Grants, Principals, Refused, Stamps, Txn, View, fold, op

from .agents import Agents
from .channels import Channel, Channels, Groups
from .common import (
    DIGEST_ITEMS,
    IN_A_RESULT,
    RESULT_LIMIT,
    WAKING,
    AgentName,
    BasedOn,
    Body,
    Exposed,
    Gist,
    Seq,
    address,
    checked_after,
    decoded,
    expose_read,
    fitted,
    inline_body,
    size_of,
    stream_of,
)
from .sessions import SessionRecord

_SCAN_LIMIT = 4096
_VERSION_DIGITS = 18
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


class Cursor(NamedTuple):
    """A reader's place in one stream, as seqs. `offered` steps back only when a handover failed, and `shown` is how far
    a tool's result took it, which unlike a handover needs no confirming."""

    offered: int = 0
    delivered: int = 0
    acked: int = 0
    closed: bool = False
    shown: int = 0

    def state_of(self, seq: int) -> str:
        """Where one entry stands for this reader. None of these means understood."""
        if seq <= self.acked:
            return "acked"
        if seq <= self.delivered:
            return "delivered"
        if seq <= self.offered:
            return "offered"
        return "undeliverable" if self.closed else "queued"


class Offered(NamedTuple):
    """One offer: whose, how far it moves each cursor, whether a driver confirmed it landed, and what it carries into
    the turn that hears it."""

    reader: str
    positions: dict[str, int]
    delivered: bool
    hops: int
    asked: bool


class Deliveries(View):
    """Entries, the audience each one recorded, and a cursor per `(reader, stream)`, held here and not by readers."""

    version = 4
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
        shown INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (reader, stream)
    ) WITHOUT ROWID, STRICT;
    CREATE TABLE v_deliveries_offers(
        input INTEGER PRIMARY KEY,
        reader TEXT NOT NULL,
        positions TEXT NOT NULL,
        before TEXT NOT NULL,
        effect INTEGER,
        delivered INTEGER NOT NULL,
        taken INTEGER NOT NULL DEFAULT 0,
        hops INTEGER NOT NULL,
        asked INTEGER NOT NULL
    ) STRICT;
    CREATE INDEX v_deliveries_offers_effect ON v_deliveries_offers(effect);
    CREATE TABLE v_deliveries_heard(agent TEXT PRIMARY KEY, hops INTEGER NOT NULL) WITHOUT ROWID, STRICT;
    CREATE TABLE v_deliveries_blocked(agent TEXT PRIMARY KEY, why TEXT NOT NULL) WITHOUT ROWID, STRICT;
    """

    @fold("message.sent")
    def sent(self, event: Event) -> None:
        data = event.data
        entry = Entry(
            seq=event.seq,
            ref=f"{event.stream}@{event.version}",
            gist=event.gist,
            **{field: data[field] for field in ("sender", "body", "thread", "reply_to", "hops", "subject")},
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
        """A v1 offer asked nothing of its reader."""
        data = event.data
        before = {stream: self.cursor(event.agent, stream).offered for stream in data["positions"]}
        in_a_result = data["how"] in IN_A_RESULT
        for stream, seq in data["positions"].items():
            self._touch(event.agent, stream)
            self.db.execute(
                "UPDATE v_deliveries_cursors SET offered = max(offered, ?), shown = max(shown, ?) "
                "WHERE reader = ? AND stream = ?",
                (seq, seq if in_a_result else 0, event.agent, stream),
            )
        self.db.execute(
            """
            INSERT INTO v_deliveries_offers(input, reader, positions, before, delivered, hops, asked)
            VALUES (?, ?, ?, ?, 0, ?, ?)
            """,
            (
                event.seq,
                event.agent,
                json.dumps(data["positions"]),
                json.dumps(before),
                data["hops"],
                data.get("asked", False),
            ),
        )
        self._heard(event.agent, data["hops"])

    def _heard(self, agent: str | None, hops: int) -> None:
        self.db.execute(
            "INSERT INTO v_deliveries_heard VALUES (?, ?) ON CONFLICT DO UPDATE SET hops = max(hops, excluded.hops)",
            (agent, hops),
        )

    @fold("effect.requested")
    def handing_over(self, event: Event) -> None:
        data = event.data
        if data["kind"] == "deliver":
            self.db.execute(
                "UPDATE v_deliveries_offers SET effect = ? WHERE input = ?", (data["id"], data["data"]["input"])
            )

    @fold("effect.finished")
    def taken(self, event: Event) -> None:
        """The harness has it, which says nothing of whether it will land."""
        self.db.execute("UPDATE v_deliveries_offers SET taken = 1 WHERE effect = ?", (event.data["id"],))

    def _queue_again(self, offer: Any) -> None:
        """Queue an offer's entries again, even past a newer offer: at-least-once allows the repeat, and the event id
        dedupes it."""
        for stream, seq in json.loads(offer["before"]).items():
            self.db.execute(
                "UPDATE v_deliveries_cursors SET offered = min(offered, ?) WHERE reader = ? AND stream = ?",
                (seq, offer["reader"], stream),
            )

    @fold("effect.failed")
    def handover_failed(self, event: Event) -> None:
        """What never reached the harness is queued again. Its reservation has come back too, so a refused wake gets
        another try."""
        row = self.db.execute("SELECT * FROM v_deliveries_offers WHERE effect = ?", (event.data["id"],)).fetchone()
        if row is not None:
            self._queue_again(row)
            self.db.execute("DELETE FROM v_deliveries_blocked")

    @fold("turn.ended", "turn.lost", "agent.resumed")
    def stopped_short(self, event: Event) -> None:
        """What a harness took and never landed is queued again when its turn stops short, or when it comes back from
        a crash, as none of them keeps it for certain. One that stopped on its own lands it in the turn that follows."""
        if event.type == "turn.ended" and event.data["reason"] == "stopped":
            return
        rows = self.db.execute(
            "SELECT * FROM v_deliveries_offers WHERE reader = ? AND taken = 1 AND delivered = 0", (event.agent,)
        ).fetchall()
        for row in rows:
            self._queue_again(row)
        self.db.execute("UPDATE v_deliveries_offers SET taken = 0 WHERE reader = ?", (event.agent,))

    @fold("context.delivered")
    def delivered(self, event: Event) -> None:
        """Its offer's hops count in the turn it landed in too, which for a steer can be the one after the offer's. A v1
        landing carried none: its offer's counted alone."""
        for stream, seq in event.data["positions"].items():
            self.db.execute(
                "UPDATE v_deliveries_cursors SET delivered = max(delivered, ?) WHERE reader = ? AND stream = ?",
                (seq, event.agent, stream),
            )
        self.db.execute("UPDATE v_deliveries_offers SET delivered = 1 WHERE input = ?", (event.data["input"],))
        self._heard(event.agent, event.data.get("hops", -1))

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

    @fold("budget.set", "budget.reconciled", "agent.ended", "turn.lost")
    def unblocked(self, event: Event) -> None:
        """Whatever moved the budget may have made room, so every refused wake gets one more try."""
        self.db.execute("DELETE FROM v_deliveries_blocked")

    def cursor(self, reader: str | None, stream: str) -> Cursor:
        row = self.db.execute(
            "SELECT offered, delivered, acked, closed, shown FROM v_deliveries_cursors WHERE reader = ? AND stream = ?",
            (reader, stream),
        ).fetchone()
        return Cursor() if row is None else Cursor(*row[:3], bool(row["closed"]), row["shown"])

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

    def addressed(self, reader: str, stream: str, seq: int) -> bool:
        """Whether an entry's recorded audience held this reader."""
        row = self.db.execute(
            "SELECT 1 FROM v_deliveries_audience WHERE reader = ? AND stream = ? AND seq = ?", (reader, stream, seq)
        ).fetchone()
        return row is not None

    def entries_at(self, seqs: Sequence[int]) -> list[Entry]:
        marks = ", ".join("?" * len(seqs))
        rows = self.db.execute(f"SELECT entry FROM v_deliveries WHERE seq IN ({marks})", seqs)
        return [Entry.model_validate_json(row["entry"]) for row in rows]

    def depth(self, reader: str, stream: str) -> int:
        """Entries still to reach the reader, which is what an inbox cap counts. One a driver confirmed has reached it,
        so a harness whose tools are hidden never reads, and its inbox still drains."""
        row = self.db.execute(
            """
            SELECT count(*) AS n FROM v_deliveries_audience
            WHERE reader = ?1 AND stream = ?2 AND seq > coalesce(
                (SELECT max(acked, delivered) FROM v_deliveries_cursors WHERE reader = ?1 AND stream = ?2), 0
            )
            """,
            (reader, stream),
        ).fetchone()
        return row["n"]

    def queued(self, reader: str, modes: Sequence[str]) -> tuple[list[Entry], int]:
        """The oldest entries an offer in these modes hands over, and how many there are in all: on each stream, all up
        to the newest of those modes, since a cursor cannot pass one left out."""
        marks = ", ".join("?" * len(modes))
        where = f"""
            WHERE c.reader = ? AND c.closed = 0 AND a.seq <= (
                SELECT max(o.seq) FROM v_deliveries_audience AS o JOIN v_deliveries AS n ON n.seq = o.seq
                WHERE o.reader = c.reader AND o.stream = c.stream AND n.delivery IN ({marks})
            )
        """
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

    def report_queued(self, reader: str) -> bool:
        """Whether a report of a child waits for this reader's next turn."""
        return (
            self.db.execute(
                f"""
                SELECT 1 {_QUEUED}
                WHERE c.reader = ? AND c.closed = 0 AND e.delivery = 'next-turn'
                    AND json_extract(e.entry, '$.subject') IS NOT NULL
                LIMIT 1
                """,
                (reader,),
            ).fetchone()
            is not None
        )

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

    def heard(self, agent: str | None) -> int:
        """The largest hops offered to this agent's turn or landed in it, or -1 when nothing has been."""
        row = self.db.execute("SELECT hops FROM v_deliveries_heard WHERE agent = ?", (agent,)).fetchone()
        return -1 if row is None else row["hops"]

    def blocked(self, agent: str) -> str | None:
        row = self.db.execute("SELECT why FROM v_deliveries_blocked WHERE agent = ?", (agent,)).fetchone()
        return None if row is None else row["why"]

    def any_blocked(self) -> bool:
        """Whether a budget has refused a wake that nothing has given another try."""
        return self.db.execute("SELECT 1 FROM v_deliveries_blocked LIMIT 1").fetchone() is not None

    def offer(self, input: int) -> Offered | None:
        row = self.db.execute("SELECT * FROM v_deliveries_offers WHERE input = ?", (input,)).fetchone()
        if row is None:
            return None
        positions = json.loads(row["positions"])
        return Offered(row["reader"], positions, bool(row["delivered"]), row["hops"], bool(row["asked"]))


class _Reach(NamedTuple):
    """Where one message goes. `generation` is the group's, and `human` names a person to bring it to."""

    channel: Channel
    readers: tuple[str, ...]
    generation: int | None = None
    human: str | None = None


def _audience(txn: Txn, stream: str) -> _Reach:
    """A message's settings and its audience at this commit."""
    channel = txn.view(Channels).get(stream)
    if stream.startswith("inbox/"):
        name = stream.removeprefix("inbox/")
        principal = txn.view(Principals).named(name)
        if principal is None:
            raise Refused("not_found", f"nobody is called {name}")
        if principal.state != "live":
            agent = txn.view(Agents).get(name)
            raise Refused("undeliverable", f"{name} has ended: {agent.status}" if agent else f"{name} has left")
        if channel is None and principal.kind not in ("human", "program"):
            raise Refused("not_found", f"{name} has no inbox")
        human = principal.id if principal.kind == "human" else None
        return _Reach(channel or Channel(stream=stream, kind="inbox"), (name,), human=human)
    if channel is None:
        raise Refused("not_found", f"no channel {stream}")
    if stream.startswith("channel/+"):
        group = stream.removeprefix("channel/+")
        generation = txn.view(Stamps).version_of(f"group/{group}")
        return _Reach(channel, txn.view(Groups).get(group).members, generation)
    grants = txn.view(Grants)
    live = txn.view(Principals).select(txn.me, "all")
    readers = (p.name for p in live if p.kind == "agent" and grants.permits(p, channel.reading, channel.object))
    return _Reach(channel, tuple(readers))


def chain_of(txn: Txn, reader: str, entries: Sequence[Entry]) -> dict[str, Any]:
    """What an offer of these entries carries into the turn that hears them: the largest hops, and whether the
    reader's parent asked it something, by a message of its own to the reader's inbox that it was never offered."""
    agent = txn.view(Agents).get(reader)
    parent = None if agent is None or agent.parent is None else address(agent.parent)
    inbox = f"inbox/{reader}"
    offered = txn.view(Deliveries).cursor(reader, inbox).offered
    new = [entry for entry in entries if entry.seq > offered and entry.ref.startswith(f"{inbox}@")]
    return {
        "hops": max((entry.hops for entry in entries), default=0),
        "asked": any(entry.sender == parent for entry in new),
    }


def _hops(txn: Txn, cause: Sequence[int], subject: str | None, follows: int) -> int:
    """One hop more than anything this followed from."""
    if txn.me.kind == "human":
        return 0
    deliveries = txn.view(Deliveries)
    heard = deliveries.heard(subject or (txn.me.name if txn.me.kind == "agent" else None))
    return max(follows, heard, *(entry.hops for entry in deliveries.entries_at(cause))) + 1


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
    wake: bool | None = None,
    answers: bool = False,
    follows: int = -1,
) -> Event:
    """Journal one entry for its audience. The runtime posts here too: a report about a `subject`, which wakes its
    reader only while that agent was asked something, and `answers` it, or to `wake` the reader regardless, or with
    False to leave it for the reader's next turn. `follows` is the hops of what a post follows when no `cause` can say
    so, as for a wait's notice."""
    channel, readers, generation, human = _audience(txn, stream)
    by_runtime = subject is not None or wake is not None
    audience = readers if channel.kind == "inbox" else tuple(reader for reader in readers if reader != txn.me.name)
    if channel.depth is not None and not by_runtime:
        depth = txn.view(Deliveries).depth(readers[0], stream)
        if depth >= channel.depth:
            raise Refused("queue_full", {"receipt": "full", "depth": depth, "cap": channel.depth})

    hops = _hops(txn, cause, subject, follows)
    max_hops = txn.view(SessionRecord).settings().limits.max_hops
    past_hops = max_hops is not None and hops > max_hops
    setting = "wake" if wake else channel.delivery
    wants = setting in WAKING and wake is not False
    about = None if subject is None else txn.view(Agents).get(subject)
    wakes = wants and not past_hops and (wake or about is None or about.asked)
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
            "answers": answers,
            "audience": audience,
            "generation": generation,
            "delivery": "next-turn" if setting in WAKING and not wakes else setting,
            "coalesce": channel.coalesce,
            "mention": human,
        },
        v=2,
    )
    if wants and past_hops:
        ref = f"{event.stream}@{event.version}"
        for reader in audience:
            data = {"why": "hops", "hops": hops, "limit": max_hops, "ref": ref}
            txn.emit("wake.refused", f"wake/{reader}", gist=f"wake of {reader} past max_hops", agent=reader, data=data)
    return event


def announce(txn: Txn, channel: Channel, gist: str, cause: int) -> None:
    """Tell a queue's or board's readers of a write as an entry, so `delivery` works as it does on a topic. It announces
    work and never assigns it. `pull` wants no telling, and an entry nobody takes would pile up unread."""
    if channel.delivery != "pull":
        post(txn, channel.stream, gist[:GIST_LIMIT], cause=[cause])


class Send(Args):
    to: Annotated[str, Field(description="`@agent`, `#channel` or `+group`.")]
    gist: Gist
    body: Body = None
    thread: Annotated[str | None, Field(max_length=512, description="A thread id. `reply_to` sets it for you.")] = None
    reply_to: Annotated[str | None, Field(max_length=512, description="The `ref` of the entry you answer.")] = None
    based_on: BasedOn = ()


def _reads_whole(txn: Txn, stream: str) -> bool:
    """Whether the caller reads this stream entire, and not only the entries whose audience held it."""
    channel = txn.view(Channels).get(stream)
    return txn.me.kind != "agent" or (channel is not None and channel.history == "full")


def _replied(txn: Txn, ref: str) -> Entry:
    """The entry `ref` names, if the caller may read it. A miss and a denial answer alike, so a ref is no oracle."""
    stream, _, version = ref.partition("@")
    deliveries = txn.view(Deliveries)
    entry = deliveries.at(stream, int(version)) if version.isdecimal() and len(version) <= _VERSION_DIGITS else None
    readable = entry is not None and (
        txn.view(Grants).permits(txn.me, "message.read", stream)
        and (_reads_whole(txn, stream) or deliveries.addressed(txn.me.name, stream, entry.seq))
    )
    if entry is None or not readable:
        raise Refused("not_found", f"no message {ref}")
    return entry


@op("message.send", on=lambda a: stream_of(a.to), tool=True)
def send(txn: Txn, a: Send) -> dict[str, Any]:
    """Send to `@agent`, `#channel` or `+group`. `gist`, at most 280 characters, is what readers see first; put anything
    longer in `body`. To reply, set `to` to the entry's `sender` and `reply_to` to its `ref`. Refused `not_permitted`
    when you cannot reach the target. Call `peers` for agents, `channel.list` for channels. `undeliverable` when the
    agent has ended: tell someone else. `queue_full` when its inbox is full: try later. `not_found` when `reply_to`
    names nothing you can read. `conflict` once the session is closing, when it would reach nobody."""
    session = txn.view(SessionRecord)
    if not session.accepting():
        raise Refused(
            "conflict", f"the session is {session.state()}, so nothing new starts and this would reach nobody"
        )
    thread, cause = a.thread, ()
    if a.reply_to is not None:
        replied = _replied(txn, a.reply_to)
        thread = thread or replied.thread or replied.ref
        cause = (replied.seq,)
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
    """Move past what the agent saw: a tool's result, or a handover a driver confirmed. So a made-up number, or a read
    while an offer is in flight, acks nothing unshown."""
    cursor = txn.view(Deliveries).cursor(reader, stream)
    upto = min(upto, cursor.offered, max(cursor.shown, cursor.delivered))
    if upto > cursor.acked:
        data = {"stream": stream, "upto": upto}
        txn.emit("message.acked", f"cursor/{reader}", gist=f"{stream} acked to {upto}", agent=reader, data=data)


class Read(Args):
    channel: Annotated[str | None, Field(description="`#channel` or `+group`; your own inbox if left out.")] = None
    after: Annotated[Seq | None, Field(description="A `cursor` from an earlier read.")] = None
    limit: Annotated[int, Field(ge=1, le=DIGEST_ITEMS, description="The most entries to return.")] = DIGEST_ITEMS
    sender: Annotated[AgentName | None, Field(description="Only entries from this agent.")] = None
    thread: Annotated[str | None, Field(description="Only entries of this thread.")] = None
    bodies: Annotated[bool, Field(description="Add each body's `text`.")] = False


class _Shown(NamedTuple):
    """An entry as a reader gets it, and what showing it exposed."""

    entry: Entry
    row: dict[str, Any]
    exposed: list[Exposed]


def _show(txn: Txn, entry: Entry, *, bodies: bool) -> _Shown:
    row = entry.model_dump()
    exposed = [Exposed.of(entry.ref, "gist", entry.gist)]
    if bodies and entry.body is not None:
        row["text"] = None  # A surface fetches what an op may not read.
        data = inline_body(txn, entry.body)
        text = None if data is None else decoded(data)
        if data is not None and text is not None and size_of({**row, "text": text}) <= RESULT_LIMIT:
            row["text"] = text
            exposed.append(Exposed.of(entry.body, "body", data))
    return _Shown(entry, row, exposed)


@op("message.read", on=lambda a: None, exposes=True, tool=True)
def read(txn: Txn, a: Read) -> dict[str, Any]:
    """Read your inbox, or `#channel` or `+group`, from where you left off. Passing `after`, a `cursor` from an earlier
    read, acks up to it and reads past it. `sender` and `thread` filter, and a filtered read leaves unread what it
    skipped. `bodies` adds body `text`, recorded apart from gists; a long one comes back cut, with `rest` a ref, and
    past what one result holds `text` is null. Pass `rest` or `body` to `blob.get`. `behind` counts what is left, up to
    4096. Refused `not_permitted` when you do not read this channel. Call `channel.list` to see yours. `invalid` for an
    `after` past every event: leave it out."""
    stream = stream_of(a.channel) if a.channel else f"inbox/{txn.me.name}"
    txn.view(Grants).authorize(txn.me, read, stream)
    deliveries = txn.view(Deliveries)
    reader = txn.me.name if txn.me.kind == "agent" else None
    whole = _reads_whole(txn, stream)
    after = checked_after(txn, a.after)
    start = deliveries.cursor(reader, stream).offered if after is None else after
    if reader is not None:
        ack(txn, reader, stream, start)

    def wanted(entry: Entry) -> bool:
        in_thread = a.thread is None or a.thread in (entry.thread, entry.ref)
        return in_thread and (a.sender is None or a.sender in (entry.sender.removeprefix("@"), entry.subject))

    def window(past: int) -> Iterator[Entry]:
        return islice(deliveries.entries(stream, reader, past, whole=whole), _SCAN_LIMIT)

    matching = islice(filter(wanted, window(start)), a.limit)
    shown = fitted((_show(txn, entry, bodies=a.bodies) for entry in matching), show=lambda item: item.row)
    entries = [item.entry for item in shown]
    expose_read(
        txn,
        [exposed for item in shown for exposed in item.exposed],
        positions=None if reader is None else deliveries.stops(reader, entries, whole=whole),
        **chain_of(txn, txn.me.name, entries),
    )
    cursor = entries[-1].seq if entries else start
    left = list(window(cursor))
    if not entries and len(left) == _SCAN_LIMIT:  # A whole window matched nothing, so go on from past it.
        cursor = left[-1].seq
        left = list(window(cursor))
    return {"entries": [item.row for item in shown], "cursor": cursor, "behind": len(left)}
