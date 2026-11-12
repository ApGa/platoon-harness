# RFC 0046: A daemon that keeps failing needs a person

| | |
|---|---|
| Status | Accepted, 2026-11-05 |

## Summary

Its first failure since a run that lasted is `daemon.failed` and the next run that lasts `daemon.recovered`, so a daemon that fails on every pass stands in `attention` as a kind of its own and never passes for a quiet session

## Motivation

The supervisor restarts a daemon that raises, with backoff from a tenth of a second to thirty, and a run that lasts a minute forgives
the failures before it ([RFC 0005](0005-daemons-and-effects.md)). It only logged. A courier or a host that fails on every pass
therefore hands nothing over and starts nothing, and the session it serves looks quiet: no event, no `attention` row, nothing in the
terminal or the browser but a log nobody reads. A review raised it. A person must see it, so it is a kind of
`attention` of its own.

## Proposal

- **The journal hears a daemon's failure when it begins and when its error changes, and its recovery once.** A failure that begins a
  run of them, or says another error than the last, is `daemon.failed{daemon, error}` on `daemon/<name>`, and the next run that lasts
  a minute is `daemon.recovered{daemon}`. Failures in between with the same error are the same failure, as the supervisor already
  counts them, so a daemon that fails on every pass with one error writes one event and not one a pass. The supervisor says them
  through two runtime-only ops of the kernel's, `daemon.fail` and `daemon.recover`, and waits out a busy writer, as evidence is never
  shed.
- **`attention` has the kind `daemon`.** Its row, `daemon/<name>`, names the daemon, where its traceback is, the session folder's
  `runtime.log`, what starts it anew, `session stop` then `session resume`, and its latest error. It has no actions, as only a person
  can find out what broke, and closes once a run lasts a minute or a new runtime starts, whose daemons have not failed yet. The
  terminal's dock and the browser's Needs you draw it as they draw any row.

## Alternatives

| Alternative | Why not |
|---|---|
| A row from the runtime's memory, with no event | `attention` is a fold every client watches by `seq`, so a row nothing journals could not be watched, would differ between clients, and would vanish from history |
| An existing event: a gap, a `native` frame, a failed effect | A gap says what went unobserved of an agent's work, a `native` frame what a harness said that nobody's vocabulary covers, and an effect is a request to touch the world. A daemon's failure is none of these, and dressing it as one would mislead every reader of that kind |
| An event per failure | A daemon that fails on every pass with one error would write one every thirty seconds for as long as it runs, and the row would say no more |
| Keep the error that began the failures | The design asked for the latest, and a person fixing a daemon needs what it fails with now |
| One event type, `daemon.changed`, whose error is null once it runs again | A reader would have to know that no error means it recovered; a pair says it by name, as `session.opened` and `session.closed` and `timer.set` and `timer.cleared` do |
| A setting for the minute | The supervisor's forgiveness already uses it, and two clocks for one daemon would disagree |

## Consequences

- `attention` is a fold, so a kind of its own needs an event, and no existing event says this, so this adds two, `daemon.failed`
  and `daemon.recovered`, in a namespace the kernel now takes, `daemon`.
- A daemon whose error changes on every pass writes an event a pass: one every thirty seconds once its backoff is full.
- A daemon's error text reaches the journal, cut to 2048 characters and its gist to 280. The runtime's log keeps the traceback.
- `Attention` is at view version 4.

## Evidence

- `tests/unit/kernel/test_daemon.py`, `test_a_daemon_that_keeps_failing_is_said_at_each_new_error_until_a_run_of_it_lasts_a_minute` and
  `test_a_daemon_that_never_failed_says_nothing`, on a manual clock.
- `tests/unit/primitives/test_clients.py`, `test_a_daemon_that_keeps_failing_stands_in_attention_until_a_run_of_it_lasts`.
- `tests/unit/tui/test_workspace.py`, `test_a_daemon_that_keeps_failing_is_a_place_in_the_dock`, and `tests/e2e/test_acts.py`,
  `test_needs_you_names_a_daemon_that_keeps_failing`, each on a session whose courier fails on every pass.
