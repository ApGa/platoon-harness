# RFC 0010: Provenance: backward references, bounds, evidence and gaps

| | |
|---|---|
| Status | Accepted, 2026-11-02; superseded in part by [RFC 0036](0036-one-ref-names-what-a-model-is-shown.md), [RFC 0037](0037-an-offer-is-confirmed-only-by-its-harness.md) and [RFC 0038](0038-provenance-is-answered-from-the-record.md) |

**Superseded in part by [RFC 0036](0036-one-ref-names-what-a-model-is-shown.md)**, on refs and
citations, [RFC 0037](0037-an-offer-is-confirmed-only-by-its-harness.md), on confirmations, the launch offer, calls and gaps, and
[RFC 0038](0038-provenance-is-answered-from-the-record.md), on the queries, which answer one hop at a time.

## Summary

Backward references, context bounds, sole writers, three axes, gaps, `Seen`, `NotSeen` or `Unknown`

## Motivation

Credit estimators and a human asking "why" both need dependencies between actions. Agent interaction has cycles, and credit needs a partial order. We see only part of what happens: any harness with a shell reads things we never observe. A claim, an observation and an opinion mean different things, and a yes-or-no answer about exposure would be false whenever we do not know.

## Proposal

- **References point backward.** `cause`, `based_on` and every ref resolve to a lower `seq`, so the time-expanded graph is acyclic by construction. The graph is not stored: edges are the references events already hold.
- **Context version gives bounds.** Offers and compactions advance `context/<agent>`, and every agent event records it. That is an upper bound on what an action could have known, and `delivered` edges are a lower bound. The distance between them is measured uncertainty.
- **Four evidence types, each with a sole writer:** observed exposure (courier and agent-read ops), declared dependency (the op's actor), judged attribution (a `judge`), validated intervention (a `program`). **Three axes never merge:** evidence type, attribution of a model call to an agent, and assurance of an actor to a credential.
- **Gaps are records.** Standing gaps come from `coverage`, and incident gaps are events of a closed set. `exposure` answers `Seen`, `NotSeen` or `Unknown`, and `lineage` returns paths with the gaps that qualify them.

## Alternatives

| Alternative | Why not |
|---|---|
| `exposed: bool` | It cannot say unknown, and a missing edge is not missing influence |
| A stored edge table | A second structure to keep in step, for edges the events already hold |
| One confidence score | It hides why. A reader could no longer tell a claim from an observation |
| Linking tools to model calls by timing | Fabrication. Only real anchors count: `claudecode/toolUseId`, `llm_response_id`. Codex's `callId` joins to the `exec` script, not to a model call |
| Editing an event when a late join arrives | Events are immutable. `call.joined` is a new event citing both sides, with its quality |

## Consequences

- An agent's read is a journaled command. That is the price of exposure evidence.
- A harness with a shell is blind to `shell_reads` for life, so a negative answer there is usually `Unknown`, not `NotSeen`.
- Whether the bounds are tight is unverified. It needs a logged-prompt test on real harnesses.

## Evidence

- [platoon-training.md](../research/platoon-training.md), section 3. [acp-mcp.md](../research/acp-mcp.md), "Call anchors".
- [tools-and-parking.md](../research/spikes/tools-and-parking.md): 0 of 2 Codex `callId`s equalled the model's id, and 8 of 8 Claude Code anchors did. [distributed-primitives.md](../research/distributed-primitives.md), vector clocks row. [swarm-patterns.md](../research/swarm-patterns.md): `informed_by` kept apart from Git ancestry. [Architecture section 11](../architecture.md).
