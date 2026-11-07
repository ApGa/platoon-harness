# Compatibility

What each upstream is, how we use it, and what is known about it. Everything here was inspected or measured on 2026-11-02.
These are **upstream facts**, not claims about our drivers. Each driver records its own verified result in the status list of
section 3 as it lands, and a result pins to the driver, the harness version, the SDK and the host (architecture §9.3).

Detail and citations live in [research/](../research/README.md). Where a report and a spike disagree, the spike wins because
it was measured later. The critic's corrections in the research index are authoritative. Section 3 lists what changed.

## 1. Upstreams

**IMPLEMENTED** is code on the default branch. **EXPERIMENTAL** is shipped and labelled unstable. **DRAFT** is a proposal with
no code. **DOCUMENTED-ONLY** has no code to read.

| Upstream | Inspected | License and constraint | How we use it | IMPLEMENTED versus DRAFT | Most important fact |
|---|---|---|---|---|---|
| Platoon | `efe3b277c82c`, 0.5.0 | MIT AND Apache-2.0 (tool parsers). Optional extension; keep its NOTICE if parser code is ever copied | Training authority through an extension, pinned `>=0.5,<0.6` | IMPLEMENTED: gateway, child mint, trajectories, env forks, extensions. EXPERIMENTAL: credit, policies, Responses and Messages dialects. DRAFT: `AgentGraph`, `RewardEvent`, attribution levels, native selectors, `bus` | The only exact identity for an external agent is one key per agent, from `POST /v1/platoon/agents` |
| SwarmChat | `fb5aa6a05b40`, PyPI 0.1.0 | MIT. Its notice heads each of its scripts we serve. Exact pin, `swarmchat==0.1.0` in the CLI package | Second client: its five page files, each held to its SHA-256, over our own backend, from `platoon-harness web`, with an overlay of ours that acts through `/x/command`. Its server never runs | IMPLEMENTED: server, agent API and a read-only viewer. No composer exists or is documented. Nothing DRAFT | Messages have no idempotency key, no metadata and no caller ids, so a projection into its server cannot be idempotent |
| Toad | `dd4f90e8b370`, 0.6.20 | AGPL-3.0. Ideas only: no code, no dependency. Its `textual-diff-view` is AGPL too | Interaction reference | IMPLEMENTED: own ACP v1 client. Nothing DRAFT | Copying is ruled out by license, not merely unnecessary |
| OpenHands | SDK `988494576218`, wheels 1.59.0. CLI `283c6ac3610f`, `openhands` 1.16.0 | MIT. The SDK requires proprietary `lmnr-claude-code-proxy` 0.2.0 through `lmnr`: the worker runs without it, the workspace lock excludes it, and the extra installed from an index brings it in unless excluded | Wire worker on SDK `arun()`, from the SDK's `openhands` extra | IMPLEMENTED: SDK, agent server, `openhands acp`. Docs list `--streaming`, absent from CLI 1.16.0 | Passed the exact path on a minted key. Cannot share an environment with `mcp` 2.3.0 or ACP 1.0.0rc3, and the CLI pins SDK 1.28.1 |
| Codex | `05c08d765523`, CLI 0.164.0 probed (latest stable 0.166.0), and 0.167.0 on 2026-11-06. Spike source read at tag commit `6aaac6948030` | Apache-2.0 with NOTICE. User-installed. Never read or copy `auth.json` | `codex app-server` over stdio, no `experimentalApi` | IMPLEMENTED in behavior, labelled Experimental upstream. `codex mcp-server` is removed. `turn/steer`, `thread/fork`, `thread/inject_items` are on the stable handshake | The model reaches MCP tools only from inside a Code Mode script, so `omit_tools_from: ["deferred"]` is required |
| Claude Code | `f0b737f94f3b` (changelog and examples only), CLI 2.1.316 probed, Agent SDK `2146f9d89855` | Proprietary. Never bundle, vendor or patch. Agent SDK wheels bundle the CLI: no default dependency, no re-hosting | `claude -p` stream-json with the control protocol on the user's own binary | IMPLEMENTED. Undocumented: `--permission-prompt-tool stdio`, `command_lifecycle`. EXPERIMENTAL: agent teams, which do not run in `-p` | `ANTHROPIC_BASE_URL` alone keeps a saved login active, so it is never set without a gateway credential |
| OpenCode | `ff90ed91607c`, 2.2.5 (`@opencode/cli`; `opencode-ai` stops at 1.19.5) | MIT. User-installed | Generic ACP driver first. An HTTP driver is a later option | IMPLEMENTED: `opencode acp`, `opencode serve`. Its `/api` spec calls itself experimental. `/api/experimental/*` is EXPERIMENTAL | With no model set, prompts go to a hosted free model, with no credentials configured |
| pi | `c9f4c7b9fcd0`, 1.4.0. Driver built on 1.5.0, source and binary | MIT. User-installed | `pi --mode rpc` | IMPLEMENTED: RPC, first-party MCP, extensions. No ACP in the repository | Passed the full trainable path on a minted key, and native spawning does not exist to reconcile |
| Prime Agent | `c6d4da9421e6`, 0.10.2 | MIT, tarball adds `PHOTON-LICENSE.md`. User-installed. Not on npm or PyPI | After a live probe: `--mode rpc` or ACP | IMPLEMENTED per source. EXPERIMENTAL: Factory. Nothing beyond version and help has run | No capability claim can be made: no model turn was run |
| ACP | Spec `212f0cace08a`, schema 1.29.0. Python SDK `9853d8b514d6`, 0.12.1 and 1.0.0rc3 | Apache-2.0. Wheels have no License field, so scanners may flag them. Never bundle the Claude or Codex adapters | Generic driver, protocol 1 | IMPLEMENTED: v1 stable. EXPERIMENTAL: `session/fork`, `subagent_update`, `providers/*`, `mcp/message` and more. DRAFT: v2 | Stable v1 has no mid-turn message, sender identity, idempotent prompt or model-call attribution |
| MCP | Spec `d0e246ea3c69`, revision 2026-07-28. Python SDK `d7845c073a2b`, 2.3.0 | Spec Apache-2.0, MIT in transition, docs CC-BY-4.0: attribute quoted docs. Python SDK MIT | Tool plane, through our own stdlib server | IMPLEMENTED: revision 2026-07-28 is current. `draft` has no changes | Real clients settle on older revisions: Codex `2025-06-18`, Claude Code `2025-11-25` |
| DeLM | `66617616e708` | MIT. Pattern only, credit in docs | Pattern reference | IMPLEMENTED: research runner. Read, not executed | State is a fold over one append-only events table, and a claim is one `BEGIN IMMEDIATE` transaction |
| Agensh | `d6063b9086d5` | MIT. Pattern only, credit in docs | Pattern reference | IMPLEMENTED: research harness on Docker Compose. Read, not executed | Mid-turn notices are appended to tool results, which needs no harness patch. Its `CLAIM` is advisory |
| GitSwarm | Site `9f66af0b919f`, arXiv 2610.04862v1 | No license in the repository. Paper CC BY 4.0 per PDF metadata, unconfirmed. Pattern reference by owner permission: write our own code, credit it | Pattern reference | DOCUMENTED-ONLY: the repository is a website, not the system | `informed_by` is declared, not causal. That is the split our evidence types keep |

**Starting observations from brief section 2:**

| Observation | Verdict | Note |
|---|---|---|
| [Platoon RFC 0021](https://github.com/ApGa/platoon/blob/efe3b277c82c/docs/rfcs/0021-trainers-credit-and-policies.md)'s `CreditEstimator` partly supersedes [Platoon RFC 0001](https://github.com/ApGa/platoon/blob/efe3b277c82c/docs/rfcs/0001-native-multi-agent.md)'s credit section, with per-token advantages | **Verified** | EXPERIMENTAL. [Platoon RFC 0021](https://github.com/ApGa/platoon/blob/efe3b277c82c/docs/rfcs/0021-trainers-credit-and-policies.md)'s header still says "Implementation: None yet", so the code is what counts. Only `reverse_kl` uses per-token advantages |
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
  with `mcp==2.3.0` or `agent-client-protocol==1.0.0rc3`, and unpinned it resolves silently to 1.49.1 and 1.44.1. The SDK's
  `openhands` extra pins it and `openhands-tools` exactly, so an environment with the extra holds OpenHands' pins, and one that
  cannot runs the worker from an environment of its own, as a wire command. `litellm`, which the worker imports too, is not
  pinned: it floats in the range `openhands-sdk` asks, `>=1.93.0,<1.106`, and every test here ran on 1.105.7. The effort refusal
  reads the catalog of whichever is installed, the one that would drop the field. The workspace's one lock holds the extra beside the
  rest, which moved `filelock` from 4.2.6 to 3.32.7, a package the core reaches only through `pre-commit` in its dev group, and
  leaves out `lmnr-claude-code-proxy`, which the extra installed from an index brings in unless excluded, as uv's `--excludes`
  does. The planned `[acp]` extra's `agent-client-protocol` 1.0.0rc3 cannot share that lock with the SDK's 0.12.1, so when that
  extra lands, no one environment holds both.
- **Harness versions.** Exact, user-installed, shown by `doctor`, checked on this machine by `doctor --check`, which keeps what it
  found for the version it ran on, under that SDK on that host, and recorded from `ready` on `agent.started` and `agent.resumed`, with
  that result when it speaks for the harness that runs. Adapters seen:
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
| **claude** 2.1.316 | yes. `claude -p` stream-json, stdin held open. User installs and logs in [R] | yes. Subagents gave no partial events; `assistant` output tokens are a placeholder [R] | yes. HTTP MCP, needs `alwaysLoad` or tools defer. `system/init` does not prove visibility [R] [L] | yes. Stdin across turns [R]; absorbed at a tool boundary or next turn [L] | yes. Receipt in 22 ms; the aborted call's tokens go unrecorded [R] | yes. `can_use_tool`; `stdio` value is SDK-private; read-only commands skip it [R] [L] | yes. `--resume`, 1 cold trial; needs a persisted transcript [R] | partial. Observed, identity `inferred` [R]. Agent teams add no tool in `-p` [L] | partial. Base URL plus credential [L]. Non-Claude models unsupported upstream [S] | partial. `toolUseId` equals the model id [R]. Native: none. Gateway join exists but no call records [L] | **no.** Gateway run exits 1 with zero records; terms await an owner decision [L] |
| **codex** 0.164.0 | yes. `codex app-server`, labelled Experimental upstream [R] | yes. `item/*`, deltas; `item/completed` is truth [R] | yes. Per thread, needs `omit_tools_from` and an approve mode [R] | yes. `turn/start`, `turn/steer` with `expectedTurnId`; next model call [R] | partial. `turn/interrupt` [R]; running children continue [L] | yes. Server requests [L]. Set `approvalsReviewer`; `accept` does not fix the outcome [R] [L] | yes. `thread/resume`, 1 cold trial; resend config [R] | partial. v1 and v2 observed, identity `inferred`, no `thread/started` for a child [L] | yes. `model_providers`; `responses` only. Thread scoped at 0.164.0; from 0.167.0 a thread runs on its app-server's provider alone [L] | partial. Thread and turn only on stable. `callId` joins to the `exec` script, not a call [R]. Exact per key at a gateway [L] | **no.** Identity passes, but MCP tools never reach the policy [L] |
| **pi** 1.4.0 | yes. `pi --mode rpc`; Node >= 22.19 [L] | yes. `message_end` is authoritative; a stalled reader stalls pi [L] | yes. MCP with `exposure: direct`, on a stdio server, and over HTTP on our real tool server at 1.4.0 and 1.5.0 [L] | yes. `prompt`, `steer`, `follow_up`; turn boundaries [L] | yes. `abort`, then `agent_settled {aborted: true}` [L] | partial. None native. A probe gate worked; we would ship one. Not a security boundary [L] | yes. `--session <id>` with full history [L] | no. None by design; extensions can add them [S] | yes. `models.json`, one agent dir per agent [L] | partial. Agent level by key. `message_end` carries the model's `responseId` over RPC, at 1.4.0 and 1.5.0, on a fake model. No MCP anchor [L] | candidate. Full path passed on a minted key. Platoon has no pi spec [L] |
| **openhands** SDK 1.59.0 | yes. SDK `Conversation` under `arun()`; import 8-11 s on network storage, 10 s on local disk. The wire worker drives it [L] | yes. Needs `stream=True` and a token callback; children never stream [L] | yes. MCP per `Agent`, tool in the prompt, on a stdio server, our shim among them. HTTP with a bearer in `headers` worked on FakeTools in a probe. A failed start is silent [L] | yes. `send_message`, next model request; log order misleads [L] | yes. `interrupt()` abandons the call in 0.05 s; a gateway may have recorded it [L] | partial. Confirmation policies. No pending event; lone `finish` and `think` skip it [L] | yes. Same id, fresh `Agent`. Key resupplied; tools cannot be removed [L] | partial. `task`, opt-in. No child events reach the parent [L] | yes. `LLM(...)`; unrequested fields sent [L] | yes. `llm_response_id == call_id` per action on a scoped key. A native child is exact only with a keyed factory. Extra calls share the endpoint [L] | **yes, on a profile.** Exact records and datums on a minted child, SDK 1.59.0 and a scripted policy. Platoon's own 1.54.0 spec has no MCP, and its live test did not run. Condenser, delegation and long runs untested [L] |
| **opencode** 2.2.5 via ACP | yes. `opencode acp`, private server per process [L] | partial. `session/update`; less detail than HTTP [L] | partial. `mcpServers` landed behind Code Mode, even with `codemode: false` in config [L] | partial. Turn boundary. A second prompt fails -32603 [L] | yes. `session/cancel`, stop reason `cancelled` [L] | partial. `session/request_permission`, only under an `ask` rule. No rule, no ask [L] | unverified. Advertised, not exercised over ACP [L] | partial. Child sessions seen on HTTP [L]; ACP updates need opt-in [S] | yes. `OPENCODE_CONFIG_CONTENT`; reaches the tool shell. Always pin a model [L] | partial. Session level by header, one credential per process; title calls unlabelled [L] | unknown. Untested through the gateway. Title calls would train as `policy` [U] |
| **prime** 0.10.2 | unverified. Version and help ran; no model turn. Needs `uv` and Python [S] | unverified [S] | unverified. Through the Python REPL [S] | unverified. `steer`, `follow_up` on RPC [S] | unverified. Children and kernels must stop too [S] | no. None in the crates [S] | unverified. CLI only in source; ACP `load_session: false` [S] | unverified. `rlm.spawn`, reported by the harness [S] | unverified. `models.json` [S] | unknown. No parent header found; kernel calls unknown [U] | unknown. No live probe [U] |
| **generic ACP**, protocol 1 | yes. Baseline required of every agent [S]; SDK checked on a fake agent [L] | partial. 14 stable update kinds; the SDK drops unknown ones [S] [L] | unverified. `mcpServers`, stdio mandatory. Visibility varies by agent [S] | unverified. Next turn. A second prompt mid-turn is undefined [S] | unverified. `session/cancel` is baseline. `openhands acp` maps it to `pause()` [S] | unverified. `session/request_permission` is a baseline client method. Whether an agent asks is per agent [S] | unverified. Only if advertised [S] | no. Stable has none; `subagent_update` is unstable [S] | no. `providers/*` is unstable [S] | no. `toolCallId` only [S] | no. Only through a gateway, per agent [S] |
| **generic exec**, one-shot | unknown. Any command; `exec` driver is planned [U] | unknown. Stdout only, no structured events [U] | unknown. `ph` on `PATH`; a sandbox may block it [U] | no. No input after launch; cannot park [S] | unknown. Process group only [U] | unknown. No answer path in the design [U] | unknown. Depends on the command [U] | unknown. Opaque [U] | unknown. Whatever the command accepts [U] | unverified. Exact only if it uses its own key alone [S] | unknown. Per command; Platoon admits a custom agent on its own key [S] |

### Driver status

A driver fills in its row when `check_driver` passes, with the result pinned to the harness version. A cell above is never upgraded
by a driver landing; only the row below changes.

| Driver | Path | Depends on | Driver status | Conformance result |
|---|---|---|---|---|
| `claude` | Stream-json plus control protocol | User's binary | implemented | 2.1.319 on FakeModel: 26 passed, 0 failed, 4 skipped (`one_shot_exits`: it is persistent; `sealed_first_request_holds_only_ours` and `environment_tools_in_first_request`: it declares no sealed launch; `declared_but_unproven`: no check proves `coverage`). Operational and observable met. It passed on 2.1.316 and 2.1.318 before |
| `codex` | `codex app-server` over stdio | User's binary | implemented | 0.167.0 on FakeModel: 25 passed, 0 failed, 5 skipped (`call_ids_reported`: it has no id per model call; `one_shot_exits`: it is persistent; `sealed_first_request_holds_only_ours` and `environment_tools_in_first_request`: it declares no sealed launch; `declared_but_unproven`: no check proves `tool_timeout_s`, `coverage` or `sandboxes`). Operational and observable met. It passed on 0.164.0 before, and still does |
| `pi` | `pi --mode rpc` | User's install | implemented | 1.5.0 on FakeModel: 26 passed, 0 failed, 4 skipped (`native_children_off_by_default` and `native_child_seen`: it has none by design; `one_shot_exits`: it is persistent; `declared_but_unproven`: no check proves `tool_timeout_s` or `coverage`). Operational and observable met, and trainable on a gateway login, from its sealed checks on FakeModel acting as a gateway. No live model has run: pi has no login on the machine that ran this |
| `openhands` | `WireDriver`, worker `python -P -m platoon_harness.drivers.openhands` on SDK `arun()` | `[openhands]` extra | implemented | 1.59.0 on FakeModel: 26 passed, 0 failed, 4 skipped (`tool_item_carries_its_anchor`: it sends no anchor; `native_child_seen`: its native children are opaque, and `tests/integration/test_openhands.py` holds an allowed child to the runtime's approvals; `one_shot_exits`: it is persistent; `declared_but_unproven`: no check proves `tool_timeout_s` or `coverage`). Operational and observable met, and trainable on a gateway login, from its sealed checks on FakeModel acting as a gateway; never for a role that allows its own agents, as they are opaque. No live model has run: no OpenHands login or provider key is on the machine that ran this |
| ACP, covering `opencode` | Generic driver, protocol 1 | `[acp]` extra | planned | none |
| `prime` | Decided after a live probe | User's install | planned | none |
| `exec` | One-shot command, `ph` only | Nothing | planned | none |

### Evidence

**claude, CLI 2.1.316.** [Report](../research/adapter-claude-code.md), [spike](../research/spikes/tools-and-parking.md),
[fixture](../research/fixtures/claude-stream-sample.jsonl).

- Real model: 5 turns with `haiku` in one process (multi-turn, one subagent, interrupt, MCP approval), then 14 spike turns with `claude-haiku-5-5`.
- Loopback: the real CLI against a scripted Messages server. `Bash(echo *)` ask rule, mid-Bash message, `/compact`, `--resume`, `--fork-session`.
- Visibility: tool search defers MCP tools. `alwaysLoad` or `ENABLE_TOOL_SEARCH=false` put the tool in the first request. Live runs made 0 `ToolSearch` uses in 28 messages, but that request body was not inspected.
- Stream usage: `model_usage_since_last_result` gives the tree's delta (undocumented). Interrupted calls record nothing.
- Fallback trial: after `interrupt` and stop, the process exits 1. Treat that as normal. In the earlier probe, after `interrupt` alone, the same process took the next turn.
- Background: in `-p` a subagent started in the background and a later notification opened an extra turn, so `result` is not one per user message. `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1` is the driver's setting. Loopback. With it, `run_in_background` on `Agent` still ran in the foreground, `is_backgrounded: false`, and `Bash` refused the parameter [L].
- Approvals: `can_use_tool` ran in the report, with `--permission-prompt-tool stdio`. The spike's launch did not use that flag and set `--permission-prompts none`, which denies anything that would prompt, so that launch has no approval path. The driver uses the flag, and every approval goes through the runtime.
- Floors: 2.1.259 for `--permission-prompts`, 2.1.273 for hint headers, 2.1.283 for prompt id.
- The driver on 2.1.316, on FakeModel [L] and then on `claude-haiku-5-5` with a plan login [R]. `system/init` comes only with a turn, so `ready` is `initialize`, `get_settings` and `mcp_status`, which call no model. `get_settings.applied.model` is the resolved model, so `--model haiku` reads `claude-haiku-5-5` and the host refuses it against a role that pins `haiku`: name the model in full. `--append-system-prompt-file` works and is not in `--help`. After `--resume` a session sends the text it began with, whatever the file holds then [L]. `--include-partial-messages` is needed for deltas and for true output tokens, and is not in the spike's launch.
- An unknown `--effort` is a warning on stderr, and the run goes on at the default, so the driver compares `applied.effort` and refuses.
- `command_lifecycle` runs `queued`, `started`, then `completed` or `cancelled`. A message sent during a tool is `started` after its `tool_result` in the same turn, with both uuids on the next `system/status`. Sent during a last model call, it begins the next turn. A uuid already in the transcript answers `completed` and starts nothing.
- A `result` can say `is_error: true` with `subtype: success`: `Not logged in · Please run /login` does, under an `assistant` frame of model `<synthetic>` whose id is no model call's.
- A request cut off before it streams leaves no `message_start`, so only `system/status: requesting` shows it. Usage is `{}` and cost 0, which means unknown. A live interrupt met this.
- A stream the harness aborts closes with a `message_delta` of its own, whose `stop_reason` is null and whose counts are the placeholder from `message_start`. Read as a measurement it undercounts: a live interrupt showed that, so the driver takes only one with a stop reason [R].
- An interrupt as a handover begins a turn cut that turn, and it read `interrupted` on each harness, through a session too [L].
- A frame of a known type with a shape nobody expected, a null usage part or a lone surrogate among them, is a `native` frame and a gap, and the turn goes on. On a stand-in so far, and in the first-party API's frames the parts were integers [L] [R].
- Interrupt: `still_queued` names inputs left in the queue, and the first begins a new turn by itself. `cancel_queued: true` moves them to `cancelled` before the interrupt is answered, which is what the driver sends, as the runtime offers them again. An approval pending at an interrupt gets `control_cancel_request`.
- Stop: an interrupt then end of stdin exits 1 and ends a running `Bash` in 1.3 s, and `SIGTERM` to the group exits 143 in the same time. End of stdin alone waits for the tool. `SIGKILL` of the group leaves the tool alive, in a group of its own, 1 trial each [L]. A tool's `&`, `nohup` and `setsid` children outlived `stop` with no gap, and each carried the agent's own `TMPDIR`, by which `Process` now ends them [L].
- Resume with a dangling tool call: the next request holds a synthetic error `tool_result`, `[Tool call interrupted: the session ended before this call's result was recorded, so its outcome is unknown...]`, then `No response requested.` That agrees with our cut-off notice (1 trial) [L]. A harness whose runtime was killed outlives it, so on a real model the transcript held a true result instead: `Exit code 137` when a resume reaped it, and `(Bash completed with no output)` when it was left alone, 3 trials [R].
- A killed runtime leaves the harness running: with stdin gone it finishes its turn, here a tool and a model call no journal saw, and exits 18 s later. A resume reaps it, and its tool, at once. The cut-off notice held on it in 3 of 3 runtime kills and 1 owner's stop: the model read the file and did not repeat the command [R].
- `kill -9` of the harness alone leaves a running `Bash` going, in a group of its own, past the end of the agent and of the session, so its agent's `crash_window` is what says so. `--resume` of that session worked, during a tool and between turns, 1 trial each [R].
- A harness that exits on its own rests its agent, and its next handover resumes it (architecture section 7). Killed during a tool,
  `--resume` brought it back told, in run 77 [R], and the `rest` effect ended the `Bash` it left, its group gone by the time the effect
  finished [L]. Killed in its first turn, `--resume` answered `No conversation found` in most kills here, during a model call or a call
  of ours, on FakeModel [L] and in run 76 [R], as it had not written its conversation down, though the journal held the turn it began.
  That relaunch exits before it is ready, with code 1, which is its second exit on its own, so its agent is lost there, saying why,
  in run 81 [R] and on FakeModel [L].
- Native children: `task_started` carries `task_id` and the `tool_use_id` of the `Agent` call, and with background tasks off a child ends before that call's `tool_result`, so an open turn covers it and `child.seen` needs no end. That held on a real model, 2 trials: `session.status` said `open_turn` throughout, an interrupt ended the turn in 0.2 s and the child's shell tool 0.3 s later, and a real child sends `system/task_progress`, which a fake one did not. A child's approval reaches the runtime on the parent's stream, and its outcome is unread, since a child's frames are dropped [R]. Its spend reaches us only in `model_usage_since_last_result`, so `ChildSeen` comes with the gap `native_child_unattributed`. A `task_started` with `is_backgrounded: true` is reported as an unknown frame. `--forward-subagent-text` is not passed, so a child's text is not seen [L].
- Compaction: `system/status: compacting`, `compact_boundary` naming only what was kept, then a `user` frame with `isSynthetic: true` holding the summary. It has no `message_start`, so its model call has no id, and its tokens reach us only in `model_usage_since_last_result`. `/compact` ran; auto compaction was not probed [L].
- A rejected tool token leaves `mcp_status` at `failed`, and the tool is not offered, so that fails the start, and no model call is made. `ready.tools_visible` stays unknown: a connected server proves no model saw a tool [L].
- Its own agents, off unless a role allows them: `Agent` and `Workflow` start them, and `ListAgents` and `SendMessage` reach them,
  and other Claude sessions on the machine too. The four are disallowed, and the first request offers none, `SendMessage` among
  the deferred tools included, and lists no agent types. Agent teams, on in a user's settings or the environment, added no tool to
  the first request in `-p` [L]. Asked to hand a search to a sub-agent of its own, a live model started none, and did the search [R].
- A launch with `--permission-prompt-tool` adds `AskUserQuestion` to what `-p` shows, 13 tools to 12. Allowed, the model reads `The user did not answer the questions.`, so a person would have approved a question and never seen it. It is disallowed, and a request shows the same 12 [L].
- `permissions.defaultMode` of `acceptEdits` or `bypassPermissions` in a user's settings ran a `Bash` with no approval asked, so a role's `deny` did not hold. `--permission-mode default` took both back to asking, 1 trial each [L].
- Inline `--mcp-config` JSON expands `${PLATOON_HARNESS_TOKEN}` from the harness's environment, so the token is in no file and not in argv [L] [R].
- The transcript is internal, and the driver reads it for one thing: whether an input's uuid is on a line, to `reconcile` after a crash. A miss says `unknown`. On a native login it is also the one place a live test can read a request: all of a session's requests shared one `api-request-shape`, across a resume too [R].
- Real teams, in [the spike](../research/spikes/real-harness.md): a lead and two workers fixed a seeded bug through the queue and a board and settled, in 25 calls and 28.5 s, and a lead with a Codex worker in 22 and 23 calls. `ready` took 1.2 s at the median and 1.4 s at worst, and a handover 0.03 s to begin a turn, or up to 0.8 s as a process's first [R].
- The mixed-team example, from SwarmChat's page with the terminal UI attached: as the lead it added the task, spawned a
  Codex worker, read the worker's note when its report came and finished citing it, in 6 calls of the run's 11, run 80 [R].
- The live run: a goal, `board_post` called directly with no `ToolSearch`, its `toolUseId` matching the item, a delivery, an interrupt, an approval, and a resume by a new process, with the preamble once in every request and no unknown frame, in the user's own setup, at 7 model calls. Getting there took 20 calls over four runs [R]. It passed again on the launch of now, in run 19, at 7 calls: our tool reached through `--mcp-config` naming the token's variable, the approval asked under `--permission-mode default`, and the interrupt that dropped the queue read `interrupted` [R].
- A child that stays: a lead spawned one with `stays`, gave it a follow-up task and a question, each once the last was answered, and
  retired it, on one helper process, in 13 calls, twice, runs 22 and 25. Each answer reached the lead at the end of the helper's turn,
  which it took as a wake or through a held `wait` with `from`. No woken turn, of 20 this stage, opened with a `message_read` that
  showed nothing new [R]. It passed again in runs 35 and 39, in 15 and 14 calls, the second on steps worded in an order no reading
  can mistake, and none of 17 woken turns in runs 34 to 39 opened with such a read [R].
- What a client reads: a follower of live text was shown the start of the message item it became, a child spawned through our tool
  carries as its spawn's anchor the `native_id` of the tool item of its call, and an interrupt under a stop below reached a child [L]. An
  interrupt during a call under a `tokens` limit charged the cut turn its estimate, labelled `estimated`, and the session went on,
  on FakeModel [L] and on `claude-haiku-5-5` in run 44, in 2 calls [R].
- From the command line: one `platoon-harness run` on FakeModel settled, and one stopped mid-turn by `session stop` was resumed by
  `session resume`, took the cut-off notice and settled [L]. On `claude-haiku-5-5`, as the lead `init` wrote, it took
  the job on stdin and a person's message from a second process, and settled with a Codex worker in 20 calls, run 41. Stopped by
  `session stop` during `sleep 20`, it was resumed with the text it was told at launch, journaled again whole, read the cut-off notice,
  checked, found the file unwritten and ran the command once more, in 6 calls, run 40 [R].

**codex, CLI 0.164.0, and 0.167.0 where a line says so.** [Report](../research/adapter-codex.md), [spike](../research/spikes/tools-and-parking.md),
[fixture](../research/fixtures/codex-appserver-sample.jsonl).

- Real model: 3 report turns, then 24 spike turns with `gpt-6-luna`. Client approval, subagents and interrupt scope came from the stub.
- Tool found by the model: default 6 of 7 threads, each needing a discovery call. With `omit_tools_from: ["deferred"]`, 8 of 8.
- `approvalPolicy: never` fails MCP calls closed unless `default_tools_approval_mode` is `approve`.
- `accept` is not an outcome: 29 of 48 accepted commands ran and 19 failed with EROFS on identical input, cause not established.
- Stable usage has no response id. `rawResponse/completed` has one but is internal-only. Interrupted calls report nothing, so a turn that stopped short reports a call `unavailable`, which a budget charges its estimate, as on Claude Code and pi. Under a `tokens` limit an interrupt during a call left the session to go on, on FakeModel [L] and on `gpt-6-luna` in run 45, where the cut call never reached the journal, as no frame says a call began [R].
- `bearer_token_env_var` reaches the agent shell unless `shell_environment_policy.exclude` names it (1 trial).
- A provider: on 0.164.0 a thread runs on the one `thread/start` names, and a resume by an app-server without that provider went
  on under `openai`, its turn never reaching the URL the thread began on. From 0.167.0 a thread runs on the provider its app-server
  started on alone: a turn of a thread given another is refused, `modelProviderMismatch`, "This chat uses platoon-harness, but
  your current provider is openai", and a resume by an app-server without the thread's provider is refused,
  `modelProviderNotConfigured`. So the driver names a provider of the agent's own with `-c` as the app-server starts, and the
  thread gives it its URL, as a dotted key, since a table there would have to be a whole provider; both versions run that [L].
- The driver on 0.164.0, on FakeModel [L] and then on `gpt-6-luna` at low effort with a plan login [R]. `thread/start` answers with the effective model, effort and version, and calls no model. A thread has no rollout until its first turn, so one that took no turn cannot resume: `no rollout found`. `claude --resume` says the same of a session that took no turn, so the runtime starts such an agent anew, on either, and it took a message after an owner's stop and a resume [L].
- The driver on 0.167.0, on FakeModel [L] and on `gpt-6-luna` at low effort with a plan login: an approval through the
  runtime, then a resume by a new process that answered from what came before, in 4 calls with no unknown frame, run 82 [R].
  The stable schema `generate-json-schema` gives grew by nothing else the driver meets: data on a provider's refusal,
  `thread/section/changed` for sections the driver never moves a thread into, `startedAtMs` and `completedAtMs` on items, a
  `generationId` on a generated image, and input by URL or file id. Its client requests are the same 106, and `--help`,
  `app-server --help` and `codex login status` say what they said, but for one line about `agents` [L].
- `developerInstructions` replaces the user's `developer_instructions`, and `shell_environment_policy.exclude` replaces theirs, which let a variable they excluded reach the shell. `config/read` gives both, and the driver keeps them. A project's `AGENTS.md` reached the model beside ours [L].
- `thread/resume` keeps the `developerInstructions` and the `agents.enabled` a thread began with, whatever it is sent: a thread begun with its own agents off had none after a resume that turned them on, and one begun with them on kept them [L].
- `turn/start` on a turn under way steers it, returning that turn's id, so `turn/steer` and its "no active turn" race are not needed. A steer sent during a stalled model call ended that call: its text and usage never came, and the input was in the next one. Whether a call was cut or had finished cannot be told from the frames [L].
- `turn/started` comes up to 2.2 s after a handover, and an interrupt in that time has no turn to name, so the driver cuts the turn as it starts. A turn the harness ended `interrupted` with no interrupt of ours reads `aborted`, and a turn that failed says its failure whatever an interrupt asked [L].
- A steered input that has not landed is dropped by `turn/interrupt`, with no frame to say so, and is not in the next turn, so the runtime offers it again [L].
- `clientUserMessageId` comes back as `clientId` on the `userMessage` item as it lands, and in `thread/turns/list` after a `SIGKILL`, which is `input.delivered` and `reconcile` [L].
- `thread/tokenUsage/updated` comes once per model call, with the same `total` again at an interrupt, and the old `total` at a resume. A cut call adds nothing. No frame says a model call began, so `model.call` comes with its usage, with no id, and a cut one goes uncounted [L] [R].
- Tools: a live call of ours is an `mcpToolCall` item whose id is the `exec-<uuid>` of `_meta.callId`, so `tool_item_carries_its_anchor` holds at the script, and the id is no model call's. On FakeModel, with no Code Mode, the same field holds the model's `call_id` [L] [R].
- Stop: end of stdin, `SIGTERM` and `SIGKILL` of the app-server each end a running `exec_command`, which leads a session of its own, 1 trial each. A `SIGKILL` as a sandboxed command was starting left it alive under `codex-linux-sandbox`, orphaned and out of the group, once in about ten kills, which is the `crash_window` a stop that comes to `SIGKILL` reports. `turn/interrupt` leaves a command running: an exec session outlives a turn [L].
- Sandboxes: `read-only`, `workspace-write` and `danger-full-access` each did what they say on a shell write [L]. `/tmp` is writable under `workspace-write` unless config excludes it.
- A required server that refuses us fails `thread/start`, naming it, so `ready.tools_visible` stays unknown. A connected server proves no model saw a tool [L].
- `mcpServer/elicitation/request` is how a tool of the user's own asks under `on-request`, with `codex_approval_kind: mcp_tool_call`. `accept` runs it, and `decline` tells the model `user rejected MCP tool call`. Ours asks nothing, by `default_tools_approval_mode` [L].
- An approval's id is ours, and unique across a session: a process's own count from 1 collided in the journal, which answers a refused approval `deny`. Told `deny` on a real model, the item reads `declined`, and nothing ran [R].
- `request_user_input` is offered to the model and answers `unavailable in Default mode`, so no request reached the driver. One that came could not be answered by a verdict, so the driver refuses it with a gap, which only a stand-in has shown [L].
- Compaction: `contextCompaction` starts and completes with no text, and on a custom provider its call reaches `tokenUsage`, so `model.call` carries `purpose: compaction`. `compacted` has neither `forgotten` nor `summary`. A provider that compacts on its side was not observed, and with no usage the driver reports `hidden_call` [L].
- Children: no `thread/started`, and a child's first `turn/started` on an unknown thread is the signal. `rootTurnId` names the parent turn, and no frame names the parent thread of a nested child, so `child.seen.parent` is None. A child's turn can end after its parent's, so our turn runs until the last thread stops, and `turn/interrupt` goes to each. `multi_agent_v1` ran on FakeModel [L]. On `gpt-6-luna` a child came through the V2 tools, as `subAgentActivity` items and a `wait` item, with no unknown frame: one `child.seen`, `session.status` saying `open_turn` while the child ran, and the turn ending only once the child had (1 trial) [R]. A child's usage comes per thread, as `tree` [L].
- Resume with a dangling tool call: the next request holds `function_call_output: "aborted"` for it, and it did not run again. That agrees with our cut-off notice (1 trial) [L]. On a real model the rollout says `aborted by user after 0.4s`, or 0.5s, of a tool that ran for seconds, with no user there, 4 trials, which the notice's "whatever your history shows" covers [R].
- A killed runtime takes the app-server with it, and its tool, in 0.2 s, as stdin ends. The cut-off notice held on it: in 4 of 4 the model looked first. In 2 it ran only the half that was missing, in 1 it ran the whole command again, having found it unfinished, and in 1, after an owner's stop, it left it alone [R].
- `kill -9` of the app-server alone ends its tool too, and `thread/resume` of that thread worked, during a tool and between turns, 1 trial each [R].
- Real teams, in [the spike](../research/spikes/real-harness.md): a Codex worker under a Claude lead claimed, fixed and completed two tasks, in teams of 22 and 23 calls. `ready` took 1.9 s at the median and 2.9 s at worst, and a handover 1.0 s to begin a turn and 2.2 s at worst. Each first turn cost a call looking up our tools in `ALL_TOOLS`, whatever `omit_tools_from` says [R].
- Its own agents, off unless a role allows them: `agents.enabled = false` in `thread/start.config` takes away the V1 tools a
  model outside the catalog gets and the V2 `collaboration` tools a catalog model such as `gpt-6-luna` gets, with the
  `<multi_agent_role>` text that says it is `/root`. `features.multi_agent = false` takes away V1 alone, and
  `features.multi_agent_v2 = false` nothing. A catalog model's tools come as an `additional_tools` item of the input, not as
  `tools` [L]. Asked to hand a search to a sub-agent of its own, `gpt-6-luna` started none, and did the search [R].
- One MCP tool call is cut at 300 s, `timed out awaiting tools/call after 300s`, and the model is told it failed (1 trial) [L]. So `tool_timeout_s` is 300, which `wait` refuses a `hold` at or above, and `declared_but_unproven` names it, as no check proves it.
- Several app-servers started at once on a `CODEX_HOME` never used before failed to open their state database, 3 of 4 in one probe, and
  once one had run all 4 came up. The failure is loud, and only a home of its own meets it, such as a test's: start one first [L].
- A login's kind is read from `codex login status`, on stderr. `account/*` frames name the account, so the driver drops them unread.
- A model on a native login treats the delivery as a pointer: it called `message_read` before answering, and called `agent_finish` when a goal seemed done, even at `Reply with the single word beta` [R]. In run 21 it did so with a role that said never to, as the preamble, which came after the role's words, tells an agent somebody spawned to make `agent.finish` its last call, so the first test of `tests/live/test_codex.py` failed, at 4 calls. In run 27, with the role's words after the preamble, it did so again, at 4 calls, and spawned with `stays` it answered and stayed, in run 28 at 7 [R]. The child of `tests/live/test_stays.py`, spawned with `stays` by a human, answered twice by ending its turn, called no `wait`, and finished when told, on the preamble that teaches `wait` for something named, in run 33 at 6 [R]. A woken turn opened with a `message_read` that showed nothing new in 2 of 14 woken turns this stage [R]. The owner's flow, a
  Codex lead and helper, settled in run 36 with no deadlock, and failed its check as the lead sent the follow-up at once, which
  landed in the helper's first turn; with the steps in an order no reading can mistake it passed in run 38, in 24 calls, the lead
  taking each answer in its one turn by a held `wait` with `from`. In runs 34 to 39 no agent opened a turn with a `wait` that named
  nothing, and a helper's woken turn opened with a `message_read` that showed nothing new in 4 of 6 [R]. With the shell in `read-only` it reported the failure and did not ask to escalate until told to [R].
- An empty read names what was already handed over (RFC 0047): woken three times by a memo on a `wake` topic and asked to read
  `#memo`, it read right after the first wake, was told nothing was new past `channel/memo@1` and given the `after` that reads it,
  read again with it, and answered from the memo; in the next two turns it read with `after` at once, in 7 calls, run 79 [R].
- The mixed-team example: a Codex worker under a Claude Code lead claimed the task, posted the note, completed the task and
  finished citing the note and its result, in 5 calls of the run's 11, run 80 [R].
- The live run: `board_post` reached on a first turn with no discovery call, a delivery, an interrupt, an approval through the runtime, and a resume by a new process with `excludeTurns`, no unknown frame, in the user's own setup. A first mixed team, `claude-haiku-5-5` and `gpt-6-luna`, exchanged a message each way and a board entry, in 7 calls. Getting there took 29 calls over five runs [R].
- What a client reads: a follower of live text was shown the start of the message item it became, a child spawned through our tool
  carries as its spawn's anchor the `native_id` of the tool item of its call, the call's own id with no Code Mode, and an interrupt
  under a stop below reached a child [L].
- From the command line: one `platoon-harness run` on FakeModel settled, and one stopped mid-turn by `session stop` was resumed by
  `session resume`, took the cut-off notice and settled [L]. On `gpt-6-luna`, as the worker `init` wrote, it claimed
  and fixed both tasks of run 41 in one turn of 11 calls. Stopped by `session stop` during `sleep 20`, its interrupted call was
  reported `unavailable`, so a `tokens` limit refused the resume's wake `unavailable`, as section 7 of the architecture says, and the
  run waited out its wall limit, run 42, which a turn charged its estimate now prevents. With no `tokens` limit it resumed with the text it was told at launch, journaled again whole,
  looked for the file, found it missing and ran the command once, in 4 calls, run 43 [R].

**pi 1.4.0, and the driver on 1.5.0.** [Report](../research/adapter-others.md), [fixture](../research/fixtures/pi-sample.jsonl).

- All loopback: fake chat server, isolated `HOME`, on Node 26.13.0. No real model, in the research or through the driver: nothing below is [R].
- `mcp__coord__ping` was in the first request. A tool turn made exactly 2 calls, with no title call.
- Critic probe: real pi on a minted child key through the real gateway. Tool seen and called, exact tokens, 2 datums on the child.
- `tools/call` `_meta` held only `progressToken`, and still does at 1.5.0, so pi's MCP client gives no anchor of its own. The `tool_call` hook
  sees `toolCallId` after pi checked a call's arguments and before the tool runs, and what a tool is handed is a copy of them, so the
  extension can put pi's id among ours' arguments without the transcript or the model's next request holding it [S].
- `cacheWarming` defaults to `"streaming"`: set it `"off"` for trainable runs.
- Split on LF only: U+2028 is legal inside JSON strings, so `str.splitlines` is unsafe.
- How ours arrive: not through an agent directory of ours. A per-agent `PI_CODING_AGENT_DIR` would cost a user their login, settings and extensions, and the only way back would be to read or link `auth.json`, which is refused. `pi.registerMcpServer` from an extension loaded with `-e` is pi's documented path and writes nothing. It ran on 1.5.0 beside a user's agent directory: a key saved in `auth.json` paid the model, the default provider and model of `settings.json` held, and a user's extension's tool and a project's `AGENTS.md` reached the first request beside ours, with their files unchanged [L]. A login kept in `auth.json` was a key: an OAuth login has not been run.
- The stdio shim's first run with pi: through that extension on the running interpreter, `exposure: direct`, our tool in the first request. Two identical `task_claim` calls in one turn were two claims, where over HTTP the second was a repeat [L]. Each now goes under pi's own id for it, `pi/toolCallId`, which the extension puts among its arguments as `_meta` and the shim moves to where MCP keeps it; the tool item pi reports holds that id, and `tool_item_carries_its_anchor` passes [L].
- The `timeout` on a registered server is what cuts a tool call: at 1 s a tool that never answered failed with a timeout, and the turn went on. `tool_timeout_s` is that number, 600. Pi's default is 60 [L].
- `--append-system-prompt` runs under `--mode rpc` and takes a file, once in each request. It also takes the place of a user's `APPEND_SYSTEM.md` [L], so it is not our path. Ours are a section of its own, set on `before_agent_start`, which stands beside that file, once in each request, across a tool call, a next turn and a resume [L]. It is what a launch hands it, a resume's too, so a resume is handed what it was told at launch [L].
- `--session-id` keeps our id, with a warning on stderr at each launch. `--session` of an id it cannot find exits 1. Pi writes a session at its first prompt, so one that took no turn cannot resume, and the runtime starts such an agent anew, as on Claude Code and Codex [L].
- With no login `get_state` names the model `unknown` or the one asked for, `get_available_models` is empty, and only a `prompt` is refused, so the driver refuses at start when no available model is of its provider. A bare model id several providers share, with none of them signed in, exits 1 at launch. `provider/id` names one, and `ready` reads it back as asked [L].
- `prompt` with a `streamingBehavior` begins a turn when idle and queues otherwise, so no turn can end between a look and a send. `disposition: handled` means an extension took it, and no model heard it, so the driver refuses it [L].
- `abort` during a stalled call leaves a queued steer queued, with no `queue_update`, and no run takes it, where pi's docs say `abort` continues what stays queued (1 trial, 1 s). The driver clears the queue once the turn settles, and the runtime offers it again, once [L].
- `--thinking` warns on stderr of a level it does not know, and reads `off` on a model with no reasoning, then runs on, so the driver compares `thinkingLevel` and refuses. On a provider of the agent's own a model has reasoning only when an effort was asked for, and `reasoning_effort` went in the request [L].
- `--model fake` resolves by pattern to `fake-model`, and the host refuses that against a role that pinned `fake`. With `--provider` an id it does not know runs as a custom id, with a warning on stderr [L].
- `usage.totalTokens` is whole. A call cut off says zeros and `stopReason: aborted`, which is unknown. `usage.cost.totalFromProvider` is a boolean: false on FakeModel, and by source only OpenRouter sets it, so `usd` came `estimated`, on a model the user's `models.json` priced, and `provider` only on a stand-in. A model with no price says 0, which the driver leaves unknown, so a `usd` limit on such a model goes unmeasured, loudly [L] [S].
- `responseId` on `message_end` equals the id the model gave, and `call_ids_reported` holds it to that on FakeModel. It says nothing of Platoon's gateway, whose join is claimed at M3 [L].
- Compaction, the first success seen on pi: `compaction_end` comes after `agent_end` and before `agent_settled`, with the summary, `firstKeptEntryId` and usage. `usage` sums one or two calls with no id, as a split turn takes two, so one `model.call` with `purpose: compaction` stands for them. `get_entries` walked from `leafId` turns the position into `forgotten`, from the first kept entry of the compaction before. It ran on a threshold set low on FakeModel; a manual `compact` on a small session says it is too small, and overflow recovery has not run [L].
- Resume with a dangling tool call: the next request holds `No result provided` for it, and it did not run again. That agrees with our cut-off notice (1 trial) [L].
- Stop: end of stdin and `SIGTERM` each end a running `bash`, which leads a group of its own. `SIGKILL` of pi's group leaves it alive, 1 trial each, which is the `crash_window` a stop that comes to `SIGKILL` reports [L]. A tool's `&`, `nohup` and `setsid` children, and a foreground `setsid` one, outlived `stop` with no gap, and each carried the agent's own `TMPDIR`, by which `Process` now ends them [L].
- Approvals: `tool_execution_start` comes before the `tool_call` hook, so a tool item has started when its approval is asked. Our gate's `confirm` title is the tool call's id, which ties a verdict to its observed outcome. A refused call comes back `isError` and the model is told. An answer to an id nobody waits for is ignored. A `confirm` of the user's own extension is an approval too, and `select`, `input` and `editor`, which a verdict cannot answer, are cancelled with a gap, so a gate of theirs built on `select`, as pi's own example is, blocks [L].
- The gate is ours, in the same process as the tools, and no security boundary. It lets our tools through, and `read`, `grep`, `find`, `ls` and what declares `readOnlyHint`, and asks for the rest.
- `reconcile` looks for the delivery's heading in the user messages of `get_entries`, which is whole and on disk. A kill loses what was only queued, but recovery asks of an approval's id too, so a miss is `unknown` [L].
- A landed input's entry: no frame names it. Pi writes a user message down as an entry once that message has ended, before it reads another command, so `get_entries` with `since`, the last entry seen, names it. The ids of a goal and of a handover that landed were the ids a compaction later named forgotten [L]. A fast model can answer before pi does, so the driver holds what pi says after an input until it is named [S].
- `agent_settled` with `aborted` and no interrupt of ours, from pi or a user's extension, reads `aborted`, which wakes a parent as a turn gone wrong does [S].
- A login's kind is `authType` from `pi auth check --provider <default> --json --no-refresh`, for the provider `settings.json` names, and with none it is unknown. `api_key` ran; `oauth` is read as a plan login on a stand-in alone. `print-api-key`, `print-bearer-token` and `--credentials` are never used [L].
- No tool for agents of its own is in pi's core, so a role's `allow_native_children` changes nothing. An extension of the user's can add
  one, which nothing of ours turns off, and a child it starts goes unseen [S].
- A warning from pi, such as a server of ours that failed, comes as `notify`, and is a `native` frame plus a gap. Pi connects a server after `ready`, so unlike on Claude Code and Codex this cannot fail the start, and the agent runs on with the gap [L].
- From the command line: one `platoon-harness run` on FakeModel settled, and one stopped mid-turn by `session stop` was resumed by
  `session resume`, took the cut-off notice and settled [L]. No live model has run it, as pi has no login here.
- What a client reads: a follower of live text was shown the start of the message item it became, an interrupt under a stop below
  reached a child, and an interrupt during a call under a `tokens` limit charged the cut turn its estimate and the session went on
  [L]. A spawn's anchor is pi's own id for the call that made it, which its tool item holds [L].

**openhands, SDK 1.59.0.** [Report](../research/adapter-openhands.md), [fixture](../research/fixtures/openhands-events-sample.json).

- All loopback, against a scripted OpenAI-compatible server. No real model. The clone is ahead of the wheel, so unprobed citations need rechecking.
- Critic probes: Platoon's runner on 1.59.0 gave 2 exact records with logprobs and 2 datums on the child. `arun()` with an MCP tool had `llm_response_id == call_id` for every action.
- Platoon pins 1.54.0.post1 and overrides private methods. The driver pins 1.59.0 exactly and reaches no private name.
- Undeclared tool arguments fail client-side here, unlike Codex and Claude Code. Server-side rejection stays mandatory.
- `Agent()` alone has no condenser and ignores `AGENTS.md`.
- The `openhands acp` path is a weaker row: CLI 1.16.0, SDK 1.28.1, no token streaming, no `usage_update`, no `session/resume`, and `session/cancel` maps to `pause()`. It is a generic ACP conformance target.
- The driver, a wire worker on SDK and tools 1.59.0, on FakeModel, and no live model: nothing below is [R]. An environment of the
  worker alone, built from the workspace lock without `lmnr-claude-code-proxy`, was 498 MB on local disk, and loading the SDK took
  10 s there, so `ready` comes that much after a launch. `describe` loads nothing and answers in under a second [L].
- Where the extra is missing, in an environment of the SDK and the command line alone, `doctor` said `openhands-sdk` is not
  installed for that environment's interpreter, and an agent's start was refused in the same words, while `team check` found no
  problem. A dry run of uv's resolver installing the extra brought in `lmnr-claude-code-proxy` 0.2.0, and with `--excludes` naming
  it did not.
- A runtime on an interpreter that finds the SDK only on `PYTHONPATH`, as a module system, an install to a prefix or a checkout
  would have it, described the worker and started it, which found the SDK there too [L]. The worker named as a wire command, as
  for an environment of its own, ran a turn that called our tools by their own names [L].
- Our tools come through the stdio shim, whose `_meta` holds a `platoon-harness/callId` per call beside the SDK's `progressToken`,
  so two identical calls in a turn are two. They show by their own names. Across a tool call, a wake and a resume by a new process
  the tool block and the system prompt held byte for byte, with our words once in each request, 25,817 bytes of tools [L].
- The SDK readies an agent, and starts its MCP servers, on a message, a run or a tool, so the worker runs `think` at start. A server
  that failed is a warning in its log, and the worker fails the start then. Called on the thread of the loop that serves the tools,
  readying waits out the SDK's 30 s listing timeout: it blocks, so the worker calls it on a thread of its own [L].
- What a request carried is in the SDK's completion log, which the agent's own LLM sends to a callback and writes no file. Its
  copies log nothing: the condenser's has telemetry of its own, and a child's, which `log_completions` would have write a
  `logs/completions` folder in the workspace, did so before the worker turned the flag off [L].
- Confirmation: `ConfirmRisky` over an analyzer that calls our tools low and the rest unknown asks for every action but ours and a
  lone `finish` or `think`. `deny` reached the model as `Action rejected: The runtime denied this.`, and the command never ran [L].
- Deliveries go to the conversation only between runs with no action pending. A message handed during a model call whose reply asked
  to run a command had the SDK reject the command as `Superseded by a new user message`, unasked, though the role allowed it; a
  message handed once `allow` came, before the next run, landed between the call and its result in the next request [L]. So one
  that comes while a run goes on asks the run to pause, which the SDK does after the step under way: the message then landed after
  the command's result, which one approval allowed [L]. One that waited through an approval missed the call right after the result
  in the run measured, as the run that runs what was allowed may hear the pause only during that call [L]. One handed in the
  last ticks of a turn had reached the conversation with no run after it; now a run runs it at whichever of the first eight turns
  of the loop it comes, on a stand-in of the SDK [L].
- An interrupt during a stalled call ended the turn `interrupted` with `InterruptEvent`, and the next run sent the call again. Under a
  `tokens` limit the cut turn was charged its estimate and the session went on [L]. A steer it cut off had waited in the worker, and
  the runtime's next offer of it reached the model once [L]. A message handed between runs that only a call an interrupt cut carried
  stays in the conversation, so once the runtime offers it again the model hears it twice, which at-least-once allows; this was
  read from the code and not measured.
- An interrupt while an approval was open measured the turn whole, as no run was under way, and the next turn's request told the
  model `The turn ended before this ran.` [L]. An allow and an interrupt sent together leave the action answered in its own turn,
  whichever the worker heard first, and the next request held its result right after its call [L]. A provider's 500 ended the turn
  `LLMServiceUnavailableError` after one request, with its usage a lower bound [L]. Four identical `think` calls ended it `stuck`,
  its usage whole [L]. The SDK's cap of 500 steps a run, which the worker lifts, has not been run past.
- Condensation with OpenHands' own default condenser: once its view held more than 80 events, after 40 `think` calls, it forgot
  events by id, a set the worker puts in the conversation's order, with the summary, and its call is measured under the usage id
  `condenser` [L].
- Resume: the same id with a fresh agent kept the history. An id with no conversation on disk is started anew by the SDK, so the
  worker refuses it. After a `kill -9` during a terminal command the action has no result, and the SDK would run it on the next run;
  the worker rejects it first, the model is told, and the command ran once [L]. `reconcile` reads the user messages on disk [L].
- Its own agents, allowed: `task` was offered, the call of it asked, and the child's terminal step asked the runtime through the task
  tool's confirmation handler, which the tool alone would answer yes. No event of the child reached the parent's callbacks, and the
  parent's stats gained `task:<id>` with the child's 2 calls [L]. An interrupt answered a child's open ask as cut off, and the
  child ended there, with no call after [L]: the task tool checks no cancellation, so a child the interrupt finds between asks calls
  the model until its next, where it ends. The child's terminal is tmux, which keeps its socket in the shared `tmux-<uid>` directory
  when `TMUX_TMPDIR` would make a path too long for a socket, so the driver gives the worker a short directory of its own, which a
  `tmux` the agent runs in its terminal uses too, and takes it back at `stop`, after a worker killed outright too [L].
- Credentials: `env` in the agent's terminal showed `TMPDIR` and no key, endpoint or token, no file of the session held the key, and
  the workspace held nothing the SDK wrote, its own agents allowed or not [L]. The proxy variables and `SSL_CERT_FILE` reach the
  worker from the shell, as litellm reads them; no real proxy has met it [L]. In the home it is given the SDK makes `.openhands/profiles` and
  `.openhands/provider-connections`, and its terminal's bash writes `.bash_history`, as they would in the user's shell [L].
- Project instructions: with `load_project_skills=True` a project's `AGENTS.md` reached the first request beside ours [L]. The SDK takes
  the nearest folder above the workspace that holds a `.git` entry as the repository's root, and reads its instructions there too; one
  it cannot read loses every project instruction, with a warning in the log alone [L].
- `litellm`'s catalog says which models take `reasoning_effort`, and it drops the field for one that does not, so the worker refuses
  an effort there. `num_retries` is 0.
- From the command line: one `platoon-harness run` settled, and one stopped mid-turn by `session stop` was resumed by `session
  resume`, took the cut-off notice and settled [L]. A scripted lead and an OpenHands agent exchanged messages through our tools, and
  the session settled [L].

**opencode, 2.2.5 via ACP.** [Report](../research/adapter-others.md), [fixture](../research/fixtures/opencode-sample.jsonl).

- Loopback frames cover `initialize`, `session/new`, `session/prompt`, `session/request_permission` and `session/cancel`.
- `initialize` advertised `loadSession`, `additionalDirectories`, `close`, `delete`, `fork`, `list`, `resume`, HTTP MCP, no SSE.
- A config entry with `codemode: false` gives a direct tool on the `run` and `serve` paths. A prompt sent before MCP connects misses the tool. Whether a config entry can win over `mcpServers` is not established.
- Hidden calls: a one-tool turn made 3 calls, one a title call with `tools: []` and no purpose header.
- A child's own id appears only in `x-opencode-session-id`, and the parent headers name its parent. `x-session-id` stays the root id. Key on `x-opencode-session-id`.
- One unpinned run reached hosted `opencode/flint-40b-free` by accident. That is the only real-model contact, and it proves the risk, not a capability.
- HTTP depth (`steer`, `queue`, inbox evidence) ran on loopback but is not reachable through ACP. Per-session permission rules are source only.

**prime, 0.10.2.** [Report](../research/adapter-others.md), [fixture note](../research/fixtures/prime-agent-sample.md).

- The Linux x64 tarball printed its version and help. A model turn was denied by the session's permission policy and not retried.
- Everything else is source. The fixture states it holds no capture. Make no claim from this row.

**generic ACP.** [Report](../research/acp-mcp.md).

- The spec and schema are read at `212f0cace08a`. Both SDK versions ran against a fake raw agent, on `initialize`, `session/new`, `prompt` and `_meta`.
- `claude-agent-acp@0.99.1` and `codex-acp@2.5.0` were probed at `initialize` only. They advertise `_meta.steering.supported`. No steering request was sent.

**generic exec.** Nothing upstream to inspect. [Architecture §9.1](../architecture.md) defines it. Platoon's `platoon-bash` and
`mini-swe-agent` specs show that one process on one key is exact there, which is the only fact the row rests on.

### SwarmChat on our backend

`platoon-harness web` serves SwarmChat 0.1.0's page, from source commit `fb5aa6a05b40`, over a projection of the journal, as
[RFC 0027](../rfcs/0027-the-browser-on-our-backend.md) says and [web.md](../how-to/web.md) guides. These are the page files it serves, read from
the installed package and held to these SHA-256 values when it starts. A file that differs stops it before anything is served.

| File | SHA-256 |
|---|---|
| `index.html` | `00f9da6be1f44e73c8a8120f3c0ea46df1f0f9d9b901e546d32681a51d405c8e` |
| `app.css` | `3dc776935e38c8f32e7fa2383eea8924ed4f114f861b5fb56ec005e91578a3b4` |
| `app.js` | `20e425ebb49b3cfa2d47e208f97b7dc319638568987bd23d8410021fa3b1a3de` |
| `gate.html` | `ab77cea699e17bb4157d30b1d834a185b4a690598574e07617acac92f4383cee` |
| `gate.js` | `83cb82cebcb7aada0fcc610e456b2bccc62b62c293dc92aa5b39453adad12bec` |

- What the page asks is SwarmChat's internal shape, unversioned upstream. A test runs one scenario through SwarmChat's own server,
  in the test alone, and through ours, and holds every reply the page uses to the same keys of the same types: `view_info`,
  `view_snapshot`, `view_messages`, `view_thread`, `view_receipts`, `view_posts`, `view_search`, `view_activity`, `view_as`,
  `view_knew`, `view_text` and `view_feed`. What we add is named `x` or begins `x_`, which the page passes by, and the one read
  of ours, `x_provenance`, is asked only by our overlay.
- The overlay is our script after SwarmChat's, in the same script, and reaches only names its script declares at its top level.
  It replaces `api`, `start`, `login`, `setLive`, `readRoute`, `route`, `onKey`, `apply`, `onClick`, `renderTop`, `avatar`,
  `messageHtml`, `systemHtml`, `openReceipts`, `openMembers`, `chatRow`, `chatRows`, `postHtml`, and the classes `ChatView`,
  `ThreadPane`, `PersonView`, `KnewPane`, `UnreadView`, `BoardView` and `MapView`, adds `provenance` to the address keys `KEYS`, and
  uses `S`, `TOKEN`, `ARROW`, `go`, `overlay`, `toast`, `throttle`, `buildSide` and the helpers `html`, `Safe`, `$` and `$$`. An upgrade that renames one breaks the browser tests,
  which fail on any page error.
- The link exchange is a script of ours before the gate's. It hands the gate the session token through the `#token=` the gate
  watches, as a link pasted into its tab would.
- `view_posts` answers sorted new or active, and refuses hot and top, which rank by reactions a session's messages do not take, and
  its `votes` is null. `view_as` and `view_knew`, and `as` on posts and activity, answer for an agent, and refuse a person, whose
  reading leaves no evidence.
- Upgrading is deliberate work: new hashes here and in the code, and the shape and browser suites run again.

### Report text this page overrides

| Report said | Now | Why |
|---|---|---|
| Codex `callId` equals the model's call id (acp-mcp, claim 11, finding 5) | True on a stub with a plain tool. Under live Code Mode it is `exec-<uuid>`: 0 of 2 matched | Spike. One Codex script can make several calls under shared ids |
| Codex live tool visibility unverified (adapter-codex, finding 1) | Default 6 of 7, `omit_tools_from` 8 of 8 | Spike |
| Over the gateway, Codex coordination uses the shell client (finding 3) | Shell `socket()` to loopback failed under `workspace-write` (1 trial), so that path looks blocked too. Unix sockets are untested | Spike. Section 4 states the result |
| `mcp` SDK in an extra, dual-era server (acp-mcp); stdio shim (adapter-codex) | Stdlib tools-only HTTP server, stdio shim as fallback, `server/discover` -32601 | Spike, architecture §10 |
| Parking unproven; cold resume untested (index, distributed-primitives) | Parking clean 10 of 10 with the tool visible. Cold resume 1 trial each | Spike |
| 3 of 4 `codex exec` stdio runs sent no MCP tools (acp-mcp) | Not reproduced over HTTP with a slow `initialize` (1 trial). `exec` and stdio were not rerun, so it stays open | Spike |
| Deliver with `turn/start` idle, `turn/steer` active, and retry on "no active turn" (adapter-codex, implication 7) | `turn/start` alone does both, and answers with the turn it joined | Driver probe on 0.164.0, FakeModel |
| Approval policy `never` with `approve` for tools (spike's settings) | `on-request`: every approval goes through the runtime | Owner's ruling |
| Codex child usage: "take increases in `total` per thread" | Holds, and a resume sends the old `total` again, which is no spending | Driver probe on 0.164.0, FakeModel |
| A thread-scoped provider works, `thread/start {modelProvider, config: {model_providers}}` (adapter-codex) | At 0.164.0. From 0.167.0 its first turn is refused, `modelProviderMismatch`: a thread runs on its app-server's provider alone, which `-c` names | Driver probe on 0.167.0, FakeModel |
| Claude launch omits `--setting-sources` (adapter-claude-code) | True. A role runs in the user's own setup, and a sealed launch belongs to a role's trainable profile at M3. The spike's `--strict-mcp-config --setting-sources= --permission-prompts none` is not the driver's launch | Owner's ruling |
| One agent dir per agent, for `mcp.json` and `models.json` (adapter-others; pi-durable) | A role keeps the user's agent directory, and one extension loaded with `-e` adds our server and a provider | Driver probe on 1.5.0, FakeModel. A per-agent directory has no login in it |
| `prompt`, `steer` and `follow_up` deliver (adapter-others) | `prompt` with `streamingBehavior` alone: the others race a turn's end | Driver probe on 1.5.0, FakeModel, and upstream docs |
| No successful compaction observed on pi (adapter-others) | Observed on a low threshold, with `forgotten` named | Driver probe on 1.5.0, FakeModel |
| ACP untested past `initialize` on real agents (index) | Holds for the Claude and Codex adapters. OpenCode and `openhands acp` ran prompts on loopback | Recorded frames |

## 4. Operational, Observable, Trainable

Levels are computed per agent from what was verified, and no driver can claim one (architecture §9.4). This table is the ceiling
upstream allows today, not a computed level. A training system still decides what trains.

| Adapter | Operational | Observable | Trainable |
|---|---|---|---|
| `claude` | **Yes.** Control, tools, interrupt, approvals and resume all ran on a real model | **Yes, with gaps.** Stable ids across stream and hooks. No token ids or logprobs, thinking text unreliable, aborted calls unrecorded, shell reads blind, children need `--forward-subagent-text` | **No.** Native login never. Through Platoon: `Unsupported message role 'system'`, exit 1, zero records. No Platoon spec. Anthropic does not support non-Claude models behind a gateway. Terms await the owner |
| `codex` | **Yes, with a guard.** Tools need `omit_tools_from`. A turn that ends with no required `wait` must be flagged, since the default failure was silent | **Yes, with gaps.** Items and per-thread usage are good. No response id on stable. Review, compact, memory and Auto-review work are hidden. Tool-to-call links stop at the script | **No.** Exact calls land on a minted key, but the gateway's Responses dialect drops `namespace` and `custom` tools, so MCP tools never reach the policy. The shell could not reach loopback under `workspace-write` (1 trial), and Unix sockets from that shell are untested. So no coordinated path is known in that sandbox. No Platoon spec |
| `pi` | **Yes on loopback.** No real model yet. Approvals are an extension we ship, which is no boundary | **Yes on loopback.** Assembled prompt visible, clean call profile, compaction named. A queue does not survive a kill. A tool call joins the model call that chose it through `pi/toolCallId` | **Yes, sealed, on FakeModel acting as a gateway.** Its sealed launch passes both sealed checks at 1.5.0: no built-in tool, nothing of the user's, our tools and the environment's, each body id its call id. Each compaction call, one or two, carries the gateway's headers through our extension and is reported with its id. Nothing real has met it |
| `openhands` | **Yes on loopback.** A worker process per agent. Assert the tools appear in `SystemPromptEvent.tools`, or fail the spawn | **Yes on loopback.** Best record: `llm_response_id`, `Condensation` with forgotten ids. Children visible only on disk after the fact | **Yes, sealed, on FakeModel acting as a gateway, at 1.59.0.** No coding tool, `num_retries` 0, `api_mode="chat"`, native delegation off, our tools and the environment's beside `finish` and `think`, the environment's named by its server as `environment_<tool>`, since a bare `finish` of TextCraft's collided with OpenHands' own and was refused at launch, and the condenser's every call carrying the gateway's headers, reported as `compaction` with its id. Subscription or Cloud auth never |
| `opencode` via ACP | **Partial.** Control works. Tool exposure through `mcpServers` is unresolved, so tools may hide behind Code Mode | **Partial.** Coarser than HTTP. Title calls hidden. Inbox delivery evidence is HTTP only | **Unknown.** Untested with Platoon. Title and compaction calls cannot be told apart by anything exact |
| `prime` | **Unknown.** No model turn ran | **Unknown** | **Unknown.** Not marked until a live probe exists |
| Generic ACP | **Per agent,** after conformance. Turn boundary only, `steer` after a fixture | **At best.** ACP carries no call attribution. Gaps across reconnect are labelled | **No by ACP alone.** Requires the gateway plane, which ACP neither gives nor blocks |
| Generic exec | **Degraded.** One-shot, `ph` only, no parking. `wait` beyond `hold` refuses `unsupported` | **Minimal.** Turn-end probes and the monitor. Most surfaces are `none` | **Possible,** one process on its own key with a verified profile. Nothing has been verified |

Across adapters: only Claude Code and Codex give an MCP-to-tool-call anchor, Codex's stops at the script, and any harness with a
shell is blind to `shell_reads` for life. A native child on a shared key stays on the parent and is never `exact`: a `child.seen`
makes its agent `forked`. A profile on a plan login is never Trainable. Token ids and logprobs come only from the gateway.

The computed level needs more than this ceiling: a gateway admission, a driver that declares `sealed`, our tools seen, and a result
kept on the machine that proves trainable, its two sealed checks among it, and a trainable session refuses a role without them before
any harness launches. Of the drivers shipped, ScriptedDriver, `pi` and `openhands` declare `sealed`, and a wire program may; Claude
Code, Codex, `exec` and ACP do not, so a gateway admission to one fails. Each sealed driver shows the environment's tools named by
its server, never bare: `mcp__environment__<tool>` on ScriptedDriver and pi, and `environment_<tool>` on OpenHands, as its SDK's
client of two servers names a server's tools. Bare, TextCraft's `finish` collided with OpenHands' own, and every agent of a sealed
launch was refused at launch. `environment_tools_in_first_request` holds each sealed driver to it, on FakeModel's own `finish` and
`think`.

| Harness | How each compaction call carries the gateway's headers | How it is reported | Settled by |
|---|---|---|---|
| ScriptedDriver | Its `Compact` step makes one call with them | `model.call` of purpose `compaction`, with the response's id | `tests/unit/drivers/test_sealed.py` |
| A wire program | It sends them from the gateway in its launch frame | As it reports any call, with purpose `compaction` | `tests/unit/drivers/test_sealed.py`, on a program serving ScriptedDriver |
| `pi` 1.5.0 | Our extension takes `session_before_compact` and runs pi's own exported `compact` with them, and a stream function that keeps each response's id; one call, or two for a split turn's prefix and the history before it | One `model.call` of purpose `compaction` per call made, by its id or none for one that never answered, which our extension says as a status before pi says the compaction ended, so one cut after its first call still reports both | `tests/integration/test_pi.py`, slow, on FakeModel [L] |
| `openhands` 1.59.0 | Its condenser's LLM sends them as `extra_headers` | Its `condenser` usage id is reported under `compaction`, with `llm_response_id` | `tests/integration/test_openhands.py`, slow, on FakeModel [L] |

Pi's overflow handling and its tools off are settled too, at 1.5.0 on FakeModel [L]: with `--no-builtin-tools` its first request
shows only ours and the environment's, and a request the model refuses as too long in the Chat Completions dialect's own words, which
pi reads as an overflow, is compacted and retried once. A sealed launch states a context window no context reaches, as pi takes an
unstated one as none at all, which had it compact after every turn once its history passed what a compaction keeps [L]. Whether
Platoon's own refusal text reaches pi as its error message has been read only in code.

## 5. Native features and coordination

Rules that hold on every harness:

- **Instructions.** We append through the supported path. We never overwrite `CLAUDE.md`, `AGENTS.md`, skills or hooks. What we
  append is journaled as `agent.instructed`, and on FakeModel Claude Code, Codex and pi each sent it whole, once, in the first
  request, and in the first after a resume [L]. A resume hands a harness again what it was told at launch: handed other text, Claude
  Code and Codex sent what their session began with, and pi what it was handed [L]. What is the user's or the harness's own we
  neither record nor change.
- **Teaching tools.** The preamble and tool descriptions name tools exactly. No harness's tool discovery is relied on.
- **Tool set.** Fixed per role at launch, with the preamble. Valid targets change, so `peers` lists them as they stand. On FakeModel,
  Claude Code, Codex and pi each kept the tool block byte for byte across a tool call, a wake and a resume by a new process, and said
  our words once per request [L]. That is a measurement and not a gate, and a live Codex's block, one `exec` tool, cannot be read.
- **Skills.** Per harness. No unification is claimed.
- **Slash commands.** A small core of ours plus namespaced passthrough, planned. The TUI sends what its composer holds as a person's
  message, and asks first about one that begins with `/`, since a harness may still read it as its own command, which nothing here
  claims yet. Its own commands are in its palette.
- **Hooks.** Displayed, not reimplemented.
- **Compaction.** Passed through and recorded as `compacted{forgotten, summary}`, native ids and the text that replaced them, both as
  bodies. If what was forgotten is unknown, that is a `compaction_opaque` gap. The context version advances either way. Coordination survives because the state is on the server:
  cursors are server-held, and a fence defaults to the caller's live lease. A notice carried on a tool result can still be lost to
  compaction, so "delivered" never means "still in context".

**Passthrough** means the native feature keeps working and we leave it alone. **Namespaced** means it sits beside ours under a
distinct name. **Unsupported** means it is unavailable on this path, with a reason. **Not determined** means the research does not say.

| Harness | Surface | Mode | Interaction |
|---|---|---|---|
| `claude` | Project instructions | Passthrough | Omitting `--setting-sources` loads `CLAUDE.md` and rules. A sealed launch belongs to a role's trainable profile at M3. Ours goes in `--append-system-prompt-file`, never `--system-prompt` |
| | Native skills | Passthrough | The same switch, and the same for a sealed launch. Built-in skills stay listed with empty sources: 20 in the probe. A forked skill uses a `forked-command-` prefix, not a tool id |
| | Slash commands | Passthrough, partial | `initialize` returns the command list. `/compact` ran over stream-json [L]. Other commands: not determined. A goal that starts with `/` is refused, as a model may have written it: `/clear` began a new session, which left the agent's id stale, `/compact` read as a turn that stopped, and a leading space or line made it plain text [L] |
| | Tool configuration | Namespaced | Ours arrive as `mcp__<ns>__<tool>` and are pre-approved by `--allowedTools`. The user's servers stay, and a sealed launch belongs to a role's trainable profile at M3 |
| | Hooks | Passthrough | User hooks still run, and we register none. A sealed launch belongs to a role's trainable profile at M3. A known limit: a headless harness shows no trust dialog, so a project's own hooks and `.mcp.json` run as they would under `claude -p`, in an untrusted folder too |
| | Auto memory | Passthrough | A user's memory for a project reached the first request under the driver's launch, as it does under `claude -p` [L] [R]. A sealed launch belongs to a role's trainable profile at M3 |
| | Permissions | Passthrough, with a known limit | `--permission-mode default` means a user's `defaultMode` cannot answer in the runtime's place, and a tool of the shell asks. A user's own `permissions.allow` rule still answers before the runtime hears, so a role's `deny` does not reach what that rule allows: the rule is theirs, and a role runs in their setup |
| | Native subagents | Off unless a role allows them | `Agent`, `Workflow`, `ListAgents` and `SendMessage` are disallowed. A child that runs is `child.seen`, `inferred` [L] [R]. Whether a skill that forks runs as a child with them off: not determined |
| | Session compaction | Passthrough, observed | `compact_boundary`, `PreCompact`, `PostCompact` [L]. Whether their fields name what was forgotten: not determined. Compaction also fires a false `SubagentStop`: it is not a child. Auto compaction was not probed |
| `codex` | Project instructions | Passthrough | A project's `AGENTS.md` reached the model under the driver's launch. Ours go in `developerInstructions` on `thread/start`, and again on `thread/resume`, where a thread keeps what it began with, after the user's `developer_instructions`, which that field would otherwise replace [L] |
| | Native skills | Passthrough in everyday mode | A shared `CODEX_HOME` inherits skills and plugins. A per-run `CODEX_HOME` has none |
| | Slash commands | Not determined | 70+ in the TUI. Their reach over app-server was not researched. Compaction has its own RPC |
| | Tool configuration | Namespaced | `thread/start.config` overlays the user's config, so the user's servers still start, and one of theirs that asks reaches the runtime as an approval. Ours arrive as namespace `mcp__<ns>`. Never `codex mcp add` or a config write. Project `.codex/config.toml` loads only when trusted |
| | Hooks | Not determined | Listed in the TUI. Behavior under app-server was not researched |
| | Native subagents | Off unless a role allows them | `agents.enabled = false` for the thread, V1 and V2 alike [L]. A child that runs is `child.seen`, `inferred` [L] [R] |
| | Session compaction | Passthrough, opaque | `thread/compact/start` is stable, and the driver does not call it. Compaction runs as hidden internal work (`x-openai-subagent: compact`). What it forgets is not said, so `compaction_opaque` stands. Auto compaction ran on FakeModel, and not on a real model |
| `pi` | Project instructions | Passthrough | A project's `AGENTS.md` reached the model under the driver's launch. Ours are a system prompt section of its own, from the extension, beside `APPEND_SYSTEM.md`, which `--append-system-prompt` would replace [L]. The assembled prompt is visible as a `role: system` message with named `sections` |
| | Native skills | Passthrough | The user's own load, and `/skill:<name>` in a prompt expands [L]. `.pi/skills` needs project trust |
| | Slash commands | Passthrough, partial | Prompt templates and `/skill:` expand in a `prompt`, and an extension's command runs at once, which `disposition: handled` says [L]. A goal starting `/` takes that path. `/compact` is a TUI command, and over RPC it is plain text to the model [L] |
| | Tool configuration | Namespaced | `pi.registerMcpServer` from the one extension `-e` loads, `exposure: direct`, for this process alone. Ours arrive as `mcp__<ns>__<tool>`. The user's `mcp.json` stays, and a known limit: a server of the same name there, or in a trusted project, takes our place, and nothing on the wire says so [S]. `.pi/mcp.json` needs project trust. The stdio shim sends a fresh id per call [L]. Over HTTP pi sends no id we can read, so identical calls in one turn would be one call, the trade-off of architecture section 6 |
| | Network | Passthrough | Pi does what it does in the user's shell: it fetches `fd` and `rg` when they are missing, installs a package a user named, and refreshes its model catalog. `PI_OFFLINE`, `PI_TELEMETRY` and `PI_SKIP_VERSION_CHECK` are left to the user. Tests set `PI_OFFLINE`, as a test reaches no network |
| | Hooks | Passthrough, restricted in training | No hooks as such: extensions on `tool_call`, which keep working beside our gate [L]. User extensions can add subagents or alter calls. Training plans `--no-extensions` plus an explicit `-e` list, a combination not probed. A known limit: `--mode rpc` shows no trust prompt, so `.pi/` resources load only under a saved decision or `defaultProjectTrust: "always"`, as they would for `pi -p`. Both ran. The driver passes neither `--approve` nor `--no-approve` [L] |
| | Native subagents | None in core; an extension's cannot be turned off | A user's extension can add a tool for agents of its own. Nothing of ours turns it off, and its children go unseen [S] |
| | Session compaction | Passthrough, exact | `compaction_end` names `firstKeptEntryId`, `get_entries` turns that into `forgotten`, and the summary is kept [L]. Purpose is on our `model.call` and unlabelled at a gateway |
| `openhands` | Project instructions | Passthrough | `Agent()` ignores them, so the worker sets `AgentContext(load_project_skills=True)`, as OpenHands' CLI does, which loads `.cursorrules`, `AGENTS.md`, `AGENT.md`, `CLAUDE.md` and `GEMINI.md` from the workspace and the repository's root. A project's `AGENTS.md` reached the first request beside ours, which are `system_message_suffix` [L]. The choice is the driver's and no role's, so the resolved team holds nothing of it, and this table and `docs/extending/drivers.md` record it. A training profile that turns it off arrives with M3 |
| | Native skills | Project skills only | A project's `.agents/skills` load with its instructions. The user's own, in `~/.openhands/skills`, and public skills, which fetch from GitHub, stay off, as the SDK's defaults are, where OpenHands' CLI loads all three |
| | Slash commands | Not determined | Found only in the CLI's TUI, which the worker does not run. `openhands acp` sends `available_commands_update`. The SDK path was not researched |
| | Tool configuration | Ours by their own names | Our server, through the stdio shim, is the agent's one `mcp_config` entry, as the SDK reads no user's server, and its tools show unprefixed, so `tool_names` is `bare` [L]. Whether one can collide with a built-in: not determined. A child inherits our server and calls it on its parent's token |
| | Hooks | None | The SDK loads no hooks file, `.openhands/hooks.json` being the CLI's, and the worker passes no `hook_config`, so a user's hooks do not run. A `Stop` hook could deny finishing and inject feedback [S] |
| | Native subagents | Off unless a role allows them | `task` and `delegate` are absent by default [L]. Allowed, `task` starts OpenHands' built-in kinds, each step asking the runtime through the task tool's confirmation handler [L]. A child is unseen: none of its events reaches the parent and no observation names it, so it is the gap `native_child_unattributed`, its spending its parent's at `tree` [L]. An interrupt stops a child at its next ask [L]; the task tool checks no cancellation, so until then the child calls the model on. A project's agent file that says `permission_mode: never_confirm` makes a child that asks nothing, which an interrupt then never stops, as the file is the user's [S] |
| | Session compaction | Passthrough, exact | `Agent()` has no condenser, so the worker gives it OpenHands' default one, as its own default agent has, which forgets past 80 events. `Condensation` names `forgotten_event_ids`, so `compacted{forgotten}` is exact [L]. Through the gateway: untested |
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

### Provenance per harness

What each harness's own reports let the runtime confirm, and tie, of what an agent was handed (architecture §11). An offer is
confirmed only by the harness's report: an `input.delivered` for an input, the goal at launch among them, or a tool item that came
back `completed`, whose `native_id` is the anchor a read went under. One that `failed`, as an `is_error` result, an interrupted call
and a lost reply do, confirms nothing, so a steer notice that rode on one of our refusals stays unconfirmed. Nothing joins by order or
timing.

| Harness | An input said to land | A model call's id | A tool call's anchor, and what holds it | A read confirmed | What a compaction names | Native children | Where its turns are cut into spans |
|---|---|---|---|---|---|---|---|
| `claude` 2.1.316 | `command_lifecycle`, under the uuid5 of the input's id, which is its `native_id`; the goal at launch too [L] | The message id at `message_start` [L] | `claudecode/toolUseId`, which the tool item's `native_id` holds and equals the model's tool id [L] [R] | By the completed tool item that holds its result [L] | Nothing: `compaction_opaque`, so no handover is known forgotten [L] | `child.seen` with the tool call that started it [L] | At each write a model call chose, as its tool calls join their calls [S] |
| `codex` 0.164.0 | `userMessage`, under its `clientId`, with the item id as `native_id`; the goal at launch too [L] | None: it gives no id per model call [L] | `callId`, which the `mcpToolCall` item holds: under live Code Mode the `exec-<uuid>` of a script, which several calls can share [L] [R] | By the completed item, as returned to the script; one item confirms each read under a shared id [L] | Nothing it names [L] | `child.seen` for a thread it starts [L] | Nowhere: each turn is one span, as no tool call joins a model call, and its calls have no id to train by [S] |
| `pi` 1.5.0 | `message_start`, matched by the input's text, with the id of the entry pi wrote it down as, from `get_entries`, as `native_id`; the goal at launch too [L] | `responseId` at `message_end` [L] | `pi/toolCallId`, pi's own id for the call, which the tool item's `native_id` holds and which reaches us through the shim [L] | By the completed tool item that holds its result [L] | Entry ids from `get_entries`, which a delivered input carries, so a handover is marked `forgot` or `kept` [L] | None in core [L] | At each write a model call chose, as its tool calls join their calls [S] |
| `openhands` 1.59.0 | `request`, read from the SDK's completion log, with no `native_id` [L] | `llm_response_id` [L] | The shim's own id, which no item holds [L] | Not yet: no item holds the shim's id [L] | Event ids through `Condensation`, which no delivered input carries until the worker reports a message's id [L] | Opaque, a gap [L] | Nowhere: each turn is one span, as no item holds the shim's id, though its calls have ids [S] |
| `exec` | Never: the goal is in argv, which says nothing of whether it landed | None | `ph`'s own id, which nothing holds | Never | Nothing | None | None: it reports no model call, so no turn of it has a span [S] |

What the queries make of it (architecture §11): a Claude Code or pi tool call joins the model call that chose it, so an answer about
an event it made is bounded at that call, `call`; pi's bound rests on `message_end` coming before that call's tool items, which it
did on FakeModel. A Codex tool call reaches its script's item and no call, and an OpenHands or `exec` one reaches nothing, so theirs
are bounded at the event's commit, `commit`, which can count a read the same model call chose as below. A compaction is `unsaid` on
Claude Code and Codex, which name nothing they forgot, on OpenHands, whose delivered inputs carry no id, and for every read; on pi it
is `forgot` or `kept` for a handover. Each of these ran on the real binary against FakeModel, a read then a cited write, in
`tests/integration` [L]. `spans` cuts a turn only at a write the record joins to its call, so where each harness's turns are cut
follows from those joins: ScriptedDriver's, whose model-chosen tool calls go under `scripted/toolCallId`, are cut at writes in
`tests/unit/primitives/test_spans.py`. `spans` and `propagate@3` ran on pi 1.5.0 and on OpenHands 1.59.0 against FakeModel in
the contract test, which shows each agent's last words lying in a span with its row [L]; no real binary has shown a turn cut at
a write, so the cuts in the last column are inferred [S]. `propagate@3` counts an offer its harness took
while a call ran as a take of that call where the harness reports a call at its end, as pi and ScriptedDriver do, and of the next
where it reports one at its start, as Claude Code does, so at a span's edge the same take can fall in neighboring spans on the two
[S]. A read through `ph` stays unconfirmed on every harness, and is labelled so: `ph` would have to send the id of
the shell call that runs it, and neither Claude Code 2.1.316 nor pi 1.5.0 hands a shell command any such id, by its environment on
FakeModel [L]; Codex's shell does not run on the machine this was checked on. `exec` reports no tool item at all. Every harness here has a
shell, and no stored conformance result proves a surface yet, so a negative answer is `unknown` on each. The terminal's `/provenance`
and the browser's Provenance pane say what the answers say: on Claude Code the call that chose a cited write and the tool item that
joins it, and the read before it returned to the harness under that item's id [L]; a tool item's own panel names the call its report
names and opens the write its command made [L]; elsewhere why no call is joined, as their reports above leave it. A read a Codex
script made is said to have returned to that script, which may never have shown it to the model.

### Workspaces

What each harness sees in a worktree of its own ([workspaces.md](../how-to/workspaces.md), RFC 0031), and what git does that the runtime's
own git relies on or works around. Git 2.47.3 is the only version run; [V] verified here, [S] read in source, [U] unverified. In a
snapshot each sees the same, but that the repository's own `.git/hooks` are new and empty there, while a `core.hooksPath` your global
or system config sets still runs for an agent's commits [V].

| Harness | In a worktree |
|---|---|
| Claude Code 2.1.316 | Offers `EnterWorktree` and `ExitWorktree` in its first request, which the driver turns off on every launch, and takes `--worktree`, which nothing passes [V]. Reads the tracked `CLAUDE.md` and skills there; an untracked `CLAUDE.local.md` is absent [V], and `.claude/settings.local.json` and untracked skills are too [U]. Its auto memory is keyed on the repository, so every worktree of one shares it, a channel no topology binds [V]. It commits there and resumes in the same folder on FakeModel and on a real model [V]. After a commit on a real model it sent `system/vcs_state_changed`, a frame the driver does not know, journaled as `native` plus the gap `unknown_update` in runs 59, 60, 62 and 64 [V], in a snapshot too |
| Codex 0.164.0 | `thread/start` and `thread/resume` name the thread's `cwd`, which the driver holds to `spec.cwd` [V]. Reads `AGENTS.md` at the worktree's root, its project root [V]. Under `workspace-write` and `read-only` its sandbox keeps `.git` and the resolved git directory read-only, so each commit outside the session's checkout, and in it too, escalates to one approval that runs outside the sandbox [V]. Escalated and allowed, it committed in a worktree and resumed there on FakeModel [V]. Project trust taken from the main checkout for a new worktree path [U] |
| pi 1.5.0 | Sessions are keyed on the folder, which never changes, so a resume never meets its prompt to fork into another [S]. It commits there and resumes in the same folder on FakeModel [V]. `.pi/` resources load only under a trusted path, which a session folder usually is not, so they are silently absent [S, from 1.4.0] |
| OpenHands 1.59.0 | `workspace=spec.cwd`, and skills are read at the worktree's root [S] |

In an isolated workspace each runs inside the `bwrap` extension's isolation, with its home in its agent's folder and yours hidden.
Each committed, left a process in a session of its own, which ended with it, and called our tools on loopback, against FakeModel on
one Linux host with bubblewrap 0.4.1 [V]. What each needs, which its driver declares as `installed`:

| Harness | Isolated |
|---|---|
| Claude Code 2.1.319 | Its native binary is a link from `~/.local/bin` into a versions folder in your home, so with your home hidden it is `command not found` [V]. The driver declares where `PATH` finds it, and the wrap binds what that resolves to and makes each link on the way again [V]. It keeps its state in `home/.claude` [V]. An npm install, which runs on node from a package folder, is not declared [U] |
| Codex 0.167.0 | Its standalone release, which `codex-package.json` names, holds the `bwrap` its own sandbox runs and `rg`, and is declared whole [V]. Under `workspace-write` its sandbox ran a command nested inside ours, and its commit escalated, was allowed, and ran inside ours [V]. It keeps its state in `home/.codex` [V]. An npm install [U] |
| pi 1.5.0 | Itself, the `node_modules` its package is in, node, and the Python our stdio shim runs on [V]. It keeps its state in `home/.pi` [V] |
| OpenHands 1.59.0 | The worker runs on the runtime's own Python: the interpreter, its environment, the installation that is made from, and our package's folder [V]. The folder its driver makes for tmux is under /tmp, so the worker makes it again inside its own [V] |

A Codex role in a worktree or a snapshot has three postures, which `team check` names before any cost when its sandbox keeps `.git`
read-only and its approvals are left to ask: `sandbox = "danger-full-access"`, where commits work and its commands run with no
sandbox; `approvals = "allow"`, where the sandbox stays and each escalation is allowed by policy; or `ask`, where a person approves
each commit, so a headless run ends `needs_human` at its first. Under `approvals = "deny"` it warns that each commit is refused.

Git, as the runtime's own git meets it [V]:

- `rev-parse --git-path=X` prints `--git-path=X` back, unresolved, where `--git-path X` resolves it.
- `worktree add --lock --reason` writes the reason into its `locked` file from the first write, with a newline after it. A
  registration git never wrote `gitdir` into is invisible to `worktree list` and, locked, never pruned. One missing `commondir` or
  `HEAD` is listed, detached at zeros, and `worktree remove -f -f` refuses it as no `.git` file; `worktree add -f -f`, once its folder
  is empty, takes it back.
- A locked worktree survives `prune` with its folder gone and refuses `remove`, and `unlock` works with the folder gone.
- `rev-list --all` takes every worktree's HEAD, so a commit only a worktree's detached HEAD holds reads as reachable; `--glob='refs/*'`
  in the session's checkout takes refs alone.
- `worktree remove` deletes ignored files without asking, and refuses one with submodules. It judges a worktree clean by `status` as
  your config has it, so under `status.showUntrackedFiles=no` it removed one holding an untracked file; the runtime's own status
  names `--untracked-files=normal` and `--ignore-submodules=none`, so no config hides a path from a look or a stop.
- In a sparse checkout `worktree add` copies your patterns, so a new worktree's paths outside them are `skip-worktree` and absent
  from its tree, which loses nothing when it goes.
- `worktree add` with LFS files and no LFS filter checks out their pointers, silently.
- Commit, amend, a merge `git merge` makes, cherry-pick, revert and each pick of a rebase write a HEAD reflog entry whose time is the new
  commit's committer time, under a set `GIT_COMMITTER_DATE` too; a fast-forward, a reset and a rebase's start onto existing commits
  write one at the time they ran. Reflog times have one-second resolution. A HEAD reflog the runtime made goes on taking an agent's
  entries under `core.logAllRefUpdates=false`.
- `rev-list --ignore-missing` passes over a missing negative only when it comes before `--stdin`.
- `rev-parse` resolves `HEAD`, `main` and `main@{1.year.ago}` as readily as a hex prefix, and a ref named in hex digits before an object
  with that prefix, so a look resolves an `Informed-By` value with `rev-parse --disambiguate`, which names objects alone.
- `log --numstat -z` puts a renamed file's two paths in entries of their own after its counts, and says `-` for a binary file's.
- `git add -A` and `write-tree` run in your checkout with `GIT_INDEX_FILE`, `GIT_OBJECT_DIRECTORY` and
  `GIT_ALTERNATE_OBJECT_DIRECTORIES` pointed at a snapshot capture its tree under your config, change neither your index, refs nor
  object store, and write only what is new into the snapshot's store; a blob only staged in yours is not copied, and the snapshot's
  own pack is what keeps it once you unstage it and prune.
- `repack -a -d` in a repository with alternates packs what it borrowed too, so removing `objects/info/alternates` after it leaves
  it whole.
- `ls-files --others --exclude-standard` names an untracked repository inside the tree as `dir/`, where `status` names only its
  untracked parent folder; `check-attr -z --stdin filter` gives each tracked file's filter, `unspecified` for none.
- A fetch from a snapshot with no branch to land on writes only `FETCH_HEAD`, so its commits stay unreachable from your refs.
- `git add -A` on a copy of an index with unmerged entries marks them resolved, so a capture of a checkout mid-merge would hold
  the conflict markers as settled, which is why a snapshot is refused there.
- With `core.splitIndex`, a capture writing a copy of your index put a new `sharedindex.*` into your git directory and left the
  copy unreadable in the snapshot; with `core.splitIndex=false` in its environment it writes the copy whole.
- `bundle create` refuses a bare commit with no ref; `bundle unbundle` restores a commit pruned since.
- `checkout --detach <sha>` in a repository just made, whose `objects/info/alternates` names another's store, checks that commit out
  whole and clean from the borrowed objects, following a snapshot's own alternates on to yours, as a runtime test's checkout does.

By git's release notes, not run: `--path-format` arrived in 2.31, `worktree add --reason` in 2.33 and `worktree list -z` in 2.36 [S].
Git other than 2.47.3, macOS, a case-insensitive filesystem and a repository past 100,000 files or on Lustre are [U], as section 8
says.

## 6. Supported platforms

The initial release targets **Linux and macOS**. Linux is the only platform anything has run on. Only the kernel and filesystem
detection rows describe our code. The others record probes of upstreams or throwaway prototypes, and [STATUS.md](../STATUS.md) holds what exists.

| Component | Linux | macOS | Windows | WSL |
|---|---|---|---|---|
| Kernel and journal | **Tested.** Unit tests, including SIGKILL. The spike's prototype had 0 violations in 226,807 acked commands over 40 kills. Power loss not tested | **Not run.** Needs `fullfsync=ON` and `checkpoint_fullfsync=ON`. `F_FULLFSYNC` latency is unmeasured and decides the 50 ms mark | **Not a target.** Not run. The design uses `flock`, Unix sockets and process groups | **Not run.** Linux rules inside the distro filesystem. `/mnt/c` is 9p and refused |
| Control socket | **Measured.** Python `bind` allows 107 bytes | **Not run.** 103 usable, from headers | Not run | Not run |
| Filesystem detection | **Exercised:** xfs, tmpfs, Lustre, FUSE control, `proc`, symlinks. Other magics come from headers | **Not run.** Written from the man page | Not run | 9p magic known, not exercised |
| TUI | **Tested.** Textual 8.2.8 under Pilot, and `platoon-harness attach` on a real PTY read through `pyte`. Real terminals, tmux and SSH have not been measured | Not run | Untested: the tests use Unix `pty` | Not run |
| SwarmChat client | **Tested** on our backend, reading and acting, in Playwright 1.64.1's Chromium headless shell, revision 1248, on RHEL 9 x86-64, on scripted harnesses, the real `claude` binary against FakeModel, and real models in live run 58. Chromium's headless shell only: Firefox, WebKit and a headed Chromium untested | Not run by us. Upstream runs `unittest` only | Not run by us. Upstream runs `unittest` only | Not run |
| Claude Code, Codex | **Real model** on x86-64 | Not run. Seatbelt not tested | Not run | Not run. Codex's sandbox does not support WSL1 |
| pi, OpenCode, OpenHands | **Loopback** on x86-64 | Not run | Not run | Not run |
| Isolated workspaces | **Experimental.** The `bwrap` extension, its escape tests passing on Claude Code, Codex, pi and OpenHands against FakeModel, on one host with bubblewrap 0.4.1 | **Not given.** No provider, and it is refused before any cost | Not a target | Not run |
| Prime Agent | Version and help on linux-x64 | Not run | Not run | Not run |
| Platoon bridge | Probed on CPU | **Unverified.** Platoon classifiers list POSIX Linux only. This does not affect the SDK | Not a target | Not run |

Performance on Linux, from the [journal spike](../research/spikes/journal-performance.md): at 500 events per second with 100 simulated
agents, ack p99 was 2.8 ms on node-local NVMe. Those are server disks with near-instant flush, so they do not stand in for a laptop.
Ack p99 is at least twice the sync time, so a sync above about 20 ms misses the 50 ms mark. Run the benchmark on a real Mac before
Milestone 1 closes.

| Prerequisite | Requirement |
|---|---|
| `platoon-harness` | Python 3.12+. ACP wheels cap at `<3.15` |
| `claude`, `codex` | User-installed binary |
| `opencode` | `@opencode/cli`, platform binary, no Node at runtime. Check the major version: bins are `opencode` and `opencode2` |
| `pi` | Node >= 22.19 |
| `openhands` | The SDK's `openhands` extra, in the runtime's environment or, run as a wire command, one of its own: Python 3.12+. An environment of the worker with OpenHands' tools and without the proxy was 498 MB, and 387 MB without the tools. The OpenHands CLI needs `==3.12.*` and is not used |
| `prime` | Release tarball, `uv`, Python >= 3.11 kernel |
| Codex sandbox on Linux | Bubblewrap and user namespaces. A bundled `bwrap` is the fallback. With user namespaces blocked, sandboxed commands cannot run (docs, not reproduced). Never fall back to `danger-full-access` silently |
| `isolated` workspaces | The SDK's `bwrap` extension: Linux, `bwrap` on `PATH` and unprivileged user namespaces, which a kernel setting, AppArmor or a container's seccomp can block, and which its probe says before any cost. Run on bubblewrap 0.4.1 alone. No provider for macOS |

## 7. Auth and terms

This is engineering policy, not legal advice.

| Profile | What it is | What we do | Levels |
|---|---|---|---|
| **Native login** | The harness's own sign-in, made by the user through its own flow | Spawn the user's binary on the user's machine, with no credential added. `doctor` shows only whether a login exists and which kind. Each harness signs itself in | Operational, Observable |
| **Plan login** | A native login on a subscription | The same, for that user's own work. Headless multi-agent exits 78 and names the fix unless the user opts in. `web` serves loopback unless `--host` names another address with TLS, and a control link is the owner's alone to use, a view link what another person gets: refusing another address to a session on a plan login is planned | Operational, Observable. Never Trainable |
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

**Open questions.**

- Prime Agent: run a live probe, or leave it unclaimed?
- Training through Claude Code against a non-Claude policy: its system prompt and tool descriptions would enter datasets. Blocked until decided.
- DAO is the owner's research on training self-organizing teams with Platoon and this SDK.
  [Scenario 2](../research/swarm-patterns.md#6-example-scenarios-for-brief-section-10) implements only the brief's table row.

**Terms and licenses.**

- OpenAI Terms clauses need review from a direct source.
- `lmnr-claude-code-proxy` is proprietary, and the `openhands` extra installed from an index brings it in unless excluded, as uv's `--excludes` does. The worker runs without it, and the workspace lock excludes it. Nothing is published, so no install of the extra from an index has run, and its resolution with and without `--excludes` was a dry run.
- `claude-stream-sample.jsonl` holds short strings authored by a proprietary CLI. Review before the repository goes public.
- Concurrency of one plan login across many processes is unknown for both Claude Code and Codex.

**Harness behavior not measured.**

- Stronger models and long tasks: parking used cheap models, low effort and an instruction to stop.
- A natural overrun past `wait`: no model ignored it unprompted, so the spike's proposed interrupt trigger never met one. The design leaves the wait open instead.
- Long parks: nothing parked beyond seconds. Cache cost after expiry, long blocking `wait` calls and client tool timeouts are untested.
- Fallback, cold resume, token exclusion, slow init and shell socket are 1 trial each.
- Several agents in one `codex app-server`, with distinct tokens.
- Codex child agents on a real model past one trial, and v1 on a real model: v2 ran once through the driver, in run 26.
- A Codex child that stays under a Codex lead past one trial: on the words it is told now the owner's flow passed once, in run 38,
  after a lead in run 36 sent its follow-up before the first answer. Told it stayed for the next message, a child held a `wait` for
  its parent instead of answering, in runs 23 and 24.
- Teams past three agents, and work past a minute: everything in [the spike](../research/spikes/real-harness.md) was small and quick.
- Auto compaction, a turn that fails and a child's approval on a real Codex model, and `fileChange` items anywhere: FakeModel offered no patch tool, so a stand-in is all that has shown one.
- Whether a steer that ended a model call on FakeModel does so on a real model.
- Unix sockets from the Codex sandboxed shell, the `read-only` sandbox, and blocked user namespaces.
- `omit_tools_from` durability: under-development `code_mode_only_strict_3p_tools` ignores it, and the model catalog is served remotely, so a live first-turn check belongs in conformance.
- Why `accept` gave two outcomes on identical Codex input.
- Whether `thread/resume` keeps the rest of a thread's `config`, as it keeps the instructions and the setting of its own agents a thread
  began with [L]. We resend it, and our tool and the effort held on a resume.
- `--bare` becoming the default for `claude -p`: announced with no version, and it stops reading a native login.
- Auto compaction, nested subagents and parallel tool batches on Claude Code. A harness killed outright on a real model, as a power cut would, since on real runs it outlived its runtime.
- `tool_timeout_s` on Claude Code: no cap was measured, so none is declared.
- Successful compaction on OpenCode, so provenance across compaction is unconfirmed there. On pi it ran on FakeModel, on a low threshold, and its overflow recovery, sealed, on a refusal in the Chat Completions dialect's words: a real summary has not run.
- pi on anything real: a provider, an OAuth login, retries, `totalFromProvider`, parallel tool calls on a real model, and steering on a real stream. Nothing but FakeModel has met the driver.
- OpenCode: `mcpServers` precedence, repeated prompt `id` retry semantics, and the empty experimental log replay.
- Our HTTP tools server against OpenCode, and against OpenHands through its driver, which takes the shim. Claude Code and Codex have met it, and so has pi, on a fake model, and OpenHands' MCP client with a bearer in `headers` on FakeTools.
- Delivery through `claude-agent-acp` and `codex-acp` past `initialize`, including resume, permissions, `mcpServers`, `env` leak behavior and steering.
- Whether adapter `toolCallId` equals the model tool id, and whether native-subagent MCP calls carry a usable anchor.
- OpenHands: anything on a real model; condenser, delegation and long runs through the gateway. A delivery that comes while a tool runs, a child's `task` among them, waits in the worker until the run pauses after that step, so a long tool holds it as long; the worker takes it at once, so the runtime's handover does not wait, and no long tool has been timed. Memory at 100 agents, given 210 MB RSS at import, and one worker per agent.

**Training path.**

- Hidden calls: any unlabelled side call trains as `policy`. Platoon's classifier is unbuilt.
- `rollout_isolation: process`, mint over a Unix socket, and mint through a sandbox route.
- Prefix merging across compaction, and with a real model's renderer: both tool probes diverged under the toy tokenizer.
- `platoon.sandbox`, `platoon.extensions` and `/v1/platoon/agents` carry no stated stability promise. Experimental credit APIs may change in a minor release.
- The OpenHands pin: Platoon's 1.54.0.post1, where the driver pins 1.59.0.

**Platform and scale.**

- macOS: nothing has run. `F_FULLFSYNC` latency decides the journal's ack promise there.
- Power loss, devices that ignore flush, and NFS, CIFS, GPFS or BeeGFS. Lustre with two hosts did not corrupt in short runs, but that is not evidence of safety, and it stalled up to 6.4 s.
- Many sessions in one process, lagging followers at scale, payloads above 4 KiB, and soak beyond 60 s.
- Real terminal throughput over SSH and tmux, and accessibility on an alternate screen.
- Shell-capable agents at one UID can read each other's tokens through `/proc`. Whether Codex's sandbox blocks that read is unknown.
- Workspaces on git other than 2.47.3, on macOS, on a case-insensitive filesystem, where branch refs differing only in case may
  collide, and on a repository past 100,000 files or on Lustre. Where Claude Code 2.1.316 reports `cwd` in its init frame.
