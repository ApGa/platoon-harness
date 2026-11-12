# RFC 0081: platoon-harness is one distribution, with the command line as its cli extra

| | |
|---|---|
| Status | Accepted, 2026-11-12 |
| Created | 2026-11-12 |
| Authors | Apurva Gandhi (`ApGa`) |
| Builds on | [`pyproject.toml`](../../pyproject.toml), [`launcher.py`](../../packages/cli/src/platoon_harness_cli/launcher.py), [RFC 0030](0030-openhands-is-an-extra-of-the-sdk.md) and [RFC 0072](0072-acp-agents-are-driven-by-a-first-party-extension-that-names-its-own-check.md) |
| Discussion | Decided by the maintainers on 2026-11-12, before the first release |
| Implementation | `build: Ship platoon-harness as one distribution with the command line as its cli extra` |

## Summary

platoon-harness ships as one distribution, `platoon-harness`. Its wheel holds two layers, the SDK, `platoon_harness`, and
the command line, `platoon_harness_cli`, built from the source trees they had. The library requires pydantic alone; the
`cli` extra adds what the command line needs, and the `openhands` extra is as it was. The `platoon-harness` command runs a
launcher that needs only the standard library, so without the `cli` extra it says what to install and exits 78.

## Motivation

The SDK and the command line were built as two distributions, `platoon-harness-sdk` and `platoon-harness-cli`, never
published, and the ACP driver a third. Publishing them would have needed a name on PyPI, a release tag and a publisher
each, and a person would have had to know which to install, where the name a person types is `platoon-harness`.

## Proposal

### 1. One distribution of two layers

`pyproject.toml` at the root builds one sdist and one wheel from `packages/sdk/src/platoon_harness` and
`packages/cli/src/platoon_harness_cli`, which hold no packaging of their own. The layers stay as they were: the SDK never
imports the command line or Textual, as the boundary tests check. `packages/sdk/src/platoon_harness/version.py` sets the
one version, and `platoon-harness --version` says it once. The ACP driver is in the SDK (RFC 0072).

### 2. The name a person installs is the name they import

`pip install platoon-harness` gives `import platoon_harness`. An extension requires `platoon-harness>=0.1,<0.2`, and
discovery checks that requirement against the release that runs, as it checked one on `platoon-harness-sdk`.

### 3. A light library

The base requires pydantic alone, so a library built on the SDK, such as a training system's bridge, installs no terminal
UI, web server or command-line parser:

| Install | Brings |
|---|---|
| `platoon-harness` | The SDK, and pydantic |
| `platoon-harness[cli]` | The command line besides: cyclopts, markdown-it-py, rich, swarmchat, textual and tomlkit |
| `platoon-harness[openhands]` | OpenHands' SDK and tools, as RFC 0030 has it |

### 4. A command that says what is missing

`platoon-harness` runs `platoon_harness_cli.launcher:main`, which imports only the standard library before the command
line. Where the installed metadata shows a distribution of the `cli` extra missing, it prints

```text
platoon-harness: the command line needs its extra: uv tool install "platoon-harness[cli]", or pip install "platoon-harness[cli]"
```

and exits 78, the code for a machine that cannot be used as it is.

What changes for users: the install commands above; `--version` and `doctor` print one version, and `doctor --json` gives
`version` in place of `versions`; an extension requires `platoon-harness`; and the OpenHands worker asks for
`platoon-harness[openhands]`.

## Alternatives

| Alternative | Why not |
|---|---|
| Keep `platoon-harness-sdk` and `platoon-harness-cli`, and add `platoon-harness` to install both | Three names, tags and publishers for what releases at one version |
| One distribution whose base brings the command line's dependencies | A library built on the SDK would install a terminal UI and a web server it never imports |
| The command pointing at the command line itself | Without the extra it fails on an import, with a traceback that does not say what to install |

## Consequences

- One name to install, one tag, `vX.Y.Z`, and one publisher.
- The SDK and the command line cannot release apart, which they never did.
- A checkout installs the project with its `cli` and `openhands` extras through the dev group, and
  `UV_NO_DEV=1 uv sync --extra cli` installs it without the group.

## Evidence

- `tests/unit/test_packaging.py`: one version, one distribution, the library on pydantic alone, the `cli` extra holding
  what the command line imports, and a launcher that needs only the standard library.
- `tests/unit/cli/test_launcher.py`, and `tests/integration/test_installed.py`, slow, on the built wheel: alone, with the
  `cli` extra, and as a tool.
- The release workflow's checks, which CONTRIBUTING shows under Releases.
