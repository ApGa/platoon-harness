# platoon-harness

Run the agent harnesses you already use, such as Claude Code, Codex, pi and OpenHands, as one team, in durable sessions
you can watch, steer, resume and read back.

![The terminal UI on the mixed team's closed session: the pi lead and the OpenHands worker it spawned in the navigator, the lead's transcript beside them, and the composer below](docs/assets/tui-wide.svg)

*The terminal UI on the mixed team's session, as a live run on DeepSeek V4.1 Flash recorded it: a pi lead and the
OpenHands worker it spawned.*

- **The harnesses you already use, on your own logins.** Claude Code, Codex and pi run as you installed them, signed in
  as you usually are, and nothing here reads, copies or stores their credentials
  ([compatibility](docs/reference/compatibility.md#7-auth-and-terms)). OpenHands keeps no login, so its role names the
  variables its key is in, never a value.
- **Durable sessions.** A session is a folder holding one journal, so it can be watched from several clients at once,
  stopped, resumed, and read back later.
- **Coordination you name.** Each agent gets tools to message, start agents, claim tasks, post to boards and wait, under
  a topology that says who may reach whom: presets such as `manager-worker`, `tree` and `mesh` write the common ones,
  an approval is resolved once, by a person or a stated policy, and a budget stops a runaway
  ([topologies](docs/how-to/topologies.md)).
- **Four ways in.** The terminal UI, a browser page, headless commands for scripts and CI, and the Python SDK they are
  all built on ([terminal UI](docs/how-to/tui.md), [browser](docs/how-to/web.md), [headless](docs/how-to/headless.md)).
- **Provenance.** What reached each agent, what each write rests on, and whose work an outcome reaches, read from the
  record ([provenance](docs/how-to/provenance.md)). The SDK's half of a training contract is tested; no released trainer
  uses it yet ([training](docs/extending/training.md)).

Agents run commands as you: a worktree or a snapshot is not a sandbox, and the confined `isolated` workspace is
experimental ([workspaces](docs/how-to/workspaces.md), [security](docs/security.md)).

## Install

You need Linux, Python 3.12 or later, [uv](https://docs.astral.sh/uv/) (or pip), git, and the harnesses you use on your
PATH, signed in as you usually are. Then:

```console
$ uv tool install "platoon-harness[cli]"
```

`pip install platoon-harness` installs the SDK alone, whose `platoon-harness` command only says how to install the `cli`
extra. [Install](docs/getting-started/install.md) says where to get each harness, how to add OpenHands, and what
`doctor` says.

## Quickstart

Agents work where you start a session, so start one in a repository of yours:

```console
$ platoon-harness doctor     # what this machine has
$ platoon-harness init       # a starter platoon-harness.toml from the harnesses it found
$ platoon-harness            # the terminal UI, where n starts a session from it
```

The agents spend model calls on your own logins: give the team a [budget](docs/reference/team-file.md#budget) to stop a
runaway. [Your first session](docs/getting-started/first-session.md) runs a team of pi and OpenHands on any
OpenAI-compatible model, one step at a time.

## Python

The command line and both clients are built on the SDK, `platoon_harness`, and a script can use it alone. This one runs
a team of two OpenHands agents on a model you name, each fixing an issue of the sample project in a worktree of its own:

```python
# examples/sdk-script/run.py (abridged)
from platoon_harness import Role, Session, Team
from platoon_harness.team import AuthProfile, Budget

PROVIDER = AuthProfile(env=("OPENAI_BASE_URL", "OPENAI_API_KEY"))


def team(model: str) -> Team:
    fixer = Role(harness="openhands", model=model, auth="provider", workspace="worktree", approvals="allow", count=0)
    return Team(roles={"fixer": fixer}, auth={"provider": PROVIDER}, budget=Budget(turns=8, wall="15m"))


async def main(model: str) -> None:
    async with Session.start(team(model)) as session:
        for name, goal in GOALS.items():
            await session.spawn(name, "fixer", goal)
        ending = await session.settled(timeout="15m")
```

[examples/sdk-script](examples/sdk-script/README.md) runs it and reads it back.

## Status

Alpha, on Linux alone: nothing has run on macOS. Below 1.0 a minor release may change the Python API, the team file or
the command line, as [CHANGELOG](CHANGELOG.md) says. [STATUS](docs/STATUS.md) lists what is implemented, tested and
experimental.

## Learn more

- [The documentation](docs/README.md): every page, from getting started to the design.
- [The examples](examples/README.md): teams at work on a sample project, each on a model you name.
- [STATUS](docs/STATUS.md) and [CHANGELOG](CHANGELOG.md): where each capability stands, and what each release changed.
- [CONTRIBUTING](CONTRIBUTING.md): how to set up a checkout, run the tests and propose a change. Questions and bugs go to
  [the issues](https://github.com/ApGa/platoon-harness/issues).
- [Security](docs/security.md): what is protected and what is not, and [SECURITY.md](SECURITY.md): how to report a
  vulnerability privately.

## License

MIT; see [LICENSE](LICENSE). `platoon-harness web` serves SwarmChat 0.1.0's page from the installed package, under
SwarmChat's MIT license (© The SwarmChat Authors); it is not vendored. The terminal UI's agents are drawn from the icon of
[Platoon](https://github.com/ApGa/platoon) (MIT, © Apurva Gandhi). The optional `openhands` extra brings
`lmnr-claude-code-proxy`, a binary under Laminar's own terms, unless you exclude it, as
[Install](docs/getting-started/install.md#openhands) says.
