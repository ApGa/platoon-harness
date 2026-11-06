# Adapter research: Claude Code

## Inspected

| Project | Commit or version | Date | License |
|---|---|---|---|
| Claude Code CLI (installed, probed) | 2.1.316 | 2026-11-02 | Proprietary: "All rights reserved", Commercial Terms (`claude-code@f0b737f94f3b:LICENSE.md:1`) |
| `anthropics/claude-code` (examples, changelog only) | f0b737f94f3b | 2026-11-02 | Same |
| `claude-agent-sdk-python` | 2146f9d89855 = PyPI 0.2.176 | 2026-10-31 | Wrapper MIT; README says use is governed by Commercial Terms, except a component with its own LICENSE |
| `@anthropic-ai/claude-agent-sdk` (npm metadata only) | 0.3.316 | 2026-11-02 | "SEE LICENSE IN README.md" |
| `@agentclientprotocol/claude-agent-acp` (npm metadata only) | 0.99.1 | 2026-11-02 | Apache-2.0 |
| `ApGa/platoon` | efe3b277c82c (0.5.0) | 2026-10-28 | See Platoon report |
| Official docs (`code.claude.com/docs/en/`), Anthropic legal pages | retrieved 2026-11-02 | 2026-11-02 | n/a |

Doc keys, all retrieved 2026-11-02 under `https://code.claude.com/docs/en/`: `headless`, `cli-reference`, `legal-and-compliance`, `authentication`, `agent-sdk/overview`, `agent-sdk/typescript`, `agent-sdk/cost-tracking`, `agent-sdk/claude-code-features`, `agent-teams`, `sub-agents`, `sessions`, `hooks`, `permissions`, `env-vars`, `llm-gateway`, `llm-gateway-connect`, `llm-gateway-protocol`.

Labels: IMPLEMENTED, DOCUMENTED-ONLY, DRAFT/RFC, EXPERIMENTAL. Evidence tags: **[live]** real model turn on a subscription login; **[loopback]** the real CLI against a scripted local Messages server with a dummy credential and an isolated config dir; **[static]** code read, not executed.

## Bottom line

- Build a thin first-party driver that spawns the user's own `claude` binary with `-p --input-format stream-json --output-format stream-json` and speaks the control protocol. It keeps the process alive across turns and gives approvals, interrupts, hooks and MCP injection. All of it worked in the live probe.
- Native login is operational and observable, never trainable. Exact call attribution needs a gateway. A gateway needs a non-subscription credential.
- **Never set `ANTHROPIC_BASE_URL` alone.** With no gateway credential the saved claude.ai login stays active and is sent to that URL (`llm-gateway`). That would make us an intermediary of a claude.ai credential, which the terms forbid.
- **Platoon has no Claude Code harness at efe3b277c82c.** It has an experimental Messages dialect only (see "Platoon status").
- Training through Claude Code is technically reachable but must default to blocked until the owner settles the terms question (`platoon@efe3b277c82c:docs/rfcs/0005-gateway-dialects-and-tito.md:172`).

## 1. Integration paths

| Path | Status | Facts |
|---|---|---|
| `claude -p --output-format stream-json --verbose` | IMPLEMENTED, documented | NDJSON events; last line of a run is `result`. `--include-partial-messages` adds `stream_event` (`headless`). |
| `--input-format stream-json` | IMPLEMENTED, documented flag | Multi-turn over stdin in one process **[live]**. Each user message gets its own `result` plus a re-emitted `system/init` **[live]**. |
| Control protocol over the same stdio | IMPLEMENTED; partly documented | `agent-sdk/typescript` refers to "a client that drives the CLI's control protocol directly". The MIT Python SDK is the best wire reference. |
| Agent SDK for Python | IMPLEMENTED | Spawns the CLI; `query()` and `ClaudeSDKClient`. Platform wheels are 134-149 MB because they bundle the CLI (PyPI, 0.2.176); sdist 0.4 MB. `claude-agent-sdk-python@2146f9d89855:src/claude_agent_sdk/_cli_version.py:3` pins 2.1.316. |
| ACP adapter | IMPLEMENTED by third party | `@agentclientprotocol/claude-agent-acp` 0.99.1, Apache-2.0; maintainers benbrandt, aguzubiaga, cirwin; repo `agentclientprotocol/claude-agent-acp`; depends on `@anthropic-ai/claude-agent-sdk` 0.3.312 and `@agentclientprotocol/sdk` 2.1.0. `@zed-industries/claude-code-acp` and `@zed-industries/claude-agent-acp` are deprecated renames (npm, 2026-11-02). Behavior not inspected here. |
| `--bare` | IMPLEMENTED | Skips discovery of hooks, skills, agents, plugins, MCP, memory, CLAUDE.md. **Never reads OAuth or keychain**; needs an API key or `apiKeyHelper`. Docs say it "will become the default for `-p` in a future release" (`headless`). |

SDK traps:

- `_find_cli` prefers the bundled binary over `PATH` (`claude-agent-sdk-python@2146f9d89855:src/claude_agent_sdk/_internal/transport/subprocess_cli.py:255`, `:258`, `:264`). Using the SDK without `cli_path` does not run the user's install.
- The SDK removes only `CLAUDECODE` from the inherited environment (`claude-agent-sdk-python@2146f9d89855:src/claude_agent_sdk/_internal/transport/subprocess_cli.py:819`). Everything else leaks through.
- `session_store` resume reads the credentials file or macOS keychain and writes a copy with the refresh token removed to a temp config dir (`claude-agent-sdk-python@2146f9d89855:src/claude_agent_sdk/_internal/session_resume.py:327`, `:367`, `:431`). platoon-harness must not use this path.
- `HookEvent` in Python lists 10 events (`claude-agent-sdk-python@2146f9d89855:src/claude_agent_sdk/types.py:284`); the wire accepts more (`PostCompact` fired **[loopback]**).

### Sessions

| Flag | Behavior |
|---|---|
| `--session-id <uuid>` | Must be a UUID. Honored **[live]**. |
| `--resume <id or path>` | Finds the session in any project on the machine. Restored history and cost totals in a new process **[loopback]**. |
| `--resume <id> --fork-session` | New `session_id`, shared history; `x-claude-code-session-id` changes too **[loopback]**. |

SIGTERM exits 143 and leaves the turn with no result; send `interrupt` or SIGINT first (`headless`).

## 2. Control protocol (stdin and stdout)

Envelope, from `claude-agent-sdk-python@2146f9d89855:src/claude_agent_sdk/types.py:2870` and `:2899`, confirmed **[live]**:

```json
{"type":"control_request","request_id":"r1","request":{"subtype":"interrupt"}}
{"type":"control_response","response":{"subtype":"success","request_id":"r1","response":{"still_queued":[]}}}
```

| Direction | Subtype | Evidence |
|---|---|---|
| host to CLI | `initialize` (`hooks`, `agents`, `skills`, `forwardSubagentText`) | **[live]** answered in 1.2 s, before any model call. Returns commands, agents, models, `account`, `capabilities`, `pid`. Use it as the ready handshake: `system/init` only appears at the first user message. |
| host to CLI | `interrupt` (`cancel_queued` optional) | **[live]** receipt `{"still_queued":[]}` in 22 ms |
| host to CLI | `set_permission_mode` | **[live]** echoes the mode, then `system/status` |
| host to CLI | `mcp_status`, `get_context_usage` | **[live]** no model call |
| host to CLI | `set_model`, `stop_task`, `mcp_reconnect`, `mcp_toggle`, `rewind_files` | **[static]** `claude-agent-sdk-python@2146f9d89855:src/claude_agent_sdk/_internal/query.py:794`-`:865` |
| CLI to host | `can_use_tool` | **[live]** MCP tool, **[loopback]** Bash. Fields: `tool_name`, `input`, `tool_use_id`, `permission_suggestions`, `decision_reason_type`, `mcp_server`; `agent_id` when a subagent asks. |
| CLI to host | `hook_callback` (`callback_id`, `input`, `tool_use_id`) | **[live]** PreToolUse, PostToolUse, SubagentStart/Stop, Stop |
| CLI to host | `mcp_message` | **[static]** `claude-agent-sdk-python@2146f9d89855:src/claude_agent_sdk/_internal/query.py:656`; SDK-type in-process servers. Not probed. |
| CLI to host | `control_cancel_request` | **[static]** `claude-agent-sdk-python@2146f9d89855:src/claude_agent_sdk/_internal/query.py:420` |

Details that bite:

- Enabling `can_use_tool` means passing `--permission-prompt-tool stdio`; the SDK does this internally (`claude-agent-sdk-python@2146f9d89855:src/claude_agent_sdk/types.py:2304`). The `stdio` value is **not in the CLI reference**, which documents only an MCP tool name, and `claude --help` has no entry for the flag itself (it is only mentioned under `--permission-prompts`). Treat `stdio` as an SDK-private contract, tested by fixture.
- Allow reply: `{"behavior":"allow","updatedInput":<input>}`. Deny reply: `{"behavior":"deny","message":"..."}`, optional `interrupt`. Deny becomes a `tool_result` with that message plus an entry in `result.permission_denials` **[loopback]**.
- `--replay-user-messages` also echoes the host's own `control_response` back on stdout **[live]**. Ignore control responses with unknown ids.
- Closing stdin while hooks, SDK MCP servers or `can_use_tool` are configured makes later control requests fail CLI-side with "Stream closed"; keep stdin open until the session is done (`claude-agent-sdk-python@2146f9d89855:src/claude_agent_sdk/_internal/query.py:1044`).
- `--permission-prompts none` denies anything that would prompt, removes `AskUserQuestion`, and cancels unanswered MCP elicitation; v2.1.259+ (`headless`). This is the correct headless policy.
- `-p` with no host denies calls that need approval; since v2.1.302 `-p` starts in Manual mode unless something sets a mode (`headless`).

## 3. Tools, permissions, settings

| Need | Mechanism | Notes |
|---|---|---|
| Inject our tools | `--mcp-config '<json or path>'` | Stdio server connected **[live]**; `system/init.mcp_servers` shows `source: "dynamic"`; skipped entries appear in `mcp_server_errors`, silently when stderr is captured (`headless`). Fail fast on it. |
| Only our servers | `--strict-mcp-config` | Ignores `.mcp.json`, user servers, claude.ai connectors (`agent-sdk/claude-code-features`). Keep the user's servers by omitting it. |
| Tool naming | `mcp__<server>__<tool>` | Called as `mcp__probe__add` **[live]** |
| Tool visibility (critic correction) | Tool search, on by default | "Tool search is enabled by default: MCP tools are deferred and discovered on demand", including behind `ANTHROPIC_BASE_URL` (https://code.claude.com/docs/en/mcp, retrieved 2026-11-02; `claude-code@f0b737f94f3b:CHANGELOG.md:586`). **[loopback]** `system/init` listed the tool as connected, yet the request carried 13 of 26 tools and not this one. Server config `"alwaysLoad": true` or `ENABLE_TOOL_SEARCH=false` put it in the first request. The docs also define per-tool `_meta["anthropic/alwaysLoad"]: true` (not probed). So `system/init` does not prove the model can see a tool. The live fixture shows a direct call with no `ToolSearch` use, which is unexplained. |
| Pre-approve | `--allowedTools "mcp__platoon__*"` | Without this, each coordination call raises `can_use_tool` **[live]**. It approves; it does not restrict. |
| Restrict | `--tools`, `--disallowedTools` | `--tools` limits built-ins. A bare name in `--disallowedTools` removes the tool from context; a scoped rule denies matching calls (`cli-reference`). |
| In-process SDK MCP | `{"type":"sdk"}` in `--mcp-config`, routed as `mcp_message` | IMPLEMENTED **[static]**. Not needed: the same stdio or HTTP MCP server serves every harness. |
| Force an approval | `--settings '{"permissions":{"ask":["Bash(echo *)"]}}'` | **[loopback]** Read-only commands such as `echo` never prompt in any mode (`permissions`). |

Permission modes: `default` (alias `manual`), `acceptEdits`, `plan`, `auto`, `dontAsk`, `bypassPermissions`. Hook input reports Manual as `default`.

Preserving the user's setup:

| Setting | Effect |
|---|---|
| Omit `--setting-sources` | Same as `user,project,local`: CLAUDE.md, rules, skills, agents, commands, hooks, settings all load (`agent-sdk/claude-code-features`). **Use this for everyday use.** |
| `--setting-sources=` | Disables those three. Still read: managed policy, `~/.claude.json`, auto memory, claude.ai connectors unless `--strict-mcp-config`. Builtin plugins, commands and skills stayed listed **[live]**: 55 commands, 20 skills. |
| Hermetic worker | `--setting-sources=`, `--strict-mcp-config`, `CLAUDE_CODE_DISABLE_AUTO_MEMORY=1`, and an API key (optionally `--bare`). |
| Extra instructions | `--append-system-prompt-file`. Never `--system-prompt` for ordinary use: it drops the default prompt. |

Security: `-p` shows no trust dialog. A project's `.claude/settings.json` hooks and `.mcp.json` servers run even in an untrusted folder (`headless`). Spawning `claude` in a freshly cloned repo is code execution.

## 4. Stream events

The `SDKMessage` union has 39 members (`agent-sdk/typescript`). Unknown types must be preserved, not rejected: a type absent from those docs appeared in the probe.

| Event | Fields that matter | Seen |
|---|---|---|
| `system/init` | `session_id`, `model`, `tools`, `mcp_servers`, `permissionMode`, `claude_code_version`, `capabilities`, `apiKeySource` | **[live]** once per turn |
| `assistant` | `message` (Messages shape), `parent_tool_use_id`, `agent_id`, `request_id`, `uuid` | **[live]** one content block per event; `message.id` repeats across blocks |
| `user` | `tool_result` blocks, `tool_use_result`, `parent_tool_use_id`, `isReplay` | **[live]** |
| `stream_event` | Raw Messages SSE, incl. `thinking_delta`, `signature_delta`, `input_json_delta`, `message_delta.usage` | **[live]** main thread only in this probe |
| `result` | `subtype`, `is_error`, `num_turns`, `usage`, `modelUsage`, `total_cost_usd`, `permission_denials`, `terminal_reason`, `result_index` | **[live]** |
| `rate_limit_event` | `rate_limit_info` | **[live]** Account-like: do not persist raw. |
| `system/task_started`, `task_updated`, `task_notification` | `task_id`, `tool_use_id`, `subagent_type`, `spawn_depth`, `is_backgrounded`, `usage` | **[live]** |
| `system/compact_boundary` | Docs list `trigger`, `pre_tokens`; 2.1.316 also sends `post_tokens`, `preserved_segment`, `preserved_messages`, `logical_parent_uuid` | **[loopback]** |
| `system/status`, `thinking_tokens`, `background_tasks_changed` | | **[live]**/**[loopback]** |
| `command_lifecycle` | `command_uuid`, `state`: `queued`, `started`, `completed` | **[loopback]** only when the sent message has a `uuid`. **Absent from docs**; capability `msg_lifecycle_v1`. EXPERIMENTAL. |
| `system/api_retry`, `permission_denied`, `hook_*`, `session_state_changed`, `task_progress`, `tool_progress` | DOCUMENTED-ONLY here | Not seen in the probe |

Thinking: live requests carry `thinking: {"type":"adaptive","display":"updates"}` **[loopback]**. The one complete thinking block seen **[live]** had empty text and a 1168-character signature. Reasoning content is not reliably observable under native auth; never synthesize it.

`system/init.capabilities` on 2.1.316 **[live]**: `interrupt_receipt_v1`, `interrupt_cancel_queued_v1`, `interrupt_send_now_v1`, `interrupt_requeue_taken_v1`, `msg_lifecycle_v1`, `request_marker_lists_v1`, `ask_user_question_unanswered_v1`, `lifecycle_wakeup_source_v1`, `sdk_mcp_tools_list_changed`, `sdk_mcp_manifests`, `mcp_read_resource_v1`, `mcp_tool_ui_meta_v1`, `ui_surface_v1`, `mcp_call_result_not_for_model_v1`. Feature-detect on these; ignore unknown values (`headless`). `apiKeySource` was `"none"` for both the subscription and a bearer token, so it does not identify the credential.

### Usage exactness

| Field | Scope | Exactness |
|---|---|---|
| `assistant.message.usage` input and cache | One API response; **dedupe by `message.id`** | As reported by the server. Duplicates seen **[live]**. |
| `assistant.message.usage.output_tokens` | | **Placeholder** from `message_start` (`agent-sdk/cost-tracking`). **[live]** 16 versus true 137. |
| `stream_event` `message_delta.usage` | One API response | True output count, main thread **[live]** |
| `result.usage` | This turn, main loop, **excludes subagents** | **[live]** 140 output, while the tree used 144 |
| `result.modelUsage`, `total_cost_usd` | Process cumulative incl. subagents, restored on resume | Cumulative: read the latest, never sum. |
| `result.model_usage_since_last_result` | Delta since the previous result, incl. subagents | **[live]** 144 = 140 + subagent 4. Undocumented. |
| `task_notification.usage.total_tokens` | One subagent, total | **[live]** 5117 = 2 + 5111 + 4 |
| `total_cost_usd` | Client estimate from a bundled price table (`agent-sdk/cost-tracking`) | Not billing. Reported on a subscription too **[live]**. Priced a loopback mock at Haiku list, `costBasis: "list"` **[loopback]**. Always label estimated. |
| Interrupted call | | **[live]** `result.usage` zero, totals unchanged: tokens of the aborted request are unrecorded. |
| Crash | | May zero every cost field (`agent-sdk/cost-tracking`). |

So stream usage is good for budgets and display, labeled approximate. It is not per-token data: no token ids, no logprobs, no rendered prompt.

### Hooks

Events (`hooks`): SessionStart, Setup, UserPromptSubmit, UserPromptExpansion, PreToolUse, PermissionRequest, PermissionDenied, PostToolUse, PostToolUseFailure, PostToolBatch, Notification, MessageDisplay, SubagentStart, SubagentStop, TaskCreated, TaskCompleted, Stop, StopFailure, TeammateIdle, InstructionsLoaded, ConfigChange, CwdChanged, DirectoryAdded, FileChanged, WorktreeCreate, WorktreeRemove, PreCompact, PostCompact, PreModelSwitch, PostModelSwitch, Elicitation, ElicitationResult, SessionEnd.

- Common fields: `session_id`, `prompt_id`, `transcript_path`, `cwd`, `permission_mode`, `effort`, `hook_event_name`; `agent_id`, `agent_type` inside a subagent.
- Tool events add `tool_name`, `tool_input`, `tool_use_id`; PostToolUse adds `tool_response`, `duration_ms` **[live]**.
- Stop and SubagentStop add `last_assistant_message`; SubagentStop adds `agent_transcript_path`. PreCompact has `trigger`, PostCompact has `compact_summary` **[loopback]**.
- `PermissionRequest` has no `tool_use_id` **[loopback]**. Use `can_use_tool` instead.
- **No hook exposes usage or request ids.** Hooks provide lifecycle and tool anchors, not model-call data.
- Registering callbacks through `initialize` does not touch the user's settings files, and the user's own hooks still run. Prefer that over writing settings.

## 5. Native subagents and teams

Subagents: IMPLEMENTED; the tool is `Agent`, though `system/init.tools` shows it as `Task` **[live]**. Default depth 3 layers, 20 concurrent (`sub-agents`). Transcript: `~/.claude/projects/<project>/<sessionId>/subagents/agent-<agentId>.jsonl` with a `.meta.json` holding `agentType`, `toolUseId`, `spawnDepth`, `requestShape` **[loopback]**. The transcript format "is internal" and can change on any release (`sessions`).

Join keys, all observed equal for one child:

| Key | Where |
|---|---|
| `tool_use_id` of the `Agent` call | `assistant` block, `task_started.tool_use_id`, children's `parent_tool_use_id`, `.meta.json` `toolUseId` |
| `agent_id` | `task_started.task_id`, stream `agent_id`, hooks, `tool_use_result.agentId`, `x-claude-code-agent-id`, transcript filename |
| `prompt_id` | Hooks, `x-claude-code-prompt-id` (shared by children of a prompt) |
| `session_id` | Everything, `x-claude-code-session-id` |

Reconciliation rules:

- Mint a child identity only from `task_started` (or `SubagentStart` plus a matching `tool_use_id`). Attribution level stays inferred.
- **SubagentStop alone is not a child.** Compaction fired `SubagentStop` with `agent_type: ""` and an `agent_id` that had no `task_started`, no `SubagentStart`, and no `x-claude-code-agent-id` on its request **[loopback]**.
- Without `--forward-subagent-text`, subagent text and thinking are withheld from foreground runs (`headless`). Enable it, or child activity is incomplete.
- Count tokens once: per-child data comes from `task_notification` or the gateway. Never add `assistant` usage of children to `result.usage` and then also `modelUsage`.
- A resumed subagent keeps its id and starts a new run: `task_id` repeats, `run_id` differs (`sub-agents`, `agent-sdk/typescript`). Key child runs by `(agent_id, run_id)`.
- Explore and Plan are one-shot and return no agent id to Claude (`sub-agents`). Forked skills use a `forked-command-` prefix instead of a tool id (`headless`).
- **Background is the default in `-p`:** with `run_in_background` unset the subagent started in the background, the turn ended, and a later notification started an extra main turn with its own `result` and no user message **[loopback]**. So `result` is not 1:1 with user messages. Correlate by `command_lifecycle` and origin. `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1` gives simpler semantics.

Agent teams: EXPERIMENTAL, off by default, `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`. **Not available to this adapter:** "In non-interactive mode with the `-p` flag, including Agent SDK sessions, Claude doesn't spawn teammates" (`agent-teams`). Storage for reference: mailbox `~/.claude/teams/{team-name}/inboxes/{agent-name}.json`, config `~/.claude/teams/{team-name}/config.json`, tasks `~/.claude/tasks/{team-name}/`. Teammates reuse a stable name-based agent id (`llm-gateway-protocol`). Do not read or write these files. Our own coordination plays this role.

## 6. Model endpoint

Credential precedence (`authentication`): cloud provider, `ANTHROPIC_AUTH_TOKEN`, `ANTHROPIC_API_KEY`, `apiKeyHelper`, `CLAUDE_CODE_OAUTH_TOKEN`, profiles, then `/login`. A signed-in Claude apps gateway outranks these.

| Setting | Effect on subscription |
|---|---|
| `ANTHROPIC_AUTH_TOKEN` | Sent as `Authorization: Bearer`. Replaces the login for requests; login stays saved and unused (`llm-gateway-connect`). `Authorization` only, no `x-api-key` **[loopback]**. |
| `ANTHROPIC_API_KEY` | Sent as `x-api-key`. In `-p` always used when present (`authentication`). Silent billing surprise if inherited: scrub unless chosen. |
| `apiKeyHelper` in `--settings` | Sent in both headers; cached 5 minutes (`llm-gateway-connect`). |
| `ANTHROPIC_BASE_URL` **alone** | "a saved claude.ai login remains the active credential"; requests still route through the gateway (`llm-gateway`). **Forbidden configuration for us.** Deliberately not probed. |
| `CLAUDE_CONFIG_DIR=<isolated>` | No saved login exists to send. Defense in depth for gateway mode **[loopback]**. |

What a gateway sees **[loopback]**, 2.1.316, with `CLAUDE_CODE_GATEWAY_HINT_HEADERS=1`:

| Item | Value |
|---|---|
| Endpoint | `POST /v1/messages?beta=true`; base URL has no `/v1`. No `count_tokens`, `HEAD /api/hello` or `/v1/models` call seen with nonessential traffic off. |
| Always | `x-claude-code-session-id`, `x-claude-code-agent-id` on subagent requests, `anthropic-beta` (7-8 values), `anthropic-version` |
| Hints (off by default on a custom URL; v2.1.273+) | `x-claude-code-request-class` (`main`, `subagent`, `compaction` seen; docs add `workflow`, `auxiliary`), `-agent-type`, `-compaction`, `-context-compacted`, `-prev-tool-durations`, `-prompt-id` (v2.1.283+) |
| Body keys | `context_management`, `max_tokens`, `messages`, `metadata`, `model`, `output_config`, `stream`, `system`, `thinking`, `tools` |
| `system[0]` | `x-anthropic-billing-header: cc_version=…; cc_entrypoint=…`, fingerprint differed between conversations and after compaction. `CLAUDE_CODE_ATTRIBUTION_HEADER=0` is the documented client-side way to omit it for gateways (`llm-gateway-protocol`). |
| `messages` | Contains `role: "system"` entries **[loopback]**, sent for Opus 4.8+, later models and unrecognized ids (`llm-gateway-protocol`) |
| Thinking | Non-Anthropic signature `pg1:…` echoed back verbatim on later requests **[loopback]** |

Exact join: the CLI repeats the gateway's response `id` as `assistant.message.id` **[loopback]**. Platoon sets that id to its `call_id` (`platoon@efe3b277c82c:platoon/gateway/dialects/anthropic.py:186`). So `call_id -> message.id -> tool_use ids` is an exact chain through the stream, with no timing heuristics.

"Anthropic doesn't endorse, maintain, or audit third-party gateway products, and doesn't support routing Claude Code to non-Claude models through any gateway." (`llm-gateway`). A gateway serving a trained non-Claude policy is therefore an **unsupported** configuration; expect breakage on any release.

## 7. Terms

Quoted verbatim, retrieved 2026-11-02. Source in brackets.

- [legal-and-compliance, Authentication and credential use] "**OAuth authentication** is intended exclusively for purchasers of Claude Free, Pro, Max, Ultra, Team, and Enterprise subscription plans and is designed to support ordinary use of Claude Code and other native Anthropic applications."
- [legal-and-compliance, Authentication and credential use] "**Developers** building products or services that interact with Claude's capabilities, including those using the Agent SDK, should use API key authentication through Claude Console or a supported cloud provider. Anthropic does not permit third-party developers to offer Claude.ai login into their own applications, or to route requests through Free, Pro, Max, or Ultra plan credentials on behalf of their users. Moreover, developers may not collect, store, or intermediate Claude.ai credentials or session tokens — sign-in to a Claude account must complete through Anthropic's own flow."
- [legal-and-compliance, Authentication and credential use] "Nor does it prevent an end user from signing in to the unmodified Claude Code binary with their own Claude subscription, including where a platform hosts Claude Code as described under *Can customers offer Claude Code in their products?* above."
- [legal-and-compliance, Authentication and credential use] "Anthropic reserves the right to take measures to enforce these restrictions and may do so without prior notice."
- [legal-and-compliance, Can customers offer Claude Code in their products?] "**The Claude Code binary must not be modified.** Claude Code must be installed and run as published by Anthropic, and customers may not remove, disable, or restrict any authentication method built into it (including methods that permit signing in with a Claude account or the user's own API key)."
- [legal-and-compliance, Can customers offer Claude Code in their products?] "**Customers may not pay for, resell, or intermediate Claude usage on their end users' behalf.** Each end user must authenticate with their own Anthropic API key, Claude subscription plan credentials, or 3P inference provider credential"
- [legal-and-compliance, Acceptable use] "Advertised usage limits for Pro, Max, and Ultra plans assume ordinary, individual usage of Claude Code and the Agent SDK."
- [agent-sdk/overview] "Unless previously approved, Anthropic does not allow third party developers to offer claude.ai login or rate limits for their products, including agents built on the Claude Agent SDK. Use the API key authentication methods described in the Quickstart instead."
- [Consumer Terms §3, effective Oct 8, 2025, https://www.anthropic.com/legal/consumer-terms] "Except when you are accessing our Services via an Anthropic API Key or where we otherwise explicitly permit it, to access the Services through automated or non-human means, whether through a bot, script, or otherwise."
- [Consumer Terms §3, effective Oct 8, 2025, https://www.anthropic.com/legal/consumer-terms] "To develop any products or services that compete with our Services, including to develop or train any artificial intelligence or machine learning algorithms or models or resell the Services."
- [Commercial Terms D.4, effective Jun 17, 2025, https://www.anthropic.com/legal/commercial-terms] "Customer may not and must not attempt to (a) access the Services to build a competing product or service, including to train competing AI models or resell the Services except as expressly approved by Anthropic; (b) reverse engineer or duplicate the Services"

Decision for platoon-harness (engineering policy, not legal advice):

| | Rule |
|---|---|
| **May** | Spawn the `claude` the user installed, on the user's machine, under the login they made through `claude auth login` or `/login`, for that user's own work. |
| **May** | Pass a user-supplied API key or provider credential to the process, or a gateway credential we mint. |
| **May** | Run `claude auth status` in `doctor` and show only whether a login exists and which kind. |
| **May** | Say in plain text that a harness "runs Claude Code". Name our driver and profile neutrally (`claude`), since names in features are restricted. |
| **Must not** | Read, copy, store, log, refresh or forward `~/.claude/.credentials.json`, keychain entries, `CLAUDE_CODE_OAUTH_TOKEN` values, or any claude.ai token. |
| **Must not** | Offer a claude.ai sign-in in our UI, or embed, wrap or proxy Anthropic's flow. Tell the user to run `claude auth login` themselves. |
| **Must not** | Set `ANTHROPIC_BASE_URL` while a login could be the active credential. |
| **Must not** | Let one person's login serve another: no shared service mode, no remote user, no team pool. A service run on native login must be owned by the logged-in human. |
| **Must not** | Bundle, vendor or patch the binary, or depend on it through a default install. |
| **Must not** | Use "Claude Code" or Anthropic names in our product, feature or logo, or set `CLAUDE_CODE_ENTRYPOINT` to misrepresent the client. |
| **Must not** | Treat Claude-generated traces as training data for any model. |

Redistribution: the wheels and npm platform packages contain the proprietary binary. Do not re-host them. `claude-agent-sdk` as a dependency of a default install would pull 145 MB of proprietary code; MIT classifiers cover the wrapper, not the bundled binary.

Gray area to state honestly: the Consumer Terms automation clause allows "where we otherwise explicitly permit it", and the docs describe `claude -p` for scripts. But "ordinary, individual usage" is undefined, and a swarm of scripted sessions on one subscription login may exceed it. Default to warning when more than one concurrent native-login agent is configured, and recommend an API key for teams, unattended runs and anything hosted. The owner can ask Anthropic through the contact link on the legal page.

## 8. Live probe

Throwaway cwd, 14 s, one process, `--model haiku`, `--max-turns 3`, allowlisted env. Five real turns; estimated cost $0.0032 at list price. Fixture: `docs/research/fixtures/claude-stream-sample.jsonl` (283 lines; ids replaced by stable placeholders; paths, account, rate-limit, plugin and signature fields removed).

| # | Turn | Result |
|---|---|---|
| 1 | "Reply alpha" | `success`, ~1 s |
| 2 | Second stdin message, same process; asked for one `Agent` call | Multi-turn confirmed; subagent ran with all join keys present |
| 3 | `echo hi` under `default` | Ran **without** approval: `echo` is in the read-only set. Requirement not met here; see below. |
| 4 | Count to 400, `interrupt` on first delta | Receipt in 22 ms; synthetic `[Request interrupted by user]`; `result` `error_during_execution`, `is_error: true`, `terminal_reason: "aborted_streaming"`. Same process took the next turn. |
| 5 | Tiny stdio MCP server, `add(2,3)` | `can_use_tool` for `mcp__probe__add` answered allow over stdin; output returned. This is the live approval. |

Extra no-cost runs against a scripted loopback server, a separate real `claude` process with dummy credential and isolated config, no Anthropic traffic for inference:

| Check | Result |
|---|---|
| `Bash(echo *)` ask rule | `can_use_tool` for `echo hi`, denied then allowed by control response |
| Message sent during a running Bash call, default priority | `command_lifecycle: queued`, then `started` after the tool result; transcript shows `absorbed_mid_turn`; model got it in the same turn as a system reminder |
| `/compact` | `PreCompact`, `SubagentStop` (orphan), `PostCompact`, `compact_boundary`, request class `compaction`; next request has `x-claude-code-context-compacted` |
| `--resume`, `--fork-session` | New processes kept history and cost; fork got a new id |

Delivery boundaries (`agent-sdk/typescript`): no `priority` or `next` means at the next tool boundary, else next turn; `later` means a new turn; `now` with human origin moves running work to background, and `now` without that origin interrupts. `shouldQuery: false` appends context with no model call. There is no injection into a response being generated.

### Environment

Variables present here because this is inside Claude Code (names only): `CLAUDECODE`, `CLAUDE_CODE_CHILD_SESSION`, `CLAUDE_CODE_ENTRYPOINT`, `CLAUDE_CODE_EXECPATH`, `CLAUDE_CODE_MESSAGING_SOCKET`, `CLAUDE_CODE_MESSAGING_TOKEN`, `CLAUDE_CODE_SESSION_ATTENDED`, `CLAUDE_CODE_SESSION_ID`, `CLAUDE_EFFORT`, `CLAUDE_PID`.

Effect: with `CLAUDECODE=1`, `CLAUDE_CODE_CHILD_SESSION=1`, `CLAUDE_CODE_ENTRYPOINT=cli` added **[loopback]**, `-p` still ran, persisted a transcript, and sent the same `user-agent` (`claude-cli/2.1.316 (external, sdk-cli)`). Docs: a nested interactive TUI is excluded from `--resume`, `--continue` and history; `-p` still persists (`env-vars`). So the nesting flags are mostly benign for `-p`. The inherited session id, messaging socket and token are not: they belong to the parent and must never reach a child. These inherited-session variables were not probed for behavior.

Clean env: **allowlist, do not denylist.** Start from `PATH`, `HOME`, `USER`, `LOGNAME`, `LANG`, `LC_*`, `TERM`, `TMPDIR`, `SHELL`; add network and CA variables by explicit config; add only the credential and gateway variables this agent's profile selects. Native login needs nothing extra: the probe authenticated with exactly that env. This avoids inheriting `ANTHROPIC_*`, `CLAUDE_CODE_*` and `CLAUDECODE`. Subprocesses Claude Code spawns inherit `CLAUDECODE=1`, so a `platoon-harness` CLI called from Bash inside an agent should use this to detect agent context, never as an identity.

## 9. Capability matrix row

Version 2.1.316; driver path `claude -p` stream-json with control protocol.

| Capability | Status | Evidence | Limitations |
|---|---|---|---|
| Launch | Operational | **[live]** | User must install and log in. `initialize` handshake about 1 s. |
| Streaming | Observable | **[live]** | No partial events for subagents in the probe. Assistant usage output is a placeholder. |
| Tool injection | Operational | **[live]** stdio MCP | Each call needs `--allowedTools` or approval. MCP tools are deferred by default: set `alwaysLoad` (section 3). |
| Messaging | Operational | **[live]** stdin; **[loopback]** mid-turn | Tool boundary or turn boundary only. `command_lifecycle` undocumented. |
| Interruption | Operational | **[live]** | Aborted call's tokens unrecorded. |
| Approvals | Operational | **[live]** MCP, **[loopback]** Bash | `stdio` prompt tool is an SDK-private value; read-only commands skip it; `PermissionRequest` lacks `tool_use_id`. |
| Resume | Operational | **[loopback]** | Requires persisted transcript. In-process teammates do not resume. |
| Native subagents | Observable, inferred | **[live]** | Teams unavailable in `-p`. Compaction emits a false SubagentStop. Background turns break 1:1 results. |
| Model endpoint config | Operational with credential | **[loopback]** | Non-Claude models unsupported by Anthropic. `ANTHROPIC_BASE_URL` alone is forbidden. |
| Exact call attribution | Native: no. Gateway: call-to-stream join is exact; child identity stays inferred | **[loopback]** header and id join | Requires hint headers. No such reader exists in Platoon. Per-token data only from the gateway. |
| Training eligibility | **Not eligible by default** | Decision above | Native login: never. Gateway: blocked pending owner decision. Hosted Claude through gateway: eval only. |

## 10. Platoon status

- **No Claude Code harness exists.** Builtin specs: `mini-swe-agent`, `openhands`, `platoon-bash` (`platoon@efe3b277c82c:platoon/harness/builtin/specs/`). `Dialect` admits `anthropic_messages` (`platoon@efe3b277c82c:platoon/harness/spec.py:78`), so a future TOML spec could select it, with `env` carrying `{base_url}` and `{api_key}` as `platoon-bash` does (`platoon@efe3b277c82c:platoon/harness/builtin/specs/platoon-bash.toml:19`).
- Dialect: IMPLEMENTED, labeled experimental (`platoon@efe3b277c82c:platoon/gateway/dialects/anthropic.py:1`). `POST {prefix}/v1/messages` and `count_tokens` (`platoon@efe3b277c82c:platoon/gateway/server.py:235`). Agent key accepted as Bearer or `x-api-key` (`platoon@efe3b277c82c:platoon/gateway/server.py:498`).
- **Mismatch with 2.1.316 [static]:** `chat_request` raises on any role other than user or assistant (`platoon@efe3b277c82c:platoon/gateway/dialects/anthropic.py:169`), and Claude Code sends `role: "system"` entries. Docs say Claude Code retries once with the text moved into user messages (`llm-gateway-protocol`). **Resolved by the critic's probe:** real 2.1.316 through the real gateway on a minted key exited 1 with zero recorded calls, with and without `CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS=1`, matching `platoon-platform.md`. The documented fallback does not rescue this path today.
- `x-claude-code-*` headers are read nowhere in `platoon/*.py` (grep: 0 matches). Native-child selectors (`platoon@efe3b277c82c:docs/rfcs/0001-native-multi-agent.md:200`) and call kinds (`platoon@efe3b277c82c:docs/rfcs/0005-gateway-dialects-and-tito.md:107`) are DRAFT/RFC for Claude Code. Platoon RFC 0005 milestone M4 is not done.

## Implications for platoon-harness

1. Ship an extension driver with no Python dependency on `claude-agent-sdk`: find `claude` on `PATH` or by config, refuse a missing binary with an actionable error. This keeps the proprietary binary out of installs; it changes no terms, and the same credential rules apply.
2. Launch argv: `-p --input-format stream-json --output-format stream-json --verbose --include-partial-messages --forward-subagent-text --permission-prompt-tool stdio --mcp-config <ours> --allowedTools mcp__platoon__* --session-id <uuid>`. Set `--permission-mode` explicitly, with `--permission-prompts none` for headless. If `stdio` ever changes, `--permission-prompt-tool mcp__platoon__approve` is the documented form. Declare our server with `"alwaysLoad": true`, so coordination tools are in the first request (section 3).
3. Handshake with `initialize`, then record `capabilities` and `claude_code_version` in the manifest. Floors: 2.1.259 for `--permission-prompts`, 2.1.273 hint headers, 2.1.283 prompt id. Test against a pinned version; warn, do not refuse, on newer.
4. Strip `account` and `rate_limit_info` at the driver boundary, before the journal.
5. Send a `uuid` on every user message and treat `command_lifecycle` when present as delivery evidence. "Started" is observed exposure only at the injection level, not understanding.
6. Attach coordination by `--append-system-prompt-file` and MCP. Never edit the user's CLAUDE.md, settings or hooks. Everyday profile omits `--setting-sources`; worker profile uses empty sources plus strict MCP.
7. Do not depend on the implicit default of `-p`: if `--bare` becomes default, native login stops working silently. Detect it in `doctor` and in a smoke test.
8. Auth profiles: `native` (no auth env at all), `api_key`, `gateway` (bearer token we mint plus isolated `CLAUDE_CONFIG_DIR`). Validate that `gateway` always has both base URL and credential, then fail closed. Gateway env: `CLAUDE_CODE_GATEWAY_HINT_HEADERS=1`, `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1`, `CLAUDE_CODE_ATTRIBUTION_HEADER=0`.
9. Provenance: model-call events from `message.id` deduped, `tool_use_id` anchors, `compact_boundary` as a compaction event with coverage gap; transcripts stay out of the core path because the format is internal.
10. Budgets from `model_usage_since_last_result` when present, else diff `modelUsage`. Label as estimated. On a subscription show tokens, not dollars.
11. Worker env: `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1` so a turn means a turn, and `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=0`. Leave native behavior for everyday single-agent use.
12. Treat repo-supplied hooks and `.mcp.json` as code execution: warn on first run in an untrusted worktree.
13. Termination: `interrupt`, then close stdin, then SIGTERM to the process group. Expect stdio MCP children.
14. Upstream asks for Platoon: accept `role: "system"` entries in the Messages dialect, and read `x-claude-code-*` into call kinds. Both are small Platoon RFC 0005 M4 items.

## Taste notes

- Elegant: one stdio pipe carries events and bidirectional control, correlated by `request_id`. No sockets, no second channel.
- Elegant: `capabilities` strings let a client feature-detect instead of comparing versions, and consumers must ignore unknown values. Copy this for our driver protocol.
- Elegant: `interrupt` returns a receipt describing what was still queued. Cancellation becomes data rather than a guess. Apply this to our delivery semantics.
- Elegant: stable ids run through stream, hooks, headers and files, so joins never need timing. Our journal should hold the same discipline.
- Avoid: fields whose scope differs silently. `usage` (turn, main loop), `modelUsage` (cumulative tree) and a placeholder `output_tokens` sit side by side. Name scope in our field names.
- Avoid: lifecycle events that overload a type. A compaction surfacing as `SubagentStop` shows the cost of reusing an agent abstraction for internal work.

## Unknowns and risks

- `--bare` becoming the `-p` default is announced without a version. Effect on native login and on explicit flags is unknown, and no opt-out is documented.
- Whether `ordinary, individual usage` covers concurrent native-login agents is undefined. Enforcement "without prior notice" could hit the user's account.
- Terms question for training through the Claude Code binary against a non-Claude policy is open: its system prompt and tool descriptions would enter policy context and datasets. Owner must decide before any trainable claim.
- `--permission-prompt-tool stdio`, `command_lifecycle`, `model_usage_since_last_result`, `subagent_stats` and `tool_result_meta` are undocumented; any release may change them. The CLI ships very often: changelog top is 2.1.316, and the fixture will age.
- Not probed: SDK-type MCP, `mcp_message`, auto compaction, nested subagents, parallel tool batches, `--max-turns` limit exit, `priority: now`, crash recovery, macOS, the ACP adapter's behavior.
- Loopback results come from a scripted server with known model id `claude-haiku-5-5`. An unknown gateway model id changes context window and capability assumptions (`llm-gateway-protocol`), not exercised here.
- `OTEL_LOG_RAW_API_BODIES` and `api-request` transcript entries may offer request bodies under native auth. Not evaluated; transcripts are internal and OTEL raw bodies are sensitive. Do not claim exactness from them.
- The `role: "system"` failure through Platoon has since been executed (section 10). The fix belongs upstream.
- The live probe left one session transcript in the user's own Claude config directory, subject to the normal 30-day cleanup.
- Clean-room: no `platoon-harness` implementation was searched for, surfaced or opened.
