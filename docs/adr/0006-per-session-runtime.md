# 0006. A runtime per session, with ownership modes

**Status:** Accepted, 2026-11-02

## Context

The brief asks for an in-process SDK and a supervised service with the same semantics. A UI disconnect must not kill a service-owned session, and an embedded runtime must have a documented shutdown. Terminal users expect closing a window to leave agents working. A script expects leaving a block to stop what it started. Starting or restarting agents can spend money, so no read may do it.

## Decision

One runtime process runs per live session. It holds `lock` and binds the control socket in every mode, so modes differ only in who keeps it alive: your script, a detached runtime the TUI starts the way tmux starts its server, or a supervisor under `serve`. `Session.start(team)` makes you the owner, and leaving runs the shutdown contract. `Session.attach(name)` gives the same class as a guest in every mode, and leaving only disconnects. **Attach never has side effects.** With no live runtime it gives read-only history. Only `resume` restarts anything.

## Alternatives considered

| Alternative | Why not |
|---|---|
| A central daemon and session registry | One more process to upgrade, secure and recover, and a registry that can disagree with the disk. A folder scan plus `flock` answers the same questions |
| Separate embedded and service implementations | The brief forbids it, and the semantics would diverge |
| `attach` starts a runtime when the lock is free | Reading history would relaunch agents and could spend money. Recovery must be something you ask for |
| `Session.open` or `Session(team)` | Neither says that agents start or that leaving stops them, and `Kernel.open` already means a different thing |
| `embedded()` and `attach()` | `embedded` names a mechanism, not what the caller is doing. `start` and `attach` read as the two things a user does |
| The socket inside the session folder | A Python `bind` allows 107 bytes on Linux, and a deep folder exceeds that. The path is a short hash in a 0700 runtime directory |

## Consequences

- A script's session and a training rollout can both be watched with the same call.
- Listing sessions scans folders, and `flock` is the liveness check. There is no index to go stale.
- A detached runtime outlives its client by design, so stopping it is always an explicit op.
- A Platoon function harness runs in the rollout worker's event loop, so there the process is the worker's. Several sessions can share it, and that case is unmeasured.
- Orphan cleanup after `kill -9` with real harness children is designed but not yet tested.

## Evidence

- [Architecture section 4](../architecture.md), [brief section 3](../spec/BRIEF.md).
- [journal-performance.md](../research/spikes/journal-performance.md), result 9 on socket paths and the unknown on many sessions in one process. [acp-mcp.md](../research/acp-mcp.md), "What ACP cannot express": the runtime owns the connection, and UIs attach to the runtime.
