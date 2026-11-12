# Training on sessions

A training system runs a session per rollout and trains on what its agents' model calls did. It builds on one contract, which this
page describes, and the SDK names no training system in it. Section 14 of [the architecture](../architecture.md) is the design.

What the SDK owns is execution and evidence: the session, its journal and what the record says of each agent. What the training
system owns is identity and model access, through its authority, and what trains.

**Goal:** a training system that runs a session per rollout, admits each agent through a gateway of its own, asks the record
what can train, and writes rewards and credit beside the journal.

**Prerequisites:**

- the SDK, `pip install platoon-harness`;
- a gateway of yours that records each call on a bearer as one agent's, or `FakeModel` in its place, as
  [testing without a training system](#test-without-a-training-system) shows;
- roles on harnesses whose drivers launch sealed: ScriptedDriver, pi, OpenHands or a wire program that declares it
  ([What a sealed launch is](#what-a-sealed-launch-is)).

## Write the authority

A session admits each agent through an `Authority`. A training system's admits it through a gateway of its own:

```python
from platoon_harness.config import Secret
from platoon_harness.runtime import Admission, AgentOutcome, AgentRef, Gateway, SpawnRequest


class MyAuthority:
    async def admit(self, spawn: SpawnRequest) -> Admission:
        agent_id = await my_backend.open(spawn.role, spawn.goal, parent=spawn.parent)  # Yours to do.
        gateway = Gateway(
            origin="http://127.0.0.1:8100",
            bearer=Secret(my_backend.key_of(agent_id)),
            model="my-policy",
            tools="http://127.0.0.1:8100/tools",
            compaction_headers={"X-My-Call-Kind": "aux"},
        )
        return Admission(token=Secret(fresh_token()), access=gateway, backend={"agent_id": agent_id})

    async def finish(self, agent: AgentRef, outcome: AgentOutcome) -> None:
        await my_backend.close(agent.agent, outcome.status, outcome.report)
```

- **`spawn`** names the agent, its role, the principal that spawned it, as its `agent.spawned` records it, or None for one the
  session started, and its goal. `resumed` asks again for an agent this runtime admitted, whose harness comes back: give it the
  backend ids and the access it had, as a resume is no second admission. One that gives others loses the agent, saying why, as its
  calls would go on an identity the record does not name.
- **`Gateway`** is the agent's model access. Its `origin` is a scheme and a host and nothing more, as no URL of a gateway's carries
  a credential: the bearer alone does, to the origin alone, and the harness's words are masked of it in every form. Its `model` is
  the one pinned, which a role may name only as it is. `tools` is the URL of the environment's own MCP server, at the origin under
  the same bearer, and `compaction_headers` are what each call a harness makes to compact its context carries, so the gateway can
  tell such a call apart when it is made. No URL or header of it may hold the bearer in any form, and no header may authorize a
  call. A secret the SDK cannot know, such as another agent's key in a path, is yours to keep out of every URL. Only a driver that
  declares the capability `sealed` is given a gateway, and its agent's login is `gateway`.
- **A bearer is one agent's.** Your gateway records each call on a bearer as one agent's, so an admission on a bearer another agent
  of the session holds is refused, and the spawn fails, in words that name no key.
- **`backend`** is your ids for the agent. The admit effect records them as its result, which is the one join between an agent of
  the session and yours. Each entry names this agent alone: an id of something agents share, such as their rollout, bars every
  agent that names it from training, as `shared_key`. No key or value may hold a secret of the admission's own, in any form, and a
  gateway admission must name backend ids.
- **`finish`** tells you how an agent ended: its `status`, `finished`, `cancelled`, `retired`, `lost` or `failed`, and its
  report, the gist, which is the agent's own for a finish and the session's words for any other end, and then the body, its last
  words. A child that ended with its parent is `cancelled` only if a turn of its was under way, and `retired` otherwise, even on
  its way to a turn, as its parent's end cut no turn of its. It comes last in the agent's
  stop, once its harness has ended or failed to, and until it returns the agent's parent is handed nothing and a `wait` the
  parent holds open does not answer `released`, so settle the agent there and return once you have. A parent at work on its own
  when the agent ended can still read of the end first, by a call it makes. A stop that a crash cut is said again, alike, so take
  a second telling as the first.
- **Budgets** stay the session's. Count steps at your gateway.

A refusal of yours wins: `admit` raises, and the spawn fails with your words. An admission is never retried.

## Start each rollout's session

Start each rollout's session as a program, with the authority, and with `trainable=True`, and end every agent before you close
the episode:

```python
async with Session.start(
    team, name=rollout_id, principal="program:trainer", authority=MyAuthority(), cwd=workdir, trainable=True
) as session:
    await session.open_episode("task")
    for agent in team.recipients():
        await session.send(agent, instruction)
    await session.settled()
    for row in sorted(await session.agents(), key=lambda row: row["depth"], reverse=True):
        if row["state"] != "ended":
            try:
                await session.retire(f"@{row['agent']}")
            except Refused as refused:  # `conflict`: it is at work, which only a cancel ends.
                if refused.refusal.code != "conflict":
                    raise
                await session.cancel_agent(f"@{row['agent']}")
    said = [row["said"] for row in await session.agents() if f"@{row['agent']}" in team.recipients()]
    await session.close_episode(based_on=[ref for ref in said if ref is not None])
```

- **A program is no person.** Its message goes as its reader's setting says, and its session issues no owner credential, so anyone
  who attaches can watch and nobody can steer.
- **`team.recipients()`** is whom a session's prompt goes to: every agent the session starts, or the one named.
- **`trainable=True`** checks the team as you start it, before any harness launches: `trainable_problems(team)`, which reads the
  team alone, as a load check can with no driver to ask, and then each role's driver, for a sealed launch and a result kept under
  the root that proves trainable for the harness it would run. `platoon-harness team check --trainable` runs the same check, so run
  it, and `platoon-harness doctor --check`, on each machine that runs rollouts before you spend anything.
- **What `trainable_problems` refuses:** a model or an auth profile a role names, as your gateway gives both; approvals left to
  `ask`, which nobody answers, by the session's own `approvals` where it states one and else by each role's; a harness's own agents
  allowed, whose calls go on their parent's key; a workspace other than `shared` or `isolated`; and an `until` only a person
  reaches.
- **Under `until = "program"`, wait on your own condition.** Such a session is done only when its program closes it, so
  `settled()` would wait until the budget ran out, or for ever with none: wait instead on what your program does, such as
  `session.wait` on the tasks it added, as [Run a program from Python](../how-to/topologies.md#run-a-program-from-python) does,
  then end every agent.
- **End every agent, deepest first,** by `depth` and `state` from `session.agents()`: retire one at rest, and cancel one at work,
  as a `retire` of it is refused `conflict`. An agent with no end is `no_end`, so none of its calls can train, and `finish` hears of
  an agent only once it has ended: leaving a session stops it, and an agent still live then keeps no end. One that does not stay
  has ended already, `finished`, at a turn that stopped with nothing more to come for it, its last words its report, so a team whose
  roles do not stay settles on its own. Its `said` names the message that said those words, which its end carries.
- **Close the episode** on what each agent that started came to, with `close_episode(based_on=...)`: its `said`, in its row of
  `session.agents()` or in `session.status(agent)`, is the ref of its last words. For a finished agent it is what its end's report
  carries: for an `agent.finish` with a gist or a body, its `agent.finished` in a turn and its `agent.ended` out of one, and else
  the latest turn's last message, whose words the report took, or its `agent.ended` where that turn said nothing. For any
  other it is its latest turn's last message, and None while it has said nothing since that turn began. Credit walks back from
  these refs, so an episode closed on an end the session wrote, or on nothing, credits nobody's work. What it was worth is an
  annotation's to say.

A session started trainable, or whose agents your authority admitted, is never resumed, as their keys went with it, even one a stop
cut short while an admit was under way. Read it as history.

## What can train

`session.eligibility(agent, episode)` answers from the record alone, alike after a rebuild and on a closed copy, whether an
agent's calls in an episode can train: an agent is barred by `not_trainable`, `shared_key`, `forked` or `no_end`, and a call
by `outside_episode`, `person` or `purpose`. A call your gateway recorded that no harness reported has no call id to join, so it
never trains. [provenance.md](../how-to/provenance.md#what-can-train) says what each bar means; what trains is yours to decide.

**Labels.** Give your team a vocabulary for its work, each label with the values it may take, and its agents label the tasks they
add and the agents they spawn, from it alone, as their tools' schemas show them:

```toml
[labels]
difficulty = ["easy", "medium", "hard"]
kind = ["design", "execution", "search", "verification"]
```

`session.spans(agent)` gives each span the labels of the work it was done for, and the claims it held, so a baseline can be kept
per label and a span trained against the one its labels name:

```python
async with Session.attach(rollout_id) as ended:
    for span in (await ended.spans("@worker")).spans:
        key = None if span.labels is None else tuple(sorted(span.labels.items()))
```

A span's labels are those of the task its agent held while its calls were made, else those it was spawned with, else none, `{}`;
a span that claimed a task carries the task's for its calls before the claim too. `None` is unknown, as where it held tasks of
different labels at once, and has no key: what trains on it is yours to decide. A span's `claims` are `None` where the record
cannot say which it held, as for a claim tied to no call in a turn that was cut. The creator decides a task's labels, and its
claimant trains against them, so a policy that learns to call its work hard lowers the baseline its claimants are measured by:
watch what each label's work comes to.

## What a sealed launch is

A gateway goes only to a driver that declares `sealed`, which launches its harness on the gateway's model with nothing of the
user's: no settings, extensions, skills or project instructions, no tool of the harness's own that acts, no native agents and
no retries. ScriptedDriver, pi, OpenHands and a wire program that declares it launch sealed; Claude Code, Codex, `exec` and ACP
do not, and a gateway admission to one fails, naming why. [drivers.md](drivers.md#a-sealed-launch) says how each keeps these
out. What a trainer can count on:

- **The bearer goes by environment alone,** under `PLATOON_HARNESS_BEARER`, so the session folder, which is your export, holds
  no key.
- **Your environment's tools are a second MCP server,** named `environment`, at `Gateway.tools`, under the same bearer: pi and
  ScriptedDriver show a tool of yours as `mcp__environment__finish`, and OpenHands as `environment_finish`. Agents' calls
  arrive at once ([what runs at once](../architecture.md#what-runs-at-once)), so a server that runs tools one at a time
  across the agents sharing it makes them take turns.
- **Each compaction call carries your `compaction_headers`,** and is reported as `model.call` of purpose `compaction`, with
  the id your model gave it. Pi compacts only when your gateway refuses a request as longer than its window, in its dialect's
  own words, and then retries it once.
- **A sealed launch makes no call but its turns' and its compactions',** as it retries nothing and warms no cache.
- **It is earned, never declared.** `doctor --check`, or `check_driver` with `write_conformance`, proves on `FakeModel` acting
  as a gateway that the first request goes under the bearer, holds none of the project's instructions and shows only our
  tools and the environment's.

## Write rewards and credit

Every reward and credit is an annotation, written through `Session.annotate` once the session has ended, on the session attached
with no runtime, so no context a policy could see held one. Its status is `scored`, `invalid`, `error`, `timeout` or `cancelled`, a
value is given when it is `scored` alone, and a target with no statement is unscored. A team's reward targets the episode's
`episode.closed`, an agent's its first `agent.started`, and a span's the `model.called` of its last call, which names it in
`session.spans(agent)`.

A producer writes what it estimates of one episode, and is one function, named by `module:attr`:

```python
async def produce(session: Session, episode: str, *, judge: Gateway | None, **params) -> None: ...
```

`judge` is model access for a producer that asks a model, or None. The SDK ships one, `platoon_harness.credit:propagate`,
`propagate@4`, a heuristic:

```python
from platoon_harness.credit import propagate

async with Session.attach(rollout_id) as ended:
    await propagate(ended, "task", judge=None, retained=0.5)
```

It reads the one team reward on the episode's close, and splits it over the refs the episode closed on, refusing `invalid` an
episode that closed on none. Each event it reaches keeps `retained` of what reached it for its maker, and the rest goes equally,
one share each, along the event's causes, its previous version or a commit's parents, its citations, an agent's only where its
exposure says Seen, and its takes: the events, but its own agent's, shown by offers its agent's harness confirmed taking before a
call of its span, since the call before and the agent's latest start or resume, and below the event's own bound. An event in no
span takes nothing, nor does an entry that carries an event, as a child's report does, which reaches that event, and what it took,
as its cause; and an offer the harness never said it took is no edge. It walks newest first, at most 4,096 events. What an
agent's event keeps is that agent's, and also its span's when the event lies in one: the span holding the model call that made it,
for an entry that carries an event, as a child's report does, that event's, and for an event tied to no call its turn's, when that
turn is one span; but what a claimant's event of a claim keeps, the claim, and the completion, failure or release that ended it,
is shared equally by the spans that held the claim, and kept by the event's own span only where none did. It writes, under the
producer `platoon_harness.credit:propagate`, one local `credit` row per span it reached, on the span's name, and one per agent it
reached, on that agent's first `agent.started`, holding all that agent's events kept. A span or an agent it never reached gets no
row, so is unscored; a team reward that is not scored passes its status to each row; and a walk cut short, or one that meets an
edge to an event no older than its own, makes every row `invalid`. What reached the events of no agent, or of one that never
started, as one whose launch failed, which has no start for a row to target, is the reward less the agents' rows, and what an
agent kept in no span, such as an end out of a turn that nothing joins to a call, is its row less its spans' rows, and no span's
row holds it.

What credit reaches depends on what you close on, so close each topology on what its team came to:

- **A tree:** its root's `said`, what its finish's report carries. Its citations of its children's reports carry credit where it
  was shown them, and so do the reports its finishing span took. A helper's report that a credited span took is reached cited or
  not, and keeps all that reaches it on the span that wrote it unless it cites something. An agent's citation carries credit only
  where its harness took what it cites, and nothing hands an agent its own post unless it reads it back, so a helper that wants its
  crafting span reached reads its post back and cites it.
- **A mesh whose peers never finish:** each starting peer's `said`, the last message of its last turn, which cites nothing. It
  keeps `retained` and passes the rest along what its span took: other peers' messages, board entries, children's reports.
- **A queue:** each task's result, which a program closes on. A result keeps a share for the spans that held its claim and
  passes the rest to its claim, as its cause and its previous version, and to what its span took; the claim keeps a share for
  the same spans. A queue closed on its worker's last words credits only the worker's last span, but a lead whose last words took
  its workers' results, as `task.list` shows them, reaches every span that held their claims.

A worker that claims and completes three tasks in one turn, a model call for each step, closed on the three results, has three
spans, each holding its own task's result and claim, and the spans hold 5/24, 2/9 and 2/9: the task statement each claim showed,
and the message that began the turn, take a share each, for nobody. Where a call completes one task and claims the next, the
span that held the claim keeps its share. A worker that crafts with the environment's tools in one span, says how far it has
come, which cuts its turn, and completes the task in the next, is credited in both: both held its claim.

Its incentives: citing, and taking, give away all but `retained` of what reaches the event, being cited or taken by a credited
span earns credit, broadcasting draws more takes, reading in a last turn costs, and work nobody cites or takes earns nothing from
it. The default template asks every agent to cite, so training under it pulls against that request: watch the citation rate, and
what each span read and sent. Rows like these are fractions of the team reward, so center them per role across your rollouts. A
span's row is a slice of its agent's, so pooling spans as agents of their
own would tie an agent's advantage to how many spans it was cut into: center agents' rows per role, train each scored span's calls
on its row less its agent's baseline shared equally by that agent's scored spans, and the calls no scored span holds on nothing.

## The export

The export is the session as it ended: its folder, closed, or stopped for a rollout cut short, with `annotations.sqlite` beside
its journal. It holds no key, as bearers lived only in the harnesses' environments. Nor does it hold an agent's harness's
scratch or a file its driver names as where its harness kept a credential, once that agent has ended and its stop has run,
which removes them before your `finish` hears of the end. So end every agent, as above, and wait until your `finish` has heard
of each before you leave the session: a stop that has not begun when the session stops runs only at a resume, which a
trainable session never has, and an agent that has not ended keeps them. The scratch goes whole, with pi's
full text of a tool result it cut among it, which its transcript names by a path that then names nothing; what the model was
shown stays. Read it with `Session.attach` once its runtime has stopped: eligibility, lineage, exposure and annotations all
answer on it, alike on a copy. To show what a model call took in, read each offer its harness said it took, a
`context.offered` its `context.delivered` names, with `Session.shown(offer)`: the text each item showed, a gist as it was
shown, with any fields beside it, and a body or the lines of one, or None where the journal does not prove it by the item's
digest. The form a gist is shown in is the SDK's to change, so read it there.

## Test without a training system

`platoon_harness.testing` is what a training system's own tests build on:

- **`FakeModel` acts as your gateway.** `model.gateway(bearer)` gives a `Gateway` to its models, at its origin, and to an MCP
  server of three tools, `ENVIRONMENT_TOOLS`, at `/mcp`, which answers only a bearer it gave, with compaction headers of its own.
  The tools are `ENVIRONMENT_TOOL`, `ping`, and `finish` and `think`, named as harnesses name tools of their own. It
  logs every request with its bearer and headers, gives each response an id in its body, and answers an `Overflow` in its script
  with each dialect's own refusal of a request too long for the model's window.
- **`ScriptedDriver` launches sealed** with no binary: its tool calls are real MCP, its `AskModel` step a real model call, and its
  `Compact` step a compaction call with the headers.
- **An example to read:** this repository's `tests/integration/test_contract.py`, whose
  `test_a_managed_session_runs_as_a_training_authority_drives_it` runs a training system's whole use of the SDK with none
  behind it, on ScriptedDriver, pi and OpenHands.
