# Headless quickstart

From a terminal or CI, with harnesses you already use and their own logins. [cli.md](../reference/cli.md) is the full reference.

## Check the machine

```console
$ platoon-harness doctor
platoon-harness 0.1.0, SDK 0.1.0
claude     2.1.319 (Claude Code), plan login, checked on 2.1.319: 26 passed, 4 skipped, none failed
codex      codex-cli 0.167.0, plan login, checked on 0.167.0: 25 passed, 5 skipped, none failed
openhands  1.59.0, login unknown, checked on 1.59.0: 26 passed, 4 skipped, none failed
pi         not on PATH
root       <home>/.local/state/platoon-harness, on <filesystem>
sockets    /run/user/<uid>/platoon-harness
...
usable
```

Its root and sockets lines are shown as they read for the default root, with `<home>`, `<filesystem>` and `<uid>` for your own,
and `...` for a line per driver and extension. It says each harness's version and the kind of its login, from the harness's own
status command, and never an account. It exits 0 when the machine can run sessions and 78 when it cannot. `doctor --check` runs
every check of each harness it finds that a check ships for against a model of ours on loopback, on no account, and keeps what it
found under the root, where the runtime reads it at each launch and resume: an agent's levels come from it, and say `unverified`
for a harness, an SDK or a host no result was made on. `doctor` says whether a kept result speaks for the binary that runs, and
what it found. `openhands` is there once the SDK's `openhands` extra is installed for the interpreter it names, as
[Install](../getting-started/install.md#openhands) says.

## Write a team

```console
$ platoon-harness init
platoon-harness: wrote platoon-harness.toml: a lead on claude, which starts workers on codex
$ platoon-harness team show
lead (claude) may message its workers and you. Workers (codex) may message lead.
lead adds to queue `tasks`; workers claim from it. Everyone shares board `notes`. Limits: hops 8. Closes when lead finishes.
$ platoon-harness team check --plan-login
no problems
```

`init` never overwrites a file. `team check` says every problem at once and exits 78 on an error, and `team told` says what an
agent of each role would be told. `--harness codex` adds a role on Codex over the project file, so where there is none it is a team
of one that needs no file.

[examples/mixed-team](../../examples/mixed-team/README.md) is such a team with a job to give it, which runs as below, and with no keys
on scripted stand-ins.

## Run it

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

The ending's `workspaces` names each agent's worktree or snapshot its end did not take, with its host, path, branch, size and why,
such as `1 uncommitted path: notes.md` or `ignored: .venv/`, and a `release`, the commands that let it go, only where they lose nothing
it was kept for but the ignored files it names: a worktree's unlock and remove, or a snapshot's fetch of its branch into your
repository and the removal of its folder. Where `release` is empty, `why` says what to save first. Its `unobserved` names each agent
whose last look never finished, as when a session is cancelled before its stops ran, so what that agent last changed was not
recorded. See [workspaces.md](workspaces.md).

## From another shell

Each command under Ops on a session acts on it by its name, as a guest, and runs one op, the one an agent's `ph` would run:

```console
$ platoon-harness events ci-42 --follow --json
$ platoon-harness message send ci-42 --to @lead --gist "Keep the public API stable"
$ platoon-harness board post ci-42 --board notes --name spec --gist "The spec" --body-file spec.md
$ platoon-harness agent interrupt ci-42 --agent @worker-1
$ platoon-harness session show ci-42
```

A person's message steers: it lands at the earliest boundary its harness has. An interrupt stops a turn and quiets what was waiting
for the agent, and what you send after it wakes the agent as usual. `session show` lists where you must act with the command that
settles each, such as `platoon-harness approval resolve ci-42 --id a7 --verdict allow --expected-version 3`.

`events` reads and never writes, on a live session or a closed one. Each JSON line carries its `seq`: pass the last one as `--after`
to go on exactly where you stopped. A person has no turn to park, so `wait` is no command: `events --follow` watches instead.

## Stop, resume, serve

```console
$ platoon-harness session stop ci-42
$ platoon-harness session resume ci-42
$ platoon-harness serve --team crew.toml --name nightly
```

`session stop` is the owner's stop from another shell, and keeps the session resumable. `session resume` restarts its harnesses,
which can spend money, and owns it as `run` does. A session started trainable, or whose agents a training system's authority
admitted, is never resumed, as their keys went with that authority, and `session resume` refuses it with exit 64; it stays history, which `events` reads. `session refold` brings a stopped session's views up to its journal, as a runtime
does as it opens, and writes no event, for when an upgrade changed a view and its history refuses to answer. `serve` keeps a session's runtime in the foreground with no client attached, for a
supervisor, and stops on `SIGTERM`.
