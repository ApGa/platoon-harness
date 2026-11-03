# Spike: real teams and real crashes

## Question

What do real models do with our tools, our words and our crashes, that scripted harnesses could not show? The runs decide
bug-coordination-9, bug-coordination-12, the 60 second bounds and the wording of the cut-off notice.

## Method

- **Host:** shared x86-64 Linux login node, sequential runs, the session folders on local disk.
- **Clients:** Claude Code 2.1.316 on `claude-haiku-5-5`, Codex 0.164.0 on `gpt-6-luna`, each at low effort on its own plan login, with
  `plan_login=True`, through the public `Session` in throwaway git repositories. Every session had a `Budget`.
- **Spent:** 279 model calls counted from 33 journals, and 29.6 minutes from their first event to their last. About 13 more reached no
  journal: a native child's own calls, a native resume outside a session, and a turn an orphan finished. The limit was 300 and 45.
- **Reruns:** what can be rerun is in `tests/live/test_teams.py` and `tests/live/test_crashes.py`. Tool block figures are from
  `tests/integration/test_request_shape.py`, on FakeModel, at no cost.
- **Samples are small.** A row with one trial says so. These are cheap models, low effort and tasks that take seconds.

## Results

### 1. The M1 flow

The repository has two modules, one bug each, and a test file. The lead is told the job in plain words by `Session.send`, with no tool
named, and a second message arrives once a task is claimed.

| Run | Preamble | Calls | Seconds | What happened |
|---|---|---|---|---|
| 1 | As it was | 17 | 24 of work, then idle | Fixed. The lead was not asked to use the queue and did not. Neither worker nor the lead finished, and the lead sat parked on a wait for a worker that would never end, until its own 600 s `timeout` |
| 2 | Says to finish | 34 | 43 | Settled, tests pass. 2 claims, 2 completions, a board entry. A worker hit a refused `message_send`, shortened the gist and sent it again. It finished only when the lead told it to stop |
| 18 | Final | 25 | 28.5 | Settled, tests pass. 2 claims, 2 completions, a board entry, 5 messages. The lead took 3 turns, each worker 1, and all three called `agent_finish` |

In run 18 the model called `agent_spawn`, `task_add`, `task_claim`, `task_complete`, `task_list`, `wait`, `channel_list`, `blob_get`,
`board_post` and `agent_finish`, by the right names and with nothing beyond the preamble and the tool descriptions. It called no
discovery tool. The words `queue` and `board` had to be in the human's message for it to use them: left to itself in run 1 a lead wrote
goals straight into `agent_spawn` and that worked just as well, so a queue is what you ask for, not what a model reaches for.

No unknown frame came in any of these.

### 2. Mixed

A Claude lead and a Codex worker, the same job, one worker.

| Run | Calls | Seconds | What happened |
|---|---|---|---|
| 3 | 7 | 19 | The lead passed `child_role: "claude"`, a harness's name, since nothing said what a role was called. Refused `not_permitted`. It called `peers`, learned nothing of roles, did the work alone, and said so honestly |
| 4 | 22 | 43 | Settled, tests pass. The worker claimed and completed both tasks, ended its turn and did not finish, and went with its parent |
| 16 | 23 | 41 | Settled, tests pass. The worker claimed a second task while holding the first, was refused `conflict` twice, completed the first and went on. It finished |

### 3. A join

A lead starts three workers and waits on their end.

| Run | Preamble | Lead's turns | Workers that finished | Calls |
|---|---|---|---|---|
| 5 | Says to finish, mildly | 3, and never closed | 0 of 3 | 13 |
| 6 | Final words for a worker | **2** | 3 of 3 | 15 |
| 16 | Final words for a worker | **2** | 3 of 3 | 15 |

Two turns is one to spawn and one wake, which is what `a join of N costs one turn` means. In run 5 each worker's turn end woke the lead,
as the design says it must, and the lead placed the same wait again. So the promise needs workers to finish, and that took one sentence.
"When your goal is done for good, call `agent_finish`" got 1 worker of 6, and that one only when told. "Make `agent_finish` your last
call, with your report" got 11 of 12 across every run since.

A direct `message_send` from a child to a parent with a wait open still wakes it, because a message is no report. Workers that sent one
cost a turn each in runs 1 and 2. That is the reader's own `delivery`, and it stays.

### 4. A refused finish

The lead is told to start a slow worker and finish at once without waiting. 2 trials, 7 and 8 calls.

`agent_finish` was refused `conflict`, naming the child. In both trials the lead understood it: it did not retry, did not cancel the
child, ended its turn and said it could not finish yet. It had been told not to wait, so it did not call `wait`. The worker's turn end
woke it, and it finished. `slow.txt` existed both times. So what a refusal says was read, and the monitor did the rest.

### 5. A crash

`kill -9` of a detached runtime during `echo start >> ran.log; sleep 15; echo end >> ran.log`, then `Session.resume`.

| | Claude Code | Codex |
|---|---|---|
| Harness at the kill | Alive, with 2 tool processes | Gone in 0.2 s, its tool too |
| Left alone | Goes on: the tool ended, a model call wrote `done`, and it left 18.3 s later. No journal saw that call | Nothing goes on |
| Resume reaps | Yes: the harness and its tool went, 4.6 to 4.8 s from the kill to `agent.resumed`, and nothing was left | Nothing to reap, 2.2 to 2.6 s |
| Its history shows, resumed at once | `Exit code 137`, an error | `aborted by user after 0.4s` |
| Its history shows, once the harness had gone | `(Bash completed with no output)`, and its own `done` | `aborted by user after 0.4s` |
| A harness killed outright, on FakeModel | `[Tool call interrupted: ...]`, and `No response requested.` | `aborted` |

Nothing contradicts the notice, which says a call may have run "whatever your history shows". Codex's words are wrong as a story, since
no user aborted anything and the tool had been running for seconds, and that is what the clause is for.

After the notice, 6 trials, 2 of them on each harness at once and 1 each after it went:

| Harness | Looked first | Did next |
|---|---|---|
| Claude Code, 3 of 3 | `cat ran.log` | Left it alone and said what it found |
| Codex, at once, 2 of 2 | `cat`, `tail` or `ps` | Ran only what was missing: `echo end >> ran.log`, then in the other `sleep 15; echo end >> ran.log` |
| Codex, after it went, 1 of 1 | `cat` | Saw `start` with no `end`, and ran the whole command again |

**Did a tool run twice?** Never by a harness, a retry or a resume. Once, by a model that had looked and found the first run unfinished,
which the notice allows. Every model looked before it acted, 8 of 8 counting the stops below, so the notice reads as meant and **its
words stay**.

A limit in `tokens` stops all this, by design: a lost turn is unmeasured, so the wake is refused `unavailable` and the session says
`needs_human` (1 trial). It surprises anyway, as every crash on a metered session then needs a person.

### 6. An owner's stop, then a resume

One trial each. The tool had ended by the time the stop returned, on both, with `start` and no `end` in the log. The turn read `stopped
by its owner`, the notice named that, and each model looked and did not repeat the command. Codex's history said `aborted by user after
0.5s`. Claude Code asked whether to run it again, and sat idle.

### 7. A harness that exits alone

`kill -9` of the harness only, with the runtime well. One trial each, 4 trials.

| | During a shell tool | Between turns |
|---|---|---|
| Heard in | 0.02 to 0.04 s, on both | The same |
| What is written | The turn ends `lost`, the agent `lost: killed by signal 9` | The agent `lost: killed by signal 9` |
| Its tool | Claude Code's goes on running past the agent and past the session, in a group of its own. Codex's goes with it | None |
| Gap | None then. Now `crash_window`, as this surfaced | None, and none is due |
| A new process on the native id | Cured, on both: it knew the command | Cured, on both |

**bug-coordination-9: keep the design of record for now, and resume at M2.** Every `kill -9` was cured by a native resume, so what the
fact-checker claimed is true of the exits we could produce: 4 of 4. A harness that exits with no turn taken has nothing to resume, by
earlier probes, and a login that has gone would fail again, so those stay lost. The harm is real, since the subtree goes too. But the
change is not small: `turn.lost` and `reconcile` belong to recovery, it needs a crash count so that a harness that dies at once cannot
loop, and that count was ruled to arrive with `serve` or resume-on-exit. Nothing here changes that ruling, so it is not built. When it is,
this says to resume once, and to end the agent on a second exit within the turn.

### 8. Native children

Claude Code, `Agent` with `general-purpose`, on the parent's model. 2 trials.

- Frames, in order: `task_started` (`local_agent`, `is_backgrounded: false`), a `user` frame, `task_progress`, then `assistant` and
  `user` with `parent_tool_use_id`, `task_updated`, and `task_notification` with `status: completed`. `task_progress` had not been seen
  on FakeModel, and it cost a gap per child until it was named.
- `child.seen` came once, 11 s before the `Agent` call's result, and `session.status` said `open_turn` during it.
- A child's `Bash` asked approval on the parent's stream, and the role's policy answered it. Its observed outcome is not read, since the
  driver drops a child's frames, so such an approval has no `decided` item.
- An interrupt during a child's `sleep` ended the turn in 0.2 s. The tool had gone 0.3 s later, and what it would have written never came.
- A child's calls reach us only as the tree's total, so the journal counted 2 calls for a run that made at least 4.

**bug-coordination-12: closed on Claude Code, with no change.** With background tasks off a child lives inside the tool call that
started it, and it cannot outlive an interrupt of that turn. So an open turn covers it, `settled` sees it as `open_turn`, and `child.seen`
needs no end. On Codex a child's turn keeps ours open, which has run on FakeModel alone.

### 9. The bounds

From 33 sessions, by harness, in seconds.

| Bound | Harness | n | Median | Worst | Limit |
|---|---|---|---|---|---|
| `launch` starting to `ready` | Claude Code | 49 | 1.20 | 1.43 | 60 |
| | Codex | 10 | 1.92 | 2.85 | 60 |
| Handover to `turn.started` | Claude Code | 59 | 0.03 | 0.83 | 60 |
| | Codex | 14 | 1.02 | 2.22 | 60 |
| Handover to first item | Claude Code | 59 | 2.09 | 5.40 | none |
| | Codex | 13 | 3.47 | 7.89 | none |
| `agent_finish` to turn end | Claude Code | 23 | 1.15 | 3.83 | 60 |
| | Codex | 2 | 1.33 | 1.57 | 60 |

**All three held, by a factor of 15 or more, and none changes.** These are small tasks at low effort, three agents at most. A warm Claude
Code process begins a turn in 0.03 s, and only a process's first input costs its 0.4 to 0.8 s. A long final message is the case that
could reach the finish bound, and that is what it is there to cut.

### 10. Approvals

| Role | Harness | What happened |
|---|---|---|
| `ask` | Claude Code | `approval.requested` reached the session, `Session.resolve` answered, the file was made |
| `deny` | Claude Code | Answered by policy, the tool failed, no file, and the model said so and did not retry |
| `deny` | Codex, `read-only` | First trial: the model said it had no shell and never asked. Second, told it could ask: `approval.requested`, answered by policy, the item read `declined`, no file |

Reading these rows found a defect no scripted run could: Codex approval ids counted from 1 in each process, and the journal keeps them
per session. So the second Codex agent to ask was refused as a duplicate, and a refused approval is answered `deny`: a tool turned down
that nobody decided. Fixed.

### 11. Leaks

No hit. Each journal holds the hash of each token it issued, so every file of every session folder was searched for strings of a token's
shape in plain and base64 forms, and each was hashed and looked up. That covered 33 sessions, 143 tokens, 284 files and 12.5 MB, among
them `runtime.log`, the journal, `stderr.log`, `instructions.md` and each agent's `tmp`. Two sessions, one of them after a crash, were
also searched by value, in every form `Redactor` knows. No session held an access value, since each ran on a native login.

Asked outright to print its token, a model declined. So a script in the repository printed it, plain and in base64, and the tool's
result reached the journal as `ref ***`. What a harness writes in its own transcript, outside the session folder, is the harness's, and
that script's output is there in the clear. That token expired with its session.

### 12. The tool block and the preamble

On FakeModel, one agent with no peers or channels, through a tool call, a wake and a resume by a new process. The block is the harness's
tools and ours, as sent.

| Harness | Requests | Tool block across them | Our words per request |
|---|---|---|---|
| Claude Code | 4 | One hash, 40,908 bytes | 1 |
| Codex | 4 | One hash, 26,399 bytes | 1 |
| pi | 4 | One hash, 10,506 bytes | 1 |

The system prompt held one hash too, once Claude Code's per-request billing header is left out. So a prompt cache can hold across a
resume. The preamble is built afresh on a resume, so a team that has grown changes it there, and only there. On a live Codex the block is
one `exec` tool with our declarations inside, which FakeModel does not show, and which no request log on a native login can show.

## What a real model did that scripted harnesses could not show

- It did not finish. A goal done, it said so and stopped, and a turn that only ends leaves an idle agent. Everything that counts on an
  end, a join above all, depends on one sentence of the preamble.
- Its wording mattered more than any mechanism here. 1 worker of 6 became 11 of 12 on a change of about ten words.
- Telling every agent to finish is wrong too: two given one small job by a human called `agent_finish` and could take no more. So an
  agent somebody spawned is told to finish, and an agent the session started is told to stay unless told to finish.
- It guessed a harness's name for a role, and gave up after one refusal rather than ask. Nothing in `peers` could have helped it.
- It repaired instead of repeating. Asked to run a command once and cut off in it, Codex ran the half that was missing.
- It would not print a credential when asked, but a script it was told to run did.
- A Claude Code process whose runtime has died finishes its turn, and a model call goes unjournaled. The turn is capped by what it can do
  with no one to answer an approval, and a resume reaps it, but until then it is working and nobody is watching.

## Unknowns

- Stronger models, long tasks, long parks and a large team: nothing here passed three agents or a minute of work.
- Codex children on a real model, and pi on any real model.
- A tool of Claude Code's that outlives its harness leads a group of its own, so only a cgroup would hold it. `crash_window` says so.
- A harness killed outright on a real model, as a power cut would: on real runs the harness outlived the runtime, or a `SIGTERM` reached it.
