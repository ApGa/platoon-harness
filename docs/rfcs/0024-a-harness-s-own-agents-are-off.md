# RFC 0024: A harness's own agents are off

| | |
|---|---|
| Status | Accepted, 2026-11-03 |

## Summary

`allow_native_children` on a role, false unless said, and each driver turns them off by the harness's own setting for one launch

## Motivation

Claude Code and Codex can each start agents of their own, and the owner was concerned that agents would reach for that instead of
`agent.spawn`. It was allowed and only observed, as `child.seen`. Such an agent is none of ours. Its calls reach us only in its
parent's total, so a budget and a trainer cannot see them per child. No topology binds it, so a worker that may not spawn can. Its
calls to our tools go out on its parent's token, so the journal records them as the parent's. Only its approvals still came through
the role's policy. In 36 live sessions a native child had run only where a test asked for one.

## Proposal

- **`allow_native_children` on a role, false unless said.** It reaches the driver on `AgentSpec`, which turns the harness's own agents off
  for that launch by the harness's own setting, and writes none of the user's configuration.
- **Claude Code** disallows `Agent` and `Workflow`, which start its own agents, and `ListAgents` and `SendMessage`, which reach them,
  and other Claude sessions on the machine too. The names are those its first request showed on 2.1.316 against FakeModel. Agent
  teams, on in a user's settings or the environment, added none in `-p`.
- **Codex** gets `agents.enabled = false` in the thread's config overlay, which takes away both generations of its tools, the V2
  tools a catalog model gets among them, where `features.multi_agent` takes only the first.
- **Pi** has none in its core. An extension of the user's can add one, which nothing of ours turns off, and compatibility.md says so.
- **`team check` labels an opt-in** with what it gives up, in one sentence, and `check_driver` holds a driver to the default with
  `native_children_off_by_default`, read from the tools the first request names.

## Alternatives

| Alternative | Why not |
|---|---|
| Keep them on and observed | Each of the three losses above holds for every child, and the topology is the one place authority is written |
| Tell agents in the preamble to start agents only with ours | Words a model can ignore. Both harnesses have a setting that removes the tools, so the words would be the weaker of two ways |
| `features.multi_agent = false` for Codex | Takes the V1 tools alone, and a catalog model gets V2 |
| Disallow `Agent` alone on Claude Code | `Workflow` starts agents too, and `SendMessage` reaches sessions no topology knows of |
| Refuse a role that allows them | A user may want them, as run 26 did. A warning says what it costs |

## Consequences

- A role that wants a harness's own agents says `allow_native_children = true`, and `team check` says what that gives up.
- A child still seen, as a forked skill might be, is recorded as before, with the gap `native_child_unattributed`.
- Live tests that start a native child opt in.

## Evidence

- `tests/integration/test_claude.py` and `test_codex.py`, on the real binaries against FakeModel, a catalog model's V2 tools among
  them, and `check_driver` on each driver.
- `tests/live/test_launch.py`, run 34: asked to hand a search to a sub-agent of its own, neither harness started one.
- [compatibility.md](../reference/compatibility.md), the evidence for each driver and the native features table.
