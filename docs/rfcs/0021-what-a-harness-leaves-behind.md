# RFC 0021: What a harness leaves behind

| | |
|---|---|
| Status | Accepted, 2026-11-03 |

## Summary

A harness's own `TMPDIR` marks what it started, so `stop` and `reap` end it whichever group it left for

## Motivation

[RFC 0018](0018-who-owns-a-process.md) holds a harness by its process group, and leaves a process that leaves the group to escape `stop`.
It weighed an environment marker read from `/proc` and set it aside, for a case it took to be rare and loud. Real harnesses showed the
case is neither. A model's `npm run dev &` under Claude Code or pi leads a group of its own, since each harness runs a tool in a group of
its own, and it outlived `stop` and the session with no word in the journal. A `setsid` child under pi did the same. The contract says
`stop` leaves no process behind, and `check_driver` passed while it did not hold.

## Proposal

- **A harness's own `TMPDIR` is its marker.** `harness_env` already gives each harness `TMPDIR=<agent folder>/tmp`, and everything it
  starts inherits that, whichever group or session it leaves for. Nothing else carries that path.
- **`stop` ends the group, then what carries the marker.** After the group has gone, `Process.stop` scans `/proc` for this user's
  processes whose environment holds it, sends `SIGTERM`, waits what is left of twice `grace`, then `SIGKILL`.
- **`reap` does the same after a crash,** for the agent's folder and a wire program's, and only when a record was left, since a stop that
  ran to its end leaves none. A group that outlived its leader is named only for what the marker did not end.
- **A pidfd is opened before the look,** so a pid reused after the scan signals nobody, and readiness of that pidfd is how the wait
  ends, with no polling.

## Alternatives

| Alternative | Why not |
|---|---|
| A variable of our own as the marker | A harness may filter its tools' environment by name, and Codex does by pattern. `TMPDIR` is kept by every shell, and is already ours |
| Correct the contract to say a background child outlives `stop` | True on macOS, and loud nowhere: a gap at every stop would say nothing, and the scan is what could tell |
| A cgroup per agent | Not available to an unprivileged user everywhere, and nowhere on macOS |
| `PR_SET_CHILD_SUBREAPER` on the runtime | Several runtimes share a process, and the runtime would reap strangers' zombies of every kind |

## Consequences

- On Linux, a tool's background child, `nohup` and `setsid` among them, ends with its agent, and after a crash with the next runtime.
- A process that clears its environment, as `env -i` does, escapes, and so does anything on macOS, where no process can read another's
  environment. `tests/unit/drivers/test_process.py` holds that limit to what it is.
- A stop scans `/proc` once, about 40 ms on a host with 8,700 processes.

## Evidence

- A review's probe on Claude Code 2.1.316 and pi 1.5.0 against FakeModel: `sleep &`, `nohup` and `setsid` children survived `stop` with
  no gap, and on pi a foreground `setsid` child too. Codex 0.164.0 left none.
- `TMPDIR=<agent folder>/tmp` was in the environment of each such child, on Claude Code and on pi, and each is gone after `stop` now.
- `tests/unit/drivers/test_process.py`, and `stop_ends_a_running_tool` in `check_driver`, which now puts a child in the background and one
  in a session of its own, on each real binary in `tests/integration/`.
