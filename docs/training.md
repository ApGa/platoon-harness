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
  access it had, as a resume is no second admission.
- **`Gateway`** is the agent's model access. Its `origin` is a scheme and a host and nothing more, as no URL of a gateway's carries
  a credential: the bearer alone does, and the harness's words are masked of it in every form. Its `model` is the one pinned, which
  a role may name only as it is. `tools` is the URL of the environment's own MCP server, under the same bearer, and
  `compaction_headers` are what each call a harness makes to compact its context carries, so the gateway can tell such a call apart
  when it is made. Only a driver that declares the capability `sealed` is given a gateway, and its agent's login is `gateway`.
- **`backend`** is your ids for the agent. The admit effect records them as its result, which is the one join between an agent of
  the session and yours: no key is recorded, an admission whose backend names one of its own secrets is refused, and a gateway
  admission must name backend ids.
- **`finish`** tells you how an agent ended, with its report, the gist and then the body its end keeps. A stop that a crash cut is
  said again, alike, so take a second telling as the first.
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
  `ask`, which nobody answers; a harness's own agents allowed, whose calls go on their parent's key; a workspace other than `shared`
  or `isolated`; and an `until` only a person reaches.
- **Close the episode** on the refs of what each agent that started reported, with `close_episode(based_on=...)`. What it was worth
  is an annotation's to say.

A session whose agents your authority admitted is never resumed, as their keys went with it. Read it as history.

## What can train

`session.eligibility(agent, episode)` answers from the record alone, alike after a rebuild, on a closed copy and with the
conformance store gone:

- **Attribution:** `exact` where every start of the agent recorded its trainable level met and no other agent's admission names its
  backend ids, `forked` once a native child of its harness is seen, whose calls go on its key, and None otherwise.
- **Verdict:** eligible when nothing bars it. An agent's bars are `not_trainable`, `shared_key`, `forked` and `no_end`, and a call's
  own are `outside_episode`, `person` and `purpose`; a call is eligible when its agent is and it has none.

[provenance.md](provenance.md#what-can-train) says what each bar means. What trains is still yours to decide.

## Rewards

Every reward and credit is an annotation, written through `Session.annotate` once the session has ended, on the session attached
with no runtime, so no context a policy could see held one. Its status is `scored`, `invalid`, `error`, `timeout` or `cancelled`, a
value is given when it is `scored` alone, and a target with no statement is unscored. A team's reward targets the episode's
`episode.closed`, and an agent's its first `agent.started`.

## Not yet

The drivers' sealed launches, the environment's tools as a second MCP server, compaction sent with your headers and reported with
its id, the testing kit's gateway on `FakeModel`, the shipped producer `propagate@1` and the contract test are still to land, and
[STATUS.md](STATUS.md) says which have.
