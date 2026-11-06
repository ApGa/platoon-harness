# RFC 0022: What a harness took is the runtime's again

| | |
|---|---|
| Status | Accepted, 2026-11-03 |

## Summary

An offer taken and never landed is queued again when its turn stops short or its harness comes back, and no driver sends it again

## Motivation

A steer finishes its `deliver` when the harness has taken it, which says nothing of whether it will land. Each real harness can lose
what it took: Codex drops a steer at `turn/interrupt`, pi leaves it in a queue no run takes, Claude Code begins a turn on it by itself, and
a crash takes all of it. Two drivers each kept every delivery's text to send it again, and swallowed a refusal while they did, and across
a crash nothing sent it again at all, so a message was lost for good. `Receipt.queued` was meant to say what a harness still held, and
nothing read it.

## Proposal

- **An offer the harness took and did not land is queued again** when its turn ends short of `stopped`, is lost, or its harness comes
  back from a crash, in one fold in `Deliveries`, as a failed handover is. A turn that stopped on its own lands it in the turn that
  follows, so it is left alone.
- **A driver sends nothing again.** Where a harness can be told to drop what it queued, the driver tells it, so nothing comes twice:
  Claude Code's interrupt passes `cancel_queued`, and pi's queue is cleared at a turn cut short.
- **The contract returns nothing from `start`, `deliver` and `interrupt`.** `ready.native` names a session, and the journal says what
  landed, so `Started` and `Receipt` went.

## Alternatives

| Alternative | Why not |
|---|---|
| Each driver sends again what its harness dropped | That is policy written in each driver, it was written twice and failed in silence, and no driver can see a crash |
| Read `Receipt.queued` at an interrupt | It says what a harness holds at one moment, and a harness can drop it later, at a crash most of all |
| Reconcile every taken offer on resume | `reconcile` reads a harness's own record, which a kill can leave short of what it had queued, so a miss would still be a guess |

## Consequences

- A harness that keeps what it took, against what it was told, may hear it twice, which at-least-once allows and refs dedupe.
- `interrupt_keeps_a_steer` left `check_driver`, as the promise is the runtime's, and tests hold it in `tests/unit/primitives` and on each
  real binary through a session.

## Evidence

- A review's `kill -9` of a runtime with a steer taken and not landed: the steer was never offered again, on Claude Code against
  FakeModel. Now it is, in `tests/integration/test_claude.py` and `tests/unit/runtime/test_recovery.py`.
- [Architecture section 7](../architecture.md), Inboxes and topics.
