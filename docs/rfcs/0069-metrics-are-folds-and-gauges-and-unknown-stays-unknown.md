# RFC 0069: Metrics are folds and gauges, and unknown stays unknown

| | |
|---|---|
| Status | Draft |
| Created | 2026-11-08 |
| Authors | Apurva Gandhi (`ApGa`) |
| Builds on | [`kernel/writer.py`](../../packages/sdk/src/platoon_harness/kernel/writer.py), [`kernel/txn.py`](../../packages/sdk/src/platoon_harness/kernel/txn.py), [`primitives/clients.py`](../../packages/sdk/src/platoon_harness/primitives/clients.py), [architecture sections 5, 6 and 16](../architecture.md#16-observability), [the brief's section 12](../spec/BRIEF.md#12-reliability-security-and-scale), [RFC 0004](0004-one-operation-table.md), [RFC 0044](0044-a-level-is-earned-on-the-machine-that-runs-it.md) and [RFC 0052](0052-a-reward-has-five-statuses-and-eligibility-is-read-from-the-record.md) |
| Discussion | Milestone 4's plan and the critiques of its first draft, kept outside this repository |
| Implementation | `feat: Give the kernel's writer gauges public names`, `feat: Answer session.metrics, unknown where nothing measured` |

## Summary

`session.metrics`, a query op that is no agent's tool, with `Session.metrics` and the command `session metrics`, says how a
session runs from two sources. Counters that are folds: a view, `Counters`, counts each event by its type and each journaled
refusal by its code as it commits, so counting adds no journal write and reading walks nothing. And the kernel's gauges: a live
kernel keeps in memory what its writer has measured since it opened the journal, the events and commits, the writes queued and
the most there were, the commands in flight by principal, the writes refused `busy` and each write's ack latency, and what its
process has used, and gives them by public names as `Gauges`, through `Kernel.gauges()` and, to an op, `Txn.gauges()`. Beside
them the answer reads the views it already has: agents by the roster's groups, agents by the trainable level their latest start
recorded, each surface's declared coverage with what is proved, and gaps by kind. Each metric section 16 names is defined in a
sentence. What nothing measured is None, never zero, and `unknown` names it with why: the gauges where no runtime answers, ack
latency before any write, memory where the system gives it in no unit checked here, and what an agent's harness processes use,
which nothing measures. A person or a program reads it, on a view credential too, and no agent does.

## Motivation

[Architecture section 16](../architecture.md#16-observability) names `session.metrics` and what it reads: throughput, ack
latency, queue depth, failures, active and blocked agents, resource use, provenance coverage and training eligibility, with
counters as folds, so that instrumentation adds no journal write. [The brief's section
12](../spec/BRIEF.md#12-reliability-security-and-scale) asks for the same list and for bounded instrumentation overhead. None of
it exists. The numbers the writer keeps, `_depth`, `_inflight` and `_batch_seconds`, are private, and a primitive may use only
public kernel names (law 11), so no op can read them. `session.status` says where a session stands and what blocks it, not how
much or how fast. A person watching a long session cannot tell a busy writer from a stuck one, or whether the runtime's memory
grows. A program supervising one has nothing to poll, and milestone 4's scale tests need throughput, ack latency and memory
read through public names.

The danger is the one law 10 names. A closed session has no writer, so a depth and a latency of zero would say an idle writer
where nothing measured one. A host whose memory we cannot read would report no memory. And the harnesses' processes, which
nothing measures, would read as using nothing.

## Proposal

### 1. Counters are a fold

```python
class Counters(View):
    # v_counters(type, events) and v_counters_refused(code, events)

    @fold("*")
    def counted(self, event: Event) -> None: ...  # one upsert, two for an `op.refused`
```

It counts every event by its type, and each `op.refused` by its code as well, in the writer's own transaction. Being a fold, it
adds no journal write (section 16), drops and refolds as any view does, answers alike on a closed copy, and is refolded as a
writer opens a session from before it. It sees every event, as `Waits` does, because it cannot name what it counts. `busy` is
never journaled (section 5.7), so it is the writer's to count.

### 2. The writer's gauges, by public names

```python
class Gauges(BaseModel, frozen=True):
    seconds: float                    # since the kernel opened the journal for writing
    events: int                       # committed since
    commits: int                      # transactions committed since, one fsync each
    depth: int                        # writes queued or in the open transaction now
    deepest: int                      # the most there were at once
    in_flight: dict[str, int]         # the commands among them, by principal
    busy: int                         # writes refused for want of room, which no journal holds
    acks: int                         # writes answered
    ack_p50: float | None             # from joining the queue to the answer after the commit
    ack_p99: float | None
    ack_max: float | None
    cpu_seconds: float                # the process's, user and system, since it started
    peak_resident_bytes: int | None   # the most memory the process has held

class Kernel:
    def gauges(self) -> Gauges | None: ...  # None from a read-only kernel, which measures nothing

class Txn:
    def gauges(self) -> Gauges | None: ...  # the kernel's, as an op reads them
```

A write is what the writer takes: a command, a body or a rebuild. The writer already takes its lock to admit a write and to
answer it, and keeps the gauges under that lock: one more clock reading as a write joins the queue and one for each batch
answered, and one bisection into 97 buckets for each write. Ack latency runs from joining the queue to the answer, after the commit that made the write durable
(law 4). The buckets are a quarter octave wide, from 10 µs to about two minutes, with one more for the rest. A percentile is the
nearest rank's bucket bound, or the slowest ack where that is lower, so it is never below the true one and at most 19% above it,
or 10 µs: a budget held against it errs on the safe side. CPU is `time.process_time()`. Peak memory is `getrusage`'s
`ru_maxrss`, which Linux gives in KiB; anywhere else it is None, since its unit there is unchecked here: macOS documents bytes
(UNVERIFIED, as nothing has run there).

`Txn` gains one member: an op receives `me`, `now`, `view`, `gauges`, `emit` and `effect`. Law 3 holds, since the gauges are
memory and two system calls about the process itself, so an op that reads them still waits on nothing. Law 11 holds, since the
primitives read them through the name any extension would. A read-only kernel has none: it measures nothing, and the process
reading a closed journal is not the one that ran it.

### 3. The op

```python
class Metrics(Model):
    head: int
    events: dict[str, int]                   # by type, from Counters
    refused: dict[str, int]                  # by code, from Counters
    agents: dict[Group, int]                 # the roster's groups, now
    trainable: dict[str, int]                # met, unmet, unverified or unrecorded
    coverage: dict[Surface, dict[str, int]]  # observed, partial, none or undeclared
    proved: tuple[Surface, ...]
    gaps: dict[str, int]                     # by kind
    gauges: Gauges | None
    unknown: dict[str, str]                  # each metric nothing measured, with why

@op("session.metrics", query=True)
def session_metrics(txn: Txn, a: Args) -> Metrics: ...
```

It is a query, so it enters no history, and it reads one read transaction, at `head`. `Session.metrics()` and the command
`platoon-harness session metrics SESSION` reach it, as they reach every op a person may run, the command on a view credential.

### 4. Each metric in a sentence

| Metric | What it is | Read from |
|---|---|---|
| Throughput | The events and the transactions the writer committed since the runtime started, over the seconds since: `gauges.events`, `gauges.commits` and `gauges.seconds`. `events` says what the whole record holds, by type | The gauges, and `Counters` |
| Ack latency | The time from a write joining the writer's queue to its answer, after the commit that made it durable, for every write answered since the runtime started: `ack_p50`, `ack_p99` and `ack_max` over `acks` | The gauges |
| Queue depth | The writes queued or in the open transaction now, the most there were at once, and the commands each principal has among them: `depth`, `deepest` and `in_flight` | The gauges |
| Failures | The refusals the journal holds, by code, in `refused`; the writes refused `busy`, which it never holds, in `gauges.busy`; and, among `events`, the effects that failed or became uncertain, the turns lost, the daemon runs that failed and the tasks failed: `effect.failed`, `effect.uncertain`, `turn.lost`, `daemon.failed` and `task.failed`. An agent that failed or was lost stands in the roster's `failed` group | `Counters`, the gauges and the roster |
| Active and blocked agents | How many agents stand in each of the roster's groups now, `needs_you`, `working`, `blocked`, `idle`, `done` and `failed`, by the one function that draws the roster | The roster |
| Resource use | The CPU seconds and the peak resident memory of the process holding the journal. What an agent's harness processes use is unknown | The gauges |
| Provenance coverage | For each surface, how many agents' latest start declared it observed, partial or none, or declared nothing, beside the surfaces a stored result proves, read from the set `exposure` decides by, which holds none today; and the gaps the record holds, by kind | `Exposures`, `Gaps` |
| Training eligibility | How many agents' latest start recorded their trainable level met, unmet or unverified, or recorded none. An agent's work can train only where it is met; whether its work in an episode can, with each call's bars, is `eligibility`'s to say | `Agents` |

A group nobody stands in, a surface nobody declared and a level nobody recorded are counted zeros, which the fold and the views
know. A type absent from `events` is a type no event has, since the fold counts every one.

### 5. Unknown stays unknown

`unknown` names each metric nothing measured, with why:

| Key | When | Why |
|---|---|---|
| `gauges` | No runtime answered: a read-only kernel, as on a closed session | Only the runtime holding a session measures its writer and its process |
| `ack_latency` | No write answered since the runtime started | Nothing has been timed |
| `peak_resident_bytes` | Anywhere but Linux | The system gives it in no unit checked here |
| `harness_resources` | Always | Nothing measures what an agent's harness processes use, only the process holding the journal |

Each such field is None, never zero.

### 6. Who reads it

A person or a program reads it, on a view credential too, and it writes nothing. No agent does: no grant a preset compiles
reaches it for an agent, it is no tool, so neither MCP nor `ph` lists it, and it refuses an agent `not_permitted` whatever its
grants, as `repo.test` does. An agent's read is evidence (law 9), and a query records none. That is the default, pending the
owner's ruling (Open questions).

## The hard parts

- **What it costs the writer.** One upsert per event in the writer's transaction, and per write a clock reading and a bisection
  under a lock it already takes. Measured below, the difference is inside the noise of a loaded host. Milestone 4's scale tests
  measure it on the real stack and hold it to a budget, as the brief asks.
- **What it costs to read.** The agents' groups are the roster's, drawn by the roster's own function, which reads every open
  attention row. At 20,000 open mentions a reading took about 110 ms, nearly all of it there, and everything else under 5 ms.
  A second, cheaper way to group agents would drift from what the roster draws. If the scale tests find the roster past its
  budget, the remedy serves both.
- **Three horizons.** Counters cover the record since the session began, the views stand now, and the gauges run since the
  runtime started, so a resumed session's gauges start again. Each field says which it is. The gauges are read as they stand,
  so they may be past `head`, which says where the record was read.
- **Whose process.** The process holding the journal is the runtime's. A script that runs `Session.start` in its own process
  holds the runtime itself, so the CPU and memory are the script's too. A process that only reads a closed journal measures
  nothing, and says so.

## Alternatives

| Alternative | Why not |
|---|---|
| Counters as events, a sampled metric journaled now and then | Instrumentation would add journal writes, which section 16 rules out, and a sample is display telemetry, not evidence |
| Counting at query time, `count(*)` by type over `events` | A walk of the journal on every reading, growing with it, where the fold costs one upsert per event |
| A fold keeping throughput or latency | A fold sees one event and no clock (law 2), and latency is the writer's, not the record's |
| Gauges read by a second route, a `Session` method on the kernel or a field of the link | Every surface derives from the op table ([RFC 0004](0004-one-operation-table.md)), so an op reaches the command line, Python and a view link at once, where a second route would be a surface of its own on each |
| Exact percentiles over every ack | Memory grows with the writes. A window of the latest acks would mix a second horizon into one answer. Buckets are bounded and never understate |
| Resident memory now, from `/proc/self/status` | A file read inside an op, which law 3 keeps out. The peak, from a system call, is what a budget on bounded memory needs |
| Measuring each agent's harness processes, through a registry of gauges the host writes | A second kernel concept with one user. The host knows a harness's process group, but a process that leaves the group is not counted, and an in-process driver shares the runtime's. Unknown now, pending the owner's ruling on per-agent limits |
| `eligibility`'s whole verdict for each agent | It reads each agent's stream, which grows with its turns, on every reading. The trainable level is the bar a fold already holds, and the sentence says what it leaves to `eligibility` |
| A tool agents may read | An agent's read is evidence, and a query records none. No agent has asked for it |
| Leaving out what nothing measured | An absent field reads as nothing to report. None with why says what is not known |

## Consequences

- A person or a program asks how a session runs, from the command line, Python or a view link, and the scale tests read
  throughput, ack latency and memory by public names.
- An op may read the kernel's gauges, so `Txn` has six members, and a test pins them.
- Each session folds one view more, at one upsert an event; a session from before it refolds it as its writer opens, and a
  read-only reader of one that never had it is refused `unavailable`, naming the view, until a writer has.
- Nothing is limited. Resource use is reported, the runtime's own, and an agent's harness reads unknown.
- What no runtime measured reads None, with why, and never zero.

## Rollout plan

| Milestone | Scope | Exit check | Pull requests |
|---|---|---|---|
| M1 the gauges | `Gauges`, `Kernel.gauges()` and `Txn.gauges()` | `tests/unit/kernel/test_writer.py`, `test_the_writer_reports_its_depth_in_flight_and_ack_latency_by_public_names` |`feat: Give the kernel's writer gauges public names` |
| M2 the query | `Counters`, `session.metrics`, `Session.metrics` and the command `session metrics` | `tests/unit/primitives/test_metrics.py` |`feat: Answer session.metrics, unknown where nothing measured` |
| M3 measured at scale | The writer's cost of metrics and a reading's cost, held to budgets set from measurements on the real stack | Milestone 4's scale tests, `test_metrics_cost_the_writer_no_more_than_their_budget` | |

## Open questions

1. Who may read `session.metrics`, and are per-agent resource limits in milestone 4? M1 and M2 build the default, pending the
   owner's ruling: a person's or a program's query, which a view credential reads and no agent holds, and resource use reported
   and never limited, the runtime's own, with an agent's harness unknown. A ruling for agents adds a tool and drops one refusal.
   A ruling for limits needs each harness's processes measured first, which nothing here builds and nothing here would have to
   undo. Needed before milestone 4 closes.
2. Should each agent's harness processes be measured, and how is a process that leaves its group counted? Until a ruling, it
   reads unknown.

## Evidence

- `tests/unit/kernel/test_writer.py`, `test_the_writer_reports_its_depth_in_flight_and_ack_latency_by_public_names`;
  `tests/unit/kernel/test_envelope.py`, `test_txn_is_exactly_me_now_view_gauges_emit_effect`.
- `tests/unit/primitives/test_metrics.py`: `test_counters_are_folds_that_add_no_journal_write`,
  `test_a_metric_nothing_measured_is_unknown_never_zero`, `test_active_and_blocked_agents_are_the_roster_s_groups`,
  `test_metrics_on_a_view_credential_write_nothing` and `test_no_agent_holds_a_grant_for_metrics`.
- The writer's cost, measured with a script kept outside this repository: 20 agents through the kernel's ops, then 20,000
  `message.send`s to a person, 256 at a time, four runs of each build in turn. With this change, 3,709 to 4,028 events a second;
  with the counters fold taken out, 2,976 to 3,826; at the commit before it, 3,816 to 4,089. The spread within each build is
  wider than any difference between them. A reading of `session.metrics` at the end, 20,264 events with 20,000 open mentions,
  took 108 to 112 ms, nearly all of it the roster reading attention's rows. On a shared host with 192 threads of Xeon Platinum
  8468 at a load of about 20, the journal on a local XFS disk. Scripted reports alone, and no runtime: a real session's mix is
  UNVERIFIED.
- `getrusage(2)` on Linux gives `ru_maxrss` in kilobytes. That macOS gives bytes is UNVERIFIED here.
