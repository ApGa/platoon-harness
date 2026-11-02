# 0013. Platoon bridge on the function-harness seam

**Status:** Accepted, 2026-11-02

## Context

Exact model calls can only come from Platoon's gateway, and training must run the same sessions as everyday use, or its results describe a different system. Platoon's own multi-agent types (`AgentGraph`, `RewardEvent`, attribution levels) are draft at 0.5, so they are not targets. Platoon requires one root, while a mesh has none. Minting has no idempotency, no fork and no depth policy.

## Decision

The bridge is an optional extension, `platoon-harness-platoon`, on Platoon's stable function-harness and program seam. The kernel has no Platoon branch: standalone and managed differ only in the `Authority` object and the role's trainable profile. Our topology check runs first and Platoon's refusal wins.

- **Two admission routes.** Tree children use `ctx.agents.spawn` with a member harness, which gives forks, grading and depth. Peers with no fork use `POST /v1/platoon/agents`. Mint is never retried.
- **Root rule.** A single-entry tree uses `ctx.endpoint`, which preserves RAO's depth and row shape. Mesh and git-swarm use a zero-call root, labelled as a mapping artifact. The root samples the default policy, so `team check --trainable` refuses a mismatch.

## Alternatives considered

| Alternative | Why not |
|---|---|
| A TOML `HarnessSpec` | It runs no program, so there are no finalizers, children share the episode reward, and `spawn` cannot target it |
| A custom `rollout:` or `RolloutWorkflow` | The first relies on internal `proxy_interactions`. The second bypasses group credit and must build datums itself |
| One route for every child | Mint alone loses forks and grading, which only the spawn route gives. Spawn alone makes a mesh invent parentage, because a peer has no parent to fork from |
| An `if platoon` path in the kernel | Two execution systems, and competing authorities for spawn, identity and budget |
| Everyday traffic through the gateway | It buffers streams, needs API keys rather than plan logins, and keeps no request |

## Consequences

- A mesh's root is visibly an artifact, not a privileged agent. Message edges stay in our journal as non-tree evidence.
- The default mint cap of 64 is below the 100-agent case, so recipes must set `PLATOON_MAX_MINTED_AGENTS`.
- G1, G3, G4 and G5 block token-level and graph credit and go upstream as amendments. Until then provenance is a labelled out-of-band export. A session inside `rollout_isolation: process` is untested.

## Evidence

- [platoon-training.md](../research/platoon-training.md), sections 5, 6 and 7: identity, seams A to F, gaps G1 to G12.
- [platoon-platform.md](../research/platoon-platform.md): `ctx.agents.spawn`, packaging, gateway limits. [Research index](../research/README.md), claims 6 and 7. [distributed-primitives.md](../research/distributed-primitives.md), section 4.10. [Architecture section 14](../architecture.md).
