# 0055. The export is the session as it ended

**Status:** Accepted, 2026-11-06

## Context

A training system reads what a rollout came to once it has ended: which of its agents' calls can train, and the rewards and credit
written about them. It needs one place to read that from, which holds no credential, since rollouts are kept and copied, and which
answers alike wherever and whenever it is read. And a session whose agents an authority admitted could be resumed like any other,
under `LocalAuthority`, though the keys its agents ran on went with the authority that gave them.

## Decision

- **The export is the session folder as it ended,** closed, or stopped for a rollout cut short, with `annotations.sqlite` beside its
  journal. There is no second format.
- **It is read through `Session.attach` once its runtime has stopped.** Lineage, exposure, contributors, eligibility and annotations
  answer on it, alike after a rebuild, on a copy and with the conformance store gone, as eligibility reads the levels each start
  recorded.
- **It holds no key.** A bearer lives only in its harness's environment, a file a sealed launch writes names the bearer's variable,
  and the admit result records the backend's ids, never a key.
- **Rewards and credit go into it after the session has ended,** through `Session.annotate`, so no context a policy could see held
  one.
- **A session whose admit results name the backend's ids is never resumed.** It is history: `Session.resume` takes no authority, and
  `Runtime.start` refuses such a session before anything runs, naming `Session.attach`.

## Alternatives considered

| Alternative | Why not |
|---|---|
| A file of what trains, written at the end | A second format to keep in step with a journal that already answers every question on a closed copy |
| Copies of attribution, reasons or rewards in the training system's records | Copies drift; the session's name, the backend's ids and the row's id join the two |
| A `Manifest.authority` naming who admitted the agents | The admit results already say it, and a manifest field would be a second record of one fact |
| Resuming under a new authority | A new authority admits new agents; the backend knows them by the keys that went with the old one |

## Consequences

- A training system names each rollout's session and finds its agents by `backend`, and keeps the folder for as long as it wants
  the evidence.
- A rollout cut short leaves a stopped session, which reads as history like a closed one.

## Evidence

- [tests/integration/test_contract.py](../../tests/integration/test_contract.py): no bearer in the session folder or the cwd, and
  the session attached with no runtime answers eligibility `exact` and takes a reward of each status and `propagate@1`'s rows.
- [tests/unit/runtime/test_training.py](../../tests/unit/runtime/test_training.py),
  `test_eligibility_answers_alike_after_rebuild_on_a_closed_copy_and_without_the_conformance_store`.
- [tests/unit/runtime/test_authority.py](../../tests/unit/runtime/test_authority.py),
  `test_a_session_whose_admissions_name_backend_ids_is_never_resumed` and
  `test_the_admit_result_records_backend_ids_and_never_a_key`.
