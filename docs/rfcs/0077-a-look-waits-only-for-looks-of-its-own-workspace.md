# RFC 0077: A look waits only for looks of its own workspace

| | |
|---|---|
| Status | Draft |
| Created | 2026-11-08 |
| Authors | Apurva Gandhi (`ApGa`) |
| Builds on | [`runtime/host.py`](../../packages/sdk/src/platoon_harness/runtime/host.py), [`tools/mcp.py`](../../packages/sdk/src/platoon_harness/tools/mcp.py), [architecture sections 4](../architecture.md#what-runs-at-once), [10](../architecture.md#10-tool-plane) and [13](../architecture.md#13-workspaces), [RFC 0005](0005-daemons-and-effects.md), [RFC 0009](0009-tools-only-mcp-server.md) and [RFC 0032](0032-the-runtime-looks-and-never-moves-a-branch.md) |
| Discussion | The owner's request of 2026-11-08, that tool calls and their execution run in parallel across agents that share one tool server, as faster wall clock is one of the benefits of several agents. The request accepts no design: this one waits for the owner's acceptance |
| Implementation | `fix: Run an agent's query on a reader thread, so a slow one holds up no other call`, `test: Show agents' shell tools run at once on each real binary, and measure one response's calls`, `feat: Look at different workspaces at once, each after the shared one` and `fix: Run the host's git and files on threads of its own, so no round of looks holds up a query` |

## Summary

A look at a workspace waits only for another look at the same workspace, and looks at different workspaces run at once. Each
probe still looks at the shared workspace first and at its agent's own after, so a worker whose base holds the shared workspace's
new commits finds them recorded before its own, as [RFC 0032](0032-the-runtime-looks-and-never-moves-a-branch.md) decided. Beside
it, a query an agent calls runs off the event loop on a thread of the loop's pool, as a person's already does, and the host's git
and files run on threads of their own, so a slow query holds up no other call while a thread is free. With these, one agent waits
for another only where the two share a thing: the journal's one writer, the shared workspace's look, the tool server's 1,024
connections and the readers' pool of threads. How a harness takes the calls of one response is its own, and holds up no other
agent.

## Motivation

The owner asked that tool calls and their execution run in parallel across the agents of a team that share one tool server. Most
already did: every harness is a process of its own, the tool server answers each request on a connection of its own, and the host
gives each effect a task of its own. Two things did not.

- **Looks ran one at a time in a session.** `Host._look` held one lock across both of a probe's looks, so the looks of a team of N
  agents in worktrees, each committing each turn, queued behind each other at every turn's end, though each reads its own work
  tree. A look's cost grows with the team, as it reads every workspace's HEAD reflog to say whose a new commit is, so a round of
  looks grew faster than the team. Measured on 32 hardware threads of a compute node, a round of such a team, from the person's message to
  every agent until every look after that turn had finished, took 0.74 to 0.77 s for 10 agents, 3.5 to 3.6 s for 30 and
  27 to 30 s for 100, against 0.36 to 0.42 s, 1.3 to 1.5 s and 8.6 to 10.3 s with looks one at a time per workspace. RFC 0032 had
  weighed concurrent looks only as looks deduplicated by the op, which "would race on the shared workspace's last look, which every
  look takes".
- **A query an agent called ran on the event loop.** The tool server ran `Kernel.query` on the runtime's loop, so one slow query,
  such as an extension's, held up every agent's calls, every harness's reports and every daemon until it returned. The core's
  queries an agent holds read a view and are quick, and the control link already ran a person's query, which may walk the
  journal, off the loop.

## Proposal

### 1. One look at a time per workspace, the shared one first in each probe

`Host._looking` is a lock per workspace, `shared` or `@ada`, where it was one lock for the session. A probe takes the shared
workspace's lock, looks at it and records what is new, lets it go, then takes its agent's own workspace's and does the same; a
stop's look does the same before it ends its workspace. Each look reads its workspace's last reading, and every workspace still on
disk, under its own lock, so it starts from where the last look of that workspace ended. So:

- **Two looks of one workspace never overlap.** Each starts from the reading the last one recorded, and a rewrite or a reading is
  recorded once, as before. Every probe looks at the shared workspace, so those looks still queue: that is the one look every agent
  shares.
- **The shared workspace comes first in every probe.** A worker's own look starts only once its probe's look at the shared
  workspace has recorded what it found, so a commit made in your checkout before the worker's workspace was, which its base holds
  and its own look leaves out, is recorded before the worker's commits that rest on it, and an `Informed-By` that cites it resolves.
- **Parents still come first.** Looks of different workspaces interleave their pages, and `repo.report` passes over a commit the
  journal holds. Each look lists its commits parents first, and leaves out only what the session started with, its workspace's
  base, which the shared look before it recorded, and its own last look's head, which that look recorded, so a commit's parents
  the journal will hold are recorded before it, whichever look records them.
- **Whose a commit is does not change.** It is read from the HEAD reflogs, which git writes when the commit is made, so it never
  depended on which look ran first. Which look records a commit first, and so its `found_in`, now depends on which finishes first,
  as it depended on which probe started first. `found_in` says where its diff is read, which any repository that holds the commit
  serves, and whether its code is confined, which matters only for a commit an isolated agent made, and another workspace finds
  that only once it has fetched it from the isolated one.

### 2. A query an agent calls runs off the event loop, and the host's work on threads of its own

The tool server runs a query an agent calls on a thread of the loop's default pool, as the control link runs a person's. A query
holds a read transaction of its own and writes nothing, so it can run beside the writer and other readers. That pool has four
threads more than the CPUs Python counts, and 32 at most: Python 3.12 counts the machine's CPUs, and 3.13 those the process may
use. So a slow query holds up no other call while a thread is free, and past that, queries wait for one.

Looks of different workspaces run at once (1), and each holds a thread for as long as its git runs, so in that pool a round of
looks would leave every reader, an agent's query or a person's, waiting behind git. The host's blocking work, its git, the
making of its drivers and its files, runs on a pool of its own instead, as many threads as the loop's and shared by the sessions
of one process, and readers share the loop's pool with the kernel's blob writes alone.

### 3. Slow work in an extension is an effect its daemon performs

An op runs inside the writer's transaction, one at a time with every other command of the session, and holds the writer while it
runs, by [law 3](../architecture.md#3-laws). So an extension's op does what it can at once and requests an effect for anything
slow, which a daemon of the extension's performs on the event loop, with its slow part in a thread or a process of its own, and
reports back through an op. Its query is read off the loop, so a slow one holds up only its own call while a thread is free.

## Alternatives

| Alternative | Why not |
|---|---|
| Keep looks one at a time in a session | A round of looks grew faster than the team: 27 to 30 s for 100 agents in worktrees, where per workspace it took 8.6 to 10.3 s |
| Concurrent looks deduplicated by the op, RFC 0032's alternative | Two looks of one workspace would race on its last reading, which a lock per workspace prevents |
| Look at the shared workspace once for the probes that queue on it together | What that queue costs apart from the rest of a look was not measured, and a probe would have to know that the look it shares began after its worker's base was made |
| A thread pool of the tool server's own for queries | Queries are not the loop's pool's only readers, as a person's queries and the kernel's blob writes are there too, and what would fill it is the host's git, so the host's work is what moves |
| A cap on looks at once, in the loop's pool | One more number to choose, and the host's other git, a spawn's worktree, a stop's and a diff, would still share the readers' pool |

## Consequences

- A team of agents in worktrees records its commits some three times sooner at 100 agents, and twice as soon at 10, on the node
  measured. A round of looks still grows with the team, as each look reads every workspace's HEAD reflog, and the shared
  workspace's looks still queue.
- An agent's slow query costs only its own call while a thread of the loop's pool is free; past its threads, queries wait for
  one, behind other readers and blob writes and never behind the host's git. What a saturated pool costs is not measured.
- The look's promise in architecture section 13 changes from one at a time in a session to one at a time in a workspace, and its
  test with it: `test_looks_run_one_at_a_time` becomes `test_looks_of_one_workspace_run_one_at_a_time`, beside
  `test_looks_of_two_workspaces_run_at_once_each_after_the_shared_one`.
- Nothing of the journal, the op table or the team file changes.

## Open questions

1. Whether a look should read only the reflogs of the workspaces that could have made what it found, where it reads every
   workspace's, one git process each, whenever it finds a commit. Nothing here measures what that would save, and it changes how
   whose a commit is gets read ([RFC 0032](0032-the-runtime-looks-and-never-moves-a-branch.md)), so it is the owner's to ask for.

## Evidence

- The cost of the session-wide lock, a probe by hand on 2026-11-08 and not a test in this repository: one script ran a team of N
  scripted agents in worktrees of a repository of 200 files, each committing a file of its own each turn, for four rounds after
  the first, twice for each N, on the code of `fix: Run an agent's query on a reader thread, so a slow one holds up no other call`
  and on the same code with the `host.py` of `feat: Look at different workspaces at once, each after the shared one`, on Git
  2.47.3, Python 3.12.13 and xfs, in jobs of 32 hardware threads on two nodes of two Intel Xeon Platinum 8558, whose other threads
  other jobs used. The looks' git ran in the event loop's pool there, which on those nodes has the 32 threads the host's own pool
  has now; the code with the host's own pool was not measured. [scale.md](../reference/scale.md#a-git-teams-looks) has the
  numbers.
- Tests: [tests/unit/runtime/test_looks.py](../../tests/unit/runtime/test_looks.py),
  `test_looks_of_two_workspaces_run_at_once_each_after_the_shared_one`, whose looks of two agents' own workspaces each wait until
  both are in, which fails under one lock in a session, and which finds a commit made in your checkout before both workspaces
  recorded before either agent's, `test_looks_of_one_workspace_run_one_at_a_time`, and `test_a_held_look_holds_up_no_query`,
  whose person's query answers while a look is held with the loop's pool cut to one thread;
  [tests/unit/tools/test_mcp.py](../../tests/unit/tools/test_mcp.py),
  `test_several_agents_calls_are_in_flight_at_once_a_held_wait_among_them`, whose queries each answer only once all are in,
  which a query on the loop never lets happen; and [tests/unit/tools/test_shim.py](../../tests/unit/tools/test_shim.py),
  `test_one_agent_s_calls_through_the_shim_are_in_flight_at_once`.
- On each real binary against FakeModel, `test_several_agents_run_their_shell_tools_at_once` and
  `test_what_one_response_runs_at_once`, which [compatibility.md](../reference/compatibility.md#tool-calls-at-once) records.
