# Status

Every capability is one of: **planned**, **implemented** (code exists and is exercised by something), **tested** (named tests
pass, and the row says which kind), **experimental** (works, but rests on an unstable upstream surface or lacks coverage) or
**deferred** (a stated decision not to do it yet). An interface, a mock, a screenshot or a TODO does not count as implemented.

## Milestones

| Milestone | Definition | State |
|---|---|---|
| M0 Inspect and decide | Compatibility map, architecture and ownership decisions, schemas, plan | done |
| M1 Vertical slice | Configure a real harness, launch a small team, exchange messages and artifacts, watch in a basic TUI and SwarmChat, send a human message through either, and the same flow headless | in progress |
| M2 Dependable coordination | Dynamic lifecycle, leased claims, watches, budgets, workspace modes, reconnect and recovery, provenance for supported flows, two real adapter paths, mixed-harness example | planned |
| M3 Training integration | Platoon bridge, exact-identity fixtures, reward and export contracts, RAO parity, no-extra-rollout baseline, upstream amendments | planned |
| M4 Production UX and extensibility | Complete TUI and web interactions, reviews and approvals, Git examples, extension conformance, packaging, docs, hardening, measured scale | planned |

## Acceptance cases (brief section 13)

| Case | State | Evidence |
|---|---|---|
| SDK independence | tested | `tests/integration/test_independence.py`: a headless script importing only `platoon_harness` runs a session in a subprocess, on the `exec` driver, and imported no CLI, Textual, Platoon, Torch or Tinker |
| Mixed backends | planned | |
| End-to-end collaboration | tested | `tests/integration/test_vertical_slice.py`, `test_detached.py`: spawn, post, query, claim, message, completion and a final artifact. Scripted harnesses on the real tool plane, in-process and as real wire processes. No real harness has run in a session |
| Human parity | planned | |
| Claim race | tested | `tests/unit/primitives/test_tasks.py`, `test_claim_race_*`, including a hypothesis interleaving. Concurrent commands on one writer; no real harness |
| Watch race | tested | `tests/unit/primitives/test_waits.py`, `test_watch_race_*`, including a hypothesis interleaving of sends, reads, waits and reopening the journal. No real harness |
| Retry and crash | tested | `tests/integration/test_crash.py`: `kill -9` of a detached runtime mid-turn, then a resume, with wire processes as harnesses. Each effect kind has its row in `tests/unit/runtime/test_recovery.py`, and `test_crash_points.py` cuts a journal at every command boundary. No real harness has been through it |
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
| Views: versions, per-view rebuild, high-water marks, `rebuild_all` | tested | `test_views.py`, properties |
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
| A person settling an uncertain effect with `effect.settle`, offered as two actions on its row | tested | `test_effects.py`, `tests/unit/primitives/test_clients.py`, `tests/unit/runtime/test_recovery.py`. No client draws the buttons yet |
| `native` ids stamped on a command's events and read by nothing | tested | `test_commands.py`, `tests/unit/tools/test_mcp.py` |
| A reader's limit on a body, and refs that name lines of a body | tested | `test_bodies.py` |

### Primitives (`platoon_harness.primitives`)

Rows marked tested have CPU-only unit tests in `tests/unit/primitives`, named for the promises in architecture section 7, and each
test's fixture compares live views to a full rebuild when it ends. A test there does what a host would, by hand. The host itself is
under Runtime below, so every effect is now performed, and nothing here has met a real harness.

| Capability | State | Evidence |
|---|---|---|
| Inboxes, topics, `message.send`, address grammar, replies, threads, gist plus body | tested | `test_messages.py` |
| Reader cursors: `offered`, `delivered`, `acked`, omitted `after`, clamped `after`, a refused `after` past the head, filtered reads paging past their window, delivery states, per-seq acks | tested | `test_messages.py` |
| Broadcast: recorded audience, group generation, late joiners, `history` | tested | `test_messages.py` |
| Inbox depth cap with a `full` receipt, undeliverable on ended readers | tested | `test_messages.py` |
| Hops, `max_hops`, chains followed through what a turn was offered, replies, and a wait's notice | tested | `test_messages.py`, `test_lifecycle.py`, `test_waits.py` |
| Injection ladder, coalesce, steer degrading visibly, digests with a gap notice | tested | `test_delivery.py`. Boundaries are whatever a test's `ready` report declares |
| `steer` notices on a tool result | tested | `test_delivery.py`, and `tests/unit/tools/test_mcp.py` over a real socket, with a call that has none journaling nothing extra. No real harness |
| At-least-once handover: a failed `deliver` is queued again under a new input, even past a newer offer | tested | `test_delivery.py` |
| Courier daemon: wakes, wait releases, coalesce and deadlines, a refused wake not retried until the budget moves, back-off after a failed handover, and an agent lost after six in a row | tested | `test_delivery.py`, `test_waits.py`, on the kernel's supervisor and a manual clock |
| `channel.create` with attenuation, `channel.list` naming what the next call takes, `group.define` | tested | `test_messages.py`, `test_compiled_grants.py` |
| Context stream, `context.offered`, `context.delivered`, compaction, a human's read writing nothing | tested | `test_messages.py`, `test_delivery.py` |
| A resume under other SDK or component versions labelled on `runtime.started`, not refused | tested | `test_recovery.py`, `test_config.py`. Harness versions are on `agent.resumed` |
| A compaction's `forgotten` and `summary` stored as bodies, with `compaction_opaque` recorded for an unknown `forgotten` | tested | `test_reports.py`, and a long list through a host in `test_host.py`. No compaction has been observed on a real harness |
| `call_id` on `item.recorded` and `usage.reported`, `purpose` on `model.called`, `native_id` on `context.delivered`, and a closed `Item.phase` | tested | `test_reports.py`. `call.joined` for the late case is not built |
| Wait: `on`, friendly arguments, `all`/`any`, `after`, `timeout`, `hold`, atomic check, progress, parking at turn end, how each closed | tested | `test_waits.py`, properties |
| A waiter's own cancel or completion counts for its wait, placed before or after | tested | `test_waits.py` |
| A report the parent is counting does not wake it unless the child ended badly, so a join of N costs one turn, on agents, on senders and on tasks | tested | `test_lifecycle.py`, and in a session in `tests/unit/runtime/test_session.py`. No real harness |
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
| Lifecycle: spawn admission and enrolment in one transaction, one `agent.ended`, `on_parent_exit`, retire, interrupt, takeover, the monitor on every ending, a final report kept in the journal | tested | `test_lifecycle.py`, `test_compiled_grants.py` |
| `agent.finish` in a turn ending the agent with that turn, so usage and a last message count, cut off after a minute | tested | `test_lifecycle.py`, and on a harness in `tests/unit/runtime/test_session.py`. A real harness's turn end after the tool call has not been observed |
| `agent.finish` and `agent.retire` refused over children that would end with the agent and are on their way to a turn or in one, saying what to do next, and `agent.cancel` never refused | tested | `test_lifecycle.py`, with the limits of architecture section 7 each named: a child that begins work after a finish, a harness that exits, a one-shot parent, which `team_check` warns of. Whether a real model does what the refusal says has not been observed |
| An interrupt reaching a wake whose turn has not begun | tested | `test_lifecycle.py`, `tests/unit/runtime/test_host.py` |
| A failed admit, workspace or launch ends the agent `failed`, through the courier, and what it had still to start never starts | tested | `test_lifecycle.py`, on the kernel's supervisor |
| Completion: `settled`, `until`, `session.close`, `session.cancel`, resuming a stopped session, episodes | tested | `test_lifecycle.py` |
| Closing a headless session at `until` | tested | `tests/unit/runtime/test_session.py`: `settled()` closes, and waits for it to drain |
| Approvals: four facts, one winner, per-role policy journaled at open, moot with the turn that asked, and lowered in `attention` with it, across a crash too | tested | `test_approvals.py`, `tests/unit/runtime/test_recovery.py` |
| An `ask` no human can answer | tested | `settled()` returns `needs_human`, never a hang: `test_session.py`. The exit code itself arrives with the headless CLI |
| A session settled short of `until` with nothing scheduled says `stalled`, and `settled()` returns `needs_human`, with no timeout too | tested | `test_lifecycle.py` against each thing scheduled, `tests/unit/runtime/test_session.py` against a wall limit, a wait's deadline, `agent.conclude`, two agents parked on each other, and a guest that acts, or leaves having done nothing. An extension daemon's private schedule cannot be seen |
| Budgets: limits, reservations, reconciliation, labels with `counted` for what the runtime counts, no amount for a unit nobody measured, `over_budget` versus `unavailable`, overshoot bound, a failed wake returning its reservation and a failed steer keeping the turn's, a lost turn counting as unmeasured | tested | `test_budgets.py`, properties. A lost turn with no reservation, which only a harness-started turn can be, charges nothing: `Budgets` has no role for it |
| Client views: `roster` with typed `why`, `parent`, `stopped` and `held_by`, `attention` with actions, `changes`, `view.watch` | tested | `test_clients.py`, which holds a roster delta to a fresh snapshot. A roster changes as a whole, about 21 KB and 3 ms at 100 agents. `changes` is fed by a test's report; the turn-end probe arrives with workspaces |
| `blob.get`, by a ref that can name lines, and `blob.offer` for what a surface showed | tested | `test_lifecycle.py`. A surface stores the bytes first |
| A `body` argument offered as text on the tool plane | tested | `tests/unit/tools/test_mcp.py`, `test_ph.py`: stored first, cited by hash, the same for a retry |
| Tool descriptions: every argument described, what a refusal means, real op names | tested | `test_tool_surface.py`, and `tests/unit/tools/test_surface.py` rendered for MCP, `mcp__<ns>__` and `ph` |
| `lineage`, `exposure` | deferred | Provenance queries, after the host |
| `topology.patch`, `topology.show` | planned | Named in architecture sections 6 and 8. Neither is in the registry yet |
| `platoon_harness.patterns`, the library tier of architecture section 6 | planned | |
| `doctor`, `docs/security.md`, and guides for training, the TUI and SwarmChat | planned | The architecture holds their promises until then |
| Team to session wiring: `Team` roles, limits and groups reaching `session.open` and `group.define` | tested | `tests/unit/runtime/test_opening.py` |
| An agent with no goal, which holds no turn's reservation and waits | tested | `test_lifecycle.py`, `tests/unit/runtime/test_opening.py` |
| A one-shot agent ending with its turn | tested | `test_lifecycle.py`, and on the `exec` driver in `tests/integration/test_independence.py` |
| A resumed harness back on the agent as it stood | tested | `test_lifecycle.py`, `tests/unit/runtime/test_recovery.py` |
| `session.ending`: the reason, each agent and its last report, usage with labels, gaps | tested | `test_lifecycle.py`, `tests/unit/runtime/test_session.py` |

### Tool plane (`platoon_harness.tools`)

Rows marked tested have CPU-only tests in `tests/unit/tools`, against a real `Kernel` with `PRIMITIVES`, a compiled team and a real
socket on port 0. No real harness has run against this server: the spike's prototype did, and its log is replayed here.

| Capability | State | Evidence |
|---|---|---|
| One derivation from `ops.list`, per token: names per surface, closed schemas showing only what a model should see, an honest `readOnlyHint` | tested | `test_surface.py` |
| The preamble: exact tools, who can be reached, how to park | tested | `test_surface.py`. It reaches a harness once, at launch, in `AgentSpec.instructions`: `tests/unit/runtime/test_host.py`. It is fixed there, so who can be reached goes stale until `peers` is asked |
| A sentence naming a tool its reader does not hold left out, in descriptions and handovers. No agent holds `agent.list` or `task.renew` | tested | `test_surface.py` |
| `peers` and `channel.list` a page at a time, a generic refusal of a query past 32 KiB | tested | `test_mcp.py`, with a 600 agent team |
| A ceiling on each default role's tool list | tested | `test_surface.py`: 22,737 bytes for a lead, 22,592 for a worker, 6,290 for a narrow role, as `json.dumps` of `list_tools` on a harness's surface |
| The server: Streamable HTTP, JSON replies, no sessions, `initialize` at `2025-11-25` and `2025-06-18`, 405, -32601, 202, -32600, 401, 403 | tested | `test_mcp.py`, `test_replay.py`, which replays every non-tool request of the spike's log |
| Bounded HTTP: head and body limits, a body read only after the token, deadlines on the kernel's clock, a connection limit, hostile bytes | tested | `test_mcp.py`. A client that will not read its answer is bounded by the same deadline, which no test reaches, since an answer fits a socket buffer |
| Identity from the token alone, `tools/list` filtered and enforced again at call time, undeclared arguments journaled, an agent's refused query journaled, an ended agent's token refused | tested | `test_mcp.py` |
| The idempotency key: one operation for a retry, the turn with no id, a label on a repeat, anchors kept in `native` as evidence only | tested | `test_mcp.py`. Anchors were read from the spike's log, not from a live client |
| Refusals a model can act on: code, what it means, what to do next, in the words of its surface, and no next step that names a tool its token does not hold | tested | `test_surface.py`, `test_mcp.py` |
| Results capped, with `rest` saying where the rest of a body is, and reading on reaching the end | tested | `test_mcp.py` |
| A query's answer past 32 KiB refused with its size | tested | `test_mcp.py` |
| A held wait closing as told only once its answer has left | tested | `test_mcp.py`, with an answer that cannot be sent |
| An idle client costs nothing, and one that vanishes during a held wait frees its server task and keeps its wait | tested | `test_mcp.py` |
| `ph`: argv and help from `tools/list`, JSON on stdout, a plain refusal on stderr, exit codes in its help | tested | `test_ph.py`, real processes, on the test interpreter and on the host's `python3` from the default path, skipped where there is none. A name that is no tool answers `no such tool` and journals nothing: only a tool the token does not hold is evidence |
| The stdio shim, with a call waiting out a hold beside others | tested | `test_shim.py`, real processes, on both interpreters. No real harness has run it |
| The official MCP client | tested | `tests/conformance/test_mcp_client.py`, slow, through `uv run --isolated --with 'mcp>=2.3,<3'`. `mcp` 2.3.0 connected in `auto`, which took -32601 for `server/discover` and fell back to `initialize`, and in `legacy`, negotiated `2025-11-25`, pinged, listed closed schemas and `readOnlyHint`, called tools, read a refused spoof as `isError`, and kept a `?surface=` in its URL. It sent no `GET` or `DELETE`. Its `2026-07-28` mode is not claimed and not run |
| Real Claude Code and Codex against this server | planned | Needs the drivers. The spike's prototype passed both |

### Drivers (`platoon_harness.drivers`, `platoon_harness.rpc`, `platoon_harness.testing`)

Rows marked tested have tests in `tests/unit/drivers`, `tests/conformance` and `tests/integration`, on real subprocesses and real sockets
on Linux. Nothing here has run on macOS. The host calls these drivers now, so `ScriptedDriver`, `WireDriver` and `ExecDriver` have run
inside a session. The drivers for `claude`, `codex` and `pi` do not exist.

| Capability | State | Evidence |
|---|---|---|
| One JSON-RPC peer: LF only, requests, notifications, errors, a line limit that ends the connection, pending calls failed at EOF, duplicate ids, two peers that cannot echo errors, a reader that stops being dropped | tested | `test_rpc.py`. `jsonrpc=False` is tested on hand-written frames: no Codex session has run on it. ACP does not use it yet |
| The contract: seven methods, `DriverInfo`, `AgentSpec`, `ToolBinding`, `Delivery`, `Receipt`, `Started`, every field of section 9.2 | tested | `test_public_api.py`, `tests/unit/primitives/test_reports.py`, and every driver below |
| One closed report vocabulary, serializable for the wire, with a path through `agent.report` for each | tested | `tests/unit/primitives/test_reports.py`, against the architecture's list |
| `agent.start`: what the runtime concluded, which a report has no field for, so no driver can claim a level or a capability | tested | `test_reports.py`, `test_wire.py`, with a real program trying |
| `levels`: a pure function, reasons for each, a result pinned to `(driver, version)`, a skip no pass, three-valued tool visibility | tested | `test_levels.py`, and from a live agent in `tests/unit/runtime/test_host.py`. Nothing stores a conformance result yet, so a live agent's levels are `unverified`. The rules are a first reading of compatibility section 4, and no real harness has been through them |
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
| `FakeModel`: three dialects, whole and streamed, a script, a log of what arrived | tested | `test_fake_model.py`. `tests/integration/test_fake_model_clients.py`, marked `slow`, ran with dummy keys: Codex 0.164.0 and Claude Code 2.1.316 on text and a tool call, pi 1.4.0 on text. It skips a client that is not installed, and a skip proves nothing |
| `check_driver`: named checks, all failures at once, a skip no pass, nothing left running | tested | `test_check_driver.py` gives each check a driver that lies. It passes on `ScriptedDriver`, a wire program and `exec`, and no real harness has been through it |
| What `check_driver` cannot prove yet | deferred | `tool_timeout_s`, `native_children`, `coverage` and `sandboxes`. The `declared_but_unproven` check names them when declared, and always skips |
| `check_extension`: names, naming law, schemas, descriptions, public API only, rebuild equals live | tested | `test_check_extension.py`, each with an extension that breaks it |
| `docs/drivers.md`: its wire driver runs through the conformance suite, and its tables match the code | tested | `test_docs.py` |
| The SDK imports nothing but the standard library and pydantic, and nothing public holds a local path | tested | `test_boundaries.py`, by AST and by pattern. A pattern catches what it knows |

### Runtime (`platoon_harness.runtime`, `platoon_harness.session`)

Rows marked tested have tests in `tests/unit/runtime` and `tests/integration`, on real sockets and real subprocesses on Linux, with
scripted harnesses on the real tool plane and wire programs as processes. **No real harness has run in a session,** and nothing here
has run on macOS. The fast suite covers everything below except a second crash during recovery, the kill matrix and the sweep of crash
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
| Model pinning: `ready` naming another model fails the spawn or the resume, and an unnamed one stays unknown | tested | `test_host.py`. No real harness has been through it |
| `assurance` on `agent.started` and `agent.resumed` | tested | `test_host.py`. Always `cooperative`: nothing earns `isolated` until OS isolation exists |
| A token in memory and its hash in the journal, a binding per agent, `ph` in `agents/<id>/bin`, instructions and preamble | tested | `test_host.py` |
| A delivery as text in the words of its surface, with refs and the input id | tested | `test_host.py`, `tests/unit/tools/test_surface.py` |
| Reports in order, bodies stored by hash, deltas to followers and never the journal, capabilities and levels on `agent.started` | tested | `test_host.py` |
| A takeover holding deliveries, already requested ones too | tested | `test_host.py`. Driving the native session during one is not built, so `agent.takeover` holds and releases and no more |
| A report stream that dies, a driver that raises, a harness that never starts or never says ready, a report the journal refuses: `exited` and a gap, never a silent hang | tested | `test_host.py`. A Python driver whose own background task dies without a word is out of reach: nothing reports, and nothing raises |
| Credentials masked in every report of every driver, deltas too, in failed effects, and in the runtime's log | tested | `test_host.py`, `test_exec.py`, `test_wire.py`. A secret can be cut by a driver that does not mask first: `Process` gives one what it needs, and the ones here use it |
| Shutdown bounded: a journal that will not commit, a driver that breaks in `stop`, a stop already running | tested | `test_host.py` |
| Every process tree gone with its agent, a wire program's own harness among them | tested | `test_host.py`, on real processes |
| Links that outlive a daemon restart | tested | `test_host.py` |
| Several runtimes in one process, nothing global, signals only in the entry point | tested | `test_host.py`, `test_public_api.py` |
| A turn cut off by a crash or by the owner's stop told once on resume, in words that keep the two apart, with a wake, only while the session accepts work, and not twice across a second crash | tested | `test_recovery.py`, `test_lifecycle.py`, and `kill -9` in `tests/integration/test_crash.py`, where nobody has to say anything for the work to finish. No real harness has seen the notice, so whether one reads it as meant, or shows something it does not cover, is unknown |
| A wake the budget refuses after a crash ends the session `needs_human`, and raising the budget lets it go on | tested | `test_recovery.py`, by name |
| Sweep of crash points: cut a journal at each command boundary of one team's run, resume, and find no exception, no effect left `started`, nothing owed, and rebuild equal to live | tested | `tests/integration/test_crash_points.py`, slow, on a driver that resumes and idles. It cuts the journal alone: blobs, agent folders and process records stay from a later time, so it says nothing of them. One scenario |
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
| A plan login refused for headless multi-agent, exit 78 | planned | Architecture section 15. `prepare` will refuse it, from each role's `DriverInfo.login`, so `Session` and the CLI share the rule. No driver reports `plan` yet, so nothing can reach it |
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
