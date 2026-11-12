# RFC 0009: A tiny tools-only MCP server, HTTP bearer by default, and ph

| | |
|---|---|
| Status | Accepted, 2026-11-02 |

## Summary

Our own server rather than the `mcp` package, HTTP bearer by default, `ph` as the shell client

## Motivation

Agents reach coordination ops as tools. The design first planned on the `mcp` package as an optional extra. Three things pushed the other way. Identity must come only from a credential and undeclared arguments must be refused, while that SDK silently drops them. A Python `MCPServer` shim costs about 42 MB per agent. And the SDK embeds in environments we do not control, such as a Platoon rollout worker, so the tool plane should add nothing there. A spike then showed that coordination needs very little of MCP.

## Proposal

The SDK ships its own tools-only MCP server: Streamable HTTP on loopback with a per-agent bearer token, JSON replies, no SSE, no sessions. `GET` and `DELETE` return 405, and `server/discover` returns -32601. A stdlib stdio shim serves harnesses without HTTP. Identity comes from the token and nothing else. Undeclared arguments return `isError: true` and are journaled. `ph` is one stdlib file on the agent's `PATH` only, building its argv and help from `ops.list`. The server must pass contract tests against the official client and each real harness. The official client passes. Against Claude Code and Codex, only a spike's prototype had run when this was decided.

## Alternatives

| Alternative | Why not |
|---|---|
| The `mcp` package as an extra | It ignores undeclared arguments, brings a large dependency set, and is unsatisfiable beside OpenHands SDK 1.59.0 |
| A stdio shim per agent by default | One process per agent. At the SDK's weight that is about 4 GB at 100 agents. HTTP needs none |
| Identity from `clientInfo`, `_meta` or arguments | Both real clients forwarded a spoofed `caller`. `_meta` anchors are correlation evidence only |
| `ph` as the Codex coordination path | Under workspace-write a shell `socket()` to loopback failed, in one trial. MCP calls still worked, because the host makes them |
| Modern-only `2026-07-28` semantics | Codex speaks `2025-06-18` by default, so core tools must work on the oldest era |

## Consequences

- We own protocol tracking. A client that speaks only the stateless revision would need `server/discover`, which we do not implement. Both real clients reach the server through `initialize`. Claude Code tries `server/discover` first and falls back.
- The tool set is fixed per role at launch, because live list updates vary by harness.
- Connected does not mean visible. Launches need `alwaysLoad` for Claude Code and `omit_tools_from=["deferred"]` for Codex, and conformance asserts the tool is in the first model request.
- Codex needs `shell_environment_policy.exclude`, or the token reaches the agent's shell.
- A shell-capable agent at the same UID can still read another agent's token. That tier stays open, and assurance stays `cooperative`.

## Evidence

- A spike of 2026-11-02, not published: a 142-line stdlib server served real Claude Code 2.1.316 and Codex 0.164.0 for 38 harness turns, with the sandbox and token checks. Sample log: [mcp-http-probe.jsonl](../../tests/fixtures/mcp-http-probe.jsonl).
- Design-phase research, not published: Codex settles on MCP revision `2025-06-18` and Claude Code on `2025-11-25`; `_meta` carries each client's anchors; and a spoofed `caller` argument reached the server verbatim from both, so the server must bind identity. A Python `MCPServer` shim costs about 42 MB each, so a light stdio shim is the fallback and HTTP the default. [Architecture section 10](../architecture.md).

Also verified with `uv pip compile` on Python 3.12: `platoon[ors]>=0.5,<0.6` with `mcp>=2.3,<3` is unsatisfiable, because `openreward` pins `sse-starlette==2.3.6` and `mcp>=2.3` needs `sse-starlette>=3.0.0`. An unpinned `mcp` silently resolves to 1.30.0. So the SDK, which runs inside Platoon rollout workers, cannot take this dependency.
