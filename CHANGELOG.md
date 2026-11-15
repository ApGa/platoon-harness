# Changelog

What each release of platoon-harness changes. 0.1.0 is the first, for Linux: `uv tool install "platoon-harness[cli]"`
installs the command line, and `pip install platoon-harness` the library. Below 1.0, a minor release may change the
Python API, the team file or the command line, and a patch release only fixes bugs; require a range such as
`platoon-harness>=0.1,<0.2`. The Python API is each name `tests/public_api.txt` lists, and each attribute and method
without a leading underscore that a class it lists defines; nothing else is, and a name the
[Python API reference](docs/reference/python.md) marks experimental is part of it too.

## 0.2.0 (unreleased)

- **A result made from a read-only installation speaks for it wherever it is mounted.** Where every path a harness reads
  to run lies on a read-only mount, its conformance result names those paths, and speaks for an agent whose harness runs
  from them, read-only, on any host, as in a training system's sandbox; a level earned from one made on another host
  says where it was made, and so does `doctor`
  ([Training on sessions](docs/extending/training.md#start-each-rollouts-session)).
- **A gateway can say its session runs in the environment,** `Gateway.in_environment`, where a driver that declares
  `Capabilities.in_environment` keeps the harness's own tools, and name the `PATH` the environment gives its own
  commands, `Gateway.environment_path`, for the model's commands there, which a gateway outside the environment is
  refused. A session holds to the first gateway's word, a gateway that says so goes to no other driver, and each start
  records it ([Training on sessions](docs/extending/training.md#what-a-sealed-launch-is)).
- **A launch in the environment is earned, never declared.** A conformance check,
  `own_tools_in_first_request_in_the_environment`, proves it shows the harness's own shell beside ours and the
  environment's, and `trainable` stands on it there; a driver whose launch in the environment fails it is trainable at
  no launch ([Drivers](docs/extending/drivers.md#a-sealed-launch)).
- **ScriptedDriver keeps its `shell` in the environment.** It declares `Capabilities.in_environment`, and on a gateway
  that says its session runs in the environment it shows the model its `shell`, asks before each call, runs it on the
  `PATH` that `command_path` gives, the gateway's `environment_path` behind the agent's `bin` where it names one, and
  reports each call as pi and OpenHands report a tool of their own; a tool of ours named `shell` is refused there, as it
  would take every call of the harness's own. Elsewhere it is as it was
  ([Drivers](docs/extending/drivers.md#a-scripted-harness)).
- **OpenHands keeps its coding tools in the environment.** It declares `Capabilities.in_environment`, and on a gateway
  that says its session runs in the environment its sealed launch keeps its terminal, file editor and task tracker
  beside ours and the environment's, each action asking as on a key, and its terminal's shell starts on the `PATH` that
  `command_path` gives, the gateway's `environment_path` behind the agent's `bin` where it names one, which the startup
  files of the image's `bash` may change. Its check passes `own_tools_in_first_request_in_the_environment`, so it is
  trainable there ([Drivers](docs/extending/drivers.md#openhands-a-wire-worker)).
- **pi keeps its default tools in the environment.** It declares `Capabilities.in_environment`, and on a gateway that
  says its session runs in the environment its sealed launch keeps `read`, `bash`, `edit` and `write` beside ours and
  the environment's, all but `read` asking as on a key, and its settings put a line before each command its `bash`
  runs that sets the `PATH` `command_path` gives, the gateway's `environment_path` behind the agent's `bin` where it
  names one, while pi runs on Node and its packages as the runtime's `PATH` finds them. Its check passes
  `own_tools_in_first_request_in_the_environment`, so it is trainable there
  ([Drivers](docs/extending/drivers.md#a-sealed-launch)).
- **A pi that cannot start is refused with what it printed,** as where an image lacks a library pi's Node loads, such as
  `libatomic.so.1`: `team check`, `doctor`, a start and a check of pi say why, where before they said at most that pi
  said no version, or that it was gone ([Troubleshooting](docs/how-to/troubleshooting.md#pi-cannot-start)).
- **Every report is masked of every credential the runtime has given a harness,** an ended agent's among them, whichever
  agent's harness says it, as a command one agent runs can read another's; before, a harness's words were masked of its
  own alone ([Security](docs/security.md#redaction)). So each value of eight characters or more that an auth profile
  hands a harness is masked in every agent's words and in the ids they name, one that is no secret, such as a base URL,
  among them. A shorter value is too short to be any provider's key, and is masked in its own agent's words alone, as
  before, so it loses no other agent
  ([Troubleshooting](docs/how-to/troubleshooting.md#an-agent-is-lost-its-report-refused-with--in-it)).
- **Two admissions under way at once can no longer share a gateway's bearer.** The second was checked while the first
  waited for its agent's credential, before the first kept its bearer, so both could be admitted on one bearer, whose
  calls then went to no one agent; the second is now refused, as one made after the first is.

Changes a caller must follow:

- **A `Profile` you build to read levels names the installation its harness runs from,** with
  `platoon_harness.drivers.levels.installation`, new here, as the runtime's does: one that names none says nothing of
  a result made from a read-only installation ([Drivers](docs/extending/drivers.md#conformance)).
- **`DriverLink` takes the redactor of its agent's reports, `redact`, after `info`, and `in_environment` and
  `installation` by keyword, each required,** so code that makes one passes them; `Redactor.add` masks more secrets
  from then on.
- **A wire program served by 0.2.0's `serve` describes `capabilities.in_environment`,** which a runtime of 0.1.0
  refuses, as it refuses any field added since, saying the program did not describe itself: run such a program under a
  runtime of 0.2.0 or later. A frame names `in_environment` and `environment_path` only where they are given, so a
  program built on 0.1.0 takes every frame this release sends.
- **Every result `check_driver` makes holds a 32nd check,** `own_tools_in_first_request_in_the_environment`, which
  skips on each driver that declares no launch in the environment, so a test of a driver that asserts which checks
  skipped names it too, as the conformance tests here now do ([Drivers](docs/extending/drivers.md#conformance)).
- **`doctor --json` names each kept result's `installation`, and says in `unknown` why `current` is null:** the binary
  said no version, as before, or the mount of a path it runs from cannot be read. A harness whose driver cannot
  describe it, as a pi that cannot start, is not `found`, and the driver's words are its `reason`, which its line says
  ([Command line reference](docs/reference/cli.md#platoon-harness-doctor)).

A result kept under 0.1.0 speaks for no harness under 0.2.0, as a result speaks only for the SDK it was made under, so
every agent reads `unverified` until `platoon-harness doctor --check` runs again, or, where the command line is not
installed, `check_harness` and `write_conformance` do.

## 0.1.0 (2026-11-12)

The first release. platoon-harness runs the agent harnesses you already use, such as Claude Code, Codex, pi and
OpenHands, as one team, in durable sessions you can watch, steer, resume and read back.

- **Drivers for Claude Code, Codex, pi and OpenHands**, which can share a session, each harness on its own login or an
  auth profile, and a driver for agents that speak ACP. All are experimental, the four resting on upstream surfaces
  that change; no real ACP agent has passed the ACP driver's checks: OpenCode 2.2.6, run by hand on 2026-11-08, failed 7
  of 18 ([Compatibility](docs/reference/compatibility.md)).
- **Durable sessions.** A session is a folder holding one journal, so it can be watched from several clients at once,
  stopped, resumed, recovered after a crash and read back ([Concepts](docs/getting-started/concepts.md)).
- **Coordination.** Messages, channels, leased task queues, boards and waits as each agent's tools, with approvals a
  person or a policy answers once and budgets that stop a runaway
  ([architecture section 7](docs/architecture.md#7-primitive-semantics)).
- **Teams.** A team in TOML or Python, eight topology presets, and `team check` before anything costs
  ([Topologies](docs/how-to/topologies.md), [Team file](docs/reference/team-file.md)).
- **Workspaces.** The session's checkout, or a git worktree or a snapshot for each agent, each commit recorded as its
  maker's, a runtime test of a commit, and a merge queue written out. `isolated`, a confined snapshot, is experimental
  ([Workspaces](docs/how-to/workspaces.md)).
- **Three ways in besides Python.** The terminal UI, with review, provenance, a team editor and replay; the browser,
  with SwarmChat's page over a session and a page of your sessions; and headless commands for scripts and CI, with JSON
  lines and exit codes ([The terminal UI](docs/how-to/tui.md), [The browser](docs/how-to/web.md),
  [Command line reference](docs/reference/cli.md)).
- **Provenance.** What reached each agent, what an event rests on, whose work an outcome reaches, and estimators'
  rewards and credit beside the journal ([Provenance](docs/how-to/provenance.md)).
- **A Python SDK to extend.** Extensions, drivers of your own checked by `check_driver` and extensions by
  `check_extension`, and the SDK's half of a training contract, which no released trainer uses yet
  ([Extending](docs/extending/index.md), [Python API reference](docs/reference/python.md)).
- **One distribution, `platoon-harness`.** The library needs pydantic alone, and the `cli` extra adds the command
  line; without it, the `platoon-harness` command says what to install. The `openhands` extra adds OpenHands
  ([Install](docs/getting-started/install.md#openhands)).
- **A security policy and issue templates.** [SECURITY.md](SECURITY.md) says how to report a vulnerability privately,
  and the bug report and feature request templates ask for what `platoon-harness --version` prints, each harness and
  its version, the OS and the steps.

Its known limitations, Linux only among them, are in [STATUS](docs/STATUS.md#known-limitations), and what
platoon-harness does not protect against is in [Security](docs/security.md#what-it-does-not-protect).
