# Your first session

**Goal:** run a team with no keys, read back what it did and whose work reached its answer, open it in the terminal UI
and the browser, then set up a team of the harnesses you use.

**Prerequisites:**

- a checkout installed as [Install](install.md) says;
- for step 5, the harnesses you use on your PATH, signed in as you usually are; its output here is from a machine with
  `claude` and `codex`. Steps 1 to 4 need no harness and no key.

Run steps 1 to 4 from the root of the checkout. [Concepts](concepts.md) explains each word.

## 1. Run a team with no keys

[The mixed team](../../examples/mixed-team/README.md) is a [team](concepts.md#one-session-traced) of a lead and a
worker, and its scripted stand-ins do what its job asks with no model at all:

```console
$ PYTHONPATH=examples/mixed-team uv run platoon-harness run --team examples/mixed-team/team.toml \
    --prompt-file examples/mixed-team/job.md --set 'roles.lead.harness = "stand_ins:lead"' \
    --set 'roles.worker.harness = "stand_ins:worker"' --name first
```

`PYTHONPATH` lets the runtime import the stand-ins, and each `--set` puts a role on one of them in place of its harness.
`run` says the session's name on stderr at once, prints a line per event as the session journals it, and exits 0 once
the session has settled. It ends with how the session ended and each agent's last words:

```text
settled, exit 0
  @lead            finished  Three risks of caching DNS answers are on the board.
  @w               finished  The risks are on the board as risks.
```

## 2. Read it back

The session is closed, and its journal stays. Each of these reads it:

```console
$ uv run platoon-harness session list
$ uv run platoon-harness session show first
$ uv run platoon-harness task list first --queue tasks
$ uv run platoon-harness board get first --board notes --name risks
```

`session list` names every session under the root, `first` among them, closed. `session show` says how it stands:

```text
first  no runtime, closed, until role:lead
  @lead            lead       stand_ins:lead ended    agent_finish completed
  @w               worker     stand_ins:worker ended    agent_finish completed
  needs you: mention agent/lead, lead finished: Three risks of caching DNS answers are on the board.
```

`task list` shows the task on the queue `tasks`, done, with its result, and `board get` the worker's note on the board
`notes`, as JSON. `platoon-harness events first` prints every event, as [Concepts](concepts.md#one-session-traced)
traces them.

## 3. Ask what the record says

Every write may cite what it rests on, and the stand-ins cite as the default template asks each agent to:

```console
$ uv run platoon-harness uses first --ref board/notes/risks@1
$ uv run platoon-harness contributors first --ref REF
```

`uses` says what cites the worker's note, `board/notes/risks@1`, which is a ref: the task's result, the worker's finish
and the lead's finish, an `agent.finished` whose `maker` is `agent:lead`, among the rest. Put that row's `ref` for REF,
and `contributors` says whose work the record ties to the lead's answer: the lead, the worker and you, each once, in the
order reached. `contributors` is reachability in the record and never credit: it weighs and ranks nobody, and a citation
is its agent's claim. [Provenance](../how-to/provenance.md) says how to read each answer.

## 4. Open it in the terminal UI and the browser

```console
$ uv run platoon-harness attach first
$ uv run platoon-harness web first
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
