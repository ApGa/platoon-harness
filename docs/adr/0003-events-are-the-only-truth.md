# 0003. Events are the only truth, and bodies are separate

**Status:** Accepted, 2026-11-02

## Context

Three needs pull against each other. A credit estimator written next year cannot rerun anything, so the record must be complete and immutable. Redaction must be able to erase a leaked secret. A retry must receive the first answer, including a refusal. The obvious design keeps an idempotency ledger, an outbox and timers as authority tables beside the log. That makes several truths, which a crash can leave disagreeing and a rebuild cannot check.

## Decision

`events` is the only truth. Triggers abort `UPDATE` and `DELETE` on it, and dropping every other table and refolding gives identical contents. Commands, effects, timers and principals are all folds. A command's result is the `outcome` on its last event, and `v_commands` folds from that. Bodies live in `bodies` and `blobs/`, keyed by SHA-256, and events cite the hash. `body.tombstone` erases the bytes while the event and its hash survive, so the graph stays whole.

## Alternatives considered

| Alternative | Why not |
|---|---|
| A `commands` ledger as a second truth table | Two sources must agree after a crash, and a refold could not reproduce it. With `outcome` on the event, one commit holds both |
| Bodies inline in events | Immutable events would make a secret in tool output permanent, or redaction would have to break law 1 |
| Mutable state plus an audit log | Nothing proves the state derives from the log, so they drift |
| Replaying commands, as durable-execution engines do | Ops would have to be deterministic, and replay would run them. Replay must never re-execute a tool. Folding events cannot |
| A raw frame spool for every harness | It is a second durable path and a scrubbing problem. Only unknown updates keep their frames |
| Per-event hash chains | Tamper evidence has no requester |

## Consequences

- Law 1 is checkable: a property test compares live views to a rebuild. Running that after every scenario in CI is planned, since neither exists yet.
- A secret in a `gist` or in `data` cannot be erased in place. It needs an offline rewrite that produces a new session.
- A command's last event is held back from `events` until the op returns, because its `outcome` does not exist before then. Folds never see `outcome`, and only `v_commands` is written from it.
- A refused or empty command still ends on one event, on `commands/<actor>`, so a failed attempt moves no object's version.
- Folds ignore unknown types, so an extension's events survive export and replay.

## Evidence

- [Architecture laws 1, 2 and 5, sections 5.1, 5.2 and 15](../architecture.md).
- [journal-performance.md](../research/spikes/journal-performance.md), result 8: no partial command and no lost ack across SIGKILL rounds. [distributed-primitives.md](../research/distributed-primitives.md), Temporal row: deterministic replay is out.
