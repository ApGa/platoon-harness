# 0050. A script is a person or a program

**Status:** Accepted, 2026-11-05

## Context

`Session.start(human=)` made whoever started a session a person, `human:<name>`, and the runtime issued that person an owner
credential, kept in `owner.token`, which any guest attaching with control used. A training system starts a session per rollout
from its own code. Recorded as a person, its message to an agent steers, at the earliest boundary its harness has, as a person's
correction must, and every turn after it reads as one a person shaped, which is what eligibility will not train on. And a guest
attaching with the owner credential would act as that program: a person could steer a rollout and the journal would say the
program did it.

## Decision

- **A session's principal is a person or a program**: `Session.start(principal=)` and `prepare(principal=)` take `human:<name>`,
  the default being `human:you`, or `program:<name>`, and `Manifest.principal` names it in place of `Manifest.human`. Anything
  else is a configuration error.
- **A program's message is a program's**, as the journal already treats one: it goes as its reader's setting says, as any agent's
  does, and starts a chain of hops of its own.
- **A session a program starts issues no owner credential.** A guest of its runtime holds the view credential, which reads and
  never writes, and a program's session cannot detach, as the guest it would hand back could act on nothing. Once its runtime has
  gone, attaching gives its history, as for any session, which an estimator writes annotations beside.
- **A manifest from before names its person `human`**, which loading reads as its principal, so a session survives the upgrade.

## Alternatives considered

| Alternative | Why not |
|---|---|
| A second principal for attachers | A credential that acts as nobody in particular is a person the journal cannot name |
| An owner credential the program keeps and never writes to disk | The program owns the session in its own process and needs none, and any token on disk is one a guest can use |
| `Session.start(episode=)`, a training flag on the person | The difference is who acts, which is the principal, not what the session is for |
| A program principal named after its training system | The name is the caller's: the contract names no system |

## Consequences

- The training system's bridge starts each rollout's session as `program:<its name>`, and anyone can watch it and nobody can steer it.
- The TUI and the browser show a program's session with the program where the person would be, read-only.
- A detached start under a program is refused `unsupported`.

## Evidence

- `tests/unit/runtime/test_session.py`: `test_a_script_is_a_person_or_a_program_in_the_journal`,
  `test_a_session_a_program_opens_gives_attachers_a_view_credential_only`, `test_a_program_s_session_cannot_detach`,
  `test_a_human_is_a_name_in_the_journal`.
- `tests/unit/runtime/test_opening.py`, `test_a_principal_is_a_person_or_a_program_by_a_name`;
  `tests/unit/config/test_config.py`, `test_a_manifest_from_before_programs_names_its_person`.
