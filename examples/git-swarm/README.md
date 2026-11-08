# A GitSwarm population

**Goal:** run a population of workers on a model you name, each in a worktree of its own, from a Python script that owns
the session, on a feature the sample project asks for, and read back each worker's outcome and the nominations among
which you choose.

pi workers under the `git-swarm` preset, started by [`run.py`](run.py), a script that owns the session as `program:swarm`
and runs `population`, from `platoon_harness.patterns`, on it, in your copy of
[the sample project](../sample-project/README.md). The script starts four workers with one goal, the `--json` option
that issue 4 of its `ISSUES.md` asks for, at most two at once. Each works on a branch of its own, in a worktree of its
own, and comes to one outcome: it contributes commits, nominates one recorded commit in a message to `#nominations`, or
abstains. Anything else is invalid, and an end other than finishing is failed. A worker builds on a peer's commit by
checking out on its own branch the SHA that peer's outcome records. Once each worker has ended, the script records its
outcome on board `outcomes`, and once every worker has one, it closes the session and prints them. It reads out no
winner: choosing among the nominations is yours. This is the population that
[the topologies guide](../../docs/how-to/topologies.md#git-swarm) describes, under
[RFC 0070](../../docs/rfcs/0070-a-population-gives-each-worker-one-outcome-which-its-program-records.md), a draft.

**Prerequisites:**

- a checkout of this repository with its packages installed, as [the README](../../README.md#install) says, and its
  environment active, as [your first session](../../docs/getting-started/first-session.md#1-run-a-team-on-your-model)
  has it;
- `pi` on your PATH, which needs no login here;
- a model at an endpoint that speaks OpenAI's Chat Completions, and a key for it, in `OPENAI_BASE_URL` and
  `OPENAI_API_KEY`, as [the mixed team](../mixed-team/README.md#1-check-it) names them;
- git that knows your name and email, as `git config user.name` and `git config user.email` say, since the workers
  commit as you, and `python3` 3.9 or later on your PATH, which they run the tests on.

The example has two files:

| File | What it is |
|---|---|
| [`team.toml`](team.toml) | The team: one role, `worker`, on pi in a worktree of its own, of which the session starts none, `count = 0`, as the script starts each; the `git-swarm` preset, with at most two workers at once; an auth profile, `provider`, that hands each worker's harness your endpoint and key; and a budget of 16 turns and 25 minutes, so a runaway stops itself. The workers allow their approvals, as each of their commands that writes, their commits among them, asks for one |
| [`run.py`](run.py) | The script: the team, which it trusts, with any `--set` lines, started as `program:swarm`, a population of four workers with one goal, the session closed, and each worker's outcome printed |

## 1. Check it

Make a copy of the sample project, as a repository of its own, and work there, with the checkout's environment active:

```console
$ source path/to/platoon-harness/.venv/bin/activate
$ cp -r path/to/platoon-harness/examples/sample-project tally
$ cd tally
$ git init -q && git add -A && git commit -qm "Start from the sample project"
```

Check the team with a `--set` line that names your model, MODEL as your endpoint names it:

```console
$ platoon-harness team check path/to/platoon-harness/examples/git-swarm/team.toml --trust \
    --set 'roles.worker.model = "MODEL"'
$ platoon-harness team show path/to/platoon-harness/examples/git-swarm/team.toml --trust
```

`--trust` says you trust the team file's auth profile, which hands your key to each worker's harness: without it, each
command that reads the file refuses it, with exit 78. `team check` says `no problems`, before any cost, and `team show`
says in sentences what the team allows:

```text
Workers (pi, own worktrees) may message no one.
Workers post to topic `nominations`; everyone reads it. Readers fetch it when they choose. Everyone shares board `inflight`. The program writes board `outcomes`; everyone reads it. Limits: live 2. Closes when the program closes it.
```

The session closes when its program closes it, so `platoon-harness run` and the terminal UI refuse this team, naming
the script way: here the program is `run.py`. Each worker commits, and nobody is there to answer an approval, so the team
file gives the workers `approvals = "allow"`: they run commands, git among them, as you, unasked. A worktree is not a
sandbox: what runs there can reach anything you can.

## 2. Run it

```console
$ python path/to/platoon-harness/examples/git-swarm/run.py --set 'roles.worker.model = "MODEL"'
```

The session's runtime runs in the script's process. The script holds `program:swarm`, so the session issues no owner
credential: a client that attaches only reads. It ends with a line with the session's name and how it ended, as in
`session 20261108-110931-468d3828: settled`, then a line for each worker with its outcome as `outcomes` records it: the
outcome, then the commit's short SHA and subject for a contribution or a nomination, or the worker's own words for an
abstention, such as `worker-1: contribute: 6faf7ad0b9f8 Add --json`. The session's name and each SHA differ from run to
run, and each outcome is what that worker's model chose. Each waits for the outcome it rests on. Each worker works on the
branch `platoon-harness/<session>/<worker>`, in a worktree in the session's folder, made at your HEAD: nothing of it is
in your checkout, and the branches stay in your repository.

If the script dies, its session stops with it, resumable: `population` keeps nothing, so a script that runs it again on
the session, with `Session.resume` in place of `Session.start`, starts no worker and records no outcome twice, as
[Run a program from Python](../../docs/how-to/topologies.md#run-a-program-from-python) says, and
`platoon-harness session resume`, a person's, refuses the session, naming this way.

A real model chooses its own outcome: whether a worker builds on a peer's commit, nominates or abstains, how often one
does something else, which is invalid, and how many turns each takes. A live run of this example is held to 60 model
calls and 25 minutes, by `tests/live/test_examples.py`, which has not run yet: [docs/STATUS.md](../../docs/STATUS.md)
says what has run live. `tests/integration/test_examples.py` runs the commands on this page as shown, on the real `pi`
against FakeModel, a loopback model that replies from a script, so the harness, the tools, git and the team file are real
and only the model is scripted: there, one worker contributes `--json`, a second builds a test on it by the SHA its
outcome records, a third nominates that commit and the fourth abstains.

## 3. Read it back, and choose

NAME is the session's name, from the first line the script printed:

```console
$ platoon-harness board query NAME --board outcomes
$ platoon-harness message read NAME --channel '#nominations'
$ platoon-harness lineage NAME --ref channel/nominations@1
```

`board query` prints each worker's entry on `outcomes`, which only the program writes, and of which the board takes no
second, with the outcome and, for a contribution or a nomination, the commit's whole `sha` in its `fields`.
`message read` prints each nomination, and `lineage` what the first cites: under `declared`, the commit, who made it, and
whether the nominator was shown it, `seen` when it read the commit through `repo.commit`. Choosing among the nominations
is yours. Each commit is in your repository, so `git show SHA` reads one, and `git merge SHA` takes it onto your branch.
