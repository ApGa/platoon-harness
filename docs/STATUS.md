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
| SDK independence | planned | |
| Mixed backends | planned | |
| End-to-end collaboration | planned | |
| Human parity | planned | |
| Claim race | tested | `tests/unit/primitives/test_tasks.py`, `test_claim_race_*`, including a hypothesis interleaving. Concurrent commands on one writer; no real harness |
| Watch race | tested | `tests/unit/primitives/test_waits.py`, `test_watch_race_*`, including a hypothesis interleaving of sends, reads, waits and reopening the journal. No real harness |
| Retry and crash | planned | |
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
| Writer thread: group commit, ack after commit, admission limits, runtime reserve, every admitted command answered through a failed commit, a failed rollback, an op that exits, and close | tested | `test_writer.py` |
| Commands: idempotency through an index on `events`, key reuse, refusals journaled, outcome on the last event, `expected_version`, strict decoding, bounded refusals | tested | `test_commands.py`, properties. In a 5 s closed loop on the shared login node the index, the replace trigger and `secure_delete` left about 5,000 commands/s unchanged |
| `authorize`: grants, live relations, scopes, runtime-only ops, credentials by hash | tested | `test_authorize.py` |
| Envelope stamping and payload limits, one open episode | tested | `test_envelope.py` |
| Bodies: inline, `blobs/`, fsync before citation, tombstones, erased bytes gone from the journal, the WAL and `blobs/`, redacted content kept out | tested | `test_bodies.py` on Linux. Bytes on the device below the filesystem are out of scope |
| Effects: lifecycle, timeouts, `on_uncertain`, priority, attempt fence, recovery of the journal side including `turn.lost` | tested | `test_effects.py` |
| Timers and the clock daemon on an injected clock, unjournaled firings kept | tested | `test_timers.py` |
| Views: versions, per-view rebuild, high-water marks, `rebuild_all` | tested | `test_views.py`, properties |
| Readers: `read`, `follow` with one shared read per pulse, `query`, lossy `deltas`, live principals only, a follower stopped at its revocation | tested | `test_readers.py` |
| Read-only kernels: schema check, staleness per query, a moving head, a closed journal refused once a writer touches it | tested | `test_journal.py` |
| Daemon supervision with backoff | tested | `test_daemon.py` |
| Extension loading and the naming law | tested | `test_extension.py` |
| Laws 1 to 9 and 12 | tested | `test_laws.py` |
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

### Primitives (`platoon_harness.primitives`)

Rows marked tested have CPU-only unit tests in `tests/unit/primitives`, named for the promises in architecture section 7, and each
test's fixture compares live views to a full rebuild when it ends. No driver exists yet: a test does what a host would, by hand, so
nothing here has met a real harness. Effects such as `deliver`, `launch` and `answer` are requested and tracked, and nothing performs them.

| Capability | State | Evidence |
|---|---|---|
| Inboxes, topics, `message.send`, address grammar, replies, threads, gist plus body | tested | `test_messages.py` |
| Reader cursors: `offered`, `delivered`, `acked`, omitted `after`, clamped `after`, a refused `after` past the head, filtered reads paging past their window, delivery states, per-seq acks | tested | `test_messages.py` |
| Broadcast: recorded audience, group generation, late joiners, `history` | tested | `test_messages.py` |
| Inbox depth cap with a `full` receipt, undeliverable on ended readers | tested | `test_messages.py` |
| Hops, `max_hops`, chains followed through what a turn was offered, replies, and a wait's notice | tested | `test_messages.py`, `test_lifecycle.py`, `test_waits.py` |
| Injection ladder, coalesce, steer degrading visibly, digests with a gap notice | tested | `test_delivery.py`. Boundaries are whatever a test's `ready` report declares |
| `steer` notices on a tool result | implemented | `delivery.offer` with `boundary="tool"` is tested. No tool plane exists to attach them yet |
| At-least-once handover: a failed `deliver` is queued again under a new input, even past a newer offer | tested | `test_delivery.py` |
| Courier daemon: wakes, wait releases, coalesce and deadlines, a refused wake not retried until the budget moves | tested | `test_delivery.py`, `test_waits.py`, on the kernel's supervisor and a manual clock |
| `channel.create` with attenuation, `channel.list` naming what the next call takes, `group.define` | tested | `test_messages.py`, `test_compiled_grants.py` |
| Context stream, `context.offered`, `context.delivered`, compaction, a human's read writing nothing | tested | `test_messages.py`, `test_delivery.py` |
| Wait: `on`, friendly arguments, `all`/`any`, `after`, `timeout`, `hold`, atomic check, progress, parking at turn end, how each closed | tested | `test_waits.py`, properties |
| Waiting for work on a queue, from `queue_empty` with no gap | tested | `test_waits.py`. A task that reopens after a lapse releases no such wait: pass a `timeout` |
| `hold` as a surface keeps it | implemented | `hold_open` is tested. No tool plane calls it yet |
| One-shot refusal and the `tool_timeout_s` cap | tested | `test_waits.py`, from a test's `ready` report |
| Boards: immutable versions, `expected_version`, ranges, exact refs, structured query, true totals, cursors, a wait counting only versions unread | tested | `test_boards.py` |
| Board text search on FTS5, over names, gists and fields | tested | `test_boards.py`. Bodies are not searched, on purpose. The no-FTS5 refusal is tested by flag, not on a build without it |
| Reading a body held in `blobs/` from an op | deferred | An op may do no I/O, so it returns the hash and the surface reads the body. No surface exists yet |
| Queues: atomic claim, fence, default fence, expiry through timers, `stale_fence`, `max_attempts`, `dead`, `max_inflight`, paging, results read back | tested | `test_tasks.py`, properties |
| `delivery` on queues and boards, as an entry on the channel | tested | `test_tasks.py`, `test_boards.py` |
| Lease renewal from observed harness activity | deferred | `task.renew` is tested, for the runtime too. The host that would call it arrives with drivers |
| Lifecycle: spawn admission and enrolment in one transaction, one `agent.ended`, `on_parent_exit`, retire, interrupt, takeover, the monitor on every ending, a final report kept in the journal | tested | `test_lifecycle.py`, `test_compiled_grants.py` |
| A failed admit, workspace or launch ends the agent `failed`, through the courier, and what it had still to start never starts | tested | `test_lifecycle.py`, on the kernel's supervisor |
| Completion: `settled`, `until`, `session.close`, `session.cancel`, resuming a stopped session, episodes | tested | `test_lifecycle.py` |
| Closing a headless session at `until` | deferred | `session.status` reports `done`. The owner that acts on it arrives with `Session` |
| Approvals: four facts, one winner, per-role policy journaled at open | tested | `test_approvals.py` |
| Exit 4 for an `ask` no human can answer | deferred | Arrives with the headless CLI |
| Budgets: limits, reservations, reconciliation, labels, `over_budget` versus `unavailable`, overshoot bound, a failed wake returning its reservation and a failed steer keeping the turn's, a lost turn counting as unmeasured | tested | `test_budgets.py`, properties. A lost turn with no reservation, which only a harness-started turn can be, charges nothing: `Budgets` has no role for it |
| Client views: `roster` with typed `why`, `attention` with actions, `changes`, `view.watch` | tested | `test_clients.py`. `changes` is fed by a test's report; the turn-end probe arrives with workspaces |
| `blob.get` | tested | `test_lifecycle.py`. A surface stores the bytes first |
| A `body` argument offered as text on the tool plane | planned | Architecture section 10. No tool plane exists, so only `Kernel.put_body` makes a body today |
| Tool descriptions: every argument described, what a refusal means, real op names | tested | `test_tool_surface.py`. Rendering op names per surface arrives with the tool plane |
| `lineage`, `exposure` | deferred | Provenance queries, after drivers |
| Team to session wiring: `Team` roles, limits and groups reaching `session.open` and `group.define` | planned | Both ends exist; nothing joins them yet |

### Teams and topologies (`platoon_harness.team`, `platoon_harness.topology`)

Rows marked tested have CPU-only unit tests in `tests/unit/topology`. No session runs a team yet: the compiled grants are checked
against a real kernel with stand-in ops, and nothing yet journals a team at open.

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
| `Capabilities.measures` and `sandboxes` as drivers report them | planned | No driver exists, so `team_check` takes them as arguments |
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
| Redaction of encoded forms and URLs | planned | Architecture section 15. Only exact values are refused here |
| The manifest: resolved team, components, versions, topology hash | tested | `test_config.py`. Nothing writes `manifest.json` yet |
| Discovery from metadata with no import, in two groups | tested | `test_extensions.py` |
| Duplicates and incompatible SDK requirements caught before import | tested | `test_extensions.py`. Versions compare by release number, so a pre-release suffix is ignored |
| `name`, `name@version` and `module:attr` references, lazy load by exact name, with nothing installed too | tested | `test_extensions.py` |
| Errors listing registered, installed and nearest names | tested | `test_extensions.py` |
| Installing activates nothing | tested | `test_extensions.py` |
