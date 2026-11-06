# platoon-harness

Bring the agent harnesses you already use, such as Claude Code, Codex and pi, together as a team: durable multi-agent
sessions with explicit coordination primitives, a terminal UI, a browser client, and honest provenance.

- **A session** is a folder holding one journal. Everything that happens is an event in it, so a session can be watched
  from several clients at once, stopped, resumed, and read back later.
- **Agents** run in their own harnesses, on your own logins. The runtime gives each one tools to message, start agents,
  claim tasks, post to boards and wait, under a topology you choose, which says who may reach whom.
- **Clients**: `platoon-harness` alone opens the terminal UI, `platoon-harness web` serves SwarmChat's page over a session's
  journal, the headless commands suit scripts and CI, and the Python SDK is what all of them are built on.

## Status

Milestone 1, a working vertical slice, is done on Linux: a team of real harnesses, started, watched and steered from the
terminal UI, the browser or the command line. Milestones 2 (dependable coordination) and 3 (training with Platoon) are in
progress, and 4 (production polish) is planned. [docs/STATUS.md](docs/STATUS.md) says what is implemented, what is tested
and how, and what is planned. Nothing is published to PyPI yet.

## Try it

You need Python 3.12 or later, [uv](https://docs.astral.sh/uv/), and the harnesses you want on your PATH (`claude`,
`codex`, `pi`), signed in as you usually are.

```console
$ git clone https://github.com/ApGa/platoon-harness.git && cd platoon-harness
$ uv sync
$ uv run platoon-harness doctor     # what this machine has
$ uv run platoon-harness init       # a starter platoon-harness.toml from the harnesses it found
$ uv run platoon-harness            # the terminal UI
```

## Documentation

| Read | For |
|---|---|
| [docs/architecture.md](docs/architecture.md) | The design of record, and [docs/rfcs/](docs/rfcs/) for why each decision was made |
| [docs/how-to/tui.md](docs/how-to/tui.md), [docs/how-to/web.md](docs/how-to/web.md), [docs/how-to/headless.md](docs/how-to/headless.md), [docs/reference/cli.md](docs/reference/cli.md) | The terminal UI, the browser, headless runs, and every command |
| [docs/how-to/topologies.md](docs/how-to/topologies.md) | Teams and topologies, with a worked example per preset |
| [docs/how-to/workspaces.md](docs/how-to/workspaces.md) | Where each agent works, a worktree of its own among them, and what becomes of it |
| [docs/how-to/provenance.md](docs/how-to/provenance.md) | What reached each agent, what it rests on, whose work an outcome reaches, and credit beside the journal |
| [examples/mixed-team](examples/mixed-team/README.md) | A Claude Code lead and a Codex worker in one session, run, watched, steered and read back, with no keys too |
| [docs/extending/drivers.md](docs/extending/drivers.md), [docs/reference/compatibility.md](docs/reference/compatibility.md) | How a harness is driven, and what each one supports |
| [AGENTS.md](AGENTS.md) | Rules for changing this repository, human or agent |
| [CHANGELOG.md](CHANGELOG.md) | What changed |

## License

MIT. `platoon-harness web` serves SwarmChat's page assets, which are MIT, © The SwarmChat Authors.
