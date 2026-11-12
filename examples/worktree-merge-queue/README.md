# A worktree team with a merge queue

**Goal:** run a team on a model you name whose workers each fix an issue of the sample project on a branch of their own
and hand it to one merger through a queue, and read back what came of each merge, a conflict among them.

A pi lead starts two OpenHands workers, `ada` on issue 1 of the sample project's `ISSUES.md` and `bob` on issue 3, each
in a worktree of its own. Each fixes its issue with a test, adds a line at the top of `## Unreleased` in `CHANGELOG.md`,
commits, and adds a task to the queue `merges` naming its branch. A pi merger in a worktree of its own merges each branch
with git; both lines land at the same place, so the second merge stops on a conflict, which its worker reads from its
task's result. This is the merge queue [the topologies guide](../../docs/how-to/topologies.md#merge-worktrees-through-a-queue)
writes out.

**Prerequisites:** those of [every example](../README.md#prerequisites), pi among them. The workers commit and the
merger merges as you.

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
sandbox: what runs there can reach anything you can. The lead only reads, so its approvals deny: a command or an edit it
tries is refused, and nobody is asked.

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
both branches merge, or the merger may try to resolve a conflict its instructions leave for you. A live run on DeepSeek
V4.1 Flash took 74 model calls. The team's budget of 24 turns and 25 minutes stops a runaway: no budget counts model
calls, and one turn can make many.

## 3. Read it back

```console
$ platoon-harness task list fixes --queue merges
$ platoon-harness session show fixes
```

`task list` prints each task on `merges` with its `result`, which is what the merger completed it with: that the branch
merged, or the paths in conflict. `session show` names the merger under needs you while its worktree rests on the
conflict, with where to resolve it. That worktree stays, since its agent has not ended;
[When a workspace goes](../../docs/how-to/workspaces.md#when-a-workspace-goes) says when one is removed, and how to let go
of one that stays. In the terminal UI, `platoon-harness attach fixes` opens the same session, and `/review` lists what
changed, as [Review what changed](../../docs/how-to/tui.md#review-what-changed) says.
