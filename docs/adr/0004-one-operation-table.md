# 0004. One operation table, with every surface derived

**Status:** Accepted, 2026-11-02

## Context

The brief requires an extension primitive to work through the SDK, the tool protocol, the CLI and a generic UI with no core edit. Six surfaces written by hand would drift, and each would be one more place to forget an authorization check. The concept also needs words a reader would guess, and it touches `call`, a word training readers depend on.

## Decision

One `Op` definition reaches every surface. Python, MCP, `ph`, the CLI, the web route and the TUI are all derived from one registry, and core primitives register the same way a third party does. An `Operation` is a definition. A `Command` is one invocation, with an idempotency key. Ops are imperative and events are past tense. The extension's name is the namespace. A public op table has no abbreviations.

## Alternatives considered

| Alternative | Why not |
|---|---|
| Hand-written tools per surface | Agents and humans would slowly get different semantics, and an extension would need core edits |
| Middleware in the op path | Behavior would depend on interceptor order. An extension adds ops and daemons, and nothing intercepts another op |
| `Call` for one invocation | `call` means a model call. Training data must be able to trust that word |
| An `x.<extension>.` prefix | The extension's own name is already unique, because a collision is refused at load |
| `msg.*`, `chan.*` | Models read these names too. `message.*` and `channel.*` need no comment |
| Async ops that may do I/O | A transaction would wait on the world, which law 3 forbids |

## Consequences

- A disabled UI entry can carry `authorize`'s reason, because the palette and the check read the same table.
- An op's docstring is its tool description, so it must say what a refusal means and what to do next.
- `exposes` makes one op a command for agents and a query for everyone else. A query cannot emit, so the op's body must check `txn.me.kind`.
- The naming law is mechanical: the kernel checks it at load and at `emit`. `effect.uncertain` is the one event named for a state.
- The Python surface is `session.call`, which uses the word as a verb for running an op. That sits badly with the naming law and is unresolved.

## Evidence

- [Architecture sections 2, 6 and 17](../architecture.md), [brief section 11](../spec/BRIEF.md).
- [acp-mcp.md](../research/acp-mcp.md), section 4: `tools/list` may vary by authorization, which is what lets it be a filtered view of this table. [distributed-primitives.md](../research/distributed-primitives.md), Temporal row: the split between queries, which enter no history, and tracked writes.
