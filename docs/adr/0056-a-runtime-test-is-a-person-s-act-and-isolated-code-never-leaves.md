# 0056. A runtime test is a person's act, and isolated code never leaves

**Status:** Accepted, 2026-11-06

## Context

The brief asks for tests to be captured beside commits, and section 13 names them as events on `repo/<name>`. An exit code tied to
an immutable SHA is the only test evidence the runtime can hold at the validated level: an agent saying its tests passed is a claim,
and a test run read out of a tool item is a link nobody recorded. So the runtime runs a test itself. What it runs is a commit's code,
written by an agent: a `conftest.py`, a `Makefile`, a script the test command names. The trust step that covers a `command` harness
covers the command a team names, and not the code that command loads. An isolated agent's code is confined by an isolation
(ADR 0034), and a test run unconfined would carry it out. A test with no bound could keep a session from ever settling.

## Decision

- **A person or a program asks, and an agent never does.** `repo.test{commit}` is an op with no tool, and refuses an agent whatever
  its grants, so no topology a team writes can let an agent have the runtime run its code. It takes a recorded commit's SHA or its
  first 4 or more hex digits naming one, and gives back the `test` effect it requested.
- **The team names the test.** `test = {command, timeout}`, with `timeout` required. From a project or team file it needs the trust
  step, as a `command` harness does. The session records the command at open, so the op and the `changes` view know whether there is
  one; a team with none refuses `repo.test`, naming why.
- **A clean detached checkout, in a repository of its own.** The `test` effect makes `tests/<effect>/checkout` in the session folder,
  a repository that borrows the objects of your repository and of each workspace's own but an isolated one's, checks the commit out
  detached and runs the command in the session's subfolder of it, as you, on what every process inherits and a `TMPDIR` of its own,
  in a process group recorded before it can exec. Nothing is written into any repository, and none of their own config applies. A
  program the command names by a relative path is the commit's own.
- **Its outcome is the runtime's finding.** The host records `repo.tested` on `repo/<name>` through the runtime-only `repo.record`,
  with no agent in the envelope: the commit, the command, `exit`, None when it never exited on its own, `seconds`, None when it never
  started, `outcome` (`passed`, `failed`, `error`), `why` where the exit does not say, and as its `body` the last 64 KiB of what it
  printed, as much as the journal holds in an event's own body, so that `blob.get` reads it for anyone, with how many bytes it
  printed in all. A timeout is an `error`, not a failure, and ends the group and whatever carries its `TMPDIR`. The checkout goes
  once the outcome is recorded.
- **Retried, and never run twice for one record.** The effect is owned by no agent and `on_uncertain = retry`. A retried attempt first
  ends what an earlier one left in its folder, then finishes from its effect's `repo.tested` when the journal holds one, and
  otherwise runs again from the start.
- **An isolated agent's code runs only in its isolation.** A commit the journal records as made in an isolated workspace, or built
  on one, is refused, naming why. The design refused only the commit itself; a merge of it holds its code, and a person releasing a
  kept isolated snapshot with `git fetch` and an agent merging that branch is an ordinary path, so the rule follows recorded
  ancestry. That is the smallest change that keeps the design's reason. The `Looks` view learns which workspaces are isolated from
  their `workspace` effects and carries the isolated maker down each recorded parent, so the op and the `changes` view read one
  answer. The checkout never borrows an isolated workspace's objects either, so a commit only it holds cannot be checked out.
- **The act says whose code it runs.** When the team names a test, each commit row in `changes` carries `actions[]` with
  'Test: runs @ada's commit as you, unconfined', 'this commit' where no one workspace made it, or a disabled 'Test' saying why. The
  terminal asks before it runs one, as it does for every act nothing takes back.

## Alternatives considered

| Alternative | Why not |
|---|---|
| Defer runtime tests until someone asks | Section 13's test events would stay unbuilt, and test evidence would rest on what agents say |
| A tool agents call | The trust step does not cover the code the command loads, so an agent could have the runtime run anything it wrote |
| Test every commit as it is recorded | Cost grows with commits, and nobody asked for each one |
| Infer test runs from tool items | It fabricates a link between a tool call and a commit that nobody recorded |
| `git worktree add --detach` in the repository that holds the commit | It writes a registration into your repository, or into an agent's snapshot, and a crash leaves it there |
| Refuse only a commit made in an isolated workspace | A merge of it carries the same code out of its isolation |
| An `output` field for what it printed | An event's one body is already `body`, which `blob.get` reads by the record's ref with nothing new |
| Keep the last 1 MiB, as a harness's log does | A body past 64 KiB is kept outside the journal's own row, which `blob.get` gives back as no text, so the command line could not show it |
| A query for whether an effect's test is recorded | Only a retried attempt asks, and the journal's `repo/<name>` past the effect's own seq answers it |

## Consequences

- A runtime test's outcome is evidence of what one command did at one SHA in a clean checkout. It can honestly differ from the agent's
  own run, which had untracked and ignored files; a filter only your repository's config names does not run.
- Code an isolated agent wrote that reached another commit without git ancestry, copied by hand, is not caught: the rule is ancestry
  the journal recorded.
- A test keeps the session from settling until it ends, and a closing session waits for it, at most its timeout.
- A test the owner's stop cut off runs again when the session resumes.

## Evidence

- `tests/unit/primitives/test_repo.py`: `test_a_commit_s_tests_are_its_latest_runtime_test_or_none`,
  `test_a_test_is_a_person_s_or_a_program_s_act_on_a_recorded_commit`, `test_a_test_needs_the_team_s_test_command`,
  `test_an_agent_cannot_ask_the_runtime_to_run_its_code`, `test_a_test_of_an_isolated_commit_is_refused` and
  `test_a_test_action_says_whose_code_it_runs`.
- `tests/unit/runtime/test_commit_tests.py`, on real git: `test_a_runtime_test_runs_at_the_exact_commit_in_a_clean_checkout`,
  `test_a_runtime_test_s_exit_time_and_output_are_recorded_and_its_checkout_removed`,
  `test_a_snapshot_s_commit_is_tested_from_the_repository_that_holds_it`,
  `test_what_a_test_printed_past_what_its_record_holds_is_cut_saying_how_much`,
  `test_a_test_past_its_timeout_is_an_error_not_a_failure`, `test_a_test_the_journal_recorded_is_not_run_again` and
  `test_a_commit_only_an_isolated_workspace_holds_is_never_checked_out`.
- `tests/unit/config/test_config.py`, `test_a_test_command_from_a_project_file_needs_the_trust_step` and
  `test_a_test_needs_a_timeout`.
- `tests/unit/drivers/test_process.py`, `test_a_run_says_how_its_command_exited_and_keeps_what_it_printed` and
  `test_a_run_ends_what_its_command_left_and_what_its_limit_cut_off`.
- `tests/unit/tui/test_review.py`, `test_review_tests_a_commit_once_you_say_yes_and_shows_what_it_came_to`.
