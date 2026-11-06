# OpenHands adapter research

## Inspected

| Project | Commit or version | Date | License |
|---|---|---|---|
| software-agent-sdk (monorepo) | `988494576218` (HEAD, ahead of the 1.59.0 wheel; pyproject still says 1.59.0) | 2026-11-01 | MIT, root `LICENSE`; `clients/typescript/LICENSE` also MIT |
| openhands-sdk, -tools, -agent-server, -workspace (PyPI) | 1.59.0 (live probes ran on these wheels) | uploaded 2026-10-28 | MIT by repo; the wheels carry no license metadata or license file |
| OpenHands-CLI | `283c6ac3610f`; PyPI `openhands` 1.16.0, uploaded 2026-05-08 | 2026-10-22 | MIT |
| Platoon | `efe3b277c82c` (version 0.5.0) | 2026-10-28 | MIT AND Apache-2.0 (tool-call parsers) |
| litellm (pinned by the SDK) | 1.105.7 | installed 2026-11-02 | MIT; its `enterprise/` directory is not in the wheel |
| agent-client-protocol (Python) | 0.12.1 (SDK) and 0.8.x (CLI) | installed 2026-11-02 | Apache-2.0 (`acp-python-sdk@9853d8b514d6:LICENSE:1`) |
| lmnr-claude-code-proxy (transitive) | 0.2.0 | installed 2026-11-02 | **Proprietary**, see below |
| docs.openhands.dev | `/sdk`, `/openhands/usage/run-openhands/acp` | retrieved 2026-11-02 | n/a |

Labels used: IMPLEMENTED, DOCUMENTED-ONLY, DRAFT/RFC, EXPERIMENTAL. "Probe" means observed in a live run on 2026-11-02 against a scripted fake OpenAI-compatible server. A bare `:N` after a citation repeats its file. Code citations point to the clone. The clone is a few days past the 1.59.0 wheel (for example `llm/decision.py` is not in the wheel), so re-check a citation against the pinned wheel before relying on an unprobed detail.

## Summary

- Use the **SDK path** (`LocalConversation` driven through `arun()`) as the primary, trainable integration. It gives per-event callbacks, `llm_response_id` on every action, `Condensation` events with exact forgotten ids, a per-call `TokenUsage` list, MCP per agent, and scoped credentials per LLM.
- `openhands acp` is real and worked in a probe, but it is a weak path: published CLI 1.16.0 pins SDK 1.28.1, has no token streaming, no usage updates and no `session/resume`, and it echoes any protocol version.
- A real OpenHands agent ran deterministically with no credentials against a fake server, using only `openhands-sdk`. The fixture is `docs/research/fixtures/openhands-events-sample.json`.

## 1. Packages and entry points

| Distribution | Import | Entry point | Notes (all IMPLEMENTED) |
|---|---|---|---|
| `openhands-sdk` 1.59.0 | `openhands.sdk` | none | Python >=3.12. Hard deps include litellm `>=1.104.3,<1.106`, fastmcp `>=3.2,<4`, `agent-client-protocol>=0.12.1,<0.13`, `lmnr`, fakeredis (`software-agent-sdk@988494576218:openhands-sdk/pyproject.toml:7`) |
| `openhands-tools` 1.59.0 | `openhands.tools` | none | Adds libtmux, browser-use, tom-swe (`software-agent-sdk@988494576218:openhands-tools/pyproject.toml:7`) |
| `openhands-agent-server` 1.59.0 | `openhands.agent_server` | `agent-server` | FastAPI, uvicorn, sqlalchemy, alembic, docker (`software-agent-sdk@988494576218:openhands-agent-server/pyproject.toml:7`) |
| `openhands-workspace` 1.59.0 | `openhands.workspace` | none | Docker and container workspaces; depends on the server (`software-agent-sdk@988494576218:openhands-workspace/pyproject.toml:7`) |
| `openhands` 1.16.0 (the CLI) | `openhands_cli` | `openhands`, `openhands-acp` (broken) | `requires-python ==3.12.*`, pins `openhands-sdk==1.28.1` (`OpenHands-CLI@283c6ac3610f:pyproject.toml:12`, `:25`, `:41`) |

- The CLI distribution is named `openhands`, not `openhands-cli`. `openhands-ai` 1.11.0 is a separate package.
- **The CLI lags the SDK by 31 minor versions.** A CLI adapter and an SDK adapter would run different engines. Probes confirm the CLI installs SDK 1.28.1 event and tool behaviour, not 1.59.0.
- `openhands-acp` fails at runtime with `ModuleNotFoundError: No module named 'openhands_cli.acp'` (probe). The target module does not exist. Use `openhands acp`.
- Licenses: no non-MIT directory exists in either OpenHands clone. A search of LICENSE, toml and md files for GPL, Polyform, proprietary and commercial terms found nothing.
- **Redistribution flag:** `openhands-sdk` requires `lmnr`, which has a hard requirement on `lmnr-claude-code-proxy` (a binary `.so`, `LicenseRef-Proprietary`, "All rights reserved", subject to Laminar's terms). The SDK never imports it (grep finds no use), but it is installed, and Platoon's lockfile includes it too (`platoon@efe3b277c82c:platoon/harness/builtin/specs/openhands-1.54.0.txt`). Keep OpenHands in an optional extra and name this in the release license check.

| Measure (this machine, shared network filesystem) | Value |
|---|---|
| `openhands-sdk` venv | 387 MB, 138 distributions (litellm alone 135 MB) |
| + `openhands-tools` | 562 MB, 185 distributions |
| `openhands-agent-server` venv | 460 MB, 194 distributions |
| `openhands` CLI venv | 501 MB |
| `import openhands.sdk` | 8.2 to 9.9 s wall, 210 MB RSS, 3,946 modules (litellm is loaded eagerly) |
| `import openhands.sdk` + `openhands.tools.terminal` | 11.2 s |

Import times are from a shared login node on network storage and should be treated as an upper bound. The weight is still real: never import this from the core SDK, and run it in a subprocess worker rather than the runtime process. `litellm` is capped below 1.106, so the SDK resolves poorly alongside anything needing `mcp>=2`.

## 2. Agent, Conversation and Event APIs (IMPLEMENTED unless noted)

**Creating.** `Conversation(agent=..., workspace=..., ...)` is a factory returning `LocalConversation`, or `RemoteConversation` for a `RemoteWorkspace` (`software-agent-sdk@988494576218:openhands-sdk/openhands/sdk/conversation/conversation.py:34`, `:161`). `Agent` fields: `llm, tools, mcp_config, filter_tools_regex, include_default_tools, agent_context, system_prompt, condenser, critic, tool_concurrency_limit, persona` (`software-agent-sdk@988494576218:openhands-sdk/openhands/sdk/agent/base.py:115`). `finish` and `think` are added by default (probe).

**Run versus step.** `send_message(msg, sender=None)` appends only. `run()` is blocking; `arun()` is async with non-blocking LLM I/O (`software-agent-sdk@988494576218:openhands-sdk/openhands/sdk/conversation/impl/local_conversation.py:1887`, `:1982`, `:2181`). There is no public single-step API on the conversation; `agent.step()` is internal. `run()` returns on `FINISHED`, `PAUSED`, `STUCK`, `WAITING_FOR_CONFIRMATION`, the iteration limit, or the budget limit. Hitting the limit does not raise locally; LLM errors raise `ConversationRunError` (`software-agent-sdk@988494576218:openhands-sdk/openhands/sdk/conversation/base.py:256`).

**Status enum.** `idle, running, paused, waiting_for_confirmation, finished, error, stuck, deleting` (`software-agent-sdk@988494576218:openhands-sdk/openhands/sdk/conversation/state.py:48`).

**Callbacks.** `callbacks=[fn(Event)]` run synchronously on the run thread, under the state lock. `token_callbacks=[fn(ModelResponseStream)]` receive raw litellm chunks. `stream_callbacks` exists on `LocalConversation` only, not on the factory (`software-agent-sdk@988494576218:openhands-sdk/openhands/sdk/conversation/impl/local_conversation.py:263`). `set_token_callbacks()` works after construction.

**Event envelope.** `id` (random uuid4), `timestamp` (naive local ISO), `source` (`agent|user|environment|hook`), `parent_id` (conversation tree), `kind`. Events are frozen with `extra="forbid"` (`software-agent-sdk@988494576218:openhands-sdk/openhands/sdk/event/base.py:21`).

| Event | Key fields | Citation (`software-agent-sdk@988494576218:openhands-sdk/openhands/sdk/event/...`) |
|---|---|---|
| `SystemPromptEvent` | system prompt, tools, dynamic context | `llm_convertible/system.py:12` |
| `MessageEvent` | `llm_message`, `llm_response_id`, `sender`, `activated_skills`, `extended_content` | `llm_convertible/message.py:25` |
| `ActionEvent` | `thought`, `reasoning_content`, `thinking_blocks`, `action`, `tool_name`, `tool_call_id`, `tool_call`, `llm_response_id`, `security_risk`, `summary` | `llm_convertible/action.py:39` |
| `ObservationEvent` | `observation`, `action_id`, `tool_call_id`, `extended_content` | `llm_convertible/observation.py:32` |
| `UserRejectObservation` | `rejection_reason`, `rejection_source` (`user` or `hook`) | `llm_convertible/observation.py:86` |
| `AgentErrorEvent` | tool error fed back to the LLM | `llm_convertible/observation.py:146` |
| `Condensation`, `CondensationRequest`, `CondensationSummaryEvent` | `forgotten_event_ids`, `summary`, `summary_offset`, `llm_response_id` | `condenser.py:11`, `:99`, `:120` |
| `PauseEvent`, `InterruptEvent` | user control | `user_action.py:7`, `:24` |
| `ConversationErrorEvent` | `code`, `detail` | `conversation_error.py:11` |
| `HookExecutionEvent`, `SecurityAnalysisEvent`, `ACPToolCallEvent` | audit and ACP passthrough | `hook_execution.py:22`, `security.py:11`, `acp_tool_call.py:46` |
| `ConversationStateUpdateEvent` | seen only through the agent server (durable there) | `conversation_state.py:18` |
| `TokenEvent` | `prompt_token_ids`, `response_token_ids` | `token.py:7`; only with `litellm_extra_body={"return_token_ids": True}` against vLLM (`agent/agent.py:1610`) |
| `StreamingDeltaEvent`, `LLMCompletionLogEvent` | server-side transient delta and log | `streaming_delta.py:5`, `llm_completion_log.py:9` |

**Streaming tokens.** Needs both `LLM(stream=True)` and a token callback. Probe: `stream=True` without a callback sends a non-streaming request. No delta event reaches `callbacks`; local deltas go only to `token_callbacks`. Sub-agents are forced to `stream=False` (`software-agent-sdk@988494576218:openhands-tools/openhands/tools/task/manager.py:381`).

**send_message during a run** (probe).

| Mode | Blocked for | Behaviour |
|---|---|---|
| `run()` | until the step ends (lock held across `agent.step`, `software-agent-sdk@988494576218:openhands-sdk/openhands/sdk/conversation/impl/local_conversation.py:2083`) | Message lands after the step, then the run continues. Not lost. |
| `arun()` | 0.05 s (lock released for the LLM wait, `software-agent-sdk@988494576218:openhands-sdk/openhands/sdk/agent/agent.py:1034`) | The in-flight call does not see it. The run continues even after `finish` (`software-agent-sdk@988494576218:openhands-sdk/openhands/sdk/conversation/impl/local_conversation.py:2416`). |

**Surprise for provenance.** Under `arun()` the event log order is `Message(first), Message(mid-run), Action, Observation`, and the next request merges both user messages into one message *before* the assistant turn. So the log says the second message preceded an action that was sampled without seeing it. The observed exposure boundary is the *next* LLM request, not the log position.

**Pause and interrupt** (probe).

| Call | Under | Result |
|---|---|---|
| `pause()` | `run()` | Blocks on the state lock until the step ends; `PauseEvent`, status `paused`; `run()` resumes |
| `interrupt()` | `arun()` | Cancels a scripted 8 s LLM call within 0.05 s; `InterruptEvent`, status `paused`, `arun()` returns without raising; next `arun()` re-sends the call |
| `interrupt()` | `run()` | Falls back to pause, but the cancel token is set, so a pending tool yields a synthetic `AgentErrorEvent` then `PauseEvent` (`software-agent-sdk@988494576218:openhands-sdk/openhands/sdk/conversation/impl/local_conversation.py:2832`) |

**Confirmation.** Policies: `NeverConfirm` (default), `AlwaysConfirm`, `ConfirmRisky(threshold, confirm_unknown)` (`software-agent-sdk@988494576218:openhands-sdk/openhands/sdk/security/confirmation_policy.py:27`). Approval is implicit: call `run()` again. Rejection: `reject_pending_actions(reason)` emits `UserRejectObservation` and moves to `idle` (`software-agent-sdk@988494576218:openhands-sdk/openhands/sdk/conversation/impl/local_conversation.py:2737`). There is no pending-approval event; detect `WAITING_FOR_CONFIRMATION` plus unmatched `ActionEvent`s.
- A lone `finish` or `think` never needs confirmation, even under `AlwaysConfirm` (`software-agent-sdk@988494576218:openhands-sdk/openhands/sdk/agent/agent.py:1200`).
- Without a security analyzer, risk is `UNKNOWN`: the model's `security_risk` argument was `LOW` on the wire but `ActionEvent.security_risk` was `UNKNOWN` (probe).
- Under `arun()`, a new message while waiting rejects the pending action as "Superseded by a new user message" (`software-agent-sdk@988494576218:openhands-sdk/openhands/sdk/conversation/impl/local_conversation.py:2402`).

**Persistence and resume.** `persistence_dir=X` writes `X/<conv hex>/base_state.json` and `events/event-NNNNN-<id>.json`; without it, an in-memory store is used (`software-agent-sdk@988494576218:openhands-sdk/openhands/sdk/conversation/state.py:539`). Resume by constructing a `Conversation` with the same `conversation_id` and a fresh `Agent` (probe: 6 events before, 9 after). The agent is checked by `verify()`: same class, and tools may be added but not removed (`software-agent-sdk@988494576218:openhands-sdk/openhands/sdk/agent/base.py:686`). `fork()` and `navigate_to()` give branching (`software-agent-sdk@988494576218:openhands-sdk/openhands/sdk/conversation/impl/local_conversation.py:840`, `:988`). Without a `Cipher`, secrets are redacted in persisted state, so the caller must supply the LLM key again on resume (`software-agent-sdk@988494576218:openhands-sdk/openhands/sdk/conversation/impl/local_conversation.py:307`). Observations also persist `username` and `hostname` metadata (probe), so treat event files as sensitive.

**Stats.** `conversation.conversation_stats.usage_to_metrics[usage_id]` holds `accumulated_cost`, `accumulated_token_usage`, and per-call `token_usages[]` and `response_latencies[]`, each with `response_id` (`software-agent-sdk@988494576218:openhands-sdk/openhands/sdk/llm/utils/metrics.py:34`). `ActionEvent.llm_response_id` joins an action to its call's usage (probe). Limits:
- An unmapped model gives `accumulated_cost: 0.0` with `costs: []`; zero does not mean free. `input_cost_per_token` and `output_cost_per_token` fix this (probe).
- `reasoning_tokens: 6` appeared in the stream run although the fake sent none; it is a litellm estimate. Do not treat it as measured.
- `max_budget_per_run` is a local cost cap only.

**Condenser.** `Agent(condenser=LLMSummarizingCondenser(llm=..., max_size=240, max_tokens=None, keep_first=2))` (`software-agent-sdk@988494576218:openhands-sdk/openhands/sdk/context/condenser/llm_summarizing_condenser.py:64`). `Agent()` has none by default; `get_default_agent` adds one. `conversation.condense()` forces it. Events are `CondensationRequest` then `Condensation` (probe). The log keeps everything; only the view shrinks (13 logged, 7 in view). The summary call uses the condenser LLM's own headers and is tracked under its own `usage_id`: stats showed `agent` and `condenser` separately (probe).

**Hooks.** `PreToolUse, PostToolUse, UserPromptSubmit, SessionStart, SessionEnd, Stop`, as `command`, `prompt` or `agent` hooks (`software-agent-sdk@988494576218:openhands-sdk/openhands/sdk/hooks/types.py:9`, `software-agent-sdk@988494576218:openhands-sdk/openhands/sdk/hooks/config.py:40`). Pass `hook_config=` per conversation. `.openhands/hooks.json` is loaded by the CLI, not automatically by `Conversation` (`OpenHands-CLI@283c6ac3610f:openhands_cli/acp_impl/agent/local_agent.py:181`). A `Stop` hook can deny finishing and inject feedback (`software-agent-sdk@988494576218:openhands-sdk/openhands/sdk/conversation/impl/local_conversation.py:2041`). Decisions are allow and deny; `ask` is a comment for later (`software-agent-sdk@988494576218:openhands-sdk/openhands/sdk/hooks/types.py:40`).

**Skills and AGENTS.md.**
- `Agent()` alone ignores `AGENTS.md` (probe: not in the prompt with `agent_context=None` or a default `AgentContext`).
- `AgentContext(load_project_skills=True)` puts it in the system message (probe). `load_user_skills` and `load_public_skills` also default to False in the SDK (`software-agent-sdk@988494576218:openhands-sdk/openhands/sdk/context/agent_context.py:93`).
- Recognised files: `.cursorrules, AGENTS.md, AGENT.md, CLAUDE.md, GEMINI.md` (`software-agent-sdk@988494576218:openhands-sdk/openhands/sdk/skills/skill.py:347`). Skill directories: `.agents/skills`, `~/.openhands/skills`.
- The CLI enables all three, and public skills fetch from GitHub (`OpenHands-CLI@283c6ac3610f:openhands_cli/stores/agent_store.py:408`).

**Extras worth knowing.** `ask_agent(question)` is a stateless side query that records no events but does make an LLM call. `execute_tool()` runs a tool outside the loop. `conversation/goal/` drives a goal loop with a judge LLM. The stuck detector moves the run to `stuck` after repeats (probe: four identical `think` calls).

## 3. MCP per conversation (IMPLEMENTED, probe)

- Put it on the agent: `Agent(mcp_config={"board": {"command": ..., "args": [...]}})`. Remote: `{"url": ..., "transport": "http"|"sse", "headers": {...}, "auth": ...}` (`software-agent-sdk@988494576218:openhands-sdk/openhands/sdk/mcp/config.py:497`). Each `Agent` has its own config, so per-agent MCP identity tokens in headers work. `headers` are `SecretStr`.
- Tools resolve lazily on first run. Tool names are **not** prefixed (probe: tool `post` stayed `post`). `filter_tools_regex` restricts them.
- `security_risk` and `summary` are injected into MCP schemas and stripped before the call (probe: server received only `{"text": "hi"}`).
- Results appear as `ActionEvent(action.kind="MCPToolAction")` and `ObservationEvent(kind="MCPToolObservation")`.
- **Failure is silent.** A bad server logs a warning and the run proceeds without its tools, ending `finished` (`software-agent-sdk@988494576218:openhands-sdk/openhands/sdk/conversation/impl/local_conversation.py:1451`, probe). The adapter must assert its coordination tools appear in `SystemPromptEvent.tools`, or fail the spawn.
- Sub-agents inherit the parent's MCP servers exactly (`software-agent-sdk@988494576218:openhands-sdk/openhands/sdk/subagent/scope.py:41`), so a parent-identity MCP token is shared with children.
- `MCPToolProvider` is an injectable protocol for custom clients (`software-agent-sdk@988494576218:openhands-sdk/openhands/sdk/mcp/utils.py:45`).
- `client_tools` only acknowledge: the executor returns at once and a consumer handles the `ActionEvent`, so the model never sees a real result (`software-agent-sdk@988494576218:openhands-sdk/openhands/sdk/tool/client_tool.py:1`). Do not use them for coordination primitives. Use MCP, or `register_tool` for in-process Python tools.

## 4. Delegation (IMPLEMENTED, off by default)

| Tool | Status | Behaviour |
|---|---|---|
| `TaskToolSet`, tool name `task` | Current default in the CLI; opt-in via `get_default_tools(enable_sub_agents=True)` | Blocking; `subagent_type`, `resume` (`software-agent-sdk@988494576218:openhands-tools/openhands/tools/task/definition.py:48`, `software-agent-sdk@988494576218:openhands-tools/openhands/tools/preset/default.py:64`) |
| `DelegateTool` | Legacy, kept for old conversations (`OpenHands-CLI@283c6ac3610f:openhands_cli/utils.py:176`) | Named children, parallel (`software-agent-sdk@988494576218:openhands-tools/openhands/tools/delegate/impl.py:34`) |
| `start_child_conversation` | Agent server | `POST /conversations/{id}/children`, linked by `parent_conversation_id` (`software-agent-sdk@988494576218:openhands-agent-server/openhands/agent_server/conversation_router.py:843`) |

Agents come from `register_agent()` or `.agents/agents/*.md` and `.openhands/agents/*.md` (`software-agent-sdk@988494576218:openhands-sdk/openhands/sdk/subagent/AGENTS.md:33`). **The registry is a process-global dict, first registration wins** (`software-agent-sdk@988494576218:openhands-sdk/openhands/sdk/subagent/registry.py:57`), which is another reason for one process per agent.

**Child identity, from a real `task` run (probe).**
- The child is a separate `LocalConversation` with its own UUID. It is built with **no callbacks** (`software-agent-sdk@988494576218:openhands-tools/openhands/tools/task/manager.py:327`).
- The parent callback sees only `ActionEvent(task)` and `ObservationEvent(TaskObservation{task_id, subagent, status})`. **Zero child events reach it.** The observation does not name the child conversation id.
- On the wire, each child call has `x-litellm-session-id: <child id>`, `prompt_cache_key: <parent id>`, and the parent's `extra_headers` and key.
- Child events persist under `<parent>/subagents/<child hex>/` when the parent persists, and survived `close()` in the probe.
- Parent stats gain `task:task_00000001` with the child's combined metrics (`software-agent-sdk@988494576218:openhands-tools/openhands/tools/task/manager.py:500`). Do not add this to child-recorded usage: it double-counts.
- `MessageEvent.sender` for the child comes from the parent's visualizer name, so with `visualizer=None` it is None (`software-agent-sdk@988494576218:openhands-tools/openhands/tools/task/manager.py:415`).

**Exact child credentials work.** The agent factory receives the LLM and may replace it. A factory setting `api_key` and `extra_headers` on `llm.model_copy(...)` produced `Bearer child-key` on child calls and `Bearer parent-key` on parent calls (probe). Pairing this with Platoon's `POST /v1/platoon/agents` mint (`platoon@efe3b277c82c:platoon/gateway/server.py:22`, `:238`) gives exact attribution. Platoon's RFC 0001 proposes this as an option and classifies the header route as "inferred" (`platoon@efe3b277c82c:docs/rfcs/0001-native-multi-agent.md:201`); that RFC is Draft, and Platoon's gateway does not read `x-litellm-session-id` today (grep of `platoon/gateway/`).

## 5. LLM config

- **OpenAI-compatible endpoint** (probe): `LLM(model="openai/<name>", base_url="http://host/v1", api_key="k", usage_id="agent", num_retries=0, timeout=...)`. The `openai/` prefix selects litellm's OpenAI provider, and the wire model becomes `<name>`.
- `extra_headers` are per LLM and reach the wire (probe; `software-agent-sdk@988494576218:openhands-sdk/openhands/sdk/llm/options/common.py:26`). The condenser can have a different header: `llm.model_copy(update={"usage_id": "condenser", "extra_headers": {...}})` (probe).
- `litellm_extra_body` passes through to `extra_body` (`software-agent-sdk@988494576218:openhands-sdk/openhands/sdk/llm/options/common.py:55`).
- `api_mode` (`auto|chat|responses`) picks the endpoint; set `chat` for gateway aliases so auto-detection cannot pick Responses (`software-agent-sdk@988494576218:openhands-sdk/openhands/sdk/llm/llm.py:467`). `capability_overrides`, `model_canonical_name`, `native_tool_calling`, `max_input_tokens` and `max_output_tokens` handle unknown models.
- Headers and fields the SDK adds on its own (probe): `x-litellm-session-id: <conversation id>`, `prompt_cache_key: <conversation id>`, `reasoning_effort: "high"`, `x-title: OpenHands`, `http-referer`, and `stream_options.include_usage` when streaming. `drop_params` defaults to true. A gateway must accept or ignore these.
- `num_retries` defaults to 5. A retry resends the call and can record it twice, so set 0 or 1 for training (`platoon@efe3b277c82c:platoon/harness/builtin/openhands/run_openhands.py:13`).
- `native_tool_calling=False` mocks tools in text; keep it true for token-exact training.
- Set `LITELLM_LOCAL_MODEL_COST_MAP=True` and `OPENHANDS_SUPPRESS_BANNER=1` for offline, quiet runs.
- Observability is off unless `LMNR_PROJECT_API_KEY` or OTEL env vars are set (`software-agent-sdk@988494576218:openhands-sdk/openhands/sdk/observability/laminar.py:28`). Scrub those from worker envs unless wanted.

**Auth options.**

| Method | How | Notes |
|---|---|---|
| API key | `api_key`, SecretStr | Passed in-process; no env mutation by the SDK (`software-agent-sdk@988494576218:openhands-sdk/openhands/sdk/llm/llm.py:778`) |
| Provider-specific | AWS fields, `provider_connection_id` | `software-agent-sdk@988494576218:openhands-sdk/openhands/sdk/llm/llm.py:294`, `:332` |
| ChatGPT subscription | `LLM.subscription_login(vendor="openai", model=...)`, browser or device flow | Only `openai` is supported (`software-agent-sdk@988494576218:openhands-sdk/openhands/sdk/llm/llm.py:312`, `:3438`). Needs an interactive consent the first time and raises in non-interactive mode (`software-agent-sdk@988494576218:openhands-sdk/openhands/sdk/llm/auth/openai.py:79`). Calls the fixed Codex backend (`software-agent-sdk@988494576218:openhands-sdk/openhands/sdk/llm/auth/openai.py:125`), so it does not go through a gateway. Operational, not Trainable |
| OpenHands Cloud | `openhands login`, device flow | CLI only |
| Other harness via `ACPAgent` | Native auth of Claude Code, Codex, Gemini CLI | See section 6; opaque to OpenHands' LLM layer |

## 6. ACP and the agent server

**`openhands acp`: IMPLEMENTED, ACP agent (server side) over stdio JSON-RPC** (`OpenHands-CLI@283c6ac3610f:openhands_cli/acp_impl/agent/launcher.py:16`). Probe against real CLI 1.16.0:

| Item | Result |
|---|---|
| `initialize` | Works, but echoes the client version: `protocolVersion: 99` returned 99 (`OpenHands-CLI@283c6ac3610f:openhands_cli/acp_impl/agent/base_agent.py:245`). The library's `PROTOCOL_VERSION` is 1. Pin 1 yourself and never trust the echo as negotiation |
| Capabilities | `loadSession: true`, `mcpCapabilities {http, sse}`, prompt `image` and `embeddedContext`, no audio |
| `session/new` | Needs saved `~/.openhands/agent_settings.json`; otherwise "Authentication required" (-32000). `--override-with-envs` is accepted but not forwarded in ACP mode, so it had no effect (`OpenHands-CLI@283c6ac3610f:openhands_cli/entrypoint.py:132`) |
| `session/prompt` | Ran a real terminal call; updates: `available_commands_update`, `agent_thought_chunk`, `tool_call`, `tool_call_update`, `agent_message_chunk`; `stopReason: end_turn` |
| Streaming | **None.** Docs list `--streaming`, but the flag is absent from `openhands acp --help` and the entrypoint does not pass it. Requests were non-streaming, and chunks are whole messages. DOCUMENTED-ONLY for 1.16.0 |
| Noise | The whole system prompt arrives as an `agent_thought_chunk` |
| Usage | No `usage_update` frames |
| `session/list` | Not found over the wire (handler returns empty in code) |
| `session/resume`, `session/fork` | Method not found (`OpenHands-CLI@283c6ac3610f:openhands_cli/acp_impl/agent/base_agent.py:351`) |
| `session/set_model`, config options | No-ops, `set_mode` works (`OpenHands-CLI@283c6ac3610f:openhands_cli/acp_impl/agent/base_agent.py:331`) |
| `session/cancel` | Maps to `pause()`, so it cannot stop an in-flight LLM call (`OpenHands-CLI@283c6ac3610f:openhands_cli/acp_impl/agent/base_agent.py:405`) |
| MCP | From `session/new` `mcpServers` (stdio, http, sse) |
| Docs mismatch | Docs say settings live in `settings.json`; code uses `agent_settings.json` (`OpenHands-CLI@283c6ac3610f:openhands_cli/locations.py:51`) |

Process hygiene: SIGTERM to `openhands acp` orphaned its tmux server under a shared `-Lopenhands` socket (probe; it had to be killed by hand). Kill the process group and use a private `TMUX_TMPDIR`.

**`ACPAgent` (SDK as ACP client): IMPLEMENTED.** The reverse direction: an OpenHands `Conversation` drives Claude Code, Codex, Gemini CLI or Kimi over ACP (`software-agent-sdk@988494576218:openhands-sdk/openhands/sdk/agent/acp_agent.py:1766`, `:3177`; catalog `software-agent-sdk@988494576218:openhands-sdk/openhands/sdk/settings/acp_install_catalog.py:119`). Useful as reference, not for us: it would hide those harnesses behind OpenHands events.

**Agent server: IMPLEMENTED** (probe, 1.59.0). `python -m openhands.agent_server --host H --port P`, with `/openapi.json` listing 148 paths and `X-Session-API-Key` auth (no key gave 401). The README default host is `0.0.0.0`, so bind loopback.

| Route | Purpose |
|---|---|
| `POST /api/conversations`, `GET /{id}`, `/search`, `/count`, `DELETE` | Lifecycle |
| `POST /api/conversations/{id}/events`, `/events/respond_to_confirmation`, `GET /events/search` | Messages, approvals, paged history (`software-agent-sdk@988494576218:openhands-agent-server/openhands/agent_server/event_router.py:213`, `:231`) |
| `POST /{id}/run`, `/pause`, `/interrupt`, `/fork`, `/navigate`, `/condense`, `/ask_agent`, `/confirmation_policy`, `/switch_llm`, `/children`, `/goal` | Control (`software-agent-sdk@988494576218:openhands-agent-server/openhands/agent_server/conversation_router.py:366`) |
| `WS /sockets/events/{id}` | Legacy: compares naive timestamps for replay (`software-agent-sdk@988494576218:openhands-agent-server/openhands/agent_server/sockets.py:228`) |
| `WS /sockets/session/{id}?after_seq=N` | Newer: envelopes with resumable `seq`, deltas, bounded per-connection backpressure; marked PROVISIONAL for frame caps (`software-agent-sdk@988494576218:openhands-agent-server/openhands/agent_server/session_socket.py:315`, `software-agent-sdk@988494576218:openhands-agent-server/openhands/agent_server/session_protocol.py:31`) |

Probe frames: `sync`, `durable` with `seq`, `transient`, `item_started`, `delta` (`kind: text|reasoning`, with `chunk_id` equal to the LLM response id). `ConversationStateUpdateEvent` entries for `execution_status` and `stats` are durable here.

**Surprise:** `autotitle` defaults to true (`software-agent-sdk@988494576218:openhands-sdk/openhands/sdk/conversation/request.py:406`), and the server spent one scripted response on a title call to the agent's LLM endpoint outside the agent loop (`software-agent-sdk@988494576218:openhands-agent-server/openhands/agent_server/conversation_service.py:2516`, probe: 3 requests for a 2-step run). Set `autotitle=false` on any gateway-backed conversation.

## 7. Live probe (credential-free CI)

Setup: a stdlib `ThreadingHTTPServer` serving `POST /v1/chat/completions`, both JSON and SSE, with scripted content, reasoning and tool calls.

Result, SDK and tools 1.59.0: a real `Conversation`, a real tmux terminal, one `echo` command, `finish`, then resume in a new object.

```text
SystemPromptEvent, MessageEvent(user), ActionEvent(terminal), ObservationEvent,
ActionEvent(finish), ObservationEvent          -> finished, 2 requests
resume: MessageEvent, ActionEvent(finish), ObservationEvent -> finished
```

- The run is deterministic apart from ids and timestamps. `/v1/chat/completions` was the only path called.
- Nothing needed a credential. The SDK alone also runs finish-only and `think` scripts, so basic conformance needs no tools package.
- `Tool(name="terminal", params={"terminal_type": "subprocess"})` runs without tmux (`software-agent-sdk@988494576218:openhands-tools/openhands/tools/terminal/definition.py:292`).
- Other surprises not listed above: `finish` gives `ActionEvent` + `ObservationEvent`, with no `MessageEvent`; text on a tool-call turn lives in `ActionEvent.thought`; a text-only reply gives `MessageEvent(source=agent)`. Malformed tool calls and content-filter blocks are fed back as `MessageEvent(source="user")` (`software-agent-sdk@988494576218:openhands-sdk/openhands/sdk/agent/agent.py:833`, `:846`), so **`source=user` does not prove a human wrote it**. `sender` is free text, not an authenticated identity.

Fixture: `docs/research/fixtures/openhands-events-sample.json` holds stream and non-stream runs, resume, wire requests, a condensation, and control sequences, redacted (ids renumbered, paths, user, host and timestamps replaced).

## 8. Capability matrix row (OpenHands SDK 1.59.0, `LocalConversation`)

| Capability | Status | Evidence | Limitations |
|---|---|---|---|
| Launch | Yes | Probe; `software-agent-sdk@988494576218:openhands-sdk/openhands/sdk/conversation/conversation.py:34` | 8 to 11 s import here; use one process per agent |
| Streaming | Yes | Probe; `stream=True` + token callback | Raw litellm chunks; sub-agents never stream; nothing durable |
| Tool injection | Yes: MCP per `Agent`, or `register_tool` | Probe | Failed MCP start is silent; names unprefixed; inherited by children |
| Messaging | Yes | Probe; `send_message` | Queued to next LLM call; in-flight call does not see it; log order misleads; `sender` unauthenticated |
| Interruption | `arun`: mid-LLM. `run`: step boundary | Probe | Cancelled call may already be recorded by a gateway |
| Approvals | Yes | Probe | No pending event; approve is `run()` again; lone finish and think skip it; risk `UNKNOWN` without analyzer |
| Resume | Yes, same-tool-set | Probe | Requires key resupply unless a `Cipher` is used; tools cannot be removed |
| Native subagents | Yes, `task`, opt-in | Probe | No child events in parent stream; child id only in header and on disk; global registry |
| Model endpoint config | Yes | Probe | Unrequested fields sent; litellm dep |
| Exact call attribution | Per process with scoped key: yes. Action to call: `llm_response_id`. Child: yes only with keyed factory | Probe | No token ids locally except vLLM `TokenEvent`; those come from the Platoon gateway. `ask_agent`, title and condenser calls are extra calls on the same endpoint |
| Training eligibility | **Trainable** with Platoon's gateway, fixed config, no native subagents unless keyed | Platoon's working harness | Depends on private overrides, see below. Subscription or Cloud auth: Operational + Observable only |

`openhands acp` row (CLI 1.16.0): launch yes; streaming no (whole chunks); tool injection via `mcpServers`; messaging at prompt boundaries; interruption step boundary only; approvals yes; resume via `session/load` and `--resume` (no `session/resume`); native subagents with no identity; endpoint via saved settings only; attribution none; training ineligible as shipped.

### Platoon's existing OpenHands harness

- Declared by a TOML spec, not code: `openhands@1.54.0.post1`, dialect `openai_chat`, pinned hashed toolchain (`platoon@efe3b277c82c:platoon/harness/builtin/specs/openhands.toml:16`). The agent runs inside the task sandbox with `{toolchain}/bin/python3 -I run_openhands.py`, with env `LLM_MODEL=openai/{model}`, `LLM_BASE_URL={base_url}/v1`, `LLM_API_KEY={api_key}` (`platoon@efe3b277c82c:platoon/harness/builtin/specs/openhands.toml:77`).
- The runner is headless and single-agent: `Conversation(...)`, `send_message(instruction)`, `run()`, then writes the final message; exit codes 0, 1, 3 (limit), 4 (stuck) (`platoon@efe3b277c82c:platoon/harness/builtin/openhands/run_openhands.py:594`, `:517`). No event streaming, no persistence, no MCP: Platoon's trace comes wholly from the gateway.
- Identity is the agent key; the gateway records each call on that agent (`platoon@efe3b277c82c:platoon/harness/agent.py:93`). The key is popped from the environment so the terminal cannot read it (`platoon@efe3b277c82c:platoon/harness/builtin/openhands/run_openhands.py:483`).
- Tools are terminal, file editor, task tracker, finish, think; no skills, no delegation (`platoon@efe3b277c82c:platoon/harness/builtin/openhands/run_openhands.py:491`).
- **`ReplayLLM`** subclasses `LLM` and overrides private `_model_features` and `_to_chat_dicts` so each turn resends its reasoning, so prompts extend exactly (`platoon@efe3b277c82c:platoon/harness/builtin/openhands/run_openhands.py:115`). Those privates still exist at the clone (`software-agent-sdk@988494576218:openhands-sdk/openhands/sdk/llm/llm.py:2597`, `:3068`), but this is why the version is pinned.
- Condenser calls are marked `X-Platoon-Call-Kind: aux` through a copied LLM (`platoon@efe3b277c82c:platoon/harness/builtin/openhands/run_openhands.py:463`, `platoon@efe3b277c82c:platoon/gateway/server.py:315`).
- Platoon's pin is 1.54.0; we would probe 1.59.0. Any shared adapter must cover both or pin one.

## Implications for platoon-harness

1. **Primary adapter: a worker process per agent, using the SDK directly**, in an optional extra such as `platoon-harness-openhands`. The core never imports OpenHands. The worker speaks our driver protocol over stdio or a socket, drives `arun()`, and forwards events.
2. **Always use `arun()`**, as `run()` makes messaging and pausing wait for the step. Treat `interrupt()` as the cancel primitive.
3. **Declare the injection boundary as the next LLM request.** Record exposure from the actual request, or from the gateway, not log position. Mark `Message` events that arrive during a call as queued.
4. **Do not reuse OpenHands' identity fields.** Map `source=user` plus our own delivery record to a principal; never derive a human actor from `source` or `sender`.
5. **Tool injection:** one MCP server per agent with a scoped token. On startup, read `SystemPromptEvent.tools` and fail the spawn if coordination tools are missing.
6. **Approvals:** synthesize a pending-approval event from `WAITING_FOR_CONFIRMATION` and unmatched actions. Headless runs must use `NeverConfirm` or an explicit reject policy, and never hang.
7. **Native subagents:**
   - Trainable runs: disable `task` by default, and let delegation go through our `spawn`.
   - Everyday runs: allow it; ingest `<parent>/subagents/<hex>/events/` as a labelled observed-after-completion source, identity `inferred` (a child with no credential of its own; [Platoon RFC 0001](https://github.com/ApGa/platoon/blob/efe3b277c82c/docs/rfcs/0001-native-multi-agent.md) rates the header route `inferred`).
   - Advanced trainable path: keyed factory with a minted child credential, identity exact, unique factory name per role.
   - Reconcile stats so `task:*` is not added to child records.
8. **Training profile:** `num_retries` 0 or 1, `api_mode="chat"`, condenser `aux` header, no `ask_agent`, no autotitle, fixed tool set, pinned version. Eligibility must check these in a manifest rather than assume them.
9. **Honest measures:** report cost as unavailable when `costs` is empty, and label reasoning tokens as estimates.
10. **Resume:** store our own run-to-`conversation_id` map, re-supply credentials through the runtime, and keep the same tool list. Do not depend on the persisted key.
11. **Compaction provenance:** convert `Condensation` to a first-class event with its forgotten ids. It is one of the few exact compaction records across harnesses.
12. **Sandboxing and privacy:** `HOME`, `OPENHANDS_PERSISTENCE_DIR`, `TMUX_TMPDIR` per worker; kill the process group on stop; treat event dirs as sensitive; set `load_public_skills` off in CI and offline runs.
13. **Project instructions:** set `AgentContext(load_project_skills=True)` for everyday runs to match user expectations, and record that decision in the resolved config. Training stays off by default.
14. **ACP path:** keep `openhands acp` as a generic-ACP conformance target only, labelled Operational, since it runs a different engine version from the SDK adapter. Do not use the agent server in Milestone 1; its `after_seq` socket is good and a later remote option.
15. **CI:** ship our fake OpenAI server in tests, run SDK-only finish scripts always, and put terminal cases behind the extra with `terminal_type="subprocess"`.
16. **Upstream asks (small, optional):** child conversation id on `TaskObservation`, a pending-confirmation event, `stream_callbacks` on the factory, and a failure mode for MCP startup.

## Unknowns and risks

- Fast upstream: 1.54 to 1.59 in weeks, and the clone is already past 1.59.0. Private `ReplayLLM` overrides can break on any bump.
- CLI and SDK drift: the CLI's next release may jump many SDK versions and change the ACP results above. Re-probe on bump.
- `lmnr-claude-code-proxy` is proprietary and installed by default. Legal status for redistribution in an image is unreviewed; a user installing from PyPI is the likely safe path. Excluding it (for example with a uv override) is untested.
- Not probed: `DelegateTool`, `ACPAgent`, `RemoteConversation`, `Responses` API paths, hooks in a live run, `fork()`, `ConfirmRisky` with an analyzer, MCP over HTTP with headers, subscription login (no interactive login attempted). These rest on code reading.
- Critic probe against the real gateway: SDK 1.59.0 `arun()` on a minted child key with a stdio MCP tool recorded exact tokens and logprobs on the child, and `ActionEvent.llm_response_id` equalled the gateway `call_id`. Platoon's own runner on 1.59.0 also produced datums tagged to that child. `initialize` used `2025-11-25`, `tools/call` `_meta` held only `progressToken`, and an undeclared argument failed client-side validation before reaching the server. Condenser, delegation and long runs through the gateway remain untested.
- `task` under `arun()`: the parent's lock release covers the LLM wait, but tool execution holds locks differently. A long blocking child may delay `send_message` to the parent; this needs a probe before relying on it.
- Memory and start-up cost per agent is unmeasured at scale: 210 MB RSS at import suggests a 100-agent single-host team needs a shared-worker or lighter strategy. Bench before promising.
- Docs were partial: `/sdk` landing page did not name packages or subscription login, and the ACP page disagrees with the CLI on `--streaming`. Code was treated as authoritative.
- No result in this work surfaced any project with the clean-room name; no web search was run on this topic.

## Taste notes

- Elegant: the event log is the state. Frozen, typed, one-file-per-event, with a `parent_id` tree; views and condensation are projections, and nothing is erased.
- Elegant: `Condensation` names exactly what was forgotten. Our compaction records should be that explicit.
- Elegant: `session_protocol.py` states its delivery rules in five lines, and separates durable frames (seq, resumable) from deltas (droppable). Copy the idea, not the code.
- Elegant: the factory takes the LLM and returns an agent, which is what makes keyed children possible without any new API.
- Avoid: the sync and async run loops are near-duplicates of 500 lines that have already diverged (concurrent-message handling differs). Have one loop.
- Avoid: process-global registries and class-name-keyed dynamic types (`register_agent`, tool and action registries). Prefer explicit per-run objects.
- Avoid: silent degradation (`MCP startup failed` as a warning, `0.0` as unknown cost, `--override-with-envs` accepted and ignored). Unsupported states must be loud.
- Avoid: eager imports and a heavy mandatory dependency set in the core package: 8 s and 3,946 modules just to import. Keep ours lazy.
