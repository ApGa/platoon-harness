# Changelog

What each release of platoon-harness changes. 0.1.0 is the first, for Linux: `uv tool install "platoon-harness[cli]"`
installs the command line, and `pip install platoon-harness` the library. Below 1.0, a minor release may change the
Python API, the team file or the command line, and a patch release only fixes bugs; require a range such as
`platoon-harness>=0.1,<0.2`. The Python API is each name `tests/public_api.txt` lists, and each attribute and method
without a leading underscore that a class it lists defines; nothing else is, and a name the
[Python API reference](docs/reference/python.md) marks experimental is part of it too.

## 0.1.0 (2026-11-12)

The first release. platoon-harness runs the agent harnesses you already use, such as Claude Code, Codex, pi and
OpenHands, as one team, in durable sessions you can watch, steer, resume and read back.

- **Drivers for Claude Code, Codex, pi and OpenHands**, which can share a session, each harness on its own login or an
  auth profile, and a driver for agents that speak ACP. All are experimental: the four rest on upstream surfaces that
  change, and the ACP driver has passed its checks only on a scripted agent, OpenCode on it being implemented only
  ([Compatibility](docs/reference/compatibility.md)).
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
