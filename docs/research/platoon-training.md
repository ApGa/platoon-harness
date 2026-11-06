# Platoon training-facing interfaces

## Inspected

| Project | Commit or version | Date | License |
|---|---|---|---|
| platoon (git clone, default branch) | `efe3b277c82c`, "Release 0.5.0" | committed 2026-10-28, inspected 2026-11-02 | MIT AND Apache-2.0 (tool parsers); `platoon@efe3b277c82c:pyproject.toml:13` |
| platoon (PyPI wheel, for CPU probes) | 0.5.0, with tinker 0.16.1, tinker-cookbook 0.3.0, torch 2.15.0+cpu | 2026-11-02 | as above |

The wheel's `platoon/` tree has no file differences from the clone (`diff -rq`), so probe results apply to this commit. RFC status lines and `docs/architecture.md` lag the code (see "Brief check").

Research report for Milestone 0. Labels: **IMPLEMENTED** (code on the default branch), **DOCUMENTED-ONLY**, **DRAFT/RFC** (proposal, no code), **EXPERIMENTAL** (shipped, labelled unstable). Tiers: **stable** (`platoon`, `platoon.gym`, `platoon.testing`), **experimental** (`platoon.experimental`), **internal** (everything else); `platoon@efe3b277c82c:scripts/public_api.py:42`.

## Findings in brief

- **Shipped:** agent tree at the gateway, `TrajectoryCollection`, `Outcome`, role-to-policy binding, env forks, `CreditEstimator` with per-token advantages (experimental), and `POST /v1/platoon/agents` (scoped child keys).
- **Not shipped:** `AgentGraph`, `Edge`, `RewardEvent`, attribution levels, `AgentHandle`/`ChildCredentials`, wait/finish/cancel, messaging, native selectors, token spans per call, token persistence. These exist only in RFCs.
- **`leave_one_out_baseline` defaults to false.** Brief section 7's formula is opt-in, used by the RAO recursive recipe.
- **Credit sees rows and tags, not trajectories,** so provenance needs a new channel. **A trace needs exactly one root.**

## 1. Surface map

| Concept | Module | Tier | Status |
|---|---|---|---|
| `AgentGraph`, `AgentRecord`, `Edge`, `RewardEvent` | none (Platoon RFC 0001 section 1) | n/a | DRAFT/RFC; no such symbol in `platoon/` or `extensions/` |
| `AgentContext`, `AgentAPI`, `AgentResult`, `ChatReply`, `ModelEndpoint`, `McpEndpoint`, `SubagentResult` | `platoon.harness.agent` | stable | IMPLEMENTED |
| `EpisodeContext`, `program`, finalizers | `platoon.programs` | stable | IMPLEMENTED |
| `ModelGateway`, `AgentSession`, `ChatResponse`, `TinkerLLMInteraction`, `ProviderRecord` | `platoon.gateway.core` | internal (reachable through `EpisodeContext.root`) | IMPLEMENTED |
| HTTP gateway and mint route | `platoon.gateway.server` | internal API, documented wire contract | IMPLEMENTED; Responses and Messages dialects EXPERIMENTAL |
| MCP tool plane | `platoon.gateway.mcp` | internal | IMPLEMENTED in part (Platoon RFC 0005 section 5); orchestrator tools not built |
| `Trajectory`, `TrajectoryCollection` | `platoon.trajectory` | stable (`TrajectoryStep`, `ParentInfo` internal) | IMPLEMENTED |
| Trace builder | `platoon.gateway.trace` | internal | IMPLEMENTED |
| Converter, `AgentTag`, `TrajectoryCollectionResult` | `platoon.utils.tinker_data_processing` | internal | IMPLEMENTED |
| `Outcome`, `EnvSession`, `EnvironmentService`, `ForkMode` | `platoon.envs.service` | stable | IMPLEMENTED |
| Reward events | none as a type; `Trajectory.reward`, `Outcome.rewards`, `reward_misc` stand in | n/a | `RewardEvent` DRAFT/RFC |
| `PolicySpec`, `AgentBindings`, `MAIN`, `PolicySnapshot`, `PolicyMoved` | `platoon.train.policy.*` | experimental | EXPERIMENTAL |
| `Policy`, `PolicySet` | `platoon.train.policy.policy`, `.set` | internal | IMPLEMENTED |
| `CreditEstimator` family | `platoon.train.credit.api` | experimental | EXPERIMENTAL |
| `RolloutWorkflow`, `RolloutOutput`, `OutputReport` | `platoon.train.workflow.protocol` | experimental | EXPERIMENTAL |
| `RolloutSource` | `platoon.train.dispatch.source` | internal (trainers get it from `run.rollouts()`) | IMPLEMENTED |

### Field lists and flow

- **`AgentContext`** (`platoon@efe3b277c82c:platoon/harness/agent.py:201`): `agent_id, trajectory_id, parent_agent_id, depth, role, task, session, instruction, max_steps, access, options, endpoint, mcp, budget, agents`; methods `chat, list_tools, call_tool, annotate, annotate_step`. `annotate_step` writes to the agent's last recorded call and raises without one (`platoon@efe3b277c82c:platoon/harness/inline.py:201`).
- **`AgentAPI`** (`platoon@efe3b277c82c:platoon/harness/agent.py:163`): `spawn(goal, *, harness, max_steps, fork, access, role="subagent", options, task_misc) -> SubagentResult`, `keep_children()`. `spawn` runs the child to completion; there is no separate wait, join or fan-out handle (`asyncio.gather` over spawns is the pattern). Children must be function harnesses; a TOML spec raises `TypeError` (`platoon@efe3b277c82c:platoon/harness/agents.py:318`).
- **`SubagentResult`** (`platoon@efe3b277c82c:platoon/harness/agent.py:119`): `agent_id, trajectory_id, goal, result, outcome, message`, with `launched`, `ok`. A rejected launch has empty ids.
- **Spawn sequence** (`platoon@efe3b277c82c:platoon/harness/agents.py:1`): reserve budget, `EnvSession.fork`, `open_subagent`, run, grade by `agents.child_grading` (`env`, `verifier`, or `none`, the default at `platoon@efe3b277c82c:platoon/train/components.py:152`), close, stamp `reward/subagent_launched` and `reward/subagent_succeeded` on the parent's spawning step.
- **`AgentSession`** (`platoon@efe3b277c82c:platoon/gateway/core.py:891`), main fields: `agent_id` (uuid4 hex), `rollout_id, trajectory_id, secret, interactions, parent_agent_id, role, policy, goal, fork_step, calls, depth, max_steps, call_kinds, tool_calls, call_cap, call_tally, policy_only, misc, step_misc, task, result, outcome, judges`. `fork_step` is `len(parent.calls)` at opening (`platoon@efe3b277c82c:platoon/gateway/core.py:1522`).
- **`TrajectoryCollection`** (`platoon@efe3b277c82c:platoon/trajectory.py:70`): `id`, `trajectories: dict[trajectory_id, Trajectory]`, root first. **`Trajectory`** (`:50`): `id, task, parent_info(id, fork_step), steps, reward: float = 0.0, finish_message, error_message, misc`. **`TrajectoryStep`**: `misc` only.
- Produced by `build_trajectory_collection` (`platoon@efe3b277c82c:platoon/gateway/trace.py:91`), then consumed by `get_train_data_for_trajectory_collection` (`platoon@efe3b277c82c:platoon/utils/tinker_data_processing.py:606`), which needs the separate `interactions` map. `to_dict()` holds no tokens (probe).
- **Trajectory misc keys:** `agent {agent_id, role, policy?}`, `model_generations`, `model_call_spans`, `outcome` (own outcome only), `agent_result`, `judge_calls`, `tool_calls`, `harness` (root), `budget`, plus `ctx.annotate` keys. **Step misc:** `action_misc {completion_id, model, usage, kind?, provider fields}`, `message`, `reward_misc`, plus `ctx.annotate_step` keys (`platoon@efe3b277c82c:platoon/gateway/trace.py:265`). `action_misc` cannot be overridden by annotations (`:280`).
- **`Outcome`** (`platoon@efe3b277c82c:platoon/envs/service.py:44`): `status` (`scored, invalid, error, timeout, cancelled`), `rewards`, `primary="reward"`, `reason`, `failure_kind`, `metadata`. Only `scored` trains. Non-scored outcomes write `reward=0.0` plus a marker in misc (`platoon@efe3b277c82c:platoon/gateway/trace.py:259`); `None` is not representable on `Trajectory.reward`.
- **Reward channels today:** root gets the episode outcome. A child with `AgentSession.outcome` uses it; otherwise it shares the episode's (`platoon@efe3b277c82c:platoon/gateway/trace.py:113`). Finalizers then mutate the collection in place. A `reward_processor` maps a trajectory dict to `(score, components)` (`platoon@efe3b277c82c:platoon/train/workers/run.py:57`); components reach estimators through `member.result.trajectory_stats[*].rewards_dict`.
- **Role and policy binding** (EXPERIMENTAL): `AgentBindings(default=MAIN, roles)` (`platoon@efe3b277c82c:platoon/train/policy/spec.py:177`), from `agents.policy` and `agents.roles.<role>.{policy, tools}` (`platoon@efe3b277c82c:platoon/train/config_defs.py:739`). The root samples the default; any other agent samples its role's policy, else the default (`platoon@efe3b277c82c:platoon/gateway/core.py:1173`). One agent, one policy for life. Frozen policies (`PolicySpec.trainable=False`) make no datums, but agents keep rewards and tags (`platoon@efe3b277c82c:platoon/utils/tinker_data_processing.py:705`). A `PolicySpec` also has `id, model_name, renderer_name, renderer_kwargs, context_window_length, sample_timeout_seconds, tinker_base_url, lora_rank, load_checkpoint_path, load_optimizer_state, optimizer, loss_fn, loss_fn_config, max_staleness, batch_size, checkpoint`. `PolicySet`: `leader`, `agents`, `trainable()`, `sampled()` (`platoon@efe3b277c82c:platoon/train/policy/set.py:27`).
- **Env forks** (IMPLEMENTED): `ForkMode = shared | copy | fresh` (`platoon@efe3b277c82c:platoon/envs/service.py:40`), `EnvSession.fork(mode, *, task)` (`:241`), implemented by table, ORS and Harbor sessions. An unsupported mode fails loudly (`platoon@efe3b277c82c:docs/architecture.md:299`). Fork mode is not recorded: `fork_mode` appears nowhere in `platoon/`.

**Credit seam** (EXPERIMENTAL), `platoon@efe3b277c82c:platoon/train/credit/api.py`:

| Type | Fields |
|---|---|
| `TrainingSample` (`:47`) | `datum, policy, member, agent_id, role, trajectory_id, depth`; `advantages`, `mask`, `set_advantage(v)`, `set_advantages(values)` |
| `AgentRun` (`:103`) | `agent_id, trajectory_id, parent_id, role, policy, depth, reward: float\|None, samples` |
| `MemberRollout` (`:124`) | `index, samples, agents, task_reward, task_reward_valid, result` |
| `PolicyView` (`:147`) | `id, renderer, tokenizer, scorer, current_version`; `version`, `score(datums)` |
| `CreditGroup` (`:185`) | `task_id, label, entry, settings, members, policies, versions, stats`; `samples()`, `agents()` |
| `CreditSetup` (`:214`) | `name, entry, settings, policies, policy_views` |
| `CreditEstimator` (`:244`) | `needs_agents`, `async assign(group)`; optional `settle(group)`, `state()`, `load_state(state)`, `assign_timeout_seconds` |

Built per entry as `Class(setup, options)`, selected by `environments[].credit` and `credit_options` (`platoon@efe3b277c82c:platoon/train/components.py:514`), by built-in name, `@credit_estimator`, or `module:Class`. Runs in the trainer process, once per group. Evaluation never runs one. A raising estimator stops the run; `ScoringFailed` fails only its group (`platoon@efe3b277c82c:platoon/train/credit/runtime.py:55`). `settle` is called as the group is filed; `state()` is checkpointed with kept groups.

## 2. Platoon RFC 0001 section 7 versus Platoon RFC 0021

Platoon RFC 0021 replaces section 7 and leaves the rest of Platoon RFC 0001 standing as draft (`platoon@efe3b277c82c:docs/rfcs/0001-native-multi-agent.md:9`, `platoon@efe3b277c82c:docs/rfcs/0021-trainers-credit-and-policies.md:1039`).

| Platoon RFC 0001 section 7 | After Platoon RFC 0021 | Status at this commit |
|---|---|---|
| `CreditPolicy.returns/advantages`, one number per agent | `CreditEstimator.assign`, async, per entry, per-token capable | EXPERIMENTAL |
| Runs inside a `GroupRolloutWorkflow` subclass | `environments[].credit`; hooks `compute_baselines`, `assign_advantages` remain, refused beside an estimator | IMPLEMENTED |
| `rao` preset | `group` (`GroupCredit`) | EXPERIMENTAL; value-for-value test below |
| `BaselineSpec` | `keyed`: `key` from `task, policy, role, depth`, plus `leave_one_out` | EXPERIMENTAL; `platoon@efe3b277c82c:platoon/train/credit/keyed.py:20` |
| `source`, `estimator: ema`, `normalize`, `exclude`, `min_peers`, `fallback`, `ordinal`, `harness` key fields | dropped from `keyed` | Not built |
| `by_role`, `hierarchical`, `rae`, `agentwise` presets | none | Not built |
| `RoleRule.policy` | `agents.roles.<role>.policy` | EXPERIMENTAL |

Per-token advantages today:

- `TrainingSample.set_advantages(values)` takes one value per target token and writes only where `mask > 0` (`platoon@efe3b277c82c:platoon/train/credit/api.py:82`).
- `reverse_kl` is the one built-in that uses it (`platoon@efe3b277c82c:platoon/train/credit/reverse_kl.py:126`). `group` and `keyed` set one value per row or agent.
- Before credit, the converter loads each action token with the trajectory's processed reward (`platoon@efe3b277c82c:platoon/utils/tinker_data_processing.py:562`).
- A row is a prefix-merged run of calls, and no call boundaries reach the estimator. Platoon RFC 0021 lists "per-call token spans" as not built (`platoon@efe3b277c82c:docs/rfcs/0021-trainers-credit-and-policies.md:1026`).
- Platoon RFC 0021's `CreditGroup.emit` and `gae` are not built; `gae` is only a reserved name (`platoon@efe3b277c82c:platoon/train/credit/registry.py:40`).

## 3. Attribution levels

**DRAFT/RFC only.** Defined at `platoon@efe3b277c82c:docs/rfcs/0001-native-multi-agent.md:39` and `:93`. The code has no `Attribution` type, no `train_attribution`, no `X-Platoon-Agent`, no `[native]` selector.

| Level (RFC) | Established by (RFC) | Trains by default (RFC) | Actual behavior at this commit |
|---|---|---|---|
| `exact` | agent has its own secret | yes | Every recorded agent. Identity is always the presented key |
| `declared` | cooperating harness labels calls on a shared secret | no | Not built; a label header is ignored |
| `inferred` | HarnessSpec `[native]` selectors | no | Not built |
| `forked` | no signal; calls branch from the parent's context | as the parent's rows | De facto behavior for native subagents on a shared key: calls stay on that agent, and a broken prefix starts a new datum |

RFC rules, unimplemented: an agent takes the weakest level of its calls; `credit.train_attribution` (default `{"exact"}`). That key cannot exist as written, because `credit` is now a selector string on the entry. A call to resolve in the amendment.

**What trains by default:** `policy` and `aux` calls of trajectories that are not interrupted, not `exclude_from_training`, not `exclude_from_policy_training`, and on a trained policy. `judge` calls and judge-role subtrees get no trajectory (`platoon@efe3b277c82c:platoon/gateway/trace.py:313`). Verifier agents get `exclude_from_training` through `mark_verifier_agent` (`platoon@efe3b277c82c:platoon/harness/verify.py:674`), which only the spawn path calls. Hosted calls have no tokens and never train (`platoon@efe3b277c82c:platoon/gateway/core.py:782`).

## 4. The RAO baseline as implemented

Code: `group_baselines` (`platoon@efe3b277c82c:platoon/train/credit/group.py:66`), `compute_baselines` and `assign_advantages` (`platoon@efe3b277c82c:platoon/train/workflow/group.py:607`, `:620`), `GroupCredit` (`platoon@efe3b277c82c:platoon/train/credit/group.py:217`). The name `R_root_local` does not appear in the code.

**Group formation.** One draw of one task row runs `group_size` members (default 8, `platoon@efe3b277c82c:platoon/train/config_defs.py:85`) concurrently; stragglers may be cancelled. `results` is the members with a non-None result, in member order (`platoon@efe3b277c82c:platoon/train/workflow/group.py:464`). A member has no result when it failed, was cut, or converted to no datum before sampling (`conversion_empty`, `platoon@efe3b277c82c:platoon/train/workers/run.py:432`). A result emptied only by sampling or policy exclusion stays and keeps its baseline vote (`:434`).

**Per-trajectory reward, in the rollout process** (`platoon@efe3b277c82c:platoon/utils/tinker_data_processing.py:671`):

1. Skip trajectories with `exclude_from_training`, or a verifier task (no stats, no tag).
2. `reward, components = reward_processor(trajectory)`. The default returns `trajectory["reward"]`.
3. `is_root`: first key of `trajectories`.
4. `policy_ineligible = interrupted or (not is_root and exclude_from_policy_training)`.
5. `task_reward` is the root's processed reward. `task_reward_valid = not trajectory_was_interrupted(root)` (`:660`).
6. Ineligible trajectories give no datums, but their reward and stats remain.

Interrupted means a cancelled, timed-out or invalid marker, or error text containing `CancelledError`, `Episode cancelled`, `Episode timed out` or `\nTimeoutError:` (`platoon@efe3b277c82c:platoon/utils/trajectory_status.py:57`).
**Pre-credit gates, in order** (`platoon@efe3b277c82c:platoon/train/workflow/group.py:526`): members trained different reward keys (`reward_key_mismatch`); no results (`no_results`); `min_successful_group_size > 1` and too few valid (`below_min`, default 1); no valid root (`no_completed_root`); no datums (`no_datums`).

**Baseline.** Let `V` be the valid members and `m = mean(R_root[l] for l in V)`:

| Case | `b[k]`, k valid | `b[k]`, k invalid |
|---|---|---|
| `leave_one_out_baseline=false` (default) | `m` | `m` |
| true, `len(V) > 1` | `(sum(V) - R_root[k]) / (len(V) - 1)` | `m` |
| true, `len(V) == 1` | `R_root[k]` | `m` (the one valid reward) |
| `len(V) == 0` | `ValueError`; unreachable in the workflow, the gate stops first | same |

**Advantage.** For each row of member k, on tokens with `mask > 0`: `A = R_i[k] - b[k]`, where `R_i` is that trajectory's processed reward. Root and all children of a rollout share `b[k]`. There is no normalization and no per-agent weighting at this stage.

**After centering:**

1. `filter_error_tokens`: with `filter_errors` (default true in config), error tokens with positive advantage get mask 0 and advantage 0; datums with no action token left are dropped (`platoon@efe3b277c82c:platoon/train/credit/group.py:97`).
2. `group_verdict`: `no_datums`, `trained`, or `uniform` when all advantages are zero (`:164`).
3. Per microbatch, optional and mutually exclusive: `depth_level_weighting` multiplies by `(1/n_d) * total_tokens / sum_d(tokens_d / n_d)`; `depth_level_discount_gamma` by `gamma**depth`, renormalized (`platoon@efe3b277c82c:platoon/train/step/batch_transforms.py:128`). Both default off.
4. Zero-advantage datums are dropped, with their share of the loss denominator kept.

**Root and child.** For the root, `R_i = task_reward`, so the brief's `R_root_local = R_task` holds, after the reward processor. A child's `R_i` is one of: its env grade, its verifier's score, the shared episode reward (`child_grading: none`), 0 (`skip_subagent_reward_computation`), or the root's success (`propagate_root_success`, `platoon@efe3b277c82c:platoon/utils/subagent_rewards.py:126`). The stock processor `platoon-delegation` adds a bonus capped at 0 (`platoon@efe3b277c82c:platoon/rewards.py:23`). The RAO recursive recipe sets `leave_one_out_baseline: true`, `depth_level_weighting: true`, `child_grading: env`, `propagate_root_success: false` (`platoon@efe3b277c82c:recipes/rao/textcraft-synth/recursive.yaml:34`). **Interrupted root:** A child that has its own outcome still trains, against `m`. A child sharing the episode outcome inherits the root's marker and is excluded (`platoon@efe3b277c82c:platoon/gateway/trace.py:114`).

### Differences from brief section 7

| # | Brief | Code |
|---|---|---|
| 1 | Always leave-one-out | Group mean by default; leave-one-out is opt-in |
| 2 | `l` ranges over the G rollouts | `l` ranges over valid roots among members that returned a result |
| 3 | G > 1 only | `len(V)==1`: self-baseline, so the root gets 0 and a child gets `R_child - R_root` |
| 4 | Nothing about invalid members | Invalid members use the mean of valid roots; their root rows never train |
| 5 | Raw `R_root`, `R_i_local` | Processed rewards after finalizers and `reward_processor` |
| 6 | No group gates | Reward-key agreement and `min_successful_group_size` |
| 7 | No later steps | Error filter, verdict, optional depth transforms, zero-advantage filter |
| 8 | Silent on datum sampling | `subagent_datum_keep_probability` drops child rows with no reweighting |

### Golden fixture

Advantages are float32 (`platoon@efe3b277c82c:platoon/utils/tinker_data_processing.py:387`); compare with tolerance, or in float32 for byte parity. Run on the 0.5.0 wheel with `filter_errors` off, through `GroupRolloutWorkflow.arun_episode`:

| Scenario | Members `(root, children)` | Baselines | Row advantages in order | Verdict |
|---|---|---|---|---|
| LOO | `(1,[0]) (0) (1) (0.9 invalid,[1])` | `0.5, 1, 0.5, 2/3` | `0.5, -0.5, -1, 0.5, 1/3` | trained |
| Mean | same | `2/3` all | `1/3, -2/3, -2/3, 1/3, 1/3` | trained |
| G=1, either mode | `(0.7,[0.2])` | `0.7` | `0, -0.5` | trained |
| Singleton valid, LOO | `(1,[0]) (0.4 invalid,[1])` | `1, 1` | `0, -1, 0` | trained (upstream test) |
| No valid root | `(0.5 invalid) (0.2 invalid)` | none | none | `no_completed_root` |
| `min_successful_group_size=2` | `(1) (0 invalid)` | none | none | `below_min` |
| Uniform | `(1) (1)` | `1, 1` | `0, 0` | `uniform` |

The invalid member has no root row, so the LOO case has five rows from four members.

**Tests that pin this:** `platoon@efe3b277c82c:tests/train/credit/test_group_baselines.py:19` (table; also `:105`, `:117`, `:134`, `:144`, `:162`), `platoon@efe3b277c82c:tests/train/credit/test_credit_estimators.py:74` (`group` equals the workflow value for value), `platoon@efe3b277c82c:tests/train/workflow/test_credit_workflow.py:151`, `platoon@efe3b277c82c:tests/train/workflow/test_group_trainable_members.py:135`, `platoon@efe3b277c82c:tests/train/workflow/test_group_reward_keys.py:74`, `platoon@efe3b277c82c:tests/train/workflow/test_group_verdicts.py:396` (error filter sign), `platoon@efe3b277c82c:tests/train/step/test_depth_transforms.py`, `platoon@efe3b277c82c:tests/train/workflow/test_post_merge_datum_sampling.py`, `platoon@efe3b277c82c:tests/test_subagent_rewards.py:63`, `platoon@efe3b277c82c:recipes/rao/test_rao_recipes.py:198` (recipe settings), and scenario `depth-zero-adv` at `platoon@efe3b277c82c:tests/train/parity/trace_scenarios.py:346`.

## 5. Identity for an external harness

- **Root.** A TOML spec gets `{base_url}` and `{api_key}`; the key renders only into `[launch.env]` and `[mcp.env]` (`platoon@efe3b277c82c:platoon/harness/spec.py:87`). A function harness gets `ctx.endpoint`, whose URL is path-scoped, `.../s/<secret>/v1` (`platoon@efe3b277c82c:platoon/harness/inline.py:101`). That URL is a credential: `repr(ctx.endpoint)` hides `api_key` but prints the key inside `base_url` (critic probe), and a path-form mint reply carries the child's key the same way. `{agent_id}` is not a placeholder, and no route tells a harness its own id.
- **Per-agent secret.** `secrets.token_urlsafe(32)`, held in memory, one per agent (`platoon@efe3b277c82c:platoon/gateway/core.py:1532`). Presented as `Authorization: Bearer`, `x-api-key`, or `/s/<secret>/` (`platoon@efe3b277c82c:platoon/gateway/server.py:242`, `:497`). The server takes only its own rollout's keys. Unknown keys get 401, closed agents 410.

**Child credentials.** `platoon@efe3b277c82c:platoon/gateway/server.py:267`, IMPLEMENTED:

```http
POST {base}/v1/platoon/agents
Authorization: Bearer <parent key>

{"role": "worker", "goal": "optional"}

201 {"agent_id": "...", "api_key": "...", "base_url": "{origin}/v1"}
```

`base_url` is path-form when the parent used path form. Missing role gives 400; passing the limit gives 400 (`AgentLimitError` is a `ValueError`). Probe: a grandchild mints with its child's key at depth 2; extra fields such as `policy` are ignored without error; `POST .../agents/{id}/wait` gives 404.

What a mint does and does not do (`platoon@efe3b277c82c:platoon/gateway/core.py:1581`):

- Inherits rollout, interaction map, tool binding, access, sampling defaults, judges switch, `call_cap` with a shared tally, and `policy_only`.
- Cap: 64 per rollout, or `PLATOON_MAX_MINTED_AGENTS` (`platoon@efe3b277c82c:platoon/gateway/core.py:105`).
- No `may_spawn`, no depth limit, no idempotency, no `fork`, no status, wait, finish or cancel. These are Platoon RFC 0001 section 3, DRAFT/RFC.
- `role` is a free string, and it selects the policy and the treatment. Probe: a minted `judge` gets its calls moved to the parent's `judge_calls`, untrained. A minted `verifier` is not marked as one, so it trains.
- The minted child has `result=None` and `outcome=None`, so it shares the episode reward (probe), unless a finalizer changes it.
- It sees the parent's tool binding, in effect a `shared` fork.

**How `agent_id` reaches the gateway.** It does not. Identity is derived from the key on every request; the body and headers name no agent. The `model` field does not select a policy.

**Call to span mapping.** One HTTP request is one `call_id` (`tinker-sampling-<uuid>` observed), one `ChatResponse`, one `interactions[call_id]`, one trajectory step with `action_misc.completion_id = call_id`.

| Dialect | How the client learns `call_id` |
|---|---|
| OpenAI Chat | response `id`; chunk `id` when streaming |
| OpenAI Responses | response `id` (`platoon@efe3b277c82c:platoon/gateway/dialects/responses.py:178`) |
| Anthropic Messages | message `id` (`platoon@efe3b277c82c:platoon/gateway/dialects/anthropic.py:186`) |
| Non-streaming, any | also header `x-platoon-call-id` (`platoon@efe3b277c82c:platoon/gateway/server.py:344`); absent on streams (probe) |

The "span" is the call's whole sampled sequence; nothing subdivides it. After prefix merging, the boundary is lost from the datum. Native tool ids sit in `message.tool_calls`. MCP tool records carry `event_id, name, arguments, text, is_error, finished, reward, after_call_id, started_at, ended_at` (`platoon@efe3b277c82c:platoon/gateway/mcp.py:134`), where `after_call_id` is the agent's last call when the tool started, with no `tool_call_id` link. Native tools are not recorded.

**What the gateway records:**

| Data | Where | Notes |
|---|---|---|
| Prompt token ids | `ChatResponse.prompt`, `TinkerLLMInteraction.obs` | Exact rendered `ModelInput`; in memory only |
| Sampled token ids, logprobs | `ChatResponse.tokens, logprobs`, `interaction.action` | A client sees token text and logprobs with `logprobs: true`, never ids |
| Routing handle, policy, version | `routing_id, policy, version` | Absent from step `action_misc` |
| Assistant message | `ChatResponse.message()`, step `message` | `content, reasoning_content, tool_calls` |
| Diagnostics | `stop_reason, parse_success, tool call counts`, `CallTiming` | In `model_generations`, `model_call_spans` |
| Kind | `call_kinds` | `policy`, `aux`, `judge`; header `X-Platoon-Call-Kind` |
| Hosted call | `ProviderRecord`, no tokens | Observable, not trainable |
| **Request messages and tools** | **Not recorded** | Only recoverable by decoding `obs` |

Tokens are never written to disk; the rollout's event file is built from the collection (`platoon@efe3b277c82c:platoon/train/workers/run.py:173`). Platoon RFC 0007's sidecar and Platoon RFC 0005's TITO are DRAFT/RFC.

## 6. Seams for an external execution system

Ranked narrowest first.

| Seam | Tier | What platoon-harness provides | What it gets | Limits |
|---|---|---|---|---|
| **A. TOML `HarnessSpec`** | documented data format, `platoon.harnesses` entry point | A spec launching `platoon-harness run` with env-provided URL and key; a final-message source | Exact calls, children by mint, MCP tools, grading | Runs no program, so no finalizers (`platoon@efe3b277c82c:platoon/train/components.py:1153`); children share the episode reward; no annotations; `spawn` cannot target it |
| **B. Function harness plus program** (recommended) | stable | `@pt.harness` running the SDK in the worker's event loop; `@pt.program` with a finalizer | All of A, plus `annotate`, per-agent rewards in finalizers, `ctx.agents.spawn` with forks | Runs in the rollout worker; `EpisodeContext.run` runs function harnesses only |
| **C. Reward processor** | entry point `platoon.reward_processors` | `(score, components)` from a trajectory dict | Local and team numbers to estimators via `rewards_dict` | Numbers only; must be importable under process isolation |
| **D. `CreditEstimator`** | experimental | `assign`, optional `settle`, `state`, `load_state` | Replaceable credit, per-token | Sees rows, tags, `trajectory_stats`; no misc |
| **E. Custom `rollout:`** | config key (`platoon@efe3b277c82c:platoon/train/components.py:458`) | `async (Task, RolloutConfig) -> dict` | Own session lifecycle | Interactions must land in `proxy_interactions` (internal) |
| **F. Custom `RolloutWorkflow`** | experimental | `arun_episode(row) -> RolloutOutput \| Sequence[Datum] \| None` | Bypasses group credit entirely | Must build `tinker.Datum`s from real samples; `make_output` from Platoon RFC 0021 is not built |
| **`RolloutSource`** | internal | Nothing: it is the consumer | | Not a seam for us |

**Harness kinds:** exactly two, `FunctionHarness` (`platoon@efe3b277c82c:platoon/harness/function.py:41`) and `HarnessSpec` (`platoon@efe3b277c82c:platoon/harness/spec.py:396`). The `platoon harness` CLI group only lists and shows them.

**`TrajectoryCollection` builders:** `build_trajectory_collection` needs live `AgentSession`s and is internal. There is no public constructor from external records. A `TrajectoryCollection` alone cannot train; trainable data is the collection plus `interactions`, and interactions only come from real sampling through the gateway.
**To be driven by Platoon, platoon-harness must:**

1. Take identities from Platoon: mint per agent, and hand each adapter that `base_url` and key.
2. Route every trainable model call through that endpoint in a supported dialect.
3. Keep native subagents on a shared key labelled, never split.
4. Return `AgentResult` with honest status. Children's reward and eligibility are set in a finalizer.
5. Keep one root.

**CPU testing without Tinker** (needs `platoon[tinker]`, not a backend; the `ors` extra was not needed for a plain `EnvironmentService`):

| Tool | Module | Probe result |
|---|---|---|
| `run_episode`, `ScriptedPolicy`, `EpisodeRun` | `platoon.testing` (stable) | Ran TOML local harness and function harness end to end |
| `make_gateway`, `serve_policy`, toy tokenizer and renderer | `platoon.testing` (stable) | Real gateway, including HTTP mint |
| `check_credit_estimator` | `platoon.testing` (changes with API) | `group`, `keyed`, and a `settle`-based prior-baseline stub pass in seconds |
| `check_trainer`, `fake_tinker_service`, `FakePolicyService` | `platoon.testing` (changes with API) | `check_trainer(PlatoonTinkerRLTrainer)` passes in about 2 s; it takes a class, not a name |

Probe: a root with zero model calls and two minted peers is valid (`steps=0`, `task_reward_valid=True`, two rows), so a synthetic coordinator root works.

## 7. Gaps needing a small RFC amendment

| # | Gap | Evidence | Smallest amendment |
|---|---|---|---|
| G1 | Minted child cannot report end, status or reward | No route; `result=None` | Platoon RFC 0001 M2 subset: `POST /v1/platoon/agents/{id}/finish` with status and message; or a documented finalizer contract |
| G2 | Mint has no policy over `role`, depth or retries | Section 5 | `agents.roles.<role>.may_mint`, `max_depth` check, `request_id` idempotency |
| G3 | No attribution or purpose on records | Section 3 | `AgentSession.attribution`, `harness`, `purpose` in `misc.agent`; a converter filter with default `{exact}`; settle the config key name |
| G4 | No call spans in rows | Platoon RFC 0021 section 18 | `TrajectoryCollectionResult.datum_calls` and `TrainingSample.calls`: `(call_id, start, end, version)` per merged call |
| G5 | Provenance cannot reach credit | Worker returns `result` only (`platoon@efe3b277c82c:platoon/train/workers/run.py:338`); `draw_provenance` false for `rl` | Bounded `AgentTag.annotations`, or a per-rollout content reference on the result |
| G6 | One scalar reward per agent, no `None` on `Trajectory` | `platoon@efe3b277c82c:platoon/trajectory.py:60` | `AgentRun.rewards: Mapping[str, float \| None]` from `misc.outcome`; `RewardEvent` as Platoon RFC 0001 M1 subset |
| G7 | Exactly one root; single parent | `platoon@efe3b277c82c:platoon/gateway/trace.py:338` | Keep for now with a synthetic root; propose a rollout-level team outcome and non-tree edges later |
| G8 | Black-box harness cannot mark a call | `annotate_step` is function-only and last-call-only; `aux` trains | Header `X-Platoon-Exclude-From-Training: <reason>`, or step annotation by `call_id` |
| G9 | Harness cannot learn its own `agent_id` | No placeholder or route | `{agent_id}` placeholder and `GET /v1/platoon/agents/self` |
| G10 | Fork mode unrecorded; black-box has no fork | `fork_mode` absent | Record in `misc.agent`; `fork` on mint where the env supports it |
| G11 | Per-step policy version missing from step misc | `platoon@efe3b277c82c:platoon/gateway/trace.py:265` | Add `policy` and `version` to `action_misc` |
| G12 | Request messages not recorded | `ChatResponse` has no messages | Optional request digest per call, for exposure evidence |

G1, G3, G4 and G5 block the brief's token-level and graph-based credit. The others have workarounds in seam B.

## Implications for platoon-harness

1. **Ship the bridge as an optional extension**, exposing `platoon.harnesses`, `platoon.programs` and `platoon.reward_processors` entry points; estimators are named `module:Class` because no credit entry-point group exists. Pin `platoon>=0.5,<0.6`.
2. **Use seam B as the primary trainable path; keep seam A as a documented lesser mode** with a capability row saying per-agent rewards are unavailable.
3. **Define an identity provider in the SDK:** standalone mode issues its own run-scoped identities; Platoon-managed mode calls mint. Never fabricate a key or `agent_id`, and never log a key.
4. **Journal correlation:** store `harness_agent_id`, gateway `agent_id`, `trajectory_id` and `call_id` for each model call. Read `call_id` from the dialect's response id. Tokens stay in Platoon; the SDK never holds them.
5. **Keep attribution in our own versioned enum**, documented as tracking a Platoon draft. Only agents with their own key are `exact`. Native subagents on a shared key stay on the parent, labelled `forked` or `inferred`, and are not exported as separate training agents.
6. **Gate eligibility in the export,** then let Platoon decide. Humans and judges must never hold a trainable key: use role `judge` or a separate hosted route. Do not rely on role strings for authorization.
7. **Model missing rewards as `None` in our events;** convert to Platoon markers only in the bridge finalizer. Avoid the `error_message` substrings listed in section 4.
8. **RAO golden:** keep a dependency-free table test from section 4, plus an optional compatibility test against `platoon.train.credit.group.group_baselines` and `GroupRolloutWorkflow`. Name the mode (mean or LOO) explicitly in the fixture.
9. **No-extra-rollout baseline:** implement as a `CreditEstimator` with `needs_agents=True`, reading frozen state in `assign` and updating only in `settle`, with `group_size: 1`. A stub of this shape passes `check_credit_estimator`.
10. **Local and team rewards:** carry them in trajectory misc from the finalizer, then through a reward processor into `rewards_dict`.
11. **Decentralized teams:** use a synthetic coordinator root that owns the team outcome; document that it is a mapping artifact, not a privileged agent.
12. **Provenance:** keep it in our journal. Until G5 lands, a graph-based estimator joins on `trajectory_id` or `agent_id` to an out-of-band export; state that this is a workaround.
13. **Budget and limits:** treat the gateway budget stop (an assistant message with no tool calls) as an end-of-run signal in adapters. Set `PLATOON_MAX_MINTED_AGENTS` deliberately; the default of 64 is below the brief's 100-agent scale case.
14. **Coordination tools stay in our MCP server.** The gateway's `/mcp` serves env tools. Forward an env's tools rather than replacing them.
15. **CI:** put Platoon compatibility tests in an optional job with `platoon[tinker]`, using `run_episode`, `ScriptedPolicy` and a tiny `EnvironmentService`.

## Taste notes

- **Elegant:** one gateway implementation with thin dialect translators; the agent is the unit of identity, and the key is the only credential.
- **Elegant:** fail-closed outcomes. A verifier in flight writes a pending ineligible judgment first; infrastructure failures are never a score.
- **Elegant:** `settle` as the single place stateful credit may change, which makes resume exact. This is worth copying as a pattern for our rebuildable views.
- **Elegant:** public surface enforced by a checked snapshot (`tests/public_api.txt`), plus conformance kits with named checks.
- **Elegant:** `platoon.testing` swaps only the sampler, so tests run real code paths.
- **Avoid:** stringly typed protocols in `misc` (`reward_misc`, `reward/*`, markers). Our events should be typed, with namespaced extensions.
- **Avoid:** untrainable state encoded as `0.0` plus a flag, and detection by error-message substrings.
- **Avoid:** identity semantics hidden in role strings (`judge`, `verifier`). Purpose and role should be separate fields.

## Brief check

`AgentGraph`, reward events and attribution levels are draft only, which the brief allows for; no integration can target them. Section 7's formula is opt-in, not the default. Platoon RFC 0021's header says "Implementation: None yet" (`platoon@efe3b277c82c:docs/rfcs/0021-trainers-credit-and-policies.md:10`), and `docs/architecture.md` says multi-policy training is not built and treats credit as subclass-only (`platoon@efe3b277c82c:docs/architecture.md:858`). Code and tests show otherwise; trust the code.

## Unknowns and risks

- Experimental APIs (`credit`, `workflow`, `agents:`) may change in a minor release. Internal `platoon.gateway` types may change at any time.
- Not tested: mint through a sandbox route or Unix socket. `base_url` comes from `request.url.origin()`, whose value behind a route is unverified.
- Not tested: running the SDK's event loop work inside a rollout worker under `rollout_isolation: process`; the 2 s `check_trainer` probe used fakes only.
- Not tested: real Codex or Claude Code against experimental dialects in this report; the adapter reports cover that.
- `AgentGraph` may land with a different shape; the upstream RFC says it waits for "the first per-step credit user", which this project may be.
- Stateful estimators: `assign` calls overlap and `CreditGroup` carries no step number, so "frozen prior batch" needs care. Groups in flight see the state as of their `assign`, and `settle` order is filing order.
- Prefix merging interacts with harness compaction: a broken prefix starts a new datum, which raises token cost and changes row counts per agent.
- Platoon classifiers list POSIX Linux only. macOS support for the training extension is unverified, which does not affect the SDK.
- Clean-room: no external platoon-harness implementation was searched for or opened; mentions of "platoon harness" here are Platoon's own CLI group and package.
