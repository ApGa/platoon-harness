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
| Claim race | planned | |
| Watch race | planned | |
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
| Law 10, for what the kernel owns: unknown stays `None` in the envelope and in `Effect` | tested | `test_laws.py`. Rewards, usage, tool visibility and exposure do not exist yet |
| Law 11: the kernel's own extensions reach no private name, and code outside the kernel imports only `__all__` | tested | `test_laws.py`. No code exists outside the kernel yet, so that half guards an empty set |
| Rebuild equals live, idempotent retry, gapless versions, backward references | tested | `test_properties.py` (hypothesis) |
| Acked commands survive SIGKILL, partial commands are invisible | tested | `test_crash.py` (subprocess) |
| `v`-based upcasting of old payloads | deferred | `v` is recorded. No upcaster exists until a second payload version does |
| `next`, `prev` and `group:x` in `on` | deferred | `grant.add` refuses them until groups exist |
| Credential rotation for a live principal | deferred | Arrives with resume, in M2 |
