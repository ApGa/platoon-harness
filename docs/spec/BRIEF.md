# platoon-harness product brief (verbatim)

> Provenance: this is the project owner's brief, reproduced verbatim. Implementation status against this brief is
> tracked in `docs/STATUS.md`, not here. It is kept as the source of STATUS's acceptance cases and cited by RFCs as
> evidence; the RFCs it names are Platoon's.

I want to build `platoon-harness`: a production-quality, harness-agnostic multi-agent SDK and CLI, co-designed with Platoon's training interfaces.

Work in the provided repository/workspace. Inspect the referenced projects and relevant code before settling the architecture. Then implement, test, document, and demonstrate working software. Do not stop at an architecture document, scaffold, or collection of interfaces. Work in independently testable milestones and clearly distinguish implemented, tested, experimental, and deferred functionality.

## 1. Product and package boundaries

The project has two equally important uses:

**Everyday use:** an excellent multi-agent coding/research experience that lets people coordinate existing agent harnesses, use their own supported credentials and subscriptions, and interact through a polished TUI, a Slack-like SwarmChat frontend, or headless commands. While multi-agent needs to be a first-class citizen, the cli should also be a first-class single-agent experience with all the features that are typically present in a tui (you can look at pi, openhands, hermes, claude code, prime agent, codex, etc. for understanding typical user expectation for tui agents.)

**Training:** the same execution system exposes sufficiently precise identities, model-call associations, provenance, rewards, and lifecycle events for Platoon to train multi-agent policies and research credit assignment. Do not build a separate toy training harness with different semantics.

Use these names:

| Item | Name |
|---|---|
| Repository/project | `platoon-harness` |
| SDK distribution | `platoon-harness-sdk` |
| SDK Python import | `platoon_harness` |
| CLI distribution | `platoon-harness-cli` |
| CLI Python import | `platoon_harness_cli` |
| Executable | `platoon-harness` |

The CLI is a thin SDK consumer. The SDK must not import the CLI, require a TUI, or require Platoon, Torch, Tinker, or any particular agent implementation. Put training integration and heavyweight/provider-specific dependencies behind optional extensions. Do not install into or shadow Platoon's `platoon` namespace.

We are **not building another mandatory single-agent loop**. Existing harnesses retain responsibility for reasoning, coding tools, context management, and provider-specific behavior. We add coordination, supervision, shared workspaces, provenance, observability, and interoperable control. A minimal scripted agent is useful for tests and demos, not a substitute for real integrations.

## 2. Inspect upstreams and establish compatibility

Start with these primary references, recording the commit/version inspected:

```text
https://github.com/ApGa/platoon
https://github.com/ApGa/platoon/blob/main/docs/architecture.md
https://github.com/ApGa/platoon/blob/main/docs/rfcs/0001-native-multi-agent.md
https://github.com/ApGa/platoon/blob/main/docs/rfcs/0021-trainers-credit-and-policies.md
https://github.com/ApGa/platoon/blob/main/docs/rfcs/0013-extension-model.md
https://github.com/Pranjal2041/swarmchat
https://github.com/batrachianai/toad
https://github.com/OpenHands/software-agent-sdk
https://github.com/OpenHands/OpenHands-CLI
https://agentclientprotocol.com/
https://modelcontextprotocol.io/
https://github.com/yuzhenmao/DeLM
https://veds12.github.io/git-swarm/
https://github.com/microsoft/Agensh
https://github.com/PrimeIntellect-ai/prime-agent
https://github.com/earendil-works/pi
```

Also inspect the current official integration documentation for Codex, Claude Code, OpenCode, and the selected adapter implementations. Check the licenses of dependencies and any reused code; taking interaction-design inspiration does not require copying upstream implementation code. Preserve applicable notices and document redistribution constraints. Follow upstream renames rather than assuming old package paths or command flags still work. Review relevant Platoon configuration, public-surface/conformance, environment-forking, and multi-policy RFCs and their actual implementations.

Important starting observations to verify against the checked-out revisions:

- Platoon RFC 0001's per-agent credit section is partly superseded by RFC 0021's asynchronous `CreditEstimator`, including per-token advantages. Do not implement the superseded design as the only integration target.
- SwarmChat's documented browser viewer is read-only. Human interaction through that frontend is required work, not an assumed existing capability.
- Toad uses ACP and is an interaction-design reference, not a dependency we must fork or copy wholesale.
- Platoon's extension design uses explicitly selected components, lazy loading, package/version provenance, and conformance checks. Follow those principles rather than adding import-time plugin magic.

Write a short compatibility report and architecture decision records. Separate what is already implemented upstream from draft RFC proposals. Maintain a capability matrix for each adapter: launch, streaming, tool injection, messaging, interruption, approvals, resume, native subagents, model-endpoint configuration, exact call attribution, and training eligibility. Give capabilities evidence, versions, and known limitations.

If an upstream contract is missing, isolate a versioned experimental adapter and provide a focused upstream RFC amendment or patch. Do not silently patch installed dependencies, mutate unrelated repositories, publish packages, or push changes.

## 3. Architecture: one runtime, multiple clients

Build a reusable asynchronous Python SDK with typed public contracts. Prefer Python 3.12+, a uv workspace, and a small core dependency set, following Platoon's engineering conventions where appropriate.

Separate the following responsibilities:

| Layer | Responsibility |
|---|---|
| Protocol/model | Versioned commands, results, identities, events, artifacts, graph edges, schemas |
| Runtime/control service | Lifecycle, admission, scheduling, delivery, permissions, budgets, durable state |
| Agent drivers | Adapt existing SDKs, ACP agents, structured CLI/RPC interfaces, or user implementations |
| Workspace/services | Boards, task queues, files, Git references, sandbox/environment bindings |
| Clients | Python API, thin CLI/TUI, SwarmChat integration, headless/remote clients |
| Training integration | Export/bridge to Platoon; optional reward and credit-estimator extensions |

Support an in-process SDK entry point and a supervised service that clients can attach to. They must use the same runtime implementation and semantics. A UI disconnect must not implicitly kill a service-owned run; explicit stop/cancel commands control execution. An embedded SDK runtime should instead have a documented context-manager shutdown contract. Distinguish these ownership modes rather than leaking subprocesses from short-lived scripts. Do not implement a second scheduler inside the TUI or frontend bridge.

Use a durable canonical event journal with rebuildable views. Local-first operation should require no Redis, Kafka, Kubernetes, or external database. A single-writer SQLite implementation on local storage is an acceptable starting point. Multi-machine workers should connect to the service, not share a SQLite database over a network filesystem. Keep storage/worker interfaces extensible without prematurely building a distributed database.

Define ownership explicitly in standalone and Platoon-managed modes. In Platoon-managed mode, delegate identities, model routing, budgets, spawning, and environment forks to their appropriate Platoon authority rather than maintaining competing authorities. An ownership matrix must state which component authorizes, executes, records, and reconciles each operation.

## 4. Bring-your-own harness, model, and credentials

A run must be able to mix OpenHands, Codex, Claude Code, OpenCode, pi, Prime Agent, and user-defined drivers. Support both persistent conversational agents and one-shot workers. Different roles may select different harnesses, models, and auth profiles.

Prefer supported interfaces: native SDKs, native app-server/RPC APIs, or ACP. Expose coordination tools through MCP where supported, plus a structured command-line/Python client for agents that can call tools through a shell. Treat PTY integration as an explicit degraded fallback, not a reliable substitute for structured events.

Keep these boundaries clear:

**ACP/native RPC:** controlling sessions and receiving supported agent events.

**MCP/SDK/tool CLI:** giving agents access to our coordination primitives.

**Platoon gateway:** recording exact model calls for trainable policies.

None of these automatically implies the others. Negotiate and pin supported protocol versions; do not accidentally depend on a draft protocol.

Use native supported authentication flows. Preserve an agent's existing provider setup where possible. Do not require migrating every user to a shared API key, or assume a subscription can be reused as an arbitrary API credential. Do not scrape credentials or bypass provider restrictions. Scope credentials to the appropriate process and never put them in logs, artifacts, exports, or resolved configuration.

Distinguish:

| Capability level | Meaning |
|---|---|
| Operational | We can run/control the harness and expose supported coordination tools |
| Observable | We can collect specified events, with explicit provenance coverage and gaps |
| Trainable | The configured policy exposes the exact data and attribution required by Platoon |

These are separate capabilities, not a single Boolean. A useful native-auth agent may remain opaque and untrainable. Never fabricate token IDs, log probabilities, context contents, child identities, or tool-to-model-call associations from rendered text.

Implement at least two real integrations using different integration paths, including one suitable for an exact Platoon training path. Also provide a documented custom-driver protocol and conformance suite. Keep unsupported operations explicit and actionable in every UI.

## 5. Distributed primitives and execution semantics

Expose these concepts through typed SDK methods and role-configurable tools. Final naming may improve, but semantics must remain explicit.

| Area | Operations |
|---|---|
| Lifecycle | `spawn`, `attach`, `status`, `list_agents`, `wait/join`, `wait_any`, `finish`, `cancel`, `retire` |
| Communication | `send`, `receive/read_messages`, `reply`, `broadcast`, channels, threads |
| Shared information | `post`, `get`, `query`, `revise`, version-checked updates |
| Work distribution | `enqueue`, `claim/take`, `renew`, `release`, `complete` |
| Reactive coordination | `watch/subscribe`, cursor-based reads, acknowledgement |
| Synchronization | Explicitly scoped barriers, leased locks, semaphores, events where needed |

Provide map/gather/reduce, manager-worker, verifier-generator, and other patterns as compositions rather than mandatory scheduler modes. Do not try to implement every MPI primitive or invent a consensus algorithm.

**Dynamic lifecycle.** Fixed teams and evolving populations must both work. Policies may spawn and retire agents within granted roles, capabilities, depth limits, and budgets. Deleting an agent from the live team must not erase its historical trajectory. Specify parent-cancellation behavior, orphan handling, admission reservations, and run completion for decentralized teams that have no privileged root.

**Delivery.** Define acknowledgement and cursor semantics; handle retries, duplicates, reconnects, and backpressure. State the ordering guarantee, broadcast membership snapshot, and message-injection boundary. A message sent to a busy agent may be queued until its next supported turn boundary; never claim universal mid-generation interruption.

**Boards.** Objects have stable identities and immutable versions. Structured queries are core; semantic search is optional. Query outputs must carry the actual versions/content ranges exposed. Updates use optimistic concurrency or equivalent version checks; concurrent edits must not silently overwrite one another.

**Claims.** A task claim is atomic and lease-based, with renewal, expiry, release, and completion. Use fencing/version checks so an expired claimant cannot commit stale completion. Distinguish exclusive task ownership from exactly-once external execution.

**Watches and barriers.** Avoid the read-then-subscribe lost-wakeup race. Watches resume from durable cursors. Barriers specify membership and generation, timeout, and participant failure behavior. Waiting agents should suspend without wasting model calls.

**Budgets.** Enforce shared and per-role limits atomically, including concurrent agents and spawn admission. Separate policy-caused budget exhaustion from infrastructure unavailability. Report unavailable cost/token measurements honestly; approximate measurements must be labeled.

All transports must call the same implementation. Model-supplied arguments must not let an agent choose an arbitrary caller identity, elevate permissions, or select a disallowed policy.

## 6. Provenance is a first-class protocol feature

Build an event/artifact-level dependency graph, not merely a parent-agent tree.

Separate the **agent interaction graph**, which may contain cycles, from the **time/version-expanded dependency graph**, which should be acyclic. For example, A's first post can influence B's response, which influences A's next action. Collapsing these events into one node per agent creates a cycle and loses credit-assignment detail.

A minimal model should represent runs/episodes, agents, principals, actions/model calls, tool calls, messages, artifact versions, context snapshots, task/lease transitions, workspace revisions, and reward/credit annotations. Keep user-facing sessions and training episode boundaries explicit.

Event envelopes should support schema version, event ID, run/episode ID, authenticated actor, agent ID where applicable, sequence/cursor, correlation and causation references, native/backend IDs, timestamps, and payload. Model/action events additionally carry policy/version and call/tool/token-span references where actually available. Wall-clock ordering is not proof of causality.

Automatically record production, delivery, retrieval, actual context injection where observable, delegation, task claims, tool outputs, Git/workspace operations, and summarization/compaction. Capture nested/programmatic tool-call anchors when the backend provides them. Store large bodies out of line behind durable content references.

Distinguish these forms of evidence:

| Evidence | Interpretation |
|---|---|
| Observed exposure | The runtime observed particular content delivered or inserted into a context |
| Declared dependency | An agent claims `based_on=[...]` or `informed_by=[...]` |
| Judged attribution | A judge estimates usefulness or influence, with its version and evidence |
| Validated intervention | A specific controlled intervention and its measured result |

These are not interchangeable. Delivery is not understanding; read receipts are not marginal usefulness; a citation is not causal proof. Keep evidence type separate from Platoon's agent-identity attribution levels such as exact/declared/inferred/forked.

Preserve immutable evidence and attach versioned attribution annotations separately. A different credit estimator must be able to reuse the same trace without rerunning agents or overwriting prior annotations.

Do not claim complete causal coverage. Shared files, shell commands, external services, native compaction, and opaque harness behavior can create unobserved dependencies. Record coverage and gaps. Absence of a recorded path is not proof that no influence occurred. Observation of a shared-board retrieval alone does not capture every information flow.

Human actions are first-class events with human identity. Watching a UI must not move an agent's read cursor or imply the agent saw something. Human edits, messages, approvals, and takeovers must remain distinguishable from sampled policy actions.

## 7. Platoon integration and credit-assignment boundaries

Implement an optional integration against verified Platoon interfaces, with explicit compatibility tests and a small proposal for any missing protocol pieces.

Co-design with the current `AgentGraph`, agent API, gateway trace, `TrajectoryCollection`, reward events, role/policy binding, environment forks, and current credit-estimation seam. Where these are draft-only, state that and avoid shipping a fictitious integration.

The SDK owns execution and evidence. Platoon owns training-data construction, optimization, and training eligibility. Credit algorithms are replaceable consumers of traces, not hardwired into message delivery or UI rendering.

Required properties:

- Correlate exact agent identities with gateway calls and generated-token spans. External spawning should use scoped child credentials where supported. Reconcile native subagents without double-counting or inventing exact identities.
- Preserve policy/model version, role, purpose, harness version, episode membership, workspace/fork relationships, and attribution confidence. A role's training policy binding must follow Platoon's rules. Frozen agents, judges, humans, and unsupported traces must not silently become policy-gradient samples.
- Preserve raw local and team rewards separately. Missing/unscored/invalid/error/cancelled outcomes are not automatically zero rewards. Keep judge versions, reward definitions, and scoring evidence.
- Allow both agent-level and action/token-level credit through available mappings. Do not assume every agent has a single scalar reward forever.
- Export enough provenance to distinguish task execution, delegation, communication, retrieval, and compute allocation. Preserve environment-owned board/tool semantics rather than replacing every environment with ours.

Provide a compatibility example for the original RAO baseline:

```text
For rollout k in a group of G > 1 independent rollouts:

b_root[k] = mean(R_root[l] for l != k)
A_i[k] = R_i_local[k] - b_root[k]

For the root: R_root_local = R_task.
```

Reproduce existing behavior in a golden fixture rather than silently changing normalization, filtering, weighting, or fallback semantics. For a single large swarm, demonstrate a no-extra-rollout alternative, such as a frozen prior-batch baseline keyed by policy, role, and reward definition, with explicitly saved state and documented sparse-bucket fallback. Form keys from information available before the credited action, not from its observed outcome; update baseline state only after the current batch or group has been credited. Do not call an average over interacting siblings an independent leave-one-out baseline.

Provide extension seams and small tests for judge-based local rewards and graph-based credit propagation. Label heuristic attribution as heuristic: it is not automatically an unbiased marginal contribution, and local reward shaping can change the objective. Do not assume local reward, team reward, and downstream credit should be added with fixed coefficients.

Do not require a learned critic, per-node resampling, or repeated execution of the entire swarm. Keep future intervention/replay hooks possible without pretending production traces are deterministic counterfactual simulators. If implementing conservative credit redistribution, test conservation, reconverging paths, and retained local credit explicitly.

Human interventions must be identifiable and configurable for exclusion or separate dataset use. Reward/judge information used only for training must not leak into policy-visible contexts or evaluation by default.

## 8. CLI and TUI: useful enough for everyday work

The CLI must be a genuine production-facing application, not a research dashboard. Draw interaction ideas from Toad, Claude Code, Codex, OpenHands, OpenCode, and pi while preserving our multi-agent identity.

Provide a discoverable command surface along these lines:

```text
platoon-harness                    # interactive TUI
platoon-harness init
platoon-harness doctor
platoon-harness run ...             # headless or interactive selection
platoon-harness serve ...
platoon-harness attach SESSION
platoon-harness sessions ...
platoon-harness agents ...
platoon-harness message ...
platoon-harness board ...
platoon-harness tasks ...
platoon-harness events ...
platoon-harness export ...
platoon-harness web ...
platoon-harness extensions ...
```

Headless mode needs stable JSON/JSONL output, documented exit codes, stdin/file prompts, explicit noninteractive approval policy, cancellation/timeouts, and resumable event cursors. Keep logs on stderr. CI must never hang waiting for an invisible confirmation.

The TUI should make five questions immediately answerable: who is working, on what, what is blocked, what changed, and where does the user need to act?

Design an adaptive layout with a team/channel navigator, focused conversation or activity pane, optional details/provenance inspector, and a clear composer target. Do not merge dozens of token streams into one unreadable transcript. Support aggregate summaries, agent/channel filters, unread/mention indicators, and focused drill-down.

Include multiline editing, history, file/context attachment, readable streaming Markdown/code, diffs, search, keyboard navigation, a command palette, discoverable shortcuts, cancellation, approvals, and session resume where supported. Provide clear native/backend settings without exposing a wall of internal configuration. Preserve native project instructions and extension mechanisms rather than indiscriminately overwriting them. Explicitly define how project instructions, native skills, slash commands, tool configuration, hooks, and session compaction interact with our coordination tools. Support passthrough or namespaced access where feasible; do not claim every backend exposes identical features.

Allow users to address an agent, channel, thread, or team; inspect why an agent is waiting; review tool calls and patches; and follow a message/artifact into its provenance. Show provider/harness identity, budget usage, and observability gaps. Use progressive disclosure: ordinary users should not need to understand training graphs to get work done.

Support native interactive terminal workflows through safe, supported adapters where practical. Keep workspace and terminal ownership clear. Do not build an entire terminal emulator in the first milestone or pretend a simple stdout pane handles all interactive programs.

Test resizing, narrow layouts, Unicode, large histories, reconnects, slow consumers, and concurrent updates. Preserve scroll position while users read. Unsupported capabilities should be disabled with a reason, not hidden behind successful-looking no-ops.

## 9. SwarmChat: a real second client, not a log dump

Reuse SwarmChat's frontend and interaction model where practical. Inspect its actual server/client/viewer boundaries before choosing an upstream extension, compatibility backend, or narrow maintained patch. Do not replace it with an unrelated dashboard while claiming integration.

Make the runtime journal authoritative for our runs. Build an idempotent projection and authenticated command ingress, with stable mappings among run IDs, participants, channels, message IDs, artifacts, and SwarmChat IDs. Do not create two independent message/task/lifecycle authorities. If reusing SwarmChat's server, document ownership and reconciliation precisely.

Represent agents and humans distinctly. Use channels/threads for collaboration and provide accessible views of tools, task status, artifacts, diffs, and provenance without flooding normal conversation with low-level telemetry.

Human interaction through the browser is required: sending/replying, asking agents questions, issuing authorized lifecycle commands, handling approval requests, and providing context/artifacts. Route all mutations through the same SDK command service as the TUI. A read-only viewer credential must never implicitly become a control credential.

Support simultaneous TUI and browser attachment. Commands and approvals need idempotency, expected-version checks where relevant, and explicit conflict behavior. Reconnection must not duplicate messages or actions. Prevent bridge echo loops. Browser read receipts must not acknowledge agent deliveries.

Provide frontend end-to-end tests showing a human message entering an agent's supported input path, a reply appearing in both clients, and an approval resolved exactly once across two clients. Include authentication, origin checks, safe rendering, and deliberate remote exposure rather than an unauthenticated public control server.

## 10. Flexible topologies, workspaces, and examples

Make topology a combination of configuration, optional episode programs, permissions, and policy decisions. Do not hardcode a root orchestrator, a fixed number of agents, or a fixed workflow graph.

Ship runnable examples for:

| Example | What it demonstrates |
|---|---|
| RAO-style recursion | Dynamic delegation, child completion, return links, local/team rewards |
| DAO-style team | Peer messaging, spawning, shared artifacts, non-tree information flow |
| DeLM-style board | Persistent shared context, claimed tasks, asynchronous workers |
| GitSwarm-style work | Separate worktrees/branches, immutable commits, explicit semantic dependencies |
| Review/verification | Fixed roles and independent verification with scoped capabilities |
| Mixed human/agent team | Different harnesses, human steering, shared TUI/web session |

These are examples of patterns, not claims of reproducing a paper's full system or results.

Treat Git ancestry, declared `informed_by`, observed reads, and causal credit as different relations. Capture commits, tests, merges, conflicts, and workspace provenance. Never silently discard uncommitted work or auto-resolve conflicts destructively.

Provide a path to Gitea/GitLab-style collaboration through extensions, without making either service mandatory. Start with useful local Git support and explicit boundaries for remote integrations.

Support explicit shared, isolated, snapshot, or worktree workspace modes according to backend capabilities. A worktree is not a security sandbox. Reuse available environment/sandbox interfaces; do not reimplement Platoon's infrastructure or assume Docker privileges on every machine.

## 11. Extension and configuration model

Use an extension model inspired by Platoon: installed distributions expose explicitly selected components, discovered through metadata and loaded lazily. First-party and third-party extensions use the same contracts.

Useful extension seams include agent drivers, tools/primitives, topology/episode programs, workspace providers, event sinks/frontends, exporters, and training/credit integration. Add dedicated registry groups when justified, not dozens of speculative abstractions.

Provide typed configuration with validation, documented precedence, role-level capability allowlists, and a sanitized resolved config. Support a programmatic API without requiring configuration files. Record resolved component versions and schema/protocol versions in a reproducibility manifest.

Installing a package must not activate it in unrelated runs. Detect duplicate names, incompatible versions, and missing capabilities before launching expensive work. Avoid global monkey patches, eager imports, and arbitrary installation from untrusted project config. Treat plugins as trusted code unless separately isolated.

An extension should be able to add a coordination primitive that emits provenance-aware events and is usable through the SDK, tool protocol, CLI, and generic UI renderer without editing core. Preserve unknown namespaced events through export/replay even when a client cannot render them specially.

Suggested repository layout; adjust to match verified Platoon conventions:

```text
platoon-harness/
  pyproject.toml
  uv.lock
  AGENTS.md
  packages/
    sdk/src/platoon_harness/
    cli/src/platoon_harness_cli/
  extensions/
    ... optional first-party adapters and integrations ...
  examples/
  recipes/
  docs/
    architecture.md
    compatibility.md
    rfcs/
  tests/
    unit/
    integration/
    conformance/
    e2e/
  benchmarks/
```

## 12. Reliability, security, and scale

Design crash behavior before declaring production readiness. Persist accepted command/event transitions before acknowledging them. Use idempotency keys, transactional state changes/outbox patterns where appropriate, and explicit recovery states for external side effects whose completion is uncertain.

Do not promise exactly-once arbitrary shell/API effects or deterministic live reruns. Distinguish event replay, resumable execution, workspace snapshotting, and counterfactual re-execution. Replaying history to a UI must never re-execute tools.

Handle termination and cancellation across process trees, pending tool calls, watchers, leases, and native sessions. Release reservations and clean up only resources owned by the run. Support bounded queues and payloads, pagination, and backpressure. No observer may hold execution hostage or force unbounded memory growth.

Scope identities and permissions to runs, agents, roles, and human sessions. An agent may not spoof another author, read another run, claim admin identity, or bypass budgets through recursive spawning. Verify shared-state mutations server-side. Prompt instructions are not an authorization boundary.

Treat board contents, repository files, tool outputs, and rendered Markdown as untrusted data. Protect terminal rendering and browser rendering. Store secrets separately with restrictive permissions, sanitize exports, and document data-retention/redaction behavior. Do not log protected credential values or invent unavailable private reasoning traces.

Record metrics for throughput, latency, queueing, failures, active/blocked agents, resource use, provenance coverage, and training eligibility. Bound instrumentation overhead and support reduced display telemetry without silently discarding credit-critical evidence. Full traces may contain sensitive code and prompts; exporting them must be deliberate.

## 13. Testing and acceptance criteria

Create deterministic fake drivers, a controllable clock/scheduler, synthetic graph fixtures, recorded protocol fixtures, and real-adapter smoke tests. Core CI must run without provider credentials. Paid/live tests require explicit ot-in and budgets; a skipped live test is not a passing integration.

Required acceptance cases:

| Case | Passing behavior |
|---|---|
| SDK independence | A headless SDK example runs without CLI, TUI, Platoon, or ML packages |
| Mixed backends | Two real adapter paths cooperate; capabilities and auth limitations are visible |
| End-to-end collaboration | Spawn, post, query, claim, message, completion, and final artifact work together |
| Human parity | TUI and SwarmChat can control the same run through the shared command path |
| Claim race | Concurrent claimants get one valid lease; stale owners cannot complete after reassignment |
| Watch race | Messages arriving across read/subscribe/reconnect boundaries are not lost |
| Retry/crash | Retried spawn/send commands do not duplicate logical operations; uncertain effects are surfaced |
| Provenance | Exact versions/exposures survive compaction and event replay where observable; gaps are labeled |
| Identity | Native child reconciliation, run isolation, secret redaction, and spoof rejection are tested |
| Credit integration | RAO golden advantages match; unsupported/frozen/human traces stay out of RL samples |
| UI correctness | Resize, focus, history, streaming, approvals, cancellation, and reconnect tests pass |
| Extensibility | A separate sample extension adds a primitive/driver without modifying core |
| Git workflow | Independent work, test evidence, merge/conflict handling, and lineage remain inspectable |
| Scale | At least 100 simulated agents and 100,000 events are exercised with bounded active memory and paginated views |

For scale testing, publish measured hardware/configuration, throughput, memory, and interaction latency. Set explicit regression budgets from measurements; do not label the system production-scale based on a tiny demo.

Also test malformed adapter events, duplicate IDs, schema migrations, authorization failures, cross-client approval races, resource cleanup, and serialization round trips. Specify and exercise supported platforms (at least Linux and macOS for the initial release); label any Windows/WSL limitations. Include dependency-license and secret-leakage checks in the release checklist. Run type checking, linting, unit tests, integration tests, frontend/TUI tests, and packaging/install smoke tests.

## 14. Implementation sequence and deliverables

**Milestone 0: inspect and decide.** Produce a concise upstream compatibility map, architecture/ownership decisions, schemas, and a scoped implementation plan. Resolve nonblocking ambiguities with documented decisions. Keep this phase short and proceed to code.

**Milestone 1: working vertical slice.** A user configures an existing harness, launches a small team, exchanges messages/artifacts, observes it in a basic TUI and SwarmChat, and sends a human message through either client. The same flow works headlessly. Use durable events and genuine adapters, not only mocks.

**Milestone 2: dependable coordination.** Add dynamic lifecycle, leased work claiming, watches, budgets, explicit workspace modes, reconnect/recovery, and complete provenance for the supported flows. Expand to two real adapter paths and the mixed-harness example.

**Milestone 3: training integration.** Implement the supported Platoon bridge, exact-identity fixtures, reward/export contracts, RAO parity test, and a no-extra-rollout baseline example. Deliver minimal upstream RFC amendments for actual gaps. Do not claim draft-only functionality already works.

**Milestone 4: production-facing UX and extensibility.** Complete TUI/web interactions, reviews and approvals, Git examples, extension conformance, packaging, documentation, security hardening, and measured scale tests.

At each milestone, keep the repository runnable and update tests, docs, and a concrete completion checklist. Do not expand breadth at the expense of a broken core. Do not count an interface, mock, screenshot, or TODO as implemented functionality.

Deliver source, tests, a no-key clearly labeled demo, real-provider quickstarts, SDK examples, CLI help, configuration reference, extension tutorial, architecture/provenance diagrams, training integration notes, compatibility matrix, troubleshooting guide, and release/CI configuration. Include screenshots or terminal recordings of the actual working UX where tooling permits.

Your final report must list working commands, implemented capabilities, tests actually run and their results, upstream changes proposed, limitations, and the next bounded milestones. Preserve the project's central promise throughout: **bring existing agents together with excellent interaction, explicit distributed primitives, and honest provenance suitable for training.**

## Addendum from the project owner (2026-11-02)

Regarding the distributive communication primitives: Basically I want the sdk to make it easy to configure various communication primitives/topologies across the multi-agent systems where the primitives are inspired by distributed computing.

## Second addendum from the project owner (2026-11-02)

Do not look at any existing or upstream platoon-harness implementation for reference. The owner did not like that implementation and wants this project implemented from scratch with very good taste.
