# 0012. Waiting parks at turn end, with a monitor and a hop limit

**Status:** Accepted, 2026-11-02. The monitor's wake rule is superseded by [0023](0023-agents-that-stay.md)

## Context

An LLM agent cannot block. A held tool call has a harness cap: 300 s by default on Codex, and DeLM stops at 25 s because its harness cuts a call near 31 s. A wake costs money. A worker whose harness hides our tools must still report back. And mesh agents can reply to each other forever: budgets make that expensive, not finite.

## Decision

- **`wait` parks.** Check and registration are one transaction from `after`. The tool result says the wait is registered and to end the turn. The agent becomes `waiting` when its turn ends, not at the call. When the condition holds, the runtime starts the next turn with its delivery attached.
- **The wait lives in the service,** so a wake never depends on the model having seen the tool result. `hold` keeps a short call open below `tool_timeout_s`. A one-shot driver refuses anything longer, with the reason.
- **The monitor.** `spawn` installs one. When an agent finishes, or a turn ends with no `finish` and no open wait, the runtime posts the turn's final text to the spawning parent's inbox, as a runtime-authored event naming the child as subject. It wakes at most once per causal chain and stops at `max_hops`. Changed on 2026-11-03 by [ADR 0023](0023-agents-that-stay.md): it wakes the parent once for the spawn and once for each message the parent sent that child, and a message from a peer or a human asks nothing, so the return rule below stays rejected.
- **A report the parent is counting does not wake it,** unless the child ended badly. The wait wakes it when it holds, so a join of N costs one turn, and a failure still breaks in, past a chain's spent wake too. A wait that has only counted something of the child's doing, such as a task it settled, keeps it quiet only while someone else below the parent is at work, or the parent sleeps on what nobody is left to do. Added on 2026-11-03, after the [Pi Durable review](../research/pi-durable.md), which found each child of a join waking its parent.
- **Hop limit.** A message carries `hops`, one more than the largest in its `cause`, and a human message resets it. A wake past `max_hops` is refused and shown in attention.

## Alternatives considered

| Alternative | Why not |
|---|---|
| Blocking inside the tool call | The harness cap ends it, and it holds a turn open. Short waits use `hold` |
| Marking the agent parked at the `wait` call | Claude Code sent `wait` beside a sibling tool in 5 of 5 trials, so a wake would race that sibling |
| A return rule: final text goes to whoever caused the turn, unless already messaged | It fires on turns woken by peers, so replying becomes the default loop, a coalesced turn has several causes, and "already messaged" needs a judgment. The monitor follows one stable relation, Erlang-style |
| Interrupting as soon as work follows `wait` | The spike proposed this as a fallback. Its one trial per harness fired on `wait` itself, where the interrupt hid the result from Codex's model, so the proposed trigger, tool activity after the result, has never met a real overrun. If the model keeps working, the wait stays open and nothing breaks |

## Consequences

- Parking was clean in 10 of 10 trials with the tool visible, on cheap models told to stop. Natural overruns and long tasks are unobserved.
- A kept-alive wake cached 99% on Claude Code and 49-95% on Codex. A wake past cache lifetime is unmeasured.
- A default Codex trial never called `wait`, and nothing signalled it. Tool visibility settings matter, and the monitor covers such a turn.
- An agent with no spawning parent has no monitor, so it reports only through tools.

## Evidence

- [tools-and-parking.md](../research/spikes/tools-and-parking.md): parking, wake turns, fallback, clean-stop counts.
- [distributed-primitives.md](../research/distributed-primitives.md), section 2, the Erlang row, and the wake-storm risk. [acp-mcp.md](../research/acp-mcp.md), client support and rule 8 on blocking tools. [Architecture section 7](../architecture.md).

Decided: no interrupt fallback and no notion of a required `wait`. Interrupting spends a cold resume to save a model's own overrun, which no trial showed, and budgets already bound the cost. A turn that ends with no `wait` and no `finish` is handled by the monitor, so the silent case reaches the parent.
