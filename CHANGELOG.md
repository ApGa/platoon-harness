# Changelog

## Unreleased

### Added

- The session kernel: journal, writer thread, operations, grants, effects, timers, views, readers and daemons.
- The core primitives as extensions on the public kernel: messages and channels, context, wait, boards, leased queues,
  lifecycle and completion, approvals, budgets, and the `roster`, `attention` and `changes` views.
- Teams and topologies: roles, nine presets that mix by union, one compiled grant table, `team_check`, and `team.show()`.
- Layered configuration, `Secret`, the reproducibility manifest, and extension discovery from metadata alone.
