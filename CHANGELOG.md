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
- `stays` on `Role`, on `agent.spawn` and on `Session.spawn`: an agent that stays takes a follow-up task or a question by message
  after its first, on the same harness, until it is told to finish, retired or cancelled. It is resolved once, at the spawn, from the
  spawn, then the role, then whether the session started it, and refused for a harness that is not persistent. `agent.status` shows it,
  and the result of a spawn that stays says how to end it. See ADR 0023.
- `preamble` on `Team` and `Role`: the generated part of what an agent is told is a template, a role's in place of its team's, with
  eight slots the runtime fills per agent and per surface, and `PREAMBLE`, the default, renders what it said before byte for byte.
  `name` and `tools` are values and the rest sentences of ours, a line that holds a slot and comes out blank is left out, so no word
  of a template's is, and an empty template tells nothing. A slot nobody fills is refused when the team loads, an op in backticks in
  a template's words or a role's `instructions` is named as the surface names it, and `team_check` warns of a template that leaves
  out `tools` or `ending` and of words that name a tool a role cannot hold, refuses a role's own template on a harness that reaches
  none of our tools, and warns of its team's. `agent.instructed` journals the exact text added to each harness, at launch and at
  every resume, which hands a harness that reopens its own session what it was told when that began. `told(team)` renders what each
  role would be told, starting no harness, and `tools.NAMESPACE` and `tools.surface_of` say how a harness names our tools.
- `allow_native_children` on `Role` and `AgentSpec`. A harness's own agents are off unless a role allows them, as such an agent's calls
  reach us only in its parent's total, no topology binds it, and its calls to our tools go out on its parent's token. Claude Code's
  `Agent`, `Workflow`, `ListAgents` and `SendMessage` are disallowed, and Codex's own agents are off for the thread by
  `agents.enabled = false`, both generations. `team_check` says what a role that allows them gives up, `check_driver` has the row
  `native_children_off_by_default`, and `Request.tools` names the tools a model is shown, exactly.
- `tests/live/test_launch.py`: a job an agent would hand to a sub-agent of its own starts none, and a team's template reaches
  the model, on Claude Code and Codex. Live tests count the agents that open a turn with a `wait` naming nothing.
- `tests/live/test_stays.py`: the owner's flow on Claude Code and on Codex, and a Codex child's half alone. `tests/live/test_codex.py`
  runs a Codex agent's own sub-agent.
- The headless command line, `platoon-harness`: `run`, which owns a session in the foreground from a team file, the project file or
  `--harness`, with a prompt from an argument, stdin or a file; `serve`; `events`, from a cursor and following; `session list`,
  `show`, `stop` and `resume`; `team check`, `show` and `told`; `init`; `doctor`; `extension list`; and a command for each op a person
  may run but `wait`, made from the op registry and its schemas, so `ph task.claim --queue tasks` for an agent is `platoon-harness
  task claim SESSION --queue tasks` for a person, its help naming commands and flags where its op names ops and arguments. `--json`
  prints one line per event the runtime it owns journals, from its `runtime.started`, and then the Ending, in a shape versioned by
  `format`. Exit codes are an Ending's, 64 for usage, a refused `run` or `session resume` among it, and 78 for configuration. Ctrl+C
  or `SIGTERM` at any point runs the owner's shutdown. `--approvals` answers every approval one way and the manifest keeps it, and
  nothing prompts. `docs/cli.md` is made from the command definitions, and `docs/headless.md` is a quickstart.
- `kernel.registry(extensions)`, the op table before any session exists, and `Op.agent`, which keeps `agent.finish` to agents by
  kind as `runtime` keeps an op to the runtime.
- `runtime.opening.check(team, plan_login=)`, every problem `Session.start` would meet, which `team check` prints, and
  `Session.head()`.
- An interrupt quiets what was waiting for its agent, whoever interrupts: what came before it wakes nothing and stays unread for the
  next turn, and a wait that already holds closes with no notice, while what comes after wakes as usual. `wake.quieted` records it.
- `platoon_harness.tools.taught` and `OP_NAMED`, which the command line words its help with.
- `tests/live/test_cli.py`: milestone 1's flow from a terminal, and a stop and a resume of a live session.
  `tests/integration/test_cli_harnesses.py` runs, stops and resumes from the command line on each real binary against FakeModel.

- `before` and `streams` on `Kernel.read`, and through every link form, as `Session.page`: a page back from `before`, still in
  order, whose cursor is the next `before`, and a set of stream names a page holds, so a transcript pages back without reading the
  journal whole. `Session.events` takes `streams` too. bug-clients-3.

### Changed

- A person's message to an agent steers, whatever the reader's delivery setting, and a script's `Session.send` is a person's. An
  agent's message follows the reader's setting as before. Nothing withdraws a sent message.
- An interrupt of an agent on its way to a turn, by a wake that is due or a wait that holds, is accepted and cancels that wake or
  closes that wait, where it was refused. Before an agent's first turn begins it is refused saying so, where it said nothing was on
  its way, as `agent.retire` knew otherwise.
- The preamble template's `peers`, `roles` and `channels` are values, `@a, @b` for `peers`, and the default carries our words around
  them. A line whose slots all come out empty is left out, words and all. A line with no slot, and every word of a role's
  `instructions`, is never dropped. An empty `peers` or `channels` is an empty value, where `nobody yet` and `none yet` were words of
  ours in it, so the default renders byte for byte as before but for a line that would name no peer or no channel. ADR 0025 is
  amended.
- A session that was closing reads `closed` once its owner has stopped, where it read `closing` for good.
- A root another user owns or can write, a sessions folder or a socket directory not this user's, and no socket directory at all are
  configuration errors, which the command line exits 78 for and `doctor` reports, where they were refused `unsupported`.
- A start cut short, cancelled or failed, once its incarnation is in the journal, runs the owner's shutdown and appends
  `session.stopped`, where it ended its harnesses and left the journal as a crash would.
- `Team.starts(role)` names the agents a role starts, where it counted them, so the command line and the runtime name them alike.
- `agent.finish` from anyone but an agent is refused `not_permitted` by kind, where its body refused `invalid`.
- `Session.submit` of a read answers it as a query, which writes nothing, so a view credential may ask it.
- The plan-login refusal names `--plan-login` beside `plan_login=True`, and history names `platoon-harness session resume`.
- `ScriptedDriver` names its turns after the instance too, so no resume repeats a turn's name.

- The owner's flow in `tests/live/test_stays.py` words its steps in an order no reading can mistake: on the old words a Codex
  lead sent the follow-up at once, in run 36, and it landed in the helper's first turn.
- The monitor wakes a parent once for the spawn and once for each message of its own the first time it lands in its child's turn, in
  place of once per causal chain, so the answer to a follow-up reaches the parent as the first did. Every report answers, one a wait
  counts too, but one from a turn an interrupt or the owner's stop cut. A message from a peer or a human asks nothing, and nor does one
  read again. A steer that lands in the turn after its offer counts there, its hops too.
- What the preamble says of ending follows whether an agent stays, and a child that stays is told to answer by ending its turn, which
  sends its last words to its parent and leaves it there for the next message. Told it stayed for the next message, a Codex child held a
  `wait` for it instead of answering.
- The preamble teaches `wait` as how to wait for something named, where it used to say to call it with nothing to do until something
  changed, which beside "answer by ending your turn" told a child that had answered to park. `stays` is said one way everywhere: an
  agent told to stay after its task for the next message.
- An agent's instructions are the preamble and then the role's words, so a role has the last word. A role that told a Codex agent
  never to finish lost to the preamble in run 21.
- A child that ends with its parent ends `retired` unless a turn of its was cut off, open or on its way, which still ends it
  `cancelled`, as Platoon drops a cancelled child's tokens. A parked child is retired. `session.cancel` still cancels every agent, each
  parent before its children, so that no report goes to a parent ending with it.
- An agent's `wait` for the end of one that stays is refused while it has not ended, naming `from`, a refusal over working children
  names `from` for one that stays, and a `max_children` refusal says that ending a child makes room.
- `agent.retire` is refused for an agent on its way to a turn, as for one in a turn: `agent.cancel` is what stops one.
- `team_check` warns of a wake cycle that closes through a parent and a child that can stay, with no `max_hops`, and refuses a role
  that stays on a one-shot harness. The `manager-worker` and `tree` presets take `max_hops`, 8 unless given, as `mesh` and `star` do,
  so no shipped preset sets the warning off.
- `agent.spawned`, `context.offered`, `context.delivered` and `message.sent` are at payload v2, and the folds that read what v1 lacked
  fill it with what held when it was written, so a journal from before agents could stay still opens.
- A tool result's `next` is in the words of its surface, with no sentence naming a tool its reader does not hold, as a refusal's is.
- `open_session` takes what each role's driver said, and the runtime asks each driver when it opens a session.
- The live crash test holds a log to no more runs of a command than the journal saw begin, since a kill can come before a command it
  set going ran.
- `check_driver` has rows for a denial that holds, an effort honored or refused, and `reconcile` after a restart, and its `gated`
  argument turns a command into a call that asks approval, as `shell` turns one into a call that runs it.
- An unset model is refused only where access was given. On the harness's own login it means the harness's own default, and `ready`
  says which.
- A live test runs in `tests/live`, marked `live`, on `PLATOON_HARNESS_LIVE=1`.
- The driver contract shrank to what the runtime reads. `start`, `deliver` and `interrupt` return nothing, on the wire too, so `Started`
  and `Receipt` are gone, and `ready.native` is the one statement of a session's id. `interrupt` in `Capabilities` is a boolean, `Login`
  has no `native`, `DriverInfo` has no `version`, and `Item.phase` is `started` or `completed`: a message or a thought has none, and
  `approval` is what says an item answers one.

- A turn nobody measured whole, a lost one or one an interrupt cut short among them, is charged what was measured plus its estimate,
  labelled `estimated`, and limits hold on that, where it was charged its estimate and left every later reservation in its unit
  refused `unavailable`. On Codex every interrupt did that, so one Esc under a `tokens` limit left a session to a person. `Budget` and
  `budget.set` take `estimate`, which a `tokens` or `usd` limit needs, and `team check` and `budget.set` refuse one without it.
  `fallback = "turns"` is gone, as an estimate does its job. Usage in the Ending and the roster counts `unmeasured` turns, as
  `budget.status` did.
- A timer that can only end a session moves nothing, so a wall limit no longer holds off a stall: a wake the budget refuses under one
  ends the session `needs_human` at once. Live run 42 waited out its four minute wall and exited 2.
- `session.stop` cancels each handover that has not started, which queues its entries again and is no failure of its harness's. The
  owner's stop failed them before, which counted toward the six that lose an agent.
- Op descriptions hold for every reader who may run the op, so a person's surface shows no sentence written to an agent, such as
  "Your own open turn is always among `blockers` while you ask".

- Live text is a tail bound to its item: one per agent of what it is saying now, ended by the host at a message or thought item and a
  turn's end, and by the kernel when its agent's principal is revoked. `deltas` joins what came past a reader's frame into one
  `Delta`, whose new `ended` names the seq through which the journal holds what the text before it became, so a client that joins
  late is shown only text not yet committed, with its true `lag`, and a reader of an ended agent is told so once and then nothing
  more. `Kernel.end_delta(agent, seq)` ends it. A tail holds 256 KiB, where a ring held 256 frames. bug-clients-2, -4 and -5.
- The writer resolves a batch's acks before it wakes followers, so what a caller does on its ack comes before a follower on its loop
  looks.

### Fixed

- Esc did not stop an agent with something queued, as what an interrupted harness took was queued again and woke it, and an interrupt
  was refused between a wake and its turn: bug-coordination-7 and -8.
- A handover an interrupt cut counted as one that failed, so each later message waited twice as long, and six interrupts lost the
  agent. That wait had hidden a race: a harness can begin a turn on the handover the interrupt failed, and a message sent at once
  landed in that turn as the interrupt cut it, on pi against FakeModel. Nothing is handed over while an interrupt is under way.
- A command whose runtime went for good after it committed, before its ack, was refused on its retry, and running it again after a
  resume ran it twice. History answers a key its journal holds.
- A call whose send failed as its connection went left asyncio to say on stderr that nobody read its answer.
- A resumed `ScriptedDriver` named its first turn as the first instance had, so a call identical to one of that turn, with no id of
  its own, was answered from the journal as a repeat and nothing ran.
- A test that failed part way could leave a detached runtime running. A fixture every test has ends each one its `tmp_path` holds,
  by its pid and its group.

- The scan for local paths and account details skipped `docs/research`, its fixtures, the top-level pages and the package
  READMEs. It reads them now, and an email address too, and a path inside a repository no longer reads as a local one.
- A wait that closed with no notice of its own posted "A report came in during your wait." as a wake, which stayed queued after its
  reader had read the report itself, as the lead of run 22 did with `sender`. Each report the wait named or counted now wakes its
  reader itself, within `max_hops`, as `wake.restored` records, so a report read first wakes nobody. Section 7 also says what held all
  along: a report from a turn stopped on purpose wakes nobody by the monitor, and a wait counts it as it counts anything it names.
- A stop under heavy load could fail with a group that "outlived SIGKILL", or `reap` name a group that outlived its leader, when nothing
  in it ran: a member that has exited counts for `killpg(group, 0)` until its parent reaps it, and an orphan waits on pid 1. A group is
  judged by whether anything in it still runs, on Linux, and a process whose main thread has exited while another runs still does,
  so a stop of one that ignores `SIGTERM` comes to `SIGKILL` and says so.
- A resume rendered what an agent was told afresh and journaled that, while Claude Code and Codex kept what their session began with,
  so the record held words no model heard. A harness that reopens its own session is handed, and journaled, what it was told when
  that began.
- `wait.cancel` let a report from a turn an interrupt or the owner's stop cut wake its reader, which such a report never does. Only a
  report that answers is restored.
- A template's own words on a line whose slots came out empty were left out with the line, and nothing said so. `preamble = ""` was
  checked as written and run as the default, a template on a harness that reaches none of our tools went untold without a word, and
  `team_check` warned of a tool held through a grant to a named agent as one the role lacked.
- `told(team)` refused a team whose limits or budget stopped one agent of each role, said a driver that could not describe itself
  with no role named, and showed a child whose spawner starts with nothing as a session's own agent.
- The scan for local paths reads the CLI's sources too, a home folder whose name begins with a capital, and this cluster's name.
- The plan-login refusal was checked only at the start, so a human spawning more agents later, and a resume after a harness was signed
  in on a plan, escaped it. The manifest keeps `plan_login`, and without it a launch beside a live agent on a plan login fails, and a
  resume that would bring back several is refused, each naming the fix in the same words, `PLAN_LOGIN_FIX`.
- A budget that an unmeasured turn left unable to hold said so and no more. Its `unavailable` refusal names the two ways on, a
  `fallback = "turns"` with a `turns` limit or no limit in that unit, and says no higher limit helps.
- A Codex interrupt that came while a `turn/start` was on its way, which the harness then refused, stayed set and cut the next turn.
  A refused handover with no other turn on its way clears it.
- A role a written grant lets another spawn was not counted as spawnable, so a plan login with one such role was not refused, and the
  role started an agent of its own. `Team.spawners` reads written grants of `agent.spawn` as `team_check` does, as the same thing as
  `may_spawn`.
- A turn with one call unmeasured was charged its estimate alone, so a million measured tokens counted as none. What was measured now
  stands as a floor. A Codex turn cut short reports a call `unavailable`, as Claude Code's and pi's do, rather than reading as whole.
- An agent whose harness took no turn was lost at any resume, as Claude Code, Codex and pi write no session until a turn. The runtime
  starts it anew, and tells it what it must know as before. `agent.records` says whether an agent's harness `began`.
- `stop` left a tool's background child running on Claude Code and pi, `npm run dev &` among them, with no word in the journal, and
  `check_driver` passed. On Linux, `Process` now ends what carries the harness's own `TMPDIR`, whichever group it left for, at a stop and
  after a crash, and `stop_ends_a_running_tool` puts a child in the background and one in a session of its own.
- A frame of a known type with a shape nobody expected stopped a Claude Code agent. It is a `native` frame and a gap, as on the other
  two, a request the harness waits on is still answered, and a turn's end still ends the turn. A call whose count is nothing, or a null
  part, is no measurement.
- An interrupt as a handover begins a turn reads `interrupted` on every harness: Claude Code read it as a failure, which woke a parent,
  and Codex sent nothing and ran the turn on. A refused interrupt labels no turn, a failed turn says its failure, and a turn the harness
  cut with nobody asking reads `aborted` on Codex and pi.
- A Claude Code goal that starts with `/` is refused, as it ran as a slash command.
- pi's `reconcile` no longer says `not_landed` of an id it cannot know, an approval's among them, and a compaction whose listing does not
  read is still reported. Codex's `answer` to a harness that has died is a `DriverError`.
- A late answer to a JSON-RPC call its caller gave up on is no unknown frame.
- A role runs in the user's own setup. Claude Code no longer has auto memory turned off, and pi no longer has its network, telemetry and
  version check turned off: those were a sealed launch's settings, left behind.
- A user's `defaultMode` can no longer answer before the runtime hears, so a role's `deny` holds on Claude Code, and `AskUserQuestion`,
  which a verdict cannot answer, is no longer offered.
- Claude Code's tool token is in no file: `--mcp-config` names its variable, as Codex's and pi's launches do.
- Our tools failing to connect fails a Claude Code agent's start, where the agent used to run on with no way to coordinate.
- Codex declares its 300 s cap on one tool call, so a `hold` past it is refused up front.
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

- Ctrl+C while `run` prepared could leave a session folder behind after `run` said no session was made. A start cancelled while it
  prepares takes its folder back.

### Changed

- `check_driver` has rows for a denial that holds, an effort honored or refused, and `reconcile` after a restart, and its `gated`
  argument turns a command into a call that asks approval, as `shell` turns one into a call that runs it.
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
