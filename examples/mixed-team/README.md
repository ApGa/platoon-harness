# A mixed team

**Goal:** run a pi lead and an OpenHands worker in one session on a model you name, have them fix a bug in a copy of the
sample project, watch and steer them while they work, and read back whose work reached the lead's answer.

The lead puts a task for issue 1 of the sample project's `ISSUES.md` on the queue `tasks` and starts a worker, `fixer`.
The worker claims the task, fixes the bug with a test, writes a note on the board `notes` and reports back; the lead
reads the note and the code, and finishes. Each write may cite what it rests on, as the default template asks, so the
record can say afterwards whose work reached the lead's answer.

**Prerequisites:** those of [every example](../README.md#prerequisites), pi among them.

| File | What it is |
|---|---|
| [`team.toml`](team.toml) | The team: two roles, the `manager-worker` preset, which gives the queue and the board, an auth profile, `provider`, that hands both harnesses your endpoint and key, and a budget of 16 turns and 20 minutes, so a runaway stops itself. Both agents work in your copy, the session's `shared` workspace. The lead only reads, so its approvals deny, and the worker edits and runs the tests, so its approvals allow |
| [`job.md`](job.md) | What you ask of the lead |

## 1. Check it

In a new, empty folder, make a copy of the sample project, as a repository of its own, and work there:

```console
$ cp -r path/to/platoon-harness/examples/sample-project tally
$ cd tally
$ git init -q && git add -A && git commit -qm "Start from the sample project"
```

Check the team with a `--set` line for each role that names your model, MODEL as your endpoint names it, such as
`vendor/model` on OpenRouter:

```console
$ platoon-harness team check path/to/platoon-harness/examples/mixed-team/team.toml --trust \
    --set 'roles.lead.model = "MODEL"' --set 'roles.worker.model = "MODEL"'
$ platoon-harness team show path/to/platoon-harness/examples/mixed-team/team.toml --trust
```

`--trust` says you trust the team file's auth profile, which hands your key to each harness: without it, each command
that reads the file refuses it, with exit 78. `team check` says `no problems`, before any cost, and `team show` says in
sentences what the team allows:

```text
lead (pi) may message its workers and you. Workers (openhands) may message lead.
lead adds to queue `tasks`; workers claim from it. Everyone shares board `notes`. Limits: hops 8. Closes when lead finishes.
```

## 2. Run it

```console
$ platoon-harness run --team path/to/platoon-harness/examples/mixed-team/team.toml \
    --prompt-file path/to/platoon-harness/examples/mixed-team/job.md --trust --name tally \
    --set 'roles.lead.model = "MODEL"' --set 'roles.worker.model = "MODEL"'
```

The run says the session's name on stderr at once, prints a line per event as the session journals it, owns the session
in the foreground until the lead finishes, and exits 0 once it has settled. It ends with `settled, exit 0` and a line for
each agent, `@lead` and `@fixer`, with how it ended and its last words, which are the model's own. The worker's change
stays in your copy, uncommitted: `git diff` shows it, and `python3 -m unittest` runs its test.

A real model chooses its own steps, so a run can go otherwise: it may name its worker differently, read more files before
it acts, or take more turns. Two live runs on DeepSeek V4.1 Flash took 30 model calls each. The team's budget of 16 turns
and 20 minutes stops a runaway: no budget counts model calls, and one turn can make many.

The run names its session `tally`, and a name is taken once: a second run named `tally` is refused, with exit 64, so give
it another `--name`, and use that name in the steps below.

## 3. Watch and steer it

While it runs, from another shell:

```console
$ platoon-harness attach tally    # the terminal UI, as a guest of the running session
$ platoon-harness web tally       # SwarmChat's page; open the control link it prints
```

A message from either goes to whoever you address, `@lead` or `@fixer`, and a person's message steers. Once the session
has closed, both show its history, read-only.

## 4. Read it back

The queue, the board and the messages are ordinary commands on the session, live or closed:

```console
$ platoon-harness task list tally --queue tasks
$ platoon-harness board get tally --board notes --name fix-1
$ platoon-harness message read tally --channel @lead
```

Then ask what cites the worker's note, and whose work the record ties to the lead's answer:

```console
$ platoon-harness uses tally --ref board/notes/fix-1@1
$ platoon-harness contributors tally --ref REF
```

`uses` lists what cites the note, the lead's finish among it when the lead cited the note as the job asks: put the `ref`
of the row whose `maker` is `agent:lead` and whose `type` is `agent.finished` for REF. `contributors` then names each
maker the record ties to that answer, in the order reached. It is reachability in the record and never credit: it weighs
and ranks nobody, and a citation is its agent's claim. [Provenance](../../docs/how-to/provenance.md) says how to read
each answer, and how to follow it in the terminal UI and the page.

## 5. Other harnesses

A role's harness is one setting, so swap it with `--set`. Codex takes the same two variables and speaks OpenAI's
Responses API, which your endpoint must serve for it. This swap is untested:

```console
$ platoon-harness run --team path/to/platoon-harness/examples/mixed-team/team.toml \
    --prompt-file path/to/platoon-harness/examples/mixed-team/job.md --trust --name tally-codex \
    --set 'roles.lead.model = "MODEL"' --set 'roles.worker.model = "MODEL"' --set 'roles.worker.harness = "codex"'
```
