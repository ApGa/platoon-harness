# Replay a session

Play a session's record back in the terminal, from its start, at the pace it happened or faster, and go
forward and back an event or a turn at a time or to any event or moment. A replay draws the session exactly as it stood
at each point: who was working, what needed you, what changed and what each agent said, from a copy of its record that
grows as it plays. Nothing in a replay acts on the session.

**Goal:** watch how a session got where it is, stop at a moment, and step through it.

**Prerequisites:**

- `platoon-harness` on your PATH, from a checkout installed as [Install](../getting-started/install.md) says;
- a session under the root, live or not: `platoon-harness session list` shows them;
- a terminal.

## Open a replay

```console
$ platoon-harness attach fix-auth --replay
```

or, on the sessions screen, choose the session and press `R`.

A replay begins before the session's first event, paused. A live session's replay plays its record as it stood when the
replay opened, and goes no further: open another to see what came since. Opening one copies the record under the root,
in `replays/`, never in the session's own folder, which a replay writes nothing in; leaving the replay takes the copies
back.

## The banner

A replay always says it is one, at the top of the screen:

```text
Replay of fix-auth, at event 120 of 10,482, 0:12:30 into it, 2026-11-09 10:42:07 UTC: playing at 4x. Nothing here acts on the session.
```

That is the event the replay stands at, of how many the record held, how long into the session it came, and when, and
how it plays.

## Play, step and jump

| Control | Keys | Does |
|---|---|---|
| Play or pause | Space or `/play` | Play from where it stands, or pause; from its end, from its start |
| Speed | `s` or `/speed` | The next of 1x, 4x, 16x and idle skipped |
| Step | `.` or `/step` | One event on |
| Back | `,` or `/back` | One event back |
| Turn | `]` or `/turn` | To where the next turn ends, of any agent |
| Turn back | `[` or `/turn-back` | To where the turn before ended, of any agent |
| Jump | `j` or `/jump` | To an event by its number, or to a time into the session, as `m:ss` or `h:mm:ss` |

Playing waits each event's recorded gap, divided by the speed; idle skipped plays at the recorded pace with every gap
longer than a second cut to one. A step, a turn or a jump pauses the replay; a jump while it plays plays on from there.

The keys work where nothing is typed: the transcript has focus as a replay opens, and Tab reaches the navigator and the
dock. In the composer, type the command, such as `/jump`.

## What a replay shows

Everything a session shows, as it stood at the event the replay stands at: the agents and their states, which move as
the replay plays, the transcript and its folds, what needed you, what changed, tasks and entries, and each event's
provenance. Going back draws the session anew from that point, and the agent or channel in view stays in view where it
was there then.

What an agent was saying as it said it, its live text, was never in the record, so a replay has none.

**Rewards and credit**, which estimators write beside the journal, often after the session, show in an event's
provenance once the replay has reached that event, each saying when it was written, and drawn as a warning where that
was after the point the replay stands at, as it was not known there:

```text
credit      0.5 by even-split, version 1, params 44136fa3, local, of the trace at head 10,482, written 2026-11-10 09:00:00 UTC, after this point of the replay, so it was not known here
```

A replay keeps what estimators had said when it opened.

## Nothing acts

A replay is a read-only copy of the record. Every act and form of the session's is disabled, and says so:

```text
A replay acts on nothing, as it is a read-only copy of fix-auth's record: open the session itself to act.
```

Open the session itself, with `platoon-harness attach fix-auth`, to act on it.

## Long sessions

A replay keeps checkpoints of the session's views as it opens, at most eight, evenly spaced through the record, so a seek
back, or far on, starts from the nearest and stays quick: at 10,000 events, under a tenth of a second here. They take
about four times the journal's size on disk until the replay ends.

See [RFC 0080](../rfcs/0080-a-replay-is-a-read-only-copy-of-a-session-s-record-through-its-playhead.md), a draft, for
the design.
