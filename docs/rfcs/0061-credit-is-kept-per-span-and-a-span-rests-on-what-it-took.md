# RFC 0061: Credit is kept per span, and a span rests on what it took

| | |
|---|---|
| Status | Accepted, 2026-11-07 |
| Created | 2026-11-07 |
| Authors | Apurva Gandhi (`ApGa`) |
| Builds on | [`credit.py`](../../packages/sdk/src/platoon_harness/credit.py), [`primitives/provenance.py`](../../packages/sdk/src/platoon_harness/primitives/provenance.py), [architecture sections 11 and 14](../architecture.md#11-provenance), [RFC 0054](0054-credit-is-a-producers-annotation-and-propagate-is-the-first.md), [RFC 0060](0060-an-agent-that-does-not-stay-finishes-with-a-turn-that-leaves-nothing-to-come.md), [RFC 0038](0038-provenance-is-answered-from-the-record.md), [RFC 0037](0037-an-offer-is-confirmed-only-by-its-harness.md) and [RFC 0052](0052-a-reward-has-five-statuses-and-eligibility-is-read-from-the-record.md) |
| Discussion | The owner's request and a design review with two critiques, kept outside the repository |
| Implementation | `fix: Say a finished agent's last words by what its report carries`; `feat: Send each scripted tool call's id as a harness does`; `feat: Cut each agent's turns into spans at its writes`; `feat: Keep propagated credit per span`; `feat: Follow what a span took` |

## Summary

A span is a stretch of one turn of one agent: the turn is cut after each model call that chose a write of content, and a
trailing piece with no write joins the span before it. `spans(agent)` answers an agent's spans from the record, and
`propagate` keeps credit per span as well as per agent, writing a row on each span it reaches, named by the `model.called` of
its last call. It moves in place, under one name, to version 2, `propagate@1`'s walk with each kept share also booked to the
span its event lies in, and then to version 3, which adds one edge, the take: another principal's event that an offer showed and
the agent's harness confirmed taking in the span, before the event's bound. A finished agent's `said` becomes the ref its end's
report carries, ScriptedDriver sends each tool call's id as a harness does, and "span" keeps one meaning.

## Motivation

The owner asked that only a particular span of a persistent agent's history be mapped to the message board task it did.
`propagate@1` ([RFC 0054](0054-credit-is-a-producers-annotation-and-propagate-is-the-first.md)) wrote one row per agent, so a
worker that claimed and completed three tasks in one turn had one row for all three, and a training system could train it only on
everything it did, or not at all.

A GPU run of a mesh showed the second gap. Its peers never finished, so each closed on its last words: a message item, which
follows from nothing and cites nothing, as an answer given by ending a turn does. So `propagate@1` keeps each peer's share on that
message and passes nothing on: on a scripted mesh of three such peers and a helper, each peer's last turn got a third and the
helper that did the work got nothing. Declared edges can never leave such a closing; what reached the closing span is the
record's one exact tie to what came before it.

A third came from [RFC 0060](0060-an-agent-that-does-not-stay-finishes-with-a-turn-that-leaves-nothing-to-come.md): a finished
agent's `said` named its `agent.ended`, while that end's report carried its `agent.finished` or its last message, so one act had
two refs. An episode closed on the end walked from an event that cites nothing and that no model call chose: a finish's
citations carried no credit, and once credit is kept per span, an end out of a turn lies in no span, where its share trains
nothing.

## Proposal

### 1. A finished agent's `said` is what its end's report carries

`end()` works out the ref its report carries before it emits, and records it on `agent.ended`, payload 2, as `carries`, None
meaning the end itself; the `Agents` fold reads it, and an end written before payload 2 says itself, so no existing event folds
differently. In one sentence, for each way an agent ends: once an agent has finished, its `said` is the ref its end's report
carries, which for an `agent.finish` with a gist or a body is that call's `agent.finished` in a turn and its `agent.ended` out of
one, and for any other finish, an empty one, a one-shot's stopped turn or a turn that leaves nothing to come, the latest turn's
last message, whose words the report took, or its `agent.ended` where that turn said nothing; an agent cancelled, retired, lost
or failed says its latest turn's last message, as a live one does, or None where that turn said nothing. A finish has words of
its own by its gist or its body alike, in a turn or out of one, so an empty finish after a message with a body says that message.

This amends RFC 0060, whose `said` named the end of an agent that finishes with a turn that leaves nothing to come: it now names
the message that said those words, which that end's report holds.

### 2. ScriptedDriver sends each tool call's id

Each tool call a model chose goes under the id the model gave it, as `scripted/toolCallId` in MCP's `_meta`, which its tool item
already held. The key is among the tool server's `HARNESS_ANCHORS`, so conformance's `tool_item_carries_its_anchor` checks the
scripted driver too. A `Call` step, which no model chose, sends none. Without it no fast test could show a join, and two identical
calls one model call chose were one op.

An op joins its call by that id, so an id must name one call. `FakeModel` gives a tool call its script names no id
`call_<reply>_<place>`, where every such call was `call_1`, so no two calls share one, as a model's never do; and ScriptedDriver
fails the turn of a call under an id it has sent already, rather than join its op to the call that sent it first or answer it as
a repeat.

### 3. Spans, from the record alone

A span is cut after each call that chose a write of content, where the record joins them: the op's anchor names a tool item and
that item names the call. The writes are the eight that take `based_on`, made by the agent itself. A claim, a read, an announce
and a write with no join cut nothing, and a turn with no joined write, or with joined writes from one call alone, is one span.
Every `model.called` an agent's harness reported in a turn lies in exactly one span, by its place on the agent's own report
stream, the order a bound already rests on; a call out of a turn lies in none. A span is named by its last call's `model.called`.

```python
class Span(Model):
    ref: str                   # the model.called of its last call, its name and its credit's target
    first: str                 # the model.called of its first call
    turn: str
    writes: tuple[str, ...]    # the writes of content the record ties to its calls

class Spans(Model):
    agent: str
    spans: tuple[Span, ...]    # oldest first, a page
    total: int
    cursor: str | None
    head: int
    open: bool                 # while the latest turn has not ended, as a late tool item can cut it again

async def spans(self, agent: str, *, after: str | None = None) -> Spans: ...  # Session; a query op, no agent's tool
```

It is worked out as it is asked, from a scan of `turn/<agent>` and the agent's anchored events through lineage's own join, so no
view changes and it answers alike after a rebuild and on a closed copy. Lineage gains no span: an event's span follows from its
call and the spans.

An event lies in the span holding the call `lineage` says made it; an entry that carries an event, as an announce or a child's
report does, lies where that event lies; an event tied to no call lies in its turn's span when that turn is one span; any other
event lies in no span. Which span an event lies in is the record's to say; that a span's calls made what lies in it is an
estimator's claim.

### 4. `propagate@2`: credit kept per span

The walk is `propagate@1`'s, unchanged. What an agent's event keeps is that agent's, and also its span's when the event lies in
one. It writes one local `credit` row per span it reached, on the span's name, and one per agent it reached, on its first
`agent.started`, holding all that agent's events kept. An agent's row is its spans' rows and what it kept in no span; the reward
is the agents' rows and what nobody's events kept; a span or agent never reached has no row. Its agent rows equal `propagate@1`'s
on every journal. The annotation schema does not change: a span's row targets the `model.called` of its last call, in the place
of a turn's `turn.started` and a call's `model.called`, targets nothing wrote.

### 5. `propagate@3`: a span rests on what it took

One edge is added, the take. A call's takes are the events, other than its own agent's, that offers its agent's harness confirmed
taking showed, by gist or body, after the agent's previous call and its latest start or resume and before the call; a span's takes
are its calls' takes, and an event's takes are its span's takes confirmed below its bound. An event in no span has none. Each
event shown is one take, one share, as each relation is: a post cited and taken gets two shares. A confirmation is written by
`agent.report` from the harness's own report, which comes in order with the reports of its model calls, and an offer its harness
never confirmed is no edge: [provenance.md](../how-to/provenance.md)'s "never along an offer" becomes "never along an unconfirmed offer". Takes of the
agent's own events never count, as what it made is already its own; takes of a program's or a person's events count, and keep
for nobody, as their citations do.

Every edge points to an older event. A take points back only if the host commits one agent's reports in order, which is the
bound's own assumption, so a walk that meets an edge to an event no older than its own makes every row `invalid`, as one cut short
at 4,096 events does, where its share would otherwise vanish while the rows still claimed to sum to the reward.

The producer keeps its name and one function, `platoon_harness.credit:propagate`, and moves from version 1 to 2 to 3 in place.
An earlier version is reached by pinning an earlier SDK; an ablation that tells spans from takes is one pin at version 2, with no
switch and no second producer.

### 6. One word, one meaning

`primitives.Lines.span`, the line range a result shows, is `Lines.range`, as the read tools' argument already was; the facade's
own alias for a duration is gone in favour of `schema.Duration | float`, and `schema.seconds` takes a `duration`; an episode is
a part of a session. `primitives.Span`, `primitives.Spans` and `Session.spans` are added, and the command `spans` is derived.

## The hard parts

- **Order on one stream.** Cuts, takes and the older-edge rule rest on the host committing one agent's reports in order, and for
  pi on `message_end` coming before that call's tool items: the bound's own unverified assumption. If it fails, walks turn
  `invalid`, and say so, rather than lose credit silently.
- **Where a call is reported.** pi and ScriptedDriver report `model.called` at a call's end, so a take confirmed during call N is
  N's; Claude Code reports at a call's start, so such a take is N+1's. The same take can fall one call apart between harnesses at
  a span's edge.
- **Coverage.** OpenHands joins no tool call to its call, so each of its turns is one span; Codex gives no id per call, so its
  spans name calls nothing can train; `exec` reports no call, so it has none. A worker that does several tasks in one turn there
  gets one span for all of them.
- **Credit kept in no span.** An end out of a turn, runtime events about an agent in a cut turn and an op whose anchor never came
  lie in no span. What they keep is their agent's alone, and a training system that trains spans trains nothing on it.

## Alternatives

| Alternative | Why not |
|---|---|
| Whole turns as the unit | A worker that loops over tasks in one turn would have them merged |
| A cut after every write, the turn's last included | Closing on last words put the whole reward on one trailing call |
| Spans that cross turns | A turn's "finished A" landed in the next task's span |
| Cutting at claims too | A call that completes one task and claims the next is one call, and lies in one span either way |
| A turn holding an unjoined write is one span | A second rule, a stored index and a view version bump, and one lost report would erase a turn's cuts |
| Placing an unjoined write by its commit seq | It compares two report pipes |
| A carried entry passing everything through | It changes `propagate@1`'s walk, so `propagate@2`'s agent rows would no longer equal it |
| `Made.span` on lineage, `Span.unjoined`, or each span's calls or takes in the answer | They restate the record, make every lineage answer pay for its turn's cuts, or make answers unbounded |
| A `scope` value, an event, or a span named by its write | The schema stays; producers write no events; a span may hold several writes or none |
| One `propagate@2` with spans and takes together | The reduction to `@1` would be conditional, and an arm would differ in two ways nobody could tell apart |
| A span producer beside `propagate`, or a `taken` parameter | Two ways to do one thing |
| Unconfirmed offers, or every take in an agent's history | Being handed something is not using it, and an earlier process's takes were never this one's |
| Exempting native resumes from the launch bound | A branch on the resume's kind, to keep the takes between a native resume's last call and its crash |
| Counting own takes | What an agent made is its own already; counted, its own instructions kept part of the queue's credit for no span |
| `said` naming `agent.finished` for every finish in a turn | One act would keep two refs where an empty finish carries its last message |
| Copying `based_on` onto `agent.ended`, or walking from the end to the finish by order | One claim with two homes, or an edge the record does not hold |
| Pooling spans as agents of their own in a training system | It ties an agent's advantage to how many spans it was cut into |
| Renaming only the duration alias | "Span" would keep two meanings in public names |

## Consequences

- A persistent worker's tasks are credited apart, each to the span whose call completed it, on harnesses that join a tool call to
  its call: pi, Claude Code and ScriptedDriver.
- A helper whose report a credited span took is reached, cited or not, and a spawn is credited through the goal its child took.
  An uncited report keeps all that reaches it on the span that wrote it. An agent that wants its crafting span reached cites its
  own earlier write, which carries credit only once its harness has taken that write back, by a read, as an agent's citation
  counts only where its exposure says Seen, and nothing hands an agent its own write otherwise.
- A program's task statement taken in a span earns its share for nobody: on a scripted queue, the worker's spans fall from three
  quarters in all under version 2 to under two thirds under version 3.
- The incentives change and are stated: being cited or taken by a credited span earns credit; citing, and taking, give away all
  but `retained`; broadcasting draws more takes; reading in one's last turn costs.
- A training system trains each scored span on its row less its agent's baseline shared equally by its scored spans, so an agent's
  advantage does not depend on how many spans it was cut into; that is the training system's to build, and Platoon's is under way
  apart from this repository.
- Spans are worked out when asked, and `propagate@3` reads each reached agent's offers once. Its cost on long agents is not
  measured beyond scripted sizes.
- A queue program closes on its tasks' results; a training system that closes on starting agents' `said`, as Platoon's bridge does,
  credits only a queue worker's last span, and keeps doing so until it trains a queue team.

## Rollout plan

| Milestone | Scope | Exit check | Pull requests |
|---|---|---|---|
| M1 `said` | The ref an end's report carries, on `agent.ended` payload 2 | `test_a_finished_agents_said_is_what_its_report_carries` and the four beside it in `test_lifecycle.py` | `fix: Say a finished agent's last words by what its report carries` |
| M2 Scripted ids | `scripted/toolCallId`, and an id per tool call | `test_scripted_driver_sends_each_tool_calls_id_so_each_op_joins_its_call`, `test_scripted_driver_joins_each_op_to_its_own_call_on_the_ids_fake_model_gives` and `test_scripted_driver_fails_the_turn_of_a_tool_call_under_an_id_it_has_sent`, and `tool_item_carries_its_anchor` passing on ScriptedDriver | `feat: Send each scripted tool call's id as a harness does` |
| M3 Spans | The `spans` query and the renames | `tests/unit/primitives/test_spans.py` | `feat: Cut each agent's turns into spans at its writes` |
| M4 `propagate@2` | Span rows beside agent rows on `@1`'s walk | `test_propagate_2_writes_the_agent_rows_propagate_1_wrote`, over generated journals | `feat: Keep propagated credit per span` |
| M5 `propagate@3` | The take and the older-edge rule | The take tests in `test_credit.py`, and `test_a_mesh_whose_peers_never_finish_reaches_the_helpers_its_closing_spans_took` | `feat: Follow what a span took` |
| M6 Training on spans | A training system trains each span on its row | The training system's own tests | Built apart from this repository |

## Open questions

1. Should a fresh smoke run on a GPU, of the arm that trains on `propagate@3`, come before a longer run, given that the arm's
   meaning changed after the last smoke's readout? The owner decides, before any GPU run of it.
2. Should the ablation that tells spans from takes, the same arm pinned at `propagate@2`, be run? The owner decides, before the
   longer run.

## Evidence

- [tests/unit/runtime/test_credit.py](../../tests/unit/runtime/test_credit.py): a test named for each rule of sections 4 and 5,
  among them two properties over generated journals, `test_propagate_3_writes_propagate_2s_rows_where_no_span_took_another_principals_event`,
  against RFC 0054's rule read off the journal, and `test_each_agent_row_is_at_least_its_span_rows_and_the_rest_was_kept_in_no_span`;
  the owner's case on ScriptedDriver against FakeModel acting as a gateway,
  `test_a_persistent_worker_credits_each_task_to_the_span_whose_call_completed_it`, with a claim made in the call that completed the
  task before and two claims open at once; and the GPU run's failure on ScriptedDriver,
  `test_a_mesh_whose_peers_never_finish_reaches_the_helpers_its_closing_spans_took`, where the helper gets three sixteenths of the
  reward. Before `propagate@3` replaced it,
  `test_propagate_2_writes_the_agent_rows_propagate_1_wrote` held `propagate@2`'s agent rows to `propagate@1`'s rule on generated
  journals that confirmed offers.
- [tests/unit/primitives/test_spans.py](../../tests/unit/primitives/test_spans.py): a test named for each rule of section 3, among
  them a property over generated reports, `test_every_call_reported_in_a_turn_lies_in_exactly_one_span`.
- [tests/unit/primitives/test_lifecycle.py](../../tests/unit/primitives/test_lifecycle.py): the five `said` tests, and RFC 0060's
  turn-finish test, which asserts `said` and `carries` name the message that said the last words.
- [tests/unit/drivers/test_scripted.py](../../tests/unit/drivers/test_scripted.py) and the conformance suite, for section 2.
- [tests/integration/test_contract.py](../../tests/integration/test_contract.py): a row for each agent and for the span its last
  words lie in, on ScriptedDriver in the fast pass and on pi and OpenHands in the slow pass.
- A throwaway reimplementation of these rules, written for the design and kept outside the repository, gives the numbers these
  tests assert on the owner's case, the claims made in a completing call and the never-finishing mesh, read off the same
  sessions; on that mesh without takes it keeps each peer's half on its last span and gives the helper nothing. No real harness,
  no live model and no GPU run has produced a span row.
