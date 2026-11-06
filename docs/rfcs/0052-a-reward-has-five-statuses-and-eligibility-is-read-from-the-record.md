# RFC 0052: A reward has five statuses, and eligibility is read from the record

| | |
|---|---|
| Status | Accepted, 2026-11-05 |

## Summary

`scored`, `invalid`, `error`, `timeout` or `cancelled`, no row meaning unscored; `eligibility` answering attribution and every bar from the levels starts recorded; a team checked for training from its file alone, then on the machine as its session starts

## Motivation

An annotation's status was `scored`, `invalid`, `error`, `cancelled` or `unscored`. A training system's outcome is scored, invalid,
error, timeout or cancelled, so a timeout had no word of its own, and a written `unscored` said what having no statement already
says. Architecture section 14 promised an `eligibility(agent, episode)` that was not built, and the record held no way to tell a
training system whether an agent's calls are tied to it exactly, or why some of them cannot train. And a team could not be checked
for training before a rollout spent anything: what its file decides needs no driver, and what the machine decides needs each
driver and the result kept for it.

## Proposal

- **A status is one of five,** `scored`, `invalid`, `error`, `timeout` or `cancelled`, a value only with `scored`, and no statement
  means unscored. A stored status outside the five fails validation, as any malformed row does. A team's reward targets the
  episode's `episode.closed`, an agent's its first `agent.started`, never its spawn.
- **`eligibility(agent, episode)` is a query op**, with a `Session` method and a command, as the provenance queries are. It answers
  an attribution, `exact`, `forked` or None, and a verdict with every bar of a closed set, for the agent and for each of its calls:
  `not_trainable`, `shared_key`, `forked` and `no_end` of an agent, and `outside_episode`, `person` and `purpose` of a call. It
  reads the levels the agent's starts recorded, never the conformance store, so a closed session's answer never changes.
- **`exact` needs a met trainable level and backend ids of the agent's own.** A met level already means a gateway login, call ids
  reported, a sealed launch and no opaque native children allowed, so uniqueness of the admit results is all that is added, and no
  key is ever recorded to compare. Each entry of an admission's `backend` names its agent alone, so one entry another admission
  names too bars both; the host refuses two agents on one bearer before either is admitted.
- **A call reported with no purpose is its turn's.** A sealed launch makes no call but its turns' and its compactions', as it
  retries nothing, warms no cache and labels each compaction call as it makes it, so `purpose` bars a purpose a harness gave other
  than `compaction`, and a call no harness reported has no id to join.
- **`person` counts what was handed, not what was seen.** A person's entry handed to an agent below a call is either seen or
  unknown, never `not_seen`, and counting only `seen` would read unknown as no. A turn a person held is a person's too.
- **What a team decides is checked from its file, and what a machine decides when the session starts.** `trainable_problems(team)`
  is pure, so a training system's load check runs it with no driver to ask, and judges approvals by a session's own `approvals` when
  it is given them, as that policy overrules every role's. `check(team, trainable=True)`, which
  `Session.start(trainable=True)` passes the flag to as it passes `plan_login`, adds each role's driver: a sealed launch, and a result
  kept under the root that proves trainable for the harness it would run, by the version its `describe` gives, which
  `DriverInfo.version` now carries. A trainable start needs an authority.

## Alternatives

| Alternative | Why not |
|---|---|
| Keeping six statuses | A written `unscored` and no row would be two ways to say one thing |
| Four, with timeout folded into error | A training system tells the two apart, and a label lost here cannot be found again |
| A refusal on read for `unscored` rows | No released SDK wrote one; validation refuses a malformed row already |
| `declared` and `inferred` attribution | Nothing can make them yet: no gateway reads an identity a harness declares |
| `exact` on the mere absence of `child.seen` | A harness on its own login would read as exact |
| Reading the conformance store at query time | A check run again would change a closed session's verdict |
| A separate attribution op | One answer per agent and episode holds both, as a verdict needs the attribution's reasons |
| `team_check(trainable=True)` | It needs each role's capabilities, which only a driver's `describe` gives, and a load check runs nothing |
| Checking the kept result's version only at launch | A launch is after the cost, and the rule is to refuse before any harness launches |

## Consequences

- An estimator that wrote `unscored` writes nothing instead.
- Every shipped driver is refused from a trainable session until sealed launches land, as none declares `sealed` or says its
  version in `describe`.
- `run` and the other clients read eligibility as any query, and an agent never can.

## Evidence

- `tests/unit/runtime/test_annotations.py`, `test_a_reward_row_has_one_of_five_statuses_and_a_value_only_when_scored`.
- `tests/unit/primitives/test_eligibility.py`, every test, refolded and compared at each end; `tests/unit/runtime/test_training.py`,
  `test_eligibility_answers_alike_after_rebuild_on_a_closed_copy_and_without_the_conformance_store`.
- `tests/unit/topology/test_check.py`, `test_trainable_problems_reads_the_team_file_alone`; `tests/unit/runtime/test_training.py`,
  `test_check_trainable_refuses_what_the_machine_decides` and `test_session_start_trainable_refuses_before_any_harness_launches`;
  `tests/unit/drivers/test_levels.py`, `test_a_harness_with_no_sealed_launch_is_not_trainable` and
  `test_what_a_result_does_not_prove_of_a_level_is_said_with_what_makes_one`.
