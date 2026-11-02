# Changelog

## Unreleased

### Added

- The session kernel: journal, writer thread, operations, grants, effects, timers, views, readers and daemons.
- The core primitives as extensions on the public kernel: messages and channels, context, wait, boards, leased queues,
  lifecycle and completion, approvals, budgets, and the `roster`, `attention` and `changes` views.
- Teams and topologies: roles, nine presets that mix by union, one compiled grant table, `team_check`, and `team.show()`.
- Layered configuration, `Secret`, the reproducibility manifest, and extension discovery from metadata alone.
- The tool plane: a tools-only MCP server on loopback, a stdio shim, `ph`, and one derivation of tools and the turn preamble from
  `ops.list`, per token.
- `platoon_harness.rpc`: one line-delimited JSON-RPC 2.0 peer on asyncio streams, split on LF only.
- The driver contract: seven methods, one closed report vocabulary, `levels`, and `docs/drivers.md`.
- `Process`, for every subprocess driver: a group recorded before exec, pipes that always drain, a bounded masked log, and a
  verified `stop`. `harness_env` is the allowlist of section 15.
- `WireDriver` and `serve`, and the `exec` driver. `harness = { command = [...], mode = "wire" }` names a program in a team.
- `platoon_harness.testing`: `ScriptedDriver`, `FakeModel`, `FakeTools`, `check_driver` and `check_extension`.

### Changed

- `agent.spawn` adds the principal, and a host issues its credential with `principal.issue`.
- `lease_lost` and `blob.put` are gone, and `task.claim` at `max_inflight` refuses `conflict`.
- `message.send` takes no `cause`: a program carries a chain with `reply_to`.
- `load_team(trust_commands=)` is now `trust_project=`, and covers `module:attr` references and auth profiles.
- `Kernel.submit` takes `native`, stamped on a command's events, and `Kernel.get_body` takes `limit`.
- `blob.get` takes one `ref`, which can name lines. A cut body says `rest`, and `text` is null where an op could not read a body.
- `agent.status` names the open `turn`.
- `ready` holds only what a driver knows. A harness commits through the new runtime op `agent.start`, with what was declared and
  verified and the levels, so a report cannot claim one. `agent.report` refuses `ready` and `delta`.
- `agent.report` takes `input.delivered`, `approval.requested`, `model.call`, `child.seen` and `native`, and `usage` has a `scope`.
- A report's `body` is text until the host stores it, as ingress does for a tool's body argument.
- `Capabilities` holds every field of architecture section 9.2, and absence means unsupported.
