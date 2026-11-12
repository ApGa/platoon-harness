# Status

Every capability is one of: **planned**, **implemented** (code exists and is exercised by something), **tested** (named tests
pass, and the row says which kind), **experimental** (works, but rests on an unstable upstream surface or lacks coverage) or
**deferred** (a stated decision not to do it yet). An interface, a mock, a screenshot or a TODO does not count as implemented.

A row's evidence names its test files. The fast suite, `uv run pytest`, needs no harness, login or model key. Tests marked
`slow` run the real harness binaries, `e2e` ones drive a real browser, `live` ones call a real model and run only with
`PLATOON_HARNESS_LIVE=1`, and the `scale` test runs alone, by hand, before each release. `FakeModel`, in
`platoon_harness.testing`, is a model server that speaks the APIs harnesses call and answers from a script, so a harness
"against FakeModel" met no real model. `ScriptedDriver`, beside it, is a harness that plays a script on the real tool plane.

## Known limitations

- **Linux only.** Nothing has run on macOS, and no CI job runs there.
- **Agents run as you.** An agent with a shell can do whatever your account can. Approvals and session boundaries are
  workflow controls, not security boundaries, and only the experimental `isolated` workspace confines an agent: see
  [What it does not protect](security.md#what-it-does-not-protect).
- **Few real models.** Claude Code and Codex have run on real models in most live tests. pi and OpenHands have run on one,
  DeepSeek V4.1 Flash, in the examples' live tests.
- **Experimental drivers.** The `claude`, `codex`, `pi` and OpenHands drivers rest on upstream surfaces that are
  undocumented or change quickly. No real ACP agent has passed the ACP driver's checks: OpenCode 2.2.6, run by hand on
  2026-11-08, failed 7 of 18.
- **`isolated` is experimental.** It rests on unprivileged user namespaces, which a kernel setting, AppArmor or a container
  can block, and has run on one Linux host.
- **A short value in an auth profile loses its agent.** A value of a character or two that a profile hands a harness is
  masked inside the ids its reports name, so the agent is lost. Give each such variable a longer value.
- **Memory grows with the journal.** The runtime's resident memory is not bounded: see [Scale](reference/scale.md).
- **No per-agent resource limits.** Budgets bound tokens, money, time and live agents. Nothing limits an agent's memory,
  processes, CPU or disk.

## Not built yet

Planned, each under its row below:

- a driver for Prime Agent;
- switching a running agent's model, and driving an agent's own terminal;
- approval scopes, a denial with feedback, and permission modes;
- image input, a harness's own slash commands, and notifications outside the terminal;
- per-agent resource limits;
- `topology.patch`, `topology.show`, and the library tier beyond `population`;
- the fast tests on macOS in CI;
- diagrams of the process model and of one provenance trace.

A deferred row says what is left out for now, and why.

## Acceptance cases

The cases the first release is held to, each with what it takes to pass. A case's state is that of its evidence, and
**Not met** names any part of what it takes that nothing here shows.

| Case | Passes when | State | Evidence |
|---|---|---|---|
| SDK independence | A headless SDK example runs without the CLI, the TUI, Platoon or ML packages | tested | `tests/integration/test_independence.py`: a script importing only `platoon_harness` runs a session on the `exec` driver and imports no CLI, Textual, Platoon, Torch or Tinker |
| Mixed backends | Two real drivers cooperate, and their capabilities and auth limits are visible | experimental | Live, a Claude Code agent and a Codex agent in one session: `tests/live/test_codex.py`, `test_teams.py`, `test_cli.py`, `test_tui.py` and `test_web.py`; a pi lead and an OpenHands worker on DeepSeek V4.1 Flash: `tests/live/test_examples.py`. Each agent's levels and login kind are journaled and drawn in the terminal's inspector; every live run began with no kept result, so its agents' levels read `unverified`. The browser draws no levels |
| End-to-end collaboration | Spawn, post, query, claim, message, completion and a final artifact work together | tested | `tests/integration/test_vertical_slice.py` and `test_detached.py`, on scripted harnesses; live, a Claude Code lead and two workers in `tests/live/test_teams.py`, which settled the one time it ran on the current preamble and in one of three runs on earlier ones |
| Human parity | The TUI and SwarmChat control the same run through the shared command path | tested | `tests/e2e/test_acts.py`: both clients on one session, each one's message and one approval answered from both, taking effect once; live, `tests/live/test_web.py` |
| Claim race | Concurrent claimants get one valid lease, and a stale claimant cannot complete after reassignment | tested | `tests/unit/primitives/test_tasks.py`, `test_claim_race_*`, with a hypothesis interleaving |
| Watch race | Messages arriving across read, subscribe and reconnect boundaries are not lost | tested | `tests/unit/primitives/test_waits.py`, `test_watch_race_*`, with a hypothesis interleaving of sends, reads, waits and reopening the journal |
| Retry and crash | A retried spawn or send does not duplicate its logical operation, and uncertain effects are surfaced | tested | `tests/integration/test_crash.py` and `test_crash_points.py`, `tests/unit/runtime/test_recovery.py`; live, `tests/live/test_crashes.py`, on Claude Code and Codex. pi and OpenHands have met it against FakeModel alone |
| Provenance | Exact versions and exposures survive compaction and event replay where observable, and gaps are labelled | tested | `tests/unit/primitives/test_provenance.py`, `test_the_provenance_scenario` and a property against a brute-force reading of the journal; on Claude Code, Codex, pi and OpenHands against FakeModel in `tests/integration/`. No check proves a coverage surface yet, so no answer is `not_seen` |
| Identity | Native child reconciliation, run isolation, secret redaction and spoof rejection are tested | tested | `tests/unit/tools/test_mcp.py`, `tests/unit/runtime/test_session.py` and `test_control.py`, `tests/unit/drivers/test_env.py`, `tests/unit/primitives/test_reports.py`, `tests/integration/test_contract.py`. **Not met:** a native child's calls reconciled on a real gateway, which is a training system's to show. Run isolation holds at the tool plane and the control socket, not against an agent's own shell |
| Credit integration | The golden advantages of Recursive Agent Optimization ([RAO](https://arxiv.org/abs/2605.06639)) match, and unsupported, frozen and human traces stay out of RL samples | tested | `tests/unit/primitives/test_eligibility.py`, `tests/unit/runtime/test_annotations.py` and `test_credit.py`, `tests/integration/test_contract.py`. **Not met:** RAO's advantages are a training system's to match, and no released trainer uses this contract yet |
| UI correctness | Resize, focus, history, streaming, approvals, cancellation and reconnect tests pass | tested | `tests/unit/tui/`, `tests/integration/test_tui.py` and `test_tui_budgets.py`, on scripted harnesses and on Claude Code, Codex and pi against FakeModel; the page in `tests/e2e/`, in Chromium and Firefox, and in WebKit in CI |
| Extensibility | A separate sample extension adds a primitive or a driver without modifying the core | tested | `examples/extension-package`, an op, a view and a preset installed from its wheel, in `tests/integration/test_installed_extensions.py`; a driver outside the SDK, as a wire program, in `tests/conformance/test_conformance.py` |
| Git workflow | Independent work, test evidence, merge and conflict handling, and lineage remain inspectable | tested | `tests/unit/runtime/test_workspaces.py`, `test_looks.py`, `test_commit_tests.py` and `test_merge_queue.py`, `tests/unit/tui/test_review.py`, and the Git examples in `tests/integration/test_examples.py`. Only git 2.47.3 has run |
| Scale | At least 100 simulated agents and 100,000 events are exercised with bounded active memory and paginated views | tested | `tests/integration/test_scale.py`: 100 ScriptedDriver agents drive 100,000 events through the real stack, each measure held to a budget of twice what [Scale](reference/scale.md) publishes, or half for throughput. **Not met:** memory grows with the journal, and the roster and attention are read whole, not paged |

## Capabilities

One row per capability, under the module that holds it. A bare test file name is in the folder its section names.

### Kernel (`platoon_harness.kernel`)

Tests in `tests/unit/kernel/`, CPU only.

| Capability | State | Evidence |
|---|---|---|
| Journal: SQLite in WAL with `synchronous=FULL`, one writer held by `flock`, immutable events, a versioned schema and a checkpoint thread, acked commands surviving SIGKILL and partial ones invisible | tested | `test_journal.py`, `test_crash.py`, `test_laws.py`. Durability is tested against SIGKILL, not against power loss |
| Network filesystems refused, tmpfs and unknown filesystems warned of, and closed and live journals opened read-only | tested | `test_journal.py`. Lustre's refusal was seen on a real mount; other network filesystems are simulated |
| macOS filesystem detection and `F_FULLFSYNC` | experimental | Written from the man page, never run |
| The writer: group commit, an ack only after commit, admission limits, a runtime reserve, and every admitted command answered, through a failed commit too, which ends the runtime as a kill would | tested | `test_writer.py`, `tests/unit/runtime/test_recovery.py`. The failures are made by hand: no real disk has filled under a session |
| Gauges, `Kernel.gauges()` and `Txn.gauges()`: events, commits, queued writes, commands in flight, refusals, ack latency, CPU and peak memory, each None where nothing measured it | tested | `test_writer.py`, `test_envelope.py`. Peak memory is None anywhere but Linux |
| Commands and the envelope: idempotency keys, journaled refusals, `expected_version`, strict decoding, stamping, payload limits, `native` ids read by nothing, and old payloads read by their `v` | tested | `test_commands.py` and `test_envelope.py`, properties; `tests/unit/primitives/test_lifecycle.py` |
| `authorize`: grants, live relations, scopes, ops kept to the runtime or to agents, credentials by hash, issued, replaced and revoked, and names unique and safe as a path part | tested | `test_authorize.py`, `tests/unit/primitives/test_lifecycle.py` |
| Bodies: inline or in `blobs/`, fsync before citation, a reader's limit, refs to lines, tombstones, and erased bytes gone from the journal, the WAL and `blobs/` | tested | `test_bodies.py`, `tests/unit/runtime/test_host.py`. Bytes on the device below the filesystem are out of scope |
| Effects and timers: lifecycle, timeouts, `on_uncertain`, priority, the attempt fence, cancelling one before it starts, waiting on another, an extension's own kind, a person settling an uncertain one with `effect.settle`, and the clock daemon | tested | `test_effects.py`, `test_timers.py`, `tests/unit/primitives/test_clients.py`, `tests/unit/runtime/test_recovery.py`, `tests/unit/tui/test_workspace.py`. No extension has an effect kind of its own yet, and no uncertain effect has been settled from the browser |
| Views: versions, per-view rebuild, high-water marks, `rebuild_all`, wildcard folds, and each schema pinned to its version | tested | `test_views.py`, properties, `tests/unit/primitives/test_extensions.py`. What a fold writes is not pinned, so a change there needs its version bumped by hand |
| Readers: `read`, `follow` with one shared read per pulse, `query`, pages read back, live principals only, and live text as a tail bound to its item | tested | `test_readers.py`, `tests/unit/runtime/test_host.py` and `test_control.py`. A sparse stream deep in a long journal takes a page per 4,096 events scanned, as no index serves a stream by `seq` |
| Read-only kernels: schema and staleness checks, a refusal naming the views behind and the fix, and `platoon-harness session refold` | tested | `test_journal.py`, `tests/unit/primitives/test_provenance.py`, `tests/integration/test_cli.py` |
| Daemon supervision with backoff, a daemon that keeps failing said once until a run of it lasts a minute | tested | `test_daemon.py` |
| Extensions: loading, the naming law, and `registry(extensions)`, the op table before any session exists | tested | `test_extension.py`, `tests/unit/runtime/test_session.py`, `tests/unit/cli/test_commands.py` |
| Laws 1 to 12, and rebuild equal to live, idempotent retry, gapless versions and backward references | tested | `test_laws.py`, `test_properties.py`, properties, `tests/unit/runtime/test_control.py` |
| `Kernel.copy`: a journal copied through a seq with the bodies it names, taking no command and running no daemon | tested | `test_copy.py`, `tests/unit/runtime/test_replay.py`. A body redacted after the copied seq reads as not found |
| `next`, `prev` and `group:x` as kernel relations | deferred | `grant.add` refuses them. Compiling a team expands them over roles, so a team never needs them |

### Primitives (`platoon_harness.primitives`)

Tests in `tests/unit/primitives/`, named for the promises of [architecture section 7](architecture.md#7-primitive-semantics),
each comparing live views to a full rebuild at its end.

| Capability | State | Evidence |
|---|---|---|
| Messages: inboxes, topics, `message.send`, addresses, replies, threads, a gist and a body, broadcast to a recorded audience, an inbox's depth cap, hops and `max_hops`, channels and groups | tested | `test_messages.py`, `test_lifecycle.py`, `test_waits.py`, `test_compiled_grants.py` |
| Cursors and delivery states: `offered`, `delivered` and `acked`, filtered reads paging past their window, per-seq acks, and an empty read naming what a handover already gave | tested | `test_messages.py`, `tests/unit/tools/test_mcp.py`; live, `tests/live/test_reads.py`, on Codex |
| Delivery: the injection ladder, coalescing, a steer that degrades visibly, digests with a gap notice, `steer` notices on a tool result, a person's message steering whatever its reader's setting, and nothing withdrawing a sent message | tested | `test_delivery.py`, `tests/unit/tools/test_mcp.py`, `tests/integration/test_cli.py`. A person's message steering a role that pulls has met no real model |
| Interrupts: quieting what waited for the agent, refused before its first turn begins, cancelling a wake not yet begun, and stop below, stopping the turns of an agent and of everyone under it as one act | tested | `test_delivery.py`, `test_lifecycle.py`, `tests/unit/runtime/test_host.py`, and on Claude Code, Codex and pi against FakeModel in `tests/integration/` |
| At-least-once handover and the courier: a failed handover queued again under a new input, back-off, and an agent lost after six failures in a row, where an interrupt or the owner's stop counts as none | tested | `test_delivery.py`, `test_waits.py`, `tests/unit/runtime/test_recovery.py`, and on the real binaries in `tests/integration/test_claude.py`, `test_codex.py` and `test_pi.py` |
| Context and confirmations: `context.offered`, `context.delivered` and compaction, every offer, the launch's too, confirmed only by its harness's own report of the input or by the tool item holding its anchor | tested | `test_messages.py`, `test_delivery.py`, `test_confirmations.py`, `tests/unit/tools/test_mcp.py`, on Claude Code, Codex and pi against FakeModel; live, `tests/live/test_launch.py`. OpenHands' calls go under the shim's own id, so its reads stay unconfirmed |
| Reports and gaps: a compaction's `forgotten` and `summary` as bodies, `call_id`, `purpose` and `native_id` as their harness gave them, `child.seen` claiming no attribution, and one `gap.recorded` per incident from a closed set | tested | `test_reports.py`, `test_gaps.py`, `tests/unit/runtime/test_host.py` and `test_recovery.py`. Claude Code's automatic compaction has not been observed |
| Wait: `on`, `all` or `any`, `after`, `timeout`, `hold`, an atomic check, parking at a turn's end, the waiter's own acts counting, waiting for work on a queue, a one-shot refusal and the `tool_timeout_s` cap | tested | `test_waits.py`, properties, `tests/unit/tools/test_mcp.py`; live, a held `wait` on Claude Code and Codex in `tests/live/test_stays.py`. A task that reopens after a lapse releases no wait for work: pass a `timeout` |
| Lifecycle: spawn admission and enrolment in one transaction, one `agent.ended`, `on_parent_exit`, retire, hold, the monitor on every ending, `crash_window`, and a spawn carrying the anchor of the call that made it | tested | `test_lifecycle.py`, `test_compiled_grants.py`, `tests/unit/tools/test_mcp.py`, and on the real binaries against FakeModel. OpenHands' calls go under the shim's own id, so its children join no call |
| A report to a parent: waking it once for the spawn and once for each of its messages as it lands, a join of N costing one turn, a report held back reaching the turn its wait closes into, and a cut turn's report waking nobody | tested | `test_lifecycle.py`, `tests/unit/runtime/test_session.py`, on Claude Code, Codex and pi against FakeModel; live, `tests/live/test_teams.py` and `test_stays.py`, on Claude Code and Codex. A report held for a wait that a new one replaced waits on that one, and if it never comes the session stalls |
| Failures and stops reaching a parent: a failed turn or a bad end breaking in, and nothing reaching it while a child's stop is under way, until the stop has told the authority | tested | `test_lifecycle.py`, `tests/unit/runtime/test_host.py`. With no `max_hops`, only a budget bounds a model that answers each failure by asking again |
| Staying and finishing: `stays` on a role or a spawn, resolved once and refused on a one-shot harness, and an agent that does not stay finishing once a turn leaves nothing more to come for it | tested | `test_lifecycle.py`, `test_waits.py`, `tests/unit/topology/test_check.py`, `tests/unit/runtime/test_session.py`, on pi and OpenHands against FakeModel; live, `tests/live/test_codex.py`. No live test holds an agent finishing because it does not stay |
| Ending agents: `agent.finish` ending its agent with its turn, finish and retire refused over children at work, `agent.cancel` never refused, a child ending with its parent `cancelled` or `retired`, and a close ending no agent | tested | `test_lifecycle.py`, `tests/unit/runtime/test_session.py`, `tests/integration/test_claude.py`; live, `tests/live/test_teams.py`. An agent left idle at a close has no end in the journal, which is unknown, not `cancelled` |
| Rest: an agent idle ten minutes put to rest where its harness can resume, brought back natively at its next handover, and a harness that exits on its own resting its agent once | tested | `test_lifecycle.py`, `tests/unit/runtime/test_host.py`, and on the real binaries against FakeModel in `tests/integration/clients.py`; live, `tests/live/test_rests.py`, on Claude Code and Codex. What an idle harness costs, and what a resume costs a prompt cache, is not measured |
| Agents with no goal, one-shot agents ending with their turn, and a resumed harness back on its agent as it stood | tested | `test_lifecycle.py`, `tests/unit/runtime/test_opening.py` and `test_recovery.py`, `tests/integration/test_independence.py`, and on each real binary in `tests/integration/` |
| Completion: `settled`, `until`, `session.close`, `session.cancel`, resuming a stopped session, episodes closed on refs, each agent's `said`, `session.ending`, and `stalled` or `needs_human` where nothing can move | tested | `test_lifecycle.py`, `test_citations.py`, `tests/unit/runtime/test_session.py`, `tests/integration/test_cli.py`. Two clients both in `settled()` wait on each other, so give one a timeout |
| Boards: immutable versions, `expected_version`, ranges, exact refs, structured query, true totals, cursors, and text search over names, gists and fields | tested | `test_boards.py`. Bodies are not searched, on purpose |
| Queues: atomic claim, fences, expiry, `stale_fence`, `max_attempts`, `dead`, `max_inflight`, paging, results read back, `delivery` as an entry on the channel, and a lease renewed by its harness's activity | tested | `test_tasks.py`, properties, `test_boards.py`, `tests/unit/runtime/test_host.py`. Activity is a harness's reports: a tool call alone renews nothing |
| Labels: a team's vocabulary, given to tasks and spawns and refused outside it | tested | `test_labels.py`. No real harness has given a label |
| Approvals: four facts, one winner, a per-role policy, moot with the turn that asked, across a crash too | tested | `test_approvals.py`, `tests/unit/runtime/test_recovery.py` |
| Budgets: limits, reservations, reconciliation, labels for what was counted, an overshoot bound, a turn nobody measured whole charged its estimate, and wall time | tested | `test_budgets.py`, properties, `tests/unit/topology/test_check.py`, `tests/unit/runtime/test_opening.py` and `test_recovery.py`. A lost turn with no reservation charges nothing |
| Client views and marks: `roster`, `attention` with the act that settles each kind of place, `changes`, `view.watch`, what waits for an agent, and each person's unread marks in `marks.sqlite` | tested | `test_clients.py`, `test_repo.py`, `tests/unit/kernel/test_daemon.py`, `tests/unit/runtime/test_session.py`, `tests/unit/tui/test_workspace.py`, `tests/e2e/test_acts.py`. Losing the marks file loses only badges |
| Refs and citations: one ref form for everything a model is shown, a ref from every write of content, `blob.get` reading only what its caller was handed or made, `based_on` on the eight writes of content, each event's maker, and a commit's `Informed-By` | tested | `test_citations.py`, `test_provenance.py`, `tests/unit/tools/test_mcp.py` and `test_ph.py`, `tests/unit/runtime/test_looks.py`. A citation says whether the event it names exists, never what it holds |
| The provenance queries `exposure`, `lineage`, `uses` and `contributors`, and `context.show`, from the views `Exposures`, `References` and `Calls`, as `Session` methods and commands, alike after a rebuild and on a closed copy | tested | `test_provenance.py`, `tests/unit/runtime/test_control.py` and `test_session.py`, `tests/unit/cli/test_commands.py`, `tests/integration/test_cli.py`. No check proves a coverage surface yet, so `not_seen` is never answered |
| The provenance queries on Claude Code, Codex, pi and OpenHands against FakeModel: a read, then a write citing it, each answer within its bound | tested | `tests/integration/clients.py`, run by `test_claude.py`, `test_codex.py`, `test_pi.py` and `test_openhands.py`. A compaction on Claude Code, Codex and OpenHands is `unsaid`, and a read through `ph` or by `exec` stays unconfirmed |
| Annotations: rewards and credit beside the journal, in `annotations.sqlite`, by a named producer at a version, with one of five statuses and a value only when scored | tested | `tests/unit/runtime/test_annotations.py`, `tests/unit/cli/test_commands.py`, `tests/integration/test_cli.py`. One producer ships, `propagate@4`; judged attribution and validated intervention are not built |
| Asking agents to cite: the `{citing}` slot of the default template | tested | `tests/unit/tools/test_surface.py`; live, `tests/live/test_citing.py`. How often agents cite is not measured: in two live runs, one on Claude Code and one on Codex, each citation named what its citer had been shown |
| `eligibility(agent, episode)`: an agent's attribution, and each bar to training on it or on a page of its calls | tested | `test_eligibility.py`, `tests/unit/runtime/test_training.py`, `tests/unit/cli/test_commands.py`. ScriptedDriver, pi and OpenHands have been `exact` on FakeModel acting as a gateway; no real gateway has been behind one |
| `spans(agent)`: each turn cut after each model call that chose a write of content, with the claims held and the labels worked under | tested | `test_spans.py`, `tests/unit/cli/test_commands.py`, `tests/integration/test_contract.py`. No test reads a claim or a cut at a write in a real harness's spans, so where those fall there rests on the joins each driver is tested to make |
| `session.metrics`: events, refusals, agents by group and trainable level, coverage, gaps and the kernel's gauges, each None where nothing measured it | tested | `test_metrics.py`, `tests/unit/runtime/test_session.py`. Nothing measures an agent's harness processes |
| Who reached whom, `interactions`: each pair of makers and the edges between them by kind, never summed, with each agent's unknowns | tested | `test_interactions.py`. No real harness's session has been asked |
| `platoon_harness.patterns`, the library tier, holding `population`, which git-swarm runs under | tested | `tests/unit/patterns/test_population.py`, `tests/unit/kernel/test_laws.py` |
| The rest of the library tier: `scatter`, `gather`, `reduce`, `barrier`, `latch`, `semaphore`, `lock`, `request`, `vote`, `supervisor`, `verifier_generator` | planned | Each waits for a user |
| `topology.patch`, `topology.show` | planned | Neither is in the registry. `topology.patch` waits for a program that needs a live rewire, and `topology.show` for a team view that draws reachable pairs |
| One reward per task of a child that stays | deferred | `propagate@4` gives each span its own row, so a persistent worker's tasks get separate credit rows; training each span on its row is the training system's |

### Tool plane (`platoon_harness.tools`)

Tests in `tests/unit/tools/`, against a real `Kernel`, a compiled team and a real socket on port 0.

| Capability | State | Evidence |
|---|---|---|
| Tools derived from `ops.list` per token: names per surface, closed schemas, an honest `readOnlyHint`, every argument described, no sentence naming a tool its reader lacks, and a ceiling on each default role's list | tested | `test_surface.py`, `tests/unit/primitives/test_tool_surface.py`, `tests/unit/runtime/test_host.py` |
| The preamble: tools, who can be reached, which roles can be started, how to wait and how to end, from a template on `Team` or `Role` with nine slots, each label's values among them | tested | `test_surface.py`, `tests/unit/runtime/test_host.py`, `tests/unit/topology/test_check.py`, `tests/unit/primitives/test_labels.py`. It reaches a harness once, at launch, so who can be reached goes stale until `peers` is asked |
| `agent.instructed`: the exact text the runtime adds to a harness, journaled at each launch and resume | tested | `tests/unit/runtime/test_host.py`; live, `tests/live/test_launch.py`, on Claude Code and Codex. The harness's own prompt and your configuration are not recorded |
| `told(team)`: what an agent of each role would be told, starting no harness | tested | `tests/unit/runtime/test_host.py` and `test_opening.py`, `tests/integration/test_cli.py` |
| Refusals a model can act on: a code, what it means and what to do next, in the words of its surface | tested | `test_surface.py`, `test_mcp.py` |
| Paging and caps: `peers` and `channel.list` a page at a time, results capped with `rest` saying where the rest is, and an answer past 32 KiB refused with its size | tested | `test_mcp.py` |
| Retries and repeats: an idempotency key making a retry one operation, and identical calls in one turn with no client id made one, labelled a repeat | tested | `test_mcp.py`, `tests/integration/test_pi.py`. A stated trade-off: a key that told them apart would run a retry twice after a lost ack |
| The server: Streamable HTTP with JSON replies and no sessions, protocols `2025-11-25` and `2025-06-18`, bounded HTTP, and an `Origin` that must be its `Host`'s | tested | `test_mcp.py`, `test_replay.py` |
| Identity from the token alone: tools filtered and enforced again at call time, undeclared arguments journaled, and an ended agent's or another session's token refused | tested | `test_mcp.py` |
| Held waits: one closing only once its answer has left, an idle client costing nothing, and one that vanishes freeing its server task and keeping its wait | tested | `test_mcp.py` |
| Calls at once: several agents' calls in flight with a held `wait` among them, and queries run off the event loop | tested | `test_mcp.py`, `test_shim.py`, `tests/unit/runtime/test_looks.py`. A saturated thread pool is not measured |
| `ph`, its argv and help from `tools/list`, and the stdio shim, which pi and OpenHands reach our tools through | tested | `test_ph.py`, `test_shim.py`, `tests/integration/test_pi.py` and `test_openhands.py` |
| MCP clients against this server: the official client, Claude Code and Codex | tested | `tests/conformance/test_mcp_client.py`, on `mcp` 2.3.0; `tests/integration/test_claude.py` and `test_codex.py`, against FakeModel; live, `tests/live/test_claude.py` and `test_codex.py`. The official client's `2026-07-28` mode is not claimed and not run |

### Drivers (`platoon_harness.drivers`, `platoon_harness.rpc`, `platoon_harness.testing`)

Tests in `tests/unit/drivers/`, `tests/conformance/` and `tests/integration/`, on real subprocesses and sockets on Linux; a
bare name is in `tests/unit/drivers/`.

| Capability | State | Evidence |
|---|---|---|
| One JSON-RPC peer, and `Lines` for a line protocol that is no JSON-RPC | tested | `test_rpc.py` |
| The driver contract: seven methods, `DriverInfo`, `AgentSpec`, `ToolBinding`, `Delivery` and one closed report vocabulary, with what the runtime concludes beyond any driver's claim | tested | `test_public_api.py`, `test_wire.py`, `tests/unit/primitives/test_reports.py` |
| Levels: a pure function of a conformance result pinned to its driver, the harness's version, the SDK and the host, kept on your machine by `doctor --check` | tested | `test_levels.py`, `tests/unit/runtime/test_host.py`, `tests/integration/test_cli.py` and `test_sealed.py`, and on each real binary against FakeModel. A result proves no coverage surface, so nothing answers `not_seen` |
| `Process`: a harness in its own process group, recorded before it can exec, stopped by the end of stdin, TERM and then KILL, verified, with pipes that always drain, stderr in a bounded masked log, and what it started outside its group ended | tested | `test_process.py`, `test_wire.py`, on Linux. Of what a harness starts outside its group, a process that clears its environment escapes, and a harness running as you can forge its process records |
| `Process` on macOS | experimental | `ps -o lstart=` and the rest are written from the man page and have never run |
| The harness's environment: an allowlist, a `HOME` in the spec as its home, `AgentSpec.wrap` for an isolation, and `DriverInfo.installed`, the paths each harness reads to run | tested | `test_env.py`, `test_process.py`, `test_wire.py`, `test_claude.py`, `test_codex.py`, `test_pi.py`, `test_openhands.py`, `test_exec.py`, `tests/integration/test_isolated.py` |
| `DriverInfo.credentials`: where beneath its folder each harness keeps a credential, refused if it could leave that folder | tested | `test_wire.py`, `test_openhands.py`, and on the real binaries in `tests/integration/test_pi.py`, `test_codex.py` and `test_claude.py`. Claude Code's `.credentials.json` and pi's and Codex's MCP-server logins are read from their code, as no test signs in through a browser |
| `WireDriver` and `serve`: a program driven over the wire, `describe` among its verbs | tested | `test_wire.py`, `tests/conformance/`, `tests/integration/test_scripted_tool_plane.py` |
| The `exec` driver: a one-shot command with `{goal}` and `ph` on its path, and the `exec` and `wire` entry points | tested | `test_exec.py`, `tests/unit/config/test_config.py`, `tests/conformance/` |
| The test kit: `ScriptedDriver`, every step of a script on real MCP and real model calls, and `FakeModel`, three API dialects, whole and streamed, and a gateway with its own bearer and tools | tested | `test_scripted.py`, `test_fake_model.py`, `tests/conformance/test_conformance.py`, `tests/integration/test_scripted_tool_plane.py` and `test_fake_model_clients.py` |
| `check_driver`: named checks, every failure at once, a skip never a pass, and nothing left running | tested | `test_check_driver.py`, and on `claude`, `codex`, `pi` and `openhands` against FakeModel. Codex reports no `call_id`, so that check skips |
| What `check_driver` cannot prove yet: `tool_timeout_s`, `coverage` and `sandboxes` | deferred | The `declared_but_unproven` check names them where declared and always skips |
| On each real binary against FakeModel: the tool block and the preamble held still across calls and resumes, what a client reads, and several agents' tools running at once | tested | `tests/integration/test_request_shape.py`, `clients.py` and `parallel.py`, run by `test_claude.py`, `test_codex.py`, `test_pi.py` and `test_openhands.py`; [Compatibility](reference/compatibility.md#tool-calls-at-once) says what each harness does. OpenHands runs one response's calls in turn, and a live Codex's tool block cannot be read |
| An approval carrying its whole ask, the command, patch or tool input, cut at 64 KiB, from every driver | tested | `tests/unit/primitives/test_approvals.py`, `tests/unit/runtime/test_host.py`, `test_wire.py`, `test_check_driver.py`, and on the real binaries. A driver that sends no ask fails `approval_shows_its_ask` and is not `operational` |
| The `claude` driver: `claude -p` stream-json and the control protocol, every report, resume, interrupt, approvals through the runtime, a steer at a tool boundary, and `stop` ending a running tool | experimental | `test_claude.py`; `tests/integration/test_claude.py`, every check against FakeModel; live, `tests/live/test_claude.py`, `test_teams.py` and `test_crashes.py`. It rests on surfaces undocumented upstream, and automatic compaction, nested children and parallel tool batches have not run |
| The `codex` driver: `codex app-server` on one peer, every report, resume, interrupt across native children, approvals through the runtime, a steer at a model call, and `stop` ending a running tool | experimental | `test_codex.py`; `tests/integration/test_codex.py`, every check against FakeModel on 0.164.0 and 0.167.0; live, `tests/live/test_codex.py`, `test_teams.py` and `test_crashes.py`. The app-server is labelled experimental upstream, and automatic compaction has run only against FakeModel |
| The `pi` driver: `pi --mode rpc` in your own agent directory, our tools through the stdio shim, every report but `child.seen`, resume, interrupt, approvals, a steer at a model call, compaction naming what it forgot, and `stop` ending a running tool | experimental | `test_pi.py`; `tests/integration/test_pi.py`, every check against FakeModel; live, `tests/live/test_examples.py`, on DeepSeek V4.1 Flash. It pins pi 1.5.0, no OAuth login has met it, and on a loaded machine `pi --version` can outlast the 5 s a status command gets |
| OpenHands as a wire worker: the `openhands` extra, OpenHands' SDK and tools pinned at 1.59.0, one worker process per agent, every report but `child.seen`, resume, interrupt, approvals, a steer between runs, compaction naming what it forgot, and `stop` ending a running tool | experimental | `test_openhands.py`; `tests/integration/test_openhands.py`, every check against FakeModel; live, `tests/live/test_examples.py`, on DeepSeek V4.1 Flash. It pins 1.59.0, as the SDK moves fast |
| The ACP driver, architecture section 9.5, `AcpDriver`, a driver of the SDK's own: ACP agents on protocol 1 over the SDK's own `Peer`, a permission request through the runtime's approvals as its whole ask, a role on it allowing an agent's own agents, which ACP cannot turn off, and no agent on it trainable | experimental | `test_acp.py`; `tests/conformance/test_conformance.py`, on a scripted ACP agent. No real ACP agent has passed its checks |
| The `opencode` driver: `AcpDriver` on `opencode acp`, a start that names no model refused, and its own check | implemented | `test_acp.py`, `tests/integration/test_acp.py`. On OpenCode 2.2.6 against FakeModel, run by hand on 2026-11-08, its check passed 11 checks and failed 7, as OpenCode asked a session's title on the side and shows our tools only through its own `execute` tool |
| The `prime` driver, for Prime Agent, by `--mode rpc` or ACP as a live probe decides | planned | Nothing beyond its version and help has run |
| A role's settings handed to its harness: the harness's own agents off unless the role allows them, and `sandbox` and `effort` handed over as they stand or refused | tested | `test_check_driver.py`, `test_claude.py`, `test_codex.py`, `test_pi.py`, `test_exec.py`, `test_scripted.py`, `tests/unit/runtime/test_host.py` and `test_opening.py`, `tests/unit/topology/test_check.py`; live, `tests/live/test_launch.py`. pi has no agents of its own in core, and an extension's own cannot be turned off |
| A role with no auth profile signing in as the harness does in your shell | tested | `test_claude.py`, `test_codex.py`, `test_pi.py`, `test_openhands.py`. A proxy or a certificate file from your shell rests on these tests alone |
| `check_extension`: names, the naming law, schemas, descriptions, the public API and rebuild equal to live, naming each part of an extension it does not check | tested | `test_check_extension.py`, `tests/integration/test_installed_extensions.py`. A pass vouches for none of an extension's daemons, presets or isolation |
| `docs/extending/drivers.md` and `docs/reference/compatibility.md` held to the code | tested | `test_docs.py`, `tests/unit/docs/test_compatibility.py`. The compatibility page's facts about upstreams are held to nothing |
| The SDK's imports: the standard library and pydantic, and the `openhands` extra in its worker alone | tested | `test_boundaries.py` |
| Sealed launches on a gateway: nothing of yours and none of the harness's own tools, the gateway's model under its bearer, compaction labelled at call time, and the two checks `trainable` stands on | tested | `test_sealed.py`, `test_pi.py`, `test_check_driver.py`, `test_levels.py`; `tests/integration/test_pi.py`, `test_openhands.py` and `test_sealed.py`. Only FakeModel has acted as a gateway |

### Runtime (`platoon_harness.runtime`, `platoon_harness.session`)

Tests in `tests/unit/runtime/` and `tests/integration/`, on real sockets and subprocesses on Linux, with scripted harnesses
on the real tool plane; a bare name is in `tests/unit/runtime/`.

| Capability | State | Evidence |
|---|---|---|
| The root: chosen, from the environment or the state home, and refused where another user owns it or can write it | tested | `test_paths.py`, `tests/integration/test_cli.py` |
| The session folder: unique names, a private socket, `runtime.json`, tokens at 0600, names safe as path and branch parts, and sessions listed by scan | tested | `test_paths.py`. A detached runtime's socket has not been run across a logout |
| Opening: `team_check` on each driver's `describe` before any cost, the manifest, roles, limits, grants, channels, groups, budgets and starting agents, and opening again after a crash part of the way | tested | `test_opening.py` |
| Effects performed level-triggered, each a task of its own, so one agent's hung handover holds up no other's, and a handover, an interrupt or an answer to a harness that stops reading cut off at a minute | tested | `test_host.py`, `test_looks.py`, `test_recovery.py`, `tests/integration/test_kill_matrix.py`, `tests/unit/drivers/test_claude.py`. A failed interrupt or answer leaves its turn open until a wall limit ends it |
| The host: an agent's token in memory and its hash in the journal, `ph` on its path, the preamble then the role's own words, deliveries in the words of their surface, model pinning, and `assurance`, `isolated` only for a confined launch | tested | `test_host.py`, `test_isolation.py`, `tests/unit/tools/test_surface.py`, `tests/integration/test_isolated.py`. That a model alias a harness resolves fails its spawn is reasoned from a probe, not run |
| `agent.hold` and `agent.release`: an agent's deliveries held, the gap `hold` recorded where it begins | tested | `test_host.py`, `tests/unit/primitives/test_gaps.py`. Driving the native session during a hold, `/takeover`, is not built |
| Failing loudly: a report stream that dies, a driver that raises or a harness that never says ready ending `exited` with a gap, a bounded shutdown, every process tree gone with its agent, and several runtimes in one process | tested | `test_host.py`, `test_public_api.py`. A Python driver whose background task dies without a word is out of reach |
| Credentials masked in every driver's reports, live text and failed effects, and in the runtime's log | tested | `test_host.py`, `tests/unit/drivers/test_env.py`, `test_exec.py` and `test_wire.py`; live, `tests/live/test_teams.py` |
| Per-agent resource limits: the memory, processes and CPU of an agent's process tree, and the disk a session takes | planned | Nothing limits them, and nothing bounds a journal, its `blobs/` or a workspace. `session.metrics` reports the runtime's own use |
| Recovery: a turn a crash or a stop cut told on resume, per-agent reap, resume and reconcile on fresh credentials, a goal told again, a wake the budget refuses ending `needs_human`, and a resume under other versions labelled | tested | `test_recovery.py`, `tests/integration/test_crash.py` and `test_kill_matrix.py`; live, `tests/live/test_crashes.py`, on Claude Code and Codex. pi has met it against FakeModel alone |
| A sweep of crash points: a journal cut at each command boundary of a team's run and resumed, no effect left started and rebuild equal to live | tested | `tests/integration/test_crash_points.py`. It cuts the journal alone, so it says nothing of blobs, agent folders or process records |
| `Session`: `start`, `attach` and `resume`, typed wrappers checked against the registry, the body API, `Ending`, `settled()` and its six reasons, `head()`, and `detach=True` | tested | `test_session.py`, `test_control.py`, `tests/integration/test_detached.py` and `test_cli.py` |
| The control socket: a credential checked once, the principal bound, refusals as data, long-polls, a reader that stops dropped, view and control credentials, and reads answered as queries | tested | `test_control.py`. A view credential reads and never writes |
| No runtime token, the owner's, the view's or an agent's, in a session's folder after a clean stop or close, and an ended agent's scratch and credential files removed by its stop, before its authority hears of the end | tested | `test_session.py`, `test_host.py`, `tests/unit/drivers/test_process.py`, `tests/integration/test_crash.py` and `test_contract.py`. A killed runtime's dead token files stay until the next stop, and an agent that has not ended, such as one idle at a close, keeps its files |
| Guests: reconnecting from a cursor, falling back to history and finding the next runtime, two racing a message and an approval, and leaving or attaching to a closed session changing nothing | tested | `test_control.py`, `test_session.py`, `tests/unit/kernel/test_journal.py`, `tests/integration/test_crash.py`, `test_detached.py` and `test_vertical_slice.py` |
| A session's principal, a person, `human:<name>`, or a program, `program:<name>`, and a program as a script that owns its session and runs again against what the record holds | tested | `test_session.py`, `test_opening.py`, `test_programs.py`, `tests/unit/config/test_config.py`, `tests/unit/topology/test_check.py`, `tests/integration/test_cli.py` and `test_tui.py` |
| Training authorities: `Authority` and `LocalAuthority`, a `Gateway`, and a session started trainable never resumed | tested | `test_authority.py`, `test_training.py`, `test_host.py`, `test_opening.py`, `test_recovery.py`, `tests/unit/drivers/test_env.py` and `test_sealed.py`. Only a test's authority has given a gateway |
| `worktree`: a linked worktree of your repository on a branch of its own, made in steps a crash resumes from, refused before any cost where git cannot hold it, and a Codex role whose sandbox keeps `.git` read-only warned of | tested | `test_workspaces.py`, `test_recovery.py`, `tests/integration/test_worktree_crashes.py`, and on Claude Code, Codex and pi against FakeModel; live, `tests/live/test_worktrees.py`. Only git 2.47.3 has run |
| The runtime's own git, through one runner with no hook, fsmonitor, gc, prompt or remote, and a workspace's end: a worktree removed only when nothing would go with it, and the recorded commits kept in `commits.bundle` | tested | `test_diffs.py`, `test_ending_workspaces.py`, `tests/integration/test_worktree_crashes.py`. Only git 2.47.3 has run |
| `snapshot`: a repository of its own holding your tree as your git sees it, uncommitted and untracked work included | tested | `test_snapshots.py`, `tests/integration/test_worktree_crashes.py`; live, `tests/live/test_worktrees.py`. Capture and pack cost on a large dirty tree are not measured |
| `isolated`: a snapshot whose harness, and all the runtime runs in its tree, an isolation confines, writing only its agent's folder and a private /tmp, finding your home and the session root hidden, and seeing only its own processes, though it still reads what you can read elsewhere and reaches the network and every loopback service | experimental | `tests/integration/test_isolated.py`, on Claude Code, Codex, pi and OpenHands against FakeModel, and `test_bwrap.py`. It rests on unprivileged user namespaces, which a kernel setting, AppArmor or a container can block, and has run on one Linux host, on bubblewrap 0.4.1 |
| `isolated` refused at exit 78 before any cost where it cannot confine, and the runtime's own git in an isolated tree run through the agent's wrap | tested | `test_isolation.py`, `tests/unit/topology/test_check.py` |
| A plan login refused for several agents headless, unless the start opts in with `--plan-login` or `plan_login=True` | tested | `test_opening.py`, `tests/unit/drivers/test_claude.py`, `tests/integration/test_cli.py`; live, `tests/live/test_claude.py` |
| A short value an auth profile hands a harness kept out of the ids its reports name | deferred | A known defect: a value of a character or two, such as `PI_OFFLINE=1`, is masked inside those ids, so the agent is lost. Give each such variable a longer value, as [Troubleshooting](how-to/troubleshooting.md) says |
| The look and the `changes` view: each turn's end looked at, one look at a time in a workspace and at once across them, each commit recorded as its maker's, and each commit's latest runtime test and each uncommitted path | tested | `tests/unit/primitives/test_repo.py`, `test_looks.py`; live, `tests/live/test_worktrees.py`. Look cost past 100,000 files is not measured, and two makers in one second make a commit nobody's |
| `repo.test`: a runtime test of a commit, a person's or a program's act, run as you in a clean checkout | tested | `tests/unit/primitives/test_repo.py`, `test_commit_tests.py`, `tests/unit/drivers/test_process.py`, `tests/unit/config/test_config.py`. A clean checkout lacks untracked and ignored files, so its outcome can differ from the agent's own run |
| `repo.diff`, a commit's patch or a workspace's uncommitted diff for a person or a program, and `repo.commit`, an agent's read of a recorded commit by its SHA | tested | `tests/unit/primitives/test_repo.py`, `test_diffs.py`, `test_recovery.py`, `test_isolation.py`, `tests/unit/tools/test_surface.py`. A diff's cost past 100,000 files is not measured |
| A conflict as a place that needs you: an agent resting on one its look found, and your checkout's | tested | `tests/unit/primitives/test_repo.py`, `tests/unit/tui/test_review.py`, `tests/e2e/test_acts.py` |
| The merge queue for worktree teams, written out in [Topologies](how-to/topologies.md): workers add to a `merges` queue, a merger merges with git, and a conflict reaches its worker as its task's result | tested | `test_merge_queue.py`, on real git with scripted harnesses; `tests/unit/topology/test_docs.py` |
| `git-swarm` and its population program: one outcome for each worker, recorded once by the program, a worker building on a peer's nominated commit, and anything but worktrees refused | tested | `tests/unit/topology/test_presets.py` and `test_check.py`, `tests/unit/patterns/test_population.py`, and the git-swarm example under Teams and topologies. Choosing among the nominations is yours, with no winner read out |
| `platoon_harness.credit.propagate`, `propagate@4`, experimental and heuristic, in the one producer signature, at version 4 in place of 1, 2 and 3: an episode's team reward split back along causes, ancestry and citations into a row for each span and agent it reaches, a claim's share split among the spans that held it | tested | `test_credit.py`, properties, `tests/integration/test_contract.py`, on pi and OpenHands against FakeModel. No test has shared a claim's credit on a real harness's session |
| The training contract's tests: a training authority's whole use of the SDK, and an isolated agent launched sealed on its gateway | tested | `tests/integration/test_contract.py`, on ScriptedDriver, a wire program, pi and OpenHands against FakeModel acting as a gateway. The isolation's start-up probe has stalled past 10 s on a loaded machine, for a cause not known |
| `Replay`: a read-only copy of a session through a playhead, in `replays/` under the root, `seek` going either way through its checkpoints | tested | `test_replay.py`, `tests/integration/test_replay.py`. An installed extension's own views are not built in a replay, and nothing has measured one at 100,000 events |

### Command line (`platoon_harness_cli`)

Tests in `tests/unit/cli/` and `tests/integration/test_cli.py`, which runs the installed `platoon-harness` against scripted
harnesses on the real tool plane.

| Capability | State | Evidence |
|---|---|---|
| A command for each op a person may run, made from the op registry with a flag per argument, its help in a person's words, and `docs/reference/cli.md` made from the definitions | tested | `test_commands.py` |
| `docs/getting-started/first-session.md`: the mixed team on a model you name, and the reads of its closed session | tested | `tests/integration/test_examples.py`, on pi and OpenHands against FakeModel; live, `tests/live/test_examples.py`, on DeepSeek V4.1 Flash in 27 model calls |
| `run`: a team from the project file, a team file or `--harness`, a prompt to every agent or to `--to` alone, `--json`, `--approvals`, and never a prompt of its own | tested | `test_cli.py`, `tests/unit/topology/test_check.py` |
| Exit codes: each reason of an Ending, 64 for usage, 74 for a failed commit, 78 for configuration, and 130 on Ctrl+C or `SIGTERM`, the session resumable | tested | `test_cli.py`, `test_commands.py`, `tests/unit/runtime/test_session.py` |
| `events`, from `--after` or `--follow`, as a guest on a view credential, and acting from a second process: a message, an interrupt, retire, cancel, an approval, a board post, and a command run again under its `--key` | tested | `test_cli.py` |
| `session list`, `show`, `stop`, `resume` and `refold`, `serve`, `team check`, `team show` and `team told` | tested | `test_cli.py` |
| `init` from the harnesses on PATH, and `doctor`, saying each harness's version, login kind and conformance result | tested | `test_cli.py`, `test_machine.py` |
| `extension list`, and an installed extension's op as a command | tested | `test_cli.py`, `test_commands.py`, `test_machine.py`, `tests/integration/test_installed_extensions.py` |
| `run` on each real binary against FakeModel, stopped mid-turn and resumed | tested | `tests/integration/test_cli_harnesses.py`. It skips a binary that is not installed, and a skip proves nothing |
| The command line on real models: a team from `init` run headless, a message from a second process, `events --follow`, a stop and a resume, and an interrupt under a `tokens` limit | tested | `tests/live/test_cli.py` and `test_interrupts.py`, on Claude Code and Codex. pi and OpenHands have run none of this live |
| `attach`, and a bare `platoon-harness` opening the terminal UI | tested | `tests/integration/test_tui.py` |
| `web SESSION`, serving loopback unless `--host` names another address, and `web` with no session, the sessions page on loopback alone | tested | `tests/integration/test_web.py`, `tests/unit/web/test_page.py` |
| The team editor's shared part, `team_editor.py`, which both clients draw | tested | `test_team_editor.py`. A model is free text, as no driver lists the models its harness takes |
| `replay.py`: a replay's controls, worded alike in both clients | tested | `test_replay.py`, `test_provenance.py` |
| `export`, a command | deferred | The session folder as it ended is the export, read through `Session.attach` once its runtime has stopped |

### Terminal UI (`platoon_harness_cli.tui`)

Pilot tests in `tests/unit/tui/` attach to a session the test owns, and `tests/integration/test_tui.py` runs a detached
runtime, all on scripted harnesses. [The terminal UI](how-to/tui.md) is the guide.

| Capability | State | Evidence |
|---|---|---|
| The sessions screen: every session under the root, one started from the project's team or a team file, resumed or stopped | tested | `tests/integration/test_tui.py`, `test_keymap.py` |
| Detaching with `/detach` or Ctrl+D and leaving with `/quit` or Ctrl+Q, the runtime running on; a session with no runtime opened as history, `/resume` offered; and a runtime stopped, resumed or killed shown as what it is | tested | `tests/integration/test_tui.py`, `test_workspace.py` |
| The navigator, the inspector and the header: agents grouped by what you must do, why an agent waits, what it runs on and has spent, and how the session stands | tested | `test_workspace.py`, `test_snapshots.py` |
| The look, motion and toasts: titled panels, themes and logos, agents' glyphs moving from the roster's state, and a toast when an agent comes to need you while another is in view | tested | `test_logo.py`, `test_motion.py`, `test_workspace.py`, `test_snapshots.py`. Frames and colours have been seen only as images, in no real terminal |
| The transcript: a line per event, a call's start and end as one line, a child drawn under the call that made it, following as one state, and links followed only to `http` and `https` | tested | `test_transcript.py`, `test_safe.py`, `test_workspace.py`, `tests/unit/cli/test_calls.py`, `tests/integration/clients.py`. A call whose start and end name no id is drawn as two calls |
| Layout at 120, 80 and 60 columns and 16 rows, a resize changing neither the scroll position nor the composer's target | tested | `test_snapshots.py`, `test_workspace.py` |
| The composer: multiline, its target shown and changed with `@agent` or `#channel`, history, a file as the body, and typed commands that never reach an agent | tested | `test_workspace.py`, and on Claude Code, Codex and pi against FakeModel in `tests/integration/clients.py` |
| Every act by a typed command, from one keymap table that makes the bindings, the help, the footer, the palette's acts and the guide's keymap | tested | `test_keymap.py`. Keys were tried on no Mac and in no editor's terminal |
| The dock and approvals: each place you must act, never taking focus by itself, its letters answering only a place you chose, an ask read before answering as whole as the record holds it, and who answered drawn in the transcript | tested | `test_workspace.py`, `test_transcript.py`, `test_safe.py` |
| Esc interrupting the agent in view, and `/stop-below`, each disabled with the runtime's reason where it would stop nothing | tested | `test_workspace.py` |
| The palette: each write op you hold, as a form | tested | `test_workspace.py` |
| Drawing: one coalescer between the journal and the widgets, at most 15 frames a second, dropping frames and never events, and `SafeText`, the one boundary for untrusted text | tested | `test_workspace.py`, `test_safe.py` |
| Responsiveness budgets: event-loop lag at 100 agents, an append to a large history, resident memory, and a live session's motion at rest | tested | `tests/integration/test_tui_budgets.py`, measured on a loaded shared machine, in short runs |
| A headless `run` never importing Textual | tested | `tests/integration/test_tui.py` |
| Provenance: `p` or `/provenance` on a line, `/reached`, a ref opened from a message's text or by hand, and spans drawn | tested | `test_provenance.py`, `test_transcript.py`, `test_snapshots.py`, `tests/unit/cli/test_provenance.py`, `tests/integration/test_claude.py`. No real harness has shown a turn cut at a write |
| `/review` or Alt+D: what changed, by workspace, each commit's patch and each uncommitted diff read a page at a time, and a comment citing their lines | tested | `test_review.py`, `test_snapshots.py` |
| The tasks and board views, `/tasks` or Ctrl+T | tested | `test_tasks.py`, `test_keymap.py`, `tests/unit/cli/test_channels.py` |
| Words found with `/find` or Ctrl+F, threads with `/thread`, text copied with Ctrl+C or `/copy`, and the mouse beside each key | tested | `test_workspace.py`, `test_keymap.py`, `test_transcript.py`, `test_rows.py`. Some terminals take no OSC 52, or none past a length of their own: hold Shift as you drag to select natively |
| A newcomer's start: the sessions screen offering to write a team, as `init` does, and a harness that cannot start saying what `doctor` finds of it | tested | `tests/integration/test_tui.py` |
| The team editor, `e` on the sessions screen | tested | `test_editor.py`, `test_snapshots.py`, `tests/integration/test_tui.py` |
| A replay, `attach SESSION --replay` or `R` on the sessions screen | tested | `test_replay.py`, `test_keymap.py`. Driven by Pilot alone, in no real terminal |
| The terminal UI on real models and native logins | tested | `tests/live/test_tui.py`, on Claude Code and Codex. pi and OpenHands have run none of it live |
| Switching an agent's model, Alt+M or `/model` | planned | The driver contract carries no switch of model, and each harness differs. The key and typed command say it is planned and send nothing |
| Driving an agent's own terminal, Alt+T or `/takeover` | planned | The driver contract carries no terminal, and each harness differs. `agent hold` holds an agent's deliveries and no more, and the key and typed command say so and send nothing |
| Approval scopes, such as for this session, a denial with feedback, and permission modes | planned | Whether each harness honours a scope is unverified, so offering one could fail silently |
| Image input, a harness's slash commands, and notifications outside the terminal, its bell or the desktop's | planned | The driver contract carries none of them, and each differs per harness. A message beginning with `/` that is none of the typed commands is asked about |
| Credit drawn beside who contributed, and a part of the provenance panel paged in place | deferred | RFC 0043 rejects both: credit beside a maker would read as its share of the outcome, and paging each part would mix pages read at different heads |

### SwarmChat (`platoon_harness_cli.web`)

Tests in `tests/unit/web/`, over a session the test owns on scripted harnesses, in `tests/integration/test_web.py`, and in
`tests/e2e/`, marked `e2e`, in Playwright's Chromium and Firefox, each failing on any page error; CI runs `tests/e2e/` in
WebKit too. [The browser](how-to/web.md) is the guide.

| Capability | State | Evidence |
|---|---|---|
| SwarmChat 0.1.0's page files, each held to its SHA-256 and put together as upstream's server does, and the projection, a one-way fold into `swarmchat.sqlite` rebuilt from nothing equal to the fold made live | tested | `test_page.py`, `test_projection.py` |
| What a chat holds: messages, reports, goals, an approval as a card, a body as its gist or a file, and "Delivered to" from delivery evidence alone | tested | `test_projection.py`, `test_server.py`. A picture is offered as a download and not drawn |
| Every view the page reaches, in SwarmChat's own reply shapes, and the feed, a long-poll held at most 25 s | tested | `test_server.py`, `test_board.py`, `test_conformance.py` |
| Links and requests: a link opening once and expiring unspent, view and control links, `Host` on every request and `Origin` on every POST checked, and bounds before belief | tested | `test_server.py`, `tests/e2e/test_guards.py` |
| Acts into `Session.submit`: the kernel's grants deciding, and each act one operation from any link, across an offline window, a lost answer and a reload | tested | `test_server.py`, `tests/e2e/test_follow.py` |
| Browsing that writes no event and moves no cursor or mark, and history: what happened shown, every act disabled naming `platoon-harness session resume`, and a runtime that comes back followed | tested | `test_server.py`, `tests/e2e/test_follow.py` |
| The page in a real browser: its link spent, a message from another shell drawn live, a reload drawing nothing twice, your message entering the agent's input once, replies in threads, and the terminal attached at once | tested | `tests/e2e/test_web.py`, `test_acts.py` and `test_harnesses.py`, `test_server.py`, `tests/unit/cli/test_commands.py` |
| Approvals in the page: a card with Allow and Deny, Needs you, a race between clients taking effect once, and an ask read before answering as whole as the record holds it | tested | `tests/e2e/test_acts.py`, `test_server.py` |
| An agent's acts on its page, and the session's close and cancel, asking first where the terminal asks | tested | `tests/e2e/test_acts.py`. Cancel runs the same path, untested in a browser |
| A view link's controls disabled, saying why, and hostile text rendered safely under the page's policy | tested | `tests/e2e/test_guards.py` |
| The Board, Tasks and Entries | tested | `tests/e2e/test_board.py`, `test_board.py`, `test_server.py` |
| Provenance and who reached whom in a pane of the page, in the terminal's words | tested | `tests/e2e/test_provenance.py` and `test_acts.py`, `test_server.py` |
| Commands, a palette of each write op you hold, and one read route, `/v1/x_read`, for every pane | tested | `test_server.py`, `tests/e2e/test_acts.py`, `test_guards.py`, `test_provenance.py` and `test_follow.py`. A form starts empty wherever it was opened from |
| Tool activity and live text on an agent's page | tested | `tests/unit/cli/test_calls.py`, `test_server.py`, `tests/e2e/test_activity.py`. No real harness's live text has been drawn there, and the pane does not follow the journal |
| Access: one column at a phone's width, each pane pinned by an aria snapshot, and a disabled control taking focus with its reason as its accessible description | tested | `tests/e2e/test_access.py`, and the rest of `tests/e2e/`. The page claims no WCAG level: no rule-based check such as axe-core and no screen reader has been run |
| The browser suite in Chromium, Firefox and WebKit | tested | `tests/e2e/conftest.py`. WebKit runs in CI alone |
| Links of either kind made from your own page | tested | `tests/e2e/test_acts.py` and `test_web.py` |
| The page on real models, the terminal UI attached at once | tested | `tests/live/test_web.py`, on Claude Code and Codex |
| A session on a plan login served on loopback alone, any other address exiting 78 | tested | `tests/integration/test_web.py`, `test_server.py`. A harness that cannot say which login it has is not counted |
| The sessions page: every session under the root, Open, Start, Resume and Stop, and the team editor | tested | `test_sessions.py`, `tests/e2e/test_sessions.py` and `test_team_editor.py`. Other users of the machine reach loopback: the bearer keeps them from reading or acting, and nothing keeps them from holding its connections |
| A replay, `web SESSION --replay` or Replay on the sessions page, under a banner that always says it is one | tested | `test_replay.py`, `tests/e2e/test_replay.py`, `tests/integration/test_replay.py`. It is served past loopback even for a plan-login session, as its links act on nothing, though they read the whole record |

### Teams and topologies (`platoon_harness.team`, `platoon_harness.topology`)

Tests in `tests/unit/topology/`, the compiled grants checked against a real kernel.

| Capability | State | Evidence |
|---|---|---|
| `Role`, `Team` and `Topology` as frozen models, TOML and Python building one object, and the eight presets | tested | `test_presets.py` |
| `labels` in the team file: each label with the values it may take | tested | `tests/unit/primitives/test_labels.py` |
| Presets from an extension, with the power of a built-in | tested | `test_check.py`, `tests/unit/config/test_extensions.py` |
| Union, commutative and associative with a stable hash, and `compile` to edges, channels, groups, `may_spawn`, lifecycle, `wait` and scopes, `next`, `prev` and groups expanded over roles | tested | `test_union.py` and `test_compile.py`, properties; `tests/unit/primitives/test_compiled_grants.py` |
| `team_check`: refusals, warnings, did-you-mean and every problem at once, a preset nobody knows, and a channel setting nothing enforces | tested | `test_check.py` |
| `trainable_problems(team)` and `check(team, trainable=True)`: what keeps a team from training, from the team file alone, a workspace other than `shared` or `isolated` among it | tested | `test_check.py`, `tests/unit/runtime/test_training.py` |
| `team.show()` in English, and the resolved form as valid input | tested | `test_show.py`, `test_docs.py` |
| `Capabilities.measures` and `sandboxes`, asked of each role's driver | tested | `tests/unit/runtime/test_opening.py` |
| `docs/how-to/topologies.md`: every snippet runs, both forms agree, and its program runs on a scripted reviewer | tested | `test_docs.py`, `tests/unit/runtime/test_programs.py` |
| `docs/how-to/provenance.md`: its code runs on a session of a scripted harness | tested | `tests/unit/runtime/test_provenance_guide.py` |
| `examples/mixed-team`: a pi lead and an OpenHands worker on a model you name, fixing an issue of the sample project through a queue, a board and messages | tested | `tests/integration/test_examples.py`, on pi 1.5.0 and OpenHands 1.59.0 against FakeModel, and from the page in `tests/e2e/test_examples.py`; live, `tests/live/test_examples.py`, on DeepSeek V4.1 Flash in 30 model calls in each of two runs. Its README's commands to watch it, and its swap of a harness, are not tested |
| `examples/sdk-script`: a headless script on the SDK alone, two OpenHands agents in worktrees each fixing an issue | tested | `tests/integration/test_examples.py`, against FakeModel; live, `tests/live/test_examples.py`, on DeepSeek V4.1 Flash in 29 model calls |
| `examples/worktree-merge-queue`: OpenHands workers in worktrees of their own and a pi merger, one fix merged and the other handed its conflict | tested | `tests/integration/test_examples.py`, against FakeModel; live, `tests/live/test_examples.py`, on DeepSeek V4.1 Flash in 74 model calls |
| `examples/review-verification`: an OpenHands author, a pi reviewer reading the commit, and a pi verifier whose evidence is your test of it | tested | `tests/integration/test_examples.py`, against FakeModel; live, `tests/live/test_examples.py`, on DeepSeek V4.1 Flash in 42 model calls. The reviewer asks `repo.commit` again while a commit is not recorded yet, as no wait wakes it once one is |
| `examples/git-swarm`: a population of pi workers in worktrees, run from a script, ending with each worker's outcome | tested | `tests/integration/test_examples.py`, against FakeModel; live, `tests/live/test_examples.py`, on DeepSeek V4.1 Flash in 64 model calls |
| `examples/sample-project`: `tally`, a small package with its own tests, two defects and two feature requests, which each example copies | tested | `tests/integration/test_examples.py` |
| A role's `on_parent_exit` set by a preset | deferred | A preset returns a topology, and this is a role's policy: the guide tells a mesh to set it |

### Configuration and extensions (`platoon_harness.config`, `platoon_harness.extensions`)

Tests in `tests/unit/config/`, discovery against fake `dist-info` folders, and against installed wheels under the sample
package's row.

| Capability | State | Evidence |
|---|---|---|
| Precedence across six layers: mappings merge, lists replace, every problem at once | tested | `test_config.py` |
| `docs/reference/team-file.md`, made from the schema | tested | `tests/unit/cli/test_team_file.py` |
| Trust: what a project file needs it for, a `command` harness, a `module:attr` reference, an auth profile or a `test` command | tested | `test_config.py` |
| Secrets: `Secret` refusing to be serialized, input kept out of errors, a resolved config holding names only, and encoded forms and URLs redacted | tested | `test_config.py`, `tests/unit/drivers/test_env.py` and `test_process.py`. A credential no profile names cannot be recognised, and nothing sanitizes a session's folder |
| The manifest: the resolved team, how it was started, components, versions and the topology's hash | tested | `test_config.py`, `tests/unit/runtime/test_opening.py` |
| Extensions found from metadata with no import, in two entry-point groups, by `name`, `name@version` or `module:attr`, duplicates and SDK requirements caught first, and installing activating nothing | tested | `test_extensions.py`. A pre-release suffix is ignored when versions compare |
| An extension's op with no core edit: through the SDK, as an agent's tool and `ph` command, and from the terminal's palette and the page | tested | `tests/unit/runtime/test_session.py`, `tests/unit/tools/test_mcp.py`, `tests/unit/tui/test_workspace.py`, `tests/unit/web/test_server.py`, `tests/e2e/test_acts.py` |
| `bwrap`, the SDK's own extension, under the `platoon_harness.extensions` group: an isolation on bubblewrap that says why where it cannot confine, loaded only for a team that names it | experimental | `tests/unit/runtime/test_bwrap.py`, on bubblewrap 0.4.1 and on GitHub's Ubuntu 24.04 runners' 0.9.0 in CI; `tests/unit/drivers/test_check_extension.py` and `test_boundaries.py` |
| `examples/extension-package`, the ballot extension of architecture section 17: an op, a view and a preset, built as a wheel and installed beside a rival, activating nothing until a team names it | tested | `tests/integration/test_installed_extensions.py`, `tests/unit/tui/test_sample_extension.py`, `tests/e2e/test_extension.py` |
| The bubblewrap tests failing in CI, rather than skipping, where bubblewrap cannot confine | tested | `tests/unit/runtime/support.py` and `test_bwrap.py` |
| Gitea and GitLab through extensions | deferred | Nothing is built, and no user of either is in sight |

### Packaging and docs

Rows here span the one distribution, `platoon-harness`: how it is versioned, built, checked and released, and the docs a
release ships. 0.1.0 is the first release, which its tag, `v0.1.0`, publishes.

| Capability | State | Evidence |
|---|---|---|
| One distribution, `platoon-harness`, built from the SDK's and the command line's source trees, its version set in one place | tested | `tests/unit/test_packaging.py` |
| The library needing pydantic alone, and the command line its `cli` extra, whose command says what to install where the extra is missing, and exits 78 | tested | `tests/unit/test_packaging.py`, `tests/unit/cli/test_launcher.py`, `tests/integration/test_installed.py` |
| The installed command line run from the built wheel in a fresh environment | tested | `tests/integration/test_installed.py` |
| The `openhands` extra pinning OpenHands' SDK and tools at the release [Install](getting-started/install.md) names | tested | `tests/integration/test_installed.py` |
| Every runtime dependency's license held to an allowlist of permissive licenses and MPL-2.0, and a new one refused until the maintainers admit it | tested | `tests/unit/test_packaging.py`, on Python 3.12, 3.13 and 3.14 |
| A release workflow that builds and checks the sdist and the wheel on each pull request and push to `main`, and publishes from a `v` tag to PyPI by trusted publishing once a maintainer approves | implemented | `.github/workflows/release.yml`, whose commands CONTRIBUTING shows under Releases, as `tests/unit/test_contributing.py` holds. That a tag publishes is not yet shown |
| CI's actions pinned to commits, with read-only permissions but for the `publish` job's OIDC token | tested | `tests/unit/test_contributing.py` |
| CONTRIBUTING's account of how a release is cut and published | implemented | CONTRIBUTING's Releases, whose commands `tests/unit/test_contributing.py` holds to the workflow's. 0.1.0 is the first release cut by it |
| The fast tests on macOS in CI, and the classifiers naming macOS once they pass | planned | Nothing has run on macOS |
| The public API: each name `tests/public_api.txt` lists, and each attribute and method without a leading underscore that a class it lists defines, under the policy below 1.0 that [CHANGELOG](../CHANGELOG.md) states | tested | `test_public_api.py` in `tests/unit/kernel/`, `tools/`, `drivers/`, `runtime/` and `topology/`, which hold the list to the code, each frozen member's parameters among it |
| `docs/reference/python.md`: every public name with its signature and docstring, made from `tests/public_api.txt`, marking what this page calls experimental | tested | `tests/unit/docs/test_python_reference.py` |
| `docs/extending/`: an index of every way to extend platoon-harness, and an extension tutorial on the sample package whose steps a test runs | tested | `tests/unit/docs/test_extending.py` and `test_links.py`, `tests/integration/test_installed_extensions.py` |
| `docs/security.md`: what is protected, tier by tier, and what is not, credentials, retention and redaction, with other users on the same machine out of scope | implemented | Each claim rests on the row that tests it. `tests/unit/docs/test_links.py` holds a row there for each tier of architecture section 15 |
| The docs' images: the terminal UI and the page drawn from the mixed team's session as a live run recorded it, each caption saying whether a recorded or a scripted session drew it | tested | `tests/integration/test_recorded.py`, `tests/e2e/test_examples.py` and `test_page_images.py`, `tests/unit/tui/test_snapshots.py`, `tests/unit/docs/test_images.py`. No test holds an image of the page to what a browser draws, as that differs with a machine's fonts; CONTRIBUTING says how to make them again |
| Diagrams of the process model and of one provenance trace | planned | None is drawn yet |
| `SECURITY.md`, through GitHub's private vulnerability reporting, and issue templates for a bug report and a feature request | implemented | `SECURITY.md` and `.github/ISSUE_TEMPLATE/`. No test holds them but the privacy scan and the link check |
| The privacy scan: nothing the repository holds names a local path, a site, an account, a key or an email address, but the author's contact the distribution publishes and addresses under `.invalid` | tested | `tests/unit/test_no_internal_references.py`. It catches the shapes it knows: an AWS secret access key, which has no shape of its own, is not caught |
| The process scan: no public page but an RFC names a ruling, a run by its number, a milestone of the project or a host | tested | `tests/unit/docs/test_process_language.py`. It catches the phrases it knows |
