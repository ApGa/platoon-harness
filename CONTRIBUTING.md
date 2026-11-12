# Contributing to platoon-harness

Thank you for helping. This guide says how to set up a checkout, run the tests, check and commit a change, open a pull
request, and add what contributors add most often: a driver, an extension, a topology preset, an op and an example.
[AGENTS.md](AGENTS.md) holds the rules every change follows, human or agent, and [architecture.md](docs/architecture.md)
is the design.

Small changes, such as a bug fix, a test or a fix to the docs, go straight to a pull request. Some changes start with an
RFC: see [When a change needs an RFC](#when-a-change-needs-an-rfc).

- [Ways to contribute](#ways-to-contribute)
- [Set up a development environment](#set-up-a-development-environment)
- [Repository layout](#repository-layout)
- [Run the tests](#run-the-tests)
- [Lint, format and type-check](#lint-format-and-type-check)
- [Commits and pull requests](#commits-and-pull-requests)
- [Generated docs](#generated-docs)
- [Add a driver](#add-a-driver)
- [Add an extension](#add-an-extension)
- [Add a topology preset](#add-a-topology-preset)
- [Add an op or a primitive](#add-an-op-or-a-primitive)
- [Add an example](#add-an-example)
- [The docs' images](#the-docs-images)
- [When a change needs an RFC](#when-a-change-needs-an-rfc)
- [Releases](#releases)

## Ways to contribute

| You want to | Start with |
|---|---|
| Report a bug | An issue from the bug report template: what you ran, what it printed and what you expected, what `platoon-harness --version` prints, each harness with its version, your OS, and what `platoon-harness doctor` prints, which shows your paths, user id and host name: edit out what you would not post |
| Report a security vulnerability | Never an issue: see [SECURITY.md](SECURITY.md) |
| Ask a question | An issue |
| Ask for a feature | An issue from the feature request template |
| Fix a bug | A pull request; a fix comes with a test that fails without it |
| Run a harness the SDK does not drive | Usually no change here: [Add a driver](#add-a-driver) |
| Add a topology preset | Usually an extension of your own: [Add a topology preset](#add-a-topology-preset) |
| Propose a design change | An RFC: [When a change needs an RFC](#when-a-change-needs-an-rfc) |
| Improve the docs | A pull request; [docs/README.md](docs/README.md) lists every page |

## Set up a development environment

**Goal:** a checkout where `platoon-harness` runs and the tests pass.

**Prerequisites:** Linux, as nothing has run on macOS; Python 3.12 or 3.13, the two CI tests, and
[uv](https://docs.astral.sh/uv/); git 2.47 or later, as CI requires; and optionally
[bubblewrap](https://github.com/containers/bubblewrap), without which the tests of the `isolated` workspace skip, saying
why. On Ubuntu, AppArmor blocks bubblewrap unless `sudo sysctl -w kernel.apparmor_restrict_unprivileged_userns=0`, as
CI's test job sets. The fast and browser tests need no harness, login or model key.

1. Clone the repository:

   ```bash
   git clone https://github.com/ApGa/platoon-harness.git && cd platoon-harness
   ```

2. Install platoon-harness and the `dev` group, which holds the tests' tools and the `cli` and `openhands` extras, from
   `uv.lock`, as CI does, with `UV_NO_DEV` unset; after changing a requirement, run `uv lock` and commit `uv.lock` too:

   ```bash
   uv sync --locked
   ```

3. Install the git hooks, the `pre-commit` hook, which runs CI's lint checks on what you commit, and the `commit-msg`
   hook, which checks each message:

   ```bash
   uv run pre-commit install
   ```

4. Check that the command line runs:

   ```bash
   uv run platoon-harness --version
   ```

   ```text
   platoon-harness 0.1.0
   ```

**Next:** [run the tests](#run-the-tests).

## Repository layout

| Path | What it holds |
|---|---|
| `packages/sdk/` | The SDK, `platoon_harness`: the kernel, the primitives, the runtime, the topology, the tool plane, the drivers and the testing kit |
| `packages/cli/` | The command line, `platoon_harness_cli`: the `platoon-harness` command, the terminal UI and the server of SwarmChat's page, whose dependencies the `cli` extra installs |
| `examples/` | The runnable examples, the sample project they work on, and a sample extension package |
| `tests/` | `unit/` and `integration/`, on a CPU, the slow ones marked; `e2e/`, the browser tests; `live/`, on real models and logins; `conformance/`, the suite run on every driver |
| `docs/` | The documentation, which [docs/README.md](docs/README.md) lists |

## Run the tests

All but the live tests run on a CPU, with no network and no login: a harness under test runs against `FakeModel`, a
model of ours on loopback, on a dummy key. `pyproject.toml`'s `addopts` selects the fast tests, which CI runs on Python
3.12 and 3.13, with `UV_PYTHON` naming each:

```bash
uv run pytest -q -n auto
```

| Tests | Marker | Need | In CI |
|---|---|---|---|
| Fast | none | Nothing more | Yes, on 3.12 and 3.13 |
| Slow | `slow` | The harness binaries to cover on `PATH`, such as `claude`, `codex` and `pi`, each against `FakeModel`; a test whose binary is missing skips, saying so. Those of the installed wheels need uv's cache to hold what they install | Only those of the installed wheels, in the release workflow |
| Browser | `e2e` | Playwright's Chromium headless shell, or each browser `PLATOON_HARNESS_BROWSERS` names, comma-separated, of `chromium`, `firefox` and `webkit`; a missing one fails, saying how to install it | Yes, once in each of the three |
| Live | `live` | `PLATOON_HARNESS_LIVE=1` and the harnesses signed in as you usually are; the examples' also `pi`, and `PLATOON_HARNESS_LIVE_MODEL`, `OPENAI_BASE_URL` and `OPENAI_API_KEY` | Never |

```bash
uv run pytest -q -m slow
uv run playwright install chromium-headless-shell
uv run pytest -q -m e2e
PLATOON_HARNESS_LIVE=1 uv run pytest -q -m live tests/live/test_claude.py
```

Playwright's WebKit needs glibc 2.38 or later. A live test spends model calls on your logins, and fails a run that took
more model calls or minutes than its test's docstring states, so run only the ones your change needs, and say in the pull
request which ran and what they spent: a skipped live test is not a passing one. Every run ends by listing each skipped
test with its reason; the bubblewrap tests skip where `bwrap` cannot confine, and fail instead under
`PLATOON_HARNESS_REQUIRE_BWRAP=1`, as CI's test job sets it. While you work, run what you touch, such as
`uv run pytest -q tests/unit/primitives`.

## Lint, format and type-check

`.pre-commit-config.yaml` defines four hooks: `ruff-check` and `ruff-format`, configured in `pyproject.toml`; `ty`,
configured in `ty.toml`; and `conventional-pre-commit`, which checks each commit message. CI's `lint` job runs every hook
of the `pre-commit` stage on every file:

```bash
uv run pre-commit run --all-files --show-diff-on-failure
```

To run the checks one at a time, without the hooks' fixes:

```bash
uv run ruff check . && uv run ruff format --check .
uv run ty check
```

When a hook fixes a file during `git commit`, the commit stops; add the fixed files and commit again. The ruff hook's
`rev` is the ruff the `dev` group pins, which a test holds equal, so change both together.

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

The `commit-msg` hook checks the form of each message, but not the summary's case, which reviewers and the title check
do. To check a message without committing, save it to a file and run the hook on it:

```bash
uv run pre-commit run conventional-pre-commit --hook-stage commit-msg --commit-msg-filename message.txt
```

**Pull request titles.** A pull request's title has the form of a commit subject, as maintainers squash-merge pull
requests and the title becomes the subject of the commit on `main`. CI's `pr-title` job checks it, and a single commit's
subject too, as GitHub suggests that for the squashed commit.

**What CI runs.** On each pull request, and each push to `main`:

| Job | Checks |
|---|---|
| `pr-title` | The title, and a single commit's subject, on pull requests only |
| `lint` | Every hook of the `pre-commit` stage, on every file, with `uv.lock` up to date |
| `test` | The fast tests, on Python 3.12 and 3.13, with bubblewrap able to confine and git 2.47 or later |
| `e2e` | The browser tests, once in each of Chromium, Firefox and WebKit |
| `build`, of the release workflow | The distribution built and checked, as [Releases](#releases) says |

The slow tests need harness binaries that CI does not have, so CI runs none of them but those of the installed wheels,
and it never runs the live ones.

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
page's form with no core edit ([architecture §17](docs/architecture.md#17-extensions-and-configuration)).
[examples/extension-package](examples/extension-package/README.md) is one, with an op, a view and a preset. Hold it to
what a core primitive keeps with `check_extension` from `platoon_harness.testing`.
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

An example is a folder of `examples/`, with a row in [examples/README.md](examples/README.md), and has:

- a `README.md` that states the goal, what it needs, the steps and what to expect, and only the files a person runs, no
  stand-in of a harness or a model among them;
- a team that runs on a real model the person names, through an auth profile of `OPENAI_BASE_URL` and
  `OPENAI_API_KEY`, on a copy of [the sample project](examples/sample-project/README.md), whose issues list names each
  job;
- a slow test in `tests/integration/test_examples.py` that runs its README's commands as shown against `FakeModel`,
  which plays each agent from `tests/integration/plays.py`, and a fast one of its copy, `team check` and `team show`;
- a live test in `tests/live/test_examples.py`, whose docstring states its budget: the model calls and minutes past which
  it fails a run, as no budget of the team's counts model calls;
- files that import nothing from the tests and reach the SDK by the names `tests/public_api.txt` lists alone;
- a cost its README quotes only from a run that was made.

## The docs' images

The terminal UI's images in `docs/assets` are copies of the snapshots `tests/unit/tui/test_snapshots.py` draws, held to
them byte for byte, and the page's, `web-chat.png` and `web-provenance.png`, are what `tests/e2e/test_page_images.py`
writes. The page's images, and the screenshots `RECORDED_SNAPSHOTS` names, show the mixed team's session as its live test
records it in the folder `RECORDED` names in `tests/recorded.py`: with every local path, the host, the user, the group,
the endpoint and the key replaced, refused while the privacy scan catches anything, and never from an endpoint on
loopback, where FakeModel serves. The other screenshots show scripted sessions.

To record it again, run the mixed team's live test alone, which may spend 50 model calls, with
`PLATOON_HARNESS_LIVE_MODEL`, `OPENAI_BASE_URL` and `OPENAI_API_KEY` set; it records only a run that passed each of its
checks. Then draw the images from it:

```bash
PLATOON_HARNESS_LIVE=1 PLATOON_HARNESS_RECORD=tests/fixtures/sessions/mixed-team uv run pytest -q -m live tests/live/test_examples.py -k mixed_team
uv run pytest -q tests/unit/tui/test_snapshots.py -k recorded --snapshot-update
PLATOON_HARNESS_IMAGES=docs/assets uv run pytest -q -m e2e tests/e2e/test_page_images.py
```

Copy each snapshot over its screenshot as `test_each_screenshot_the_docs_show_is_its_snapshot_byte_for_byte` says, and
say under each image what drew it, as `tests/unit/docs/test_images.py` holds: `recorded`, with the model, or `scripted`.
No test holds the page's images to what a browser draws, as that differs with the host's fonts. Read the recording and
each image before you commit them, as they are published with the repository.

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
     test holds to the version, and [Install](docs/getting-started/install.md).

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

Each step checks what an install from PyPI would get, on Python 3.12, the oldest the distribution names: a wheel built
from the sdist, so an sdist that leaves out a file the wheel needs fails; metadata and a description that render on PyPI;
the library imported alone and the command run with its `cli` extra, each in an environment of its own; and the
`openhands` extra resolved with `lmnr-claude-code-proxy` excluded, as [Install](docs/getting-started/install.md#openhands)
says. `tests/integration/test_installed.py` builds the wheel again and installs it as a person does, taking no network,
so uv's cache must hold what it installs, as the steps before it leave it; where it does not, it fails, saying so.

The job keeps `dist/` as an artifact of the run. On a tag pushed to this repository, and on no other event, the
`publish` job uploads it to PyPI with `pypa/gh-action-pypi-publish`, in the `pypi` environment. That job asks for an
OIDC token and nothing more, which PyPI trades for the right to upload, and runs no code of the repository.
