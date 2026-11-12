# RFC 0020: Finish and handover wait for the turn

| | |
|---|---|
| Status | Accepted, 2026-11-03 |

## Summary

`agent.finish` takes effect at turn end and a wake's `deliver` stays open until its turn begins, each with a live bound

## Motivation

A harness reports its usage and last message at turn end, so an `agent.finish` that ended its agent inside the call had those reports refused: the cost went unmeasured, and a budgeted teammate stalled with nothing to show for it. A `deliver` that finished at the handover left an agent `waking` with nothing behind it, so a SIGKILL matrix wedged agents there, in a state only a report that would never come could move. Both came from treating a harness's next report as if it were sure to come.

## Proposal

- **`agent.finish` takes effect when its turn ends.** In an open turn it records the report as `agent.finished`, and `agent.ended` commits at turn end. A timer ends a turn still going a minute later, an exit concludes it, and so does recovery once that turn is lost. Out of a turn it ends the agent at once.
- **A wake's `deliver` stays open until its turn begins.** So `waking` always has an effect behind it, and recovery needs no second path. Past a minute, or at an interrupt, it fails, which queues its entries again.
- **Nothing rests on a harness's next report alone.** Each state that waits for one has a live bound as well as a crash path, because a quiet harness wedges the same way a dead one does.

## Alternatives

| Alternative | Why not |
|---|---|
| End the agent in the call and take its reports late | A revoked token and a returned reservation would each need an exception for an agent that has ended, and what it reported would land after the end it belongs to |
| Refuse `agent.finish` in a turn | A model is only ever in a turn, so it could never finish |
| Hold an agent in a `completing` state until its children are done | A hold needs an escape, a live harness or a report kept undelivered, and a second meaning of ended. A review rejected it for a refusal at the call |
| Finish `deliver` at the handover, and let recovery sweep `waking` | That is a second recovery path, and it does nothing for a harness that goes quiet with no crash |

## Consequences

- An agent keeps its tools until its turn ends, so a model can do more after `finish`. Spawning is refused then, since that child would end with it.
- A turn cut off by the timer goes unmeasured, and is labelled so.
- The check over working children is at the call, so a child that begins work between `finish` and the turn's end ends with its parent. Architecture section 7 states this.
- A `deliver` can stay open for a minute, which `settled` counts and which holds up that agent's later effects. `interrupt`, `stop` and `answer` go around it.
- No real harness has been observed ending a turn after this tool call, or beginning one late.

## Evidence

- [Architecture section 5.4 and section 7](../architecture.md). `tests/integration/test_kill_matrix.py`, which found the wedged `waking`, and `tests/unit/runtime/test_session.py` for what a harness reports after a finish.
