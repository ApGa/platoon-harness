# A worktree team with a merge queue

**Goal:** run a team whose workers each commit on a branch of their own and hand it to one merger through a queue, and
read back what came of each merge, a conflict among them, with no keys first.

A Claude Code lead, two Codex workers each in a worktree of its own, and a Claude Code merger in a worktree of its own.
The lead starts the workers, `ada` and `bob`. Each adds a line naming itself at the end of `CONTRIBUTORS.md`, commits it
on its branch, adds a task to the queue `merges` naming that branch, and waits on the task. The merger claims each task,
merges the branch it names into its own with git, and completes the task with what came of that. Both workers add their
line at the same place, so the second merge stops on a conflict: the merger completes that task naming the path, and
its worker reads that from its task's result. The runtime never merges: the look after each turn records the merge
commit as the merger's, or the merge under way and its conflicted paths, which put the merger under Needs you. This is
the merge queue [the topologies guide](../../docs/how-to/topologies.md#merge-worktrees-through-a-queue) writes out, with
each role's instructions saying its part, as [RFC 0058](../../docs/rfcs/0058-a-merge-queue-is-a-queue-and-a-merger-written-out.md)
decided.

**Prerequisites:**

- a checkout of this repository with its packages installed, as [the README](../../README.md#install) says, and its
  environment active, as [your first session](../../docs/getting-started/first-session.md#5-set-up-your-own-team) has
  it;
- a git repository with a commit, from which you start the session: each agent's branch is made there, so a scratch
  one does;
- git that knows your name and email, as `git config user.name` and `git config user.email` say, since the workers
  commit and the merger merges as you;
- for a run on real models, `claude` and `codex` on your PATH and signed in as you usually are. The run with no keys
  needs neither.

The example has two files:

| File | What it is |
|---|---|
| [`team.toml`](team.toml) | The team: the `manager-worker` preset for the lead and its workers, a merger, the queue `merges` that workers add to and the merger claims from, each role's instructions, and a budget of 20 turns and 15 minutes, so a runaway stops itself. The workers and the merger allow their approvals, as each git command of theirs that writes may ask for one |
| [`job.md`](job.md) | What you ask: two workers, a line each in `CONTRIBUTORS.md` handed to the merger, and what came of each merge |

## 1. Check it

From your repository, with the checkout's environment active:

```console
$ source path/to/platoon-harness/.venv/bin/activate
$ platoon-harness team check path/to/platoon-harness/examples/worktree-merge-queue/team.toml --plan-login
$ platoon-harness team show path/to/platoon-harness/examples/worktree-merge-queue/team.toml
```

`team check` says `no problems`, before any cost. `team show` says in sentences what the team allows:

```text
lead (claude) may message its workers and you. merger (claude, own worktree) may message no one. Workers (codex, own worktrees) may message lead.
Workers add to queue `merges`; merger claims from it. lead adds to queue `tasks`; workers claim from it. Everyone shares board `notes`. Limits: hops 8. Closes when lead finishes.
```

Codex keeps `.git` read-only under its sandbox unless that is `danger-full-access`, so each commit a worker makes waits
on an approval, and the merger's git commands may ask too, as your Claude Code settings decide. An approval left to ask,
with nobody attached to answer, ends a headless run at once with exit 4. So the team file gives those two roles
`approvals = "allow"`, and they run git as you, unasked. A worktree is not a sandbox: what runs there can reach anything
you can. Without those two lines, `team check` warns of the commits and names the other choices.

## 2. Run it with no keys

The test suite's scripted stand-ins, in `tests/integration/scripts.py`, do what the job asks with git and no model at
all:

```console
$ PYTHONPATH=path/to/platoon-harness platoon-harness run \
    --team path/to/platoon-harness/examples/worktree-merge-queue/team.toml \
    --prompt-file path/to/platoon-harness/examples/worktree-merge-queue/job.md --name contributors \
    --set 'roles.lead.harness = "tests.integration.scripts:spawning_contributors"' \
    --set 'roles.worker.harness = "tests.integration.scripts:contributing"' \
    --set 'roles.merger.harness = "tests.integration.scripts:merging"'
```

It prints a line per event as the session journals it, and ends with how the session ended and each agent's last words.
Whichever worker adds its task first is merged, so `ada` and `bob` may be the other way round:

```text
settled, exit 0
  @ada             finished  merged platoon-harness/contributors/ada
  @bob             finished  conflict in CONTRIBUTORS.md: rebase platoon-harness/contributors/bob onto mine and add it again
  @lead            finished  Both workers have ended: each one's report says what came of its branch.
  @merger          waiting
```

The workers and the merger each work on the branch `platoon-harness/contributors/<agent>`, in a worktree in the
session's folder, made at your HEAD: nothing of it is in your checkout. `tests/integration/test_examples.py` runs the `platoon-harness` commands on
this page as shown, in a repository of its own. A session's name is taken once, so a second run needs another `--name`.

## 3. Read it back

```console
$ platoon-harness task list contributors --queue merges
$ platoon-harness session show contributors
```

`task list` prints each task on `merges` with its `result`, which is what the merger completed it with: that the branch
merged, or the paths in conflict, and each worker is told to finish with its task's result. `session show` names the
merger under needs you while its worktree rests on the conflict, with where to resolve it. That worktree stays, since its
agent has not ended; [When a workspace goes](../../docs/how-to/workspaces.md#when-a-workspace-goes) says when one is
removed, and how to let go of one that stays. In the terminal UI, `platoon-harness attach contributors` opens the same
session: `/review` lists what changed, grouped by workspace, and the conflict waits in the dock, saying where to resolve
it, as [Review what changed](../../docs/how-to/tui.md#review-what-changed) says, with a
[snapshot](../../docs/assets/tui-review.svg) of the list for one scripted harness's worktree.

## 4. Run it on your harnesses

The same command with neither `PYTHONPATH` nor the three `--set` lines, and with `--plan-login` and a new `--name`, runs
the team on `claude` and `codex`. `--plan-login` says you mean to run several agents on plan logins at once, which a
headless run refuses otherwise, with exit 78. The run says the session's name on stderr at once, owns the session in the
foreground until it settles, and exits 0 once it has. This team has not run on real models yet:
[docs/STATUS.md](../../docs/STATUS.md) says what has run live.
