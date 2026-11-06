# 0059. A parent hears of a child's end once its authority has

**Status:** Accepted, 2026-11-06

## Context

The ended transition posts a child's report to its parent's inbox and requests the child's `stop` in one transaction. The stop ends
the child's harness, looks once more at what it left, ends its workspace, and tells the authority how it ended last, in
`Authority.finish`. The courier, a daemon of its own, hands the report over as soon as it sees it, so the parent's next turn could
begin, and its next model call go out, while the stop was still under way and before the authority had heard of the end. A `wait`
the parent held open in a call answered as soon as the end was journaled, to the same effect. And a stop whose harness would not
end failed before it told the authority at all.

A training authority settles a child in `finish`. Under Platoon's linear agents budget, a parent's call made before its child's spawn
returns is charged that child's reservation, and Platoon's `platoon-teams` bridge returns the spawn once it hears of the end. So a
serialized tree through the bridge could be stopped where a native one is not, by how the two effects raced, and the bridge refuses
the linear budget for a team whose agents spawn.

## Decision

- **Nothing reaches an agent while a stop of a child of its is under way.** `delivery.offer` hands it nothing, whether a wake, a
  steer or a notice on a tool's result, and the courier keeps it on its way to a turn instead of ready. A `wait` it holds open in a
  call does not answer `released`, as `wait.progress`, which the held call asks, says it holds only then; a `hold` that runs out
  first answers `pending`, as any does.
- **The stop tells the authority last, whatever failed before.** `finish` is the stop's outermost `finally`, after the harness has
  ended or failed to, and after the look and the workspace's end. So a parent hears of its child's end, by its report, by the notice
  of a wait that holds on it, or by a held call's answer, only once `finish` has returned or raised.
- **The rule holds the parent, not the entry.** A cursor cannot pass an entry left out, so holding the report alone would stop the
  inbox behind it all the same.
- **The parent stays on its way to a turn,** so what the working-children rule (§7) refuses over it is as before, and the session
  is no more settled than it was: a stop under way is an open effect.
- **A call the parent makes once the child has ended reads the journal as it stands.** A `wait` that holds as it is placed is
  released at once, and `message.read` and `agent.status` show the end. A parent that waits for its child, parked or holding the
  call open, is waiting when the end comes and hears of it only once the authority has; only a parent at work on its own when its
  child ended can read of it first.

## Alternatives considered

| Alternative | Why not |
|---|---|
| Post the report when the stop finishes | The ended transition would become two events, and every view that folds `agent.ended`, and every wait that counts it, would move with it |
| Run the handover's `deliver` effect `after` the stop | `after` names one effect, a handover can carry the reports of two children, and an effect after one that failed never starts |
| Hold a `wait` that holds as it is placed, too | A join on a child that has ended is released at once, which a parent that cancels its own child relies on, as parking instead would cost it a turn; and a parent that places it once the child has ended was at work on its own when the end came |
| Call `finish` before the stop ends the harness | The authority would close an agent whose harness may still call its gateway |
| Hold handovers only under a training authority | The kernel has no training branch (§14), and a parent that reads what its child left gains from the stop's look coming first |

## Consequences

- A parent hears of a child's end after its harness has ended, its stop's look has recorded what it left, and its workspace is
  ended, so a stop that is slow, such as a kept snapshot made whole, delays the report by as long.
- A `finish` that never returns keeps the parent from its next turn, as it already kept the session from settling.
- A stop that fails still tells the authority, after `reap` has ended what a harness that would not end left.
- A training authority that settles a child in `finish` and returns once it has knows that a parent waiting for that child has not
  heard of the end. Platoon's bridge can lift its refusal of the linear budget once it pins a commit with this rule and its
  `finish` returns only once its spawn for that agent has, if it accepts that a parent at work on its own when its child ends may
  read of the end first.

## Evidence

- [tests/unit/primitives/test_lifecycle.py](../../tests/unit/primitives/test_lifecycle.py),
  `test_a_parent_hears_of_a_child_s_end_only_once_its_stop_has_finished`, and the four after it: a wait's notice, a held call, a
  steer and a tool's result, and a refusal over working children. Each fails on the code before this record.
- [tests/unit/runtime/test_host.py](../../tests/unit/runtime/test_host.py),
  `test_a_parent_hears_of_a_child_s_end_only_once_its_authority_has`, with an authority whose `finish` waits until the test lets
  it, and `test_an_authority_hears_of_an_end_whose_harness_would_not_stop`, with a harness whose `stop` raises.
