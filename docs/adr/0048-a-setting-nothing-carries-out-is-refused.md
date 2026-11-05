# 0048. A setting nothing carries out is refused

**Status:** Accepted, 2026-11-05

## Context

A team could say things nothing in the SDK does. A topology's `program` named an episode program, and no program can run, so
`team check` warned and let the team start: a session under `until = "program"` then never ended short of its budget, and the
`map-reduce` and `git-swarm` presets name one each. A topic took `digest`, `entry`, `requires` and `validator`, and a board `keys`,
which were parsed, hashed and resolved, and enforced by nothing, so `team check` labelled them; a lagging reader's digest has always
been the fixed 32 entries a constant holds. Loud failure says a setting that is not carried out is refused or labelled, and a label on
a setting that does nothing is still a setting that does nothing.

## Decision

- **`team check` refuses a `program` while none runs**, naming it and what to use instead, a topology that names none or a session
  driven from Python, so `run` and `Session.start` refuse such a team before any cost, with exit 78 on the command line. The
  `map-reduce` and `git-swarm` presets stay, as their expansions are what a program will need, and are refused with the rest.
- **The settings nothing enforces are gone**, together: a topic's `digest`, with its `Digest`, `entry`, `requires` and `validator`,
  and a board's `keys`. A team that sets one is refused where it does, as any unknown key is. The `git-swarm` preset loses its
  `contributions` topic, which held nothing but those settings, as the workspaces design decided: the repository is the
  contribution log, and `Informed-By` the declaration.

## Alternatives considered

| Alternative | Why not |
|---|---|
| Keep warning of a program | A warning that a session will never end on its own is a refusal that costs money first |
| Keep the settings, labelled | Each is a promise the code does not keep; a label tells the reader that, and the setting still reads as one |
| A refusal of its own for each removed setting | A message kept for keys that no longer exist is a compatibility shim; the CHANGELOG names each removal |
| Keep `digest` and enforce it | No user has asked for another digest size, and `summarize` would spend budget with no reader asking |
| Rework `git-swarm` here | Its program and outcome rules belong to the workspaces design's later steps, with the population program |

## Consequences

- No team that `team check` accepts names something nothing does.
- A session whose resolved team set one of the removed settings, which only `git-swarm` did by itself, can no longer be resumed: its
  manifest names a key that is not a key, which `session resume` refuses, naming it. Its journal still reads, as `events`, `session
  show` and the provenance queries do. No such session could have ended on its own.
- When programs run, the refusal becomes the check of a program that cannot be resolved.

## Evidence

- `tests/unit/topology/test_check.py`, `test_team_check_refuses_a_program_it_cannot_run` and
  `test_a_channel_setting_nothing_enforces_is_no_setting`.
- `tests/unit/topology/test_presets.py`, `test_every_preset_passes_team_check_but_for_a_program_none_runs_yet` and
  `test_git_swarm_coordinates_through_artifacts_alone`.
- `tests/integration/test_cli.py`, `test_team_check_and_run_refuse_a_program_none_can_run_with_78`.
