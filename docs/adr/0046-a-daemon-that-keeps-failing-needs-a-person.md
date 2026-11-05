# 0046. A daemon that keeps failing needs a person

**Status:** Accepted, 2026-11-05

## Context

The supervisor restarts a daemon that raises, with backoff from a tenth of a second to thirty, and a run that lasts a minute forgives
the failures before it ([ADR 0005](0005-daemons-and-effects.md)). It only logged. A courier or a host that fails on every pass
therefore hands nothing over and starts nothing, and the session it serves looks quiet: no event, no `attention` row, nothing in the
terminal or the browser but a log nobody reads. [The durable review](../research/pi-durable.md) raised it, and the owner chose a kind
of `attention` of its own.

## Decision

- **The journal hears a daemon's failure once, and its recovery once.** The first failure since a run that lasted is
  `daemon.failed{daemon, error}` on `daemon/<name>`, and the next run that lasts a minute is `daemon.recovered{daemon}`. Failures in
  between are the same failure, as the supervisor already counts them, so a daemon that fails on every pass writes one event and not
  one a pass. The supervisor says them through two runtime-only ops of the kernel's, `daemon.fail` and `daemon.recover`, and waits out
  a busy writer, as evidence is never shed.
- **`attention` has the kind `daemon`.** Its row, `daemon/<name>`, names the daemon and the error that began it, has no actions, as only
  a person can find out what broke, and closes once a run lasts a minute or a new runtime starts, whose daemons have not failed yet.
  The terminal's dock and the browser's Needs you draw it as they draw any row.

## Alternatives considered

| Alternative | Why not |
|---|---|
| A row from the runtime's memory, with no event | `attention` is a fold every client watches by `seq`, so a row nothing journals could not be watched, would differ between clients, and would vanish from history |
| An existing event: a gap, a `native` frame, a failed effect | A gap says what went unobserved of an agent's work, a `native` frame what a harness said that nobody's vocabulary covers, and an effect is a request to touch the world. A daemon's failure is none of these, and dressing it as one would mislead every reader of that kind |
| An event per failure | A daemon that fails on every pass would write one every thirty seconds for as long as it runs, and the row would say no more |
| A setting for the minute | The supervisor's forgiveness already uses it, and two clocks for one daemon would disagree |

## Consequences

- The design of record held to "no new event type" for provenance. This adds two, `daemon.failed` and `daemon.recovered`, in a
  namespace the kernel now takes, `daemon`, because a fold needs an event and none that exists says this.
- A daemon's error text reaches the journal, cut to 2048 characters and its gist to 280. The runtime's log keeps the traceback.
- `Attention` is at view version 4.

## Evidence

- `tests/unit/kernel/test_daemon.py`, `test_a_daemon_that_keeps_failing_is_said_once_until_a_run_of_it_lasts_a_minute` and
  `test_a_daemon_that_never_failed_says_nothing`, on a manual clock.
- `tests/unit/primitives/test_clients.py`, `test_a_daemon_that_keeps_failing_stands_in_attention_until_a_run_of_it_lasts`.
- `tests/unit/tui/test_workspace.py`, `test_a_daemon_that_keeps_failing_is_a_place_in_the_dock`, and `tests/e2e/test_acts.py`,
  `test_needs_you_names_a_daemon_that_keeps_failing`, each on a session whose courier fails on every pass.
