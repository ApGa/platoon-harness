# Swarm patterns: DeLM, GitSwarm, Agensh, Prime Agent, RAO/DAO

> Background research, dated 2026-11-02 and not maintained: [reference/compatibility.md](../reference/compatibility.md) is current.

## Inspected

| Project | Commit or version | Date | License |
|---|---|---|---|
| DeLM | `66617616e708` (main) | 2026-10-08 | MIT |
| delm-agent-plugin | README only, via URL below | retrieved 2026-11-02 | MIT (per README) |
| GitSwarm site repo | `9f66af0b919f`, one commit | 2026-10-09 | none in repo; owner permits pattern study, no verbatim code |
| GitSwarm paper | arXiv:2610.04862v1, Appendix H prompts read in full | 2026-10-04 | PDF metadata reports CC BY 4.0 (not separately confirmed) |
| Agensh | `d6063b9086d5` | 2026-10-30 | MIT (Microsoft) |
| Prime Agent | `c6d4da9421e6` (0.10.2) | 2026-10-30 | MIT |
| Platoon | `efe3b277c82c` (0.5.0) | 2026-10-28 | MIT AND Apache-2.0 (parsers) |

**Method.** Everything below comes from reading code and docs. No upstream code was executed: a probe that ran
scratch copies of the DeLM and Agensh board classes was blocked by the session's permission policy, and it was not
worked around. "Verified" therefore means "verified by reading the code", not "observed at runtime".

Labels: IMPLEMENTED, DOCUMENTED-ONLY, DRAFT/RFC, EXPERIMENTAL. Paper citations are by section because the paper is
the only source of GitSwarm's protocol.

**The key correction.** GitSwarm's `source/` directory is the project website (`build.py`, `template.html`, `app.js`,
figure data), not the system. `app.js` is an animation; its Figure 5 is captioned "a constructed example"
(`git-swarm@9f66af0b919f:source/template.html:410`). There is no harness code to read, and arXiv links none
(https://arxiv.org/abs/2610.04862, retrieved 2026-11-02). Every GitSwarm fact here is therefore DOCUMENTED-ONLY.

## 1. DeLM

**Status: IMPLEMENTED, as a research runner.** Fixed `--n 2|4` (`DeLM@66617616e708:delm.py:36`), Docker only, one
container per worker.

| Topic | What the code does | Evidence |
|---|---|---|
| Data model | One append-only `events(sequence, time_ns, actor, kind, payload)` table. Kinds: `status, item, claim, done, note, body, session, read, wait, attached, expand, apply, apply_error, apply_result`. All state is a fold over the log | `DeLM@66617616e708:board/shared_context.py:113`, `:148` |
| Bodies | Files live in a second attached SQLite DB, written in the same transaction. Reads show only names and sizes; `expand` or `apply` pulls content | `DeLM@66617616e708:board/shared_context.py:116`, `:288` |
| Notes | `FACT` or `FAIL`, with required `text`, `scope`, `basis`. Corrections are new entries, never edits | `DeLM@66617616e708:board/shared_context.py:26`, `:454` |
| Claim | `BEGIN IMMEDIATE`, fold queue, first writer wins; a loser gets `won=false` plus the owner. One unfinished claim per actor | `DeLM@66617616e708:board/shared_context.py:130`, `:378` |
| `reserve` | Atomic create-and-claim on a normalized subject (case and whitespace folded) | `DeLM@66617616e708:board/shared_context.py:397` |
| `done` | Owner only; atomic with files; idempotent via `request_id`, where a reused ID with different content is rejected. The CLI derives the ID by hashing the payload | `DeLM@66617616e708:board/shared_context.py:430`, `:495`, `DeLM@66617616e708:board/context_client.py:129` |
| Identity | Random per-worker token in the URL path; the server maps token to actor and the body cannot override it | `DeLM@66617616e708:runtime/runner.py:298`, `DeLM@66617616e708:runtime/containers.py:27` |
| Workers | Each runs one unmodified native session in its own container with its own workspace. "Nothing is ever added to the session after the prompt"; the board is reached only through the agent's shell | `DeLM@66617616e708:runtime/native_worker.py:3` |
| Tool delivery | A shell CLI at `/tools/context.sh`; `CONTEXT_URL` and `CONTEXT_TOKEN` in env. No MCP: Claude runs with `--strict-mcp-config` and an empty server list, and the audit rejects any MCP server | `DeLM@66617616e708:runtime/runner.py:325`, `DeLM@66617616e708:runtime/claude_api.py:51`, `:174` |
| Harness launch | Via Humanize (`hmz`) at a pinned commit: Claude stream-json, Codex app-server. The upstream Claude command is validated, then extended. Native subagents are denied and a use is a run error | `DeLM@66617616e708:runtime/config.py:8`, `DeLM@66617616e708:runtime/claude_api.py:20`, `:30`, `:187` |
| Auth | API key or subscription; credential loaded from a read-only mount, never in argv; `clean_environment` strips inherited provider vars; preflight refuses inherited logins | `DeLM@66617616e708:runtime/claude_api.py:55`, `:67`, `:131` |
| Retries | No run-level retry and no overwrite. Client: transport errors are logged and raised, not retried; validation failures have a budget of 20 per target, serialized with `flock` | `DeLM@66617616e708:delm.py:90`, `:95`, `DeLM@66617616e708:board/context_client.py:27`, `:337` |
| Failure | Run `status` is `finished` or `incomplete`; failed attempts keep their workspace and records; a 600-second guard follows the model time limit | `DeLM@66617616e708:runtime/runner.py:346`, `:396` |
| Recorded | `read` events store the exact view served. Also `context-events.json`, bodies, per-worker `prompt.txt`, `trajectory.jsonl`, `native-trajectory.jsonl`, `result.json`, `runtime.json`, a framework source copy, usage audited against native totals | `DeLM@66617616e708:board/shared_context.py:232`, `DeLM@66617616e708:runtime/runner.py:307`, `DeLM@66617616e708:runtime/claude_api.py:198` |

Also noteworthy:
- `ProtectedBoard.apply` refuses the whole batch when a local file matches neither the incoming version, the original,
  nor a version registered only by the incoming author. A later publication "is not proof of a merged file"
  (`DeLM@66617616e708:board/protected_board.py:9`).
- `unattached_changes` warns about files edited but not attached (`DeLM@66617616e708:board/context_client.py:217`).
- `delm-agent-plugin` is a separate product with `/delm:run`, `/delm-status`, `/delm-stop`, run in private project
  copies with a 30-minute default (https://github.com/Decentralized-LM/delm-agent-plugin, retrieved 2026-11-02;
  README only).

## 2. Agensh

**Status: IMPLEMENTED, as a research harness on Docker Compose.** Services: Gitea (workspace), Mattermost (messages),
MySQL, board-service, secret-service, and one mini-router sidecar per worker.

| Component | What the code does | Evidence |
|---|---|---|
| board-service | FastAPI. Append-only `board_gists` in MySQL plus an in-memory recent view of at most 2,000 entries. Types `FACT, OBSERVED, FAIL, CLAIM, PATCH_SUMMARY`; caps 100 and 300 chars; long text goes in `detail` behind a `G<id>` label | `Agensh@d6063b9086d5:mini-router/sql/03_board_schema.sql:3`, `Agensh@d6063b9086d5:board-service/shared_lessons.py:14` |
| API | `POST /board/{id}/note`, `GET .../read`, `.../read_all`, `.../grep`, `.../unfold`, `POST .../lifecycle`, `GET /snapshot`, `GET /pending/{agent}`, `POST /shown/{agent}` | `Agensh@d6063b9086d5:board-service/main.py:341`, `:467`, `:652` |
| "Verification" | A deterministic text check on placeholder evidence. It does not run anything | `Agensh@d6063b9086d5:board-service/verifier.py:2` |
| `CLAIM` | A typed note with a TTL, 1 hour by default. Admission has no uniqueness check, so two agents can claim the same thing. Expiry only hides it | `Agensh@d6063b9086d5:board-service/shared_lessons.py:77`, `:92`, `:345` |
| `PATCH_SUMMARY` | Per author and `delegation_id`: replaces the older entry in the recent view; a `FAIL` with the same label invalidates it. MySQL keeps all revisions | `Agensh@d6063b9086d5:board-service/shared_lessons.py:109`, `:124` |
| mini-router | SSE and WebSocket listeners feed a per-agent MySQL `events` queue, deduplicated on `(dedup_key, agent)`; states `pending, sending, sent, failed, retrying`; backoff 1, 5, 30, 120 s, 5 attempts max | `Agensh@d6063b9086d5:mini-router/src/state.ts:20`, `:119`, `:194` |
| Dispatcher | One serialized turn at a time; prepends unread board context; acknowledges after the turn ends; nudges the agent if it published nothing | `Agensh@d6063b9086d5:mini-router/src/dispatcher.ts:81`, `:125`, `:151` |
| Mid-turn delivery | `mcp_notice_shim` wraps each MCP server and appends leased DMs and peer gists to tool results, acknowledging after emit. It also enforces the tool allowlist and reviewed description overrides | `Agensh@d6063b9086d5:mini-router/mcp_notice_shim.cjs:125`, `:149`, `:213` |
| secret-service | Small stdlib server: `GET /tokens/<agent>` guarded by `X-Internal-Auth`, name regex, path containment. Routers fetch tokens from it | `Agensh@d6063b9086d5:secret-service/main.py:17`, `:54`, `Agensh@d6063b9086d5:mini-router/src/main.ts:68` |
| Agent identity | `AGENT_NAME` env. Workers mount only their own token files. Gitea and Mattermost auth is real per-agent. Board identity is client-asserted in `thread_id` and `viewer`; the README states this | `Agensh@d6063b9086d5:tools/gen_compose_prod.py:341`, `Agensh@d6063b9086d5:board-service/mcp.cjs:132`, `Agensh@d6063b9086d5:board-service/README.md:41` |
| Harness wrapping | All harnesses are exposed as ACP over a Unix socket. Copilot native ACP; Claude via stream-json adapter with `--resume`; Codex via app-server adapter with `thread/resume`; Pi via RPC adapter. Native multi-agent is disabled | `Agensh@d6063b9086d5:agent/claude/acp.py:60`, `Agensh@d6063b9086d5:agent/claude/config.py:14`, `Agensh@d6063b9086d5:agent/codex/config.py:54`, `Agensh@d6063b9086d5:agent/acp_bridge.py:148` |
| Project instructions | Identity and rules rendered into `AGENTS.md` and copied to `CLAUDE.md` | `Agensh@d6063b9086d5:agent/entrypoint.sh:66` |
| Code integration | PR-only `main`, enforced by Gitea branch protection; a refused merge triggers merge-latest, re-check, push | `Agensh@d6063b9086d5:docker/bootstrap/bootstrap.sh:266`, `Agensh@d6063b9086d5:prompts/agents.txt:77` |

**Decentralization model.** Decision-making is peer-to-peer with no orchestrator agent, but infrastructure is central:
one board process, one MySQL, one Gitea. A runner seeds the issue, staggers kickoff DMs, posts deadline reminders, and
sends idle nudges (`Agensh@d6063b9086d5:scripts/pbench_run.sh:376`, `:539`). The roster is fixed at compose time
(`Agensh@d6063b9086d5:tools/gen_compose_prod.py:314`).

Agensh's README says its shared context is adapted from DeLM. In one respect it is weaker: DeLM's atomic claim became
an advisory note. Agensh compensates at the merge gate, and the board is not its source of truth for code.

## 3. GitSwarm

**Status: DOCUMENTED-ONLY.** Authors: Shah et al. Page: https://veds12.github.io/git-swarm/. Retrieved 2026-11-02.

| Topic | Protocol as the paper states it | Source |
|---|---|---|
| Graph | Repo root is immutable. Each contribution is one atomic commit with one physical parent | §2.2 |
| `informed_by` | Mandatory, must include the Git parent, may cross branches. Prompt: "the Git parent records physical ancestry; provenance records semantic influence" | §2.2, H.2 |
| Commit format | Subject line: `[<type>\|informed_by=<sha1>,<sha2>] <summary>`. The website figure shows a different shape, a second `-m` body line, in a constructed example | H.2; `git-swarm@9f66af0b919f:source/app.js:654` |
| Causal status | "declared by workers, not independently established as causal influence" | §2.2, §4 |
| Contribute | One validated commit, plus `MY_THOUGHTS.md` and `EVALUATION.md`. Validation checks publication rules, not correctness. Every candidate node must stand alone as a submission (for example, `compile.sh` present). Charged | §2.3, H.2, H.3 |
| Nominate | `gs_fork <sha> record-best-solution`, `gs_nominate_best_solution <sha>`, write `BEST_SOLUTION.md`, commit. The scheduler checks the tree is unchanged except that file, then publishes one immutable ballot. Ballot commits cannot receive votes or be parents. Charged | H.2 |
| Abstain | `gs_abstain --rationale "..."`, no empty commit. Replaced and uncharged, though its tokens are spent | §2.3, G.4 |
| Other exits | Invalid actions, invalid nominations, no-action exits and system failures are charged. 3.1% of charged B100 ProgramBench episodes | G.2, G.4 |
| Budget | `B` charged worker episodes. Research runs use wall-clock budgets and a shared GPU pool | §2.3, §2.4 |
| Concurrency | At most `C` workers, 5 for benchmarks, 12 to 20 for research. A replacement starts as a slot frees; workers never wait for each other | §2.3, site |
| Readout | After budget exhaustion, plurality of ballots. Ties go by lexicographic full SHA. No valid nomination falls back to the repo root. Research runs use validation score instead | §2.5, H.2 |
| Dashboard | Spawn-time snapshot in the prompt plus live `gs_dashboard`: total and remaining budget, workers in flight, nomination workers in flight, valid nominations, tally. Labelled "selection state; not correctness evidence". Research variant: GPU, CPU and job usage, a low-utilization warning, best protected score | §2.4, H.2, Figure 2 |
| In-flight view | `gs_inflight` list; `announce --stage scoping --summary "Gap \| Deliverable \| Success \| Abort" --target <sha>`; `update`; `inspect <id>`; `read <id> <path>`. Advisory: "no scheduler grants, rejects, ranks, or reserves the work" | §2.4, H.2 |
| In-flight rule | Unfinished peer content is coordination evidence, not provenance; do not depend on it unless it later appears in a committed node you cite | H.2 |
| Anti-herding | Nominators announce `--stage nominating` and must not reveal a tentative preference | H.2 |
| Launch | Codex CLI gets system, user and transport override as one input. ProgramBench Codex workers' only execution tool is a guarded MCP tool, `pb.container_bash`. Gemini workers have fenced blocks run by the harness. The harness detects the commit and ends the episode | H.1, H.2, H.4 |
| Isolation | "isolated Git worktrees and isolated environments with no internet access". Peer read-only access is stated, but how it is enforced is not | §2.3, §2.4, H.2 |
| Costs | Declared redundancy is about one in six ProgramBench workers, usually due to in-flight overlap. Abstainers use 6 to 7% of tokens | G.4 |
| Tradeoffs | Async 38.0 min vs sync waves 49.3 min, scores 62.06 vs 63.11. Central selector +2.34 pp, central aggregator -3.87 pp. Three seeds, nine dev tasks; the paper disclaims equivalence | G.6, Table 13 |

The paper's caution, which we should echo: declared dependencies, observed artifact use, and selected-solution ancestry
each differ from causal influence (§4). This matches the evidence split in brief section 6.

**Adopt as patterns**, in our own words and with credit:

1. **Separate the edges.** Keep physical parent and `informed_by` as two edge kinds. Require the parent in the declared set.
2. **Typed terminal outcomes.** Every worker episode ends in exactly one of contribute, nominate, abstain, or a
   runtime-assigned `invalid`/`failed`. Budget charging is a function of the outcome.
3. **Scope announcement.** Gap, deliverable, success, abort, published before work. Advisory, non-reserving.
4. **Publication validation** that checks structure, never correctness, and says so.
5. **Ballots separate from ancestry,** so evaluation never mutates what it evaluates. Deterministic tie-break and an
   explicit fallback outcome.
6. **Spawn-time snapshot plus live tool,** so the first read is not a wasted turn.
7. **Legible handoff artifacts** in each commit (what was checked, known gaps, next work).
8. **Negative results as first-class contributions.** 70 to 74% of negative research results were later cited (site).

**Improve on it:**

- Carry `informed_by` as a structured event as well as a Git trailer. Parsing a subject line is fragile.
- Check that cited SHAs exist, and record reads separately so declared and observed evidence can be compared.
- Uncharged abstention needs its own cap. The paper states no termination rule if every worker abstains: a spin risk.
- Enforce fork-before-write in the runtime. Pilot Gemini workers batched a whole workflow, guessed a SHA, and committed
  on the wrong branch, which forced a prompt extension and `set -e` gating (H.4).

## 4. Semantics compared with brief section 5

Prime Agent has no board. It is compared on lifecycle and messaging.

| Semantic | DeLM | Agensh | GitSwarm | Prime Agent | Brief requires |
|---|---|---|---|---|---|
| Stable IDs, immutable versions | Partial: immutable publications, no revision chain | Partial: all rows kept, recent view replaces in place | Yes: commits | n/a | Stable identity plus immutable versions |
| Update conflict | Corrections are new entries; file apply refuses batches | None on the board; Git refuses at merge | None needed: commits are immutable | n/a | Optimistic version checks |
| Query | Full or incremental view; no search | `board_grep` with booleans, true totals | Git itself | n/a | Structured queries returning versions |
| Claim atomicity | **Atomic** | **Not atomic** | None by design | None | Atomic |
| Lease, renewal, expiry | **None** | TTL on visibility only; refresh by writing again | None | None | Lease with renew, expiry, release |
| Fencing | Not needed since no reassignment; owner check only | None | n/a | n/a | Stale claimant cannot complete |
| Crash of a claimant | **Claim is stranded** | Claim hides after TTL | Slot refills; no claims | Child settles as error | Reassignment |
| Read cursor | Derived from the last served view | Durable `board_cursor` | None: workers re-read Git | `rlm.collect`, session files | Durable, acknowledged |
| Delivery guarantee | Serve-time advance, at-most-once if a response is lost; `read --all` recovers | Turn start at-most-once; mid-turn at-least-once; queue at-least-once | n/a | Receipts `delivered` or `queued` | Stated acks, retries, duplicates |
| Lost wakeups | **None by design:** waits scan the durable log from the cursor | Router has 30 s fallback polling | n/a | Unknown | None |
| Wake cost | One blocking call of at most 25 s, then a model turn | Zero: idle until an event | Zero: workers exit | Zero: a message wakes idle agents | Suspend without model calls |
| Barriers | **None** | None | None; sync waves only as an experiment | `collect(timeout_ms)`; factory joins | Scoped, with generation and failure rules |
| Membership | Fixed roster of 2 or 4 | Fixed at compose time | Dynamic episodes, one identity each | Dynamic tree | Fixed and evolving |
| Identity | Server-derived from token | Board client-asserted; Git and chat real | Unknown | Daemon-derived | Server-derived |
| Budgets | Official task limits | Wall-clock via runner | `B` and `C` | Depth and factory budgets | Atomic, shared and per-role |

Specific gaps:

| System | Gap | Evidence |
|---|---|---|
| DeLM | **Stranded claim.** Nobody can release or take over an ended worker's item: `claim` and `reserve` report the owner, `done` is owner-only. Work continues outside the queue, and `queue_empty` never becomes true | `DeLM@66617616e708:prompts/prompts_n4.py:147`, `DeLM@66617616e708:board/shared_context.py:513` |
| DeLM | **Cursor moves on serve.** The `read` event is appended before the HTTP reply is delivered, so a lost response skips updates. The prompt names the workaround, `--all` | `DeLM@66617616e708:board/shared_context.py:232`, `DeLM@66617616e708:prompts/prompts_n4.py:70` |
| DeLM | **Prompt-only boundaries.** "Never inspect credential files or /records", yet those mounts are inside the worker's container | `DeLM@66617616e708:prompts/prompts_n4.py:3`, `DeLM@66617616e708:runtime/containers.py:197` |
| DeLM | **Scale.** Every operation folds the log and each `read` stores a full view: fine for 4 agents, not for 100 agents and 100,000 events | `DeLM@66617616e708:board/shared_context.py:148`, `:232` |
| Agensh | **Duplicate claims.** Nothing rejects them; the prompt says to settle a collision by DM | `Agensh@d6063b9086d5:prompts/agents.txt:66` |
| Agensh | **Turn-start loss.** `/snapshot` advances the cursor when fetched, before the turn is delivered, so a retried prompt lacks those gists unless the agent calls `board_read` | `Agensh@d6063b9086d5:board-service/main.py:678`, `Agensh@d6063b9086d5:mini-router/src/dispatcher.ts:137` |
| Agensh | **Window eviction.** Entries past 2,000 leave the view whether or not a reader's cursor passed them; only `board_grep` finds them | `Agensh@d6063b9086d5:board-service/shared_lessons.py:143` |
| Agensh | **Repeated turns.** Acks follow the turn, so a crash replays it into a resumed session; after 5 attempts an event stays `failed` | `Agensh@d6063b9086d5:mini-router/src/state.ts:271` |
| Agensh | **Spoofable board.** `/pending/{agent}`, `viewer` and `thread_id` are unauthenticated while the prompt invites `curl`, breaking the brief's "no arbitrary caller identity" | `Agensh@d6063b9086d5:prompts/agents.txt:85` |
| Agensh | **"Verified notes".** The prompt says entries are verified; the check only inspects text | `Agensh@d6063b9086d5:prompts/agents.txt:21` |
| GitSwarm | No mutual exclusion, on purpose; duplication is the accepted price. Do not read it as a claim design | §2.4 |
| Prime | Reach is limited to parent, siblings and children, a useful example of topology as an access rule. The skill promises a rate limit, but the daemon's module note says "no per-sender rate bucket (the daemon's queue capacity bound is the enforced limit)" | `prime-agent@c6d4da9421e6:skills/agent-message/SKILL.md:8`, `:59`, `prime-agent@c6d4da9421e6:crates/pa-daemon/src/agent_message_ingest.rs:3` |

**Prime Agent features worth noting:**

| Feature | Status | Evidence |
|---|---|---|
| `rlm.spawn(prompt, name, model, thinking, cwd)` async; results arrive by message; `rlm.collect(targets, timeout_ms)` snapshots or blocks; `rlm.progress_note` throttled to about 1 per 10 s, 512 chars | IMPLEMENTED | `prime-agent@c6d4da9421e6:crates/pa-core/src/prompts/layers/core.md:33`, `:39`, `:40` |
| Depth bound, default 2 | IMPLEMENTED | `prime-agent@c6d4da9421e6:crates/pa-core/src/session_engine/rlm_host.rs:280` |
| Sender identity derived by the daemon; a message to an idle completed child starts a follow-up turn | IMPLEMENTED | `prime-agent@c6d4da9421e6:skills/agent-message/SKILL.md:34`, `:58` |
| Factory: declarative state machines with guards, joins, foreach, bounded re-entry, budgets, failure policies | EXPERIMENTAL: off until `/factory on` | `prime-agent@c6d4da9421e6:skills/factory/SKILL.md:30` |
| Factory limits: runs are lost on kernel restart; `wait` states rejected at write time | Stated in code | `prime-agent@c6d4da9421e6:prime-agent-runtime/src/rlm/factory.py:13`, `:24` |

## 5. RAO and DAO in Platoon

| Item | Status | Evidence |
|---|---|---|
| RAO: arXiv:2605.06639, "Recursive Agent Optimization" | Published paper | https://arxiv.org/abs/2605.06639 (retrieved 2026-11-02) |
| RAO recipes: linear, recursive, sparse ablation on TextCraft-Synth | IMPLEMENTED | `platoon@efe3b277c82c:recipes/rao/README.md:3` |
| Inline `ctx.agents.spawn`, budgets reserved at spawn, child cancel returns budget, a failing child never raises into the parent | IMPLEMENTED | `platoon@efe3b277c82c:platoon/harness/agents.py:1` |
| Fork modes `shared`, `copy`, `fresh`; `copy` never degrades to `shared` | IMPLEMENTED | `platoon@efe3b277c82c:docs/architecture.md:301` |
| Group baseline: only completed roots count; a singleton completed root gets zero advantage | IMPLEMENTED | `platoon@efe3b277c82c:platoon/train/credit/group.py:66` |
| `CreditEstimator` seam, `group`, `keyed` | IMPLEMENTED under a Draft RFC | `platoon@efe3b277c82c:platoon/train/credit/api.py:244` |
| `AgentGraph`, edges including `informed_by`, `RewardEvent`, `send_message`, `read_messages`, `spawn_agent`, `await_agents` | DRAFT/RFC: zero code hits for `informed_by` and no graph types | `platoon@efe3b277c82c:docs/rfcs/0001-native-multi-agent.md:36`, `:115` |
| [Platoon RFC 0001](https://github.com/ApGa/platoon/blob/efe3b277c82c/docs/rfcs/0001-native-multi-agent.md) section 7 credit | Superseded by [Platoon RFC 0021](https://github.com/ApGa/platoon/blob/efe3b277c82c/docs/rfcs/0021-trainers-credit-and-policies.md), confirming the brief's observation | `platoon@efe3b277c82c:docs/rfcs/0001-native-multi-agent.md:9` |
| Shared boards stay env tools and report `_meta.platoon.edges` | DRAFT/RFC | `platoon@efe3b277c82c:docs/rfcs/0001-native-multi-agent.md:177` |

**DAO: unknown.** A whole-word search for `DAO` across Platoon returns nothing. Three web searches found no matching
paper or definition, and the RAO abstract page mentions no decentralized variant. I will not guess an expansion. The
only available definition is the brief's own row: "Peer messaging, spawning, shared artifacts, non-tree information
flow". The nearest Platoon idea is
[Platoon RFC 0001](https://github.com/ApGa/platoon/blob/efe3b277c82c/docs/rfcs/0001-native-multi-agent.md)'s peer swarm
(`:26`, `:298`). Scenario 2 below implements the brief's row and needs nothing more. Asking the owner what DAO stands
for would resolve this.

## 6. Example scenarios for brief section 10

Rules for all six: a deterministic fake driver and controllable clock run a scripted transcript; each role names its
`driver`, so a real adapter replaces a fake with no change to example logic; assertions read the journal, not stdout;
each example prints that it demonstrates a pattern and does not reproduce the named system or its results.

| Example | Script | Assert | Not claimed |
|---|---|---|---|
| 1. RAO-style recursion | Root spawns C1, C2; C1 spawns G1; a third level exceeds `max_depth` and gets a deterministic tool error; G1, C1, C2, root finish. Repeat as 3 rollouts with root rewards `[1.0, 0.0, 0.5]` | Spawn and return events pair up. Local and team rewards stay separate. Baselines `[0.25, 0.75, 0.5]`, root advantages `[0.75, -0.75, 0.0]`. An invalid root leaves the baseline, as in `group_baselines`. Unscored is not 0 | RAO training results. The numbers are illustrative; the real golden comes from Platoon |
| 2. DAO-style team | Peers A, B, C start with no parent. A posts `spec` v1; B reads it and messages A; A revises with `expected_version=1` to v2; C's concurrent revise conflicts and rebases. B spawns D, then B is cancelled. An explicit rule ends the run | Interaction graph has an A-B cycle; version-expanded graph is acyclic. No silent overwrite. D follows the orphan policy. B's history survives | Any published DAO method (section 5) |
| 3. DeLM-style board | 4 workers, 3 items. All race for item 1; W2 wins, then stalls. The clock passes its lease; W1 reclaims with a higher fence and completes; W2 resumes and tries to complete. W3 posts `FAIL`; W4 changes plan after reading it, disconnects across a post, resumes from its cursor | One winner per race. W2's stale completion is rejected with an event. If the script's external effect ran twice, the journal shows both: exclusive ownership is not exactly-once. W4 misses nothing. Exposure events carry exact versions | Leases are ours; DeLM has none, and the README must say so |
| 4. GitSwarm-style work | Real local Git, `B=6`, `C=2`. W1, W2 contribute on separate branches; W3 forks W1 and cites W2; W4 abstains (uncharged); W5 commits invalid work (charged); W6, W7 nominate different candidates and tie. A later merge conflicts | `C` never exceeded; budget exact; `informed_by` includes the parent and every SHA exists; ballots outside ancestry; tie follows the rule; conflict surfaced, uncommitted work kept. A report shows Git ancestry, declared `informed_by`, observed reads and credit disagreeing on at least one node | Compounding benefits, scores, or that a worktree is a sandbox |
| 5. Review and verification | Author submits a change and a test. A verifier on a read-only snapshot with no write tools runs three times: pass; fail on a seeded defect, then repair; unparseable verdict. It also tries a disallowed write | Denial is server-side and recorded. Unparseable is `invalid`, not 0. Test evidence attaches to the commit. A frozen verifier's calls never become policy samples. No reward data in its context | That approval proves correctness |
| 6. Mixed human and agent team | A fake persistent driver (turn-boundary injection) and a fake one-shot driver with different capabilities. A human messages the busy agent; two clients race on one approval; one reconnects; a human edits a board object | Message queues to the next boundary. Approval resolves once; the loser sees a conflict. No duplicates after reconnect. Viewing moves no agent cursor. Human actions carry human identity. Unsupported actions show a reason | Universal mid-generation interruption |

## 7. Tool surface that works for agents

**Patterns visible in all three systems:**

| Pattern | Evidence |
|---|---|
| Few verbs: DeLM 9 actions, Agensh 4 board tools, GitSwarm about 8 commands | `DeLM@66617616e708:board/context_client.py:22`, `Agensh@d6063b9086d5:agent/config/mcp_allowed_tools.json:31` |
| Descriptions state semantics and loss cases, not just parameters: "First claim wins; a loss names the owner" | `DeLM@66617616e708:prompts/prompts_n4.py:80` |
| Explain what a parameter's misuse does: "A fresh id per note silently disables both" | `Agensh@d6063b9086d5:board-service/mcp.cjs:125` |
| Report truncation honestly: "showing 500 of 3182" means narrow terms | `Agensh@d6063b9086d5:board-service/mcp.cjs:153` |
| Rejections are actionable: `BoardError` text goes to the agent verbatim; a bad expression is "rejected rather than guessed at" | `DeLM@66617616e708:board/shared_context.py:37`, `Agensh@d6063b9086d5:board-service/mcp.cjs:149` |
| Writes return fresh incremental views, so no follow-up read | `DeLM@66617616e708:board/shared_context.py:235` |
| Unchanged items are compact because "every later call re-reads what the model was shown" | `DeLM@66617616e708:board/shared_context.py:206` |
| Type the evidence: `FACT`, `FAIL`, with `scope` and `basis` | `DeLM@66617616e708:prompts/prompts_n4.py:89` |
| Gist plus unfoldable body keeps context small | `Agensh@d6063b9086d5:board-service/mcp.cjs:100` |
| Unknown is not empty: "contents are UNKNOWN, not empty" when the board is unreachable | `Agensh@d6063b9086d5:mini-router/src/board_client.ts:41` |
| Membership as an enum in the schema, generated per agent | `Agensh@d6063b9086d5:board-service/mcp.cjs:59` |
| Warn after the fact: `changed_but_not_attached` | `DeLM@66617616e708:board/context_client.py:423` |

**Failure modes these systems warn about:**

| Failure | Their counter | Ours |
|---|---|---|
| Polling with `sleep`, or duplicate probes while idle (`DeLM@66617616e708:prompts/prompts_n4.py:157`) | Prompt rule | Runtime suspend |
| Tool cut off during a wait: about 31 s harness limit, so a 25 s cap (`DeLM@66617616e708:board/shared_context.py:28`) | Bounded call | Per-driver cap; timeout is a normal result |
| Waiting hides a response batched before it (`DeLM@66617616e708:prompts/prompts_n4.py:155`) | Prompt rule | Document it; never pair wait with writes |
| Waiting on an ended peer (`:157`) | Session states in views | Membership events wake waits |
| Paperwork: statuses, verification items, wrapper docs (`:115`, `:137`) | Prompt rules | Keep status optional |
| Treating closure as correctness (`:120`) | Prompt rule | Separate `complete` from verification |
| Publication order read as merge (`DeLM@66617616e708:board/protected_board.py:9`) | Conflict refusal | Same; version checks |
| Treating votes as evidence (GitSwarm H.2) | Label; hide preferences | Same label in tool output |
| Reading titles, not work (GitSwarm H.2) | Prompt rule | Output links to content |
| Batching a workflow on guessed IDs (GitSwarm H.4) | `set -e`, gating | Server preconditions |
| Duplicating peers' work (GitSwarm G.4; `Agensh@d6063b9086d5:prompts/agents.txt:31`) | In-flight logs, `FAIL` | Scope announcements |
| Over-coordination (`Agensh@d6063b9086d5:prompts/agents.txt:41`: use tools only when information "can greatly impact others' work") | Prompt rule | Same guidance, role-configurable |
| Assuming a 403 means lost access (`Agensh@d6063b9086d5:prompts/task_brief.txt:20`) | Prompt rule | Precise error codes |
| Silence: no publication in a turn | Forced nudge | Optional policy; off by default, since it costs a model turn |

**Proposed surface.** Names may change; identity is never a parameter, and the caller's credential decides it.

| Tool | Parameters | Result carries |
|---|---|---|
| `board_post` | `board, kind, title, body?, based_on?, idempotency_key?` | object ID, version, new changes since cursor |
| `board_get` | `object_id, version?, range?` | exact version and range served |
| `board_query` | `board, kinds?, text?, after?, limit` | matches with versions, true total, next cursor |
| `board_revise` | `object_id, expected_version, body` | new version, or a conflict with the current version |
| `task_add` | `queue, title, detail, idempotency_key?` | task ID, whether it already existed |
| `task_claim` | `queue, task_id? or next` | `won`, owner, lease expiry, fence |
| `task_renew`, `task_release` | `task_id, fence` | new expiry, or `lease_lost` |
| `task_complete` | `task_id, fence, summary, artifacts?` | completion ID, or `stale_fence` |
| `msg_send` | `to or channel, text, thread?, reply_to?, idempotency_key?` | receipt: `accepted`, `queued`, `delivered` |
| `msg_read` | `after?, channel?, limit` | messages, next cursor |
| `wait` | `for` (event, task, agent, barrier), `timeout_s` | `woke_by`, including `timeout`, plus changes |
| `agent_spawn`, `agent_status`, `agent_list` | `role, goal, idempotency_key?` | handle, or a deterministic refusal |
| `run_status` | none | budget, in flight, outcomes, gaps |
| `finish` | `outcome, summary, informed_by?` | terminal record |
| `barrier_arrive` | `barrier, generation` | released, waiting, or broken |

Style: one verb, one noun; each description ends with what a loss or refusal means and what to do next.

## Implications for platoon-harness

1. **Event-source the board on the run journal,** as DeLM does in one SQLite transaction, but with indexed projections
   so reads do not fold the log.
2. **Record exposure as content references.** DeLM's "store exactly what was served" maps directly to observed
   exposure. Store versions and hashes, not repeated bodies.
3. **Split "served" from "acknowledged".** Advance a delivery cursor on an explicit ack or the agent's next call, so a
   lost response cannot skip data. This closes the DeLM and Agensh gaps above.
4. **Claims: DeLM's atomicity plus what it lacks.** Lease, renew, runtime-clock expiry, release, a monotonic fence per
   task, reclaim. Test a stale `complete` directly.
5. **Two waiting modes, chosen by driver capability.** Persistent drivers end the turn and are woken by the runtime
   (Agensh's dispatcher, Prime's follow-up turn), costing no model calls. One-shot agents use a bounded `wait` under the
   harness's tool timeout. Record the mode in the capability matrix.
6. **Mid-turn delivery is an optional, labelled boundary.** Agensh's tool-result suffix reaches only MCP results and
   alters what the model sees, so emit an event naming the anchor call and appended content to keep traces exact.
7. **MCP and CLI over one implementation.** DeLM shows a shell CLI suffices; Agensh shows an allowlisting MCP proxy
   works across four harnesses.
8. **Identity comes from a per-agent credential checked by the service,** as in DeLM and Prime, never an asserted field.
9. **GitSwarm's protocol is an extension, not a scheduler mode:** a topology program keeps `C` live until `B` is spent,
   using `spawn`, typed outcomes and ballots. Separate charged units from spend, report abstainers' tokens, and cap
   uncharged replacements.
10. **Topology as data plus access rules.** Prime's family reach, Agensh's board membership and tool allowlists, and
    Factory's write-time validated machines point to role-level reach rules and named boards and channels. This serves
    the owner's addendum. Keep run state in the journal, unlike Factory's kernel memory.
11. **Honest words and run discipline.** "Validated" means structural unless a test ran. Copy DeLM's pinned versions,
    audited usage, no-overwrite run records and `incomplete` status into the reproducibility manifest. Do not disable
    native subagents by default: DeLM and Agensh do so for accounting, which a role policy can choose for trainable runs.
12. **Attribution.** Credit DeLM, GitSwarm and Agensh in docs, and write our own code and prompts. MIT reuse would need
    notices. GitSwarm's site has no license, so nothing beyond short cited quotes.

## Taste notes

- Elegant: DeLM's board is 639 lines over one log, every feature is a fold, and its errors are written for the model.
- Elegant: GitSwarm has few concepts (one commit, one added link type, three exits) and is honest in its own prompts:
  votes are "selection state", and validation is not correctness.
- Elegant: Agensh's tool descriptions explain consequences; `delegation_id` carries revision semantics in one field.
- Elegant: Prime's `delivered` and `queued` receipts say exactly what happened, and the daemon derives the sender.
- Avoid: enforcing safety in prompts when the service could do it. DeLM and Agensh both do this; GitSwarm's enforcement
  of its own prompt rules is unknown.
- Avoid: words that overclaim, such as "verified notes", or "claim" for an advisory post.
- Avoid: harness limits leaking into the protocol (DeLM's 25 s) instead of living per driver, and task advice mixed
  into coordination prompts.
- Avoid: lifecycle scattered across a shell runner, sidecars and prompts (Agensh), or held in one long `run()` (DeLM).

## Unknowns and risks

- **No upstream code was run,** so semantics come from reading. Our conformance tests must reproduce the race, lease
  and cursor cases rather than trust this report.
- **GitSwarm's harness is unseen.** Enforcement of read-only peers, the abstain-loop rule, slot and timeout behavior,
  and ballot storage are unknown. Revisit section 3 if code is released. Its text came from PDF extraction, and the
  website's commit example differs from the prompts; compatibility would need the H.2 format.
- **DAO is undefined** (section 5).
- **Not inspected:** Humanize (`hmz`) internals, the DeLM paper, DeLM's plugin source, Agensh's PDF report, the Copilot
  and Pi adapters beyond docs, Prime Agent's delivery ordering.
- **Results are the authors'.** Speedups, pass rates and compounding were not verified; do not repeat them as fact.
- **Injection risk.** Board content, DM text and peers' in-flight logs are untrusted data entering agent context in
  every one of these systems. The code we could read has no content-level defence. Brief section 12 requires more.
- **Clean-room rule.** No listing or search result surfaced an implementation named platoon-harness during this work.
