# Changelog

What each release of platoon-harness changes. Nothing is released yet: everything below goes into the first release, 0.1.0.
Below 1.0, a minor release may change the Python API, the team file or the command line, and a patch release only fixes
bugs; require a range such as `platoon-harness-sdk>=0.1,<0.2`.

## 0.1.0 (unreleased)

Known limitations are in [docs/STATUS.md](docs/STATUS.md), which says of every capability whether it is planned,
implemented, tested, experimental or deferred. An id such as `bug-clients-3` names a finding that
[the Pi Durable review](docs/research/pi-durable.md#defects-in-ours) lists under Defects in ours, and STATUS says each one
named here is closed.

### New features

- **The browser tests in Firefox and WebKit too.** `PLATOON_HARNESS_BROWSERS` names the browsers the browser tests run in,
  comma-separated, each test once in each with its id naming the browser, and Chromium's headless shell where it names
  none. CI's `e2e` job runs them once in each of Chromium, Firefox and WebKit. They pass in Chromium and Firefox. WebKit does
  not start on the hosts we run on, as Playwright's build of it needs glibc 2.38, so it is untested, as the compatibility
  page's section 6 says, and what CI shows of it is not known yet. The three, each claimed only where it passes, are the
  default pending the owner's ruling.
- **A disabled control in the page takes focus and says why.** Every control SwarmChat's page draws disabled stays in the
  keyboard's order, which `disabled` took it out of, and its reason, a title the mouse alone found, is its accessible
  description, which screen readers announce with a control, though none has been run on the page. Focus or a press shows
  the reason beside the control, and a press does nothing else. A control pressed says it waits for its act's answer until the answer comes. Needs you, each post's vote
  control and each name in the as-picker are buttons Tab reaches and Enter presses. That this is the page's accessibility
  bar, with no WCAG level claimed, is the default pending the owner's ruling.
- **A security guide.** [docs/security.md](docs/security.md) says what platoon-harness protects, tier by tier, linking each
  to architecture section 15, and what it does not: other users on the same machine, who reach loopback, where a bearer check
  protects the data and not availability, which is the default pending the owner's ruling; an agent that runs commands as
  you; an agent's network; resources; and macOS. It says where each credential lives and when it goes, that a session keeps
  everything until its folder is deleted, what tombstoning a body erases and what it does not reach, and that only what the
  runtime gave a harness is redacted.
- **A session on a plan login stays on loopback.** `platoon-harness web` serves a session on a plan login on loopback alone,
  as a control link acts as you, on your login, and refuses another address with exit 78, saying why and what to do: a
  session started with `--plan-login`, or one of whose agents' harnesses came up last on a plan login, as the roster says.
  It checks as it starts, and while it serves another address it stops with 78 once an agent comes up on one. A harness that
  cannot say which login it has is not counted, as the runtime does not count it for its own refusal.
- **What an offer showed, by its ref.** `context.show(offer)`, a query op with `Session.shown(offer)` and the command
  `context show`: the text each item of an offer showed, in the offer's order, a gist as it was shown, with any fields beside
  it, and a body or the lines of one, each where the journal proves it by the item's digest, a child's report and a board's
  announce, shown by the event they carry, among them, and null where it does not, as for a body redacted since or past 64 KiB.
  A training system shows a model call's inputs this way, and builds no form of its own of a gist shown with its fields, which
  was private. See [RFC 0063](docs/rfcs/0063-what-an-offer-showed-is-answered-by-its-ref.md).
- **Screenshots of the terminal UI, from its snapshot tests.** `docs/assets/tui-*.svg` are the snapshot tests' seven SVGs, byte
  for byte, which a test holds equal: the workspace at five sizes, the review list and the provenance panel, each drawn on
  scripted harnesses. The README, the terminal UI guide and both team examples show or link them, each captioned with what drew
  it. The snapshots' scripted lead says the parser is fixed in the turn its worker's report starts, so the transcript reads in
  order and ends on its words.
- **A worktree team with its merge queue written out.** [examples/worktree-merge-queue](examples/worktree-merge-queue/README.md):
  a Claude Code lead, Codex workers each in a worktree of its own and a Claude Code merger in a worktree of its own, the
  `merges` queue of RFC 0058 with each role's instructions saying its part, and a README that checks it, runs it with no keys
  on the test suite's stand-ins, reads back each merge and the conflict that reaches its worker as its task's result, and
  says how to run it on real harnesses, which it has not run on yet. A test runs the README's commands as it shows them, in a
  repository of its own.
- **Spans: each agent's turns cut at its writes.** `spans(agent)`, a query op with `Session.spans` and the command `spans`: each
  turn of an agent cut after each model call that chose a write of content, one of the eight it made itself, as the record joins
  the op's anchor, the tool item holding it and that item's call, with a trailing piece that has no write joining the span
  before it. Each span is named by its last call's `model.called`, with its first call, its turn and the writes the record ties
  to its calls, oldest first, a page beside its true count, `open` while the latest turn has not ended. It is worked out from
  the views as it is asked, with no new table, and answers alike after a rebuild and on a closed copy. `primitives.Span` and
  `primitives.Spans`. See [RFC 0061](docs/rfcs/0061-credit-is-kept-per-span-and-a-span-rests-on-what-it-took.md).
- **Install, concepts and a first session.** Getting started for a newcomer, in
  [docs/getting-started](docs/getting-started/install.md): installing from a checkout, with and without the `dev` group,
  OpenHands' extra and what `doctor` says; what platoon-harness is and is not, a session on disk and one session traced; and a
  first session, with no keys, read back, opened and then set up on your own harnesses, whose first steps a test runs as shown.
  [Troubleshooting](docs/how-to/troubleshooting.md) gives each common refusal's real message, why and what to do. The OpenHands
  install text moved from the drivers guide to the install page, for a checkout, with no index's package name, and the headless
  guide's `doctor` sample is a checkout's.
- **Every key of a team file, on one page.** [docs/reference/team-file.md](docs/reference/team-file.md), the team file's
  reference, made from its schema by `uv run python -m platoon_harness_cli.team_file > docs/reference/team-file.md`: each table
  from `Team` down, where it goes, its model's docstring and each key's type and default, a channel's `kind` among the required,
  then every preset's arguments. `tests/unit/cli/test_team_file.py` holds it to the generator and to pydantic's own schema.
- **A team run from Python, with no key and no model.** [examples/sdk-script](examples/sdk-script/README.md), a headless script
  on the SDK alone: a team of one role on a command the `exec` driver runs, two agents spawned with a goal each, the session
  waited on until it settles and what each said read from the journal, with no key and no model. A test runs its README's
  commands as shown.
- **How to set up a checkout and propose a change.** [CONTRIBUTING.md](CONTRIBUTING.md), the workflow: setting up a checkout,
  the tests and what each needs, the hooks, commits and pull requests, what CI runs, and adding a driver, an extension, a
  preset, an op or an example. AGENTS.md keeps the rules every change follows.
- **Confinement and a sealed launch, tested together.** The integration test,
  `test_an_isolated_sealed_agent_reaches_its_gateway_on_loopback`: one agent `isolated` under `bwrap` and launched sealed on a
  training authority's gateway, in the slow pass, on a scripted harness on the wire, as a harness in the runtime's own process
  cannot be confined, and on pi and OpenHands. Confined, it calls the gateway on loopback with its own bearer, reports each
  compaction by its id and is eligible from the result kept where it ran unconfined, the closed session says it ran `isolated`,
  and no form of its bearer or its token is in a file or in the command line of any process of its harness.
- **`tests/public_api.txt` records `Team.spawners(role)` and `Session.get_body(ref, *, limit)`, which a training system reads.**
- **The team's test, run at a recorded commit.** Runtime tests of a commit, `repo.test{commit}`: a person's or a program's act,
  never a tool, refused to an agent whatever its grants, that runs the team's new `test = {command, timeout}`, `timeout`
  required, in a clean detached checkout of a recorded commit, as you and unconfined, and records what it came to as
  `repo.tested` on `repo/<name>`, with no agent in the envelope: the command, its exit, its seconds, `passed`, `failed` or
  `error`, why where the exit does not say, and the last 64 KiB of what it printed as its body. The checkout is a repository of
  its own in the session folder's `tests/<effect>/`, borrowing the objects of your repository and each workspace's own but an
  isolated one's, and goes once recorded. A timeout is an `error` and ends all the test started. A commit a look of an isolated
  workspace found, or one built on it, is refused, naming why — the look that found the code decides this, not the reflog an
  isolated agent writes and could clear. A `test` from a project or team file needs the trust step. `Team.test` and `team.Test`,
  `Settings.test`, the runtime-only `repo.record`, the `test` effect, `Session.repo_test`, `drivers.process.run`, which runs a
  command in a group recorded before it can exec and ends what it leaves, `Record.of`, `runtime.workspaces.checkout` and
  `runtime.paths.TESTS`. See [RFC 0056](docs/rfcs/0056-a-runtime-test-is-a-person-s-act-and-isolated-code-never-leaves.md).
- **What each commit's latest runtime test came to, in the `changes` view.** The `changes` view's commit rows carry `tests`, the
  latest runtime test's outcome or None, its `tested` record ref and `tests_why`/`tests_exit` why it failed or erred, and, when
  the team names a test, an act saying 'Test: runs @ada's commit as you, unconfined', or disabled, saying why. The terminal's
  `/review` shows each commit's outcome and the reason it failed or erred, `untested` where none ran, and tests the chosen
  commit with Enter once you say yes. `repo.test` is among the acts both clients ask about first. The view is at version 3.
- **An agent turns a commit's SHA into the ref it cites.** `repo.commit{sha}`, an agent read every agent holds: a recorded
  commit's `ref`, `sha`, `gist` and `made_in`, by its SHA or its first 4 or more hex digits, the read recorded as exposure,
  refused 'not recorded yet: a commit is recorded at the look after the turn that made it' until then. `Session.repo_commit`.
  See [RFC 0057](docs/rfcs/0057-an-agent-cites-a-commit-by-the-ref-the-journal-gives.md).
- **Workers hand their branches to one merger.** The merge queue for worktree teams, written out in `docs/how-to/topologies.md`:
  a `merges` queue and a merger in a worktree, the look recording each merge or conflict, and a conflict going back to its
  worker as its task's result. `docs/research/landscape.md` now puts the merge-queue role there, and not in `git-swarm`, which
  never merges. See [RFC 0058](docs/rfcs/0058-a-merge-queue-is-a-queue-and-a-merger-written-out.md).
- **`isolated` workspaces, experimental.** An isolated workspace is a snapshot whose harness, and everything the runtime runs in its tree,
  one extension's isolation confines: its looks, the check at a launch or a resume, the stop's reading of what removal would lose,
  making a kept snapshot whole, and finding its objects for `commits.bundle`, so a filter an agent writes into its own config runs
  inside, on the same allowlist the harness gets and no variable the runtime holds besides. The runtime's own bookkeeping in the
  agent's folder — its process record, log, instructions and `ph` shim — it writes and reads following no symlink the confined
  harness could plant there, so none of it lands outside the tree. Inside, it writes only its agent's folder and a private /tmp; finds your home, as `HOME` names it and as your account
  does, the session root and the runtime directory empty and read-only, but for your repository's objects and where its harness is
  installed; and sees only its own processes, which all end with it. It still reads what you can read outside those folders, and
  reaches the network, every loopback service, every abstract socket and every socket file outside them. Only such a launch records
  assurance `isolated`. `Extension.isolation` carries an isolation, with `refusal()` and `wrap(writable, readable, hidden)`, and
  `platoon_harness.runtime.isolation` says what an isolated agent may do. The SDK ships `bwrap`, on Linux's bubblewrap, as the module
  `platoon_harness.bwrap`, registered as an extension and loaded only by a team that names it. Refused before any cost: no extension
  that gives an isolation, two, one that cannot confine here, a harness that declares no installed path, and a role with no auth
  profile whose harness signs itself in. Its escape tests pass on Claude Code, Codex with its own sandbox nested inside, pi and the
  OpenHands worker against FakeModel. A stop gives an isolated harness the end of its stdin and its grace, then `SIGKILL`, labelled
  `crash_window`, since bubblewrap passes no `SIGTERM` on. See [RFC 0034](docs/rfcs/0034-isolation-is-an-extension-s-and-the-runtime-s-git-runs-inside-it.md).
- **What an isolation needs from a driver: where a harness is installed, a wrap and its home.** `DriverInfo.installed`, the
  paths a harness reads to run, declared by every driver, and by a wire program in its description; `AgentSpec.wrap`, the argv
  of the isolation a harness runs in, which `Process` puts before its command; and a `HOME` in `spec.env` is the harness's home,
  so `harness_env` passes none of the variables that keep a harness's state elsewhere. `drivers.env.on_path` and
  `drivers.env.PYTHON` name where `PATH` finds a program and what the runtime's own Python reads. `drivers.env.open_beneath`
  opens a file beneath a folder following no symlink below it, which the runtime's writes into a confined agent's folder go
  through.
- **Sealed launches.** On a gateway, ScriptedDriver, pi, OpenHands and a wire program that declares `sealed` launch with nothing of the
  user's: the gateway's model under its bearer, which goes by environment alone, under `BEARER_VARIABLE`,
  `PLATOON_HARNESS_BEARER`, a file the launch writes naming it as `${PLATOON_HARNESS_BEARER}`; ours and the environment's tools, the
  environment's a second MCP server, `ENVIRONMENT`, at `Gateway.tools`; no tool of the harness's own that acts, so a call of one
  runs nothing, no project instructions and no retries. A wire frame carries a gateway as an object naming the bearer's variable. A
  gateway whose URLs or compaction headers hold its bearer in any form, whose headers would authorize a call, whose tools are at
  another origin, or whose bearer is empty, is refused. ScriptedDriver declares `sealed`. Pi gets an agent directory of its own in the agent's folder, and a
  context window no context reaches, as it took an unstated one as none and compacted after every turn once its history passed what a
  compaction keeps; OpenHands none of its coding tools, the environment's from an MCP client of their own, so ours keep their names.
  See [RFC 0053](docs/rfcs/0053-a-gateway-admission-launches-sealed.md).
- **A gateway tells each compaction call apart as it arrives.** Compaction labelled at call time: each compaction call of a
  sealed launch carries the gateway's `compaction_headers` and is reported as `model.call` of purpose `compaction` with the id
  the model gave: ScriptedDriver's new `Compact` step, OpenHands' condenser, a wire program from its frame, and pi through our
  extension, which takes `session_before_compact` and runs pi's own `compact`, and says each of its one or two calls to the
  driver, by its id or with none where it never answered, before pi says the compaction ended, even when it was cut. See
  [RFC 0053](docs/rfcs/0053-a-gateway-admission-launches-sealed.md).
- **A stand-in gateway for a training system's tests.** `FakeModel.gateway(bearer)`: FakeModel as a training system's gateway,
  its models and an MCP server of the environment's tools, `ENVIRONMENT_TOOLS`, at `/mcp`, answering only a bearer it gave.
  `Request.bearer`, `Request.carries(headers)`, `FakeModel.tool_calls`, and `Overflow`, a reply that refuses a request as too
  long in each dialect's own error form.
- **A sealed launch's first request, checked.** Two conformance checks of a sealed launch,
  `sealed_first_request_holds_only_ours` and `environment_tools_in_first_request`, kept in the one result per driver, which
  `trainable` now stands on; `check_driver(kept=)` names the tools of a harness's own that a sealed launch keeps, each acting on
  nothing, as OpenHands' `finish` and `think`. See [RFC 0053](docs/rfcs/0053-a-gateway-admission-launches-sealed.md).
- **A heuristic that splits a team's reward back along the record.** `platoon_harness.credit.propagate`, `propagate@1`, a
  heuristic producer in the one producer signature, `produce(session, episode, *, judge, **params)`, which splits an episode's
  one team reward back along causes, ancestry and seen citations, each maker keeping `retained`, and writes one local `credit`
  row per agent it reached, on its first `agent.started`. `primitives.WALK_LIMIT` names the 4,096 events a walk reaches. It
  refuses a reward on an episode that closed on no ref, which would credit nobody's work. See
  [RFC 0054](docs/rfcs/0054-credit-is-a-producers-annotation-and-propagate-is-the-first.md).
- **The hand-off contract, `test_a_managed_session_runs_as_a_training_authority_drives_it`, on ScriptedDriver in the fast pass and on pi
  and OpenHands in the slow pass.** `tests/public_api.txt` now writes each frozen member's parameters, as `name(parameters)`, and a
  closed set of words, as `name[words]`, a model's field by its name, which a test holds to the code, with every name a training
  system reads: `Session.agents` and `Session.leave`, `Eligibility`, `CallEligibility` and `Bar` with their words,
  `AgentOutcome.status`, `Annotation`, and `FakeModel` and `Request` members.
- **The ref a training system closes an episode on, per agent.** Each agent's `said`, in `Session.agents()` and
  `Session.status(agent)`: the ref of its last words, its latest turn's last message or what a finished agent's end's report
  carries, which a training system closes an episode on.
- **Ask the record what can train.** `eligibility(agent, episode)`, a query op with `Session.eligibility` and the command
  `eligibility`: whether an agent's work in one episode can train, from the record alone, with its attribution, `exact`,
  `forked` or None, and a verdict with every bar of a closed set, for the agent and a page of its calls. It reads the levels its
  starts recorded, never the conformance store. See
  [RFC 0052](docs/rfcs/0052-a-reward-has-five-statuses-and-eligibility-is-read-from-the-record.md).
- **A trainable check of a team, from `trainable_problems` and each role's driver.** `trainable_problems(team, approvals=None)`,
  what keeps a team from training, read from the team alone, with approvals judged by a session's own `approvals` where it is
  given one, and `check(team, trainable=True)`, which adds each role's driver, a sealed launch and a result kept under the root
  that proves trainable, and which `Session.start(trainable=True)`, `prepare(trainable=True)` and
  `platoon-harness team check --trainable` run. A trainable start needs an authority. `DriverInfo.version` says the harness
  version a driver would run, where it can tell without starting one, and `levels.unearned` why a result does not prove a level.
  See [RFC 0052](docs/rfcs/0052-a-reward-has-five-statuses-and-eligibility-is-read-from-the-record.md).
- **`docs/extending/training.md`, the guide for a training system building on the contract.**
- **Who starts a session, a person or a program, is in its manifest.** A session's principal is a person or a program:
  `Session.start(principal=)` and `prepare(principal=)` take `human:<name>` or `program:<name>`, and `Manifest.principal` names
  it, a manifest from before reading its `human` as one. A program's message goes as its reader's setting says, and a session a
  program starts issues no owner credential, so a guest of its runtime holds a view credential, and it cannot detach, at a start
  or a resume. See [RFC 0050](docs/rfcs/0050-a-script-is-a-person-or-a-program.md).
- **`Team.recipients(to=None)`, the one rule for whom a session's prompt goes to: the agent `to` names, or else every agent the
  session starts.** See [RFC 0051](docs/rfcs/0051-one-rule-for-whom-a-prompt-goes-to.md).
- **The contract a training system's authority builds on, which names nothing after any training system.** Model access is one
  value: variables by name, or a `Gateway(origin, bearer, model, tools, compaction_headers)`, whose origin is a scheme and a
  host and nothing more and whose bearer is masked in every form, given only to a driver that declares the new capability
  `sealed`, with its model the one pinned and its login `gateway`, which is no plan login. `keys_of(spec)` reads variables by name
  and refuses a gateway. `Admission.backend` is the backend's ids for its agent, each entry its alone, holding no secret of the
  admission's own as a key or a value in any form, which the admit effect records as its result and the agent's record keeps, at
  view version 14, and which a gateway admission must name. A gateway's bearer is one agent's, so a second agent admitted on it is
  refused, and a resumed admission that gives other backend ids or other access than its agent had loses the agent. `SpawnRequest`
  carries the `parent` and the `goal` its `agent.spawned` records, and `AgentOutcome` the `report` its end keeps and a `status` of
  the five ends. See [RFC 0049](docs/rfcs/0049-the-contract-a-training-authority-gets.md).
- **One list of a secret's forms, for masking and for tests.** `config.forms(secret)`, the forms text may carry a secret in,
  which the `Redactor` masks and a gateway, an admission and a training system's tests look for; and a `Secret` equals another
  of the same value.
- **An example team of two harnesses, runnable with no keys.** `examples/mixed-team`, a Claude Code lead and a Codex worker in
  one session, coordinating through the queue `tasks`, the board `notes` and messages, with a README that runs it headless,
  watches and steers it from the terminal UI and the page, reads its provenance, swaps a role's harness for pi or OpenHands with
  `--set`, and runs it with no keys on scripted stand-ins. The test suite runs the file with those stand-ins, from the command
  line and from the page with the terminal UI attached, and on the real binaries against FakeModel, a Claude Code lead beside
  each of Codex, pi and OpenHands.
- **An empty read names what was already handed over.** An agent's read that finds nothing past its own cursor answers with `next`,
  naming what the offer that last moved that cursor handed over on that stream, by the refs it was shown, and the `after` that reads
  it again, in the words of its surface, unless that offer was a read of its own or the read's filter passed over something new: a
  wake moves the cursor past what it hands over, so a read right after found nothing, and a Codex model took that for an empty
  channel. `Deliveries` is at view version 12, keeping the offer that last moved each cursor. See [RFC 0047](docs/rfcs/0047-an-empty-read-names-what-was-already-handed-over.md).
- **An agent's process is not its identity.** Any agent between turns for ten minutes on the session's clock, with no setting, rests
  when its harness is persistent and resumes by a native id it gave: the courier asks `agent.rest`, a runtime-only op, a `rest`
  effect ends its process tree, and its next handover brings its harness back first, natively, or anew where it took no turn, on a
  fresh credential and offering nothing, as a resume after a crash does. A held agent, one with a goal not begun or a finish to come,
  never rests, and a runtime start leaves a resting agent to its handover. A harness that exits on its own rests its agent once,
  its turn cut off and told, an exit telling nothing else but a goal not begun that waits nowhere already, and a second exit before a
  turn of its ends loses the agent, a harness brought back from rest that exits before it is ready among them. `delivery.ready`
  lists the agents to put to rest, `Agents`, at view version 13, keeps `idle_since`, `resting` and `exits`, the roster carries
  `resting`, and the terminal's inspector says an agent rests and what brings it back. See [RFC 0045](docs/rfcs/0045-an-agent-s-process-is-not-its-identity.md).
- **A level is earned on the machine that runs it.** `platoon-harness doctor --check` runs every conformance check on each harness the
  SDK ships a check of that it finds, on the binary that runs, against FakeModel and on no account, through `check_harness` in
  `platoon_harness.testing`, and keeps the result under the root, `conformance/<driver>.json`, which `write_conformance` and
  `read_conformance` in `platoon_harness.runtime.paths` write and read. The host reads it at every launch and resume, so an agent's
  levels come from it, and records it on `agent.started` and `agent.resumed`, at payload 2, as `conformance`, a body beside the
  levels, where it speaks for the harness that runs. A result is pinned to its driver, by name and by the class that implements it,
  the harness version it said, the SDK and the host, as `Conformance.implementation`, `Conformance.sdk` and `Conformance.host`, which
  `check_driver` sets, and the same fields of `Profile` say of the agent, `levels.implementation` naming a driver's class; a version
  nobody said pins nothing. A level with no result that speaks for it is `unverified`, naming what makes one, `doctor --check` for a
  harness a check ships for, which `levels.CHECKED` names with the class that drives it, and `check_driver` with
  `write_conformance` for any other. `levels.speaks_for` says whether a result speaks for an agent, and `levels.unmet_by` which
  levels its failed checks leave unmet. `doctor` says whether each harness's kept result speaks for the binary that runs, and what
  it found, skipped and left unmet; `--check` goes on past a check that cannot run and keeps no result that names no version.
  The terminal's inspector says the login kind beside the levels, which the roster carries as `login`, and `Agents` is at view
  version 12. The scripted harness has a `shell` tool of its own, `testing.SHELL`, which runs its `command` once allowed, so it and
  the conformance wire program meet every shell check, and the wire program earns `operational`. No check proves a coverage surface,
  so nothing answers `not_seen` yet. See [RFC 0044](docs/rfcs/0044-a-level-is-earned-on-the-machine-that-runs-it.md).
- **A daemon that keeps failing needs a person.** The supervisor journals a daemon's failure when it begins a run of them or says another
  error than the last, as `daemon.failed` naming it and its error, and the next run that lasts a minute, as `daemon.recovered`,
  through two runtime-only ops of the kernel's, `daemon.fail` and `daemon.recover`, so a courier or a host that fails on every pass
  stands in `attention` as a kind of its own, `daemon`, saying where its traceback is, what starts it anew and its latest error,
  until it runs a minute or a new runtime starts, and the terminal's dock and the browser's Needs you say so where a quiet session
  would show. The kernel takes the namespace `daemon`. `Attention` is at view version 4. See [RFC 0046](docs/rfcs/0046-a-daemon-that-keeps-failing-needs-a-person.md).
- **A person follows provenance from where they read.** In the terminal, `/provenance`, or `p` with the transcript in focus, opens the
  chosen line's provenance in a panel; in the browser, Provenance among a message's actions opens a pane, on a view link too, from
  `x_provenance`, a read of ours beside SwarmChat's. Both show one event at a time, worded once for both: its sources, its uses, its
  contributors, and what estimators said of it, each link labelled by how it is known and followed into its own event, each answer's
  head, bound and open turn said, what it does not hold below its bound said as not held there and never as never, `unknown` with its
  reasons, where a read's result returned, to its harness or to the Code Mode script that made a Codex call, why a link opens nothing
  in its place, and credit only as each estimator's statement, by producer, version and params, never summed. A line that carries
  another event's words opens on that event, and a harness's report of a tool item names the call its report names and opens what
  its agent's command under it made, so an agent's own transcript leads to its writes. The browser's links are buttons and a
  message's actions show while focus is in it, so the keyboard reaches both. The browser's projection, at version 6, keeps the ref
  of the event each line shows, so a link a chat shows opens that chat too. `lineage` names, for a harness's report of an item, the
  call that report names, and for a tool item the first event of each command its agent made under its id, as `Made.commands`. See
  [RFC 0043](docs/rfcs/0043-a-person-follows-provenance-from-where-they-read.md).
- **Agents are asked to cite.** The preamble template has a ninth slot, `citing`, which asks an agent holding a write of content to
  put the `ref` of what its write rests on in `based_on`, and the default template fills it, so asking is on by default; a tool's
  description says what `based_on` is and never asks, so a template without the slot asks nothing. It costs 78 bytes a request, 20
  tokens by Qwen3's tokenizer. `tests/live/test_citing.py` runs it on real models. See [RFC 0042](docs/rfcs/0042-agents-are-asked-to-cite-by-their-template.md).
- **An `Informed-By` trailer may cite an event of the session.** A commit's `Informed-By` trailer takes an event's ref, such as
  the board entry the commit implements: once checked as any citation is, and only in a commit an agent of the session made, of
  an event that agent made or was handed, it joins the commit's `based_on` beside the commits its hex values name, so lineage
  shows it with the commit maker's exposure and contributors walk from code to what informed it. A trailer travels with its
  commit between clones and sessions, so one made elsewhere, or by nobody the record names, cites no event here. A value that
  cites nothing stays as written, never refused, with why, `unrecorded`, `no_event`, `no_lines` or `unread`, which
  `repo.committed` keeps at payload 2 and lineage gives as `Unresolved.why`. See
  [RFC 0041](docs/rfcs/0041-a-commit-cites-what-informed-it-by-its-ref.md).
- **Pi names what landed and which call made a tool call.** The `pi` driver reports an input under the id of the entry pi wrote it
  down as, asked of `get_entries` from the last entry seen once the input's message has ended, and holds whatever pi says after the
  input until it has that id, and whatever it says after a compaction until it has named what that forgot, so its reports keep
  pi's order; a compaction then marks a handover pi took `forgot` or `kept`. Our pi
  extension puts pi's own id for a call of ours among its arguments as `_meta`, and the stdio shim moves a `_meta` it finds there to
  where MCP keeps it, so the call goes under `pi/toolCallId`, a harness's anchor, which pi's tool item holds: a read through pi is
  confirmed by that item, and a pi tool call joins the model call that chose it. See [RFC 0040](docs/rfcs/0040-pi-names-what-landed-and-which-call-made-a-tool-call.md).
- **Four provenance queries: `exposure`, `lineage`, `uses` and `contributors`.** Provenance queries for people and programs,
  none an agent's tool: `exposure(agent, ref, before)` answers `seen`, with each offer its harness said it took and each
  compaction since marked `forgot`, `kept` or `unsaid`, `not_seen` or `unknown`, with every reason, and never a boolean;
  `lineage(ref)` is one hop back, with the model call that chose the event, each citation with its citer's exposure, each cause,
  its ancestry and a page of what its maker was offered and the gaps in its record; `uses(ref)` is one hop forward; and
  `contributors(ref)` names each maker a walk back along citations, causes and ancestry reaches, and apart from them the makers
  only handed to one, weighing nobody. Each is a `Session` method with a typed answer, `Seen`, `NotSeen`, `Unknown`, `Lineage`,
  `Uses` or `Contributors`, and a command of its name. An answer about an event an agent made is bounded at the model call that
  chose it, on its own report stream, at its commit, or for a git commit at the look that recorded it, said; it says its `head`
  and whether its turn is `open`; each list in it is a page beside its true count; and it is the same after a rebuild and on a
  closed copy. A ranged citation's lines are shown true, or null when nothing confirmed shows them. A client's query runs off
  the runtime's event loop. No check proves coverage yet, so nothing answers `not_seen`. See
  [RFC 0038](docs/rfcs/0038-provenance-is-answered-from-the-record.md).
- **Bring an old session's views up to date after an upgrade.** `platoon-harness session refold`, which brings a session's views
  up to its journal while no runtime holds it, writing no event, so its history and the queries answer again after an upgrade
  changed a view.
- **The views behind them: `Exposures`, `References` and `Calls`, and `Gaps` at version 2 as an index of each gap by where it began.**
  `Stamps.event(seq)` gives the event a `cause` names.
- **Estimators write rewards and credit in a file of their own.** Rewards and credit beside the journal, in
  `annotations.sqlite`: `Session.annotate` and the `annotate` command write one by a named producer at a version, about events
  at or below its `head_seq`, with a `scope`, a required `status` and a value only when scored, on a live session or a closed
  one with no runtime, and `Session.annotations` and `annotations` read them: the one way in and out, each statement checked
  against the journal. The same statement again is answered with the first, and another under the same producer, version,
  params, target and kind is refused `conflict`. The file keeps a write-ahead log and an index on the target. Nothing an agent
  can reach opens the file, and no estimator ships. See [RFC 0039](docs/rfcs/0039-estimators-write-beside-the-journal-at-m2.md).
- **Refs on everything a model is shown.** A ref is `stream@version`, with `#La-b` for lines of that event's body, and every result,
  handover, notice and refusal names what it shows by one: a message row says `body: true` and gives no hash, `rest` is an event
  ref with a range, and `blob.get` takes the ref of the event that carries a body. Every write of content returns the ref it made,
  `task.claim` and `task.list` name a task by its `task.added` ref and a result by `result_ref`, and `agent.spawn` returns
  `agent/<name>@1`. See [RFC 0036](docs/rfcs/0036-one-ref-names-what-a-model-is-shown.md).
- **An announce or a report is shown by the ref of what it repeats.** A message that repeats another event's words is shown and
  handed over by that event's ref, and names it as its cause: a board's or queue's announce by the write, a child's report by
  its `agent.finished`, its turn's last message, or else its end, and a goal told again by its spawn. `reply_to` finds an entry
  by the ref it was shown by. `message.sent` is at payload version 3, and its data names that ref as `carries`.
- **Every write of content takes `based_on`, and every citation is checked.** `based_on` on `agent.spawn` and `agent.finish`, so
  all eight writes of content take it, and every citation is checked: a ref must name an existing event, and a range lines of
  that event's text body, or the whole write is refused naming it. A body in `blobs/` keeps its range as given, and a citation
  of something its citer was never handed is kept as its claim. `cited` is the check, for an extension's own writes, reading
  each ref, event and body once, and refusing a `based_on` too long for an event first. `DATA_LIMIT` is a public kernel name.
- **A goal is delivered as any input is.** The launch offer: a fresh start's `agent.instruct` offers what that launch hands the
  harness, its instructions and its goal, and the goal goes as the first delivery under that offer's id, so `AgentSpec.goal` is
  a `Delivery` and each driver sends it as it sends any input. The first input a harness says it took confirms its own launch,
  and never one a harness before it was offered. A native resume offers nothing. `platoon_harness.testing.goal` makes one for a
  test, and the conformance check `delivered_text_in_next_prompt` holds a driver to saying its goal landed under the launch's
  id. See [RFC 0037](docs/rfcs/0037-an-offer-is-confirmed-only-by-its-harness.md).
- **A read is confirmed by its harness's own report.** A tool item that came back `completed`, whose `native_id` is the anchor a
  read went under, confirms that read, with the evidence `tool_item`, and one that `failed` confirms nothing: an offer is
  confirmed only from its harness's own report. The surface hands a steer notice and a body only it could read under the call's
  anchor too.
- **A body never handed reads as a miss.** `blob.get` reads the body of an event its caller was handed or made, and answers any
  other `not_found`, as a miss; a person or a program reads any. `blob.hash`, a runtime-only query, lets the tool plane read a
  body in `blobs/` without a model seeing its hash.
- **Posts and a map of who talks to whom, in the page.** SwarmChat's Board and Map over a session: `view_posts` and
  `view_activity` answer from the projection in SwarmChat's shapes, posts from a chat or from every channel and group, sorted
  new or active, and messages over time, by the journal's times. A session's messages take no reactions, so a post's votes are
  null, hot and top are refused, and the page draws them and each post's vote control disabled, saying why. A queue's or a
  board's chat draws Tasks or Entries disabled, as the tasks and board views are planned. A post's thread is followed by an
  index on each message's parent, so the Board's time grows with a session's messages and not with their square; the projection
  is version 4, which `web` folds again from the journal when it starts. See `docs/how-to/web.md` and
  [RFC 0035](docs/rfcs/0035-the-board-and-the-map-over-messages.md).
- **The runtime records what each agent's turn left.** The look: at each turn's end and each resume the lifecycle asks the host
  for a `probe`, and an agent's stop looks once more before it ends the workspace. Looks run one at a time, change no ref, index
  or file, and record on `repo/<name>`, with no agent in the envelope, `repo.committed` once per new commit, parents first,
  `repo.rewritten` for what a branch no longer reaches of what the journal holds, and `workspace.changed` for a workspace's
  head, branch and uncommitted state when they differ. A commit is the agent's whose workspace's HEAD reflog records making it
  at its committer time, and an `Informed-By` trailer is resolved once from hex alone. A look that fails records the gap
  `workspace_unobserved`, and the Ending names the agents whose last look never finished as `unobserved`. `repo.report` and
  `repo.looks` are runtime-only ops. See [RFC 0032](docs/rfcs/0032-the-runtime-looks-and-never-moves-a-branch.md).
- **A row per commit, workspace and uncommitted path.** The `changes` view rebuilt on the look, with a row per commit, per
  workspace reading and per uncommitted path, each with the `seq` that last moved it; a `conflict` attention row while an agent
  rests on a conflict its look found; the roster's `workspace`, `agent.status`'s workspace and why it was kept, and
  `session.status`'s `repo`.
- **`/review` and the header show what changed.** In the terminal, the header says what changed, `/review` or Alt+D lists it,
  grouped by workspace, newest recorded first, a snapshot's group saying its commits are in its own repository, with rows past
  your mark marked new, the inspector names the agent's workspace and why its stop kept it, and the dock says where a conflict
  is resolved. In the browser, a conflict is listed under Needs you, saying the same. What an agent wrote of a commit, its
  author and each `Informed-By` value, is cut to fit, and a commit's first 16 values are kept with how many it had.
- **An agent's own repository, holding your uncommitted work too.** `workspace = "snapshot"`: a repository of its own in the
  session folder holding your tree as your git sees it, uncommitted and untracked work included, captured in your checkout under
  its own config into the snapshot's own store and index, reading your objects through alternates and holding in its own pack
  what your refs did not reach, with your identity and file-reading values and no remote. It is built aside and renamed into
  place last, so a retry adopts it; refused before any cost, and again when made, for filtered tracked files, a sparse checkout,
  an untracked repository inside the tree, or an operation under way or a conflict in your checkout; ended by the same lossless
  rule, a kept one made whole. A split index of yours is written whole into it.
- **An agent on a branch and a worktree of its own.** `workspace = "worktree"`: a linked git worktree of the session's
  repository, locked, on `platoon-harness/<session>/<agent>`, at `agents/<agent>/workspace` in the session folder, made in three
  steps git keeps a fact of, so the `workspace` effect is retried after a crash and adopts what an earlier attempt made. A
  launch and a resume run where the journal says the agent works, and a resume whose worktree has gone, or left its repository,
  ends its agent `lost`, naming the fix. See `docs/how-to/workspaces.md` and
  [RFC 0031](docs/rfcs/0031-a-workspace-is-a-place-git-already-knows.md).
- **What a workspace cannot be given is said before anything spends.** Refused before any cost: a git mode outside a work tree,
  in a bare repository or one with no commit, on git older than 2.36, with LFS files and no filter, from a subfolder the
  workspace would not hold, or where a session's branches exist, naming another session name first; a session folder unignored
  in its repository's work tree, in every mode. Warned of: submodules, uncommitted changes, named, and a Codex role in a
  worktree or a snapshot whose commits would each wait on an approval, naming its three postures, or be refused under
  `approvals = "deny"`.
- **A worktree with anything in it is kept, saying why.** An ended agent's worktree removed only when git says nothing would go
  with it, whatever your status config says, and otherwise kept, locked, and named in the Ending's `workspaces` with its host,
  path, branch, size and why, naming what it found, and a `release` of quoted commands only where they lose nothing it was kept
  for but the ignored files it names. A stop a crash cut finishes when it is retried.
- **Every commit the journal recorded, kept in one bundle.** `commits.bundle` in the session folder at each stop, holding every
  commit the journal recorded past the session's starting HEAD, recorded on `session.stopped`, with nothing written into your
  repository.
- **The repository a session opens on, in `session.opened`, with every ref and its tip at open as a body.**
- **`runs_in_its_workspace` in `check_driver`, which `operational` needs.**
- **`platoon_harness.runtime.git`, the runtime's one git runner, which runs no hook, no fsmonitor and no gc, and
  `platoon_harness.runtime.workspaces`.**
- **Send, reply, attach, approve and stop from the browser.** Acting from SwarmChat's page, on a control link, each act one op
  through `/x/command`: a composer at the foot of a chat that names its target, sends on Enter, starts a line on Shift+Enter and
  cuts a long text by the function the terminal cuts with, a reply in a thread citing the message's entry, a file as a message's
  body with the most a body may be said first and its progress shown, approvals as cards with Allow and Deny, Needs you with its
  count, from the runtime's `attention`, and an agent's interrupt, stop below, retire and cancel and the session's close and
  cancel, each asking first where the terminal does. Each act keeps its key until answered, across a lost connection and a
  reload, so a retry is one operation, and a refusal shows its reason. Every control the person cannot use says why. See
  `docs/how-to/web.md` and [RFC 0028](docs/rfcs/0028-acting-from-the-page.md).
- **`view_info`'s `x` says `body_limit`, the most bytes a body may be.**
- **End-to-end tests of the page in Chromium.** The browser suite, `tests/e2e/`, in Chromium's headless shell: a message in an
  agent's input path once, on a wire harness and on the real `claude` binary against FakeModel, the browser and the terminal
  attached at once, approvals raced from two clients, credentials, `Origin` and a rebound `Host` from real pages, hostile
  rendering under the policy, reconnects, receipts and history.
- **Watch a session in the browser.** `platoon-harness web SESSION`: SwarmChat's pinned page over the session's journal, in a
  browser, as a guest on the owner's control credential that starts and resumes nothing and follows the session across runtime
  restarts. A follower folds the journal one way into `swarmchat.sqlite`, with ids a rebuild gives again, and serves the page's
  `view_*` replies from it, with "Delivered to" from delivery evidence in place of "Read by". A view link and a control link,
  each opening once for a session token that expires; `Host` and `Origin` checked; loopback unless `--host` names another
  address with TLS. `/x/command`, `/x/body` and `/x/link` take what the page will send. The page reads in this stage, and every
  act is drawn disabled, saying why. See `docs/how-to/web.md` and [RFC 0027](docs/rfcs/0027-the-browser-on-our-backend.md).
- **`platoon_harness.runtime.control.BODY_LIMIT` and `platoon_harness.primitives.IN_A_RESULT` are public.**
- **`platoon_harness.http`: the tool server's bounded HTTP, as a module of its own with public names.** `Origin`, when a request has
  one, must now be the origin of its `Host`.
- **The session kernel: journal, writer thread, operations, grants, effects, timers, views, readers and daemons.**
- **Messages, boards, queues, waits, lifecycle, approvals and budgets.** The core primitives as extensions on the public kernel:
  messages and channels, context, wait, boards, leased queues, lifecycle and completion, approvals, budgets, and the `roster`,
  `attention` and `changes` views.
- **Teams and topologies: roles, nine presets that mix by union, one compiled grant table, `team_check`, and `team.show()`.**
- **Layered configuration, `Secret`, the reproducibility manifest, and extension discovery from metadata alone.**
- **The tool plane: a tools-only MCP server on loopback, a stdio shim, `ph`, and one derivation of tools and the preamble from
  `ops.list`, per token.**
- **`platoon_harness.rpc`: one line-delimited JSON-RPC 2.0 peer on asyncio streams, split on LF only.**
- **The driver contract: seven methods, one closed report vocabulary, `levels`, and `docs/extending/drivers.md`.**
- **`Process`, for every subprocess driver: a group recorded before exec, pipes that always drain, a bounded masked log, and a
  verified `stop`.** `harness_env` is the allowlist of section 15.
- **`WireDriver` and `serve`, and the `exec` driver.** `harness = { command = [...], mode = "wire" }` names a program in a team.
- **`platoon_harness.testing`: `ScriptedDriver`, `FakeModel`, `FakeTools`, `check_driver` and `check_extension`.**
- **The runtime: from a `Team` to a live session, through ops and safe to repeat.** The session folder, its socket and its tokens. The
  host, which performs every effect on a driver, level-triggered. Recovery per agent after a crash, and `python -m
  platoon_harness.runtime <folder>` as a detached runtime with the owner's shutdown on `SIGTERM`.
- **A session from Python: start, attach, resume and settle.** `Session`: `start`, `attach` and `resume`, one link in-process or
  over a control socket, typed wrappers held to the op table by a test, and `settled()`, whose `Ending` states a reason an exit
  code can be made from.
- **The control socket: JSON-RPC lines with a credential checked once per connection, separate view and control credentials, pull only.**
- **`Authority` and `LocalAuthority`, and `Session.start(team, authority=...)`.**
- **`from platoon_harness import Session, Team, Role, Ending, Refused, on, load_team`.**
- **`session.ending`, `agent.records`, `effect.list`, `lease.due`, `budget.lapse`, `Kernel.read_only`, `is_held`, and
  `schema.seconds`.**
- **`session.ending` gives each agent's last `report`.** `agent.conclude` and `agent.retell` are runtime-only ops, and `kernel.first` is
  the one race helper. A live text frame is cut at 64 KiB.
- **Claude Code as a harness.** The `claude` driver: `claude -p` in stream-json with the control protocol on the same pipes, in
  the user's own setup, with every approval through the runtime. `check_driver` passes on the real binary against FakeModel, at
  2.1.316.
- **The `codex` driver: `codex app-server` on stdio, in the user's own setup, with every approval through the runtime.** `check_driver`
  passes on the real binary against FakeModel, at 0.164.0.
- **pi as a harness.** The `pi` driver: `pi --mode rpc` in the user's own agent directory, with our tools through the stdio shim
  from one extension loaded with `-e`, and `gated` approvals through the runtime. `check_driver` passes on the real binary
  against FakeModel, at 1.5.0. No live model has run.
- **`sandbox` on `AgentSpec`, from the role.**
- **`effort` on `Role` and `AgentSpec`, handed to the harness as it stands.** A driver that cannot honor one fails the spawn.
- **`Session.start(team, plan_login=True)`.** A driver reports the login kind, and `prepare` refuses several agents on one plan login
  without it, naming the fix.
- **`check_driver` rows `unset_model_refused` and `native_child_seen`, and its `tool` and `child` arguments, because a real harness
  knows our tool by a prefixed name.**
- **`peers` lists the `roles` you may start an agent in, and the preamble names them.**
- **The preamble says how to end: an agent somebody spawned makes `agent.finish` its last call, and one the session started stays unless
  told to finish.**
- **Agents that take follow-ups.** `stays` on `Role`, on `agent.spawn` and on `Session.spawn`: an agent that stays takes a
  follow-up task or a question by message after its first, on the same harness, until it is told to finish, retired or
  cancelled. It is resolved once, at the spawn, from the spawn, then the role, then whether the session started it, and refused
  for a harness that is not persistent. `agent.status` shows it, and the result of a spawn that stays says how to end it. See
  [RFC 0023](docs/rfcs/0023-agents-that-stay.md).
- **Change what each agent is told.** `preamble` on `Team` and `Role`: the generated part of what an agent is told is a
  template, a role's in place of its team's, with eight slots the runtime fills per agent and per surface, and `PREAMBLE`, the
  default, renders what it said before byte for byte. `name` and `tools` are values and the rest sentences of ours, a line that
  holds a slot and comes out blank is left out, so no word of a template's is, and an empty template tells nothing. A slot
  nobody fills is refused when the team loads, an op in backticks in a template's words or a role's `instructions` is named as
  the surface names it, and `team_check` warns of a template that leaves out `tools` or `ending` and of words that name a tool a
  role cannot hold, refuses a role's own template on a harness that reaches none of our tools, and warns of its team's.
  `agent.instructed` journals the exact text added to each harness, at launch and at every resume, which hands a harness that
  reopens its own session what it was told when that began. `told(team)` renders what each role would be told, starting no
  harness, and `tools.NAMESPACE` and `tools.surface_of` say how a harness names our tools.
- **`allow_native_children` on `Role` and `AgentSpec`.** A harness's own agents are off unless a role allows them, as such an agent's calls
  reach us only in its parent's total, no topology binds it, and its calls to our tools go out on its parent's token. Claude Code's
  `Agent`, `Workflow`, `ListAgents` and `SendMessage` are disallowed, and Codex's own agents are off for the thread by
  `agents.enabled = false`, both generations. `team_check` says what a role that allows them gives up, `check_driver` has the row
  `native_children_off_by_default`, and `Request.tools` names the tools a model is shown, exactly.
- **`tests/live/test_launch.py`, a live test of what an agent is launched with.** `tests/live/test_launch.py`: a job an agent
  would hand to a sub-agent of its own starts none, and a team's template reaches the model, on Claude Code and Codex. Live
  tests count the agents that open a turn with a `wait` naming nothing.
- **`tests/live/test_stays.py`: the owner's flow on Claude Code and on Codex, and a Codex child's half alone.** `tests/live/test_codex.py`
  runs a Codex agent's own sub-agent.
- **Run, follow, steer and check sessions from a shell.** The headless command line, `platoon-harness`: `run`, which owns a
  session in the foreground from a team file, the project file or `--harness`, with a prompt from an argument, stdin or a file;
  `serve`; `events`, from a cursor and following; `session list`, `show`, `stop` and `resume`; `team check`, `show` and `told`;
  `init`; `doctor`; `extension list`; and a command for each op a person may run but `wait`, made from the op registry and its
  schemas, so `ph task.claim --queue tasks` for an agent is `platoon-harness task claim SESSION --queue tasks` for a person, its
  help naming commands and flags where its op names ops and arguments. `--json` prints one line per event the runtime it owns
  journals, from its `runtime.started`, and then the Ending, in a shape versioned by `format`. Exit codes are an Ending's, 64
  for usage, a refused `run` or `session resume` among it, and 78 for configuration. Ctrl+C or `SIGTERM` at any point runs the
  owner's shutdown. `--approvals` answers every approval one way and the manifest keeps it, and nothing prompts.
  `docs/reference/cli.md` is made from the command definitions, and `docs/how-to/headless.md` is a quickstart.
- **`kernel.registry(extensions)`, the op table before any session exists, and `Op.agent`, which keeps `agent.finish` to agents by
  kind as `runtime` keeps an op to the runtime.**
- **`runtime.opening.check(team, plan_login=)`, every problem `Session.start` would meet, which `team check` prints, and
  `Session.head()`.**
- **An interrupt wakes nothing that came before it.** An interrupt quiets what was waiting for its agent, whoever interrupts:
  what came before it wakes nothing and stays unread for the next turn, and a wait that already holds closes with no notice,
  while what comes after wakes as usual. `wake.quieted` records it.
- **`platoon_harness.tools.taught` and `OP_NAMED`, which the command line words its help with.**
- **`tests/live/test_cli.py`: milestone 1's flow from a terminal, and a stop and a resume of a live session.**
  `tests/integration/test_cli_harnesses.py` runs, stops and resumes from the command line on each real binary against FakeModel.
- **A transcript pages back from the journal.** `before` and `streams` on `Kernel.read`, and through every link form, as
  `Session.page`: a page back from `before`, still in order, whose cursor is the next `before`, and a set of stream names a page
  holds besides what `match` globs, so a transcript pages back without reading the journal whole. `Session.events` takes
  `streams` too. bug-clients-3.
- **A person's place in each stream, which acknowledges nothing.** `Session.marks()` and `Session.mark(stream, seq)`: how far a
  person has read each stream, kept per principal in `marks.sqlite` beside the journal, with no runtime, and apart from an
  agent's cursor, so moving a mark acknowledges nothing. A mark only moves forward, and a view credential moves none.
  `Link.principal` names who a link acts as. bug-clients-7.
- **`below` on `agent.interrupt` and `Session.interrupt`: one act that stops the turns of an agent and of every agent below it and
  keeps them all.** It stops turns, not waits, and says whose: an interrupt answers `{stopped}`, where it named an effect.
- **`agent.unread` and `Session.unread(agent)`: what the roster's `unread` counts, with how each entry would land, for a chip and a
  queue line above a composer.**
- **Client tests on the real Claude Code, Codex and pi binaries against FakeModel.** `tests/integration/clients.py`: the live
  tail, stop below, an interrupt under a `tokens` limit and a child's anchor, run on the real Claude Code, Codex and pi binaries
  against FakeModel. `tests/live/test_interrupts.py`: an interrupt during a call under a `tokens` limit on real models, after
  which the session goes on.
- **The terminal UI: `platoon-harness` on a terminal opens the sessions screen, and `platoon-harness attach SESSION` one session.** It
  starts a session on a detached runtime and is its guest, so Ctrl+D detaches and the session runs on. The workspace has a navigator
  grouped by what a person must do, a focus pane with a transcript read from the journal a page at a time, live text below it, an
  inspector, a dock of the places a person must act, and a composer whose target is always shown. One keymap table makes the
  bindings, the help, the footer, the palette and the keymap of `docs/how-to/tui.md`. Untrusted text crosses one `SafeText` boundary.
  `tests/live/test_tui.py` drives it with Pilot on a Claude Code lead and a Codex worker.
- **Needs you, working, blocked, idle, done or failed, alike in every client.** `group` on each roster row: what a person must
  do about the agent, `needs_you`, `working`, `blocked`, `idle`, `done` or `failed`, derived in the view so every client says
  the same.
- **No act out of reach in an editor's terminal.** Every act of the terminal UI takes only keys every terminal delivers, so an
  editor's terminal that keeps Ctrl, Alt or F keys, as Cursor's on a Mac does, leaves none out of reach. In the composer a line
  that is exactly `/` and an act's name runs it and goes to no agent, `/` alone lists them, `/` from any other part begins one
  there, and the footer always begins `/ commands`. Tab and Shift+Tab go round the parts in the order they are on screen. The
  dock takes focus with no place chosen, so its `y` and `n` answer only a place chosen there with the arrows. The sessions
  screen has a plain key for each act, `?` the help, `p` the palette and `q` quitting among them. `docs/how-to/tui.md` names the
  VS Code, Cursor, Terminal.app and iTerm2 settings that keep keys. [RFC 0026](docs/rfcs/0026-every-act-from-any-terminal.md).
- **Agents are told our tools by the names their harness shows.** `tool_names` on `Capabilities`: a harness that shows our MCP
  tools by their own names, as OpenHands does, says `bare`, and its agents are told them by those names, in their instructions,
  handovers and refusals, through `?surface=mcp`.
- **OpenHands as a harness.** The `openhands` harness: a wire worker per agent on OpenHands SDK and tools 1.59.0, which the
  SDK's `openhands` extra, `platoon-harness-sdk[openhands]`, pins exactly, and which `harness = "openhands"` runs as
  `python -P -m platoon_harness.drivers.openhands` on the runtime's own interpreter, finding its modules where the runtime does,
  `PYTHONPATH` among them. Only the worker loads OpenHands, in its own process, and an environment that cannot hold its pins
  runs the worker from one of its own as a wire command. [RFC 0030](docs/rfcs/0030-openhands-is-an-extra-of-the-sdk.md). It
  drives one conversation through `arun()`, signs in with a key from the role's auth profile alone, through the shell's proxies,
  gives the agent OpenHands' coding tools and ours through the stdio shim, asks the runtime before every action but ours, hands
  a delivery to the conversation only between runs with no action pending, pausing a run under way for it, leaves no action
  pending at a turn's end, says what a request carried from the SDK's completion log, and keeps its own agents off unless a role
  allows them, when their steps ask the runtime too and an interrupt stops them at their next ask. `check_driver` passes on the
  real SDK against FakeModel, and no live model has run. The workspace lock excludes the proprietary `lmnr-claude-code-proxy`,
  which nothing the worker runs imports, and which the extra installed from an index brings in unless excluded. `doctor` shows
  the version of the OpenHands SDK from the extra's metadata, or names the interpreter to install the extra for, a start without
  the extra is refused in the same words, and `init` passes it over. `WireDriver(command, inherited)` names what of the
  runtime's environment its program takes beside the allowlist, to describe it as to start it.

### Changes

- **The architecture page marks what STATUS calls planned.** [docs/architecture.md](docs/architecture.md) sends a newcomer to
  [Concepts](docs/getting-started/concepts.md) first, and marks each part STATUS calls planned where it describes it, linking
  STATUS: the library tier, `topology.patch` and `topology.show`, the topology table's team, board and tasks views,
  `session.metrics`, the ACP driver, the step that adds the session id at export, a person driving an agent's native session
  during a takeover, and the agent interaction graph's display.
- **Guides that say what you will do and need.** The how-to guides and the training guide open with their goal and
  prerequisites, and a section that is a task is headed by what you do there, the headless guide's as numbered steps. Their
  sentences are unchanged.
- **`propagate` is `propagate@3`, in place, under the same name and function.** Version 2 kept `propagate@1`'s walk, unchanged, and
  booked what each event keeps to the span it lies in too: the span holding the model call that made it, for an entry that
  carries an event, as a child's report does, that event's, and for an event tied to no call its turn's, when that turn is one
  span. Beside one local `credit` row per agent reached, on its first `agent.started`, it writes one per span reached, on the
  span's name, the `model.called` of its last call; an agent's row is its spans' rows and what it kept in no span, and version 2's
  agent rows were `propagate@1`'s on every journal. Version 3 adds one edge, the take: the events, but its own agent's, shown by
  offers its agent's harness confirmed taking before a call of its span, since the call before and its latest start or resume,
  and below the event's bound, so it walks offers its harness confirmed and never an unconfirmed one; a walk that meets an edge to
  an event no older than its own makes every row `invalid`. An entry that carries an event, as a child's report or an announce
  does, takes nothing of its own, as it reaches that event, and what it took, as its cause; by the entry's own bound, which is its
  commit, a read in a trailing call became an edge of words that never saw it. An agent that never started, as one whose launch
  failed, gets no row, as it has no start for one to target, and what its events keep is in no row, where the walk refused the
  whole episode once a read took its report. Where no span took another principal's event, its rows are version 2's. A span's
  row is now the one annotation target below an agent's: a turn's `turn.started` and a call's `model.called` were targets
  nothing wrote. See [RFC 0061](docs/rfcs/0061-credit-is-kept-per-span-and-a-span-rests-on-what-it-took.md).
- **One meaning for "span".** "Span" means one thing, a stretch of one turn of an agent: `primitives.Lines.span`, the
  `#L<first>-<last>` a result shows of a body, is `Lines.range`, as the read tools' argument already was, `schema.seconds` takes
  a `duration`, the facade's own alias for a duration is gone in favor of `schema.Duration | float`, and an episode is a part of
  a session. See [RFC 0061](docs/rfcs/0061-credit-is-kept-per-span-and-a-span-rests-on-what-it-took.md).
- **Scripted tool calls join their model call as real ones do.** `ScriptedDriver` sends each tool call a model chose under the
  id the model gave it, as `scripted/toolCallId` in MCP's `_meta`, which its tool item holds, so its op joins that model call as
  a Claude Code or pi tool call does, and two identical calls one model call chose are two ops, where the tool plane took the
  second for a repeat. The key is among the tool server's `HARNESS_ANCHORS`, so conformance's `tool_item_carries_its_anchor`
  runs on ScriptedDriver and passes, where it skipped. A call under an id it has sent already fails its turn, as its op would
  join the call that sent it first. A `Call` step, which no model chose, sends no id, as before.
- **No two of FakeModel's tool calls share an id.** `FakeModel` gives a tool call its script names no id `call_<reply>_<place>`,
  by the reply's number and its place in it, where every such call was `call_1`, so no two calls share an id, as a model's never
  do: under one id, a harness that sends it joined each later op to the first call and took an identical one in a later turn for
  a repeat. `ToolCall.id` defaults to None.
- **The seven live captures are reviewed for session and thread ids, paths, account and organization fields and what a
  model's account says.** In the Claude Code capture the two texts Claude Code itself wrote, its frame around a subagent's
  report and its message around a compaction's summary, are each reduced to their length, and the OpenHands capture
  describes its host neutrally; the others needed nothing. Compatibility's section 8 and the research index no longer
  ask for the review.
- **A test input lives with the tests.** The MCP probe's log, which `tests/unit/tools/test_replay.py` replays, is a test input,
  so it moved from `docs/research/fixtures/` to `tests/fixtures/`, where the research and RFC 0009 link it.
- **The research notes say they are dated.** The research is marked as dated background: its index is titled so, and each note
  opens with its date, that it is not maintained and that [reference/compatibility.md](docs/reference/compatibility.md) is
  current. The hosts the notes ran on are described neutrally, and pi-durable's citations of other notes by line are pinned to
  the commit it read. The brief says why it is kept and that the RFCs it names are Platoon's, and compatibility's section 8 asks
  as open questions what waited on the owner, and says what DAO is.
- **The privacy scan reads every text file git tracks.** The scan for local paths and account details is
  `tests/unit/test_no_internal_references.py`, after Platoon's, and reads every text file git tracks, every new one it does not
  ignore outside hidden folders, and the name of each, the tests and the configuration among them. It holds the site's words,
  its resource types among them, only as SHA-256 digests, so it no longer spells them out, and takes a numbered host, account or
  group by the letters before its first digit. It catches a key of the shapes Anthropic, OpenAI, GitHub and AWS give out:
  `sk-` keys, OpenAI's project and service account keys among them, GitHub's tokens, classic and fine-grained, and an AWS
  access key id. Each exemption names its text by its digest and says why; the only one is the author's contact each package
  publishes. `test_boundaries.py` keeps the import boundaries.
- **A README rebuilt for a newcomer.** The README follows Platoon's outline: the project's one sentence, what it gives you, each
  point as STATUS has it, the nine words of architecture section 2, installing from a checkout, a quickstart that begins with
  the mixed team on no keys, the SDK in a script, the milestones, the documentation, the layout, contributing and the license.
  `tests/unit/docs/test_readme.py` holds its words to architecture section 2, its milestones to STATUS and its Python to
  `examples/sdk-script/run.py`, and `tests/integration/test_examples.py` runs its first steps. The mixed team's README has a
  goal, what it needs, a table of its files and numbered steps, the output to expect from the run with no keys among them, and
  each package's README says what it is and links the project.
- **The no-keys run imports no test code.** The mixed team's scripted stand-ins live in the example,
  `examples/mixed-team/stand_ins.py`, on public names alone, so its no-keys run imports no test code:
  `PYTHONPATH=examples/mixed-team`, and `stand_ins:lead` and `stand_ins:worker` as the harnesses. Its tests run the README's
  command as the README shows it, and load the stand-ins' turns from that file.
- **Each package's description is the project's one sentence, after what the package is, and each wheel ships the MIT license
  as `LICENSE`.** The SDK no longer names macOS, where nothing has run, the command line has the SDK's classifiers, and both name
  the project's URLs and keywords.
- **The architecture decision records are RFCs, in [docs/rfcs](docs/rfcs/README.md) under the same numbers, with
  [a template](docs/rfcs/0000-template.md) and a process for proposing one.** The guides moved to `docs/how-to/`,
  `docs/extending/` and `docs/reference/`, and [docs/README.md](docs/README.md) lists every page.
- **A parent hears of a child's end once the authority's `finish` has returned.** Nothing reaches an agent while a stop of a
  child of its is under way: no handover, and no `released` from a `wait` it holds open in a call. So a parent hears of a
  child's end, by its report, by the notice of a wait that holds on it or by a held call's answer, only once the authority's
  `finish` for that child has returned, and is on its way to a turn until then. A call it makes once the child has ended reads
  the journal as it stands. See [RFC 0059](docs/rfcs/0059-a-parent-hears-of-a-child-s-end-once-its-authority-has.md).
- **A newer Claude Code, checked.** Claude Code's conformance test pins 2.1.319, which it updated itself to on the machines that
  run the slow pass, and on which its checks pass against FakeModel, 26 passed and 4 skipped, as on 2.1.318.
- **A snapshot's refusals say `a snapshot` where they said `` `snapshot` ``, as they hold for an isolated workspace too.**
  `runtime.looks.look` takes each workspace's tree with the wrap git runs under there, and a `wrap` of its own, as
  `runtime.workspaces.present`, `end_snapshot` and `operations` take one, and `write_bundle` takes each repository with its wrap.
- **Codex's conformance test pins 0.167.0, the version its checks last passed on, against FakeModel, as they had on 0.164.0.**
- **Claude Code's conformance test pins 2.1.318, the version its checks last passed on, against FakeModel, as they had on 2.1.316.**
- **`trainable` stands on the two sealed checks too, beside `ready_with_pinned_model`, `tool_in_first_request` and
  `call_ids_reported`.** See [RFC 0053](docs/rfcs/0053-a-gateway-admission-launches-sealed.md).
- **OpenHands' condenser calls are reported with the purpose `compaction`, where they were `condenser`.** Its `describe` says the
  SDK's version, and pi's says what `pi --version` said.
- **Pi's `ready.tools_visible` is pi's own list.** Pi's driver waits at start for our extension to say which tools pi declares,
  once ours have connected, so `ready.tools_visible` is pi's own list, and a server that never connects leaves our tools hidden
  rather than unverified.
- **`timeout` is an annotation status, and `unscored` is gone.** An annotation's status is one of five, `scored`, `invalid`,
  `error`, `timeout` or `cancelled`: `timeout` is new, and `unscored` is gone, as no statement is what unscored is. See
  [RFC 0052](docs/rfcs/0052-a-reward-has-five-statuses-and-eligibility-is-read-from-the-record.md).
- **`trainable` needs a driver that declares `sealed`, as well as a gateway login.** See [RFC 0052](docs/rfcs/0052-a-reward-has-five-statuses-and-eligibility-is-read-from-the-record.md).
- **`run` no longer refuses a team that starts several agents.** `run` sends its prompt to every agent the session starts unless
  `--to` names one, where it refused a team that started several, and refuses a team that starts none. See
  [RFC 0051](docs/rfcs/0051-one-rule-for-whom-a-prompt-goes-to.md).
- **What an episode came to is cited, and what it was worth is an annotation's.** `episode.close` closes on `based_on`, the refs
  of what the episode came to, checked as any citation is, in place of a free `outcome`, which an annotation says now;
  `episode.closed` is at payload version 2. `Session.close_episode(based_on=)` follows.
- **A session started trainable is never resumed.** `Session.resume` takes no authority, as a resume runs under
  `LocalAuthority`, and refuses a session started trainable, which `Manifest.trainable` records, or whose admit results name the
  backend's ids, before anything runs: an authority that has gone admitted its agents, so it stays history, even when a stop cut
  an admit short. See [RFC 0055](docs/rfcs/0055-the-export-is-the-session-as-it-ended.md).
- **The pinned model is the one that runs.** A launch whose harness runs a model other than the one pinned fails saying
  `it runs <model>, and <pinned> is pinned`, as the pinned model is a gateway's where access is one, and an agent's login is
  `key` when it was given variables, whatever its role names. See
  [RFC 0049](docs/rfcs/0049-the-contract-a-training-authority-gets.md).
- **A team that needs a program is refused before any cost.** `team check` refuses a `program`, naming it and what to use
  instead, while none runs, so `run` and `Session.start` refuse such a team before any cost, with exit 78 on the command line,
  the `map-reduce` and `git-swarm` presets among them. Before, it warned, and a session under `until = "program"` never ended
  short of its budget. See [RFC 0048](docs/rfcs/0048-a-setting-nothing-carries-out-is-refused.md).
- **An agent whose harness exits once is rested, not ended.** A harness that exits on its own rests its agent once instead of
  ending it: a turn it was in is lost, with `crash_window` naming where that turn began, its agent is told its turn was cut off,
  which wakes it at once, and the `rest` effect ends what the harness left. A second exit before a turn of its ends, an exit
  while the session accepts no work, or of a harness that cannot resume, ends its agent `lost` as before, the second saying so,
  and a harness brought back from rest that exits before it is ready has exited so, rather than failing six handovers.
  `Host.resume` brings an agent's harness back, for recovery and for a handover alike. See
  [RFC 0045](docs/rfcs/0045-an-agent-s-process-is-not-its-identity.md).
- **A kept result speaks only for what it was made on.** A result kept by `check_driver` is pinned to the class that implements
  the driver, the SDK and the host as well as the driver's name and the harness version, so a result made before, which names
  none of them, no longer reads, and `doctor --check` makes one again. `Profile` takes `implementation`. See
  [RFC 0044](docs/rfcs/0044-a-level-is-earned-on-the-machine-that-runs-it.md).
- **`ScriptedDriver` takes `version=None`, a harness that says no version.**
- **A refused query names `session refold`.** A read-only kernel whose views are behind its journal refuses a query naming those
  views and the fix: a writer refolds them as it opens, and writes no event, which `platoon-harness session refold` does.
- **A bystander's turn end is no contributor to a commit.** A look's commit and rewrite name no `cause`, as the turn end that
  prompted the look did not cause what git holds, so a bystander's turn end is no contributor to a commit in the shared
  workspace. Its reading and gap still name what prompted it.
- **`platoon_harness.annotations` is the schema alone: `annotate` and `annotations` there are gone, as `Session.annotate` is the one
  way to write a statement, checked against the journal.**
- **A commit nobody's workspace made has no maker.** `maker` names a commit's maker as the agent whose workspace made it, and
  None when nobody's did, and `blob.get` reads whether its caller was handed an event from the `Exposures` view.
- **A spawn is its spawner's event.** `agent.spawned`, at payload version 3, carries its spawner as its envelope agent, so a
  spawn is its spawner's, in its spawner's turn and context version, and the `Channels` fold reads the child from `data.name`.
  `agent.instructed`, at version 2, names its text `body`, as every content event does, and `agent.instruct` takes `body`.
  `context.offered` is at version 3, its items naming events by their refs. `Offered.body` says whether an entry has a body.
  SwarmChat's projection is version 5, naming a carried message by what it carries.
- **Four fields nothing wrote are gone from a model call's ref.** `ModelRef` holds `call_id` alone, the id a harness gave its
  call, verbatim: `policy`, `version`, `tool_call_id` and `token_span`, which nothing wrote, are gone, and an old row reads as
  its call. `ChildSeen` claims no `attribution`, as only the record can say how well a call is tied to an agent. A `GapReport`
  names only `what`, as each gap of the closed set, `GAPS`, has a plane, writers and a mark for whether content could reach an
  agent through it. Every incident gap is one `gap.recorded`, payload 2, with `since` naming where one recorded after the fact
  began: the cut turn's start, or outside a turn the request of the agent's oldest uncertain effect. `runtime.start` writes
  `crash_window` beside `turn.lost`, which at payload 2 names no gap, and `agent.takeover` records `takeover` where the hold
  begins, no longer at the release. `exposure_unconfirmed`, which nothing wrote, has left the set. The wire protocol is 2, which
  also hands a goal as a `Delivery`. `context.delivered` is at payload 3 and says how its offer was made.
- **Tool descriptions describe and never ask: `based_on` reads "Refs this write rests on.", and `board.get` no longer says to cite.**
  A refusal that said to store a body and cite its hash says to store a body.
- **The `changes` report has left the driver vocabulary, with `Changed` and `change.recorded`, as only the runtime observes a
  workspace.** The `changes` view's rows lost `agent`, `tests` and `since_mark`: a client compares `seq` with the person's mark.
- **Every name is a git branch part: no `..`, and no `.` or `.lock` at its end.** Such a name was accepted before, and a session folder
  named so is refused as no longer valid, naming the folder to rename while no runtime holds it.
- **A relative program in a `command` harness resolves against the session's cwd, for the harness and for `describe` alike.**
- **Claude Code's `EnterWorktree` and `ExitWorktree` are off on every launch, and a Codex thread naming a `cwd` other than its
  workspace is refused.** See [RFC 0033](docs/rfcs/0033-a-harness-s-own-worktrees-are-off.md).
- **`make_driver` takes the session's cwd, `open_session` the repository it opens on, `check` the session's cwd, root, name and
  approvals, and `session.stop` the bundle it left.**
- **`tools.surface_of` takes a harness's `Capabilities`, where it took its tool paths, as how a harness names our tools is
  `tool_names` too.**
- **`doctor --json` gives each harness it did not find a `reason`, `not on PATH` for a command.**
- **A `Profile` says whether its role allows the harness's own agents, and opaque native children cost `trainable` only then.**
  `check_driver` skips `native_child_seen` for a harness whose native children are opaque, as none can show, and still checks that
  they are off by default.
- **Esc elsewhere goes back to the composer.** In the terminal UI, Esc interrupts the agent in view from the composer only: from
  the transcript, the dock or the navigator it goes back to the composer and interrupts nothing. The footer names Esc by what it
  does from the part with focus, which is marked. Alt+Y, Alt+N, Alt+S and Alt+R are gone: a terminal sends Alt and a letter as
  Esc then that letter, so Esc then a word typed at once answered a place, stopped turns, or asked to resume, which can spend
  money. `/yes`, `/no`, `/stop-below` and `/resume` reach them. The dock takes focus from Tab or Shift+Tab, never on its own or
  from a click, and a part hidden while it has focus gives it back to the composer. Under 80 columns Esc or a row chosen in the
  navigator closes it. Acts are named as they are typed: `palette` where it was `commands`, `quit` for `leave`, `next-place` for
  `next for you`, `yes` and `no` for `first action` and `second action`, `open-line` for `open line`, `file` for `attach`, and
  `stop-below`, `page-up`, `page-down` and `takeover` joined where they were two words. The sessions screen looks again on `l`,
  where it was Ctrl+R. Search in a transcript, not built yet, has no key until it is, as `/` begins a typed command from every
  part of a session. The guide's keymap shows each key as the screen does.
- **Emoji joined by a zero-width joiner show whole.** The command line shows a control a terminal would act on, C0 but tab and
  newline, DEL, C1 and the bidi controls, as its escape, and nothing else, where it escaped every format character, which broke
  emoji joined by a zero-width joiner.
- **The problem a plan login with several agents raises is at `plan_login`, the setting that answers it, where it was at `roles`.**
- **A person's message to an agent steers, whatever the reader's delivery setting, and a script's `Session.send` is a person's.** An
  agent's message follows the reader's setting as before. Nothing withdraws a sent message.
- **An interrupt can stop a turn before it begins.** An interrupt of an agent on its way to a turn, by a wake that is due or a
  wait that holds, is accepted and cancels that wake or closes that wait, where it was refused. Before an agent's first turn
  begins it is refused saying so, where it said nothing was on its way, as `agent.retire` knew otherwise.
- **The preamble template's `peers`, `roles` and `channels` are values, `@a, @b` for `peers`, and the default carries our words around
  them.** A line whose slots all come out empty is left out, words and all. A line with no slot, and every word of a role's
  `instructions`, is never dropped. An empty `peers` or `channels` is an empty value, where `nobody yet` and `none yet` were words of
  ours in it, so the default renders byte for byte as before but for a line that would name no peer or no channel. [RFC 0025](docs/rfcs/0025-what-an-agent-is-told-is-a-template.md) is
  amended.
- **A session that was closing reads `closed` once its owner has stopped, where it read `closing` for good.**
- **An unusable root or socket directory is a configuration error.** A root another user owns or can write, a sessions folder or
  a socket directory not this user's, and no socket directory at all are configuration errors, which the command line exits 78
  for and `doctor` reports, where they were refused `unsupported`.
- **A start cut short is recorded as stopped, not crashed.** A start cut short, cancelled or failed, once its incarnation is in
  the journal, runs the owner's shutdown and appends `session.stopped`, where it ended its harnesses and left the journal as a
  crash would.
- **`Team.starts(role)` names the agents a role starts, where it counted them, so the command line and the runtime name them alike.**
- **`agent.finish` from anyone but an agent is refused `not_permitted` by kind, where its body refused `invalid`.**
- **`Session.submit` of a read answers it as a query, which writes nothing, so a view credential may ask it.**
- **The plan-login refusal names `--plan-login` beside `plan_login=True`, and history names `platoon-harness session resume`.**
- **`ScriptedDriver` names its turns after the instance too, so no resume repeats a turn's name.**
- **A live test's steps reworded after a model misread them.** The owner's flow in `tests/live/test_stays.py` words its steps in
  an order no reading can mistake: on the old words a Codex lead sent the follow-up at once, in run 36, and it landed in the
  helper's first turn.
- **The answer to a follow-up wakes the parent as the first answer did.** The monitor wakes a parent once for the spawn and once
  for each message of its own the first time it lands in its child's turn, in place of once per causal chain, so the answer to a
  follow-up reaches the parent as the first did. Every report answers, one a wait counts too, but one from a turn an interrupt
  or the owner's stop cut. A message from a peer or a human asks nothing, and nor does one read again. A steer that lands in the
  turn after its offer counts there, its hops too.
- **The preamble tells a child that stays how to answer.** What the preamble says of ending follows whether an agent stays, and
  a child that stays is told to answer by ending its turn, which sends its last words to its parent and leaves it there for the
  next message. Told it stayed for the next message, a Codex child held a `wait` for it instead of answering.
- **Agents are no longer told to wait with nothing to wait for.** The preamble teaches `wait` as how to wait for something
  named, where it used to say to call it with nothing to do until something changed, which beside "answer by ending your turn"
  told a child that had answered to park. `stays` is said one way everywhere: an agent told to stay after its task for the next
  message.
- **An agent's instructions are the preamble and then the role's words, so a role has the last word.** A role that told a Codex agent
  never to finish lost to the preamble in run 21.
- **A child idle at its parent's end is retired, not cancelled.** A child that ends with its parent ends `retired` unless a turn
  of its is under way, which its end cuts and which still ends it `cancelled`, as Platoon drops a cancelled child's tokens. A
  parked child is retired, and so is one on its way to a turn, by a goal not begun, a wake that is due, a wait that holds, or a
  handover under way or taken and not landed, as that turn has not begun. `session.cancel` still cancels every agent, each
  parent before its children, so that no report goes to a parent ending with it. See
  [RFC 0062](docs/rfcs/0062-a-child-ends-cancelled-with-its-parent-only-for-a-turn-under-way.md).
- **Refusals over an agent that stays say what to do.** An agent's `wait` for the end of one that stays is refused while it has
  not ended, naming `from`, a refusal over working children names `from` for one that stays, and a `max_children` refusal says
  that ending a child makes room.
- **`agent.retire` is refused for an agent on its way to a turn, as for one in a turn: `agent.cancel` is what stops one.**
- **Checks for agents that stay.** `team_check` warns of a wake cycle that closes through a parent and a child that can stay,
  with no `max_hops`, and refuses a role that stays on a one-shot harness. The `manager-worker` and `tree` presets take
  `max_hops`, 8 unless given, as `mesh` and `star` do, so no shipped preset sets the warning off.
- **Journals from before agents could stay still open.** `agent.spawned`, `context.offered`, `context.delivered` and
  `message.sent` are at payload v2, and the folds that read what v1 lacked fill it with what held when it was written, so a
  journal from before agents could stay still opens.
- **A result's next step is worded for the surface that reads it.** A tool result's `next` is in the words of its surface, with
  no sentence naming a tool its reader does not hold, as a refusal's is.
- **`open_session` takes what each role's driver said, and the runtime asks each driver when it opens a session.**
- **The live crash test's check fixed for a kill before a command runs.** The live crash test holds a log to no more runs of a
  command than the journal saw begin, since a kill can come before a command it set going ran.
- **New `check_driver` rows, and a `gated` argument.** `check_driver` has rows for a denial that holds, an effort honored or
  refused, and `reconcile` after a restart, and its `gated` argument turns a command into a call that asks approval, as `shell`
  turns one into a call that runs it.
- **An unset model is refused only where access was given.** On the harness's own login it means the harness's own default, and `ready`
  says which.
- **A live test runs in `tests/live`, marked `live`, on `PLATOON_HARNESS_LIVE=1`.**
- **The driver contract shrank to what the runtime reads.** `start`, `deliver` and `interrupt` return nothing, on the wire too, so `Started`
  and `Receipt` are gone, and `ready.native` is the one statement of a session's id. `interrupt` in `Capabilities` is a boolean, `Login`
  has no `native`, `DriverInfo` has no `version`, and `Item.phase` is `started` or `completed`: a message or a thought has none, and
  `approval` is what says an item answers one.
- **Turns nobody measured whole are charged an estimate on top, labelled so.** A turn nobody measured whole, a lost one or one
  an interrupt cut short among them, is charged what was measured plus its estimate, labelled `estimated`, and limits hold on
  that, where it was charged its estimate and left every later reservation in its unit refused `unavailable`. On Codex every
  interrupt did that, so one Esc under a `tokens` limit left a session to a person. `Budget` and `budget.set` take `estimate`,
  which a `tokens` or `usd` limit needs, and `team check` and `budget.set` refuse one without it. `fallback = "turns"` is gone,
  as an estimate does its job. Usage in the Ending and the roster counts `unmeasured` turns, as `budget.status` did.
- **A wall limit no longer holds off a stall.** A timer that can only end a session moves nothing, so a wall limit no longer
  holds off a stall: a wake the budget refuses under one ends the session `needs_human` at once. Live run 42 waited out its four
  minute wall and exited 2.
- **`session.stop` cancels each handover that has not started, which queues its entries again and is no failure of its harness's.** The
  owner's stop failed them before, which counted toward the six that lose an agent.
- **A person never reads words written for an agent.** Op descriptions hold for every reader who may run the op, so a person's
  surface shows no sentence written to an agent, such as "Your own open turn is always among `blockers` while you ask".
- **One live tail per agent, ended with its item.** Live text is a tail bound to its item: one per agent of what it is saying
  now, ended by the host at a message or thought item and a turn's end, and by the kernel when its agent's principal is revoked.
  `deltas` joins what came past a reader's frame into one `Delta`, whose new `ended` names the seq through which the journal
  holds what the text before it became, so a client that joins late is shown only text not yet committed, with its true `lag`,
  and a reader of an ended agent is told so once and then nothing more. `Kernel.end_delta(agent, seq)` ends it. A tail holds 256
  KiB, where a ring held 256 frames. bug-clients-2, -4 and -5.
- **A caller's ack comes before a follower looks.** The writer resolves a batch's acks before it wakes followers, so what a
  caller does on its ack comes before a follower on its loop looks.
- **`Session`: boards and queues take their tool's name, `board_post`, `task_claim` and so on, and `agent.release` is plain `release`.**
  `cancel()` stops the session and `cancel_agent(agent)` one agent. `finish`, `join`, `wait_any` and `broadcast` are gone, as `wait` and
  `send` state them. `spawn` says `role`. `put_body` returns a ref, and `get_body` and `tombstone` take one.
- **`Link.submit` takes no `expected_version`.** Ops that need one take it as an argument.
- **`ConfigError` is at the top of the package, and `testing` no longer exports `API_KEY` and `BASE_URL`.**
- **`primitives.Delivery` is now `Injection`, the word of architecture section 7, and `Policy` names the approval policies.**
- **Agent rows a client can walk by name.** `agent.list` and `agent.status` rows name an agent as `agent`, the bare name, as
  `session.ending` and `roster` do, and `parent` and `held_by` the same way, so a client can walk them.
- **`Peer` takes no `limit`, a `Stray` takes the line alone, and `strict_loads` is the one way to refuse a NaN.**
- **`reap` returns what it left alone in words, and `Process` masks stderr and leaves reports to the host.**
- **`agent.records` takes an `agent`.**
- **The view `primitives.Session` is now `SessionRecord`, leaving the name to the facade.**
- **An agent has no goal unless given one: `agent.spawn` takes none, such an agent holds no turn's reservation, and a driver waits for
  a delivery.** `check_driver` has `no_goal_takes_no_turn`, and the `exec` driver refuses a start with no goal.
- **A one-shot agent ends with its turn: `finished` if that turn `stopped`, and `failed` otherwise.** It used to be lost.
- **`Delivery.text` is a field the host renders in the words of an agent's surface, and `Offered` carries `sender` and `body`.**
- **`agent.start` takes `resumed`, which journals `agent.resumed` and leaves the agent as it stood.** `Agent` has `native`.
- **`Manifest` holds `human`, `approvals` and `cwd`, so a folder is all a runtime needs.**
- **`team_check` takes capabilities by a role's own name too, since a command decides them and a driver's name does not.**
- **`session.status` says how many approvals are left to `ask`.** A lost turn raises `uncertain` in `attention`.
- **`Effect.data` is `Any`, as `Event.data` is.** `__version__` lives in `platoon_harness.version`.
- **`agent.list` and `task.renew` are no longer tools.** Agents have `peers`, and the host renews leases. `peers` and `channel.list` return a
  page, `{peers, total, cursor}` and `{channels, total, cursor}`, and take `after`.
- **`check_driver` has `preamble_once_per_request`, `tool_item_carries_its_anchor` and `stop_ends_a_running_tool`, for which it takes
  `shell`, and `operational` needs that last one.** `measures_reported` holds `tokens` to what the model said, `call_ids_reported` holds an
  item and a call's usage to the id, and `interrupt` holds a turn's reason to `interrupted`.
- **`ScriptedDriver` sends `spec.instructions` as a system message, and says which call made an item.**
- **`runtime.start` takes `drift`, and `Kernel.recover` takes it as arguments.** `Manifest.drift()` says what differs from a manifest.
- **`tool_name` lives in the kernel, which claims tool names at load.** `tools` adds `held_tools`.
- **`Item.phase` is one of `started`, `completed`, `final` and `decided`, and anything else is an unknown frame.** `Item` and `Usage` have
  `call_id`, which goes on the envelope, `ModelCall` has `purpose`, `Compacted` has `summary`, and `InputDelivered` has `native_id`. An
  id, a reason and a purpose hold 256 characters, `Item.native_id` among them.
- **`Compacted.forgotten` holds native ids, and the host stores it and `summary` as bodies.** With `None` the runtime records
  `compaction_opaque`, so a driver no longer reports that gap itself.
- **A `roster` row has `parent`, `stopped`, why the last turn did not stop on its own until the next begins, and `held_by`.**
- **`session.status` says `stalled`, and `Session.settle_effect` says whether an uncertain effect happened.**
- **`agent.retell` also tells a resumed harness its last turn was cut off, from `stopped`, and with nothing to tell it says nothing.**
- **`OWNER_STOP` is the reason a turn ended by a shutdown gives.** A host reports a turn interrupted while it closes under that reason.
  `CUT_OFF` holds the reasons only the runtime gives, and a driver that says one has sent an unknown frame.
- **An agent that has finished can spawn nothing.**
- **`agent.spawn` adds the principal, and a host issues its credential with `principal.issue`.**
- **`lease_lost` and `blob.put` are gone, and `task.claim` at `max_inflight` refuses `conflict`.**
- **`message.send` takes no `cause`: a program carries a chain with `reply_to`.**
- **`load_team(trust_commands=)` is now `trust_project=`, and covers `module:attr` references and auth profiles.**
- **`Kernel.submit` takes `native`, stamped on a command's events, and `Kernel.get_body` takes `limit`.**
- **`blob.get` takes one `ref`, which can name lines.** A cut body says `rest`, and `text` is null where an op could not read a body.
- **`agent.status` names the open `turn`.**
- **`ready` holds only what a driver knows.** A harness commits through the new runtime op `agent.start`, with what was declared and
  verified and the levels, so a report cannot claim one. `agent.report` refuses `ready` and `delta`.
- **`agent.report` takes `input.delivered`, `approval.requested`, `model.call`, `child.seen` and `native`, and `usage` has a `scope`.**
- **A report's `body` is text until the host stores it, as ingress does for a tool's body argument.**
- **`Capabilities` holds every field of architecture section 9.2, and absence means unsupported.**

### Fixes

- **A link opened over the page draws nothing first.** The page loaded again for a new link opened in its tab, but first
  drew the address it was leaving, whose read the reload cut off, which Firefox reports as an uncaught error.
- **A stopped session's folder holds no credential.** A runtime left its `owner.token` and `view.token` in the folder when it
  stopped, dead, as the next runtime issues new ones, but still bearer-shaped in a folder that is the session's export and
  gets copied. A stop or a close now removes them, and a killed runtime's, which stay dead, at the next stop, as RFC 0055's
  export holding no key needs.
- **The compatibility page claimed pins and states nothing held.** It called the `exec` driver planned, where STATUS tests it,
  and the `claude`, `codex`, `pi` and `openhands` drivers implemented, where STATUS calls them experimental. It pinned
  `agent-client-protocol` in an `[acp]` extra with 1.0.0rc3 locked and CI on both, where no such extra, lock entry or CI job
  exists, and Platoon at `>=0.5,<0.6`, which nothing here depends on since the bridge became Platoon's own extension. Its rows
  now say what STATUS and the lock hold, and `tests/unit/docs/test_compatibility.py` holds each driver's state to STATUS and
  each pin the page spells to `uv.lock`.
- **A mark still being written as you leave the terminal UI is kept.** The workspace wrote each mark in a worker of its
  screen, and leaving takes the screen down, which cancels its workers, so a channel read just before leaving could come back
  unread, as a test found with marks written slowly. Leaving now writes each mark still being written before it goes.
- **Estimators writing at once to a session with no annotations yet each write.** Every write switched `annotations.sqlite` to
  WAL, and SQLite refuses at once, rather than after its five-second wait, one of two writers that switch a new file to WAL
  together, so one of several first statements could be refused `unavailable: database is locked`, as one of sixteen was in a
  run of the fast suite. Its first writer now makes the file aside, in WAL mode, and links it into place.
- **A caller that hears its commit failed finds the kernel closed.** The writer answered a failed batch's callers first and
  closed the kernel after, so a caller that had heard of the failure could still find `Kernel.closed` false, as the writer's
  own test did in two of three runs of the fast suite on two loaded cores. The kernel now closes before the callers hear.
- **A scripted turn whose step raises ends failed, saying why.** `ScriptedDriver` ended a turn failed on a `DriverError` alone,
  so a step or a subclass that raised anything else, such as a script reading a refused tool result as JSON, left its turn open
  with no error, and its session never settled. Such a turn now ends `failed:` with the type and words of what was raised, as a
  harness's own error ends its turn, and the next turn runs.
- **A Codex turn holds a native child open from the spawn that names it.** The `codex` driver learned of a native child only
  from the child's `turn/started`, and Codex can send that after its parent's `turn/completed`, as it did in about one run in
  six with Codex short of CPU, so the turn ended with the parent, and the child's turn was reported as one of its own, which the
  runtime never began, with the child's spending in it. A child now counts from the first frame that names it, in either generation of
  Codex's own agents: the spawn item that says it is yet to start, or its own `turn/started`. It holds the turn open until its
  turn ends, an interrupt cuts its turn as it starts, and a child's own spawn counts as well. One that never started a turn would
  hold it open past an interrupt, until a stop, though none has been seen: a child interrupted as it was spawned still ran one.
- **A prompt on stdin that is not UTF-8 exits 64 whatever the locale.** `run` read a prompt on stdin through Python's text
  reader, which under a C or C.UTF-8 locale, as on GitHub's runners, lets bytes that are not UTF-8 through as surrogates, so
  such a prompt started a session whose first message was refused and the run ended 0, where it exits 64 saying why. It now
  reads stdin's bytes and decodes them as UTF-8 whatever the locale.
- **A scrollbar that appears is drawn where the lines are.** Textual moves a scrollbar only as the lines move, so a transcript
  that reached its end before its scrollbar appeared drew the thumb at the top, as the slim and short layouts' snapshots had
  recorded it, and a list whose row was chosen as it was drawn, as the navigator's is when the focus changes, did the same. The
  transcript and every list now put a scrollbar that appears where they are. The slim layout's snapshot test failed under load
  whenever the scrollbar happened to appear first, which drew it right.
- **Each command group's help says what it is for.** The help of `agent`, `task` and the 13 other groups of commands that run
  ops on a session was one sentence they all shared, "The `task` ops, each on one session, ...", which said nothing of any; each
  now says what it holds and what you can do with it. `peers --help` said "in `platoon-harness peers`" where the op's words
  meant the field of its result, which an agent read as `ph peers` or its harness's name for the tool, as every surface turns an
  op's own name into its tool's: the op no longer names that field. `run --help` says plainly that it exits 64 before any cost
  when it cannot run as given.
- **A finish's citations carried no credit.** A finished agent's `said` named its end even where that end's report carried the
  agent's own `agent.finished` or its last message, so an episode closed on it walked from an event that cites nothing and that
  no model call chose, and a finish's citations carried no credit. `said` is now the ref the end's report carries, which
  `agent.ended`, payload 2, records as `carries`: for an `agent.finish` with a gist or a body, its `agent.finished` in a turn
  and the end itself out of one, and else the latest turn's last message, whose words the report took, or the end where that
  turn said nothing. An end written before payload 2 says itself, as it did. A finish with a body and no gist has words of its
  own, in a turn or out of one, and an empty finish has none, even after a message with a body, so its report carries that
  message: one act is decided one way. [RFC 0061](docs/rfcs/0061-credit-is-kept-per-span-and-a-span-rests-on-what-it-took.md)
  amends RFC 0060 so.
- **A child that reported and never finished kept its parent parked.** A tree of agents that do not stay could sit until a
  person ended it, as one did for 19 minutes on the first GPU run of a team on OpenHands: a child reported and never called
  `agent.finish`, so it stayed live and idle, and its parent, woken by the report, ended its turn and parked again on a wait on
  that child's end, which nothing would bring. An agent that does not stay now finishes with a turn that stops on its own with
  nothing more to come for it, no person holding it, no wait of its own, no entry that would wake it, no handover to it under
  way or taken and not landed and no one who would end with it at work or with more to come, a child parked on a wait among
  them, as `agent.finish` with no report would have it: its last words are its report, its parent hears of it as of any finish,
  a wait on its end holds, and a root that does not stay reaches `until`. A child's end wakes a parent that does not stay and
  has no wait open, whatever that parent asked, so one kept by a grandchild is not left idle. A turn an interrupt, the owner's
  stop or a failure cut ends no agent, nor does one an interrupt was asked in though its harness stopped first, and one that
  stays is as it was. One that does not stay is told that a turn that ends with nothing left to wait for ends it, with what it
  said last as its report, where it was told such a turn left it idle. See
  [RFC 0060](docs/rfcs/0060-an-agent-that-does-not-stay-finishes-with-a-turn-that-leaves-nothing-to-come.md).
- **OpenHands refused an environment tool named `finish`.** Every OpenHands agent of a sealed launch on an environment with a
  tool named `finish`, as TextCraft's is, was refused at launch, "Duplicate tool names found: {'finish'}": OpenHands keeps its
  own `finish` and `think`, and showed the environment's tools bare. One rule now holds for every harness: an environment's
  tools reach the model named by their server, never bare, so none can collide with a harness's own. OpenHands shows them as
  `environment_<tool>`, as its SDK's client of two servers names a server's tools, and calls the server by the names it lists;
  pi already showed them as `mcp__environment__<tool>`, and ScriptedDriver now does too, its `Call` step naming a tool as the
  model is shown it. `environment_tools_in_first_request` now asks for each of the environment's tools named by its server, with
  the server's name and a separator before it, and FakeModel's environment serves `finish` and `think` beside `ping`, all three
  as `testing.ENVIRONMENT_TOOLS`, so a harness that shows them bare fails it. A result kept before was earned on the weaker
  check: `doctor --check` again.
- **A session root given relatively, as `Session.attach(name, root="home")`, failed every read of its annotations, "relative path can't
  be expressed as a file URI".** `find_root` makes a root absolute where it finds it, against the folder it was given in.
- **The authority hears how an agent ended, whatever failed first.** A stop whose driver's `stop` raised or ran past its time
  never told the authority how its agent ended: `finish` now comes last whatever failed before it
  ([RFC 0059](docs/rfcs/0059-a-parent-hears-of-a-child-s-end-once-its-authority-has.md)).
- **A caller could be refused `busy` over its own recorded commands.** A caller that sent again as soon as it heard its commands
  were recorded could be refused `busy` over those very commands: the journal's writer took a batch out of flight only after
  answering it, and now does so first.
- **The terminal's `/review` says of an isolated workspace's group, as of any snapshot's, that its commits are in its own repository.**
- **Access by key on Codex 0.167.0.** Codex 0.167.0 refused every turn of an agent given access, "This chat uses
  platoon-harness, but your current provider is openai", as it holds a thread to the provider its app-server started on, and the
  driver had named a provider for the thread alone. The app-server now starts on a provider of the agent's own that `-c` names,
  and the thread gives it its URL, which no argv holds, so the driver runs on 0.164.0 and 0.167.0 alike.
- **A shutdown racing an agent's own stop.** Two stops of one agent at once, as a shutdown's and the agent's own, could both
  read its process record, and the second to remove it failed, so its stop effect failed and its authority was never told how it
  ended. A record the other stop removed is gone.
- **A look lost a commit to another agent's stop.** Another agent's stop could end its workspace while a look read that
  workspace's reflog to say whose a commit was, and the look then failed whole and recorded a gap, losing the commit and its
  citations. A workspace gone while a look reads it is as gone as one removed before, and one still on disk that git cannot read
  still fails the look, since it might have made the commit.
- **A commit that failed went on for ever: each batch answered `unavailable` and the runtime kept running, recording nothing.** Now one
  failed commit ends the runtime as a kill would. The kernel takes nothing more and closes, `Kernel.failure` holds a `JournalError`
  naming the journal, `Runtime.run` and an owner's `Session` raise it, the owner's shutdown ends the process trees and records
  nothing, and `run`, `serve` and `session resume` exit 74. A resume finds the turns that were open and tells them they were cut
  off, and a retry under its key answers from the journal if the batch landed.
- **A retried act from the page ran twice.** From SwarmChat's page, an act whose answer was lost went again under a new key
  after a new link, since `web` put the key under the link's session token, and so ran twice; and one `web` took whose page then
  heard its session had ended was shown as refused. The key is the page's own, 32 lowercase hex under `web/`, whichever link
  sends it; an act a page's ended session left unanswered says so, stays kept, and goes again from a new link opened over the
  page, which loads it again for the gate. A failure of `web`'s is an answer saying whether the act took effect is unknown, and
  only a request that reached nothing, or a 503, is sent again. A body holding half of a character, nested past reading, or a
  search the page could not have made, is refused 400, where some failed 500 and a long draft holding half a character was sent
  again for ever.
- **`web`'s bare address answered 404, where SwarmChat's own server sends a browser on to its page; ours now does too.** And
  `web` on loopback now says how to reach it from another machine: forward the port under the same number, since the
  page's requests must name it.
- **An act that may have been done was shown as refused.** An act left unanswered went again from a view link opened over the
  page, which refused it, so the page called refused an act that may have been done. A view link now sends none of it and says
  it waits for a control link opened in that tab.
- **Two documents claimed a refusal no code made.** [RFC 0016](docs/rfcs/0016-plan-logins-and-credentials.md) and the
  compatibility map said `web --remote` refuses a second person on a plan-login session, which no code did and no such flag
  exists; [RFC 0027](docs/rfcs/0027-the-browser-on-our-backend.md) amends it, as the architecture already said, and refusing
  another address to such a session is planned. The guide now says that while `web` runs a run's approval waits for you instead
  of ending `needs_human`, and the architecture names `web` among the entry points with signal handlers and among what writes
  beside the journal when it reads. `web` on a page file that is not the one pinned exits 78, which nothing tested before.
- **The page misreported a spawn's goal and who made an agent's chat.** The page said a spawn's goal was "Delivered to 0 of 0
  agents it was for", and that the spawner made each agent's chat with the person, which nobody in it did. A goal reached its
  agent when the agent's first turn began on it, and the runtime makes that chat. The projection is version 3, which `web` folds
  again from the journal when it starts.
- **Every body showed as `body.txt`.** A file sent as a message's body lost its name whenever words went with it, in the
  terminal and on the page, since a body keeps none, so the page showed every body as `body.txt`. The function both clients make
  a gist with names the file after the words, `TEXT (file NAME)`, and refuses the two past 280 characters; the page sends the
  file's name beside the op's args. Where no words went, the gist `file NAME` that ran past 280 was refused as a long text
  beside a file.
- **Who was working took a page per agent to see.** On SwarmChat's page, the people list showed `agent` beside every agent,
  where SwarmChat draws someone's first field, so who was working or held up needed a page per agent; it shows each agent's
  status there. Seeing as a person or the runtime was offered, and choosing one left the page half in a mode it had refused; the
  picker draws them disabled, saying why, and an address naming one shows everyone. An approval's card floated beside its
  message, crushing it on a narrow window; it sits under the question. A `via` holding a dollar and a backtick or a quote put
  the message's own markup into its card, as a string's replace read them; no replacement the page makes reads them now. Tool
  activity, reviewing changes and provenance had no control, where every unbuilt act is drawn disabled saying why; each has one.
  A person's own page makes links of either kind, which only `/x/link` did.
- **One projection folded by two writers.** Two `web` processes on one session folded one projection, each from its own cursor,
  and the first to meet a line the other had written crashed with a traceback, dropping every browser it served. One `web`
  serves a session at a time, holding `swarmchat.lock` beside the projection, and a second exits 64, saying where the first
  serves. The fold passes over an event it has folded already.
- **A refused exchange burned its link.** `web` spent a link before it believed the request to exchange it, so an exchange
  refused for its shape or cut off burned the link and gave nobody its token. A link is spent only by the answer that carries
  its token.
- **A large file could not cross a slow link.** A request to the tool server or to `web` had 10 s to arrive whole, head and
  body, and its answer 10 s to leave, so a file near the 12 MB a body may be could not cross a link slower than about 10 Mbit/s,
  and the page said only that it did not reach `web`. A head still has 10 s, and each part of a body or an answer has 10 s from
  the part before. `platoon_harness.http.length` is gone: `Server.body` reads a body on that rule.
- **Another program could take the page's port on one address.** `web --host localhost` bound `127.0.0.1` and `::1` on two ports
  and said one, leaving that port free on the other address for any program on the machine to take, and be what a browser
  reached. `platoon_harness.http` binds every address a name has on one port, trying again when a busy host has taken it on one
  of them. `web` on the scheme's own port, 80 or 443, refused every request, as a browser leaves that port out of `Host` and
  `Origin`; it leaves it out of what it serves too.
- **A message's words could hide inside its file.** The browser's projection showed a message's body in place of its words
  whenever the body held them anywhere, so a file whose text held the message's words hid them. A body takes their place only
  when it begins or ends with the gist, as a cut gist does. An agent's end line said only that it ended, so a lead's answer
  given as its finish report was not in the page; it says what the terminal's says, the report among it. The projection is
  version 2, which `web` folds again from the journal when it starts.
- **The terminal UI, from its review:**
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
- **Stops and resumes during a wake could lose the agent.** A handover under way when the owner stopped counted, once the next
  runtime failed it, as a failure of its harness's, so six stops and resumes during a wake lost the agent.
- **Partial measurements charged as whole.** A turn measured only as a lower bound was charged as if measured whole, and a
  Claude Code result with no tree usage left its turn labelled `provider`. Both are charged their estimate on top now.
- **`budget.status` said a wall limit had nothing spent against it.** It says the time since the limit was set.
- **Per-role estimates went unused.** A role's estimate with no limit of its own never reached the session, so its turns were
  reserved the shared estimate, and a role's limit was refused although the shared estimate covered it.
- **Live text broke law 8.** Each reader of live text read the journal on every commit to look for its agent's end, a private
  read per follower that law 8 rules out. It looks in the tail every follower shares.
- **A mark moved backward or by a view credential.** A mark could move backward, when a second terminal of the same person
  marked less than the first had, and a view credential could move one.
- **Two ways an interrupt failed to stop an agent.** Esc did not stop an agent with something queued, as what an interrupted
  harness took was queued again and woke it, and an interrupt was refused between a wake and its turn: bug-coordination-7 and
  -8.
- **A handover an interrupt cut counted as one that failed, so each later message waited twice as long, and six interrupts lost the
  agent.** That wait had hidden a race: a harness can begin a turn on the handover the interrupt failed, and a message sent at once
  landed in that turn as the interrupt cut it, on pi against FakeModel. Nothing is handed over while an interrupt is under way.
- **A command could run twice across a crash.** A command whose runtime went for good after it committed, before its ack, was
  refused on its retry, and running it again after a resume ran it twice. History answers a key its journal holds.
- **A call whose send failed as its connection went left asyncio to say on stderr that nobody read its answer.**
- **A resumed `ScriptedDriver` answered a new call as a repeat.** A resumed `ScriptedDriver` named its first turn as the first
  instance had, so a call identical to one of that turn, with no id of its own, was answered from the journal as a repeat and
  nothing ran.
- **A test that failed part way could leave a detached runtime running.** A fixture every test has ends each one its `tmp_path` holds,
  by its pid and its group.
- **The scan for local paths and account details skipped `docs/research`, its fixtures, the top-level pages and the package
  READMEs.** It reads them now, and an email address too, and a path inside a repository no longer reads as a local one.
- **A stale notice woke an agent that had read its report.** A wait that closed with no notice of its own posted "A report came
  in during your wait." as a wake, which stayed queued after its reader had read the report itself, as the lead of run 22 did
  with `sender`. Each report the wait named or counted now wakes its reader itself, within `max_hops`, as `wake.restored`
  records, so a report read first wakes nobody. Section 7 also says what held all along: a report from a turn stopped on purpose
  wakes nobody by the monitor, and a wait counts it as it counts anything it names.
- **A process that had exited counted as alive in a stop.** A stop under heavy load could fail with a group that "outlived
  SIGKILL", or `reap` name a group that outlived its leader, when nothing in it ran: a member that has exited counts for
  `killpg(group, 0)` until its parent reaps it, and an orphan waits on pid 1. A group is judged by whether anything in it still
  runs, on Linux, and a process whose main thread has exited while another runs still does, so a stop of one that ignores
  `SIGTERM` comes to `SIGKILL` and says so.
- **A resume journaled instructions no model heard.** A resume rendered what an agent was told afresh and journaled that, while
  Claude Code and Codex kept what their session began with, so the record held words no model heard. A harness that reopens its
  own session is handed, and journaled, what it was told when that began.
- **`wait.cancel` let a report from a turn an interrupt or the owner's stop cut wake its reader, which such a report never does.** Only a
  report that answers is restored.
- **A template's own words on a line whose slots came out empty were left out with the line, and nothing said so.** `preamble = ""` was
  checked as written and run as the default, a template on a harness that reaches none of our tools went untold without a word, and
  `team_check` warned of a tool held through a grant to a named agent as one the role lacked.
- **Three faults of `told(team)`.** `told(team)` refused a team whose limits or budget stopped one agent of each role, said a
  driver that could not describe itself with no role named, and showed a child whose spawner starts with nothing as a session's
  own agent.
- **The scan for local paths reads the CLI's sources too, a home folder whose name begins with a capital, and this cluster's name.**
- **Later spawns and resumes escaped the plan-login refusal.** The plan-login refusal was checked only at the start, so a human
  spawning more agents later, and a resume after a harness was signed in on a plan, escaped it. The manifest keeps `plan_login`,
  and without it a launch beside a live agent on a plan login fails, and a resume that would bring back several is refused, each
  naming the fix in the same words, `PLAN_LOGIN_FIX`.
- **A budget that an unmeasured turn left unable to hold said so and no more.** Its `unavailable` refusal names the two ways on, a
  `fallback = "turns"` with a `turns` limit or no limit in that unit, and says no higher limit helps.
- **A Codex interrupt that came while a `turn/start` was on its way, which the harness then refused, stayed set and cut the next turn.**
  A refused handover with no other turn on its way clears it.
- **A spawn by written grant escaped the plan-login refusal.** A role a written grant lets another spawn was not counted as
  spawnable, so a plan login with one such role was not refused, and the role started an agent of its own. `Team.spawners` reads
  written grants of `agent.spawn` as `team_check` does, as the same thing as `may_spawn`.
- **A turn with one call unmeasured was charged its estimate alone, so a million measured tokens counted as none.** What was measured now
  stands as a floor. A Codex turn cut short reports a call `unavailable`, as Claude Code's and pi's do, rather than reading as whole.
- **An agent whose harness took no turn was lost at any resume, as Claude Code, Codex and pi write no session until a turn.** The runtime
  starts it anew, and tells it what it must know as before. `agent.records` says whether an agent's harness `began`.
- **A tool's background child outlived its agent's stop.** `stop` left a tool's background child running on Claude Code and pi,
  `npm run dev &` among them, with no word in the journal, and `check_driver` passed. On Linux, `Process` now ends what carries
  the harness's own `TMPDIR`, whichever group it left for, at a stop and after a crash, and `stop_ends_a_running_tool` puts a
  child in the background and one in a session of its own.
- **A frame of a known type with a shape nobody expected stopped a Claude Code agent.** It is a `native` frame and a gap, as on the other
  two, a request the harness waits on is still answered, and a turn's end still ends the turn. A call whose count is nothing, or a null
  part, is no measurement.
- **Interrupts at a turn's start, alike on every harness.** An interrupt as a handover begins a turn reads `interrupted` on
  every harness: Claude Code read it as a failure, which woke a parent, and Codex sent nothing and ran the turn on. A refused
  interrupt labels no turn, a failed turn says its failure, and a turn the harness cut with nobody asking reads `aborted` on
  Codex and pi.
- **A Claude Code goal that starts with `/` is refused, as it ran as a slash command.**
- **pi's `reconcile` claims nothing it cannot know.** pi's `reconcile` no longer says `not_landed` of an id it cannot know, an
  approval's among them, and a compaction whose listing does not read is still reported. Codex's `answer` to a harness that has
  died is a `DriverError`.
- **A late answer to a JSON-RPC call its caller gave up on is no unknown frame.**
- **A role runs in the user's own setup.** Claude Code no longer has auto memory turned off, and pi no longer has its network, telemetry and
  version check turned off: those were a sealed launch's settings, left behind.
- **A role's `deny` holds on Claude Code.** A user's `defaultMode` can no longer answer before the runtime hears, so a role's
  `deny` holds on Claude Code, and `AskUserQuestion`, which a verdict cannot answer, is no longer offered.
- **Claude Code's tool token is in no file: `--mcp-config` names its variable, as Codex's and pi's launches do.**
- **Our tools failing to connect fails a Claude Code agent's start, where the agent used to run on with no way to coordinate.**
- **Codex declares its 300 s cap on one tool call, so a `hold` past it is refused up front.**
- **A steer no longer goes missing across a crash.** What a harness took and never landed is queued again when its turn stops
  short, and when it comes back from a crash, by one fold, so a steer no longer goes missing across a crash, and no driver sends
  anything again, or fails to in silence. Claude Code drops its queue at an interrupt, as it would otherwise begin a turn on it
  by itself.
- **Codex approval ids collided across agents.** A Codex approval id was a count per process, so a second agent's first request
  collided in the journal and was answered `deny` with nobody asked. It is unique now.
- **A harness that exits in a turn leaves the gap `crash_window`, since a tool of its own can run on.** It used to leave none.
- **A real child's `system/task_progress` frame no longer costs Claude Code a gap.**
- **A secret split across two deltas reached followers unmasked, on every driver but `exec`.** Live text is masked as one stream.
- **An `interrupt` or an `answer` that a harness never took held its effect open for ever.** Each fails after a minute, as a handover
  already did.
- **A role with an auth profile was recorded under the login its harness had, though it never used it.**
- **`Kernel.changed` no longer wakes on a batch with no events, as it never promised to.**
- **`Peer.run` treats a reset connection as the end of the stream.**
- **`agent.finish` in an open turn ends the agent with that turn, so what a harness reports at turn end counts.** It used to be refused,
  which lost the usage and last message and could stall a budgeted team.
- **`usage` has no amount for a unit nobody measured.** It used to say 0.0. `turns` and `agents` are labelled `counted`, not `provider`.
- **Handovers that a stop or a crash cut short.** A crash or a stop between a handover and its turn no longer strands an agent
  in `waking`, a goal no turn began is told again on resume, and a launch cut short by a stop is no longer recorded as finished.
- **A handover that keeps failing backs off and, after six, loses the agent with the reason.** It used to loop and grow the journal.
- **`agent.interrupt` takes an agent whose handover hangs, and that handover fails.** It used to be refused.
- **Recovery gives each agent its own failure.** One broken driver, or one `reconcile` that hangs, used to stop every other.
- **`Runtime.stop` always lets go, and a journal that will not commit holds it up for at most `grace`.**
- **A wire program's own harness ends with its agent, and a stop already running no longer leaves a harness alive.**
- **A report the journal refuses ends its harness with a gap, and so does one whose body will not store, which left none.** A `ready`, an
  item or an exit used to be dropped, which could hang an agent.
- **`ready` naming a model other than the one pinned fails the spawn.**
- **Every report is masked on the way to the journal, whichever driver said it, and text is masked before it is cut.**
- **`session.close` takes `if_done`, and `settled()` uses it, so a message that gets in first keeps a session open.** `message.send` is
  refused once a session is closing, because it would reach nobody.
- **An approval goes moot with the turn that asked.** One pending at a crash used to end in `needs_human` for nothing.
- **`reap` trusts no file a harness left.** `reap` reads only the driver's record and a wire program's, so a file a harness left
  under its folder can neither stop a resume nor name a stranger.
- **A failed `describe` says what the program said on stderr, and a malformed one is a `DriverError` that names it.**
- **`tool_visibility` matches a whole name, or its `__<name>` ending, and with no tools to look for says `unverified`.**
- **Three fixes to `wait`, `deltas` and attaching.** `wait(on=...)` works for a guest, a mistyped agent is refused by `wait` and
  `deltas` instead of hanging, and attaching says a refusal such as a protocol mismatch at once instead of blaming the runtime
  after a minute.
- **Awaiting a session that was left starts nothing, and one never entered says how to start it.**
- **`leave` takes a duration and stops nothing halfway if it cannot read one.**
- **No client can hold up a stop.** The control socket aborts every connection at a stop, so a client that stopped reading
  cannot hold one up, and a connection accepted during a stop is dropped. A socket belongs to a folder, so a copied session
  cannot take a live one's.
- **No client can grow the live text rings by naming agents that do not exist, and a `Link` raises only `Refused` and `Closed`.**
- **A guest on history survives a writer touching the journal.**
- **Four fixes to roots, session folders and detached runtimes.** A root another user owns or can write is refused, a session
  folder is built aside so a crash burns no name, an unusable `XDG_RUNTIME_DIR` falls through, and a detached runtime runs from
  its folder with `-P`.
- **`team_check` refuses a one-shot role that starts with the session, and says nothing of a `count` of zero, which was said on purpose.**
- **A held wait closes as told only once its answer has left, so an answer that is lost costs no wake.**
- **Bounds on query answers and on what a refusal names.** A query's answer past 32 KiB is refused with its size, and a refusal
  names no tool its token does not hold, in its reason either.
- **`ph <tool> --help` for an unknown tool shows what there is.**
- **An effect left `uncertain` can be settled by a person with `effect.settle`, as [RFC 0005](docs/rfcs/0005-daemons-and-effects.md) promised.** Nothing could settle one under
  `surface`. Saying it did not happen lowers its row in `attention`, as saying it did does.
- **The host retries under one key, since a failed commit may have landed.** It used to retry with none, and could run a command twice.
- **An agent hears on resume that its turn was cut off.** A turn a crash or the owner's stop cut off is told to its agent on
  resume, at-least-once, with a wake, and the words keep the two apart. A lost turn used to leave its agent idle on its leases
  with nobody told, so a session read `settled` with its work undone.
- **Three hangs of `settled()`.** `settled()` with no timeout can no longer hang on a session settled short of `until`, on a
  guest that leaves having done nothing, or on a goal the budget will not wake. It says `needs_human`, and so does
  `session.ending`. A wake the budget refused keeps a session from closing as `settled`, and so does a wait on someone still
  here, so a deadlock with no root no longer ends exit 0.
- **A goal told again after a crash takes the turn its spawn reserved.** It used to be refused by that reservation. A session that stops
  accepting before it can be told ends its agent, and used to hang as `closing`.
- **A task long settled no longer holds off a stall until its lease's timer fires.**
- **A waiter's own `agent.cancel` or `task.complete` counts for its wait.** A join after a cancel used to hang.
- **A report the parent is counting no longer wakes it, so a join of N costs one turn and not N.** The same goes for a join on tasks, while
  someone else below the parent is at work: the last worker's report wakes it, or it would sleep on what nobody is left to do.
- **A turn that did not stop on its own says so to the parent, as `<name> turn <reason>: <text>`, and an `interrupted` one wakes nobody.**
  It used to read as a final answer and wake the parent. A failed turn or a bad end breaks in on a parent with a wait open, even once
  its chain's wake is spent.
- **A report a wait held back reaches a turn when that wait closes with no notice, by `wait.cancel` or a held call's answer.**
- **A wait on other events of a child's stream no longer counts its end.**
- **A parent that ended its own child is not woken to hear of it.**
- **No end over working children.** `agent.finish` and `agent.retire` are refused over working children, a wake that is due and
  a wait that holds among them, naming them and what to do next. They used to cancel a child mid-turn in silence, or with a
  message unread. `team_check` warns of a one-shot role over children that would end with its turn.
- **A stop that comes to `SIGKILL` reports `crash_window`.** `stop_leaves_no_process` could not see a tool, and a tool that leads its own
  group outlives a kill of its harness.
- **A resume under other SDK or extension versions leaves a record on `runtime.started`.** It left none.
- **A session from before `v_agents` changed resumes: `Agents` and `Attention` are at version 2, and a test pins each view's schema to its
  version.** Such a session used to die in recovery on a `TypeError`, and agents nobody can read now stop a resume with the refusal.
- **`peers` and `channel.list` go a page at a time.** A model on a long team can still find its peers: `peers` and
  `channel.list` go a page at a time, where one past 32 KiB was refused with nothing left to try.
- **Agents are never pointed to tools they lack.** A description or a handover no longer names a tool its reader does not hold,
  and a refused query leaves its line out of the preamble. It used to read `nobody yet`. Each pointer to a tool has a sentence
  of its own, so a reader who does not hold that tool keeps the fact beside it. An argument's whole description could go with
  it.
- **Two extensions that claim one tool name are refused at load, as op names are.** They used to pass load and raise at start.
- **`check_extension` sees an op named with an underscore or a digit, and a plain `import` of a kernel module.**
- **A long `forgotten` no longer loses its agent: the list passed what an event holds, and the report was refused.**
- **`view.watch("roster")` no longer misses a row.** It keyed on `event.agent`, so a row that moved on an event naming someone else or
  nobody, a message, a wait's progress or a budget, stayed stale. A roster now changes as a whole.
- **Ctrl+C while `run` prepared could leave a session folder behind after `run` said no session was made.** A start cancelled while it
  prepares takes its folder back.

### Removed

- **`runtime.workspaces.NOT_YET`, as `isolated` is given where an extension gives an isolation.** See [RFC 0034](docs/rfcs/0034-isolation-is-an-extension-s-and-the-runtime-s-git-runs-inside-it.md).
- **`Session.start(human=)`, `prepare(human=)` and `Manifest.human`, which `principal` replaces.** See [RFC 0050](docs/rfcs/0050-a-script-is-a-person-or-a-program.md).
- **`Authority.budget_owner`, which no authority used: every limit a team states is the session's own.** `open_session` takes no
  authority. See [RFC 0049](docs/rfcs/0049-the-contract-a-training-authority-gets.md).
- **A topic's `digest` and its type, `platoon_harness.topology.Digest`, which nothing enforced: a lagging reader's digest is the
  fixed 32 entries it always was.** A team that sets it is refused, as any unknown key is. See [RFC 0048](docs/rfcs/0048-a-setting-nothing-carries-out-is-refused.md).
- **A topic's `entry`, `requires` and `validator`, which nothing enforced.** A team that sets one is refused. See [RFC 0048](docs/rfcs/0048-a-setting-nothing-carries-out-is-refused.md).
- **A board's `keys`, which nothing enforced.** A team that sets it is refused. See [RFC 0048](docs/rfcs/0048-a-setting-nothing-carries-out-is-refused.md).
- **The `git-swarm` preset's `contributions` topic, which held only those settings: the repository is the contribution log, and
  `Informed-By` the declaration.** A session whose resolved team holds it can no longer be resumed, and its journal still reads. See
  [RFC 0048](docs/rfcs/0048-a-setting-nothing-carries-out-is-refused.md).
- **`delivery.confirm`, which only tests used: a driver's `input.delivered`, through `agent.report`, is the one way to confirm a
  handover.**
