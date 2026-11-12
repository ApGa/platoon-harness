# Your first session

**Goal:** run a team on a model you name, have it fix a bug in a copy of the sample project, read back what it did and
whose work reached its answer, and open it in the terminal UI and the browser.

**Prerequisites:**

- platoon-harness with its `cli` and `openhands` extras, installed as [Install](install.md#openhands) says;
- `pi` on your PATH, on Node 22.19 or later, which needs no login here;
- a model at an endpoint that speaks OpenAI's Chat Completions, with a key for it: OpenRouter's, or any provider's
  OpenAI-compatible URL;
- git that knows your name and email, as `git config user.name` and `git config user.email` say, and `python3` 3.9 or
  later;
- this repository's files, for the team and the sample project, cloned at the release you installed, X.Y.Z being what
  `platoon-harness --version` prints:

```console
$ git clone --branch vX.Y.Z https://github.com/ApGa/platoon-harness.git
```

The commands below write the clone's path as `path/to/platoon-harness`. Agents work where you start a session, so each
step runs in a folder of yours. [Concepts](concepts.md) explains each word.

## 1. Run a team on your model

[The mixed team](../../examples/mixed-team/README.md) is a [team](concepts.md#one-session-traced) of a pi lead and an
OpenHands worker. Its job is issue 1 of [the sample project](../../examples/sample-project/README.md), a small Python
package written for the examples, so in a new, empty folder make a copy of it, as a repository of its own:

```console
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
line for each agent, `@fixer` and `@lead`, with how it ended and its last words, which are the model's own. A real model
may take other steps than these. A live run on DeepSeek V4.1 Flash took 27 model calls; the team's budget of 16 turns and
20 minutes stops a runaway.

## 2. Read it back

The session is closed, and its journal stays. Each of these reads it:

```console
$ platoon-harness session list
$ platoon-harness session show first
$ platoon-harness task list first --queue tasks
$ platoon-harness board get first --board notes --name fix-1
```

`session list` names every session under the root, `first` among them, closed, and `session show` says how it stands:
its name, then `no runtime, closed, until role:lead`, then a line for each agent and what needs you, the lead's answer
among it. `task list` shows the task, done, with its result, and `board get` the worker's note, as JSON.
`platoon-harness events first` prints every event, as [Concepts](concepts.md#one-session-traced) traces them, and
`git diff` shows the worker's fix, uncommitted in your copy.

## 3. Ask what the record says

Every write may cite what it rests on, and the default template asks each agent to:

```console
$ platoon-harness uses first --ref board/notes/fix-1@1
$ platoon-harness contributors first --ref REF
```

`uses` says what cites the worker's note, `board/notes/fix-1@1`, which is a ref. Copy the `ref` of the row whose `maker`
is `agent:lead` and whose `type` is `agent.finished`, the lead's answer, and use it as REF: `contributors` then says whose
work the record ties to that answer, in the order reached, the lead, the worker and you, when each cited as asked. It
shows reachability in the record, not credit: it weighs and ranks nobody, and a citation is its agent's claim.
[Provenance](../how-to/provenance.md) says how to read each answer.

## 4. Open it in the terminal UI and the browser

```console
$ platoon-harness attach first
$ platoon-harness web first
```

`attach` opens the terminal UI on one session: as a guest of its runtime while it runs, or as read-only history when no
runtime holds it, as now. `web` serves SwarmChat's page over the session's journal and prints two links to open in a
browser, a view link and a control link; Ctrl+C stops it. Neither starts or resumes the session, as resuming can spend
money. [The terminal UI](../how-to/tui.md) and [the browser](../how-to/web.md) say what each shows and how to act there.

## Next steps

- [The quickstart](../../README.md#quickstart): your own harnesses, on your own logins, in the terminal UI.
- [Run headless](../how-to/headless.md): a team of yours from a terminal or CI.
- [The terminal UI](../how-to/tui.md): watch a session, answer what needs you, and steer its agents.
