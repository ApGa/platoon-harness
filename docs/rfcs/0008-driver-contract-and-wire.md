# RFC 0008: Driver contract and JSON-RPC wire protocol

| | |
|---|---|
| Status | Accepted, 2026-11-02; superseded in part by [RFC 0030](0030-openhands-is-an-extra-of-the-sdk.md) |

**OpenHands in an environment of its own, and the lock and environment its consequences give it,
are superseded by [RFC 0030](0030-openhands-is-an-extra-of-the-sdk.md)**.

## Summary

Seven methods, JSON-RPC on stdio, OpenHands as a wire worker

## Motivation

Harnesses differ in control path, boundaries, approvals and what they reveal. A team needs a mix of them, and a driver of one's own needs a documented protocol and a conformance suite. One target, OpenHands, cannot live in a shared environment at all. So the contract must be small enough to implement in any language, and real enough that a first-party driver uses it.

## Proposal

A driver has seven methods: `describe`, `start`, `deliver`, `interrupt`, `answer`, `reconcile`, `stop`. There is one instance per agent. It reports through a closed vocabulary, and unknown frames become `native` plus a gap, never a log line. Another process speaks the same verbs as line-delimited JSON-RPC 2.0 on stdio, split on LF only, with logs on stderr. `protocol` is an integer, refused when unknown. `WireDriver(command)` is the only adapter, and OpenHands runs through it in its own environment. Capabilities are declared, then verified: `check_driver` tests them against a loopback model, and levels are computed, never claimed.

## Alternatives

| Alternative | Why not |
|---|---|
| ACP as the driver contract | ACP v1 has no sender identity, no retry-safe prompt and no model-call attribution, and its default injection boundary is the next turn. It is one driver here |
| A bespoke JSONL envelope | JSON-RPC 2.0 already defines ids, errors and notifications, and it is what ACP and MCP authors know |
| Six methods, without `reconcile` | After a crash a `deliver` or `answer` could only be repeated or abandoned, with no way to ask whether it landed |
| A `Driver` factory plus a separate `Link` | Two protocols for one relationship, when an instance per agent is enough |
| OpenHands in the runtime's process | `openhands-sdk` 1.59.0 is unsatisfiable beside `mcp` 2.3.0 or ACP 1.0.0rc3, unpinned extras silently resolve versions as old as 1.44.1, and its import weight does not belong in the runtime |
| PTY scraping as an integration path | Rendered text cannot yield identity. It stays an explicit degraded fallback |
| Believing declared capabilities | "Connected" proves nothing: most harnesses hide MCP tools by default |

## Consequences

- A first-party driver will use the custom-driver path, so it cannot rot unnoticed once that driver lands. No driver exists yet. It needs its own lock and environment.
- A simple one-shot CLI needs no code: `exec` runs it from config and it coordinates through `ph`.
- A report vocabulary that is too small shows up loudly, as `native` frames and gaps.
- Seven methods are unproven until pi and an ACP agent run on them. An eighth method, or normal work leaning on `native`, would mean the contract is wrong.

## Evidence

- What ACP cannot express: no mid-turn message, no sender identity, no idempotent prompt and no model-call attribution in stable v1.
- Design-phase research, not published, with `uv pip compile`: `openhands-sdk` 1.59.0 cannot share an environment with `mcp` 2.3.0 or ACP 1.0.0rc3, and unpinned it resolves silently to older versions. Most harnesses hide MCP tools from the model by default, so a check must see the tool in the first model request. [compatibility.md](../reference/compatibility.md) holds what each harness does. [Architecture section 9](../architecture.md).
