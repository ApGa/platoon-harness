# Replay a session

Play a session's record back in the terminal or the browser, from its start, at the pace it happened or faster, and go
forward and back an event or a turn at a time or to any event or moment. A replay draws the session exactly as it stood
at each point: who was working, what needed you, what changed and what each agent said, from a copy of its record that
grows as it plays. Nothing in a replay acts on the session.

**Goal:** watch how a session got where it is, stop at a moment, and step through it.

**Prerequisites:**

- platoon-harness installed as [Install](../getting-started/install.md) says;
- a session under the root, live or not: `platoon-harness session list` shows them;
- a terminal, or a browser on this machine or on another that can reach it, as [The browser](web.md#open-it) says.

## Open a replay

In the terminal:

```console
$ platoon-harness attach fix-auth --replay
```

or, on the sessions screen, choose the session and press `R`.

In the browser:

```console
$ platoon-harness web fix-auth --replay
platoon-harness: web: a replay of session fix-auth on 127.0.0.1:43211. Each link opens once, within ten minutes
platoon-harness: web: view link, which watches the replay: http://127.0.0.1:43211/view#link=…
platoon-harness: web: control link, which plays and moves the replay, and acts on nothing: http://127.0.0.1:43211/view#link=…
```

or, on the sessions page `platoon-harness web` serves, press Replay on the session's row.

A replay begins before the session's first event, paused. A live session's replay plays its record as it stood when the
replay opened, and goes no further: open another to see what came since. Opening one copies the record under the root,
in `replays/`, never in the session's own folder, which a replay writes nothing in; leaving the replay, or stopping
`web`, takes the copies back. A replay whose process was killed before it closed, by a signal, the machine going down
or a terminal closed under it, leaves its folder there, which the next replay to open, of any session, takes back.

## The banner

A replay always says it is one, at the top of the screen or the page:

```text
Replay of fix-auth, at event 120 of 10,482, 0:12:30 into it, 2026-11-09 10:42:07 UTC: playing at 4x. Nothing here acts on the session.
```

That is the event the replay stands at, of how many the record held, how long into the session it came, and when, and
how it plays. Where a client has not yet drawn where the replay went, as when it goes back, the banner names where what
it draws stands until it has.

## Play, step and jump

The controls are the same in both clients.

| Control | Terminal | Browser | Does |
|---|---|---|---|
| Play or pause | Space or `/play` | Play, Pause | Play from where it stands, or pause; from its end, from its start |
| Speed | `s` or `/speed` | Speed | The next of 1x, 4x, 16x and idle skipped |
| Step | `.` or `/step` | Step | One event on |
| Back | `,` or `/back` | Back | One event back |
| Turn | `]` or `/turn` | Next turn | To where the next turn ends, of any agent |
| Turn back | `[` or `/turn-back` | Turn back | To where the turn before ended, of any agent |
| Jump | `j` or `/jump` | Jump | To an event by its number, or to a time into the session, as `m:ss` or `h:mm:ss` |

Playing waits each event's recorded gap, divided by the speed; idle skipped plays at the recorded pace with every gap
longer than a second cut to one. A step or a turn pauses the replay; a jump while it plays plays on from where it
lands. A time is minutes and seconds, or hours, minutes and seconds, each under 60 but the first: `9:99` is no time.

In the terminal the keys work where nothing is typed: the transcript has focus as a replay opens, and Tab reaches the
navigator and the dock. In the composer, type the command, such as `/jump`. In the browser, a control link moves the
replay, and a view link watches it as it moves: each of its controls is disabled, saying so.

## What a replay shows

Everything a session shows, as it stood at the event the replay stands at: the agents and their states, which move as
the replay plays, the transcript and its folds, what needed you, what changed, tasks and entries, and each event's
provenance. What depends on the time, a timer due, a budget's wall time, a session stalled waiting for you, is as it
stood at the event the replay stands at, never as it would be now. Going back draws the session anew from that point:
in the terminal, the agent or channel in view stays in view where it was there then; the page takes a fresh snapshot.

What an agent was saying as it said it, its live text, was never in the record, so a replay has none.

**Rewards and credit**, which estimators write beside the journal, often after the session, show in an event's
provenance once the replay has reached that event, each saying when it was written, and drawn as a warning where that
was after the point the replay stands at, or where it read the trace past that point, as it was not known there:

```text
credit      0.5 by even-split, version 1, params 44136fa3, local, of the trace at head 10,482, written 2026-11-10 09:00:00 UTC, after this point of the replay, so it was not known here
```

A replay keeps what estimators had said when it opened.

## Nothing acts

A replay is a read-only copy of the record. Every act and form of the session's is disabled, and says so:

```text
A replay acts on nothing, as it is a read-only copy of fix-auth's record: open the session itself to act.
```

A diff is one: asking for one is an act, so a replay opens none, in either client, and says first:

```text
A replay reads no diff, as asking for one is an act. A replay acts on nothing, as it is a read-only copy of fix-auth's record: open the session itself to act.
```

Open the session itself, with `platoon-harness attach fix-auth` or Open on the sessions page, to act on it.

## Long sessions

A replay makes checkpoints of the session's views once it opens, one after another, at most eight, evenly spaced
through the record and at least 1,024 events apart, so a seek back, or far on, starts from the nearest and stays quick:
at 10,008 events, from 1 to 92 ms here once they were made. A record of 1,024 events or fewer has none, as a copy of it
from the start is as quick. A seek before they are made copies from the start: 1.5 s to the end of 10,008 events here,
as they were being made. They take about four times the journal's size on disk until the replay ends. One that cannot
be made, as on a full disk, is logged, and seeks go on from those made, or from the start.

The page keeps its own fold of the record, which it draws from, and a copy of it each checkpoint's spacing as it folds
past one, so a seek back in the browser starts from the nearest of those: at 10,008 events, from 16 to 270 ms here,
once the page had played or jumped that far. Its first jump far on folds every event up to there into the page, 2.8 s to
the end of 10,008 events here. The terminal keeps no fold of its own, so its seek is the replay's.

See [RFC 0080](../rfcs/0080-a-replay-is-a-read-only-copy-of-a-session-s-record-through-its-playhead.md), a draft, for
the design.
