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
| `next`, `prev` and `group:x` as kernel relations | deferred | `grant.add` still refuses them. Compilation expands them over roles, so a team never needs them |
| Credential rotation for a live principal | deferred | Arrives with resume, in M2 |

### Teams and topologies (`platoon_harness.team`, `platoon_harness.topology`)

Rows marked tested have CPU-only unit tests in `tests/unit/topology`. No session runs a team yet: the compiled grants are checked
against a real kernel with stand-in ops, and nothing yet journals a team at open.

| Capability | State | Evidence |
|---|---|---|
| `Role`, `Team`, `Topology` as frozen models, with TOML and Python building one object | tested | `test_presets.py` |
| The nine presets, with the worked examples of the research note as tests | tested | `test_presets.py` |
| Union: commutative, associative, a stable hash, conflicts naming both sources, no `deny` | tested | `test_union.py`, properties |
| `compile`: edges, channels, groups, `may_spawn`, lifecycle, `wait` and scopes, enforced by the real `authorize` | tested | `test_compile.py` against stand-in ops. The object names match `primitives` by reading its source, not by running it |
| `next`, `prev` and groups expanded over roles | tested | `test_compile.py` |
| `team_check`: refusals, warnings, did-you-mean, every problem at once | tested | `test_check.py` |
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
| A `command` harness in a project file needs trust | tested | `test_config.py` |
| `Secret`: refuses json, pickle, copy and pydantic, prints as a mask | tested | `test_config.py` |
| Sanitized resolved config: names only, refused if it holds a named variable's value | tested | `test_config.py`. A credential no profile names cannot be recognised |
| Redaction of encoded forms and URLs | planned | Architecture section 15. Only exact values are refused here |
| The manifest: resolved team, components, versions, topology hash | tested | `test_config.py`. Nothing writes `manifest.json` yet |
| Discovery from metadata with no import, in two groups | tested | `test_extensions.py` |
| Duplicates and incompatible SDK requirements caught before import | tested | `test_extensions.py`. Versions compare by release number, so a pre-release suffix is ignored |
| `name`, `name@version` and `module:attr` references, lazy load by exact name | tested | `test_extensions.py` |
| Errors listing registered, installed and nearest names | tested | `test_extensions.py` |
| Installing activates nothing | tested | `test_extensions.py` |
