# Spike: single-writer SQLite journal performance and durability

Run 2026-11-02. Prototype and benchmark are throwaway and are not in this repository.

## Question

Are WAL, `synchronous=FULL` and a group-committing writer thread acceptable as designed? What batch size and pragmas should the implementation use, and what must the docs promise on each platform? **Answer:** yes on local storage, paced p99 2.8 ms against a 20 ms warning mark, with four changes: move checkpoints off the commit path, share one tail read across followers, enforce a reader rule, and rebuild without `synchronous=OFF`.

## Method

Prototype as specified: writer thread, drain up to 64 commands, `BEGIN IMMEDIATE`, a `SAVEPOINT` per command, dedupe, a handler that reads a view and appends 1-3 rows, Python folds over 8 view tables, `COMMIT`, then futures resolved by one `call_soon_threadsafe` per batch. Bodies are 400 bytes. Idempotency keys are random 128-bit values, the worst case for that index.

**"500 events per second" is 250 commands per second,** at a mean of 2 events per command. The 1,000 ev/s row covers the other reading. Load is open-loop Poisson. Ack latency runs from the intended send time, so backlog is not hidden. `svc` runs from the actual submit and excludes event-loop timer jitter.

Compute node: 32 CPUs of a shared node, 2x Xeon Platinum 8558, node-local xfs on Micron 7450 NVMe. **Its `/tmp` is tmpfs, not a disk.** Login node: shared by about 47 users, 2x Xeon Platinum 8468, `/tmp` is xfs on a RAID-controller LUN. Lustre: cluster home and group areas, mounted with `flock`. Types were detected with `statfs` and confirmed in mountinfo. Python 3.12.13, SQLite 3.53.1, `THREADSAFE=1`, Linux 5.14. Two jobs, plus short login runs.

Both local disks are server hardware with near-instant flush, so neither stands in for a laptop. To model slower storage, an `LD_PRELOAD` shim added a fixed delay to each `fsync` and `fdatasync` ("injected" below). It does not model device queueing. Its counter confirms FULL really syncs: 1.04 syncs per commit, against 0.04 for NORMAL.

## Results

**1. Paced load, 100 simulated agents.** All latencies are in ms. Mark: p99 above 20 warns, above 50 forces a change.

| Storage | Load, seconds | Ack p50 / p95 / p99 / max | `svc` p99 | Commit p50 | Verdict |
|---|---|---|---|---|---|
| Compute NVMe | 500 ev/s, 60 | 1.3 / 2.2 / **2.8** / 14.7 | 1.5 | 0.31 | Pass |
| Compute NVMe | 1,000 ev/s, 30 | 1.2 / 2.0 / 2.4 / 3.7 | 1.6 | 0.21 | Pass |
| Compute NVMe, NORMAL | 500 ev/s, 30 | 0.9 / 1.6 / 2.4 / 4.0 | 1.5 | 0.04 | FULL costs 0.4 at p99 |
| `/dev/shm` floor | 500 ev/s, 60 | 0.9 / 1.6 / 2.3 / 3.4 | 0.7 | 0.03 | No-fsync floor |
| Login `/tmp` | 500 ev/s, 60 | 1.0 / 2.0 / 4.8 / 22.1 | 3.8 | 0.17 | Pass, noisy host |
| Lustre, compute | 500 ev/s, 15 | 2.4 / 4.1 / 9.6 / 12.9 | 8.7 | 1.05 | Pass |
| Lustre home, login | 500 ev/s, 10 | 2.6 / 5.6 / 9.1 / 19.8 | 8.3 | 1.12 | Pass |

Mean batch was 1.16, so group commit is idle at design load. Process CPU was 0.08 cores. Most of the p99 on fast disks is event-loop timer jitter, as the floor shows. With Python CPU on the event loop at 50% and 90% of a core, p99 was 4.1 and 5.9. A 0.5 ms switch interval changed nothing (4.0, 5.5).

**2. Saturated load, closed loop, 10 s.** Sustained events per second.

| Batch cap | Compute NVMe | `/dev/shm` | Login `/tmp` | Injected 20 ms sync |
|---|---|---|---|---|
| 1 (one fsync per command) | **9,731** | 15,942 | 6,953 | - |
| 16 (8: 17,079; 32: 21,202 on NVMe) | - | - | - | 1,378 |
| 64 | **24,723** | 28,269 | 17,212 | 4,779 |
| 256 (128: 24,457 on NVMe) | 26,328 | - | - | 12,811 |

Group commit gains 2.5x on NVMe. The ceiling is Python, not the disk: the writer runs at 84% of a core and `/dev/shm` beats NVMe by only 14%. Lustre reached 12,910 at batch 64 (6 s). Login runs were 8 s.

**3. Filesystems.** `fdatasync` of an appended 4 KiB block, p50 / p99: compute NVMe 0.036 / 0.063, login `/tmp` 0.073 / 0.150, tmpfs 0.000 / 0.000, Lustre 0.62 / 5.19 from compute and 0.62 / 1.33 on home from login.

**WAL on Lustre is a negative result against our expectation.** One host passes the latency mark. Two hosts on one file (login and compute) corrupted nothing here, but they stalled.

| Test | Acked | Lost | `integrity_check` | Reader anomalies | Rate, worst stall |
|---|---|---|---|---|---|
| 1 writer per host, WAL, 10 s | 3,478 | 0 | ok | not checked | 348/s, 1.9 s |
| 3 writers + 1 reader per host, autocheckpoint 20, 20 s, two runs | 2,352 | 0 | ok | 0 in 2,118 reads | 59/s, **6.4 s** |
| 1 writer per host, DELETE journal, 10 s | 1,733 | 0 | ok | not checked | Compute 1,732, login 1 (`database is locked`) |

We did not establish why it held. SQLite states that "WAL does not work over a network filesystem". This mount has coherent `flock`. Other mounts and NFS were not available. A short pass is not evidence of safety.

**Detection.** Use `statfs(2)` first, because the kernel resolves the path, including symlinks and bind mounts. Use `/proc/self/mountinfo` for FUSE subtypes (`fuse.sshfs`, `fuse.glusterfs`), matching field 3 against `st_dev`, not by path prefix. The stdlib has no `statfs`, so it needs `ctypes`:

```python
buf = ctypes.create_string_buffer(256)                  # 64-bit Linux: f_type is the first long
ctypes.CDLL(None, use_errno=True).statfs(os.fsencode(existing_dir), buf)
magic = int.from_bytes(buf.raw[:8], sys.byteorder) & 0xFFFFFFFF
```

Refuse: Lustre `0x0BD00BD0`, NFS `0x6969`, CIFS `0xFF534D42`, SMB2 `0xFE534D42`, SMB `0x517B`, GPFS `0x47504653`, BeeGFS `0x19830326`, Ceph `0x00C36400`, PanFS `0xAAD7AAEA`, GFS2 `0x01161970`, OCFS2 `0x7461636F`, AFS `0x5346414F`, kAFS `0x6B414653`, ACFS `0x61636673`, vboxsf `0x786F4256`, 9p `0x01021997` (WSL `/mnt/c`; coreutils calls it local, but it carries host shares). FUSE is `0x65735546`: consult the subtype. Exercised live: xfs, tmpfs, Lustre, `fusectl`, `proc`, a path that does not exist yet (walk up to the nearest ancestor), and a symlink from tmpfs into Lustre. statfs and mountinfo agreed. The other magics come from Linux `magic.h` and coreutils `stat.c` and were not exercised. macOS: `statfs(2)` gives `f_flags & MNT_LOCAL` (`0x1000`) and `f_fstypename`, with `statfs$INODE64` on x86-64. Written from the man page and **not run**.

**4. Rebuild, 100,180 events, compute NVMe.** All modes matched the live views. FULL committing every 64: 2.20 s. **FULL in one transaction: 1.70 s** (58,976 ev/s). NORMAL: 1.49 s. OFF: 1.38 s. OFF with 256 MiB cache: 1.37 s. One transaction peaked at 9.5 MiB of WAL. Setting `synchronous` inside a transaction raises `Safety level may not be changed inside a transaction`, so it must precede `BEGIN`.

**5. Slow reader, 500 ev/s, compute NVMe, reader active 30 s, then 10 s without it.**

| Reader | WAL peak MiB | WAL at end MiB | Ack p99 / max | Page read p50 / p99 |
|---|---|---|---|---|
| None | 4.0 | 4.0 | 2.6 / 3.9 | - |
| Short transaction per page | 4.0 | 4.0 | 2.6 / 3.7 | 0.11 / 0.48 |
| One long transaction, limit 64 MiB | 340.6 | **64.0** | 2.5 / 22.2 | 0.03 / 0.26 |
| One long transaction, no limit | 341.0 | **341.0** | 2.5 / 13.7 | 0.03 / 0.25 |

Checkpointing starves completely: up to 84,100 frames unbackfilled, at **11.4 MiB/s, or 40 GiB per hour of pinning**. It recovers fully when the reader ends, at the cost of one stall. That rate is also the write volume: about 23 KiB per event at design load, since each small commit rewrites about 14 pages, against 729 bytes per event at rest. **A half-read Python cursor pins the WAL too, while `Connection.in_transaction` says `False`.** `wal_checkpoint(TRUNCATE)` returned busy until `cursor.close()`.

**6. Followers: 100 cursors at 500 ev/s, 30 s, compute NVMe, in the writer's process.** With no followers: ack p99 2.56, 0.074 cores.

| Fan-out | Ack p99 / max | Process cores | Lag p50 / p99 | Reads/s | Behind at end |
|---|---|---|---|---|---|
| Own read on each pulse | 10.6 / 17.5 | **2.63** | **3,250 / 6,358** | 101 | 3,008 events |
| Own read, 20 Hz | 9.1 / 17.5 | 2.59 | 787 / 2,059 | 154 | 935 events |
| One shared read per pulse, real sockets | **2.7 / 4.4** | **0.14** | **0.39 / 0.85** | 218 | 0 |
| One shared read, 20 Hz, real sockets | 2.6 / 3.5 | 0.09 | 48 / 52 | 20 | 0 |

A private read per follower does not keep up and slows the writer: handler time rose from 0.12 to 1.68 ms per command. The shared read adds 0.2 ms to ack p99 and 0.07 cores. A second process drained the sockets.

**7. Memory, writer process only, 8 MiB page cache, `mmap_size=0`.** RSS was 30.8 MiB at 100,180 events and 31.7 MiB at 1,000,131, reached in 41.8 s. The DB grew to 695 MiB and the WAL stayed at 5 MiB. The 0.9 MiB drift is about the size of the prototype's own stats list (not isolated). Throughput fell 13%. At 100,000 events a 2 MiB cache gave 24.4 MiB RSS and 64 MiB gave 90.8 MiB, with no throughput change.

**8. Crash, `kill -9` of a writer that acks over a pipe after commit.** **This tests the process-crash promise only. Power loss was not tested,** and this test cannot tell FULL from OFF, because the page cache survives `kill -9`.

| Run | Rounds | Acked | Rejected | Retries deduped | Violations | First open, max ms |
|---|---|---|---|---|---|---|
| Compute NVMe, FULL | 20 | 131,506 | 8,227 | 3,835 | **0** | 2.2 |
| Login `/tmp`, hybrid checkpoints | 20 | 95,301 | 5,968 | 3,837 | **0** | 3.1 |
| **Negative control:** ack before commit | 10 | 26,964 | 1,691 | 1,340 | **363, as intended** | 0.9 |

After each kill: every acked command present with all rows, nothing from rejected commands, no partial command, view totals equal the events, `integrity_check` ok. The hybrid run left 60 commands committed but never acked. Recovery scales with the WAL: 84 ms at 302 MiB, 282 ms at 1,005 MiB, 0 violations.

**9. Control socket path.** Python `bind` allows **107 bytes**; 108 gives `OSError: AF_UNIX path too long`. Raw `bind(2)` allows 108 without a NUL; 109 gives `EINVAL`. `/proc/self/fd/N/c.sock` worked from 345- and 409-byte directories, Linux only. Abstract names work but have no file permissions. This spike's own 117-byte scratch directory failed every length, so the limit is reachable. macOS is 104 by its headers, so 103 usable (not run).

**Checkpoint placement under slow sync (injected).** Ack p99 at 500 ev/s, 20-30 s. Default autocheckpoint runs inside `COMMIT`, so acks absorb its syncs: commit p99 was 61.7 at a 20 ms sync.

| Sync delay | Auto 1,000 | Auto 4,000 | After acks, on writer | Background | **Hybrid 16,000** |
|---|---|---|---|---|---|
| None | 2.7 | 2.5 | 2.6 | 2.5 | 6.7 (login, noisy) |
| 5 ms | **23.8** (warn) | 17.7 | 20.0 | 12.4 | **17.1** |
| 20 ms | **96.8** (forced) | 80.8 | 91.4 | 43.0 | **46.7** |
| WAL peak at saturation, MiB | 4.8 | - | 161.7 | **1,902.8** | **63.5** |

Background alone is unsafe: PASSIVE cannot reset the WAL while writes keep arriving. Hybrid is that thread plus `wal_autocheckpoint` as a hard cap. It ran on the login node, where auto 1,000 gave 25.3 and 97.5, matching compute. Its max stayed near 104 at 20 ms. Ack p99 is at least twice the sync time, so a sync above about 20 ms misses the 50 ms mark whatever we do. At 1 ms and 2 ms, p99 was 4.2 and 6.8 with checkpoints after acks.

## Verdict

1. **Accept `synchronous=FULL` with group commit on local storage.** NORMAL saves 0.4 ms at p99 and gives up power-loss durability.
2. **Batch cap 64.** Fast storage gains little above it, and at an injected 20 ms sync it still gives 9x the design load. No linger timer: the sync already forms batches.
3. **Pragmas:** `journal_mode=WAL`, `synchronous=FULL`, `cache_size=-8192`, `mmap_size=0`, `temp_store=MEMORY`, `wal_autocheckpoint=16000`, `journal_size_limit=67108864`. On macOS also `fullfsync=ON`, `checkpoint_fullfsync=ON`; both default off.
4. **Checkpoint from a background thread:** PASSIVE every second on its own connection, with `wal_autocheckpoint` as the writer's cap. Never the thread alone.
5. **Readers take one short transaction per page:** `fetchall()`, or `fetchmany()` then `close()`. No held cursors. Alarm when `log - checkpointed` from the checkpoint thread passes 16,000 frames, because `in_transaction` cannot see a pin. A long export takes a copy, not a held snapshot.
6. **Followers:** one shared read per pulse into a bounded tail; followers at the tail take a slice. Lagging followers page by SQL through a small bounded pool. Leave the GIL switch interval alone.
7. **Rebuild with FULL in one transaction.** OFF saves 0.32 s per 100,000 events and risks a file that also holds the journal.
8. **Refuse network filesystems by default, on guarantee and not on speed.** SQLite does not support WAL across hosts, and two hosts stalled up to 6.4 s here. Do not tell users it corrupts on Lustre: we did not see that. The refusal must name a local state directory, since cluster home areas are exactly these filesystems. Warn on unknown types.
9. **Warn on tmpfs:** a session there survives a process crash but not a reboot.
10. **Socket rule:** never derive the path from the session directory. Bind at `<runtime dir>/<short hash of session id>.sock` in a 0700 directory, from `XDG_RUNTIME_DIR` or a short per-user fallback. Check `len(os.fsencode(path)) <= 103` first. The session directory stores a pointer. No abstract names.
11. **Clients retry with the same idempotency key after any missing ack.** Commit without ack was observed and is expected.

| Platform | The docs say an ack means | Status |
|---|---|---|
| Linux, local disk | Synced. Survives process crash, and power loss if the device honors flush | Process crash tested, power loss not |
| macOS, local disk | The same, only with `fullfsync=ON`. Plain `fsync` does not flush the drive cache | Not run |
| tmpfs | Survives process crash only. Lost on reboot | Warned |
| Network filesystem | Refused | SQLite does not support WAL across hosts |
| WSL | Linux rules inside the distro filesystem; `/mnt/c` is 9p and refused | Not run |

## Unknowns

- **macOS is unmeasured, and it is a required platform.** Real `F_FULLFSYNC` latency decides this: past about 20 ms it misses the 50 ms mark. Run this benchmark on a real Mac before Milestone 1 closes.
- **Many sessions in one process.** Each has a writer thread and they share the GIL. Only one session was tested.
- **Lagging followers at scale.** All followers stayed at the tail, so the SQL path for many reconnecting clients is unmeasured.
- **Hybrid checkpoints** ran only in short login runs, and injected delay does not model consumer SSD queueing, so the background and hybrid columns are optimistic.
- **Power loss,** devices that ignore flush, and other filesystems: NFS, CIFS, GPFS, BeeGFS, and Lustre without `flock`.
- **Payloads above 4 KiB, cold-cache rebuild, and soak** beyond 60 s. Sustained 500 ev/s writes about 0.9 TiB per day, so SSD wear needs a look if real load gets near that.
