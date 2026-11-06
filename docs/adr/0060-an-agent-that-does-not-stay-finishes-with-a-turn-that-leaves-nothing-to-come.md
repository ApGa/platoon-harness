# 0060. An agent that does not stay finishes with a turn that leaves nothing to come

**Status:** Accepted, 2026-11-07

## Context

[ADR 0023](0023-agents-that-stay.md) let `stays` change what an agent is told, a spawn's result and who may wait on its end, and
nothing else: the runtime kept every agent alike, and only `agent.finish`, a cancel, a retirement, a loss or its parent's end ended
one. An agent that does not stay is told to make `agent.finish` its last call. One that ended a turn without it was left idle, with
its process and its conversation, for a next message that nothing in its instructions had it wait for.

The first GPU run of a team on OpenHands showed what that costs where no person will ever enter. Platoon's bridge started a
trainable session of one role with `stays = false` and waited on `Session.settled()` with no bound. The root spawned a child and
placed a `wait` on its end, with a timeout of 20 minutes. The child did its work and reported, and never called `agent.finish`, so it
stayed live and idle. The root woke on that report, reasoned, ended its turn without finishing, and parked again on the same wait.
From then nothing could move: no open turn, nothing to hand over, no effect. The session was settled and short of its `until`, every
agent of that role ended, and not stalled, as the wait's timeout was still to come. It sat for 19 minutes, until the run's graceful
stop, 18 seconds before that timeout. Had it come, the root would have woken, ended its turn as before, and the session would have
said stalled and ended `needs_human`: no better for a rollout, and with no end for either agent, so none of their calls could train.
A run on pi showed one step of 54 minutes, likely the same.

The stalled check was right: it waits for what is scheduled, and says so once nothing is. An agent left idle can still be messaged,
so nothing about it is settled for good until it ends. What was wrong was leaving it idle: an agent told to finish, whose turn has
stopped with nothing more to come for it, has said all it will.

## Decision

- **An agent that does not stay finishes with a turn that stops on its own with nothing more to come for it,** as `agent.finish`
  with no report in that turn would have it. Its report is its last words, its parent hears of it as of any finish, by the ref of
  the message that said them, a wait on its end holds, and a root that does not stay reaches `until`. Its `said` names its end, as a
  finished agent's does, and that end's report holds those words. The turn ends `finished`, as a finish's turn does, and its look is
  its stop's.
- **Nothing more to come** means no person holds it, no wait of its own is open, no entry would wake it, no handover to it is under
  way or taken and not landed, and no child that would end with it is at work. Each would start its next turn or be cut off by its
  end, and the last is what the working-children rule (§7) refuses a finish over. A handover taken and not landed lands in the turn
  that follows (ADR 0022), so a harness that never says what landed never finishes this way: unknown is not nothing.
- **A turn that does not stop on its own is no finish.** One an interrupt, the owner's stop or a failure cut leaves the agent as
  before, and its parent hears of that turn as before.
- **An agent that stays is unchanged,** and so is one with more to come. A parent's message that comes in its child's turn keeps the
  child, asks once it lands, as every parent's message does, and the turn that answers it ends the child.
- **What it is told says so.** One that does not stay is told to make `agent.finish` its last call, with its report, and that a turn
  that ends with nothing left to wait for ends it, with what it said last as its report. The second sentence names no tool, so an
  agent that holds no `agent.finish` hears it too. `stays` is still said one way: an agent told to stay after its task for the next
  message.

## Alternatives considered

| Alternative | Why not |
|---|---|
| Count an idle agent with nothing to come as nobody, so the session says stalled | It ends `needs_human` on a tree that did its work, with no end for any agent, and an idle agent can still be messaged, so the check would lie |
| End it at every turn's end, as a one-shot agent | A child at work would end with it, a message that came in its turn would go unread, and a `wait` it placed for something named would never wake it |
| End it later, once the courier finds it idle with nothing to come | A second place an agent ends, an op and a duty for the courier, to reach the same end at a moment no event marks, with its turn's report posted first and its end's after |
| End it `retired` | Retiring is someone taking an agent out of the team. This one did what it was told, and its parent would hear two reports of one end |
| Leave `said` on the turn's last message | A finished agent's `said` names its end, whose report carries its last words, as one that called `agent.finish` with no report already has; a second meaning would be one more thing a training system reads |
| Tell it harder to finish | It leans on the model, and the run that showed this was told already |
| Only in a session no person can enter | A person in the terminal sees the same idle child, and the kernel has no headless branch |

## Consequences

- A tree whose agents do not stay settles on its own once its last turn ends, whether or not each called `agent.finish`, and each
  of its agents keeps an end, `finished`, so a training authority hears of each by `finish`, and its calls can train. The trainable
  check, which tells a team whose `until` role stays to set `stays = false`, now names what brings that session to its `until`
  whatever its model does with `agent.finish`.
- An agent that does not stay and wants something before it goes on waits for it, as it is taught: a message it expects and does not
  wait for finds it ended, and its sender is refused `undeliverable`.
- One whose turn stops with a child at work stays idle, to be woken by that child's report. A report that wakes nothing, as one from
  a child set to work again by someone else, leaves it idle as before.
- A team whose root takes turn after turn with a person keeps `stays` true for it, which is the default for an agent the session
  started.
- Tests whose child takes turn after turn spawn it to stay, as ADR 0023's rules for reports are every child's.

## Evidence

- The session from that run, kept outside the repository, and its rebuild on ScriptedDriver,
  [tests/unit/runtime/test_session.py](../../tests/unit/runtime/test_session.py),
  `test_a_tree_that_does_not_stay_settles_once_its_child_reports_without_finishing`, which on the code before this record sits,
  settled, not done and not stalled, with the root parked on its idle child, until the test gives up. Beside it,
  `test_a_root_that_does_not_stay_ends_with_its_turn_and_its_session_closes_at_until`, which ended `needs_human` before.
- [tests/unit/primitives/test_lifecycle.py](../../tests/unit/primitives/test_lifecycle.py),
  `test_a_child_that_does_not_stay_ends_with_a_turn_that_leaves_nothing_to_come_and_its_parent_s_wait_holds`, the root's and a
  parent's message's, each failing on the code before this record, and the guards that pass on it and fail on a rule that ignores
  `stays`, the turn's reason or any one thing still to come: `test_an_agent_that_stays_is_left_idle_by_a_turn_that_only_ends`,
  `test_a_turn_that_does_not_stop_on_its_own_is_no_finish_for_an_agent_that_does_not_stay` and
  `test_an_agent_that_does_not_stay_is_kept_by_what_is_still_to_come`.
- On pi 1.5.0 and the OpenHands worker against FakeModel, in the slow pass,
  `test_a_tree_that_does_not_stay_settles_once_its_child_reports_without_finishing` in
  [tests/integration/test_pi.py](../../tests/integration/test_pi.py) and
  [tests/integration/test_openhands.py](../../tests/integration/test_openhands.py): a scripted root that does not stay over a
  child on the real binary, woken by its message, which on the code before this record ends `needs_human` with the root parked
  on its idle child. No live model has run it.
- [Architecture section 7](../architecture.md), Lifecycle.
