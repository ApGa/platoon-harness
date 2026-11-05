# 0045. An agent's process is not its identity

**Status:** Accepted, 2026-11-05

## Context

An agent kept its harness's process for as long as it lived. A child that stays ([ADR 0023](0023-agents-that-stay.md)) idles for
hours between messages, each one a live Claude Code, Codex or pi process, and that ADR deferred to M2 releasing such a process and
resuming it natively at the next message, by the path a harness that dies while idle would take. That path did not exist: a harness
that exited on its own ended its agent `lost`, with its subtree, though [the spike](../research/spikes/real-harness.md), section 7,
found a native resume cured every `kill -9` it could produce, 4 of 4, and recommended resuming once and ending the agent on a second
exit. The owner chose a fixed ten minutes idle, with no setting.

## Decision

- **An agent rests when its harness has no process,** and its next handover brings the harness back first: on its native session, or
  anew where it took no turn, on a fresh credential, offering nothing, as a resume after a crash does. Its identity, cursors, waits,
  instructions and record stay as they stood, so the agent is the same agent with a new process. A runtime start leaves a resting
  agent to its handover, since it has no process to bring back.
- **Ten minutes between turns, on the session's clock, rest an agent,** when its harness is persistent and resumes by a native id it
  gave, and it is not held, has no goal still to begin and no finish to come, while the session accepts work. Time since its start, its
  last turn's end or its release from a hold counts. The courier asks for it, as `agent.rest`, a runtime op that checks all of this in
  its own transaction and does nothing for an agent no longer at rest, and a `rest` effect ends the harness's process tree.
- **A harness that exits on its own rests its agent, once.** The host sends its `exited` to `agent.rest` rather than ending the agent:
  a turn it was in is lost, with `crash_window` naming where that turn began, its agent is told its turn was cut off, which wakes it
  at once, and the `rest` effect ends what the harness left, its tool in a group of its own among it. A second exit before a turn of its
  ends, as the turn that ends forgives the first, ends the agent `lost`, saying so. So does an exit while the session accepts no work,
  of an agent with a finish to come, which finishes it, or of a harness that cannot resume. What ends a harness by the host's own
  word, a report it cannot take, a driver that raises, six handovers failed or a goal never begun, is no exit on its own, and ends
  the agent as before, while a process that lost its stream, past its quota among it, has exited, and rests once.
- **No event type is new.** A rest is an effect of the kind `rest`, its exit reason in its data, and `Agents` keeps `idle_since`,
  `resting` and `exits` from the events already there.

## Alternatives considered

| Alternative | Why not |
|---|---|
| A cap on live harness processes, releasing the longest idle first | The owner chose a fixed time. A cap makes one agent's rest depend on how many others there are, which no single agent's record says |
| A setting for the ten minutes | Nothing has measured what an idle harness costs or what the first turn after a resume costs its prompt cache, so no value a user picks would be better informed |
| The host ending a process on a timer of its own | A daemon's timer decides outside the journal, so a rest would be no fact, a client could not tell a resting agent, and a restart would forget it |
| A timer per agent in the journal | Two more events a turn for every agent, for a decision the courier already makes level-triggered from the record |
| Relaunching an exited harness at once, by an effect of its own | A resting agent is the same state, and its next handover already brings the harness back. An exit in a turn is told at once, which is that handover |
| Resuming at a runtime start a resting agent's harness | It spends a process on an agent that may never be spoken to again, and rests it again ten minutes later |
| Counting a relaunch that fails as an exit | The handover fails and goes again, as any does, and six in a row lose the agent: one rule for a harness that will not take what it is handed |

## Consequences

- A resting agent's next message waits for its harness to start: seconds on Claude Code, Codex and pi.
- A harness that dies on its own costs its agent the turn it was in, never the agent or its subtree, the first time.
- `Agents` is at view version 13. `delivery.ready` lists the agents to put to rest, and its `due` the next time one will be.
- The live test that held a harness killed alone to `lost` now holds it to its resume.
- A harness killed before it has written its own session has none to reopen, though the journal holds its turn: each relaunch fails,
  and its agent is lost at the sixth failed handover, about a minute later. Claude Code had not written its conversation down in
  most kills in its first turn here, during a model call or a call of ours, live run 76 among them, and had in run 77, during a shell
  tool, so the real-binary tests kill in a second turn.

## Evidence

- `tests/unit/primitives/test_lifecycle.py`: `test_an_agent_between_turns_for_ten_minutes_is_put_to_rest`,
  `test_an_agent_that_is_held_or_on_a_harness_that_cannot_resume_never_rests`,
  `test_a_harness_that_exits_on_its_own_in_a_turn_cuts_it_off_and_rests_once`,
  `test_a_second_exit_before_a_turn_ends_loses_the_agent_and_a_turn_that_ends_forgives_one` and
  `test_a_harness_with_nothing_to_come_back_to_ends_its_agent_when_it_exits`, on a manual clock.
- `tests/unit/runtime/test_host.py`, on a manual clock with scripted harnesses:
  `test_an_idle_agent_s_process_ends_after_ten_minutes_and_its_next_message_resumes_it_natively`,
  `test_a_harness_that_exits_on_its_own_in_a_turn_is_resumed_once_and_told_its_turn_was_cut_off`,
  `test_a_resting_agent_comes_back_at_its_handover_and_not_at_a_runtime_start`, and
  `test_a_harness_that_exits_twice_before_a_turn_ends_is_lost_and_its_parent_hears`.
- On the real Claude Code, Codex and pi binaries and the OpenHands worker against FakeModel, `tests/integration/clients.py`:
  `an_idle_harness_rests_and_its_next_message_resumes_it_natively`, `a_harness_killed_alone_in_a_turn_is_resumed_once_and_told` and
  `a_harness_killed_alone_twice_before_a_turn_ends_is_lost`.
- Live, `tests/live/test_rests.py`: an idle agent rested and answered on its native session after, on `claude-haiku-5-5` in run 74
  in 2 calls and on `gpt-6-luna` in run 75 in 7; a harness killed alone during a shell tool came back told, on `claude-haiku-5-5` in
  run 77 in 4 calls and on `gpt-6-luna` in run 78 in 4.
