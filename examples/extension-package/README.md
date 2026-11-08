# A sample extension package

**Goal:** add an op, a view and a preset to platoon-harness from a package of your own, with no core edit: install it
beside platoon-harness, where it activates nothing until a team names it, and cast its vote from the SDK, from an agent
through MCP or `ph`, and from the terminal's palette and the page's form.

**Prerequisites:** a checkout of this repository with its packages installed, by `uv sync`, as
[Install](../../docs/getting-started/install.md#install-from-a-checkout) says. The package needs no harness, key or model.

| File | What it is |
|---|---|
| [`pyproject.toml`](pyproject.toml) | The distribution, `ballot`, its requirement on the SDK, and the entry point under `platoon_harness.extensions` by which a team names it |
| [`src/ballot/__init__.py`](src/ballot/__init__.py) | The extension: `ballot.cast`, the op; `Votes`, the view; `pair_review`, the preset |

## 1. Read the extension

[`src/ballot/__init__.py`](src/ballot/__init__.py) has four parts:

- **The op.** `ballot.cast` casts a vote, yes or no, on an agent's work. It records `ballot.voted` on that agent's own
  stream, `agent/<name>`, with a gist that says the vote, so a client that shows the agent draws it with no code of its
  own. It is refused `not_found` where there is no such agent, and `conflict` for a second vote on the same work by the
  same voter. `tool=True` makes it a tool for an agent whose grants reach it, and its docstring is its description
  wherever it is offered.
- **The view.** `Votes` folds each `ballot.voted` into its table, `v_votes`, which the op reads to refuse a second vote.
  A view is rebuilt from the journal to the same contents, so it keeps nothing the journal does not.
- **The preset.** `pair_review(author, reviewer)` returns a topology fragment: the two roles may message each other, for
  at most 8 hops, and a grant lets the reviewer vote on the work of the author's agents. A team file uses it as the table
  `[topology.pair-review]`.
- **The extension.** `Extension("ballot", ops=[cast], views=[Votes], presets=[pair_review])`. Its name is its ops'
  namespace. It imports only the kernel's public names, and `Topology`, which a preset returns.

## 2. Install it

From the root of the checkout:

```console
$ uv pip install examples/extension-package
$ uv run platoon-harness extension list
```

`uv pip install` builds the package's wheel and installs it in the checkout's environment. `extension list` reads each
installed driver and extension from metadata alone, importing none, and names this one among them:

```text
extension  ballot       ballot 0.1.0
```

Installing activates nothing: no session loads `ballot` until its team names it. Where two installed distributions each
register an extension called `ballot`, a team that names `ballot` is refused before either is imported, and one that
names `ballot@0.1.0` loads this one alone.

## 3. Name it in a team

A team file, `team.toml`, that names it and uses its preset:

```toml
extensions = ["ballot"]

[roles.author]
harness = "codex"

[roles.reviewer]
harness = "claude"

[topology.pair-review]
author = "author"
reviewer = "reviewer"
```

`uv run platoon-harness team show team.toml` says what it allows:

```text
author (codex) may message reviewer. reviewer (claude) may message author.
Limits: hops 8. role:reviewer may ballot.cast on agent/{role:author}. Closes when the session settles.
```

## 4. Cast a vote

In a session of that team, a vote is cast from each surface, and none of them has code for it:

- **The SDK.** `await session.submit("ballot.cast", agent="@author", choice="yes")` casts yours.
- **An agent.** The reviewer's harness is shown `ballot_cast` among our MCP tools, and its shell runs
  `ph ballot.cast --agent @author --choice yes`.
- **The terminal UI.** The palette offers `ballot cast`, worded by the op's docstring, and runs it through a form made
  from its schema. It never asks first, as what is asked about first is the command line's list of its own ops.
- **The page.** Commands offers the same form.

Each vote is drawn by its gist, `a vote on @author's work: yes`: in the author's transcript in the terminal, and in its
event's Provenance pane in the page. `platoon-harness events` reads each one back. The command line has no command for an
extension's op yet, as it makes its commands from the SDK's own ops before any session exists.

## 5. Check it

`check_extension`, from `platoon_harness.testing`, holds an extension to what a core primitive keeps to, every failure at
once: see [Extensions](../../docs/extending/drivers.md#extensions). This one passes, and the result names what no check
runs, its preset: nothing in it says the topology `pair_review` returns is valid.

## How the tests hold it

[`tests/integration/test_installed_extensions.py`](../../tests/integration/test_installed_extensions.py) builds it as a
wheel and installs it in a fresh environment beside a rival that registers an extension of the same name. There, it
activates nothing until a team names it, a team that names `ballot` is refused before either is imported, its vote is
cast through the SDK, MCP and `ph` and read back by `platoon-harness events`, `extension list` names it from metadata,
and it passes `check_extension`.

[`tests/unit/tui/test_sample_extension.py`](../../tests/unit/tui/test_sample_extension.py) and
[`tests/e2e/test_extension.py`](../../tests/e2e/test_extension.py) cast its vote from the palette and from the page's
form, and find it drawn: in the transcript, and in the Provenance pane. They load it from its source, as the checkout's
environment does not install it.
