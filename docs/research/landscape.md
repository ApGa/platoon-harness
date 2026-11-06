# Landscape

Which existing projects are like ours? Reviewed on 2026-11-03.

Four sweeps each covered one category: tools that run and coordinate existing coding-agent CLIs, multi-agent frameworks, durable
runtimes and agent-to-agent protocols, and training in harnesses. A verifier per category reopened every candidate the sweep ranked
close, and corrected it. A final critic then tried to refute that no project combines what ours does, through more searches and a
directory of about 60 orchestrators, https://github.com/bradAGI/awesome-cli-coding-agents, and added seven projects. Everything was
read from READMEs, LICENSE files, docs and the GitHub API, and the review's records keep what each read found. No project was run,
and no code was copied.

## Inspected

The projects this page leans on. The rest of the field is in its own section. Dates are the latest release, or the last push where
a project has none, as read on 2026-11-03.

| Project | URL | Latest | Date | License |
|---|---|---|---|---|
| NTM | https://github.com/Dicklesworthstone/ntm | v1.38.0 | 2026-10-31 | MIT with an OpenAI/Anthropic rider |
| Gas Town | https://github.com/gastownhall/gastown | v1.2.1; pushed 2026-10-28 | 2026-06-06 | MIT |
| Beads | https://github.com/gastownhall/beads | v1.3.2 | 2026-10-24 | MIT |
| Overstory | https://github.com/jayminwest/overstory | v0.11.0; archived, last push 2026-05-28 | 2026-05-02 | MIT |
| Oh My Subagents | https://github.com/ringlochid/oh-my-subagents | v0.3.2 | 2026-08-30 | MIT; `console/` under a Sustainable Use License |
| Omnigent | https://github.com/omnigent-ai/omnigent | v0.20.0, alpha | 2026-10-28 | Apache-2.0 |
| CLI Agent Orchestrator | https://github.com/awslabs/cli-agent-orchestrator | v2.5.3 | 2026-10-08 | Apache-2.0 |
| Docker Agent | https://github.com/docker/docker-agent | v1.156.2 | 2026-11-02 | Apache-2.0 |
| Claw Orchestrator | https://github.com/Enderfga/claw-orchestrator | v7.17.0 | 2026-11-02 | MIT |
| verifiers, prime-rl | https://github.com/PrimeIntellect-ai/verifiers, https://github.com/PrimeIntellect-ai/prime-rl | v0.4.0, v0.10.0 | 2026-10-12, 2026-10-13 | MIT, Apache-2.0 |
| Dressage | https://github.com/Accio-Lab/Dressage | no release; last push | 2026-08-27 | Apache-2.0 |
| ClawTeam | https://github.com/HKUDS/ClawTeam | v0.2.0 | 2026-03-23 | MIT |
| Dr. MAS | https://github.com/langfengQ/DrMAS | no release; last push | 2026-09-26 | Apache-2.0 |
| PettingLLMs | https://github.com/pettingllms-ai/PettingLLMs | no release; last push | 2026-05-15 | MIT |
| Microsoft Agent Framework | https://github.com/microsoft/agent-framework | python-1.24.0 | 2026-10-30 | MIT |
| MCP Agent Mail | https://github.com/Dicklesworthstone/mcp_agent_mail_rust | v0.3.40 | 2026-11-01 | MIT with an OpenAI/Anthropic rider |
| Multica | https://github.com/multica-ai/multica | v0.7.2 | 2026-10-30 | Apache-2.0 plus conditions |
| Agor | https://github.com/preset-io/agor | tag v0.27.0 | 2026-10-14 | BSL 1.1 |
| CCB | https://github.com/SeemSeam/claude_codex_bridge | v8.7.21 | 2026-11-02 | AGPL-3.0, custom-worded |
| LEGO-RL | https://github.com/LegoX/Lego-RL | no release; last push | 2026-10-31 | Apache-2.0 |

## Four axes

1. **Runs unmodified agent CLIs on their own logins.** Claude Code, Codex, pi and the rest, as the user installed and signed in.
2. **Configurable coordination primitives and topologies.** Inboxes, channels, queues, boards and waits, with who may reach whom
   declared, not prompted.
3. **A durable, resumable journal with provenance.** Every fact recorded once, safe to repeat, and able to say what each agent was
   shown and why an edge is believed.
4. **Training-grade capture of model calls, per agent.** Token ids and logprobs tied to the agent that sampled them.

## Verdict

The critic's verdict: as of 2026-11-03 no project combines all four, and none holds more than three strongly. The CLI orchestrators
that best cover the first three, NTM, Gas Town, Overstory, Omnigent, Oh My Subagents and Claw Orchestrator, record at most token
counts and cost, never token ids or logprobs. The trainers that run unmodified harnesses with token-level capture, verifiers,
Dressage, rLLM, LEGO-RL and NeMo Gym, have no primitives for agents to coordinate and no durable sessions, and they replace the
harness's own login with their own endpoint. Microsoft Agent Framework touches all four, partly on each.

Its caveat: one agent cannot use a closed vendor's own login and also yield token ids. So to combine the four is to support both
modes and let each agent choose, which ours does through the trainable level computed per
agent ([architecture §9.4](../architecture.md)).

## The closest ten

The critic's ranking.

| # | Project | Shares | Lacks |
|---|---|---|---|
| 1 | NTM | Unmodified CLIs on their own logins, mailboxes and broadcast, leased file reservations, assignment from a dependency graph, checkpoints, and resumable pipelines whose uncertain handoffs an operator settles | Training capture, topology grants, and turn-level evidence in an operation journal. Source-available with a rider |
| 2 | Gas Town | Many CLIs on their own logins in fixed roles, mailboxes, convoys, molecules with checkpoint recovery, a bisecting merge queue, a TUI and a web dashboard | Grants, general primitives such as barriers and fenced leases, an operation journal with idempotency, and token ids: its telemetry has per-session counts only |
| 3 | Overstory | 11 runtimes behind one adapter interface, typed SQLite mail with broadcast groups, a merge queue, checkpoints and replay | Training and grants. Archived |
| 4 | Oh My Subagents | Codex app-server and Claude on their own identities, a per-dispatch MCP binding with an exact tool ceiling, and a fan-out whose children commit together with the parent's wait | Peer messaging, queues and leases, any topology but a tree, training, and harnesses beyond two |
| 5 | Omnigent | Claude Code, Codex, Cursor, OpenCode, Hermes and Pi on subscriptions, injected tools for child dispatch and peer messages, policies and budgets, and server-side sessions | Journal and idempotency semantics, distributed primitives, grants and token capture |
| 6 | CLI Agent Orchestrator | 12 CLIs on native auth, an injected MCP server with supervisor and worker tools, and persistent SQLite inboxes delivered only at idle | A journal or resume model, topologies and training |
| 7 | Docker Agent | Claude Code, Codex, OpenCode and pi on native logins, and per-agent `sub_agents` and handoff targets in YAML, the nearest thing to our grants among CLI drivers | Coordination by its harness agents, whose toolsets are ignored; crash recovery; a journal; training |
| 8 | Claw Orchestrator | Native CLIs as persistent sessions, a checkpointed run kernel that survives its own death, a per-turn ledger of model, tokens and cost, and MCP and ACP surfaces | Primitives for agents to coordinate, grants, token ids or logprobs, and provenance |
| 9 | verifiers and prime-rl | Unmodified Claude Code and Codex as named roles in one episode, per-role traces with trainable flags, and harness capability flags that refuse what a harness cannot honor | Native logins, agents messaging each other, and durable sessions |
| 10 | Dressage | Black-box Claude Code, Codex, OpenCode and OpenClaw with token ids, logprobs and token versions, parent and child lineage across subagents, and idempotent turns | A team runtime, coordination, native logins, and a CLI, TUI or viewer |

## What remains only ours

As far as these sweeps reached:

- **Topology as grants** over relations, compiled to one table and checked on every operation. Docker Agent's per-agent handoff
  targets come nearest, and its harness agents cannot use them.
- **One operation journal** with idempotency keys and provenance: what each agent was shown, what it claimed to rely on, and what is
  unknown. Idempotency and operator-settled uncertainty appear only in NTM, Claw Orchestrator, Oh My Subagents and the durable
  execution engines, and provenance beyond logs and ancestry nowhere among the orchestrators but Agor's origin block on a prompt.
- **Exact calls tied to a coordination record.** rLLM's gateway, Amazon Turnstile and AgentCore RL Toolkit capture token ids from
  unmodified harnesses, but none ties a call to a team member's identity or to what that member was shown, so per-agent credit
  and exposure still come from us and Platoon. The multi-agent credit methods, MrlX, PettingLLMs, MARTI, Dr. MAS and Kimi PARL, all
  run their own agent loops.

## Ideas worth borrowing

Each in our own words and code.

| Idea | After | Where it lands |
|---|---|---|
| Context rotation: a fresh native session for an agent whose context is spent, keeping its identity, leases and waits, with an uncertain handoff left for a person | NTM, ideas only | M2, in §7 Lifecycle with no new noun: a compaction the runtime begins at a turn boundary on the path that starts a harness anew. An uncertain handoff is already `effect.uncertain` |
| A merge-queue role: workers hand branches to one merger rather than merging themselves | Gas Town's bisecting Refinery, Overstory's merge queue | Worktree teams, as a `merges` queue and a merger role written out in [topologies.md](../how-to/topologies.md), not a preset. Not `git-swarm`: GitSwarm never merges, and integrates by synthesis commits. Batch bisection stays out until someone asks |
| Task dependencies that unblock themselves | ClawTeam's `--blocked-by`, Beads' `bd ready` | M4, as a library pattern in `platoon_harness.patterns` that waits on the prerequisites and then adds their dependents, on public ops only |
| A scheduled live check of each new harness release: the flags a driver passes against the binary's `--help`, and one live turn | Claw Orchestrator's weekly sweep | M4, as a scheduled `live` job with a stated budget that runs `check_driver` on each new `claude`, `codex` and `pi`. Results already pin to driver and harness version |
| Lineage attribution of a harness's own subagent calls, by parent session and prefix | Dressage | Platoon at M3, through `child.seen` and `call.joined`, recorded as `inferred` with its evidence and never as `exact` |
| Advantages normalized per agent rather than globally | Dr. MAS; PettingLLMs groups by agent and turn | Platoon's trainer at M3. We already give it per-agent identity and rewards scoped `local` or `team` |

## License warnings

- **NTM and MCP Agent Mail** carry a rider that grants no rights to OpenAI, Anthropic, their affiliates or anyone acting for them,
  and count analyzing or indexing the software, and its use in ML datasets, evaluation harnesses or pipelines, as use. Neither is OSI open source.
  Ideas only, and never a dependency.
- **Agor** is under the Business Source License 1.1.
- **Multica** is Apache-2.0 with conditions: a hosted service or an embedded commercial component needs a commercial license.
- **claude-squad and CCB** are AGPL-3.0. Ideas only, like Toad.

## Permissions bypassed

Some orchestrators launch harnesses with their approvals switched off. OpenAgents runs Claude Code with
`--dangerously-skip-permissions` outside plan mode and Codex with `--dangerously-bypass-approvals-and-sandbox`, and Docker Agent runs
Claude Code non-interactively with `--dangerously-skip-permissions`, where a harness's own tool events skip its approval hooks. Our
rule is the opposite: one launch path per harness, and every approval through the runtime ([architecture §9.5](../architecture.md)).

## The rest of the field

One line each. Projects only a sweep read, with no verifier after it, are marked unverified, though the metadata check covered
their repositories.

**Running existing CLIs.**
- [ClawTeam](https://github.com/HKUDS/ClawTeam), MIT: a leader spawns teammates in worktrees and tmux, with file inboxes and a task board. No journal.
- [hcom](https://github.com/aannoo/hcom), MIT: hooks let 14 CLIs message, watch, fork and resume each other, mid-turn or at idle.
- [Paperclip](https://github.com/paperclipai/paperclip), MIT: an org chart of agents woken on heartbeats, with tickets, atomic checkout and budgets.
- [CCB](https://github.com/SeemSeam/claude_codex_bridge), AGPL-3.0: visible panes with ask and back delegation; a send with an unknown outcome is held, not replayed.
- [Scion](https://github.com/GoogleCloudPlatform/scion), Apache-2.0, preview: harnesses in containers behind a hub that records ancestry.
- [MCP Agent Mail](https://github.com/Dicklesworthstone/mcp_agent_mail_rust), MIT with a rider: inboxes, acknowledgements and advisory file leases over MCP. It launches nothing.
- [zeroshot](https://github.com/the-open-engine/zeroshot), MIT: a fixed graph of workers and reviewers over a durable ledger, where "model output cannot add an edge or raise a bound".
- [Multica](https://github.com/multica-ai/multica), Apache-2.0 plus conditions: issues and mentions route work to 26 CLIs, and a squad wakes only its leader.
- [Agor](https://github.com/preset-io/agor), BSL 1.1: shared boards of agent sessions on branches, driven through an MCP server.
- Unverified: [MassGen](https://github.com/massgen/MassGen) (parallel answers and a vote), [agent-orchestrator](https://github.com/OrchestratorInc/agent-orchestrator) (task to merged PR), [Ruflo](https://github.com/ruvnet/ruflo) (self-reported swarm toolkit), and GitHub Agent HQ (hosted, one vendor).
- Seen by the critic and not added: Traycer, fractal, Kiro Crew, Google AX, swarm-tools, multi-agent-shogun, Vibe Kanban, OpenAI Symphony, Emdash and claude-squad. coder/agentapi is archived.

**Frameworks that own the loop.**
- [Microsoft Agent Framework](https://github.com/microsoft/agent-framework), MIT: graph workflows with checkpoints, preview Claude Agent SDK and Copilot SDK connectors, and an experimental Agent Lightning bridge.
- [Agno](https://github.com/agno-agi/agno), Apache-2.0: Claude Code and Codex as team members since 2026-10-27, each keeping its native session, under an LLM leader.
- [Mastra](https://github.com/mastra-ai/mastra), Apache-2.0 outside `ee/`: ACP agents and vendor SDK agents as long-lived subagents of a supervisor.
- [AG2 Network](https://github.com/ag2ai/ag2), Apache-2.0: a write-ahead log per channel and one arbiter before every send, nearest our kernel in design, over its own agents and with no idempotency keys.
- [AgentScope](https://github.com/agentscope-ai/agentscope), Apache-2.0: leader and worker teams; its RL tuner lives on the 1.x branch only.
- [Strands](https://github.com/strands-agents/harness-sdk), Apache-2.0: swarm, graph and workflow patterns, a repetitive-handoff detector that is off by default, and community token-level rollouts.
- [Deep Agents](https://github.com/langchain-ai/deepagents), MIT: remote subagents that take follow-ups, behind five verbs on one task id.
- Unverified: [OpenRath](https://github.com/Rath-Team/OpenRath), [PydanticAI](https://github.com/pydantic/pydantic-ai), [LangGraph](https://github.com/langchain-ai/langgraph), [Agency Swarm](https://github.com/VRSEN/agency-swarm), [CAMEL](https://github.com/camel-ai/camel), [Swarms](https://github.com/kyegomez/swarms), [Google ADK](https://github.com/google/adk-python) and [CrewAI](https://github.com/crewAIInc/crewAI).

**Durable runtimes and protocols.**
- [OpenAgents](https://github.com/openagents-org/openagents), Apache-2.0: headless Claude Code and Codex with an injected MCP server and a native session per channel, the same shape as ours, with approvals bypassed.
- [Agent Relay](https://github.com/AgentWorkforce/relay), Apache-2.0: channels and direct messages between spawned CLIs, delivered at the next idle boundary or at once, and acknowledged after injection.
- [kagent](https://github.com/kagent-dev/kagent), Apache-2.0, alpha: Claude and Codex harnesses on API keys behind A2A on Kubernetes, with idle sessions suspended to snapshots.
- [Rivet Sandbox Agent](https://github.com/rivet-dev/agents), Apache-2.0: one HTTP API over six coding agents that picks up host logins, and no coordination.
- [Vercel AI SDK harnesses](https://ai-sdk.dev/docs/ai-sdk-harnesses/overview), Apache-2.0, experimental: one harness per agent, durable through workflow steps.
- [Dapr Agents](https://github.com/dapr/dapr-agents), Apache-2.0: durable workflows over pub/sub, with one Claude Code executor whose transcript is mirrored for resume elsewhere.
- [concord-mcp](https://github.com/Get-Concord-AI/concord-mcp), MIT: five MCP tools for claims and handoffs with versions and idempotency keys. It launches nothing.
- [Cloudflare Agents](https://github.com/cloudflare/agents), MIT on a proprietary platform: pi and OpenCode loops ported into Durable Objects.
- Unverified: [Coral](https://github.com/Coral-Protocol/coral-server) (blocking waits by sender or predicate, no durability), [Letta Code](https://github.com/letta-ai/letta-code), [Temporal's AI integrations](https://temporal.io/blog/ai-framework-integrations), [Agent Framework's durable extension](https://learn.microsoft.com/en-us/agent-framework/hosting/durable-extension), [Restate](https://github.com/restatedev/restate) (BSL 1.1) and [A2A](https://a2a-protocol.org/latest/specification/).

**Training.**
- [rLLM](https://github.com/rllm-org/rllm), Apache-2.0: its own gateway records token ids and logprobs per session route, and groups advantages by task and role.
- [slime](https://github.com/THUDM/slime), Apache-2.0: Claude Code and Codex harnesses, with one rollout split into subagent and compaction samples.
- [NeMo Gym](https://github.com/NVIDIA-NeMo/Gym), Apache-2.0: many external harnesses with exact token ids across steps, and resume after preemption.
- [AReaL](https://github.com/areal-project/AReaL), Apache-2.0: an online proxy that issues each agent session its own key.
- [Agent Lightning](https://github.com/microsoft/agent-lightning), MIT: one agent at a time through a proxy, with no driver for an existing CLI.
- [Harness-RL](https://github.com/jiangxinke/Harness-RL), license unclear: black-box RL inside its own central-agent harness.
- [LEGO-RL](https://github.com/LegoX/Lego-RL), Apache-2.0: Claude Code, OpenHands and OpenCode in their own harnesses training one policy, one agent per trajectory.
- Unverified: [MrlX](https://github.com/AQ-MedAI/MrlX), [PettingLLMs](https://github.com/pettingllms-ai/PettingLLMs), [MARTI](https://github.com/TsinghuaC3I/MARTI) and [Dr. MAS](https://github.com/langfengQ/DrMAS), which credit cooperating agents in loops of their own; [OpenEnv](https://github.com/openenv/OpenEnv); [Harbor](https://github.com/harbor-framework/harbor), one agent per task, which many of these build on; and Kimi PARL, proprietary.

**Already researched here.** DeLM, Agensh, GitSwarm, Prime Agent, Pi Durable, Toad, SwarmChat, OpenHands, Codex, Claude Code,
OpenCode, pi, ACP, MCP and Platoon have reports of their own in the [index](README.md).

## Corrections the verifiers made

- Microsoft Agent Framework, AgentScope, Deep Agents, Cloudflare Agents and Agent Lightning were ranked lower, for axes they hold
  only in part.
- CCB is AGPL-3.0, and MCP Agent Mail is source-available because of its rider; both were first reported otherwise.
- Gas Town records token counts per session, not none, and still no token ids.
- Dapr Agents does drive Claude Code, and Rivet Sandbox Agent does use host logins. kagent's docs say nothing of a pinned CLI with
  streaming and resume, as first reported.
- rLLM's gateway is its own, not LiteLLM. Dressage has no Kubernetes sandbox.

## What stays unknown

- **Confirmed only by the critic and the metadata check.** NTM, Omnigent, Oh My Subagents, Claw Orchestrator, Multica, Agor and
  LEGO-RL were added by the critic after it opened each repository or docs page. No category verifier read them.
- Crash and restart semantics of Omnigent, Multica and Agor, which their pages read do not state.
- Omnigent's tie to Databricks, which a directory claims and its README does not.
- How Oh My Subagents launches Claude, beyond its operations doc saying SDK mode.
- How verifiers and prime-rl capture token ids, since a code search hit its rate limit.
- Whether Microsoft Agent Framework records token ids or assigns credit per agent.
- A project called ORCH, which the critic could not find.
- Claude Managed Agents' multi-agent preview, known only from secondary sources and so left out.
- LEGO-RL's paper, which was not opened.
- Projects marked unverified above were read once, by a sweep.

## Clean-room statement

No implementation named in the clean-room rule was searched for, surfaced or opened. No search query used those names. The work
was read-only and copied no code.
