# RFC 0005: Daemons, effects and explicit uncertainty

| | |
|---|---|
| Status | Accepted, 2026-11-02 |

## Summary

Level-triggered, requested then started then finished, explicit uncertainty, recovery per kind

## Motivation

An op cannot touch the world (law 3), yet agents must launch and input must land. A crash can fall between acting and recording, and then nothing local says which happened. Upstream protocols do not fill the hole: ACP has no retry-safe prompt, Platoon's mint has no idempotency, and Codex's `accept` does not fix the outcome.

## Proposal

A **daemon** is a restartable task that reads views, acts, and reports back through an op. It holds no durable position, so it is level-triggered. An op requests work with `txn.effect`, in the same transaction as its decision. A daemon commits `effect.start` before acting and `effect.finish` or `effect.fail` after. A `started` row left over after a crash, or past its `timeout`, becomes `effect.uncertain`, and its declared policy applies: `retry`, `reconcile` or `surface`. Recovery is per kind because safety is per kind. `deliver` reconciles by input id. `admit` is never retried, because a retry mints a second key. `workspace` never discards uncommitted work. `interrupt` and `stop` simply repeat.

## Alternatives

| Alternative | Why not |
|---|---|
| Edge-triggered workers with stored offsets | The offset is a second durable position that can disagree with the views, and a missed trigger stalls forever. A level-triggered daemon finds its work again on restart |
| Only `requested` and `finished` | "Never ran" and "may have run" look the same after a crash |
| Treating an unknown as failed, or as done | The first duplicates a delivery, a launch or a mint. The second loses work silently, and absence must stay honest (law 10) |
| One retry policy for every kind | `interrupt` is safe to repeat and `admit` never is |
| A durable-execution engine | It needs deterministic replay, and replay here never executes anything (law 5) |
| Tracking harness tool calls as effects | We did not perform them, so we cannot retry them. They are observed, and a turn in flight at a crash becomes `turn.lost` plus a gap |
| The name `worker` | It collides with the common role name and with Platoon's rollout worker |

## Consequences

- Recovery is one function, per agent: reap, resume, reconcile, dispatch. `reconcile` needs a live link, so it runs after resume and answers `unknown` without one.
- An `uncertain` effect under `surface` waits in `attention` for a principal to decide, with `effect.settle`. Nothing guesses.
- Delivery is at-least-once, with the id visible for dedupe. We promise no stronger execution guarantee.
- The journal side of recovery has tests. Recovery against real harness processes does not yet.

## Evidence

- [Architecture laws 3 and 5, section 5.4](../architecture.md), [Status](../STATUS.md). ACP has no retry-safe prompt, and Platoon 0.5.0's mint has no idempotency key.
- Design-phase research, not published: with identical input, 29 of 48 commands Codex 0.164.0 accepted ran and 19 failed, cause not established. [RFC 0002](0002-one-journal-per-session.md)'s benchmark: commits without acks were observed, as expected.
