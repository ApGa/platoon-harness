# RFC 0080: A replay is a read-only copy of a session's record through its playhead

| | |
|---|---|
| Status | Draft |
| Created | 2026-11-09 |
| Authors | Apurva Gandhi (`ApGa`) |
| Builds on | [`kernel.py`](../../packages/sdk/src/platoon_harness/kernel/kernel.py), [`session.py`](../../packages/sdk/src/platoon_harness/session.py), [`tui/workspace.py`](../../packages/cli/src/platoon_harness_cli/tui/workspace.py), [`web/server.py`](../../packages/cli/src/platoon_harness_cli/web/server.py), [architecture sections 3, 4, 5 and 12](../architecture.md#12-clients), [RFC 0003](0003-events-are-the-only-truth.md), [RFC 0011](0011-annotations-beside-the-journal.md), [RFC 0027](0027-the-browser-on-our-backend.md) and [RFC 0074](0074-the-browser-lists-starts-resumes-and-stops-sessions.md) |
| Discussion | The owner's request of 2026-11-09: "I was wondering if we have a replay functionality, where we can replay a session's history in a streaming way, with ability to move forward and backward". The owner's rulings of the same day: a replay plays in both clients, the terminal and the browser; and rewards and credit, which estimators write beside the journal after the session, are shown while replaying, each when the playhead reaches the event it is about, labelled with when it was written, so it is never passed off as known at that moment. The rest is this design's, and waits for the owner's acceptance |
| Implementation | `docs: Add RFC 0080 on replaying a session`; `feat: Replay a session from copies of its record that a seek moves either way`; `feat: Replay a session in the terminal`; `feat: Replay a session in the browser` |

## Summary

A replay of a session is a copy of its record, whose journal is the original's through a playhead: each event as it was
committed there, folded into views as the session folded it, so a client draws the copy exactly as it draws a session,
its folds, panes and agents' motion included, and the copy's state moves as the playhead does. Playing appends the next
events at their recorded pace, at 1x, 4x or 16x, or with idle gaps cut to a second. Going back starts a new copy from
the nearest checkpoint of the views at or below where it goes and copies on from there, so a seek stays quick on a long
record. The kernel gains one method, `Kernel.copy`, which makes a journal a copy of another's through a seq; a copy
takes no command, runs no daemon, and answers what depends on the time as of its newest event. The SDK gains `Replay`,
which keeps the copies under the root, never in the session's folder, and takes them back when it closes. One module of
the command line's holds the controls, the pacing and the words, which both clients use: `attach SESSION --replay` and
`web SESSION --replay` open one, and so do the sessions screen and the sessions page. A banner always says it is a
replay, of which session, at which event of how many and at what time, and every act and form says why it does nothing.
What estimators said is shown where a panel shows an event, each statement with when it was written and whether that was
after the point the replay stands at.

## Motivation

A person reads a session today as it is now: live, or as its history once no runtime holds it. Neither shows how it got
there. The journal holds every fact in order (law 1), so the record of any earlier moment is in it, but nothing reads it
as of then:

- **Views are folds through the head.** A client draws a session from the roster, attention and changes views
  ([architecture section 12](../architecture.md#12-clients)), and the kernel answers each from tables folded through the
  newest event ([section 5.5](../architecture.md#55-views)). The transcript can page back, but the navigator, the
  header, the dock and every pane say how things stand now.
- **Clients follow a journal that only grows.** The terminal's `Live` and the browser's projection each keep a cursor and
  read on past it ([`tui/live.py`](../../packages/cli/src/platoon_harness_cli/tui/live.py),
  [`web/__init__.py`](../../packages/cli/src/platoon_harness_cli/web/__init__.py) `follow`), so nothing they hold can go
  back.
- **Only an op writes a journal.** Every event is the outcome of a command ([section 5.1](../architecture.md#51-one-write)),
  so no public name appends the events another journal committed, and a client may reach no private one (law 11).
- **What estimators said has no time in a reading.** A panel shows each annotation by its producer and the head of the
  trace it read ([`provenance.py`](../../packages/cli/src/platoon_harness_cli/provenance.py) `_estimates`), which is
  right for a session as it is now and would pass a later estimate off as known at an earlier moment.

## Proposal

### 1. A copy is a journal that holds its source's events through a seq

```python
class Kernel:
    async def copy(self, source: Kernel, *, through: int) -> None:
        """Append `source`'s events past this head through `through`, each as it was committed there, with the bodies
        they name, and fold them, a page at a time."""
```

A writer kernel on a new folder copies another kernel's journal, an open read-only one included, through any seq from its
own head to its source's. Each event's row goes in as its source holds it, every column, so `seq`, `version`, `wall_time`,
`outcome` and all the rest are the source's, and each is folded as a live fold folds it; the bodies its data or outcome
names come with it, a large one's file with its row. The first copy writes `copy_of`, the source's session id, into the
journal's `meta`, which is written once, and from then on:

- a copy takes no command: `submit`, `put_body` and `recover` are refused `unsupported`, saying it is a copy, and
  `supervise` too, so no daemon runs and no effect starts (law 5);
- a copy goes on only from the journal it was first copied from, and refuses another session's `conflict`;
- a copy only grows: a seq below its head is refused `invalid`, as going back is a copy of its own;
- a journal a command wrote is no copy, and refuses to become one.

A page of events and their bodies goes in one writer job, which writes none of it where a check or a fold fails. Its views
are then the source's views as they stood at that seq, which law 1's refold already promises: the copy folds the same
events in the same order (`test_a_copy_through_a_seq_holds_its_source_s_events_as_committed_and_folds_them_as_it_did`).

A query works out what is due, spent or stalled from the time: a timer, a budget's wall time, a session waiting for its
person. A copy's queries take the wall time of its newest event as that time, not its clock's, so a copy answers as its
source did then, and a replay of a session that stalled a second in says it stalled, where today's clock would call it
done with its wall budget spent
(`test_a_replay_works_out_what_was_due_spent_or_stalled_at_its_playhead_s_time_never_now`). Every other event a session
commits enters through `submit`, and this is the one other way into a journal: only one no command wrote may take it,
and from then on it takes no command.

### 2. A replay keeps its copies under the root and moves either way

```python
class Replay:
    name: str
    total: int        # the original's head as the replay opened
    at: int           # the playhead: the newest event the copy holds
    session: Session  # a guest of the copy, which every write refuses
    folder: Path      # <root>/replays/<name>-<random>/, gone once it closes

    @classmethod
    def open(cls, name: str, *, root: str | Path | None = None) -> Self: ...  # await it or use `async with`
    async def seek(self, seq: int) -> None: ...
    async def page(self, *, after: int = 0, limit: int = 512) -> Page: ...  # the original's record through `total`
    async def close(self) -> None: ...
```

`Replay.open` reads the original through a read-only kernel, live or not, and takes its head as `total`: a live session's
replay replays its record up to that moment, and stays read-only. It keeps what estimators said, `annotations.sqlite`,
as it stood then, through SQLite's backup, and the manifest, so a client reads the copy's folder as a session's. Its
copies live in `replays/` under the root, a folder of their own per replay, never in the session's folder, which a replay
writes nothing in; `close` takes them back, and a root on a network filesystem is refused, as a copy is a journal written
here.

`seek(seq)` moves the copy either way:

- **On.** Where no checkpoint lies between the playhead and `seq`, the copy goes on from where it stands, and `session`
  stays the same guest, which follows the new events as it follows a live session.
- **Back, or far on.** Otherwise a new copy starts from the nearest checkpoint at or below `seq`, or from nothing, copies on
  to `seq`, and `session` is a guest of it. The copy before stays open until the next is made, so a client that still
  reads it as it moves to the new one reads what was there.

**Checkpoints** are closed copies, a file copy of each, which `Replay` makes on a copy of its own as it opens, evenly
spaced through the record: at most `CHECKPOINTS`, 8, at least `CHECKPOINT_EVENTS`, 1,024 events apart. A seek then folds
at most a checkpoint's spacing of events after a file copy. On a session of 10,008 events a seek took at most 91 ms where a
copy from nothing to the end took 0.46 s (`test_a_seek_on_a_10000_event_session_goes_from_the_nearest_checkpoint_within_its_budget`).

**What the session reads as.** The guest reads as the runtime does, every event and every view, as a person's principal
holds no grant before the record's first `grant.added`, so a replay at its start would answer nothing. Every write is
refused `unsupported`, saying it is a replay, a mark and an annotation among them, as a view credential's are.

### 3. Both clients play a replay through one module

`replay.py`, a new module of the command line's, is the one both clients play a replay through. It reads the record's wall
times and turn ends once, through `Replay.page`, to pace itself and to find where a control goes, and draws nothing of
them. Its `CONTROLS` are the same in both clients:

| Control | Does |
|---|---|
| `play` | Play from where it stands, at its speed, or pause; from its end, from its start |
| `speed` | The next of 1x, 4x, 16x and idle skipped |
| `step`, `back` | One event on or back |
| `turn`, `turn-back` | To where the next turn ends, or where the one before ended, of any agent |
| `jump` | To an event by its number, or to the last event by a time into the session, `m:ss` or `h:mm:ss` |

**Pacing.** Playing waits the recorded gap before each event, divided by the speed, or with idle skipped at most a second,
and takes every event within a frame, a fifteenth of a second, at once, as no client draws faster. A step, a turn or a
jump pauses it; a jump while playing plays on from where it lands. Time decides only when the next events are copied:
nothing a replay draws comes from its clock.

**The banner** says, always: `Replay of fix-auth, at event 120 of 10,482, 0:12:30 into it, 2026-11-09 10:42:07 UTC:
playing at 4x. Nothing here acts on the session.`, and why it could not move, where the replay refused a move, as one
whose original was written to since it opened can be, which pauses it and ends nothing.

**Nothing acts.** Every act and form of the session's says, in both clients, `A replay acts on nothing, as it is a
read-only copy of fix-auth's record: open the session itself to act.`, before it opens a form or sends anything, and a
replay offers no op's form: the terminal's palette lists none, and the page's Commands is disabled, saying so.

### 4. Estimates are labelled with when they were written

A panel shows an event's provenance only for an event drawn, so an estimate about an event shows once the playhead has
reached it. In a replay each says when it was written, and whether that was by the point the replay stands at, the
wall time of its newest event, or after it: `0.5 by even-split, version 1, params 44136fa3, local, of the trace at head
10,482, written 2026-11-10 09:00:00 UTC, after this point of the replay, so it was not known here`, drawn as a warning.

### 5. The terminal

`platoon-harness attach SESSION --replay` opens a replay in the workspace, and `R` on the sessions screen replays the
chosen session. It is drawn as a session is: the header says `replay` where it says `live` or `history`, and the banner
shows always. The transcript has focus, as nothing is typed to send, and the controls are plain keys there, Space,
`s`, `.`, `,`, `]`, `[` and `j`, and typed commands in the composer, `/play` to `/jump`, which the keymap table holds
and the footer, the help and the palette show. The agents move, as the replay's state moves. A copy started anew is
joined in place, keeping the agent or channel in view where it holds it, and how far you have read, which a replay keeps
in the terminal alone and writes nowhere. Leaving the replay closes it.

### 6. The browser

`platoon-harness web SESSION --replay` serves the page over a replay, and the sessions page's Replay opens one on a port
of its own, as Open opens a session. A banner under the top bar says it is a replay, with the controls beside it, each
titled with what it does; a control link moves the replay, and a view link watches it, each control disabled, saying
`A view link watches the replay: a control link moves it.` `/x/replay` takes a control and answers how the replay stands.
Every act of the session's is disabled, saying why, as `x.cannot` says it for a replay, and `/x/command`, `/x/body` and a
diff are refused. The projection folds the copy as it grows; a copy started anew gets a projection of its own, whose
`feed_id`, which now hashes the folder too, the page hears as a reset, so it draws the session anew from a snapshot. As a
replay's links act on nothing, not even as you, it is served past loopback whatever login its agents ran on.

## The hard parts

- **Going back without a hole in law 1.** A journal's events are immutable, so a copy cannot drop its newest events.
  Going back is a new copy, and the clients, which follow a journal that only grows, draw it anew: the terminal joins it
  in place and the page hears a reset.
- **A long record.** A copy from nothing folds about 20,000 events a second here, so a checkpoint every 1,024 events at
  least keeps a seek under a tenth of a second at 10,000 events. Checkpoints cost disk: at most eight copies of the
  journal at growing lengths, about four times its size, 49 MB with the copy itself at 10,000 events, which a replay
  takes back as it closes.
- **A body redacted after the playhead.** Its bytes are gone from the original, so the copy has none, and a client reads
  it as not found rather than tombstoned until the playhead reaches its tombstone.
- **Extensions' views.** A copy folds the SDK's primitives, as a session's history does, so an installed extension's
  own views are not built in a replay, though its events are copied and shown by their gists.
- **Badges.** A replay's marks are the terminal's alone, kept as it plays and across a copy started anew, and gone when it
  closes; the page keeps no marks, as for a session.

## Alternatives

| Alternative | Why not |
|---|---|
| Draw the session as it is now, and hide what came after the playhead in each client | Every view, pane and header would need a second, client-side fold of its own, which law 2 and RFC 0003 keep in the kernel, and would drift from what the session said then |
| Refold every view from the record's start at each seek | 0.46 s at 10,000 events and growing with the record; checkpoints keep a seek near 0.1 s |
| An undo log per view, to step back an event at a time | Views are arbitrary tables of each extension's, and a fold is not invertible |
| Snapshots of a live copy through SQLite's online backup | A second kernel method, where a copy that a builder closes and a file copy are enough |
| A replay served by a process of its own on the control socket | Clients would attach as a view guest and could not tell a replay from a live session to say why nothing acts |
| A new `platoon-harness replay SESSION` command | Each client already has the command that opens a session, `attach` and `web`; one flag on each is one concept in both, and the sessions screen and page each gain one act |
| Doing nothing | A person reads `events` as text, or pages the transcript back, and sees none of how the team stood then |

## Consequences

- A person can play a session's record back in either client and stop, step or jump to any moment, seeing each agent's
  state, what needed them and what changed as the record said it then.
- The kernel has a journal that no op writes. Its events are its source's, verbatim, so nothing a copy holds was not
  committed by an op somewhere, and a copy refuses every command.
- Opening a replay copies the record once more on disk, for its checkpoints, under the root, until it closes.
- A replay reads as the runtime, so it shows every event and view whatever the person's grants, which on the person's own
  machine are theirs to read through `events` already.
- What is unknown: how this behaves at the Scale case's 100,000 events, which nothing has measured; and on macOS, where
  nothing has run.

## Rollout plan

| Milestone | Scope | Exit check | Pull requests |
|---|---|---|---|
| M1 the copy and the replay | `Kernel.copy`, `Replay` and its checkpoints | `tests/unit/kernel/test_copy.py`, `tests/unit/runtime/test_replay.py`, and the budget test in `tests/integration/test_replay.py` | `feat: Replay a session from copies of its record that a seek moves either way` |
| M2 the terminal | `replay.py`, `attach --replay`, the sessions screen's `R`, the workspace in a replay | `tests/unit/cli/test_replay.py`, `tests/unit/tui/test_replay.py` | `feat: Replay a session in the terminal` |
| M3 the browser | `web --replay`, the sessions page's Replay, the page's banner and controls | `tests/unit/web/test_replay.py`, `tests/e2e/test_replay.py` in Chromium and Firefox | `feat: Replay a session in the browser` |

## Open questions

Each is taken at the default below, pending the owner's ruling, and none is built so that another answer would tear it out.

1. **Where a replay opens.** Default: `attach SESSION --replay` and `web SESSION --replay`, and an act on each client's
   sessions list, rather than the `platoon-harness replay SESSION` the brief named, so a person learns one flag for both
   clients. Adding the command would be one more name for the same thing.
2. **Who moves a page's replay.** Default: a control link moves it and a view link watches, as a view link acts on
   nothing; every page of one `web` shares one playhead.
3. **Past loopback.** Default: a replay is served past loopback whatever login its session's agents ran on, as its links
   act on nothing, not even as you.
4. **Idle skipped.** Default: the recorded pace at 1x, with every gap longer than a second cut to a second.
5. **Checkpoints.** Default: at most eight, at least 1,024 events apart. A tighter spacing buys quicker seeks for disk.

## Evidence

- `tests/unit/kernel/test_copy.py`: a copy holds its source's rows and folds to its views, carries the bodies its events
  name and no other, takes no command, stays one when opened again, only grows, and refuses another session's journal.
- `tests/unit/runtime/test_replay.py`: a replay reads as the session read at its playhead, refuses every write, keeps its
  copies under the root and takes them back, seeks either way from the nearest checkpoint, replays a live session's
  record up to its opening, and keeps what estimators said as it stood then.
- `tests/integration/test_replay.py`, slow: on this node, a seek on 10,008 events took 1 to 91 ms, a median of 43 ms,
  against 477 ms for a copy from nothing to the end.
- `tests/unit/cli/test_replay.py` and `tests/unit/cli/test_provenance.py`: pacing at each speed, steps, turns, jumps, the
  banner, and estimates labelled with when they were written.
- `tests/unit/tui/test_replay.py`, `tests/unit/web/test_replay.py` and `tests/e2e/test_replay.py`, run here in Chromium and
  Firefox, and WebKit on CI alone.
