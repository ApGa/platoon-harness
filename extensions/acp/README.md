# platoon-harness-acp

The ACP driver of platoon-harness: run an agent that speaks the Agent Client Protocol, such as OpenCode, as a harness of a
team.

It speaks ACP's protocol 1 on stdio over the SDK's own JSON-RPC peer, and requires nothing but the SDK. It is a
distribution of its own, released on a version and a tag of its own, and nothing is published to PyPI yet. From a
checkout of [the repository](https://github.com/ApGa/platoon-harness), `uv sync` installs it with the SDK and the command
line. [The driver guide](https://github.com/ApGa/platoon-harness/blob/main/docs/extending/drivers.md) says what it does,
and [STATUS](https://github.com/ApGa/platoon-harness/blob/main/docs/STATUS.md) what has run.
