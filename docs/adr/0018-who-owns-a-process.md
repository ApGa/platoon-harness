# 0018. Who owns a process

**Status:** Accepted, 2026-11-02. Its row on an environment marker, and its consequence for `setsid`, are superseded by
[0021](0021-what-a-harness-leaves-behind.md).

## Context

Architecture section 5.4 says no process can exist unrecorded, and that recovery kills a recorded group only if it is still ours.
Both are hard at the edges. A crash can fall between fork and record. A pid can be reused. A harness can exit and leave a forked child
holding its group and its pipes. `asyncio.subprocess.Process.wait` does not return while any pipe is open, so that child can also hide
the exit.

## Decision

- **The launcher records, and `sh` waits for it.** The child starts as `sh -c 'read -r go && exec "$@"'`. Python reads its pid and start
  time, writes `proc.json` with an fsync, then sends one line on stdin. If we die first, `read` fails on EOF and the harness never
  execs. `read` takes one byte at a time from a pipe, so stdin is the harness's own afterwards.
- **A start time is what tells two holders of a pid apart.** On Linux that is the boot id plus field 22 of `/proc/<pid>/stat`, and on macOS
  `ps -o lstart=`. Both survive exec, and neither depends on a clock that can step.
- **Only a leader with the recorded start time proves a group is ours.** A live process with another start time means the pid was
  reused, and a pid is reusable only once the group is empty, so nothing of ours is left. With the leader gone and members alive the group
  is `unproven`: those members may be ours, or may belong to a stranger that reused the pid, formed a group and exited. Recovery leaves it
  alone and names it. During a live run we have owned the group throughout, so `stop` ends it.
- **`loop.subprocess_exec` with `SubprocessStreamProtocol`,** whose `process_exited` reports the leader, not the pipes.
- **One task owns the group.** A closing loop cancels it, and it kills the group on the way out. A finalizer covers what no loop can.

## Alternatives considered

| Alternative | Why not |
|---|---|
| `sh` writes the record | It would parse `/proc` or `ps` in shell, and a crash before the write leaves a harness running. This way a crash leaves nothing |
| `preexec_fn` | It runs Python between fork and exec with a writer thread alive, which the documentation warns can deadlock |
| An environment marker read from `/proc/<pid>/environ` | It would prove a leaderless group on Linux, at the price of a `/proc` scan with no macOS equivalent, for a case that only leaves a process running, loudly |
| A `sleep` sentinel holding the group | One more process per agent, and it must know when to exit, which is the original problem |
| Holding the leader as a zombie to keep the pid | It does not survive the crash it would be for |
| `PR_SET_PDEATHSIG` | Linux only, cleared across some execs, and it needs `preexec_fn` |

## Consequences

- After a crash a harness's forked child can survive, with its leader gone and a named `unproven` record. The cost of being wrong the
  other way is killing a stranger, so the leak is the right side of this.
- A process that leaves the group by `setsid` escapes `stop`. Only a cgroup would hold it, and that is not available to us everywhere.
- A group of only zombies waits on its parent's reaper, so `stop` bounds its verification and raises if SIGKILL did not finish the job.

## Evidence

- `tests/unit/drivers/test_process.py`: a child that ignores TERM, one that forks and outlives its leader, pid reuse, a leaderless group,
  a closed loop. Linux only so far: macOS is written from the man page and has not run.
- CPython 3.12 `asyncio/base_subprocess.py`, where `_wait` resolves in `_call_connection_lost`, after every pipe disconnects.
- [Architecture sections 5.4 and 5.7](../architecture.md).
