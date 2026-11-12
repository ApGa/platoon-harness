# Compatibility

What each upstream is, how we use it, and what is known about it, inspected or measured from 2026-11-02 to 2026-11-08. These
are **upstream facts**, not claims about our drivers: what each driver has passed is in [Driver status](#driver-status), and a
result pins to the driver, the harness version, the SDK and the host
([architecture §9.3](../architecture.md#93-verified-not-believed)).

## 1. Upstreams

**IMPLEMENTED** is code on the default branch. **EXPERIMENTAL** is shipped and labelled unstable. **DRAFT** is a proposal with
no code. **DOCUMENTED-ONLY** has no code to read.

| Upstream | Inspected | License and constraint | How we use it | IMPLEMENTED versus DRAFT | Most important fact |
|---|---|---|---|---|---|
| Platoon | 0.5.0 | MIT AND Apache-2.0 (tool parsers). Optional extension; keep its NOTICE if parser code is ever copied | A training authority, on the contract this repository holds ([RFC 0049](../rfcs/0049-the-contract-a-training-authority-gets.md)). Nothing here depends on Platoon | IMPLEMENTED: gateway, child mint, trajectories, env forks, extensions. EXPERIMENTAL: credit, policies, Responses and Messages dialects. DRAFT: `AgentGraph`, `RewardEvent`, attribution levels, native selectors, `bus` | The only exact identity for an external agent is one key per agent, from `POST /v1/platoon/agents` |
| SwarmChat | 0.1.0 | MIT. Its notice heads each of its scripts we serve. Exact pin, `swarmchat==0.1.0` in the `cli` extra | Second client: its five page files, each held to its SHA-256, over our own backend, from `platoon-harness web`, with an overlay of ours that acts through `/x/command`. Its server never runs | IMPLEMENTED: server, agent API and a read-only viewer. No composer exists or is documented. Nothing DRAFT | Messages have no idempotency key, no metadata and no caller ids, so a projection into its server cannot be idempotent |
| Toad | 0.6.20 | AGPL-3.0. Ideas only: no code, no dependency. Its `textual-diff-view` is AGPL too | Interaction reference | IMPLEMENTED: own ACP v1 client. Nothing DRAFT | Copying is ruled out by license, not merely unnecessary |
| OpenHands | SDK 1.59.0, CLI 1.16.0 | MIT | Wire worker on SDK `arun()`, from the `openhands` extra | IMPLEMENTED: SDK, agent server, `openhands acp`. Docs list `--streaming`, absent from CLI 1.16.0 | Passed the exact path on a minted key. Cannot share an environment with `mcp` 2.3.0 or ACP 1.0.0rc3, and the CLI pins SDK 1.28.1 |
| Codex | 0.164.0, and 0.167.0 from 2026-11-06 | Apache-2.0 with NOTICE. User-installed. Never read or copy `auth.json` | `codex app-server` over stdio, no `experimentalApi` | IMPLEMENTED in behavior, labelled Experimental upstream. `codex mcp-server` is removed. `turn/steer`, `thread/fork`, `thread/inject_items` are on the stable handshake | The model reaches MCP tools only from inside a Code Mode script, so `omit_tools_from: ["deferred"]` is required |
| Claude Code | 2.1.316; its public repository holds a changelog and examples only | Proprietary. Never bundle, vendor or patch. Agent SDK wheels bundle the CLI: no default dependency, no re-hosting | `claude -p` stream-json with the control protocol on the user's own binary | IMPLEMENTED. Undocumented: `--permission-prompt-tool stdio`, `command_lifecycle`. EXPERIMENTAL: agent teams, which do not run in `-p` | `ANTHROPIC_BASE_URL` alone keeps a saved login active, so it is never set without a gateway credential |
| OpenCode | 2.2.5 (`@opencode/cli`; `opencode-ai` stops at 1.19.5) | MIT. User-installed | Generic ACP driver first. An HTTP driver is a later option | IMPLEMENTED: `opencode acp`, `opencode serve`. Its `/api` spec calls itself experimental. `/api/experimental/*` is EXPERIMENTAL | With no model set, prompts go to a hosted free model, with no credentials configured |
| pi | 1.4.0, and the driver's 1.5.0 | MIT. User-installed | `pi --mode rpc` | IMPLEMENTED: RPC, first-party MCP, extensions. No ACP in the repository | Passed the full trainable path on a minted key, and native spawning does not exist to reconcile |
| Prime Agent | 0.10.2 | MIT, tarball adds `PHOTON-LICENSE.md`. User-installed. Not on npm or PyPI | After a live probe: `--mode rpc` or ACP | IMPLEMENTED per source. EXPERIMENTAL: Factory. Nothing beyond version and help has run | No capability claim can be made: no model turn was run |
| ACP | Schema 1.29.0, and the v1 schema at crate 1.15.1, read on 2026-11-08, which the ACP driver follows. Python SDK 0.12.1 and 1.0.0rc3 | Apache-2.0. Wheels have no License field, so scanners may flag them. Never bundle the Claude or Codex adapters | `AcpDriver`, protocol 1, a driver of the SDK's own | IMPLEMENTED: v1 stable, where at crate 1.15.1 `systemPrompt` on session setup, sent only to an agent that advertises it, is in the stable schema, as it was not at schema 1.29.0, beside the compaction updates, sent only to a client that advertises them. EXPERIMENTAL: `session/fork`, `subagent_update`, `providers/*`, `mcp/message` and more. DRAFT: v2 | Stable v1 has no mid-turn message, sender identity, idempotent prompt or model-call attribution |
| MCP | Spec revision 2026-07-28. Python SDK 2.3.0 | Spec Apache-2.0, MIT in transition, docs CC-BY-4.0: attribute quoted docs. Python SDK MIT | Tool plane, through our own stdlib server | IMPLEMENTED: revision 2026-07-28 is current. `draft` has no changes | Real clients settle on older revisions: Codex `2025-06-18`, Claude Code `2025-11-25` |
| [DeLM](https://github.com/yuzhenmao/DeLM) | Commit `66617616e708` | MIT. Pattern only, credited here | Pattern reference | IMPLEMENTED: research runner. Read, not executed | State is a fold over one append-only events table, and a claim is one `BEGIN IMMEDIATE` transaction |
| [Agensh](https://github.com/microsoft/Agensh) | Commit `d6063b9086d5` | MIT. Pattern only, credited here | Pattern reference | IMPLEMENTED: research harness on Docker Compose. Read, not executed | Mid-turn notices are appended to tool results, which needs no harness patch. Its `CLAIM` is advisory |
| GitSwarm | arXiv 2610.04862v1 | No license in the repository. Paper CC BY 4.0 per PDF metadata, unconfirmed. Pattern reference only: our own code, credited | Pattern reference | DOCUMENTED-ONLY: the repository is a website, not the system | `informed_by` is declared, not causal. That is the split our evidence types keep |

## 2. Protocol pins

| Protocol | Pin | Negotiation rule | Refuse |
|---|---|---|---|
| **ACP** | Protocol `1`, schema v1 at crate 1.15.1. The ACP driver speaks it over our own `Peer`, so no ACP package is pinned: the lock holds `agent-client-protocol` 0.12.1 only as `openhands-sdk`'s dependency | Send `protocolVersion: 1` once per connection. An agent that supports it echoes it, otherwise it answers its own latest. Disconnect on anything but `1` | v2 unless an explicit experimental flag is set. An unstable feature unless it has its own opt-in, a capability check, a version guard and a fixture. Negotiating v1 implies none of them |
| **MCP** | Handshake era: `2025-11-25` and `2025-06-18`. Core tools use `2025-06-18` semantics. Our stdlib server, not the `mcp` package | Answer `server/discover` with -32601, so clients fall back to `initialize`. Answer `initialize` with the client's version when it is one of those two, and with `2025-11-25` otherwise. Observe the settled version per connection | Sessions, SSE and `GET` or `DELETE` (405). Undeclared arguments return `isError: true`. Identity from `clientInfo`, `_meta` or arguments |
| **Driver wire** | `protocol: 2`. Line-delimited JSON-RPC 2.0 on stdio, split on LF only, logs on stderr | `describe` and `start` carry one integer, `WIRE_PROTOCOL`. An unknown one is refused with -32002. There is no range and no fallback | Any verb outside the seven `Driver` methods. An unknown report frame becomes `native` plus a gap, never a log line |

Consequences:

- **ACP.** We advertise `fs: false` and `terminal: false`: both are stable in v1 and removed in v2. An echoed version proves
  nothing, since `openhands acp` returned 99 when asked for 99. Capabilities omitted are unsupported. Claude and Codex
  adapters already parse the v2 `initialize` shape, so v1 lifecycle assumptions stay inside the driver.
- **ACP SDK.** Unknown `sessionUpdate` kinds are dropped in the notification handler and the client never sees them.
  `observers` run before parsing, so a client could keep raw frames there.
- **MCP.** Revision 2026-07-28 makes `server/discover` mandatory to implement, so our server does not claim that revision. A
  modern-only client cannot reach it. Neither real client needs that. Modern-only features (multi round-trip results,
  `subscriptions/listen`, tasks) carry no core semantics.
- **Dependencies.** The core SDK depends on neither `mcp` nor `agent-client-protocol`. `openhands-sdk` 1.59.0 is unsatisfiable
  with `mcp` 2.3.0 or `agent-client-protocol` 1.0.0rc3, and unpinned it resolves silently to 1.49.1 and 1.44.1. The
  `openhands` extra pins `openhands-sdk==1.59.0` and `openhands-tools==1.59.0`, so an environment with the extra holds OpenHands'
  pins, and one that cannot runs the worker from an environment of its own, as a wire command. `litellm`, which the worker
  imports too, is not pinned: it floats in the range `openhands-sdk` asks, `litellm>=1.93.0,<1.106`, and every test here ran on
  1.105.7.
- **Harness versions.** Exact, user-installed, shown by `doctor`, checked on your machine by `doctor --check`, which keeps what it
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
Unknown is not no. Each row holds at the version it names. Of these rows only Claude Code's and Codex's rest on a real model,
and OpenCode met one only by accident; pi and OpenHands have run on one since, through their drivers, as Driver status says.

| Adapter | Launch | Streaming | Tool injection | Messaging | Interruption | Approvals | Resume | Native subagents | Model endpoint | Exact call attribution | Training eligibility |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **claude** 2.1.316 | yes. `claude -p` stream-json, stdin held open. User installs and logs in [R] | yes. Subagents gave no partial events; `assistant` output tokens are a placeholder [R] | yes. HTTP MCP, needs `alwaysLoad` or tools defer. `system/init` does not prove visibility [R] [L] | yes. Stdin across turns [R]; absorbed at a tool boundary or next turn [L] | yes. Receipt in 22 ms; the aborted call's tokens go unrecorded [R] | yes. `can_use_tool`; `stdio` value is SDK-private; read-only commands skip it [R] [L] | yes. `--resume`, 1 cold trial; needs a persisted transcript [R] | partial. Observed, identity `inferred` [R]. Agent teams add no tool in `-p` [L] | partial. Base URL plus credential [L]. Non-Claude models unsupported upstream [S] | partial. `toolUseId` equals the model id [R]. Native: none. Gateway join exists but no call records [L] | **no.** Gateway run exits 1 with zero records; training on it stays blocked, as section 8 says [L] |
| **codex** 0.164.0 | yes. `codex app-server`, labelled Experimental upstream [R] | yes. `item/*`, deltas; `item/completed` is truth [R] | yes. Per thread, needs `omit_tools_from` and an approve mode [R] | yes. `turn/start`, `turn/steer` with `expectedTurnId`; next model call [R] | partial. `turn/interrupt` [R]; running children continue [L] | yes. Server requests [L]. Set `approvalsReviewer`; `accept` does not fix the outcome [R] [L] | yes. `thread/resume`, 1 cold trial; resend config [R] | partial. v1 and v2 observed, identity `inferred`, no `thread/started` for a child [L] | yes. `model_providers`; `responses` only. Thread scoped at 0.164.0; from 0.167.0 a thread runs on its app-server's provider alone [L] | partial. Thread and turn only on stable. `callId` joins to the `exec` script, not a call [R]. Exact per key at a gateway [L] | **no.** Identity passes, but MCP tools never reach the policy [L] |
| **pi** 1.4.0 | yes. `pi --mode rpc`; Node >= 22.19 [L] | yes. `message_end` is authoritative; a stalled reader stalls pi [L] | yes. MCP with `exposure: direct`, on a stdio server, and over HTTP on our real tool server at 1.4.0 and 1.5.0 [L] | yes. `prompt`, `steer`, `follow_up`; turn boundaries [L] | yes. `abort`, then `agent_settled {aborted: true}` [L] | partial. None native. A probe gate worked; we would ship one. Not a security boundary [L] | yes. `--session <id>` with full history [L] | no. None by design; extensions can add them [S] | yes. `models.json`, one agent dir per agent [L] | partial. Agent level by key. `message_end` carries the model's `responseId` over RPC, at 1.4.0 and 1.5.0, on a fake model. No MCP anchor [L] | candidate. Full path passed on a minted key. Platoon has no pi spec [L] |
| **openhands** SDK 1.59.0 | yes. SDK `Conversation` under `arun()`; import 8-11 s on network storage, 10 s on local disk. The wire worker drives it [L] | yes. Needs `stream=True` and a token callback; children never stream [L] | yes. MCP per `Agent`, tool in the prompt, on a stdio server, our shim among them. HTTP with a bearer in `headers` worked on FakeTools in a probe. A failed start is silent [L] | yes. `send_message`, next model request; log order misleads [L] | yes. `interrupt()` abandons the call in 0.05 s; a gateway may have recorded it [L] | partial. Confirmation policies. No pending event; lone `finish` and `think` skip it [L] | yes. Same id, fresh `Agent`. Key resupplied; tools cannot be removed [L] | partial. `task`, opt-in. No child events reach the parent [L] | yes. `LLM(...)`; unrequested fields sent [L] | yes. `llm_response_id == call_id` per action on a scoped key. A native child is exact only with a keyed factory. Extra calls share the endpoint [L] | **yes, on a profile.** Exact records and datums on a minted child, SDK 1.59.0 and a scripted policy. Platoon's own 1.54.0 spec has no MCP, and its live test did not run. Condenser, delegation and long runs untested [L] |
| **opencode** 2.2.5 via ACP | yes. `opencode acp`, private server per process [L] | partial. `session/update`; less detail than HTTP [L] | partial. `mcpServers` landed behind Code Mode, even with `codemode: false` in config [L] | partial. Turn boundary. A second prompt fails -32603 [L] | yes. `session/cancel`, stop reason `cancelled` [L] | partial. `session/request_permission`, only under an `ask` rule. No rule, no ask [L] | unverified. Advertised, not exercised over ACP [L] | partial. Child sessions seen on HTTP [L]; ACP updates need opt-in [S] | yes. `OPENCODE_CONFIG_CONTENT`; reaches the tool shell. Always pin a model [L] | partial. Session level by header, one credential per process; title calls unlabelled [L] | unknown. Untested through the gateway. Title calls would train as `policy` [U] |
| **prime** 0.10.2 | unverified. Version and help ran; no model turn. Needs `uv` and Python [S] | unverified [S] | unverified. Through the Python REPL [S] | unverified. `steer`, `follow_up` on RPC [S] | unverified. Children and kernels must stop too [S] | no. None in the crates [S] | unverified. CLI only in source; ACP `load_session: false` [S] | unverified. `rlm.spawn`, reported by the harness [S] | unverified. `models.json` [S] | unknown. No parent header found; kernel calls unknown [U] | unknown. No live probe [U] |
| **generic ACP**, protocol 1 | yes. Baseline required of every agent [S]; SDK checked on a fake agent [L] | partial. 14 stable update kinds; the SDK drops unknown ones [S] [L] | unverified. `mcpServers`, stdio mandatory. Visibility varies by agent [S] | unverified. Next turn. A second prompt mid-turn is undefined [S] | unverified. `session/cancel` is baseline. `openhands acp` maps it to `pause()` [S] | unverified. `session/request_permission` is a baseline client method. Whether an agent asks is per agent [S] | unverified. Only if advertised [S] | no. Stable has none; `subagent_update` is unstable [S] | no. `providers/*` is unstable [S] | no. `toolCallId` only [S] | no. Only through a gateway, per agent [S] |
| **generic exec**, one-shot | unknown. Any command [U] | unknown. Stdout only, no structured events [U] | unknown. `ph` on `PATH`; a sandbox may block it [U] | no. No input after launch; cannot park [S] | unknown. Process group only [U] | unknown. No answer path in the design [U] | unknown. Depends on the command [U] | unknown. Opaque [U] | unknown. Whatever the command accepts [U] | unverified. Exact only if it uses its own key alone [S] | unknown. Per command; Platoon admits a custom agent on its own key [S] |

### Driver status

Each driver's state is the one [STATUS](../STATUS.md) gives it. Conformance is `check_driver` on FakeModel, and a check is skipped
for what a driver does not declare.

| Driver | Path | Depends on | Driver status | Checked on | A real model | Conformance result |
|---|---|---|---|---|---|---|
| `claude` | Stream-json plus control protocol | User's binary | experimental | 2.1.322, and 2.1.316, 2.1.318 and 2.1.319 before | `claude-haiku-5-5` on a plan login, in its live tests | 27 passed, 0 failed, 4 skipped: it is persistent, declares no sealed launch (2), and no check proves `coverage`. Operational and observable met |
| `codex` | `codex app-server` over stdio | User's binary | experimental | 0.167.0, and 0.164.0 | `gpt-6-luna` on a plan login, in its live tests | 25 passed, 0 failed, 5 skipped: it has no id per model call, is persistent, declares no sealed launch (2), and no check proves `tool_timeout_s`, `coverage` or `sandboxes`. Operational and observable met |
| `pi` | `pi --mode rpc` | User's install | experimental | 1.5.0 | DeepSeek V4.1 Flash on a key, in the examples' live tests | 26 passed, 0 failed, 4 skipped: it has no native children (2), is persistent, and no check proves `tool_timeout_s` or `coverage`. Operational and observable met, and trainable on a gateway login, from its sealed checks on FakeModel acting as a gateway |
| `openhands` | `WireDriver`, worker `python -P -m platoon_harness.drivers.openhands` on SDK `arun()` | `[openhands]` extra | experimental | SDK 1.59.0 | DeepSeek V4.1 Flash on a key, in the examples' live tests | 26 passed, 0 failed, 4 skipped: it sends no anchor, its native children are opaque, it is persistent, and no check proves `tool_timeout_s` or `coverage`. Operational and observable met, and trainable on a gateway login, from its sealed checks on FakeModel acting as a gateway; never for a role that allows its own agents, as they are opaque |
| ACP | `AcpDriver(command)`, protocol 1 over our own `Peer` | The SDK | experimental | Protocol 1, on `tests/conformance/acp_agent.py`, `ScriptedDriver` behind ACP | None. No real ACP agent has passed its checks: OpenCode 2.2.6, run by hand on 2026-11-08, failed 7 of 18 (next row) | 19 passed, 0 failed, 12 skipped: it declares no boundary inside a turn, no measures, no id per model call, no dialect (3), no way to turn native children off or see them (2), no one-shot exit, no sealed launch (2), and no check proves `coverage`. Operational and observable met, never trainable. Stable ACP neither shows an agent's own agents nor turns them off, so `allow_native_children = false` cannot be carried out: a role on an ACP harness must allow them, and `team check` refuses it otherwise |
| `opencode` | `opencode acp`, through `AcpDriver` | User's install | implemented | 2.2.6, by hand on 2026-11-08 | None | 11 passed, 7 failed: it reaches FakeModel past `initialize`, starts on its pinned model, which a role names as OpenCode does, `fake/fake-model`, takes delivered text, ends, resumes and stops its turns, and reports a malformed frame as a gap; it failed our tool in the first request, the shell checks, approvals and the interrupt, because OpenCode's first request is a title of the session that it asks of the model on the side, with no tools, and because it shows an MCP server that `session/new` gives it only through its `execute` tool, Code Mode, not as a tool of its own. Giving it our server in its configuration with `codemode: false`, and expecting its title call, are not built. As on any ACP harness, a role on it must allow its own agents, which its `subagent` tool starts |
| `prime` | Decided after a live probe | User's install | planned | None | None | None |
| `exec` | One-shot command, `ph` only | Nothing | tested | No version: `tests/conformance/one_shot.py`, a command that asks FakeModel once | None | 6 passed, 0 failed, 24 skipped, each for what a one-shot does not say, declare or get |

### SwarmChat on our backend

`platoon-harness web` serves SwarmChat 0.1.0's five page files, each held to its SHA-256 as `web` starts, over a projection of
the journal, and answers the `view_*` requests the page makes, which are SwarmChat's internal shape and unversioned upstream, so
the pin is exact and an upgrade is deliberate work: new hashes, and the shape and browser tests run again
([web.md](../how-to/web.md), [RFC 0027](../rfcs/0027-the-browser-on-our-backend.md)).

## 4. Operational, Observable, Trainable

Levels are computed per agent from what was verified, and no driver can claim one (architecture §9.4). This table is the ceiling
upstream allows today, not a computed level. A training system still decides what trains.

| Adapter | Operational | Observable | Trainable |
|---|---|---|---|
| `claude` | **Yes.** Control, tools, interrupt, approvals and resume all ran on a real model | **Yes, with gaps.** Stable ids across stream and hooks. No token ids or logprobs, thinking text unreliable, aborted calls unrecorded, shell reads blind, children need `--forward-subagent-text` | **No.** Native login never. Through Platoon: `Unsupported message role 'system'`, exit 1, zero records. No Platoon spec. Anthropic does not support non-Claude models behind a gateway, and training on it stays blocked, as section 8 says |
| `codex` | **Yes, with a guard.** Tools need `omit_tools_from`. A turn that ends with no required `wait` must be flagged, since the default failure was silent | **Yes, with gaps.** Items and per-thread usage are good. No response id on stable. Review, compact, memory and Auto-review work are hidden. Tool-to-call links stop at the script | **No.** Exact calls land on a minted key, but the gateway's Responses dialect drops `namespace` and `custom` tools, so MCP tools never reach the policy. The shell could not reach loopback under `workspace-write` (1 trial), and Unix sockets from that shell are untested. So no coordinated path is known in that sandbox. No Platoon spec |
| `pi` | **Yes,** on loopback, and on a real model in the examples' live tests. Approvals are an extension we ship, which is no boundary | **Yes on loopback.** Assembled prompt visible, clean call profile, compaction named. A queue does not survive a kill. A tool call joins the model call that chose it through `pi/toolCallId` | **Yes, sealed, on FakeModel acting as a gateway.** Its sealed launch passes both sealed checks at 1.5.0: no built-in tool, nothing of the user's, our tools and the environment's, each body id its call id. Each compaction call, one or two, carries the gateway's headers through our extension and is reported with its id. No real model has met its sealed launch |
| `openhands` | **Yes,** on loopback, and on a real model in the examples' live tests. A worker process per agent. Assert the tools appear in `SystemPromptEvent.tools`, or fail the spawn | **Yes on loopback.** Best record: `llm_response_id`, `Condensation` with forgotten ids. Children visible only on disk after the fact | **Yes, sealed, on FakeModel acting as a gateway, at 1.59.0.** No coding tool, `num_retries` 0, `api_mode="chat"`, native delegation off, our tools and the environment's beside `finish` and `think`, the environment's named by its server as `environment_<tool>`, since a bare `finish` of TextCraft's collided with OpenHands' own and was refused at launch, and the condenser's every call carrying the gateway's headers, reported as `compaction` with its id. Subscription or Cloud auth never |
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
distinct name. **Unsupported** means it is unavailable on this path, with a reason. **Not determined** means nobody has looked.

| Harness | Surface | Mode | Interaction |
|---|---|---|---|
| `claude` | Project instructions | Passthrough | Omitting `--setting-sources` loads `CLAUDE.md` and rules. Ours goes in `--append-system-prompt-file`, never `--system-prompt` |
| | Native skills | Passthrough | The same switch. Built-in skills stay listed with empty sources: 20 in the probe. A forked skill uses a `forked-command-` prefix, not a tool id |
| | Slash commands | Passthrough, partial | `initialize` returns the command list. `/compact` ran over stream-json [L]. Other commands: not determined. A goal that starts with `/` is refused, as a model may have written it: `/clear` began a new session, which left the agent's id stale, `/compact` read as a turn that stopped, and a leading space or line made it plain text [L] |
| | Tool configuration | Namespaced | Ours arrive as `mcp__<ns>__<tool>` and are pre-approved by `--allowedTools`. The user's servers stay |
| | Hooks | Passthrough | User hooks still run, and we register none. A known limit: a headless harness shows no trust dialog, so a project's own hooks and `.mcp.json` run as they would under `claude -p`, in an untrusted folder too |
| | Auto memory | Passthrough | A user's memory for a project reached the first request under the driver's launch, as it does under `claude -p` [L] [R] |
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
| | Hooks | Passthrough, restricted in training | No hooks as such: extensions on `tool_call`, which keep working beside our gate [L]. User extensions can add subagents or alter calls. A sealed launch keeps everything of the user's out, as section 4 says. A known limit: `--mode rpc` shows no trust prompt, so `.pi/` resources load only under a saved decision or `defaultProjectTrust: "always"`, as they would for `pi -p`. Both ran. Outside a sealed launch the driver passes neither `--approve` nor `--no-approve` [L] |
| | Native subagents | None in core; an extension's cannot be turned off | A user's extension can add a tool for agents of its own. Nothing of ours turns it off, and its children go unseen [S] |
| | Session compaction | Passthrough, exact | `compaction_end` names `firstKeptEntryId`, `get_entries` turns that into `forgotten`, and the summary is kept [L]. Purpose is on our `model.call` and unlabelled at a gateway |
| `openhands` | Project instructions | Passthrough | `Agent()` ignores them, so the worker sets `AgentContext(load_project_skills=True)`, as OpenHands' CLI does, which loads `.cursorrules`, `AGENTS.md`, `AGENT.md`, `CLAUDE.md` and `GEMINI.md` from the workspace and the repository's root. A project's `AGENTS.md` reached the first request beside ours, which are `system_message_suffix` [L]. The choice is the driver's and no role's, so the resolved team holds nothing of it. A sealed launch turns it off |
| | Native skills | Project skills only | A project's `.agents/skills` load with its instructions. The user's own, in `~/.openhands/skills`, and public skills, which fetch from GitHub, stay off, as the SDK's defaults are, where OpenHands' CLI loads all three |
| | Slash commands | Not determined | Found only in the CLI's TUI, which the worker does not run. `openhands acp` sends `available_commands_update`. The SDK path was not researched |
| | Tool configuration | Ours by their own names | Our server, through the stdio shim, is the agent's one `mcp_config` entry, as the SDK reads no user's server, and its tools show unprefixed, so `tool_names` is `bare` [L]. Whether one can collide with a built-in: not determined. A child inherits our server and calls it on its parent's token |
| | Hooks | None | The SDK loads no hooks file, `.openhands/hooks.json` being the CLI's, and the worker passes no `hook_config`, so a user's hooks do not run. A `Stop` hook could deny finishing and inject feedback [S] |
| | Native subagents | Off unless a role allows them | `task` and `delegate` are absent by default [L]. Allowed, `task` starts OpenHands' built-in kinds, each step asking the runtime through the task tool's confirmation handler [L]. A child is unseen: none of its events reaches the parent and no observation names it, so it is the gap `native_child_unattributed`, its spending its parent's at `tree` [L]. An interrupt stops a child at its next ask [L]; the task tool checks no cancellation, so until then the child calls the model on. A project's agent file that says `permission_mode: never_confirm` makes a child that asks nothing, which an interrupt then never stops, as the file is the user's [S] |
| | Session compaction | Passthrough, exact | `Agent()` has no condenser, so the worker gives it OpenHands' default one, as its own default agent has, which forgets past 80 events. `Condensation` names `forgotten_event_ids`, so `compacted{forgotten}` is exact [L]. Through the gateway: untested |
| `opencode` | Project instructions | Not determined | Not researched |
| | Native skills | Not determined | Exists in its TUI. Reach over ACP was not researched |
| | Slash commands | Not determined | Reach over ACP was not researched |
| | Tool configuration | Namespaced, partial | `mcp.servers.<name>` in `OPENCODE_CONFIG_CONTENT`, with `codemode: false`. Ours then arrive as `<ns>_<tool>`. Servers passed in `session/new` did not appear as direct tools. Secrets there reach the tool shell. The ACP driver passes ours in `session/new` and declares `namespaced`, so our words name them `mcp__<ns>__<tool>`, as its check calls them, which no run has checked |
| | Hooks | Not determined | Plugin hooks exist, some experimental. Interaction was not researched |
| | Native subagents | On, and a role on it must allow them | Its `subagent` tool starts child sessions [L on HTTP]. Through ACP the driver can neither turn them off nor see them, so a role on `opencode` must say `allow_native_children = true`, and `team check` refuses it otherwise. Whether a permission rule in `OPENCODE_CONFIG_CONTENT` takes the tool away is not determined |
| | Session compaction | Not determined | `POST /compact` made two extra model calls; success was not observed. `session.compacted` was removed upstream. ACP behavior was not researched |
| `prime` | Project instructions | Not determined | Source only |
| | Native skills | Not determined | Skills ship in the repository. Native peer messaging, with a daemon-derived sender, overlaps our messaging: pick an owner per run |
| | Slash commands | Not determined | `/factory on` exists. Reach over RPC or ACP was not researched |
| | Tool configuration | Not determined | `mcpServers` or ACP `session/new`. The model reaches MCP through `mcp.call_tool` in Python, so direct visibility is unverified |
| | Hooks | Not determined | None found |
| | Session compaction | Not determined | `compact` is an RPC command. Not run |
| Generic ACP | Project instructions | Passthrough | The agent keeps its own files. Ours go as `systemPrompt` where the agent advertises it, stable at crate 1.15.1, and otherwise before the first prompt |
| | Skills, slash commands | Not determined | `available_commands_update` is a stable update. How to invoke them is per agent |
| | Tool configuration | Per agent | `mcpServers`, re-supplied on resume with a fresh token. Name prefixing is per agent |
| | Hooks | Not determined | None found in ACP's surface |
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

What the queries make of it (architecture §11): a Claude Code or pi tool call joins the model call that chose it, so an answer
about an event it made is bounded at that call, `call`. A Codex tool call reaches its script's item and no call, and an OpenHands
or `exec` one reaches nothing, so theirs are bounded at the event's commit, `commit`, which can count a read the same model call
chose as below. A compaction is `unsaid` on Claude Code and Codex, which name nothing they forgot, on OpenHands, whose delivered
inputs carry no id, and for every read; on pi it is `forgot` or `kept` for a handover. Each of these ran on the real binary against
FakeModel, a read then a cited write [L]. `spans` and `propagate@4` ran on pi 1.5.0 and OpenHands 1.59.0 against FakeModel [L], but
no agent claimed a task there, so a span's claims and labels, and `propagate@4`'s sharing of a claim's credit, ran on neither. No
real binary has shown a turn cut at a write, so the cuts in the last column are inferred [S]. A read through `ph` stays
unconfirmed on every harness, and is labelled so: neither Claude Code 2.1.316 nor pi 1.5.0 hands a shell command the id of the
call that runs it [L], and Codex's was not checked. No stored conformance result proves a surface yet, so a negative answer is
`unknown` on each. A read a Codex script made is said to have returned to that script, which may never have shown it to the model.

### Workspaces

What each harness sees in a worktree of its own ([workspaces.md](../how-to/workspaces.md), RFC 0031). Git 2.47.3 is the only
version run; [V] verified here, [S] read in source, [U] unverified. In a snapshot each sees the same, but that the repository's own
`.git/hooks` are new and empty there, while a `core.hooksPath` your global or system config sets still runs for an agent's commits
[V].

| Harness | In a worktree |
|---|---|
| Claude Code 2.1.316 | Offers `EnterWorktree` and `ExitWorktree` in its first request, which the driver turns off on every launch, and takes `--worktree`, which nothing passes [V]. Reads the tracked `CLAUDE.md` and skills there; an untracked `CLAUDE.local.md` is absent [V], and `.claude/settings.local.json` and untracked skills are too [U]. Its auto memory is keyed on the repository, so every worktree of one shares it, a channel no topology binds [V]. It commits there and resumes in the same folder on FakeModel and on a real model [V]. After a commit on a real model it sent `system/vcs_state_changed`, a frame the driver does not know, journaled as `native` plus the gap `unknown_update` in live runs [V], in a snapshot too |
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

By git's release notes, not run: `--path-format` arrived in 2.31, `worktree add --reason` in 2.33 and `worktree list -z` in 2.36 [S].
Git other than 2.47.3, macOS, a case-insensitive filesystem and a repository past 100,000 files or on Lustre are [U], as section 8
says.

### Tool calls at once

What each harness ran at the same time on FakeModel, measured with calls that each end only once the others are running too, or
once one has waited alone, 15 s for the two calls of one response. Several agents' tools ran at once on every harness, on Claude
Code 2.1.319, Codex 0.167.0, pi 1.5.0 and OpenHands SDK 1.59.0 [L]: three agents' shell calls, one each, ended only once all three
were running, and three agents' calls of a query of ours, one each through its harness's own client of the one tool server they
share, ended only once all three were in it. The calls of one response are each harness's to schedule, and each row is one run
on 2026-11-08, with the approvals the harness asked for each two, under a role that allows them all [L]:

| Harness | Two commands that run a script | Two `cat`s of named pipes | Two calls of a query of ours |
|---|---|---|---|
| `claude` 2.1.319 | In turn: it asked an approval for each, and began the second once the first had ended | At once, asking none | At once, asking none |
| `codex` 0.167.0 | At once, asking none, with the shell unsandboxed, as `workspace-write` refused the script an internet socket | At once, asking none | At once, asking none |
| `pi` 1.5.0 | At once, asking an approval for each | At once, asking an approval for each | At once, asking none |
| `openhands` SDK 1.59.0 | In turn, asking one approval for the two | In turn, asking one approval for the two | In turn, asking none |

`test_several_agents_run_their_shell_tools_at_once`, `test_several_agents_call_our_tools_at_once` and
`test_what_one_response_runs_at_once`, in each harness's file under `tests/integration/`, hold these. Why Claude Code ran the
scripts in turn and the `cat`s at once, the approvals it asked or the commands themselves, is not determined; pi asked an approval
for each of its two and ran them at once all the same. A query of ours is listed with `readOnlyHint: true`.

OpenHands runs one response's calls in turn because our worker keeps the SDK's `tool_concurrency_limit` at its default of 1 [S].
Raising it is ours to do and is not done, as it changes the order in which the calls of one response run, an environment's
among them. Above 1, the SDK would still run two terminal calls in turn, as its subprocess terminal is one session, and two calls
of one MCP tool, which declares no resources [S]; different tools, such as a query of ours beside a terminal command, would run at
once. Nothing here has run it so.

Two calls of ours that write were not tried at once: none of them blocks but a held `wait`, and an agent's second `wait` replaces
its first. A harness's tools other than its shell and ours were not tried.

## 6. Supported platforms

The initial release runs on **Linux** alone: nothing has run on macOS, Windows or WSL. This table says where each part has run;
[STATUS](../STATUS.md) says what is built and tested.

| Component | Linux | macOS | Windows | WSL |
|---|---|---|---|---|
| Kernel and journal | **Tested.** Unit tests, including SIGKILL. A benchmark of the journal had 0 violations in 226,807 acked commands over 40 kills ([RFC 0002](../rfcs/0002-one-journal-per-session.md)). Power loss not tested | **Not run.** Needs `fullfsync=ON` and `checkpoint_fullfsync=ON`. `F_FULLFSYNC` latency is unmeasured and decides the 50 ms mark | **Not a target.** Not run. The design uses `flock`, Unix sockets and process groups | **Not run.** Linux rules inside the distro filesystem. `/mnt/c` is 9p and refused |
| Control socket | **Measured.** Python `bind` allows 107 bytes | **Not run.** 103 usable, from headers | Not run | Not run |
| Filesystem detection | **Exercised:** xfs, tmpfs, Lustre, FUSE control, `proc`, symlinks. Other magics come from headers | **Not run.** Written from the man page | Not run | 9p magic known, not exercised |
| TUI | **Tested.** Textual 8.2.8 under Pilot, and `platoon-harness attach` on a real PTY read through `pyte`. Real terminals, tmux and SSH have not been measured | Not run | Untested: the tests use Unix `pty` | Not run |
| SwarmChat client | **Tested** on our backend, reading and acting, in Playwright 1.64.1's Chromium headless shell, revision 1248, and its Firefox 157.0, revision 1555, headless, on Linux x86-64, on scripted harnesses and the real `claude` binary against FakeModel, and in Chromium on real models in a live test. **Tested in WebKit on GitHub's runners:** CI's `e2e` job runs the suite once in each of the three, headless on GitHub's Ubuntu 24.04 x86-64 runners on scripted harnesses, and in each it passes whole, but the one test that needs `claude`, WebKit as Playwright's WebKit 27.2, revision 2370. That build needs glibc 2.38 or later, so WebKit has run only there. A headed browser is untested. A phone's screen, 390 by 844 px with touch, is emulated, and no phone has run the page | Not run by us. Upstream runs `unittest` only | Not run by us. Upstream runs `unittest` only | Not run |
| Claude Code, Codex | **Real model** on x86-64 | Not run. Seatbelt not tested | Not run | Not run. Codex's sandbox does not support WSL1 |
| pi, OpenHands | **Real model** on x86-64, in the examples' live tests | Not run | Not run | Not run |
| OpenCode | **Loopback** on x86-64 | Not run | Not run | Not run |
| Isolated workspaces | **Experimental.** The `bwrap` extension, its escape tests passing on Claude Code, Codex, pi and OpenHands against FakeModel, on one Linux host with bubblewrap 0.4.1. Its fast tests also pass on GitHub's Ubuntu 24.04 runners with bubblewrap 0.9.0 | **Not given.** No provider, and it is refused before any cost | Not a target | Not run |

Performance on Linux, from the journal's benchmark ([RFC 0002](../rfcs/0002-one-journal-per-session.md)): at 500 events per
second with 100 simulated agents, ack p99 was 2.8 ms on local NVMe. Those are server disks with near-instant flush, so they do
not stand in for a laptop. Ack p99 is at least twice the sync time, so a sync above about 20 ms misses the 50 ms mark.

| Prerequisite | Requirement |
|---|---|
| `platoon-harness` | Python 3.12+ |
| `claude`, `codex` | User-installed binary |
| `opencode` | `@opencode/cli`, platform binary, no Node at runtime. Check the major version: bins are `opencode` and `opencode2` |
| `pi` | Node >= 22.19 |
| `openhands` | The `openhands` extra, in the runtime's environment or, run as a wire command, one of its own: Python 3.12+. The OpenHands CLI needs Python 3.12 alone and is not used |
| Codex sandbox on Linux | Bubblewrap and user namespaces. A bundled `bwrap` is the fallback. With user namespaces blocked, sandboxed commands cannot run (docs, not reproduced). Never fall back to `danger-full-access` silently |
| `isolated` workspaces | The SDK's `bwrap` extension: Linux, `bwrap` on `PATH` and unprivileged user namespaces, which a kernel setting, AppArmor or a container's seccomp can block, and which its probe says before any cost. Run on bubblewrap 0.4.1 alone. No provider for macOS |

## 7. Auth and terms

This is engineering policy, not legal advice.

| Profile | What it is | What we do | Levels |
|---|---|---|---|
| **Native login** | The harness's own sign-in, made by the user through its own flow | Spawn the user's binary on the user's machine, with no credential added. `doctor` shows only whether a login exists and which kind. Each harness signs itself in | Operational, Observable |
| **Plan login** | A native login on a subscription | The same, for that user's own work. Headless multi-agent exits 78 and names the fix unless the user opts in, and `web` serves a session on a plan login on loopback alone, as [the web guide's Security](../how-to/web.md#security) says | Operational, Observable. Never Trainable |
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

The terms this reads, retrieved 2026-11-02: Anthropic's
[Claude Code legal and compliance](https://code.claude.com/docs/en/legal-and-compliance) page, its
[Agent SDK overview](https://code.claude.com/docs/en/agent-sdk/overview), its
[LLM gateway](https://code.claude.com/docs/en/llm-gateway) page, and its
[Consumer Terms](https://www.anthropic.com/legal/consumer-terms) and
[Commercial Terms](https://www.anthropic.com/legal/commercial-terms); and OpenAI's
[CI/CD authentication](https://learn.chatgpt.com/docs/auth/ci-cd-auth.md) and
[Codex authentication](https://developers.openai.com/codex/auth) docs. OpenAI's terms were read only through search snippets and
are unverified. Its docs state no general rule for third-party tools, so spawning the user's own `codex` under its own login
rests on a reading of them: app-server and the SDK are published for this, and the user's process holds the credential.

**Open reading.** The docs describe `claude -p` for scripts, and the Consumer Terms allow automation "where we otherwise explicitly
permit it". "Ordinary, individual usage" is undefined, so a swarm on one login may exceed it. That is why headless multi-agent on a
plan login needs an explicit opt-in, and why we recommend an API key for teams, unattended runs and anything hosted.

## 8. Known unknowns

**Open questions.**

- Prime Agent is not driven yet: nothing beyond its version and help has run.
- Training through Claude Code against a non-Claude policy: its system prompt and tool descriptions would enter datasets. Blocked until decided.

**Terms and licenses.**

- OpenAI's terms, read only through search snippets, need review from the source.
- Concurrency of one plan login across many processes is unknown for both Claude Code and Codex.

**Harness behavior not measured.**

- Stronger models and long tasks: parking used cheap models, low effort and an instruction to stop.
- A natural overrun past `wait`: no model has ignored it unprompted, and the design leaves the wait open.
- Long parks: nothing parked beyond seconds. Cache cost after expiry, long blocking `wait` calls and client tool timeouts are untested.
- Fallback, cold resume, token exclusion, slow init and shell socket are 1 trial each.
- Several agents in one `codex app-server`, with distinct tokens.
- Codex child agents on a real model past one trial, and v1 on a real model: v2 ran once through the driver.
- A Codex child that stays under a Codex lead, past one trial: a lead and its helper passed once, after a run whose lead sent its
  follow-up before the first answer. Told it stayed for the next message, a child twice held a `wait` for its parent instead of
  answering.
- Teams of more than a few agents, and work of more than minutes, on a real model: the examples' live runs are the largest made.
- Auto compaction, a turn that fails and a child's approval on a real Codex model, and a `fileChange` item on one. On FakeModel, which offers no patch tool of Codex's own, Codex 0.167.0 took `apply_patch` run through its shell as a patch, and under a `read-only` sandbox started the item and then asked about it by its id, which `test_a_file_change_approval_on_the_real_binary_carries_its_patch` keeps.
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
- pi past the examples' live runs on DeepSeek V4.1 Flash on a key: an OAuth login, retries, `totalFromProvider`, parallel tool calls on a real model, and steering on a real stream.
- OpenCode: `mcpServers` precedence, repeated prompt `id` retry semantics, and the empty experimental log replay.
- Our HTTP tools server against OpenCode, and against OpenHands through its driver, which takes the shim. Claude Code and Codex have met it, and so has pi, on a fake model, and OpenHands' MCP client with a bearer in `headers` on FakeTools.
- Delivery through `claude-agent-acp` and `codex-acp` past `initialize`, including resume, permissions, `mcpServers`, `env` leak behavior and steering.
- Whether adapter `toolCallId` equals the model tool id, and whether native-subagent MCP calls carry a usable anchor.
- OpenHands past the examples' live runs on DeepSeek V4.1 Flash on a key: its condenser, delegation and long runs, on a real model or through the gateway. A delivery that comes while a tool runs, a child's `task` among them, waits in the worker until the run pauses after that step, so a long tool holds it as long; the worker takes it at once, so the runtime's handover does not wait, and no long tool has been timed. Memory at 100 agents, given 210 MB RSS at import, and one worker per agent.

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
- Real terminal throughput over SSH and tmux, accessibility on an alternate screen, and whether a line `/copy` sends as
  OSC 52 reaches the clipboard in any real terminal, through tmux or over SSH.
- Shell-capable agents at one UID can read each other's tokens through `/proc`. Whether Codex's sandbox blocks that read is unknown.
- Workspaces on git other than 2.47.3, on macOS, on a case-insensitive filesystem, where branch refs differing only in case may
  collide, and on a repository past 100,000 files or on Lustre. Where Claude Code 2.1.316 reports `cwd` in its init frame.
