# RFC 0011: Annotations live beside the journal

| | |
|---|---|
| Status | Accepted, 2026-11-02 |

## Summary

Like `git notes`: rewards and judgments never enter the journal or a policy's context

## Motivation

Rewards, judgments and credit arrive after the work, and they change as estimators improve. They must attach to the record without altering it. They must never reach a policy's context. And a closed session is a portable, read-only artifact, so adding a statement to it next year cannot need a runtime or a writer lock.

## Proposal

Annotations live in `annotations.sqlite`, beside the journal. A row attaches to an immutable target the way `git notes` attach to a commit. Rows are unique on producer, version, params, target and kind, and `head_seq` names the exact trace a statement used. Rewards live here with `scope: local | team`, a required `status`, and a nullable `value`. Judged attribution and validated intervention live here too. No agent-reachable read opens this file.

## Alternatives

| Alternative | Why not |
|---|---|
| Append-only `note/*` streams in the journal | Keeping rewards from agents would rest on a grant rather than a file boundary. A closed journal would need one op allowed after close, and a write lock, which breaks its read-only form |
| Fields on events | Events are immutable, and a new estimator is not a correction |
| Rewards only in Platoon | Everyday sessions and non-Platoon judges have statements too. `Trajectory` receives them through the finalizer |
| Zero for an unknown reward | `invalid`, `error`, `cancelled` and `unscored` are not zero (law 10) |
| A digest sealing the session at close | `head_seq` already names the trace. Tamper evidence has no requester |

## Consequences

- A new estimator adds rows beside old ones, on a closed session, so two estimators stay comparable.
- A second file must travel with an export. Losing it loses statements about the record, never the record.
- Annotations have no `seq`, and no event can reference one. An agent's action cannot cite a reward, by construction.
- `rebuild` does not touch this file, because nothing folds into it.
- `None` becomes a Platoon marker only in the finalizer, at one known place.

## Evidence

- [Architecture sections 4, 11 and 14](../architecture.md).
- [platoon-training.md](../research/platoon-training.md), section 7: G5 and G6 on provenance and rewards reaching credit. [distributed-primitives.md](../research/distributed-primitives.md), taste notes: GitSwarm keeps nomination records outside the computation graph.
- [Research index](../research/README.md), brief section 7 gap: keeping reward and judge data out of policy-visible context.
