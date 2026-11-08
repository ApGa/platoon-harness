# RFC 0078: A span carries the labels of the work it was done for

| | |
|---|---|
| Status | Draft |
| Created | 2026-11-09 |
| Authors | Apurva Gandhi (`ApGa`) |
| Builds on | [`team.py`](../../packages/sdk/src/platoon_harness/team.py), [`primitives/sessions.py`](../../packages/sdk/src/platoon_harness/primitives/sessions.py), [`primitives/tasks.py`](../../packages/sdk/src/platoon_harness/primitives/tasks.py), [`primitives/provenance.py`](../../packages/sdk/src/platoon_harness/primitives/provenance.py), [`tools/surface.py`](../../packages/sdk/src/platoon_harness/tools/surface.py), [`credit.py`](../../packages/sdk/src/platoon_harness/credit.py), [architecture sections 7, 10, 11 and 14](../architecture.md#7-primitive-semantics), [RFC 0061](0061-credit-is-kept-per-span-and-a-span-rests-on-what-it-took.md) and [RFC 0054](0054-credit-is-a-producers-annotation-and-propagate-is-the-first.md) |
| Discussion | The owner's request of 2026-11-09, and the owner's rulings that the vocabulary is fixed per team and declared in configuration, that the creating agent decides a task's difficulty as it creates it, and that crafting-style work an agent does for a task earns credit through the task. The request accepts no design: this one waits for the owner's acceptance |
| Implementation | `feat: Label tasks and spawns from a vocabulary the team declares`; `feat: Give each span the claims its agent held and the labels of its work`; `feat: Share what a claim and its result keep among the spans that held the claim` |

## Summary

A team file declares `labels`, each a name with the values it may take, fixed for the team. `task.add` and `agent.spawn` take
`labels`, at most one value for each label, refused `invalid` outside the vocabulary, recorded on `task.added` payload 2 and
`agent.spawned` payload 4; each tool that takes them shows each label's values in its schema, and none where the team declares
none. Each span carries the labels of the work it was done for: of the task its agent held while its calls were made, from the
call after the one that claimed it through the one that completed, failed or released it; else those its agent was spawned with;
else none; and None, unknown, where its calls were made under claims of different labels or the record cannot place a claim or
its end. `spans` answers them beside the claims each span held, which is the training contract a keyed baseline reads.
`propagate@4` shares what a claim and its result keep equally among the spans that held the claim, so work done before a
progress message cut a span is credited through its task. `propagate@3` stays runnable, by `version=3`.

## Motivation

The owner's idea: an agent that creates a sub-task, by spawning an agent or by adding a task for another to take, tags it with
labels, such as its difficulty and its kind of work, verification, execution, design or search, from a vocabulary that belongs
to the domain; and a training system computes the advantage of the work done for it against a baseline of other rollouts' work
of like labels. The SDK owns three parts of that: the vocabulary and the labels on the record, the tie from a span to the work it
was done for, and credit that reaches that work. Platoon's keyed baseline and DAO's team are later stages in other repositories,
on the contract this states.

Today none of it can be said:

- A team file has no place for a vocabulary. `Team` refuses a key it does not declare, and so do `task.add` and `agent.spawn`
  ([`kernel/op.py`](../../packages/sdk/src/platoon_harness/kernel/op.py) `Args`), so no label can reach the record.
- A span names its writes but no work. A worker that claims a task, crafts with an environment's tools and tells its lead how far
  it has come, which is a write and cuts its turn, then completes the task, has two spans, and nothing says both were done for that
  task. A keyed baseline needs that tie per span, since a span is what trains
  ([RFC 0061](0061-credit-is-kept-per-span-and-a-span-rests-on-what-it-took.md)).
- `propagate@3` keeps what a task's result keeps on the span whose call wrote it, and its claim's share on the span whose call
  claimed it. The crafting span, cut off by the progress message, gets the claim's share at most, and nothing of the result's,
  however the lead used the result: `test_an_uncited_report_keeps_what_reaches_it_on_the_span_that_wrote_it` shows the same for a
  report. The owner ruled that such work earns credit through the task: the claimant completes it, and the creator reads or cites
  the completion, so credit flows to the work.

## Proposal

### 1. A team's vocabulary

```toml
[labels]
difficulty = ["easy", "medium", "hard"]
kind = ["design", "execution", "search", "verification"]
```

```python
class Team(Model):
    ...
    labels: Mapping[Name, tuple[Name, ...]] = {}   # each label with the values it may take, in the order a model sees them
```

One table at the top of the team file, as `test` and `auth` are. A label and each value is a name under the naming law, since a
team names them; a label takes at least one value and each value once, or the team is refused. The vocabulary is the team's, so
it is fixed for every session of it; the domain declares it once in a project file, as mappings merge across the layers and lists
replace, and a team file may add to it. It is journaled at open, as the session's other settings are, on `session.opened`
payload 3 as `Settings.labels`; a session opened before has none. `session.labels`, a query kept to the runtime, reads it for the
tool plane.

### 2. Labels given, checked and shown

`task.add` and `agent.spawn` take `labels`, a mapping from a label to one of its values, beside their other arguments, and so do
`Session.task_add` and `Session.spawn`. A label the team does not declare, or a value its label does not take, refuses the whole
op `invalid`, saying what may be given; a team that declares none refuses any. The labels are recorded on `task.added` payload 2
and `agent.spawned` payload 4 as `labels`, sorted by name, and an older payload reads as none. A person's, a program's and the
runtime's adds and spawns meet the same check as an agent's.

They are optional, label by label. The code gives reasons: the agents a session starts have no creator to decide anything of
them, older sessions and teams with no vocabulary have none, and a label is evidence its creator gives, so one it was not sure of
is honest absence, which a training system can tell from a value, where a required label would make it guess. Difficulty is
decided by the creating agent as it creates the work, as the owner ruled, and nothing changes it after.

A tool that takes `labels` shows a model each label with its values, as an `enum`, with no other key allowed, and says them in
its description too, which `ph` shows, so a model picks from them; with no vocabulary, the argument is left out of the schema, as
no value could fill it. The op's own check is what holds, for a harness that does not enforce a tool's schema. The vocabulary is
fixed at open and the tool list at launch, so the two always agree. No reader is shown a task's labels: `task.list` and
`task.claim` say what they said before.

### 3. A span's labels

A claim is held from its claimant's claim to the first of its completion, its failure, its release, its lease's lapse and its
claimant's end, which `Tasks` now indexes by claimant. Its calls are those made after the call that chose the claim, through the
call that chose its end. Each is placed by the record alone:

- an event the record ties to one of the claimant's calls, through the op's anchor, the tool item holding it and that item's
  `call_id`, comes after that call;
- one of the claimant's own tied to no call, made in a turn that is one span and ended, not lost, as on OpenHands and Codex,
  takes that span whole: a claim at its start and an end at its end, as such an event lies in that span (RFC 0061);
- any other, as a lapse, which the clock makes and no call of the claimant's, is placed by commit order among the claimant's turns:
  exactly between two, as no call is made between turns, and anywhere within one;
- a hold that its claimant's end ended, or that holds still, runs past the claimant's last call.

A span holds a claim when one of its calls was surely made while it was held, and may hold it when one may have been. Its claims
are those it holds, oldest first, and None, unknown, where it may hold one it does not surely hold, as no list of what it surely
held says so. Its labels are those of the task of every claim it holds or may hold, and its agent's spawn labels unless it surely
holds one, even for its calls made before the claim; where these all agree they are its labels, and where they differ the span's
labels are None, unknown, never merged and never one of them guessed. A task given no labels is work with none, so a span that
held it carries none, not its agent's.

```python
class Span(Model):
    ref: str
    first: str
    turn: str
    writes: tuple[str, ...]
    claims: tuple[str, ...] | None   # each claim its agent held while one of its calls was made; None where unknown
    labels: dict[str, str] | None    # the labels of the work it was done for; None where unknown
```

`spans` answers both, worked out from the views as it is asked, alike after a rebuild and on a closed copy; `open` keeps its
meaning, as a tool item reported late can join a claim or its end to a call as it can a write. A call that completes one task and
claims the next ends the first's span, which held only the first, as no call of it was made while the next was held.

### 4. `propagate@4`

In one sentence: what a claimant's event of a claim keeps, the claim, and the completion, failure or release that ended it, is
shared equally by the spans that held the claim, and kept by the event's own span only where none did.

The walk is `propagate@3`'s, edge for edge, takes included: only where a share is booked changes. So its agent rows are version
3's on every journal; an agent's row is still its spans' rows and what it kept in no span; the rows still sum to what reached
them; and it is as deterministic, and bounded at the same 4,096 events. Where no claimant's event of a claim is reached, or each
such event's own span is the one span that held its claim, its rows are version 3's.

On the owner's case, scripted, a lead's last words take the worker's result and keep half the reward; the result keeps an eighth
and its claim a sixteenth; the worker's crafting span and its completing span share both, 3/32 each, where version 3 gave the
completing span the eighth and the crafting span the sixteenth.

`propagate(session, episode, *, judge, retained, version=4)`: `version=3` writes version 3's rows, under `producer_version` 3,
for a run recorded on it, as DAO's run notes and configs name `propagate@3`; any other version is refused `invalid`. RFC 0061
reached an earlier version by pinning an earlier SDK; a training system pins one SDK for every producer it runs, so a recorded
run could not be run again beside a new one, and a version argument is the one way to say which. The parameter is no switch
between rules: it names a version, and its rows say it.

### 5. The contract for a training system

`Span.labels` and `Span.claims` join the training contract (architecture section 14): a training system reads each scored span's
labels from `spans`, beside its `propagate` row, and keys its baseline by them. A span whose labels are None has no key, which is
the training system's to treat: this SDK says why and guesses none. The vocabulary is the team's own, which the training system
wrote; `session.opened` holds it as the session ran. Nothing here computes a baseline or an advantage.

## The hard parts

- **Two report pipes.** An op commits through the tool plane and a call is reported through the control plane, so commit order
  cannot place an op among calls (RFC 0061). A claim or an end is placed by its join, and commit order is used only against turn
  boundaries, which are on the claimant's own report stream: every call of a turn is reported before its end. A lapse inside a
  turn is left unknown, not placed.
- **A turn of one span.** A claim tied to no call is taken to hold from its turn's start, though the call that chose it may be the
  turn's last. A harness ends a turn with a call that chooses no tool, so a claim is followed by a call unless the turn was cut,
  which is why the rule holds only for a turn that ended: one lost, or still running, places the claim anywhere in it;
  UNVERIFIED on OpenHands and Codex, whose turns have not been read for it.
- **What a turn's first call says.** An op of the claimant's tied to no call, in a turn that is cut, was chosen by one of its
  calls, so it would seem to come after the turn's first. But a call can go unreported, as a `hidden_call` or a `stream_lost` gap
  says, and a native child's calls reach its parent's report stream: the first call reported is not surely the first made, and the
  op is placed anywhere in its turn.
- **Incentives.** Under a keyed baseline, a harder label lowers the baseline its work is measured against. A shared policy can learn
  to call work hard to raise its claimants' advantage, as the creator decides difficulty and its claimant trains on it. That is the
  training system's to guard, by the creator's own credit or a check of labels against outcomes; nothing here can.
- **Where the hold's work went.** A span that held a claim gets a share of its claim's and its result's keep whatever it did, as
  calls before a cut are no less the task's for the cut; an agent that held a task and spent a span on something else is credited
  through the task for it.

## Alternatives

| Alternative | Why not |
|---|---|
| Free-form labels | The owner ruled the vocabulary fixed per domain; a free label keys a baseline nothing else shares |
| A vocabulary per queue, per role or per channel | Several places for one fact; the owner's vocabulary is the domain's, which a team is |
| Labels in `Topology` | The topology says who may reach whom; labels say what the work is |
| Tags, a set of values with no labels | "Hard" and "search" are values of different questions, and a baseline keys each |
| Required labels | Started agents, older sessions and an unsure creator have none to give honestly |
| A new op to label work after it was added | Difficulty is decided at creation, as the owner ruled; a second write of one fact |
| Labels shown in the preamble | A preamble is a snapshot of targets, and a schema is where a model picks a value |
| Telling a claimant its task's labels | Nothing asked for it, and a worker told its task is easy may work it as one: an open question |
| Merging two held tasks' labels, or taking the first | The owner ruled unknown; either guesses which task a call worked for |
| Placing claims by their commit seq among calls | It compares two report pipes (RFC 0061) |
| Holding from the span a claim lies in | A claim made in the call that completed the task before lies in that task's span, which it never worked |
| Weighting held spans by their calls | A span's call count is its harness's; one share each, as each edge has one |
| Spreading the claim's and the result's takes too | Two changes in one version, so its agent rows would no longer be version 3's |
| Sharing a completion alone | A failure is the same work's other result, and its claim is reached through it; one rule for a hold's events |
| A second producer for tasks | Two ways to do one thing |
| Pinning an earlier SDK for version 3 | A training system runs one SDK, so a recorded run could not run again beside a new one |

## Consequences

- A team's work is labelled where it is created, from its own vocabulary, and the record keeps who gave which labels and when.
- A keyed baseline can read each span's labels and its row from the record alone, on every harness that reports calls; on OpenHands
  and Codex a turn is one span, so a turn that worked several tasks of different labels is unknown.
- A crafting span cut off by a progress message is credited through its task. An agent's row does not change from version 3 to 4.
- A run recorded on `propagate@3` runs again under `version=3`, with rows that say version 3.
- Old sessions read as unlabelled. The `Tasks` view gains a table and refolds once on each session's next open.
- `spans` reads each claim of the agent's and the event that ended it, a lookup each; its cost on long agents is not measured
  beyond scripted sizes.
- Neither client shows a span's labels yet: the terminal's and the browser's provenance say what they said.

## Rollout plan

| Milestone | Scope | Exit check | Pull requests |
|---|---|---|---|
| M1 Vocabulary | `Team.labels`, `Settings.labels`, `labels` on `task.add` and `agent.spawn`, the schema a model is shown | [`test_labels.py`](../../tests/unit/primitives/test_labels.py) and `test_a_team_s_labels_reach_the_session_with_their_values_in_its_order` | `feat: Label tasks and spawns from a vocabulary the team declares` |
| M2 Span labels | `Tasks` indexes claims; `Span.claims` and `Span.labels` | The label tests of [`test_spans.py`](../../tests/unit/primitives/test_spans.py) | `feat: Give each span the claims its agent held and the labels of its work` |
| M3 `propagate@4` | The shared booking, and `version` | The claim tests of [`test_credit.py`](../../tests/unit/runtime/test_credit.py) and `test_a_worker_s_spans_from_claim_to_completion_carry_its_task_s_labels_and_share_its_credit` | `feat: Share what a claim and its result keep among the spans that held the claim` |

## Open questions

1. Should a claimant be shown its task's labels in `task.claim` and `task.list`? The default, built, shows none, pending the owner's
   ruling, and showing them is a field added to two results, which tears out nothing.
2. Should a failure and a release be shared as a completion is? The default, built, shares every claimant's event of a hold,
   pending the owner's ruling; a ruling for completions alone narrows one set.
3. Should DAO's next run train on `propagate@4`, or pin `version=3` until a smoke run of it? The owner decides, before any GPU run.
4. Should a span that claimed a task carry the task's labels for its calls before the claim? The default, built, does: a span
   that surely held a claim takes its claims' labels alone, pending the owner's ruling. A ruling for the spawn's work makes such
   a span's labels None wherever its spawn's differ, which changes one rule of `spans` and tears out nothing; a worker that
   looks at its queue before it claims would then have no key for the span that claims.

## Evidence

- [tests/unit/primitives/test_labels.py](../../tests/unit/primitives/test_labels.py): a test for each rule of sections 1 and 2.
- [tests/unit/primitives/test_spans.py](../../tests/unit/primitives/test_spans.py): a test for each rule of section 3, among them a
  claim made in the call that completed the task before, two claims of different labels and of alike ones held at once, a claim
  tied to no call in a turn of one span, in a cut one and in a lost one, and a lapse between turns and within one.
- [tests/unit/runtime/test_credit.py](../../tests/unit/runtime/test_credit.py): the rule of section 4, version 3 run again on the
  same journals, a property over generated journals that version 4 writes version 3's rows where no claim's events are reached,
  and the owner's case on ScriptedDriver against FakeModel acting as each agent's gateway, whose numbers section 4 gives.
- No live model, no real binary and no GPU run has produced a labelled span.
