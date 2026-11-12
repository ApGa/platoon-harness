# RFC 0029: A harness names our tools as it shows them

| | |
|---|---|
| Status | Accepted, 2026-11-04 |

## Summary

`tool_names` on `Capabilities`, `bare` for OpenHands, picks the surface our words and a tool's URL use

## Motivation

What an agent is told names our tools: the preamble, a handover, a refusal's reason and a tool's description each say
`mcp__ph__task_claim` on a harness that reaches them by MCP, because Claude Code, Codex and pi each show a server's tools under the
server's name. The host chose that surface from `tool_paths` alone. OpenHands shows a server's tools by their own names, so an agent
on it would be taught tools it does not have, and a model that calls `mcp__ph__wait` there calls nothing. The tool server already
spoke a surface with no namespace, `?surface=mcp`, which no harness asked for.

## Proposal

- **`tool_names` on `Capabilities`:** `namespaced` unless a driver says otherwise, or `bare`. The host picks the surface from it and
  `tool_paths`, and names it in the tool URL, so our words and the model's tools agree.
- **The OpenHands driver says `bare`,** and its agents are told `task_claim`, `wait` and the rest as the model sees them.

## Alternatives

| Alternative | Why not |
|---|---|
| Teach every agent bare names | Claude Code, Codex and pi show them prefixed, so their agents would be taught tools they do not have |
| Rename OpenHands' MCP tools in the worker to `mcp__ph__*` | It needs a client of our own in place of the SDK's, for a name the model never needed |
| OpenHands through `ph` alone | Every call would be a terminal command, which asks the runtime as any does, and our token would have to stay where the terminal reads it |
| Read the surface from the tool names `ready` says | A harness may say none, as it is a list only when observed, and the words are chosen before `ready` |

## Consequences

- A driver of a harness that shows a server's tools as they are listed says `bare`, and a third party's that says nothing keeps
  what it had.
- `tools.surface_of` takes a harness's capabilities, where it took its tool paths.

## Evidence

- `tests/unit/runtime/test_host.py`, `test_a_harness_that_shows_our_tools_by_their_own_names_is_told_them_by_those`, and
  `tests/unit/tools/test_surface.py`.
- `tests/integration/test_openhands.py`: what the journal says an OpenHands agent was told names `peers` as its first request shows
  it, on the real SDK against FakeModel. Design-phase research of the OpenHands SDK, not published: a tool `post` stayed
  `post`.
