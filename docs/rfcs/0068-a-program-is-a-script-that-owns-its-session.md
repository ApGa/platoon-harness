# RFC 0068: A program is a script that owns its session

| | |
|---|---|
| Status | Accepted, 2026-11-08 |
| Created | 2026-11-08 |
| Authors | Apurva Gandhi (`ApGa`) |
| Builds on | [`topology/spec.py`](../../packages/sdk/src/platoon_harness/topology/spec.py), [`runtime/opening.py`](../../packages/sdk/src/platoon_harness/runtime/opening.py), [architecture section 5.1](../architecture.md#51-one-write), [section 6](../architecture.md#6-operations), [section 7](../architecture.md#completion) and [section 8](../architecture.md#8-topology), [RFC 0007](0007-topology-as-grants.md), [RFC 0048](0048-a-setting-nothing-carries-out-is-refused.md) and [RFC 0050](0050-a-script-is-a-person-or-a-program.md) |
| Discussion | Milestone 4's plan and the critiques of its first draft, kept outside this repository, and the owner's ruling of 2026-11-08 on its first question, which accepted this design |
| Implementation | `refactor!: Remove the map-reduce preset, which no program runs`, `refactor!: Drop the program key from a topology, as a program is a script`, `docs: Show a program run from Python in the topologies guide`, `fix: Name the script way when run is given a team left to its program` and `feat: Refuse a person's resume of a session left to its program` |

## Summary

A program is a Python script that starts its session as `program:<name>`, as [RFC 0050](0050-a-script-is-a-person-or-a-program.md)
lets any script, and drives it through the session's ops, so control flow never enters a team file. It keeps nothing that must
survive a restart: after a crash it is run again on the session, reads what the record holds, and sends each command under a key
it makes the same way on every run, so a command the journal answered before is answered again and acts once. A topology names no
program: its `program` key and the `Program` model go, and a team or a manifest that sets the key is refused as any unknown key is.
`until = "program"` stays, and leaves the session to the program that owns it, so a person's start of such a team, by `run`, by the
terminal UI or by `Session.start` under `human:<name>`, is refused before any cost, naming the script way, and so is a person's
resume of such a session, by `session resume`. The `map-reduce` preset,
which only a program could run, goes, and `git-swarm` keeps its channels and its `until`, its program's arguments going with the key,
until [RFC 0070](0070-a-population-gives-each-worker-one-outcome-which-its-program-records.md) gives it `live` again, as its `max_live`.

## Motivation

A topology could name an episode program, `program = "map_reduce"` or `Program(name, params)`, and nothing resolves a name to code.
[RFC 0048](0048-a-setting-nothing-carries-out-is-refused.md) made `team check` refuse every program, as a session left to one
waited for what nothing did. Two presets name one: `map-reduce` names `map_reduce`, with `parallel`, and `git-swarm` names
`population`, with `role`, `live`, `episodes`, `uncharged` and `readout`. So no team that uses either can run, and git-swarm, which
milestone 4 runs under its population program, cannot be built on the key.

A script can already own a session as a program. Since RFC 0050, `Session.start(team, principal="program:<name>")` gives a script
the session, under a name the journal keeps, with every op a person holds, and a training system starts each rollout that way
([training](../extending/training.md)). That is a program in all but its name. A program named in the team file would need, beside
it, a registry from names to code, a process to run the code in, arguments in TOML and a way to restart it: a second way to do what
a script already does, with the control flow the architecture keeps out of config
([section 6](../architecture.md#library-tier)) coming back in through a name.

## Proposal

### 1. A program is a script

A program is any Python script that starts a session as `program:<name>` and drives it:

```python
async with Session.start(team, name="reviews", principal="program:reviews") as session:
    added = await session.submit("task.add", key="review src/cart.py", queue="reviews", gist="review src/cart.py")
    ...
    await session.submit("session.close", key="close")
```

It holds every op, as a person does, since compilation grants `program` every op (section 8). Its message goes as its reader's
setting says, and its session issues no owner credential, so a guest of its runtime only reads, and it cannot detach (RFC 0050):
the runtime runs in the script's own process. Nothing in the SDK is new for it. `platoon_harness.patterns`, the library tier of
section 6, is a set of such programs' building blocks, and none is built here.

### 2. Run again, never restored

A program keeps nothing that must survive a restart. Its variables go with its process, and nothing saves them. After a crash it
is run again on the session, as `Session.resume(name)` in place of `Session.start`, and reads what the record holds.

Each command a program sends that must act once carries a key it makes from what the command is for, such as `review
src/cart.py`, which is the same on every run, through `Session.submit(op, key=...)`. The kernel dedupes on the actor and the key
(section 5.1), and a program's actor is its principal, so a command the journal answered under that key, before a crash or after
one, is answered again from the journal and acts once. The same key with other arguments is refused `key_reused`, and a command a
crash cut off before its commit runs on the next run. Session's own methods, such as `task_add`, choose a fresh key for each call,
which is right for a person and wrong for a command a program may send again.

A key makes each command one op, not each decision the same. What a program reads on a second run can differ from what it read on
the first, as agents have gone on, so a program keys a command by what it is for, and not by when it was sent.

### 3. A topology names no program

`Topology.program` and `platoon_harness.topology.Program` go, with no alias. A team that sets `program` is refused as any unknown key
of `[topology]` is: a string is no key, and a table is a preset nobody knows. `team check`'s refusal of a program goes with the key
it refused, and so does compilation's refusal of `until = "program"` with no `program` to wait for.

A session's manifest keeps its resolved team, so a session whose team named a program no longer loads. Since 13926da, `team check`
refused such a team before a session began, but before it, `team check` only warned, so a session that named one could start, the
`map-reduce` and `git-swarm` presets among them. Such a session is refused on resume, as its manifest names a key that is no key,
and its journal still reads as history. The project is unreleased, and [AGENTS.md](../../AGENTS.md) forbids a shim.

### 4. `until = "program"` leaves a session to the program that owns it

`until = "program"` stays. A session under it is done only when its program closes it, or its budget runs out (section 7), so a
session a person starts under it would wait for a close no program makes. `prepare`, which every start goes through, refuses it
under a person's principal, `human:<name>`, naming the script way, with every other problem the team has, before any cost. `run`,
the terminal UI and `Session.start`'s default each start a session as a person, so each refuses such a team, `run` with exit 78,
whomever the team starts.

A person's resume of such a session would wait alike, for a close only its program makes, once the harnesses it brought back had
begun to spend. `session resume` is a person's, so it refuses a session whose manifest says `until = "program"`, with exit 78,
before any harness comes back, naming the program and the script way: its script runs again, with `Session.resume`. The terminal
UI resumes on a runtime of its own, which a program's session refuses already, as it issues no owner credential (RFC 0050).
`Session.resume` takes no principal, as the runtime acts as the one the manifest names, so a script that calls it on a program's
session acts as that program, which is how the program's own script runs again.

`team check` knows no principal, as a team is checked before anyone starts it, so it says nothing of `until = "program"`: a script's
team is sound. A training system starts each rollout as a program, which can close it, so `trainable_problems` no longer counts
`program` among the `until`s only a person reaches.

### 5. The presets

`map-reduce` goes, with `platoon_harness.topology.map_reduce`: it named a program, `map_reduce`, which nothing runs, and no user of
it is in sight. Its channels, two queues the program adds to and a board, are a few lines written out, as
[topologies](../how-to/topologies.md) writes out the merge queue, and a script that adds to them is the guide's program.

`git-swarm` keeps its `role`, its `nominations` topic, its `inflight` board and `until = "program"`. Its `live` and `episodes` were
arguments of its `population` program, which only the key carried, so they go with it, rather than be taken and carried out by
nothing. The git-swarm rework, later in milestone 4, says what a population program takes, and where: [RFC 0070](0070-a-population-gives-each-worker-one-outcome-which-its-program-records.md) gives `git-swarm` its
`live` again, required, as the topology's `max_live`, which the kernel holds, and makes `attempts` an argument of
`platoon_harness.patterns.population`. `episodes` stays gone.

What changes for users:

- **The team file:** `[topology]` takes no `program`, and `git-swarm` no `live` or `episodes`, until [RFC 0070](0070-a-population-gives-each-worker-one-outcome-which-its-program-records.md) gives it `live` again.
  `map-reduce` is an unknown preset.
- **Python:** `platoon_harness.topology.Program` and `platoon_harness.topology.map_reduce` are gone, and `git_swarm` takes `role`
  alone, until RFC 0070 makes it `git_swarm(role, *, live)`.
- **The command line and the terminal UI:** `run` refuses a team under `until = "program"` with exit 78, and the terminal UI's start
  refuses it, each naming the script way. `session resume` refuses a session under it with exit 78, naming its program and the
  script way.
- **The journal:** nothing changes.

## Alternatives

| Alternative | Why not |
|---|---|
| A program named in the team file and resolved to code at load | It needs a registry of code, a process to run it in, arguments in TOML and a restart of its own: a second way to do what a script holding `program:<name>` does, with control flow back in config |
| Keep the key, refused, as RFC 0048 left it | A key that is always refused is still a key the reference documents and a reader takes for a feature |
| Read an old manifest's `program` and drop it | AGENTS.md forbids a compatibility shim, the project is unreleased, and only a session from before 13926da can hold one |
| Keep `map-reduce` with a `platoon_harness.patterns.map_reduce` to run it | No user beyond the preset itself is in sight, and the brief's examples do not name it. A pattern built to keep a preset alive is an abstraction with one user |
| Keep `git-swarm`'s `live` and `episodes`, or carry `live` as `limits.max_live` | The first is a setting nothing carries out (RFC 0048). The second decides, ahead of the git-swarm rework, what a population's `live` means, which RFC 0070 then decided so |
| Have `team check` refuse `until = "program"` | A team is checked before anyone starts it, and a script's team is sound. The refusal belongs where the principal is known |
| Save a program's state for it, as a checkpoint | A second record beside the journal, which a crash can leave disagreeing with it. The journal already holds what the program did |
| A `key` on each of Session's methods | Every method would grow a parameter that `Session.submit` already takes |

## Consequences

- No team file names code. A team that needs control flow is run from a script, which the topologies guide shows.
- A program's session lives in the script's process: the script leaving stops it, resumable, and a crash of the script is a crash
  of the runtime.
- A program run again after a crash adds nothing it added before, as long as it keys each command by what it is for.
- `run` and the terminal UI cannot start a `git-swarm` team, or any team under `until = "program"`, and `session resume` cannot
  resume such a session. A script can do both.
- A team file that sets `program`, a third party's among them, is refused as any unknown key is, and a session from before 13926da
  that named a program is refused on resume and reads as history.
- A trainable team may say `until = "program"`, and the training system's program then closes each rollout's session itself.
- How often a program's second run decides differently from its first, on what it reads, is unknown.

## Rollout plan

| Milestone | Scope | Exit check | Pull requests |
|---|---|---|---|
| M1 programs are scripts | `map-reduce` removed; `program` and `Program` gone; `git-swarm` keeping `role` alone, until RFC 0070 gives it `live`; `until = "program"` refused under a person's principal, and to a person's resume; `trainable_problems` no longer counting it | `tests/unit/runtime/test_opening.py::test_a_session_left_to_its_program_needs_a_program_to_own_it`, `tests/integration/test_cli.py::test_run_refuses_a_team_left_to_its_program_naming_the_script_way_with_78`, `::test_a_person_s_resume_of_a_session_left_to_its_program_is_refused_naming_the_script_way_with_78` and `::test_a_session_whose_team_names_program_is_refused_on_resume_as_an_unknown_key`, `tests/integration/test_tui.py::test_a_team_left_to_its_program_is_refused_from_the_sessions_screen_naming_the_script_way`, `tests/unit/topology/test_check.py::test_a_team_that_names_a_program_is_refused_as_any_unknown_key_is` and `tests/unit/topology/test_presets.py::test_every_preset_passes_team_check` | |
| M2 the script way, shown | The topologies guide's program, run again after a crash by a test | `tests/unit/runtime/test_programs.py::test_a_program_run_again_after_a_crash_adds_nothing_twice` | |

## Open questions

1. Where does a population program take its `live` and its `attempts`? The git-swarm rework's own RFC decides, later in milestone
   4, before `git-swarm` takes either again. [RFC 0070](0070-a-population-gives-each-worker-one-outcome-which-its-program-records.md) answers it: `live` is `git-swarm`'s, as its `max_live`, and `attempts` is
   `population`'s.

## Evidence

- `git show 13926da^:packages/sdk/src/platoon_harness/team.py` warns of a `topology.program` and refuses none, so a session could
  start on a team that named one until 13926da.
- [RFC 0050](0050-a-script-is-a-person-or-a-program.md)'s tests, in `tests/unit/runtime/test_session.py`, show a script owning a
  session as a program, `test_a_script_is_a_person_or_a_program_in_the_journal` among them.
- `tests/unit/kernel/test_commands.py`, `test_a_reused_key_with_other_arguments_is_refused`, `test_keys_belong_to_their_actor` and
  `test_a_crash_answers_nothing_so_its_key_can_retry`, show the keys a program's second run rests on.
- The tests named in the rollout plan.
