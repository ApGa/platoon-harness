# A GitSwarm population

**Goal:** run a population of workers, each in a worktree of its own, from a Python script that owns the session, and read
back each worker's outcome and the nominations among which you choose, with no keys first.

Codex workers under the `git-swarm` preset, started by [`run.py`](run.py), a script that owns the session as
`program:swarm` and runs `population`, from `platoon_harness.patterns`, on it. The script starts four workers with one
goal, at most two at once. Each works on a branch of its own, in a worktree of its own, and comes to one outcome: it
contributes commits, nominates one recorded commit in a message to `#nominations`, or abstains. Anything else is invalid,
and an end other than finishing is failed. A worker builds on a peer's commit by checking out on its own branch the SHA
that peer's outcome records. Once each worker has ended, the script records its outcome on board `outcomes`, and once
every worker has one, it closes the session and prints them. It reads out no winner: choosing among the nominations is
yours. This is the population that [the topologies guide](../../docs/how-to/topologies.md#git-swarm) describes, under
[RFC 0070](../../docs/rfcs/0070-a-population-gives-each-worker-one-outcome-which-its-program-records.md), a draft.

**Prerequisites:**

- a checkout of this repository with its packages installed, as [the README](../../README.md#install) says, and its
  environment active, as [your first session](../../docs/getting-started/first-session.md#5-set-up-your-own-team) has
  it;
- a git repository with a commit, from which you run the script: each worker's branch is made there, so a scratch one
  does;
- git that knows your name and email, as `git config user.name` and `git config user.email` say, since the workers
  commit as you;
- for a run on real models, `codex` on your PATH and signed in as you usually are. The run with no keys needs neither.

The example has three files:

| File | What it is |
|---|---|
| [`team.toml`](team.toml) | The team: one role, `worker`, on Codex in a worktree of its own, of which the session starts none, `count = 0`, as the script starts each; the `git-swarm` preset, with at most two workers at once; and a budget of 16 turns and 15 minutes, so a runaway stops itself. The workers allow their approvals, as each git command of theirs that writes may ask for one |
| [`run.py`](run.py) | The script: the team, with any `--set` lines, started as `program:swarm`, a population of four workers with one goal, the session closed, and each worker's outcome printed |
| [`stand_ins.py`](stand_ins.py) | Scripted stand-ins for the workers, for the run with no keys |

## 1. Check it

From your repository, with the checkout's environment active:

```console
$ source path/to/platoon-harness/.venv/bin/activate
$ platoon-harness team check path/to/platoon-harness/examples/git-swarm/team.toml
$ platoon-harness team show path/to/platoon-harness/examples/git-swarm/team.toml
```

`team check` says `no problems`, before any cost. `team show` says in sentences what the team allows:

```text
Workers (codex, own worktrees) may message no one.
Workers post to topic `nominations`; everyone reads it. Readers fetch it when they choose. Everyone shares board `inflight`. The program writes board `outcomes`; everyone reads it. Limits: live 2. Closes when the program closes it.
```

The session closes when its program closes it, so `platoon-harness run` and the terminal UI refuse this team, naming
the script way: here the program is `run.py`. Codex keeps `.git` read-only under its sandbox, so each commit a worker
makes waits on an approval, which nobody is there to answer, and the team file gives the workers `approvals = "allow"`:
they run git as you, unasked. A worktree is not a sandbox: what runs there can reach anything you can.

## 2. Run it with no keys

Scripted stand-ins, in [stand_ins.py](stand_ins.py), do what the goal asks with git and no model at all:

```console
$ python path/to/platoon-harness/examples/git-swarm/run.py --set 'roles.worker.harness = "stand_ins:worker"'
```

`--set` puts the role on the stand-ins in place of Codex, as `platoon-harness run --set` does. The session's runtime runs
in the script's process, which finds the stand-ins beside the script. The script holds `program:swarm`, so the session
issues no owner credential: a client that attaches only reads. It ends with the session's name and how it ended, then
each worker's outcome as `outcomes` records it: the outcome, then the commit's short SHA and subject for a contribution
or a nomination, or the worker's own words. The session's name and each SHA differ from run to run:

```text
session 20261108-110931-468d3828: settled
worker-1: contribute: 6faf7ad0b9f8 Add fizzbuzz.py
worker-2: contribute: 5e5eefdd20da Test fizzbuzz.py
worker-3: nominate: 5e5eefdd20da Test fizzbuzz.py
worker-4: abstain: Nothing to add: worker-3 nominated a commit that does all the goal asks.
```

`worker-1` commits `fizzbuzz.py` with no test. `worker-2` builds on it: it checks out on its own branch the SHA that
`worker-1`'s outcome records, with `git reset --hard`, and commits a test on it. `worker-3` nominates that commit, in a
message to `#nominations` citing the ref that `repo.commit` gives for its SHA, and `worker-4` abstains. Each waits for the
outcome it rests on. Each worker works on the branch `platoon-harness/<session>/<worker>`, in a worktree in the session's
folder, made at your HEAD: nothing of it is in your checkout, and the branches stay in your repository.
`tests/integration/test_examples.py` runs the commands on this page as shown, in a repository of its own.

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
whether the nominator was shown it, `seen` here, as it read the commit through `repo.commit`. Choosing among the
nominations is yours. Each commit is in your repository, so `git show SHA` reads one, and `git merge SHA` takes it onto
your branch.

## 4. What a run with no keys cannot show

The stand-ins show the flow: a contribution, a second built on it by the SHA its outcome records, a nomination citing
that commit and an abstention, each recorded once by the program. They run in the runtime's own process, so a run with
no keys cannot show what Codex's sandbox holds a worker to: that its commits escalate past the sandbox and run once
`approvals = "allow"` allows them. Nor can it show what real models choose: whether a worker builds on a peer's commit,
nominates or abstains, how often one does something else, which is invalid, or how many turns and how long each takes.
Only a run on the real harnesses shows those.

## 5. Run it on your harnesses

The same command without the `--set` line, and with `--plan-login`, runs the workers on `codex`. `--plan-login` says you
mean to run several agents headless on your plan login at once, as `Session.start`'s `plan_login` does. If the script
dies, its session stops with it, resumable: `population` keeps nothing, so a script that runs it again on the session,
with `Session.resume` in place of `Session.start`, starts no worker and records no outcome twice, as
[Run a program from Python](../../docs/how-to/topologies.md#run-a-program-from-python) says. This population has not run
on real models yet: [docs/STATUS.md](../../docs/STATUS.md) says what has run live.
