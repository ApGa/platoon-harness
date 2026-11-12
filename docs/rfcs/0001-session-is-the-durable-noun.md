# RFC 0001: Session is the only durable noun, and run is a verb

| | |
|---|---|
| Status | Accepted, 2026-11-02 |

## Summary

One word for the thing you attach to. `run` is a verb, because the noun collides with Platoon's

## Motivation

A user needs one word for the thing they start, attach to, resume and export. "Run" was the first word proposed. Harnesses say "session" or "thread". Platoon already uses "run" for its own training work, and a rollout is what a training reader counts. Every extra durable noun is a question each API and UI must answer: which one do you mean?

## Proposal

The durable thing is a **session**: one folder, one journal. `run` is only a verb. `platoon-harness run` runs a session in the foreground, and there is no `Run` class or `run_id`. A harness's own session is always written **native session**. An **episode** is an explicitly opened span inside a session, and only events inside one can become training data.

## Alternatives

| Alternative | Why not |
|---|---|
| `Run` as the durable noun | It collides with Platoon's word, so a training reader must ask whose run. It also reads as one pass, while a session settles, takes a human message and goes on |
| Both `Run` and `Session` | Two durable nouns for one folder. Every API would have to say which it takes |
| A session as one implicit episode | Everyday events would sit inside an episode by default and could become training data by accident |
| `Thread` | Codex already uses it for a native session, and chat UIs use it for a reply chain |

## Consequences

- "Session" is the noun where "run" was first proposed, and "run" stays a verb in the CLI and in prose.
- Sessions have no natural end. `settled` is a state a human message can undo, and only `close` ends one.
- Training stays opt-in by construction: anything outside an episode fails eligibility by default.
- "Session" remains overloaded by ACP and native harness sessions, so those are always qualified. Native ids live in the envelope's `native` field.

## Evidence

- [Architecture sections 2 and 18](../architecture.md).
- Design-phase research, not published: session list and resume is a must-have in every terminal agent surveyed, and a session maps onto one training rollout, so its channels are scoped to it.
