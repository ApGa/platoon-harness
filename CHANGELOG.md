# Changelog

## Unreleased

### Added

- The session kernel: journal, writer thread, operations, grants, effects, timers, views, readers and daemons.
- The core primitives as extensions on the public kernel: messages and channels, context, wait, boards, leased queues,
  lifecycle and completion, approvals, budgets, and the `roster`, `attention` and `changes` views.
- Teams and topologies: roles, nine presets that mix by union, one compiled grant table, `team_check`, and `team.show()`.
- Layered configuration, `Secret`, the reproducibility manifest, and extension discovery from metadata alone.
- The tool plane: a tools-only MCP server on loopback, a stdio shim, `ph`, and one derivation of tools and the preamble from
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

- The `claude` driver: `claude -p` in stream-json with the control protocol on the same pipes, in the user's own setup, with every
  approval through the runtime. `check_driver` passes on the real binary against FakeModel, at 2.1.316.
- The `codex` driver: `codex app-server` on stdio, in the user's own setup, with every approval through the runtime. `check_driver`
  passes on the real binary against FakeModel, at 0.164.0.
- The `pi` driver: `pi --mode rpc` in the user's own agent directory, with our tools through the stdio shim from one extension
  loaded with `-e`, and `gated` approvals through the runtime. `check_driver` passes on the real binary against FakeModel, at 1.5.0.
  No live model has run.
- `sandbox` on `AgentSpec`, from the role.
- `effort` on `Role` and `AgentSpec`, handed to the harness as it stands. A driver that cannot honor one fails the spawn.
- `Session.start(team, plan_login=True)`. A driver reports the login kind, and `prepare` refuses several agents on one plan login
  without it, naming the fix.
- `check_driver` rows `unset_model_refused` and `native_child_seen`, and its `tool` and `child` arguments, because a real harness
  knows our tool by a prefixed name.
- `peers` lists the `roles` you may start an agent in, and the preamble names them.
- The preamble says how to end: an agent somebody spawned makes `agent.finish` its last call, and one the session started stays unless
  told to finish.

### Changed

- An unset model is refused only where access was given. On the harness's own login it means the harness's own default, and `ready`
  says which.
- A live test runs in `tests/live`, marked `live`, on `PLATOON_HARNESS_LIVE=1`.
- The driver contract shrank to what the runtime reads. `start`, `deliver` and `interrupt` return nothing, on the wire too, so `Started`
  and `Receipt` are gone, and `ready.native` is the one statement of a session's id. `interrupt` in `Capabilities` is a boolean, `Login`
  has no `native`, `DriverInfo` has no `version`, and `Item.phase` is `started` or `completed`: a message or a thought has none, and
  `approval` is what says an item answers one.

### Fixed

- What a harness took and never landed is queued again when its turn stops short, and when it comes back from a crash, by one fold, so
  a steer no longer goes missing across a crash, and no driver sends anything again, or fails to in silence. Claude Code drops its queue
  at an interrupt, as it would otherwise begin a turn on it by itself.
- A Codex approval id was a count per process, so a second agent's first request collided in the journal and was answered `deny`
  with nobody asked. It is unique now.
- A harness that exits in a turn leaves the gap `crash_window`, since a tool of its own can run on. It used to leave none.
- A real child's `system/task_progress` frame no longer costs Claude Code a gap.
- A secret split across two deltas reached followers unmasked, on every driver but `exec`. Live text is masked as one stream.
- An `interrupt` or an `answer` that a harness never took held its effect open for ever. Each fails after a minute, as a handover
  already did.
- A role with an auth profile was recorded under the login its harness had, though it never used it.
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
- A report the journal refuses ends its harness with a gap, and so does one whose body will not store, which left none. A `ready`, an
  item or an exit used to be dropped, which could hang an agent.
- `ready` naming a model other than the one pinned fails the spawn.
- Every report is masked on the way to the journal, whichever driver said it, and text is masked before it is cut.
- `session.close` takes `if_done`, and `settled()` uses it, so a message that gets in first keeps a session open. `message.send` is
  refused once a session is closing, because it would reach nobody.
- An approval goes moot with the turn that asked. One pending at a crash used to end in `needs_human` for nothing.
- `reap` reads only the driver's record and a wire program's, so a file a harness left under its folder can neither stop a resume nor
  name a stranger.
- A failed `describe` says what the program said on stderr, and a malformed one is a `DriverError` that names it.
- `tool_visibility` matches a whole name, or its `__<name>` ending, and with no tools to look for says `unverified`.
- `wait(on=...)` works for a guest, a mistyped agent is refused by `wait` and `deltas` instead of hanging, and attaching says a refusal
  such as a protocol mismatch at once instead of blaming the runtime after a minute.
- Awaiting a session that was left starts nothing, and one never entered says how to start it.
- `leave` takes a span and stops nothing halfway if it cannot read one.
- The control socket aborts every connection at a stop, so a client that stopped reading cannot hold one up, and a connection accepted
  during a stop is dropped. A socket belongs to a folder, so a copied session cannot take a live one's.
- No client can grow the live text rings by naming agents that do not exist, and a `Link` raises only `Refused` and `Closed`.
- A guest on history survives a writer touching the journal.
- A root another user owns or can write is refused, a session folder is built aside so a crash burns no name, an unusable
  `XDG_RUNTIME_DIR` falls through, and a detached runtime runs from its folder with `-P`.
- `team_check` refuses a one-shot role that starts with the session, and says nothing of a `count` of zero, which was said on purpose.
- A held wait closes as told only once its answer has left, so an answer that is lost costs no wake.
- A query's answer past 32 KiB is refused with its size, and a refusal names no tool its token does not hold, in its reason either.
- `ph <tool> --help` for an unknown tool shows what there is.
- An effect left `uncertain` can be settled by a person with `effect.settle`, as ADR 0005 promised. Nothing could settle one under
  `surface`. Saying it did not happen lowers its row in `attention`, as saying it did does.
- The host retries under one key, since a failed commit may have landed. It used to retry with none, and could run a command twice.
- A turn a crash or the owner's stop cut off is told to its agent on resume, at-least-once, with a wake, and the words keep the two
  apart. A lost turn used to leave its agent idle on its leases with nobody told, so a session read `settled` with its work undone.
- `settled()` with no timeout can no longer hang on a session settled short of `until`, on a guest that leaves having done nothing, or
  on a goal the budget will not wake. It says `needs_human`, and so does `session.ending`. A wake the budget refused keeps a session from
  closing as `settled`, and so does a wait on someone still here, so a deadlock with no root no longer ends exit 0.
- A goal told again after a crash takes the turn its spawn reserved. It used to be refused by that reservation. A session that stops
  accepting before it can be told ends its agent, and used to hang as `closing`.
- A task long settled no longer holds off a stall until its lease's timer fires.
- A waiter's own `agent.cancel` or `task.complete` counts for its wait. A join after a cancel used to hang.
- A report the parent is counting no longer wakes it, so a join of N costs one turn and not N. The same goes for a join on tasks, while
  someone else below the parent is at work: the last worker's report wakes it, or it would sleep on what nobody is left to do.
- A turn that did not stop on its own says so to the parent, as `<name> turn <reason>: <text>`, and an `interrupted` one wakes nobody.
  It used to read as a final answer and wake the parent. A failed turn or a bad end breaks in on a parent with a wait open, even once
  its chain's wake is spent.
- A report a wait held back reaches a turn when that wait closes with no notice, by `wait.cancel` or a held call's answer.
- A wait on other events of a child's stream no longer counts its end.
- A parent that ended its own child is not woken to hear of it.
- `agent.finish` and `agent.retire` are refused over working children, a wake that is due and a wait that holds among them, naming them
  and what to do next. They used to cancel a child mid-turn in silence, or with a message unread. `team_check` warns of a one-shot role over children that would end with its turn.
- A stop that comes to `SIGKILL` reports `crash_window`. `stop_leaves_no_process` could not see a tool, and a tool that leads its own
  group outlives a kill of its harness.
- A resume under other SDK or extension versions leaves a record on `runtime.started`. It left none.
- A session from before `v_agents` changed resumes: `Agents` and `Attention` are at version 2, and a test pins each view's schema to its
  version. Such a session used to die in recovery on a `TypeError`, and agents nobody can read now stop a resume with the refusal.
- A model on a long team can still find its peers: `peers` and `channel.list` go a page at a time, where one past 32 KiB was refused
  with nothing left to try.
- A description or a handover no longer names a tool its reader does not hold, and a refused query leaves its line out of the preamble.
  It used to read `nobody yet`. Each pointer to a tool has a sentence of its own, so a reader who does not hold that tool keeps the fact
  beside it. An argument's whole description could go with it.
- Two extensions that claim one tool name are refused at load, as op names are. They used to pass load and raise at start.
- `check_extension` sees an op named with an underscore or a digit, and a plain `import` of a kernel module.
- A long `forgotten` no longer loses its agent: the list passed what an event holds, and the report was refused.
- `view.watch("roster")` no longer misses a row. It keyed on `event.agent`, so a row that moved on an event naming someone else or
  nobody, a message, a wait's progress or a budget, stayed stale. A roster now changes as a whole.

### Changed

- `Session`: boards and queues take their tool's name, `board_post`, `task_claim` and so on, and `agent.release` is plain `release`.
  `cancel()` stops the session and `cancel_agent(agent)` one agent. `finish`, `join`, `wait_any` and `broadcast` are gone, as `wait` and
  `send` state them. `spawn` says `role`. `put_body` returns a ref, and `get_body` and `tombstone` take one.
- `Link.submit` takes no `expected_version`. Ops that need one take it as an argument.
- `ConfigError` is at the top of the package, and `testing` no longer exports `API_KEY` and `BASE_URL`.
- `primitives.Delivery` is now `Injection`, the word of architecture section 7, and `Policy` names the approval policies.
- `agent.list` and `agent.status` rows name an agent as `agent`, the bare name, as `session.ending` and `roster` do, and `parent` and
  `held_by` the same way, so a client can walk them.
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

- `agent.list` and `task.renew` are no longer tools. Agents have `peers`, and the host renews leases. `peers` and `channel.list` return a
  page, `{peers, total, cursor}` and `{channels, total, cursor}`, and take `after`.
- `check_driver` has `preamble_once_per_request`, `tool_item_carries_its_anchor` and `stop_ends_a_running_tool`, for which it takes
  `shell`, and `operational` needs that last one. `measures_reported` holds `tokens` to what the model said, `call_ids_reported` holds an
  item and a call's usage to the id, and `interrupt` holds a turn's reason to `interrupted`.
- `ScriptedDriver` sends `spec.instructions` as a system message, and says which call made an item.
- `runtime.start` takes `drift`, and `Kernel.recover` takes it as arguments. `Manifest.drift()` says what differs from a manifest.
- `tool_name` lives in the kernel, which claims tool names at load. `tools` adds `held_tools`.
- `Item.phase` is one of `started`, `completed`, `final` and `decided`, and anything else is an unknown frame. `Item` and `Usage` have
  `call_id`, which goes on the envelope, `ModelCall` has `purpose`, `Compacted` has `summary`, and `InputDelivered` has `native_id`. An
  id, a reason and a purpose hold 256 characters, `Item.native_id` among them.
- `Compacted.forgotten` holds native ids, and the host stores it and `summary` as bodies. With `None` the runtime records
  `compaction_opaque`, so a driver no longer reports that gap itself.
- A `roster` row has `parent`, `stopped`, why the last turn did not stop on its own until the next begins, and `held_by`.
- `session.status` says `stalled`, and `Session.settle_effect` says whether an uncertain effect happened.
- `agent.retell` also tells a resumed harness its last turn was cut off, from `stopped`, and with nothing to tell it says nothing.
- `OWNER_STOP` is the reason a turn ended by a shutdown gives. A host reports a turn interrupted while it closes under that reason.
  `CUT_OFF` holds the reasons only the runtime gives, and a driver that says one has sent an unknown frame.
- An agent that has finished can spawn nothing.
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
