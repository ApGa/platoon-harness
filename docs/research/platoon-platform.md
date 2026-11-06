# Platoon platform: extensions, configuration, gateway and engineering conventions

## Inspected

| Project | Commit or version | Date | License |
|---|---|---|---|
| Platoon (`ApGa/platoon`, default branch) | `efe3b277c82c`, version 0.5.0 | 2026-10-28 | MIT AND Apache-2.0 (tool-call parsers); `platoon@efe3b277c82c:pyproject.toml:13` |
| TextCraft extension (same repo) | `platoon-textcraft` 0.4.0 | 2026-10-28 | MIT |
| Codex (flags only) | `05c08d765523`; CLI 0.164.0 probed | 2026-11-02 | Apache-2.0 |
| Claude Code (flags only) | `f0b737f94f3b`; CLI 2.1.316 probed | 2026-11-02 | Proprietary (Commercial Terms) |
| OpenHands SDK (flags only) | `988494576218`; `openhands-sdk` and `openhands-tools` 1.59.0 probed; Platoon pins 1.54.0 | 2026-11-02 | MIT |

Milestone 0 report, retrieved and probed 2026-11-02. Labels: IMPLEMENTED (code on the default branch), DOCUMENTED-ONLY, DRAFT/RFC (not implemented), EXPERIMENTAL (implemented, labelled unstable). PROBED means I ran it on CPU this session. Probes used a wheel of platoon 0.5.0 whose package tree is byte-identical to the clone, a `ScriptedPolicy` in place of a model, and isolated homes with dummy keys.

RFC headers lag the code, so status below comes from code. All seven RFCs in scope are `Draft` except 0009 (`Deferred`) and 0016 (`Accepted`); `Draft` does not mean unbuilt here.

| RFC | Header status | Built at this commit |
|---|---|---|
| 0008 config and CLI | Draft | Strict loading, `extends:`, run records, part of the CLI. Pydantic schema, file kinds, `arms:`, interpolation, `doctor`, `runs`: DRAFT/RFC |
| 0009 gateway step budgets | Deferred | Option A only, opt-in with `[budget] enforce = "gateway"` |
| 0013 extension model | Draft | M1-M4 IMPLEMENTED (shipped 0.2.0) |
| 0015 hosted models | Draft | M1-M2 IMPLEMENTED; M3 (eval without the `tinker` extra) not built |
| 0016 component configuration | Accepted | TOML `[options]` IMPLEMENTED. `requires:`, `program_options`, `env_options`, `reward_processor_options`, `TraceFilters`, `platoon.telemetry`: no code found |
| 0017 public surface | Draft ("Implementation: None yet") | Only the snapshot and import-boundary tests. `platoon/_api.py`, `platoon new`, `platoon doctor`, `env check`, `harness check`, conformance classes: DRAFT/RFC |
| 0018 config-only projects | Draft | Site profile, `platoon prepare`, relative input paths IMPLEMENTED |

## 1. Extension model

**Entry-point groups (IMPLEMENTED).** Exactly four, plus one retired, `platoon@efe3b277c82c:platoon/extensions.py:70`:

| Kind | Group | Loads to |
|---|---|---|
| harness | `platoon.harnesses` | `@pt.harness` function, `HarnessSpec`, spec path or directory, module, or a list |
| program | `platoon.programs` | `@pt.program` function, module, or a list |
| environment | `platoon.environments` | `pt.EnvironmentEntry`, or a list (versions) |
| reward_processor | `platoon.reward_processors` | a callable |

`platoon.plugins` is retired; `extensions check` flags it. `platoon.trainers` and a credit group are DRAFT/RFC: no such group is in `GROUPS`. Trainers, credit estimators, samplers and admission rules resolve by core name, by `package:` registration or as `module:Class`.

| Question | Answer from code | Evidence |
|---|---|---|
| Discovery without import | `importlib.metadata.entry_points()` once per process, cached; `select(group=...)`. Listing reads metadata only | `platoon@efe3b277c82c:platoon/extensions.py:255`, `:828` |
| Lazy loading | Only the entry point named exactly as the reference is imported, on first use. No lock is held during import; a second thread waits on an event | `platoon@efe3b277c82c:platoon/extensions.py:270`, `:467` |
| Legacy escape | A harness name that matches nothing loads every unloaded harness entry point, with a warning. Harnesses only | `platoon@efe3b277c82c:platoon/harness/registry/__init__.py:238` |
| Explicit selection | Config names a component (`harness:`, `program:`, `env:`, `reward_processor:`). Installing changes nothing until named | [Platoon RFC 0013](https://github.com/ApGa/platoon/blob/efe3b277c82c/docs/rfcs/0013-extension-model.md) s.1; `platoon@efe3b277c82c:tests/test_core_boundary.py:30` |
| Resolution order | `.toml` path, then `module:attr`, then `name[@version]`: core built-ins, entry point, `package:` registrations, then an error listing registered, installed, nearest and failed names | `platoon@efe3b277c82c:platoon/extensions.py:590` |
| Versions | `name@version`; prefix matches at dots (`@2` matches `2.4.6`); a bare name needs exactly one registered version | `platoon@efe3b277c82c:platoon/extensions.py:182` (`matching`) |
| Names | `[a-z0-9]+([._-][a-z0-9]+)*`; owner is the first `-` word; `platoon`, `platoon-*` and `CORE_NAMES` are reserved | `platoon@efe3b277c82c:platoon/extensions.py:92`, `:86`, `:144` |
| Duplicates | `name@version` from two sources raises "defined twice" at registration, so only when named. No metadata preflight: `check_extensions` does not detect it, and [Platoon RFC 0017](https://github.com/ApGa/platoon/blob/efe3b277c82c/docs/rfcs/0017-public-surface-and-conformance.md) lists that as a gap. A TOML spec beats a function harness of the same ref, with a warning | `platoon@efe3b277c82c:platoon/harness/registry/__init__.py:85`, `platoon@efe3b277c82c:platoon/harness/function.py:119`, `platoon@efe3b277c82c:platoon/programs.py:213`, `platoon@efe3b277c82c:platoon/envs/named.py:268` |
| Failure isolation | A failed entry point is recorded; only a lookup of that name fails | `platoon@efe3b277c82c:platoon/extensions.py:515` |
| Compatibility | The distribution's requirement on `platoon` is read from metadata, extras included, and refused before import. `PLATOON_IGNORE_EXTENSION_REQUIREMENTS=1` overrides with a warning | `platoon@efe3b277c82c:platoon/extensions.py:343`, `:392`, `:96` |
| Provenance | `Origin(distribution, version, entry_point, module)`; `run_components` resolves everything at run start and fills `lock.json` | `platoon@efe3b277c82c:platoon/extensions.py:1121`, `:1429` |
| Static checks | `platoon extensions check [DIST...] [--load]`: names, owners (warning), range incompatibility (error), no requirement or no upper bound (warning), retired groups; exit 78 on error | `platoon@efe3b277c82c:platoon/extensions.py:1003` |

Known provenance gaps: components named while a run is under way (a program spawning a harness by name) are not in the lock ([Platoon RFC 0013](https://github.com/ApGa/platoon/blob/efe3b277c82c/docs/rfcs/0013-extension-model.md) s.7); import-string origin is best effort.

**Conformance, `platoon.testing`.** Ships in the core wheel. Opt-in pytest plugin (`pytest -p platoon.testing`, no autoload).

| Item | Status |
|---|---|
| `ScriptedPolicy`, `Completion`, `tool_call`, `rules`, `run_episode`, `serve_policy`, `make_gateway`, `toy_tokenizer`, `toy_renderer` | IMPLEMENTED, stated stable. Needs the `tinker` extra, `platoon@efe3b277c82c:platoon/testing/__init__.py:1` |
| `check_task_sampler`, `check_group_admission`, `check_trainer`, `check_credit_estimator` | EXPERIMENTAL. Each is a tuple of named checks; one `AssertionError` lists every failure by name, `platoon@efe3b277c82c:platoon/testing/credit.py:48` |
| `EnvironmentConformance`, `HarnessConformance`, golden-record helpers, `platoon new` | DRAFT/RFC (0013 s.9, 0017) |

So no conformance suite exists today for harnesses, environments, programs or sandbox providers.

## 2. Configuration

| Topic | From code | Status |
|---|---|---|
| Schema | Stdlib dataclasses plus a hand-written strict validator of 1807 lines; pydantic fields are understood where they occur. [Platoon RFC 0008](https://github.com/ApGa/platoon/blob/efe3b277c82c/docs/rfcs/0008-config-and-cli.md)'s pydantic rewrite is not built | IMPLEMENTED, `platoon@efe3b277c82c:platoon/utils/config.py:600` |
| Unknown keys | Dotted path plus did-you-mean; every problem reported at once (`ConfigError.problems`) | IMPLEMENTED, `platoon@efe3b277c82c:platoon/utils/config.py:525` |
| File format | YAML for configs, TOML for harness specs | IMPLEMENTED |
| `extends:` | One path or a list, relative to the file; bases first, cycles rejected. Mappings deep-merge; everything else, lists included, replaces | IMPLEMENTED, `platoon@efe3b277c82c:platoon/utils/config.py:116` |
| Overrides | `a.b=v`, `a.0.b=v`, `a.b+=v`, parsed against the target field's type, not guessed | IMPLEMENTED, `platoon@efe3b277c82c:platoon/utils/config.py:1062` |
| Component options | `[options.NAME]` in TOML specs with `type`, `default`, `allowed`, `min`, `max`; checked at load and again at render; never rendered into `[install]` | IMPLEMENTED for TOML specs, `platoon@efe3b277c82c:platoon/options.py:47` |
| Phases | `train` versus `eval`; `eval_overrides` merged over per key | IMPLEMENTED |
| Site profile | `$PLATOON_SITE`, else XDG `platoon/site.yaml`. Fills gaps only; may not weaken isolation or change what trains; path and SHA-256 recorded | IMPLEMENTED, `platoon@efe3b277c82c:platoon/site.py:484` |
| CLI | cyclopts >=5, imports inside command bodies; `--help` measured 0.78 s (RFC target 0.3 s) | IMPLEMENTED, `platoon@efe3b277c82c:platoon/cli.py:90`, PROBED |
| Exit codes | 0, 1, 64 usage, 78 configuration (never restart) | IMPLEMENTED, `platoon@efe3b277c82c:platoon/cli.py:69` |

**Precedence, lowest to highest** (`platoon@efe3b277c82c:platoon/utils/config.py:1293`): schema defaults; a named environment's entry (`env:`); `extends:` bases in order; the file; `key=value` overrides. The site profile then fills only what those left unset. Within options: `harness_defaults`, `harness_options`, `eval_overrides.harness_options`.

**Sanitized resolved config: there is none.** `config.resolved.yaml` is the merged config, unredacted, with a provenance header (sources, overrides, site profile SHA) and loadable as a config (`platoon@efe3b277c82c:platoon/utils/config.py:1555`). Safety comes from construction: a config never holds a key. `inference.hosted.api_key_env` must be a variable name, and a `base_url` with credentials, query or fragment is refused (`platoon@efe3b277c82c:platoon/eval/config_defs.py:223`). `{api_key}` may render only into `[launch.env]` and `[mcp.env]` (`platoon@efe3b277c82c:platoon/harness/spec.py:100`).

**Reproducibility manifest** (`lock.json`, `platoon@efe3b277c82c:platoon/utils/config.py:1646`): `versions`, `commits`, `platoon_git_sha`, `platoon_git_dirty`, `python`, `hostname`, `started_at`, `argv`, `deprecations`, `components` (`kind`, `ref`, `resolved`, `source`, `distribution`, `distribution_version`, `entry_point`, `environments`), `extensions` (`version`, `requires`, PEP 610 `direct_url`), plus `site`, `sandbox_providers`, `tool_call_parsing`, `image_pulls` and harness options per phase. `hostname` and `argv` are not public-safe by default.

## 3. Gateway

**Where.** `platoon/gateway/`: `core.py` (`ModelGateway`, `AgentSession`), `server.py` (`GatewayServer`, aiohttp), `dialects/`, `hosted.py`, `mcp.py`, `trace.py`. IMPLEMENTED. A library only: no `platoon gateway` command exists. `harness_rollout` embeds one per rollout (`platoon@efe3b277c82c:platoon/harness/rollout.py:124`), in the process that holds the sampler.

**Routes** (`platoon@efe3b277c82c:platoon/gateway/server.py:229`), each also under `/s/{secret}` except `/healthz`:

| Route | Purpose | Status |
|---|---|---|
| `POST /v1/chat/completions` | Reference dialect | IMPLEMENTED |
| `POST /v1/responses` | OpenAI Responses | EXPERIMENTAL |
| `POST /v1/messages`, `/v1/messages/count_tokens` | Anthropic Messages | EXPERIMENTAL |
| `GET /v1/models` (key required), `GET /healthz` (open) | Discovery, health | IMPLEMENTED |
| `POST /v1/platoon/agents` | Mint a child: `{role, goal?}` to `{agent_id, api_key, base_url}` | IMPLEMENTED |
| `/mcp` | The agent's env tools over streamable HTTP | IMPLEMENTED |

[Platoon RFC 0005](https://github.com/ApGa/platoon/blob/efe3b277c82c/docs/rfcs/0005-gateway-dialects-and-tito.md)'s token ledger, TITO bridge, call-kind classifier and shards are DRAFT/RFC. SSE is synthetic: the whole completion is sampled, then emitted, with `: keepalive` comments.

**Auth and per-agent secrets.** `Authorization: Bearer`, `x-api-key`, or path `/s/<secret>/v1/...` (`platoon@efe3b277c82c:platoon/gateway/server.py:497`). `open_agent` mints `secrets.token_urlsafe(32)` per agent (`platoon@efe3b277c82c:platoon/gateway/core.py:1532`). Unknown key 401, closed agent 410. `serve_rollout` scopes a server to its rollouts, on TCP and Unix socket. There is no user or TLS layer: the agent key is the only access control, on loopback (`platoon@efe3b277c82c:platoon/harness/rollout.py:72`). `GatewayServer.start` itself defaults to `0.0.0.0`, so a direct caller must pass a host.

**Minting limits.** Only `role` and `goal`; no `max_steps`, `access`, `fork` or `harness`. Default 64 per rollout, `PLATOON_MAX_MINTED_AGENTS` to change (`platoon@efe3b277c82c:platoon/gateway/core.py:105`). A child inherits call cap and tally, `policy_only`, tools and access (`platoon@efe3b277c82c:platoon/gateway/core.py:1581`). There is no HTTP way to report a child's outcome, so a minted child shares the episode outcome (`platoon@efe3b277c82c:platoon/gateway/trace.py:1`).

**Pass-through (`inference.hosted`).** IMPLEMENTED, `platoon eval` and `platoon rollout` only; training refuses it. `HostedGateway` forwards in the harness's own dialect with no translation, and `dialect` must match what `base_url` speaks. Config: `base_url`, `api_key_env`, `timeout_s`, `max_retries`, `max_concurrent_requests`, `pricing`. Agents, keys, call kinds, budgets and judges switch are inherited. Redirects are never followed, 401/402/403/404 stop the run, and the provider key never reaches the harness (`platoon@efe3b277c82c:platoon/gateway/hosted.py:636`). PROBED against a fake provider: the agent key was swapped for the provider key and the model replaced.

| Records | Tinker-backed | Hosted |
|---|---|---|
| Identity | `call_id`, agent, rollout, role, policy, version, `fork_step`, parent link | same |
| Tokens | prompt tokens, sampled tokens, logprobs, `routing_id` | none: `prompt=None`, `tokens=[]`, `trainable=False` |
| Content | parsed `content`, `reasoning_content`, `tool_calls`, parse counts | same fields from the reply; the request is not kept |
| Accounting | timing, stop reason | `ProviderRecord`: usage, served model, ids, attempts, cost |
| Tools | `tool_calls` per agent, only for tools through the MCP plane or `ctx.call_tool` | same |

Not recorded: request headers, native session or thread ids, native tool executions. Non-streaming responses carry `x-platoon-call-id`; Tinker-backed streaming responses do not, so read the chunk `id` there (critic probe; `platoon@efe3b277c82c:platoon/gateway/server.py:344`). Evidence: `platoon@efe3b277c82c:platoon/gateway/core.py:738`, `:694`, `:891`. Call kinds `policy`, `aux`, `judge` come from `X-Platoon-Call-Kind`, default `policy` (`platoon@efe3b277c82c:platoon/harness/agent.py:41`). A harness in a task sandbox may not send `judge`, nor `aux` under a call cap (`platoon@efe3b277c82c:platoon/gateway/core.py:980`).

**Hosted streaming is buffered.** The stream is read whole before relay, so a broken stream can retry and the record is complete. PROBED: a provider emitting four events over 1.5 s reached the client at 1.50 s, all at once.

**CPU and fake backends.** Yes, PROBED, but `platoon.gateway` imports `tinker` at module load (`platoon@efe3b277c82c:platoon/gateway/core.py:43`), which brought in `tinker_cookbook` and `torch` (8.9 s import). `make_gateway(ScriptedPolicy(...))` served all three dialects, count_tokens, minting (201) and the path form; a child got its own record. The hosted path also needs that import, because [Platoon RFC 0015](https://github.com/ApGa/platoon/blob/efe3b277c82c/docs/rfcs/0015-hosted-models-and-judges-in-eval.md) M3 is not built. A `GET /v1/responses` WebSocket upgrade returned 405, where [Platoon RFC 0005](https://github.com/ApGa/platoon/blob/efe3b277c82c/docs/rfcs/0005-gateway-dialects-and-tito.md) says 426; custom Codex providers default to no WebSockets, so this is harmless (`codex@05c08d765523:codex-rs/model-provider-info/src/lib.rs:227`).

### Pointing harnesses at it

`{base_url}` is `http://127.0.0.1:<port>` without `/v1`, and `{model}` is `policy`; the Tinker path ignores the requested model name. Keys go in the environment, never argv. Results below are end-to-end PROBED against the real gateway with a scripted policy.

| Harness | Exact configuration | Probe result |
|---|---|---|
| OpenHands SDK | `LLM_MODEL=openai/{model}`, `LLM_BASE_URL={base_url}/v1`, `LLM_API_KEY={api_key}`, `LITELLM_LOCAL_MODEL_COST_MAP=True`, `HOME={state_dir}`; flags in the spec below | PASS with SDK 1.59.0 through Platoon's runner, exit 0: two tool-calling turns, each with tokens and logprobs |
| Codex 0.164.0 | `CODEX_HOME/config.toml` below, `PLATOON_API_KEY={api_key}` in env, `codex exec --skip-git-repo-check --json ...` | PASS: one-turn and tool-round-trip runs recorded with tokens and logprobs, `stream: true`, no gateway errors. "Model metadata for `policy` not found" warning |
| Claude Code 2.1.316 | `ANTHROPIC_BASE_URL={base_url}` (no `/v1`), `ANTHROPIC_AUTH_TOKEN={api_key}` (Bearer) or `ANTHROPIC_API_KEY` (`x-api-key`) | FAIL: every request 400 `Unsupported message role 'system'`; zero records. Same with `CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS=1` |

```toml
# Codex: not a Platoon spec; config I verified by running it.
model = "policy"
model_provider = "platoon"
[model_providers.platoon]
name = "platoon"
base_url = "{base_url}/v1"
env_key = "PLATOON_API_KEY"
wire_api = "responses"   # the only supported value
```

Claude Code cause: it sent `messages` with roles `['user', 'system']`; `chat_request` accepts only `assistant` and `user` (`platoon@efe3b277c82c:platoon/gateway/dialects/anthropic.py:169`). The fix upstream is small, but see the terms issue in section 4. Other refusals in training mode: `stop_sequences`, `tool_choice` `any`/`tool`, image blocks. Codex note: `function_tools` drops every non-`function` tool, so `web_search` and the `multi_agent_v1` namespace that Codex sent never reach the policy (`platoon@efe3b277c82c:platoon/gateway/dialects/responses.py:127`). Non-Platoon sources: `claude-code@f0b737f94f3b:CHANGELOG.md:6166`; https://code.claude.com/docs/en/llm-gateway-connect.md and https://learn.chatgpt.com/docs/config-file/config-reference (both retrieved 2026-11-02).

## 4. Harness integration today

Two kinds, and one rollout path (`platoon@efe3b277c82c:platoon/harness/rollout.py:207`):

| Kind | Declared by | Runs | Subagents |
|---|---|---|---|
| Function harness | `@pt.harness`; `async fn(ctx) -> pt.AgentResult` | Inline in the rollout worker's event loop | `ctx.agents.spawn(...)` with fork, access, budget, grading, role |
| TOML `HarnessSpec` | `[install]`, `[launch]`, `[builtins]`, `[mcp]`, `[final_message]`, `[exit_codes]`, `[options]`, `[resources]`, `[budget]` | `task_sandbox` or `local` subprocess with allow-listed env (`platoon@efe3b277c82c:platoon/harness/runner.py:86`) | **Not via `spawn`**: `TypeError`, `platoon@efe3b277c82c:platoon/harness/agents.py:318`. Only by minting over HTTP, cooperatively |

Placement rule: in the task sandbox when one exists; otherwise local, with built-ins disabled where the spec says how.

| Harness | Defined in Platoon? | Dialect | Status | Exact attribution now? |
|---|---|---|---|---|
| `platoon-react`, `platoon-codeact` | function | in process | IMPLEMENTED | **Yes**, exact including children |
| `platoon-bash@1` | spec, with `[mcp]` | Chat | IMPLEMENTED, CPU tests | **Yes**, one agent per process |
| `mini-swe-agent@2.4.6` | spec | Chat | IMPLEMENTED | **Yes**, one agent |
| `openhands@1.54.0.post1` | spec + `run_openhands.py` | Chat | IMPLEMENTED; live test opt-in via `PLATOON_TEST_TOOLCHAINS`, not run here | **Yes**, root only; native delegation off by construction |
| Codex | **No spec**; dialect and fixtures only | Responses | Dialect EXPERIMENTAL; harness DOCUMENTED-ONLY | Mechanically yes in my probe; no supported path |
| Claude Code | **No spec**; dialect and fixtures only | Messages | Dialect EXPERIMENTAL, fails with 2.1.316 | **No** |
| pi, opencode, Prime Agent | **No spec** | Chat ([Platoon RFC 0005](https://github.com/ApGa/platoon/blob/efe3b277c82c/docs/rfcs/0005-gateway-dialects-and-tito.md) table) | DRAFT/RFC | No |
| Any custom agent | your own TOML or function | any of three | IMPLEMENTED | Yes, when it uses only its own key |

`platoon@efe3b277c82c:README.md:15` says harnesses such as "openhands, codex, pi" are specs; the built-in spec directory holds only `mini-swe-agent`, `openhands` and `platoon-bash`.

**Adapter choice, from these facts: OpenHands SDK.** It is the only third-party real agent with a built-in spec, the stable Chat dialect, a pinned closure, retries off (`num_retries=0`, so a retry cannot record a call twice), condenser calls marked `aux` by its runner, and reasoning replay so prompts extend. Limits to carry over: the spec has no `[mcp]` table, so it receives no MCP tools from the spec path; its tools are `terminal`, `file_editor`, `task_tracker`, `finish`, `think`; it runs without skills or delegation (`platoon@efe3b277c82c:platoon/harness/builtin/openhands/run_openhands.py:12`). Our driver will likely use the SDK directly with the same LLM settings. Codex is the second candidate: it worked in a probe, but rests on an experimental dialect and has no Platoon spec. Critic addendum: Codex's MCP tools never reach a policy behind the gateway, because `namespace` tools are dropped, and pi also passed the full child-key path, so see `README.md` before ranking these.

**Claude Code is not a training path.** [Platoon RFC 0005](https://github.com/ApGa/platoon/blob/efe3b277c82c/docs/rfcs/0005-gateway-dialects-and-tito.md) leaves terms of use open (`platoon@efe3b277c82c:docs/rfcs/0005-gateway-dialects-and-tito.md:172`), and Anthropic says it does not support routing Claude Code to non-Claude models through any gateway (https://code.claude.com/docs/en/llm-gateway, retrieved 2026-11-02). Treat it as Operational and Observable only.

**Native subagents.** Nothing is implemented. Native children share the parent's key, so their calls collapse into the parent (`platoon@efe3b277c82c:docs/rfcs/0001-native-multi-agent.md:25`). `Attribution`, `AgentGraph`, `[native]` selectors, `NativeAgentMap`, `X-Platoon-Agent` and `credit.train_attribution` have zero hits under `platoon/`: all DRAFT/RFC.

| [Platoon RFC 0001](https://github.com/ApGa/platoon/blob/efe3b277c82c/docs/rfcs/0001-native-multi-agent.md) mapping | Header | Check |
|---|---|---|
| Codex | `thread-id`, `x-codex-parent-thread-id` | Headers exist; `thread-id` observed in my probe |
| Claude Code | `x-claude-code-agent-id`, `x-claude-code-parent-agent-id` | Exist in its changelog; gateway ignores them |
| OpenHands | per sub-conversation, or child credentials through a delegate factory | Proposal |

The only exact-identity path for an external agent today is one key per agent: `POST /v1/platoon/agents`, with the child's process using the returned `base_url` and `api_key`. Everything else needs an upstream change. An exact agent still shares one tree: one `parent_agent_id` per agent, no peer or `informed_by` edges (`platoon@efe3b277c82c:platoon/gateway/trace.py:1`).

## 5. Environment forking and sandbox interfaces

| Boundary | Surface | Status | Stability |
|---|---|---|---|
| Fork | `EnvSession.fork(mode, *, task=None)`, `ForkMode = shared, copy, fresh`; a mode that cannot be provided fails loudly | IMPLEMENTED for ORS, Harbor, table, `platoon@efe3b277c82c:platoon/envs/service.py:40`, `:241` | Public (`tests/public_api.txt`) |
| Spawn with fork | `ctx.agents.spawn(goal, fork=, access=, max_steps=, role=, harness=)` | IMPLEMENTED for function harnesses, `platoon@efe3b277c82c:tests/public_api.txt:6` | Public |
| ORS hooks | `platoon_fork`, `platoon_copy`; `copy` refused without them where teardown exists | IMPLEMENTED | Documented |
| Live-env gate | serial, concurrent, exclusive classes through `platoon/envs/gate.py` | IMPLEMENTED | Internal |
| Needs | `SessionNeeds(upstreams, mounts, extra_memory_mb)` | IMPLEMENTED, `platoon@efe3b277c82c:platoon/envs/service.py:148` | Public |
| Sandbox | `SandboxSpec`, `Sandbox` (`exec`, `upload`, `download`, `snapshot`, `kill_processes`, `stop`, `routes`), `SandboxProvider` (`start`, `restore`), `CAPABILITIES` | IMPLEMENTED, `platoon@efe3b277c82c:platoon/sandbox/base.py:77`, `:160`, `:206`, `:64` | Private by the current rule: not in `PUBLIC_MODULES`. [Platoon RFC 0017](https://github.com/ApGa/platoon/blob/efe3b277c82c/docs/rfcs/0017-public-surface-and-conformance.md) proposes stable |
| Providers | `process` (no isolation), `docker`, `singularity`, `enroot` (the `hpc` extra) | IMPLEMENTED | Selected by name or `module:Class` |
| Stacks | Multi-container tasks; `copy` forks refused | IMPLEMENTED ([Platoon RFC 0010](https://github.com/ApGa/platoon/blob/efe3b277c82c/docs/rfcs/0010-harbor-registry-and-multi-container-tasks.md)) | Internal |

There is no dedicated forking RFC. The contract is `platoon@efe3b277c82c:docs/architecture.md:299`, the `fork_mode` field and `snapshot_async` of [Platoon RFC 0001](https://github.com/ApGa/platoon/blob/efe3b277c82c/docs/rfcs/0001-native-multi-agent.md) (DRAFT/RFC there), and [Platoon RFC 0010](https://github.com/ApGa/platoon/blob/efe3b277c82c/docs/rfcs/0010-harbor-registry-and-multi-container-tasks.md)'s forks section. Harbor's `copy` restores a snapshot through the provider (`platoon@efe3b277c82c:platoon/envs/harbor/session.py:582`).

Reusable boundary: `EnvSession` and `pt.ForkMode` in Platoon-managed mode, with Platoon authorizing and executing forks. We should not write snapshot, copy, sandbox runtime, route or reaping code, and we should not import `platoon.sandbox` from the SDK. Minted agents get no fork: a child that needs one must come through `spawn`, or an upstream extension to the agent API.

## 6. Engineering conventions

| Area | Platoon does | Mirror? |
|---|---|---|
| Workspace | `[tool.uv.workspace] members = ["extensions/*"]`, one `uv.lock`; examples excluded because a member's components would register for every developer (`platoon@efe3b277c82c:pyproject.toml:142`) | Yes, with `members = ["packages/*", "extensions/*"]`; keep examples out |
| Build | hatchling >=1.27, `hatch-fancy-pypi-readme`; `requires-python >=3.12`; `.python-version` 3.12; `py.typed` | Yes |
| Extension layout | `extensions/<name>/{pyproject.toml,README.md,LICENSE,src/<pkg>/,tests/}`; own version, `[tool.ruff] src = ["src"]`, `[tool.uv.sources] x = { workspace = true }`; PyPI-only published requirements | Yes |
| Compat range | One minor below 1.0: `platoon[ors]>=0.5,<0.6`, read before load (`platoon@efe3b277c82c:extensions/textcraft/pyproject.toml:24`) | Yes |
| Ruff | `line-length = 120`; `select = ["E", "F", "I"]`; pre-commit `v0.14.5`, kept equal to `uv.lock` by a test | Yes; consider adding rules from day one |
| Types | `ty.toml`, pinned `uvx ty@0.0.87 check`, **manual only, not a gate**; `unresolved-import = "ignore"`; per-directory leniency | Pin it, but gate it from the start |
| Pre-commit | ruff-check `--fix`, ruff-format, `conventional-pre-commit` v4.0.0 at commit-msg, `default_stages: [pre-commit]` | Yes |
| Pytest | **No `[tool.pytest]` section.** Markers registered in `tests/suite_settings.py`; `serial` is the only custom marker; `pytest-asyncio` with `pytestmark = pytest.mark.asyncio`; `pytest-xdist` with `-n auto --dist loadfile`; no `__init__.py`, so test filenames are globally unique | Keep two passes; put markers in `pyproject.toml` and add `live` with explicit opt-in |
| Test style | CPU only, no network, port 0, `tmp_path`, `monkeypatch`; autouse fixtures keep site state out | Yes |
| CI | `lint`, `test` (3.12-3.14), `extensions` matrix, `recipes`, `docker-stacks` (fails on any skip), all gated on `!repository.private`; `pr-title` separate | Yes; add macOS, which Platoon's Linux-only classifier omits |
| Commits, PRs | Conventional Commits, no scope, sentence case, no final period (`subjectPattern: ^[A-Z].*[^.]$`, `disallowScopes: .+`); squash merge; PR template with Summary, Why, Links, Tests, Checklist; `!` and `BREAKING CHANGE:` footer | Yes |
| Agent guidance | **No `AGENTS.md` or `CLAUDE.md` in this clone.** A 61 KB `CONTRIBUTING.md` serves that purpose | Our `AGENTS.md` is new; keep it short |
| RFCs | `docs/rfcs/NNNN-title.md`, `0000-template.md`, index table checked by `tests/test_rfc_index.py`. Sections: Summary, Motivation, Proposal, optional The hard parts, Alternatives, Rollout plan with exit checks, Open questions. Lifecycle Draft, Accepted, Implemented, Rejected, Deferred. `EST` and `UNVERIFIED` markers | Yes |
| Docs | `getting-started`, `tutorials`, `how-to`, `extending`, `reference`, `rfcs`, `architecture.md`. Reference generated by `scripts/gen_reference.py`, staleness tested | Yes |
| Doc tests | `tests/test_contributing_docs.py` runs guide snippets; `tests/docs/test_docs_links.py`; `tests/docs/test_no_internal_references.py` bans private names by SHA-256 | Yes, all three |
| Public surface | `scripts/public_api.py` writes `tests/public_api.txt`, compared by `tests/test_public_api.py`, covering `platoon`, `platoon.gym`, `platoon.testing`, `platoon.experimental` | Yes |
| Boundaries | `tests/test_import_boundaries.py` (AST), with a justified `PRIVATE_IMPORTS` list that fails on stale entries; `tests/test_core_boundary.py` (subprocess, checks `sys.modules`) | Yes; this enforces "SDK must not import CLI, Platoon, Torch" |
| Packaging tests | `tests/test_packaging.py`: every requirement imported and vice versa, no direct URLs, one version source | Yes |
| Changelog | `## X.Y.Z (date)`, headings New features, Changes, Fixes, Deprecations, Install and upgrade; release PR dates it | Yes |
| Release | Tag from `main` via OIDC trusted publishing; actions pinned to commits, no cache, `persist-credentials: false`; `uv build --no-sources`, `twine check --strict`, `uvx --from dist/*.whl <cmd>` in a fresh env; tag must be on main and dated in the changelog (`platoon@efe3b277c82c:.github/workflows/release.yml:35`, `:49`, `:52`, `:55`) | Mirror the checks now; publishing is out of scope for this project's rules |
| Deprecations | One minor release with a warning naming the replacement and removal version | Yes |

## 7. Namespace analysis (this clone only)

Method: `git grep -i -E "platoon[_-]harness"` over every tracked file, parse of all four `pyproject.toml` files, and a probe. PyPI and the web were not consulted.

| Name | Could it collide? | Evidence |
|---|---|---|
| Import `platoon_harness` | **No.** The wheel holds only `platoon`; no `extend_path` remains, and a top-level `platoon_harness` is a different name from the subpackage `platoon.harness`. PROBED side by side: `hasattr(platoon, "platoon_harness")` is False | `platoon@efe3b277c82c:pyproject.toml:112` |
| Import `platoon_harness_cli` | **No.** No hits | same |
| Executable `platoon-harness` | **No.** The only console script is `platoon`; no extension declares scripts. `platoon harness` is a subcommand, not an executable | `platoon@efe3b277c82c:pyproject.toml:103` |
| Other packages in the clone | `platoon_textcraft`; `example_extension` and `tool_loop` (examples, not workspace members) | `extensions/` holds only `textcraft` |

**Confirmed: no collision.** These adjacent facts still need care:

| Finding | Consequence |
|---|---|
| Doc anchors `#platoon-harness*` in `docs/reference/cli.md` | Harmless |
| `SANDBOX_STATE_ROOT = "/tmp/platoon-harness"`, local root `platoon-harness-<uid>` (`platoon@efe3b277c82c:platoon/harness/runner.py:83`, `:178`) | Do not use these paths; our process may run inside such a sandbox |
| `AGENT_MARKER_ENV = "PLATOON_HARNESS_AGENT"` (`platoon@efe3b277c82c:platoon/harness/runner.py:84`), used to find and kill agent trees | Avoid a `PLATOON_HARNESS_` env prefix; also avoid `PLATOON_API_KEY`, which specs set |
| `__platoon_harness__` attribute (`platoon@efe3b277c82c:platoon/harness/function.py:37`) | Do not reuse it in our decorators |
| `may_use_reserved_names(distribution="platoon-harness-sdk")` is True, PROBED (`platoon@efe3b277c82c:platoon/extensions.py:144`) | Our distributions count as "the project's own" by prefix. A component they register in Platoon's groups could take `platoon-*` or `openhands`, and the one-owner warning is skipped. Module-based registration stays refused. Avoid reserved names by policy; use another owner such as `harness-*` |
| First-party convention `extensions/<name>` gives `platoon-<name>` and `platoon_<name>` (CONTRIBUTING, "Add an extension") | A Platoon extension named `harness` would take exactly `platoon_harness`. None exists; the owner should treat the name as taken |
| Config and cache dirs `~/.config/platoon`, `~/.cache/platoon` | Use `platoon-harness/` under XDG, not these |
| Groups are exact-match; Platoon reads only `platoon.<kind>` | Name ours `platoon_harness.<kind>`, never `platoon.*` |

## Implications for platoon-harness

**Extensions**
1. Copy the discovery rule, not the code: metadata scan, exact-name lazy load, reference forms `name[@version]` and `module:attr`, one resolver per kind, errors that list registered, installed, nearest and failed names.
2. Start with few groups under `platoon_harness.*` (`drivers`, plus only those with a second user). "A kind gets a group when a second independent user needs a short name" is the right bar.
3. Improve on Platoon: detect duplicates from metadata before any import, in `doctor` and at run start. Check required capabilities there too, which Platoon has no concept of.
4. Check a requirement on `platoon-harness-sdk` before import, and warn on a missing upper bound. Keep a dev-only override env var.
5. Ship `check_driver(...)` as named checks returning all failures at once, in a separate testing module with an opt-in pytest plugin. Platoon's four `check_*` functions are the model. It has no harness conformance to copy.
6. Record `lock.json`-style provenance per run: component ref, resolved, source, distribution, version, entry point, `direct_url`, plus schema and protocol versions. Leave `hostname` and `argv` out of exports by default.

**Configuration**
7. Use pydantic v2 frozen models with `extra="forbid"`, and TOML through stdlib `tomllib`. A new project should not grow an 1800-line validator; [Platoon RFC 0008](https://github.com/ApGa/platoon/blob/efe3b277c82c/docs/rfcs/0008-config-and-cli.md) reached the same conclusion, and pydantic gives the JSON schema the protocol layer needs anyway.
8. Copy these semantics: mappings merge, lists replace, typed overrides, every problem at once, did-you-mean, a resolved snapshot that reloads alone.
9. Build a real sanitizer. Platoon relies on configs never holding secrets; adopt that rule (env var names only) and add an export-time redaction pass, because our traces hold prompts. `redact` and `secret_forms` in `hosted.py` show that a key's escaped and percent-encoded forms need redacting too.
10. Use cyclopts in the CLI package only, with imports inside commands, and adopt exit code 78 for configuration errors.

**Training bridge**
11. Keep all gateway use behind an optional extension. `platoon.gateway` pulls in `torch` at import. Core CI needs its own small fake OpenAI endpoint; run gateway compatibility tests in an extension job with `platoon[tinker,ors]>=0.5,<0.6`.
12. Do not route everyday traffic through the gateway. It buffers streams, needs API keys rather than subscriptions, and keeps no request. Use it only in training or evaluation.
13. Give every trainable agent its own key. In Platoon-managed mode, the SDK receives the root's endpoint and mints children with `POST /v1/platoon/agents`; never reuse a key across agents or infer identity.
14. Our bridge could be an optional function harness in `platoon.harnesses`, with an owner not named `platoon-*`, so that Platoon still owns rollout, gateway and grading. The design step should confirm this.
15. Trainable profile for OpenHands: native delegation off, `num_retries=0`, reasoning replay on, condenser off or marked `aux`. Mark a driver Trainable only with such a pinned profile.
16. Mark Claude Code and Codex with native subagents enabled as not Trainable. A native child's calls are indistinguishable from the parent's at the gateway.
17. Export our richer graph beside Platoon's tree rather than through it: `AgentGraph` does not exist, and trajectories hold one parent per agent. Target `TrajectoryCollection`, `ParentInfo` and misc keys, and label `AgentGraph` a proposal.
18. Propose upstream, as small amendments: child outcome and goal over the agent API, `fork` on mint, the Messages `system` role, a configurable mint limit (the default of 64 is below the brief's 100 agents), and native-id capture. Do not patch installed Platoon.

**Sandboxes and repository**
19. Define a small workspace protocol of our own for standalone mode. In Platoon-managed mode, delegate to `EnvSession` and `spawn`.
20. Mirror the repository rules in section 6, and add from the first commit: `ty` as a gate, macOS CI, import-boundary tests, API snapshot, `test_no_internal_references`, generated reference.

## Taste notes

- Worth copying: one rule for finding every component, and errors that say what was found, what was close and how to fix it.
- Worth copying: refusal before cost. Exit 78 before any rollout, a probe per dialect before any task, compatibility before import.
- Worth copying: absence stays honest. `Outcome.infra` is never a reward of 0, and a fork mode that cannot be provided fails rather than degrades.
- Worth copying: tests that keep prose true (doc snippets run, the API snapshot, an index test) and lists of exceptions that fail when stale.
- Worth copying: a harness as data, with secrets allowed only in specific template fields, checked at load.
- Avoid: one configuration schema with 1800 lines of custom validation, or dataclass fields that exist for one extension ([Platoon RFC 0016](https://github.com/ApGa/platoon/blob/efe3b277c82c/docs/rfcs/0016-component-configuration.md) calls these out).
- Avoid: module docstrings that carry design history. Keep docstrings short and put rationale in RFCs.
- Avoid: `platoon-*` trust by name prefix, process-global registries and patching class attributes in test helpers (`serve_policy` patches `EvalPolicy.install`).

## Unknowns and risks

- **Claude Code result is one version and one setup** (2.1.316, `--setting-sources=`, isolated home, `-p`). No other flags were tried for suppressing the `system` message. The hosted path was not probed with it.
- **Codex was probed for one tool round trip only**: no compaction, no parallel calls, no native subagent, no long run. The model-metadata warning may degrade behavior.
- **OpenHands probe used SDK 1.59.0**, not the pinned 1.54.0, and the runner overrides private SDK methods. Platoon's live test was not run (it needs a 600 MB toolchain). A driver on a newer SDK needs its own pin.
- **Prefix extension failed in both tool probes** under the toy tokenizer: the second prompt diverged inside the first completion, so calls will not merge into one datum there. Platoon's trainer tolerates this by starting a new datum. I did not test a real model's renderer. [Platoon RFC 0005](https://github.com/ApGa/platoon/blob/efe3b277c82c/docs/rfcs/0005-gateway-dialects-and-tito.md)'s ledger, which would fix re-rendering, is unbuilt.
- **Dialects can break silently.** Responses and Messages are EXPERIMENTAL, with hand-written fixtures and no pinned harness version. Harness releases change request shapes, as the Claude Code failure shows.
- **Side calls are unclassified.** Any call without the header is `policy`. [Platoon RFC 0005](https://github.com/ApGa/platoon/blob/efe3b277c82c/docs/rfcs/0005-gateway-dialects-and-tito.md)'s classifier is unbuilt, and static headers cannot mark individual calls, so Codex or Claude background calls would train as policy turns if they occur.
- **`platoon.sandbox`, `platoon.extensions` and `/v1/platoon/agents` lack a stated stability promise.** [Platoon RFC 0017](https://github.com/ApGa/platoon/blob/efe3b277c82c/docs/rfcs/0017-public-surface-and-conformance.md) would cover them, but it is a Draft with no code. Pin `<0.6`.
- **Heavy pins in the bridge**: `tinker==0.16.1` and `tinker-cookbook<0.4` apply to the training extension, and must stay out of the SDK's dependencies.
- **Platoon classifiers are Linux-only**; macOS behavior of the bridge is unknown.
- **Clean room**: searches stayed inside this clone. `platoon-harness` strings found there are Platoon's own (listed in section 7). No external project of that name was surfaced or opened.
