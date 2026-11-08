# Your first session

**Goal:** run a team on a model you name, have it fix a bug in a copy of the sample project, read back what it did and
whose work reached its answer, open it in the terminal UI and the browser, then set up a team of the harnesses you use.

**Prerequisites:**

- a checkout installed as [Install](install.md) says, by `uv sync`, which brings the SDK's `openhands` extra;
- for steps 1 to 4, `pi` on your PATH, which needs no login here, git that knows your name and email, as
  `git config user.name` and `git config user.email` say, `python3` 3.9 or later, and a model at an endpoint that speaks
  OpenAI's Chat Completions, with a key for it: OpenRouter's, or any provider's OpenAI-compatible URL;
- for step 5, the harnesses you use on your PATH, signed in as you usually are; its output here is from a machine with
  `claude` and `codex`.

Agents work where you start a session, so each step runs in a folder of yours, with the checkout's environment active.
[Concepts](concepts.md) explains each word.

## 1. Run a team on your model

[The mixed team](../../examples/mixed-team/README.md) is a [team](concepts.md#one-session-traced) of a pi lead and an
OpenHands worker. Its job is issue 1 of [the sample project](../../examples/sample-project/README.md), a small Python
package written for the examples, so in a new, empty folder make a copy of it, as a repository of its own:

```console
$ source path/to/platoon-harness/.venv/bin/activate
$ cp -r path/to/platoon-harness/examples/sample-project tally
$ cd tally
$ git init -q && git add -A && git commit -qm "Start from the sample project"
```

Name your endpoint and key in the two variables the team's auth profile names, such as
`export OPENAI_BASE_URL=https://openrouter.ai/api/v1` and `export OPENAI_API_KEY=...` with your key, and run the team
with a `--set` line for each role that names your model, MODEL as your endpoint names it, such as `vendor/model` on
OpenRouter:

```console
$ platoon-harness run --team path/to/platoon-harness/examples/mixed-team/team.toml \
    --prompt-file path/to/platoon-harness/examples/mixed-team/job.md --trust --name first \
    --set 'roles.lead.model = "MODEL"' --set 'roles.worker.model = "MODEL"'
```

`--trust` says you trust the team file's auth profile, which hands your key to each harness. `run` says the session's
name on stderr at once, prints a line per event as the session journals it, and exits 0 once the session has settled.
The lead puts a task on a queue and starts a worker, `fixer`, which fixes the bug in your copy with a test, writes a
note on a board and reports back, and the lead reads the note and finishes. The run ends with `settled, exit 0` and a
line for each agent, `@fixer` and `@lead`, with how it ended and its last words, which are the model's own. It spends
model calls on your key, as many as its model takes: the team's budget of 16 turns and 20 minutes stops a runaway, and
a real model may take other steps than these, as [the mixed team](../../examples/mixed-team/README.md#2-run-it) says.

## 2. Read it back

The session is closed, and its journal stays. Each of these reads it:

```console
$ platoon-harness session list
$ platoon-harness session show first
$ platoon-harness task list first --queue tasks
$ platoon-harness board get first --board notes --name fix-1
```

`session list` names every session under the root, `first` among them, closed. `session show` says how it stands: its
name, then `no runtime, closed, until role:lead`, then a line for each agent with its role, its harness and how it
ended, and what needs you, the lead's answer among it. `task list` shows the task on the queue `tasks`, done, with its
result, and `board get` the worker's note on the board `notes`, as JSON. `platoon-harness events first` prints every
event, as [Concepts](concepts.md#one-session-traced) traces them, and `git diff` shows the worker's fix, which it left
uncommitted in your copy.

## 3. Ask what the record says

Every write may cite what it rests on, and the default template asks each agent to:

```console
$ platoon-harness uses first --ref board/notes/fix-1@1
$ platoon-harness contributors first --ref REF
```

`uses` says what cites the worker's note, `board/notes/fix-1@1`, which is a ref: the task's result, the worker's finish
and the lead's finish, an `agent.finished` whose `maker` is `agent:lead`, among the rest, as far as each agent cited the
note as the job asks. Put that row's `ref` for REF, and `contributors` says whose work the record ties to the lead's
answer, each once, in the order reached: the lead, the worker and you, when each cited as asked. `contributors` is
reachability in the record and never credit: it weighs and ranks nobody, and a citation is its agent's claim.
[Provenance](../how-to/provenance.md) says how to read each answer.

## 4. Open it in the terminal UI and the browser

```console
$ platoon-harness attach first
$ platoon-harness web first
```

`attach` opens the terminal UI on one session: as a guest of its runtime while it runs, or as read-only history when no
runtime holds it, as now. `web` serves SwarmChat's page over the session's journal and prints a link to open in a
browser, and Ctrl+C stops it. Either starts and resumes nothing, as resuming can spend money.
[The terminal UI](../how-to/tui.md) and [the browser](../how-to/web.md) say what each shows and how to act there.

## 5. Set up your own team

Agents work where you start a session, so set up your own in a repository of yours, with the checkout's environment
active. `doctor` says what this machine has, `init` writes a team of the harnesses it found, never overwriting a file,
`team show` says in sentences what the team allows, and `team check` says every problem at once, before any cost:

```console
$ source path/to/platoon-harness/.venv/bin/activate
$ platoon-harness doctor
$ platoon-harness init
platoon-harness: wrote platoon-harness.toml: a lead on claude, which starts workers on codex
platoon-harness: run it with `platoon-harness run "..."`, adding --plan-login on your own plan login
$ platoon-harness team show
lead (claude) may message its workers and you. Workers (codex) may message lead.
lead adds to queue `tasks`; workers claim from it. Everyone shares board `notes`. Limits: hops 8. Closes when lead finishes.
$ platoon-harness team check --plan-login
no problems
```

`--plan-login` says you mean to run several agents on your own plan login at once, which a headless run refuses
otherwise, with exit 78. `platoon-harness run --plan-login` with a job then runs the team, which spends model calls on
your logins, as [the headless quickstart](../how-to/headless.md#3-run-it) shows, and `platoon-harness` alone opens the
terminal UI, whose sessions screen starts a session from the project's team.
[The team file reference](../reference/team-file.md) lists every key the team file may set.

You can set up the same team with no command line but `platoon-harness` itself. Where no team is, the sessions screen
offers once, as it opens, to write the one `init` writes, and `y` takes the offer. It never overwrites a file either, and
`n` then starts a session from it. If a harness of it cannot start, the terminal UI says what `doctor` finds of that
harness.
