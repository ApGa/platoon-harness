# 0007. Topology as grants over relations

**Status:** Accepted, 2026-11-02

## Context

The owner asked for communication primitives and topologies inspired by distributed computing, and easy to configure. Of the systems surveyed, none combines concurrent agents, dynamic membership and server-enforced edges. Most put control flow in config or hide a central scheduler. Agents here spawn and retire, so a graph of named agents is stale at once. And a wake costs money, so who may wake whom is a resource grant.

## Decision

A topology is a set of grants over relations such as `parent` and `children`, evaluated on the live graph and compiled to one `(who, ops, on)` table. It holds no control flow. A preset is a macro: `team show --resolved` prints valid input, and the manifest stores and hashes that form. Mixing is a commutative union, so there is no `deny`, and two different definitions of one channel are a load error. Delivery strength is a ladder, `pull < next-turn < wake < steer`, set per channel on the reader's side. `steer` asks for the earliest boundary the harness has and degrades visibly.

## Alternatives considered

| Alternative | Why not |
|---|---|
| A graph of named agents | Config would be rewritten at every spawn. `worker: [parent, children]` stays true as agents come and go |
| Control flow in config | A second, weaker language. Control flow belongs in a Python program holding a `program` principal |
| An LLM speaker selector | A central scheduler in disguise, with one speaker at a time |
| `deny` rules | They make the union depend on order. Absence already means deny |
| Sender-chosen wakes | A sender could spend the reader's budget. Codex puts `trigger_turn` on the message; DeLM decides on the reader's side, and that is the side we chose |
| Presets as scheduler modes | A preset that cannot be written out by hand is a mode. One that behaves differently from its expansion is a bug |

## Consequences

- Grants name ops by glob, so an extension's op is authorized with no new vocabulary.
- `team check` can refuse a bad team before any cost, such as recursive `may_spawn` without `max_depth`.
- One ladder hides real differences: pi steering enters after the assistant turn, and Codex needs a matching turn id. The capability table records them.
- `next`, `prev` and `group:x` have no evaluator in `authorize`, so `grant.add` refuses them `unsupported`. Compilation expands them over roles instead.
- Reachability at 100 agents depends on `path` making `descendants` a prefix test. Mesh reply loops are [0012](0012-waiting-and-the-monitor.md)'s problem.

## Evidence

- [distributed-primitives.md](../research/distributed-primitives.md), bottom line and sections 2, 3 and 4.
- [swarm-patterns.md](../research/swarm-patterns.md): the patterns the presets must express. [Architecture section 8](../architecture.md), [the owner's addendum to the brief](../spec/BRIEF.md).
