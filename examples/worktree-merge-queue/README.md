# A worktree team with a merge queue

**Goal:** run a team on a model you name whose workers each fix an issue of the sample project on a branch of their own
and hand it to one merger through a queue, and read back what came of each merge, a conflict among them.

A pi lead, two OpenHands workers each in a worktree of its own, and a pi merger in a worktree of its own, in your copy of
[the sample project](../sample-project/README.md). The lead starts the workers, `ada` on issue 1 of its `ISSUES.md` and
`bob` on issue 3. Each fixes its issue with a test, adds a line for its fix at the top of the list under `## Unreleased`
in `CHANGELOG.md`, commits on its branch, adds a task to the queue `merges` naming that branch, and waits on the task.
The merger claims each task, merges the branch it names into its own with git, and completes the task with what came of
that. Both workers add their line at the same place, so the second merge stops on a conflict in `CHANGELOG.md` unless a
model writes its line elsewhere: the merger completes that task naming the path, and its worker reads that from its
task's result. The runtime never merges: the look after each turn records the merge commit as the merger's, or the merge
under way and its conflicted paths, which put the merger under Needs you. This is the merge queue
[the topologies guide](../../docs/how-to/topologies.md#merge-worktrees-through-a-queue) writes out, with each role's
instructions saying its part, as [RFC 0058](../../docs/rfcs/0058-a-merge-queue-is-a-queue-and-a-merger-written-out.md)
decided.

**Prerequisites:**

- a checkout of this repository with its packages installed by `uv sync`, as [the README](../../README.md#install) says,
  which brings the SDK's `openhands` extra, and its environment active, as
  [your first session](../../docs/getting-started/first-session.md#1-run-a-team-on-your-model) has it;
- `pi` on your PATH, which needs no login here;
- a model at an endpoint that speaks OpenAI's Chat Completions, and a key for it, in `OPENAI_BASE_URL` and
  `OPENAI_API_KEY`, as [the mixed team](../mixed-team/README.md#1-check-it) names them;
- git that knows your name and email, as `git config user.name` and `git config user.email` say, since the workers
  commit and the merger merges as you, and `python3` 3.9 or later on your PATH, which the workers run the tests on.

The example has two files:

| File | What it is |
|---|---|
| [`team.toml`](team.toml) | The team: the `manager-worker` preset for the lead and its workers, a merger, the queue `merges` that workers add to and the merger claims from, each entry of which wakes the merger, each role's instructions, an auth profile, `provider`, that hands each harness your endpoint and key, and a budget of 24 turns and 25 minutes, so a runaway stops itself |
| [`job.md`](job.md) | What you ask of the lead: two workers, each fixing an issue on its own branch and handing it to the merger, and what came of each merge |

## 1. Check it

In a new, empty folder, make a copy of the sample project, as a repository of its own, and work there:

```console
$ cp -r path/to/platoon-harness/examples/sample-project tally
$ cd tally
$ git init -q && git add -A && git commit -qm "Start from the sample project"
```

Check the team with a `--set` line for each role that names your model, MODEL as your endpoint names it:

```console
$ platoon-harness team check path/to/platoon-harness/examples/worktree-merge-queue/team.toml --trust \
    --set 'roles.lead.model = "MODEL"' --set 'roles.worker.model = "MODEL"' --set 'roles.merger.model = "MODEL"'
$ platoon-harness team show path/to/platoon-harness/examples/worktree-merge-queue/team.toml --trust
```

`--trust` says you trust the team file's auth profile, which hands your key to each harness: without it, each command
that reads the file refuses it, with exit 78. `team check` says `no problems`, before any cost, and `team show` says in
sentences what the team allows:

```text
lead (pi) may message its workers and you. merger (pi, own worktree) may message no one. Workers (openhands, own worktrees) may message lead.
Workers add to queue `merges`; merger claims from it. Each entry wakes its readers. lead adds to queue `tasks`; workers claim from it. Everyone shares board `notes`. Limits: hops 8. Closes when lead finishes.
```

Each worker commits and the merger merges, and nobody is there to answer an approval in a headless run, so the team file
gives those two roles `approvals = "allow"`: they run commands, git among them, as you, unasked. A worktree is not a
sandbox: what runs there can reach anything you can. The lead only reads, so its approvals deny: a command or an edit
it tries is refused, and nobody is asked.

## 2. Run it

```console
$ platoon-harness run --team path/to/platoon-harness/examples/worktree-merge-queue/team.toml \
    --prompt-file path/to/platoon-harness/examples/worktree-merge-queue/job.md --to @lead --trust --name fixes \
    --set 'roles.lead.model = "MODEL"' --set 'roles.worker.model = "MODEL"' --set 'roles.merger.model = "MODEL"'
```

`--to @lead` gives the job to the lead alone: the merger starts idle, and a task on its queue wakes it. The run prints a
line per event as the session journals it, and ends with `settled, exit 0` and a line for each agent: `@ada` and `@bob`
finished, each with its task's result, that its branch merged or the paths in conflict; `@lead` finished, with what came
of each merge in its words; and `@merger` waiting, as it waits for work until the lead's finish closes the session.
Whichever worker adds its task first is merged first. The workers and the merger each work on the branch
`platoon-harness/fixes/<agent>`, in a worktree in the session's folder, made at your HEAD: nothing of it is in your
checkout. A session's name is taken once, so a second run needs another `--name`.

A real model chooses its own steps, so a run can go otherwise: a worker may write its line in another place, and then
both branches merge, or the merger may try to resolve a conflict its instructions leave for you. The team's budget of
24 turns and 25 minutes is what stops a runaway: no budget counts model calls, and one turn can make many.
`tests/live/test_examples.py` fails a live run of this example that took more than 110 model calls, counted once the run
has ended, or 25 minutes, about one and a half times what live runs on DeepSeek V4.1 Flash took on 2026-11-08, 74 model calls: [docs/STATUS.md](../../docs/STATUS.md) says
what has run live. `tests/integration/test_examples.py` runs the `platoon-harness` commands on this page as shown, with
`fake-model` for MODEL, and the run with one more `--set` line, which hands pi its switch for no network, on the real
`pi` and OpenHands against FakeModel, a loopback model that replies from a script, so the harnesses, the tools, git and
the team file are real and only the model is scripted.

## 3. Read it back

```console
$ platoon-harness task list fixes --queue merges
$ platoon-harness session show fixes
```

`task list` prints each task on `merges` with its `result`, which is what the merger completed it with: that the branch
merged, or the paths in conflict, and each worker is told to finish with its task's result. `session show` names the
merger under needs you while its worktree rests on the conflict, with where to resolve it. That worktree stays, since its
agent has not ended; [When a workspace goes](../../docs/how-to/workspaces.md#when-a-workspace-goes) says when one is
removed, and how to let go of one that stays. In the terminal UI, `platoon-harness attach fixes` opens the same session:
`/review` lists what changed, grouped by workspace, and the conflict waits in the dock, saying where to resolve it, as
[Review what changed](../../docs/how-to/tui.md#review-what-changed) says, with a
[snapshot](../../docs/assets/tui-review.svg) of the list for the mixed team's recorded session.
