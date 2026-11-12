# Run headless

**Goal:** check that a machine can run sessions, write a team, run it from a terminal or CI on the harnesses you already use,
watch and steer it from another shell, and stop and resume it. [cli.md](../reference/cli.md) is the full reference.

**Prerequisites:**

- platoon-harness installed as [Install](../getting-started/install.md) says;
- the harnesses you use on your PATH, signed in as you usually are, or the `openhands` extra, as
  [Install](../getting-started/install.md#openhands) says.

## 1. Check the machine

```console
$ platoon-harness doctor
```

[Check the installation](../getting-started/install.md#check-the-installation) shows what `doctor` says. What
`doctor --check` finds it keeps under the root, which the runtime reads at each launch and resume: an agent's levels come
from it, and say `unverified` where no kept result speaks for its harness.

## 2. Write a team

```console
$ platoon-harness init
platoon-harness: wrote platoon-harness.toml: a lead on claude, which starts workers on codex
platoon-harness: run it with `platoon-harness run "..."`, adding --plan-login on your own plan login
$ platoon-harness team show
lead (claude) may message its workers and you. Workers (codex) may message lead.
lead adds to queue `tasks`; workers claim from it. Everyone shares board `notes`. Limits: hops 8. Closes when lead finishes.
$ platoon-harness team check --plan-login
no problems
```

`init` never overwrites a file. `team check` says every problem at once and exits 78 on an error, and `team told` says what an
agent of each role would be told. `--harness codex` adds a role on Codex over the project file, so where there is none it is a team
of one that needs no file.

[examples/mixed-team](../../examples/mixed-team/README.md) is such a team with a job to give it, on pi and OpenHands and a model you
name, which runs as below.

## 3. Run it

```console
$ platoon-harness run --plan-login "Fix the flaky test in tests/test_cart.py"
platoon-harness: session 20261103-101500-1a2b3c4d: follow it with `platoon-harness events 20261103-101500-1a2b3c4d --follow`
...
```

`run` owns the session in the foreground until it settles, and exits with how it ended: 0 settled, 1 an agent failed, 2 the budget
ran out, 3 it timed out, 4 it needs a person, 130 cancelled. Ctrl+C runs the owner's shutdown, which keeps the session resumable.
The prompt goes to every agent the session starts, or with `--to` to that one alone. What it cannot run as given exits 64 before
any cost: a `--to` naming no agent the session starts, a team that starts none, or a name that is taken.
Several agents on one plan login need `--plan-login`, which says this is your own work; without it the run exits 78 and says so.
A commit to the session's journal that fails, as on a full disk, ends the run with exit 74, naming the journal, as a kill would:
`platoon-harness session resume` goes on from what the journal holds.

In CI, give the prompt on stdin, answer approvals by a stated policy, bound the wait, and read JSONL:

```console
$ git log -1 --format=%B | platoon-harness run --json --approvals deny --timeout 30m --name ci-42 > events.jsonl
$ jq -r 'select(.type == "ending") | .reason' events.jsonl
settled
```

Stdout then holds one JSON line per journal event and one for the ending, and nothing else; notes and logs go to stderr. Nothing
prompts. Without `--approvals`, an approval that would ask with nobody attached to answer ends the run at once with exit 4. A Codex
role in a worktree or a snapshot is one such: its sandbox keeps `.git` read-only, so its first commit asks, and `team check` says so
before any cost, with the three ways out; under `--approvals deny` it says each commit will be refused.

The ending's `workspaces` names each agent's worktree or snapshot that was kept, with why and, where letting it go loses nothing
it was kept for, the commands that do, as [When a workspace goes](workspaces.md#when-a-workspace-goes) says.

## 4. Watch and steer it from another shell

Each command under Ops on a session acts on it by its name, as a guest, and runs one op, the one an agent's `ph` would run:

```console
$ platoon-harness events ci-42 --follow --json
$ platoon-harness message send ci-42 --to @lead --gist "Keep the public API stable"
$ platoon-harness board post ci-42 --board notes --name spec --gist "The spec" --body-file spec.md
$ platoon-harness agent interrupt ci-42 --agent @worker-1
$ platoon-harness session show ci-42
$ platoon-harness session metrics ci-42
```

A person's message steers: it lands at the earliest boundary its harness has. An interrupt stops a turn and quiets what was waiting
for the agent, and what you send after it wakes the agent as usual. `session show` lists where you must act with the command that
settles each, such as `platoon-harness approval resolve ci-42 --id a7 --verdict allow --expected-version 3`.
`session metrics` says how it runs: the events its journal holds by type, its agents by the roster's groups, and what its
runtime has measured since it started, its writer's throughput, queue and ack latency and its process's CPU and memory, with
what nothing measured as null and why.

`events` reads and never writes, on a live session or a closed one. Each JSON line carries its `seq`: pass the last one as `--after`
to go on exactly where you stopped. A person has no turn to park, so `wait` is no command: `events --follow` watches instead.

## 5. Stop, resume or serve a session

```console
$ platoon-harness session stop ci-42
$ platoon-harness session resume ci-42
$ platoon-harness serve --team crew.toml --name nightly
```

`session stop` is the owner's stop from another shell, and keeps the session resumable. `session resume` restarts its harnesses,
which can spend money, and owns it as `run` does. `serve` keeps a session's runtime in the foreground with no client attached, for
a supervisor, and stops on `SIGTERM`. `session refold` brings a stopped session's views up to its journal, for when an upgrade
changed a view and the session refuses a query. A session stays under the root until you delete it, as
[Retention](../security.md#retention) says.
