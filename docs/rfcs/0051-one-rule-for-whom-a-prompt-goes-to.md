# RFC 0051: One rule for whom a session's prompt goes to

| | |
|---|---|
| Status | Accepted, 2026-11-05 |

## Summary

`Team.recipients`: the agent named, or every agent the session starts, which `run` adopts

## Motivation

`platoon-harness run` decided whom its prompt went to in a rule of its own: `--to`, or the one agent the session started, and a
refusal when it started several. A training system's bridge sends a task's instruction to a session that may start one agent, a
mesh of peers or a git-swarm's workers, and needs the same answer from the SDK, or two clients would each keep a rule.

## Proposal

`Team.recipients(to=None)` says whom a session's prompt goes to: the agent `to` names, which the session must start, or else every
agent the session starts. `run` adopts it, so with no `--to` its prompt goes to each agent the session starts, and a `--to` naming
none of them, or a team that starts none, is refused before any cost.

## Alternatives

| Alternative | Why not |
|---|---|
| Keep refusing several starting agents | A mesh or a swarm has no one agent to ask first, and the refusal sent the user to pick one arbitrarily |
| A rule in the bridge alone | Two clients, two rules, and the command line's would drift from the one training runs |
| An entry option naming the recipients | A setting with one user that the team already decides |

## Consequences

- A user who relied on `run` refusing several starting agents now sees each of them start a turn on the prompt.
- What a prompt reaches is a fact of the team, so a run and a rollout of one team prompt the same agents.

## Evidence

- `tests/unit/topology/test_check.py`, `test_a_prompt_goes_to_the_agent_named_or_to_every_agent_the_session_starts`.
- `tests/integration/test_cli.py`, `test_a_prompt_goes_to_the_agent_named_or_to_every_agent_the_session_starts` and
  `test_who_a_prompt_is_for_is_decided_before_any_cost`.
