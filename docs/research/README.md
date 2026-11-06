# Research index and verification

Milestone 0 research for `platoon-harness`, reviewed adversarially on 2026-11-02. The reports hold the detail. This page holds the index, what was re-verified, what was corrected, and what is still open. "Probe" below means a run by the critic on 2026-11-02 with real binaries, loopback models and dummy credentials, with no paid calls. Probe scripts are not in this repository.

**Bottom line.** All 12 critical claims survived, 2 with refinements. Two real agents, OpenHands and pi, passed the full trainable path on a minted child key. The six new findings below should change the design.

> **Later spikes override this page.** [spikes/tools-and-parking.md](spikes/tools-and-parking.md) found that under live Code Mode the Codex
> `callId` is `exec-<uuid>`, not the model's `call_*` (claim 11, finding 5), and that the shell client is blocked by the default Codex sandbox,
> so MCP with `omit_tools_from=["deferred"]` is its coordination path (finding 3). [../reference/compatibility.md](../reference/compatibility.md) is current.

## Reports

| Report | Covers | Use it for |
|---|---|---|
| [platoon-training.md](platoon-training.md) | Credit seam, RAO baseline, identity, gateway records, seams, RFC gaps G1-G12 | Bridge design, RAO golden values |
| [platoon-platform.md](platoon-platform.md) | Extensions, config, gateway, harness probes, sandboxes, conventions, namespace | Repo conventions, extension and config model |
| [swarmchat.md](swarmchat.md) | Server and viewer boundaries, data model, integration options, wire contract | Compatibility backend plus overlay |
| [acp-mcp.md](acp-mcp.md) | ACP v1 surface, SDKs, MCP eras, client support, identity binding, dependency policy | Protocol pins, tool plane |
| [tui-expectations.md](tui-expectations.md) | Feature catalog, keymap, Textual measurements, safety, layout proposal | TUI design, `SafeText` boundary |
| [adapter-openhands.md](adapter-openhands.md) | SDK and ACP paths, events, delegation, capability row | First trainable driver |
| [adapter-codex.md](adapter-codex.md) | app-server, approvals, native agents, usage, capability row | Codex driver |
| [adapter-claude-code.md](adapter-claude-code.md) | stream-json control protocol, subagents, terms, capability row | Claude driver, auth rules |
| [adapter-others.md](adapter-others.md) | OpenCode, pi, Prime Agent, capability rows | pi and OpenCode drivers |
| [swarm-patterns.md](swarm-patterns.md) | DeLM, Agensh, GitSwarm, Prime, RAO/DAO, example scenarios, tool surface | Examples, tool design |
| [pi-durable.md](pi-durable.md) | Pi Durable against our design, decisions, defects found in ours, spike | What to adopt and when, pi driver notes |
| [distributed-primitives.md](distributed-primitives.md) | Primitive families, topology grammar, presets, core and library split | Owner addendum, coordination core |
| [persistent-agents.md](persistent-agents.md) | Spawned agents that take follow-ups: who chooses, the follow-up, the answer, the end, and Platoon's limits | RFC 0023, agents that stay |
| [landscape.md](landscape.md) | Projects like ours on four axes, the closest ten, licenses, ideas to borrow | Positioning, what to borrow and when |

Fixtures are in [fixtures/](fixtures/). `prime-agent-sample.md` states that it holds no capture.

## Inspected upstreams

Date is the commit date of the inspected revision, or the retrieval date for a package.

| Project | URL | Commit or version | Date | License | Redistribution constraints |
|---|---|---|---|---|---|
| Platoon | https://github.com/ApGa/platoon | `efe3b277c82c` (0.5.0) | 2026-10-28 | MIT AND Apache-2.0 (tool parsers) | Optional extension only. Keep its NOTICE if parser code is ever copied |
| SwarmChat | https://github.com/Pranjal2041/swarmchat | `fb5aa6a05b40`; PyPI 0.1.0 | 2026-10-29 | MIT | Keep the notice when serving its page assets. Exact pin |
| Toad | https://github.com/batrachianai/toad | `dd4f90e8b370` (0.6.20) | 2026-05-26 | AGPL-3.0 | Inspiration only: no code, no dependency. Its `textual-diff-view` is AGPL per PyPI metadata |
| OpenHands SDK | https://github.com/OpenHands/software-agent-sdk | `988494576218`; wheels 1.59.0 | 2026-11-01 | MIT | Optional extra. Transitively installs proprietary `lmnr-claude-code-proxy` 0.2.0, so review before shipping in any image |
| OpenHands CLI | https://github.com/OpenHands/OpenHands-CLI | `283c6ac3610f`; `openhands` 1.16.0 | 2026-10-22 | MIT | User-installed. Pins SDK 1.28.1 |
| ACP spec | https://github.com/agentclientprotocol/agent-client-protocol | `212f0cace08a`; schema 1.29.0 | 2026-11-01 | Apache-2.0 | None for implementers |
| ACP Python SDK | https://github.com/agentclientprotocol/python-sdk | `9853d8b514d6`; 0.12.1, 1.0.0rc3 | 2026-10-29 | Apache-2.0 | Wheels have no License field, so license scanners may flag them |
| claude-agent-acp, codex-acp | https://www.npmjs.com/package/@agentclientprotocol/claude-agent-acp, https://www.npmjs.com/package/@agentclientprotocol/codex-acp | 0.99.1, 2.5.0 | 2026-11-02 | Apache-2.0 (ACP registry says proprietary for the first) | Never bundle: one depends on a proprietary SDK, the other brings its own Codex |
| MCP spec | https://github.com/modelcontextprotocol/modelcontextprotocol | `d0e246ea3c69`; revision 2026-07-28 | 2026-10-31 | Apache-2.0, MIT in transition, docs CC-BY-4.0 | Attribute quoted docs |
| MCP Python SDK | https://github.com/modelcontextprotocol/python-sdk | `d7845c073a2b`; 2.3.0 | 2026-10-27 | MIT | Optional extra. Cannot share an environment with OpenHands SDK 1.59.0 |
| Codex | https://github.com/openai/codex | `05c08d765523`; CLI 0.164.0 | 2026-11-02 | Apache-2.0 with NOTICE | User-installed. Never read or copy `auth.json` |
| Claude Code | https://github.com/anthropics/claude-code | `f0b737f94f3b`; CLI 2.1.316 | 2026-11-02 | Proprietary | Never bundle, vendor or patch. The repo holds changelog and examples only |
| Claude Agent SDK | https://github.com/anthropics/claude-agent-sdk-python | `2146f9d89855` (0.2.176) | 2026-10-31 | MIT wrapper | Wheels bundle the proprietary CLI: no default dependency, no re-hosting |
| OpenCode | https://github.com/anomalyco/opencode | `ff90ed91607c` (2.2.5) | 2026-11-02 | MIT | User-installed |
| pi | https://github.com/earendil-works/pi | `c9f4c7b9fcd0` (1.4.0) | 2026-11-01 | MIT | User-installed |
| Prime Agent | https://github.com/PrimeIntellect-ai/prime-agent | `c6d4da9421e6` (0.10.2) | 2026-10-30 | MIT; tarball adds `PHOTON-LICENSE.md` | User-installed. Not on npm or PyPI |
| DeLM | https://github.com/yuzhenmao/DeLM | `66617616e708` | 2026-10-08 | MIT | Pattern only. Credit in docs |
| Agensh | https://github.com/microsoft/Agensh | `d6063b9086d5` | 2026-10-30 | MIT | Pattern only. Credit in docs |
| GitSwarm site | https://github.com/veds12/git-swarm | `9f66af0b919f` | 2026-10-09 | None in repo | Owner allows pattern reference (2026-11-02). Site only, no harness. Write our own code and credit it |
| GitSwarm paper | https://arxiv.org/abs/2610.04862 | v1 | 2026-10-04 | CC BY 4.0 per PDF metadata, unconfirmed | Cite it |
| Textual, Rich | https://github.com/Textualize/textual | 8.2.8, 15.0.0 | 2026-11-02 | MIT | Normal dependencies. `asciinema` is GPL-3.0+: dev tool only |

## Brief section 2 observations

| Observation | Verdict | Evidence and nuance |
|---|---|---|
| [Platoon RFC 0021](https://github.com/ApGa/platoon/blob/efe3b277c82c/docs/rfcs/0021-trainers-credit-and-policies.md)'s `CreditEstimator` partly supersedes [Platoon RFC 0001](https://github.com/ApGa/platoon/blob/efe3b277c82c/docs/rfcs/0001-native-multi-agent.md)'s credit section, with per-token advantages | **Verified** | `platoon@efe3b277c82c:docs/rfcs/0001-native-multi-agent.md:5`, `platoon@efe3b277c82c:platoon/train/credit/api.py:244`, `:82`, `platoon@efe3b277c82c:platoon/train/credit/reverse_kl.py:126`. It is EXPERIMENTAL. [Platoon RFC 0021](https://github.com/ApGa/platoon/blob/efe3b277c82c/docs/rfcs/0021-trainers-credit-and-policies.md)'s header still says "Implementation: None yet" (`platoon@efe3b277c82c:docs/rfcs/0021-trainers-credit-and-policies.md:10`), so trust the code |
| SwarmChat's browser viewer is read-only | **Verified** | `swarmchat@fb5aa6a05b40:swarmchat/server.py:38`, `swarmchat@fb5aa6a05b40:README.md:63`. Probe below. Read-only is a property of the `view_*` requests, not the link: the admin token also opens them |
| Toad uses ACP and is a design reference | **Verified** | Own ACP client with `PROTOCOL_VERSION = 1` and no ACP SDK dependency (`toad@dd4f90e8b370:src/toad/acp/agent.py:32`). AGPL-3.0 means copying is ruled out, not just unnecessary |
| Platoon extensions: explicit selection, lazy loading, provenance, conformance checks | **Partly verified** | First three hold (`platoon@efe3b277c82c:platoon/extensions.py:70`, `:270`, `:1121`). Conformance exists only for experimental sampler, admission, trainer and credit APIs (`platoon@efe3b277c82c:platoon/testing/credit.py:48`), plus static `platoon extensions check`. No harness or environment suite exists (`platoon@efe3b277c82c:docs/rfcs/0017-public-surface-and-conformance.md:10`) |

## Twelve critical claims, re-verified

| # | Claim | Verdict | How it was checked |
|---|---|---|---|
| 1 | ACP v1 is stable; v2 is draft; `session/fork`, `subagent_update`, `providers/*`, `mcp/message` are unstable | **Verified** | `acp-spec@212f0cace08a:agent-client-protocol-schema/src/version.rs:39`. Diffed `schema/v1/meta.json` against `meta.unstable.json`: 11 methods are unstable-only |
| 2 | `codex app-server` is labelled Experimental, yet `turn/steer`, `thread/fork`, `thread/inject_items` are on the stable handshake; `codex mcp-server` is gone | **Verified** | CLI help and live docs. Schema regenerated from the binary: 106/175 client requests, 10/11 server requests, 85 notifications. Steer ran with no `experimentalApi` |
| 3 | Codex approval order, stale-`expectedTurnId` refusal, and `never` failing MCP closed unless `default_tools_approval_mode="approve"` | **Verified, refined** | Real app-server over stdio, stub model. Order and exact error text match. Refinement: `accept` does not fix the outcome (finding 2) |
| 4 | Claude approvals via `--permission-prompt-tool stdio` and `can_use_tool` | **Verified, refined** | Allow reached MCP. Deny blocked the call and filled `permission_denials`. `stdio` stays undocumented in `claude --help`. Refinement: tools are deferred by default (finding 1) |
| 5 | Subscription rules; `ANTHROPIC_BASE_URL` alone keeps the login active | **Verified** | Quotes match https://code.claude.com/docs/en/legal-and-compliance and https://code.claude.com/docs/en/llm-gateway, retrieved 2026-11-02. Deliberately not probed |
| 6 | Exact identity through `POST /v1/platoon/agents` | **Verified** | Real gateway. Calls land on the key's agent. Spoofed `agent_id` in body, headers and `X-Platoon-Agent` was ignored. Grandchild minted at depth 2. Bad key gave 401 |
| 7 | OpenHands is an exact training path | **Verified, stronger than reported** | Platoon's own runner on SDK 1.59.0 with a minted child key under a zero-call root: 2 exact records with logprobs, 2 datums tagged to the child. Separately, `arun()` with an MCP tool: tool in the prompt and `llm_response_id == call_id` for every action |
| 8 | Codex's coordination tools do not reach a policy behind the gateway | **Verified, stronger than reported** | Real Codex on a child key with a connected MCP server: exact calls recorded, tool absent from the decoded prompt, `exec_command` present |
| 9 | SwarmChat view token cannot mutate, and writes are not idempotent | **Verified** | Real server. 8 mutating requests gave 401. Browsing changed no files. The same `send` twice made 2 messages, ignoring supplied `id`, `at`, `metadata`. Foreign Origin and Host were accepted |
| 10 | Default baseline is the group mean, leave-one-out is opt-in, and the golden values | **Verified** | `platoon@efe3b277c82c:platoon/train/config_defs.py:89`, `platoon@efe3b277c82c:recipes/rao/textcraft-synth/recursive.yaml:34`. Reproduced on the 0.5.0 wheel: LOO rows 0.5, -0.5, -1, 0.5, 1/3; mean rows 1/3, -2/3, -2/3, 1/3, 1/3 |
| 11 | MCP eras and anchors: Codex at `2025-06-18`, Claude Code discovers then uses `2025-11-25`, `_meta` carries client anchors | **Verified** | Real CLIs against a logging stub. `callId` and `claudecode/toolUseId` equalled the model ids. A spoofed `caller` argument reached the server verbatim from both, so the server must bind identity |
| 12 | `openhands-sdk` 1.59.0 conflicts with `mcp` 2.3.0 and ACP 1.0.0rc3; unpinned resolves silently to old versions | **Verified** | `uv pip compile`: both unsatisfiable when pinned; unpinned gives 1.49.1 and 1.44.1 |

Also confirmed: Textual 8.2.8 passes ST-terminated OSC 0, CSI 2J and RIS through `Static(markup=False)` and `Log` on a real PTY. Function harness plus finalizer gave a minted child its own reward. All 862 report citations resolve to a real file and line at the stated commit, and 16 random samples supported their claims.

## New findings

1. **Most harnesses hide MCP tools from the model by default.** Claude Code defers them behind tool search, adding to OpenCode and pi Code Mode, and Codex's live catalog may do the same. OpenHands does not. Conformance must assert the tool is in the first model request: "connected" proves nothing. Claude's fix is `"alwaysLoad": true`.
2. **Codex `accept` is not deterministic.** With `untrusted`, `read-only` and identical stub input, 29 of 48 accepted commands ran and 19 failed with EROFS, with or without `turn/steer`. Cause not established. Trust `item/completed`, not the decision.
3. **Trainable-path status by harness.** OpenHands and pi pass end to end. Codex passes identity but its MCP tools are invisible, so coordination must use the shell client. Claude Code fails: exit 1, zero records. OpenCode and Prime Agent are untested.
4. **A path-form URL is a credential.** `repr(ctx.endpoint)` hides `api_key` but prints the key inside `base_url`, and path-form mint replies carry one too. Redact URLs, not only key fields.
5. **Only Codex and Claude Code give an MCP-to-model anchor.** OpenHands and pi sent only `progressToken`. OpenHands has `llm_response_id` on actions instead. pi needs a separate check.
6. **OpenHands rejects undeclared tool arguments client-side,** so a spoofed `caller` never reaches the server there. Codex and Claude Code forward it. Server-side rejection stays mandatory.

## Contradictions between reports

| Topic | Conflict | Status |
|---|---|---|
| First training adapter | Platform picks OpenHands; adapter-others picks pi; Codex listed second | **Open, recommendation:** OpenHands first (Platoon maintains a profile, exact `llm_response_id` join), pi second as the native-RPC path. Codex is not a coordinated trainable path today |
| MCP identity transport | acp-mcp defaults to HTTP bearer; adapter-codex specifies a stdio shim | **Open, recommendation:** HTTP default, light stdio shim as fallback. A Python `MCPServer` shim costs about 42 MB each |
| Identity from `_meta` | adapter-codex derived the caller from it; acp-mcp forbids that | Fixed: token only, `_meta` is evidence |
| `x-platoon-call-id` | Platform said every response; training said non-streaming | Fixed: streams lack it (probe) |
| Claude through the gateway | adapter-claude-code left it open; platform said 400 | Fixed: exit 1, zero records (probe) |
| Native child level | adapter-openhands said `declared`; others `inferred` | Fixed: `inferred`, per [Platoon RFC 0001](https://github.com/ApGa/platoon/blob/efe3b277c82c/docs/rfcs/0001-native-multi-agent.md) |
| Prime Agent ACP | acp-mcp said none; adapter-others said v1 | Fixed: native v1 in source |
| Lease renewal | swarm-patterns has agent `task_renew`; primitives has the runtime renew | **Open:** keep the operation, runtime calls it by default |
| Barriers | swarm-patterns exposes `barrier_arrive`; primitives puts barriers in the library tier | **Open:** library over `wait`, exposed through the tool seam |
| Waiting | acp-mcp returns a cursor; primitives parks; swarm-patterns picks by driver | **Open:** park, with a bounded hold for one-shot workers. Parking is unproven per harness |
| OpenHands version | Platoon pins 1.54.0 on private overrides; we probed 1.59.0 | **Open:** pick one pin for the driver |

## Brief sections no report covers

| Section | Gap |
|---|---|
| 3 | Journal storage: SQLite durability settings, local versus network filesystems, crash recovery. Client-to-service transport for attach and reconnect. Embedded versus service ownership lifecycle |
| 4 | The custom-driver protocol itself. PTY fallback appears only as a TUI handoff rule |
| 6 | Event envelope and schema. A cross-harness table of what counts as observed exposure. The content store for large bodies |
| 7 | Keeping reward and judge data out of policy-visible context. Dataset handling for human interventions. The frozen prior-batch baseline is only a stub |
| 8 | A cross-harness table for project instructions, skills, slash commands, hooks and compaction versus our tools. The headless JSONL and exit-code contract |
| 10 | Workspace modes per harness. Capture of commits, tests, merges and conflicts. The Gitea or GitLab extension path |
| 11 | How an extension primitive reaches the SDK, tool protocol, CLI and generic UI. This is a design task |
| 12 | Outbox and uncertain-effect recovery. Process-tree cleanup across platforms. Secret storage, retention and redaction. Metrics and their overhead |
| 13 | Nothing ran on macOS, which is a required platform. Windows and WSL are unlabelled |

Sections 1, 2, 5, 9 and 14 and both addenda are covered; section 14 sets sequence only.

## Corrections made to reports

- **adapter-claude-code:** added tool-search deferral (table, matrix, launch advice). Closed the `role: "system"` question with probe results. Replaced a subscription plan name with a neutral term.
- **adapter-codex:** token-only identity. Added the `accept` result and the end-to-end gateway confirmation. Fixed the Platoon date.
- **adapter-openhands:** native child level is `inferred`. Replaced the untested-gateway risk with probe results. Fixed the Platoon license.
- **adapter-others:** pi training row now cites the probe. Separated built-in modules from specs. Scoped the "gateway not exercised" note.
- **acp-mcp:** Prime Agent row corrected. pi and OpenHands MCP versions filled in. Noted they lack anchors.
- **platoon-platform:** `x-platoon-call-id` scope fixed. Added an addendum to the adapter ranking.
- **platoon-training:** added the path-form URL credential warning.
- **swarm-patterns, distributed-primitives:** fixed the Platoon license and the ACP spec and OpenHands SDK dates. **swarmchat, tui-expectations:** none needed.

## Leak check

Scanned all reports and fixtures for local paths, cluster and account names, emails, tokens and structured path, host and account fields. No leak found. Path-like hits were upstream repo paths and Codex agent paths. One plan name was neutralised. Fixture paths are placeholders.

## Remaining gaps

- **Prime Agent is unverified live.** A model turn was denied by the permission policy and not retried. Everything but version and help is source-only, so make no capability claim yet. Needs an owner decision.
- **DAO is undefined.** The owner should say what it means. Scenario 2 implements only the brief's table row.
- **Terms.** Training through Claude Code against a non-Claude policy is blocked pending an owner decision. OpenAI's Terms pages returned 403, so those clauses come from search snippets and need review.
- **Hidden calls.** OpenCode title calls and any unlabelled side call would train as `policy`. Untested through the gateway.
- **Not tested:** parking and cold resume on any harness, Codex MCP tools under Code Mode on a live model, ACP past `initialize` on real agents (steering was only advertised), `rollout_isolation: process`, mint over a Unix socket, OpenHands condenser through the gateway.
- **Fixture review.** `claude-stream-sample.jsonl` holds short strings authored by a proprietary CLI. Review before the repository goes public.

## Clean-room statement

No implementation named in the clean-room rule was searched for, surfaced or opened in this review or any report. GitSwarm is used as a pattern reference with the owner's permission.
