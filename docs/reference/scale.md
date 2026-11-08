# Scale

What the brief's Scale case costs on the real stack: 100 agents driving 100,000 events through the real kernel and
runtime, measured on the hardware below, and the budget a slow test holds each measurement to. Everything here was
measured on 2026-11-08, in four runs one after another, at the commits that added this page.

`tests/integration/test_scale.py` makes the run and measures it, and
`tests/integration/test_tui_budgets.py`, `test_the_tui_attaches_to_a_100000_event_journal_within_its_budget`, attaches
the terminal UI to a run of its own. Each budget is twice the most that was measured, and no budget of time is under
50 ms, as twice a few milliseconds would fail on a busy host's noise alone. The run takes some minutes and its budgets
fit this hardware, so no CI job runs it: run it by hand before each release, on hardware like this, and say what it
printed in the pull request.

```bash
uv run pytest -q -s -m slow tests/integration/test_scale.py \
  tests/integration/test_tui_budgets.py::test_the_tui_attaches_to_a_100000_event_journal_within_its_budget
```

The hardware of record, what counts as an agent here, and that no CI job holds the budgets are the default, pending the
owner's ruling, as [STATUS](../STATUS.md) says. So is measuring the roster, attention and changes snapshots, which are
whole, rather than paging them.

## What runs

- **100 agents, each a `ScriptedDriver`**, `member-1` to `member-100`, of one role in a mesh. They are scripted, not
  real harnesses: no model is asked anything. Each runs inside the runtime's own process, as a harness the runtime
  imports does, and calls our tools as real MCP over HTTP on loopback, so every call goes through the real tool plane,
  the real kernel and its writer. The runtime runs in a process of its own, as `Session.start(detach=True)` and the
  terminal UI start one.
- **A round** begins with the person's post to `#rounds`, which wakes every member. In its turn a member tells the next
  member its news, waits in the call, with `hold`, to hear from the one before, reads its inbox and revises its notes
  on a board citing what it read, adds a task to a queue, claims one and completes it, tells the person, and says it is
  done. Once half the members have begun, the person sends `member-1` a message, which its next read finds. The round
  ends when every member has ended its turn, and `session.metrics` is read then. A round writes some 4,100 events, 41 a
  turn.
- **Rounds go on until the journal holds 100,000 events**, which took 24 rounds each time. Then the person walks each
  query that pages, takes each whole snapshot and folds the journal into the page's projection, and the runtime is
  killed with SIGKILL in the middle of one more round and resumed. Last, with no runtime, every event is counted again.
- **The session's workspace is a folder no git repository holds**, so no look runs and no commit is recorded, and the
  changes snapshot is measured empty.

## The hardware

Each run had a share of a compute node, two runs on each of two nodes of one kind, whose other cores other jobs used
at the same time.

| | |
|---|---|
| CPU | Intel Xeon Platinum 8558: two sockets of 48 cores, two threads a core |
| Cores the run could use | 32 of the node's 192 threads |
| Memory | 2 TiB |
| Filesystem of the session folder | xfs, on a local software RAID |
| Kernel | Linux 5.14.0, an Enterprise Linux 9.8 build |
| Python and SQLite | Python 3.12.13, SQLite 3.53.1 |

## What was measured

A range is the least and the most of the four runs.

| Measurement | Measured | Budget |
|---|---|---|
| The runtime's peak memory, as `session.metrics` read it at each round's end | 66 to 70 MiB after the first round, 69 to 78 MiB at half the events and 82 to 97 MiB at the end, the second half adding 12 to 22 MiB | 194 MiB at the end, and 44 MiB added over the second half |
| Throughput: the events the writer committed over the seconds since the runtime started | 1,233 to 1,250 events a second, some 100,240 events in 7,889 to 8,122 commits | At least 615 |
| Ack latency, from joining the writer's queue to the answer after the commit | p50 24.4 ms each time, p99 57.9 to 68.9 ms, the most 83 to 115 ms | p99 140 ms |
| Interaction latency: a person's message sent while the members work, end to end | p50 33 to 41 ms, the most 59 to 72 ms | 145 ms |
| The page's projection, folded from nothing as `web` folds it | 17 to 18 s | 37 s |
| What metrics cost: counting every event again from the journal, which decodes each too, beside the CPU the runtime spent on each | 13 to 14 µs an event, 1.3 to 1.4% of the 982 to 1,007 µs of CPU the runtime spent on each | 2.8% |
| A read of `session.metrics` at a round's end | p50 20 to 23 ms, the most 45 to 49 ms | 100 ms |
| A resume after a SIGKILL, until the runtime it starts answers | 3.1 to 3.7 s | 7.5 s |
| The same, until every member's harness is back | 3.2 to 3.7 s | 7.5 s |
| The terminal UI's attach, until it draws every member idle and the first one's transcript to its last turn | 0.36 to 0.44 s | 0.9 s |

The peak rose through the second half of every run, by some 2 MiB a round at the end of the run that rose most, and
nothing here says where it stops: a longer run would. The fold that counts events costs the writer less than counting
again does, as the writer folds an event it has just made and decodes nothing. Each answered write puts its ack latency
in a bucket under the writer's lock, which is not measured apart from the writer.

### Each query that pages

Each op a person may ask that answers a page and takes an earlier answer's cursor as `after`, as the op table lists
them, and the journal's own read, each walked up to 8 pages, as the person, with nothing else running. The test fails if
the op table gains such an op it does not ask.

| Query | Asked of | Pages | First page | Slowest page | Budget |
|---|---|---|---|---|---|
| `board.query` | the notes board, with history | 8 | 2 ms | 2 ms | 50 ms |
| `channel.list` | | 1 | 1 ms | 1 ms | 50 ms |
| `contributors` | `member-1`'s notes | 1 | 6 to 7 ms | 6 to 7 ms | 50 ms |
| `eligibility` | `member-1`, in the run's episode | 1 | 12 to 13 ms | 12 to 13 ms | 50 ms |
| `interactions` | | 7 | 1.97 to 2.01 s | 1.99 to 2.01 s | 4.1 s |
| `lineage` | `member-1`'s notes | 3 | 4 ms | 4 ms | 50 ms |
| `message.read` | the person's inbox | 8 | 8 ms | 27 to 29 ms | 60 ms |
| `peers` | | 1 | 3 ms | 3 ms | 50 ms |
| `spans` | `member-1` | 1 | 18 ms | 18 ms | 50 ms |
| `task.list` | the work queue | 8 | 2 ms | 2 ms | 50 ms |
| `uses` | the first round's post | 4 | 2 ms | 2 ms | 50 ms |
| The journal's read | from the start | 8 | 7 ms | 9 to 10 ms | 50 ms |
| The journal's read | back from the head | 8 | 7 to 8 ms | 8 ms | 50 ms |
| The journal's read | one member's stream, from the start | 8 | 1 ms | 1 to 2 ms | 50 ms |

`interactions`, who reached whom, walks the journal to its head on every page and folds nothing, as
[RFC 0067](../rfcs/0067-who-reached-whom-is-counted-from-the-record-kind-by-kind.md) decides, so each of its pages costs
what the journal's length does.

### The whole snapshots

`view.watch`'s first answer for each, which is whole and not paged, and must fit one line of the RPC, 16 MiB.

| Snapshot | Rows | Bytes | Time | Budget |
|---|---|---|---|---|
| Roster | 100, one a member | 105,953 | 18 to 20 ms | 208 KiB, 50 ms |
| Attention | 2,400, each a mention of the person nobody read | 694,206 | 29 to 44 ms | 1,358 KiB, 90 ms |
| Changes | None, as no git repository holds the workspace | 63 | 1 ms | 126 bytes, 50 ms |

The roster grows with the agents, some 1,060 bytes each here, and attention with what is open in it, some 290 bytes a
mention. At those sizes, which is arithmetic and was not measured, one line would hold some 15,800 agents or some
58,000 open mentions.

## What is not measured

- **Real harnesses.** Each is a process of its own, whose memory nothing here measures, and asks a model, which no run
  here does.
- **A git team.** No look, commit or diff ran, so neither did what a look costs at each turn's end, and the changes
  snapshot held nothing.
- **Many sessions in one process, 100 isolated agents**, and any system but Linux.
- **The budgets on other hardware.** A slower machine fails them and a faster one hides a regression, so a run
  elsewhere says how it compares, not whether it passed.
