# A mixed team

**Goal:** run a pi lead and an OpenHands worker in one session on a model you name, have them fix a bug in a copy of the
sample project, watch and steer them while they work, and read back whose work reached the lead's answer.

A pi lead and an OpenHands worker in one session, in your copy of [the sample project](../sample-project/README.md),
`tally`. The lead puts a task for issue 1 of its `ISSUES.md` on the queue `tasks` and starts a worker, `fixer`; the
worker claims the task, fixes the bug with a test, runs the tests, writes a note on the board `notes` and reports back by
message; the lead reads the note and the code, and finishes. Every write may cite what it rests on, which the default
template asks each agent to do, and afterwards the record says whose work reached the lead's answer.

**Prerequisites:**

- a checkout of this repository with its packages installed by `uv sync`, as [the README](../../README.md#install) says,
  which brings the SDK's `openhands` extra, and its environment active, as
  [your first session](../../docs/getting-started/first-session.md#1-run-a-team-on-your-model) has it;
- `pi` on your PATH, which needs no login here;
- a model at an endpoint that speaks OpenAI's Chat Completions, and a key for it: OpenRouter's, or any provider's
  OpenAI-compatible URL;
- git that knows your name and email, as `git config user.name` and `git config user.email` say, since the copy's
  first commit is yours, and `python3` 3.9 or later on your PATH, which the worker runs the sample project's tests on.

The example has two files:

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

Name your endpoint and key in the two variables the team's auth profile names, such as
`export OPENAI_BASE_URL=https://openrouter.ai/api/v1` and `export OPENAI_API_KEY=...` with your key, and check the team
with a `--set` line for each role that names your model:

```console
$ platoon-harness team check path/to/platoon-harness/examples/mixed-team/team.toml --trust \
    --set 'roles.lead.model = "MODEL"' --set 'roles.worker.model = "MODEL"'
$ platoon-harness team show path/to/platoon-harness/examples/mixed-team/team.toml --trust
```

MODEL is the model as your endpoint names it, such as `vendor/model` on OpenRouter. `--trust` says you trust the team
file's auth profile, which hands your key to each harness: without it, each command that reads the file refuses it, with
exit 78. `team check` says `no problems`, before any cost, and `team show` says in sentences what the team allows:

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

A real model chooses its own steps, so a run can go otherwise: it may name its worker differently, read more files
before it acts, or take more turns. The team's budget of 16 turns and 20 minutes is what stops a runaway: no budget
counts model calls, and one turn can make many. `tests/live/test_examples.py` fails a live run of this example that took
more than 40 model calls, counted once the run has ended, or 15 minutes, numbers no run has checked yet, as it has not
run: [docs/STATUS.md](../../docs/STATUS.md) says what has run live. `tests/integration/test_examples.py` runs the
commands of sections 1, 2 and 4 as shown, with `fake-model` for MODEL, and the run with one more `--set` line, which
hands pi its switch for no network, on the real `pi` and OpenHands against FakeModel, a loopback model that replies from
a script, so the harnesses, the tools and the team file are real and only the model is scripted. Section 5's swap is not
tested.

The run names its session `tally`, and a name is taken once: a second run named `tally` is refused, with exit 64, so give
it another `--name`, and use that name in the steps below.

## 3. Watch and steer it

To watch and steer it while it runs, from another shell:

```console
$ platoon-harness attach tally    # the terminal UI, as a guest of the running session
$ platoon-harness web tally       # SwarmChat's page; open the control link it prints
```

![The terminal UI on a closed session: a lead and the worker it spawned in the navigator, the lead's transcript beside them, and the composer below](../../docs/assets/tui-wide.svg)

*The terminal UI on another session, of scripted harnesses, as its snapshot test draws it.*

A message from either goes to whoever you address, `@lead` or `@fixer`, and a person's message steers. Or start the
whole thing from the terminal UI: `platoon-harness`, then start a session from the team file on its sessions screen, type
the job in the composer, and `platoon-harness web` the session it made.

## 4. Read it back

The queue, the board and the messages are ordinary commands on the session, live or closed:

```console
$ platoon-harness task list tally --queue tasks
$ platoon-harness board get tally --board notes --name fix-1
$ platoon-harness message read tally --channel @lead
```

Provenance: in the terminal UI, choose the line of the lead's answer and press `p`, or type `/provenance` and send its form
as the chosen line fills it in; in the page, Provenance is among a message's actions. Each opens on one event, with its sources, its uses and its contributors, each link by how it
is known. From the command line:

```console
$ platoon-harness uses tally --ref board/notes/fix-1@1
$ platoon-harness contributors tally --ref REF
```

`uses` says what cites the worker's note, the lead's finish among it, an `agent.finished` whose `maker` is `agent:lead`,
when the lead cited the note as the job asks. Put that row's `ref` for REF, and `contributors` says whose work the record
ties to the lead's answer, in the order reached. It is reachability in the record and never credit: it weighs and ranks
nobody, and a citation is its agent's claim. [docs/how-to/provenance.md](../../docs/how-to/provenance.md) says how to read
each answer.

## 5. Other harnesses

A role's harness is one setting, so swap it with `--set`. Codex takes the same two variables and speaks OpenAI's
Responses API, which your endpoint must serve for it:

```console
$ platoon-harness run --team path/to/platoon-harness/examples/mixed-team/team.toml \
    --prompt-file path/to/platoon-harness/examples/mixed-team/job.md --trust --name tally-codex \
    --set 'roles.lead.model = "MODEL"' --set 'roles.worker.model = "MODEL"' --set 'roles.worker.harness = "codex"'
```
