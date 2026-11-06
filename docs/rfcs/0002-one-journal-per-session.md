# RFC 0002: One journal per session folder

| | |
|---|---|
| Status | Accepted, 2026-11-02 |

## Summary

SQLite, one writer thread, WAL, `synchronous=FULL`, group commit, hybrid checkpoints

## Motivation

Every other decision rests on one write path. An ack must mean durable, 100 agents must not stall each other, and the brief rules out external services. Two facts bound the choice: fsync cost varies by orders of magnitude between disks, and SQLite does not support WAL across hosts.

## Proposal

Each session folder holds one `journal.sqlite`. One writer thread, never the event loop, owns it. It runs WAL with `synchronous=FULL`, and group-commits up to 64 commands per fsync with no linger timer. Checkpoints stay off the commit path: a background thread runs `PASSIVE` every second, and `wal_autocheckpoint=16000` is the writer's hard cap. This is the hybrid. Live writers on network filesystems are refused. A folder per session makes isolation physical: a token resolves to one journal, no query can reach another, and export and deletion are a directory.

## Alternatives

| Alternative | Why not |
|---|---|
| One database with a session column | Isolation becomes a query discipline, and one writer would serialize unrelated sessions. Cheap cross-session listing is the one thing we give up |
| `synchronous=NORMAL`, or `OFF` for rebuilds | `NORMAL` saves 0.4 ms at p99 on NVMe and gives up power-loss durability, so an ack would promise less. `OFF` saves 0.32 s per 100,000 events and risks the file that holds the journal |
| One fsync per command | 9,731 events per second against 24,723 at batch 64 on NVMe. The ceiling at 64 is Python, not the disk |
| Default autocheckpoint | It runs inside `COMMIT`, so acks absorb its syncs: p99 96.8 ms against 46.7 ms hybrid, at an injected 20 ms sync |
| Background checkpoints alone | `PASSIVE` cannot reset the WAL under constant writes: 1,902.8 MiB at saturation against 63.5 MiB hybrid |
| Writer on the event loop | An fsync would stall every client, and a Platoon rollout worker with them |
| WAL on a network filesystem | One host passed the latency mark, but two hosts stalled up to 6.4 s, and a short pass is not evidence of safety. Refused on guarantee, not speed |

## Consequences

- Paced at 500 events per second, ack p99 was 2.8 ms on server NVMe against a 20 ms warning mark. A sync above about 20 ms misses the 50 ms mark whatever we do.
- The hybrid ran only in short runs, and injected delay does not model consumer SSD queueing, so its numbers are optimistic.
- Cluster home areas are the refused filesystems, so the default root falls back to a local directory with a notice. A closed session is still portable.
- A commit without an ack is expected, so clients always retry under the same key.
- Readers take one short transaction per page, and tail followers share one read per pulse. A held cursor pins the WAL at 11.4 MiB/s, and a private read per follower does not keep up at 100.
- macOS is unmeasured and it is a required platform. Process crash is tested; power loss is not.

## Evidence

- [journal-performance.md](../research/spikes/journal-performance.md), every number above. [Architecture sections 4, 5.1, 5.6 and 5.8](../architecture.md), [brief section 3](../spec/BRIEF.md).
