# RFC 0007: Topology as grants over relations

| | |
|---|---|
| Status | Accepted, 2026-11-02 |

## Summary

Grants over relations, presets as macros, no `deny`, delivery set on the reader's side

## Motivation

Teams need communication primitives and topologies inspired by distributed computing, and easy to configure. Of the systems surveyed, none combines concurrent agents, dynamic membership and server-enforced edges. Most put control flow in config or hide a central scheduler. Agents here spawn and retire, so a graph of named agents is stale at once. And a wake costs money, so who may wake whom is a resource grant.

## Proposal

A topology is a set of grants over relations such as `parent` and `children`, evaluated on the live graph and compiled to one `(who, ops, on)` table. It holds no control flow. A preset is a macro: `team show --resolved` prints valid input, and the manifest stores and hashes that form. Mixing is a monotonic, commutative union, so there is no `deny`, and two different definitions of one channel are a load error. Delivery strength is a ladder, `pull < next-turn < wake < steer`, set per channel on the reader's side. `steer` asks for the earliest boundary the harness has and degrades visibly.

## Alternatives

| Alternative | Why not |
|---|---|
| A graph of named agents | Config would be rewritten at every spawn. `worker: [parent, children]` stays true as agents come and go |
| Control flow in config | A second, weaker language. Control flow belongs in a Python program holding a `program` principal |
| An LLM speaker selector | A central scheduler in disguise, with one speaker at a time |
| `deny` rules | Deny-wins is commutative, but it is not monotonic: adding a fragment could take authority away, so nothing could be read as a plain sum. Absence already means deny |
| Sender-chosen wakes | A sender could spend the reader's budget. Codex puts `trigger_turn` on the message; DeLM decides on the reader's side, and that is the side we chose |
| Presets as scheduler modes | A preset that cannot be written out by hand is a mode. One that behaves differently from its expansion is a bug |

## Consequences

- Grants name ops by glob, so an extension's op is authorized with no new vocabulary.
- `team check` can refuse a bad team before any cost, such as recursive `may_spawn` without `max_depth`.
- One ladder hides real differences: pi steering enters after the assistant turn, and Codex needs a matching turn id. The capability table records them.
- `next`, `prev` and `group:x` have no evaluator in `authorize`, so `grant.add` refuses them `unsupported`. Compilation expands them over roles instead.
- Reachability at 100 agents depends on `path` making `descendants` a prefix test. Mesh reply loops are [RFC 0012](0012-waiting-and-the-monitor.md)'s problem.

## Evidence

- Design-phase research, not published, a study of distributed primitives and of how agent frameworks declare topology: a topology is a set of grants over relations, not a graph of agents; one authorization function decides every verb in the transaction that records it; and collectives are library code over the core operations.
- The patterns the presets must express: DeLM's board, GitSwarm's worktrees and Agensh's notices (compatibility.md, Upstreams). [Architecture section 8](../architecture.md).
