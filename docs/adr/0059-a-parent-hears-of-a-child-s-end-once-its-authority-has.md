# 0059. A parent hears of a child's end once its authority has

**Status:** Accepted, 2026-11-06

## Context

The ended transition posts a child's report to its parent's inbox and requests the child's `stop` in one transaction. The stop ends
the child's harness, looks once more at what it left, ends its workspace, and tells the authority how it ended last, in
`Authority.finish`. The courier, a daemon of its own, hands the report over as soon as it sees it, so the parent's next turn could
begin, and its next model call go out, while the stop was still under way and before the authority had heard of the end.

A training authority settles a child in `finish`. Under Platoon's linear agents budget, a parent's call made before its child's spawn
returns is charged that child's reservation, and Platoon's `platoon-teams` bridge returns the spawn once it hears of the end. So a
serialized tree through the bridge could be stopped where a native one is not, by how the two effects raced, and the bridge refuses
the linear budget for a team whose agents spawn.

## Decision

- **Nothing is handed to an agent while a stop of a child of its is under way.** `delivery.offer` hands over nothing then, whether
  a wake, a steer or a notice on a tool's result, and the courier keeps the agent on its way to a turn instead of ready. The stop
  tells the authority last, in a `finally`, so the parent is handed its child's report, or the notice of a wait that holds on the
  child's end, only once `finish` has returned or raised.
- **The rule holds the parent, not the entry.** A cursor cannot pass an entry left out, so holding the report alone would stop the
  inbox behind it all the same.
- **The parent stays on its way to a turn,** so what the working-children rule (§7) refuses over it is as before, and the session
  is no more settled than it was: a stop under way is an open effect.
- **An answer to the parent's own call reads the journal as it stands.** A `wait` it calls on a child that has ended is released
  at once, a `wait` it holds open answers when its condition holds, and `message.read` and `agent.status` show the end. A parent
  that parks on a wait and ends its turn, as its preamble asks, or that ends its turn with nothing to wait on, is out of its turn
  when the end comes, and hears of it only by a handover.

## Alternatives considered

| Alternative | Why not |
|---|---|
| Post the report when the stop finishes | The ended transition would become two events, and every view that folds `agent.ended`, and every wait that counts it, would move with it |
| Run the handover's `deliver` effect `after` the stop | `after` names one effect, a handover can carry the reports of two children, and an effect after one that failed never starts |
| Hold a wait's answer too, until the stop has finished | A join on a child that has ended is released at once, which a parent that cancels its own child relies on, as parking instead would cost it a turn; and holding only a wait held open would give one answer to a call a rule of its own |
| Call `finish` before the stop ends the harness | The authority would close an agent whose harness may still call its gateway |
| Hold handovers only under a training authority | The kernel has no training branch (§14), and a parent that reads what its child left gains from the stop's look coming first |

## Consequences

- A parent hears of a child's end after its harness has ended, its stop's look has recorded what it left, and its workspace is
  ended, so a stop that is slow, such as a kept snapshot made whole, delays the report by as long.
- A `finish` that never returns keeps the parent from its next turn, as it already kept the session from settling.
- A training authority that settles a child in `finish` and returns once it has knows its parent has not yet heard of the end. The
  bridge can lift its refusal of the linear budget for a parent that hears of its child's end by a handover, once it pins a commit
  with this rule; a parent that holds a `wait` open in its turn reads the journal as it stands.

## Evidence

- [tests/unit/primitives/test_lifecycle.py](../../tests/unit/primitives/test_lifecycle.py),
  `test_a_parent_hears_of_a_child_s_end_only_once_its_stop_has_finished`, which fails on the code before this record.
- [tests/unit/runtime/test_host.py](../../tests/unit/runtime/test_host.py),
  `test_a_parent_hears_of_a_child_s_end_only_once_its_authority_has`: an authority whose `finish` waits until the test lets it,
  and a parent handed nothing until then.
