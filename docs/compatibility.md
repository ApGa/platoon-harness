# Compatibility

What each upstream is, how we use it, and what is known about it. Everything here was inspected or measured on 2026-11-02.
These are **upstream facts**, not claims about our drivers. No driver exists yet. Each driver records its own verified result
in the status list of section 3 as it lands, and a result pins to `(driver, harness version)` (architecture §9.3).

Detail and citations live in [research/](research/README.md). Where a report and a spike disagree, the spike wins because
it was measured later. The critic's corrections in the research index are authoritative. Section 3 lists what changed.

## 1. Upstreams

**IMPLEMENTED** is code on the default branch. **EXPERIMENTAL** is shipped and labelled unstable. **DRAFT** is a proposal with
no code. **DOCUMENTED-ONLY** has no code to read.

| Upstream | Inspected | License and constraint | How we use it | IMPLEMENTED versus DRAFT | Most important fact |
|---|---|---|---|---|---|
| Platoon | `efe3b277c82c`, 0.5.0 | MIT AND Apache-2.0 (tool parsers). Optional extension; keep its NOTICE if parser code is ever copied | Training authority through an extension, pinned `>=0.5,<0.6` | IMPLEMENTED: gateway, child mint, trajectories, env forks, extensions. EXPERIMENTAL: credit, policies, Responses and Messages dialects. DRAFT: `AgentGraph`, `RewardEvent`, attribution levels, native selectors, `bus` | The only exact identity for an external agent is one key per agent, from `POST /v1/platoon/agents` |
| SwarmChat | `fb5aa6a05b40`, PyPI 0.1.0 | MIT. Keep the notice when serving its page assets. Exact pin | Second client: its pinned frontend over our own backend. Its server never runs | IMPLEMENTED: server, agent API and a read-only viewer. No composer exists or is documented. Nothing DRAFT | Messages have no idempotency key, no metadata and no caller ids, so a projection into its server cannot be idempotent |
| Toad | `dd4f90e8b370`, 0.6.20 | AGPL-3.0. Ideas only: no code, no dependency. Its `textual-diff-view` is AGPL too | Interaction reference | IMPLEMENTED: own ACP v1 client. Nothing DRAFT | Copying is ruled out by license, not merely unnecessary |
| OpenHands | SDK `988494576218`, wheels 1.59.0. CLI `283c6ac3610f`, `openhands` 1.16.0 | MIT. The SDK installs proprietary `lmnr-claude-code-proxy` 0.2.0: review before shipping in any image | Wire worker on SDK `arun()` in its own environment | IMPLEMENTED: SDK, agent server, `openhands acp`. Docs list `--streaming`, absent from CLI 1.16.0 | Passed the exact path on a minted key. Cannot share an environment with `mcp` 2.3.0 or ACP 1.0.0rc3, and the CLI pins SDK 1.28.1 |
| Codex | `05c08d765523`, CLI 0.164.0 probed (latest stable 0.166.0). Spike source read at tag commit `6aaac6948030` | Apache-2.0 with NOTICE. User-installed. Never read or copy `auth.json` | `codex app-server` over stdio, no `experimentalApi` | IMPLEMENTED in behavior, labelled Experimental upstream. `codex mcp-server` is removed. `turn/steer`, `thread/fork`, `thread/inject_items` are on the stable handshake | The model reaches MCP tools only from inside a Code Mode script, so `omit_tools_from: ["deferred"]` is required |
| Claude Code | `f0b737f94f3b` (changelog and examples only), CLI 2.1.316 probed, Agent SDK `2146f9d89855` | Proprietary. Never bundle, vendor or patch. Agent SDK wheels bundle the CLI: no default dependency, no re-hosting | `claude -p` stream-json with the control protocol on the user's own binary | IMPLEMENTED. Undocumented: `--permission-prompt-tool stdio`, `command_lifecycle`. EXPERIMENTAL: agent teams, which do not run in `-p` | `ANTHROPIC_BASE_URL` alone keeps a saved login active, so it is never set without a gateway credential |
| OpenCode | `ff90ed91607c`, 2.2.5 (`@opencode/cli`; `opencode-ai` stops at 1.19.5) | MIT. User-installed | Generic ACP driver first. An HTTP driver is a later option | IMPLEMENTED: `opencode acp`, `opencode serve`. Its `/api` spec calls itself experimental. `/api/experimental/*` is EXPERIMENTAL | With no model set, prompts go to a hosted free model, with no credentials configured |
| pi | `c9f4c7b9fcd0`, 1.4.0 | MIT. User-installed | `pi --mode rpc` | IMPLEMENTED: RPC, first-party MCP, extensions. No ACP in the repository | Passed the full trainable path on a minted key, and native spawning does not exist to reconcile |
| Prime Agent | `c6d4da9421e6`, 0.10.2 | MIT, tarball adds `PHOTON-LICENSE.md`. User-installed. Not on npm or PyPI | After a live probe: `--mode rpc` or ACP | IMPLEMENTED per source. EXPERIMENTAL: Factory. Nothing beyond version and help has run | No capability claim can be made: no model turn was run |
| ACP | Spec `212f0cace08a`, schema 1.29.0. Python SDK `9853d8b514d6`, 0.12.1 and 1.0.0rc3 | Apache-2.0. Wheels have no License field, so scanners may flag them. Never bundle the Claude or Codex adapters | Generic driver, protocol 1 | IMPLEMENTED: v1 stable. EXPERIMENTAL: `session/fork`, `subagent_update`, `providers/*`, `mcp/message` and more. DRAFT: v2 | Stable v1 has no mid-turn message, sender identity, idempotent prompt or model-call attribution |
| MCP | Spec `d0e246ea3c69`, revision 2026-07-28. Python SDK `d7845c073a2b`, 2.3.0 | Spec Apache-2.0, MIT in transition, docs CC-BY-4.0: attribute quoted docs. Python SDK MIT | Tool plane, through our own stdlib server | IMPLEMENTED: revision 2026-07-28 is current. `draft` has no changes | Real clients settle on older revisions: Codex `2025-06-18`, Claude Code `2025-11-25` |
| DeLM | `66617616e708` | MIT. Pattern only, credit in docs | Pattern reference | IMPLEMENTED: research runner. Read, not executed | State is a fold over one append-only events table, and a claim is one `BEGIN IMMEDIATE` transaction |
| Agensh | `d6063b9086d5` | MIT. Pattern only, credit in docs | Pattern reference | IMPLEMENTED: research harness on Docker Compose. Read, not executed | Mid-turn notices are appended to tool results, which needs no harness patch. Its `CLAIM` is advisory |
| GitSwarm | Site `9f66af0b919f`, arXiv 2610.04862v1 | No license in the repository. Paper CC BY 4.0 per PDF metadata, unconfirmed. Pattern reference by owner permission: write our own code, credit it | Pattern reference | DOCUMENTED-ONLY: the repository is a website, not the system | `informed_by` is declared, not causal. That is the split our evidence types keep |

**Starting observations from brief section 2:**

| Observation | Verdict | Note |
|---|---|---|
| RFC 0021's `CreditEstimator` partly supersedes RFC 0001's credit section, with per-token advantages | **Verified** | EXPERIMENTAL. RFC 0021's header still says "Implementation: None yet", so the code is what counts. Only `reverse_kl` uses per-token advantages |
| SwarmChat's browser viewer is read-only | **Verified** | Enforced on the server. Read-only is a property of the `view_*` requests, not the link: the admin token opens them too. Eight mutating requests with a view token gave 401 |
| Toad uses ACP and is a design reference | **Verified** | Own client with `PROTOCOL_VERSION = 1`, no ACP SDK dependency |
| Platoon extensions: explicit selection, lazy loading, provenance, conformance checks | **Partly verified** | The first three hold. Conformance exists only for experimental sampler, admission, trainer and credit APIs, plus static `platoon extensions check`. No harness or environment suite exists |

## 2. Protocol pins

| Protocol | Pin | Negotiation rule | Refuse |
|---|---|---|---|
| **ACP** | Protocol `1`, schema v1. `agent-client-protocol>=0.12.1,<2` in the `[acp]` extra, 1.0.0rc3 locked, CI on both | Send `protocolVersion: 1` once per connection. An agent that supports it echoes it, otherwise it answers its own latest. Disconnect on anything but `1` | v2 unless an explicit experimental flag is set. An unstable feature unless it has its own opt-in, a capability check, a version guard and a fixture. Negotiating v1 implies none of them |
| **MCP** | Handshake era: `2025-11-25` and `2025-06-18`. Core tools use `2025-06-18` semantics. Our stdlib server, not the `mcp` package | Answer `server/discover` with -32601, so clients fall back to `initialize`. Answer `initialize` with the client's version when it is one of those two, and with `2025-11-25` otherwise. Observe the settled version per connection | Sessions, SSE and `GET` or `DELETE` (405). Undeclared arguments return `isError: true`. Identity from `clientInfo`, `_meta` or arguments |
| **Driver wire** | `protocol: 1`. Line-delimited JSON-RPC 2.0 on stdio, split on LF only, logs on stderr | `start` carries one integer. An unknown integer is refused. There is no range and no fallback | Any verb outside the seven `Driver` methods. An unknown report frame becomes `native` plus a gap, never a log line |

Consequences:

- **ACP.** We advertise `fs: false` and `terminal: false`: both are stable in v1 and removed in v2. An echoed version proves
  nothing, since `openhands acp` returned 99 when asked for 99. Capabilities omitted are unsupported. Claude and Codex
  adapters already parse the v2 `initialize` shape, so v1 lifecycle assumptions stay inside the driver.
- **ACP SDK.** Unknown `sessionUpdate` kinds are dropped in the notification handler and the client never sees them.
  `observers` run before parsing, so raw frames are captured there, and a parse failure becomes a gap.
- **MCP.** Revision 2026-07-28 makes `server/discover` mandatory to implement, so our server does not claim that revision. A
  modern-only client cannot reach it. Neither real client needs that. Modern-only features (multi round-trip results,
  `subscriptions/listen`, tasks) carry no core semantics.
- **Dependencies.** The core SDK depends on neither `mcp` nor `agent-client-protocol`. `openhands-sdk` 1.59.0 is unsatisfiable
  with `mcp==2.3.0` or `agent-client-protocol==1.0.0rc3`, and unpinned it resolves silently to 1.49.1 and 1.44.1. Pin it with a
  floor and keep it in its own environment.
- **Harness versions.** Exact, user-installed, shown by `doctor` and recorded in the manifest. Adapters seen:
  `claude-agent-acp@0.99.1`, `codex-acp@2.5.0`. Neither is bundled.

## 3. Capability matrix

Each cell is a status, a short limitation and how it is known.

| Label | Meaning |
|---|---|
| **[R]** | Live probe with a real model |
| **[L]** | Loopback probe: the real harness or gateway against a scripted local model, no paid calls |
| **[S]** | Source or docs reading, not executed |
| **[U]** | Unknown: no evidence either way |

Status is `yes`, `partial`, `no`, `unverified` (source says so, nothing ran) or `unknown`. `yes` and `partial` need [R] or [L].
Unknown is not no. Reports label OpenCode and pi runs `[LIVE]` against a fake server: those are **[L]** here. Only Claude Code and Codex have seen a real model on purpose.

| Adapter | Launch | Streaming | Tool injection | Messaging | Interruption | Approvals | Resume | Native subagents | Model endpoint | Exact call attribution | Training eligibility |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **claude** 2.1.316 | yes. `claude -p` stream-json, stdin held open. User installs and logs in [R] | yes. Subagents gave no partial events; `assistant` output tokens are a placeholder [R] | yes. HTTP MCP, needs `alwaysLoad` or tools defer. `system/init` does not prove visibility [R] [L] | yes. Stdin across turns [R]; absorbed at a tool boundary or next turn [L] | yes. Receipt in 22 ms; the aborted call's tokens go unrecorded [R] | yes. `can_use_tool`; `stdio` value is SDK-private; read-only commands skip it [R] [L] | yes. `--resume`, 1 cold trial; needs a persisted transcript [R] | partial. Observed, identity `inferred` [R]. Teams do not run in `-p` [S] | partial. Base URL plus credential [L]. Non-Claude models unsupported upstream [S] | partial. `toolUseId` equals the model id [R]. Native: none. Gateway join exists but no call records [L] | **no.** Gateway run exits 1 with zero records; terms await an owner decision [L] |
| **codex** 0.164.0 | yes. `codex app-server`, labelled Experimental upstream [R] | yes. `item/*`, deltas; `item/completed` is truth [R] | yes. Per thread, needs `omit_tools_from` and an approve mode [R] | yes. `turn/start`, `turn/steer` with `expectedTurnId`; next model call [R] | partial. `turn/interrupt` [R]; running children continue [L] | yes. Server requests [L]. Set `approvalsReviewer`; `accept` does not fix the outcome [R] [L] | yes. `thread/resume`, 1 cold trial; resend config [R] | partial. v1 and v2 observed, identity `inferred`, no `thread/started` for a child [L] | yes. `model_providers`, thread scoped; `responses` only [L] | partial. Thread and turn only on stable. `callId` joins to the `exec` script, not a call [R]. Exact per key at a gateway [L] | **no.** Identity passes, but MCP tools never reach the policy [L] |
| **pi** 1.4.0 | yes. `pi --mode rpc`; Node >= 22.19 [L] | yes. `message_end` is authoritative; a stalled reader stalls pi [L] | yes. MCP with `exposure: direct`, on a stdio server. HTTP not probed [L] | yes. `prompt`, `steer`, `follow_up`; turn boundaries [L] | yes. `abort`, then `agent_settled {aborted: true}` [L] | partial. None native. A probe gate worked; we would ship one. Not a security boundary [L] | yes. `--session <id>` with full history [L] | no. None by design; extensions can add them [S] | yes. `models.json`, one agent dir per agent [L] | partial. Agent level by key. No per-call id, no MCP anchor [L] | candidate. Full path passed on a minted key. Platoon has no pi spec [L] |
| **openhands** SDK 1.59.0 | yes. SDK `Conversation` under `arun()`; import 8-11 s on network storage. The wire worker is planned [L] | yes. Needs `stream=True` and a token callback; children never stream [L] | yes. MCP per `Agent`, tool in the prompt, on a stdio server. HTTP with headers not probed. A failed start is silent [L] | yes. `send_message`, next model request; log order misleads [L] | yes. `interrupt()` abandons the call in 0.05 s; a gateway may have recorded it [L] | partial. Confirmation policies. No pending event; lone `finish` and `think` skip it [L] | yes. Same id, fresh `Agent`. Key resupplied; tools cannot be removed [L] | partial. `task`, opt-in. No child events reach the parent [L] | yes. `LLM(...)`; unrequested fields sent [L] | yes. `llm_response_id == call_id` per action on a scoped key. A native child is exact only with a keyed factory. Extra calls share the endpoint [L] | **yes, on a profile.** Exact records and datums on a minted child, SDK 1.59.0 and a scripted policy. Platoon's own 1.54.0 spec has no MCP, and its live test did not run. Condenser, delegation and long runs untested [L] |
| **opencode** 2.2.5 via ACP | yes. `opencode acp`, private server per process [L] | partial. `session/update`; less detail than HTTP [L] | partial. `mcpServers` landed behind Code Mode, even with `codemode: false` in config [L] | partial. Turn boundary. A second prompt fails -32603 [L] | yes. `session/cancel`, stop reason `cancelled` [L] | partial. `session/request_permission`, only under an `ask` rule. No rule, no ask [L] | unverified. Advertised, not exercised over ACP [L] | partial. Child sessions seen on HTTP [L]; ACP updates need opt-in [S] | yes. `OPENCODE_CONFIG_CONTENT`; reaches the tool shell. Always pin a model [L] | partial. Session level by header, one credential per process; title calls unlabelled [L] | unknown. Untested through the gateway. Title calls would train as `policy` [U] |
| **prime** 0.10.2 | unverified. Version and help ran; no model turn. Needs `uv` and Python [S] | unverified [S] | unverified. Through the Python REPL [S] | unverified. `steer`, `follow_up` on RPC [S] | unverified. Children and kernels must stop too [S] | no. None in the crates [S] | unverified. CLI only in source; ACP `load_session: false` [S] | unverified. `rlm.spawn`, reported by the harness [S] | unverified. `models.json` [S] | unknown. No parent header found; kernel calls unknown [U] | unknown. No live probe [U] |
| **generic ACP**, protocol 1 | yes. Baseline required of every agent [S]; SDK checked on a fake agent [L] | partial. 14 stable update kinds; the SDK drops unknown ones [S] [L] | unverified. `mcpServers`, stdio mandatory. Visibility varies by agent [S] | unverified. Next turn. A second prompt mid-turn is undefined [S] | unverified. `session/cancel` is baseline. `openhands acp` maps it to `pause()` [S] | unverified. `session/request_permission` is a baseline client method. Whether an agent asks is per agent [S] | unverified. Only if advertised [S] | no. Stable has none; `subagent_update` is unstable [S] | no. `providers/*` is unstable [S] | no. `toolCallId` only [S] | no. Only through a gateway, per agent [S] |
| **generic exec**, one-shot | unknown. Any command; `exec` driver is planned [U] | unknown. Stdout only, no structured events [U] | unknown. `ph` on `PATH`; a sandbox may block it [U] | no. No input after launch; cannot park [S] | unknown. Process group only [U] | unknown. No answer path in the design [U] | unknown. Depends on the command [U] | unknown. Opaque [U] | unknown. Whatever the command accepts [U] | unverified. Exact only if it uses its own key alone [S] | unknown. Per command; Platoon admits a custom agent on its own key [S] |

### Driver status

Every row is **planned** today. A driver fills in its row when `check_driver` passes, with the result pinned to the harness version.
A cell above is never upgraded by a driver landing; only the row below changes.

| Driver | Path | Depends on | Driver status | Conformance result |
|---|---|---|---|---|
| `claude` | Stream-json plus control protocol | User's binary | planned | none |
| `codex` | `codex app-server` over stdio | User's binary | planned | none |
| `pi` | `pi --mode rpc` | User's install | planned | none |
| `openhands` | `WireDriver`, worker on SDK `arun()` | Own environment | planned | none |
| ACP, covering `opencode` | Generic driver, protocol 1 | `[acp]` extra | planned | none |
| `prime` | Decided after a live probe | User's install | planned | none |
| `exec` | One-shot command, `ph` only | Nothing | planned | none |

### Evidence

**claude, CLI 2.1.316.** [Report](research/adapter-claude-code.md), [spike](research/spikes/tools-and-parking.md),
[fixture](research/fixtures/claude-stream-sample.jsonl).

- Real model: 5 turns with `haiku` in one process (multi-turn, one subagent, interrupt, MCP approval), then 14 spike turns with `claude-haiku-5-5`.
- Loopback: the real CLI against a scripted Messages server. `Bash(echo *)` ask rule, mid-Bash message, `/compact`, `--resume`, `--fork-session`.
- Visibility: tool search defers MCP tools. `alwaysLoad` or `ENABLE_TOOL_SEARCH=false` put the tool in the first request. Live runs made 0 `ToolSearch` uses in 28 messages, but that request body was not inspected.
- Stream usage: `model_usage_since_last_result` gives the tree's delta (undocumented). Interrupted calls record nothing.
- Fallback trial: after `interrupt` and stop, the process exits 1. Treat that as normal. In the earlier probe, after `interrupt` alone, the same process took the next turn.
- Background: in `-p` a subagent started in the background and a later notification opened an extra turn, so `result` is not one per user message. `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1` is the worker setting. Loopback.
- Approvals and workers: `can_use_tool` ran in the report, with `--permission-prompt-tool stdio`. The spike's worker launch did not use that flag and sets `--permission-prompts none`, which denies anything that would prompt. So that launch has no approval path.
- Floors: 2.1.259 for `--permission-prompts`, 2.1.273 for hint headers, 2.1.283 for prompt id.

**codex, CLI 0.164.0.** [Report](research/adapter-codex.md), [spike](research/spikes/tools-and-parking.md),
[fixture](research/fixtures/codex-appserver-sample.jsonl).

- Real model: 3 report turns, then 24 spike turns with `gpt-6-luna`. Client approval, subagents and interrupt scope came from the stub.
- Tool found by the model: default 6 of 7 threads, each needing a discovery call. With `omit_tools_from: ["deferred"]`, 8 of 8.
- `approvalPolicy: never` fails MCP calls closed unless `default_tools_approval_mode` is `approve`.
- `accept` is not an outcome: 29 of 48 accepted commands ran and 19 failed with EROFS on identical input, cause not established.
- Stable usage has no response id. `rawResponse/completed` has one but is internal-only. Interrupted calls report nothing, so totals are a lower bound.
- `bearer_token_env_var` reaches the agent shell unless `shell_environment_policy.exclude` names it (1 trial).
- Resume on a different provider is refused in the app-server README at the pinned clone, which is ahead of 0.164.0. Keep the provider the same.

**pi 1.4.0.** [Report](research/adapter-others.md), [fixture](research/fixtures/pi-sample.jsonl).

- All loopback: fake chat server, isolated `HOME`, on Node 26.13.0. No real model.
- `mcp__coord__ping` was in the first request. A tool turn made exactly 2 calls, with no title call.
- Critic probe: real pi on a minted child key through the real gateway. Tool seen and called, exact tokens, 2 datums on the child.
- `tools/call` `_meta` held only `progressToken`, so tool-to-call joins have no anchor.
- `cacheWarming` defaults to `"streaming"`: set it `"off"` for trainable runs.
- Split on LF only: U+2028 is legal inside JSON strings, so `str.splitlines` is unsafe.

**openhands, SDK 1.59.0.** [Report](research/adapter-openhands.md), [fixture](research/fixtures/openhands-events-sample.json).

- All loopback, against a scripted OpenAI-compatible server. No real model. The clone is ahead of the wheel, so unprobed citations need rechecking.
- Critic probes: Platoon's runner on 1.59.0 gave 2 exact records with logprobs and 2 datums on the child. `arun()` with an MCP tool had `llm_response_id == call_id` for every action.
- Platoon pins 1.54.0.post1 and overrides private methods, so the driver pin is open.
- Undeclared tool arguments fail client-side here, unlike Codex and Claude Code. Server-side rejection stays mandatory.
- `Agent()` alone has no condenser and ignores `AGENTS.md`.
- The `openhands acp` path is a weaker row: CLI 1.16.0, SDK 1.28.1, no token streaming, no `usage_update`, no `session/resume`, and `session/cancel` maps to `pause()`. It is a generic ACP conformance target.

**opencode, 2.2.5 via ACP.** [Report](research/adapter-others.md), [fixture](research/fixtures/opencode-sample.jsonl).

- Loopback frames cover `initialize`, `session/new`, `session/prompt`, `session/request_permission` and `session/cancel`.
- `initialize` advertised `loadSession`, `additionalDirectories`, `close`, `delete`, `fork`, `list`, `resume`, HTTP MCP, no SSE.
- A config entry with `codemode: false` gives a direct tool on the `run` and `serve` paths. A prompt sent before MCP connects misses the tool. Whether a config entry can win over `mcpServers` is not established.
- Hidden calls: a one-tool turn made 3 calls, one a title call with `tools: []` and no purpose header.
- A child's own id appears only in `x-opencode-session-id`, and the parent headers name its parent. `x-session-id` stays the root id. Key on `x-opencode-session-id`.
- One unpinned run reached hosted `opencode/flint-40b-free` by accident. That is the only real-model contact, and it proves the risk, not a capability.
- HTTP depth (`steer`, `queue`, inbox evidence) ran on loopback but is not reachable through ACP. Per-session permission rules are source only.

**prime, 0.10.2.** [Report](research/adapter-others.md), [fixture note](research/fixtures/prime-agent-sample.md).

- The Linux x64 tarball printed its version and help. A model turn was denied by the session's permission policy and not retried.
- Everything else is source. The fixture states it holds no capture. Make no claim from this row.

**generic ACP.** [Report](research/acp-mcp.md).

- The spec and schema are read at `212f0cace08a`. Both SDK versions ran against a fake raw agent, on `initialize`, `session/new`, `prompt` and `_meta`.
- `claude-agent-acp@0.99.1` and `codex-acp@2.5.0` were probed at `initialize` only. They advertise `_meta.steering.supported`. No steering request was sent.

**generic exec.** Nothing upstream to inspect. [Architecture §9.1](architecture.md) defines it. Platoon's `platoon-bash` and
`mini-swe-agent` specs show that one process on one key is exact there, which is the only fact the row rests on.

### Report text this page overrides

| Report said | Now | Why |
|---|---|---|
| Codex `callId` equals the model's call id (acp-mcp, claim 11, finding 5) | True on a stub with a plain tool. Under live Code Mode it is `exec-<uuid>`: 0 of 2 matched | Spike. One Codex script can make several calls under shared ids |
| Codex live tool visibility unverified (adapter-codex, finding 1) | Default 6 of 7, `omit_tools_from` 8 of 8 | Spike |
| Over the gateway, Codex coordination uses the shell client (finding 3) | Shell `socket()` to loopback failed under `workspace-write` (1 trial), so that path looks blocked too. Unix sockets are untested | Spike. Section 4 states the result |
| `mcp` SDK in an extra, dual-era server (acp-mcp); stdio shim (adapter-codex) | Stdlib tools-only HTTP server, stdio shim as fallback, `server/discover` -32601 | Spike, architecture §10 |
| Parking unproven; cold resume untested (index, distributed-primitives) | Parking clean 10 of 10 with the tool visible. Cold resume 1 trial each | Spike |
| 3 of 4 `codex exec` stdio runs sent no MCP tools (acp-mcp) | Not reproduced over HTTP with a slow `initialize` (1 trial). `exec` and stdio were not rerun, so it stays open | Spike |
| Claude launch omits `--setting-sources` (adapter-claude-code) | True for everyday use. Workers use `--strict-mcp-config --setting-sources= --permission-prompts none` and a minimal allowlisted env | Spike |
| ACP untested past `initialize` on real agents (index) | Holds for the Claude and Codex adapters. OpenCode and `openhands acp` ran prompts on loopback | Recorded frames |

## 4. Operational, Observable, Trainable

Levels are computed per agent from what was verified, and no driver can claim one (architecture §9.4). This table is the ceiling
upstream allows today, not a computed level. Platoon still decides eligibility.

| Adapter | Operational | Observable | Trainable |
|---|---|---|---|
| `claude` | **Yes.** Control, tools, interrupt, approvals and resume all ran on a real model | **Yes, with gaps.** Stable ids across stream and hooks. No token ids or logprobs, thinking text unreliable, aborted calls unrecorded, shell reads blind, children need `--forward-subagent-text` | **No.** Native login never. Through Platoon: `Unsupported message role 'system'`, exit 1, zero records. No Platoon spec. Anthropic does not support non-Claude models behind a gateway. Terms await the owner |
| `codex` | **Yes, with a guard.** Tools need `omit_tools_from`. A turn that ends with no required `wait` must be flagged, since the default failure was silent | **Yes, with gaps.** Items and per-thread usage are good. No response id on stable. Review, compact, memory and Auto-review work are hidden. Tool-to-call links stop at the script | **No.** Exact calls land on a minted key, but the gateway's Responses dialect drops `namespace` and `custom` tools, so MCP tools never reach the policy. The shell could not reach loopback under `workspace-write` (1 trial), and Unix sockets from that shell are untested. So no coordinated path is known in that sandbox. No Platoon spec |
| `pi` | **Yes on loopback.** No real model yet. Approvals are an extension we would ship, or nothing | **Yes on loopback.** Assembled prompt visible, clean call profile. Queue durability, compaction and tool-to-call anchors are gaps | **Candidate.** Full path passed. Needs a spec, cache warming off, and extensions restricted. Compaction purpose is unlabelled |
| `openhands` | **Yes on loopback.** Own environment. Assert the tools appear in `SystemPromptEvent.tools`, or fail the spawn | **Yes on loopback.** Best record: `llm_response_id`, `Condensation` with forgotten ids. Children visible only on disk after the fact | **Yes on loopback, on a pinned profile.** `num_retries` 0 or 1, `api_mode="chat"`, reasoning replay on (Platoon gets it from private overrides), condenser marked `aux`, no autotitle, no `ask_agent`, fixed tools, native delegation off or keyed. The pin is open. Subscription or Cloud auth never |
| `opencode` via ACP | **Partial.** Control works. Tool exposure through `mcpServers` is unresolved, so tools may hide behind Code Mode | **Partial.** Coarser than HTTP. Title calls hidden. Inbox delivery evidence is HTTP only | **Unknown.** Untested with Platoon. Title and compaction calls cannot be told apart by anything exact |
| `prime` | **Unknown.** No model turn ran | **Unknown** | **Unknown.** Not marked until a live probe exists |
| Generic ACP | **Per agent,** after conformance. Turn boundary only, `steer` after a fixture | **At best.** ACP carries no call attribution. Gaps across reconnect are labelled | **No by ACP alone.** Requires the gateway plane, which ACP neither gives nor blocks |
| Generic exec | **Degraded.** One-shot, `ph` only, no parking. `wait` beyond `hold` refuses `unsupported` | **Minimal.** Turn-end probes and the monitor. Most surfaces are `none` | **Possible,** one process on its own key with a verified profile. Nothing has been verified |

Across adapters: only Claude Code and Codex give an MCP-to-tool-call anchor, Codex's stops at the script, and any harness with a
shell is blind to `shell_reads` for life. A native child on a shared key stays on the parent and is at most `inferred`. A profile on a
plan login is never Trainable. Token ids and logprobs come only from the gateway.

## 5. Native features and coordination

Rules that hold on every harness:

- **Instructions.** We append through the supported path. We never overwrite `CLAUDE.md`, `AGENTS.md`, skills or hooks.
- **Teaching tools.** The turn preamble and tool descriptions name tools exactly. No harness's tool discovery is relied on.
- **Tool set.** Fixed per role at launch. Valid targets change, so `peers` and the preamble list them.
- **Skills.** Per harness. No unification is claimed.
- **Slash commands.** A small core of ours plus namespaced passthrough. The syntax is a TUI decision and is not set here.
- **Hooks.** Displayed, not reimplemented.
- **Compaction.** Passed through and recorded as `compacted{forgotten}`. If what was forgotten is unknown, that is a
  `compaction_opaque` gap. The context version advances either way. Coordination survives because the state is on the server:
  cursors are server-held, and a fence defaults to the caller's live lease. A notice carried on a tool result can still be lost to
  compaction, so "delivered" never means "still in context".

**Passthrough** means the native feature keeps working and we leave it alone. **Namespaced** means it sits beside ours under a
distinct name. **Unsupported** means it is unavailable on this path, with a reason. **Not determined** means the research does not say.

| Harness | Surface | Mode | Interaction |
|---|---|---|---|
| `claude` | Project instructions | Passthrough; off for workers | Omitting `--setting-sources` loads `CLAUDE.md` and rules. `--setting-sources=` disables them for workers. Ours goes in `--append-system-prompt-file`, never `--system-prompt` |
| | Native skills | Passthrough; off for workers | Same switch. Built-in skills stay listed with empty sources: 20 in the probe. A forked skill uses a `forked-command-` prefix, not a tool id |
| | Slash commands | Passthrough, partial | `initialize` returns the command list. `/compact` ran over stream-json [L]. Other commands: not determined |
| | Tool configuration | Namespaced | Ours arrive as `mcp__<ns>__<tool>` and are pre-approved by `--allowedTools`. Everyday use keeps the user's servers. Workers use `--strict-mcp-config` |
| | Hooks | Passthrough; off for workers | User hooks still run. Ours go through `initialize`, never settings files. `-p` shows no trust dialog, so project hooks and `.mcp.json` run in an untrusted folder |
| | Session compaction | Passthrough, observed | `compact_boundary`, `PreCompact`, `PostCompact` [L]. Whether their fields name what was forgotten: not determined. Compaction also fires a false `SubagentStop`: it is not a child. Auto compaction was not probed |
| `codex` | Project instructions | Not determined | `developerInstructions` exists on `thread/start`, and `/init` exists in the TUI. How native project files load on app-server was not researched |
| | Native skills | Passthrough in everyday mode | A shared `CODEX_HOME` inherits skills and plugins. A per-run `CODEX_HOME` has none |
| | Slash commands | Not determined | 70+ in the TUI. Their reach over app-server was not researched. Compaction has its own RPC |
| | Tool configuration | Namespaced | `thread/start.config` overlays the user's config, so the user's servers still start. Ours arrive as namespace `mcp__<ns>`. Never `codex mcp add` or a config write. Project `.codex/config.toml` loads only when trusted |
| | Hooks | Not determined | Listed in the TUI. Behavior under app-server was not researched |
| | Session compaction | Passthrough, opaque | `thread/compact/start` is stable. Compaction runs as hidden internal work (`x-openai-subagent: compact`). What it forgets was not observed |
| `pi` | Project instructions | Not determined | The assembled prompt is visible as a `role: system` message with named `sections`. The file rules and append path were not researched |
| | Native skills | Not determined | Documented upstream. Interaction was not researched |
| | Slash commands | Not determined | Interactive surface. Their reach over RPC was not researched |
| | Tool configuration | Namespaced | `<agent-dir>/mcp.json`, one agent dir per agent, `exposure: direct`. Ours arrive as `mcp__<ns>__<tool>`. `.pi/mcp.json` needs project trust |
| | Hooks | Passthrough, restricted in training | No hooks as such: extensions on `tool_call`. User extensions can add subagents or alter calls. Training plans `--no-extensions` plus an explicit `-e` list, a combination not probed |
| | Session compaction | Not determined | No successful compaction was observed. Purpose is unlabelled at a gateway |
| `openhands` | Project instructions | Passthrough by choice | `Agent()` ignores them. `AgentContext(load_project_skills=True)` loads `.cursorrules`, `AGENTS.md`, `AGENT.md`, `CLAUDE.md`, `GEMINI.md`. On for everyday runs, off for training, recorded in resolved config |
| | Native skills | Passthrough by choice | `.agents/skills`, `~/.openhands/skills`. User and public skills default off in the SDK. Public skills fetch from GitHub: off in CI |
| | Slash commands | Not determined | Found only in the CLI's TUI, which the worker does not run. `openhands acp` sends `available_commands_update`. The SDK path was not researched |
| | Tool configuration | Namespaced by us | Per-`Agent` `mcp_config`. Tool names are **not** prefixed, so ours must not rely on a prefix. Whether they can collide with built-ins: not determined. Children inherit the parent's servers and token |
| | Hooks | Passthrough by choice | `hook_config=` per conversation. `.openhands/hooks.json` is CLI only. A `Stop` hook can deny finishing and inject feedback. Not probed live |
| | Session compaction | Passthrough, exact | `Condensation` names `forgotten_event_ids`, so `compacted{forgotten}` is exact. `Agent()` has no condenser by default. Through the gateway: untested |
| `opencode` | Project instructions | Not determined | Not researched |
| | Native skills | Not determined | Exists in its TUI. Reach over ACP was not researched |
| | Slash commands | Not determined | Reach over ACP was not researched |
| | Tool configuration | Namespaced, partial | `mcp.servers.<name>` in `OPENCODE_CONFIG_CONTENT`, with `codemode: false`. Ours then arrive as `<ns>_<tool>`. Servers passed in `session/new` did not appear as direct tools. Secrets there reach the tool shell |
| | Hooks | Not determined | Plugin hooks exist, some experimental. Interaction was not researched |
| | Session compaction | Not determined | `POST /compact` made two extra model calls; success was not observed. `session.compacted` was removed upstream. ACP behavior was not researched |
| `prime` | Project instructions | Not determined | Source only |
| | Native skills | Not determined | Skills ship in the repository. Native peer messaging, with a daemon-derived sender, overlaps our messaging: pick an owner per run |
| | Slash commands | Not determined | `/factory on` exists. Reach over RPC or ACP was not researched |
| | Tool configuration | Not determined | `mcpServers` or ACP `session/new`. The model reaches MCP through `mcp.call_tool` in Python, so direct visibility is unverified |
| | Hooks | Not determined | None found in the research |
| | Session compaction | Not determined | `compact` is an RPC command. Not run |
| Generic ACP | Project instructions | Passthrough; appending unsupported in stable | The agent keeps its own files. `systemPrompt` on setup is EXPERIMENTAL, so our preamble travels in the prompt |
| | Skills, slash commands | Not determined | `available_commands_update` is a stable update. How to invoke them is per agent |
| | Tool configuration | Per agent | `mcpServers`, re-supplied on resume with a fresh token. Name prefixing is per agent |
| | Hooks | Not determined | No hook method appears in the surface the report lists |
| | Session compaction | Passthrough, observed if sent | `compaction_update` and `compaction_summary_chunk` are stable updates. The SDK at 0.12.1 drops `compaction_update`, and the chunk was not tested, so raw capture matters |

## 6. Supported platforms

The initial release targets **Linux and macOS**. Linux is the only platform anything has run on. Only the kernel and filesystem
detection rows describe our code. The others record probes of upstreams or throwaway prototypes, and [STATUS.md](STATUS.md) holds what exists.

| Component | Linux | macOS | Windows | WSL |
|---|---|---|---|---|
| Kernel and journal | **Tested.** Unit tests, including SIGKILL. The spike's prototype had 0 violations in 226,807 acked commands over 40 kills. Power loss not tested | **Not run.** Needs `fullfsync=ON` and `checkpoint_fullfsync=ON`. `F_FULLFSYNC` latency is unmeasured and decides the 50 ms mark | **Not a target.** Not run. The design uses `flock`, Unix sockets and process groups | **Not run.** Linux rules inside the distro filesystem. `/mnt/c` is 9p and refused |
| Control socket | **Measured.** Python `bind` allows 107 bytes | **Not run.** 103 usable, from headers | Not run | Not run |
| Filesystem detection | **Exercised:** xfs, tmpfs, Lustre, FUSE control, `proc`, symlinks. Other magics come from headers | **Not run.** Written from the man page | Not run | 9p magic known, not exercised |
| TUI | **Probed.** Textual 8.2.8 on a real PTY | Not run | Untested: probes used Unix `pty` | Not run |
| SwarmChat client | **Probed** against a stub authority, not our backend. Headless Chromium on RHEL 9.4 x86-64. Firefox and WebKit untested | Not run by us. Upstream runs `unittest` only | Not run by us. Upstream runs `unittest` only | Not run |
| Claude Code, Codex | **Real model** on x86-64 | Not run. Seatbelt not tested | Not run | Not run. Codex's sandbox does not support WSL1 |
| pi, OpenCode, OpenHands | **Loopback** on x86-64 | Not run | Not run | Not run |
| Prime Agent | Version and help on linux-x64 | Not run | Not run | Not run |
| Platoon bridge | Probed on CPU | **Unverified.** Platoon classifiers list POSIX Linux only. This does not affect the SDK | Not a target | Not run |

Performance on Linux, from the [journal spike](research/spikes/journal-performance.md): at 500 events per second with 100 simulated
agents, ack p99 was 2.8 ms on node-local NVMe. Those are server disks with near-instant flush, so they do not stand in for a laptop.
Ack p99 is at least twice the sync time, so a sync above about 20 ms misses the 50 ms mark. Run the benchmark on a real Mac before
Milestone 1 closes.

| Prerequisite | Requirement |
|---|---|
| `platoon-harness` | Python 3.12+. ACP wheels cap at `<3.15` |
| `claude`, `codex` | User-installed binary |
| `opencode` | `@opencode/cli`, platform binary, no Node at runtime. Check the major version: bins are `opencode` and `opencode2` |
| `pi` | Node >= 22.19 |
| `openhands` | Python 3.12+. The CLI needs `==3.12.*`. 387 MB venv for the SDK alone |
| `prime` | Release tarball, `uv`, Python >= 3.11 kernel |
| Codex sandbox on Linux | Bubblewrap and user namespaces. A bundled `bwrap` is the fallback. With user namespaces blocked, sandboxed commands cannot run (docs, not reproduced). Never fall back to `danger-full-access` silently |

## 7. Auth and terms

This is engineering policy, not legal advice.

| Profile | What it is | What we do | Levels |
|---|---|---|---|
| **Native login** | The harness's own sign-in, made by the user through its own flow | Spawn the user's binary on the user's machine, with no credential added. `doctor` shows only whether a login exists and which kind. Each harness signs itself in | Operational, Observable |
| **Plan login** | A native login on a subscription | The same, for that user's own work. Headless multi-agent exits 78 and names the fix unless the user opts in. `web --remote` refuses a second person | Operational, Observable. Never Trainable |
| **API key** | A user-supplied key or provider credential | Pass it to that process by env var name. Scrub `ANTHROPIC_API_KEY` unless chosen: `-p` always uses it when present, which is a silent billing surprise | Operational, Observable |
| **Gateway** | A key we receive from Platoon for one agent | One key per process, with an isolated config (`CLAUDE_CONFIG_DIR`, per-run `CODEX_HOME`). A path-form URL is a credential: normalize it to origin plus bearer before a driver sees it. Validate base URL and credential together, then fail closed | Adds Trainable where section 4 allows |

**We never:**

- Read, copy, store, log, refresh or forward `~/.claude/.credentials.json`, keychain entries, `CLAUDE_CODE_OAUTH_TOKEN` values, `auth.json` or any plan token.
- Offer a provider sign-in in our UI, or embed, wrap or proxy one. We tell the user to run `claude auth login` or `codex login`.
- Set `ANTHROPIC_BASE_URL` while a login could be the active credential.
- Reuse a subscription token in our own HTTP client or a proxy, or call OAuth refresh ourselves.
- Let one person's login serve another: no shared service mode, no remote user, no team pool.
- Bundle, vendor or patch a proprietary binary, or depend on one through a default install.
- Use "Claude Code" or Anthropic names in a product, feature or logo, set `CLAUDE_CODE_ENTRYPOINT` to misrepresent the client, or impersonate a known client through `clientInfo.name`.
- Treat Claude-generated traces as training data for any model.
- Default unattended, high-volume or training runs to a plan login, or put a credential in a log, event, artifact, export or resolved config.

pi and Prime Agent ship Anthropic subscription logins, and OpenCode can drive the local `claude` binary. Our docs steer Claude
models in those harnesses to API keys, and the decision stays with the user. OpenHands' `LLM.subscription_login` calls a fixed
backend, so it never passes through a gateway. No stated policy was found on pi's provider page.

Quoted as recorded in the research, retrieved 2026-11-02.

| Source | Text |
|---|---|
| https://code.claude.com/docs/en/legal-and-compliance, Authentication and credential use | **OAuth authentication** is intended exclusively for purchasers of Claude Free, Pro, Max, Ultra, Team, and Enterprise subscription plans and is designed to support ordinary use of Claude Code and other native Anthropic applications. |
| https://code.claude.com/docs/en/legal-and-compliance, Authentication and credential use | **Developers** building products or services that interact with Claude's capabilities, including those using the Agent SDK, should use API key authentication through Claude Console or a supported cloud provider. Anthropic does not permit third-party developers to offer Claude.ai login into their own applications, or to route requests through Free, Pro, Max, or Ultra plan credentials on behalf of their users. Moreover, developers may not collect, store, or intermediate Claude.ai credentials or session tokens — sign-in to a Claude account must complete through Anthropic's own flow. |
| https://code.claude.com/docs/en/legal-and-compliance, Authentication and credential use | Nor does it prevent an end user from signing in to the unmodified Claude Code binary with their own Claude subscription, including where a platform hosts Claude Code as described under *Can customers offer Claude Code in their products?* above. |
| https://code.claude.com/docs/en/legal-and-compliance, Authentication and credential use | Anthropic reserves the right to take measures to enforce these restrictions and may do so without prior notice. |
| https://code.claude.com/docs/en/legal-and-compliance, Can customers offer Claude Code in their products? | **The Claude Code binary must not be modified.** Claude Code must be installed and run as published by Anthropic, and customers may not remove, disable, or restrict any authentication method built into it (including methods that permit signing in with a Claude account or the user's own API key). |
| https://code.claude.com/docs/en/legal-and-compliance, Can customers offer Claude Code in their products? | **Customers may not pay for, resell, or intermediate Claude usage on their end users' behalf.** Each end user must authenticate with their own Anthropic API key, Claude subscription plan credentials, or 3P inference provider credential |
| https://code.claude.com/docs/en/legal-and-compliance, Acceptable use | Advertised usage limits for Pro, Max, and Ultra plans assume ordinary, individual usage of Claude Code and the Agent SDK. |
| https://code.claude.com/docs/en/agent-sdk/overview | Unless previously approved, Anthropic does not allow third party developers to offer claude.ai login or rate limits for their products, including agents built on the Claude Agent SDK. Use the API key authentication methods described in the Quickstart instead. |
| https://code.claude.com/docs/en/llm-gateway | a saved claude.ai login remains the active credential |
| https://code.claude.com/docs/en/llm-gateway | Anthropic doesn't endorse, maintain, or audit third-party gateway products, and doesn't support routing Claude Code to non-Claude models through any gateway. |
| https://www.anthropic.com/legal/consumer-terms, §3, effective Oct 8, 2025 | Except when you are accessing our Services via an Anthropic API Key or where we otherwise explicitly permit it, to access the Services through automated or non-human means, whether through a bot, script, or otherwise. |
| https://www.anthropic.com/legal/consumer-terms, §3, effective Oct 8, 2025 | To develop any products or services that compete with our Services, including to develop or train any artificial intelligence or machine learning algorithms or models or resell the Services. |
| https://www.anthropic.com/legal/commercial-terms, D.4, effective Jun 17, 2025 | Customer may not and must not attempt to (a) access the Services to build a competing product or service, including to train competing AI models or resell the Services except as expressly approved by Anthropic; (b) reverse engineer or duplicate the Services |
| https://learn.chatgpt.com/docs/auth/ci-cd-auth.md | The right way to authenticate automation is with an API key |
| https://developers.openai.com/codex/auth | Don't expose Codex execution in untrusted or public environments |

OpenAI's Terms pages returned 403. What we hold on them comes from search snippets, one marked as a previous version, and is
unverified, so it is not quoted here. The docs state no general rule for third-party tools. Spawning the user's own `codex` under
its own login rests on a reading of the docs: app-server and the SDK are published for this, and the user's process holds the credential.

**Open reading.** The docs describe `claude -p` for scripts, and the Consumer Terms allow automation "where we otherwise explicitly
permit it". "Ordinary, individual usage" is undefined, so a swarm on one login may exceed it. That is why headless multi-agent on a
plan login needs an explicit opt-in, and why we recommend an API key for teams, unattended runs and anything hosted.

## 8. Known unknowns

**Blocked on the owner.**

- Prime Agent: approve a live probe or leave it unclaimed.
- Training through Claude Code against a non-Claude policy: its system prompt and tool descriptions would enter datasets. Blocked until decided.
- DAO is undefined. Scenario 2 implements only the brief's table row.

**Terms and licenses.**

- OpenAI Terms clauses need review from a direct source.
- `lmnr-claude-code-proxy` is proprietary and installed by default. Excluding it is untested.
- `claude-stream-sample.jsonl` holds short strings authored by a proprietary CLI. Review before the repository goes public.
- Concurrency of one plan login across many processes is unknown for both Claude Code and Codex.

**Harness behavior not measured.**

- Stronger models and long tasks: parking used cheap models, low effort and an instruction to stop.
- A natural overrun past `wait`: no model ignored it unprompted, so the spike's proposed interrupt trigger never met one. The design leaves the wait open instead.
- Long parks: nothing parked beyond seconds. Cache cost after expiry, long blocking `wait` calls and client tool timeouts are untested.
- Fallback, cold resume, token exclusion, slow init and shell socket are 1 trial each.
- Several agents in one `codex app-server`, with distinct tokens.
- Codex child agents on a real model. Real v2 subagent flow may differ from the stub.
- Unix sockets from the Codex sandboxed shell, the `read-only` sandbox, and blocked user namespaces.
- `omit_tools_from` durability: under-development `code_mode_only_strict_3p_tools` ignores it, and the model catalog is served remotely, so a live first-turn check belongs in conformance.
- Why `accept` gave two outcomes on identical Codex input.
- Whether `thread/resume` restores thread-level `config`. We resend it.
- `--bare` becoming the default for `claude -p`: announced with no version, and it stops reading a native login.
- Auto compaction, nested subagents, parallel tool batches and crash recovery on Claude Code.
- Successful compaction on OpenCode and pi, so provenance across compaction is unconfirmed on both.
- OpenCode: `mcpServers` precedence, repeated prompt `id` retry semantics, and the empty experimental log replay.
- Our HTTP tools server against OpenHands, pi and OpenCode. Only Claude Code and Codex have met it. The other probes used stdio servers.
- Delivery through `claude-agent-acp` and `codex-acp` past `initialize`, including resume, permissions, `mcpServers`, `env` leak behavior and steering.
- Whether adapter `toolCallId` equals the model tool id, and whether native-subagent MCP calls carry a usable anchor.
- OpenHands: condenser, delegation and long runs through the gateway. `task` under `arun()` may delay `send_message`. Memory at 100 agents, given 210 MB RSS at import.

**Training path.**

- Hidden calls: any unlabelled side call trains as `policy`. Platoon's classifier is unbuilt.
- `rollout_isolation: process`, mint over a Unix socket, and mint through a sandbox route.
- Prefix merging across compaction, and with a real model's renderer: both tool probes diverged under the toy tokenizer.
- `platoon.sandbox`, `platoon.extensions` and `/v1/platoon/agents` carry no stated stability promise. Experimental credit APIs may change in a minor release.
- The OpenHands pin: Platoon's 1.54.0.post1 or the probed 1.59.0.

**Platform and scale.**

- macOS: nothing has run. `F_FULLFSYNC` latency decides the journal's ack promise there.
- Power loss, devices that ignore flush, and NFS, CIFS, GPFS or BeeGFS. Lustre with two hosts did not corrupt in short runs, but that is not evidence of safety, and it stalled up to 6.4 s.
- Many sessions in one process, lagging followers at scale, payloads above 4 KiB, and soak beyond 60 s.
- Real terminal throughput over SSH and tmux, and accessibility on an alternate screen.
- Shell-capable agents at one UID can read each other's tokens through `/proc`. Whether Codex's sandbox blocks that read is unknown.
