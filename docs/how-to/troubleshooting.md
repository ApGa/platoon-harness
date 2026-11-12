# Troubleshooting

Each entry gives what you see, why, and what to do. Search this page for the message you got. Every command shares its
exit codes, which [the command line reference](../reference/cli.md#exit-codes) lists.

## First: ask doctor

```console
$ platoon-harness doctor
```

`doctor` says what this machine has and whether it can run a session, with a `problem` line for each reason it cannot, as
[Check the installation](../getting-started/install.md#check-the-installation) shows. It never names a harness's account,
but it prints local paths, your user id and the host name: remove what you would not post before you paste it into an
issue.

## doctor says `not usable`

```text
problem    no harness is on PATH
not usable
```

It exits 78. No harness it drives is on PATH, and the `openhands` extra is not installed either: install `claude`, `codex`
or `pi` and sign it in as you usually do, or install the extra, as [Install](../getting-started/install.md#openhands)
says. Its other problems are a root it cannot use, below, or a conflict among installed drivers and extensions, which
`platoon-harness extension list` names.

## doctor's `openhands` line names an interpreter

```text
openhands  openhands-sdk is not installed for ~/.local/share/uv/tools/platoon-harness/bin/python: install the SDK's `openhands` extra there, …
```

OpenHands runs on the runtime's own interpreter, and the extra that loads it is not installed for that one: install it
with the command line, as [Install](../getting-started/install.md#openhands) shows. OpenHands keeps no login, so its
role also needs an auth profile that names its key.

## The command line needs its extra

```text
platoon-harness: the command line needs its extra: uv tool install "platoon-harness[cli]", or pip install "platoon-harness[cli]"
```

It exits 78. The `platoon-harness` that ran belongs to an install of the library alone, without the `cli` extra. An
active virtual environment that holds one comes first on your PATH, ahead of a `uv tool install`: install the extra
there, or deactivate the environment.

## init says none is on PATH

```text
platoon-harness: harness: none is on PATH: install one of claude, codex, pi
```

It exits 78. `init` writes a team of the first harnesses it finds on PATH among these three, with no auth profile and no
model, so it passes over OpenHands, which needs an auth profile, and OpenCode, which needs a model: that is why `doctor`
can say `usable` while `init` finds nothing. Install one of the three and sign it in, or write the team file yourself, as
[the team file reference](../reference/team-file.md) lists its keys.

## init says the file exists

```text
platoon-harness: platoon-harness.toml exists, and init writes over nothing: edit it, or move it away first
```

It exits 1. `init` never overwrites a file: edit the one there, or move it away and run `init` again.

## A run refuses several agents on one plan login

```text
platoon-harness: plan_login: lead, worker would run several agents headless on one plan login: say this is your own work with `plan_login=True`, or `--plan-login` on the command line, or give each role an auth profile
```

It exits 78, before any cost, and `team check` says the same. Several agents on your own plan login need you to say this
is your own work: add `--plan-login`, or give each role an auth profile, which runs it on a key instead. A role that another
role can spawn counts as several, and so does one only a script's program starts, unless `max_live` is 1; a script says
`Session.start(team, plan_login=True)`.

## A name that is taken

```text
platoon-harness: refused conflict: session tally exists: resume it, or choose another name
```

`run` exits 64, before any cost. A session's name is claimed once under a root: choose another with `--name`, or
`platoon-harness session resume tally` to go on with the one there, which can spend money.

## A team file needs trust

```text
platoon-harness: roles.lead.harness: a `module:attr` in a project file needs explicit trust
```

It exits 78. A project or team file is untrusted, so what would run code or pass a credential is refused from one: a
`module:attr` or a command as a harness, a test command, and an auth profile. If you trust the file, say so with
`--trust`. The same setting given with `--set` needs none, as the command line is yours.

## A key that is not a key here

```text
platoon-harness: roles.lead.harnes: `harnes` is not a key here. Did you mean `harness`?
```

It exits 78, naming every problem at once, each at its dotted place in the team.
[The team file reference](../reference/team-file.md) lists every key of every table.

```text
platoon-harness: topology.program: `program` is not a key of [topology], and a preset is a table.
```

Under `[topology]`, a table names a preset, and one no preset or extension gives is refused so. A topology names no
program: control flow runs from a script, as [Run a program from Python](topologies.md#run-a-program-from-python) shows.

## A team a program owns

```text
platoon-harness: topology.until: `program` leaves the session to the program that owns it, and `human:you` is a person: start it from a script, with `Session.start(team, principal="program:<name>")`
```

It exits 78, before any cost. A session under `until = "program"` is done only when its program closes it, so `run`,
`serve`, the terminal UI and `session resume` refuse it as a person's. Start it, and run it again after a crash, from its
script, as [Run a program from Python](topologies.md#run-a-program-from-python) shows.

## attach says there is no terminal

```text
platoon-harness: attach draws on a terminal, and none is here: `platoon-harness events nothing --follow`
```

It exits 64. The terminal UI needs a terminal. Where there is none, as in a script, the command it names follows the
session's events instead.

## Sessions are not where you looked

Sessions live under the root: `$PLATOON_HARNESS_HOME` if you set it, else `$XDG_STATE_HOME/platoon-harness`, which is
`~/.local/state/platoon-harness` by default. If that default is on a network filesystem, sessions live in
`/var/tmp/platoon-harness-<uid>` instead, as a line on stderr and `doctor` say. A root you choose on a network
filesystem is refused to a live session, with exit 78, as a live journal is not safe there: choose a local directory.
`platoon-harness session list` lists the sessions under the root in use.

## A headless run ends at once with exit 4

With no client attached to answer, an approval that would ask ends the run at once with exit 4. In a script or CI,
answer approvals by a stated policy with `--approvals`, as [the headless quickstart](headless.md#3-run-it) shows.

## An agent is lost, its report refused, with `***` in it

```text
lost: its input.delivered report was refused: not_found: no offer ***09
```

Every value an auth profile hands a harness is masked as `***` wherever it is found in what the harness reports, and a
value of a character or two, such as a dummy key `1`, is found inside the ids a report names too, so the agent is lost.
Give each variable the profile names a value of more than a few characters, and run again; this is a known defect, which
[STATUS](../STATUS.md) records.

## Still stuck

Open an issue from the [bug report template](https://github.com/ApGa/platoon-harness/issues/new?template=bug_report.md),
which asks for what a maintainer needs to reproduce it. Report a security vulnerability privately, as
[SECURITY.md](../../SECURITY.md) says.
