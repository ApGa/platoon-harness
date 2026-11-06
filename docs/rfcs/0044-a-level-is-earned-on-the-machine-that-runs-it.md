# RFC 0044: A level is earned on the machine that runs it

| | |
|---|---|
| Status | Accepted, 2026-11-05 |

## Summary

`doctor --check` runs every check on each harness it finds, against FakeModel and on no account, and keeps the result under the root, which the host reads at every launch and resume and records on the start, beside the levels it gave; the scripted harness has a shell

## Motivation

`levels(capabilities, profile, conformance)` gives `operational`, `observable` and `trainable` only as far as a conformance result
pinned to the driver and the harness version proves them ([RFC 0008](0008-driver-contract-and-wire.md)). The host passed it no
result, so every live agent read `unverified`, whatever the slow suites had proved of its binary. And `operational` needs
`stop_ends_a_running_tool` and `runs_in_its_workspace`, which skip without a way to make a harness run its shell, so the scripted
harness and a wire program, the custom-driver path drivers.md teaches, could never earn it. The owner chose where a result comes
from: made on the user's machine, by `doctor`, against FakeModel, checking the binary that runs.

## Proposal

- **`check_harness(name, folder)` holds what checking each first-party harness needs**: model access through a home of the check's
  own and a dummy key, so no login takes part, its shell tool, a tool call it asks approval for, our tool by the name its model knows,
  a native child where it has them, and a frame no parser knows written into its stdout, which only Linux allows, so elsewhere that
  check is skipped. The slow suites call it, so what `doctor` runs is what they prove.
- **`platoon-harness doctor --check` checks each harness it finds that a check ships for and keeps what it found** under the root,
  one result for each driver, `conformance/<driver>.json`, beside the folder the checks ran in, whose logs a failed check names, until
  the next check of that harness. A check that cannot run keeps nothing, leaves what was kept and says why, and the next harness is
  checked; so does a harness that says no version, as a result naming none would speak for no binary. `doctor` says for each harness
  whether its kept result speaks for the binary that runs, and if so what it found, what it skipped and which levels a failure leaves
  unmet. Checking is a flag, as it takes minutes of real harness runs, and `doctor` alone stays a quick look.
- **A result is pinned to the driver, by the name it gives and the class that implements it, the harness version it said, the SDK
  and the host**, since the checks prove the driver's code and the binary together, where they ran. The design pinned it to the
  driver and the harness version; the rest is added because a name is a driver's own to give, so a program calling itself `claude`
  would otherwise take what was kept of the claude driver, and because a driver changed by an upgrade, or a machine whose shell behaves
  otherwise, as Codex's did here, is not what was checked. A version nobody said pins nothing, not even to another version nobody
  said. An extension driver's own version is not in the pin: a result for one is made again when it changes.
- **The host reads the kept result at every launch and resume**, computes the levels from it, and records it on `agent.started` or
  `agent.resumed`, at payload 2, as a body beside the levels, where it speaks for that harness, so anyone can read back the proof a
  level rests on. A level with no result that speaks for the harness that runs is `unverified`, naming what makes one:
  `doctor --check` for a harness a check ships for, driven by the class that check is for, and `check_driver` with
  `write_conformance` for any other. Nothing ships a result.
- **The scripted harness has a shell.** Its one tool of its own, `shell`, runs its `command` once an approval allows it, in
  `spec.cwd`, through `Process`, so its group is recorded before it can run and `stop` ends it with whatever it left in the
  background. The conformance wire program is that harness behind the wire, so it now passes both shell checks and earns
  `operational`.
- **The terminal's inspector says the login kind** beside the levels, from the profile of the agent's latest start, which the roster
  now carries as `login`.
- **Coverage stays unproved.** No check proves a coverage surface observed, so a kept result proves none, and `exposure` still
  answers no `NotSeen` ([RFC 0038](0038-provenance-is-answered-from-the-record.md)). Where a check that proves a surface comes, its
  surfaces reach `decide` through the result its agent's start records. Deriving them now would be a table with no entries.

## Alternatives

| Alternative | Why not |
|---|---|
| Ship results from our CI for pinned versions | It vouches from another machine for a binary the user may not run, and every upgrade between releases would read `unverified` anyway |
| Check on every `doctor` | A check runs each harness some thirty times; a machine check should stay quick |
| Check at every launch | It would spend minutes before every session, on a result that changes only when the binary does |
| Keep a result per version | One binary of a driver runs at a time, and a result for a version no longer installed only invites trusting it |
| Record the levels alone | The levels say what the runtime concluded, and the result says why: a person reading a level should reach the proof |
| A coverage check that passes on the scripted harness | It would make `NotSeen` reachable only for a harness nobody runs, which the design rejected as speculation |
| Pin a result to the binary's path too | A path says where a binary is, not what it is: the version names it, and the same binary moved would read `unverified` |
| Find a kept result by the name the role gives its harness | A role names a wire program `wire` and a test's driver by `module:attr`, neither of them the program's own name, so programs would share one result or have none |
| Refuse a driver that goes by an installed driver's name its role does not name | A wire program serving an installed driver goes by that driver's name and runs well; only the proof is not its own, which the pin says |

## Consequences

- A user who never runs `doctor --check` sees `unverified` on every agent, with the command to run.
- `agent.started` and `agent.resumed` are at payload 2, carrying `conformance`, a body's ref or None. `Agents` is at view version 12,
  keeping the login kind, and the roster row has `login`. `verified` holds the driver's class, the SDK and the host the agent ran
  under.
- A result made before the pin held the SDK and the host no longer reads as one, and an SDK upgrade reads `unverified` until
  `doctor --check` runs again.
- A kept result's check folder holds the checks' own homes, with their dummy keys only, and is replaced at the next check.

## Evidence

- `tests/conformance/test_conformance.py`: the scripted harness and the wire program with `shell`, the wire program earning
  `operational`.
- `tests/unit/drivers/test_levels.py`, `test_a_result_pinned_elsewhere_says_nothing_of_this_agent`,
  `test_a_result_of_an_unknown_version_vouches_for_nothing` and
  `test_the_fix_a_reason_names_is_doctor_only_for_a_harness_whose_check_ships`.
- `tests/unit/runtime/test_host.py`, `test_levels_come_from_the_conformance_result_kept_for_the_harness_that_runs`,
  `test_a_result_kept_for_another_version_says_nothing_of_the_one_that_runs`,
  `test_a_result_of_an_unknown_version_vouches_for_nothing` and
  `test_a_driver_that_calls_itself_claude_earns_nothing_from_what_was_kept_of_claude`.
- `tests/unit/cli/test_machine.py`, and `tests/integration/test_cli.py`,
  `test_doctor_check_runs_each_harness_s_checks_and_keeps_none_that_names_no_version`.
- `tests/integration/test_claude.py` and `test_pi.py`, slow: each driver's conformance through `check_harness`, kept, and read by a
  session on the real binary, Claude Code 2.1.316 and pi 1.5.0, whose agent's `operational` is met. `test_codex.py` and
  `test_openhands.py` do the same and have not passed on the machine this was built on, where Codex's shell does not run and
  OpenHands' conformance times out; they wait for a compute node.
