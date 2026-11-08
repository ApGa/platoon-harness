# RFC 0067: Who reached whom is counted from the record, kind by kind

| | |
|---|---|
| Status | Draft |
| Created | 2026-11-08 |
| Authors | Apurva Gandhi (`ApGa`) |
| Builds on | [`primitives/provenance.py`](../../packages/sdk/src/platoon_harness/primitives/provenance.py), [architecture section 11](../architecture.md#11-provenance), [the brief's section 6](../spec/BRIEF.md#6-provenance-is-a-first-class-protocol-feature), [RFC 0010](0010-provenance.md), [RFC 0038](0038-provenance-is-answered-from-the-record.md) and [RFC 0043](0043-a-person-follows-provenance-from-where-they-read.md) |
| Discussion | Milestone 4's plan and the critiques of its first draft, kept outside this repository |
| Implementation | `feat: Count who reached whom from the record, kind by kind, at a head`; step 2, `feat: Draw who reached whom in the terminal's provenance panel` |

## Summary

`interactions`, a query op that is no agent's tool, with `Session.interactions` and the command `interactions`, answers from the
record who reached whom: each ordered pair of makers, an agent, a person, a program, the runtime or nobody the record names, with
how many edges of each kind lead from the first's events to the second's. A `declared` edge is a citation, an `observed` one an
offer whose harness said it took it, a `cause` a cause an event names, and `ancestry` an object's next version or a commit's
parent. Each kind is counted apart and nothing sums them. The offers no harness has said it took are counted beside them as
unknown, and each agent is named with why what reached it is unknown. The answer is read at a head, a page of pairs and a page of
agents at a time, and every page of one answer is read at that head. Nothing is stored: each page walks the journal to its head.

## Motivation

The brief asks for the agent interaction graph apart from the time-expanded dependency graph
([section 6](../spec/BRIEF.md#6-provenance-is-a-first-class-protocol-feature)): A's post reaches B, whose answer reaches A, which
is a cycle between agents, while every reference in the record points back (law 7). [Architecture section
11](../architecture.md#11-provenance) names the graph as the quotient by agent and plans it for milestone 4, and until then the
clients show one event's hop at a time. Nothing answers it today. `lineage` and `uses` are one hop from one event, and
`contributors` walks back from one outcome ([RFC 0038](0038-provenance-is-answered-from-the-record.md)). Nobody can ask who
reached whom across a session, and a client may not walk the record to find out (section 12).

The danger is overstatement. Folding events into agents can turn one claimed citation into what reads as a fact about two
agents, and a pair the record holds no edge between can read as two agents who never reached each other, though any harness
with a shell reads what we never see. So each edge must keep how it is known, and unknown must not read as no edge.

## Proposal

### 1. A query, as the other provenance queries are

```python
class Pair(Model):
    who: str | None      # whose events reached,
    whom: str | None     # whose events rest on them
    declared: int        # citations, which their citers claim
    observed: int        # offers whose harness said it took them
    cause: int           # causes an event names
    ancestry: int        # an object's next versions, and commits naming a commit their parent
    unconfirmed: int     # offers whose harness had not said it took them: unknown
    first: dict[str, str]  # by count, the event holding the first edge of each the record learned

class Unknowns(Model):
    agent: str
    unproved: tuple[Surface, ...]  # the surfaces no result proves observed
    incidents: dict[str, int]      # gaps content could come through, by kind
    older_offers: int              # offers before payload 3, which no event can be tied to

class Interactions(Model):
    pairs: tuple[Pair, ...]        # a page, oldest first
    total: int
    unknowns: tuple[Unknowns, ...] # a page of the agents spawned by the head
    cursor: str | None             # `<head>:<n>`
    head: int
    open: bool

@op("interactions", query=True)
def interactions(txn: Txn, a: Paging) -> Interactions: ...
```

It is a query op with no tool, as `exposure`, `lineage`, `uses`, `contributors`, `eligibility` and `spans` are: a person or a
program reads it, on a view credential too, and it writes nothing. It reads the journal alone and never an annotation, so it
answers alike after a rebuild and on a closed copy. `Session.interactions(*, after=None)` and `platoon-harness interactions
SESSION` reach it, as they reach every op a person may run.

### 2. A pair is two makers

A pair names whose events reached, `who`, and whose events rest on them, `whom`, each as `maker` names it: an agent, a person, a
program, or the runtime for an event it wrote about no agent. None is nobody the record names, as for a commit no single
workspace made, and is no one maker, so an edge between two such commits is counted under nobody on both sides. A maker's events
that rest on its own are its history, which `lineage` and `spans` show, and pair it with nobody. A pair is directed: A reached B
and B reached A are two pairs, each counted its own way, and the cycle the brief asks to keep is there.

### 3. Four kinds, counted apart

Each kind is the edge it is in the record, known its own way, and none is derived from another (section 11):

- **`declared`**: an event of `whom` cites one of `who`'s, by `based_on` or a commit's `Informed-By` ref. Its citer claims it.
- **`observed`**: an offer of `who`'s event that `whom`'s harness said it took, the only way an offer is confirmed
  ([RFC 0037](0037-an-offer-is-confirmed-only-by-its-harness.md)). Handed over and taken, never understood.
- **`cause`**: an event of `whom` names one of `who`'s as its cause, as a reply names what it answers, a completion the claim it
  is fenced by, and a look's reading the turn end that prompted it.
- **`ancestry`**: an event of `whom` is the next version of `who`'s object, a board entry or a task, or `whom`'s commit names
  `who`'s a parent. A parent the journal holds no record of ties nobody.

An edge joins two events, as in the time-expanded graph: one event citing two of `who`'s events holds two edges, and two ranges
of one body cited are one. An observed edge is one offer of one event, so an event offered twice and taken twice is two. A reply
that cites what it answers holds a `declared` edge and a `cause` edge, each counted under its own kind. No field sums the kinds,
and none weighs them.

The edges back from an event are taken as `lineage` takes them, by the one function both use, and an offer's items as `exposure`
reads them, so the counts agree with what each hop shows.

### 4. Unknown is counted as unknown

An offer of `who`'s event that `whom`'s harness had not said it took by the head is `unconfirmed`: neither observed nor none.
A pair known only by such offers is listed, with no edge counted, since leaving it out would read as no reach where reach is
unknown.

Each agent spawned by the head is named in `unknowns` with why what reached it, beyond the edges counted, is unknown: the
surfaces no stored result proves observed, which is every surface today (section 11), read from the one set of proved surfaces
`exposure` decides by, so the two cannot drift apart when a check first proves one; the gaps content could come through that
its record held, by kind, and its offers from before payload 3. So an agent no pair names reads as unknown, and never as reached
by nobody. A person's or a program's reading is no evidence (law 9), so nothing reaches either but through their own writes,
which are theirs, and neither is named there.

### 5. At a head, a page of pairs and of agents at a time

Pairs come oldest first, by the first edge the record learned of each: the event holding it, and for an offer the confirmation,
or the offer while it is unconfirmed. `first` names, for each count, the event holding the first edge of it, an offer for
`observed` and `unconfirmed`, so a client can open its provenance. Agents come in the order they were spawned. A page holds at
most 32 pairs, beside `total`, and at most 32 agents' unknowns, so a page is bounded however many makers a session has, the pairs
growing with their square and the agents with their number. `cursor`, `<head>:<n>`, names the next page of both and carries the
head of the first page, so every page of one answer is read at that head and what the record learned since enters none of them
until someone asks anew. It runs until the pairs and the agents are both through. An `after` that is no cursor, or that names a
head past the record's, is refused `invalid`.

`open` says a later report can still change what the answer leaves unknown: an offer a pair counts as `unconfirmed` went to an
agent that had not ended at the head, whose harness can still say it took it. A turn under way is not the test. The courier
records a wake's offer before the harness reports the turn it starts, a launch's and a resting agent's likewise, and a steer can
land in the turn after the one it was offered in, so an offer can be taken while no turn is under way; and once its reader has
ended, nothing more can confirm it.

### 6. A walk at query time, and no fold

Each page walks the journal once, oldest first, to its head: each event's edges back, each offer's items, each confirmation, and
each spawn and end. Nothing is stored and the writer pays nothing. The cost grows with the journal, measured at about 25 µs an
event here (see Evidence), and the scale tests of milestone 4 measure it on the real stack at 100,000 events and hold it to a
budget set from that measurement.

### 7. Drawn once for both clients

The words are `platoon_harness_cli.provenance`'s, which both clients draw, as they draw one event's provenance (RFC 0043). They
show the first page: the head it was read at, and whether it is `open`; each pair a heading, oldest first, over a line for each
kind of edge it holds, labelled by the kind, saying how that kind is known and opening the event that holds the first edge it
counts, and a line of its own for its unconfirmed offers, labelled `unconfirmed` and drawn as unknown; each agent's unknowns;
and where the page was cut, the command that reads on at the same head. Neither client pages in place, as no part of a
provenance panel does, and neither walks the record (section 12). The terminal opens it in the provenance panel by
`/reached`, where Enter follows a line and Esc comes back.

## The hard parts

- **Overstatement.** A pair is reach in the record, and never credit, influence or a claim that one agent used another's work:
  `declared` is a claim, `observed` a take, and the kinds stay apart so that a claimed citation never reads as a take. Credit
  stays an annotation by a named producer ([RFC 0054](0054-credit-is-a-producers-annotation-and-propagate-is-the-first.md)).
- **Cost.** A walk per page is linear in the journal. A long session asked often pays it each time, on a reader of its own off
  the runtime's event loop, so no report or tool call waits behind it (RFC 0038). If the scale tests find it past what a person
  will wait, the remedy is a fold under an RFC of its own, at the costs the first alternative below names.
- **The runtime is a maker.** A look's reading names the turn end that prompted it as its cause (RFC 0038), so each counts as a
  `cause` from that agent to the runtime, and a notice the runtime posted that an agent took counts as `observed` from the
  runtime. Both are what the record says, and a client words the runtime as the runtime.

## Alternatives

| Alternative | Why not |
|---|---|
| A fold, a view counting each pair's edges as events commit | A fold sees one event (law 2), so it would keep a row naming each event's maker to know whose event an edge leads from, one more write per event, which RFC 0038 declined. Its counters stand at the live head alone, so a second page, read later, would mix heads, and holding them at any head means a row per edge, which is the graph stored. The writer would pay for every session whether anyone asks or not |
| SwarmChat's Map extended | The Map is who is in which chat and how much each wrote ([RFC 0035](0035-the-board-and-the-map-over-messages.md)), a graph of messages, and reach by a citation, a take, a cause or a version is not one. The query is listed in both clients' provenance instead, which is the default pending the owner's ruling |
| One strength or total per pair | Summing a claim, a take, a cause and a version weighs them, and reads one claimed citation as a fact about two agents. Weighing is an estimator's, as an annotation |
| An undirected pair | A reached B and B reached A are two facts, and the cycle the brief asks to keep is between them |
| Counting the events of `whom` that rest on `who` | One event citing two of `who`'s would count as one, and the counts would no longer be the edges `lineage` and `uses` show |
| Counting an offer as observed | Being handed is not taking: an offer is observed only once its harness said it took it. Counted apart, an unconfirmed offer reads as unknown |
| Leaving out a pair known only by unconfirmed offers | The record holds an offer between them, and leaving it out would read as no reach |
| Pairing a maker with itself | It is that maker's history, which `lineage` and `spans` show, and every agent's revisions, claims and confirmations would bury its interactions |
| A walk bounded at 4,096 events, as `contributors` is | `contributors` walks back from one outcome. Who reached whom asks of the whole record, and a bound would answer for some arbitrary part of it |
| Each agent's unknowns whole on every page | A page would grow with the agents, unbounded, and carry every agent again on every page of pairs. Under one cursor each list keeps its own order, and pages past the pairs cost a walk each only in a session with more agents than pairs |
| The unknowns of only the agents a page's pairs name | An agent no pair names is the one whose unknowns matter most, and would be on no page |
| `open` while an agent's turn had not ended | An offer made before the turn it starts, as on a wake, would read as settled though its harness can still say it took it |
| A client walking `lineage` for each event | Clients compute nothing (section 12), and RFC 0038 made `contributors` an op so that no client walks |
| A `head` argument | The cursor carries the head an answer is read at, and asking afresh asks of now. Nobody has asked for an older head |

## Consequences

- A person or a program asks who reached whom in a session, each kind apart, with what is unknown said as unknown. The terminal's
  provenance panel and a pane of the page draw it in milestone 4, through the wording both clients share.
- Each page costs a walk of the journal to its head, about 2.3 s at 91,670 events here, and nothing else: no view, no writer
  cost, no stored graph.
- A confirmation reported later moves an offer from `unconfirmed` to `observed` at a later head. A page read at an earlier head
  keeps it unconfirmed, and says it was `open` where that offer's reader had not ended there.
- Every agent has every surface unproved until a check proves one, so no agent's absence from a pair reads as no reach.
- The runtime and nobody appear as makers where the record makes them so.
- A pair is never credit, and nothing ranks the pairs but the order the record learned them in.

## Rollout plan

| Milestone | Scope | Exit check | Pull requests |
|---|---|---|---|
| M1 the query | `interactions`, `Session.interactions` and the command `interactions` | `tests/unit/primitives/test_interactions.py` | |
| M2 drawn in both clients | The terminal's provenance panel and a pane of the page list each pair, each kind apart with how it is known, and each agent's unknowns, on a view link too, worded once for both | `test_who_reached_whom_is_worded_pair_by_pair_with_how_each_is_known`, `test_the_panel_lists_who_reached_whom_and_each_agent_s_unknowns`, `test_who_reached_whom_draws_each_kind_apart` | `feat: Draw who reached whom in the terminal's provenance panel` |

## Open questions

1. Should who reached whom be a pane over a new query, or SwarmChat's Map extended, and which edges count? M1 builds the default,
   pending the owner's ruling: a query listed in both clients' provenance and not on the Map, counting declared, observed, cause
   and ancestry edges apart, with each agent's unknowns. A Map drawn from the same query would remove nothing M1 builds, and a
   different set of edges would change what the walk counts, not the answer's shape. M2 draws that default too, pending the
   ruling: a Map drawn from the same query, or a different set of edges, would remove none of the wording, which draws what
   the answer holds. Needed before this RFC is accepted.
2. Is a walk per page cheap enough at scale? The scale tests of milestone 4 measure it at 100,000 events on the real stack and
   set its budget. Past that budget, a fold under an RFC of its own. Needed before the budget is set.

## Evidence

- `tests/unit/primitives/test_interactions.py`: `test_each_kind_of_edge_is_counted_apart_and_never_merged`,
  `test_who_reached_whom_may_run_both_ways`, `test_an_agent_s_unknowns_read_as_unknown_never_as_no_interaction`,
  `test_interactions_answer_at_a_head_and_page_by_pair`, `test_a_person_s_and_a_program_s_writes_count_as_theirs`,
  `test_a_view_credential_reads_interactions_and_writes_nothing`,
  `test_interactions_answer_alike_after_a_rebuild_and_on_a_closed_copy`,
  `test_each_agent_s_unknowns_come_a_page_at_a_time_beside_the_pairs` and
  `test_an_answer_is_open_while_an_offer_it_counts_unconfirmed_can_still_be_taken`.
- Drawn, M2: `tests/unit/cli/test_provenance.py`, `test_who_reached_whom_is_worded_pair_by_pair_with_how_each_is_known`,
  `test_each_agent_s_unknowns_are_said_so_no_pair_reads_as_unknown_never_as_no_reach` and
  `test_what_a_page_of_who_reached_whom_left_out_is_said_with_the_command_that_reads_on`;
  `tests/unit/tui/test_provenance.py`, `test_the_panel_lists_who_reached_whom_and_each_agent_s_unknowns`; and
  `tests/unit/tui/test_snapshots.py`, `test_who_reached_whom_draws_each_kind_apart`.
- The cost of the walk, measured with a script kept outside this repository on journals written through the kernel's ops: a ring
  of agents in which each turn hands an agent what waits for it and its harness confirms it, reports a model call and a tool
  item, and sends the next agent a message citing the last one it got, and every fifth round every tenth agent posts or revises
  a board entry. At 20 agents for 10 rounds, 2,464 events, a page took 53 ms; at 100 agents for 82 rounds, 91,670 events and 110
  pairs, it took 2.31, 2.28 and 2.29 s, with 1.6 MiB at its peak as `tracemalloc` traced it. That is about 22 and 25 µs an
  event, so it grows with the journal, and four fifths of it is decoding events. On a shared host with 192 threads of Xeon
  Platinum 8468 at a load of about 10, the journal on a local XFS disk. Scripted reports alone: no real harness wrote these
  journals (UNVERIFIED that a real session's mix costs the same).
