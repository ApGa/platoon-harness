# Concepts

This page is the picture behind the words the rest of the documentation uses. Read it once before
[your first session](first-session.md). [Architecture](../architecture.md) is the design of record, and its
[section 2](../architecture.md#2-vocabulary) defines each word.

## What it is, and what it is not

platoon-harness runs the agent harnesses you already use, such as Claude Code, Codex, pi and OpenHands, as one team in a
durable session, and gives them, you and your scripts one way to act on it.

- **Not a model server.** Harnesses do the thinking: each reaches its model as it always does, on its own login, on a
  key its role's auth profile names, or through a training system's gateway. A person's message lands at the earliest
  boundary its harness has. Nothing claims mid-generation.
- **Not an agent framework to adopt.** A harness stays the program it is, and a driver presents it to the runtime. You
  write no agent code to use one: a role names it, as `harness = "claude"`.
- **Not a reader of your credentials.** Nothing here reads, copies or stores a harness's login
  ([compatibility](../reference/compatibility.md#7-auth-and-terms)), and an auth profile names variables, never values.
- **Not a scheduler.** A team says what may happen, never what happens next: control flow belongs in a
  [Python program](../how-to/topologies.md#run-a-program-from-python).

## A session, on disk

A [session](../architecture.md#2-vocabulary) is a folder holding one journal. The mixed team's session from
[your first session](first-session.md), named `first`, holds this, among the rest:

```text
<root>/sessions/first/
  journal.sqlite    every event of the session, in order
  manifest.json     the resolved team, who started it and how; no secrets
  agents/lead/      the lead's own state, which the runtime keeps
  agents/fixer/     the worker's
```

Everything that happens is an event in the journal, so a session can be watched from several clients at once, stopped,
resumed, and read back later. The terminal UI, the browser, the command line, your Python script and the agents' own
tools are all clients of the same operations, so closing any of them changes nothing. The root is where every session
lives, which `platoon-harness doctor` names ([install](install.md#check-the-installation)).

## One session, traced

The [team](../architecture.md#2-vocabulary) of [the mixed team](../../examples/mixed-team/README.md) has two
[roles](../architecture.md#2-vocabulary), `lead` and `worker`, and the `manager-worker`
[topology](../architecture.md#2-vocabulary) preset. A run in which each agent does as its job asks journals this, as
`platoon-harness events first` prints it, in this order:

1. You send the job to `@lead`: a `message.sent` on the stream `inbox/lead`, the lead's inbox, a
   [channel](../architecture.md#2-vocabulary).
2. The message wakes the lead, an [agent](../architecture.md#2-vocabulary) of the role `lead`, and its
   [harness](../architecture.md#2-vocabulary) begins a [turn](../architecture.md#2-vocabulary): `agent.woken`, then
   `turn.started`.
3. In its turn the harness calls the tools the runtime gave it. `task_add` puts a task on the queue `tasks`, a
   `task.added` on `task/tasks/1`, and `agent_spawn` starts the worker `fixer` in the role `worker`, an `agent.spawned`.
   Then the harness stops, and the turn ends: `turn.ended`.
4. The worker's turn claims the task, `task.claimed`, fixes the bug in your copy and runs the tests with its own
   terminal, each command an `item.recorded`, posts a note on the board `notes`, a `board.posted` on
   `board/notes/fix-1`, completes the task, and finishes. Its last words reach the lead's inbox as a message.
5. That message wakes the lead for a second turn, which reads the note and the code and finishes, citing the note.
6. The lead's finish closes the session, as the preset says, and once nothing more can happen it has settled.

The topology allowed each step: under `manager-worker` the lead may add to `tasks` and its workers claim from it, and
everyone shares the board `notes`. Had a harness asked before running something, an
[approval](../architecture.md#2-vocabulary) would have waited in the journal, to be resolved once, by you or a stated
policy.

## What keeps it true

Twelve laws, each a sentence with a test of the same name, say what stays true of every session, whatever its harnesses
and clients do: [architecture section 3](../architecture.md#3-laws) states them.

## Next steps

- [Your first session](first-session.md): run that team, read it back, then run your own harnesses.
- [The team file reference](../reference/team-file.md): every key of a team file.
- [Topologies](../how-to/topologies.md): a worked team for each preset.
