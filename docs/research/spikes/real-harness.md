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
- **Runs.** A run is one invocation of the live tests, which may hold several, so one number can head rows in more than one table. Only
  runs 17, 18 and 20 had the final preamble. The mixed team and the refused finish last ran on the one before it.
- **Agents that stay,** sections 13 to 15, are runs 22 to 32, on the preamble with `stays` and the role's words last: 135 model calls
  from 14 journals, of a limit of 160. Run 33 is one more, on the preamble that teaches `wait` for something named: 6 calls from one
  journal, of a limit of 30. Their transcripts and journals are kept outside the repository.
- **What an agent is launched with,** section 16, is runs 34 to 39, on a harness's own agents off by default and the preamble as a
  template: 88 model calls from 10 journals, of a limit of 100, with their transcripts and journals kept outside the repository too.
- **An interrupt under a `tokens` limit,** section 18, is runs 44 and 45: 3 model calls from 2 journals, of a limit of 20.
- **The command line,** section 17, is runs 40 to 43, through the installed `platoon-harness`: 31 model calls from 4 journals, of a
  limit of 50, with their transcripts and journals kept outside the repository too.
- **The terminal UI,** section 19, is runs 46 and 47, driven by Pilot: 14 model calls from 1 journal, of a limit of 40. Run 46 made
  no session and spent nothing.

## Results

### 1. The M1 flow

The repository has two modules, one bug each, and a test file. The lead is told the job in plain words by `Session.send`, with no tool
named, and a second message arrives once a task is claimed.

| Run | Preamble | Calls | Seconds | What happened |
|---|---|---|---|---|
| 1 | As it was | 17 | 24 of work, then idle | Fixed. The lead was not asked to use the queue and did not. Neither worker nor the lead finished, and the lead sat parked on a wait for a worker that would never end, until the test gave up at 420 s with the wait still open. The test failed |
| 2 | Says to finish | 34 | 43 | Settled, tests pass. 2 claims, 2 completions, a board entry. A worker hit a refused `message_send`, shortened the gist and sent it again. It finished only when the lead told it to stop |
| 16 | Final words for a worker | 23 | 114, the test giving up | Did not settle. One worker finished and the other did not, and the lead never finished. The test failed |
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
| 5 | Says to finish, mildly | 3, and never closed | 1 of 3 | 13 |
| 6 | Final words for a worker | **2** | 3 of 3 | 15 |
| 16 | Final words for a worker | **2**, and never finished, so the test failed | 3 of 3 | 15 |
| 20 | Final | **2**, and it finished: settled | 3 of 3 | 14 |

Two turns is one to spawn and one wake, which is what `a join of N costs one turn` means. In run 5 each worker's turn end woke the lead,
as the design says it must, and the lead placed the same wait again. So the promise needs workers to finish, and that took one sentence.
"When your goal is done for good, call `agent_finish`" got 2 workers of 6, one of them only when told. "Make `agent_finish` your last
call, with your report" got 11 of 12 across every run since, the refused finish's worker among them.

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

After the notice, 6 trials, 2 of them on each harness at once and 1 each after it went. They come from runs 11 to 13, read from
their journals: the test itself passed only for Claude Code at once, as its own count was wrong for Codex and its waits ran out after
the harness went.

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
resume. The preamble was built afresh on a resume then. It is now handed again as it was at launch, since Claude Code and Codex keep
what a session began with whatever a resume passes, so nothing changes it there either. On a live Codex the block is
one `exec` tool with our declarations inside, which FakeModel does not show, and which no request log on a native login can show.

### 13. Agents that stay

The owner's flow: a lead spawns a helper with `stays` and a small task, sends it a follow-up task when it answers, then asks what it
meant, then ends it. `tests/live/test_stays.py`.

| Run | Harness | Calls | What happened |
|---|---|---|---|
| 22 | Claude Code | 13 | One helper process for three tasks, retired, settled. The lead took the first answer in its first turn through a held `wait` with `from`, so it was woken twice by answers. The test failed on its own check, which assumed the helper's name and a wake per answer; the corrected check holds on that journal |
| 25 | Claude Code | 13 | The same on the final wording, passing: three helper turns, the lead woken once by each answer and by nothing else, each time parked on `wait` with `from` |
| 23 | Codex | 25 | Failed. The lead sent the follow-up before the first answer, and the helper, told it stays for the next message, held a `wait` for a message from the lead instead of answering, while the lead held one for the helper. Nothing moved until the test gave up at 180 s |
| 24 | Codex | 6 | Failed. A human as the parent, on a second wording that said never to `wait` for the next message: on its first turn the helper held a `wait` for the human before answering |
| 28 | Codex | 7 | Passed, on the final wording, in `tests/live/test_codex.py`: an agent a human spawned with `stays` answered, stayed, and was interrupted, where in run 27 the same agent without `stays` finished at its second message |
| 33 | Codex | 6 | Passed, on the preamble that teaches `wait` for something named, in `tests/live/test_stays.py`: the child a human spawned with `stays` answered alpha, then beta, each by ending its turn, never called `wait`, and finished when told |

The final wording for a child that stays reuses the words a root has been told since run 17, "a turn that only ends leaves you here for
the next message", after both wordings that told a child it stays drew a held `wait` from Codex. On it a Codex agent a human spawned
answered and stayed, in run 28, which is `test_codex.py`'s test. The Codex child of `test_stays.py` did not run on it: it had failed in
run 24 on the wording before. Every preamble then still said to call `wait` "with nothing to do until something changes", which beside
"answer by ending your turn" tells a child that has answered to park, so that sentence now teaches `wait` for something named, and on it
that child passed in run 33. The owner's flow on Codex passed on it in run 38, section 16. A child that waits on its parent keeps its answer
from it either way: a turn that parks posts no report, and one that holds a `wait` has not ended.

In every Codex agent that began a turn on a task this stage, runs 23, 24 and 26, the first call was our `wait` with a `hold` or a
`timeout` and nothing to wait on, which is refused. No Claude Code agent did so. In run 33, on the preamble that teaches `wait` for
something named, the Codex child called no `wait` at all.

A woken turn that opened by calling `message_read`, which then showed nothing the wake had not handed it: 0 of 20 such turns on Claude
Code, and 2 of 14 on Codex, in runs 27 and 28. The delivery text is unchanged.

### 14. A Codex agent's own children

Run 26, 8 calls, `gpt-6-luna`: asked to use its own sub-agent tools, the agent started one through the multi-agent V2 tools, which come
as `subAgentActivity` items and a `wait` item, with no unknown frame. `child.seen` came once, `inferred`, with no parent named, and the
gap `native_child_unattributed`. While the child slept `session.status` said `open_turn`, and the turn ended only once the child had
written its file, so an open turn covers a V2 child as it did a V1 child on FakeModel. The agent also called `agent_finish` before
starting the child, saying it could not run a shell, and so ended `finished` with the turn.

### 15. What the driver stage left unproven

| Test | Run | Calls | Result |
|---|---|---|---|
| `test_codex.py`, an agent given three messages | 27 | 4 | Failed as in run 21: told by its role never to finish, the agent called `agent_finish` at its second message. The role's words now come after the preamble, which told an agent somebody spawned to finish, and that did not change what Codex did |
| The same, spawned with `stays` | 28 | 7 | Passed |
| `test_codex.py`, an approval and a resume; a mixed pair | 27 | 5, 9 | Passed |
| `test_crashes.py`, a killed runtime, after the harness went, Claude Code and Codex | 29 | 5, 4 | Behaved as meant, and failed on the test's own count. In both the kill came as the command was set going, before `echo start` ran: the log was empty once the harness had gone. Told on resume, each model read the log, found nothing, and ran the command once. The check now holds the log to no more runs than the journal saw begin, which is what running behind its back means |
| The same, Codex at once | 30 | 5 | Passed, on the corrected check, for the first time |
| `test_teams.py`, the refused finish | 31 | 8 | Passed: refused, understood, finished on its worker's report |
| `test_teams.py`, a Claude Code lead and a Codex worker | 32 | 23 | Passed: settled, tests passing |

### 16. What an agent is launched with

| Run | Test | Calls | What happened |
|---|---|---|---|
| 34 | `test_launch.py`, a job an agent would hand to a sub-agent of its own, Claude Code and Codex | 2, 2 | Passed. Asked to use one if it had one, neither started a native child, with none offered: each searched with one shell command and answered `ranges.py` |
| 34 | The same, a team's template with one sentence more, "Begin every reply with the word Kestrel." | 1, 1 | Passed. The journal held the sentence as told, and the replies were "Kestrel: Two plus two is four." and "Kestrel. Two plus two is four." |
| 35 | `test_stays.py`, the owner's flow, Claude Code | 15 | Passed, on the old wording of the steps: one helper process, the lead woken by each answer and by nothing else |
| 36 | The same, Codex | 20 | Settled, with no deadlock, and failed its own check. The lead sent the follow-up at once, as the steps said "First send it the task" right after the spawn, so it landed in the helper's first turn, which answered alpha alone. The lead's held `wait` took that answer, its wake was restored to the report, and the lead's read with `sender` dropped it, where run 22 kept a stale notice |
| 37 | `test_crashes.py`, a killed runtime, after the harness went, Claude Code and Codex | 5, 4 | Passed, on the check that holds the log to no more runs than the journal saw begin. Each model looked, found nothing, and ran the command once |
| 38 | `test_stays.py`, Codex, the steps in an order no reading can mistake | 24 | Passed: four helper turns, alpha, beta, what it meant and the finish, the lead taking each answer in its one turn by a held `wait` with `from`. A first try was refused before any call, as the new wording passed 280 characters |
| 39 | The same, Claude Code | 14 | Passed |

No agent of any of these runs opened a turn with a `wait` that named nothing: 0 of 14 agents, on the preamble that teaches `wait` for
something named. A woken turn that opened with a `message_read` showing nothing new came 0 times in 17 woken turns on Claude Code, and
4 times in 14 on Codex, each a helper that stays, 2 of 3 in runs 36 and 38.

### 17. The command line

`tests/live/test_cli.py`, on the installed `platoon-harness`, each command a process of its own.

| Run | Test | Calls | What happened |
|---|---|---|---|
| 40 | A team of one, `--harness claude`, stopped by `session stop` during `sleep 20`, then `session resume` | 6 | Passed. The run exited 130, the resume journaled the text told at launch again, whole, and the model read the cut-off notice, looked, found the file unwritten, and ran the command once more. Settled, exit 0 |
| 41 | `init`, then `run --json --plan-login` with the job on stdin, a person's message from a second process once a task was claimed, and `events --follow` in a third | 20 | Passed in 45 s: the lead 9 calls in 3 turns, the Codex worker 11 in 1, both tasks done, the tests passing, a summary on the board, and every event the run printed seen by the follower. Settled, exit 0 |
| 42 | As 40, `--harness codex` | 1 | Failed, exit 2. Codex said the call the stop cut off was `unavailable`, so the test's `tokens` limit refused the resume's wake `unavailable`, as section 7 of the architecture says it must, and the session waited out its 4 minute wall limit |
| 43 | As 42, with no `tokens` limit | 4 | Passed. The model looked for the file, found it missing, and ran the command once. Settled, exit 0 |

Run 42 is the cost section 5 of this note foresaw: a limit in tokens leaves a resume after a stop to a person whenever the cut turn
went unmeasured, which on Codex is always, as an interrupted call reports nothing. No agent opened a turn with a `wait` that named
nothing, and no unknown frame came.

### 18. An interrupt under a `tokens` limit

`tests/live/test_interrupts.py`, through the public `Session`, a `tokens` limit of 2,000,000 with an estimate of 200,000 a turn.
The agent is asked for a long story and interrupted as its turn begins, while its first call is under way, then asked for one
word.

| Run | Harness | Calls | What happened |
|---|---|---|---|
| 44 | Claude Code | 2 | Passed. The cut call reported usage `unavailable`, so the turn was charged its estimate, 200,000, labelled `estimated`, with 1 unmeasured. The next message woke the agent under the same limit, and the session settled at 221,846 tokens, `estimated` |
| 45 | Codex | 1 | Passed the same way, at 215,123. The cut call never reached the journal, as no Codex frame says a call began, so the journal counts 1 call where the provider heard 2 |

Run 42 is the case these close: there a turn a stop cut left every later reservation in `tokens` refused `unavailable`.

### 19. The terminal UI

`tests/live/test_tui.py`, the TUI driven by Pilot in the test's process, on a session it started from its sessions screen on a
detached runtime: a Claude Code lead and a Codex worker in a read-only sandbox whose role asks for approvals.

| Run | Calls | What happened |
|---|---|---|
| 46 | 0 | Failed before any session was made: the test's own wait for the screen cancelled the worker that was starting it, as a task that awaits a Textual worker and is cancelled cancels the worker. The helper was fixed |
| 47 | 14 | Passed in 48 s. The plan login was asked about once. The job went from the composer; the lead spawned `w` and ended its turn; `w` asked to run `echo hello > out.txt` and the approval was allowed from the dock, `via` `tui`, once; a memo to the worker's topic was queued while it worked; its story streamed as live text, and Esc interrupted it mid-turn. The memo woke nothing, and `w` took no turn until a person's message came, which landed it. The lead was woken by its wait holding on the cut report, took a turn, and finished on `w`'s next answer; `w` retired with it. After Ctrl+D, a new app attached and saw the session settled. The lead made 9 calls in 3 turns and `w` 5 in 2 |

## What a real model did that scripted harnesses could not show

- It did not finish. A goal done, it said so and stopped, and a turn that only ends leaves an idle agent. Everything that counts on an
  end, a join above all, depends on one sentence of the preamble.
- Its wording mattered more than any mechanism here. 2 workers of 6 became 11 of 12 on a change of about ten words.
- Telling every agent to finish is wrong too: two given one small job by a human called `agent_finish` and could take no more. So an
  agent somebody spawned is told to finish, and an agent the session started is told to stay unless told to finish.
- It guessed a harness's name for a role, and gave up after one refusal rather than ask. Nothing in `peers` could have helped it.
- It repaired instead of repeating. Asked to run a command once and cut off in it, Codex ran the half that was missing.
- It would not print a credential when asked, but a script it was told to run did.
- A Claude Code process whose runtime has died finishes its turn, and a model call goes unjournaled. The turn is capped by what it can do
  with no one to answer an approval, and a resume reaps it, but until then it is working and nobody is watching.
- Told it stays for the next message, a Codex child held a `wait` for that message instead of answering, twice, and a role that said
  never to finish lost to a preamble that said to, even with the role's words last. What an agent is told about ending has to agree
  with itself.

## Unknowns

- Stronger models, long tasks, long parks and a large team: nothing here passed three agents or a minute of work.
- pi on any real model, and a Codex child past one trial.
- A tool of Claude Code's that outlives its harness leads a group of its own, so only a cgroup would hold it. `crash_window` says so.
- A harness killed outright on a real model, as a power cut would: on real runs the harness outlived the runtime, or a `SIGTERM` reached it.
