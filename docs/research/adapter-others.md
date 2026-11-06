# Adapter research: OpenCode, pi, Prime Agent

## Inspected

| Project | Commit or version | Date | License |
|---|---|---|---|
| anomalyco/opencode (default branch `dev`) | `ff90ed91607c`, package version 2.2.5 | commit 2026-11-02 | MIT |
| `@opencode/cli` (npm), plus `@opencode/sdk`, `@opencode/client`, `@opencode/plugin` | 2.2.5 | inspected 2026-11-02 | MIT |
| `opencode-ai` (npm, the v1 line) | 1.19.5, version and help only | inspected 2026-11-02 | not checked |
| earendil-works/pi | `c9f4c7b9fcd0`, package version 1.4.0 | commit 2026-11-01 | MIT |
| `@earendil-works/pi-coding-agent` (npm) | 1.4.0 | inspected 2026-11-02 | MIT |
| PrimeIntellect-ai/prime-agent | `c6d4da9421e6`, workspace version 0.10.2 | commit 2026-10-30 | MIT |
| Prime Agent release tarball, linux-x64 | 0.10.2, sha256 prefix `09659961dfde201c` | inspected 2026-11-02 | MIT, plus bundled `PHOTON-LICENSE.md` |
| ApGa/platoon | `efe3b277c82c` | commit 2026-10-28 | see Platoon report |

Evidence labels: **IMPLEMENTED** (code on the default branch), **DOCUMENTED-ONLY**, **DRAFT/RFC**, **EXPERIMENTAL** (flagged or labelled unstable). **[LIVE]** means I observed it on 2026-11-02 against the published version. **[SOURCE]** means read from code only.

## Summary

| | OpenCode | pi | Prime Agent |
|---|---|---|---|
| Live turn against the fake server | Yes: run, serve, ACP | Yes: JSON, RPC | **No: blocked, see Probe notes** |
| Best control surface | ACP v1 baseline, HTTP+SSE for depth | `--mode rpc` JSONL | `--mode rpc` (pi-shaped) or ACP v1 |
| ACP | Yes, v1 | **None** | Yes, v1, no load or resume |
| MCP | Yes | **Yes, first-party** | Yes, through the Python kernel |
| Native approvals | Yes, rule-based | None, extension gate only | None |
| Native subagents | Yes, child sessions | None | Yes, `rlm.spawn` |
| Hidden model calls | Title and compaction, observed | None in the probe; cache warming is on by default | Unknown |
| Adapter priority | 2 | **1** | 3 |

Three findings change the design:

1. **OpenCode v2 is a new product surface.** The package, API paths, config schema and auth variable all changed. A v1-era client gets silent wrong answers, not errors (see OpenCode section).
2. **pi has first-party MCP as of 1.4.0.** The task note that pi may avoid MCP is out of date, so no shell-client workaround is needed.
3. **An unpinned OpenCode session sends prompts to a hosted free model with no credentials configured.** This happened during the probe. The adapter must never leave the model unset.

## Probe notes

Setup: a stdlib Python fake server implementing `POST /v1/chat/completions` with SSE, plus a stdlib stdio MCP server exposing one `ping` tool. Each harness ran under an isolated `HOME` and config directory. Fixtures:

- `fixtures/opencode-sample.jsonl`: `run --format json`, SSE events, ACP transcript, and the model request headers.
- `fixtures/pi-sample.jsonl`: RPC transcript covering MCP, extension tool, approval, steer, follow-up and abort, plus model request headers.
- `fixtures/prime-agent-sample.md`: **states that no capture exists.** It contains no event data.

Incidents that affect how later probes and adapters should be written:

| Incident | What happened | Consequence |
|---|---|---|
| Unpinned ACP model | The first `opencode acp` run had no default model, so it used hosted `opencode/flint-40b-free`. My test client auto-approved five read-only shell commands proposed by that model: `ls`, `git status`, `env \| grep`, directory listings and `cat` of a toolchain env file. | Probe prompts, directory listings and that env file went to a third-party model. The `env` output held only `SHELL` and `OPENCODE_CONFIG_CONTENT`, which contained a fake key. No credential was exposed. All later probes pinned the model and approved only the scripted echo. |
| Port collision | The first request went to an unrelated service on a fixed port and got a 400. It carried only the fake key. | Probes now use OS-assigned ports. Conformance tests should do the same. |
| **Prime Agent blocked** | The harness permission classifier denied the model-turn run before execution and gave no reason. I did not retry by another route. | Every Prime Agent claim below except version and help is [SOURCE]. The exact command to approve is in the fixture file. |

## OpenCode

### Install and runtime

- **Rename:** v2 is npm `@opencode/cli`, and the README now installs that (opencode@ff90ed91607c:README.md:53). v1 remains published as `opencode-ai` 1.19.5. Docs moved to `/v2/docs`. Older mise versions still install v1 (https://opencode.ai/v2/docs, retrieved 2026-11-02).
- The npm package selects a platform binary through optional dependencies (`@opencode/cli-linux-x64`, about 250 MB) and has a `postinstall` script. No Node is needed at runtime. [LIVE] `opencode --version` prints `opencode v2.2.5`. `opencode-ai` also ran and printed 1.19.5.
- Bins are `opencode` and `opencode2`, so the driver must check the major version rather than the name.
- SDKs are TypeScript only: `@opencode/client` and the in-process `@opencode/sdk` (opencode@ff90ed91607c:packages/sdk/README.md:3). A Python driver speaks HTTP or ACP.

### Surfaces and stability

| Surface | Status | Notes |
|---|---|---|
| `opencode serve [--hostname --port --stdio --service]` | IMPLEMENTED, API labelled experimental | opencode@ff90ed91607c:packages/cli/src/commands/commands.ts:573. `--stdio` prints `{url}` as JSON (opencode@ff90ed91607c:packages/cli/src/server-process.ts:208). |
| `/api/*` HTTP+SSE, 138 paths | IMPLEMENTED | Spec at `/openapi.json` [LIVE]. Its `info.description` reads "Experimental HttpApi surface for selected instance routes" (opencode@ff90ed91607c:packages/protocol/openapi.json). |
| Stability policy | Convention | New endpoints start under `/api/experimental`; graduating is noted in the changelog; SDK breaks keep deprecated aliases until the next minor (opencode@ff90ed91607c:AGENTS.md:174). Non-experimental paths are the best available commitment, but events do break: `session.compacted` was removed (opencode@ff90ed91607c:CHANGELOG.md:921). |
| `opencode acp` | IMPLEMENTED, ACP `protocolVersion: 1` | opencode@ff90ed91607c:packages/cli/src/acp/service.ts:120, SDK `@agentclientprotocol/sdk` 1.6.0 (opencode@ff90ed91607c:packages/cli/package.json:30). Always starts a private server (opencode@ff90ed91607c:packages/cli/src/commands/handlers/acp.ts:25). |
| `opencode run --format json` | IMPLEMENTED | opencode@ff90ed91607c:packages/cli/src/commands/commands.ts:432. Emits `step_start`, `text`, `step_finish`, `error` [LIVE]. Exit 1 on error, 130 on interrupt (opencode@ff90ed91607c:packages/cli/src/run/noninteractive.ts:523). |
| Plugins (`@opencode/plugin`) | IMPLEMENTED, some hooks experimental | Requires the host's `effect` v4 (opencode@ff90ed91607c:packages/plugin/README.md:10). |

Traps:

- [LIVE] **`opencode run` hangs on an open non-TTY stdin.** It reads stdin to EOF (opencode@ff90ed91607c:packages/cli/src/run/run.ts:80). A pipe left open timed out after 60 s; `</dev/null` fixed it.
- [SOURCE] **`run` uses a shared background service unless `--standalone` is passed** (opencode@ff90ed91607c:packages/cli/src/commands/commands.ts:14). This conflicts with the brief's ownership modes, so always pass `--standalone` or own a `serve` process.
- [LIVE] **Public docs describe different routes.** `https://opencode.ai/docs/server/` documents `/event`, `/doc` and `OPENCODE_SERVER_PASSWORD`. On 2.2.5, `/event`, `/doc` and `/global/event` return **200 `text/html`**, the web UI, not an error. `/v2/docs/server` and `/v2/docs/acp` returned 404 (retrieved 2026-11-02). Check `content-type`.
- [SOURCE] **Docs lag the schema.** The docs use a singular `permission` key (opencode@ff90ed91607c:packages/web/src/content/docs/permissions.mdx:49). The v2 schema is a `permissions` array of `{action, resource, effect}` (opencode@ff90ed91607c:packages/schema/src/config.ts:58).

### Events, messaging and control (HTTP)

- **Events:** `GET /api/event` is SSE and "volatile by contract": a slow consumer fails the stream and events during disconnection are missed (opencode@ff90ed91607c:packages/protocol/src/groups/event.ts:69). [LIVE] 100 of 153 events carried `durable: {aggregateID, seq, version}`. `permission.asked` carries none (it is declared ephemeral). Reconcile after a reconnect through `/message`, `/inbox` and `/permission`.
- **Durable log:** `GET /api/experimental/session/:id/log` is EXPERIMENTAL (opencode@ff90ed91607c:packages/protocol/src/groups/session.ts:652). [LIVE] `?after=0` returned only one `log.synced` record with `seq: 39`, no events. I did not establish why, so do not depend on it for replay yet.
- **Prompt:** `POST /api/session/:id/prompt` durably admits input, takes optional client `id`, `metadata`, `delivery` and `resume` (opencode@ff90ed91607c:packages/protocol/src/groups/session.ts:337). Delivery defaults to `steer` (opencode@ff90ed91607c:packages/core/src/session/prompt.ts:52). Retry behaviour of a repeated `id` was not probed.
- **Steer and queue:** `Delivery = steer | queue` (opencode@ff90ed91607c:packages/schema/src/session-inbox.ts:11). [LIVE] While a slow stream ran, both items sat in `/inbox`. Steer then reached the model in its own request after the stream ended, followed by queue. Neither interrupted generation.
- **Exposure evidence:** `session.inbox.enqueued` and `session.inbox.delivered` give an observed delivery boundary for each input. This is the closest match to the brief's observed-exposure evidence across the three harnesses.
- **Interruption:** `POST /interrupt` returned `{interrupted: true}`, followed by `session.step.failed` (`aborted`) and `session.execution.interrupted`. The upstream stream was reset [LIVE]. `?resume=true` runs pending steering while queued prompts stay parked (opencode@ff90ed91607c:packages/protocol/src/groups/session.ts:672).
- **Compaction:** `POST /compact` enqueues an inbox item and emits `session.compaction.started/delta/failed`. It made two extra model calls [LIVE]. Success was not observed because the fake summary failed the template check.
- **Resume:** after a server restart a session accepted a new prompt and grew from 11 to 15 messages [LIVE]. The CLI has `--session`, `-c`, `--fork`.

### Approvals

- Rules are `{action, resource, effect: allow|deny|ask}`, settable in config, per agent, and per session at creation (opencode@ff90ed91607c:packages/protocol/src/groups/session.ts:174).
- [LIVE] With no rule, shell ran without asking. With an `ask` rule: `permission.asked` carried `action`, `resources`, `save` and the tool source, then `POST .../permission/:id/reply {"decision":"once"}` returned 204. The body field is `decision`, with values `once`, `always` or `reject` (opencode@ff90ed91607c:packages/protocol/src/groups/permission.ts:142).
- Non-interactive `run` rejects asks and tells the model to continue (opencode@ff90ed91607c:packages/cli/src/run/noninteractive.ts:73). `--auto` approves anything not explicitly denied.
- ACP maps to `session/request_permission` with `allow_once`, `allow_always`, `reject_once` [LIVE].

### ACP behaviour [LIVE]

`initialize` returned `loadSession: true`, `mcpCapabilities {http: true, sse: false}`, `sessionCapabilities {additionalDirectories, close, delete, fork, list, resume}` and `_meta["opencode/child-session-updates"]: true`. A prompt returned `stopReason: end_turn` with `usage`. `session/cancel` returned `stopReason: cancelled`, and the next prompt succeeded. A second concurrent prompt fails with -32603 "Session already has an active ACP prompt" (opencode@ff90ed91607c:packages/cli/src/acp/turn.ts:381), so steer and queue are HTTP-only depth.

### Tool injection

- MCP config: `mcp.servers.<name>` with `{type: "local", command: [...], environment, codemode, timeout, protocol}` (opencode@ff90ed91607c:packages/schema/src/mcp.ts:26).
- **Code Mode hides tools by default.** `codemode` defaults to true (opencode@ff90ed91607c:packages/schema/src/mcp.ts:34), so the model sees one `execute` tool, not `coord_ping` [LIVE]. Set `"codemode": false` for direct exposure.
- **First-prompt race.** A prompt sent before MCP connects misses the tool in its first model call [LIVE]. Waiting for `GET /api/mcp` to report `connected` fixed it.
- **ACP-supplied servers differ.** A stdio server in `session/new` was not declared as a direct tool, and a `<system-update>` Code Mode catalog notice appeared instead, even though a config entry of the same name set `codemode: false` [LIVE]. Calling it was not tested, and precedence between the two was not established.
- MCP protocol: `legacy` by default, up to 2025-11-25; `auto` probes the 2026-07-28 revision (opencode@ff90ed91607c:packages/schema/src/mcp.ts:20).

### Subagents

The `subagent` tool creates child sessions, foreground or background, and follows up by `sessionID` (opencode@ff90ed91607c:packages/core/src/tool/plugin/subagent.ts:16). [LIVE] The child appears as `session.created` with `parentID`, its events use its own `sessionID`, and it is listed by `GET /api/session?parentID=`. ACP exposes `opencode/session/child_update` with root, child, parent and depth (opencode@ff90ed91607c:packages/cli/src/acp/child.ts:3), after client opt-in through `_meta` (opencode@ff90ed91607c:packages/cli/src/acp/capabilities.ts:3). I did not opt in, so that path is [SOURCE].

### Model calls and attribution

Config can be passed without touching disk through `OPENCODE_CONFIG_CONTENT` (opencode@ff90ed91607c:packages/core/src/config.ts:291). Working custom provider [LIVE]:

```json
{"model":"fake/fake-model","providers":{"fake":{"package":"@ai-sdk/openai-compatible",
 "settings":{"baseURL":"http://127.0.0.1:PORT/v1","apiKey":"..."},
 "headers":{"X-Platoon-Agent":"agent-1"},
 "models":{"fake-model":{"capabilities":{"tools":true},"limit":{"context":100000,"output":1000}}}}}}
```

Model request headers [LIVE], set at opencode@ff90ed91607c:packages/core/src/session/model-request.ts:295:

| Header | Root call | Subagent call |
|---|---|---|
| `x-opencode-session-id` | root id | **child id** |
| `x-opencode-parent-session-id`, `x-parent-session-id` | absent | parent id |
| `x-session-id`, `x-session-affinity`, `x-opencode-session` | root id | **still root id** |
| `x-opencode-client` | `cli` or `acp` | same |
| configured `headers` | present | present |

- Key attribution on `x-opencode-session-id`. Keying on `x-session-id` would merge children into the parent.
- **Hidden calls.** A fresh one-tool turn made 3 calls: title, tool step, final step [LIVE]. The title call uses the same session id with `tools: []` and no purpose header. Separating it by shape is heuristic only, and the brief forbids treating that as exact.
- Headers are client-asserted, and every session in one server shares the provider credential. Exact identity needs a credential per server process.

### Auth and policy

`opencode auth login`, with provider plugins including `chatgpt`, `github-copilot`, and `claude-agent`, which runs the local `claude` binary (opencode@ff90ed91607c:packages/core/src/plugin/provider/claude-agent/index.ts:24). Server password is `OPENCODE_PASSWORD`, legacy `OPENCODE_SERVER_PASSWORD` (opencode@ff90ed91607c:packages/cli/src/env.ts:10). Basic-auth username is fixed to `opencode` (opencode@ff90ed91607c:packages/server/src/auth.ts:20). Missing auth returned 401 [LIVE].

**Secrets in `OPENCODE_CONFIG_CONTENT` are readable by the agent.** The variable reached the tool shell [LIVE]. Treat any key placed there as agent-visible.

## pi

### Install and runtime

`npm install -g --ignore-scripts @earendil-works/pi-coding-agent`, Node >= 22.19 (pi@c9f4c7b9fcd0:packages/coding-agent/package.json:95). [LIVE] 1.4.0 ran on the private Node v26.13.0. Isolation variables: `PI_CODING_AGENT_DIR`, `PI_OFFLINE`, `PI_TELEMETRY`, `PI_SKIP_VERSION_CHECK` (pi@c9f4c7b9fcd0:packages/coding-agent/docs/environment-variables.md:81).

### Surfaces

| Surface | Status | Notes |
|---|---|---|
| `--mode rpc` | IMPLEMENTED | Long-lived JSONL with commands, responses, events, extension UI (pi@c9f4c7b9fcd0:packages/coding-agent/docs/rpc.md:1). Types at pi@c9f4c7b9fcd0:packages/coding-agent/src/modes/rpc/rpc-types.ts:22. |
| `--mode json` | IMPLEMENTED | One invocation, session header then events (pi@c9f4c7b9fcd0:packages/coding-agent/docs/json.md:1). Failed responses do not by themselves produce a nonzero exit (pi@c9f4c7b9fcd0:packages/coding-agent/docs/cli-integration.md:46). |
| TypeScript SDK, `RpcClient` | IMPLEMENTED | `createAgentSession` (pi@c9f4c7b9fcd0:packages/coding-agent/docs/sdk.md:8), `RpcClient` (pi@c9f4c7b9fcd0:packages/coding-agent/src/modes/rpc/rpc-client.ts:56). |
| Extensions | IMPLEMENTED | TypeScript in process, `pi -e path.ts` (pi@c9f4c7b9fcd0:packages/coding-agent/docs/extensions.md:1). |
| ACP | **Absent** | No matches in docs or source. |

Protocol notes:

- Split records on LF only. U+2028 and U+2029 are valid inside JSON strings (pi@c9f4c7b9fcd0:packages/coding-agent/docs/rpc.md:54), so Python's `str.splitlines` is unsafe.
- Wait for `agent_settled`, not `agent_end`; retries and queued work can follow `agent_end` (pi@c9f4c7b9fcd0:packages/coding-agent/docs/rpc.md:69). [LIVE] It carries `aborted`.
- `message_update` is delta-only; `message_end` is authoritative (pi@c9f4c7b9fcd0:packages/coding-agent/docs/json.md:72).
- [LIVE] Events include a `role: system` message with named `sections`, so the assembled system prompt is observable without reading wire traffic.

### Tool injection

**First-party MCP is IMPLEMENTED** (pi@c9f4c7b9fcd0:packages/coding-agent/docs/mcp.md:1, pi@c9f4c7b9fcd0:packages/coding-agent/src/index.ts:415). The client is the standalone `@earendil-works/pi-mcp`, stdio and streamable HTTP, latest protocol 2025-11-25 (pi@c9f4c7b9fcd0:packages/mcp/src/protocol/types.ts:4).

- Config: `<agent-dir>/mcp.json`, or `.pi/mcp.json` after project trust (pi@c9f4c7b9fcd0:packages/coding-agent/docs/mcp.md:32).
- Default exposure is `codemode`, not declared to the model (pi@c9f4c7b9fcd0:packages/coding-agent/docs/mcp.md:197). **Set `"exposure": "direct"`.** [LIVE] `mcp__coord__ping` then appeared in the first model request and returned `pong:hi`. The first prompt waits up to 10 s for servers with direct tools (pi@c9f4c7b9fcd0:packages/coding-agent/docs/mcp.md:100), which avoids OpenCode's race.
- Alternative: `pi.registerTool()` in an extension. [LIVE] `coord_ext` loaded through `-e` and worked. Prefer MCP so one tool server serves all harnesses.

### Messaging, interruption, sessions

- `prompt` while busy without `streamingBehavior` returns an error [LIVE]: "Agent is already processing. Specify streamingBehavior...".
- `steer` is delivered after the current assistant turn's tool calls, before the next LLM call (pi@c9f4c7b9fcd0:packages/coding-agent/docs/rpc-commands.md:48). `follow_up` runs after. [LIVE] order was steer then follow-up, with `queue_update` events and responses reporting `disposition: queued`. Default mode is `one-at-a-time`.
- `abort` waits for idle (pi@c9f4c7b9fcd0:packages/coding-agent/docs/rpc-commands.md:96). [LIVE] It produced `agent_settled {aborted: true}`.
- Sessions are JSONL trees. Commands include `new_session`, `switch_session`, `fork`, `clone`, `get_entries`, `get_tree`. [LIVE] `--session <id>` resumed with full history (21 messages in the next request).

### Approvals

**No native approvals.** Pi "does not ask for approval before every tool call" (pi@c9f4c7b9fcd0:packages/coding-agent/docs/security.md:3). The supported gate is an extension on `tool_call` returning `{block: true}` (pi@c9f4c7b9fcd0:packages/coding-agent/examples/extensions/permission-gate.ts:13). [LIVE] A gate calling `ctx.ui.confirm` produced `extension_ui_request`, and `extension_ui_response {confirmed: true}` let the command run. We would ship this small extension. It is a policy aid, not a security boundary: the extension sits in the same process as the tools.

### Subagents

None natively, by design (pi@c9f4c7b9fcd0:README.md:19). The example extension runs each subagent as a separate `pi` process (pi@c9f4c7b9fcd0:packages/coding-agent/examples/extensions/subagent/README.md:7). This suits us: spawning stays in our runtime, so identity never has to be reconciled.

### Model calls and attribution

Custom provider in `<agent-dir>/models.json`: `baseUrl`, `api`, `apiKey` (literal, `$NAME`, or `!command`), `headers`, `compat`, `models` (pi@c9f4c7b9fcd0:packages/coding-agent/docs/models-configuration.md:11). [LIVE] A tool turn made exactly 2 calls, no title call. Configured headers arrived on each.

- Session headers (`x-session-affinity`, `x-client-request-id`, both the session id) are sent only with `compat.sendSessionAffinityHeaders` (pi@c9f4c7b9fcd0:packages/ai/src/api/openai-completions.ts:759). Default is false outside OpenRouter (pi@c9f4c7b9fcd0:packages/coding-agent/docs/models-configuration.md:136).
- `cacheWarming` defaults to `"streaming"` and can issue refresh calls, though only when a model declares a cache lifetime (pi@c9f4c7b9fcd0:packages/coding-agent/docs/settings.md:21). Set it to `"off"` for trainable runs.

### Auth and policy

OAuth modules: `anthropic`, `openai-chatgpt`, `openai-codex`, `github-copilot`, `kimi-coding` (pi@c9f4c7b9fcd0:packages/ai/src/auth/oauth/load.ts). Credentials live in `auth.json`. Prefer `$NAME` keys for scoped per-agent credentials.

## Prime Agent

**Everything in this section is [SOURCE] except the version and help output.** It is a Rust port of a TypeScript product and appears pi-derived: the changelog compares behaviour to "the TypeScript version" (prime-agent@c6d4da9421e6:CHANGELOG.md:10), the binary serves the TS `modes/rpc` surface (prime-agent@c6d4da9421e6:crates/pa-cli/tests/rpc_mode_e2e.rs:14), and `PI_OFFLINE` survives as a setting.

### Install and runtime

- Installer `curl ... | sh` from a release bucket with checksum verification (prime-agent@c6d4da9421e6:README.md:46). **Not on npm** (`prime-agent` 404) **or PyPI** (`prime-agent`, `prime-agent-runtime` 404, checked 2026-11-02). No Cargo toolchain on this host, so the release tarball was used.
- [LIVE] The binary ran with no Node: `--version` gave `0.10.2`, and `--help` listed `--mode <text|json|rpc|acp|daemon>`.
- It also needs `uv` and a Python >= 3.11 kernel environment bootstrapped at runtime (prime-agent@c6d4da9421e6:crates/pa-core/src/kernel/bootstrap/venv/uv.rs:82, prime-agent@c6d4da9421e6:prime-agent-runtime/pyproject.toml:5). Expect a slower first start.
- Telemetry is on by default and pseudonymous. Disable with `PRIME_AGENT_TELEMETRY=0`, `DO_NOT_TRACK=1` or offline mode (prime-agent@c6d4da9421e6:crates/pa-cli/src/telemetry_notice.rs:23).

### Surfaces

| Surface | Status | Notes |
|---|---|---|
| `--mode rpc` | IMPLEMENTED | JSONL, one connection drives one session, stdin close settles the turn (prime-agent@c6d4da9421e6:crates/pa-daemon/src/rpc/mod.rs:1). Commands match pi's: `prompt`, `steer`, `follow_up`, `abort`, `compact`, plus `refine` (prime-agent@c6d4da9421e6:crates/pa-daemon/src/rpc/commands.rs:214). |
| `--mode acp` | IMPLEMENTED, ACP v1 | Served over a daemon session (prime-agent@c6d4da9421e6:crates/pa-daemon/src/acp/daemon.rs:1). `load_session: false`; only `close` under session capabilities (prime-agent@c6d4da9421e6:crates/pa-daemon/src/acp/types.rs:389). Methods: `initialize`, `session/new`, `session/set_config_option`, `session/prompt`, `session/cancel`, `session/close`. |
| `--mode json`, `--print` | IMPLEMENTED | Same event family; `tool_execution_end` carries `isError` (prime-agent@c6d4da9421e6:CHANGELOG.md:10). |
| Python `rlm` runtime | IMPLEMENTED | Agent-side API inside the kernel, not a host library (prime-agent@c6d4da9421e6:prime-agent-runtime/src/rlm/__init__.py:179). |

### Behaviour from source

- **Tool injection:** the model's one built-in tool is the Python REPL. MCP services are called from it through `mcp.call_tool` (prime-agent@c6d4da9421e6:skills/mcp/SKILL.md:52). User servers go in the `mcpServers` setting (prime-agent@c6d4da9421e6:crates/pa-core/src/mcp/mod.rs:74). ACP `session/new` admits stdio and HTTP servers (prime-agent@c6d4da9421e6:crates/pa-daemon/src/acp/mcp.rs:17). Whether a model sees them directly is unverified.
- **Messaging:** `steer` and `follow_up` in RPC. ACP allows one prompt turn at a time (prime-agent@c6d4da9421e6:crates/pa-daemon/src/acp/daemon.rs:737). Native peer messaging exists with a daemon-derived sender, limited to parent, siblings and direct children (prime-agent@c6d4da9421e6:skills/agent-message/SKILL.md:8). This overlaps our messaging primitive, so decide who owns it per run.
- **Approvals: none.** No `request_permission` in the crates. The README warns it runs generated code with user permissions and that workers are not a sandbox (prime-agent@c6d4da9421e6:README.md:111).
- **Subagents:** `rlm.spawn(prompt, name=...)` creates real child sessions (prime-agent@c6d4da9421e6:prime-agent-runtime/src/rlm/__init__.py:179). ACP reports them as `rlm_child_update` metadata with id, session name, status, model and token count (prime-agent@c6d4da9421e6:crates/pa-daemon/src/acp/wire_events.rs:292). A daemon-owned append-only ledger records spawn edges (prime-agent@c6d4da9421e6:crates/pa-daemon/src/rlm_ledger.rs:1), including `child_cancelled` with reason (prime-agent@c6d4da9421e6:CHANGELOG.md:16). This is useful provenance input.
- **Model endpoint:** `models.json` in the agent dir (`PRIME_AGENT_CODING_AGENT_DIR`, default `.prime/agent`, prime-agent@c6d4da9421e6:crates/pa-cli/src/config.rs:7). Custom models need `baseUrl` and `apiKey` (prime-agent@c6d4da9421e6:crates/pa-core/src/models/custom.rs:210). Affinity headers behind the same compat flag as pi (prime-agent@c6d4da9421e6:crates/pa-ai/src/providers/openai_completions/params.rs:340). I found no parent-session header in `pa-ai`, so native child calls may not expose parentage on the wire.
- **Auth:** subscription logins exist (prime-agent@c6d4da9421e6:crates/pa-cli/src/subscription_login.rs:1). Trace upload is consent-gated (prime-agent@c6d4da9421e6:crates/pa-core/src/agent_traces/continuous.rs:1). Daemons we start must be stopped.

## Capability matrix

Versions: OpenCode 2.2.5, pi 1.4.0, Prime Agent 0.10.2. Section evidence above applies; the key citation is repeated per row.

### OpenCode 2.2.5

| Capability | Status | Evidence | Limitations |
|---|---|---|---|
| Launch | [LIVE] | opencode@ff90ed91607c:packages/cli/src/commands/commands.ts:573 | Avoid the background service. Close stdin for `run`. |
| Streaming | [LIVE] | opencode@ff90ed91607c:packages/protocol/src/groups/event.ts:69 | SSE is volatile. ACP gives less detail. |
| Tool injection | [LIVE] | opencode@ff90ed91607c:packages/schema/src/mcp.ts:34 | Needs `codemode: false` and waiting for MCP connection. |
| Messaging | [LIVE] | opencode@ff90ed91607c:packages/schema/src/session-inbox.ts:11 | Boundary delivery only. ACP has no steer. |
| Interruption | [LIVE] | opencode@ff90ed91607c:packages/protocol/src/groups/session.ts:672 | Applies to execution owned by that process. |
| Approvals | [LIVE] | opencode@ff90ed91607c:packages/protocol/src/groups/permission.ts:142 | `permission.asked` is ephemeral, so poll after reconnect. |
| Resume | [LIVE] | opencode@ff90ed91607c:packages/cli/src/acp/service.ts:122 | Replay through the experimental log is unconfirmed. |
| Native subagents | [LIVE] on HTTP | opencode@ff90ed91607c:packages/core/src/tool/plugin/subagent.ts:16 | Children share the parent's credential. ACP child updates not probed. |
| Model endpoint | [LIVE] | opencode@ff90ed91607c:packages/schema/src/config/provider.ts:112 | Must pin the model, or hosted free models are used. |
| Exact call attribution | Partial [LIVE] | opencode@ff90ed91607c:packages/core/src/session/model-request.ts:295 | Session-level exact only with one credential per process. Headers are unauthenticated. No purpose header. |
| Training eligibility | Candidate, untested with Platoon | platoon@efe3b277c82c:docs/rfcs/0005-gateway-dialects-and-tito.md:29 | Title and compaction calls must be excluded. Native children are inferred at best. |

### pi 1.4.0

| Capability | Status | Evidence | Limitations |
|---|---|---|---|
| Launch | [LIVE] | pi@c9f4c7b9fcd0:packages/coding-agent/docs/rpc.md:15 | Needs Node >= 22.19. |
| Streaming | [LIVE] | pi@c9f4c7b9fcd0:packages/coding-agent/docs/json.md:72 | Client must read continuously; a stalled reader stalls pi. |
| Tool injection | [LIVE] | pi@c9f4c7b9fcd0:packages/coding-agent/docs/mcp.md:197 | Needs `exposure: direct`. |
| Messaging | [LIVE] | pi@c9f4c7b9fcd0:packages/coding-agent/src/modes/rpc/rpc-types.ts:22 | Delivered at turn boundaries. Queue durability after a crash was not tested. |
| Interruption | [LIVE] | pi@c9f4c7b9fcd0:packages/coding-agent/docs/rpc-commands.md:94 | None observed. |
| Approvals | Extension only [LIVE] | pi@c9f4c7b9fcd0:packages/coding-agent/docs/security.md:3 | Must ship a gate extension. No effect without one. |
| Resume | [LIVE] | pi@c9f4c7b9fcd0:packages/coding-agent/src/core/session-manager.ts:49 | Run by session id with `--session-dir`. |
| Native subagents | None by design | pi@c9f4c7b9fcd0:README.md:19 | User extensions can add them, so disable or review third-party ones. |
| Model endpoint | [LIVE] | pi@c9f4c7b9fcd0:packages/coding-agent/docs/models-configuration.md:11 | Config is a file, so use one agent dir per agent. |
| Exact call attribution | Agent-level [LIVE] | pi@c9f4c7b9fcd0:packages/ai/src/api/openai-completions.ts:759 | Through per-process credential or header. No per-call id in a request: `x-client-request-id` repeats the session id. An RPC frame has one: `message_end` carries the model's `responseId`, which this report missed by reading headers and not frames. |
| Training eligibility | **Best candidate**; full path passed in a critic probe | platoon@efe3b277c82c:docs/rfcs/0005-gateway-dialects-and-tito.md:29 | Real pi on a minted child key through the real gateway: direct MCP tool seen and called, exact tokens, 2 datums on the child. Platoon has no pi spec. Turn off cache warming. Compaction purpose is unlabelled. |

### Prime Agent 0.10.2

| Capability | Status | Evidence | Limitations |
|---|---|---|---|
| Launch | Version and help [LIVE], turn unverified | prime-agent@c6d4da9421e6:crates/pa-cli/src/mode.rs:9 | Needs `uv` and a Python kernel. No npm or PyPI. |
| Streaming | [SOURCE] | prime-agent@c6d4da9421e6:crates/pa-daemon/src/rpc/mod.rs:1 | Unverified. |
| Tool injection | [SOURCE] | prime-agent@c6d4da9421e6:crates/pa-daemon/src/acp/mcp.rs:17 | Python-mediated. Prefer also shipping a Python client. |
| Messaging | [SOURCE] | prime-agent@c6d4da9421e6:crates/pa-daemon/src/rpc/commands.rs:215 | ACP is one turn at a time. |
| Interruption | [SOURCE] | prime-agent@c6d4da9421e6:crates/pa-daemon/src/rpc/commands.rs:216 | Children and kernels must also stop. |
| Approvals | None [SOURCE] | prime-agent@c6d4da9421e6:README.md:111 | Show as unsupported. Requires an external sandbox. |
| Resume | CLI only [SOURCE] | prime-agent@c6d4da9421e6:crates/pa-daemon/src/acp/types.rs:391 | Not through ACP. |
| Native subagents | [SOURCE] | prime-agent@c6d4da9421e6:crates/pa-daemon/src/acp/wire_events.rs:292 | Child identity is reported by the harness. |
| Model endpoint | [SOURCE] | prime-agent@c6d4da9421e6:crates/pa-core/src/models/custom.rs:210 | Shape unverified live. |
| Exact call attribution | Unknown | prime-agent@c6d4da9421e6:crates/pa-ai/src/providers/openai_completions/params.rs:340 | No parent header found. Kernel-issued calls unknown. |
| Training eligibility | Not established | n/a | Do not mark Trainable until a live probe exists. |

## Platoon definitions

- **No code definitions** for pi, OpenCode or Prime Agent. Built-in harness modules are `codeact`, `openhands`, `oracle`, `platoon_bash`, `react` (platoon@efe3b277c82c:platoon/harness/builtin/__init__.py), and the built-in specs are `mini-swe-agent`, `openhands`, `platoon-bash`.
- Mentions are in Draft RFCs only. [Platoon RFC 0005](https://github.com/ApGa/platoon/blob/efe3b277c82c/docs/rfcs/0005-gateway-dialects-and-tito.md) lists `pi` and `opencode` as OpenAI Chat clients (platoon@efe3b277c82c:docs/rfcs/0005-gateway-dialects-and-tito.md:29). This matches the plain chat-completions traffic I observed. The dialect module exists at `platoon/gateway/dialects/openai_chat.py`.
- [Platoon RFC 0001](https://github.com/ApGa/platoon/blob/efe3b277c82c/docs/rfcs/0001-native-multi-agent.md) says "pi subagent extension ... exact: the extension calls the agent API" (platoon@efe3b277c82c:docs/rfcs/0001-native-multi-agent.md:202). That extension does not exist in Platoon or upstream pi. Pi's example spawns plain `pi` processes and calls no Platoon API, so treat the row as a design intent.
- Platoon's table rates header-derived native child identity as `inferred`. OpenCode's child headers belong in that level, not `exact`.

## Implications for platoon-harness

Recommended adapter paths, in priority order:

1. **pi through `--mode rpc`.** Native RPC path, no ACP overlap with others, clean hidden-call profile, and spawn stays ours. This is the recommended exact-training candidate.
2. **OpenCode through the shared ACP driver first, then an optional HTTP adapter.** ACP gives Operational and basic Observable with almost no OpenCode-specific code, and exercises the "different integration path" the brief asks for. Add `opencode-http` as a versioned EXPERIMENTAL extension pinned to `>=2.2,<2.3` for steer, queue, inbox evidence, child sessions and per-session permissions.
3. **Prime Agent after a live probe.** Reuse the pi JSONL codec if the command match holds, and keep ACP as the fallback. Do not ship capability claims from source alone.

Concrete rules:

- **One process per agent for trainable runs.** Give each its own config directory and a short-lived scoped credential. This is the only path here that yields exact identity without trusting headers.
- **Treat credentials as agent-visible.** Environment reaches tool shells [LIVE for OpenCode]. Issue scoped gateway keys, and never pass a user's long-lived key through config variables.
- **Always pin the model and refuse to prompt otherwise.** Add a conformance check: after session creation, verify the effective model equals the requested one. On OpenCode also deny or disable hosted providers in restricted runs.
- **Force direct tool exposure** (`codemode: false`, `exposure: direct`) for coordination tools, and verify the tool is in the catalog before the first prompt. Both harnesses default to hiding it.
- **Model approvals as a capability with three values:** native (OpenCode), extension-gated (pi), none (Prime Agent). Show the last two honestly. An extension gate must not be presented as a sandbox.
- **Model message delivery as boundary-based.** Normalize to `steer` and `queue` semantics; never claim mid-generation injection. Record `session.inbox.delivered` as observed exposure on OpenCode. On pi use `queue_update` plus the following `message_start`. Normalize completion on `agent_settled` and `session.execution.*`.
- **Build reconnect around snapshot-then-subscribe.** OpenCode SSE loses events by contract, so subscribe first, then read messages, inbox and permissions, then dedupe on `durable.seq`.
- **Label non-policy calls.** Mark OpenCode title and compaction calls as non-policy and exclude them unless positively identified. Consider a small upstream request for a purpose header, or test the `model.request` plugin hook (opencode@ff90ed91607c:packages/plugin/src/promise/session.ts:185).
- **Doctor checks:** OpenCode major version, Node version for pi, `uv` for Prime Agent, `content-type` on server probes.
- **Subscription policy.** Use each harness's own login and never extract tokens. Anthropic states that third-party developers may not "route requests through Free, Pro, Max, or Ultra plan credentials on behalf of their users" and that developers should use API keys (https://code.claude.com/docs/en/legal-and-compliance, retrieved 2026-11-02). pi and Prime Agent ship Anthropic subscription logins, and OpenCode can drive the local `claude` binary. Our docs should steer Claude models in these harnesses toward API keys and leave the decision to the user. I could not find a stated policy from pi's provider page.

## Taste notes

- **pi's `agent_end` versus `agent_settled` split is excellent.** It names exactly the question a supervisor asks. Copy the idea.
- **pi's delta-then-authoritative rule** keeps streams linear and gives one source of truth. Copy this for our event model.
- **pi's small command vocabulary and strict framing documentation** show how little a control protocol needs. Aim for that size.
- **OpenCode's inbox is the right abstraction:** admission, delivery mode and delivery event are separate durable facts. Our delivery semantics should look like this.
- **OpenCode's experimental path convention** is cheap and clear: stability is visible in the URL and enforced by a test. Adopt it for our command API.
- **Prime Agent's `_meta` namespace and failure taxonomy** are tasteful: extensions stay out of protocol roots, and `retryable` is deliberately narrow because a retry is not an idempotent replay.
- **Avoid silent defaults that change the trust boundary.** OpenCode's hosted fallback and both harnesses' hidden MCP exposure surprised an integrator. Our defaults should fail loudly.
- **Avoid unversioned drift between docs and binary.** OpenCode's public `/docs` describes routes that now return HTML. Generate docs from the schema and pin them to releases.

## Unknowns and risks

- **Prime Agent is unverified live.** Streaming shape, `models.json`, kernel bootstrap, daemon lifecycle, and child call identity all need a probe. This needs the owner's decision on the blocked command.
- **OpenCode API churn.** The surface moves quickly (v2.0.29 on 2026-10-14, 2.2.5 now), and the spec still calls itself experimental. Pin narrowly.
- **OpenCode gaps:** log replay returned nothing past `log.synced`, cause unknown. Retry semantics of a client-supplied prompt `id` were not tested, and idempotent retry depends on them.
- **Compaction:** no successful compaction was observed on OpenCode or pi, so provenance across compaction is unconfirmed for both.
- **OpenCode `/api/experimental/client-mcp`** (opencode@ff90ed91607c:packages/protocol/src/groups/mcp.ts:10) may offer client-hosted tools. Not studied.
- **Token data.** None of these surfaces expose token IDs or logprobs. They must come from the Platoon gateway, which this report did not exercise. The critic's pi probe did; OpenCode and Prime Agent remain untested there.
- **pi extension trust.** User or project extensions can add subagents or alter tool calls, so training runs should use `--no-extensions` plus an explicit `-e` list, and project trust off. Not probed as a combination.
- **Shared-host probing.** Fixed ports and auto-approval both caused real side effects here. Later live tests should use a pinned model, a network-restricted sandbox where possible, and no blanket approval.
- **Clean-room rule.** No search surfaced an implementation named platoon-harness, and none was opened.
