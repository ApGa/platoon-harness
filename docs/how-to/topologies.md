# Topologies

A topology says who may reach whom. It never says who acts next: control flow belongs in a
[Python program](#run-a-program-from-python). Everything else is ordinary grants over relations such as `parent` and `children`,
which stay true as agents come and go.

**Goal:** a team whose roles may reach whom you mean, from a preset, several presets, grants written out or a preset of your
own, checked before it spends anything.

**Prerequisites:** the SDK for the Python forms, from a checkout installed as [Install](../getting-started/install.md) says.
The TOML forms go in a team file, whose every key [the team file reference](../reference/team-file.md) lists.

Pick a preset, name your roles, and give whoever spawns a `may_spawn`. Every example here is a team, as TOML and as Python, and a test
checks that both forms build the same object and that `team.show()` prints what is shown. `team check` accepts each, and `run` runs
each but those under `until = "program"`, git-swarm's and the reviewers' of [Run a program from Python](#run-a-program-from-python),
whose session is its program's, a script that starts it.

```python
from platoon_harness.team import Budget, Role, Team
from platoon_harness.topology import (
    Queue,
    Topic,
    Topology,
    blackboard,
    git_swarm,
    manager_worker,
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

### git-swarm

A population with no messages and no roles to speak of: commits go to a shared repository, and nominations to a topic everyone reads,
with at most `live` agents at once, which is the topology's `max_live`. Its program, a Python script that starts the session as
`program:<name>`, starts the workers, writes each one's outcome on board `outcomes` and closes the session, so `run` and the terminal
UI refuse this team, naming [the script way](#run-a-program-from-python). The program starts every worker, so the role starts with
none, `count = 0`, and a budget bounds what they spend, as `team check` warns of a population with none.

```toml
[budget]
wall = "4h"

[roles.worker]
harness = "codex"
workspace = "worktree"
count = 0

[topology.git-swarm]
role = "worker"
live = 8
```

```python
team = Team(
    budget=Budget(wall="4h"),
    roles={"worker": Role(harness="codex", workspace="worktree", count=0)},
    topology=git_swarm("worker", live=8),
)
```

```text
Workers (codex, own worktrees) may message no one.
Workers post to topic `nominations`; everyone reads it. Readers fetch it when they choose. Everyone shares board `inflight`. The program writes board `outcomes`; everyone reads it. Limits: live 8. Closes when the program closes it.
```

Its program is `population`, from `platoon_harness.patterns`. It starts workers with your goal, as many at once as `live` allows,
until it has started `attempts`, and records each one's outcome on `outcomes` once it has ended. Closing the session is the script's:

```python
from platoon_harness import Session
from platoon_harness.patterns import population


async def swarm(session: Session) -> dict[str, str]:
    """Each worker's outcome, by its name, and the session closed. Run again on the session after a crash, it starts no
    worker and records no outcome twice."""
    outcomes = await population(session, "worker", "Make `pytest` pass, as TASK.md says.", attempts=32)
    await session.submit("session.close", key="close")
    return outcomes
```

A worker's outcome is one of five, which its worker is told beside its goal:

- `contribute`: it made commits in its worktree and nominated nothing.
- `nominate`: it sent one message to `#nominations` whose `based_on` cites one recorded commit, by the ref `repo.commit` gives for
  its SHA, and committed nothing.
- `abstain`: it did neither.
- `invalid`: it did anything else.
- `failed`: it ended any way but finishing. A worker whose turn ended with nothing more to come for it, as a failed turn leaves
  one, is retired, and fails.

Each is an entry on `outcomes` named for its worker, `<outcome>: <what>`, citing what it rests on, and the board takes no second.
A contribution's and a nomination's give the `sha` of its commit in their `fields`. Every outcome counts against `attempts`,
abstaining too, so a population that only abstains still ends. The population reads out no winner: choosing among the nominations
is yours, from the board. Workers start as `worker-1`, `worker-2` and on. A population keeps nothing, so run `swarm` again on the
session after a crash, with `Session.resume`, and it goes on from what the record holds.

A worker builds on a peer's commit by checking out the `sha` its entry records on its own branch, `git reset --hard <sha>`, which
its worker is told. Every worktree shares the repository's objects, so every commit a worker made is in each, and the look after the
builder's turn records its commit with the peer's as its parent. The runtime moves no branch: the worker moves its own. So a
population runs only in worktrees, and refuses any other workspace before it starts anyone, saying why: in `shared` every worker
works in one checkout, and a `snapshot` or an `isolated` workspace is a repository of its own, which holds no peer's commits.

[examples/git-swarm](../../examples/git-swarm/README.md) runs a population from a script, with no keys on stand-ins of its own, in
which one worker builds on another's commit and a third nominates the result.

## Mix presets

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
- **Two sources may not disagree.** Defining one channel, group, limit or `until` differently in two places is a load error that
  names both. Defining it alike is fine.

To use one preset twice, write an array of tables, `[[topology.pipeline]]`, or `|` two calls, and give each a different channel name.
Presets with fixed names (`pipeline`, `ring`, `git-swarm`) cannot be used twice over the same stage: write the second out.

## Merge worktrees through a queue

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

## Write a topology by hand

A preset is a macro. Anything it does, you can write yourself, and `team.show(resolved=True)` prints exactly what it expanded to, as
valid input. That form is what the manifest stores and hashes.

| Key under `[topology]` | Meaning |
|---|---|
| `edges` | Who may send to whose inbox, as `role = [selector, ...]`. `all` as a key means every role |
| `channels` | Each with `kind` (`topic`, `queue`, `board`), `writers`, `readers`, `delivery`, and settings for its kind |
| `groups` | `roles`, `members` (principal ids) or `order`, which `next` and `prev` walk. A group is addressed as `+name` |
| `limits` | `max_depth`, `max_children`, `max_live`, `max_hops` |
| `grants` | Plain `(who, ops, on)` rows, for an extension's ops |
| `until` | `settled`, `role:x`, or `program`, which leaves the session to the program that owns it |

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

## Run a program from Python

A topology holds no control flow. When a team needs some, such as handing out work and closing the session once it is done, a program
does it: a Python script that starts the session as `program:<name>` and acts through the ops a person has. `until = "program"`
leaves the session to the program that owns it, so `run` and the terminal UI refuse such a team, naming this way. Here the program
adds a task to `reviews` for each path, starts a reviewer to do them, and closes the session once each is done.

```toml
[roles.reviewer]
harness = "claude"
count = 0

[topology]
until = "program"

[topology.channels.reviews]
kind = "queue"
writers = "program"
readers = "role:reviewer"
```

```python
from collections.abc import Iterable
from typing import Any

from platoon_harness import Refused, Session

team = Team(
    roles={"reviewer": Role(harness="claude", count=0)},
    topology=Topology(until="program", channels={"reviews": Queue(writers="program", readers="role:reviewer")}),
)


async def review(session: Session, paths: Iterable[str]) -> dict[str, str]:
    """A task on `reviews` for each path, a reviewer to do them, and the session closed once each is done, giving what
    each came to. Each command's key says what it is for, so run again it acts once."""

    async def once(key: str, op: str, **args: Any) -> Any:
        outcome = await session.submit(op, key=key, **args)
        if outcome.refusal is not None:
            raise Refused.of(outcome.refusal)
        return outcome.result

    added = [await once(f"add {path}", "task.add", queue="reviews", gist=f"review {path}") for path in paths]
    await once("spawn", "agent.spawn", name="reviewer", child_role="reviewer", goal="Review each task on `reviews`.")
    await session.wait(tasks=[f"reviews/{task['task']}" for task in added])
    done = await session.task_list("reviews")
    await once("close", "session.close")
    return {task["gist"]: task["result"] for task in done["tasks"]}


async def main(paths: list[str]) -> None:
    async with Session.start(team, name="reviews", principal="program:reviews") as session:
        print(await review(session, paths))
```

```text
Reviewers (claude) may message no one.
The program adds to queue `reviews`; reviewers claim from it. Closes when the program closes it.
```

A program keeps nothing that must survive a restart. If its script dies, run it again on the session, with
`Session.resume("reviews")` in place of `Session.start`: each command it sent before is answered from the journal under the same key,
so it adds no task and starts no reviewer twice, and it goes on from there. `Session.submit` takes a key, while `Session`'s own
methods, such as `task_add`, choose a new one for each call, so send what must act once through `submit`, keyed by what it is for and
not by when it was sent: a second run can read what the first did not. The session issues no owner credential, so anyone who attaches
only reads, and it cannot detach: its runtime runs in the script's process, and the script leaving stops it, resumable.

## Check before you spend

`team_check` is a pure function that reports every problem at once, with a suggestion where it can make one. It takes what is known of
each harness, because a budget in a unit a harness cannot measure must never silently stop enforcing.

```python
from platoon_harness.team import Capabilities, team_check

known = {"claude": Capabilities(measures={"tokens", "usd"}), "codex": Capabilities()}
problems = team_check(team, capabilities=known)
```

It refuses recursive `may_spawn` with no `max_depth`, a wake cycle with no `max_hops`, a budget a role cannot measure, a sandbox its
harness lacks, a role that stays on a harness that cannot, a role's own `preamble` on a harness that reaches none of our tools, and
any preset, harness, extension, role, group or auth profile it cannot find. It warns about a role that can never start, a role with no
path to anyone, a relation no `may_spawn` makes true, an entry that can wake more than 8 agents, a wake cycle that runs through a child
that can stay, a role that lets its harness start agents of its own, saying what that gives up, a preamble that leaves out `{tools}` or
`{ending}`, words that name a tool a role cannot hold, and a team's `preamble` that a role on a harness that reaches none of our tools
is never told. It says nothing of `until = "program"`, as it checks a team before anyone starts it: a person's start of such a team
is refused, and a program's goes ahead. Under it, it warns of a role only the program starts, none with the session and no role by
`may_spawn`, when no budget, the role's or the session's, sets a limit: nothing in the team then bounds how many the program starts,
or what they spend. A program may bound them itself, as a population's `attempts` does, so it is a warning.

A cycle means a loop of wakes between roles. A reply up a tree is not one: `parent`, `children`, `ancestors` and `descendants` never
count, and neither does a channel that wakes no one. A parent and a child that can stay are the exception, as a message from the
parent wakes the child and its answer wakes the parent, for as long as they go on. Any child on a persistent harness can stay, since a
spawn may ask it to, so `team check` warns of every role that may spawn one and can message it, unless `max_hops` bounds them. The
`manager-worker` and `tree` presets bound them, at 8 unless you say otherwise.

## Write your own preset

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
