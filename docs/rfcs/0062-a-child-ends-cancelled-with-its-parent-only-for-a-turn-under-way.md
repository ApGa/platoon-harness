# RFC 0062: A child ends cancelled with its parent only for a turn under way

| | |
|---|---|
| Status | Accepted, 2026-11-07 |
| Created | 2026-11-07 |
| Authors | Apurva Gandhi (`ApGa`) |
| Builds on | [`primitives/lifecycle.py`](../../packages/sdk/src/platoon_harness/primitives/lifecycle.py), [architecture section 7](../architecture.md#lifecycle), [RFC 0023](0023-agents-that-stay.md), [RFC 0059](0059-a-parent-hears-of-a-child-s-end-once-its-authority-has.md) and [RFC 0060](0060-an-agent-that-does-not-stay-finishes-with-a-turn-that-leaves-nothing-to-come.md) |
| Discussion | The notes of Platoon's `platoon-teams` bridge on its close, kept outside this repository |
| Implementation | `fix: End a child with its parent cancelled only for a turn under way` |

## Summary

A child that ends with its parent ends `cancelled` if a turn of its is under way, from its harness's `turn.started` to that
turn's end, which the end cuts, and `retired` otherwise. A turn on its way, by a goal not begun, a wake that is due, a wait that
holds, or a handover under way or taken and not landed, has not begun, so nothing of it is cut. This amends
[RFC 0023](0023-agents-that-stay.md), which counted a turn on its way as cut off.

## Motivation

RFC 0023 ended a child that ends with its parent `retired` unless a turn of its "was cut off, open or on its way", because a
training system drops a cancelled child's tokens and an idle child was cut off from nothing. Its reason was that every turn such a
child took is whole. The "on its way" half reached past that reason. A child is on its way to a turn while a goal it has not
begun, a wake that is due, a wait that holds or a handover waits to start one, and none of these has begun: the record holds no
`turn.started` for it and no call in it, so every turn the child took is whole, and RFC 0023's own test says `retired`.

Platoon's bridge met the cost. At a rollout's end its close retires each agent left, deepest first, and cancels one that refuses,
as one on its way to a turn refuses `agent.retire`. On its first GPU runs on pi that ended 4 to 26 of each step's 128 rollouts
cancelled, every turn of theirs whole, and the training system dropped their tokens, so the bridge now reads an agent its close
cancels with no turn under way as retired. But its close is not the only way a child ends with a parent. When a parent is cancelled while a child of its is on its
way to a turn, woken by a message or a report, or holding a handover its harness took and had begun no turn on, the SDK ended
that child `cancelled`, and the training system dropped its tokens though no turn of its was cut. The bridge left this to the
SDK, as one end read two ways is a contract with two meanings. How often it happened on those runs was not measured.

## Proposal

- **Only a turn under way is cut.** A child that ends with its parent ends `cancelled` if a turn of its is under way, from its
  harness's `turn.started` to that turn's end, and `retired` otherwise: idle, parked, or on its way to a turn. So `cancelled`
  from a parent's end says that end cut a turn of the child's, which its `agent.ended` names as the turn it closed.
  `session.cancel` still ends every agent `cancelled`, and `agent.cancel` still ends the agent it names `cancelled`, idle or
  not, as each is someone's act.
- **On its way still counts as at work for the refusals.** `agent.finish` and `agent.retire` are still refused over a child on
  its way to a turn, and `agent.retire` of an agent on its way to one: they refuse to end work someone is about to do, while
  the status says what an end cut, a different question.
- **A turn a harness began and had not yet said it began.** A harness handed something may begin a turn before its report
  says so, and its stop ends that turn unseen. The record holds no turn of it and no call in it, so eligibility lists none of
  its calls and nothing of it trains, whichever status the child ends with: the status speaks of the turns the record holds.

## Alternatives

| Alternative | Why not |
|---|---|
| Keep a turn on its way as cut | A training system drops every token of a child none of whose turns was cut, and a training authority reads an end of its own close one way and the SDK's end of a child the other |
| Count as cut only a handover under way or taken, as its harness may have begun a turn unreported | A turn the record does not hold has no call in the record, so nothing of it trains either way, and that is the bridge's case, a handover taken and no turn begun, which cost tokens |
| A status of its own for an end before a turn began | One more status every reader of an end learns, for a difference the record already holds: whether `agent.ended` closed a turn |
| Leave it to the training system to read the record | The bridge does for its close, but the status is the SDK's statement of the end, and two readings of one end is what this removes |

## Consequences

- A child that ends with its parent on its way to a turn ends `retired`, so a training system keeps its whole turns; one in a
  turn ends `cancelled`, as before.
- A parent [RFC 0059](0059-a-parent-hears-of-a-child-s-end-once-its-authority-has.md) keeps on its way to a turn while a stop
  of a child of its is under way ends `retired` if its own parent ends then, as no turn of its is under way.
- What a child had still to start, a goal, a wake or a handover it took, is dropped with it as before. Its status no longer
  says something was to come; its reason, `parent <name> ended`, says why it ended.

## Evidence

- [tests/unit/primitives/test_lifecycle.py](../../tests/unit/primitives/test_lifecycle.py),
  `test_a_child_that_ends_with_its_parent_is_cancelled_only_if_a_turn_of_its_is_under_way`: six children of a parent that is
  cancelled, one idle, one parked, one in a turn, one with a wake due, one holding a handover it took with no turn begun and one
  with a goal not begun, of which only the one in a turn ends `cancelled`. On the code before this record the three on their way
  end `cancelled` too.
- The bridge's rule for its close, which reads an agent it cancels with no turn under way as retired, and its fixtures, in
  Platoon's `platoon-teams`, kept outside this repository.
- [Architecture section 7](../architecture.md), Lifecycle.
