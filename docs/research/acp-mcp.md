# ACP and MCP: protocol research for platoon-harness

## Inspected

| Project | Commit or version | Date | License |
|---|---|---|---|
| ACP spec (`agentclientprotocol/agent-client-protocol`) | `212f0cace08a`; crate 1.15.0; schema v1 1.29.0; schema v2 2.0.0-alpha.12 | 2026-11-01 | Apache-2.0 |
| ACP Python SDK (`agent-client-protocol`) | clone `9853d8b514d6`; wheels 0.12.1 (2026-08-16) and 1.0.0rc3 (2026-10-12) | 2026-10-29 | Apache-2.0 (LICENSE file; no metadata field) |
| MCP spec | `d0e246ea3c69`; current revision 2026-07-28 | 2026-10-31 | Apache-2.0 for new work, MIT transition, docs CC-BY-4.0 |
| MCP Python SDK (`mcp`) | clone `d7845c073a2b`; wheel 2.3.0 (2026-10-02) with `mcp-types` 2.3.0 | 2026-10-27 | MIT |
| Codex | clone `05c08d765523`; CLI 0.164.0 probed | 2026-11-02 | Apache-2.0 |
| Claude Code | changelog clone `f0b737f94f3b`; CLI 2.1.316 probed | 2026-11-02 | proprietary (LICENSE.md) |
| `@agentclientprotocol/claude-agent-acp` | 0.99.1 (npm, probed `initialize`) | 2026-11-02 | Apache-2.0 (npm, LICENSE); registry says `proprietary` |
| `@agentclientprotocol/codex-acp` | 2.5.0 (npm, probed `initialize`) | 2026-11-02 | Apache-2.0 |
| OpenCode (`@opencode/cli`) | clone `ff90ed91607c`; CLI 2.2.5 probed | 2026-11-02 | MIT |
| OpenHands CLI / SDK | CLI `283c6ac3610f` (1.16.0); SDK clone `988494576218`; `openhands-sdk` 1.59.0 on PyPI | 2026-11-01 | MIT |
| pi | `c9f4c7b9fcd0` (`@earendil-works/pi-mcp` 1.4.0) | 2026-11-01 | MIT |
| ACP registry | CDN `registry/v1/latest/registry.json`, version 1.0.0, 43 agents | retrieved 2026-11-02 | per entry |

Status labels: IMPLEMENTED (default-branch code), DOCUMENTED-ONLY, DRAFT/RFC, EXPERIMENTAL (behind a flag or labelled unstable). `Probe` means run on 2026-11-02 with isolated config directories, dummy credentials, and a local fake model endpoint. No real credentials or paid model calls were used.

## 1. ACP protocol

**Stable version is `1`.** `ProtocolVersion::LATEST = V1` (`acp-spec@212f0cace08a:agent-client-protocol-schema/src/version.rs:39`). The docs tag v1 `Latest` and v2 `Draft` (`acp-spec@212f0cace08a:docs/docs.json:67`, `:124`). v2 "as a whole is still labeled draft" (`acp-spec@212f0cace08a:docs/protocol/v2/migration.mdx:20`).

**Negotiation (v1).** One `initialize` per connection. The client sends its latest supported integer. An agent supporting it echoes it, otherwise it answers its own latest (`acp-spec@212f0cace08a:docs/protocol/v1/initialization.mdx:97`, `:99`). The client must then disconnect if it does not support that answer. Capabilities omitted are UNSUPPORTED (`:109`). Baseline every agent must implement: `session/new`, `session/prompt`, `session/cancel`, `session/update` (`:280`).

Probe: OpenCode 2.2.5 answered `protocolVersion: 1` to a request for `2`. claude-agent-acp and codex-acp already parse the v2 `initialize` shape (they rejected my v1-shaped params at `protocolVersion: 2` with `-32602`, requiring `info`), so v2 is live in those adapters.

### Method and feature status (v1)

Stable means listed in `schema/v1/meta.json` and `schema.json`. Unstable means listed only in `meta.unstable.json` and gated by a Cargo feature (`acp-spec@212f0cace08a:agent-client-protocol-schema/Cargo.toml:29`). v2 has its own flag outside the umbrella (`:46`).

| Item | Status | Gate | In v2? | Verdict |
|---|---|---|---|---|
| `initialize` | IMPLEMENTED | none | reshaped (`info`, `capabilities`) | Depend on |
| `authenticate`, `logout` | IMPLEMENTED | `authMethods`, `auth.logout` | renamed `auth/login`, `auth/logout` | Depend on, behind driver |
| `session/new` + `mcpServers` | IMPLEMENTED | `mcpServers` required in v1 | optional | Depend on |
| `session/load` | IMPLEMENTED | `loadSession` | removed (`session/resume` + `replayFrom`) | Use if advertised |
| `session/resume` | IMPLEMENTED | `sessionCapabilities.resume` | required | Prefer; no replay |
| `session/list`, `close`, `delete` | IMPLEMENTED | `sessionCapabilities.*` | list/close required | Use if advertised |
| `session/prompt`, `session/cancel` | IMPLEMENTED | baseline | prompt response redesigned | Depend on |
| `session/request_permission` | IMPLEMENTED | baseline client method | params reshaped | Depend on |
| `session/set_config_option` | IMPLEMENTED | agent offers `configOptions` | required when offered | Prefer for model and mode |
| `session/set_mode`, `modes` | IMPLEMENTED, deprecated-by-notice | agent offers `modes` | removed | Fallback only |
| `fs/*` | IMPLEMENTED | `clientCapabilities.fs` | removed | Do not build on |
| `terminal/*` | IMPLEMENTED | `clientCapabilities.terminal` | removed | Do not build on |
| `elicitation/*` | IMPLEMENTED in spec | `clientCapabilities.elicitation` | yes | Python SDK marks it unstable, see section 2 |
| `$/cancel_request` | IMPLEMENTED, optional | none | yes | Best effort |
| `session/fork` | EXPERIMENTAL | `unstable_session_fork` | unstable | Gate |
| `session/status`, `set_title`, `archive`, `unarchive` | EXPERIMENTAL | `unstable_session_*` | unstable | Ignore |
| `systemPrompt` on setup | EXPERIMENTAL (RFD Preview) | `unstable_session_system_prompt` | unstable | Gate; would replace instruction injection |
| `providers/*` (LLM endpoint) | EXPERIMENTAL | `unstable_llm_providers` | unstable | Gate; relevant to Platoon gateway |
| `subagent_update`, `session_message(_chunk)` | EXPERIMENTAL (RFD Active) | `unstable_subagents` | unstable | Gate; capture raw |
| `PromptResponse.usage` | EXPERIMENTAL (RFD Draft) | `unstable_end_turn_token_usage` | moves to `state_update` | Gate |
| `plan_update`, `plan_removed` | EXPERIMENTAL | `unstable_plan_operations` | `plan_update` is baseline | Gate |
| `mcp/message` (MCP-over-ACP), `proxy/*`, `auth/status` | EXPERIMENTAL | `unstable_mcp_over_acp`, etc. | unstable | Ignore |
| Protocol v2 | DRAFT | `unstable_protocol_v2`, explicit negotiation | n/a | Never default |

Evidence: `acp-spec@212f0cace08a:schema/v1/meta.json:7`, `:8`, `:14`, `:21`, `:23`, `:28`, `:32`; `acp-spec@212f0cace08a:schema/v1/meta.unstable.json:7`; removals in `acp-spec@212f0cace08a:docs/protocol/v2/migration.mdx:44`; RFD stages `acp-spec@212f0cace08a:docs/docs.json:198`, `:213`, `:239`. Modes are slated for removal (`acp-spec@212f0cace08a:docs/protocol/v1/session-modes.mdx:6`).

**Stable `session/update` kinds (14):** `user_message_chunk`, `agent_message_chunk`, `agent_thought_chunk`, `tool_call`, `tool_call_update`, `plan`, `available_commands_update`, `current_mode_update`, `config_option_update`, `session_info_update`, `usage_update`, `notice`, `compaction_update`, `compaction_summary_chunk` (`acp-spec@212f0cace08a:schema/v1/schema.json:3815`, `:3847`). Unstable adds `plan_update`, `plan_removed`, `subagent_update`, `session_message`, `session_message_chunk` (`acp-spec@212f0cace08a:schema/v1/schema.unstable.json:4621`, `:4781`, `:4797`).

**`mcpServers`.** Stdio is mandatory for agents. HTTP and SSE need `mcpCapabilities` (`acp-spec@212f0cace08a:docs/protocol/v1/session-setup.mdx:399`). `env` and `headers` are defined as credentials: agents SHOULD launch without a shell (`:577`) and SHOULD NOT place the values in updates, errors, `_meta`, history, model context, or command lines (`:579`). That is a SHOULD, so conformance needs a leak test per adapter. `mcpServers` is required on `session/load`, optional on `session/resume`.

**`_meta`.** Custom data goes in `_meta` with reverse-DNS keys; custom methods start with `_`; custom fields at type root are forbidden (`acp-spec@212f0cace08a:docs/protocol/v1/extensibility.mdx:43`, `:117`). Root keys `traceparent` etc. are reserved for W3C trace context (`:37`). `_meta` must not carry credentials (`acp-spec@212f0cace08a:docs/protocol/v1/security.mdx:42`).

**Cancellation.** After `session/cancel`, the client MUST answer pending permission requests with `cancelled` (`acp-spec@212f0cace08a:docs/protocol/v1/prompt-turn.mdx:563`), and the agent MUST finish with stop reason `cancelled` (`:567`). Updates may still arrive before that response (`:578`).

### What ACP cannot express

| Need | Stable v1 | Unstable / extension | Consequence for us |
|---|---|---|---|
| Message an agent mid-turn | Undefined: `prompt-turn.mdx` says nothing about a second `session/prompt` during a turn | v2 lets clients send in any state, but meaning is "up to the Agent" (`acp-spec@212f0cace08a:docs/protocol/v2/prompt-lifecycle.mdx:299`). Extensions: `_session/steering`, `_meta.claudeCode.promptQueueing` | Default injection boundary is the next turn. Steering is an EXPERIMENTAL per-adapter capability |
| Sender identity on a prompt | None | Excluded even in v2 (`acp-spec@212f0cace08a:docs/rfds/v2/prompt.mdx:368`) | Provenance of who said what lives in our journal only |
| Idempotent or retry-safe prompt | None | Excluded (same line) | A crash during prompt delivery is an uncertain effect |
| Native subagent identity | None | `subagent_update` gives child session IDs and links, not policy identity | Native IDs are reconciliation hints, never exact Platoon identity |
| Model-call attribution | None. `usage_update` is context size plus cumulative cost | `usage` on turn end only. Cost must not be added across parent and child (`acp-spec@212f0cace08a:docs/rfds/subagents.mdx:1071`) | Exact attribution needs the gateway. ACP gives Observable at best |
| Tool call to model call link | `toolCallId` only; `name` optional | `_meta` on `tool_call` by adapter | Use the MCP-side anchors in section 4 |
| Durable event cursor | None; load replays all, resume replays nothing | v2 `replayFrom` | Our journal is authoritative. Gaps across reconnect must be labelled |
| Multiple attached clients | Single connection model | not defined | Runtime owns the connection; UIs attach to the runtime |

## 2. ACP Python SDK

**Client API (both versions).** `spawn_agent_process(to_client, command, *args, env, cwd, transport_kwargs, **connection_kwargs)` or `connect_to_agent(...)`. Subclass `acp.Client` (`session_update`, `request_permission`, optional `fs`, `terminal`, elicitation). Connection methods are snake_case with expanded params (`initialize`, `new_session`, `load_session`, `resume_session`, `prompt`, `cancel`, `set_config_option`, `close`). `PROTOCOL_VERSION` is `1` in both (Probe).

| Property | 0.12.1 | 1.0.0rc3 |
|---|---|---|
| Schema classes (Probe) | 279 | 297 |
| Schema tag | `schema-v1.19.0` | `schema-v1.23.0`; spec is 1.29.0 |
| Parses `notice`, `compaction_update` | No: dropped | Yes |
| `delete_session`, `logout`, `$/cancel_request` constant | No | Yes |
| v2 runtime | No | `acp.experimental.v2`, binding `alpha.5` vs upstream `alpha.12` (`acp-python-sdk@9853d8b514d6:docs/experimental-v2.md:6`) |
| Requires-Python | `>=3.10,<3.15` | `>=3.10,<3.15` |
| Runtime deps | `pydantic>=2.7` | `pydantic>=2.7`, `pydantic-core>=2.18.1` |
| Optional | `logfire`, `http` (httpx) | `logfire`, `http` (httpx2, websockets, starlette) |

Comparing `$defs` at SDK HEAD with spec 1.29.0 stable found none missing, so the 1.23.0 tag is not a stable-surface gap. The clone's `pyproject.toml` says 0.12.1 only because release CI rewrites the version from the tag (`acp-python-sdk@9853d8b514d6:.github/workflows/on-release-main.yml:29`).

**Verified behaviour (Probe, fake raw agent):**

- `initialize`, `session/new` with typed `configOptions`, `prompt`, and `_meta` round trip all work on both versions.
- **Unknown or unmodelled `sessionUpdate` kinds are dropped.** The SDK raises `ValidationError` inside the notification handler, logs it (`acp-python-sdk@9853d8b514d6:src/acp/connection.py:294`), and the turn continues. The client never sees it. `subagent_update` is dropped on both versions; `notice` and `compaction_update` are also dropped on 0.12.1.
- **Raw capture works through a public path.** `spawn_agent_process(..., observers=[fn])` delivered both `subagent_update` and known frames to the observer on both versions. Observers run before parsing (`acp-python-sdk@9853d8b514d6:src/acp/connection.py:151`).
- An unknown `ToolKind` value did not break parsing.
- A 1.2 MB line passed with the default reader limit on both versions.
- Unstable methods answer `method_not_found` unless `use_unstable_protocol=True` (`acp-python-sdk@9853d8b514d6:src/acp/router.py:66`). `elicitation/create` is marked `unstable=True` in the SDK although the spec lists it as stable (`acp-python-sdk@9853d8b514d6:src/acp/interfaces.py:236`).

**Stability.** Pre-1.0 releases break callers: OpenHands records "0.11.0 reordered prompt() args" (`software-agent-sdk@988494576218:openhands-sdk/pyproject.toml:8`) and OpenHands CLI is still on `<0.9.0` (`OpenHands-CLI@283c6ac3610f:pyproject.toml:31`). Three release candidates have shipped since 2026-09-11; no 1.0 final as of 2026-11-02.

**Recommendation: use the SDK, wrapped.** It supplies process supervision, bidirectional routing, typed models, and cancellation. A thin own JSON-RPC client would save a small dependency and cost us all of that plus schema tracking. Keep `acp` types private to the ACP driver so none reach our public protocol. Journal raw frames from the observer so unknown updates survive export and replay.

**Pinning.** See section 5. Exact pins are unsafe in an extra because `openhands-sdk` caps this package (Probe in section 5).

## 3. Agents that speak ACP today

| Agent | Path | Package | Version | License | `initialize` probe | Notes |
|---|---|---|---|---|---|---|
| OpenCode | Native `opencode acp` | `@opencode/cli` (repo moved to `anomalyco/opencode`); `opencode-ai` npm stops at 1.19.5 | 2.2.5 | MIT | v1. `loadSession`; `additionalDirectories`, `close`, `delete`, `fork`, `list`, `resume`; HTTP MCP yes, SSE no; `_meta["opencode/child-session-updates"]` | `opencode-ai` is not the current name. Uses TS SDK 1.6.0 (`opencode@ff90ed91607c:packages/cli/package.json:30`) |
| OpenHands | Native `openhands acp` | `openhands` | 1.16.0 | MIT | Not probed. Source: `loadSession`, HTTP and SSE MCP, no `sessionCapabilities` (`OpenHands-CLI@283c6ac3610f:openhands_cli/acp_impl/agent/base_agent.py:248`) | Not in the registry. Pinned to `<0.9.0`, so expect old schema. Has a `resume_session` handler but does not advertise it |
| Claude Code | Adapter | `@agentclientprotocol/claude-agent-acp` (renamed twice from `@zed-industries/*`, both deprecated) | 0.99.1 | Apache-2.0, depends on proprietary `@anthropic-ai/claude-agent-sdk` 0.3.312 | v1 (also serves v2). `loadSession`; all session caps including `fork`, `systemPrompt`; HTTP and SSE MCP; unstable `providers`; top-level `_meta.steering.supported` | Registry lists `proprietary`, so do not bundle or redistribute |
| Codex | Adapter over app-server | `@agentclientprotocol/codex-acp` (replaces `@zed-industries/codex-acp`) | 2.5.0 | Apache-2.0 | v1 (also serves v2). Same session caps plus `subagents`; HTTP MCP yes, SSE no; auth `api-key`, `chat-gpt`; `_meta.steering.supported` | Depends on `@openai/codex` `^0.165.0`, so it brings its own Codex unless `CODEX_PATH` is set. Install was large |
| Gemini CLI | Native `--acp` | `@google/gemini-cli` | 0.66.0 | Apache-2.0 | Not probed (registry only) | Older flag names should not be assumed |
| pi | Third-party adapter | `pi-acp` (`svkozak/pi-acp`) | 0.0.34 | MIT | Not probed | No ACP in the pi repo: `git grep` for `acp` in `*.md` and `*.ts` is empty at `c9f4c7b9fcd0`. Use pi's native RPC |
| Prime Agent | Native `--mode acp` | Release tarball only | 0.10.2 | MIT | Not probed. Source: v1, `load_session: false` (`prime-agent@c6d4da9421e6:crates/pa-daemon/src/acp/types.rs:389`) | Not in the registry. Critic correction: this row said none, from a registry lookup alone |

Others in the registry include Goose, Cline, Qwen Code, Cursor, Kimi, Mistral Vibe, Junie, and GitHub Copilot. Entries are vendor-declared metadata, and registry `license` differs from npm for claude-agent-acp, so verify before relying on it.

**Extensions now shipping in the official adapters (EXPERIMENTAL; shape not in schema):**

- `_session/steering`, advertised at top-level `InitializeResponse._meta.steering.supported` (Probe on both). Source: `@agentclientprotocol/claude-agent-acp@0.99.1 dist/acp-agent.js:251` and `@agentclientprotocol/codex-acp@2.5.0 dist/index.js:46466`. The Claude adapter says it is v1-only for now (README line 120). I confirmed advertisement only; I did not send a steering request.
- Native subagent sessions on the draft RFD: claude-agent-acp announces children with `subagent_update` when the client declares `clientCapabilities.subagents` (README line 41) and uses the launching tool-use ID as the message ID. codex-acp documents the same with a tool-call fallback.

## 4. MCP

**Current stable revision is `2026-07-28`** (`mcp-spec@d0e246ea3c69:schema/2026-07-28/schema.ts:30`; https://modelcontextprotocol.io/specification/versioning, retrieved 2026-11-02). `draft` currently has no changes (`mcp-spec@d0e246ea3c69:docs/specification/draft/changelog.mdx:5`). Earlier revisions are Final. This revision is a redesign, not an increment.

| Topic | Handshake era (≤ `2025-11-25`) | Modern `2026-07-28` | Evidence |
|---|---|---|---|
| Lifecycle | `initialize` + `notifications/initialized`; session | Stateless. Every request carries version and capabilities in `_meta` | `mcp-spec@d0e246ea3c69:docs/specification/2026-07-28/changelog.mdx:14` |
| Discovery | `initialize` result | `server/discover`, mandatory to implement, optional to call | `changelog.mdx:16` |
| Version mismatch | Server counters | `UnsupportedProtocolVersionError` `-32022` listing supported versions | `mcp-spec@d0e246ea3c69:docs/specification/2026-07-28/basic/versioning.mdx:59` |
| Server to client | Server-initiated requests | Removed. Multi round-trip: `InputRequiredResult`, client retries | `changelog.mdx:24` |
| Result shape | No `resultType` | Required `resultType`; list results require `ttlMs`, `cacheScope` | `changelog.mdx:26` |
| HTTP session | `Mcp-Session-Id` | Removed; state uses explicit server-minted handles | `changelog.mdx:12` |
| HTTP headers | `MCP-Protocol-Version` | Also `Mcp-Method`, `Mcp-Name` | `changelog.mdx:35` |
| Resumability | `Last-Event-ID` | Removed; a broken stream means reissue with a new ID | `changelog.mdx:28` |
| Change push | GET stream, `resources/subscribe` | `subscriptions/listen` | `changelog.mdx:18` |

Deprecated: Roots, Sampling, Logging, Dynamic Client Registration, HTTP+SSE (`mcp-spec@d0e246ea3c69:docs/specification/2026-07-28/deprecated.mdx:24`). Tasks moved to an extension (`changelog.mdx:22`).

**Era detection.** On stdio, probe `server/discover` and fall back to `initialize` on any non-modern error or timeout (`mcp-spec@d0e246ea3c69:docs/specification/2026-07-28/basic/transports/stdio.mdx:125`, `:136`). Legacy clients cannot reach modern-only servers, so **our server must be dual-era** (`mcp-spec@d0e246ea3c69:docs/specification/2026-07-28/basic/versioning.mdx:170`).

**Stateless rules that bind our design** (`mcp-spec@d0e246ea3c69:docs/specification/2026-07-28/basic/index.mdx:192`, `:207`): no reliance on earlier requests for client identity; connection or process identity is not a proxy for conversation continuity; state spans calls through explicit identifiers passed on each request. `tools/list` must not vary per connection but MAY vary by authorization (`mcp-spec@d0e246ea3c69:docs/specification/2026-07-28/server/tools.mdx:65`, `:67`).

**Tool annotations.** `title`, `readOnlyHint`, `destructiveHint`, `idempotentHint`, `openWorldHint` (`mcp-spec@d0e246ea3c69:schema/2026-07-28/schema.ts:1923`, `:1933`, `:1943`, `:1953`). They are hints and clients MUST treat them as untrusted unless the server is trusted (`mcp-spec@d0e246ea3c69:docs/specification/2026-07-28/server/tools.mdx:305`). Codex reads them for its approval flow (`codex@05c08d765523:codex-rs/core/src/mcp_tool_call.rs:456`). Never use them as authorization.

### Python SDK 2.x vs 1.x

| Area | 1.x (`v1.x`, 1.30.0; critical fixes only) | 2.x (`main`, 2.3.0) |
|---|---|---|
| Server class | `FastMCP` | `MCPServer` in `mcp.server.mcpserver` (`from mcp.server import MCPServer` also works) |
| Client | `ClientSession` plumbing | First-class `mcp.Client(target, mode=...)`, target is URL, transport, or in-process server |
| Types | `mcp.types`, camelCase | `mcp-types` package, snake_case fields, exact lockstep pin |
| HTTP client | `httpx`, `httpx-sse` | `httpx2` |
| Transport options | Constructor | `run()` and app methods |
| Eras | Handshake only | Both. `mode="auto"` (probe), `"legacy"`, or a modern version string |
| Limits | none | 4 MiB HTTP POST body by default (`mcp-python-sdk@d7845c073a2b:docs/migration.md:850`) |
| Sync handlers | Event loop | Worker thread |

Serving: `app.run("stdio")`; `app.run("streamable-http", host=..., port=..., stateless_http=True, json_response=True, transport_security=...)`; or mount `streamable_http_app()`. One app serves both eras with no switch to disable either (`mcp-python-sdk@d7845c073a2b:docs/run/legacy-clients.md:9`). `stateless_http=True` affects only the legacy leg (`:115`). Elicitation and sampling through `Client` need `mode="legacy"`. Versioning: breaking changes only in majors; `provisional` and `experimental` APIs may move in minors (`mcp-python-sdk@d7845c073a2b:VERSIONING.md:11`).

**Weight (Probe):** the probe venv holds 29 distributions (`mcp` plus the ACP SDK), including `cryptography`, `uvicorn`, `starlette`, `opentelemetry-api`. `import mcp.server.mcpserver` costs about 1.1 s and 42 MB RSS here. A Python stdio shim per agent would cost about 4 GB RSS at 100 agents before sharing, so it is not the scale path.

### Verification (Probe)

| Check | Result |
|---|---|
| Stdio server (`MCPServer`), `Client` with `auto`, `legacy`, `2026-07-28` | Negotiated `2026-07-28`, `2025-11-25`, `2026-07-28`; tool call passed in each |
| In-process `Client(app)` | `2026-07-28`; tool call passed |
| Streamable HTTP, `TokenVerifier`, two tokens | Each saw its own `client_id` in `get_access_token()`, in both eras |
| HTTP rejection | No token 401 with `resource_metadata`; bad token 401; bad `Origin` 403; bad `Host` 421 |
| Spoof: `{"echo":"hi","caller":"agent-b"}` | Undeclared `caller` silently ignored; result reports the bound `agent-a` |
| Real Claude Code 2.1.316 to real `mcp` 2.3.0 server over stdio | Tool result returned `caller: agent-a` despite the spoofed argument |
| Real Codex 0.164.0 to real `mcp` 2.3.0 server | Pinned modern: 1 of 1 passed. Default legacy: see risk below |

### Client support

| Client | Default on stdio | Other | Evidence |
|---|---|---|---|
| Claude Code 2.1.316 | `server/discover` at `2026-07-28`, falling back to `initialize` at **`2025-11-25`** | `MCP_PROTOCOL_NEGOTIATION=legacy` opts out; stdio default since 2.1.292 | Probe; `claude-code@f0b737f94f3b:CHANGELOG.md:1379`; https://code.claude.com/docs/en/mcp retrieved 2026-11-02 |
| Codex 0.164.0 | `initialize` at **`2025-06-18`** | `2026-07-28` needs feature `mcp_2026_07_28` (UnderDevelopment, off) **and** server env `CODEX_MCP_PROTOCOL_VERSION=2026-07-28`. The feature alone stayed legacy | Probe; `codex@05c08d765523:codex-rs/rmcp-client/src/protocol_mode.rs:21`, `:43`; `codex@05c08d765523:codex-rs/features/src/lib.rs:1677` |
| OpenCode | Not probed | Uses `@modelcontextprotocol/client` 2.3.1, with a local patch | `opencode@ff90ed91607c:packages/core/package.json:106`; `opencode@ff90ed91607c:package.json:180` |
| pi | `initialize` at `2025-11-25` (critic probe, 1.4.0) | Own client; latest `2025-11-25`, supports back to `2024-11-05` | `pi@c9f4c7b9fcd0:packages/mcp/src/protocol/types.ts:4`, `:9` |
| OpenHands | `initialize` at `2025-11-25` (critic probe, SDK 1.59.0) | `fastmcp<4`; resolved `mcp` 1.30.0, so handshake era | Probe (resolver) |

Codex docs do not state a protocol revision (https://learn.chatgpt.com/docs/extend/mcp?surface=cli, retrieved 2026-11-02; `developers.openai.com/codex/mcp` now redirects there). Codex uses `rmcp` 3.5.1 pinned to a git rev (`codex@05c08d765523:codex-rs/Cargo.toml:470`) and a default tool timeout of 300 s (`codex@05c08d765523:codex-rs/codex-mcp/src/rmcp_client.rs:123`).

**So every real client must be assumed handshake-era or dual-era. Modern-only features cannot carry core semantics.** Legacy Codex means `2025-06-18`, which predates `2025-11-25`. MRTR, `subscriptions/listen`, and tasks are therefore out for core tools.

### Call anchors: an important positive finding

Both clients put provenance anchors in `tools/call` `_meta`, in both eras (Probe, real CLI with a fake model emitting a known ID):

- Claude Code: `claudecode/toolUseId` equal to the model's `tool_use.id` (`toolu_PROBE123` observed), plus `progressToken`.
- Codex: `callId` equal to the model's `call_id` (source `codex@05c08d765523:codex-rs/core/src/mcp_tool_call.rs:1374`), plus `threadId`, `sessionId`, `itemId`, `windowId`, `x-codex-turn-metadata`.

These are client-set, not model-set; the model only chose the arguments, which passed through verbatim. They give an exact client-reported join from an MCP call to a model tool-use ID. They are undocumented conventions, so treat them as versioned optional evidence. OpenHands 1.59.0 and pi 1.4.0 sent only `progressToken` in a critic probe, so neither offers this anchor.

## 5. Identity and dependency recommendation

### Binding identity

Hard rule: **no identity, role, run, or policy field exists in any tool schema.** The runtime resolves the caller from a credential bound outside model control. Tool code receives a resolved `AgentPrincipal`, never a parameter.

| Binding | How | Use when | Limits |
|---|---|---|---|
| **Loopback or remote Streamable HTTP + per-agent bearer** (default) | Runtime mints a token per `(run, agent)`. ACP: `McpServerHttp.headers`. Codex: `bearer_token_env_var` or `env_http_headers`. Claude: `headers`, `headersHelper` | Agent has `mcpCapabilities.http`: Claude, Codex, OpenCode, OpenHands | Single service, no per-agent process, authorization is per request as the spec intends |
| **Per-agent stdio shim + token env** (fallback) | ACP `McpServerStdio.env`. Shim holds the token and forwards to the runtime, never trusting anything else | No HTTP support, or ACP's mandatory path | One process per agent; keep the shim light and not `MCPServer` at scale |

Rules for both:

1. Verify server-side on every request. Map token to principal, scopes, and budget in the runtime. In `TokenVerifier`, set `client_id` to the agent ID and read `get_access_token()`; set `validate_token_resource=True`.
2. Never derive identity from `clientInfo`, `_meta`, connection, or arguments. `_meta` anchors are correlation evidence only. `x-mcp-header` mirrors tool arguments into headers, so no header it can set may be trusted.
3. Reject rather than ignore undeclared arguments. The SDK silently drops them; `caller` would otherwise leave no trace. Generate `additionalProperties: false` or validate strictly, and journal the attempt.
4. Tokens are scoped to one run and agent, short-lived, revocable, and renewable through `session/resume` (which re-supplies `mcpServers`) or reconnect. Never log them or put them in journal payloads, exports, or resolved config.
5. Stdio identity is launch configuration of a distinct server instance, fixed before any request, so it does not break the rule against inferring identity from prior requests (`mcp-spec@d0e246ea3c69:docs/specification/2026-07-28/basic/index.mdx:192`). The spec also says clients SHOULD NOT tie stdio process lifetime to a conversation (`:198`); ACP's per-session `mcpServers` makes that the practical outcome. We accept this and never treat the process as session state.
6. Filter `tools/list` by the authorization presented (on stdio, the instance's configured token) and enforce again at call time. Return `cacheScope: "private"` (SDK default observed: `ttlMs` 0, `private`).
7. HTTP: bind loopback by default. `MCPServer` auto-enables DNS-rebinding protection only for loopback hosts (`mcp-python-sdk@d7845c073a2b:src/mcp/server/mcpserver/server.py:1164`); on any other host it stays off unless configured (`mcp-python-sdk@d7845c073a2b:src/mcp/server/transport_security.py:48`). Always pass explicit `TransportSecuritySettings`, because the spec requires `Origin` validation.
8. Coordination state uses explicit handles (`lease_id`, `cursor`, `board_version`). No session semantics. Blocking `wait` tools must return within client timeouts and resume by cursor.

**Threat tiers must stay separate in docs and events:**

- *Model arguments* (hallucination, prompt injection): closed by construction and tested above.
- *Shell-capable agent at the same UID*: not closed by any of this. Probe: a sibling process read `/proc/<pid>/environ` of another same-UID process (`ptrace_scope` 0), so agent A's shell can read B's shim token. HTTP does not help, since the token sits in the agent's env or config. Only OS isolation (per-agent UID, sandbox, restricted `/proc`) closes it. Record an `identity_assurance` value such as `cooperative` or `isolated` so training data does not overclaim.

**Native subagents inherit MCP config, so their calls present the parent's token.** Attribute these to the parent principal and carry the anchor; never mint a child identity from the call. Reconcile through `subagent_update` where available, and mark the rest as a coverage gap.

### Versions and dependency policy

| Component | Policy |
|---|---|
| Core `platoon-harness-sdk` | Neither `mcp` nor `agent-client-protocol`. Our protocol types are our own |
| ACP protocol | Request `protocolVersion: 1`. Refuse anything else. v2 only behind an explicit experimental flag. Treat unknown updates as data |
| ACP SDK | Extra `[acp]`: `agent-client-protocol>=0.12.1,<2`. Lock 1.0.0rc3 in our `uv.lock`; CI matrix on both; move the floor to 1.0 on final |
| MCP protocol | Dual-era server. Do not pin client mode. Core tools work on `2025-06-18` semantics |
| MCP SDK | Extra `[mcp]`: `mcp>=2.3,<3`. Used by the service. `mcp-types` follows automatically. Keep its imports behind a lazy boundary. Stay off `provisional` APIs |
| Adapters | Exact versions, user-installed, resolved and shown by `doctor`, recorded in the reproducibility manifest: `claude-agent-acp@0.99.1`, `codex-acp@2.5.0`. Never bundled |
| Unstable ACP features | Per-feature opt-in with capability check, adapter version guard, and a recorded fixture. Never implied by negotiating v1 |

Resolver probes with `uv pip compile --python-version 3.12`:

| Requirements | Result |
|---|---|
| `openhands-sdk==1.59.0` alone | OK: `mcp` 1.30.0, `fastmcp` 3.4.11, `agent-client-protocol` 0.12.1 |
| `openhands-sdk==1.59.0` + `mcp==2.3.0` | **Unsatisfiable** (via `fastmcp<4`) |
| `openhands-sdk==1.59.0` + `agent-client-protocol==1.0.0rc3` | **Unsatisfiable** |
| Unpinned `openhands-sdk` + `mcp==2.3.0` | **Silently resolves `openhands-sdk` 1.49.1** |
| Unpinned `openhands-sdk` + acp rc3 | **Silently resolves `openhands-sdk` 1.44.1** |
| `mcp==2.3.0` + acp rc3 + `claude-agent-sdk` | OK (`claude-agent-sdk` allows `mcp>=1.23,<3`) |

So an OpenHands driver cannot share an environment with our MCP service, and unpinned extras can silently pick a very old OpenHands. The OpenHands path needs its own process and environment, or a separate lock. Make the extras declared `conflicts` in uv and add a floor on `openhands-sdk`.

## Implications for platoon-harness

1. **Keep three planes independent, as the brief demands.** ACP or native RPC controls sessions, MCP exposes primitives, and the gateway records model calls. An ACP-driven agent is Operational and Observable; it is Trainable only through the gateway.
2. **Advertise `fs: false` and `terminal: false`.** These are stable in v1 but gone in v2. Agents keep their own tools, and workspace and terminal ownership stays clear.
3. **Model the injection boundary explicitly.** Default `next_turn`. Report `steering` per adapter only after a recorded fixture passes. Never claim mid-generation delivery.
4. **Journal raw ACP frames first, then parse.** Use the `observers` hook. Parsing failures become an `unknown_update` event plus a coverage gap, not a log line.
5. **Use `configOptions` first, `modes` as fallback.** Select model by category `model`. Do not hardcode IDs.
6. **Inject tools per session via `mcpServers`.** One ACP session per logical agent. Re-supply on resume with a fresh token. For native integrations, use each harness's own config path with the same token model.
7. **Add anchor capture to the MCP service.** Store `claudecode/toolUseId` and Codex `callId` as `native_tool_call_id` with source and harness version. Combined with gateway traces, this is a candidate for exact tool-to-model-call joins, which ACP cannot give.
8. **Design tools for the weakest era.** No sessions, no server push, no elicitation dependency. Long waits return a cursor. Keep tool responses well below 4 MiB and use content references.
9. **Set annotations honestly, but enforce nothing with them.** `read` tools use `readOnlyHint`; `claim`-style tools are `idempotentHint: false`.
10. **Conformance suite additions.** Credential non-leak in updates and history, spoof rejection, unknown-update preservation, both eras on stdio and HTTP, cancellation stop reason, and tool visibility at first turn.
11. **Do not depend on the ACP registry at runtime.** Treat it as discovery input only; licenses and packages need local verification.

## Taste notes

- ACP's capability discipline is excellent: absence means unsupported, and every optional method has an explicit marker. Copy this in our capability matrix.
- ACP's `stable` and `unstable` schemas are generated from the same source and shipped side by side. That is a clean way to publish experiments; mirror it for our event schemas.
- MCP's move to stateless requests with explicit handles matches our lease and cursor design. Follow it rather than rebuilding sessions.
- MCP's `TokenVerifier` is a one-method seam. Good model for our own extension points.
- The `mcp` VERSIONING and DEPENDENCY_POLICY files are concise promises. Write ours the same way.
- Avoid the ACP SDK's silent drop on unknown variants. Forward compatibility must be a type, and v2's `other` variant is the right shape.
- Avoid MCP SDK's silent acceptance of undeclared arguments for anything security-adjacent.
- Avoid expanding one protocol until it does everything. `mcp/message`, proxy chains, and `providers/*` show ACP accreting; keep our control, tool, and model planes separate.

## Unknowns and risks

- **Codex legacy tool visibility is flaky against a real server (cause not established).** Against the real `mcp` 2.3.0 stdio server launched directly, 3 of 4 `codex exec` runs sent no MCP tools in the first model request, with no error. A `tee` wrapper around the same server passed 3 of 3, and the fast stub passed. A startup race with the 1.1 s import is my hypothesis only. Small sample. Do not assume tools are present at turn one; verify before use.
- **My first Codex pinned run stalled because my stub omitted `ttlMs` and `cacheScope`.** Fixed in the stub; not a Codex defect. It does show strict modern clients reject incomplete results.
- **ACP v2 may arrive soon.** Adapters already serve it. Drivers should isolate v1 lifecycle assumptions, chiefly "prompt response ends the turn".
- **`agent-client-protocol` 1.0 is unreleased.** Final API may differ from rc3. `Requires-Python` caps at `<3.15` in the wheels.
- **The license metadata for `agent-client-protocol` is missing** (no `License` field), so scanners may report unknown. The LICENSE file is Apache-2.0.
- **Not probed:** session flows beyond `initialize` on real ACP agents, including resume, permissions, `mcpServers` injection, `env` leak behaviour, and steering. OpenHands, Gemini, pi-acp, OpenCode's MCP client, and Claude's `headersHelper` were also not exercised.
- **Unknown:** whether `toolCallId` in the adapters equals the model tool ID. Whether native subagent MCP calls carry a usable `_meta` anchor. Whether Codex's sandbox blocks `/proc/<pid>/environ` reads.
- **`claudecode/toolUseId` and Codex `callId` are undocumented** and could change without notice. Guard by harness version.
- **Codex `mcp_connection_sharing`** (UnderDevelopment, off) shares stdio connections across chats (`codex@05c08d765523:codex-rs/features/src/lib.rs:1690`). Check that distinct tokens prevent sharing before anyone enables it.
- **Claude Code ships feature flags** that can keep specific servers on the earlier protocol, so negotiated version must be observed per connection, not assumed.
- **Clean-room note:** no web search was run for this report and nothing surfaced any `platoon-harness` implementation.
