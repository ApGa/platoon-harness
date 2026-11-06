# Training on sessions

A training system runs a session per rollout and trains on what its agents' model calls did. It builds on one contract, which this
page describes, and the SDK names no training system in it. The first to build on it is Platoon's `platoon-teams` extension, in
Platoon's own repository. [architecture.md](architecture.md) section 14 is the design of record.

What the SDK owns is execution and evidence: the session, its journal and what the record says of each agent. What the training
system owns is identity and model access, through its authority, and what trains.

## The authority

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
  words. A stop that a crash cut is said again, alike, so take a second telling as the first.
- **Budgets** stay the session's. Count steps at your gateway.

A refusal of yours wins: `admit` raises, and the spawn fails with your words. An admission is never retried.

## Who starts it

Start each rollout's session as a program, with the authority, and with `trainable=True`:

```python
async with Session.start(
    team, name=rollout_id, principal="program:trainer", authority=MyAuthority(), cwd=workdir, trainable=True
) as session:
    await session.open_episode("task")
    for agent in team.recipients():
        await session.send(agent, instruction)
    await session.settled()
    ...
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
- **End every agent, deepest first,** by `depth` and `state` from `session.agents()`: retire one at rest, and cancel one at work,
  as a `retire` of it is refused `conflict`. An agent with no end is `no_end`, so none of its calls can train, and `finish` hears of
  an agent only once it has ended: leaving a session stops it, and an agent still live then keeps no end.
- **Close the episode** on what each agent that started came to, with `close_episode(based_on=...)`: its `said`, in its row of
  `session.agents()` or in `session.status(agent)`, is the ref of its last words, its latest turn's last message or a finished
  agent's end, and None while it has said nothing since its latest turn began. Credit walks back from these refs, so an episode
  closed on an end the session wrote, or on nothing, credits nobody's work. What it was worth is an annotation's to say.

A session started trainable, or whose agents your authority admitted, is never resumed, as their keys went with it, even one a stop
cut short while an admit was under way. Read it as history.

## What can train

`session.eligibility(agent, episode)` answers from the record alone, alike after a rebuild, on a closed copy and with the
conformance store gone:

- **Attribution:** `exact` where every start of the agent recorded its trainable level met and no other agent's admission names its
  backend ids, `forked` once a native child of its harness is seen, whose calls go on its key, and None otherwise.
- **Verdict:** eligible when nothing bars it. An agent's bars are `not_trainable`, `shared_key`, `forked` and `no_end`, and a call's
  own are `outside_episode`, `person` and `purpose`; a call is eligible when its agent is and it has none.

[provenance.md](provenance.md#what-can-train) says what each bar means. What trains is still yours to decide.

## What a sealed launch is

A gateway goes only to a driver that declares `sealed`, and that driver launches its harness on the gateway's model with nothing of
the user's: no settings, extensions, skills or project instructions of theirs, no tool of the harness's own that acts, no native
agents and no retries. ScriptedDriver, pi, OpenHands and a wire program that declares it launch sealed; Claude Code, Codex, `exec`
and ACP do not, and a gateway admission to one fails, naming why.

- **The bearer goes only by environment,** under `PLATOON_HARNESS_BEARER`. A file the launch writes names the variable, as
  `${PLATOON_HARNESS_BEARER}`, never its value, so the session folder, which is your export, holds no key. A wire program finds the
  variable's name in its launch frame, beside your origin, model, tools and compaction headers.
- **Your environment's tools are a second MCP server,** named `environment`, at `Gateway.tools`, under the same bearer, beside the
  session's own tools.
- **Compaction stays on, and each compaction call carries your `compaction_headers`,** so your gateway tells it apart as it arrives
  and can keep it out of a step budget. The harness reports each such call as `model.call` of purpose `compaction`, with the id
  your model gave it: ScriptedDriver's `Compact` step, OpenHands' condenser, a wire program from its launch spec, and pi through
  the extension our driver loads, which runs pi's own `compact`, one call or two for a split turn, each with the headers and its id.
  Pi compacts when your gateway refuses a request as longer than its window, in its dialect's own words, and retries it once.
- **A sealed launch is earned, never declared.** `doctor --check`, or `check_driver` with `write_conformance` for a driver it ships
  no check of, runs `sealed_first_request_holds_only_ours` and `environment_tools_in_first_request` beside the rest, on `FakeModel`
  acting as a gateway, and keeps them in the one result an agent's levels read.

## Rewards and credit

Every reward and credit is an annotation, written through `Session.annotate` once the session has ended, on the session attached
with no runtime, so no context a policy could see held one. Its status is `scored`, `invalid`, `error`, `timeout` or `cancelled`, a
value is given when it is `scored` alone, and a target with no statement is unscored. A team's reward targets the episode's
`episode.closed`, and an agent's its first `agent.started`.

A producer writes what it estimates of one episode, and is one function, named by `module:attr`:

```python
async def produce(session: Session, episode: str, *, judge: Gateway | None, **params) -> None: ...
```

`judge` is model access for a producer that asks a model, or None. The SDK ships one, `platoon_harness.credit:propagate`,
`propagate@1`, a heuristic:

```python
from platoon_harness.credit import propagate

async with Session.attach(rollout_id) as ended:
    await propagate(ended, "task", judge=None, retained=0.5)
```

It reads the one team reward on the episode's close, and splits it over the refs the episode closed on. Each event it reaches keeps
`retained` of what reached it for its maker, and the rest goes equally along the event's causes, its previous version or a commit's
parents, and its citations, an agent's only where its exposure says Seen. It walks newest first, at most 4,096 events, and writes one
local `credit` row per agent it reached, on that agent's first `agent.started`, under the producer `platoon_harness.credit:propagate`.
An agent it never reached gets no row, so is unscored; a team reward that is not scored passes its status to each row; and a walk
cut short makes every row `invalid`. What reached the events of no agent is the reward less the rows.

Its incentive: citing gives away all but `retained` of what reaches the citer, and work nobody cites earns nothing from it. The
default template asks every agent to cite, so training under it pulls against that request: watch the citation rate. Rows like
these are fractions of the team reward, so a training system centres them per role, as Platoon's keyed credit does at a group size
above one.

## The export

The export is the session as it ended: its folder, closed, or stopped for a rollout cut short, with `annotations.sqlite` beside its
journal. It holds no key, as bearers lived only in the harnesses' environments. Read it with `Session.attach` once its runtime has
stopped: eligibility, lineage, exposure and annotations all answer on it, alike on a copy.

## Testing without a training system

`platoon_harness.testing` is what a training system's own tests build on:

- **`FakeModel` acts as your gateway.** `model.gateway(bearer)` gives a `Gateway` to its models, at its origin, and to an MCP
  server of one tool, `environment_ping`, at `/mcp`, which answers only a bearer it gave, with compaction headers of its own. It
  logs every request with its bearer and headers, gives each response an id in its body, and answers an `Overflow` in its script
  with each dialect's own refusal of a request too long for the model's window.
- **`ScriptedDriver` launches sealed** with no binary: its tool calls are real MCP, its `AskModel` step a real model call, and its
  `Compact` step a compaction call with the headers.
- **The contract test,** `test_a_managed_session_runs_as_a_training_authority_drives_it` in this repository's
  `tests/integration/test_contract.py`, runs your whole use of the SDK with no training system behind it, on ScriptedDriver and, in
  the slow pass, on pi and OpenHands.
