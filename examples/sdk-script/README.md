# A headless script

**Goal:** run a team from a Python script on the SDK alone, wait for it to settle, and read back what each agent said,
with no key and no model.

**Prerequisites:** a checkout of this repository with its packages installed, by `uv sync` or `uv sync --no-dev`. The
script imports only `platoon_harness`, the SDK, and needs no harness on `PATH`: its one role runs a Python one-liner.

| File | What it is |
|---|---|
| [`run.py`](run.py) | The script: a team of one role on a command, two agents spawned with a goal each, the session waited on until it settles, and what each said read from the journal |

## 1. Run it

From the root of the checkout:

```console
$ uv run python examples/sdk-script/run.py
```

Expected output, where the session's name differs from run to run:

```text
session 20261107-075705-a6e898c9: settled
counter-1: 6 words
counter-2: 4 words
```

## 2. Read the script

[`run.py`](run.py) has six parts:

- **A one-shot harness.** `Command(command=[...])` is a role's harness given as a command line, which the `exec` driver
  runs once per agent, with the agent's goal in place of `{goal}`. The process is the agent's one turn: its stdout is the
  message, and its exit ends the turn and the agent. Any command-line agent that takes a task and exits goes here the same
  way: see [A one-shot CLI](../../docs/extending/drivers.md#a-one-shot-cli-exec).
- **A team.** One role, `counter`, with `count=0`, so the session starts none of its agents: a one-shot harness needs a
  goal to start, so the script spawns each with one.
- **A session.** `Session.start(TEAM)` starts the team, and the script owns the session until its `async with` block
  ends. The session lives under the root where every session does, so the command line finds it too.
- **Agents.** `session.spawn(name, role, goal)` starts an agent in a role with a goal.
- **Settling.** `session.settled(timeout="30s")` waits until the session is done and says what it came to: `settled`
  here, or `timed_out` past the timeout.
- **The journal.** `session.events()` reads each event the session journaled. What an agent says is an
  `item.recorded` event, and its `gist` is the words.

## 3. Read it back

The session stays where it was journaled, closed, and the command line reads it as it reads any other:

```console
$ uv run platoon-harness session list
$ uv run platoon-harness events NAME
```

NAME is the session's name, from the first line the script printed. [The headless quickstart](../../docs/how-to/headless.md)
runs teams of the harnesses you use from a shell, and [Topologies](../../docs/how-to/topologies.md) builds teams in Python.
