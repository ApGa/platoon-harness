# platoon-harness-sdk

The Python SDK of platoon-harness: run the agent harnesses you already use, such as Claude Code, Codex, pi and
OpenHands, as one team, in durable sessions you can watch, steer, resume and read back.

Nothing is published to PyPI yet. From a checkout of [the repository](https://github.com/ApGa/platoon-harness),
`uv sync` installs it with the command line. [The project's README](https://github.com/ApGa/platoon-harness#readme) says
what it gives you and how to start, and [its documentation](https://github.com/ApGa/platoon-harness/tree/main/docs) the
rest.

Its `openhands` extra pins OpenHands' SDK and tools. `openhands-sdk` requires `lmnr`, which requires
`lmnr-claude-code-proxy`, a binary under Laminar's own terms. A checkout's lock leaves it out, but installed from this
package's wheel, the extra brings `lmnr-claude-code-proxy` unless you exclude it, as uv's `exclude-dependencies` setting
or `uv pip install --excludes` does.
