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
- The runtime: from a `Team` to a live session, through ops and safe to repeat. The session folder, its socket and its tokens. The
  host, which performs every effect on a driver, level-triggered. Recovery per agent after a crash, and `python -m
  platoon_harness.runtime <folder>` as a detached runtime with the owner's shutdown on `SIGTERM`.
- `Session`: `start`, `attach` and `resume`, one link in-process or over a control socket, typed wrappers held to the op table by a
  test, and `settled()`, whose `Ending` states a reason an exit code can be made from.
- The control socket: JSON-RPC lines with a credential checked once per connection, separate view and control credentials, pull only.
- `Authority` and `LocalAuthority`, and `Session.start(team, authority=...)`.
- `from platoon_harness import Session, Team, Role, Ending, Refused, on, load_team`.
- `session.ending`, `agent.records`, `effect.list`, `lease.due`, `budget.lapse`, `Kernel.read_only`, `is_held`, and
  `schema.seconds`.
- `session.ending` gives each agent's last `report`. `agent.conclude` and `agent.retell` are runtime-only ops, and `kernel.first` is
  the one race helper. A live text frame is cut at 64 KiB.

### Fixed

- `Kernel.changed` no longer wakes on a batch with no events, as it never promised to.
- `Peer.run` treats a reset connection as the end of the stream.
- `agent.finish` in an open turn ends the agent with that turn, so what a harness reports at turn end counts. It used to be refused,
  which lost the usage and last message and could stall a budgeted team.
- `usage` has no amount for a unit nobody measured. It used to say 0.0. `turns` and `agents` are labelled `counted`, not `provider`.
- A crash or a stop between a handover and its turn no longer strands an agent in `waking`, a goal no turn began is told again on
  resume, and a launch cut short by a stop is no longer recorded as finished.
- A handover that keeps failing backs off and, after six, loses the agent with the reason. It used to loop and grow the journal.
- `agent.interrupt` takes an agent whose handover hangs, and that handover fails. It used to be refused.
- Recovery gives each agent its own failure. One broken driver, or one `reconcile` that hangs, used to stop every other.
- `Runtime.stop` always lets go, and a journal that will not commit holds it up for at most `grace`.
- A wire program's own harness ends with its agent, and a stop already running no longer leaves a harness alive.
- A report the journal refuses ends its harness with a gap. A `ready`, an item or an exit used to be dropped, which could hang an agent.
- `ready` naming a model other than the one pinned fails the spawn.
- Every report is masked on the way to the journal, whichever driver said it, and text is masked before it is cut.
- `session.close` takes `if_done`, and `settled()` uses it, so a message that gets in first keeps a session open. `message.send` is
  refused once a session is closing, because it would reach nobody.
- An approval goes moot with the turn that asked. One pending at a crash used to end in `needs_human` for nothing.
- `reap` reads only the driver's record and a wire program's, so a file a harness left under its folder can neither stop a resume nor
  name a stranger.
- A failed `describe` says what the program said on stderr, and a malformed one is a `DriverError` that names it.
- `tool_visibility` matches a whole name, or its `__<name>` ending, and with no tools to look for says `unverified`.

### Changed

- `primitives.Delivery` is now `Injection`, the word of architecture section 7, and `Policy` names the approval policies.
- `agent.list` and `agent.status` rows name an agent as `agent`, the bare name, as `session.ending` and `roster` do.
- `Peer` takes no `limit`, a `Stray` takes the line alone, and `strict_loads` is the one way to refuse a NaN.
- `reap` returns what it left alone in words, and `Process` masks stderr and leaves reports to the host.
- `agent.records` takes an `agent`.
- The view `primitives.Session` is now `SessionRecord`, leaving the name to the facade.
- An agent has no goal unless given one: `agent.spawn` takes none, such an agent holds no turn's reservation, and a driver waits for
  a delivery. `check_driver` has `no_goal_takes_no_turn`, and the `exec` driver refuses a start with no goal.
- A one-shot agent ends with its turn: `finished` if that turn `stopped`, and `failed` otherwise. It used to be lost.
- `Delivery.text` is a field the host renders in the words of an agent's surface, and `Offered` carries `sender` and `body`.
- `agent.start` takes `resumed`, which journals `agent.resumed` and leaves the agent as it stood. `Agent` has `native`.
- `Manifest` holds `human`, `approvals` and `cwd`, so a folder is all a runtime needs.
- `team_check` takes capabilities by a role's own name too, since a command decides them and a driver's name does not.
- `session.status` says how many approvals are left to `ask`. A lost turn raises `uncertain` in `attention`.
- `Effect.data` is `Any`, as `Event.data` is. `__version__` lives in `platoon_harness.version`.

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
