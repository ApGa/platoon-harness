# Changelog

## Unreleased

### Added

- The session kernel: journal, writer thread, operations, grants, effects, timers, views, readers and daemons.
- The core primitives as extensions on the public kernel: messages and channels, context, wait, boards, leased queues,
  lifecycle and completion, approvals, budgets, and the `roster`, `attention` and `changes` views.
- Teams and topologies: roles, nine presets that mix by union, one compiled grant table, `team_check`, and `team.show()`.
- Layered configuration, `Secret`, the reproducibility manifest, and extension discovery from metadata alone.

### Changed

- `agent.spawn` adds the principal, and a host issues its credential with `principal.issue`.
- `lease_lost` and `blob.put` are gone, and `task.claim` at `max_inflight` refuses `conflict`.
- `message.send` takes no `cause`: a program carries a chain with `reply_to`.
- `load_team(trust_commands=)` is now `trust_project=`, and covers `module:attr` references and auth profiles.
- `Kernel.submit` takes `native`, stamped on a command's events, and `Kernel.get_body` takes `limit`.
- `blob.get` takes one `ref`, which can name lines. A cut body says `rest`, and `text` is null where an op could not read a body.
- `agent.status` names the open `turn`.
