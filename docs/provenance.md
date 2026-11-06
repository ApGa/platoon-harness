# Provenance

A session's journal says what each agent was handed, what it claimed to rest on, and what followed from what. This guide is how to
ask it. Architecture section 11 is the design of record, and [ADR 0038](adr/0038-provenance-is-answered-from-the-record.md) the
decision.

Three things stay apart in every answer, and none is ever drawn as another:

- **What an agent claims.** A citation, `based_on` on a write, is its writer's claim, checked to name an event and, for a range,
  lines of its body.
- **What reached it.** An offer the runtime made, and its harness's own report that it took it, is observed exposure. Seen means
  handed over and taken, never understood: a read's result returned to its harness, or, under Codex's `callId`, to the Code Mode
  script that made the call.
- **What an estimator thinks.** Credit and rewards are annotations, each by a named producer at a version, never facts.

## Refs and citations

Every event has a ref, `stream@version`, and `#La-b` names lines of that event's body: `board/notes/spec@3#L10-40`. Every result,
handover and notice names what it shows by one, and every write of content returns the one it made. A message that repeats another
event's words, an announce of a board write or a child's report, is shown by the ref of what it repeats, so one act has one ref.

The eight writes of content take `based_on`: `message.send`, `board.post`, `board.revise`, `task.add`, `task.complete`,
`task.fail`, `agent.spawn` and `agent.finish`. A citation must name an existing event, and a range lines of that event's body, or
the whole write is refused, so a citation says whether the event it names exists, and never what that event holds. A citation of
something its citer was never handed is kept, and `exposure` says so beside it. A commit cites through its `Informed-By` trailers:
a commit by its SHA, and an event of the session by its ref, such as the board entry the commit implements, so the walk back from
code reaches the messages and entries that informed it. An event's ref is checked as any citation is, and cites only in a commit an
agent of the session made, of an event that agent made or was handed, as `blob.get` reads: a trailer is text git carries between
clones and sessions, so a ref in a commit made elsewhere, or by nobody the record names, names nothing here. A value that cites
nothing stays as written, never refused, and lineage lists it as unresolved, saying why.

## Asking agents to cite

What an agent is told is a template, and the default asks every agent that holds a write of content, in one line of its own:

```text
When what you write rests on something you read, put its `ref` in `based_on`.
```

That line, the template's `{citing}` slot, is the one place an agent is asked: a tool's description says what `based_on` is and
never asks. It costs 78 bytes in every request of such an agent, 20 tokens by Qwen3's tokenizer, and a refused write and its retry
for each citation that names nothing or no lines of its event. A team that copies the default and leaves the slot out asks nothing,
and its agents' citations are still checked and kept. In two live runs, one on each of Claude Code and Codex, each of the two
citations made named something its citer had been shown, and none was refused; two runs measure no rate, and
[STATUS.md](STATUS.md) keeps them.

## Asking the record

Four queries answer people and programs, from a live session or a closed one, and none is an agent's tool:

- `exposure(agent, ref, before)`: whether one event reached one agent through us before another, `seen`, `not_seen` or `unknown`.
- `lineage(ref)`: one hop back, who made an event, in which turn and model call, what it cites and what it followed from.
- `uses(ref)`: one hop forward, what cites an event, what followed from it, and who was handed it.
- `contributors(ref)`: each maker a walk back from an outcome reaches, and apart from them those only handed to one.

This reads an event's citations with what its writer had been shown of each:

```python
async def citations(session, ref):
    """Each ref an event cites, its maker, and whether the event's own maker had been shown it before writing."""
    traced = await session.lineage(ref)
    rows = []
    for cited in traced.declared:
        answer = None if cited.exposure is None else cited.exposure.answer
        rows.append((cited.ref, cited.maker, answer))
    return rows
```

`lineage` names the model call that chose the event when the harness's ids join one, and its answers stop there: what the agent's
harness reported taking before that call counts, and nothing after. With no call joined, an answer stops at the event's commit and
says `commit`. A git commit is recorded by the look that found it, after git made it at a time the record does not hold, so its
answers stop at that look and say `look`: what counts may have come after the commit. Every answer names its `head`, and is `open`
while the turn its event was made in has not ended, since a later report can still confirm what was handed over. A ranged citation
says whether its lines were shown as exposure says whether its event was: true when a confirmed offer showed them, and otherwise
null, as no answer can say they were not.

## In the terminal and the browser

A person follows provenance from where they read: `/provenance` in the terminal, or `p` with the transcript in focus, on the chosen
line, and Provenance among a message's actions in the browser, on a view link too. Both show one event at a time, in the same words,
in four parts: its sources, its uses, its contributors, and what estimators said of it. Each link is labelled by how it is known,
`declared`, `observed`, `cause`, `ancestry` or `gap`, and following one shows that event's provenance; a line that opens nothing says
why. Each part says the head it was read at, where it stops counting, and whether its turn was still open, and a page an answer cut
names the command below that reads on. A harness's report of a tool item names the model call it says chose it and opens what each
command of its agent's under that call's id made, so an agent's own transcript leads to its writes. What was not said below a bound
reads as not said there, never as never. [tui.md](tui.md) and [web.md](web.md) are the clients' guides.

## What `unknown` means

`unknown` lists its reasons: offers its harness had not said by the bound that it took, surfaces of the agent's harness no stored
conformance result proves observed, and gaps content could have come through. An empty list of offers is how "not handed over
through us below the bound" reads, which is not "never seen": every harness here has a shell, and what reaches an agent through a shell, a file or git leaves nothing in the
journal. So nothing answers `not_seen` today. [compatibility.md](compatibility.md), Provenance per harness, says what each harness's
reports let the runtime confirm and join.

## Contributors are not credit

`contributors` follows citations, causes and ancestry back from an outcome, at most 4,096 events, and names each maker in the order
it reached them, with the kinds of edge that reached each. A maker whose work was only handed to one of them is listed apart, as
being handed something is not using it, and the walk does not go through them. Nobody is weighed or ranked: that is an estimate, and
an estimate is an annotation.

## Writing credit

An estimator reads the record, then writes what it found beside the journal, in `annotations.sqlite`, with no runtime, on a live
session or a closed one. `Session.annotate` and the `annotate` command are the one way in, and each statement is checked against
the journal: it names its producer and version, the events it is about and rests on, and the `head` it read at, which names the
trace, and each of those events lies at or below that head. Its status is `scored`, `invalid`, `error`, `timeout` or `cancelled`,
and a value is given when it is `scored` and only then, so no other is ever zero; an event nobody said anything of is unscored,
which no status says. A team's reward targets its episode's `episode.closed`, an agent's its first `agent.started`, never the
spawn its spawner made, a turn's a `turn.started` and a call's its `model.called`. A second estimator, or a second version, writes
beside the first. This one is a toy, labelled as one, and its target is an event of each agent's own, the first the walk reached,
never a spawn:

```python
async def even_split(session, outcome):
    """A toy estimator: an even share of an outcome for each agent the record ties to it, which is a heuristic."""
    found = await session.contributors(outcome)
    agents = [row for row in found.rows if row.maker and row.maker.startswith("agent:")]
    for row in agents:
        await session.annotate(
            row.first,
            kind="credit",
            producer="even-split",
            producer_version="0",
            scope="team",
            status="scored",
            value=1 / len(agents),
            params={"outcome": outcome},
            evidence=[outcome],
            head_seq=found.head,
        )
    return await session.annotations()
```

A client shows a value only with its producer and version, beside any other estimate of the same target, and never sums two: the
terminal's and the browser's provenance list each under Credit and rewards, as it was said.

The SDK ships one producer, `platoon_harness.credit.propagate`, `propagate@1`, and it is a heuristic, run only when someone runs it.
It splits an episode's one team reward, on its `episode.closed`, over the refs the episode closed on; each event it reaches keeps
`retained` of what reached it for its maker and passes the rest equally along its causes, its previous version or a commit's parents,
and its citations, an agent's only where its exposure says `seen`, never along an offer. It writes one local `credit` row per agent it
reached, on that agent's first `agent.started`, and none for an agent it never reached, which stays unscored. Citing gives away all
but `retained` of what reaches the citer, and work nobody cites earns nothing from it, so training on it pulls against the default
template's request to cite. [training.md](training.md) shows it run.

## What can train

`eligibility` says whether an agent's work in one episode can train, from the record alone, and what trains is the training
system's to decide:

```python
async def what_can_train(session, agent, episode):
    """An agent's attribution and verdict in an episode, and each bar to training it or any call of its met."""
    answer = await session.eligibility(agent, episode)
    bars = [bar.reason for bar in answer.reasons]
    while True:
        bars += [bar.reason for call in answer.calls for bar in call.reasons]
        if answer.cursor is None:
            return answer.attribution, answer.verdict, bars
        answer = await session.eligibility(agent, episode, after=answer.cursor)
```

An agent is `exact` where every start of it recorded its trainable level met and no other agent's admission names any of its backend
ids, and `forked` once a native child of its harness is seen. Its bars are `not_trainable`, with the level its start recorded,
`shared_key`, for an entry of its backend ids another admission names too, `forked` and `no_end`, and a call's own are
`outside_episode`, `person`, for a turn a person held or a person's entry its agent was handed before it, and `purpose`, for a
purpose its harness gave other than `compaction`: a call reported with no purpose is its turn's. A program's message is no
person's. It reads the levels each start recorded, so a result kept or lost since changes no answer.

## From the command line

Each query is a command of its name, and prints its answer as JSON:

```console
$ platoon-harness lineage fix-auth --ref task/tasks/1@3
$ platoon-harness contributors fix-auth --ref task/tasks/1@3
$ platoon-harness exposure fix-auth --agent @lead --ref task/tasks/1@3
$ platoon-harness eligibility fix-auth --agent @lead --episode task-17
$ platoon-harness annotate fix-auth --target task/tasks/1@3 --kind credit --producer mine --producer-version 1 \
    --scope local --status scored --value 0.5 --head-seq 812
$ platoon-harness annotations fix-auth --target task/tasks/1@3
```

[examples/mixed-team](../examples/mixed-team/README.md) runs a team whose writes cite what they rest on, and asks `uses` and
`contributors` of its lead's answer.

A session closed before an upgrade changed a view refuses a query, naming the views behind its journal. `platoon-harness session
refold fix-auth` brings them up to it while no runtime holds the session, as a runtime does as it opens, and writes no event.
