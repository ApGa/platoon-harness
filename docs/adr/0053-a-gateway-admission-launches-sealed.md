# 0053. A gateway admission launches sealed

**Status:** Accepted, 2026-11-05

## Context

ADR 0049 gave a training authority a `Gateway` and a capability, `sealed`, that only a driver declaring it is given one, but no
driver declared it, so a gateway admission failed every real launch. A training system needs three things of a launch on its
gateway. Every call must go on the agent's own bearer, which ties it to that agent, and no credential may outlive the rollout in a
file of the session's, which is its export. The policy must see nothing of the user's setup and no tool that acts outside the
training system's environment, whose own tools come through an MCP server of its own. And a call a harness makes to compact its
context must be told apart when it is made: a gateway counts a step budget as calls arrive, so a label set after the rollout
cannot keep a compaction out of it, and a call whose purpose is unknown must never train.

## Decision

- **A sealed launch has nothing of the user's.** On a gateway, a driver launches its harness with the gateway's model under its
  bearer, ours and the environment's tools, no tool of its own that acts, none of the user's settings, extensions, skills or project
  instructions, no retries, and its compaction on. A driver with no sealed launch refuses a gateway.
- **A bearer goes only by environment,** under `PLATOON_HARNESS_BEARER`, and a file a launch writes names that variable, as
  `${PLATOON_HARNESS_BEARER}`, never its value. A wire frame names it, with the gateway's origin, model, tools and compaction
  headers in the clear. A gateway whose origin has a path, or whose tools' URL holds its bearer, is refused, as a credential goes by
  the bearer alone.
- **The environment's tools are a second MCP server,** at `Gateway.tools`, named `environment`, under the same bearer.
- **Each compaction call carries the gateway's `compaction_headers` and is reported with its id,** as `ModelCall(purpose=
  "compaction", call_id=...)`, by every sealed driver: ScriptedDriver's `Compact` step, a wire program from its launch spec,
  OpenHands' condenser through its LLM's `extra_headers`, and pi through our extension, which takes `session_before_compact` and
  runs pi's own exported `compact` with the headers and a stream function that keeps each response's id, for each of its one or
  two calls. The ids reach the driver in the details pi keeps of the compaction.
- **A sealed launch is earned, never declared.** Two checks, `sealed_first_request_holds_only_ours` and
  `environment_tools_in_first_request`, run on FakeModel acting as a gateway, inside the one result `doctor --check` keeps, and
  `trainable` stands on them.

## Alternatives considered

| Alternative | Why not |
|---|---|
| A training system relabelling compaction steps after the rollout | Its gateway counts the budget as calls arrive, so a label set later leaves them counted |
| Bracketing pi's compaction between its start and end frames, or headers set while one runs | Both join by order |
| Writing our own summarizer for pi | It would train on a compaction pi never makes |
| A private config directory outside the session folder, removed on stop | One more place to bind under isolation and to clean after a cut rollout, whose stop may never run |
| A second kept result per mode | Part 3 keeps one result per driver, pinned to its harness version |
| The environment's server beside ours in OpenHands' own MCP config | The SDK's client of two servers names each tool by its server, so ours would lose the names we teach |
| OpenHands' `finish` and `think` taken away | It ends a run and notes a thought with them, and neither acts on anything; a harness check names the tools a sealed launch keeps |

## Consequences

- A sealed pi states a context window no context reaches: it takes an unstated one as none, which had it compact after every
  turn once its history passed what a compaction keeps, so it compacts when its gateway refuses a request as too long, and retries
  it once.
- Pi's driver waits, at start, for our extension to say which tools pi declares once ours and the environment's have connected,
  so `ready.tools_visible` is pi's own list and an agent's tools are seen or hidden, never unverified.
- Each sealed driver reports `DriverInfo.version` from `describe`, which a check before any launch holds a kept result to.

## Evidence

- [tests/unit/drivers/test_sealed.py](../../tests/unit/drivers/test_sealed.py): each sealed driver's compaction headers and ids, the
  bearer in the environment alone, and a path-form URL refused.
- [tests/integration/test_pi.py](../../tests/integration/test_pi.py): on pi 1.5.0, each body id is its call id, the first request
  holds no built-in tool, an overflow refusal is compacted and retried, and a compaction of two calls carries the headers on each and
  reports both ids.
- [tests/integration/test_openhands.py](../../tests/integration/test_openhands.py): OpenHands 1.59.0's condenser carries the headers
  and is reported as `compaction` with its id.
- [tests/integration/test_sealed.py](../../tests/integration/test_sealed.py): the sealed checks pass on both, and earn trainable.
