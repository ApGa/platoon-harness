# Codex adapter research

## Inspected

| Project | Commit or version | Date | License |
|---|---|---|---|
| openai/codex (default branch clone) | `05c08d765523` | 2026-11-02 | Apache-2.0, with NOTICE (Ratatui MIT attribution) |
| openai/codex protocol files at `rust-v0.164.0` | tag commit `6aaac6948030` | fetched 2026-11-02 | Apache-2.0 |
| Codex CLI (standalone install, probed) | `codex-cli 0.164.0`; latest stable is 0.166.0 | 2026-11-02 | Apache-2.0 |
| `@openai/codex-sdk` (npm) | 0.166.0 | 2026-11-02 | Apache-2.0 |
| `openai-codex` (PyPI) | 0.163.0, pins `openai-codex-cli-bin==0.163.0` | 2026-11-02 | Apache-2.0 per repo `pyproject.toml` |
| ApGa/platoon | `efe3b277c82c` | 2026-10-28 | MIT AND Apache-2.0 |
| Official docs | `developers.openai.com/codex/*` (redirects to `learn.chatgpt.com/docs/*`) | 2026-11-02 | n/a |

Evidence notation: `codex@05c08d765523:…` and `platoon@efe3b277c82c:…`. The clone is ahead of the installed CLI, so line numbers track HEAD and behavior claims come from 0.164.0.
- **PROBE-LIVE**: real model, native login, 3 short turns, this report.
- **PROBE-STUB**: real `codex app-server` 0.164.0 against a scripted local Responses stub, isolated `CODEX_HOME`, dummy key, no paid model.
- **SCHEMA**: `codex app-server generate-json-schema [--experimental]` from 0.164.0.
- Labels: IMPLEMENTED, DOCUMENTED-ONLY, DRAFT/RFC, EXPERIMENTAL.
- Recorded flows: `docs/research/fixtures/codex-appserver-sample.jsonl`.

## 1. Integration paths

| Path | Upstream label | Our label | Evidence | Fit |
|---|---|---|---|---|
| `codex app-server` over stdio (JSONL, JSON-RPC without the `jsonrpc` member) | CLI reference: **Experimental**. Docs call it the integration for deep clients | EXPERIMENTAL by label, IMPLEMENTED in behavior | `https://developers.openai.com/codex/cli/reference`; CLI help `[experimental]`; `https://developers.openai.com/codex/app-server`; Experimental means "OpenAI may remove or change it" (`https://learn.chatgpt.com/docs/feature-maturity.md`) | **Primary** |
| `codex exec --json` | **Stable** | IMPLEMENTED | CLI reference; `codex@05c08d765523:codex-rs/exec/src/exec_events.rs:11` | One-shot fallback |
| `codex mcp-server` | **Removed** | gone | Docs: "have been removed. Use the Codex app server" (`https://developers.openai.com/codex/sdk`); changelog #42993; not in 0.164.0 subcommands | Do not use |
| TypeScript SDK | npm, no maturity label found | IMPLEMENTED | Wraps `codex exec --experimental-json`, an alias of `--json` (`codex@05c08d765523:sdk/typescript/src/exec.ts:95`, `codex-rs/exec/src/cli.rs:65`) | No: exec limits, Node dependency |
| Python SDK `openai-codex` | "Stable release", `Production/Stable` classifier | IMPLEMENTED | Drives app-server JSON-RPC, pins its own runtime binary (`codex@05c08d765523:sdk/python/pyproject.toml:19`); `CodexConfig(codex_bin=…)` overrides | Reference only |
| Shared daemon (`codex app-server daemon`, `proxy`, `--listen unix://`) | "experimental … lifecycle contract may change" | EXPERIMENTAL | `codex@05c08d765523:codex-rs/app-server-daemon/README.md:3`; "per-client environment isolation is not provided" (`:24`) | No: a run needs its own env |
| WebSocket `--listen ws://` | "experimental and unsupported" | EXPERIMENTAL | App-server docs | No |

Tension: the most stable-looking SDK sits on a surface the CLI reference calls Experimental. Treat the protocol as version-pinned, not as a contract.

### Protocol inventory (SCHEMA, 0.164.0)

Stable bundle: 106 client requests, 1 client notification (`initialized`), 10 server requests, 85 notifications. `--experimental` adds 69 client requests and 1 server request (`currentTime/read`).

| Capability | Method or event | Stable handshake? | Notes |
|---|---|---|---|
| Handshake | `initialize` → `initialized` | Yes | Before it: `-32600 Not initialized`; second call: `Already initialized` |
| Experimental opt-in | `capabilities.experimentalApi: true` | n/a | Refused with `<descriptor> requires experimentalApi capability`, for methods and fields (`codex@05c08d765523:codex-rs/app-server-protocol/src/experimental_api.rs:30`) |
| Thread | `thread/start`, `thread/resume`, `thread/fork`, `thread/read`, `thread/turns/list`, `thread/items/list`, `thread/list`, `thread/loaded/list`, `thread/unsubscribe`, `thread/archive`, `thread/delete` | Yes | Stable `thread/start` fields include `config`, `modelProvider`, `approvalPolicy`, `approvalsReviewer`, `sandbox`, `developerInstructions`, `baseInstructions`, `ephemeral`, `threadSource` |
| Turn | `turn/start`, `turn/steer`, `turn/interrupt` | Yes | `turn/start` takes `sandboxPolicy`, `approvalPolicy`, `outputSchema`, `toolOutput`, `clientUserMessageId` |
| Context | `thread/inject_items`, `thread/compact/start` | Yes | Injects raw Responses items with no turn |
| Items | `item/started`, `item/completed`, `item/agentMessage/delta`, `item/commandExecution/outputDelta`, `item/reasoning/*`, `turn/diff/updated`, `turn/plan/updated`, `thread/tokenUsage/updated` | Yes | `item/completed` is authoritative |
| Approvals | `item/commandExecution/requestApproval`, `item/fileChange/requestApproval`, `item/permissions/requestApproval`, `serverRequest/resolved` | Yes | Decisions: `accept`, `acceptForSession`, `decline`, `cancel`, plus an execpolicy variant for commands. `availableDecisions` and `additionalPermissions` are experimental fields |
| MCP | `mcpServer/elicitation/request`, `mcpServerStatus/list`, `mcpServer/tool/call`, `config/mcpServer/reload` | Yes | Elicitation answer: `accept`, `decline` or `cancel`, with `content` |
| User input | `item/tool/requestUserInput` | Yes in schema | Docs call `tool/requestUserInput` experimental |
| Dynamic tools | `item/tool/call` (schema stable), `thread/start.dynamicTools` (experimental) | No | Usable only with opt-in |

Experimental at 0.164.0 and relevant here (`codex@05c08d765523:codex-rs/app-server-protocol/src/protocol/v2/thread.rs:111,145,163`):
- `thread/start`: `dynamicTools`, `multiAgentMode`, `permissions`, `environments`, `experimentalRawEvents`, `historyMode`.
- `turn/start`: `multiAgentMode`, `collaborationMode`, `additionalContext`, `responsesapiClientMetadata`.
- `thread/fork`: `beforeTurnId`, `path`.
- `thread/resume`: `path`, `history`.
- `thread/list`: `parentThreadId`, `ancestorThreadId`.
- Methods: `thread/queue/*`, `thread/settings/update`, `turn/settings/update`, `process/*`, `collaborationMode/list`, `thread/backgroundTerminals/*`.

`rawResponse/completed` and `rawResponseItem/completed` are "internal-only" and absent from both schema bundles (`codex@05c08d765523:codex-rs/app-server-protocol/src/protocol/common.rs:2052,2054`). Experimentally annotated notifications are not filtered out of the stable schema, so the 85-notification list is not a stability statement.

## 2. MCP tool injection

| Scope | Mechanism | Verified |
|---|---|---|
| Per thread | `thread/start.config = {"mcp_servers": {"coord": {...}}}` (stable field) | PROBE-LIVE: `mcpServerStatus/list` shows connected; `mcpServer/tool/call` returned the per-thread env value. PROBE-STUB with no `experimentalApi`: works |
| Per process | `codex app-server -c 'mcp_servers.coord={command="…",args=[…],env={…}}'` | PROBE-STUB via `codex -c … mcp list` and `exec -c`; `app-server -c` not run separately. Inline table and dotted forms apply. `-c` wrote no `config.toml`. An unknown key (`bogus=1`) was accepted silently |
| One-shot | `codex exec -c … --ignore-user-config` | PROBE-STUB. "Authentication still uses CODEX_HOME" (CLI reference) |
| Avoid | `codex mcp add`, `config/value/write`, `config/batchWrite` | All persist to user config |

Facts that shape the design:
- **Thread `config` overlays, not replaces.** In PROBE-LIVE the user's own MCP server still started beside `coord`. Disabling one needs `mcp_servers.<name>.enabled=false` by name (documented, untested here).
- **Agent-called MCP tools need an approval mode.** Under `approvalPolicy: never`, a tool with no annotations failed with "MCP tool call requires approval, but approval policy is never" (PROBE-STUB; `codex@05c08d765523:codex-rs/core/src/mcp_tool_call.rs:1694`). Setting `default_tools_approval_mode = "approve"` fixed it. `mcpServer/tool/call` from the client does not hit this path.
- **Children inherit servers, each with its own process.** A v1 child got `mcp__coord` tools and a second stdio process with the **same env** (two `start_pid` lines, same scope, PROBE-STUB). An env token therefore identifies the root, not the child.
- **`tools/call` `_meta` carries runtime identity** (IMPLEMENTED, not documented in the MCP guide). PROBE-STUB from a child: `callId`, `threadId`, `sessionId`, `windowId`, `itemId`, `progressToken`, plus `x-codex-turn-metadata` with `turn_id`, `parent_thread_id`, `subagent_kind`, `thread_source` (`codex@05c08d765523:codex-rs/core/src/mcp_tool_call.rs:1308-1311,1374`). Set by Codex, outside model arguments, so it is a good caller claim. It is not a credential.
- **Wire shape.** MCP tools arrive as `{"type":"namespace","name":"mcp__coord"}` with nested tools (PROBE-STUB).
- **Live catalog differs from the stub.** `gpt-6.1-sol` received namespaces plus a `custom` tool `exec` (Code Mode), and `coord` did not appear in `additional_tools` (PROBE-LIVE). No live turn had the model call `coord`. See risks.

Isolation options:

| Option | User config | Native login | Use |
|---|---|---|---|
| A. Shared `CODEX_HOME` plus `config` overlay | Inherited, plus skills, plugins, MCP | Yes | Everyday mode. 15k prompt tokens for "OK" (PROBE-LIVE) |
| B. Per-run `CODEX_HOME` | None | **No**. Copying `auth.json` is out of scope for us | API-key and gateway runs, training. Requires `env_key` provider (PROBE-STUB) |
| C. `exec --ignore-user-config` | Skipped | Yes | One-shot only; app-server has no such flag at 0.164.0 |

Project `.codex/config.toml` cannot set `model_providers`, `model_provider`, `openai_base_url` or `profile`, and loads only when trusted (`https://developers.openai.com/codex/config-advanced`).

## 3. Model endpoint and auth

- `model_providers.<id>`: `name`, `base_url`, `env_key`, `experimental_bearer_token`, `auth` (command-backed), `gateway_oauth`, `wire_api`, `query_params`, `http_headers`, `env_http_headers`, retry and timeout fields (`codex@05c08d765523:codex-rs/model-provider-info/src/lib.rs:151-217`).
- `wire_api` accepts only `responses`; `chat` is a hard error (`codex@05c08d765523:codex-rs/model-provider-info/src/lib.rs:116,139`).
- A thread-scoped provider works: `thread/start {modelProvider, config:{model_providers:{…}}}` routed to the stub with no provider in user config (PROBE-STUB).
- Resume needs the same provider: input is rejected on a mismatch, including launch overrides (`codex@05c08d765523:codex-rs/app-server/README.md:336-345`, HEAD text, not in the 0.164.0 README; treat as coming).
- Custom providers used HTTP POST `/v1/responses` (PROBE-STUB). Platoon's RFC notes Codex "prefers websockets" and falls back on 426 (`platoon@efe3b277c82c:docs/rfcs/0005-gateway-dialects-and-tito.md:62`).
- `openai_base_url` retargets the built-in provider without a new entry.

| Login | Billing | Docs say |
|---|---|---|
| ChatGPT (`codex login`) | Plan limits | Default for people. Tokens cached in `auth.json` or the keyring; Codex refreshes them |
| API key (`CODEX_API_KEY`, `codex login --with-api-key`) | API rates | "The right way to authenticate automation is with an API key" (`https://learn.chatgpt.com/docs/auth/ci-cd-auth.md`) |
| Access token | Enterprise | Trusted automation only |
| `chatgptAuthTokens` | External host | Experimental, host-managed (`codex@05c08d765523:codex-rs/app-server-protocol/src/protocol/v2/account.rs:100`). We do not need it |

### Third-party use of a ChatGPT login

- **Spawning the user's own `codex` under its own login is fine for local, user-driven use.** Basis: app-server and SDK are published for this; the Python SDK "reuses your existing Codex authentication"; the user's process holds the credential and we never touch it. This is a reading of docs, not legal advice.
- The Sign in with ChatGPT page is a separate partner OAuth flow. It lists plan-usage apps and open-source integrations including OpenCode and Pi (`https://learn.chatgpt.com/docs/sign-in-with-chatgpt.md`). We are not on it and do not need it, because we do not perform OAuth.
- Docs do not state a general rule for third-party tools. A maintainer pointed to the Terms and said "I'm not qualified to answer" (`https://github.com/openai/codex/discussions/8338`).
- OpenAI Terms pages returned HTTP 403 to fetch; text below comes from search snippets, including a page marked "previous version", and is unverified: no sharing credentials or making the account available to others; no circumventing rate limits.

Must not do:
- Read, copy, parse or seed `auth.json`; the CI guide allows copying only for trusted private runners, one machine at a time.
- Call OAuth refresh; "not 'call the refresh API yourself'".
- Reuse a subscription token in our own HTTP client or a proxy, or as an API credential.
- Serve one login to several people, or run a hosted service on it.
- Expose runs to untrusted input: "Don't expose Codex execution in untrusted or public environments" (`https://developers.openai.com/codex/auth`). ChatGPT auth in CI is barred for public or open-source repositories.
- Impersonate a known client. `clientInfo.name` becomes the wire `originator` and User-Agent (PROBE-STUB) and feeds compliance logs.
- Default unattended, high-volume or training runs to a plan login. Use API keys or a gateway.

## 4. Native multi-agent

Current default-on feature (`agents.enabled`, `features.multi_agent`), plus `features.multi_agent_v2`. The account's live model received v2 prompts ("You are `/root`"); the stub with an unknown model got v1. PROBE-STUB covers both.

| | v1 | v2 |
|---|---|---|
| Tool namespace | `multi_agent_v1`: `spawn_agent`, `send_input`, `resume_agent`, `wait_agent`, `close_agent` | `collaboration`: `spawn_agent`, `followup_task`, `send_message`, `interrupt_agent`, `list_agents`, `wait_agent` |
| Spawn result | `{"agent_id","nickname"}` | `{"task_name":"/root/child1"}` |
| Parent item | `collabAgentToolCall`, `tool:"spawnAgent"`, `id`=call id, `senderThreadId`, `receiverThreadIds:[child]`, `prompt`, `model`, `agentsStates` | `subAgentActivity`, `kind` started/interacted/interrupted/completed, `id`=call id or `subagent-completed-<turn>`, `agentThreadId`, `agentPath`, `model` |
| Wait item | `receiverThreadIds:[child]`, `agentsStates` with final message | `collabAgentToolCall` wait with empty `receiverThreadIds` |
| `agent_name` in metadata | `/root` even in the child: unusable | `/root/child1` |
| Context | Not checked | `fork_turns` defaults to `all`: the child request held parent history items |

Child discovery, observed in both versions on one connection:
- **No `thread/started` for a child.** First signal is `thread/status/changed` for an unknown id, then the spawn item. `thread_started` emits only from start and fork handlers (`codex@05c08d765523:codex-rs/app-server/src/request_processors/thread_processor.rs:1766,5937`).
- The connection then receives the child's `turn/*`, `item/*`, `thread/tokenUsage/updated` and approval requests, tagged with the child `threadId`. A child approval arrived and resolved on the parent connection (`stubApproval` in the fixture).
- Stored `Thread` gives the links: `parentThreadId`, `source.subAgent.thread_spawn{parent_thread_id, depth, agent_path, agent_nickname, agent_role}`, `agentNickname`, `agentRole` (`codex@05c08d765523:codex-rs/protocol/src/protocol.rs:3203`). `thread/list.parentThreadId` needs opt-in.
- Child `turn/started` has `rootTurnId` = the parent turn. `parentTurnId` is null or absent there. The exact parent turn appears only in wire metadata.
- `exec --json` reports only root items and root-only usage: 60/11 tokens, excluding the child's 7/3 (PROBE-STUB).

Wire identity for a child request (PROBE-STUB; `codex@05c08d765523:codex-rs/core/src/client.rs:172,175`; `codex@05c08d765523:codex-rs/core/src/responses_metadata.rs:53,56,473`):

```text
thread-id: <child>            session-id: <root>            x-client-request-id: <child>
x-codex-parent-thread-id: <parent>                          x-openai-subagent: collab_spawn
x-codex-window-id: <child>:0  prompt_cache_key: <root>
x-codex-turn-metadata: {turn_id, parent_thread_id, parent_turn_id, root_turn_id,
                        subagent_kind:"thread_spawn", thread_source:"subagent", request_kind, ...}
```

Reconciliation rules:

| Rule | Reason |
|---|---|
| Child key = `(backend process, threadId)`; create on the first of status event, spawn item or notification; never wait for `thread/started` | No such event |
| Spawn edge = parent `threadId` + `turnId` + item `id` → child `threadId`; confirm with `thread/read` | `parentThreadId` is stable, the filter is not |
| Do not use `Thread.sessionId` as a tree root | Stored child showed its own id while the wire `session-id` was the root; docs imply otherwise |
| Per-thread usage counts only that thread's calls: root 71 = 15+24+32, child 10 | Run total = sum over threads. No rollup exists, so none must be subtracted |
| Never sum `last`. Take increases in `total` per thread, or dedupe on response id | Same update re-emitted at interrupt (PROBE-LIVE), and on full-history resume or fork, including under the fork's id (earlier attempt, same CLI) |
| Key items by `(threadId, turnId, itemId)` | Stub ids repeat across threads; in live runs `exec-<uuid>` is not the model `call_id` |
| Treat `wait` output as observed exposure of child text in the parent | `agentsStates.message` and the tool result carry it |
| Treat `fork_turns=all` input as inherited, not as new child context | Prevents double attribution of parent tokens |
| Mark review, compact, memory and Auto-review work as hidden | Internal sources (`x-openai-subagent: review/compact/memory_consolidation`); Auto-review calls did not appear in the thread's usage (PROBE-LIVE) |
| Native child identity level: `inferred` | Same credential as the parent; matches `platoon@efe3b277c82c:docs/rfcs/0001-native-multi-agent.md:199` |

Kill-switch: `[features] multi_agent = false` or `[agents] enabled = false` removes every collab tool (PROBE-STUB). Custom agents inherit permissions, provider and MCP; they cannot override them (`https://developers.openai.com/codex/subagents`).

## 5. Sandbox and approvals

Wire values (rejected otherwise at 0.164.0):
- `sandbox`: `read-only`, `workspace-write`, `danger-full-access`.
- `approvalPolicy`: `on-request`, `never`, `untrusted`, or `{granular:{…}}`.
- `sandboxPolicy.type` (turn): `readOnly`, `workspaceWrite`, `dangerFullAccess`, `externalSandbox`.
- `approvalsReviewer`: `user`, `auto_review`.

Doc examples `"sandbox":"workspaceWrite"` and `"approvalPolicy":"unlessTrusted"` are **rejected** (`-32600 unknown variant`, PROBE-STUB). `untrusted` is retired in docs (`https://developers.openai.com/codex/agent-approvals-security`) but accepted by 0.164.0.

- Settings on `turn/start` persist for later turns, except `outputSchema`.
- `approvalsReviewer` follows user config. With the probing user's `auto_review`, a required approval went to Auto-review, with `item/autoApprovalReview/started|completed` and `guardianWarning`, and **no client request** (PROBE-LIVE). Sending `approvalsReviewer:"user"` overrode it (response echo on an ephemeral thread, no turn). The client-request flow itself is recorded in PROBE-STUB, where the reviewer defaults to `user`.
- `on-request` plus `readOnly`: the command first ran sandboxed and failed (exit 1), then the model re-requested escalation (PROBE-LIVE). `echo hi` would not have needed approval.
- **`accept` does not fix the outcome (critic probe).** With `approvalPolicy: untrusted`, `sandbox: read-only` and identical stub input, 29 of 48 accepted commands created the file and 19 failed with EROFS, with or without a concurrent `turn/steer`. Cause not established. Drivers must read `item/completed` status and exit code, never infer success from the decision.
- Order: `item/started` (commandExecution) → `requestApproval` → client reply → `serverRequest/resolved` → `item/completed`. `requestApproval.kind:"humanCommand"` at HEAD is experimental.
- `thread/shellCommand` and experimental `process/spawn` run outside the sandbox. Never route agent input there.

Linux behavior:

| Case | Result | Evidence |
|---|---|---|
| Bubblewrap present (0.4.1), user namespaces available | Read-only: EROFS in cwd and `/tmp`. Workspace-write: cwd writable, `$HOME` read-only, DNS blocked | Probe via `codex sandbox` |
| No system `bwrap` on PATH | Falls back to bundled `codex-resources/bwrap`, still enforced; startup warning | Probe; `codex@05c08d765523:codex-rs/sandboxing/src/bwrap.rs:21` |
| User namespaces blocked | Startup warning; sandboxed commands cannot run. Docs warn about Docker | Source and docs only, not reproduced |
| Landlock | Legacy; "rejected for these policies", disable `features.use_legacy_landlock` | `codex@05c08d765523:codex-rs/linux-sandbox/README.md:47` |
| WSL1 | Unsupported | `codex@05c08d765523:codex-rs/sandboxing/src/bwrap.rs:30` |

Never fall back silently to `danger-full-access`. Inside an outer sandbox, use `externalSandbox` and declare it. `codex exec` also reads stdin: an inherited open stdin hung at "Reading additional input from stdin..." until the timeout; use `</dev/null` (PROBE-STUB). Default exec sandbox is read-only and it needs `--skip-git-repo-check` outside Git.

## 6. Live probe results

Fixture: `docs/research/fixtures/codex-appserver-sample.jsonl` (header line, then `{src,t_ms,dir,msg}`; ids renumbered; account, moderation and prompt bodies removed). Scanned for emails, tokens, paths and host names.

Turns on 0.164.0: 3 of 3, all short.

| Step | Result |
|---|---|
| Startup | `initialize` 2.0 s, `thread/start` 2.7 s with user config |
| Turn 1 "Reply with exactly: OK" | Text `OK`, `phase:"final_answer"`, 3.1 s, 15,087 tokens |
| Fork, unsubscribe, resume | `forkedFromId` set; `excludeTurns:true` returned no turns and no deprecation notice; `thread/turns/list` paged history |
| Turn 2 approval | `on-request`, read-only: sandbox failure, escalation, Auto-review approved, file created. Three model calls |
| Turn 3 steer and interrupt | Wrong `expectedTurnId` → `-32600`. Valid steer returned `{turnId}`, and the input appeared as a `userMessage` item before the next model call. `turn/interrupt` → `{}`, then `turn/completed status:"interrupted"` with `items:[]`, `itemsView:"notLoaded"` |
| Client approval | Recorded in PROBE-STUB, because the live path used Auto-review and the 3-turn limit was spent |

Usage:

| Event | Fields | Exactness |
|---|---|---|
| `thread/tokenUsage/updated` (stable) | `threadId`, `turnId`, `tokenUsage.total` and `.last` (`inputTokens`, `cachedInputTokens`, `cacheWriteInputTokens`, `outputTokens`, `reasoningOutputTokens`, `totalTokens`), `modelContextWindow` | `last` is provider-reported per response. No response id. Can arrive after later items |
| `rawResponse/completed` (internal, `experimentalRawEvents`) | `responseId`, same `usage`, `usageMetadata` | Exact per model response. All 5 matched `last` |
| `exec --json` `turn.completed` | Summed `usage`, snake_case | Per turn, root thread only |
| `account/rateLimits/updated` | Plan windows | Account data: keep out of traces |

- Sum check: 15,087 + 15,402 + 15,518 + 15,581 + 15,636 = 77,224 = final `total`.
- The call cut by interrupt reported nothing, so spend on interrupted calls is **unmeasured**. Label totals as a lower bound.
- `cachedInputTokens` is inside `inputTokens`.
- No token ids, log probabilities or prompt hashes on this surface.

Interrupt scope (PROBE-STUB, v1 and v2): `turn/interrupt` on a parent ended the parent in about 30 ms and **did not stop a running child**. The child finished its model call 5.5 s later with status `completed`. Shutdown cascades exist in source (`codex@05c08d765523:codex-rs/core/src/agent/control/legacy.rs:110`), but that path is agent shutdown, not `turn/interrupt`.

## 7. Capability matrix row: Codex 0.164.0

| Capability | Level | Evidence | Limitations |
|---|---|---|---|
| Launch | Implemented; upstream Experimental | PROBE-LIVE, stdio; `initialize` stable | Pin versions. Avoid daemon |
| Streaming | Implemented | `item/*`, deltas, `turn/*` | `turn/completed.items` may be empty; page history |
| Tool injection | Implemented | `thread/start.config.mcp_servers`, per thread; `-c` per process | Needs approval mode. Live model visibility unverified |
| Messaging | Implemented | `turn/start` idle; `turn/steer` active; `thread/inject_items` | Steer fails with no active turn; reaches the model at the next call boundary |
| Interruption | Implemented, partial | `turn/interrupt` | Per thread; no child cascade; lost usage |
| Approvals | Implemented | Command, file, permissions, elicitation server requests | Set `approvalsReviewer:"user"`. `never` fails closed. A decision does not fix the outcome (section 5) |
| Resume | Implemented | `thread/resume`, `thread/fork`, `excludeTurns` | Provider must match; resend `config` |
| Native subagents | Implemented, observable | v1 and v2 items, stored links | No `thread/started`; identity `inferred`; can be disabled |
| Model endpoint | Implemented | `model_providers`, `env_key`, thread scope | `responses` only; `chat` removed |
| Exact call attribution | Observable on stable: thread and turn only. Exact at gateway | Stable has no response id; `thread-id`, `x-codex-turn-metadata` on each request | Gateway headers are client claims under one key. Code Mode nests tool calls |
| Training eligibility | **Not eligible today** | No Codex spec in Platoon; Responses dialect experimental | Native-auth run: Operational + Observable only |

### Platoon's Codex support at `efe3b277c82c`

There is **no dedicated Codex harness**. `platoon/harness/builtin/specs/` holds `mini-swe-agent`, `openhands`, `platoon-bash`; the RFC's "Codex HarnessSpec" is planned work (`platoon@efe3b277c82c:docs/rfcs/0005-gateway-dialects-and-tito.md:165`, Status Draft). What exists:
- IMPLEMENTED/experimental: `POST /v1/responses` dialect (`platoon@efe3b277c82c:platoon/gateway/dialects/responses.py:1`), reasoning round-trip via `pg1:` handles (`:37`), and `dialect = "openai_responses"` in `HarnessSpec` (`platoon/harness/spec.py:78`).
- DRAFT: `NativeAgentMap` selectors for `thread-id` and `x-codex-parent-thread-id` (Platoon RFC 0001:199). No code matches.
- Gap: `function_tools` keeps only `type:"function"` entries (`responses.py:127`). Codex 0.164.0 sends `namespace` tools for MCP and collab, and `custom` for `exec`, so these are **dropped**, and a policy behind the gateway would not see coordination tools. `INPUT_ITEM_TYPES` (`:41`) refuses `custom_tool_call`, and the `namespace` on `function_call` is not preserved. Confirmed end to end by the critic: real Codex on a minted child key recorded exact calls and its MCP server connected, but the tool never reached the policy prompt, while `exec_command` did. Over the gateway, Codex coordination must therefore use the shell client.

## Implications for platoon-harness

1. Build the driver on `codex app-server` over stdio, one child process per driver instance, with a small hand-written client over generated types. Do not depend on the SDKs or daemon.
2. Initialize **without** `experimentalApi` by default. Gate opt-in per feature and record it in the manifest. Exact usage ids (`experimentalRawEvents`) belong in a separate `codex-raw` capability labeled internal-upstream.
3. Pin a tested range. At startup, compare `generate-json-schema` output with a checked-in hash and report drift through `doctor`. Treat unknown items and notifications as preserved namespaced events.
4. Set explicitly on every `thread/start`: `approvalPolicy`, `approvalsReviewer`, `sandbox`, `serviceName`, `threadSource`, and `clientInfo.name = "platoon_harness"`. Do not inherit reviewer or approval from user config silently.
5. Inject coordination through `thread/start.config.mcp_servers.<ns>` with a stdio shim, `default_tools_approval_mode="approve"`, `required=true`. The shim holds a root-scoped token in env and forwards `_meta` (`threadId`, `callId`, `itemId`, turn metadata). The runtime derives the principal from the token alone, never from arguments. `_meta` is correlation evidence (`acp-mcp.md`, binding rule 2): a child seen through it stays on the root principal and is recorded as `inferred`.
6. Never write user config. Use option A for everyday runs and B for training and CI. Offer no path that copies credentials.
7. Message delivery: idle → `turn/start`; active → `turn/steer` with `expectedTurnId` and `clientUserMessageId`; on "no active turn" retry as `turn/start`. Record the boundary as next-model-call, not immediate.
8. Cancellation: the driver must walk descendants (`thread/list parentThreadId` or its own graph) and call `turn/interrupt` on each. Treat this as a required conformance test.
9. Native subagent policy per role: `allow-observed` (default for everyday use) or `disabled` (`features.multi_agent=false`, required for Trainable). In Trainable, spawning goes through our primitives with one Codex thread and scoped key per agent, which gives exact identity.
10. Usage: journal per-thread `total` deltas, mark `measured_from: provider`, set `coverage: lower_bound` after interrupts, keep plan rate limits out of traces.
11. Capability levels: native login = Operational + Observable. API key or custom provider = same, with wire headers at a proxy. Trainable requires a Platoon gateway provider and no opaque internal subagents.
12. Upstream proposal for Platoon: a Codex `HarnessSpec`, Responses `namespace` and `custom` handling, and `NativeAgentMap`. Isolate as a versioned experimental adapter until merged.
13. Use the scripted stub approach from this research as the CI fixture for the driver: it exercises the real binary with no credentials or spend.

## Taste notes

- Elegant: one Thread → Turn → Item model across live events and history; `item/completed` is the single authoritative state.
- Elegant: per-field experimental gating with a uniform refusal; version-matched schema generated by the binary itself.
- Elegant: approvals as server requests plus `serverRequest/resolved`, which suits multi-client races and maps well onto our approval events.
- Elegant: `expectedTurnId` as an optimistic check on steering. Copy that shape for commands.
- Elegant: identity travels out of band from model arguments (`_meta`, headers).
- Avoid: lifecycle gaps such as a child with no started event, or `source:"vscode"` for an app-server thread. Every actor should have a birth event.
- Avoid: doc examples and enums drifting from the wire, and two namings for one thing (`collabToolCall` in docs, `collabAgentToolCall` on wire, `collab_tool_call` in exec). Generate docs from schema.
- Avoid: "internal-only" events that are the only exact source, and a 175-method surface. Keep ours small, and make exact data first-class.

## Unknowns and risks

- `codex app-server` is labeled Experimental; methods can change without deprecation. Clone HEAD already differs from 0.164.0, and the CLI is two releases behind stable.
- Whether the live model can call injected MCP tools: `coord` connected, but it was absent from `additional_tools`, and Code Mode may defer it. Needs a live turn in M1. Also check whether `_meta` is present through `exec` Code Mode calls.
- Real-model subagent flow not captured live; the 3-turn limit was kept. All child evidence is PROBE-STUB, which used fallback model metadata. Live v2 may differ.
- Code Mode: one `custom_tool_call` can issue several nested calls, and items use `exec-<uuid>` ids. Tool-to-call mapping beyond that is not established.
- User-namespace-blocked behavior not reproduced. macOS Seatbelt not tested.
- MCP approval under `on-request` without `approve` mode not tested; may surface as elicitation or `tool/requestUserInput`.
- Whether `thread/resume` restores thread-level `config` is unverified; resend it.
- Concurrency limits of one ChatGPT login across many `codex` processes, and shared `CODEX_HOME` SQLite under parallel app-servers, unknown. Rate-limit behavior for swarms unknown.
- Terms text could not be fetched directly; `openai.com/policies/*` returned 403. Get it reviewed before shipping guidance.
- Steer boundary: the in-flight response ended with 33 output tokens in both runs, so whether Codex cut it or the model stopped is unclear.
- Probe footprint: 3 live turns here plus 3 from an earlier stopped attempt. Threads were deleted; the ephemeral fork was dropped with its process. `thread/delete` took 6.7 s.
- Clean-room: no platoon-harness implementation surfaced in searches or listings, and none was opened.
