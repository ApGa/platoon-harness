# 0037. An offer is confirmed only by its harness, and the record claims nothing more than it holds

**Status:** Accepted, 2026-11-05

## Context

[ADR 0010](0010-provenance.md) made exposure a pair of events, an offer and its confirmation, and left three things loose that
credit research now leans on. An agent's read was counted as seen when its op committed, before its result had left: a crash or a
hang-up after the commit left a seen with no delivery. A launch handed a harness its goal and instructions and recorded neither as
offered, so a child's dependence on its goal was no edge, and `context_version` did not count it. And the record said more than it
knew in places: `ModelRef` had fields nothing wrote, a driver stated how well a native child's calls were tied to an agent, which
depends on an admission it cannot see, a gap had two shapes, and a takeover's gap was written when the hold ended, so no answer
bounded inside the hold could see it. `call.joined`, the late join of a tool to its model call, was designed and never needed.

## Decision

- **One way to confirm.** A `context.delivered`, payload 3, is written only from the harness's own report, in that report's
  transaction: an `input.delivered` for an input it said it took, or a completed tool item whose `native_id` is the anchor an
  unconfirmed offer was made under, with the evidence `tool_item`. A read records its offer under its call's anchor as before, and
  the surface hands a steer notice and a body only it could read under that anchor too. A cursor still moves when a result shows
  something, as a cursor says what was handed, and a confirmation of what a result showed moves nothing more. `delivery.confirm`,
  which only tests called, is gone.
- **The launch offer.** A fresh start's `agent.instruct` offers what it hands the harness, `context.offered{how: launch}`: the
  instructions, and the goal, `agent/<x>@1`, gist and body. The goal is the first delivery, `AgentSpec.goal` a `Delivery` under the
  offer's id, which each driver sends as it sends any input, so its harness says it landed as it says any did, and the first input
  a harness says it took confirms the launch. A native resume offers nothing, as Claude Code and Codex keep what their session began
  with, and a relaunch with no native session is a fresh start. `exec` puts the goal in argv, which confirms nothing.
- **Calls by their own ids.** `ModelRef` holds `call_id` alone, verbatim, and keeps its type as the envelope's `model` is a
  column of every journal. A tool reaches its call only through ids both records hold, the op's anchor and a tool item's
  `native_id` and `call_id`, so `call.joined` is dropped.
- **No driver claims attribution.** `child.seen` names the native child and the tool call that started it.
- **Gaps of one shape.** Every incident gap is one `gap.recorded{plane, what, since}`, payload 2. `GAPS` gives each member of the
  closed set its plane, its writers and whether content could reach an agent through it. `runtime.start` writes `crash_window`
  beside `turn.lost`, which names no gap at payload 2, and `since` names the cut turn's start. `agent.takeover` records `takeover`
  where the hold begins. `exposure_unconfirmed`, which nothing wrote, has left the set.

## Alternatives considered

| Alternative | Why not |
|---|---|
| Seen when a read commits | A crash or a hang-up after the commit leaves a seen with no delivery |
| A second confirmation event for reads | Two ways to confirm. The tool item is the harness's own report already |
| Comparing an item's body with what was offered | Only Claude Code's item holds the result's text, and it adds nothing to the order |
| Confirming a launch by its first `turn.started` | A second way to confirm, when the drivers already confirm their first input |
| Offering the instructions again at a resume | It records a delivery nobody handed, and raises the context version for nothing |
| Sending the goal through the courier | It changes every first prompt |
| `call.joined` with a quality field | The join is an equality of ids both records already hold |
| A `plane` a driver states | The plane is the gap's own, so a stated one is either redundant or wrong |
| The takeover's gap at its release, with the open hold read from the agents view | A second source for one gap |

## Consequences

- A read is confirmed only where its harness's tool item names its anchor: Claude Code's and Codex's do, a Codex read being
  confirmed as returned to its Code Mode script. A read through pi's shim, through `ph` or by `exec` stays unconfirmed, as no item
  holds the shim's own id, until the shim passes pi's own tool call id.
- `context_version` counts what a launch handed over, so a child's first event counts its goal.
- The wire protocol is 2: a goal is a `Delivery`, and `gap` and `child.seen` lost a field each.
- The bound that compares a confirmation with the model call that chose an event, on the agent's ordered report stream, is the
  queries' to apply. The record keeps both in the order its harness said them.

## Evidence

- The design's honesty probes: `expose_read` wrote the offer before the reply left, and a takeover's gap followed its hold.
- `tests/unit/primitives/test_confirmations.py`, `tests/unit/primitives/test_gaps.py`, `test_reports.py`, and the conformance check
  `delivered_text_in_next_prompt`, whose launch case ran on the real Claude Code, Codex and pi binaries against FakeModel.
  [Architecture section 11](../architecture.md).
