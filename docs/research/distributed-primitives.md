# Distributed primitives and configurable topologies

## Inspected

| Project | Commit or version | Date | License |
|---|---|---|---|
| Platoon (`ApGa/platoon`) | `efe3b277c82c`, 0.5.0 | 2026-10-28 | MIT AND Apache-2.0 (parsers) |
| DeLM | `66617616e708` | 2026-10-08 | MIT |
| Agensh | `d6063b9086d5` | 2026-10-30 | MIT |
| GitSwarm project page | `9f66af0b919f` | 2026-10-09 | No license file; page only, no implementation. Pattern read from the paper, with the owner's permission |
| GitSwarm paper | arXiv:2610.04862v1 | 2026-10-04 | Paper; ideas only |
| Codex | `05c08d765523` | 2026-11-02 | Apache-2.0 |
| SwarmChat | `fb5aa6a05b40` | 2026-10-29 | MIT |
| pi | `c9f4c7b9fcd0` | 2026-11-01 | MIT |
| ACP spec | `212f0cace08a` | 2026-11-01 | Apache-2.0 |
| OpenHands SDK | `988494576218` | 2026-11-01 | MIT |
| Claude Code, LangGraph, AutoGen, AG2, CrewAI, OpenAI Agents SDK, ADK docs | Web, current pages | retrieved 2026-11-02 | Docs only |

Status labels: IMPLEMENTED, DOCUMENTED-ONLY, DRAFT/RFC, EXPERIMENTAL. `[K]` marks a fact from the author's knowledge that was not re-fetched this session; every `[K]` is a classic result, not a current API claim. All web sources were retrieved 2026-11-02.

## Bottom line

- **Four nouns, one verb, one policy.** Role, Relation, Group, Channel; `wait`; and the `delivery` ladder. Presets are macros that expand to these, so users can read and edit the result.
- **A topology is a set of grants over relations, not a graph of agents.** `worker: [parent, children]` stays true as agents spawn. Nothing rewrites config at runtime.
- **One authorization function** decides every verb, in the same transaction as the event it permits. Tools and UI are projections of the same table. A topology has no control flow.
- **Storage is two things:** an append-only log with cursors (mailbox, topic, queue) and a versioned object store (board). "Stream" is a topic with `history: full`, not a separate kind.
- **What LLMs change most:** a wakeup is expensive and a blocked call is impossible. So delivery strength is an explicit ladder, `wait` ends the turn instead of blocking, leases renew from observed liveness, and payloads are gist plus reference.
- **Collectives are library code** over core operations, with no private API. `reduce` makes no algebraic assumption, because an LLM reducer is neither associative nor deterministic.

## 1. Primitive families

Each row gives what we borrow, what LLM participants change, and the verdict: **core**, **lib** (composition) or **out**.

| Family | Semantics worth borrowing | Change for LLM agents | Verdict |
|---|---|---|---|
| MPI communicators, groups, tags [K] ([MPI 4.1](https://www.mpi-forum.org/docs/mpi-4.1/mpi41-report/mpi41-report.htm)) | A communicator scopes messages, so a library cannot collide with app traffic. A `tag` selects within it | Membership is not fixed at init. Scope is a group rule plus a **generation**. `MPI_Comm_spawn` returns an intercommunicator linking parents and children; our `parent`/`children` relations are that link | Group, generation: core |
| MPI collectives [K] | Vocabulary and contract of bcast, scatter, gather, allgather, reduce, barrier | Every member must arrive in MPI; a dead rank hangs or aborts. Here every collective needs `timeout`, partial results and a recorded member list. Reduce ops are not associative. allgather is N prompts of N inputs, so it is usually wrong; prefer a board | Compositions: lib. Broadcast (needs atomic snapshot): core |
| CSP / Go channels [K] (spec fetch failed twice; see Unknowns) | Bounded capacity, rendezvous, `select` over several sources | Rendezvous would hold an LLM turn open and is rejected. Keep bounds as backpressure. `select` becomes `wait(any_of=[...])`, which is server-evaluated | `wait` any-of: core. Rendezvous: out |
| Erlang processes ([signals](https://www.erlang.org/doc/system/ref_man_processes.html)) | "If an entity sends multiple signals to the same destination entity, the order is preserved"; nothing stronger. Monitors deliver `DOWN`, and links propagate exit | Keep per-pair honesty. Monitor is the default parent-child return link. Links are `on_parent_exit` policy. "Let it crash" is costly: a restart loses context and pays again, so restart is a role policy with a budget, never automatic | Monitor: core. Supervisor: lib |
| Akka ([delivery](https://doc.akka.io/libraries/akka-core/current/general/message-delivery-reliability.html)) | Default at-most-once; pair ordering "is not transitive"; `/deadLetters` | We need at-least-once to the driver, since a lost message wastes dollars of work. Dead letters become a receipt to the sender, which is data rather than a debug aid | Undeliverable receipt: core |
| Linda tuple space [K] (Gelernter 1985), blackboard | Space-uncoupled sharing; `out`/`rd`/`in`; writers need not know readers | Exactly DeLM's and Agensh's success story. Pattern matching becomes structured `query`. Destructive `in` is replaced by leased `claim` | Board: core. Tuple matching: out |
| Kafka / Redis Streams | Log plus per-group offset; Redis pending list, `XAUTOCLAIM`, delivery count, [at-least-once](https://redis.io/docs/latest/develop/data-types/streams/) | Kafka's `max.poll.interval.ms` default of [5 minutes](https://docs.confluent.io/platform/current/installation/configuration/consumer-configs.html) treats a slow consumer as failed. LLM turns exceed that, so liveness must come from harness events. Replay is **not** free: re-delivering 1,000 entries is a prompt-size event | Log, cursors: core |
| NATS JetStream | Pull consumer, explicit ack, [`MaxAckPending`](https://docs.nats.io/nats-concepts/jetstream/consumers) default 1000 as a flow limit; ack variants [K] | For agents the in-flight limit is 1 or a few. A "working on it" ack is worth keeping, sent by the runtime not the model | Inflight cap: core |
| SQS ([visibility timeout](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-visibility-timeout.html)) | Invisible while leased; default 30 s, max 12 h; heartbeat extension; DLQ; at-least-once even inside the window | Default lease is tens of minutes. Heartbeat by LLM call is absurd, so the runtime renews while the harness shows activity. DLQ becomes a `dead` task state shown to a human | Queue: core |
| Leases, fencing ([Kleppmann](https://martin.kleppmann.com/2016/02/08/how-to-do-distributed-locking.html), Chubby [K], ZooKeeper) | A paused holder cannot know its lease expired, so "you need to include a fencing token with every write request to the storage service". The storage side checks | An LLM turn is a very long GC pause, so this is the common case. Our journal is the store and checks the fence. External effects (a push, a paid API) cannot be fenced by us; say so | Fence on every claim-bound write: core |
| Barriers ([ZooKeeper recipes](https://zookeeper.apache.org/doc/current/recipes.html)) | Double barrier; ephemeral nodes keep failed processes from blocking; "each node is watched by exactly one client" avoids the herd | Waiters are parked, costing nothing until release. Release wakes N agents, a herd in dollars, so coalesce and stagger. Failure policy is required: `shrink`, `break` or `wait` | Lib, over `wait` |
| Vector clocks, happens-before [K] (Lamport 1978; Fidge, Mattern 1988) | Causality is a partial order; wall clock is not evidence | Single-writer journal gives a total `seq`, so we need no clocks on the wire. What provenance needs is the **exposure vector**: per turn, `{channel: cursor}` shown to the agent. That is a version vector, recorded as deltas | Exposure vector: core. Vector clocks: out |
| MapReduce [K], [Pregel via LangGraph](https://docs.langchain.com/oss/python/langgraph/graph-api) | Split, independent map, group, reduce; re-execute failed tasks. Pregel halts when "no nodes are active and no messages are in transit" | Re-execution is not idempotent or cheap. Reducer is an LLM with a prompt limit, hence tree reduce with bounded fan-in and an explicit `missing` list. Pregel's halt rule is our quiescence rule | Lib. Quiescence: core |
| Gossip [K] (Demers 1987) | Epidemic spread, no central node | We have a central journal, so gossip as transport buys nothing. As a *research topology* it is just a sampled topic reader set | Out of core; extension filter |
| 2PC [K] | Atomic commit across participants; blocks on coordinator failure | An LLM cannot hold a prepare lock over hours, or be relied on to vote deterministically. Atomicity lives in one SQLite transaction; everything external is a saga-like state | Out |
| Sagas [K] (Garcia-Molina, Salem 1987) | Forward steps with compensations | Compensation for `git push` or a sent email is agent work, not a rollback. Useful recipe; do not promise it | Lib, later |
| Temporal ([messages](https://docs.temporal.io/encyclopedia/workflow-message-passing)) | Queries read and never enter history; Signals are fire-and-forget writes; Updates are tracked writes with validation and an accepted result | The split maps cleanly: read view / `send` / `request` with reply. Durable timers are `wait(deadline)`. Deterministic replay is out: replay must not re-execute tools (brief section 12) | Vocabulary, timers: core. Replay: out |
| Ray ([actors](https://docs.ray.io/en/latest/ray-core/actors.html)), Dask [K] | Actor methods "execute serially in the order you call them"; restarts opt-in. Dask `as_completed`, leased semaphores | An agent is an actor with one turn at a time. Object store maps to content references. `as_completed` is the right shape for `wait_any` | Content refs: core. Rest: lib |

## 2. What LLM participants change

**Injection boundary is per harness and there are three, not one.** No path interrupts a response being generated.

| Path | Boundary | Evidence |
|---|---|---|
| Claude Code stream-json | Next tool boundary, else next turn; `shouldQuery: false` appends with no model call | Sibling report `adapter-claude-code.md`, section on delivery boundaries |
| Codex app-server | `turn/steer` with `expected_turn_id`. Inter-agent mail has `trigger_turn`; non-triggering mail waits for the next turn "without sampling again" | `codex@05c08d765523:codex-rs/app-server-protocol/src/protocol/common.rs:1098`, `codex@05c08d765523:codex-rs/app-server-protocol/src/protocol/v2/turn.rs:348`, `codex@05c08d765523:codex-rs/protocol/src/protocol.rs:976`, `codex@05c08d765523:codex-rs/core/src/session/input_queue.rs:356` |
| pi RPC | "Steering messages enter after the current assistant turn. Follow-up messages enter after the agent has finished its pending work" | `pi@c9f4c7b9fcd0:packages/coding-agent/docs/how-pi-works.md:13`, `pi@c9f4c7b9fcd0:packages/coding-agent/src/modes/rpc/rpc-client.ts:211` |
| ACP v1 | Turn-scoped prompt; queued messages are an open question. v2 prompt lifecycle is DRAFT/RFC | `acp-spec@212f0cace08a:docs/rfds/v2/prompt.mdx:23`, `acp-spec@212f0cace08a:docs/rfds/v2/prompt.mdx:43` |
| Our own MCP result piggyback | Any harness: append pending notices to the result of a coordination tool, then report them shown. Agensh does this by wrapping infrastructure MCP servers; it acknowledges only after emitting ("failures can redeliver") | `Agensh@d6063b9086d5:mini-router/mcp_notice_shim.cjs:3`, `Agensh@d6063b9086d5:mini-router/mcp_notice_shim.cjs:213` |

- **A wake has a real price.** Multi-agent use is about 15x chat tokens ([Anthropic](https://www.anthropic.com/engineering/built-multi-agent-research-system)). Claude Code teammate prompt cache holds [five minutes by default](https://code.claude.com/docs/en/agent-teams), so a parked agent woken after that pays a cold prompt. Inference: frequent trivial wakes are the worst pattern; so are spread-out wakes past the TTL. Coalesce.
- **Who may wake whom is a resource grant.** Codex puts `trigger_turn` on the message, the sender's choice. DeLM decides on the reader's side: `WAKE_KINDS` excludes status updates, so "a status never does" wake (`DeLM@66617616e708:board/shared_context.py:33`). Prefer the DeLM side: config decides, a sender cannot buy a wake.
- **Agents cannot block.** A held tool call has a harness cap. DeLM caps waits at 25 s because the harness cuts a call at about 31 s (`DeLM@66617616e708:board/shared_context.py:30`). Long waits must end the turn and resume later. "Suspend" therefore costs one cold turn.
- **Broadcast hits prompt limits.** Agensh keeps the newest 32 group messages inline and spills the rest to a JSONL file (`Agensh@d6063b9086d5:mini-router/src/group_messages.ts:37`). It caps gists at 100 characters, patch summaries at 300 (`Agensh@d6063b9086d5:board-service/README.md:19`). DeLM shows names and sizes, and peers pull bodies by id (`DeLM@66617616e708:board/shared_context.py:5`). Anthropic has subagents save outputs and pass "lightweight references". **Every entry should be gist plus optional body ref.**
- **Long leases are normal.** Agensh's claim TTL is 3600 s (`Agensh@d6063b9086d5:board-service/shared_lessons.py:23`). It is a soft note: a colliding `CLAIM` is settled by DM (`Agensh@d6063b9086d5:prompts/agents.txt:66`). DeLM's claim is atomic and owner-checked, one held item per agent, with no lease or expiry (`DeLM@66617616e708:board/shared_context.py:392`, `DeLM@66617616e708:board/shared_context.py:444`). A dead DeLM claimant holds its item forever. We need both properties.
- **Ack means committed, not sent.** Codex: "Only history commitment consumes mail" (`codex@05c08d765523:codex-rs/core/src/agent_communication.rs:2`). DeLM: a timed-out wait "serves nothing and leaves the read cursor where it was" (`DeLM@66617616e708:board/shared_context.py:526`). SwarmChat: waits start from durable positions, so nothing between two waits is lost, and access is rechecked each pass (`swarmchat@fb5aa6a05b40:swarmchat/api.py:500`, `swarmchat@fb5aa6a05b40:swarmchat/api.py:513`).
- **Membership churn is the default.** GitSwarm replaces workers continually (paper section 2.3). A broadcast is defined by its recorded snapshot. Late joiners get history only if the channel says so.
- **Conflict is the failure mode, so isolate or surface it.** Cognition's objection is that parallel actions carry conflicting implicit decisions ([post](https://cognition.com/blog/dont-build-multi-agents)). Anthropic saw duplicated searches and 50 subagents for simple queries. GitSwarm's in-flight log and DeLM's board exist to prevent duplicated work. So a topology needs a cheap "what is everyone doing" read, not more messages.

## 3. How frameworks declare topology

| System | Declaration | Status | Easy | Restrictive |
|---|---|---|---|---|
| LangGraph | `StateGraph`, `add_edge`, `add_conditional_edges`, reducers per state key, `Send` for map, Pregel super-steps ([docs](https://docs.langchain.com/oss/python/langgraph/graph-api)) | IMPLEMENTED | Precise state merge, checkpoints, `interrupt` | Graph is control flow, closed before run. Shared state only. Interrupted node re-runs from its start |
| AutoGen `SelectorGroupChat` | `selector_prompt`, `selector_func`, `candidate_func`, termination conditions ([docs](https://microsoft.github.io/autogen/stable/user-guide/agentchat-user-guide/selector-group-chat.html)) | IMPLEMENTED; repo [archived](https://github.com/microsoft/autogen), successor Microsoft Agent Framework | LLM picks next speaker in a few lines | One speaker per turn, one shared history: a central scheduler in disguise. Custom selector funcs do not serialize |
| AutoGen `GraphFlow` | `DiGraphBuilder.add_edge(a, b, condition=...)`, `activation_group`, `MessageFilterAgent` ([docs](https://microsoft.github.io/autogen/stable/user-guide/agentchat-user-guide/graph-flow.html)) | EXPERIMENTAL; archived repo | Fan-out and join with `all`/`any` | Execution order and visibility are separate systems |
| AutoGen Swarm | `handoffs=[...]`; next speaker from latest `HandoffMessage` ([docs](https://microsoft.github.io/autogen/stable/user-guide/agentchat-user-guide/swarm.html)) | IMPLEMENTED | Handoff list is a permission list | One active agent; no concurrency |
| AG2 | Patterns `AutoPattern`, `RoundRobinPattern`, `RandomPattern`, `ManualPattern`, context variables ([docs](https://docs.ag2.ai/latest/docs/user-guide/advanced-concepts/orchestration/group-chat/introduction/)) | IMPLEMENTED | Named patterns are discoverable | Patterns select a speaker, not a channel |
| CrewAI | `Process.sequential`, `Process.hierarchical` ([docs](https://docs.crewai.com/en/concepts/processes)); Flows `@listen`, `@router`, `and_`, `or_` ([docs](https://docs.crewai.com/en/concepts/flows)); `agents.yaml`, `tasks.yaml` | IMPLEMENTED; consensual process absent from the docs page | Readable role config | Two topology systems; escaping the abstraction is hard (secondary sources) |
| OpenAI Agents SDK | `handoffs=[...]`, `transfer_to_<agent>` tools, `input_filter`, `Agent.as_tool` ([docs](https://openai.github.io/openai-agents-python/handoffs/)) | IMPLEMENTED | Topology visible as tools; control transfer vs tool call is explicit | Stays in one run; a single thread of control |
| Google ADK | Overview lists graph, dynamic, collaborative, template workflows, and experimental routing ([docs](https://adk.dev/workflows/)). `sub_agents`, `transfer_to_agent`, `AgentTool`, `output_key` from secondary sources | IMPLEMENTED per overview; details unverified | Sequential/Parallel/Loop composition | Tree-shaped hierarchy (secondary); shared-state key collisions in parallel branches |
| MetaGPT | Role `_watch` on action types; filter `cause_by in watch or name in send_to` ([role.py](https://github.com/geekan/MetaGPT/blob/main/metagpt/roles/role.py)) | IMPLEMENTED, via source and a blog; docs host unreachable | Pub/sub by what produced a message: subscribe to a kind of event, not a person | In-process; versions differ |
| Claude Code teams | Natural language; no project team file; lead, teammates, mailbox, task list; "any teammate can message any other"; "send one message per recipient" ([docs](https://code.claude.com/docs/en/agent-teams)) | EXPERIMENTAL; not in `-p` | Zero config; hooks gate task events | Fixed lead, no nesting, one team, no way to restrict edges |
| Codex MAv2 | `spawn_agent`, `send_message`, `followup_task`, `wait_agent`, `list_agents` (`codex@05c08d765523:codex-rs/core/src/tools/spec_plan.rs:770`); agent paths; board tools | `multi_agent_v2` stage Stable, default off; `agent_message_board` UnderDevelopment (`codex@05c08d765523:codex-rs/features/src/lib.rs:1601`, `codex@05c08d765523:codex-rs/features/src/lib.rs:1643`) | Backend-computed permissions: "Effective board actions for the authenticated caller, not an ACL definition" (`codex@05c08d765523:codex-rs/message-board/src/permissions.rs:11`) | Tree of threads; `max_depth` ignored by V2 (`codex@05c08d765523:codex-rs/config/src/config_toml.rs:775`) |
| Agensh | Fixed: one task channel, DMs, board, Gitea; identity from a supplied id on a private network (`Agensh@d6063b9086d5:board-service/README.md:41`) | IMPLEMENTED | 1,024 agents with almost no structure (README claim; not reproduced) | Topology is prompts plus compose files; no declared edges; router and shim per worker |
| DeLM | Fixed n=2 or 4 peers; board and queue | IMPLEMENTED | Very small: about 640 lines for board core | Not a framework |
| GitSwarm | Fixed: population, shared repo, no roles (paper section 2) | Paper; no code available | Stigmergy: coordination by artifacts alone | Fixed shape |
| Platoon | Tree. `may_spawn`, `bus`, `max_depth` DRAFT/RFC (`platoon@efe3b277c82c:docs/rfcs/0001-native-multi-agent.md:166`); minting has only `role`, `goal` and a cap of 64 (`platoon@efe3b277c82c:platoon/gateway/core.py:105`) | Mint IMPLEMENTED; rest DRAFT | Role names as policy binding | "Only trees exist" (`platoon@efe3b277c82c:docs/rfcs/0001-native-multi-agent.md:26`) |

**What people like or hate.** Direct evidence is thin: a search found vendor-grade comparisons, no forum corpus. They cite LangGraph's learning curve, and CrewAI's abstractions getting in the way of custom orchestration. The inferences below are mine, drawn from the table:

- Liked: named patterns; a list of who you may talk to next to the agent; handoffs shown as tools.
- Disliked: control flow encoded in config; a central speaker selector hiding as a "team"; two parallel systems (process and flow, order and filter); config that cannot express the dynamic case, forcing a rewrite in Python.
- Of the systems surveyed, none combines concurrent agents, dynamic membership and server-enforced edges. Each has at most two. This is the gap to fill.

## 4. Design proposal

### 4.1 Concepts

| Concept | Meaning | Lineage |
|---|---|---|
| **Role** | Template: harness, model, tools, workspace, `may_spawn`, limits | Platoon `RoleRule` (name kept) |
| **Relation** | Selector evaluated on the live graph against the actor: `self parent children siblings ancestors descendants next prev`, `human`, `program`, `all`, a role name, `group:x` | Zanzibar relation tuples ([paper](https://www.usenix.org/conference/atc19/presentation/pang)) |
| **Group** | Named membership rule plus a generation that increments on every change | MPI communicator |
| **Channel** | Durable named carrier. `kind` plus `writers`, `readers`, `delivery`; kind-specific fields | Kafka, SQS, tuple space |
| **`wait`** | The only suspend primitive; a declarative condition evaluated by the server | `select`, Temporal timers |
| **`delivery`** | Per-channel ladder: `pull` < `next-turn` < `wake` < `steer` | New; `steer` degrades visibly per driver |

Presets are macros over these. Every agent has an implicit mailbox; `edges` is sugar for writer grants on mailboxes, so there is one grant table.

### 4.2 Channel kinds and guarantees

| Kind | Writers get | Readers get | Default delivery | Ordering | Delivery guarantee and ack | Backpressure |
|---|---|---|---|---|---|---|
| `mailbox` (implicit) | `send`, `request` | `read_messages`, `reply`, `ack` | `wake` | Total per mailbox | At-least-once to the driver, dedupe by event id; cursor moves when injection is confirmed | Depth cap; over cap returns a receipt, never silent drop |
| `topic` | `publish` | `read`, `ack`, `watch` | `next-turn` | Total per channel | Per-reader cursor; each post records group, generation, member ids | Writer never blocks on a slow reader; reader gets gap notice plus spill ref |
| `queue` | `enqueue` | `claim`, `release`, `complete` | `pull` | FIFO for unclaimed items only | One live lease, monotonic fence; execution is at-least-once | `max_inflight` per reader, default 1 |
| `board` | `post`, `revise` | `get`, `query`, `watch` | `pull` | Per-object version order | Immutable versions; `expected_version` required; change feed is a topic | Payload caps; query pagination |

- **Global.** Order is promised per channel only, like Erlang pairs and Akka, so storage can shard later. `history: from-join | full` selects a late joiner's start. Humans have separate cursors, and UI views move none.
- **Entry shape.** `gist` (capped, inline), optional `body_ref`, `correlation_id`, `causation`, `based_on`, and a `fence` for claim-bound writes. Digests show gists; exposure of a gist is recorded separately from exposure of a body.
- **Delivery states.** `offered`, `delivered` (injection confirmed by the driver; this is the observed exposure level), `acked` (explicit agent action). None means understood.
- **Digest.** `digest: {items: 32, bytes: 16k, overflow: spill | summarize}`. `summarize` spends budget and records exposure of the summary, not of the sources.
- **`coalesce: 30s`** merges wakes into one turn.

### 4.3 `wait`

`wait(all_of|any_of=[...], after=cursor, deadline=...)` over `message(channel)`, `count(correlation_id, n)`, `agent(ids, finished)`, `task(state)`, `board(key, version>=n)`, `group_changed`.

- Registered atomically against the journal with `after`, so the read-then-subscribe race cannot occur.
- **Parks by default:** the tool returns "parked, end your turn", the driver sees turn end, and the runtime starts a turn when the condition holds, with the delivery attached.
- **`hold: 20s`** keeps the call open for short waits, capped below the driver's declared tool timeout, then falls back to parking.
- **One-shot workers** cannot park. The capability is reported, and `wait` is refused with a reason or the worker finishes and a successor is spawned (Unknowns).
- The server tracks a wait-for graph, so quiescence and cycles are detected, not guessed. Pregel's rule becomes an event `run.quiescent`. Central journal makes this cheap, so no Dijkstra-Scholten [K] is needed.

### 4.4 Grammar

```text
topology:
  use:      [ <preset> | {<preset>: {params}} ]   # macros, union of results
  groups:   {<name>: {roles: [...]} | {members: [...]} | {order: [...]}}
  channels: {<name>: {kind: topic|queue|board, writers: <sel>, readers: <sel>, delivery: ..., ...}}
  edges:    {<role|all>: [<relation>...]}         # who may send to whose mailbox; default none
  limits:   {max_depth: n, max_children: n, max_live: n}
  program:  <registered episode program>          # optional control flow, Python, not topology
  completion: root | program | quiescent          # all stop at budget exhaustion
```

Rules: default deny. `use` is a union, so order does not matter. There is no `deny`, because it would make mixing non-commutative. Two sources defining one channel differently is a load error, not a merge. Anything a preset can do, the user can write out. `platoon-harness topology show --resolved` prints the expansion, and the resolved form is what the manifest stores and hashes. YAML is shown; the schema is one Pydantic model, so TOML and Python load identically.

```python
from platoon_harness import Topology, patterns as p
from platoon_harness.topology import tree, blackboard, topic

team = (Topology()
        .use(tree("agent", max_depth=6, max_children=4), blackboard("agent", board="notes"))
        .channel("alerts", topic(writers="human", readers="all", delivery="steer"))
        .edges(agent=["parent", "children", "human"]))
```

### 4.5 Preset expansions

| Preset | Edges | Channels | Other |
|---|---|---|---|
| `manager-worker` | manager: children, human; worker: parent | queue, board | `completion: root` |
| `tree` | role: parent, children | none | Limits required; `on_parent_exit: cancel-subtree` |
| `mesh` | role: `group:peers`, human | `general` topic, optional board | `quiescent`; orphans adopted by the run |
| `star` / hub-and-spoke | spokes: hub; hub: spokes | Optional hub topic | Hub routes; spokes are not siblings |
| `blackboard` | none | board, queue | Stigmergy; DeLM-shaped |
| `pipeline` | none | One queue per stage | `max_hops` required if `back: true` |
| `ring` | none | `pipeline` with wrap | `laps` bound |
| `map-reduce` | none | `map`, `reduce` queues, `results` board | Attaches `map_reduce` program |
| `git-swarm` | none | See 4.6 | Attaches `population`, `readout` programs |

### 4.6 Worked examples

Each block is the short form followed by what it resolves to. The resolved form is valid input.

**Manager-worker with shared board.** Workers cannot talk to each other. Claiming is competitive, so the lead need not assign.
```yaml
roles:
  lead:   {harness: claude-code, may_spawn: [worker]}
  worker: {harness: codex, workspace: worktree}
topology:
  use: [{manager-worker: {manager: lead, workers: worker, queue: tasks, board: notes}}]
  limits: {max_children: 8}
# resolves to
  edges: {lead: [children, human], worker: [parent]}
  channels:
    tasks: {kind: queue, writers: lead, readers: worker, lease: 30m, max_attempts: 3}
    notes: {kind: board, writers: all, readers: all}
  completion: root
```

**Recursive tree (RAO).** `spawn` installs a monitor, so `finish(result)` arrives in the parent's mailbox with `wake`. The parent calls `wait(agent(children, finished))`, which is `join`.
```yaml
roles: {agent: {harness: openhands, may_spawn: [agent]}}
topology:
  use: [{tree: {role: agent, max_depth: 6, max_children: 4}}]
# resolves to
  edges: {agent: [parent, children]}
  limits: {max_depth: 6, max_children: 4}
  completion: root
```

**Full mesh of peers (DAO).** Group fan-out does not wake anyone by default, which keeps wake cost linear. DMs wake. Any peer may spawn within `max_live`.
```yaml
roles: {peer: {harness: opencode, may_spawn: [peer]}}
topology:
  use: [{mesh: {role: peer, board: notes}}]
  limits: {max_live: 16}
# resolves to
  groups: {peers: {roles: [peer]}}
  edges: {peer: ["group:peers", human]}
  channels:
    general: {kind: topic, writers: "group:peers", readers: "group:peers", delivery: next-turn,
              history: from-join, digest: {items: 32, overflow: spill}}
    notes:   {kind: board, writers: "group:peers", readers: "group:peers"}
  completion: quiescent
```

**Review chain.** Queues, not named successors, so a stage can have several instances. Verifier independence is enforced: there is no edge or shared channel from author to verifier except the chain. `max_hops` is a TTL on an item, which bounds review loops. `delivery: wake` on a queue announces available work; it does not assign it. `ring` is the same with `wrap`.
```yaml
roles:
  author:   {harness: codex}
  reviewer: {harness: claude-code, tools: read-only}
  verifier: {harness: opencode, tools: read-only}
topology:
  use: [{pipeline: {stages: [author, reviewer, verifier], back: true, max_hops: 6}}]
# resolves to
  edges: {}
  channels:
    to-reviewer: {kind: queue, writers: author, readers: reviewer, delivery: wake, max_hops: 6}
    to-verifier: {kind: queue, writers: reviewer, readers: verifier, delivery: wake, max_hops: 6}
    to-author:   {kind: queue, writers: [reviewer, verifier], readers: author, delivery: wake, max_hops: 6}
```

**Map-reduce with LLM reducer.** All control flow is the program. Mappers cannot read each other's results; reducers read them.
```yaml
roles:
  mapper:  {harness: codex}
  reducer: {harness: claude-code}
topology:
  use: [{map-reduce: {map: mapper, reduce: reducer, parallel: 16}}]
# resolves to
  channels:
    map:     {kind: queue, writers: program, readers: mapper, lease: 1h, max_attempts: 2}
    reduce:  {kind: queue, writers: program, readers: reducer, lease: 1h}
    results: {kind: board, writers: [mapper, reducer], readers: [reducer, program]}
  program: map_reduce
  completion: program
```

```python
tasks = await p.scatter(run, "map", shards)
maps  = await p.gather(run, tasks, min_ok=0.9, timeout="2h")  # Gathered(ok, missing, generation)
final = await p.reduce(run, maps.ok, queue="reduce", fanin=8)  # tree of LLM reductions
```

`fanin` is a prompt-size bound. Every reduction lists `based_on` versions and `missing` partitions. Grouping is recorded, since results depend on it.

**Git swarm.** No messaging at all; coordination is through artifacts. `contributions` announces commits; Git holds them. `informed_by` is required by schema and is a declared dependency, not causation (paper section 2.2). Ending as `contributed`, `nominated` or `abstained` follows the paper; abstaining does not consume budget. Readout is a plurality tally run by the program. The paper says a "consensus needs to form", but its mechanism is harness plurality with deterministic tie-breaking (section 2.5), so this needs no consensus algorithm.
```yaml
roles: {worker: {harness: codex, workspace: worktree}}
topology:
  use: [{git-swarm: {role: worker, live: 8, episodes: 64}}]
# resolves to
  edges: {}
  channels:
    contributions: {kind: topic, writers: worker, readers: all, delivery: pull, history: full,
                    schema: commit, requires: [informed_by], validate: task_publication}
    inflight:      {kind: board, writers: all, readers: all, keys: author}
    nominations:   {kind: topic, writers: worker, readers: all, delivery: pull, history: full}
  program: {population: {role: worker, live: 8, episodes: 64, uncharged: [abstained]}, readout: plurality}
  completion: program
```

### 4.7 One resolved config, three projections

| Config | Enforcement (server) | Tools shown | UI |
|---|---|---|---|
| `edges` | `send` checks grant from caller's authenticated role against the target's relations | `send(to, gist, body_ref?)`, `peers()`; absent if the role has no edges | DMs; team view draws reachable pairs |
| `channels` | Verb and selector check on write and on read (recheck as SwarmChat does) | Verbs by kind, only for held grants | topic: channel; board: board view; queue: tasks view |
| `groups` | Membership from the live graph; generation in every broadcast event | Addressed as `group:x` | Sidebar section; member changes shown |
| `may_spawn`, `limits` | Atomic admission with budget reservation; depth from the parent record, never from arguments | `spawn(role, goal)` only if `may_spawn` is non-empty | Tree in team view; refusal reason |
| `delivery` | Driver-negotiated injection; `steer` degrades to `wake` when unsupported | Not shown; preamble says when messages arrive | Unread and "queued until turn end" badges |
| `wait` | Parked state with its condition | `wait(...)` | "Why waiting: barrier r1, 3 of 4, missing w7" |

- **Authorization.** `authorize(actor, verb, object)` runs against compiled topology plus a live graph rebuilt from the journal, inside the transaction that appends the event. Actor comes from the session credential; no model-supplied argument can name it. Codex states the same rule: "Tool arguments and MCP metadata cannot change the bound board or caller. Tool selection does not grant access" (`codex@05c08d765523:codex-rs/message-board-mcp/README.md:27`). Prompts are never the boundary.
- **Refusal.** A deterministic tool error with `{code: not_permitted, verb, object, reachable: [...]}` plus an `authz.denied` event. [Platoon RFC 0001](https://github.com/ApGa/platoon/blob/efe3b277c82c/docs/rfcs/0001-native-multi-agent.md) also wants refusals as deterministic tool errors (`platoon@efe3b277c82c:docs/rfcs/0001-native-multi-agent.md:272`). Policy-caused refusal stays separate from infrastructure failure.
- **Tools versus targets.** The tool *set* is fixed by role at launch, since live tool-list updates vary by harness. Valid *targets* change, so `peers()` and the turn preamble list them, and tool schemas do not enumerate them.
- **Static check.** `platoon-harness topology check` runs before launch: error on recursive `may_spawn` without `max_depth`, or a cyclic pipeline without `max_hops`. Warn on a role nobody can reach, on a role with no path to anyone, and on `wake` topics whose worst-case wakes per post exceed a threshold.

### 4.8 Core, library, out

| Tier | Contents |
|---|---|
| **Core** (protocol and transaction) | Roles, relation evaluation, groups and generations. Mailbox and topic log with cursors, broadcast snapshot. Queue with lease, fence, retries, dead state. Board with versions and CAS. `wait` and timers. Lifecycle with monitors. `authorize`, budgets. Exposure vector, quiescence |
| **Library** (public API only; namespaced events; same usable by extensions) | `scatter`, `gather`, `reduce`, `allgather`, `barrier`, `latch`, `semaphore` and `lock` (tokens in a queue, which gives lease and fence free), `request`, `vote`/`tally`, `verifier_generator`, `supervisor`, `population`, `map_reduce`, all presets |
| **Out** | Consensus, leader election (use a role, or one token in a queue), 2PC, vector clocks on the wire, rendezvous channels, tuple pattern matching, MPI datatypes and all-to-all variants, deterministic workflow replay, mid-generation interrupt, exactly-once claims |

Test for the library tier: if a preset or collective needs a private call, the core is missing something. An extension must pass the same test (brief section 11).

Barrier sketch: `arrive` publishes to `barrier/<id>/<generation>`; `wait(count_distinct >= snapshot)`, with `on_failure: shrink | break | wait` driven by monitor events. Generation is taken at creation; a member joining later does not join that barrier.

### 4.9 Runtime evolution

- **Spawn adds members.** Rules re-evaluate; `group.changed{generation, added, removed}` is journaled. Retiring removes from the live graph, never from history.
- **Attenuation.** `create_channel` is a grant. A creator may name only readers and writers within its own reach. A child never holds more than `may_spawn` allows. So agents can self-organize Slack-style without escalating.
- **Patches.** `topology.patched{rev, diff, actor}` comes from a human or program principal, unless a role is granted `rewire`. Every event carries `topology_rev`. Queued deliveries to a removed reader become receipts to the sender.
- **Dead targets.** Sending to a finished agent yields `undeliverable`, unless the role sets `revive: true` and the driver can resume.

### 4.10 Platoon-managed mode

Topology config stays ours in both modes. The effective rule is the **intersection** of our topology and Platoon's authority, and Platoon's refusal wins.

| Operation | Authorizes | Executes | Records | Reconciles |
|---|---|---|---|---|
| Spawn | Topology check, then Platoon | Platoon: function `spawn` or `POST /v1/platoon/agents` | Journal, requested then completed with Platoon `agent_id` | Group membership updates only on Platoon success |
| Identity | Platoon | Platoon mints per-agent key | Journal stores Platoon ids | No competing id; ours are aliases at most |
| Messaging, channels | Ours | Ours (Platoon `bus` is DRAFT/RFC) | Journal | If `bus` ships, adapter; do not run two |
| Budgets | Platoon for model calls; ours for wakes and queues | Both | Journal mirrors | Platoon is authoritative |
| Env boards | Environment | Env tools | Edges via env metadata where reported | Not modelled as channels (brief section 7) |

- Gaps: minting has no policy on role or depth and caps at 64 by default. Run our check first, and propose `may_mint` and `max_depth` upstream, as `platoon-training.md` G2 already says.
- Platoon requires one root and a single parent (`platoon-training.md` G7). Mesh and Git swarm need a synthetic root at export; message edges are non-tree evidence.
- `run` maps to one rollout, so channels are scoped to it. Include `topology_hash` in exported metadata so a baseline can key on it.
- A parked agent makes no gateway calls, so waiting has no training samples. The wake prompt's injected content is recorded as exposure.

## Implications for platoon-harness

1. Build `TopologySpec` (frozen Pydantic), `compile()` and `authorize()` first. Everything in Milestone 1 calls `authorize`, even with one preset.
2. Implement in this order: mailbox, topic, board, `wait` with parking, then queue with fencing. Milestone 1 needs `manager-worker` and `mesh`; `tree` needs monitors in Milestone 2.
3. Put `delivery` in the driver contract as declared capability: `boundaries: [turn, tool, steer, piggyback]`, and report degradation in the capability matrix and UI. Coordination tool results carry pending notices for `steer` channels, which gives a tool boundary on any MCP-capable harness.
4. Auto-renew leases from harness activity events, with an absolute cap. Keep `renew` for programs, not agents by default. Bind the fence to every claim-scoped write, including publishing a commit under a claim.
5. Record the exposure vector at each injection, as deltas. It feeds the dependency DAG without new evidence types.
6. Add a `gist`/`body_ref` entry shape to the protocol now; retrofitting is expensive.
7. Ship `topology show --resolved`, `topology check`, and a team view that reads the same table. Treat presets as first-party extensions, so third-party presets have the same power.
8. Conformance tests per kind: watch race, claim race, stale fence, broadcast snapshot, quiescence, and a mixed-topology commutativity test (`use` in any order gives the same hash).
9. Use `may_spawn` and keep the role name as Platoon's policy key. Do not add a second vocabulary.

## Where upstream reality refines the brief

- "Turn boundary" is too coarse: tool boundary, steer and turn start all exist, and they differ per harness (section 2). The non-claim about mid-generation interruption holds.
- `renew` as an agent operation (brief section 5) wastes a model call to heartbeat. Keep the operation; have the runtime call it.
- "Suspend without wasting model calls" is achievable only at a turn end, and it pays a cold prompt on resume. No harness can pause mid-turn for hours through a supported path found here.
- The proposed `stream` delivery mode adds nothing over a topic with `history: full`, so it is dropped as a kind.
- A no-root mesh conflicts with Platoon's one-root, single-parent trace, and 100 managed agents exceed the default mint cap of 64. Both need upstream proposals or a synthetic root.
- GitSwarm, listed as a reference, has no public implementation in the inspected clone.

## Taste notes

- **Elegant, DeLM:** one append-only log, with queue state derived from it, in a few hundred lines. "The only way an agent learns the board is to read it." Status never wakes.
- **Elegant, Agensh:** mid-turn notices on tool results, a real answer to the injection problem with no harness patch. Avoid its identity by supplied name, and three services for the job.
- **Elegant, Codex:** "only history commitment consumes mail"; permissions computed by the backend and returned as effective actions.
- **Elegant, GitSwarm:** physical parent separate from `informed_by`; nomination records kept outside the computation graph; "report state but do not assign work".
- **Elegant, Claude Code:** a message counts as sent only when the mailbox write succeeds, and a message from another agent can never carry approval.
- **Elegant, SwarmChat:** `wait` starts from durable positions; access rechecked each pass.
- **Avoid:** control flow in YAML; an LLM speaker selector as hidden central scheduler; `deny` rules; sender-chosen wakes; a shared transcript as the bus; string names for agents in config where a relation would do.
- **Avoid:** presets that behave differently from their expansion; a preset that cannot be written out by hand is a scheduler mode.

## Unknowns and risks

- **Parking is unproven per harness.** "End your turn" is a request to the model. Needs a probe per adapter, plus a fallback when the model keeps working. Measure the cold-resume cost.
- **Live tool-result piggyback** may be lost to compaction. Delivered is recorded honestly, but later exposure is not guaranteed.
- **Auto-renew liveness** can keep a lease alive for a looping agent. Needs an absolute max like SQS's 12-hour cap, or a progress signal.
- **Wake storms.** Mesh agents that reply to each other can loop. `coalesce` and budgets bound the cost, not the loop. A hop limit from causation depth may be needed; test with fake drivers.
- **`steer` semantics differ.** pi steering enters after the assistant turn, Codex needs a matching turn id, Claude Code has priorities. One ladder may hide useful differences; the matrix must record them.
- **One-shot workers** have no mailbox after finish, and `wait` means finish-and-respawn with context loss. The design needs a concrete choice per driver.
- **Relation cost at 100+ agents.** Evaluating `descendants` per send must be O(1) or close. Requires a maintained closure in the view; benchmark.
- **Reducer quality.** `reduce` output depends on grouping; a summarizing reducer can lose minority results, and `missing` covers only absent partitions.
- **Secondary sources.** ADK `sub_agents`/`transfer_to_agent` details and MetaGPT routing are not from a primary page fetched here. Agensh scale figures are its README's claims, not reproduced. Sentiment evidence is weak.
- **Failed or partial fetches.** Go spec failed twice. `docs.metagpt.com` did not resolve. ADK deep pages returned 404 or redirects. NATS pages did not show `AckWait` or `MaxDeliver`. Kafka offset semantics were not confirmed. MPI collectives are `[K]`, with the report linked but not read.
- **GitSwarm** has no implementation to inspect, so tool semantics (`gs_inflight`, `gs_dashboard`) come from the paper only, and it has no license. Use the pattern only.
- **Clean-room.** No search result or listing surfaced any implementation named in the rule.
