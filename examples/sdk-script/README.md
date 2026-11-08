# A headless script

**Goal:** run a team from a Python script on the SDK alone, on a model you name, in which two agents each fix an issue
of the sample project on a branch of its own; wait for the session to settle, and read back what each reported.

**Prerequisites:**

- a checkout of this repository with its packages installed by `uv sync`, which brings the SDK's `openhands` extra, as
  [Install](../../docs/getting-started/install.md#install-from-a-checkout) says, and its environment active, as
  [your first session](../../docs/getting-started/first-session.md#1-run-a-team-on-your-model) has it. The script imports
  only `platoon_harness`, the SDK, and OpenHands runs on the SDK's own interpreter, so it needs no harness on PATH;
- a model at an endpoint that speaks OpenAI's Chat Completions, and a key for it, in `OPENAI_BASE_URL` and
  `OPENAI_API_KEY`, as [the mixed team](../mixed-team/README.md#1-check-it) names them;
- git that knows your name and email, as `git config user.name` and `git config user.email` say, since the agents
  commit as you, and `python3` 3.9 or later on your PATH, which they run the sample project's tests on.

| File | What it is |
|---|---|
| [`run.py`](run.py) | The script: a team of one role on OpenHands, built in Python, two agents spawned with a goal each, the session waited on until it settles, and what each reported |

## 1. Run it

Make a copy of [the sample project](../sample-project/README.md) as a repository of its own, and run the script there,
with MODEL the model as your endpoint names it:

```console
$ cp -r path/to/platoon-harness/examples/sample-project tally
$ cd tally
$ git init -q && git add -A && git commit -qm "Start from the sample project"
$ python path/to/platoon-harness/examples/sdk-script/run.py --model MODEL
```

The script prints a first line with the session's name and how it ended, `settled`, as in
`session 20261108-110931-468d3828: settled`, where the name differs from run to run, then a line for each agent, `cents`
and `comments`, with its report, in the model's own words. Each agent fixes its issue on the branch
`platoon-harness/<session>/<agent>`, in a worktree in the session's folder, made at your HEAD: nothing of it is in your
checkout, and the branches stay in your repository. Its approvals allow, as nobody is there to answer one, so it runs
commands as you, unasked, and a worktree is not a sandbox: what runs there can reach anything you can.

A live run of the script is held to 30 model calls and 15 minutes, by `tests/live/test_examples.py`, which has not run
yet: [docs/STATUS.md](../../docs/STATUS.md) says what has run live. `tests/integration/test_examples.py` runs the
commands on this page as shown, on OpenHands against FakeModel, a loopback model that replies from a script, so the
harness, the tools and the team are real and only the model is scripted.

## 2. Read the script

[`run.py`](run.py) has six parts:

- **An auth profile.** `AuthProfile(env=(...))` names the variables your endpoint and key are in, which a role's harness
  is handed. It holds names only: a value never enters a team. OpenHands reaches any endpoint that speaks Chat
  Completions this way, and pi and Codex take the same two variables.
- **A team.** One role, `fixer`, on `harness="openhands"` with your `model`, in a `worktree` of its own, and with
  `count=0`, so the session starts none of its agents: the script spawns each with a goal. `approvals="allow"` answers
  each approval, as nobody is there to, and a `Budget` of turns and wall time stops a runaway.
- **A session.** `Session.start(team)` starts the team where you run the script, and the script owns the session until
  its `async with` block ends. The session lives under the root where every session does, so the command line finds it
  too.
- **Agents.** `session.spawn(name, role, goal)` starts an agent in a role with a goal.
- **Settling.** `session.settled(timeout="15m")` waits until the session is done and returns its `Ending`: how it ended,
  `settled` here, or `timed_out` past the timeout.
- **The ending.** Each of `ending.agents` has its last `report`, whose `gist` is the words it finished with.

## 3. Read it back

The session stays where it was journaled, closed, and the command line reads it as it reads any other. NAME is the
session's name, from the first line the script printed:

```console
$ platoon-harness session list
$ platoon-harness events NAME
$ git log --oneline -1 platoon-harness/NAME/cents
```

`events` prints every event of the session, each agent's commands and our tools among them, and `git log` the commit
`cents` made on its branch. [The headless quickstart](../../docs/how-to/headless.md) runs teams from a shell, and
[Topologies](../../docs/how-to/topologies.md) builds teams in Python.
