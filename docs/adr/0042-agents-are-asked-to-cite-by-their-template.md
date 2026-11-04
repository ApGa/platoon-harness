# 0042. Agents are asked to cite by their template, on by default

**Status:** Accepted, 2026-11-05

## Context

Every write of content takes `based_on`, and every citation is checked and kept as its citer's claim
([ADR 0036](0036-one-ref-names-what-a-model-is-shown.md)), but nothing asked an agent to cite, so the declared edges that make
`contributors` and credit research worth having came only from agents that thought to. The owner wants provenance to be a selling
point, and asked that agents be asked to cite by default. What an agent is told is a template
([ADR 0025](0025-what-an-agent-is-told-is-a-template.md)), and a tool's description is fixed, so asking there could not be turned
off.

## Decision

- **A ninth slot, `citing`, holds one sentence of ours:** "When what you write rests on something you read, put its `ref` in
  `based_on`." It is filled for an agent that holds a write of content, an op whose arguments take `based_on`, and is empty
  otherwise, as every slot is where it would say nothing.
- **The default template asks.** `PREAMBLE` has the slot on a line of its own, between `waiting` and `ending`, so the default renders
  what it rendered before and that one line more.
- **The slot is the one place an agent is asked.** A tool's description says what `based_on` is, "Refs this write rests on.", and
  never asks, so a template without the slot asks nothing, and a citation an agent makes all the same is checked and kept as before.

## Alternatives considered

| Alternative | Why not |
|---|---|
| A `cite = true` setting on a team or a role | A second way to change what agents are told, beside the template that already does |
| Off by default | It hides what the owner wants to sell, and a team can leave the slot out |
| A citation required on every write | Nobody asked for it, and an agent with nothing to cite would be refused for telling the truth |
| Asking in tool descriptions | They are fixed, so asking could not be turned off, and they are in every request of every agent whatever it holds |
| Filling the slot for every agent | One that holds no write of content would be asked for what it cannot do |

## Consequences

- The cost, stated in full: 78 bytes in every request of an agent that holds a write of content, 20 tokens by Qwen3's tokenizer,
  as Claude's and GPT's are not at hand to count with; nothing in the tool list, which already described `based_on`; and a refused
  write and its retry for each citation that names nothing, or no lines of its event.
- A team that copied the default before this keeps its own text, which asks nothing, until it adds the slot.
- If more than one write in ten were refused for a citation on real models, the default would go back to the owner. The live runs
  below refused none; two runs measure no rate.
- Citing moves credit along declared edges, so a trained policy may learn to cite nothing, or agents to cite each other in rings:
  a declared edge never feeds a reward alone, without exposure beside it.

## Evidence

- `tests/unit/tools/test_surface.py`: `test_the_citing_sentence_is_said_to_every_agent_holding_a_citing_tool`, for every preset's
  roles on each surface, `test_with_no_citing_slot_no_surface_text_asks_to_cite`, and the default template held to what it said
  before plus the line. The tool-list ceilings, measured again: 23,823, 22,876 and 6,427 bytes for a lead, a worker and a narrow role.
- `tests/live/test_citing.py`, a person's checklist on a board and a lead starting a worker to read it, on the default template: on
  `claude-haiku-5-5`, run 72, 6 model calls, the worker's `agent.finish` cited the checklist it had been shown and the lead's spawn
  cited nothing; on `gpt-6-luna` at low effort, run 73, 9 calls, the lead read the checklist itself and its spawn cited it. Every
  citation resolved and was `seen` by its citer, and no write was refused for a citation.
