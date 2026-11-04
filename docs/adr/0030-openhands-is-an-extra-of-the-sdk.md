# 0030. OpenHands is an extra of the SDK

**Status:** Accepted, 2026-11-04

## Context

[ADR 0008](0008-driver-contract-and-wire.md) ran OpenHands through the wire in an environment of its own, as `openhands-sdk` 1.59.0
cannot share one with `mcp` 2.3.0 or ACP 1.0.0rc3. Its worker became a distribution apart, `platoon-harness-openhands` in
`extensions/openhands`, which the runtime found on `PATH`. Nothing was published, so the one install that ran was a second
environment built from a checkout's lock, which every user and every slow run had to build, and a run that had not skipped. The
worker's command needed a case of its own in the naming law, and the workspace's one lock held OpenHands' pins all the same. The
owner chose otherwise: "I am actually ok with importing openhands sdk in our package, making it an optional/extra dependency."

## Decision

- **An extra.** `platoon-harness-sdk[openhands]` pins `openhands-sdk` and `openhands-tools` at 1.59.0 exactly. The distribution
  apart is gone, and the worker is `platoon_harness.drivers.openhands`, beside the other drivers.
- **Still a worker per agent, on the wire.** The runtime runs it as `python -P -m platoon_harness.drivers.openhands` on its own
  interpreter, so nothing is looked up on `PATH` and nothing else is installed, and `-P` keeps the workspace it runs in off its path.
- **Only the worker loads OpenHands.** Its one module that imports `openhands` and `litellm` runs in the worker's process alone, and
  importing the SDK, the runtime, any driver class or the command line loads none of it.
- **Missing, it says so.** Without the extra, `doctor` says it is not installed and how to install it, and an agent's start is
  refused in the same words. Nothing else changes.
- **An environment of its own stays one wire command away.** Where a user's environment cannot hold OpenHands' pins, they install the
  SDK with the extra in one of its own and name its interpreter and the module as a wire command.
- **The proprietary proxy stays out of our lock.** `exclude-dependencies` keeps `lmnr-claude-code-proxy` out, and the docs say that
  the extra installed from an index brings it in unless excluded, as uv's `--excludes` does.

## Alternatives considered

| Alternative | Why not |
|---|---|
| Keep the distribution apart | Unpublished, it asks every user and every slow run to build a second environment from a checkout, and a run without one skips |
| OpenHands in the runtime's process | The runtime is the session's one writer. The SDK takes about 10 s and some 200 MB to load, keeps one registry of agents a process, holds its state's lock while a tool runs, and starts processes that a group must own for `stop` to end them |
| A script of the SDK's on `PATH` for the worker | A second name for one program, which `PATH` can find in another environment, where the runtime's own interpreter is known |
| `python -I` for the worker | It drops the user's site-packages too, so an SDK installed with `--user` would not load. `-P` drops only the workspace's path, as the runtime's own launch does |
| A uv conflict declared now with the planned `[acp]` extra | No such extra exists, so it would guard nothing |

## Consequences

- The dev environment installs the extra, so the OpenHands tests run in every full slow run, and none of them skips.
- An environment with the extra holds OpenHands' pins: our lock moved `filelock` to 3.32.7, and the `[acp]` extra, when it lands,
  cannot share an environment with this one.
- `ty` checks the worker against the real SDK, so its allowance for unresolved `openhands` and `litellm` is gone.
- Run as a plain wire command, the worker gets what any wire program gets: the shell's proxy variables only where an auth profile
  names them, and the socket directory every tmux of the user's shares.
- The SDK's rule that it imports no agent implementation has one exception, which `AGENTS.md` states.

## Evidence

- `tests/unit/drivers/test_boundaries.py`: `test_only_the_openhands_worker_imports_openhands`, by AST, and
  `test_nothing_but_the_openhands_worker_loads_openhands`, by `sys.modules` in a fresh interpreter.
- `tests/unit/drivers/test_openhands.py`: the worker's command, a workspace whose modules stand in for none of the worker's, and a
  start refused without the extra. `tests/integration/test_cli.py`: `doctor` with the extra, and on an interpreter that finds none.
- `tests/integration/test_openhands.py`, slow, on the real SDK against FakeModel, from the dev environment.
- By hand, in an environment of the SDK and the command line alone: `doctor` said how to install the extra, `team check` found no
  problem, and a `run` failed its agent at start with the same words. A dry run of uv's resolver installing the extra brought in
  `lmnr-claude-code-proxy` 0.2.0, and with `--excludes` naming it did not.
