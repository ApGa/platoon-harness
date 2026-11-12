# Install

**Goal:** `platoon-harness` on your PATH, with what the harnesses you use need.

## Requirements

- **Linux.** Nothing has run on macOS ([STATUS](../STATUS.md)).
- **Python 3.12 or 3.13**, the two that CI tests, and [uv](https://docs.astral.sh/uv/), which finds one or downloads it.
- **The harnesses you want, on your PATH,** signed in as you usually are: `claude`, `codex` or `pi`. OpenHands needs no
  binary: see [OpenHands](#openhands).
- **git**, for an agent in a worktree or a snapshot of its own. A git workspace refuses a git older than 2.36, and
  2.47.3 is the only git the tests have run on.
- **Optionally, [bubblewrap](https://github.com/containers/bubblewrap)**, whose `bwrap` the experimental `isolated`
  workspace confines an agent with ([workspaces](../how-to/workspaces.md#where-an-isolated-agent-runs)).

To try it, [your first session](first-session.md) runs a team of pi and OpenHands on a model you name, at any endpoint
that speaks OpenAI's Chat Completions, with your key for it, from a checkout, which holds the examples.

## Install from PyPI

The command line, as a tool of its own:

```console
$ uv tool install "platoon-harness[cli]"
```

uv installs it in an environment of its own, on a Python it finds or downloads, and puts the `platoon-harness` command
on your PATH. The library alone, which needs pydantic and nothing more: `uv add platoon-harness`, or
`pip install platoon-harness`.

The tool sees only the drivers and extensions installed in its own environment, so name them when you install it, by
their extras and with `--with`:

```console
$ uv tool install "platoon-harness[cli,openhands]" --with my-extension
```

## Install from a checkout

To work on platoon-harness, or to run the examples, clone the repository and install from its lock file:

```console
$ git clone https://github.com/ApGa/platoon-harness.git && cd platoon-harness
$ uv sync
```

`uv sync` installs platoon-harness from the checkout, at the versions `uv.lock` names, with the `dev` group, which
holds the tests' tools, Playwright and platoon-harness's `cli` and `openhands` extras: what you need to work on
platoon-harness, which [CONTRIBUTING.md](../../CONTRIBUTING.md) goes on from.

To leave the dev group out, set `UV_NO_DEV=1` in your shell before `uv sync`, and keep it set: `uv run` brings the
environment in step with the lock file before it runs anything, with the dev group unless the variable says otherwise.
Name the `cli` extra, which the command line needs:

```console
$ export UV_NO_DEV=1
$ uv sync --extra cli
```

| You want | Run | It installs |
|---|---|---|
| To use it, and to work on it | `uv sync` | platoon-harness, and the dev group with its `cli` and `openhands` extras |
| To use it alone | `UV_NO_DEV=1 uv sync --extra cli` | platoon-harness with its `cli` extra |
| To use it with OpenHands | `UV_NO_DEV=1 uv sync --extra cli --extra openhands` | platoon-harness with its `cli` and `openhands` extras |

## OpenHands

`harness = "openhands"` runs a worker per agent on the runtime's own interpreter, so nothing is looked up on PATH. The
worker alone loads OpenHands, which the SDK's `openhands` extra brings, pinning `openhands-sdk` and `openhands-tools` at
1.59.0 exactly. Install the extra for the interpreter that runs the runtime, which is the command line's when it starts
a session: for the tool, name it with `cli`, as `uv tool install "platoon-harness[cli,openhands]"`. In a checkout, that
is the checkout's own, and `uv sync` installs the extra with the dev group. Without the dev group, name it with the
`cli` extra:

```console
$ UV_NO_DEV=1 uv sync --extra cli --extra openhands
```

`openhands-sdk` requires `lmnr`, which requires `lmnr-claude-code-proxy`, a binary under Laminar's own terms. The
checkout's lock leaves it out with `exclude-dependencies`, so a checkout never installs it, and the worker runs without
it. [Drivers](../extending/drivers.md#openhands-a-wire-worker) says why, and how to run the worker on an interpreter of
its own. A wheel carries no such exclusion, so the extra installed from the wheel, as an install from PyPI is, brings
`lmnr-claude-code-proxy` unless you exclude it: with uv, by `--excludes` with a file that names it, which
`uv tool install` and `uv pip install` take, or by `exclude-dependencies` in your own project's `[tool.uv]`, as the
checkout's `pyproject.toml` does. Either way, platoon-harness itself stays under the MIT license. OpenHands keeps no
login, so its role needs an auth profile that names its key.

## Check the installation

```console
$ platoon-harness --version
platoon-harness 0.1.0
$ platoon-harness doctor
```

In a checkout, run them through `uv run`.

`doctor` says what this machine has, and whether it can run a session. On a machine with `claude` and `codex` signed in
and no `pi`, after a checkout's `uv sync` and `platoon-harness doctor --check`, it printed this, its root and sockets
lines shown in the form they take for the default root, with `<home>`, `<filesystem>` and `<uid>` standing for your own,
and `...` for a line per driver and extension:

```text
platoon-harness 0.1.0
claude     2.1.319 (Claude Code), plan login, checked on 2.1.319: 26 passed, 4 skipped, none failed
codex      codex-cli 0.167.0, plan login, checked on 0.167.0: 25 passed, 5 skipped, none failed
openhands  1.59.0, login unknown, checked on 1.59.0: 26 passed, 4 skipped, none failed
pi         not on PATH
root       <home>/.local/state/platoon-harness, on <filesystem>
sockets    /run/user/<uid>/platoon-harness
...
usable
```

Each harness's line says its version and the kind of its login, from the harness's own status command, and never an
account, and whether a kept result of its checks speaks for the binary that runs: `platoon-harness doctor --check` runs
them, against a model of ours on loopback and on no account. Then come the root, where sessions live, and where their
sockets do, each driver and extension installed, and the verdict.

`doctor` exits 0 with `usable` when this machine can run a session, and 78 with `not usable` after a `problem` line for
each reason. With the dev group, or the `openhands` extra, it says `usable` even with no harness on PATH, as OpenHands
runs on the runtime's own interpreter. Without either, and with no harness on PATH, it ends:

```text
problem    no harness is on PATH
not usable
```

The root is `$PLATOON_HARNESS_HOME` if you set it, else `$XDG_STATE_HOME/platoon-harness`, which is
`~/.local/state/platoon-harness` by default. If that default is on a network filesystem, sessions live in
`/var/tmp/platoon-harness-<uid>` instead, and `doctor` says so under its root line.
[Troubleshooting](../how-to/troubleshooting.md) says what to do about each problem.

## Next steps

- [Concepts](concepts.md): the nine words, and what happens in a session.
- [Your first session](first-session.md): a team on your model, read back, then your own harnesses.
- [The headless quickstart](../how-to/headless.md): running teams from a terminal or CI.
