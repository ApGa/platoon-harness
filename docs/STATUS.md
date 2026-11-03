# Status

Every capability is one of: **planned**, **implemented** (code exists and is exercised by something), **tested** (named tests
pass, and the row says which kind), **experimental** (works, but rests on an unstable upstream surface or lacks coverage) or
**deferred** (a stated decision not to do it yet). An interface, a mock, a screenshot or a TODO does not count as implemented.

## Milestones

| Milestone | Definition | State |
|---|---|---|
| M0 Inspect and decide | Compatibility map, architecture and ownership decisions, schemas, plan | done |
| M1 Vertical slice | Configure a real harness, launch a small team, exchange messages and artifacts, watch in a basic TUI and SwarmChat, send a human message through either, and the same flow headless | in progress: the headless flow ran on real models. No TUI or SwarmChat client exists |
| M2 Dependable coordination | Dynamic lifecycle, leased claims, watches, budgets, workspace modes, reconnect and recovery, provenance for supported flows, two real adapter paths, mixed-harness example | planned |
| M3 Training integration | Platoon bridge, exact-identity fixtures, reward and export contracts, RAO parity, no-extra-rollout baseline, upstream amendments | planned |
| M4 Production UX and extensibility | Complete TUI and web interactions, reviews and approvals, Git examples, extension conformance, packaging, docs, hardening, measured scale | planned |

## Acceptance cases (brief section 13)

| Case | State | Evidence |
|---|---|---|
| SDK independence | tested | `tests/integration/test_independence.py`: a headless script importing only `platoon_harness` runs a session in a subprocess, on the `exec` driver, and imported no CLI, Textual, Platoon, Torch or Tinker |
| Mixed backends | experimental | `tests/live/test_codex.py`, live, once: a Claude Code agent and a Codex agent in one session on their own logins, with a message each way and a board entry, `plan_login=True` said aloud. `tests/live/test_teams.py`, live, twice: a Claude Code lead and a Codex worker fixed two seeded bugs through a queue and settled, the tests of that repository passing. `agent.started` journals what each declared and earned, and no client draws that yet |
| End-to-end collaboration | tested | `tests/integration/test_vertical_slice.py`, `test_detached.py`: spawn, post, query, claim, message, completion and a final artifact. Scripted harnesses on the real tool plane, in-process and as real wire processes. `tests/live/test_teams.py`, live, on `claude-haiku-5-5`: a lead and two workers, tasks claimed, messages exchanged, an artifact on a board, a human message through `Session.send`, settled, and the repository's tests passing, on the final preamble in 25 model calls. Once, and three runs before it failed to settle: `docs/research/spikes/real-harness.md` says what each taught |
| Human parity | planned | |
| Claim race | tested | `tests/unit/primitives/test_tasks.py`, `test_claim_race_*`, including a hypothesis interleaving. Concurrent commands on one writer; no real harness |
| Watch race | tested | `tests/unit/primitives/test_waits.py`, `test_watch_race_*`, including a hypothesis interleaving of sends, reads, waits and reopening the journal. No real harness |
| Retry and crash | tested | `tests/integration/test_crash.py`: `kill -9` of a detached runtime mid-turn, then a resume, with wire processes as harnesses. Each effect kind has its row in `tests/unit/runtime/test_recovery.py`, and `test_crash_points.py` cuts a journal at every command boundary. `tests/live/test_crashes.py`, live: `kill -9` of a detached runtime during a real shell tool on Claude Code and on Codex, 3 trials each, and an owner's stop, then a resume told each model, and nothing ran behind the journal's back. Pi has not been through it on a real model |
| Provenance | planned | |
| Identity | planned | |
| Credit integration | planned | |
| UI correctness | planned | |
| Extensibility | planned | |
| Git workflow | planned | |
| Scale | planned | |

## Capabilities

Updated as work lands.

### Kernel (`platoon_harness.kernel`)

Rows marked tested have CPU-only unit tests in `tests/unit/kernel`. Durability is tested against SIGKILL on Linux, not against
power loss. Nothing here has run on macOS.

| Capability | State | Evidence |
|---|---|---|
| Journal: WAL, `synchronous=FULL`, flock-held writer, immutable events, versioned schema | tested | `test_journal.py`, `test_laws.py` |
| Spike pragmas and the checkpoint thread | tested | `test_journal.py`. The thread's one-second cadence is not itself timed |
| Network filesystem refusal, tmpfs and unknown warnings, read-only open of closed and live journals | tested | `test_journal.py`, Linux. The refusal was also seen on this host's Lustre; other network filesystems are simulated |
| macOS filesystem detection and `F_FULLFSYNC` | experimental | Written from the man page, never run |
| Writer thread: group commit, ack after commit, admission limits, runtime reserve, every admitted command answered through a failed commit, a failed rollback, an op that exits, and close | tested | `test_writer.py`. What a failed commit left is unknown, so a retry keeps its key: `tests/unit/runtime/test_host.py` for the host. Keeping a failed commit from going on for ever is planned for M2 |
| Commands: idempotency through an index on `events`, key reuse, refusals journaled, outcome on the last event, `expected_version`, strict decoding, bounded refusals | tested | `test_commands.py`, properties. In a 5 s closed loop on the shared login node the index, the replace trigger and `secure_delete` left about 5,000 commands/s unchanged |
| `authorize`: grants, live relations, scopes, runtime-only ops, credentials by hash | tested | `test_authorize.py` |
| Envelope stamping and payload limits, one open episode | tested | `test_envelope.py` |
| Bodies: inline, `blobs/`, fsync before citation, tombstones, erased bytes gone from the journal, the WAL and `blobs/`, redacted content kept out | tested | `test_bodies.py` on Linux. Bytes on the device below the filesystem are out of scope |
| Effects: lifecycle, timeouts, `on_uncertain`, priority, attempt fence, recovery of the journal side including `turn.lost`, a list by state, an incarnation's number | tested | `test_effects.py` |
| Timers and the clock daemon on an injected clock, unjournaled firings kept | tested | `test_timers.py` |
| Views: versions, per-view rebuild, high-water marks, `rebuild_all`, each schema pinned to its version | tested | `test_views.py`, properties, `tests/unit/primitives/test_extensions.py`. What a fold writes has no pin: a change there needs its bump by hand |
| Readers: `read`, `follow` with one shared read per pulse, `query`, lossy `deltas` from a frame, live principals only, a follower stopped at its revocation, no wake on a batch with no events | tested | `test_readers.py` |
| Read-only kernels: schema check, staleness per query, a moving head, a closed journal refused once a writer touches it | tested | `test_journal.py` |
| Daemon supervision with backoff | tested | `test_daemon.py` |
| Extension loading and the naming law | tested | `test_extension.py` |
| Laws 1 to 9 and 12 | tested | `test_laws.py`. Law 8 over a socket: `tests/unit/runtime/test_control.py` |
| Law 10, for what the kernel owns: unknown stays `None` in the envelope and in `Effect` | tested | `test_laws.py`. Usage labels are tested in `test_budgets.py`. Rewards, tool visibility and exposure queries do not exist yet |
| Law 11: the kernel's own extensions reach no private name, and code outside the kernel imports only `__all__` | tested | `test_laws.py`, over everything outside the kernel too |
| Rebuild equals live, idempotent retry, gapless versions, backward references | tested | `test_properties.py` (hypothesis) |
| Wildcard folds for a view that cannot name what it counts | tested | `tests/unit/kernel/test_views.py` |
| Acked commands survive SIGKILL, partial commands are invisible | tested | `test_crash.py` (subprocess) |
| `v`-based upcasting of old payloads | deferred | `v` is recorded. No upcaster exists until a second payload version does |
| `next`, `prev` and `group:x` as kernel relations | deferred | `grant.add` still refuses them. Compilation expands them over roles, so a team never needs them |
| A credential issued after a principal exists, replacing any it held, and refused once revoked | tested | `test_authorize.py`, `test_lifecycle.py` |
| Names unique across kinds and safe as a path part | tested | `test_authorize.py`, `test_lifecycle.py` |
| Effects cancelled before they start, and effects that wait for another to finish | tested | `test_effects.py` |
| A person settling an uncertain effect with `effect.settle`, offered as two actions on its row, which goes with either answer | tested | `test_effects.py`, `tests/unit/primitives/test_clients.py`, `tests/unit/runtime/test_recovery.py`. No client draws the buttons yet |
| `native` ids stamped on a command's events and read by nothing | tested | `test_commands.py`, `tests/unit/tools/test_mcp.py` |
| A reader's limit on a body, and refs that name lines of a body | tested | `test_bodies.py` |

### Primitives (`platoon_harness.primitives`)

Rows marked tested have CPU-only unit tests in `tests/unit/primitives`, named for the promises in architecture section 7, and each
test's fixture compares live views to a full rebuild when it ends. A test there does what a host would, by hand. The host itself is
under Runtime below, so every effect is now performed. One real harness has met these, where a row says so.

| Capability | State | Evidence |
|---|---|---|
| Inboxes, topics, `message.send`, address grammar, replies, threads, gist plus body | tested | `test_messages.py` |
| Reader cursors: `offered`, `delivered`, `acked`, omitted `after`, clamped `after`, a refused `after` past the head, filtered reads paging past their window, delivery states, per-seq acks | tested | `test_messages.py` |
| Broadcast: recorded audience, group generation, late joiners, `history` | tested | `test_messages.py` |
| Inbox depth cap with a `full` receipt, undeliverable on ended readers | tested | `test_messages.py` |
| Hops, `max_hops`, chains followed through what a turn was offered, replies, and a wait's notice | tested | `test_messages.py`, `test_lifecycle.py`, `test_waits.py` |
| Injection ladder, coalesce, steer degrading visibly, digests with a gap notice | tested | `test_delivery.py`. Boundaries are whatever a test's `ready` report declares |
| `steer` notices on a tool result | tested | `test_delivery.py`, and `tests/unit/tools/test_mcp.py` over a real socket, with a call that has none journaling nothing extra. No real harness |
| At-least-once handover: a failed `deliver` is queued again under a new input, even past a newer offer, and so is what a harness took and never landed, when its turn stops short or it comes back from a crash | tested | `test_delivery.py`, `tests/unit/runtime/test_recovery.py`. On the real binaries, an interrupted steer in a session, in `tests/integration/test_claude.py`, `test_codex.py` and `test_pi.py`, and a `kill -9` of the runtime in `test_claude.py` |
| Courier daemon: wakes, wait releases, coalesce and deadlines, a refused wake not retried until the budget moves, back-off after a failed handover, and an agent lost after six in a row | tested | `test_delivery.py`, `test_waits.py`, on the kernel's supervisor and a manual clock |
| `channel.create` with attenuation, `channel.list` naming what the next call takes, `group.define` | tested | `test_messages.py`, `test_compiled_grants.py` |
| Context stream, `context.offered`, `context.delivered`, compaction, a human's read writing nothing | tested | `test_messages.py`, `test_delivery.py` |
| A resume under other SDK or component versions labelled on `runtime.started`, not refused, and a session from before a view changed refolded and resumed | tested | `test_recovery.py`, `test_config.py`. Harness versions are on `agent.resumed`. A journal that was stopped under the old reason for a stop is not told |
| A compaction's `forgotten` and `summary` stored as bodies, with `compaction_opaque` recorded for an unknown `forgotten` | tested | `test_reports.py`, and a long list through a host in `test_host.py`. On Claude Code a manual `/compact` ran on FakeModel, with a summary and `forgotten` unknown. Auto compaction has not been observed |
| `call_id` on `item.recorded` and `usage.reported`, `purpose` on `model.called`, `native_id` on `context.delivered`, and a closed `Item.phase`, which a message or a thought leaves unset | tested | `test_reports.py`. `call.joined` for the late case is not built |
| Wait: `on`, friendly arguments, `all`/`any`, `after`, `timeout`, `hold`, atomic check, progress, parking at turn end, how each closed | tested | `test_waits.py`, properties |
| A waiter's own cancel or completion counts for its wait, placed before or after | tested | `test_waits.py` |
| A report the parent is counting does not wake it, so a join of N costs one turn, on agents, on senders and on tasks while someone else below it is at work | tested | `test_lifecycle.py`, and in a session in `tests/unit/runtime/test_session.py`. On real models in `tests/live/test_teams.py`: three workers that finished cost the lead one wake, twice. It needs them to finish, which the preamble now says, and a message a child sends still wakes its parent |
| A failed turn or a bad end breaking in on a parent with a wait open, past a spent chain, up to `max_hops` | tested | `test_lifecycle.py`. With no `max_hops`, only a budget bounds a model that answers each failure by asking again |
| A report held back reaching a turn when its wait closes with no notice, by `wait.cancel` or a held call's answer | tested | `test_lifecycle.py`, and through a held tool call in `tests/unit/runtime/test_session.py`. A wait a new one replaced is left to that one: its wake attaches the report, and if it never comes the session stalls |
| A parent is not woken to hear of a child it ended itself, and a turn that did not stop on its own says so | tested | `test_lifecycle.py` |
| Waiting for work on a queue, from `queue_empty` with no gap | tested | `test_waits.py`. A task that reopens after a lapse releases no such wait: pass a `timeout` |
| `hold` as a surface keeps it | tested | `tests/unit/tools/test_mcp.py`, on a manual clock over a real socket: released, `pending`, closed under the call, a retry, a role without `wait.progress`, and a client that vanishes. `hold_open` running as the runtime is confirmed in architecture section 10. No real harness |
| One-shot refusal and the `tool_timeout_s` cap | tested | `test_waits.py`, from a test's `ready` report |
| Boards: immutable versions, `expected_version`, ranges, exact refs, structured query, true totals, cursors, a wait counting only versions unread | tested | `test_boards.py` |
| Board text search on FTS5, over names, gists and fields | tested | `test_boards.py`. Bodies are not searched, on purpose. The no-FTS5 refusal is tested by flag, not on a build without it |
| Reading a body held in `blobs/` | tested | An op may do no I/O, so it leaves `text` null beside the hash and the tool plane reads it, within its limits: `test_mcp.py`. Only the tool plane reads one so far |
| Queues: atomic claim, fence, default fence, expiry through timers, `stale_fence`, `max_attempts`, `dead`, `max_inflight`, paging, results read back | tested | `test_tasks.py`, properties |
| `delivery` on queues and boards, as an entry on the channel | tested | `test_tasks.py`, `test_boards.py` |
| Lease renewal from observed harness activity | tested | `test_tasks.py` for `lease.due`, and `tests/unit/runtime/test_host.py` from a harness's reports on a manual clock, up to `lease_max`. Activity is reports: a tool call alone renews nothing |
| Lifecycle: spawn admission and enrolment in one transaction, one `agent.ended`, `on_parent_exit`, retire, interrupt, takeover, the monitor on every ending, a final report kept in the journal, and `crash_window` for a harness that exits in a turn | tested | `test_lifecycle.py`, `test_compiled_grants.py`. On real harnesses in `tests/live/test_crashes.py`: `kill -9` of the harness alone was heard in 0.04 s at worst. Resuming such a harness is not built, and `docs/research/spikes/real-harness.md` gives the evidence and the recommendation |
| `agent.finish` in a turn ending the agent with that turn, so usage and a last message count, cut off after a minute | tested | `test_lifecycle.py`, and on a harness in `tests/unit/runtime/test_session.py`. Claude Code on FakeModel ended its turn after the call, and finished, in `tests/integration/test_claude.py` |
| `agent.finish` and `agent.retire` refused over children that would end with the agent and are on their way to a turn or in one, by a wake that is due or a wait that holds too, saying what to do next, and `agent.cancel` never refused | tested | `test_lifecycle.py`, with the limits of architecture section 7 each named: a child that begins work after a finish, a harness that exits, a one-shot parent, which `team_check` warns of. A real model read the refusal, 2 of 2, in `tests/live/test_teams.py`: it stopped, said why, and finished when its worker's report woke it |
| An interrupt reaching a wake whose turn has not begun | tested | `test_lifecycle.py`, `tests/unit/runtime/test_host.py` |
| A failed admit, workspace or launch ends the agent `failed`, through the courier, and what it had still to start never starts | tested | `test_lifecycle.py`, on the kernel's supervisor |
| Completion: `settled`, `until`, `session.close`, `session.cancel`, resuming a stopped session, episodes | tested | `test_lifecycle.py` |
| Closing a headless session at `until` | tested | `tests/unit/runtime/test_session.py`: `settled()` closes, and waits for it to drain |
| Approvals: four facts, one winner, per-role policy journaled at open, moot with the turn that asked, and lowered in `attention` with it, across a crash too | tested | `test_approvals.py`, `tests/unit/runtime/test_recovery.py` |
| An `ask` no human can answer | tested | `settled()` returns `needs_human`, never a hang: `test_session.py`. The exit code itself arrives with the headless CLI |
| A session settled short of `until` with nothing scheduled says `stalled`, and `settled()` and `session.ending` say `needs_human`, with no timeout too, a `"settled"` session parked on someone still here among them | tested | `test_lifecycle.py` against each thing scheduled, `tests/unit/runtime/test_session.py` against a wall limit, a wait's deadline, `agent.conclude`, two agents parked on each other under either kind of `until`, and a guest that acts, or leaves having done nothing. Two clients both in `settled()` wait on each other: give one a timeout. An extension daemon's private schedule cannot be seen |
| Budgets: limits, reservations, reconciliation, labels with `counted` for what the runtime counts, no amount for a unit nobody measured, `over_budget` versus `unavailable`, overshoot bound, a failed wake returning its reservation and a failed steer keeping the turn's, a lost turn counting as unmeasured | tested | `test_budgets.py`, properties. A lost turn with no reservation, which only a harness-started turn can be, charges nothing: `Budgets` has no role for it |
| Client views: `roster` with typed `why`, `parent`, `stopped`, for a turn that did not stop on its own, and `held_by`, `attention` with actions, `changes`, `view.watch` | tested | `test_clients.py`, which holds a roster delta to a fresh snapshot. A roster changes as a whole, about 21 KB and 3 ms at 100 agents. `changes` is fed by a test's report; the turn-end probe arrives with workspaces |
| `blob.get`, by a ref that can name lines, and `blob.offer` for what a surface showed | tested | `test_lifecycle.py`. A surface stores the bytes first |
| A `body` argument offered as text on the tool plane | tested | `tests/unit/tools/test_mcp.py`, `test_ph.py`: stored first, cited by hash, the same for a retry |
| Tool descriptions: every argument described, what a refusal means, real op names | tested | `test_tool_surface.py`, and `tests/unit/tools/test_surface.py` rendered for MCP, `mcp__<ns>__` and `ph` |
| `lineage`, `exposure` | deferred | Provenance queries, after the host |
| `topology.patch`, `topology.show` | planned | Named in architecture sections 6 and 8. Neither is in the registry yet |
| `platoon_harness.patterns`, the library tier of architecture section 6 | planned | |
| Per-human unread positions in `marks.sqlite`, architecture section 4 | planned | Nothing creates the file yet. The UI that shows badges arrives with the clients |
| `doctor`, `docs/security.md`, and guides for training, the TUI and SwarmChat | planned | The architecture holds their promises until then |
| Team to session wiring: `Team` roles, limits and groups reaching `session.open` and `group.define` | tested | `tests/unit/runtime/test_opening.py` |
| An agent with no goal, which holds no turn's reservation and waits | tested | `test_lifecycle.py`, `tests/unit/runtime/test_opening.py` |
| A one-shot agent ending with its turn | tested | `test_lifecycle.py`, and on the `exec` driver in `tests/integration/test_independence.py` |
| A resumed harness back on the agent as it stood | tested | `test_lifecycle.py`, `tests/unit/runtime/test_recovery.py` |
| `session.ending`: the reason, each agent and its last report, usage with labels, gaps | tested | `test_lifecycle.py`, `tests/unit/runtime/test_session.py` |

### Tool plane (`platoon_harness.tools`)

Rows marked tested have CPU-only tests in `tests/unit/tools`, against a real `Kernel` with `PRIMITIVES`, a compiled team and a real
socket on port 0. Real Claude Code and real Codex have run against this server, as a row says. The spike's prototype log of Codex is replayed here too.

| Capability | State | Evidence |
|---|---|---|
| One derivation from `ops.list`, per token: names per surface, closed schemas showing only what a model should see, an honest `readOnlyHint` | tested | `test_surface.py` |
| The preamble: exact tools, who can be reached, which roles can be started, how to park and how to end | tested | `test_surface.py`. It reaches a harness once, at launch, in `AgentSpec.instructions`: `tests/unit/runtime/test_host.py`. It is fixed there, so who can be reached goes stale until `peers` is asked. What it does to a real model is in `docs/research/spikes/real-harness.md` |
| A sentence naming a tool its reader does not hold left out, in descriptions, handovers and a refusal's reason, and no fact lost with it. No agent holds `agent.list` or `task.renew` | tested | `test_surface.py`, for a reader holding one tool at a time |
| `peers` and `channel.list` a page at a time, a generic refusal of a query past 32 KiB | tested | `test_mcp.py`, with a 600 agent team |
| With no client id, identical calls in one turn are one call, labelled a repeat: a stated trade-off | tested | `test_mcp.py`. A key that told them apart would run a retry twice after a lost ack, which is worse. It costs pi over HTTP MCP a second identical claim, so the `pi` driver takes the shim, which sends a fresh id per call: two identical claims in one turn were two, in `tests/integration/test_pi.py` |
| An extension's own effect kind settled by its own daemon | tested | The kernel's half, in `test_effects.py`. Stated in architecture section 5.4. No extension has one yet |
| A ceiling on each default role's tool list | tested | `test_surface.py`: 22,815 bytes for a lead, 22,623 for a worker, 6,274 for a narrow role, as `json.dumps` of `list_tools` on a harness's surface |
| The server: Streamable HTTP, JSON replies, no sessions, `initialize` at `2025-11-25` and `2025-06-18`, 405, -32601, 202, -32600, 401, 403 | tested | `test_mcp.py`, `test_replay.py`, which replays every non-tool request of the spike's log |
| Bounded HTTP: head and body limits, a body read only after the token, deadlines on the kernel's clock, a connection limit, hostile bytes | tested | `test_mcp.py`. A client that will not read its answer is bounded by the same deadline, which no test reaches, since an answer fits a socket buffer |
| Identity from the token alone, `tools/list` filtered and enforced again at call time, undeclared arguments journaled, an agent's refused query journaled, an ended agent's token refused | tested | `test_mcp.py` |
| The idempotency key: one operation for a retry, the turn with no id, a label on a repeat, anchors kept in `native` as evidence only | tested | `test_mcp.py`. Anchors were read from the spike's log, not from a live client |
| Refusals a model can act on: code, what it means, what to do next, in the words of its surface, and nothing that names a tool its token does not hold | tested | `test_surface.py`, `test_mcp.py` |
| Results capped, with `rest` saying where the rest of a body is, and reading on reaching the end | tested | `test_mcp.py` |
| A query's answer past 32 KiB refused with its size | tested | `test_mcp.py` |
| A held wait closing as told only once its answer has left | tested | `test_mcp.py`, with an answer that cannot be sent |
| An idle client costs nothing, and one that vanishes during a held wait frees its server task and keeps its wait | tested | `test_mcp.py` |
| `ph`: argv and help from `tools/list`, JSON on stdout, a plain refusal on stderr, exit codes in its help | tested | `test_ph.py`, real processes, on the test interpreter and on the host's `python3` from the default path, skipped where there is none. A name that is no tool answers `no such tool` and journals nothing: only a tool the token does not hold is evidence |
| The stdio shim, with a call waiting out a hold beside others | tested | `test_shim.py`, real processes, on both interpreters. No real harness has run it |
| The official MCP client | tested | `tests/conformance/test_mcp_client.py`, slow, through `uv run --isolated --with 'mcp>=2.3,<3'`. `mcp` 2.3.0 connected in `auto`, which took -32601 for `server/discover` and fell back to `initialize`, and in `legacy`, negotiated `2025-11-25`, pinged, listed closed schemas and `readOnlyHint`, called tools, read a refused spoof as `isError`, and kept a `?surface=` in its URL. It sent no `GET` or `DELETE`. Its `2026-07-28` mode is not claimed and not run |
| Real Claude Code against this server | tested | `tests/integration/test_claude.py`, slow, on FakeModel: `peers` and a `wait` that parks, through a URL with `?surface=`, its `toolUseId` kept as `native`. `tests/live/test_claude.py` on `claude-haiku-5-5`: `board_post` |
| Real Codex against this server | tested | `tests/integration/test_codex.py`, slow, on FakeModel: `channel_list` and a `wait` that parks, through a URL with `?surface=`, its `callId` kept as `native`. `tests/live/test_codex.py` on `gpt-6-luna`: `board_post` on a first turn, `message_send` and `board_get` in a mixed team, each under `exec-<uuid>`, and no discovery call |

### Drivers (`platoon_harness.drivers`, `platoon_harness.rpc`, `platoon_harness.testing`)

Rows marked tested have tests in `tests/unit/drivers`, `tests/conformance` and `tests/integration`, on real subprocesses and real sockets
on Linux. Nothing here has run on macOS. The host calls these drivers now, so `ScriptedDriver`, `WireDriver`, `ExecDriver` and the
`claude`, `codex` and `pi` drivers have run inside a session, the first two on a real model and `pi` on FakeModel alone.

| Capability | State | Evidence |
|---|---|---|
| One JSON-RPC peer: LF only, requests, notifications, errors, a line limit that ends the connection, pending calls failed at EOF, duplicate ids, two peers that cannot echo errors, a reader that stops being dropped | tested | `test_rpc.py`. `jsonrpc=False` is tested on hand-written frames, and `codex app-server` has run on it, on FakeModel and on a real model. ACP does not use it yet |
| The contract: seven methods, `DriverInfo`, `AgentSpec`, `ToolBinding`, `Delivery`, every field of section 9.2 | tested | `test_public_api.py`, `tests/unit/primitives/test_reports.py`, and every driver below |
| One closed report vocabulary, serializable for the wire, with a path through `agent.report` for each | tested | `tests/unit/primitives/test_reports.py`, against the architecture's list |
| `agent.start`: what the runtime concluded, which a report has no field for, so no driver can claim a level or a capability | tested | `test_reports.py`, `test_wire.py`, with a real program trying |
| `levels`: a pure function, reasons for each, a result pinned to `(driver, version)`, a skip no pass, three-valued tool visibility | tested | `test_levels.py`, and from a live agent in `tests/unit/runtime/test_host.py`. Nothing stores a conformance result yet, so a live agent's levels are `unverified`. The rules are a first reading of compatibility section 4. `claude`, `codex` and `pi` each earned `operational` and `observable` from a result on FakeModel, in `tests/integration/`. `trainable` was not reached |
| A harness in its own group, recorded before it can exec, with nothing run if we die first | tested | `test_process.py` |
| Recognising a group on restart: a reused pid signals nobody | tested | `test_process.py`. A group whose leader is gone stays `unproven`: `reap` leaves it and names it, so a forked child can outlive a crash. `reap` reads the driver's record and a wire program's and no others, and names one it cannot read. A harness at the same UID can still forge those two: see security tiers in architecture section 15 |
| `stop`: TERM, wait, KILL, verify, for a child that ignores TERM, forks, or outlives its leader holding the pipes | tested | `test_process.py`, `test_wire.py` |
| Pipes always drain, a report quota that counts what a report holds and stops the agent with a gap, a lost reader, a lost stdout, a reporter that fails, a delta dropped first | tested | `test_process.py`, `test_wire.py` |
| A closing loop or interpreter takes the group down | tested | `test_process.py`, in a real interpreter with three endings. SIGKILL of the runtime is left to `reap` |
| Stderr in a bounded, masked log, never journaled, surviving a full disk | tested | `test_process.py` on Linux, with `/dev/full` |
| The harness environment as an allowlist | tested | `test_env.py`, on a real child with a poisoned parent environment |
| `Process` on macOS | experimental | `ps -o lstart=` and the rest are written from the man page and have never run |
| A process that leaves its group by `setsid` | deferred | It escapes `stop`. Only a cgroup would hold it. See ADR 0018 |
| `WireDriver` and `serve`: verbs equal to the methods, an integer protocol refused both ways, credentials by name, unknown frames and reports as `native` plus a gap, whether notifications or requests, a program's own record kept apart | tested | `test_wire.py`, `tests/conformance`, and against the real tool plane in `tests/integration/test_scripted_tool_plane.py` |
| Wire `describe`, with what a program said on stderr when it did not answer | tested | `test_wire.py`. It runs the program once with a blocking `subprocess.run`, so the host calls it on a thread, and keeps the answer per role. It runs in the caller's directory and a harness in the session's `cwd`, so a relative `command` can pass one and fail the other: `docs/drivers.md` says to use an absolute path |
| OpenHands as a wire worker | planned | The path is real. That worker does not exist |
| The `exec` driver, with `{goal}`, `ph` on the path, and what it cannot do refused with the reason, a goal that would be an option among it | tested | `test_exec.py`, and `tests/conformance` with a small CLI that calls the model |
| `harness = { command = [...], mode = "wire" }` and the `exec` and `wire` entry points | tested | `test_exec.py`, `test_config.py`, and launched from a role in `tests/integration/` |
| `ScriptedDriver`: every step, capabilities as data, real MCP, real model calls, resume | tested | `test_scripted.py`, and against the real `ToolServer` in `test_scripted_tool_plane.py` |
| `FakeModel`: three dialects, whole and streamed, a script, a log of what arrived | tested | `test_fake_model.py`. `tests/integration/test_fake_model_clients.py`, marked `slow`, ran with dummy keys: Codex 0.164.0 and Claude Code 2.1.316 on text and a tool call, pi 1.5.0 on text. It skips a client that is not installed, and a skip proves nothing |
| `check_driver`: named checks, all failures at once, a skip no pass, nothing left running | tested | `test_check_driver.py` gives each check a driver that lies, an interrupt reported as anything but `interrupted` among them. It passes on `ScriptedDriver`, a wire program, `exec`, `claude` on the real 2.1.316 binary against FakeModel, `codex` on the real 0.164.0 binary against FakeModel, and `pi` on the real 1.5.0 binary against FakeModel |
| `check_driver` rows for a preamble once per request, a tool item's anchor, a stop during a running shell tool, token totals, an unset model refused where access was given, a native child, and `call_id` on items and usage | tested | `test_check_driver.py` shows each failing for its lie. The scripted and wire drivers pass what they can reach. `claude`, `codex` and `pi` pass every one that applies on the real binary, which is what gives each `operational`. `codex` has no `call_id`, so that row skips, and a skip proves nothing. `tool` names our tool for a harness that prefixes it |
| A stop that came to `SIGKILL` reports `crash_window` | tested | `test_process.py`, on a process that ignores `SIGTERM` |
| The tool block and the preamble held still across a tool call, a wake and a resume by a new process | tested | `tests/integration/test_request_shape.py`, slow, on FakeModel, for each of `claude`, `codex` and `pi`. A live Codex's block cannot be read |
| What `check_driver` cannot prove yet | deferred | `tool_timeout_s`, `coverage` and `sandboxes`. The `declared_but_unproven` check names them when declared, and always skips. `claude`, `codex` and `pi` declare `coverage` from the frames probed, so that row names it. `pi` declares `tool_timeout_s` too, which it sets itself, and a tool cut at that number ran on the real binary in `test_pi.py`. `codex` declares `tool_timeout_s` too, a cap of its own measured once at 300 s, and `sandboxes`, each value of which ran on the real binary in `test_codex.py`, which no check does |
| The `claude` driver: `claude -p` stream-json and the control protocol, every report of the vocabulary but `changes`, resume, interrupt, approvals through the runtime, a steer at a tool boundary, `reconcile` from the transcript, and `stop` that ends a running tool | experimental | Rests on `--permission-prompt-tool stdio`, `command_lifecycle`, `get_settings`, `model_usage_since_last_result` and the transcript, all undocumented upstream. `tests/unit/drivers/test_claude.py` on a stand-in; `tests/integration/test_claude.py`, slow, on the real binary against FakeModel, every `check_driver` row; `tests/live/test_claude.py`, `test_teams.py` and `test_crashes.py`, live, on `claude-haiku-5-5`, the first not rerun since its instructions were changed. It skips where the binary is absent, and a skip proves nothing. A real child ran, and a child's approval has no observed outcome. Auto compaction, nested children and parallel tool batches have not run |
| The `codex` driver: `codex app-server` on one `Peer`, every report of the vocabulary but `changes`, resume, interrupt across native children, approvals through the runtime, a steer at a model call, `reconcile` from the thread, and `stop` that ends a running tool | experimental | The app-server is labelled Experimental upstream. `tests/unit/drivers/test_codex.py` on a stand-in; `tests/integration/test_codex.py`, slow, on the real binary against FakeModel, every `check_driver` row; `tests/live/test_codex.py`, `test_teams.py` and `test_crashes.py`, live, on `gpt-6-luna`. It skips where the binary is absent, and a skip proves nothing. Auto compaction ran on FakeModel only. A child ran on FakeModel only, at v1. A `fileChange` item has been seen only on the stand-in, as has a request for permissions |
| The `pi` driver: `pi --mode rpc` in the user's own agent directory, with our tools through the stdio shim from one extension, every report of the vocabulary but `child.seen` and `changes`, resume, interrupt, `gated` approvals through the runtime, a steer at a model call, `reconcile` from `get_entries`, compaction with `forgotten` named, and `stop` that ends a running tool | experimental | Pi's RPC is documented, and pi moves quickly, so this pins 1.5.0. `tests/unit/drivers/test_pi.py` on a stand-in; `tests/integration/test_pi.py`, slow, on the real 1.5.0 binary against FakeModel, every `check_driver` row with `gated` and `shell` given, a user's login, settings and extension beside ours, the shim, and a session with a wait, a wake and a resume. No live model has run: pi has no login here, so no provider, no OAuth login and no real `totalFromProvider` has met it. `native_child_seen` skips, as pi has none |
| `sandbox` on `AgentSpec`, from the role, one of the values a driver declared and left to the harness with none | tested | `test_opening.py` for the refusal, and `test_codex.py` on the real binary, each value on a shell write and a role's through a session |
| `effort` on `Role` and `AgentSpec`, handed over as it stands, and refused by a driver that cannot honor it | tested | `test_claude.py`, `test_pi.py`, `test_exec.py`, `test_scripted.py`, `tests/unit/runtime/test_host.py`, and on the real binaries, where an effort one would drop is refused. A wire program must refuse one itself, and `check_driver` has no row for that |
| A role with no auth profile signing in as the harness does in the shell | tested | `test_claude.py`, `test_codex.py` and `test_pi.py`, each for its own: a home variable, proxies and a CA file pass by name, for `codex` the session bus a keyring login needs too, and a provider key does not. A `pi` with no login is refused at start, on the real binary too. The machine that ran the live tests sets none of them, so those paths rest on those tests alone |
| `check_extension`: names, naming law, schemas, descriptions, public API only, rebuild equals live | tested | `test_check_extension.py`, each with an extension that breaks it |
| `docs/drivers.md`: its wire driver runs through the conformance suite, and its tables match the code | tested | `test_docs.py` |
| The SDK imports nothing but the standard library and pydantic, and nothing public holds a local path | tested | `test_boundaries.py`, by AST and by pattern. A pattern catches what it knows |

### Runtime (`platoon_harness.runtime`, `platoon_harness.session`)

Rows marked tested have tests in `tests/unit/runtime` and `tests/integration`, on real sockets and real subprocesses on Linux, with
scripted harnesses on the real tool plane and wire programs as processes. Two real harnesses have run in a session, on a real model and on
FakeModel: teams of up to four on real models, for a minute at most. A third, `pi`, has run in one on FakeModel alone. Nothing has run with more, and nothing here has run on macOS. The fast suite covers everything below except a second crash during recovery, the kill matrix and the sweep of crash
points, which are marked `slow`.

| Capability | State | Evidence |
|---|---|---|
| The root: chosen, environment, state home, the network fallback with a notice, a chosen network root refused to a live writer, a root another user owns or can write refused | tested | `test_paths.py`, with a simulated filesystem. The `doctor` entry arrives with the CLI |
| The folder: unique names built aside and renamed in with their manifest, the socket's length and private directory, a socket per folder, an unusable runtime directory falling through, `runtime.json`, tokens at 0600, listing by scan and `flock` | tested | `test_paths.py`. `/run/user/<uid>` can go at logout where logind is set to, taking a detached runtime's socket: nothing here has run across a logout |
| Opening: `team_check` on each driver's `describe` before any cost, the manifest and its body, roles, limits, `until`, policy, grants, channels, groups, budgets in seconds, starting agents | tested | `test_opening.py` |
| Opening again after a crash part of the way through | tested | `test_opening.py`, by a kill between two steps, in-process |
| Effects performed level-triggered: `admit`, `workspace` (`shared`, and any other fails loudly), `launch`, `deliver`, `interrupt`, `stop`, `answer` | tested | `test_host.py` |
| `interrupt`, `stop` and `answer` around a delivery that hangs, and an interrupt or a minute failing a handover under way | tested | `test_host.py` |
| A wake's `deliver` open until its turn begins, so a crash or a quiet harness cannot strand `waking` | tested | `test_host.py`, `test_recovery.py`, and the kill matrix in `tests/integration/test_kill_matrix.py` |
| A harness that says ready and never begins its goal is lost, and one resumed before it began is told again | tested | `test_host.py`, `test_recovery.py` |
| Model pinning: `ready` naming another model fails the spawn or the resume, and an unnamed one stays unknown | tested | `test_host.py`. Claude Code has been through it with the model matching. An alias it resolves fails, and that was reasoned from a probe and not run through the host |
| `assurance` on `agent.started` and `agent.resumed` | tested | `test_host.py`. Always `cooperative`: nothing earns `isolated` until OS isolation exists |
| A token in memory and its hash in the journal, a binding per agent, `ph` in `agents/<id>/bin`, instructions and preamble | tested | `test_host.py` |
| A delivery as text in the words of its surface, with refs and the input id | tested | `test_host.py`, `tests/unit/tools/test_surface.py` |
| Reports in order, bodies stored by hash, deltas to followers and never the journal, capabilities and levels on `agent.started` | tested | `test_host.py` |
| A takeover holding deliveries, already requested ones too | tested | `test_host.py`. Driving the native session during one is not built, so `agent.takeover` holds and releases and no more |
| A report stream that dies, a driver that raises, a harness that never starts or never says ready, a report the journal refuses or a body that will not store: `exited` and a gap, never a silent hang | tested | `test_host.py`. A Python driver whose own background task dies without a word is out of reach: nothing reports, and nothing raises |
| Credentials masked in every report of every driver, deltas too, in failed effects, and in the runtime's log | tested | `test_host.py`, `test_exec.py`, `test_wire.py`. A secret can be cut by a driver that does not mask first: `Process` gives one what it needs, and the ones here use it. After 33 live sessions no token was found in any session folder, plain or in base64, and a real tool's output printing one reached the journal masked: `tests/live/test_teams.py`, `docs/research/spikes/real-harness.md` |
| Shutdown bounded: a journal that will not commit, a driver that breaks in `stop`, a stop already running | tested | `test_host.py` |
| Every process tree gone with its agent, a wire program's own harness among them | tested | `test_host.py`, on real processes |
| Links that outlive a daemon restart | tested | `test_host.py` |
| Several runtimes in one process, nothing global, signals only in the entry point | tested | `test_host.py`, `test_public_api.py` |
| A turn cut off by a crash or by the owner's stop told on resume, at-least-once, in words that keep the two apart, with a wake, only while the session accepts work, and reasons a driver cannot forge | tested | `test_recovery.py`, `test_lifecycle.py`, and `kill -9` in `tests/integration/test_crash.py`, where nobody has to say anything for the work to finish. Claude Code on FakeModel took the notice after an owner's stop, in `tests/integration/test_claude.py`, and its own synthetic result for a dangling tool call agrees with it. Real Claude Code and Codex models took it in `tests/live/test_crashes.py`, 8 trials: each looked before acting, and one ran the command again, having found it unfinished. Pi has seen it on FakeModel alone |
| A wake the budget refuses after a crash ends the session `needs_human`, a goal never begun's too, and raising the budget lets it go on | tested | `test_recovery.py`, by name |
| A goal told again on the turn its spawn reserved, and its agent ended if the session stops accepting first | tested | `test_recovery.py` |
| Sweep of crash points: cut a journal at each command boundary of one team's run, resume, and find no exception, no effect left `started`, every turn cut off told, and rebuild equal to live | tested | `tests/integration/test_crash_points.py`, slow, on a driver that resumes and idles. It cuts the journal alone: blobs, agent folders and process records stay from a later time, so it says nothing of them. One scenario |
| Per-agent recovery: reap, resume, reconcile, on a fresh credential, one broken driver losing one agent, a `reconcile` that hangs, and a stop asked during it | tested | `test_recovery.py` for each effect kind, `tests/integration/test_crash.py` and the kill matrix for `kill -9` on real processes. Grace is the host's `GRACE` per group |
| A group that cannot be proved ours left alone and named, for an agent that has ended too | tested | `test_recovery.py`, with a stubbed `reap`. `test_process.py` proves the state itself |
| `Session`: `start`, `attach`, `resume`, as `await` or `async with`, one link in two forms | tested | `test_session.py`, `test_control.py` |
| Typed wrappers checked against the registry: every client op has a method, each method takes what its op declares, defaults agree | tested | `test_session.py`. `agent.finish` has none: a `Session` is no agent |
| One spelling for a body, the ref, on every method that takes or gives one | tested | `test_session.py` |
| `Ending.agents[n]["report"]`, a unit nobody measured with no amount, and why a spawn failed | tested | `test_session.py`, `tests/unit/primitives/test_lifecycle.py` |
| `settled()` and its six reasons, a quiet session past its wall limit among them | tested | `test_session.py`, on a manual clock where time matters |
| `detach=True`, the entry point, `SIGTERM` as the owner's shutdown, an exit once drained, nothing in the caller's directory able to stand in for a module | tested | `tests/integration/test_detached.py`, `test_session.py` |
| The control socket: a credential checked once, the principal bound, refusals as data and nothing else, long-polls, a client that stops reading is dropped and holds up no stop, a connection accepted during one dropped, live text refused for a name nobody holds | tested | `test_control.py`. The drop is shown at a 64 KiB limit. The real limit is 16 MiB per client, since one frame shares it with a body |
| View and control credentials | tested | `test_control.py`. A view token reads and never writes, and a try leaves no event |
| A client reconnecting from its cursor, retrying under its key | tested | `test_control.py`, `test_crash.py` |
| A guest falling back to history when its runtime goes, finding the next one, and outliving a writer | tested | `test_control.py`, `test_session.py`, `test_crash.py` |
| A human message and an approval raced by two guests | tested | `test_detached.py` |
| A guest's leaving changes nothing, an owner's leaves no process, attaching to a closed session writes nothing | tested | `test_detached.py`, `test_vertical_slice.py`, with the journal's bytes compared |
| `Authority` and `LocalAuthority` | tested | `test_host.py`, `test_opening.py`, `test_recovery.py`. `Admission` holds a token and model access: tool endpoints, workspace and attribution arrive with `PlatoonAuthority` |
| Workspaces other than `shared` | planned | A role naming one fails its spawn with the reason |
| A plan login refused for headless multi-agent, unless `Session.start(team, plan_login=True)` | tested | `tests/unit/runtime/test_opening.py`: several agents, a role that can be spawned, one alone, an auth profile, the opt-in. `claude` reports `plan` from `claude auth status`, reading one field, in `test_claude.py`, and on the native login in `tests/live/test_claude.py`. Exit 78 itself arrives with the CLI, which will map this refusal |
| Live text masked as one stream, so a secret split across two deltas is masked, and a cut never falls inside a character | tested | `test_host.py`, `tests/unit/drivers/test_env.py`. Its tail waits for the next delta or any other report |
| A harness that stops reading: a handover cut off at a minute, and `interrupt` and `answer` too | tested | `test_host.py` for all three on a manual clock, `tests/unit/drivers/test_claude.py` for a real pipe. A handover was bounded before this. `interrupt` and `answer` had no bound, and what they leave is a failed effect beside a turn still open, which only a wall limit ends |
| Exit codes and `platoon-harness resume` | planned | `Ending.reason` is what they are made from. The CLI does not exist yet, so history names `Session.resume` |
| The turn-end probe behind `changes` | planned | Arrives with workspaces |

### Teams and topologies (`platoon_harness.team`, `platoon_harness.topology`)

Rows marked tested have CPU-only unit tests in `tests/unit/topology`, where the compiled grants are checked against a real kernel with
stand-in ops. A session runs a team through `tests/unit/runtime/test_opening.py`.

| Capability | State | Evidence |
|---|---|---|
| `Role`, `Team`, `Topology` as frozen models, with TOML and Python building one object | tested | `test_presets.py` |
| The nine presets, with the worked examples of the research note as tests | tested | `test_presets.py` |
| Union: commutative, associative, a stable hash, conflicts naming both sources, no `deny` | tested | `test_union.py`, properties |
| `compile`: edges, channels, groups, `may_spawn`, lifecycle, `wait` and scopes, enforced by the real `authorize` | tested | `test_compile.py` against stand-in ops, `test_compiled_grants.py` against the real ones. Channel verbs come from one table in `primitives` |
| `next`, `prev` and groups expanded over roles | tested | `test_compile.py` |
| `team_check`: refusals, warnings, did-you-mean, every problem at once, recursion through a written grant, relations no `may_spawn` makes true | tested | `test_check.py` |
| A preset nobody knows, refused at load unless the team names an extension | tested | `test_check.py` |
| `team.show()` in English, and the resolved form as valid input | tested | `test_show.py`, `test_docs.py` |
| `docs/topologies.md`: every snippet runs, and both forms agree | tested | `test_docs.py` |
| Presets from `Extension.presets`, with the power of a built-in | tested | `test_check.py`, `test_extensions.py` |
| `Capabilities.measures` and `sandboxes` as drivers report them | tested | `tests/unit/runtime/test_opening.py`: each role's driver is asked, by role, since a wire program's capabilities are per command |
| `digest`, `entry`, `requires`, `validator` and `keys` on channels | experimental | Parsed, hashed and resolved, and `team_check` warns that no primitive enforces them yet |
| A role's `on_parent_exit` set by a preset | deferred | A preset returns a topology, and this is a role policy. The guide tells a mesh to set it |

### Configuration and extensions (`platoon_harness.config`, `platoon_harness.extensions`)

Rows marked tested have CPU-only unit tests in `tests/unit/config`. Discovery ran against fake `dist-info` folders, not against
installed wheels.

| Capability | State | Evidence |
|---|---|---|
| Precedence across six layers, mappings merge, lists replace, every problem at once | tested | `test_config.py` |
| What a project file needs trust for: a `command` harness, a `module:attr` reference, an auth profile | tested | `test_config.py` |
| `Secret`: refuses json, pickle, copy and pydantic, keeps its state to itself, prints as a mask | tested | `test_config.py` |
| Input kept out of configuration errors and their tracebacks | tested | `test_config.py` |
| Sanitized resolved config: names only, refused if it holds a named variable's value, however rendering escapes it | tested | `test_config.py`. A credential no profile names cannot be recognised |
| Redaction of encoded forms and URLs | tested | `tests/unit/drivers/test_env.py`, `test_process.py`: plain, JSON-escaped, URL-quoted and base64 forms, on what a harness writes to stderr and reports. Only exact values are refused in a resolved config. Exports do not exist yet |
| The manifest: resolved team, how it was started, components, versions, topology hash | tested | `test_config.py`, and written with its stored body in `tests/unit/runtime/test_opening.py` |
| Discovery from metadata with no import, in two groups | tested | `test_extensions.py` |
| Duplicates and incompatible SDK requirements caught before import | tested | `test_extensions.py`. Versions compare by release number, so a pre-release suffix is ignored |
| `name`, `name@version` and `module:attr` references, lazy load by exact name, with nothing installed too | tested | `test_extensions.py` |
| Errors listing registered, installed and nearest names | tested | `test_extensions.py` |
| Installing activates nothing | tested | `test_extensions.py` |
