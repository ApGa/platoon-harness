# RFC 0003: Events are the only truth, and bodies are separate

| | |
|---|---|
| Status | Accepted, 2026-11-02 |

## Summary

Bodies sit apart so redaction works, and commands fold from events

## Motivation

Three needs pull against each other. A credit estimator written next year cannot rerun anything, so the record must be complete and immutable. Redaction must be able to erase a leaked secret. A retry must receive the first answer, including a refusal. The obvious design keeps an idempotency ledger, an outbox and timers as authority tables beside the log. That makes several truths, which a crash can leave disagreeing and a rebuild cannot check.

## Proposal

`events` is the only truth. Triggers abort `UPDATE`, `DELETE` and a replacing `INSERT` on it, and dropping every view and refolding gives identical contents. Effects, timers and principals are all folds. A command's result is the `outcome` on its last event, and a retry finds it through an index over `events`. Bodies live in `bodies` and `blobs/`, keyed by SHA-256, and events cite the hash. `body.tombstone` erases the bytes while the event and its hash survive, so the graph stays whole.

## Alternatives

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
- A command's last event is held back from `events` until the op returns, because its `outcome` does not exist before then. Folds never see `outcome`.
- A refused or empty command still ends on one event, on `commands/<actor>`, so a failed attempt moves no object's version.
- Folds ignore unknown types, so an extension's events survive export and replay.

## Evidence

- [Architecture laws 1, 2 and 5, sections 5.1, 5.2 and 15](../architecture.md).
- [RFC 0002](0002-one-journal-per-session.md)'s benchmark: no partial command and no lost ack across `kill -9` rounds. Design-phase research, not published: Temporal's deterministic replay is out, as a replay must not run a tool again.
