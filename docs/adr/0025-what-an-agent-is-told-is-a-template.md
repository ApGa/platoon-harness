# 0025. What an agent is told is a template

**Status:** Accepted, 2026-11-03. Amended the same day: `peers`, `roles` and `channels` are values, as the owner was told.

## Context

The owner asked to configure what agents are told at launch. Only a role's own `instructions` could be set. The generated part, the
preamble, was fixed code; nothing recorded what an agent was told; and a role's words did not name tools as the agent's harness does.
The preamble's wording mattered more than any mechanism in the live runs, so a team must be able to change it without losing what
the runtime knows: the exact tool names, who can be reached, and how to end.

## Decision

- **A template on the team, and one on a role in its place.** `preamble`, as the code already called it. Left out it is `PREAMBLE`,
  which renders what the code said before byte for byte, for every preset's roles on each surface, as a test holds.
- **Slots are words in braces**, `{{` and `}}` write a brace, and the runtime fills them per agent and per surface: `name`, `tools`,
  `peers`, `roles` and `channels` are values, as `@a, @b` for `peers`, and `help`, `waiting` and `ending` are sentences of ours, taught
  as before, so one naming a tool the agent lacks is left out. Each is empty where it would say nothing. The default carries our words
  around the values, as `You can message: {peers}.`, so a template words those lines as it likes. A line whose slots all come out
  empty is left out, words and all. A line with no slot, and every word of `Role.instructions`, is never dropped. A slot nobody fills
  is refused when the team loads.
- **Words a user wrote name tools as the surface does.** An op in backticks, in a template's words or in `Role.instructions`, becomes
  the surface's tool name. `team check` warns of one a role cannot hold, and of a template that leaves out
  `tools` or `ending`, saying what breaks: an empty template leaves out both, and tells the role's words alone. A harness that reaches
  none of our tools is told `instructions` alone, so `team check` refuses a role's own template there and warns of its team's. The
  role's own words come last.
- **`agent.instructed` journals the exact text** at a launch and at every resume. A harness that reopens its own session is handed
  the text it was told when that began, since Claude Code and Codex keep that whatever a resume passes. The harness's own prompt and
  the user's own configuration are theirs, and neither is recorded nor changed.
- **`told(team)`** renders what an agent of each role would be told, on a session thrown away after, which starts no harness and has
  no limit or budget, as no text says one.

## Alternatives considered

| Alternative | Why not |
|---|---|
| Seven slots, as asked | The `ph` surface has a line telling how to ask for a tool's arguments, which no MCP surface has. Without a slot for it the default could not render what it did before on that surface, and a template could not place it |
| Append that line after the line holding `{tools}` | A rule a template writer cannot see or move |
| `str.format` with its full grammar | Attributes, indexes and format specs fill nothing here, and a template is a user's text: a slot is a word, and anything else is refused |
| Drop a user's sentence that names a tool the role lacks, as ours are | Words a user wrote are theirs. A warning before any cost says what is wrong |
| `peers`, `roles` and `channels` as sentences of ours, and a template's own words kept whatever their slots came to | A template could not word a line around a value, and the owner had been told they would be values. A line around a value that came out empty, as `You can message: .`, says nothing, so it goes, words and all |
| Warn of a template line that can come out empty | Whether it does depends on the agent and the moment, and going is what a line of words around a value asks for |
| Render the text again at a resume | Claude Code and Codex keep what a session began with, so the journal would hold words no model heard |
| Record the whole system prompt | It is the harness's and the user's, and on a native login only the harness sees it |
| Render `told` from the team alone | Who an agent can reach comes from the live graph, so a second derivation would drift from the one a session uses |

## Consequences

- A session's record shows what every agent was told, and a test reads it back from the first request on each real binary.
- A template that leaves out `tools` or `ending` runs, with a warning, since a team may teach those its own way.
- `platoon-harness team told` prints `told(team)`.

## Evidence

- `tests/unit/tools/test_surface.py`, the default against a frozen copy of the code before it, and the template's rules.
- `tests/unit/runtime/test_host.py`, `tests/unit/topology/test_check.py`, and `tests/integration/` on the real Claude Code, Codex and
  pi binaries against FakeModel, at a launch and after a resume. Resumed with other text, Claude Code 2.1.316 and Codex 0.164.0 sent
  the text the session began with, and pi 1.5.0 the text it was passed.
- `tests/live/test_launch.py`, run 34: a team's template with one sentence more was told and acted on, on Claude Code and Codex.
- [Architecture section 10](../architecture.md), the everyday instruction surface.
