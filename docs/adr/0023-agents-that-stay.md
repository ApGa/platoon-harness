# 0023. Agents that stay

**Status:** Accepted, 2026-11-03

## Context

The owner asked for a spawned agent that stays for follow-ups: a parent spawns one for a task, it answers, and later the parent sends
it another task or asks what it meant. The runtime nearly allowed it. A turn that ends leaves an agent idle with its process and its
conversation, and a message wakes it. Three things stood in the way. The preamble told every agent with a parent to make
`agent.finish` its last call. The monitor woke a parent at most once per causal chain for each child, so the answer to a follow-up
reached nobody: a scripted parent that re-tasked its child by message stalled after the second round. And an idle child that ended
with its parent was recorded `cancelled`, which Platoon drops from training, though it was cut off from nothing.

[The review](../research/persistent-agents.md) found that most systems keep a child after its first task, none lets the spawner
choose, several notify a parent for the first task only, and almost none bounds a loop by mechanism.

## Decision

- **`stays`**, on a role and on `agent.spawn`, which overrides the role either way. It is resolved once, at the spawn: the spawn's
  word, else the role's, else true for an agent the session started and false for one spawned. `agent.spawned` records it.
- **A harness that is not persistent cannot stay.** `team check` refuses a role that says it stays on one, and `agent.spawn` refuses
  `stays` for it `unsupported`, from what the role's driver said when the session opened.
- **What an agent is told about ending follows `stays`.** One that does not stay makes `agent.finish` its last call. One that stays
  with no parent stays unless told to finish, as before. One that stays with a parent is told to answer by ending its turn, that what it
  says last goes to its parent, that a turn that only ends leaves it there for the next message, and to call `agent.finish` only when
  told to. The role's own words come after the preamble, so a role has the last word.
- **A report wakes its parent only for what the parent asked.** The spawn asks, and so does each message of the parent's own, to the
  child's inbox, that the child is handed. A report that wakes the parent answers. So a parent is woken once for the spawn and once
  more for each message it sent that child, within `max_hops` and budgets. A turn that parks, or that an interrupt or the owner's stop
  cut, answers nothing yet. A message from a peer or a human, and a parent's broadcast, asks nothing, so ADR 0012's reason for
  rejecting a return rule holds. This is every child's rule, and it replaces once per causal chain.
- **The result of a spawn that stays says so**, that its answers come back at the end of each of its turns, and how to end it:
  `agent.retire` when it is idle, `agent.cancel` at any time, or telling it to finish. A result's `next` is taught in the words of its
  surface, as a refusal's next step is. A `max_children` refusal says that ending a child makes room.
- **An agent's `wait` for the end of one that stays is refused** `invalid`, naming `from` for its answers and `agent.retire` to end
  it. That end comes only when someone ends it. A human or a program may still wait for it.
- **A child that ends with its parent ends `cancelled` if it was at work, in a turn or on its way to one, and `retired` otherwise.**
  This is every child's rule. `session.cancel` ends every agent `cancelled`, deepest first, so that none ends as its parent's child.
- **`team check` warns of a wake cycle that closes through a child that can stay.** It flags a team in which a role may spawn a role
  whose harness is persistent, can message it by an edge, and both their inboxes wake, with no `max_hops`. Any persistent child can
  stay, since a spawn may ask, so every such team is flagged, a manager-worker team among them. It warns rather than refuses, because
  that cycle is how follow-ups work and a budget bounds it too. A cycle that does not need such a pair is still refused.
- **An ended agent stays ended.** `agent.interrupt` is the stop that keeps an agent. No new verb was added.

## Alternatives considered

| Alternative | Why not |
|---|---|
| Tell a child to message its answer | It leans on the model, it says what the monitor already posts, and a child's message wakes a parent its report would have left to a join: a turn per worker, in the spike |
| Keep once per causal chain, with a parent's message starting its child's chain afresh | A turn hears several entries, and one from a peer's chain spends the wake the parent's message asked for. A human's message would start one too, which brings back the return rule's loop |
| Ask at a message sent, not one handed | A second message sent while the child answers the first is answered by that first report, and the second answer wakes nobody |
| Count asks, and spend one per report | Two messages handed in one turn leave an ask over for a later turn that nobody asked for |
| Answer at any turn's end | A turn that parks, or one cut short, has answered nothing yet, and the turn after it would wake nobody |
| Flag only roles that say `stays = true` | `agent.spawn` can ask any persistent child to stay, and the owner's flow does just that, so nothing it does would be flagged |
| Refuse the cycle, as a peer cycle is | Every tree team with a persistent child and no `max_hops` would be refused for using a follow-up |
| Refuse `wait` with `agents` on a staying child for humans and programs too | They can end it themselves, and a program's control flow is its own |
| A verb that releases a child, besides `retire` and `cancel` | `interrupt` stops a turn, `finish` and `retire` end an agent with a report or quietly, and `cancel` is the kill |
| End every agent left idle when a session closes | That is M3's close of idle children, below, and an agent the session started is someone's conversation |

## Consequences

- A child that a peer or a human set to work reports into its parent's next turn. One whose parent counts it on a wait leaves that
  ask open, so a later report of its may wake the parent once more.
- A parent and a child that stays can wake each other until `max_hops` or a budget stops them, and `team check` says so.
- `stays` adds a field to `agent.spawn` and a sentence to the preamble of a child that stays. Each default role's tool list stays under
  its ceiling.
- The runtime asks each role's driver to describe itself when it opens a session, to learn whether its harness can stay.
- A session that closes ends no agent. One left idle has no end in the journal, which is unknown and not `cancelled`.
- A child that waits on its parent keeps its answer from it: a turn that parks posts no report, and one that holds a `wait` has not
  ended. Twice on Codex a child told it stays for the next message did that, so the words for a child that stays say what a root's
  have said since run 17, and nothing of waiting. That they hold on Codex has not been shown.
- Deferred, at M2: an idle child's process is released, and resumed natively at its next message, by the path a harness that dies
  while idle will take.
- Deferred, at M3: Platoon gives one trajectory one reward, so a child's several tasks share one reward unless each becomes its own
  spawn, and idle children are closed cooperatively before a rollout returns.

## Evidence

- [persistent-agents.md](../research/persistent-agents.md): the systems reviewed, and the scripted runs of cases A to G.
- `tests/unit/primitives/test_lifecycle.py`, `test_waits.py`, `tests/unit/tools/test_surface.py`, `tests/unit/topology/test_check.py`
  and `tests/unit/runtime/test_session.py` hold each promise. The owner's flow ran on the real Claude Code, Codex and pi binaries
  against FakeModel in `tests/integration`: one process, three turns, the lead woken by each answer and by nothing else.
- On real models, [the spike](../research/spikes/real-harness.md), sections 13 to 15: the owner's flow passed on Claude Code in 13
  calls, and failed on Codex, where a child held a `wait` for its parent instead of answering. A Codex agent spawned with `stays`
  answered and stayed, where without it a role's words alone did not keep it from finishing.
- [Architecture section 7](../architecture.md), the monitor and Lifecycle, and section 8, `team check`.
