# RFC 0002: One journal per session folder

| | |
|---|---|
| Status | Accepted, 2026-11-02 |

## Summary

SQLite, one writer thread, WAL, `synchronous=FULL`, group commit, hybrid checkpoints

## Motivation

Every other decision rests on one write path. An ack must mean durable, 100 agents must not stall each other, and nothing may need an external service, such as a database or a queue. Two facts bound the choice: fsync cost varies by orders of magnitude between disks, and SQLite does not support WAL across hosts.

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
- The home directories of shared machines are often on refused filesystems, so the default root falls back to a local directory with a notice. A closed session is still portable.
- A commit without an ack is expected, so clients always retry under the same key.
- Readers take one short transaction per page, and tail followers share one read per pulse. A held cursor pins the WAL at 11.4 MiB/s, and a private read per follower does not keep up at 100.
- macOS is unmeasured and it is a required platform. Process crash is tested; power loss is not.

## Evidence

- A benchmark of a prototype of this design on 2026-11-02, not published, gave every number above. It drained up to 64 commands into one `BEGIN IMMEDIATE`, a `SAVEPOINT` each, with Python folds over eight view tables, 400-byte bodies and random 128-bit idempotency keys, under open-loop Poisson load whose ack latency counts from the intended send. It ran on 32 CPUs of a shared machine of two Xeon Platinum 8558, on local xfs over NVMe, with Python 3.12.13 and SQLite 3.53.1, and briefly on another shared machine and on Lustre. An `LD_PRELOAD` shim added a fixed delay to each sync to stand in for slower disks, which models no device queueing.
- What it found besides: paced at 500 events per second, the mean batch was 1.16 and the process used 0.08 cores. A rebuild of 100,180 events took 1.70 s in one transaction under `FULL`. 100 followers each reading on every pulse lagged 3,250 ms at the median and took 2.63 cores, and one shared read per pulse lagged 0.39 ms and took 0.14. Across 40 `kill -9` rounds of a writer that acks after commit, 226,807 acked commands left no violation, while a control that acked before commit left 363. The writer's resident memory was 30.8 MiB at 100,180 events and 31.7 MiB at 1,000,131. A Python `bind` allows a socket path of 107 bytes on Linux. Power loss and macOS were not tested.
- [Architecture sections 4, 5.1, 5.6 and 5.8](../architecture.md).
