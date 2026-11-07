# Contributing to platoon-harness

Thank you for helping. This guide says how to set up a checkout, run the tests, check and commit a change, open a pull
request, and add what contributors add most often: a driver, an extension, a topology preset, an op and an example.
[AGENTS.md](AGENTS.md) holds the rules every change follows, and [architecture.md](docs/architecture.md) is the design.

Small changes, such as a bug fix, a test or a fix to the docs, go straight to a pull request. Some changes start with an
RFC: see [When a change needs an RFC](#when-a-change-needs-an-rfc).

- [Ways to contribute](#ways-to-contribute)
- [Set up a development environment](#set-up-a-development-environment)
- [Run the tests](#run-the-tests)
- [Design rules](#design-rules)
- [Lint, format and type-check](#lint-format-and-type-check)
- [Commits and pull requests](#commits-and-pull-requests)
- [Generated docs](#generated-docs)
- [Add a driver](#add-a-driver)
- [Add an extension](#add-an-extension)
- [Add a topology preset](#add-a-topology-preset)
- [Add an op or a primitive](#add-an-op-or-a-primitive)
- [Add an example](#add-an-example)
- [When a change needs an RFC](#when-a-change-needs-an-rfc)
- [Releases](#releases)

## Ways to contribute

| You want to | Start with |
|---|---|
| Report a bug | An issue with the command you ran, what it printed, what you expected, the commit you ran it on, and what `uv run platoon-harness doctor` prints, which shows your paths, user id and host name: edit out what you would not post |
| Fix a bug | A pull request; a fix comes with a test that fails without it |
| Run a harness the SDK does not drive | Usually no change here: [Add a driver](#add-a-driver) |
| Add a topology preset | Usually an extension of your own: [Add a topology preset](#add-a-topology-preset) |
| Propose a design change | An RFC: [When a change needs an RFC](#when-a-change-needs-an-rfc) |
| Improve the docs | A pull request; [docs/README.md](docs/README.md) lists every page |

## Set up a development environment

**Goal:** a checkout where `platoon-harness` runs and the tests pass.

**Prerequisites:**

- Linux. Nothing has run on macOS ([STATUS](docs/STATUS.md)).
- Python 3.12 or 3.13, the two that CI tests, and [uv](https://docs.astral.sh/uv/), which finds one or downloads it.
- git 2.47 or later. A git workspace refuses a git older than 2.36, but 2.47.3 is the only git the tests have run on, so
  CI fails on an older one.
- Optionally, [bubblewrap](https://github.com/containers/bubblewrap): the `isolated` workspace confines an agent with its
  `bwrap`, and without it those tests skip, saying why.

The fast and browser tests need no harness, login or model key.

1. Clone the repository:

   ```bash
   git clone https://github.com/ApGa/platoon-harness.git && cd platoon-harness
   ```

2. Install the packages and the `dev` group from `uv.lock`, as CI does:

   ```bash
   uv sync --locked
   ```

   The `dev` group holds pytest and its plugins, hypothesis, pyte, Playwright, pre-commit, ruff, ty, and the SDK's
   `openhands` extra. `--locked` refuses when `uv.lock` is out of date with a `pyproject.toml`: after changing a
   requirement, run `uv lock` and commit `uv.lock` with it. If you set `UV_NO_DEV=1` to use the packages alone, as
   [Install](docs/getting-started/install.md#install-from-a-checkout) has it, unset it first: while it is set, `uv sync`
   leaves the group out, and the hooks and the tests run from it.

3. Install the git hooks. `.pre-commit-config.yaml` names both kinds, so this installs the `pre-commit` hook, which runs
   the checks of CI's `lint` job on what you commit, and the `commit-msg` hook, which checks each commit message:

   ```bash
   uv run pre-commit install
   ```

   ```text
   pre-commit installed at .git/hooks/pre-commit
   pre-commit installed at .git/hooks/commit-msg
   ```

4. Check that the command line runs:

   ```bash
   uv run platoon-harness --version
   ```

   ```text
   platoon-harness 0.1.0, SDK 0.1.0
   ```

**Next:** [run the tests](#run-the-tests).

## Run the tests

All but the live tests run on a CPU, with no network and no login: a harness under test runs against `FakeModel`, a
model of ours on loopback, on a dummy key. `pyproject.toml`'s `addopts` selects the fast tests by default, leaving out
the slow, browser and live ones. CI runs the fast tests on Python 3.12 and 3.13, on one worker per CPU:

```bash
uv run pytest -q -n auto
```

To run them on 3.13, set `UV_PYTHON=3.13` for both `uv sync` and `uv run`, as CI's `test` job does.

| Tests | Marker | Need | In CI |
|---|---|---|---|
| Fast | none | Nothing more | Yes, on 3.12 and 3.13 |
| Slow | `slow` | The harness binaries to cover on `PATH`, such as `claude`, `codex` and `pi`, and no login, as each runs against `FakeModel`. A test whose binary is missing skips, saying so | No |
| Browser | `e2e` | Playwright's Chromium headless shell, or each browser `PLATOON_HARNESS_BROWSERS` names, comma-separated, of `chromium`, `firefox` and `webkit`. Where one is missing, a browser test fails, saying how to install it, and never skips. One test also needs `claude` on `PATH`, and skips without it | Yes, once in each of the three, as the workflow says, which no runner has shown yet |
| Live | `live` | `PLATOON_HARNESS_LIVE=1`, and the harnesses signed in as you usually are. Each file's docstring states the model calls its tests may spend | Never |

```bash
uv run pytest -q -m slow
uv run playwright install chromium-headless-shell
uv run pytest -q -m e2e
PLATOON_HARNESS_LIVE=1 uv run pytest -q -m live tests/live/test_claude.py
```

Each browser test runs once in each browser `PLATOON_HARNESS_BROWSERS` names, its id naming the browser, as
`PLATOON_HARNESS_BROWSERS=chromium,firefox` runs them in both; `uv run playwright install firefox` or `webkit` installs another.
Playwright's WebKit needs glibc 2.38 or later, so it does not start on RHEL 9, whose glibc is 2.34.

A live test spends model calls on your logins, so run only the ones your change needs, and say in the pull request which
ran and what they spent. A skipped live test is not a passing one.

While you work, run what you touch, such as `uv run pytest -q tests/unit/primitives`.

### What skips, and why

`addopts` has `-ra`, so every run ends by listing each skipped test with its reason. Of the fast tests, these skip:

| Tests | Skip when |
|---|---|
| `tests/unit/runtime/test_bwrap.py`, and those of `tests/unit/runtime/test_isolation.py` on real bubblewrap | `bwrap` is not on `PATH`, or cannot confine here, as where unprivileged user namespaces are blocked. Ubuntu's AppArmor blocks them unless `kernel.apparmor_restrict_unprivileged_userns` is 0, which CI's `test` job sets |
| One test of `tests/unit/runtime/test_bwrap.py` | There is no writable folder outside `/tmp` |
| One test each of `tests/unit/tools/test_ph.py` and `tests/unit/tools/test_shim.py` | The machine has no system `python3` |
| One test of `tests/unit/drivers/test_process.py` | There is no `/dev/full` |

## Design rules

[AGENTS.md](AGENTS.md) holds the rules every change follows, human or agent: the clean room, taste, the layers, how tests
are written, the commit form and STATUS. Read it before your first change.

## Lint, format and type-check

`.pre-commit-config.yaml` defines four hooks. CI's `lint` job runs every hook of the `pre-commit` stage on every file:

```bash
uv run pre-commit run --all-files --show-diff-on-failure
```

| Hook | What it checks | Configured in |
|---|---|---|
| `ruff-check` (ruff-pre-commit `v0.14.5`, with `--fix`) | Lint rules; it fixes what it can | `[tool.ruff]` and `[tool.ruff.lint]` in `pyproject.toml` |
| `ruff-format` | Formatting | `[tool.ruff]` in `pyproject.toml` |
| `ty` (`uv run ty check`) | Types, across the packages, when a commit changes a Python file | `ty.toml` |
| `conventional-pre-commit` (`v4.0.0`, at the `commit-msg` stage, with `--verbose`) | The form of each commit message, when you commit; a rejection lists the accepted types. CI does not run it: the title check holds a pull request's title to the same form | Its default types, the ones in [Commits and pull requests](#commits-and-pull-requests) |

To run the checks one at a time, without the hooks' fixes:

```bash
uv run ruff check . && uv run ruff format --check .
uv run ty check
```

When a hook fixes a file during `git commit`, the commit stops; add the fixed files and commit again.

The ruff hook's `rev` is the version the `dev` group pins, `ruff==0.14.5`, so the hook and `uv run ruff` agree; a test
holds them equal, so change both together. Keep `conventional-pre-commit` at `v4.0.0`: later releases accept any message
that starts with `Merge`, and a type in any case (`Feat:`), which the pull request title check rejects.

## Commits and pull requests

**Branches.** Branch from `main`, and keep one topic per pull request.

**Commit messages.** [AGENTS.md](AGENTS.md#commits) gives the form: a
[Conventional Commit](https://www.conventionalcommits.org/), `<type>: <summary>`, with no scope and a summary in sentence
case without a final period, then a blank line and a body that says why:

```text
fix: Name a test command in the --trust help

A `test` command from a project file is refused until trusted, but the `--trust`
help listed only a command harness, a module:attr and an auth profile, so a
person reading it would not learn that --trust is what clears the new refusal.
The help now names a test command too, and the generated reference is regenerated.
```

| Type | For |
|---|---|
| `feat` | A new feature, option or command |
| `fix` | A bug fix |
| `docs` | Documentation only |
| `refactor` | A code change that neither fixes a bug nor adds a feature |
| `perf` | A performance improvement |
| `test` | Tests only |
| `build` | Packaging and dependencies |
| `ci` | The CI workflows |
| `chore` | Other maintenance, such as the git hooks |
| `style` | Formatting only |
| `revert` | Reverting an earlier commit |

For example, from this repository's history:

```text
feat: Give an agent the ref of a recorded commit, by its SHA
docs: Write out the merge queue for worktree teams
test: Pin Claude Code's conformance at 2.1.318, where its checks last passed
chore: Drop the extensions workspace member that has no package
```

A change that breaks a public contract needs an RFC first. The commit that makes it puts `!` after the type and ends
with a `BREAKING CHANGE:` footer that says what users must change:

```text
refactor!: Rename <the old name> to <the new name>

<Why.>

BREAKING CHANGE: <what users must change>
```

The `commit-msg` hook rejects a subject that is not one of these types, an optional scope, an optional `!`, a colon, a
space and a summary, and a body that does not follow a blank line. It accepts a scope and does not check the summary's
case: reviewers do, and for the title, the title check. To check a message without committing, save it to a file and run
the hook on it:

```bash
uv run pre-commit run conventional-pre-commit --hook-stage commit-msg --commit-msg-filename message.txt
```

**Pull request titles.** A pull request's title has the form of a commit subject. Maintainers squash-merge pull requests,
so the title becomes the subject of the commit on `main`. CI's `pr-title` job (`amannn/action-semantic-pull-request@v6`)
checks that the title is a Conventional Commit whose type is one of those above, with no scope and a summary that starts
with a capital letter and has no final period. When a pull request has a single commit, the job checks that commit's
subject too, because GitHub suggests it for the squashed commit. The job runs again whenever you edit the title.

**What CI runs.** Each job runs on GitHub's Ubuntu runners for pull requests into any branch, so that a pull request
stacked on another one is checked too, and for pushes to `main`. A new push cancels the run it makes stale.

| Job | Checks | Fails when |
|---|---|---|
| `pr-title` | The title, on pull requests only | The title, or a single commit's subject, is not in the form above |
| `lint` | Every hook of the `pre-commit` stage, on every file | `uv.lock` is out of date, or a hook fails or changes a file |
| `test` | The fast tests, once on each of Python 3.12 and 3.13, with `UV_PYTHON` set to it, after lifting Ubuntu's restriction on unprivileged user namespaces, which bubblewrap needs | git is older than 2.47, or a test fails |
| `e2e` | The browser tests, once in each of Chromium, Firefox and WebKit, with `PLATOON_HARNESS_BROWSERS` naming it, as the workflow says, which no runner has shown yet | A browser test fails in that browser |

The commands, job by job:

```bash
# lint
uv sync --locked
uv run pre-commit run --all-files --show-diff-on-failure
# test
sudo apt-get update && sudo apt-get install -y bubblewrap
sudo sysctl -w kernel.apparmor_restrict_unprivileged_userns=0
git --version && printf '2.47\n%s\n' "$(git --version | cut -d' ' -f3)" | sort -V -C
uv sync --locked
uv run pytest -q -n auto
# e2e, once with PLATOON_HARNESS_BROWSERS set to each of chromium, firefox and webkit
uv sync --locked
uv run playwright install --with-deps --only-shell "$PLATOON_HARNESS_BROWSERS"
uv run pytest -q -m e2e
```

The slow tests need harness binaries that CI does not have, so CI never runs them, and it never runs the live ones.

**The pull request.** Push your branch and open a pull request into `main`. The
[pull request template](.github/pull_request_template.md) asks for each of these:

- What changes and why, and how you tested it: the tests you added, the commands you ran with what they showed, and
  which live tests ran with their budget, or none.
- A test for every fix and feature; a fix's test fails without the fix.
- The docs, examples, command-line help, STATUS and `tests/public_api.txt` that the change affects, updated, and
  generated docs made again.
- No secrets, local paths, cluster names or account details in code, configs, docs or tests.
- A link to what it belongs to: `Fixes #123`, or `Implements RFC NNNN, milestone M2`
  ([Linking an RFC to its implementation](docs/rfcs/README.md#linking-an-rfc-to-its-implementation)).

platoon-harness is released under the [MIT license](LICENSE), and contributions are accepted under the same license.

## Generated docs

Some pages are made from the code. Never edit them by hand: change the code, and make them again. A test holds each one
to the code, and names the command when they differ.

| Page | Made from | Held by |
|---|---|---|
| [docs/reference/cli.md](docs/reference/cli.md) | The command definitions | `tests/unit/cli/test_commands.py` |
| [docs/reference/team-file.md](docs/reference/team-file.md) | The team file's schema, from `Team` down, and the presets | `tests/unit/cli/test_team_file.py` |
| The key table in [docs/how-to/tui.md](docs/how-to/tui.md) | The terminal UI's bindings | `tests/unit/tui/test_keymap.py` |

```bash
uv run python -m platoon_harness_cli.reference > docs/reference/cli.md
uv run python -m platoon_harness_cli.team_file > docs/reference/team-file.md
uv run python -m platoon_harness_cli.tui.keymap docs/how-to/tui.md
```

## Add a driver

A driver presents one harness session to the runtime. Most harnesses need no change here:
[Drivers](docs/extending/drivers.md) has the contract and a guide to each way in.

| You have | Do this | Pull request here |
|---|---|---|
| A CLI that takes a task and exits | An `exec` harness: one line of a team file | No |
| A program in any language, or a dependency set that cannot share ours | A `wire` program that speaks JSON-RPC on stdio | No |
| A Python package | A class with the seven methods, under the `platoon_harness.drivers` entry-point group | No |
| A harness the SDK should drive itself | A driver in `packages/sdk/src/platoon_harness/drivers/` | Yes |

Whichever way, prove it with `check_driver` from `platoon_harness.testing`, which runs named checks against `FakeModel`
and reports every failure at once; a skip is never a pass. A driver the SDK ships also needs:

- its entry point in `packages/sdk/pyproject.toml`;
- its name in `CHECKED`, in `packages/sdk/src/platoon_harness/drivers/levels.py`, and how to check it in
  `packages/sdk/src/platoon_harness/testing/harnesses.py`, so that `platoon-harness doctor --check` checks it where it
  finds it;
- a slow test on the real binary against `FakeModel`, as `tests/integration/test_claude.py` is for `claude`;
- what is known of it in [compatibility](docs/reference/compatibility.md);
- its rows under Drivers in [STATUS](docs/STATUS.md).

## Add an extension

An extension adds ops, views, daemons, presets or an isolation with no core edit. It is an `Extension` from
`platoon_harness.kernel`, registered under the `platoon_harness.extensions` entry-point group of its package:

```toml
[project.entry-points."platoon_harness.extensions"]
ballot = "my_package:extension"
```

Installing it activates nothing: a team names it in `extensions = [...]`. It uses only the kernel's public names, as the
core's primitives do, and its ops are usable through the SDK, MCP and `ph` with no core edit, though the command line and
the terminal UI have no command for them yet ([architecture §17](docs/architecture.md#17-extensions-and-configuration),
[STATUS](docs/STATUS.md#configuration-and-extensions-platoon_harnessconfig-platoon_harnessextensions)).
Hold it to what a core primitive keeps with `check_extension` from `platoon_harness.testing`
([Drivers, Extensions](docs/extending/drivers.md#extensions)).

## Add a topology preset

A preset is a plain function that returns a `Topology`. Listed on an extension of your own, it has the power of a built-in:
[Write your own preset](docs/how-to/topologies.md#write-your-own-preset) shows one. A built-in preset is a function in
`packages/sdk/src/platoon_harness/topology/presets.py`, added to `PRESETS`, which also needs:

- its name in `tests/public_api.txt`, as `platoon_harness.topology` exports it;
- a team in `tests/unit/topology/support.py`, and its name in `tests/unit/topology/test_presets.py`, which checks every
  preset against its team;
- a worked example under The presets in [docs/how-to/topologies.md](docs/how-to/topologies.md), whose forms
  `tests/unit/topology/test_docs.py` runs;
- the presets' row under Teams and topologies in [STATUS](docs/STATUS.md).

## Add an op or a primitive

An op is a named, typed, synchronous function, and the only way to change a session; `ph`, MCP, the SDK and the command
line all derive from the op table ([architecture §6](docs/architecture.md#6-operations)). A new op of the core, or a new
primitive, needs:

- an RFC first, as it changes the op table and so the command line
  ([When a change needs an RFC](#when-a-change-needs-an-rfc));
- names under the [naming law](docs/architecture.md#naming-law);
- its public names in `tests/public_api.txt`;
- for each promise it makes in [architecture §7](docs/architecture.md#7-primitive-semantics), a test named for it;
- its row in [STATUS](docs/STATUS.md), naming the tests that hold it;
- [docs/reference/cli.md](docs/reference/cli.md) made again, as the command line derives its commands from the op table.

## Add an example

An example is a folder of `examples/`: a `README.md` that states the goal, what it needs, the steps and what to expect,
with the files it runs. Each has a CPU test that runs it as its README does, on scripted stand-ins or `FakeModel`, so it
cannot break unseen: `tests/integration/test_examples.py` runs [the mixed team](examples/mixed-team/README.md) and
[the SDK script](examples/sdk-script/README.md). A cost the README quotes comes from a run that was made, as the mixed
team's does.

## When a change needs an RFC

The list of changes that start with an RFC is in [the RFC index](docs/rfcs/README.md#when-to-write-an-rfc), with
[how to propose one](docs/rfcs/README.md#how-to-propose-a-change).

## Releases

Nothing is published yet. How to cut a release is written here before the first one.
