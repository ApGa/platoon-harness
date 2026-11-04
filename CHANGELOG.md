# Changelog

## Unreleased

### Added

- Acting from SwarmChat's page, on a control link, each act one op through `/x/command`: a composer at the foot of a chat that names
  its target, sends on Enter, starts a line on Shift+Enter and cuts a long text by the function the terminal cuts with, a reply in
  a thread citing the message's entry, a file as a message's body with the most a body may be said first and its progress shown,
  approvals as cards with Allow and Deny, Needs you with its count, from the runtime's `attention`, and an agent's interrupt, stop
  below, retire and cancel and the session's close and cancel, each asking first where the terminal does. Each act keeps its key
  until answered, across a lost connection and a reload, so a retry is one operation, and a refusal shows its reason. Every control
  the person cannot use says why. See `docs/web.md` and ADR 0028.
- `view_info`'s `x` says `body_limit`, the most bytes a body may be.
- The browser suite, `tests/e2e/`, in Chromium's headless shell: a message in an agent's input path once, on a wire harness and on
  the real `claude` binary against FakeModel, the browser and the terminal attached at once, approvals raced from two clients,
  credentials, `Origin` and a rebound `Host` from real pages, hostile rendering under the policy, reconnects, receipts and history.
- `platoon-harness web SESSION`: SwarmChat's pinned page over the session's journal, in a browser, as a guest on the owner's
  control credential that starts and resumes nothing and follows the session across runtime restarts. A follower folds the journal
  one way into `swarmchat.sqlite`, with ids a rebuild gives again, and serves the page's `view_*` replies from it, with "Delivered to"
  from delivery evidence in place of "Read by". A view link and a control link, each opening once for a session token that expires;
  `Host` and `Origin` checked; loopback unless `--host` names another address with TLS. `/x/command`, `/x/body` and `/x/link` take what
  the page will send. The page reads in this stage, and every act is drawn disabled, saying why. See `docs/web.md` and ADR 0027.
- `platoon_harness.runtime.control.BODY_LIMIT` and `platoon_harness.primitives.IN_A_RESULT` are public.
- `platoon_harness.http`: the tool server's bounded HTTP, as a module of its own with public names. `Origin`, when a request has
  one, must now be the origin of its `Host`.
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
  order, whose cursor is the next `before`, and a set of stream names a page holds besides what `match` globs, so a transcript pages
  back without reading the journal whole. `Session.events` takes `streams` too. bug-clients-3.
- `Session.marks()` and `Session.mark(stream, seq)`: how far a person has read each stream, kept per principal in
  `marks.sqlite` beside the journal, with no runtime, and apart from an agent's cursor, so moving a mark acknowledges nothing. A
  mark only moves forward, and a view credential moves none. `Link.principal` names who a link acts as. bug-clients-7.
- `below` on `agent.interrupt` and `Session.interrupt`: one act that stops the turns of an agent and of every agent below it and
  keeps them all. It stops turns, not waits, and says whose: an interrupt answers `{stopped}`, where it named an effect.
- `agent.unread` and `Session.unread(agent)`: what the roster's `unread` counts, with how each entry would land, for a chip and a
  queue line above a composer.
- `tests/integration/clients.py`: the live tail, stop below, an interrupt under a `tokens` limit and a child's anchor, run on the
  real Claude Code, Codex and pi binaries against FakeModel. `tests/live/test_interrupts.py`: an interrupt during a call under a
  `tokens` limit on real models, after which the session goes on.
- The terminal UI: `platoon-harness` on a terminal opens the sessions screen, and `platoon-harness attach SESSION` one session. It
  starts a session on a detached runtime and is its guest, so Ctrl+D detaches and the session runs on. The workspace has a navigator
  grouped by what a person must do, a focus pane with a transcript read from the journal a page at a time, live text below it, an
  inspector, a dock of the places a person must act, and a composer whose target is always shown. One keymap table makes the
  bindings, the help, the footer, the palette and the keymap of `docs/tui.md`. Untrusted text crosses one `SafeText` boundary.
  `tests/live/test_tui.py` drives it with Pilot on a Claude Code lead and a Codex worker.
- `group` on each roster row: what a person must do about the agent, `needs_you`, `working`, `blocked`, `idle`, `done` or
  `failed`, derived in the view so every client says the same.
- Every act of the terminal UI takes only keys every terminal delivers, so an editor's terminal that keeps Ctrl, Alt or F keys,
  as Cursor's on a Mac does, leaves none out of reach. In the composer a line that is exactly `/` and an act's name runs it and
  goes to no agent, `/` alone lists them, `/` from any other part begins one there, and the footer always begins `/ commands`.
  Tab and Shift+Tab go round the parts in the order they are on screen. The dock takes focus with no place chosen, so its `y`
  and `n` answer only a place chosen there with the arrows. The sessions screen has a plain key for each act, `?` the help, `p`
  the palette and `q` quitting among them. `docs/tui.md` names the VS Code, Cursor, Terminal.app and iTerm2 settings that keep
  keys. ADR 0026.

- `tool_names` on `Capabilities`: a harness that shows our MCP tools by their own names, as OpenHands does, says `bare`, and its
  agents are told them by those names, in their instructions, handovers and refusals, through `?surface=mcp`.
- The `openhands` harness: `platoon-harness-openhands`, a distribution of its own in `extensions/openhands`, is a wire worker per
  agent on OpenHands SDK and tools 1.59.0, pinned exactly, in an environment of its own that the SDK and the command line never
  import, and `harness = "openhands"` runs it from PATH, built from the repository's lock, as nothing is published. It drives one
  conversation through `arun()`, signs in with a key from the role's auth profile alone, through the shell's proxies, gives the
  agent OpenHands' coding tools and ours through the stdio shim, asks the runtime before every action but ours, holds a delivery
  while an approval is open and until what it allowed has its result, says what a request carried from the SDK's completion log,
  and keeps its own agents off unless a role allows them, when their steps ask the runtime too. `check_driver` passes on the real
  SDK against FakeModel, and no live model has run. The workspace lock excludes the proprietary `lmnr-claude-code-proxy`, which
  nothing the worker runs imports. `doctor` finds it by its worker, and `init` passes it over. `WireDriver.command` says the
  program a wire driver runs, and `WireDriver(command, inherited)` names what of the runtime's environment it takes beside the
  allowlist.

### Changed

- `tools.surface_of` takes a harness's `Capabilities`, where it took its tool paths, as how a harness names our tools is
  `tool_names` too.
- A `Profile` says whether its role allows the harness's own agents, and opaque native children cost `trainable` only then.
  `check_driver` skips `native_child_seen` for a harness whose native children are opaque, as none can show, and still checks that
  they are off by default.
- In the terminal UI, Esc interrupts the agent in view from the composer only: from the transcript, the dock or the navigator it
  goes back to the composer and interrupts nothing. The footer names Esc by what it does from the part with focus, which is
  marked. Alt+Y, Alt+N, Alt+S and Alt+R are gone: a terminal sends Alt and a letter as Esc then that letter, so Esc then a word
  typed at once answered a place, stopped turns, or asked to resume, which can spend money. `/yes`, `/no`, `/stop-below` and
  `/resume` reach them. The dock takes focus from Tab or Shift+Tab,
  never on its own or from a click, and a part hidden while it has focus gives it back to the composer. Under 80 columns Esc or a
  row chosen in the navigator closes it. Acts are named as they are typed: `palette` where it was `commands`, `quit` for `leave`,
  `next-place` for `next for you`, `yes` and `no` for `first action` and `second action`, `open-line` for `open line`, `file`
  for `attach`, and `stop-below`, `page-up`, `page-down` and `takeover` joined where they were two words. The sessions screen
  looks again on `l`, where it was Ctrl+R. Search in a transcript, not built yet, has no key until it is, as `/` begins a typed
  command from every part of a session. The guide's keymap shows each key as the screen does.
- The command line shows a control a terminal would act on, C0 but tab and newline, DEL, C1 and the bidi controls, as its escape,
  and nothing else, where it escaped every format character, which broke emoji joined by a zero-width joiner.
- The problem a plan login with several agents raises is at `plan_login`, the setting that answers it, where it was at `roles`.
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

- From SwarmChat's page, an act whose answer was lost went again under a new key after a new link, since `web` put the key
  under the link's session token, and so ran twice; and one `web` took whose page then heard its session had ended was shown as
  refused. The key is the page's own, 32 lowercase hex under `web/`, whichever link sends it; an act a page's ended session left
  unanswered says so, stays kept, and goes again from a new link opened over the page, which loads it again for the gate. A
  failure of `web`'s is an answer saying whether the act took effect is unknown, and only a request that reached nothing, or a
  503, is sent again. A body holding half of a character, nested past reading, or a search the page could not have made, is
  refused 400, where some failed 500 and a long draft holding half a character was sent again for ever.
- `web`'s bare address answered 404, where SwarmChat's own server sends a browser on to its page; ours now does too. And
  `web` on loopback now says how to reach it from another machine: forward the port under the same number, since the
  page's requests must name it.
- An act left unanswered went again from a view link opened over the page, which refused it, so the page called refused an
  act that may have been done. A view link now sends none of it and says it waits for a control link opened in that tab.
- ADR 0016 and the compatibility map said `web --remote` refuses a second person on a plan-login session, which no code did
  and no such flag exists; ADR 0027 amends it, as the architecture already said, and refusing another address to such a
  session is planned. The guide now says that while `web` runs a run's approval waits for you instead of ending
  `needs_human`, and the architecture names `web` among the entry points with signal handlers and among what writes beside
  the journal when it reads. `web` on a page file that is not the one pinned exits 78, which nothing tested before.
- The page said a spawn's goal was "Delivered to 0 of 0 agents it was for", and that the spawner made each agent's chat with
  the person, which nobody in it did. A goal reached its agent when the agent's first turn began on it, and the runtime makes
  that chat. The projection is version 3, which `web` folds again from the journal when it starts.
- A file sent as a message's body lost its name whenever words went with it, in the terminal and on the page, since a body
  keeps none, so the page showed every body as `body.txt`. The function both clients make a gist with names the file after
  the words, `TEXT (file NAME)`, and refuses the two past 280 characters; the page sends the file's name beside the op's
  args. Where no words went, the gist `file NAME` that ran past 280 was refused as a long text beside a file.
- On SwarmChat's page, the people list showed `agent` beside every agent, where SwarmChat draws someone's first field, so
  who was working or held up needed a page per agent; it shows each agent's status there. Seeing as a person or the
  runtime was offered, and choosing one left the page half in a mode it had refused; the picker draws them disabled,
  saying why, and an address naming one shows everyone. An approval's card floated beside its message, crushing it on a
  narrow window; it sits under the question. A `via` holding a dollar and a backtick or a quote put the message's own
  markup into its card, as a string's replace read them; no replacement the page makes reads them now. Tool activity,
  reviewing changes and provenance had no control, where every unbuilt act is drawn disabled saying why; each has one.
  A person's own page makes links of either kind, which only `/x/link` did.
- Two `web` processes on one session folded one projection, each from its own cursor, and the first to meet a line the other
  had written crashed with a traceback, dropping every browser it served. One `web` serves a session at a time, holding
  `swarmchat.lock` beside the projection, and a second exits 64, saying where the first serves. The fold passes over an event
  it has folded already.
- `web` spent a link before it believed the request to exchange it, so an exchange refused for its shape or cut off
  burned the link and gave nobody its token. A link is spent only by the answer that carries its token.
- A request to the tool server or to `web` had 10 s to arrive whole, head and body, and its answer 10 s to leave, so a file
  near the 12 MB a body may be could not cross a link slower than about 10 Mbit/s, and the page said only that it did not
  reach `web`. A head still has 10 s, and each part of a body or an answer has 10 s from the part before.
  `platoon_harness.http.length` is gone: `Server.body` reads a body on that rule.
- `web --host localhost` bound `127.0.0.1` and `::1` on two ports and said one, leaving that port free on the other address
  for any program on the machine to take, and be what a browser reached. `platoon_harness.http` binds every address a name has
  on one port, trying again when a busy host has taken it on one of them. `web` on the scheme's own port, 80 or 443, refused
  every request, as a browser leaves that port out of `Host` and `Origin`; it leaves it out of what it serves too.
- The browser's projection showed a message's body in place of its words whenever the body held them anywhere, so a file whose
  text held the message's words hid them. A body takes their place only when it begins or ends with the gist, as a cut gist does.
  An agent's end line said only that it ended, so a lead's answer given as its finish report was not in the page; it says what the
  terminal's says, the report among it. The projection is version 2, which `web` folds again from the journal when it starts.
- The terminal UI, from its review:
  - Showing another agent or channel left the last one's lines under it, and each showing stacked them again.
  - The dock had two markers of where you were: Alt+A stuck on the second place, and Alt+Y could answer a place you had not
    chosen, or one that took the top when another client answered yours. Only you move the dock's cursor now, and a place
    that goes takes it with it.
  - An unread count read one page, so lines past 4,096 other events read as none, a channel first seen in a frame counted
    that frame twice, and your own lines counted. Counts read on to the newest line drawn, and leave out what you wrote.
  - A marks file that could not be read stopped the workspace, and one that could not be written ended the app. Either
    loses only badges, said once.
  - A window's edge on a tool's line read back lines twice, showed a finished call as running or lost lines, a child
    spawned while the first page was read lost the history, and a page read for a focus shown before another was put in.
  - A lead with more than 253 children could not show its transcript. It reads every `agent/*` by a glob.
  - Live text a runtime was saying when it went stayed on screen and was joined to the next runtime's. It goes with the
    runtime, and showing the agent in view again keeps it.
  - An edited recall was thrown away by Up or Down, Ctrl+D away from the composer dropped a draft, Ctrl+D from a session
    opened on the sessions screen quit the app, leaving history said the session ran on, and a UI that failed exited 0.
  - Esc, refused, sent again on every press. Ctrl+Home went to the oldest line held, not the start. Under 16 rows the dock
    and the banner stayed. The header ran off the edge, said nothing of what changed and no limit but tokens and usd.
  - The palette cut a read's answer to 280 characters of JSON, erased a body without asking, and held an agent's
    deliveries for a terminal not built. It offers commands, asks before an erase, and says a takeover is not built.
  - A typo in a yes-or-no field went as no, Enter in a form's first field sent the form, Shift+N was shown for `n`, F1 in
    the help opened another, a slash command went with no word, and keys outside the one table were bound by hand.
  - `tests/integration/test_tui.py` stopped reading its PTY once the agent's words showed, so the UI's next repaint
    filled it and Textual's exit waited on its writer for ever: it failed twice on a loaded host.
- A handover under way when the owner stopped counted, once the next runtime failed it, as a failure of its harness's, so six stops
  and resumes during a wake lost the agent.
- A turn measured only as a lower bound was charged as if measured whole, and a Claude Code result with no tree usage left its
  turn labelled `provider`. Both are charged their estimate on top now.
- `budget.status` said a wall limit had nothing spent against it. It says the time since the limit was set.
- A role's estimate with no limit of its own never reached the session, so its turns were reserved the shared estimate, and a
  role's limit was refused although the shared estimate covered it.
- Each reader of live text read the journal on every commit to look for its agent's end, a private read per follower that law 8
  rules out. It looks in the tail every follower shares.
- A mark could move backward, when a second terminal of the same person marked less than the first had, and a view credential
  could move one.
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
