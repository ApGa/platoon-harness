# Headless quickstart

From a terminal or CI, with harnesses you already use and their own logins. [cli.md](cli.md) is the full reference.

## Check the machine

```console
$ platoon-harness doctor
platoon-harness 0.1.0, SDK 0.1.0
claude     2.1.316 (Claude Code), plan login
codex      codex-cli 0.164.0, plan login
pi         not on PATH
root       ~/.local/state/platoon-harness, on xfs
sockets    /run/user/1000/platoon-harness
...
usable
```

It says each harness's version and the kind of its login, from the harness's own status command, and never an account. It exits 0
when the machine can run sessions and 78 when it cannot.

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

## Run it

```console
$ platoon-harness run --plan-login "Fix the flaky test in tests/test_cart.py"
platoon-harness: session 20261103-101500-1a2b3c4d: follow it with `platoon-harness events 20261103-101500-1a2b3c4d --follow`
...
```

`run` owns the session in the foreground until it settles, and exits with how it ended: 0 settled, 1 an agent failed, 2 the budget
ran out, 3 it timed out, 4 it needs a person, 130 cancelled. Ctrl+C runs the owner's shutdown, which keeps the session resumable.
What it cannot run as given exits 64 before any cost: a `--to` naming no agent the session starts, or a name that is taken.
Several agents on one plan login need `--plan-login`, which says this is your own work; without it the run exits 78 and says so.

In CI, give the prompt on stdin, answer approvals by a stated policy, bound the wait, and read JSONL:

```console
$ git log -1 --format=%B | platoon-harness run --json --approvals deny --timeout 30m --name ci-42 > events.jsonl
$ jq -r 'select(.type == "ending") | .reason' events.jsonl
settled
```

Stdout then holds one JSON line per journal event and one for the ending, and nothing else; notes and logs go to stderr. Nothing
prompts. Without `--approvals`, an approval that would ask with nobody attached to answer ends the run at once with exit 4.

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
which can spend money, and owns it as `run` does. `serve` keeps a session's runtime in the foreground with no client attached, for a
supervisor, and stops on `SIGTERM`.
