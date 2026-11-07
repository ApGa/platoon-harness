# Persistent agents

> Background research, dated 2026-11-03 and not maintained: [reference/compatibility.md](../reference/compatibility.md) is current.

Do other systems keep a spawned agent alive after its first task so that it can take follow-ups? Who chooses, how does a
follow-up reach it, is the parent woken by the answer, and how does it end? Reviewed on 2026-11-03.

Eight analysts read source and docs, one or two systems each. A skeptic then reopened the source behind 58 of their claims: 49
held, 9 held only once corrected in detail, and none was wrong. Its summary says 55 claims; its records hold 58, and those are
what is counted here. No upstream was run, so every behavior below is read from code, except Claude Code, which is read from
public docs, the changelog, mod type declarations and the Python Agent SDK, and never from its binary. One scripted experiment ran
on our own runtime, with no model.

## Inspected

| Project | URL | Commit or version | Date | License |
|---|---|---|---|---|
| Codex | https://github.com/openai/codex | `05c08d7`, a one-commit clone newer than 0.166.0. Tool text checked against the 0.164.0 binary | commit 2026-11-02 | Apache-2.0 |
| Prime Agent | https://github.com/PrimeIntellect-ai/prime-agent | `c6d4da9`, past 0.10.2 | commit 2026-10-30 | MIT |
| Claude Code | https://github.com/anthropics/claude-code, https://code.claude.com/docs/en/sub-agents.md, https://code.claude.com/docs/en/agent-teams.md | `f0b737f`, CLI 2.1.316; docs retrieved 2026-11-03 | commit 2026-11-02 | Proprietary |
| Claude Agent SDK | https://github.com/anthropics/claude-agent-sdk-python | `2146f9d` (0.2.176) | commit 2026-10-31 | MIT wrapper |
| OpenCode | https://github.com/anomalyco/opencode | `ff90ed9` (2.2.5) | commit 2026-11-02 | MIT |
| OpenHands SDK | https://github.com/OpenHands/software-agent-sdk | `9884945` (1.59.0) | commit 2026-11-01 | MIT |
| OpenHands CLI | https://github.com/OpenHands/OpenHands-CLI | `283c6ac` (1.16.0, pins SDK 1.28.1) | commit 2026-10-22 | MIT |
| pi and pi durable | https://github.com/earendil-works/pi | `c9f4c7b`, past 1.4.0 | commit 2026-11-01 | MIT |
| ACP spec | https://github.com/agentclientprotocol/agent-client-protocol | `212f0ca` | commit 2026-11-01 | Apache-2.0 |
| Agensh | https://github.com/microsoft/Agensh | `d6063b9` (v1.0.2) | commit 2026-10-30 | MIT |
| DeLM | https://github.com/yuzhenmao/DeLM | `6661761` | commit 2026-10-08 | MIT |
| GitSwarm site | https://github.com/veds12/git-swarm | `9f66af0` | commit 2026-10-09 | None in repo |
| Platoon | https://github.com/ApGa/platoon | `efe3b27` (0.5.0) | commit 2026-10-28 | MIT AND Apache-2.0 |

Evidence is cited as `project@commit:path:line`, against the commit above. Claude Code docs are cited by page, since their line
numbers belong to copies not kept here. The License column is not from this review, whose records hold no license:
[compatibility.md](../reference/compatibility.md) records those of the upstreams it shares.

## Answer

Most systems keep a spawned agent after its first task. None lets the spawner choose that per spawn. A follow-up is a message, or
the spawn tool called again with the child's id. Whether the parent hears the answer is where they break: several notify only for
the first task. Ending is the weakest part: few give the parent a way to end a child that is not also a kill, and some give none.

| System | After the first task | Who chooses | Follow-up | Parent woken by the answer? | How it ends |
|---|---|---|---|---|---|
| Codex V2 (most current models) | Stays; evicted when idle, reloaded on demand | Nobody | `followup_task` | No: it waits as mail, seen only by a running parent or a `wait_agent` | No close tool, only `interrupt_agent`, which keeps it |
| Codex V1 | Stays, holding a slot | Nobody | `send_input` | No: a notice joins the parent's next turn, for the first task only | `close_agent`; `resume_agent` reopens it |
| Prime Agent | Stays; its kernel and then its process are released when idle | Nobody | `agent_message.send` | Yes, by the child's own message. The backstop notice covers the first task only | The parent's `rlm.delete_subagent`, which destroys it |
| Claude Code subagents | Ends; its transcript is kept 30 days | Nobody | `SendMessage` runs it again under its id | Told in a later turn | `TaskStop`, still reopenable by a message |
| Claude Code teammates (experimental) | Stays, idle | Indirectly: teams are switched on, and the model passes `name` | `SendMessage` | An idle notice carrying the answer, which the docs say arrives unasked | Negotiated shutdown or `TaskStop`; dies with the lead's process |
| OpenCode | Stays as a stored session | Nobody | `subagent` with `sessionID` | Yes, for background children; a foreground call returns it | Users and clients only; the model has no kill |
| OpenHands task tool | Closed; rebuilt on resume | Nobody | `task` with `resume` | A blocking call returns it | No kill |
| pi durable, example code | Stays | The extension author | `send` | Yes, unless Esc drops it while queued | `stop` ends its work; nothing ends the agent |
| ACP (draft) | Stays associated | The agent | Inside the agent, reported as `session_message` | Left to the agent | `session/cancel` stops its work; closing the parent ends that work too |
| Platoon | Ends, graded | Nobody | None | The awaited `spawn` returns | Its run returns, or a cancel, which forfeits its tokens |

Agensh, DeLM and GitSwarm have no parent and child. Agensh's peers stay alive between turns and are fed by a durable queue per
agent. DeLM and GitSwarm workers are one-shot by design, and reuse what is on the board or in the repository instead.

## Codex

Codex has two generations of tools, and the model catalog picks between them: 9 of 12 bundled models say V2, 2 say V1, and an unknown model
falls to V1, as a real 0.164.0 run with a stub model showed. The choice is fixed per session at its first full turn, so switching
model does not switch generation (`codex@05c08d7:codex-rs/core/src/config/mod.rs:1687`,
`codex@05c08d7:codex-rs/core/src/session/mod.rs:4717`). The `multi_agent_v2` flag defaults false, but it is not the switch.

- **A child stays.** `completed` is a turn's outcome, and only `Shutdown` ends the thread (`codex@05c08d7:codex-rs/core/src/agent/status.rs:26`).
  V1 says "Completed agents remain open and count toward the concurrency limit until closed". V2 evicts an idle child and reloads it
  from its rollout on the next follow-up, with no cap on how many it knows.
- **Follow-up.** V1 has `send_input`. V2 splits it: `followup_task` wakes the child or steers it, and `send_message` only queues.
  App-server refuses `turn/start` and `turn/steer` on a V2 child, so only an agent can follow one up
  (`codex@05c08d7:codex-rs/app-server/src/request_processors/thread_input.rs:8`).
- **The answer.** V2 mails the parent on every terminal turn with `trigger_turn=false`, so an idle parent is not woken unless
  `wake_on_agent_messages` is on, which defaults false and applies to the root alone (`codex@05c08d7:codex-rs/core/src/session/turn_input.rs:802`).
  An interrupted child sends nothing, and neither does one stopped by a budget, since that maps to `Interrupted` too. V1's watcher is
  one-shot: it stops at the first final status, so the answer to a `send_input` arrives only if the parent calls `wait_agent`
  (`codex@05c08d7:codex-rs/core/src/agent/control.rs:445`).
- **The end.** V1's `close_agent` closes a child and its descendants for good, and `resume_agent` reopens it. V2 registers no close
  tool, and its `interrupt_agent` says "The agent remains available". A parent's shutdown leaves its children registered, and their
  results are dropped, not sent up (`codex@05c08d7:codex-rs/core/src/agent/control_tests.rs:4507`).

## Prime Agent

Every `rlm.spawn` child is a daemon session that outlives its task, and the prompt says so: "These subagents are persistent, just
like the root session." An idle child gives up its Python kernel at once and its worker process after 90 minutes, and keeps its
session file and ledger edge until deleted.

- **Follow-up.** `agent_message.send` to the child's durable id wakes a fresh worker over its session file if needed
  (`prime-agent@c6d4da9:crates/pa-daemon/src/messaging.rs:177`). The child keeps its transcript and its REPL namespace.
- **The answer.** The child is told to reply by message, which wakes the parent or queues if it is busy. A child that ends a task
  silently sends one `[child-exited: no-reply ...]` notice. Follow-ups are not tracked as runs: the settle watcher has exited, so
  during one `collect` says settled, keeps the first answer, and a silent follow-up gets no notice. The skeptic found this worse
  than reported: a user's Stop does nothing to a follow-up, an idle-only delete is not refused, and the parent gets no cancel notice
  (`prime-agent@c6d4da9:crates/pa-daemon/src/rlm_children/host.rs:625`, `prime-agent@c6d4da9:crates/pa-daemon/src/rlm_children/usage.rs:231`).
- **The end.** `rlm.delete_subagent` is the only end the model has, and it destroys the child. The user's Agents view can also
  cancel a run and keep the session. Close reasons keep a shutdown from reading as a cancel. Nothing bounds a reply loop but a cap
  of 20 pending messages; the rate limit that its status reports is not enforced
  (`prime-agent@c6d4da9:crates/pa-daemon/src/agent_message_ingest.rs:3`).

## Claude Code

Two mechanisms, both through the `Agent` tool.

- **Subagents** end at their task, and their transcript stays. `SendMessage` by id or name runs one again under the same id with its
  full history, after it completed, failed, hit `maxTurns` or was stopped by the model with `TaskStop`. A stop by the user or the
  SDK holds until the user types into its transcript. Built-in Explore and Plan return no id and cannot be continued. A background
  subagent's result reaches the parent "as a completion notification in a later turn"; the skeptic found no doc that says an idle
  interactive parent starts a turn for it (https://code.claude.com/docs/en/sub-agents.md, https://code.claude.com/docs/en/headless.md).
- **Teammates** stay running and idle, and send the lead an idle notice carrying their answer. They need
  `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` and an interactive session, not `-p` or the SDK. An `Agent` call with `name` makes a
  teammate when teams are on, which the docs list as a cause of teams forming unasked. A teammate ends by a negotiated shutdown it
  may reject, or by `TaskStop`, dies with the lead's process, and is not restored by `/resume`
  (https://code.claude.com/docs/en/agent-teams.md).
- **Loops.** Messaging between sessions has real guards: a rate limit, repeats dropped, a queue of 50, and "a message loop between
  two sessions therefore stops on its own" (https://code.claude.com/docs/en/cross-session-messaging.md). Nothing like it is
  documented inside a session. The changelog records messages lost to a finishing subagent (2.1.280) and a resumer never woken by
  the agent it resumed (2.1.260).

## OpenCode

Every child is a durable session. `subagent` with `sessionID` continues a direct child, "running or finished": it steers a
running child and wakes an idle one (`opencode@ff90ed9:packages/core/src/tool/plugin/subagent.ts:153`). A background child's
answer is admitted to the parent's inbox as a message that wakes it, and is deleted only once admitted, so a restart cannot lose it
(`opencode@ff90ed9:packages/core/src/session/subagent-completion.ts:37`). A follow-up to a running child joins its job and gets no
notice of its own, which is inferred from code. The model has no way to stop or delete a child: of the 19 plugin tools none does,
and interrupt and remove belong to users and clients. A child has no channel to its parent but its final answer.

## OpenHands

The `task` tool closes a child after every run and rebuilds it from its event log on `resume=<task_id>`
(`software-agent-sdk@9884945:openhands-tools/openhands/tools/task/manager.py:164`). Nothing live stays, so an idle child costs
nothing, and its shell state dies between tasks. The registry is in memory, so the ids go dead on restart, and a resume drops the
iteration and budget limits the first run had. The parent blocks in the call, so there is nothing to wake. There is no kill, and
the executor's `interrupt` is a no-op, so a blocked parent cannot stop its child. The tool is off by default in the SDK presets and
on in the CLI. `start_child_conversation` makes a durable child the parent's model can never reach again, and orphans it on delete.

## pi and pi durable

Core pi has no subagents, by design, and its example extension runs each task as a one-shot process with `--no-session`. Pi durable
supplies the parts: a conversation outlives its owner's run, and `submit` to it is a follow-up that steers or queues
(`pi@c9f4c7b:packages/durable/docs/spec.md:2724`). Persistent subagents exist only as example code, `test/examples/22-subagent-background.ts`,
which no test or package script was found to run. There a background reporter posts each answer to the parent as an input that
starts a turn if it is idle. Esc while that input is queued drops it, and an aborted child reports nothing. `stop` aborts the child's
work and leaves it usable, and nothing deletes one, so names stay forever. The coding agent does not depend on pi durable.

## ACP, Agensh, DeLM and GitSwarm

ACP's subagents RFD is a draft behind the `unstable_subagents` feature. A child's identity outlives its tasks, and `idle` means "the
parent may assign more work" (`acp-spec@212f0ca:docs/rfds/subagents.mdx:738`). A client may only cancel a child, and only if the
child advertises it; cancel leaves it reusable. Closing the parent cancels all its descendants' work and frees their resources,
which ends their work, not necessarily the children. Agensh keeps a native session open per worker and serializes a durable event
queue into prompts on it, acknowledged after the turn. DeLM runs one prompt per session and refuses to restart an ended one
(`DeLM@6661761:board/shared_context.py:340`). GitSwarm's workers exit at episode end and a fresh worker takes the slot, by its
website, since no harness code is published.

## Platoon

Platoon trains on what we record, so its rules bound ours.

- **One spawn, one run.** `ctx.agents.spawn` runs a child to completion and returns once; there is no send, resume or message API
  (`platoon@efe3b27:platoon/harness/agent.py:163`).
- **One trajectory, one reward.** A trajectory's single reward goes undivided onto its trainable action tokens and is then centered
  within the group, so several tasks in one child cannot be credited apart (`platoon@efe3b27:platoon/utils/tinker_data_processing.py:562`).
  Per-task credit would need one spawn per task.
- **A cancel forfeits the tokens.** A cancelled child gets no grade and its tokens are policy-ineligible
  (`platoon@efe3b27:platoon/utils/trajectory_status.py:102`). A child that returns `completed` keeps them.
- **Nothing outlives a rollout.** The collection is built after the episode program returns, and then every agent key is closed
  (`platoon@efe3b27:platoon/harness/rollout.py:325`). A parent's run waits on its running children, so an idle child blocked on a
  queue holds the parent to its deadline and is then cancelled, untrainable. That case is inferred; no test runs it.

## What the findings support

- **No system offers a per-spawn lifetime choice.** Lifetime is fixed by the system, by which tool is used, or by code an extension
  author writes. Claude Code's nearest, a `name` that makes a teammate when teams are on, is the one its own docs warn about.
- **A follow-up's answer gets lost.** Codex V1 and Prime Agent notify the parent for the first task and not after it. Codex V2 sends
  nothing for an interrupted or budget-stopped turn, OpenCode folds a follow-up to a running child into one notice, and pi durable
  drops a queued answer at Esc. Codex V2 and OpenCode notify per run, which is what holds.
- **Almost nobody has a mechanical loop guard.** Codex avoids loops by never waking an idle agent, OpenHands by blocking, pi durable by
  taking the spawn tool from the child and asking for no reply. Prime Agent has a queue cap and a rate limit it does not enforce.
  Only Claude Code's messaging between sessions stops a loop by mechanism.
- **Ending is two verbs or none.** ACP, pi durable, Codex V2 and Claude Code stop work and keep the child. Prime Agent's only end
  destroys it. OpenCode's and OpenHands's models have no end at all.
- **Platoon gives one trajectory one reward, drops a cancelled child's tokens, and lets nothing outlive a rollout.**

## Our runtime today

A throwaway script, not in this repository, ran a lead and a worker of scripted harnesses through the public `Session`, with no
model, on 2026-11-03 at about commit `4d098cc`. The worker never calls `agent_finish` unless a case says so.

| Case | What happened |
|---|---|
| A. The lead re-tasks the worker by message and ends its turn, five rounds | Two rounds ran. The second answer woke nobody, since the monitor wakes once per causal chain for each child, and the session stalled |
| B. The same, with a `wait` on the worker after each message | All five ran, one lead turn each |
| C. The worker answers each task with its own `message_send` | All five ran, in seven lead turns: each message woke the lead, as a report would not |
| D. The worker is spawned with no goal, then given one by message | It was told to finish, not to stay. Two runs differed, one taking no turn and one taking one, which was not explained |
| E. The lead finishes over an idle worker | Under `cancel-subtree` the worker ended `cancelled`, and a human's later message was refused `undeliverable`. Under `adopt` it stayed idle and took the human's task |
| F. The owner stops the session and resumes it | The worker came back idle on a new process resumed natively, and took a second task |
| G. A session-started agent | It took two tasks and stayed idle. `settled()` then closed the session, and a third message was refused `conflict` |
| Ends | The lead cancelling an idle worker ended it `cancelled`, retiring one ended it `retired`, and cancelling one in a turn ended it `cancelled`. A worker told by message to finish ended `finished`. A worker calling `agent_cancel` on itself was refused `not_permitted` |

So a child already outlives its first task here and takes follow-ups by message, as in most systems above. Case A is the gap Codex
V1 and Prime Agent have, and case E records an end the child did nothing to earn.

## Implications for platoon-harness

The owner's design follows, to be recorded as RFC 0023, "Agents that stay".

- **`stays` on a role, and an optional `stays` on `agent.spawn` that overrides it either way.** This is the per-spawn choice no
  system offers, stated outright rather than derived, as Claude Code derives a teammate from a name.
- **By default a spawned agent finishes and a session-started one stays.** It is the rule the preamble already teaches, since
  [the spike](spikes/real-harness.md) found that workers finish only when told to, and that agents a human started could take no
  more work once told to finish.
- **A parent's message to its own child re-arms that child's report wake.** The answer to a follow-up reaches the parent as the first
  answer did, which closes case A and the gap in Codex V1 and Prime Agent. `max_hops` still bounds the chain, which is the
  mechanical loop guard almost nobody has.
- **Waiting for a staying child to end is refused.** That end never comes on its own: Platoon's parent held by an idle child and
  Claude Code's `--print` hanging on teammates until 2.1.71 are what such a wait does.
- **An idle child ended with its parent ends `retired`, not `cancelled`.** It was told nothing and did nothing wrong, and Platoon
  drops a cancelled child's tokens. Case E shows today's record.
- **At M2 an idle child's process is released and resumed natively.** Prime Agent's tiers, OpenHands's rebuild, Claude Code's
  transcript and Codex V2's eviction all keep an idle child's identity without its process, and case F shows a native resume on a
  new process already works.
- **At M3 one trajectory has one reward.** A staying child's tasks share it, and nothing outlives a rollout, so per-task credit is a
  spawn per task.

The ends need no new verb: `interrupt` stops a turn, `finish` and `retire` end an agent with a report or quietly, and `cancel` is
the kill. Most systems above have one of these, or none.

## Unknowns

- No upstream ran. The Codex clone is newer than the 0.164.0 we drive by an unknown margin, V2 frames were never seen on the wire,
  and the live model catalog may differ from the bundled one.
- What an idle child costs in memory or tokens: no system states a figure, and none was measured.
- Whether `SendMessage` can continue a native subagent under our `claude` driver, which turns background tasks off.
- Whether Claude Code guards against loops inside a session, and whether a stopped subagent's nested children stop too.
- Prime Agent: whether a message revives a child archived by a parent's kill, and how a child that continues after a restart
  reconciles with its parent's row. Both are inferred from code.
- OpenCode: "none found" claims cover the files read, except the missing kill, which a listing of every plugin tool backs.
- pi durable: whether example 22 runs anywhere in CI.
- Platoon: a long-lived child on an in-process queue was not run.

## Clean-room statement

No implementation named in the clean-room rule was searched for, surfaced or opened in this review. GitSwarm is used as a pattern
reference with the owner's permission.
