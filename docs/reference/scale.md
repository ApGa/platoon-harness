# Scale

What the brief's Scale case costs on the real stack: 100 agents driving 100,000 events through the real kernel and
runtime, measured on the hardware below, and the budget a slow test holds each measurement to. Everything in the tables
but [A git team's looks](#a-git-teams-looks) was measured on 2026-11-08, in four runs one after another on one node, on
the code this page is published with but for the budgets, which were set from what the runs measured, and for docstrings
and an xdist option that change nothing a run without `-n` does.

`tests/integration/test_scale.py` makes the run and measures it, and
`tests/integration/test_tui_budgets.py`, `test_the_tui_attaches_to_a_100000_event_journal_within_its_budget`, attaches
the terminal UI to a run of its own. Each budget is twice the most that was measured, but half the least for
throughput, and no budget of time is under 50 ms, as twice a few milliseconds would fail on a busy host's noise alone. A
budget twice what was measured catches what doubles a cost, not what adds a half to it: a writer slowed by 4 ms a
commit, which made a round two fifths longer, passed the budgets a review held it to. The run takes some minutes and its
budgets fit this hardware, so no CI job runs it: run it by hand before each release, on hardware like this, and say what
it printed in the pull request. Run it without `-n`: under it, each worker that takes one of its tests makes the run
anew, at the same time as the others.

```bash
uv run pytest -q -s -m scale
```

The hardware of record, what counts as an agent here, budgets at twice the measured values, and that no CI job holds
them are the default, pending the owner's ruling, as [STATUS](../STATUS.md) says. So is measuring the roster and
attention snapshots, which are whole, rather than paging them. The 50 ms floor under each budget of time is this page's
addition to that default, pending the same ruling.

## What runs

- **100 agents, each a `ScriptedDriver`**, `member-1` to `member-100`, of one role in a mesh. They are scripted, not
  real harnesses: no model is asked anything. Each is a wire program in a process of its own, as a harness is, and
  calls our tools as real MCP over HTTP on loopback, so every call goes through the real tool plane, the real kernel and
  its writer. The runtime runs in a process of its own, as `Session.start(detach=True)` and the terminal UI start one,
  so what it measures of its own memory and CPU leaves the members out.
- **A round** begins with the person's post to `#rounds`, which wakes every member. In its turn a member tells the next
  member its news, waits in the call, with `hold`, to hear from the one before, reads its inbox and revises its notes
  on a board citing what it read, adds a task to a queue, claims one and completes it, tells the person, and says it is
  done. Once `member-1` has begun its turn, the person sends it a message, which steers into that turn, as a person's
  message to an agent does. The round ends when every member has ended its turn, and `session.metrics` is read then. A
  round writes some 4,100 events, 41 a turn.
- **Rounds go on until the journal holds 100,000 events**, which took 24 rounds each time. Then the person walks
  each query that pages, takes each whole snapshot and folds the journal into the page's projection, and the runtime is
  killed with SIGKILL in the middle of one more round and resumed. Last, with no runtime, every event is counted again.
- **The session's workspace is a folder no git repository holds**, so no look runs and no commit is recorded, and the
  changes snapshot holds nothing: it is not measured here.

## The hardware

The four runs had a share of one compute node, whose other cores other jobs used at the same time: the node's load
was 40 to 71 as each began.

| | |
|---|---|
| CPU | Intel Xeon Platinum 8558: two sockets of 48 cores, two threads a core |
| Cores the run could use | 32 of the node's 192 threads |
| Memory | 2 TiB |
| Filesystem of the session folder | xfs, on a local software RAID |
| Kernel | Linux 5.14.0, an Enterprise Linux 9.8 build |
| Python and SQLite | Python 3.12.13, SQLite 3.53.1 |

## What was measured

A range is the least and the most of the four runs. Other runs fall outside these ranges: a range says what four runs
on one node came to, not what every run will.

| Measurement | Measured | Budget |
|---|---|---|
| A round, from the person's post to the last member's end of turn | median 3.41 to 4.01 s, the fastest 3.19 to 3.57 s, the slowest 5.80 to 6.95 s | 8.1 s at the median |
| The runtime's peak memory, `VmHWM`, as `session.metrics` read it at each round's end | 61 MiB after the first round, 79 to 80 MiB at half the events and 100 to 106 MiB at the end, the second half adding 20 to 26 MiB | 212 MiB at the end, and 52 MiB added over the second half |
| Events committed a second, over the seconds since the runtime started, at the pace the members set: not the most the writer could commit | 950 to 1,109 a second, some 100,241 to 100,258 events in 7,447 to 7,965 commits | At least 475 |
| Ack latency, from joining the writer's queue to the answer after the commit, each percentile the upper edge of the quarter-octave bucket that holds it | p50 24.4 to 29.0 ms, p99 68.9 to 81.9 ms, the most 240 to 735 ms | p50 58 ms, p99 164 ms |
| A person's message sent while the members work, from the send until the runtime answers that it is recorded | p50 28 to 30 ms, the most 51 to 332 ms | 664 ms |
| The page's projection, folded from nothing as `web` folds it | 17 to 21 s | 42 s |
| What metrics cost: counting every event again from the journal, set beside the runtime's own CPU for each, which is taken as a bound on what the fold costs, as counting decodes each event and the fold does not | 13 to 16 µs an event, 1.1 to 1.3% of the 1,128 to 1,321 µs of CPU the runtime spent on each | 2.6% |
| A read of `session.metrics` at a round's end | p50 25 to 30 ms, the most 49 to 66 ms | 132 ms |
| A resume after a SIGKILL, until the runtime it starts answers | 6.7 to 7.7 s | 15.4 s |
| The same, until every member's harness is back | 6.7 to 7.8 s | 15.6 s |
| The terminal UI's attach, until it draws every member idle and the first one's transcript to its last turn | 0.39 to 0.43 s | 0.86 s |

### Memory

The runtime's peak memory rose through every run, and nothing here shows where it stops, so the brief's bounded memory
is not shown: the test holds the peak, and what the second half adds to it, to budgets and no more. Probes made by hand
on nodes of the same kind, which are not tests in this repository, found this much:

- **It grows with the journal.** One run to 1,000,000 events, with the members inside the runtime's process as this
  case first ran them, was resident in 119 MiB at 100,000 events, 261 MiB at 500,000, 319 MiB at 750,000 and 348 MiB
  at 1,000,000, its peak then 384 MiB: some 0.26 KiB an event past the first 100,000, rising more slowly past 750,000
  but still rising. Its rounds took 3.2 s at first and 4.1 s at the end.
- **It is the runtime's own.** A run to 150,000 events with each member a process of its own rose no slower than one
  with the members inside the runtime.
- **It is not Python's heap, and no connection piles up.** With the members outside it, what tracemalloc traced of the
  runtime's allocations stayed near 5 MiB once warm and its count of Python objects stayed flat, while its resident
  memory kept rising. It held at most nine descriptors on the journal throughout.
- **Nothing tried stops it.** In runs to 150,000 events, a page cache of 1 MiB a connection instead of 8 slowed it by a
  third, `malloc_trim` at each round's end by half, and two malloc arenas instead of one for each thread by three
  quarters, and in each it still rose; with two arenas, a run to 500,000 events still rose, and its rounds took a third
  longer.

So what rises is native memory. SQLite's page caches and glibc's arenas, one for each thread that runs a query, hold
some of it; what holds the rest, and whether it stops, is not known. The peak is `VmHWM`, which `session.metrics` reads
from `/proc`: `getrusage`, which it read before, gave 13 to 23 MiB less on this hardware.

### Each query that pages

Each op a person may ask that answers a page and takes an earlier answer's cursor as `after`, as the op table lists
them, and the journal's own read, each walked up to 8 pages, as the person, with nothing else running. The test fails if
the op table gains such an op it does not ask.

| Query | Asked of | Pages | First page | Slowest page | Budget |
|---|---|---|---|---|---|
| `board.query` | the notes board, with history | 8 | 1 to 2 ms | 1 to 2 ms | 50 ms |
| `channel.list` | | 1 | 1 to 2 ms | 1 to 2 ms | 50 ms |
| `contributors` | `member-1`'s notes | 1 | 6 to 7 ms | 6 to 7 ms | 50 ms |
| `eligibility` | `member-1`, in the run's episode | 1 | 12 to 27 ms | 12 to 27 ms | 54 ms |
| `interactions` | | 8 | 2.0 to 2.6 s | 2.0 to 2.6 s | 5.2 s |
| `lineage` | `member-1`'s notes | 3 | 4 to 5 ms | 4 to 5 ms | 50 ms |
| `message.read` | the person's inbox | 8 | 8 to 10 ms | 8 to 24 ms | 50 ms |
| `peers` | | 1 | 3 to 4 ms | 3 to 4 ms | 50 ms |
| `spans` | `member-1` | 1 | 18 to 23 ms | 18 to 23 ms | 50 ms |
| `task.list` | the work queue | 8 | 2 ms | 2 ms | 50 ms |
| `uses` | the first round's post | 4 | 2 ms | 2 ms | 50 ms |
| The journal's read | from the start | 8 | 8 to 23 ms | 11 to 29 ms | 58 ms |
| The journal's read | back from the head | 8 | 7 to 9 ms | 8 to 10 ms | 50 ms |
| The journal's read | one member's stream, from the start | 8 | 2 ms | 2 ms | 50 ms |

`interactions`, who reached whom, walks the journal to its head on every page and folds nothing, as
[RFC 0067](../rfcs/0067-who-reached-whom-is-counted-from-the-record-kind-by-kind.md) decides, so each of its pages costs
what the journal's length does.

### The whole snapshots

`view.watch`'s first answer for each, which is whole and not paged, and must fit one line of the RPC, 16 MiB.

| Snapshot | Rows | Bytes | Time | Budget |
|---|---|---|---|---|
| Roster | 100, one a member | 122,253 | 19 to 40 ms | 239 KiB, 80 ms |
| Attention | 2,400, each a mention of the person nobody read | 694,188 to 694,202 | 27 to 42 ms | 1,356 KiB, 84 ms |

Each roster row names its agent's harness, here a command that names this checkout's Python and a script in it, and its
workspace path, so the roster's bytes grow with where the checkout and the session live. The roster grows with the
agents, some 1,220 bytes each here, and attention with what is open in it, some 290 bytes a mention. At those sizes,
which is arithmetic and was not measured, one line would hold some 13,700 agents or some 58,000 open mentions.

## A git team's looks

What a round of looks costs a team in worktrees whose agents each commit each turn, as each turn's end requests a look
([architecture §13](../architecture.md#13-workspaces)), before and after a look waited only for looks of its own
workspace ([RFC 0077](../rfcs/0077-a-look-waits-only-for-looks-of-its-own-workspace.md)). A probe made by hand on
2026-11-08, which is not a test in this repository: N agents, each a scripted harness in the runtime's process, in
worktrees of a repository of 200 files, each committing a file of its own at each turn. A round is the person's message
to every agent, from the first send until every agent's look after that turn has finished, timed four times after a
first round that made the workspaces, in each of two runs of each, on 32 of the threads of a node of the kind above, one
node for 10 and 30 agents, whose load was 69 to 70, and another for 100, whose load was 12 to 16, with Git 2.47.3 and
the repository on xfs. A range is the least and the most of the eight rounds. The looks' git ran in the event loop's
pool, which there has the 32 threads that the host's own pool has now; the code with the host's own pool was not
measured.

| Agents | One look at a time in a session | One look at a time in a workspace |
|---|---|---|
| 10 | 0.74 to 0.77 s | 0.36 to 0.42 s |
| 30 | 3.5 to 3.6 s | 1.3 to 1.5 s |
| 100 | 27.1 to 30.3 s | 8.6 to 10.3 s |

A round still grows faster than the team: a look that finds a commit reads every workspace's HEAD reflog, one git
process each, to say whose it is, and every probe's look at the shared workspace waits for the one before. No budget
holds these, and no run measured real harnesses, a larger repository, snapshots or isolated agents here. The
architecture says [what runs at once](../architecture.md#what-runs-at-once) across agents and within one, with the tests
that show each.

## What is not measured

- **Bounded memory.** The runtime's memory grows with the journal, as [Memory](#memory) says.
- **Real harnesses.** Each is a process of its own, whose memory nothing here measures, and asks a model, which no run
  here does.
- **A git team in the Scale case, and the changes snapshot.** The Scale case runs no look, commit or diff, so what a
  look costs at each turn's end is only what [A git team's looks](#a-git-teams-looks) measured by hand, and the changes
  snapshot, which no run here fills, is not measured at 100 agents.
- **The writer's capacity.** The events committed a second are what the members' pace drove, not the most the writer
  could commit.
- **Many sessions in one process, 100 isolated agents**, and any system but Linux.
- **The budgets on other hardware.** A slower machine fails them and a faster one hides a regression, so a run
  elsewhere says how it compares, not whether it passed.
