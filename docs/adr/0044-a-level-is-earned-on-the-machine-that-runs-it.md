# 0044. A level is earned on the machine that runs it

**Status:** Accepted, 2026-11-05

## Context

`levels(capabilities, profile, conformance)` gives `operational`, `observable` and `trainable` only as far as a conformance result
pinned to the driver and the harness version proves them ([ADR 0008](0008-driver-contract-and-wire.md)). The host passed it no
result, so every live agent read `unverified`, whatever the slow suites had proved of its binary. And `operational` needs
`stop_ends_a_running_tool` and `runs_in_its_workspace`, which skip without a way to make a harness run its shell, so the scripted
harness and a wire program, the custom-driver path drivers.md teaches, could never earn it. The owner chose where a result comes
from: made on the user's machine, by `doctor`, against FakeModel, checking the binary that runs.

## Decision

- **`check_harness(name, folder)` holds what checking each first-party harness needs**: model access through a home of the check's
  own and a dummy key, so no login takes part, its shell tool, a tool call it asks approval for, our tool by the name its model knows,
  a native child where it has them, and a frame no parser knows written into its stdout, which only Linux allows, so elsewhere that
  check is skipped. The slow suites call it, so what `doctor` runs is what they prove.
- **`platoon-harness doctor --check` checks each harness it finds and keeps what it found** under the root, one result for each
  driver, `conformance/<driver>.json`, beside the folder the checks ran in, whose logs a failed check names, until the next check of
  that harness. `doctor` says for each harness what its kept result found and on which version. Checking is a flag, as it takes
  minutes of real harness runs, and `doctor` alone stays a quick look.
- **The host reads the kept result at every launch and resume**, computes the levels from it, and records it on `agent.started` or
  `agent.resumed`, at payload 2, as a body beside the levels, so anyone can read back the proof a level rests on. A result that ran
  on another version says nothing of this one, and a level with none for the version that runs is `unverified`, naming the command
  that makes one. Nothing ships a result: a result vouches for the binary it ran on, on the machine it ran on.
- **The scripted harness has a shell.** Its one tool of its own, `shell`, runs its `command` once an approval allows it, in
  `spec.cwd`, through `Process`, so its group is recorded before it can run and `stop` ends it with whatever it left in the
  background. The conformance wire program is that harness behind the wire, so it now passes both shell checks and earns
  `operational`.
- **The terminal's inspector says the login kind** beside the levels, from the profile of the agent's latest start, which the roster
  now carries as `login`.
- **Coverage stays unproved.** No check proves a coverage surface observed, so a kept result proves none, and `exposure` still
  answers no `NotSeen` ([ADR 0038](0038-provenance-is-answered-from-the-record.md)). Where a check that proves a surface comes, its
  surfaces reach `decide` through the result its agent's start records. Deriving them now would be a table with no entries.

## Alternatives considered

| Alternative | Why not |
|---|---|
| Ship results from our CI for pinned versions | It vouches from another machine for a binary the user may not run, and every upgrade between releases would read `unverified` anyway |
| Check on every `doctor` | A check runs each harness some thirty times; a machine check should stay quick |
| Check at every launch | It would spend minutes before every session, on a result that changes only when the binary does |
| Keep a result per version | One binary of a driver runs at a time, and a result for a version no longer installed only invites trusting it |
| Record the levels alone | The levels say what the runtime concluded, and the result says why: a person reading a level should reach the proof |
| A coverage check that passes on the scripted harness | It would make `NotSeen` reachable only for a harness nobody runs, which the design rejected as speculation |

## Consequences

- A user who never runs `doctor --check` sees `unverified` on every agent, with the command to run.
- `agent.started` and `agent.resumed` are at payload 2, carrying `conformance`, a body's ref or None. `Agents` is at view version 12,
  keeping the login kind, and the roster row has `login`.
- A kept result's check folder holds the checks' own homes, with their dummy keys only, and is replaced at the next check.

## Evidence

- `tests/conformance/test_conformance.py`: the scripted harness and the wire program with `shell`, the wire program earning
  `operational`.
- `tests/unit/runtime/test_host.py`, `test_levels_come_from_the_conformance_result_kept_for_the_harness_that_runs` and
  `test_a_result_kept_for_another_version_says_nothing_of_the_one_that_runs`.
- `tests/integration/test_cli.py`, `test_doctor_check_keeps_what_each_harness_s_checks_found_where_the_runtime_reads_it`.
- `tests/integration/test_claude.py`, `test_codex.py`, `test_pi.py` and `test_openhands.py`, slow: each driver's conformance through
  `check_harness`, kept, and read by a session on the real binary, whose agent's `operational` is met.
