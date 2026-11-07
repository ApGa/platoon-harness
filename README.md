# platoon-harness

Run the agent harnesses you already use, such as Claude Code, Codex, pi and OpenHands, as one team, in durable sessions
you can watch, steer, resume and read back.

Bring the agent harnesses you already use, such as Claude Code, Codex and pi, together as a team: durable multi-agent
sessions with explicit coordination primitives, a terminal UI, a browser client, and honest provenance.

What it gives you:

- **The harnesses you already use, on your own logins.** Claude Code, Codex and pi run as you installed them, signed in
  as you usually are, and nothing here reads, copies or stores their credentials
  ([compatibility](docs/reference/compatibility.md#7-auth-and-terms)). OpenHands keeps no login, so its role names an
  auth profile: the variables its key is in, and never a value.
- **Durable sessions.** A session is a folder holding one journal. Everything that happens is an event in it, so a
  session can be watched from several clients at once, stopped, resumed, and read back later.
- **Coordination you can name.** The runtime gives each agent tools to message, start agents, claim tasks, post to
  boards and wait, under a topology you choose, which says who may reach whom. Presets such as `manager-worker`, `tree`
  and `mesh` write the common ones, an approval is resolved once, by a person or a stated policy, and a budget stops a
  runaway ([topologies](docs/how-to/topologies.md)).
- **Four ways in.** `platoon-harness` alone opens the terminal UI, `platoon-harness web` serves SwarmChat's page over a
  session's journal, the headless commands suit scripts and CI, and the Python SDK is what all of them are built on
  ([terminal UI](docs/how-to/tui.md), [browser](docs/how-to/web.md), [headless](docs/how-to/headless.md)).
- **Workspaces.** An agent works in the session's checkout, in a git worktree of its own or in a snapshot. After each
  turn the runtime looks at what the agent left, and a look changes no ref, index or file: the runtime never merges,
  rebases or moves a branch an agent has. `isolated`, a confined snapshot, is experimental
  ([workspaces](docs/how-to/workspaces.md)).
- **Provenance.** What reached each agent, what it rests on, whose work an outcome reaches, and credit beside the
  journal, each row its named producer's statement ([provenance](docs/how-to/provenance.md)).
- **A training contract.** The one contract a training system builds on, whose SDK half is tested. Platoon's own
  extension, `platoon-teams`, builds on it in a fork of Platoon's repository, not released, and no team has trained on a
  GPU yet ([training](docs/extending/training.md)).

## Concepts

Nine everyday words name what a user meets ([architecture section 2](docs/architecture.md#2-vocabulary)):

| Word | Meaning |
|---|---|
| **Session** | The durable thing you start, attach to, resume and export: one folder, one journal. `run` is only a verb. |
| **Agent** | One participant with its own identity and history, driven through one harness. Retiring it leaves the live team, never the journal. |
| **Role** | A template for agents: harness, model, instructions, workspace, what it may spawn. |
| **Harness** | An existing agent program such as `claude`, `codex` or `pi`. |
| **Turn** | One stretch of harness work, from the input that started it until the harness stops. The unit of waking, cost and exposure. |
| **Channel** | A durable named place with readers and writers, of one kind: `inbox`, `topic`, `queue` or `board`. |
| **Team** | Roles plus a topology, as a file or a Python object. It says what may happen, never what happens next. |
| **Topology** | Who may reach whom, as grants over relations such as `parent` and `children` that stay true as agents come and go. |
| **Approval** | A durable decision a harness is waiting on, resolved once by a human or a stated policy. |

## Install

Nothing is published to PyPI yet, so install from a checkout. You need Linux, Python 3.12 or later,
[uv](https://docs.astral.sh/uv/), git 2.47 or later, and the harnesses you want on your PATH (`claude`, `codex`, `pi`),
signed in as you usually are.

```console
$ git clone https://github.com/ApGa/platoon-harness.git && cd platoon-harness
$ uv sync
```

`uv sync` installs both packages with the `dev` group, which holds the tests' tools and the SDK's `openhands` extra. To
leave the group out, set `UV_NO_DEV=1` for `uv sync` and for every `uv run` after it, as `uv run` installs the group
otherwise. [Install](docs/getting-started/install.md) has the rest: OpenHands, and what `doctor` says.

## Quickstart

[Your first session](docs/getting-started/first-session.md) takes these steps one at a time, with what to expect.

**1. See a team work, with no keys.** In [the mixed team](examples/mixed-team/README.md), a lead puts a task on a queue
and starts a worker, which writes a note on a board and reports back. Scripted stand-ins play both, with no model at
all:

```console
$ PYTHONPATH=examples/mixed-team uv run platoon-harness run --team examples/mixed-team/team.toml \
    --prompt-file examples/mixed-team/job.md --set 'roles.lead.harness = "stand_ins:lead"' \
    --set 'roles.worker.harness = "stand_ins:worker"' --name dns
$ uv run platoon-harness session list
$ uv run platoon-harness task list dns --queue tasks
$ uv run platoon-harness board get dns --board notes --name risks
$ uv run platoon-harness uses dns --ref board/notes/risks@1
```

`run` prints a line per event as the session journals it, and exits 0 once the session has settled. The commands after
it read the closed session: the sessions there are, the task on the queue, the note on the board, and what cites the
note.

**2. Run your own harnesses.** Agents work where you start a session, so do this in a repository of yours, with the
checkout's environment active:

```console
$ source path/to/platoon-harness/.venv/bin/activate
$ platoon-harness doctor     # what this machine has
$ platoon-harness init       # a starter platoon-harness.toml from the harnesses it found
$ platoon-harness            # the terminal UI
```

`doctor` says `usable` when this machine can run a session. With the `dev` group it says so even with no harness on
PATH, as the group installs the SDK's `openhands` extra and OpenHands runs on the runtime's own interpreter. Without the
group and with no harness on PATH, it says `not usable`.

**3. Watch and steer.** While a session runs, from another shell in the checkout:

```console
$ uv run platoon-harness attach dns    # the terminal UI, as a guest of the running session
$ uv run platoon-harness web dns       # SwarmChat's page; open the control link it prints
```

A message from either goes to whoever you address, and a person's message steers. On step 1's `dns`, which has closed,
both show its history read-only, as neither starts or resumes a session, which can spend money.
[The terminal UI](docs/how-to/tui.md) and [the browser](docs/how-to/web.md) say what each shows and how to act.

![The terminal UI on a closed session: a lead and the worker it spawned in the navigator, the lead's transcript beside them, and the composer below](docs/assets/tui-wide.svg)

*The terminal UI on scripted harnesses, as its snapshot test draws it: a lead that spawned a worker, read back as history.*

**4. Read it back.** `uses` says what cites an event, and `contributors` whose work the record ties to one, on a live
session or a closed one. The mixed team's [What to look at](examples/mixed-team/README.md#3-what-to-look-at) walks from
the worker's note to the lead's answer, and [provenance](docs/how-to/provenance.md) says how to read each answer.

## Python SDK

The command line and both clients are built on the SDK, `platoon_harness`, and a script can use it alone. This one runs
a team of one-shot command-line agents with no key:

```python
# examples/sdk-script/run.py (abridged)
from platoon_harness import Role, Session, Team
from platoon_harness.team import Command

COUNT = Command(command=[sys.executable, "-c", "import sys; print(len(sys.argv[1].split()), 'words')", "{goal}"])
TEAM = Team(roles={"counter": Role(harness=COUNT, count=0)})


async def main() -> None:
    async with Session.start(TEAM) as session:
        for number, goal in enumerate(GOALS, 1):
            await session.spawn(f"counter-{number}", "counter", goal)
        ending = await session.settled(timeout="30s")
        said = [f"{event.agent}: {event.gist}" async for event in session.events() if event.type == "item.recorded"]
```

[examples/sdk-script](examples/sdk-script/README.md) runs it and reads it back.

## Status

Milestones 0 (inspect and decide) and 1 (a working vertical slice) are done, 1 on Linux: a team of real harnesses,
started, watched and steered from the terminal UI, the browser or the command line. Milestones 2 (dependable
coordination) and 3 (training with Platoon) are in progress: the SDK's half of the training contract is tested, and the
bridge lives on a branch of a fork of Platoon's repository. Milestone 4 (production polish) is planned. Nothing has run
on macOS. [docs/STATUS.md](docs/STATUS.md) says what is implemented, what is tested and how, and what is planned.
Nothing is published to PyPI yet.

## Documentation

- [docs/README.md](docs/README.md): the table of contents, every page of the docs by kind: getting started, tutorials,
  how-to guides, extending, the reference, the architecture and the RFCs.
- [examples/](examples/): runnable examples, each with a README, and each runnable with no keys.
- [docs/architecture.md](docs/architecture.md): the design of record, and [docs/rfcs/](docs/rfcs/README.md) for why each
  decision was made.
- [docs/STATUS.md](docs/STATUS.md): what is implemented, what is tested and how, and what is planned.
- [CHANGELOG.md](CHANGELOG.md): what changed.

## Repository layout

| Path | Contents |
|---|---|
| `packages/sdk/` | `platoon-harness-sdk`, the Python SDK, `platoon_harness`: the kernel, the primitives, the runtime, the topology, the tool plane, the drivers and the testing kit |
| `packages/cli/` | `platoon-harness-cli`, the `platoon-harness` command: the command line, the terminal UI and the server of SwarmChat's page |
| `examples/` | runnable examples, each run with no keys by `tests/integration/test_examples.py` |
| `tests/` | `unit/` and `integration/`, on a CPU, with the slow ones marked; `e2e/`, the browser tests; `live/`, on real models and logins; `conformance/`, the conformance suite run on every driver |
| `docs/` | the documentation, which [docs/README.md](docs/README.md) lists |
| `pyproject.toml`, `uv.lock` | the uv workspace of the two packages, and the versions every checkout installs |

## Contributing

[CONTRIBUTING.md](CONTRIBUTING.md) says how to set up a checkout, run the tests and propose a change, and
[AGENTS.md](AGENTS.md) holds the rules every change follows, human or agent. Some changes start as an RFC: see
[when to write an RFC](docs/rfcs/README.md#when-to-write-an-rfc).

## License

MIT; see [LICENSE](LICENSE). `platoon-harness web` serves SwarmChat 0.1.0's page from the installed package, under
SwarmChat's MIT license (© The SwarmChat Authors); it is not vendored.
