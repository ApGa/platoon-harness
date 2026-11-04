# platoon-harness-openhands

OpenHands as a platoon-harness harness. `platoon-harness-openhands` is a wire worker: one process per agent, driving one
conversation of the OpenHands SDK through `arun()`, and speaking the driver protocol on stdio. A team names it as it names any
harness:

```toml
[roles.worker]
harness = "openhands"
model = "gpt-5.4"
auth = "openai"

[auth.openai]
env = ["OPENAI_API_KEY"]
```

## Install it as a tool of its own

The OpenHands SDK pins its dependencies tightly enough that it shares an environment with nothing else, so the worker lives in
one of its own, apart from the SDK and the command line, which never import it. The runtime finds it on `PATH`:

```console
$ uv tool install platoon-harness-openhands
$ platoon-harness doctor
openhands  1.59.0, login unknown
```

It pins `openhands-sdk` and `openhands-tools` at 1.59.0 exactly, as the SDK moves fast, and a version it was not tested on is no
version it claims.

**A proprietary dependency.** `openhands-sdk` requires `lmnr`, which requires `lmnr-claude-code-proxy`, a binary distributed
under Laminar's own terms ("All rights reserved"). Nothing the worker runs imports it: only `lmnr`'s instrumentation of the Claude
Agent SDK does. To install without it:

```console
$ echo lmnr-claude-code-proxy > excludes.txt
$ uv tool install platoon-harness-openhands --excludes excludes.txt
```

The repository's own lock excludes it the same way, with `exclude-dependencies` in its workspace, and every test of the worker runs
without it. A tool install with `--excludes` has not run, as the distribution is not published yet, and a plain `pip install`
brings the proxy in.

## What a role gets

- **Sign-in:** a key alone. The role's auth profile names `OPENAI_API_KEY`, and `OPENAI_BASE_URL` for an endpoint other than
  OpenAI's. A role with none is refused, and so are a ChatGPT subscription and an OpenHands Cloud login, which need a person at a
  browser. The model is a Chat Completions model, sent as it is named.
- **Tools:** OpenHands' terminal, in a subprocess, its file editor and its task tracker, as its own CLI gives them, and ours,
  through the stdio shim. The model sees ours by their own names, as OpenHands shows a server's tools.
- **Instructions:** the project's, as OpenHands loads them, and ours after OpenHands' own system prompt.
- **Approvals:** every action asks the runtime but a call of our tools, and a lone `finish` or `think`, which OpenHands never asks
  about.
- **Its own agents:** off, unless the role says `allow_native_children = true`.

[docs/drivers.md](../../docs/drivers.md) states each rule, and [docs/compatibility.md](../../docs/compatibility.md) what ran.

## Tests

The worker's tests run the real SDK against a scripted model, in `tests/integration/test_openhands.py`, and skip unless the worker
is on `PATH`. To build its environment from the repository's lock:

```console
$ UV_PROJECT_ENVIRONMENT=/somewhere/openhands uv sync --package platoon-harness-openhands --frozen
$ PATH=/somewhere/openhands/bin:$PATH uv run pytest -m slow tests/integration/test_openhands.py
```

A skip is not a pass.
