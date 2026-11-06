# Topologies

A topology says who may reach whom. It never says who acts next: control flow belongs in a Python program. Everything else is
ordinary grants over relations such as `parent` and `children`, which stay true as agents come and go.

Pick a preset, name your roles, and give whoever spawns a `may_spawn`. Every example here is a team, as TOML and as Python, and a test
checks that both forms build the same object and that `team.show()` prints what is shown. `team check` accepts each but the two that
need a program, map-reduce and git-swarm, which it refuses until programs run: see [STATUS.md](STATUS.md).

```python
from platoon_harness.team import Role, Team
from platoon_harness.topology import (
    Queue,
    Topic,
    Topology,
    blackboard,
    git_swarm,
    manager_worker,
    map_reduce,
    mesh,
    pipeline,
    ring,
    star,
    tree,
)
```

## The presets

### manager-worker

A lead fills a queue, workers claim from it, and everyone shares a board. Claiming is competitive, so the lead never has to assign.
Workers cannot talk to each other. A lead and a worker that stays can wake each other with follow-ups and answers, so it bounds hops:
8 unless you say otherwise.

```toml
[roles.lead]
harness = "claude"
may_spawn = ["worker"]

[roles.worker]
harness = "codex"
workspace = "worktree"

[topology.manager-worker]
manager = "lead"
workers = "worker"
```

```python
team = Team(
    roles={
        "lead": Role(harness="claude", may_spawn=["worker"]),
        "worker": Role(harness="codex", workspace="worktree"),
    },
    topology=manager_worker("lead", "worker"),
)
```

```text
lead (claude) may message its workers and you. Workers (codex, own worktrees) may message lead.
lead adds to queue `tasks`; workers claim from it. Everyone shares board `notes`. Limits: hops 8. Closes when lead finishes.
```

### tree

Agents delegate downward and report upward. A finished child's result reaches its parent through the monitor, so a parent can
simply wait for its children. A recursive role must say how deep it may go, and a parent and a child that stays bound their hops, 8
unless you say otherwise.

```toml
[roles.agent]
harness = "pi"
may_spawn = ["agent"]

[topology.tree]
role = "agent"
max_depth = 6
max_children = 4
```

```python
team = Team(
    roles={"agent": Role(harness="pi", may_spawn=["agent"])},
    topology=tree("agent", max_depth=6, max_children=4),
)
```

```text
Agents (pi) may message their children, their parent and you.
Limits: depth 6, children 4, hops 8. Closes when every agent has finished.
```

### mesh

Peers message each other directly and share their group's topic, `+peers`, which wakes no one, so a post costs nothing until the next
turn. A direct message does wake, so a mesh bounds hops: 8 unless you say otherwise. Give it a list of roles to mix harnesses in one
mesh. If peers spawn peers, set `limits.max_depth`, and `on_parent_exit = "adopt"` on the role so that a peer outlives whoever started
it.

```toml
[roles.peer]
harness = "claude"
count = 4

[topology.mesh]
role = "peer"
board = "notes"
```

```python
team = Team(
    roles={"peer": Role(harness="claude", count=4)},
    topology=mesh("peer", board="notes"),
)
```

```text
Peers (claude) may message +peers and you.
+peers is every peer. +peers share board `notes`. Limits: hops 8. Closes when the session settles.
```

### star

Everything goes through a hub, which may also announce on a topic, and which a person can reach. Spokes never reach each other.

```toml
[roles.dispatcher]
harness = "claude"

[roles.scout]
harness = "codex"
count = 3

[topology.star]
hub = "dispatcher"
spokes = "scout"
topic = "orders"
```

```python
team = Team(
    roles={"dispatcher": Role(harness="claude"), "scout": Role(harness="codex", count=3)},
    topology=star("dispatcher", "scout", topic="orders"),
)
```

```text
dispatcher (claude) may message scouts and you. Scouts (codex) may message dispatcher.
dispatcher posts to topic `orders`; scouts read it. Limits: hops 8. Closes when the session settles.
```

### blackboard

No messages at all: agents coordinate through shared artifacts, with a queue of open work if you want one.

```toml
[roles.analyst]
harness = "pi"
count = 4

[topology.blackboard]
role = "analyst"
board = "findings"
queue = "leads"
```

```python
team = Team(
    roles={"analyst": Role(harness="pi", count=4)},
    topology=blackboard("analyst", board="findings", queue="leads"),
)
```

```text
Analysts (pi) may message no one.
Analysts share queue `leads`. Analysts share board `findings`. Closes when the session settles.
```

### pipeline

Each stage feeds a queue for the next, so a stage can have several agents. `back` lets every later stage return work to the first, and
a loop like that must bound its hops. A queue with `delivery = "wake"` announces work; it never assigns it.

```toml
[roles.author]
harness = "codex"

[roles.reviewer]
harness = "claude"

[roles.verifier]
harness = "pi"
sandbox = "read-only"

[topology.pipeline]
stages = ["author", "reviewer", "verifier"]
back = true
max_hops = 6
```

```python
team = Team(
    roles={
        "author": Role(harness="codex"),
        "reviewer": Role(harness="claude"),
        "verifier": Role(harness="pi", sandbox="read-only"),
    },
    topology=pipeline(["author", "reviewer", "verifier"], back=True, max_hops=6),
)
```

```text
author (codex) may message no one. reviewer (claude) may message no one. verifier (pi) may message no one.
reviewer and verifier add to queue `to-author`; author claims from it. Each entry wakes its readers. author adds to queue `to-reviewer`; reviewer claims from it. Each entry wakes its readers. reviewer adds to queue `to-verifier`; verifier claims from it. Each entry wakes its readers. Limits: hops 6. Closes when the session settles.
```

### ring

A pipeline whose last stage feeds the first, for a stated number of laps: each announcement carries its hops, so `max_hops` stops it.

```toml
[roles.writer]
harness = "claude"

[roles.critic]
harness = "codex"

[topology.ring]
stages = ["writer", "critic"]
laps = 3
```

```python
team = Team(
    roles={"writer": Role(harness="claude"), "critic": Role(harness="codex")},
    topology=ring(["writer", "critic"], laps=3),
)
```

```text
critic (codex) may message no one. writer (claude) may message no one.
writer adds to queue `to-critic`; critic claims from it. Each entry wakes its readers. critic adds to queue `to-writer`; writer claims from it. Each entry wakes its readers. Limits: hops 6. Closes when the session settles.
```

### map-reduce

A program holds all the control flow: it shards work to mappers and folds their results through reducers. Mappers cannot read each
other's results, and the program, not an agent, closes the session. No program runs yet, so `team check` refuses this team, naming it.

```toml
[roles.mapper]
harness = "codex"
count = 16

[roles.reducer]
harness = "claude"

[topology.map-reduce]
map = "mapper"
reduce = "reducer"
parallel = 16
```

```python
team = Team(
    roles={"mapper": Role(harness="codex", count=16), "reducer": Role(harness="claude")},
    topology=map_reduce("mapper", "reducer", parallel=16),
)
```

```text
Mappers (codex) may message no one. reducer (claude) may message no one.
The program adds to queue `map`; mappers claim from it. The program adds to queue `reduce`; reducer claims from it. Mappers and reducer write board `results`; the program and reducer read it. Program `map_reduce` runs it. Closes when the program finishes.
```

### git-swarm

A population with no messages and no roles to speak of: commits go to a shared repository, and a program tallies nominations at the end.
No program runs yet, so `team check` refuses this team, naming it.

```toml
[roles.worker]
harness = "codex"
workspace = "worktree"
count = 8

[topology.git-swarm]
role = "worker"
live = 8
episodes = 64
```

```python
team = Team(
    roles={"worker": Role(harness="codex", workspace="worktree", count=8)},
    topology=git_swarm("worker", live=8, episodes=64),
)
```

```text
Workers (codex, own worktrees) may message no one.
Workers post to topic `nominations`; everyone reads it. Readers fetch it when they choose. Everyone shares board `inflight`. Program `population` runs it. Closes when the program finishes.
```

## Mixing

Presets are a union, so write as many as you like, in any order. In TOML that means several tables under `[topology]`, plus any keys of
your own; in Python, `|`. Here a lead runs a recursive team of workers, with a channel for alerts added by hand. `until` makes the tree
agree with the manager on when the session closes.

```toml
[roles.lead]
harness = "claude"
may_spawn = ["worker"]

[roles.worker]
harness = "codex"
may_spawn = ["worker"]

[topology.manager-worker]
manager = "lead"
workers = "worker"

[topology.tree]
role = "worker"
max_depth = 3
max_children = 4
until = "role:lead"

[topology.channels.alerts]
kind = "topic"
writers = "human"
readers = "all"
delivery = "steer"
```

```python
team = Team(
    roles={
        "lead": Role(harness="claude", may_spawn=["worker"]),
        "worker": Role(harness="codex", may_spawn=["worker"]),
    },
    topology=(
        manager_worker("lead", "worker")
        | tree("worker", max_depth=3, max_children=4, until="role:lead")
        | Topology(channels={"alerts": Topic(writers="human", readers="all", delivery="steer")})
    ),
)
```

```text
lead (claude) may message its workers and you. Workers (codex) may message their children, their parent and you.
lead adds to queue `tasks`; workers claim from it. You post to topic `alerts`; everyone reads it. Each entry steers its readers. Everyone shares board `notes`. Limits: depth 3, children 4, hops 8. Closes when lead finishes.
```

Three rules keep this safe:

- **Order never matters.** Any arrangement of the same parts gives the same hash.
- **There is no `deny`.** Grants only add up, and anything not granted is refused.
- **Two sources may not disagree.** Defining one channel, group, limit, `program` or `until` differently in two places is a load error
  that names both. Defining it alike is fine.

To use one preset twice, write an array of tables, `[[topology.pipeline]]`, or `|` two calls, and give each a different channel name.
Presets with fixed names (`pipeline`, `ring`, `map-reduce`, `git-swarm`) cannot be used twice over the same stage: write the second out.

## A merge queue for worktrees

Workers in worktrees of their own hand their branches to one merger, rather than merge each other's: a `merges` queue the workers
add to and a `merger` role claims from, the merger in a worktree of its own. It is a queue and a role, so it is written out and is no
preset. The runtime never merges: the merger merges each branch a task names into its own branch with git, and the look after its turn
records the merge commit as the merger's, or the merge under way and its conflicted paths, which put the merger under Needs you while
it rests on them. On a conflict the merger completes the task with a result naming the paths, and the worker reads it from its task,
by `task.list` or by a `wait` on `task/merges/<id>`, which whoever adds to a queue may do. A worker that does not stay waits so, as a
turn that ends with nothing left to wait for ends it, and a lead that does not stay is kept while a worker of its waits, as its end
would retire that worker. `task.fail` is no way back to the worker: it returns the task to the queue's readers, the merger, until it
dies. Each role's `instructions` say this to its agents: a worker adds a task naming its branch, and a merger merges what it claims
and completes it with what came of that.

```toml
[roles.lead]
harness = "claude"
may_spawn = ["worker"]

[roles.worker]
harness = "codex"
workspace = "worktree"

[roles.merger]
harness = "claude"
workspace = "worktree"

[topology.manager-worker]
manager = "lead"
workers = "worker"

[topology.channels.merges]
kind = "queue"
writers = "role:worker"
readers = "role:merger"
```

```python
team = Team(
    roles={
        "lead": Role(harness="claude", may_spawn=["worker"]),
        "worker": Role(harness="codex", workspace="worktree"),
        "merger": Role(harness="claude", workspace="worktree"),
    },
    topology=(
        manager_worker("lead", "worker")
        | Topology(channels={"merges": Queue(writers="role:worker", readers="role:merger")})
    ),
)
```

```text
lead (claude) may message its workers and you. merger (claude, own worktree) may message no one. Workers (codex, own worktrees) may message lead.
Workers add to queue `merges`; merger claims from it. lead adds to queue `tasks`; workers claim from it. Everyone shares board `notes`. Limits: hops 8. Closes when lead finishes.
```

## Writing it out

A preset is a macro. Anything it does, you can write yourself, and `team.show(resolved=True)` prints exactly what it expanded to, as
valid input. That form is what the manifest stores and hashes.

| Key under `[topology]` | Meaning |
|---|---|
| `edges` | Who may send to whose inbox, as `role = [selector, ...]`. `all` as a key means every role |
| `channels` | Each with `kind` (`topic`, `queue`, `board`), `writers`, `readers`, `delivery`, and settings for its kind |
| `groups` | `roles`, `members` (principal ids) or `order`, which `next` and `prev` walk. A group is addressed as `+name` |
| `limits` | `max_depth`, `max_children`, `max_live`, `max_hops` |
| `grants` | Plain `(who, ops, on)` rows, for an extension's ops |
| `program` | Optional control flow, in Python, by name |
| `until` | `settled`, `program` or `role:x` |

**Selectors** are the same everywhere: `self parent children siblings ancestors descendants next prev human program all role:x group:x`.
A channel in a team has no agent to be relative to, so its `writers` and `readers` use only `human`, `program`, `all`, `role:x` and
`group:x`.

**Delivery** is set by the reader, so a sender cannot buy a wake: `pull`, `next-turn`, `wake`, or `steer`, which asks for the earliest
boundary the harness has. A role's `delivery` does the same for its inbox, and is `wake` unless you say otherwise.

```toml
[roles.lead]
harness = "claude"

[roles.worker]
harness = "codex"
count = 2

[topology]
edges = { lead = ["role:worker"], worker = ["role:lead"] }
limits = { max_hops = 4 }

[topology.channels.tasks]
kind = "queue"
writers = "role:lead"
readers = "role:worker"
lease = "1h"
```

```python
team = Team(
    roles={"lead": Role(harness="claude"), "worker": Role(harness="codex", count=2)},
    topology=Topology(
        edges={"lead": ["role:worker"], "worker": ["role:lead"]},
        limits={"max_hops": 4},
        channels={"tasks": Queue(writers="role:lead", readers="role:worker", lease="1h")},
    ),
)
```

```text
lead (claude) may message workers. Workers (codex) may message lead.
lead adds to queue `tasks`; workers claim from it. Limits: hops 4. Closes when the session settles.
```

## Checking before you spend

`team_check` is a pure function that reports every problem at once, with a suggestion where it can make one. It takes what is known of
each harness, because a budget in a unit a harness cannot measure must never silently stop enforcing.

```python
from platoon_harness.team import Capabilities, team_check

known = {"claude": Capabilities(measures={"tokens", "usd"}), "codex": Capabilities()}
problems = team_check(team, capabilities=known)
```

It refuses recursive `may_spawn` with no `max_depth`, a wake cycle with no `max_hops`, a budget a role cannot measure, a sandbox its
harness lacks, a role that stays on a harness that cannot, a role's own `preamble` on a harness that reaches none of our tools, a
program, since none runs yet, and any preset, harness, extension, role, group or auth profile it cannot find. It warns about a role
that can never start, a role with no path to anyone, a relation no `may_spawn` makes true, an entry that can wake more than 8 agents, a
wake cycle that runs through a child that can stay, a role that lets its harness start agents of its own, saying what that gives up, a
preamble that leaves out `{tools}` or `{ending}`, words that name a tool a role cannot hold, and a team's `preamble` that a role on a
harness that reaches none of our tools is never told.

A cycle means a loop of wakes between roles. A reply up a tree is not one: `parent`, `children`, `ancestors` and `descendants` never
count, and neither does a channel that wakes no one. A parent and a child that can stay are the exception, as a message from the
parent wakes the child and its answer wakes the parent, for as long as they go on. Any child on a persistent harness can stay, since a
spawn may ask it to, so `team check` warns of every role that may spawn one and can message it, unless `max_hops` bounds them. The
`manager-worker` and `tree` presets bound them, at 8 unless you say otherwise.

## Your own preset

A preset is a plain function that returns a `Topology`. Its TOML table is named after it, with dashes for underscores, and its keys are
its arguments. List it on an extension and it has the same power as a built-in. Installing the extension activates nothing: a team must
name it.

```python
from platoon_harness.kernel import Extension


def pair_review(author: str, reviewer: str) -> Topology:
    """An author and a reviewer who talk directly, bounded by hops."""
    return Topology(edges={author: [f"role:{reviewer}"], reviewer: [f"role:{author}"]}, limits={"max_hops": 8})


extension = Extension("pairing", presets=[pair_review])
```

```toml
extensions = ["pairing"]

[roles.author]
harness = "codex"

[roles.reviewer]
harness = "claude"

[topology.pair-review]
author = "author"
reviewer = "reviewer"
```

```python
team = Team(
    extensions=["pairing"],
    roles={"author": Role(harness="codex"), "reviewer": Role(harness="claude")},
    topology=pair_review("author", "reviewer"),
)
```

```text
author (codex) may message reviewer. reviewer (claude) may message author.
Limits: hops 8. Closes when the session settles.
```
