# 0057. An agent cites a commit by the ref the journal gives

**Status:** Accepted, 2026-11-06

## Context

A citation is a ref, `stream@version` (ADR 0036), and a recorded commit's ref is its `repo.committed` on `repo/<name>`. An agent knows
a commit by its SHA, from its own git, and had no way to turn that into the ref `based_on` takes. A nomination that names a SHA in its
text, for something to resolve later, is the text parsing the `Informed-By` decision rejected (ADR 0041). A commit read with `git log`
is also a read nobody observed.

## Decision

- **`repo.commit{sha}` is an agent read.** It gives a recorded commit's `ref`, its full `sha`, its `gist` and the workspace it was
  `made_in`, by its SHA or its first 4 or more hex digits naming one. It is `exposes`, so an agent's read records the gist and those
  fields as exposure, and a person's or a program's runs as a query and writes nothing.
- **Refused in the design's words.** `not_found` with 'not recorded yet: a commit is recorded at the look after the turn that made
  it', `invalid` when the digits name several, and `unsupported` in a session that observes no repository.
- **Every agent holds it.** The topology's base grants give `repo.commit` to every agent, as `blob.get` and `session.status`, since any
  agent of a session in a repository may cite a commit. It costs 554 bytes in every request of an agent that holds every tool, which
  the tool list's ceiling now allows: the alternative is an agent that cannot cite the work it builds on.

## Alternatives considered

| Alternative | Why not |
|---|---|
| A nomination naming a SHA in its text | Text parsing, which `Informed-By` resolution already refused |
| Full SHAs only | An agent sees short SHAs in its own git's output; 4 or more digits naming one recorded commit is what a trailer accepts too |
| A grant only where a preset asks | A citation is useful in every team in a repository, and a role's `tools` narrows it where a team says |
| Fold `made_in` and the ref into `blob.get` | A commit's record has no body to read; its ref is what is asked for |

## Consequences

- A commit read through `repo.commit` is an observed read in an agent's exposure; one read with `git log` stays unobserved.
- The git-swarm rework's nominations, planned with the population program, cite commits through this read.
- A session outside any repository shows the tool to every agent, which refuses saying the session observes no repository.

## Evidence

- `tests/unit/primitives/test_repo.py`, `test_repo_commit_gives_a_recorded_commit_s_ref_or_says_not_recorded_yet` and
  `test_repo_commit_says_a_session_with_no_repository_observes_none`.
- `tests/unit/tools/test_surface.py`, `test_a_tool_list_stays_under_its_ceiling`, the lead's ceiling raised from 23,850 to 24,400 bytes.
