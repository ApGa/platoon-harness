# Install

**Goal:** `platoon-harness` on your PATH, with what the harnesses you use need.

## Requirements

- **Linux.** Nothing has run on macOS.
- **Python 3.12 or later**, which CI tests on 3.12 and 3.13, and [uv](https://docs.astral.sh/uv/), which finds one or
  downloads it.
- **git 2.36 or later**, for an agent in a worktree or a snapshot of its own. The tests run on 2.47.
- **Optionally, [bubblewrap](https://github.com/containers/bubblewrap)**, for the experimental `isolated` workspace
  ([workspaces](../how-to/workspaces.md#where-an-isolated-agent-runs)).
- **The harnesses you use**, on your PATH and signed in as you usually are. OpenHands needs no binary: see
  [OpenHands](#openhands).

| Harness | Command | Install and sign in |
|---|---|---|
| Claude Code | `claude` | [anthropics/claude-code](https://github.com/anthropics/claude-code) |
| Codex | `codex` | [openai/codex](https://github.com/openai/codex) |
| pi | `pi` | [earendil-works/pi](https://github.com/earendil-works/pi), on Node 22.19 or later |
| OpenCode | `opencode` | [anomalyco/opencode](https://github.com/anomalyco/opencode). Its driver does not pass all its checks yet |

[STATUS](../STATUS.md) says what has run on each.

## Install

The command line, as a tool of its own:

```console
$ uv tool install "platoon-harness[cli]"
```

uv installs it in an environment of its own and puts `platoon-harness` on your PATH. The tool sees only what that
environment holds, so add a driver or an extension package to it with `--with`, as
`uv tool install "platoon-harness[cli]" --with PACKAGE`, and OpenHands with its extra, [below](#openhands). Installing
again replaces what the tool held, so name every extra and package you want each time. `uv tool upgrade platoon-harness`
upgrades it, and your sessions stay where they are.

The library alone, for a script, needs pydantic and nothing more: `uv add platoon-harness`, or
`pip install platoon-harness`. Its `platoon-harness` command only says how to install the `cli` extra.

To work on platoon-harness itself, set up a checkout as
[CONTRIBUTING](../../CONTRIBUTING.md#set-up-a-development-environment) says.

## OpenHands

`harness = "openhands"` runs a worker per agent on the runtime's own interpreter, so nothing is looked up on PATH. The
worker alone loads OpenHands, which platoon-harness's `openhands` extra brings, pinning `openhands-sdk` and
`openhands-tools` at 1.59.0 exactly. Install the extra with the command line:

```console
$ echo lmnr-claude-code-proxy > excludes.txt
$ uv tool install "platoon-harness[cli,openhands]" --excludes excludes.txt
```

`openhands-sdk` requires `lmnr`, which requires `lmnr-claude-code-proxy`, a binary under Laminar's own terms. Nothing
the worker runs imports it, as only `lmnr`'s instrumentation of the Claude Agent SDK does, so the worker runs without
it. A wheel carries no exclusion, so the extra installed from the wheel, as an install from PyPI is, brings
`lmnr-claude-code-proxy` unless you exclude it: `--excludes` with that file does, for `uv tool install` as above or for
`uv pip install` in a virtual environment, and pip has no way to. The checkout's lock leaves it out with
`exclude-dependencies`, so a checkout never installs it. Either way, platoon-harness itself stays under the MIT license.

OpenHands keeps no login, so its role needs an auth profile that names its key. Where OpenHands' pins cannot share an
environment with yours, [Drivers](../extending/drivers.md#openhands-a-wire-worker) runs the worker on an interpreter of
its own.

## Check the installation

```console
$ platoon-harness --version
platoon-harness 0.1.0
$ platoon-harness doctor
```

On a machine with `claude` and `codex` signed in on plans, once `platoon-harness doctor --check` has run, `doctor` says
this, with `<home>`, `<filesystem>` and `<uid>` standing for your own, and `...` for a line per installed driver and
extension:

```text
platoon-harness 0.1.0
claude     2.1.319 (Claude Code), plan login, checked on 2.1.319: 26 passed, 4 skipped, none failed
codex      codex-cli 0.167.0, plan login, checked on 0.167.0: 25 passed, 5 skipped, none failed
opencode   not on PATH
openhands  1.59.0, login unknown, checked on 1.59.0: 26 passed, 4 skipped, none failed
pi         not on PATH
root       <home>/.local/state/platoon-harness, on <filesystem>
sockets    /run/user/<uid>/platoon-harness
...
usable
```

A harness's line says its version and the kind of its login, from the harness's own status command, never an account,
and what its checks found: `doctor --check` runs them against a model of ours on loopback, on no account. The root is
where sessions live, chosen as
[Sessions are not where you looked](../how-to/troubleshooting.md#sessions-are-not-where-you-looked) says. `doctor` ends
`usable` and exits 0 when this machine can run a session, and otherwise names each `problem`, ends `not usable` and
exits 78: [Troubleshooting](../how-to/troubleshooting.md) says what to do about each.

## Next steps

- [Concepts](concepts.md): the nine words, and what happens in a session.
- [Your first session](first-session.md): a team on a model you name, read back.
- [Run headless](../how-to/headless.md): teams from a terminal or CI, on your own harnesses.
