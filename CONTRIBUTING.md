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
| Report a bug | An issue from the bug report template, with what `platoon-harness doctor` prints, which shows your paths, user id and host name: edit out what you would not post |
| Report a security vulnerability | Never an issue: see [SECURITY.md](SECURITY.md) |
| Ask for a feature | An issue from the feature request template |
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

2. Install platoon-harness and the `dev` group from `uv.lock`, as CI does:

   ```bash
   uv sync --locked
   ```

   The `dev` group holds pytest and its plugins, hypothesis, pyte, Playwright, pre-commit, ruff, ty, and
   platoon-harness's `cli` and `openhands` extras. `--locked` refuses when `uv.lock` is out of date with
   `pyproject.toml`: after changing a requirement, run `uv lock` and commit `uv.lock` with it. If you set `UV_NO_DEV=1`
   to use platoon-harness alone, as
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
   platoon-harness 0.1.0
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
| Slow | `slow` | The harness binaries to cover on `PATH`, such as `claude`, `codex` and `pi`, and no login, as each runs against `FakeModel`. A test whose binary is missing skips, saying so. Those of the installed wheels need uv's cache to hold what they install, as [Releases](#releases) says | Only those of the installed wheels, in the release workflow |
| Browser | `e2e` | Playwright's Chromium headless shell, or each browser `PLATOON_HARNESS_BROWSERS` names, comma-separated, of `chromium`, `firefox` and `webkit`. Where one is missing, a browser test fails, saying how to install it, and never skips. One test also needs `claude` on `PATH`, and one `pi`, and each skips without it, as on CI's runners | Yes, once in each of the three |
| Live | `live` | `PLATOON_HARNESS_LIVE=1`, and the harnesses signed in as you usually are; the examples' need `pi`, and `PLATOON_HARNESS_LIVE_MODEL`, `OPENAI_BASE_URL` and `OPENAI_API_KEY` naming a model, its endpoint and your key. Each file's docstring states the model calls its tests may spend | Never |

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
| `tests/unit/runtime/test_bwrap.py`, and those of `tests/unit/runtime/test_isolation.py` on real bubblewrap | `bwrap` is not on `PATH`, or cannot confine here, as where unprivileged user namespaces are blocked. Ubuntu's AppArmor blocks them unless `kernel.apparmor_restrict_unprivileged_userns` is 0, which CI's `test` job sets. Where `PLATOON_HARNESS_REQUIRE_BWRAP=1`, as CI's `test` job sets it, they fail instead, saying why |
| One test of `tests/unit/runtime/test_bwrap.py` | There is no writable folder outside `/tmp` |
| One test each of `tests/unit/tools/test_ph.py` and `tests/unit/tools/test_shim.py` | The machine has no system `python3` |
| One test of `tests/unit/drivers/test_process.py` | There is no `/dev/full` |
| `test_the_recorded_mixed_team_s_layout_at_each_size` in `tests/unit/tui/test_snapshots.py`, and `tests/e2e/test_page_images.py` | No live run has recorded the mixed team's session yet, as [The docs' images](#the-docs-images) says |

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
so the title becomes the subject of the commit on `main`. CI's `pr-title` job (`amannn/action-semantic-pull-request` v6.1.2)
checks that the title is a Conventional Commit whose type is one of those above, with no scope and a summary that starts
with a capital letter and has no final period. When a pull request has a single commit, the job checks that commit's
subject too, because GitHub suggests it for the squashed commit. The job runs again whenever you edit the title.

**What CI runs.** Each job runs on GitHub's Ubuntu runners for pull requests into any branch, so that a pull request
stacked on another one is checked too, and for pushes to `main`. A new push cancels the run it makes stale. Each
workflow's token reads the repository and nothing more, and a job that needs more asks only to read, as `pr-title`
reads its pull request, but for the release workflow's `publish` job, which asks for an OIDC token alone, as
[Releases](#releases) says. Each action is pinned to a commit, with its release beside it, and each tool `uvx` fetches is
pinned to a release, so that a tag moved upstream or a new release changes nothing CI runs, and each checkout keeps no
credentials for a later step to read.

| Job | Checks | Fails when |
|---|---|---|
| `pr-title` | The title, on pull requests only | The title, or a single commit's subject, is not in the form above |
| `lint` | Every hook of the `pre-commit` stage, on every file | `uv.lock` is out of date, or a hook fails or changes a file |
| `test` | The fast tests, once on each of Python 3.12 and 3.13, with `UV_PYTHON` set to it, after lifting Ubuntu's restriction on unprivileged user namespaces, which bubblewrap needs, and with `PLATOON_HARNESS_REQUIRE_BWRAP=1` | git is older than 2.47, bubblewrap cannot confine, or a test fails |
| `e2e` | The browser tests, once in each of Chromium, Firefox and WebKit, with `PLATOON_HARNESS_BROWSERS` naming it | A browser test fails in that browser |
| `build`, of the release workflow | The distribution built and checked, and on a `v*` tag the tag too, as [Releases](#releases) says | A build or a check fails |

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
# build, of the release workflow, as Releases shows
```

The slow tests need harness binaries that CI does not have, so CI runs none of them but those of the installed wheels,
which need none, and it never runs the live ones.

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
| [docs/reference/python.md](docs/reference/python.md) | `tests/public_api.txt`, the docstrings, and what STATUS calls experimental | `tests/unit/docs/test_python_reference.py` |
| The key table in [docs/how-to/tui.md](docs/how-to/tui.md) | The terminal UI's bindings | `tests/unit/tui/test_keymap.py` |

```bash
uv run python -m platoon_harness_cli.reference > docs/reference/cli.md
uv run python -m platoon_harness_cli.reference python > docs/reference/python.md
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

- its entry point in `pyproject.toml`;
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
ballot = "ballot:extension"
```

Installing it activates nothing: a team names it in `extensions = [...]`. It uses only the kernel's public names, as the
core's primitives do, and its ops are usable through the SDK, MCP, `ph`, the command line, the terminal's palette and the
page's form with no core edit ([architecture §17](docs/architecture.md#17-extensions-and-configuration),
[STATUS](docs/STATUS.md#configuration-and-extensions-platoon_harnessconfig-platoon_harnessextensions)).
[examples/extension-package](examples/extension-package/README.md) is one, a package of its own with an op, a view and a
preset. An extension's name is its command group's, so one named as a command of the command line's own, such as `run`,
has no command, and the command line says why; and no session can load one named as an extension of the SDK's own, which
every session holds, such as `task` or `lease`.
Hold it to what a core primitive keeps with `check_extension` from `platoon_harness.testing`.
[Write an extension](docs/extending/extensions.md) builds that package step by step, checks it and says how to publish
one.

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
- its public names in `tests/public_api.txt`, and [docs/reference/python.md](docs/reference/python.md) made again;
- for each promise it makes in [architecture §7](docs/architecture.md#7-primitive-semantics), a test named for it;
- its row in [STATUS](docs/STATUS.md), naming the tests that hold it;
- [docs/reference/cli.md](docs/reference/cli.md) made again, as the command line derives its commands from the op table.

## Add an example

An example is a folder of `examples/`: a `README.md` that states the goal, what it needs, the steps and what to expect,
with the files a person runs and nothing else, no stand-in of a harness or a model among them. One that runs a team runs
it on a real model the person names, at an endpoint that speaks OpenAI's Chat Completions, which a role's auth profile
hands its harness as `OPENAI_BASE_URL` and `OPENAI_API_KEY`, and works on a copy of [the sample
project](examples/sample-project/README.md), whose issues list names each job. Each has a slow test in
`tests/integration/test_examples.py` that runs its README's commands as shown, with `fake-model` for MODEL and, beside a
run's settings, the one line `plays.OFFLINE` that hands pi its switch for no network, on its real pi or OpenHands
against `FakeModel`, which plays each agent from `tests/integration/plays.py`, so the harness, the tools and the team
file are real and only the model is scripted. A fast test there runs its copy, `team check` and `team show` as shown,
which need no harness, so CI's runners, which have no pi, run them. Each has a live test in
`tests/live/test_examples.py` that runs it on a real model and fails a run that took more model calls or minutes than
its README states; no budget counts model calls as they are made, so the team's own budget of turns and wall time is
what stops a runaway. Its files import nothing from the tests and reach the SDK by the names `tests/public_api.txt`
lists alone, which tests there hold. A cost a README quotes comes from a run that was made.

## The docs' images

The images of the terminal UI in `docs/assets` are copies of snapshots that `tests/unit/tui/test_snapshots.py` draws, which a
test holds to them byte for byte, and the page's images, `web-chat.png` and `web-provenance.png`, are what
`tests/e2e/test_page_images.py` writes. Each is to show a real session: the mixed team's, as a live run of it records it in
the folder `RECORDED` names in `tests/recorded.py`, its manifest and its journal's events and bodies in text, with every local
path, the host, the user, the group, the endpoint and the key replaced, and refused while the privacy scan catches anything. Once that recording is
there, `SCREENSHOTS` maps each screenshot to the recorded session's snapshot, but for `tui-patch.svg`, which stays a scripted
session's: a patch is read from git when it opens, and a recording keeps no repository. A live run on DeepSeek V4.1 Flash recorded the session
on 2026-11-08. The docs never show one of FakeModel's: the
live test refuses to record from an endpoint on loopback, where FakeModel serves.

Record it with the mixed team's live test alone, which may spend 50 model calls, with `PLATOON_HARNESS_LIVE_MODEL`,
`OPENAI_BASE_URL` and `OPENAI_API_KEY` set. It records only a run that passed each of its checks. Then draw the images from it:

```bash
PLATOON_HARNESS_LIVE=1 PLATOON_HARNESS_RECORD=tests/fixtures/sessions/mixed-team uv run pytest -q -m live tests/live/test_examples.py -k mixed_team
uv run pytest -q tests/unit/tui/test_snapshots.py -k recorded --snapshot-update
PLATOON_HARNESS_IMAGES=docs/assets uv run pytest -q -m e2e tests/e2e/test_page_images.py
```

Copy each snapshot over its screenshot as `test_each_screenshot_the_docs_show_is_its_snapshot_byte_for_byte` says, and say
under each image what drew it, as `tests/unit/docs/test_images.py` holds: `recorded`, with the model, under one of the recorded
session, and `scripted` under one of a scripted session. Show `web-chat.png` in the README's step 3 and in
[the browser guide](docs/how-to/web.md), and `web-provenance.png` in [provenance](docs/how-to/provenance.md), and reword the
sentences that link a screenshot as a scripted session's, in [the terminal UI guide](docs/how-to/tui.md) and the worktree team's
step 3. No test holds an image of the page to what a browser draws byte for byte, as that differs with the host's fonts. Read the
recording and each image before you commit them, as they are published with the repository.

## When a change needs an RFC

The list of changes that start with an RFC is in [the RFC index](docs/rfcs/README.md#when-to-write-an-rfc), with
[how to propose one](docs/rfcs/README.md#how-to-propose-a-change).

## Releases

platoon-harness is one distribution, `platoon-harness`, at the version `packages/sdk/src/platoon_harness/version.py`
sets. Below 1.0, as [CHANGELOG.md](CHANGELOG.md) says, a minor release may change the Python API, the team file or the
command line, and a patch release only fixes bugs.

A tag `vX.Y.Z` pushed to the repository publishes that release to PyPI. The release workflow checks it, and its
`publish` job uploads by trusted publishing from the GitHub environment `pypi`, which only `v*` tags may deploy to and
whose required reviewer, a maintainer, approves each deployment. A tag ruleset lets only the repository's admins create
`v*` tags, and a tag is pushed only at a maintainer's request.

### Cut a release

**Goal:** a commit on `main` that holds a release's version and its dated notes, which a maintainer's tag publishes.

1. Choose the version: the next patch release if the release only fixes bugs, and the next minor release otherwise.

2. In one pull request, set it:

   - in `packages/sdk/src/platoon_harness/version.py`, the one place the version is set;
   - in [CHANGELOG.md](CHANGELOG.md), by dating the release's heading, `## 0.2.0 (unreleased)` becoming
     `## 0.2.0 (YYYY-MM-DD)` with the day it merges;
   - on each page that shows what `--version` prints, `platoon-harness 0.1.0` today: this guide, whose line a
     test holds to the version, [Install](docs/getting-started/install.md) and
     [the headless quickstart](docs/how-to/headless.md).

   For the first release, also say how to install from PyPI where the README, the install guide and CHANGELOG's
   opening say that nothing is published or released yet, and keep it to Linux: its notes, like the install
   guide and each package's classifiers, name Linux alone, as nothing has run on macOS, whose CI the owner has put on
   hold.

3. Check the pull request as the release workflow does, with the commands below, and run the slow tests, which need the
   harness binaries CI does not have: `uv run pytest -q -m slow`, as [Run the tests](#run-the-tests) says. Then run the
   Scale case alone, `uv run pytest -q -s -m scale`, which no other run includes: it holds the Scale case to budgets that
   fit the hardware [Scale](docs/reference/scale.md) describes, so on other hardware, say in the pull request how what it
   printed compares.

4. Merge it once CI and the release workflow pass on it. The release workflow runs again on the commit on `main`.

5. A maintainer tags the merged commit and pushes the tag:

   ```bash
   git switch main && git pull --ff-only
   git tag -a v0.2.0 -m "platoon-harness 0.2.0"
   git push origin v0.2.0
   ```

   The release workflow checks the tag, builds and checks as on a pull request, and waits for a maintainer to approve
   the deployment to `pypi`, under Review deployments on the run's page. A tag that fails a check publishes nothing.

### The release workflow

The release workflow, `.github/workflows/release.yml`, builds platoon-harness and checks it on each pull request, each
push to `main` and each pushed `v*` tag. On a tag, its `build` job first checks that the tagged commit is on `main` and
that CHANGELOG.md dates the version:

```bash
gh api "repos/$GITHUB_REPOSITORY/compare/main...$GITHUB_SHA" --jq .status | grep -xE 'identical|behind'
grep -q "^## ${GITHUB_REF_NAME#v} (2" CHANGELOG.md
```

On every event, it builds the sdist and the wheel, checks on a tag that the tag names the version built, and checks
what it built:

```bash
uv build --no-sources
test -f "dist/platoon_harness-${GITHUB_REF_NAME#v}-py3-none-any.whl"
uvx twine@7.0.0 check --strict dist/*
uv run --isolated --no-project --with dist/*.whl python -I -c "import platoon_harness"
uv run --isolated --no-project --with "$(echo dist/*.whl)[cli]" platoon-harness --version
echo "platoon-harness[openhands] @ ./$(echo dist/*.whl)" | uv pip compile --excludes <(echo lmnr-claude-code-proxy) -
uv sync --locked
uv run pytest -q -m slow tests/integration/test_installed.py
```

`uv build` writes the sdist to `dist/`, then the wheel, built from the sdist, so an sdist that leaves out a file the
wheel needs fails here. `twine check --strict`, at the release the workflow pins, checks their metadata, and that the
description renders on PyPI, failing on a warning too. Each `uv run --isolated` installs the wheel in an environment of
its own, with only what its metadata requires: alone, the library imports, and with the `cli` extra, the command runs.
`uv pip compile` resolves the `openhands` extra with `lmnr-claude-code-proxy` excluded, as
[Install](docs/getting-started/install.md#openhands) says. The workflow runs every step on Python 3.12, the oldest the
distribution names, with `UV_PYTHON=3.12`.

`tests/integration/test_installed.py`, slow tests, build the wheel again and install it in environments of their own.
With the `cli` extra, the command line says its version, a headless run of
[examples/sdk-script](examples/sdk-script/README.md) settles on the `exec` driver and the command line reads it back,
and `uv tool install` puts the command on PATH. Alone, the library imports with nothing of the extra, and the command
says what to install. The wheel holds every file git tracks in each layer's package, and the `openhands` extra
requires what the install guide says. The tests take no network, so uv's cache must hold the build backend and each
requirement, as the steps before them leave it; where it does not, they fail, saying so, and never skip.

The job keeps `dist/` as an artifact of the run. On a tag pushed to this repository, and on no other event, the
`publish` job uploads it to PyPI with `pypa/gh-action-pypi-publish`, in the `pypi` environment. That job asks for an
OIDC token and nothing more, which PyPI trades for the right to upload, and runs no code of the repository.
