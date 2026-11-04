# Command line reference

<!-- Made from the command definitions by `uv run python -m platoon_harness_cli.reference > docs/cli.md`. Do not edit:
change the definitions, and make it again. A test holds it to them. -->

Each command under Ops on a session takes the session's name first, and runs one op there as a guest, by the name and
with the arguments an agent's `ph` uses: `ph task.claim --queue tasks` is `platoon-harness task claim SESSION --queue
tasks`. A read runs on a view credential, which writes nothing, and anything else on a control credential. `wait` and
the ops on a wait have no command, as a wait parks a turn and a person has none: `events --follow` watches a session,
and a script has `Session.wait`. The [headless quickstart](headless.md) shows them together.

## Exit codes

`run` and `session resume` exit with how their session ended, as architecture section 12 lists it:

| Reason | Code |
|---|---|
| `settled` | 0 |
| `agent_failed` | 1 |
| `budget_exhausted` | 2 |
| `timed_out` | 3 |
| `needs_human` | 4 |
| `cancelled` | 130 |

Every command shares these:

| Code | When |
|---|---|
| 1 | A command other than `run` and `session resume` was refused, and nothing it asked for happened |
| 64 | A command line that cannot run as it was given. `run` and `session resume` exit this for a refusal before the session is theirs, such as a name that is taken or no session of that name, so they never exit 1 for one |
| 74 | A commit to the session's journal failed, which ended its runtime as a kill would. `run`, `serve` and `session resume` exit this, with what the journal said, and `session resume` goes on from what it holds |
| 78 | A team, a root or a machine that cannot be used as it is. `team check` and `doctor` print each problem on stdout, as what they say, and every other command on stderr |
| 130 | Ctrl+C, where no session's ending says more |

## JSONL

With `--json`, `run`, `session resume` and `events` print one JSON object per line on stdout, and nothing else reaches
it: logs, notes and refusals go to stderr. Each line has `format`, which is 1, and holds ASCII alone, anything
else escaped. `run` and `session resume` print each event the runtime they own journals, from its `runtime.started`,
and `events` each event past `--after`.

An event's line is its envelope as the journal holds it, as architecture section 5.3 says, with these keys:

`v`, `seq`, `stream`, `version`, `type`, `actor`, `agent`, `turn`, `context_version`, `episode`, `topology_rev`, `correlation`, `cause`, `based_on`, `native`, `model`, `wall_time`, `gist`, `data`, `outcome`

Its `v` is its payload's version. Its `seq` is a cursor: pass the last one as `--after` to go on exactly where you
stopped. The last line of `run` and `session resume` is the ending, with these keys, where `type` is `ending` and
`code` is what the command exits with. One stopped while its runtime starts prints its ending alone:

`type`, `state`, `reason`, `agents`, `usage`, `gaps`, `workspaces`, `unobserved`, `code`

Without `--json` each event is one readable line, which is no contract. JSONL is the one versioned shape here: what
another command prints with `--json`, and what an op's command prints, is that op's result or that command's report,
whose shape follows it, with no `format`.

## platoon-harness

```console
platoon-harness COMMAND
```

Bring the agent harnesses you already use together as a team, from a terminal or from CI.

On a terminal, `platoon-harness` alone opens the terminal UI, and `attach` opens one session there. A session is a
folder holding a journal. `run` starts one and owns it until it settles, and `serve` keeps one for clients to attach
to. Each command under Ops on a session runs one op there as a guest, as an agent's `ph` does.

For example:

    platoon-harness init
    platoon-harness run "Fix the flaky test" --name fix-auth
    platoon-harness events fix-auth --follow
    platoon-harness message send fix-auth --to @lead --gist "Keep the public API stable"
    platoon-harness session show fix-auth

## Table of Contents

- [`attach`](#platoon-harness-attach)
- [`web`](#platoon-harness-web)
- [`run`](#platoon-harness-run)
- [`serve`](#platoon-harness-serve)
- [`events`](#platoon-harness-events)
- [`session`](#platoon-harness-session)
    - [`list`](#platoon-harness-session-list)
    - [`show`](#platoon-harness-session-show)
    - [`stop`](#platoon-harness-session-stop)
    - [`resume`](#platoon-harness-session-resume)
    - [`refold`](#platoon-harness-session-refold)
    - [`cancel`](#platoon-harness-session-cancel)
    - [`close`](#platoon-harness-session-close)
    - [`ending`](#platoon-harness-session-ending)
    - [`manifest`](#platoon-harness-session-manifest)
    - [`status`](#platoon-harness-session-status)
- [`team`](#platoon-harness-team)
    - [`check`](#platoon-harness-team-check)
    - [`show`](#platoon-harness-team-show)
    - [`told`](#platoon-harness-team-told)
- [`init`](#platoon-harness-init)
- [`doctor`](#platoon-harness-doctor)
- [`extension`](#platoon-harness-extension)
    - [`list`](#platoon-harness-extension-list)
- [`annotate`](#platoon-harness-annotate)
- [`annotations`](#platoon-harness-annotations)
- [`agent`](#platoon-harness-agent)
    - [`cancel`](#platoon-harness-agent-cancel)
    - [`interrupt`](#platoon-harness-agent-interrupt)
    - [`list`](#platoon-harness-agent-list)
    - [`release`](#platoon-harness-agent-release)
    - [`retire`](#platoon-harness-agent-retire)
    - [`spawn`](#platoon-harness-agent-spawn)
    - [`status`](#platoon-harness-agent-status)
    - [`takeover`](#platoon-harness-agent-takeover)
    - [`unread`](#platoon-harness-agent-unread)
- [`approval`](#platoon-harness-approval)
    - [`resolve`](#platoon-harness-approval-resolve)
- [`attention`](#platoon-harness-attention)
    - [`list`](#platoon-harness-attention-list)
- [`blob`](#platoon-harness-blob)
    - [`get`](#platoon-harness-blob-get)
- [`board`](#platoon-harness-board)
    - [`get`](#platoon-harness-board-get)
    - [`post`](#platoon-harness-board-post)
    - [`query`](#platoon-harness-board-query)
    - [`revise`](#platoon-harness-board-revise)
- [`body`](#platoon-harness-body)
    - [`tombstone`](#platoon-harness-body-tombstone)
- [`budget`](#platoon-harness-budget)
    - [`set`](#platoon-harness-budget-set)
    - [`status`](#platoon-harness-budget-status)
- [`channel`](#platoon-harness-channel)
    - [`create`](#platoon-harness-channel-create)
    - [`list`](#platoon-harness-channel-list)
- [`contributors`](#platoon-harness-contributors)
- [`effect`](#platoon-harness-effect)
    - [`settle`](#platoon-harness-effect-settle)
- [`episode`](#platoon-harness-episode)
    - [`close`](#platoon-harness-episode-close)
    - [`open`](#platoon-harness-episode-open)
- [`exposure`](#platoon-harness-exposure)
- [`lineage`](#platoon-harness-lineage)
- [`message`](#platoon-harness-message)
    - [`read`](#platoon-harness-message-read)
    - [`send`](#platoon-harness-message-send)
- [`ops`](#platoon-harness-ops)
    - [`list`](#platoon-harness-ops-list)
- [`peers`](#platoon-harness-peers)
- [`task`](#platoon-harness-task)
    - [`add`](#platoon-harness-task-add)
    - [`claim`](#platoon-harness-task-claim)
    - [`complete`](#platoon-harness-task-complete)
    - [`fail`](#platoon-harness-task-fail)
    - [`list`](#platoon-harness-task-list)
    - [`release`](#platoon-harness-task-release)
    - [`renew`](#platoon-harness-task-renew)
- [`uses`](#platoon-harness-uses)
- [`view`](#platoon-harness-view)
    - [`watch`](#platoon-harness-view-watch)

**Commands**:

* [`annotate`](#platoon-harness-annotate): Say what an estimator found of an event, a `reward` or a `credit`, in `annotations.sqlite` beside the journal and never in it, on a live session or a closed one, with no runtime.
* [`annotations`](#platoon-harness-annotations): List what estimators said of one event, or of every one, oldest first, each with its producer and version and never summed. Nothing an agent can reach reads these.
* [`attach`](#platoon-harness-attach): Open a session in the terminal UI: live, as a guest of its runtime, or as its history when no runtime holds it.
* [`doctor`](#platoon-harness-doctor): Say whether this machine can run sessions, and what it has.
* [`events`](#platoon-harness-events): Print a session's events past a cursor, live or closed, writing nothing.
* [`extension`](#platoon-harness-extension): What is installed, read from metadata alone.
* [`init`](#platoon-harness-init): Write a starter `platoon-harness.toml` from the harnesses on PATH, and say how to run it.
* [`run`](#platoon-harness-run): Start a session, give it a prompt, and own it in the foreground until it settles.
* [`serve`](#platoon-harness-serve): Start a session and keep its runtime in the foreground, with no client attached, for a supervisor.
* [`session`](#platoon-harness-session): Sessions, from their folders, and what can be done to one as a whole.
* [`team`](#platoon-harness-team): What a team allows and what its agents are told, before any cost.
* [`web`](#platoon-harness-web): Open a session in the browser: SwarmChat's page, served over the session's journal.

**Ops on a session**:

* [`agent`](#platoon-harness-agent): The `agent` ops, each on one session, with the arguments an agent's `ph agent.<op>` takes as flags.
* [`approval`](#platoon-harness-approval): The `approval` ops, each on one session, with the arguments an agent's `ph approval.<op>` takes as flags.
* [`attention`](#platoon-harness-attention): The `attention` ops, each on one session, with the arguments an agent's `ph attention.<op>` takes as flags.
* [`blob`](#platoon-harness-blob): The `blob` ops, each on one session, with the arguments an agent's `ph blob.<op>` takes as flags.
* [`board`](#platoon-harness-board): The `board` ops, each on one session, with the arguments an agent's `ph board.<op>` takes as flags.
* [`body`](#platoon-harness-body): The `body` ops, each on one session, with the arguments an agent's `ph body.<op>` takes as flags.
* [`budget`](#platoon-harness-budget): The `budget` ops, each on one session, with the arguments an agent's `ph budget.<op>` takes as flags.
* [`channel`](#platoon-harness-channel): The `channel` ops, each on one session, with the arguments an agent's `ph channel.<op>` takes as flags.
* [`contributors`](#platoon-harness-contributors): Name each maker a walk back from an outcome reaches along citations, causes and ancestry, in the order it reached them, with the kinds that reached each and the gaps on the way, and apart from them each maker whose work was only handed to one of them, which the walk does not go through.
* [`effect`](#platoon-harness-effect): The `effect` ops, each on one session, with the arguments an agent's `ph effect.<op>` takes as flags.
* [`episode`](#platoon-harness-episode): The `episode` ops, each on one session, with the arguments an agent's `ph episode.<op>` takes as flags.
* [`exposure`](#platoon-harness-exposure): Say whether an event reached an agent through us before another, `--before`, or by now: `seen`, with each offer of it its harness said it took and each compaction since, `not_seen`, or `unknown`, with the offers its harness never said it took, the surfaces no result proves observed and the gaps content could have come through.
* [`lineage`](#platoon-harness-lineage): Show one hop back from an event: who made it, in which turn and model call, what it cites, each with its citer's exposure, what it followed from, its previous version or a commit's parents, and a page of what its maker was offered and the gaps in its record below it, newest first, with true totals.
* [`message`](#platoon-harness-message): The `message` ops, each on one session, with the arguments an agent's `ph message.<op>` takes as flags.
* [`ops`](#platoon-harness-ops): The `ops` ops, each on one session, with the arguments an agent's `ph ops.<op>` takes as flags.
* [`peers`](#platoon-harness-peers): List whom you may message directly now, in `platoon-harness peers`, with the true `total` and a `cursor` to pass as `--after`, or none at the end.
* [`task`](#platoon-harness-task): The `task` ops, each on one session, with the arguments an agent's `ph task.<op>` takes as flags.
* [`uses`](#platoon-harness-uses): Show one hop forward from an event, oldest first: what cites it, what follows from it, its next version or the commits that name it a parent, and each agent it was offered to, with whether its harness said it took it, and true totals.
* [`view`](#platoon-harness-view): The `view` ops, each on one session, with the arguments an agent's `ph view.<op>` takes as flags.

### platoon-harness attach

```console
platoon-harness attach SESSION
```

Open a session in the terminal UI: live, as a guest of its runtime, or as its history when no runtime holds it.

Attaching changes nothing in the session, and reading it moves only your own marks of how far you have read:
only `/resume`, which resumes a session with no runtime, can spend money. `/detach` detaches, and the session runs
on. It needs a terminal: `events --follow` follows a session as text.

For example:

    platoon-harness attach fix-auth

**Arguments**:

* `SESSION`: A session, by name. `platoon-harness session list` shows them. **[required]**

### platoon-harness web

```console
platoon-harness web [OPTIONS] SESSION
```

Open a session in the browser: SwarmChat's page, served over the session's journal.

It says two links on stderr, each of which opens once, within ten minutes, for a session in the browser that lasts
twelve hours: a view link, which shows the session and acts on nothing, and a control link, which acts as you,
through the same ops as the terminal. A page that acts can make more links of either kind. Stopping `web` ends
every browser's session, and leaving it changes nothing in the session, which runs on. It starts and resumes
nothing: on a session no runtime holds, the page shows its history and names `session resume`, which can spend
money. Ctrl+C or SIGTERM stops it.

It serves loopback alone unless --host names another address, which needs --certificate and --key, as TLS. On
loopback it also says how to reach it from another machine: forward its port under the same number.

For example:

    platoon-harness web fix-auth
    platoon-harness web fix-auth --port 8484
    platoon-harness web fix-auth --host 192.0.2.7 --certificate cert.pem --key key.pem

**Arguments**:

* `SESSION`: A session, by name. `platoon-harness session list` shows them. **[required]**

**Parameters**:

* `--host`: The address or name to serve, which a browser's requests must name.
* `--port`: The port to serve, or 0 for any free one, which stderr says.
* `--certificate`: A certificate chain, in PEM, to serve TLS with.
* `--key`: The certificate's private key, in PEM.

### platoon-harness run

```console
platoon-harness run [OPTIONS] [ARGS]
```

Start a session, give it a prompt, and own it in the foreground until it settles.

It exits with how the session ended: 0 settled, 1 an agent failed, 2 the budget ran out, 3 timed out, 4 it needs a
person, and 130 cancelled, by Ctrl+C or `session stop` too. Ctrl+C runs the owner's shutdown first, which keeps the
session resumable. What it cannot run as given, a name that is taken among it, exits 64 before any cost, and a
commit to its journal that fails ends it with exit 74, as a kill would, leaving it to `session resume`.

The team is the project file, `platoon-harness.toml`, or the file --team names over it, and --harness adds a role
on that harness. The prompt goes to the one agent the session starts, or to --to. A person's message steers: it
lands at the earliest boundary the harness has. The session's name is on stderr at the start, so another shell can
reach it.

With --json, stdout holds one JSON line per event of the session's journal, then one for its ending, and nothing
else. An approval left to ask, with nobody attached to answer, ends the run at once with exit 4, and never prompts:
--approvals answers every one.

For example:

    platoon-harness run "Fix the flaky test in tests/test_cart.py"
    git diff | platoon-harness run - --json --harness codex --approvals deny > events.jsonl
    platoon-harness run --team crew.toml --to @lead --prompt-file task.md --plan-login --timeout 30m

**Arguments**:

* `PROMPT`: What to ask. `-`, or none when stdin is no terminal, reads stdin to its end.

**Parameters**:

* `--team`: A team file, over the project file.
* `--harness`: A role on this harness, whose agent takes its name, over the rest: with no team file and no project file, a team
        of one.
* `--set`: A line of TOML over the rest, such as `budget.usd = 5`. Give it again for more.
* `--trust`: Run what the project file or the team file names to run: a command harness, a `module:attr` or an auth
        profile.
* `--to`: Who the prompt is for, as `@agent`, when the session starts more than one.
* `--prompt-file`: A file whose text is the prompt.
* `--name`: The session's name. Left out, one is made from the time.
* `--approvals`: Answer every approval this way, over each role's own policy. The manifest keeps it. *[choices: ask, deny, allow]*
* `--plan-login`: Several agents may run headless on one plan login: say so to say this is your own work.
* `--timeout`: How long to wait for it to settle, such as 90s, 30m or 2h. Past it the run ends with exit 3.
* `--json`: Print JSONL on stdout.

### platoon-harness serve

```console
platoon-harness serve [OPTIONS]
```

Start a session and keep its runtime in the foreground, with no client attached, for a supervisor.

Clients attach as guests by its name, which is on stderr. SIGTERM, or Ctrl+C, runs the owner's shutdown, which
keeps it resumable. It exits 0 once that is done or once the session has closed and drained, 74 when a commit to its
journal fails, which ends it as a kill would, and 78 when the team cannot run.

For example:

    platoon-harness serve --team crew.toml --name nightly
    platoon-harness message send nightly --to @lead --gist "Start on the backlog"

**Parameters**:

* `--team`: A team file, over the project file.
* `--harness`: A role on this harness, whose agent takes its name, over the rest: with no team file and no project file, a team
        of one.
* `--set`: A line of TOML over the rest, such as `budget.usd = 5`. Give it again for more.
* `--trust`: Run what the project file or the team file names to run: a command harness, a `module:attr` or an auth
        profile.
* `--name`: The session's name. Left out, one is made from the time.
* `--approvals`: Answer every approval this way, over each role's own policy. *[choices: ask, deny, allow]*
* `--plan-login`: Several agents may run headless on one plan login: say so to say this is your own work.

### platoon-harness events

```console
platoon-harness events [OPTIONS] SESSION
```

Print a session's events past a cursor, live or closed, writing nothing.

With --json each line is one event's JSON, carrying its `seq`: pass the last one as --after to go on exactly where
you stopped, across a runtime that stopped and resumed. It ends once nobody reads what it prints, and Ctrl+C ends it
with exit 130.

For example:

    platoon-harness events fix-auth
    platoon-harness events fix-auth --follow --json | jq -c 'select(.type == "message.sent")'
    platoon-harness events fix-auth --after 140 --follow

**Arguments**:

* `SESSION`: A session, by name. `platoon-harness session list` shows them. **[required]**

**Parameters**:

* `--after`: A `seq`: print only what came after it.
* `--follow`: Keep printing as the journal grows, until the session's runtime has gone and nothing more can come.
* `--json`: Print JSONL on stdout.

### platoon-harness session

Sessions, from their folders, and what can be done to one as a whole.

For example:

    platoon-harness session list
    platoon-harness session show fix-auth
    platoon-harness session stop fix-auth
    platoon-harness session resume fix-auth

#### platoon-harness session list

```console
platoon-harness session list [OPTIONS]
```

List the sessions under the state root, from their folders.

Each has its name, whether a runtime holds it now, and its state, which is unknown for one whose journal cannot be
read, and stderr says why.

For example:

    platoon-harness session list
    platoon-harness session list --json | jq -r '.[] | select(.live) | .name'

**Parameters**:

* `--json`: Say it as JSON.

#### platoon-harness session show

```console
platoon-harness session show SESSION
```

Say how a session stands: who is working, on what, what is blocked, and where you must act.

Each place you must act comes with the command that would settle it. `session status`, `view watch` and `attention
list` say the same as JSON.

For example:

    platoon-harness session show fix-auth

**Arguments**:

* `SESSION`: A session, by name. **[required]**

#### platoon-harness session stop

```console
platoon-harness session stop SESSION
```

Stop a session's runtime as its owner would, keeping the session resumable.

Turns are interrupted and harnesses end. It sends SIGTERM to the runtime, which `run`, `serve`, `session resume` and
a detached runtime take as the owner's stop, and follows the session until the runtime has let go.

For example:

    platoon-harness session stop fix-auth
    platoon-harness session resume fix-auth

**Arguments**:

* `SESSION`: A session, by name. **[required]**

#### platoon-harness session resume

```console
platoon-harness session resume [OPTIONS] SESSION
```

Restart a session whose runtime has gone, and own it in the foreground until it settles.

Its harnesses come back, and a turn they were cut off in is told and woken, which can spend money. It prints what
its runtime does, from its start, and exits as `run` does.

For example:

    platoon-harness session resume fix-auth
    platoon-harness session resume fix-auth --json --timeout 10m

**Arguments**:

* `SESSION`: A session, by name. `platoon-harness session list` shows them. **[required]**

**Parameters**:

* `--timeout`: How long to wait for it to settle, such as 90s, 30m or 2h.
* `--json`: Print JSONL on stdout.

#### platoon-harness session refold

```console
platoon-harness session refold SESSION
```

Bring a session's views up to its journal while no runtime holds it, as a runtime does as it opens, writing no event, so that its history and the provenance queries answer again after an upgrade changed a view.

Refused `unavailable` while a runtime holds the session, whose views are current.

For example:

    platoon-harness session refold fix-auth

**Arguments**:

* `SESSION`: A session, by name. **[required]**

#### platoon-harness session cancel

```console
platoon-harness session cancel [OPTIONS] SESSION
```

Stop now: every live agent ends, cancelled.

Refused `conflict` once the session has stopped.

For example:

    platoon-harness session cancel SESSION

**Arguments**:

* `SESSION`: A session, by name. `platoon-harness session list` shows them. **[required]**

**Parameters**:

* `--key`: Name this command, so that running it again with the same key is one operation.

#### platoon-harness session close

```console
platoon-harness session close [OPTIONS] SESSION
```

Drain: nothing new starts, and what is in flight finishes.

Refused `conflict` when the session is not open, and with `--if-done` when `platoon-harness session status` would no longer say done, as a message that got in first makes it.

For example:

    platoon-harness session close SESSION

**Arguments**:

* `SESSION`: A session, by name. `platoon-harness session list` shows them. **[required]**

**Parameters**:

* `--if-done, --no-if-done`: Close only if `platoon-harness session status` still says done.
* `--key`: Name this command, so that running it again with the same key is one operation.

#### platoon-harness session ending

```console
platoon-harness session ending SESSION
```

What this session has come to: its state, why, each agent and its last report, what was spent with its labels, every gap, each workspace left in place, with why and the commands that let it go, and the agents whose last look never finished, which left what they changed unobserved.

For example:

    platoon-harness session ending SESSION

**Arguments**:

* `SESSION`: A session, by name. `platoon-harness session list` shows them. **[required]**

#### platoon-harness session manifest

```console
platoon-harness session manifest SESSION
```

Name the stored manifest of this session, which holds no secrets.

For example:

    platoon-harness session manifest SESSION

**Arguments**:

* `SESSION`: A session, by name. `platoon-harness session list` shows them. **[required]**

#### platoon-harness session status

```console
platoon-harness session status SESSION
```

Say whether this session is settled and what remains.

Asked in a turn, that turn is among `blockers`. A message can un-settle it; only close ends it. `stalled` says it has stopped short of `until` with nothing scheduled, so only someone acting can move it.

For example:

    platoon-harness session status SESSION

**Arguments**:

* `SESSION`: A session, by name. `platoon-harness session list` shows them. **[required]**

### platoon-harness team

What a team allows and what its agents are told, before any cost.

Each reads the project file `platoon-harness.toml`, or the team file named over it, and starts nothing.

For example:

    platoon-harness team check crew.toml
    platoon-harness team show --resolved > resolved.toml
    platoon-harness team told --harness codex

#### platoon-harness team check

```console
platoon-harness team check [OPTIONS] [ARGS]
```

Say every problem a session would meet in a team, at once, before any cost.

It exits 78 when one is an error.

**Arguments**:

* `TEAM`: A team file. Left out, the project file.

**Parameters**:

* `--harness`: A role on this harness, whose agent takes its name, over the rest: with no team file and no project file, a team
        of one.
* `--set`: A line of TOML over the rest, such as `budget.usd = 5`. Give it again for more.
* `--trust`: Run what the project file or the team file names to run: a command harness, a `module:attr` or an auth
        profile.
* `--plan-login`: Several agents may run headless on one plan login, as `run --plan-login` says.

#### platoon-harness team show

```console
platoon-harness team show [OPTIONS] [ARGS]
```

Say what a team allows, in plain words or as TOML that loads back to the same team.

**Arguments**:

* `TEAM`: A team file. Left out, the project file.

**Parameters**:

* `--harness`: A role on this harness, whose agent takes its name, over the rest: with no team file and no project file, a team
        of one.
* `--set`: A line of TOML over the rest, such as `budget.usd = 5`. Give it again for more.
* `--trust`: Run what the project file or the team file names to run: a command harness, a `module:attr` or an auth
        profile.
* `--resolved`: The expansion, which is what a session's manifest keeps, with no secret in it.

#### platoon-harness team told

```console
platoon-harness team told [OPTIONS] [ARGS]
```

Say what an agent of each role would be told at launch.

That is all the runtime adds to its harness. No harness starts.

**Arguments**:

* `TEAM`: A team file. Left out, the project file.

**Parameters**:

* `--harness`: A role on this harness, whose agent takes its name, over the rest: with no team file and no project file, a team
        of one.
* `--set`: A line of TOML over the rest, such as `budget.usd = 5`. Give it again for more.
* `--trust`: Run what the project file or the team file names to run: a command harness, a `module:attr` or an auth
        profile.

### platoon-harness init

```console
platoon-harness init
```

Write a starter `platoon-harness.toml` from the harnesses on PATH, and say how to run it.

A lead on the first, which starts workers on the second. It never overwrites one. It writes no auth profile, so it
passes over `openhands`, which signs in only with a key from one.

For example:

    platoon-harness init
    platoon-harness team show
    platoon-harness run "Fix the flaky test"

### platoon-harness doctor

```console
platoon-harness doctor [OPTIONS]
```

Say whether this machine can run sessions, and what it has.

Each harness on PATH, with its version and the kind of its login, `openhands` where the SDK's `openhands` extra is
installed, and where not the interpreter to install it for, pi's Node, where sessions and sockets live, and what is
installed. It exits 0 when it can run sessions, and 78 when it cannot. A login's kind comes from the harness's own
status command: no account name is kept, and no credential file is read.

For example:

    platoon-harness doctor
    platoon-harness doctor --json | jq .harnesses

**Parameters**:

* `--json`: Say it as one JSON object.

### platoon-harness extension

What is installed, read from metadata alone.

Nothing is imported, and installing activates nothing.

For example:

    platoon-harness extension list

#### platoon-harness extension list

```console
platoon-harness extension list [OPTIONS]
```

List every installed driver and extension, with its distribution, and any problem among them.

**Parameters**:

* `--json`: Say it as one JSON object.

### platoon-harness annotate

```console
platoon-harness annotate --target STR --kind LITERAL[REWARD, CREDIT] --producer STR --producer-version STR --scope LITERAL[LOCAL, TEAM] --status LITERAL[SCORED, INVALID, ERROR, CANCELLED, UNSCORED] --head-seq INT [OPTIONS] SESSION
```

Say what an estimator found of an event, a `reward` or a `credit`, in `annotations.sqlite` beside the journal and never in it, on a live session or a closed one, with no runtime.

It is `--producer`'s at `--producer-version`, run with `--params`, of the trace up to `--head-seq`, at or below which the target and each ref of `--evidence` lie: an estimate, never a fact. `--value` is given when `--status` is `scored` alone, so nothing unscored is zero. The same statement again is answered with the first, and another under the same producer, version, params, target and kind is refused `conflict`.

For example:

    platoon-harness annotate SESSION --target TARGET --kind KIND --producer PRODUCER --producer-version PRODUCER_VERSION --scope SCOPE --status STATUS --head-seq HEAD_SEQ

**Arguments**:

* `SESSION`: A session, by name. `platoon-harness session list` shows them. **[required]**

**Parameters**:

* `--target`: The event it is about, by its ref, `stream@version`. **[required]**
* `--kind`: `reward` or `credit`. **[required]** *[choices: reward, credit]*
* `--producer`: The estimator that made it, by name. **[required]**
* `--producer-version`: The estimator's version. **[required]**
* `--params`: What the estimator was run with, kept as `params_hash`. As JSON.
* `--scope`: `local` for the target's own, `team` for what its team shares. **[required]** *[choices: local, team]*
* `--status`: `scored`, `invalid`, `error`, `cancelled` or `unscored`. **[required]** *[choices: scored, invalid, error, cancelled, unscored]*
* `--value`: The estimate, given when `--status` is `scored` alone.
* `--evidence`: The refs of the events it rests on.
* `--head-seq`: The head the estimator read at, which names the trace it is about. **[required]**

### platoon-harness annotations

```console
platoon-harness annotations [OPTIONS] SESSION
```

List what estimators said of one event, or of every one, oldest first, each with its producer and version and never summed. Nothing an agent can reach reads these.

For example:

    platoon-harness annotations fix-auth --target agent/lead@1

**Arguments**:

* `SESSION`: A session, by name. `platoon-harness session list` shows them. **[required]**

**Parameters**:

* `--target`: The event they are about, by its ref, `stream@version`.

### platoon-harness agent

The `agent` ops, each on one session, with the arguments an agent's `ph agent.<op>` takes as flags.

#### platoon-harness agent cancel

```console
platoon-harness agent cancel --agent STR [OPTIONS] SESSION
```

End an agent now, mid-turn if need be, with the children that cannot outlive it.

Its tasks reopen. Refused `conflict` when it has ended already: nothing to do. `not_permitted` when it is not below you.

For example:

    platoon-harness agent cancel SESSION --agent AGENT

**Arguments**:

* `SESSION`: A session, by name. `platoon-harness session list` shows them. **[required]**

**Parameters**:

* `--agent`: An agent, as `@agent`. `platoon-harness peers` shows who is here. **[required]**
* `--key`: Name this command, so that running it again with the same key is one operation.

#### platoon-harness agent interrupt

```console
platoon-harness agent interrupt --agent STR [OPTIONS] SESSION
```

Stop an agent's turn at the boundary its harness can, or the turn it is on its way to, and with `--below` those of all below it.

It stops turns, not waits. What was waiting for each then wakes nothing and stays unread for its next turn, and what comes after wakes it as usual. All live on. Refused `conflict` when it would stop no turn, as before a first turn begins, which no harness can stop. `not_permitted` when one is not below you.

For example:

    platoon-harness agent interrupt SESSION --agent AGENT

**Arguments**:

* `SESSION`: A session, by name. `platoon-harness session list` shows them. **[required]**

**Parameters**:

* `--agent`: An agent, as `@agent`. `platoon-harness peers` shows who is here. **[required]**
* `--below, --no-below`: Stop the turns below it too.
* `--key`: Name this command, so that running it again with the same key is one operation.

#### platoon-harness agent list

```console
platoon-harness agent list SESSION
```

List every agent of this session, live or ended, as `agent`, which is what the ops that take one go by.

For example:

    platoon-harness agent list SESSION

**Arguments**:

* `SESSION`: A session, by name. `platoon-harness session list` shows them. **[required]**

#### platoon-harness agent release

```console
platoon-harness agent release --agent STR [OPTIONS] SESSION
```

Return a held agent to the runtime.

Refused `conflict` when it is not held.

For example:

    platoon-harness agent release SESSION --agent AGENT

**Arguments**:

* `SESSION`: A session, by name. `platoon-harness session list` shows them. **[required]**

**Parameters**:

* `--agent`: An agent, as `@agent`. `platoon-harness peers` shows who is here. **[required]**
* `--key`: Name this command, so that running it again with the same key is one operation.

#### platoon-harness agent retire

```console
platoon-harness agent retire --agent STR [OPTIONS] SESSION
```

Retire an agent that has stopped working: it leaves the team, and its history stays.

Refused `conflict` while it is at work, in a turn or on its way to one, or while children that would end with it are, and when it has ended already. `platoon-harness agent cancel` stops one now.

For example:

    platoon-harness agent retire SESSION --agent AGENT

**Arguments**:

* `SESSION`: A session, by name. `platoon-harness session list` shows them. **[required]**

**Parameters**:

* `--agent`: An agent, as `@agent`. `platoon-harness peers` shows who is here. **[required]**
* `--key`: Name this command, so that running it again with the same key is one operation.

#### platoon-harness agent spawn

```console
platoon-harness agent spawn --name STR --child-role STR [OPTIONS] SESSION
```

Start a new agent in a role you may spawn.

Put anything longer than `--goal` in `--body`. With neither it starts idle and takes no turn until a message wakes it. What it says at the end of a turn comes back to you, and so does how it ends, so a parent can simply wait. Refused `not_permitted` for a role or limit outside your reach, `over_budget` when the budget cannot cover another agent, and `conflict` when the name is taken, the session is closing or its spawner finished: use another name, or stop. `not_found` when no such role exists. `unsupported` for `--stays` on a harness that cannot stay.

For example:

    platoon-harness agent spawn SESSION --name NAME --child-role CHILD_ROLE

**Arguments**:

* `SESSION`: A session, by name. `platoon-harness session list` shows them. **[required]**

**Parameters**:

* `--name`: A name nobody in this session has used. **[required]**
* `--child-role`: The role to start it in. **[required]**
* `--goal`: What it should do, at most 280 characters.
* `--body`: Anything longer than the gist. --body-file reads it from a file.
* `--body-file`: A file whose bytes are the body.
* `--stays, --no-stays`: Whether it stays after its task for the next message. Left out, its role decides, else it does not.
* `--based-on`: Refs this write rests on.
* `--key`: Name this command, so that running it again with the same key is one operation.

#### platoon-harness agent status

```console
platoon-harness agent status --agent STR SESSION
```

Show one agent's state, live or ended, and its open `turn`.

Refused `not_found` when no such agent ever existed, and `not_permitted` when it is not below you.

For example:

    platoon-harness agent status SESSION --agent AGENT

**Arguments**:

* `SESSION`: A session, by name. `platoon-harness session list` shows them. **[required]**

**Parameters**:

* `--agent`: An agent, as `@agent`. `platoon-harness peers` shows who is here. **[required]**

#### platoon-harness agent takeover

```console
platoon-harness agent takeover --agent STR [OPTIONS] SESSION
```

Hold an agent's deliveries so a human can drive its native session, which records the gap from here.

Refused `unsupported` with no resume.

For example:

    platoon-harness agent takeover SESSION --agent AGENT

**Arguments**:

* `SESSION`: A session, by name. `platoon-harness session list` shows them. **[required]**

**Parameters**:

* `--agent`: An agent, as `@agent`. `platoon-harness peers` shows who is here. **[required]**
* `--key`: Name this command, so that running it again with the same key is one operation.

#### platoon-harness agent unread

```console
platoon-harness agent unread --agent STR SESSION
```

List what waits for an agent's next handover, oldest first, which the roster's `unread` counts: each entry with the `delivery` it would land by now, and the true `total`.

Refused `not_permitted` for an agent, which reads its own inbox and channels, and `not_found` when no such agent ever existed.

For example:

    platoon-harness agent unread SESSION --agent AGENT

**Arguments**:

* `SESSION`: A session, by name. `platoon-harness session list` shows them. **[required]**

**Parameters**:

* `--agent`: An agent, as `@agent`. `platoon-harness peers` shows who is here. **[required]**

### platoon-harness approval

The `approval` ops, each on one session, with the arguments an agent's `ph approval.<op>` takes as flags.

#### platoon-harness approval resolve

```console
platoon-harness approval resolve --id STR --verdict LITERAL[ALLOW, DENY] --expected-version INT [OPTIONS] SESSION
```

Decide an approval.

The first commit wins, and the loser is refused `conflict`, told who won and how.

For example:

    platoon-harness approval resolve SESSION --id ID --verdict VERDICT --expected-version EXPECTED_VERSION

**Arguments**:

* `SESSION`: A session, by name. `platoon-harness session list` shows them. **[required]**

**Parameters**:

* `--id`: The approval, as its row in `platoon-harness attention list` names it. **[required]**
* `--verdict`: `allow` or `deny`. **[required]** *[choices: allow, deny]*
* `--expected-version`: Its version as you saw it, so that a decision someone made since stands. **[required]**
* `--via`: What it was decided through, which a loser is told.
* `--key`: Name this command, so that running it again with the same key is one operation.

### platoon-harness attention

The `attention` ops, each on one session, with the arguments an agent's `ph attention.<op>` takes as flags.

#### platoon-harness attention list

```console
platoon-harness attention list SESSION
```

List what needs a human now, each with the actions that would settle it.

For example:

    platoon-harness attention list SESSION

**Arguments**:

* `SESSION`: A session, by name. `platoon-harness session list` shows them. **[required]**

### platoon-harness blob

The `blob` ops, each on one session, with the arguments an agent's `ph blob.<op>` takes as flags.

#### platoon-harness blob get

```console
platoon-harness blob get --ref STR SESSION
```

Read the body an event carries: pass its `--ref`, or a `rest`, from any result.

An agent reads what it was handed or wrote. A long body comes back cut: `lines` says how many exist and `rest` is the ref to read on with. `text` is null for a binary body. Refused `not_found` when there is no such body to read, or it was redacted. `invalid`, with `lines`, for a range past the end.

For example:

    platoon-harness blob get SESSION --ref REF

**Arguments**:

* `SESSION`: A session, by name. `platoon-harness session list` shows them. **[required]**

**Parameters**:

* `--ref`: A `--ref` or `rest` from a result. **[required]**

### platoon-harness board

The `board` ops, each on one session, with the arguments an agent's `ph board.<op>` takes as flags.

#### platoon-harness board get

```console
platoon-harness board get --board STR --name STR [OPTIONS] SESSION
```

Read one object, its latest version or `--version`, and of a text body the lines of `--range`, written `L10-40`.

A long body comes back cut: `lines` says how many exist and `rest` is a ref. Pass it to `platoon-harness blob get` to read on. `text` is null for a binary body. Refused `invalid`, with `lines`, for a range past the end. `not_found` when the board, object or version does not exist.

For example:

    platoon-harness board get SESSION --board BOARD --name NAME

**Arguments**:

* `SESSION`: A session, by name. `platoon-harness session list` shows them. **[required]**

**Parameters**:

* `--board`: The board. `platoon-harness channel list` names them. **[required]**
* `--name`: The object's name. **[required]**
* `--version`: A version; the latest if left out.
* `--range`: Lines of the body, as `L10-40`.

#### platoon-harness board post

```console
platoon-harness board post --board STR --name STR --gist STR [OPTIONS] SESSION
```

Create an object on a board, at version 1.

Put anything longer than `--gist` in `--body`. Refused `conflict`, with the current version, when the name exists. Read it, then `platoon-harness board revise`. `not_found` when no such board exists.

For example:

    platoon-harness board post SESSION --board BOARD --name NAME --gist GIST

**Arguments**:

* `SESSION`: A session, by name. `platoon-harness session list` shows them. **[required]**

**Parameters**:

* `--board`: The board. `platoon-harness channel list` names them. **[required]**
* `--name`: The object's name. **[required]**
* `--gist`: What readers see first, at most 280 characters. **[required]**
* `--body`: Anything longer than the gist. --body-file reads it from a file.
* `--body-file`: A file whose bytes are the body.
* `--fields`: Short JSON values. `platoon-harness board query` can match them with `where`. As JSON.
* `--based-on`: Refs this write rests on.
* `--key`: Name this command, so that running it again with the same key is one operation.

#### platoon-harness board query

```console
platoon-harness board query --board STR [OPTIONS] SESSION
```

Find objects by `--prefix` of name, `--author`, exact `--where` on fields, or `--text` over names, gists and fields, never bodies.

Results are gists with exact refs, the true `total`, and a `cursor` to pass as `--after`. `--history` includes old versions. Refused `unsupported` for `--text` when this SQLite has no FTS5: use structured filters. `not_found` when no such board exists.

For example:

    platoon-harness board query SESSION --board BOARD

**Arguments**:

* `SESSION`: A session, by name. `platoon-harness session list` shows them. **[required]**

**Parameters**:

* `--board`: The board. `platoon-harness channel list` names them. **[required]**
* `--prefix`: Only names starting with this.
* `--author`: Only what this author wrote.
* `--where`: Exact matches on `fields`. As JSON.
* `--text`: Words to find in names, gists and fields.
* `--history, --no-history`: Include old versions.
* `--after`: A `cursor` from an earlier query.
* `--limit`: The most results to return. *[default: 20]*

#### platoon-harness board revise

```console
platoon-harness board revise --board STR --name STR --gist STR --expected-version INT [OPTIONS] SESSION
```

Add a version to an object.

`--expected-version` is the version you read. Refused `conflict`, with the current version, when someone got there first and nothing was overwritten: read it, then revise again. `not_found` when no such object exists.

For example:

    platoon-harness board revise SESSION --board BOARD --name NAME --gist GIST --expected-version EXPECTED_VERSION

**Arguments**:

* `SESSION`: A session, by name. `platoon-harness session list` shows them. **[required]**

**Parameters**:

* `--board`: The board. `platoon-harness channel list` names them. **[required]**
* `--name`: The object's name. **[required]**
* `--gist`: What readers see first, at most 280 characters. **[required]**
* `--body`: Anything longer than the gist. --body-file reads it from a file.
* `--body-file`: A file whose bytes are the body.
* `--fields`: Short JSON values. `platoon-harness board query` can match them with `where`. As JSON.
* `--based-on`: Refs this write rests on.
* `--expected-version`: The version you read. **[required]**
* `--key`: Name this command, so that running it again with the same key is one operation.

### platoon-harness body

The `body` ops, each on one session, with the arguments an agent's `ph body.<op>` takes as flags.

#### platoon-harness body tombstone

```console
platoon-harness body tombstone --sha256 STR [OPTIONS] SESSION
```

Redact a body.

Reads stop now; a daemon erases the bytes. Events citing the hash stay whole.

For example:

    platoon-harness body tombstone SESSION --sha256 SHA256

**Arguments**:

* `SESSION`: A session, by name. `platoon-harness session list` shows them. **[required]**

**Parameters**:

* `--sha256`: The body's hash, its ref without `sha256:`. **[required]**
* `--key`: Name this command, so that running it again with the same key is one operation.

### platoon-harness budget

The `budget` ops, each on one session, with the arguments an agent's `ph budget.<op>` takes as flags.

#### platoon-harness budget set

```console
platoon-harness budget set [OPTIONS] SESSION
```

Set a scope's limits and turn estimate.

Refused `invalid` for a `tokens` or `usd` limit with no estimate in that unit, its own or, for a role, the shared one, which a turn nobody measured whole could not be charged.

For example:

    platoon-harness budget set SESSION

**Arguments**:

* `SESSION`: A session, by name. `platoon-harness session list` shows them. **[required]**

**Parameters**:

* `--scope`: `shared`, or `role:<name>` for one role's. *[default: shared]*
* `--limits`: A limit per unit, such as `{"usd": 5, "wall": 1800}`, with `wall` in seconds. As JSON.
* `--estimate`: What a turn is reserved before it is measured, per unit, and charged on top of what was measured when nobody measured it whole. A `tokens` or `usd` limit needs one. As JSON.
* `--key`: Name this command, so that running it again with the same key is one operation.

#### platoon-harness budget status

```console
platoon-harness budget status SESSION
```

Each limit with what is spent, held, and how well that is known.

For example:

    platoon-harness budget status SESSION

**Arguments**:

* `SESSION`: A session, by name. `platoon-harness session list` shows them. **[required]**

### platoon-harness channel

The `channel` ops, each on one session, with the arguments an agent's `ph channel.<op>` takes as flags.

#### platoon-harness channel create

```console
platoon-harness channel create --name STR --kind LITERAL[TOPIC, QUEUE, BOARD] [OPTIONS] SESSION
```

Create a topic, queue or board that you can read and write.

`--readers` and `--writers` add others: each selector means those it covers now, so a later arrival is not among them. Refused `not_permitted` when one reaches beyond you, or for `wake` or `steer`, which belong to the reader: use `next-turn`. `invalid` when one covers nobody yet. `conflict` when the name is taken: choose another.

For example:

    platoon-harness channel create SESSION --name NAME --kind KIND

**Arguments**:

* `SESSION`: A session, by name. `platoon-harness session list` shows them. **[required]**

**Parameters**:

* `--name`: A name no channel of this kind has. **[required]**
* `--kind`: What sort of channel this is. **[required]** *[choices: topic, queue, board]*
* `--readers`: Who else may read: selectors, such as `children`.
* `--writers`: Who else may write: selectors, such as `role:x`.
* `--delivery`: `pull` or `next-turn`, the most you may choose. *[choices: pull, next-turn, wake, steer]*
* `--key`: Name this command, so that running it again with the same key is one operation.

#### platoon-harness channel list

```console
platoon-harness channel list [OPTIONS] SESSION
```

List the channels you may use, in `channels`, with the true `total` and a `cursor` to pass as `--after`, or none at the end.

Pass `name` as `to` or `channel` for a topic, `queue` for a queue, `board` for a board.

For example:

    platoon-harness channel list SESSION

**Arguments**:

* `SESSION`: A session, by name. `platoon-harness session list` shows them. **[required]**

**Parameters**:

* `--after`: A `cursor` from an earlier call.

### platoon-harness contributors

```console
platoon-harness contributors --ref STR [OPTIONS] SESSION
```

Name each maker a walk back from an outcome reaches along citations, causes and ancestry, in the order it reached them, with the kinds that reached each and the gaps on the way, and apart from them each maker whose work was only handed to one of them, which the walk does not go through.

It walks at most 4096 events and says when it stopped short. It weighs and ranks nobody: credit is an annotation. Pass `cursor` as `--after` for the next page. Refused `invalid` for a range or a body's hash, which name no event, and `not_found` for no such event.

For example:

    platoon-harness contributors SESSION --ref REF

**Arguments**:

* `SESSION`: A session, by name. `platoon-harness session list` shows them. **[required]**

**Parameters**:

* `--ref`: An event's ref, `stream@version`. **[required]**
* `--after`: A `cursor` from an earlier answer.

### platoon-harness effect

The `effect` ops, each on one session, with the arguments an agent's `ph effect.<op>` takes as flags.

#### platoon-harness effect settle

```console
platoon-harness effect settle --id INT --happened BOOL [OPTIONS] SESSION
```

Say whether an uncertain effect happened, which is left to a person when nothing else can tell.

Refused `conflict` once it is no longer uncertain, as when recovery got there first.

For example:

    platoon-harness effect settle SESSION --id ID --happened

**Arguments**:

* `SESSION`: A session, by name. `platoon-harness session list` shows them. **[required]**

**Parameters**:

* `--id`: The effect, as its row in `platoon-harness attention list` names it. **[required]**
* `--happened, --no-happened`: Whether it happened. **[required]**
* `--key`: Name this command, so that running it again with the same key is one operation.

### platoon-harness episode

The `episode` ops, each on one session, with the arguments an agent's `ph episode.<op>` takes as flags.

#### platoon-harness episode close

```console
platoon-harness episode close [OPTIONS] SESSION
```

Close the open episode, or refuse `conflict` when none is open.

For example:

    platoon-harness episode close SESSION

**Arguments**:

* `SESSION`: A session, by name. `platoon-harness session list` shows them. **[required]**

**Parameters**:

* `--outcome`: What the span came to. As JSON.
* `--key`: Name this command, so that running it again with the same key is one operation.

#### platoon-harness episode open

```console
platoon-harness episode open --episode STR [OPTIONS] SESSION
```

Open a span of this session with one outcome.

Only events inside one can become training data.

For example:

    platoon-harness episode open SESSION --episode EPISODE

**Arguments**:

* `SESSION`: A session, by name. `platoon-harness session list` shows them. **[required]**

**Parameters**:

* `--episode`: A name for the span. **[required]**
* `--key`: Name this command, so that running it again with the same key is one operation.

### platoon-harness exposure

```console
platoon-harness exposure --agent STR --ref STR [OPTIONS] SESSION
```

Say whether an event reached an agent through us before another, `--before`, or by now: `seen`, with each offer of it its harness said it took and each compaction since, `not_seen`, or `unknown`, with the offers its harness never said it took, the surfaces no result proves observed and the gaps content could have come through.

Seen means handed over and taken, never understood, and an agent with a shell never answers `not_seen`. Refused `invalid` for a range or a body's hash, which name no event, and for a person or a program, whose reads are no evidence, and `not_found` when no such event or agent exists.

For example:

    platoon-harness exposure SESSION --agent AGENT --ref REF

**Arguments**:

* `SESSION`: A session, by name. `platoon-harness session list` shows them. **[required]**

**Parameters**:

* `--agent`: The agent, as `@agent`. **[required]**
* `--ref`: An event's ref, `stream@version`. **[required]**
* `--before`: The ref of the event the answer stops before. Left out, the head.

### platoon-harness lineage

```console
platoon-harness lineage --ref STR [OPTIONS] SESSION
```

Show one hop back from an event: who made it, in which turn and model call, what it cites, each with its citer's exposure, what it followed from, its previous version or a commit's parents, and a page of what its maker was offered and the gaps in its record below it, newest first, with true totals.

Pass `cursor` as `--after` for the next page. Refused `invalid` for a range or a body's hash, which name no event, and `not_found` for no such event.

For example:

    platoon-harness lineage SESSION --ref REF

**Arguments**:

* `SESSION`: A session, by name. `platoon-harness session list` shows them. **[required]**

**Parameters**:

* `--ref`: An event's ref, `stream@version`. **[required]**
* `--after`: A `cursor` from an earlier answer.

### platoon-harness message

The `message` ops, each on one session, with the arguments an agent's `ph message.<op>` takes as flags.

#### platoon-harness message read

```console
platoon-harness message read [OPTIONS] SESSION
```

Read your inbox, or `#channel` or `+group`, past `--after`, a `cursor` from an earlier read, which an agent's read acks.

Left out, an agent reads on from where it left off. `--sender` and `--thread` filter, and a filtered read leaves unread what it skipped. `--bodies` adds body `text`, recorded apart from gists; a long one comes back cut, with `rest` a ref, and past what one result holds `text` is null. Pass `rest` or the entry's `ref` to `platoon-harness blob get`. `behind` counts what is left, up to 4096. Refused `not_permitted` when you do not read this channel. Call `platoon-harness channel list` to see yours. `invalid` for an `--after` past every event: leave it out.

For example:

    platoon-harness message read SESSION

**Arguments**:

* `SESSION`: A session, by name. `platoon-harness session list` shows them. **[required]**

**Parameters**:

* `--channel`: `#channel` or `+group`; your own inbox if left out.
* `--after`: A `cursor` from an earlier read.
* `--limit`: The most entries to return. *[default: 32]*
* `--sender`: Only entries from this agent.
* `--thread`: Only entries of this thread.
* `--bodies, --no-bodies`: Add each body's `text`.

#### platoon-harness message send

```console
platoon-harness message send --to STR --gist STR [OPTIONS] SESSION
```

Send to `@agent`, `#channel` or `+group`.

`--gist`, at most 280 characters, is what readers see first; put anything longer in `--body`. To reply, set `--to` to the entry's `sender` and `--reply-to` to its `ref`. Refused `not_permitted` when you cannot reach the target. Call `platoon-harness peers` for agents, `platoon-harness channel list` for channels. `undeliverable` when the agent has ended: tell someone else. `queue_full` when its inbox is full: try later. `not_found` when `--reply-to` names nothing you can read. `conflict` once the session is closing, when it would reach nobody.

For example:

    platoon-harness message send SESSION --to TO --gist GIST

**Arguments**:

* `SESSION`: A session, by name. `platoon-harness session list` shows them. **[required]**

**Parameters**:

* `--to`: `@agent`, `#channel` or `+group`. **[required]**
* `--gist`: What readers see first, at most 280 characters. **[required]**
* `--body`: Anything longer than the gist. --body-file reads it from a file.
* `--body-file`: A file whose bytes are the body.
* `--thread`: A thread id. `--reply-to` sets it for you.
* `--reply-to`: The `ref` of the entry you answer.
* `--based-on`: Refs this write rests on.
* `--key`: Name this command, so that running it again with the same key is one operation.

### platoon-harness ops

The `ops` ops, each on one session, with the arguments an agent's `ph ops.<op>` takes as flags.

#### platoon-harness ops list

```console
platoon-harness ops list SESSION
```

List the ops this caller holds a grant for, with their schemas.

For example:

    platoon-harness ops list SESSION

**Arguments**:

* `SESSION`: A session, by name. `platoon-harness session list` shows them. **[required]**

### platoon-harness peers

```console
platoon-harness peers [OPTIONS] SESSION
```

List whom you may message directly now, in `platoon-harness peers`, with the true `total` and a `cursor` to pass as `--after`, or none at the end.

Targets change as agents come and go, so ask rather than remember. `roles` lists the roles you may start an agent in.

For example:

    platoon-harness peers SESSION

**Arguments**:

* `SESSION`: A session, by name. `platoon-harness session list` shows them. **[required]**

**Parameters**:

* `--after`: A `cursor` from an earlier call.

### platoon-harness task

The `task` ops, each on one session, with the arguments an agent's `ph task.<op>` takes as flags.

#### platoon-harness task add

```console
platoon-harness task add --queue STR --gist STR [OPTIONS] SESSION
```

Add a task to a queue.

`--gist` says what to do; put anything longer in `--body`. Refused `not_permitted` when you may not write this queue, and `not_found` when no such queue exists. Call `platoon-harness channel list` to see yours.

For example:

    platoon-harness task add SESSION --queue QUEUE --gist GIST

**Arguments**:

* `SESSION`: A session, by name. `platoon-harness session list` shows them. **[required]**

**Parameters**:

* `--queue`: The queue. `platoon-harness channel list` names them. **[required]**
* `--gist`: What readers see first, at most 280 characters. **[required]**
* `--body`: Anything longer than the gist. --body-file reads it from a file.
* `--body-file`: A file whose bytes are the body.
* `--based-on`: Refs this write rests on.
* `--key`: Name this command, so that running it again with the same key is one operation.

#### platoon-harness task claim

```console
platoon-harness task claim --queue STR [OPTIONS] SESSION
```

Claim the next open task, or `--task` by id.

`text` is its body; a long one comes back cut, with `rest` a ref. Pass it to `platoon-harness blob get`. The runtime renews an agent's lease while its harness is at work. `platoon-harness task complete` finds the task without being told. If your lease lapses someone else may redo the work, so make it safe to repeat. Refused `conflict`, naming the owner, when `--task` is taken, and when you hold `max_inflight` tasks: claim another, or finish one first. `not_found` when no such task or queue exists. `queue_empty` when nothing is open.

For example:

    platoon-harness task claim SESSION --queue QUEUE

**Arguments**:

* `SESSION`: A session, by name. `platoon-harness session list` shows them. **[required]**

**Parameters**:

* `--queue`: The queue. `platoon-harness channel list` names them. **[required]**
* `--task`: A task's id; the next open task if left out.
* `--key`: Name this command, so that running it again with the same key is one operation.

#### platoon-harness task complete

```console
platoon-harness task complete --queue STR [OPTIONS] SESSION
```

Finish your task, with `--gist` and `--body` as its result.

`platoon-harness task list` shows it. Refused `stale_fence` once the lease has expired, even if nobody else took the task: your work may be lost, so check the task and claim it again if it is open. `invalid` when you hold several: name `--task`.

For example:

    platoon-harness task complete SESSION --queue QUEUE

**Arguments**:

* `SESSION`: A session, by name. `platoon-harness session list` shows them. **[required]**

**Parameters**:

* `--queue`: The queue. `platoon-harness channel list` names them. **[required]**
* `--task`: A task's id; your live lease if left out.
* `--fence`: The `--fence` from your claim; your live lease if left out.
* `--gist`: The result, at most 280 characters. `platoon-harness task list` shows it.
* `--body`: Anything longer than the gist. --body-file reads it from a file.
* `--body-file`: A file whose bytes are the body.
* `--based-on`: Refs this write rests on.
* `--key`: Name this command, so that running it again with the same key is one operation.

#### platoon-harness task fail

```console
platoon-harness task fail --queue STR [OPTIONS] SESSION
```

Report that this attempt failed, and why.

Someone may claim the task again until `max_attempts`, when it is dead and shown to a human. Refused `stale_fence` once your lease has expired: the task has moved on without you.

For example:

    platoon-harness task fail SESSION --queue QUEUE

**Arguments**:

* `SESSION`: A session, by name. `platoon-harness session list` shows them. **[required]**

**Parameters**:

* `--queue`: The queue. `platoon-harness channel list` names them. **[required]**
* `--task`: A task's id; your live lease if left out.
* `--fence`: The `--fence` from your claim; your live lease if left out.
* `--gist`: The result, at most 280 characters. `platoon-harness task list` shows it.
* `--body`: Anything longer than the gist. --body-file reads it from a file.
* `--body-file`: A file whose bytes are the body.
* `--based-on`: Refs this write rests on.
* `--key`: Name this command, so that running it again with the same key is one operation.

#### platoon-harness task list

```console
platoon-harness task list --queue STR [OPTIONS] SESSION
```

List a queue's tasks, oldest first, each with its `result` once it has one, with the true `total` and a `cursor` to pass as `--after`, or none at the end.

Refused `not_permitted` when you may not read this queue, and `not_found` when no such queue exists. Call `platoon-harness channel list` to see yours.

For example:

    platoon-harness task list SESSION --queue QUEUE

**Arguments**:

* `SESSION`: A session, by name. `platoon-harness session list` shows them. **[required]**

**Parameters**:

* `--queue`: The queue. `platoon-harness channel list` names them. **[required]**
* `--state`: Only tasks in this state. *[choices: open, claimed, done, failed, dead]*
* `--after`: A `cursor` from an earlier list.
* `--limit`: The most tasks to return. *[default: 32]*

#### platoon-harness task release

```console
platoon-harness task release --queue STR [OPTIONS] SESSION
```

Give a task back unfinished, which spends no attempt.

Refused `stale_fence` when your lease has gone: there is nothing to give back.

For example:

    platoon-harness task release SESSION --queue QUEUE

**Arguments**:

* `SESSION`: A session, by name. `platoon-harness session list` shows them. **[required]**

**Parameters**:

* `--queue`: The queue. `platoon-harness channel list` names them. **[required]**
* `--task`: A task's id; your live lease if left out.
* `--fence`: The `--fence` from your claim; your live lease if left out.
* `--key`: Name this command, so that running it again with the same key is one operation.

#### platoon-harness task renew

```console
platoon-harness task renew --queue STR [OPTIONS] SESSION
```

Extend your lease, up to the queue's `lease_max`.

The runtime already does this for an agent while its harness is at work. Refused `stale_fence` when the lease has gone: claim again.

For example:

    platoon-harness task renew SESSION --queue QUEUE

**Arguments**:

* `SESSION`: A session, by name. `platoon-harness session list` shows them. **[required]**

**Parameters**:

* `--queue`: The queue. `platoon-harness channel list` names them. **[required]**
* `--task`: A task's id; your live lease if left out.
* `--fence`: The `--fence` from your claim; your live lease if left out.
* `--key`: Name this command, so that running it again with the same key is one operation.

### platoon-harness uses

```console
platoon-harness uses --ref STR [OPTIONS] SESSION
```

Show one hop forward from an event, oldest first: what cites it, what follows from it, its next version or the commits that name it a parent, and each agent it was offered to, with whether its harness said it took it, and true totals.

Pass `cursor` as `--after` for the next page. Refused `invalid` for a range or a body's hash, which name no event, and `not_found` for no such event.

For example:

    platoon-harness uses SESSION --ref REF

**Arguments**:

* `SESSION`: A session, by name. `platoon-harness session list` shows them. **[required]**

**Parameters**:

* `--ref`: An event's ref, `stream@version`. **[required]**
* `--after`: A `cursor` from an earlier answer.

### platoon-harness view

The `view` ops, each on one session, with the arguments an agent's `ph view.<op>` takes as flags.

#### platoon-harness view watch

```console
platoon-harness view watch --name LITERAL[ROSTER, ATTENTION, CHANGES] [OPTIONS] SESSION
```

A snapshot, then keyed changes.

Pass `cursor` as the next `--after`; a reader too far behind gets a new snapshot. Snapshot and cursor come from one read, so nothing commits between them.

For example:

    platoon-harness view watch SESSION --name NAME

**Arguments**:

* `SESSION`: A session, by name. `platoon-harness session list` shows them. **[required]**

**Parameters**:

* `--name`: The view. **[required]** *[choices: roster, attention, changes]*
* `--after`: The `cursor` of an earlier answer, for what changed since it.
