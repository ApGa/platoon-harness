"""Provenance: what reached an agent, what an event rests on, what rests on it, and whose work an outcome reaches.

The graph is not stored. Three views index the references events already hold, `Exposures` among them, and the queries
answer from them, for people and programs and never as an agent's tool: four about events, and `spans`, which cuts an
agent's turns where its model calls chose its writes. A query reads the journal alone, and never an annotation. See
architecture section 11.
"""

import json
import sqlite3
from collections import defaultdict, deque
from collections.abc import Callable, Collection, Iterator, Mapping, Sequence
from functools import cache, partial
from typing import Annotated, Any, Literal, NamedTuple, get_args

from pydantic import Field

from platoon_harness.kernel import Args, Event, Principals, Refused, Stamps, Txn, View, fold, op
from platoon_harness.schema import Model

from .agents import Agents
from .clients import Gaps
from .common import DIGEST_ITEMS, AgentName, event_at, inline_body, maker, name_of, parts_of
from .exposures import Exposures
from .repo import Looks, Uncited
from .reports import GAPS, Surface

WALK_LIMIT = 4096
"""How many events a walk back from an outcome reaches before it stops and says so."""

_PAGE = DIGEST_ITEMS
_SURFACES: tuple[Surface, ...] = get_args(Surface)
_UNCARRIED = tuple(what for what, kind in GAPS.items() if not kind.carries)

Back = Literal["declared", "cause", "ancestry"]
"""The edges that lead back from an event and are no exposure: a citation, a stated cause, and a previous version or a
commit's parent."""

_WRITES = frozenset(
    {
        "message.sent",
        "board.posted",
        "board.revised",
        "task.added",
        "task.completed",
        "task.failed",
        "agent.spawned",
        "agent.finished",
    }
)
"""The events that hold an agent's writes of content, the eight ops that take `based_on`, but `agent.finish` out of a
turn, whose event is its agent's own end."""


def _ref(event: Event) -> str:
    return f"{event.stream}@{event.version}"


def _versioned(event: Event) -> bool:
    """Whether an event is a version of an object with a stream of its own: a board object or a task."""
    return event.type in ("board.posted", "board.revised") or event.stream.startswith("task/")


# The views.


class References(View):
    """The references events hold, by what they point at: what cites an event, what follows from one, which commits
    name a commit as a parent, and which of an agent's events came under one tool call's id."""

    schema = """
    CREATE TABLE v_references_cited(stream TEXT NOT NULL, version INTEGER NOT NULL, seq INTEGER NOT NULL) STRICT;
    CREATE INDEX v_references_cited_event ON v_references_cited(stream, version, seq);
    CREATE TABLE v_references_caused(
        cause INTEGER NOT NULL, seq INTEGER NOT NULL, PRIMARY KEY (cause, seq)
    ) WITHOUT ROWID, STRICT;
    CREATE TABLE v_references_parents(
        sha TEXT NOT NULL, seq INTEGER NOT NULL, PRIMARY KEY (sha, seq)
    ) WITHOUT ROWID, STRICT;
    CREATE TABLE v_references_anchors(
        agent TEXT NOT NULL, anchor TEXT NOT NULL, seq INTEGER NOT NULL, PRIMARY KEY (agent, anchor, seq)
    ) WITHOUT ROWID, STRICT;
    """

    @fold("*")
    def held(self, event: Event) -> None:
        """Any event can cite or follow from another, an extension's too, so this cannot name what it folds."""
        for ref in event.based_on:
            stream, version, _ = parts_of(ref) or (None, None, None)
            if stream is not None:
                self.db.execute("INSERT INTO v_references_cited VALUES (?, ?, ?)", (stream, version, event.seq))
        for cause in event.cause:
            self.db.execute("INSERT OR IGNORE INTO v_references_caused VALUES (?, ?)", (cause, event.seq))
        if event.native and event.actor.startswith("agent:"):
            anchor = next(iter(event.native.values()))
            self.db.execute(
                "INSERT INTO v_references_anchors VALUES (?, ?, ?)", (name_of(event.actor), anchor, event.seq)
            )

    @fold("repo.committed")
    def committed(self, event: Event) -> None:
        for sha in event.data["parents"]:
            self.db.execute("INSERT OR IGNORE INTO v_references_parents VALUES (?, ?)", (sha, event.seq))

    def citing(self, stream: str, version: int, after: int) -> tuple[list[int], int]:
        """The seqs of the events that cite one, past `after`, as many as a page holds and one more, and how many in
        all."""
        found = "FROM v_references_cited WHERE stream = ? AND version = ?"
        rows = self.db.execute(
            f"SELECT DISTINCT seq {found} AND seq > ? ORDER BY seq LIMIT ?", (stream, version, after, _PAGE + 1)
        )
        total = self.db.execute(f"SELECT count(DISTINCT seq) AS n {found}", (stream, version)).fetchone()["n"]
        return [row["seq"] for row in rows], total

    def caused(self, cause: int, after: int) -> tuple[list[int], int]:
        """The seqs of the events that follow from one, past `after`, as `citing` gives them."""
        rows = self.db.execute(
            "SELECT seq FROM v_references_caused WHERE cause = ? AND seq > ? ORDER BY seq LIMIT ?",
            (cause, after, _PAGE + 1),
        )
        total = self.db.execute("SELECT count(*) AS n FROM v_references_caused WHERE cause = ?", (cause,))
        return [row["seq"] for row in rows], total.fetchone()["n"]

    def children(self, sha: str) -> list[int]:
        """The seqs of the recorded commits that name a commit as a parent."""
        rows = self.db.execute("SELECT seq FROM v_references_parents WHERE sha = ? ORDER BY seq", (sha,))
        return [row["seq"] for row in rows]

    def anchored(self, agent: str, anchor: str) -> list[int]:
        """The seqs of an agent's events that came under one tool call's id."""
        rows = self.db.execute(
            "SELECT seq FROM v_references_anchors WHERE agent = ? AND anchor = ? ORDER BY seq", (agent, anchor)
        )
        return [row["seq"] for row in rows]

    def under_ids(self, agent: str) -> list[int]:
        """The seqs of an agent's events that came under any tool call's id, oldest first."""
        rows = self.db.execute("SELECT seq FROM v_references_anchors WHERE agent = ? ORDER BY seq", (agent,))
        return [row["seq"] for row in rows]


class Calls(View):
    """What each agent's harness reported of its model calls, by the id it gave each, of its tool items, by theirs,
    and where each of its turns began and who drove it."""

    schema = """
    CREATE TABLE v_calls(
        agent TEXT NOT NULL, call_id TEXT NOT NULL, seq INTEGER NOT NULL, PRIMARY KEY (agent, call_id)
    ) WITHOUT ROWID, STRICT;
    CREATE TABLE v_calls_items(
        agent TEXT NOT NULL, native_id TEXT NOT NULL, seq INTEGER NOT NULL, call_id TEXT, PRIMARY KEY (agent, native_id)
    ) WITHOUT ROWID, STRICT;
    CREATE TABLE v_calls_turns(
        agent TEXT NOT NULL, seq INTEGER NOT NULL, by TEXT, PRIMARY KEY (agent, seq)
    ) WITHOUT ROWID, STRICT;
    """

    @fold("model.called")
    def called(self, event: Event) -> None:
        if event.model is not None:
            self.db.execute(
                "INSERT OR IGNORE INTO v_calls VALUES (?, ?, ?)", (event.agent, event.model.call_id, event.seq)
            )

    @fold("item.recorded")
    def item(self, event: Event) -> None:
        """A tool item is found by its first report, and names the call its harness said made it in any report."""
        data = event.data
        if data["kind"] == "tool" and data["native_id"]:
            self.db.execute(
                """
                INSERT INTO v_calls_items VALUES (?, ?, ?, ?)
                ON CONFLICT DO UPDATE SET call_id = coalesce(call_id, excluded.call_id)
                """,
                (event.agent, data["native_id"], event.seq, data["call_id"]),
            )

    @fold("turn.started")
    def turn(self, event: Event) -> None:
        self.db.execute("INSERT INTO v_calls_turns VALUES (?, ?, ?)", (event.agent, event.seq, event.data.get("by")))

    def item_for(self, agent: str, native_id: str) -> sqlite3.Row | None:
        return self.db.execute(
            "SELECT * FROM v_calls_items WHERE agent = ? AND native_id = ?", (agent, native_id)
        ).fetchone()

    def call(self, agent: str, call_id: str) -> int | None:
        row = self.db.execute("SELECT seq FROM v_calls WHERE agent = ? AND call_id = ?", (agent, call_id)).fetchone()
        return None if row is None else row["seq"]

    def began(self, agent: str, upto: int) -> sqlite3.Row | None:
        """The start of an agent's latest turn at or below `upto`."""
        return self.db.execute(
            "SELECT * FROM v_calls_turns WHERE agent = ? AND seq <= ? ORDER BY seq DESC LIMIT 1", (agent, upto)
        ).fetchone()


# The answers.


class Bound(Model):
    """Where an answer stops counting: at the model `call` that chose its event, by that call's ref, on its agent's
    report stream; at the event's `commit` when no call is joined; at the `look` that recorded a git commit, which git
    made before it, at a time the record does not hold, so what counts may have come after that commit; or at the
    `head`. What lies below `seq` counts."""

    by: Literal["call", "commit", "look", "head"]
    seq: int
    call: str | None = None


class Anchor(Model):
    """The tool call a command came under: the `id` its client gave it under `key`, which says whose id that is, and
    how many of its agent's commands share it. Codex's `callId` names a Code Mode script, whose calls share it, so what
    such a call returned went to that script, however few ops share it."""

    key: str
    id: str
    ops: int


class Shown(Model):
    """What an offer showed of an event: its `ref`, with `#La-b` for the lines of its body, in one `form`."""

    ref: str
    form: Literal["gist", "body"]


class Confirmation(Model):
    """A harness's own report that it took an offer, recorded as the event `ref` at `seq`, in `turn`, with where it
    landed, the `evidence` and the harness's `native_id`."""

    ref: str
    seq: int
    turn: str | None
    boundary: str | None
    evidence: str | None
    native_id: str | None


class Mark(Model):
    """What a compaction since a confirmation did with what that offer handed over: `forgot` or `kept` it, by the id its
    harness reported delivering it under, or left it `unsaid`."""

    compaction: str
    mark: Literal["forgot", "kept", "unsaid"]


class Offer(Model):
    """One offer to an agent, which is an observed edge: the offer's `ref` and `seq`, `how` it was made, what it showed,
    the tool call it came under, and once its harness said it took it below the bound, that `confirmed` report, with a
    page of the compactions since as `compactions`, which ends at one that forgot what it handed over, and how many
    there are, `compacted`, up to that one when the page holds it. Those two are None where an answer does not ask."""

    kind: Literal["observed"] = "observed"
    ref: str
    seq: int
    how: str
    shown: tuple[Shown, ...]
    anchor: Anchor | None = None
    confirmed: Confirmation | None = None
    compactions: tuple[Mark, ...] | None = None
    compacted: int | None = None


class Incident(Model):
    """One incident gap: its `ref`, `what` it was, its `plane`, where it `began`, and whether content could reach its
    agent through it unseen, which makes it a reason that what the agent saw is unknown."""

    kind: Literal["gap"] = "gap"
    ref: str
    what: str
    plane: str
    began: int
    carries: bool


class Coverage(Model):
    """One surface, and what its agent's driver `declared` of it: `observed`, `partial`, `none`, or None for nothing."""

    surface: Surface
    declared: Literal["observed", "partial", "none"] | None


class Seen(Model):
    """The event reached the agent through us below the bound: `edges` holds a page of the offers of it its harness said
    it took there, `total` of them. Seen means handed over and taken, never understood: a read's result returned to
    its harness, or under a Codex `callId` to the Code Mode script that made the call."""

    answer: Literal["seen"] = "seen"
    edges: tuple[Offer, ...]
    total: int
    bound: Bound
    head: int
    open: bool


class NotSeen(Model):
    """Nothing offered the event to the agent below the bound, a stored conformance result proves every surface in
    `proved` observed, which is all of them, and no gap content could come through lies below it."""

    answer: Literal["not_seen"] = "not_seen"
    proved: tuple[Surface, ...]
    bound: Bound
    head: int
    open: bool


class Unknown(Model):
    """Whether the event reached the agent below the bound is not known, and these are why: the offers of it made below
    the bound that its harness had not said there it took, `handed`, empty when none was made through us below it; the
    surfaces no result proves observed, `standing`; the gaps content could have come through, `incidents`; and
    `older_offers`, from before offer payload 3, which named bodies by hash and announces by their own refs, so none can
    be tied to this event."""

    answer: Literal["unknown"] = "unknown"
    handed: tuple[Offer, ...]
    standing: tuple[Coverage, ...]
    incidents: tuple[Incident, ...]
    older_offers: int
    totals: dict[str, int]
    bound: Bound
    head: int
    open: bool


Exposure = Annotated[Seen | NotSeen | Unknown, Field(discriminator="answer")]
"""What `exposure` answers: never a boolean."""


class Node(Model):
    """An event as an answer names it."""

    ref: str
    seq: int
    type: str
    gist: str
    actor: str
    agent: str | None
    turn: str | None
    context_version: int | None
    episode: str | None


class Made(Model):
    """Who made an event: its `maker`, None for a commit nobody's workspace made alone, in `turn`, driven `by` a person
    holding the agent or by nobody, the model `call` that chose it, joined through the tool call it came under and the
    tool `item` holding that call's id, or for a harness's report of an item through the call that report names, and
    how its maker ran, from its latest start below: `assurance` and `levels`. For a tool item, `anchor` is its tool call
    as its agent's commands came under it, and `commands` names the first event of each, which is its own act, as many
    as a page holds, empty when none came under it; for any other event it is None."""

    maker: str | None
    turn: str | None
    by: str | None
    call: str | None
    anchor: Anchor | None
    item: str | None
    commands: tuple[str, ...] | None
    assurance: str | None
    levels: dict[str, Any] | None


class Declared(Model):
    """A citation, which is its citer's claim: the `ref` as cited, the cited event's `maker` and `gist`, the citer's
    `exposure` to it at the bound, None for a person's or a program's, whose reads are no evidence, and for a range
    whether those lines were shown, decided as exposure is: True when a confirmed offer showed them, False only beside
    `not_seen`, and None otherwise."""

    kind: Literal["declared"] = "declared"
    ref: str
    maker: str | None
    gist: str
    exposure: Exposure | None
    lines_shown: bool | None


class Step(Model):
    """An edge of one `kind` from the asked event to another, and that event: its `ref`, `seq`, `type`, `gist` and
    `maker`. A commit names its `sha`, and a parent the journal holds no record of has nothing else."""

    kind: Back
    ref: str | None
    seq: int | None = None
    type: str | None = None
    gist: str | None = None
    maker: str | None = None
    sha: str | None = None


class Unresolved(Model):
    """An `Informed-By` value of a commit as it was `written`, which its record cites nothing for, with the commit git
    resolved it to, if any, and `why`, as its look found it: it names a commit the journal held no record of,
    `unrecorded`; no event, `no_event`; no lines of its event's body, `no_lines`; or an event its commit's maker, an
    agent of the session, had neither made nor been handed, `unread`, as nobody else can be shown to have read one. A
    look before payload 2 looked for commits alone, so what it could not tie to one is `unchecked`."""

    written: str
    sha: str | None
    why: Uncited | Literal["unchecked"]


class Lineage(Model):
    """One hop back from an event: the `event`, who `made` it, what it `declared`, a commit's `unresolved` trailers and
    how many more it had than were kept (`cut`), each `cause`, its `ancestry`, its maker's `standing` coverage, and a
    page of what its maker was offered and the gaps in its record below the bound, `history`, newest first, with true
    `totals`. A maker that is no agent has no context, so those three are None."""

    event: Node
    made: Made
    declared: tuple[Declared, ...]
    unresolved: tuple[Unresolved, ...]
    cut: int
    cause: tuple[Step, ...]
    ancestry: tuple[Step, ...]
    standing: tuple[Coverage, ...] | None
    history: tuple[Annotated[Offer | Incident, Field(discriminator="kind")], ...] | None
    totals: dict[str, int] | None
    cursor: str | None
    bound: Bound
    head: int
    open: bool


class Handed(Model):
    """An agent an event was offered to: its first `offer` and that offer's `seq`, and whether its harness said it took
    any offer of it."""

    kind: Literal["observed"] = "observed"
    agent: str
    offer: str
    seq: int
    confirmed: bool


class Uses(Model):
    """One hop forward from an event, oldest first: what cites it, what follows from it, its next version or the
    commits that name it a parent, and each agent it was offered to, with true `totals` by kind."""

    rows: tuple[Annotated[Step | Handed, Field(discriminator="kind")], ...]
    totals: dict[str, int]
    cursor: str | None
    head: int
    open: bool


class Contributor(Model):
    """A maker the walk back from an outcome reached: the edge `kinds` that reached its events, how many it `reached`,
    the `first`, at `hops` from the outcome, and its gaps below the last: the surfaces no result proves observed, None
    for a maker with no harness, and how many gaps content could come through began there, by kind."""

    maker: str | None
    kinds: tuple[Back, ...]
    reached: int
    first: str
    hops: int
    unproved: tuple[Surface, ...] | None
    incidents: dict[str, int]


class HandedOnly(Model):
    """A maker whose events were only offered to makers the walk reached, never reached by it: whom they were handed
    `to`, and the `first` offer."""

    maker: str | None
    to: tuple[str, ...]
    first: str


class Contributors(Model):
    """Each maker a walk back from an outcome along citations, causes and ancestry reaches, in the order it reached
    them, the outcome's own first, and apart from them each maker whose work was only handed to one of them. It walks
    at most 4096 events, `walked` of them, and says when it `stopped_short`. It is reachability in the record and never
    credit: nobody is weighed or ranked."""

    rows: tuple[Contributor, ...]
    handed_only: tuple[HandedOnly, ...]
    walked: int
    stopped_short: bool
    cursor: str | None
    head: int
    open: bool


class Span(Model):
    """A stretch of one turn of an agent, named by `ref`, the `model.called` of its last call, which a credit row about
    it targets: its calls are those its harness reported on its turn stream from `first` to `ref`, in the turn named
    `turn`, and `writes` are the writes of content the record ties to them, which one of them chose."""

    ref: str
    first: str
    turn: str
    writes: tuple[str, ...]


class Spans(Model):
    """Each span of an agent, oldest first: a page of them, `total` in all, with `cursor` to pass as `after` for the
    next page, `open` while its latest turn has not ended, as a late report can still join a write to a call and cut
    that turn again, and `head` where the record was read."""

    agent: str
    spans: tuple[Span, ...]
    total: int
    cursor: str | None
    head: int
    open: bool


# Deciding exposure.


class Facts(NamedTuple):
    """What exposure is decided from, below one bound, each list a page with its count beside it: the offers of the
    event its harness said it took, `edges`, `confirmed` of them, and those it did not, `handed`, `unconfirmed` of
    them; each surface as its driver declared it; the gaps content could come through, newest first, `gaps` of them;
    and how many offers came before payload 3."""

    edges: Sequence[Offer]
    confirmed: int
    handed: Sequence[Offer]
    unconfirmed: int
    standing: Sequence[Coverage]
    incidents: Sequence[Incident]
    gaps: int
    older_offers: int


def decide(
    facts: Facts, *, proved: Collection[Surface], bound: Bound, head: int, open: bool
) -> Seen | NotSeen | Unknown:
    """The one rule: `Seen` on any offer its harness took below the bound; `NotSeen` only when nothing offered it there,
    every surface is in `proved` and no gap content could come through lies below the bound; `Unknown` otherwise, with
    every reason. No check proves a surface yet, so the queries pass none, and nothing answers `NotSeen`."""
    if facts.confirmed:
        return Seen(edges=tuple(facts.edges[:_PAGE]), total=facts.confirmed, bound=bound, head=head, open=open)
    unproved = tuple(coverage for coverage in facts.standing if coverage.surface not in proved)
    if not (facts.unconfirmed or unproved or facts.gaps or facts.older_offers):
        return NotSeen(
            proved=tuple(surface for surface in _SURFACES if surface in proved), bound=bound, head=head, open=open
        )
    return Unknown(
        handed=tuple(facts.handed[:_PAGE]),
        standing=unproved,
        incidents=tuple(facts.incidents[:_PAGE]),
        older_offers=facts.older_offers,
        totals={"handed": facts.unconfirmed, "incidents": facts.gaps},
        bound=bound,
        head=head,
        open=open,
    )


# Reading the record.


class Join(NamedTuple):
    """How an event reaches the model call that chose it: the tool call it came under, the tool item holding that
    call's id, and the call that item names, each None where the records hold no id to join by; and for a tool item,
    the commands its agent made under its id, or None for any other event."""

    anchor: Anchor | None
    item: Event | None
    call: Event | None
    commands: Sequence[Event] | None = None


def _asked(txn: Txn, ref: str) -> Event:
    """The event a query asks about. A body's hash names bytes, and a range lines of a body: neither is an event."""
    if ref.startswith("sha256:"):
        raise Refused("invalid", "a body's hash names bytes and no event: ask by the ref of the event that carries it")
    parts = parts_of(ref)
    if parts is None:
        raise Refused("invalid", f"{ref[:80]!r} is no ref, which is `stream@version`")
    stream, version, lines = parts
    if lines is not None:
        raise Refused(
            "invalid", f"these ask about events, and {ref[:80]} names lines of one: ask by {stream}@{version}"
        )
    event = txn.view(Stamps).at(stream, version)
    if event is None:
        raise Refused("not_found", f"nothing is {ref[:80]}")
    return event


def _agent_of(made_by: str | None) -> str | None:
    """The agent a maker is, or None for a person, a program, the runtime or nobody."""
    return name_of(made_by) if made_by is not None and made_by.startswith("agent:") else None


def _commands(txn: Txn, agent: str, anchor: str) -> list[Event]:
    """Each of an agent's commands under one tool call's id, by its first event, which is its own act: a command's
    events are written together, and the last of them holds its outcome."""
    stamps, firsts, starting = txn.view(Stamps), [], True
    for seq in txn.view(References).anchored(agent, anchor):
        found = _at(stamps, seq)
        if starting:
            firsts.append(found)
        starting = found.outcome is not None
    return firsts


def _join(txn: Txn, event: Event) -> Join:
    """The join through ids both records hold: the op's anchor equal to a tool item's `native_id`, and that item's
    `call_id`. A harness's report of an item is joined by its own ids. Anything else joins nothing."""
    if event.type == "item.recorded" and event.agent is not None:
        return _reported(txn, event.agent, event.data)
    if not event.native or not event.actor.startswith("agent:"):
        return Join(None, None, None)
    agent, stamps, calls = name_of(event.actor), txn.view(Stamps), txn.view(Calls)
    key, id = next(iter(event.native.items()))
    item = calls.item_for(agent, id)
    called = None if item is None or item["call_id"] is None else calls.call(agent, item["call_id"])
    return Join(
        Anchor(key=key, id=id, ops=len(_commands(txn, agent, id))),
        None if item is None else stamps.event(item["seq"]),
        None if called is None else stamps.event(called),
    )


def _reported(txn: Txn, agent: str, item: Mapping[str, Any]) -> Join:
    """An item as its harness reported it: the call its reports name, and for a tool item the commands its agent made
    under its `native_id`, each under the anchor that names it."""
    calls, native_id = txn.view(Calls), item["native_id"]
    first = calls.item_for(agent, native_id) if native_id else None
    call_id = item["call_id"] if first is None else first["call_id"]
    called = None if call_id is None else calls.call(agent, call_id)
    commands = _commands(txn, agent, native_id) if item["kind"] == "tool" and native_id else []
    anchor = Anchor(key=next(iter(commands[0].native)), id=native_id, ops=len(commands)) if commands else None
    call = None if called is None else txn.view(Stamps).event(called)
    return Join(anchor, None, call, commands if item["kind"] == "tool" else None)


def _bound(event: Event, join: Join, agent: str | None) -> Bound:
    """Where what an agent was handed stops counting for an event: below the model call that chose it, when the event
    is the agent's and its call is joined, as the two are reports on one ordered stream, and else below its commit, or
    for a git commit below the look that recorded it."""
    if join.call is not None and agent is not None and maker(event) == f"agent:{agent}":
        return Bound(by="call", seq=join.call.seq, call=_ref(join.call))
    return Bound(by="look" if event.type == "repo.committed" else "commit", seq=event.seq)


def _open(txn: Txn, event: Event | None, agent: str | None = None) -> bool:
    """Whether the turn an event was made in had not ended at the head, or with no event whether `agent` is in a turn,
    since a later report can still confirm an offer or join a call."""
    if event is None:
        return agent is not None and txn.view(Stamps).turn(agent) is not None
    if event.turn is None or event.agent is None:
        return False
    began = txn.view(Calls).began(event.agent, event.seq)
    return began is not None and began["seq"] == txn.view(Stamps).began(event.agent)


def _forgotten(txn: Txn, ref: str | None) -> frozenset[str] | None:
    """The ids a compaction named as forgotten, or None when it named none, or they cannot be read here."""
    data = None if ref is None else inline_body(txn, ref)
    try:
        listed = None if data is None else json.loads(data)
    except ValueError:
        return None
    return frozenset(map(str, listed)) if isinstance(listed, list) else None


Forgetting = Callable[[str | None], frozenset[str] | None]
"""What each compaction named as forgotten, by its record, read once for one answer however many offers ask."""


def _marks(
    txn: Txn, agent: str, confirmed: Confirmation, bound: Bound, forgetting: Forgetting
) -> tuple[tuple[Mark, ...], int]:
    """The compactions since a confirmation below the bound, up to the one that forgot what it handed over, as many as
    a page holds, and how many. Only an input its harness reported delivering under an id can be named forgotten or
    kept, so a read's, confirmed by its tool item, is unsaid."""
    rows, total = txn.view(Exposures).compactions(agent, confirmed.seq, bound.seq)
    by_id = confirmed.evidence != "tool_item" and confirmed.native_id is not None
    marks = []
    for row in rows:
        forgotten = forgetting(row["forgotten"]) if by_id else None
        mark = "unsaid" if forgotten is None else "forgot" if confirmed.native_id in forgotten else "kept"
        marks.append(Mark(compaction=row["ref"], mark=mark))
        if mark == "forgot":
            return tuple(marks), len(marks)
    return tuple(marks), total


def _offer(
    txn: Txn, row: sqlite3.Row, shown: Sequence[sqlite3.Row], bound: Bound, forgetting: Forgetting | None = None
) -> Offer:
    """An offer as an answer shows it, and with `forgetting` the compactions since it was confirmed."""
    anchor = None
    if row["key"] is not None:
        anchor = Anchor(key=row["key"], id=row["anchor"], ops=len(_commands(txn, row["agent"], row["anchor"])))
    confirmed = None
    if row["confirmed"] is not None:
        fields = ("turn", "boundary", "evidence", "native_id")
        confirmed = Confirmation(ref=row["confirmed"], seq=row["confirmed_seq"], **{key: row[key] for key in fields})
    marks, compacted = None, None
    if forgetting is not None:
        marks, compacted = ((), 0) if confirmed is None else _marks(txn, row["agent"], confirmed, bound, forgetting)
    return Offer(
        ref=row["ref"],
        seq=row["offer"],
        how=row["how"],
        shown=tuple(Shown(ref=item["ref"], form=item["form"]) for item in shown),
        anchor=anchor,
        confirmed=confirmed,
        compactions=marks,
        compacted=compacted,
    )


def _standing(txn: Txn, agent: str, bound: Bound) -> tuple[Coverage, ...]:
    """Every surface, as the driver of the agent's latest start below the bound declared it."""
    start = txn.view(Exposures).start(agent, bound.seq)
    declared = {} if start is None else json.loads(start["coverage"])
    return tuple(Coverage(surface=surface, declared=declared.get(surface)) for surface in _SURFACES)


def _incident(txn: Txn, row: sqlite3.Row) -> Incident:
    event = txn.view(Stamps).event(row["seq"])
    assert event is not None
    kind = GAPS.get(row["what"])  # One outside the closed set is taken as one content could come through.
    carries = kind is None or kind.carries
    return Incident(ref=_ref(event), what=row["what"], plane=row["plane"], began=row["began"], carries=carries)


def _facts(txn: Txn, agent: str, event: Event, bound: Bound) -> Facts:
    exposures = txn.view(Exposures)
    forgetting = cache(partial(_forgotten, txn))

    def offers(confirmed: bool) -> tuple[list[Offer], int]:
        rows, total = exposures.offers_of(agent, event.stream, event.version, bound.seq, confirmed=confirmed)
        found = [(row, exposures.shown(row["offer"], event.stream, event.version)) for row in rows]
        return [_offer(txn, row, shown, bound, forgetting) for row, shown in found], total

    edges, confirmed = offers(True)
    handed, unconfirmed = offers(False)
    rows, gaps = txn.view(Gaps).below(agent, bound.seq, besides=_UNCARRIED)
    incidents = [_incident(txn, row) for row in rows]
    standing, older = _standing(txn, agent, bound), exposures.older(agent, bound.seq)
    return Facts(edges, confirmed, handed, unconfirmed, standing, incidents, gaps, older)


def _exposed(txn: Txn, agent: str, event: Event, bound: Bound, open: bool) -> tuple[Seen | NotSeen | Unknown, Facts]:
    facts = _facts(txn, agent, event, bound)
    return decide(facts, proved=(), bound=bound, head=txn.view(Stamps).head(), open=open), facts


def _step(kind: Back, event: Event) -> Step:
    return Step(kind=kind, ref=_ref(event), seq=event.seq, type=event.type, gist=event.gist, maker=maker(event))


def _ancestor(event: Event | str) -> Step:
    """An ancestor as a step: a version, a recorded commit with its sha, or a commit's sha alone."""
    if isinstance(event, str):
        return Step(kind="ancestry", ref=None, sha=event)
    sha = event.data["sha"] if event.type == "repo.committed" else None
    return _step("ancestry", event).model_copy(update={"sha": sha})


def _back(txn: Txn, event: Event) -> Iterator[tuple[Back, Event | str]]:
    """The edges that lead back from an event, of each kind: what it cites, what it followed from, and its previous
    version or, for a commit, each parent, by its record or by its sha when the journal holds none. Every reference
    points backward, so each names an event."""
    stamps = txn.view(Stamps)
    for ref in event.based_on:
        yield "declared", _held(event_at(txn, ref))
    for seq in event.cause:
        yield "cause", _held(stamps.event(seq))
    if event.type == "repo.committed":
        looks = txn.view(Looks)
        for sha in event.data["parents"]:
            ref = looks.ref(sha)
            yield "ancestry", sha if ref is None else _held(event_at(txn, ref))
    elif _versioned(event) and event.version > 1:
        yield "ancestry", _held(stamps.at(event.stream, event.version - 1))


def _held(event: Event | None) -> Event:
    assert event is not None  # A reference points backward to an event the journal holds (law 7).
    return event


def _node(event: Event) -> Node:
    fields = ("seq", "type", "gist", "actor", "agent", "turn", "context_version", "episode")
    return Node(ref=_ref(event), **{field: getattr(event, field) for field in fields})


def _covers(shown: str, wanted: str) -> bool:
    """Whether the lines one item of an offer showed hold the lines a range names: a whole body holds every line."""
    parts = parts_of(shown)
    held = None if parts is None else parts[2]
    if held is None:
        return True
    first, last = (int(n) for n in held.removeprefix("L").split("-"))
    wanted_first, wanted_last = (int(n) for n in wanted.removeprefix("L").split("-"))
    return first <= wanted_first and wanted_last <= last


def _declared(txn: Txn, ref: str, citer: str | None, bound: Bound, open: bool) -> Declared:
    cited = event_at(txn, ref)
    assert cited is not None  # A citation names an existing event, or its write was refused (law 7).
    if citer is None:
        return Declared(ref=ref, maker=maker(cited), gist=cited.gist, exposure=None, lines_shown=None)
    answer, facts = _exposed(txn, citer, cited, bound, open)
    wanted = (parts_of(ref) or ("", 0, None))[2]
    lines = None
    if wanted is not None:
        held = [item.ref for edge in facts.edges for item in edge.shown if item.form == "body"]
        covered = any(_covers(shown, wanted) for shown in held)
        lines = True if covered else False if isinstance(answer, NotSeen) else None
    return Declared(ref=ref, maker=maker(cited), gist=cited.gist, exposure=answer, lines_shown=lines)


def _position(cursor: str | None) -> tuple[int, int] | None:
    """A cursor's position, `<seq>:<n>`, or None for none."""
    if cursor is None:
        return None
    seq, colon, n = cursor.partition(":")
    if not (colon and seq.isdecimal() and n.isdecimal()):
        raise Refused("invalid", "`after` is a `cursor` from an earlier answer")
    return int(seq), int(n)


def _history(
    txn: Txn, agent: str, bound: Bound, after: str | None
) -> tuple[tuple[Offer | Incident, ...], dict[str, int], str | None]:
    """A page of what an agent was offered and the gaps in its record below the bound, newest first, by the offer's seq
    and by where a gap began, and the true totals."""
    exposures = txn.view(Exposures)
    before = _position(after) or (bound.seq, 0)
    rows: list[tuple[tuple[int, int], Offer | Incident]] = [
        ((row["offer"], 0), _offer(txn, row, exposures.shown(row["offer"]), bound))
        for row in exposures.history(agent, bound.seq, before[0])
    ]
    gaps, total = txn.view(Gaps).below(agent, bound.seq, before=before)
    rows += [((row["began"], row["seq"]), _incident(txn, row)) for row in gaps]
    rows.sort(key=lambda row: row[0], reverse=True)
    page = rows[:_PAGE]
    cursor = f"{page[-1][0][0]}:{page[-1][0][1]}" if len(rows) > _PAGE else None
    handed, confirmed = exposures.counts(agent, bound.seq)
    totals = {"handed": handed, "confirmed": confirmed, "unconfirmed": handed - confirmed, "gaps": total}
    return tuple(row for _, row in page), totals, cursor


def _unresolved(txn: Txn, event: Event) -> tuple[Unresolved, ...]:
    """A commit's `Informed-By` values that cite nothing, each with why, as its record keeps them."""
    if event.type != "repo.committed":
        return ()
    if event.v >= 2:
        return tuple(Unresolved.model_validate(value) for value in event.data["informed_by"] if value["why"])
    looks, cited = txn.view(Looks), set(event.based_on)
    return tuple(
        Unresolved(written=value["written"], sha=value["sha"], why="unrecorded" if value["sha"] else "unchecked")
        for value in event.data["informed_by"]
        if (looks.ref(value["sha"]) if value["sha"] else value["written"]) not in cited
    )


# The queries.


class Asked(Args):
    ref: Annotated[str, Field(max_length=1024, description="An event's ref, `stream@version`.")]
    after: Annotated[str | None, Field(max_length=64, description="A `cursor` from an earlier answer.")] = None


class AskedOf(Args):
    agent: Annotated[AgentName, Field(description="The agent, as `@agent`.")]
    ref: Annotated[str, Field(max_length=1024, description="An event's ref, `stream@version`.")]
    before: Annotated[
        str | None,
        Field(max_length=1024, description="The ref of the event the answer stops before. Left out, the head."),
    ] = None


@op("exposure", query=True)
def exposure(txn: Txn, a: AskedOf) -> Seen | NotSeen | Unknown:
    """Say whether an event reached an agent through us before another, `before`, or by now: `seen`, with each offer of
    it its harness said it took and each compaction since, `not_seen`, or `unknown`, with the offers its harness had not
    said it took by then, the surfaces no result proves observed and the gaps content could have come through. Seen
    means handed over and taken, never understood, and an agent with a shell never answers `not_seen`. Refused `invalid`
    for a range or a body's hash, which name no event, and for a person or a program, whose reads are no evidence, and
    `not_found` when no such event or agent exists."""
    if txn.view(Agents).get(a.agent) is None:
        found = txn.view(Principals).named(a.agent)
        if found is not None:
            raise Refused("invalid", f"{a.agent} is a {found.kind}, whose reading is no evidence, and has no exposure")
        raise Refused("not_found", f"no agent {a.agent}")
    event = _asked(txn, a.ref)
    if a.before is None:
        head = txn.view(Stamps).head()
        bound, open = Bound(by="head", seq=head + 1), _open(txn, None, a.agent)
    else:
        bounding = _asked(txn, a.before)
        bound, open = _bound(bounding, _join(txn, bounding), a.agent), _open(txn, bounding)
    return _exposed(txn, a.agent, event, bound, open)[0]


@op("lineage", query=True)
def lineage(txn: Txn, a: Asked) -> Lineage:
    """Show one hop back from an event: who made it, in which turn and model call, what it cites, each with its citer's
    exposure, what it followed from, its previous version or a commit's parents, and a page of what its maker was
    offered and the gaps in its record below it, newest first, with true totals. Pass `cursor` as `after` for the next
    page. Refused `invalid` for a range or a body's hash, which name no event, and `not_found` for no such event."""
    event = _asked(txn, a.ref)
    join = _join(txn, event)
    made_by = maker(event)
    agent = _agent_of(made_by)
    bound = _bound(event, join, agent)
    open = _open(txn, event)
    start = None if agent is None else txn.view(Exposures).start(agent, bound.seq)
    began = None if event.turn is None or event.agent is None else txn.view(Calls).began(event.agent, event.seq)
    made = Made(
        maker=made_by,
        turn=event.turn,
        by=None if began is None else began["by"],
        call=None if join.call is None else _ref(join.call),
        anchor=join.anchor,
        item=None if join.item is None else _ref(join.item),
        commands=None if join.commands is None else tuple(_ref(found) for found in join.commands[:_PAGE]),
        assurance=None if start is None else start["assurance"],
        levels=None if start is None else json.loads(start["levels"]),
    )
    history, totals, cursor = _history(txn, agent, bound, a.after) if agent is not None else (None, None, None)
    back = list(_back(txn, event))
    commit = event.type == "repo.committed"
    return Lineage(
        event=_node(event),
        made=made,
        declared=tuple(_declared(txn, ref, agent, bound, open) for ref in event.based_on),
        unresolved=_unresolved(txn, event),
        cut=event.data["informed_by_total"] - len(event.data["informed_by"]) if commit else 0,
        cause=tuple(_step("cause", found) for kind, found in back if kind == "cause" and isinstance(found, Event)),
        ancestry=tuple(_ancestor(found) for kind, found in back if kind == "ancestry"),
        standing=None if agent is None else _standing(txn, agent, bound),
        history=history,
        totals=totals,
        cursor=cursor,
        bound=bound,
        head=txn.view(Stamps).head(),
        open=open,
    )


@op("uses", query=True)
def uses(txn: Txn, a: Asked) -> Uses:
    """Show one hop forward from an event, oldest first: what cites it, what follows from it, its next version or the
    commits that name it a parent, and each agent it was offered to, with whether its harness said it took it, and
    true totals. Pass `cursor` as `after` for the next page. Refused `invalid` for a range or a body's hash, which name
    no event, and `not_found` for no such event."""
    event = _asked(txn, a.ref)
    stamps, references, exposures = txn.view(Stamps), txn.view(References), txn.view(Exposures)
    after = _position(a.after) or (0, -1)
    citing, cited = references.citing(event.stream, event.version, after[0] - 1)
    following, caused = references.caused(event.seq, after[0] - 1)
    later = (
        [_at(stamps, seq) for seq in references.children(event.data["sha"])] if event.type == "repo.committed" else []
    )
    if _versioned(event) and (next_version := stamps.at(event.stream, event.version + 1)) is not None:
        later.append(next_version)
    offered = exposures.readers(event.stream, event.version)
    found: list[tuple[tuple[int, int], Step | Handed]] = [
        *(((seq, 0), _step("declared", _at(stamps, seq))) for seq in citing),
        *(((seq, 1), _step("cause", _at(stamps, seq))) for seq in following),
        *(((version.seq, 2), _ancestor(version)) for version in later),
        *(
            (
                (row["offer"], 3),
                Handed(
                    agent=row["agent"],
                    offer=exposures.ref_of(row["offer"]),
                    seq=row["offer"],
                    confirmed=bool(row["confirmed"]),
                ),
            )
            for row in offered
        ),
    ]
    rows = sorted((row for row in found if row[0] > after), key=lambda row: row[0])
    page = rows[:_PAGE]
    more = len(rows) > _PAGE or len(citing) > _PAGE or len(following) > _PAGE
    return Uses(
        rows=tuple(row for _, row in page),
        totals={"declared": cited, "cause": caused, "ancestry": len(later), "observed": len(offered)},
        cursor=f"{page[-1][0][0]}:{page[-1][0][1]}" if more and page else None,
        head=stamps.head(),
        open=_open(txn, event),
    )


def _at(stamps: Stamps, seq: int) -> Event:
    found = stamps.event(seq)
    assert found is not None  # The views fold only what the journal holds.
    return found


@op("contributors", query=True)
def contributors(txn: Txn, a: Asked) -> Contributors:
    """Name each maker a walk back from an outcome reaches along citations, causes and ancestry, in the order it reached
    them, with the kinds that reached each and the gaps on the way, and apart from them each maker whose work was only
    handed to one of them, which the walk does not go through. It walks at most 4096 events and says when it stopped
    short. It weighs and ranks nobody: credit is an annotation. Pass `cursor` as `after` for the next page. Refused
    `invalid` for a range or a body's hash, which name no event, and `not_found` for no such event."""
    outcome = _asked(txn, a.ref)
    reached, stopped_short = _walk(txn, outcome)
    makers: dict[str | None, dict[str, Any]] = {}
    for event, hops, kinds in reached:
        found = makers.setdefault(
            maker(event), {"kinds": set(), "reached": 0, "first": _ref(event), "hops": hops, "last": event.seq}
        )
        found["kinds"] |= kinds
        found["reached"] += 1
        found["last"] = max(found["last"], event.seq)
    start = _position(a.after) or (0, 0)
    listed = list(makers.items())
    page = listed[start[0] : start[0] + _PAGE]
    return Contributors(
        rows=tuple(_contributor(txn, made_by, found) for made_by, found in page),
        handed_only=_handed_only(txn, makers),
        walked=len(reached),
        stopped_short=stopped_short,
        cursor=f"{start[0] + _PAGE}:0" if start[0] + _PAGE < len(listed) else None,
        head=txn.view(Stamps).head(),
        open=_open(txn, outcome),
    )


def _walk(txn: Txn, outcome: Event) -> tuple[list[tuple[Event, int, set[Back]]], bool]:
    """Every event a walk back from `outcome` reaches, breadth first, each with its hops and the kinds of edge that
    reached it, and whether it stopped at its limit with more to reach. A commit's parent with no record ends a path."""
    hops: dict[int, int] = {outcome.seq: 0}
    kinds: dict[int, set[Back]] = {outcome.seq: set()}
    order, queue = [outcome], deque([outcome])
    while queue:
        event = queue.popleft()
        for kind, found in _back(txn, event):
            if isinstance(found, str):
                continue
            if found.seq in hops:
                kinds[found.seq].add(kind)
                continue
            if len(order) == WALK_LIMIT:
                return [(found, hops[found.seq], kinds[found.seq]) for found in order], True
            hops[found.seq], kinds[found.seq] = hops[event.seq] + 1, {kind}
            order.append(found)
            queue.append(found)
    return [(found, hops[found.seq], kinds[found.seq]) for found in order], False


def _contributor(txn: Txn, made_by: str | None, found: dict[str, Any]) -> Contributor:
    agent = _agent_of(made_by)
    bound = Bound(by="commit", seq=found["last"] + 1)
    unproved = None if agent is None else tuple(coverage.surface for coverage in _standing(txn, agent, bound))
    incidents = {} if agent is None else txn.view(Gaps).counted(agent, bound.seq, besides=_UNCARRIED)
    return Contributor(
        maker=made_by,
        kinds=tuple(kind for kind in get_args(Back) if kind in found["kinds"]),
        reached=found["reached"],
        first=found["first"],
        hops=found["hops"],
        unproved=unproved,
        incidents=incidents,
    )


def _handed_only(txn: Txn, makers: dict[str | None, dict[str, Any]]) -> tuple[HandedOnly, ...]:
    """Each maker whose events were offered to an agent the walk reached, below the last of its reached events, and
    that the walk did not reach, with the first such offer. A fold sees one event, so no view holds an offered event's
    maker: each is read by its ref, once for one answer however many agents it was offered to."""
    stamps, exposures = txn.view(Stamps), txn.view(Exposures)
    made = cache(lambda stream, version: maker(_held(stamps.at(stream, version))))
    handed: dict[str | None, tuple[set[str], int]] = {}
    for made_by, found in makers.items():
        if (agent := _agent_of(made_by)) is None:
            continue
        for row in exposures.events_offered(agent, found["last"] + 1):
            who = made(row["stream"], row["version"])
            if who not in makers:
                to, first = handed.get(who, (set(), row["offer"]))
                handed[who] = (to | {f"agent:{agent}"}, min(first, row["offer"]))
    ordered = sorted(handed.items(), key=lambda entry: entry[1][1])
    return tuple(
        HandedOnly(maker=who, to=tuple(sorted(to)), first=exposures.ref_of(first)) for who, (to, first) in ordered
    )


# Spans.


class OfAgent(Args):
    agent: Annotated[AgentName, Field(description="The agent, as `@agent`.")]
    after: Annotated[str | None, Field(max_length=64, description="A `cursor` from an earlier answer.")] = None


def _written(event: Event, agent: str) -> bool:
    """Whether an event of an agent's own command holds one of its writes of content: its own end, for an
    `agent.finish` out of a turn, and no entry that carries another event, as an announce of a write does."""
    if event.type == "agent.ended":
        return event.stream == f"agent/{agent}" and event.data["status"] == "finished"
    return event.type in _WRITES and not (event.type == "message.sent" and event.data.get("carries"))


def _turns(txn: Txn, agent: str) -> list[tuple[str, list[Event]]]:
    """Each turn of an agent, by its name, with the model calls its harness reported in it, in the order reported. A
    call reported out of any turn lies in none."""
    turns: list[tuple[str, list[Event]]] = []
    calls: list[Event] | None = None
    for event in txn.view(Stamps).events(f"turn/{agent}"):
        if event.type == "turn.started":
            calls = []
            turns.append((event.data["turn"], calls))
        elif event.type in ("turn.ended", "turn.lost"):
            calls = None
        elif event.type == "model.called" and calls is not None:
            calls.append(event)
    return turns


def _cut(turn: str, calls: Sequence[Event], chose: Mapping[int, Sequence[str]]) -> list[tuple[int, Span]]:
    """A turn's spans, each with the seq of its last call: cut after each call that chose a write, but the last, whose
    span runs on to the turn's end. A turn with no call has none."""
    if not calls:
        return []
    cuts = [index for index, call in enumerate(calls) if call.seq in chose][:-1]
    found, first = [], 0
    for last in (*cuts, len(calls) - 1):
        writes = tuple(ref for call in calls[first : last + 1] for ref in chose.get(call.seq, ()))
        span = Span(ref=_ref(calls[last]), first=_ref(calls[first]), turn=turn, writes=writes)
        found.append((calls[last].seq, span))
        first = last + 1
    return found


@op("spans", query=True)
def spans(txn: Txn, a: OfAgent) -> Spans:
    """Cut each turn of an agent into spans, oldest first: a turn is cut after each model call that chose a write of
    content, as the tool call id its op came under and the tool item holding that id join them, and a trailing piece
    with no write joins the span before it, so each call its harness reported in a turn lies in one span. Each is named
    by its last call's `model.called`, with its first call, its turn and the writes the record ties to its calls. Pass
    `cursor` as `after` for the next page. Refused `invalid` for a person or a program, whose turns no harness reports,
    and `not_found` for no such agent."""
    if txn.view(Agents).get(a.agent) is None:
        found = txn.view(Principals).named(a.agent)
        if found is not None:
            raise Refused("invalid", f"{a.agent} is a {found.kind}, whose turns no harness reports")
        raise Refused("not_found", f"no agent {a.agent}")
    if a.after is not None and not a.after.isdecimal():
        raise Refused("invalid", "`after` is a `cursor` from an earlier answer")
    stamps, chose = txn.view(Stamps), defaultdict[int, list[str]](list)
    for seq in txn.view(References).under_ids(a.agent):
        event = _at(stamps, seq)
        if _written(event, a.agent) and (call := _join(txn, event).call) is not None:
            chose[call.seq].append(_ref(event))
    cut = [span for turn, calls in _turns(txn, a.agent) for span in _cut(turn, calls, chose)]
    page = [(seq, span) for seq, span in cut if seq > int(a.after or 0)][:_PAGE]
    return Spans(
        agent=a.agent,
        spans=tuple(span for _, span in page),
        total=len(cut),
        cursor=str(page[-1][0]) if page and page[-1][0] != cut[-1][0] else None,
        head=stamps.head(),
        open=stamps.turn(a.agent) is not None,
    )
