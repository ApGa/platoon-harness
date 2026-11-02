# Spike: tools and parking with real harnesses

## Question

Does a stdlib, tools-only MCP server work with real Claude Code and Codex? Does a live Codex model see the tool? Is parking (`wait`, then end of turn) reliable enough to be the default, and what is the fallback? What launch settings must the drivers use?

## Method

- **Host:** shared x86-64 Linux login node, 192 logical CPUs, kernel 5.14, Python 3.12.13. No GPU. Runs were sequential.
- **Clients:** Claude Code 2.1.316 (`claude-haiku-5-5`, stream-json, native login). Codex 0.164.0 (`gpt-6-luna`, effort low, `codex app-server` over stdio, ChatGPT login).
- **Server:** 142 lines, stdlib only, `asyncio.start_server`, loopback HTTP, bearer per agent, tools `note`, `read_notes`, `wait`. The count includes a 2-line slow-init test hook. Sample log: [mcp-http-probe.jsonl](../fixtures/mcp-http-probe.jsonl).
- **Budget:** 38 harness turns (Claude 14, Codex 24), against a limit of 40. That is about 89 model requests: 28 Claude messages plus about 61 Codex usage updates. If the limit meant model requests, it was exceeded.
- **Parking task:** create `result.txt`, call `wait`, stop; after a later message, append `approved`.
- **Own client bug:** my first read loop mixed `select` with buffered lines. One Codex wake appeared to take 80 s. I excluded that latency and fixed the loop.
- **Source read:** tag `rust-v0.164.0`, commit `6aaac6948030`, not the `05c08d765523` pin in the research reports. Exposure rules come from that source; every setting named as tested ran live.

## Results

### Server against both clients

| Item | Claude Code | Codex |
|---|---|---|
| Sequence | `server/discover` at `2026-07-28`, -32601, `initialize` at `2025-11-25`, `initialized`, GET 405, `tools/list`, `tools/call` | `initialize` at `2025-06-18`, `initialized`, `tools/list`, `tools/call`. No GET |
| JSON reply accepted, though `Accept` offers SSE | Yes | Yes |
| `MCP-Protocol-Version` header after init | Yes | Yes |
| Tool called, arguments arrived | Yes | Yes |
| `_meta` keys on `tools/call` | `claudecode/toolUseId`, `progressToken` | `callId`, `itemId`, `threadId`, `sessionId`, `windowId`, `progressToken`, `x-codex-turn-metadata` |
| Anchor equals the model's tool id | Yes, 8 of 8 compared | No, 0 of 2: `callId` is `exec-<uuid>`, the model's id is `call_*` |
| Forced spoof `caller="root"` | Reached server, refused | Reached server, refused |
| What the model sees | `is_error` tool result: `refused: undeclared=['caller'] ...` | Script output with `"isError":true`; item status `failed` |

Self-test without a model: no or bad token 401, foreign `Origin` 403, GET and DELETE 405, notification 202, batch -32600, unknown method -32601. An unknown `protocolVersion` was answered with `2025-11-25`.

Two calls from one Codex `exec` script shared one `itemId`. An unforced Codex spoof never reached the server: the model read the schema and declined.

### Why the Codex tool looks missing

All 7 models in the Codex catalog carry `tool_mode: code_mode_only` and `supports_search_tool: true`. The model gets one `exec` JavaScript tool. MCP tools are deferred: they are absent from the prompt and listed only in a runtime `ALL_TOOLS` array that the model must filter itself.

| Setting | Threads | Tool found | Notes |
|---|---|---|---|
| Default, prompt says "note tool" | 5 | 5 | Each needed 1 discovery call |
| Default, parking task | 2 | **1** | The model filtered `/wait.*review\|review.*wait/`, found nothing, and said no such tool exists |
| `omit_tools_from=["deferred"]` | 8 | 8 | Declaration in the `exec` prompt, 0 discovery calls, about 170 more input tokens |

- Features cannot turn this off: `tool_search` is reported as removed, and model metadata overrides the Code Mode features (`codex-rs/core/src/tools/mod.rs:65`).
- The 3-of-4 startup miss was not reproduced. It came from stdio and `codex exec`, which I did not rerun. With a 4 s `initialize` delay over HTTP, `thread/start` took 4.26 s and the tool worked (1 trial; normal start was 0.12-0.17 s).
- Codex has native `functions.wait`, `wait_agent` and `clock.sleep`. None was called in place of ours in the trials.

### Sandbox and token, Codex workspace-write

| Check | Result |
|---|---|
| MCP tool calls under workspace-write | Worked: the host makes the call, not the shell |
| Shell `socket()` to loopback | `PermissionError` errno 1, command exit 1 (1 trial) |
| `bearer_token_env_var` value in the agent shell | **Present**: `env \| grep -c` gave 1 |
| Same, with `shell_environment_policy.exclude` | Absent: 0 (1 trial) |

### Parking

A closing message after `wait` is unavoidable, since the tool result must return to the model. "Clean" means no tool call after `wait`.

| Harness and setting | Trials | Called `wait` | Clean stop | Further tool calls | Further model calls |
|---|---|---|---|---|---|
| Claude, `alwaysLoad` | 5 | 5 | 5 of 5 | 0 | 1 each |
| Codex, `omit_tools_from=["deferred"]` | 5 | 5 | 5 of 5 | 0 | 1 each |
| Codex, default | 2 | 1 | 1 of 1 | 0 | 1 |

- Claude sent `Bash` and `wait` in one model message in 5 of 5 trials, so `wait` runs beside a sibling tool. Codex used separate `exec` calls.
- Codex's closing message was empty in 3 of 6 clean stops. One said `DONE` early.
- The failed default trial never parked, and the wake message still completed the task. Nothing in the run signalled the failure.

### Wake turn, process kept alive

Same session or thread and the task finished in all 5 trials on each harness. Figures are totals for the wake turn, 2 model requests each.

| Harness | Input tokens | Cached | Cached share | Cache write | Output | Time |
|---|---|---|---|---|---|---|
| Claude | 35,394-35,672 | 35,134-35,322 | 99.0-99.3% | 256-346 | 102-190 | 1.9-4.0 s |
| Codex, omit deferred | 30,668-30,716 | 15,104-29,056 | 49-95% | 0 reported | 39-52 | 2.3-5.0 s |

Claude's CLI estimated $0.0016-0.0018 per wake at list price; its cache writes were 1-hour entries. One Codex wake got 0 cached tokens on its first request, so Codex cache hits cannot be assumed.

### Fallback: interrupt, kill the process, cold resume

One trial each. The task told the model to keep working after `wait`, and the driver interrupted as soon as `wait` was recorded.

| Step | Claude | Codex |
|---|---|---|
| Interrupt sent | 1.95 s, `control_request` `interrupt` | 4.05 s, `turn/interrupt` |
| Turn end | `error_during_execution`, `aborted_streaming` | `interrupted` |
| Process exit | **1** | 0 |
| `sleep && touch early.txt` | Never ran | Never ran |
| What the model saw for `wait` | The wait result reached the turn | `aborted by user after 0.1s`, though the server registered it |
| Resume | `--resume <id>`, same session | `thread/resume`, same thread, 1.61 s, config resent |
| Wake | Finished; read 34,575, wrote 647, output 535, 6.4 s | Finished; requests 15,187 (0 cached) and 15,313 (13,696 cached) |
| MCP on resume | New `initialize` | New `initialize` |

### Clean environment

Claude ran on an allowlist from the first turn. The minimum tested was `PATH` and `HOME`, plus a `TMPDIR` we supplied (1 trial, native login worked). Nothing else was needed.

Dropped: `CLAUDECODE`, `CLAUDE_CODE_CHILD_SESSION`, `CLAUDE_CODE_SESSION_ID`, `CLAUDE_PID`, `CLAUDE_EFFORT`, `CLAUDE_CODE_MESSAGING_SOCKET`, `CLAUDE_CODE_MESSAGING_TOKEN`, `CLAUDE_CODE_SESSION_ATTENDED`, `CLAUDE_CODE_ENTRYPOINT`, `CLAUDE_CODE_EXECPATH`. Codex also ran on the allowlist, plus its token variable. Inheriting these variables was not tested.

## Verdict

1. **Ship the stdlib server.** It works with both real clients in both eras, with JSON replies, no sessions, and GET 405. Keep -32601 for `server/discover`. Refuse undeclared arguments with `isError: true`, because both clients forward them when the model sends them.
2. **Park by default, with a guard.** Parking was clean 10 of 10 when the tool was visible.
3. **Mark an agent parked at turn end, not at the `wait` call.** Claude batches `wait` with sibling tools, and the wake must not race them.
4. **Fallback: interrupt when work follows `wait`.** Trigger on any new tool activity after the `wait` result. Do not interrupt on `wait` itself, since that can abort a sibling and Codex then hides the result from the model. The state of `wait` lives in the service, so a wake must never depend on the model having seen the result.
5. **Flag a turn that ends without a required `wait` as a coverage gap.** The default Codex failure was silent.
6. **Do not use the shell as the Codex coordination path under workspace-write.** Loopback TCP is blocked there.
7. **Treat `_meta` as a join to the script on Codex, not to the model call.**
8. **Name exact tools in prompts.** Do not rely on model discovery on any harness.

**Claude driver launch settings:**
```
claude -p --input-format stream-json --output-format stream-json --verbose
  --model <m> --max-turns <n> --strict-mcp-config --setting-sources=
  --mcp-config <0600 file> --allowedTools mcp__<ns>__* <built-ins>
  --permission-mode acceptEdits --permission-prompts none
  --session-id <uuid>        (later: --resume <uuid>)
```

- Server entry: `{"type":"http","url":...,"headers":{"Authorization":"Bearer ..."},"alwaysLoad":true}`, in a file rather than argv.
- Env allowlist, plus `CLAUDE_CODE_DISABLE_AUTO_MEMORY=1`, `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1`.
- Treat exit 1 after our own interrupt as normal. Do not read `num_turns` as model calls: it was 3 for 2 messages.

**Codex driver settings:**
```json
{"method":"thread/start","params":{"cwd":"...","model":"...","approvalPolicy":"never",
 "sandbox":"workspace-write","approvalsReviewer":"user","config":{
  "mcp_servers":{"<ns>":{"url":"http://127.0.0.1:<port>/mcp","bearer_token_env_var":"<VAR>",
   "default_tools_approval_mode":"approve","required":true,"omit_tools_from":["deferred"]}},
  "shell_environment_policy":{"exclude":["<VAR>"]}}}}
```

- `<VAR>` must be in the app-server environment. Send `approvalsReviewer` explicitly, because user config can route approvals elsewhere. Resend the same fields on `thread/resume`.
- Assert in conformance that a live first turn reaches our tool. The catalog is served remotely and can change without a CLI update.

## Unknowns

- **Sample size.** Fallback, cold resume, token exclusion, slow init and shell socket are 1 trial each. Parking is 5 each, with cheap models, low effort and an instruction to stop. Stronger models and long tasks may behave differently.
- **Natural overrun.** No model ignored `wait` unprompted, so the fallback trigger never met a real overrun.
- **Long parks.** No park lasted beyond seconds. Cache cost after expiry is unmeasured. Long blocking `wait` calls and client tool timeouts were not tested.
- **Several agents in one app-server.** Per-agent tokens through distinct env variable names, or inline headers, were not tested.
- **`--permission-prompt-tool stdio`.** Not used: `--allowedTools` covered every call.
- **`omit_tools_from` durability.** Under-development feature `code_mode_only_strict_3p_tools` ignores it (`codex-rs/features/src/lib.rs:155`). Off by default in 0.164.0.
- **Other paths.** Unix sockets from the sandboxed shell, Codex child agents, `read-only` sandbox, macOS. Claude's request was not inspected: visibility is inferred from direct calls, with 0 `ToolSearch` uses in 28 messages.
