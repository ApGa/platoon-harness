# 0054. Credit is a producer's annotation, and `propagate@1` is the first

**Status:** Accepted, 2026-11-05

## Context

A training system that trains each agent of a team on a reward of its own needs that reward from somewhere: the team's reward is
one number for the episode, and the record already holds the edges along which work rested on work, citations, causes and
ancestry. M2 kept credit out of the SDK: an annotation by a named producer, never a fact, and the SDK made no estimate of its own.
A training system still needs one producer to start from, with one way to be run, and the record must say whose work it is about.

## Decision

- **Every producer is `async def produce(session, episode, *, judge, **params) -> None`,** named by `module:attr`, run on an ended
  session, and writing only through `Session.annotate`. `judge` is model access for a producer that asks a model, or None. A
  producer answers about one episode, named, never guessed.
- **`platoon_harness.credit.propagate` is the first, `propagate@1`, a heuristic.** It splits the episode's one team reward over the
  refs the episode closed on; each event it reaches keeps `retained` of what reached it for its maker, and passes the rest equally
  along its causes, its ancestry and its citations, an agent's only where its exposure says Seen. It walks newest first, so a path
  that reconverges adds once, and stops at 4,096 events. It writes one local `credit` row per agent it reached, on that agent's
  first `agent.started`, with the refs of its events that took a share as evidence, under the producer
  `platoon_harness.credit:propagate`, the name an entry runs it by. An agent it never reached gets no row, so is unscored. A team
  reward that is not scored passes its status to each row, and a walk that stopped short makes every row `invalid`. What reached an
  event nobody of the session's agents made is the reward less the rows, and is no row.
- **Its incentive is said.** Citing gives away all but `retained` of what reaches the citer, and work nobody cites earns nothing
  from it; the default template asks every agent to cite, so training under it pulls against that request.

## Alternatives considered

| Alternative | Why not |
|---|---|
| Walking offers too | Being handed something is not using it |
| Zero for an agent the walk did not reach | Unknown is not zero |
| A row for the unassigned share | Evidence holds refs only, and absence already says it |
| A default `retained` | It decides the incentive, so a caller says it |
| `contributors` as the walk | It names makers, not edges, so it cannot carry a share along a path |

## Consequences

- The SDK now ships one estimate, labelled heuristic; any other producer writes beside it under its own name and version.
- A training system centres a producer's rows per role, as Platoon's keyed credit does at a group size above one.

## Evidence

- [tests/unit/runtime/test_credit.py](../../tests/unit/runtime/test_credit.py): conservation, reconverging paths, retention, a ring
  of citations, unseen citations and handed-only edges, an unreached agent, status, the cap, refusal, and the target.
- [tests/integration/test_contract.py](../../tests/integration/test_contract.py): it writes its rows on a session a training authority
  drove.
