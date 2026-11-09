# RFC 0080: A replay is a read-only copy of a session's record through its playhead

| | |
|---|---|
| Status | Draft |
| Created | 2026-11-09 |
| Authors | Apurva Gandhi (`ApGa`) |
| Builds on | [`kernel.py`](../../packages/sdk/src/platoon_harness/kernel/kernel.py), [`session.py`](../../packages/sdk/src/platoon_harness/session.py), [`tui/workspace.py`](../../packages/cli/src/platoon_harness_cli/tui/workspace.py), [`web/server.py`](../../packages/cli/src/platoon_harness_cli/web/server.py), [architecture sections 3, 4, 5 and 12](../architecture.md#12-clients), [RFC 0003](0003-events-are-the-only-truth.md), [RFC 0011](0011-annotations-beside-the-journal.md), [RFC 0027](0027-the-browser-on-our-backend.md) and [RFC 0074](0074-the-browser-lists-starts-resumes-and-stops-sessions.md) |
| Discussion | The owner's request of 2026-11-09: "I was wondering if we have a replay functionality, where we can replay a session's history in a streaming way, with ability to move forward and backward". The owner's rulings of the same day: a replay plays in both clients, the terminal and the browser; and rewards and credit, which estimators write beside the journal after the session, are shown while replaying, each when the playhead reaches the event it is about, labelled with when it was written, so it is never passed off as known at that moment. The rest is this design's, and waits for the owner's acceptance |
| Implementation | `docs: Add RFC 0080 on replaying a session`; `feat: Replay a session from copies of its record that a seek moves either way`; `feat: Replay a session in the terminal`; `feat: Replay a session in the browser`; and after review, `fix: Answer a replay's queries at the time its playhead stood`, `fix: Keep a replay's copy going through checkpoints and take back what a killed replay left`, `fix: Draw a replay's banner where its client has drawn it, from a fold the page keeps at each checkpoint` and `docs: Say who a replay's links read as and that it alone is served past loopback on a plan login` |

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
    spacing: int      # how many events apart its checkpoints are
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
here. A client may keep what it folds of the replay in that folder too, which goes with it. Its process holds a lock in
the folder until it closes it, or dies, so the next replay to open, of any session, takes back each folder there whose
lock nobody holds: one whose process was killed, or went down with its machine, before it closed it
(`test_a_replay_whose_process_was_killed_leaves_a_folder_the_next_replay_takes_back`).

`seek(seq)` moves the copy either way:

- **On.** The copy goes on from where it stands, and `session` stays the same guest, which follows the new events as it
  follows a live session, unless the nearest checkpoint at or below `seq` lies more than `CHECKPOINT_EVENTS` past the
  playhead. So playing or stepping on through a checkpoint never starts a copy anew, which a client would draw anew
  (`test_a_replay_played_on_through_a_checkpoint_goes_on_in_the_copy_it_has`).
- **Back, or far on.** Otherwise a new copy starts from the nearest checkpoint at or below `seq`, or from nothing, copies on
  to `seq`, and `session` is a guest of it. The copy before stays open until the next is made, so a client that still
  reads it as it moves to the new one reads what was there.

A seek once begun is finished, though whoever awaits it is cancelled, so a copy is never left half made, and `close`
lets it finish before it takes the folder back.

**Checkpoints** are closed copies, a file copy of each, which `Replay` makes one after another on a copy of its own once
it opens, evenly spaced through the record, `spacing` apart: at most `CHECKPOINTS`, 8, at least `CHECKPOINT_EVENTS`,
1,024 events apart, so a record of 1,024 events or fewer has none. A seek then folds at most a checkpoint's spacing of
events after a file copy. On a session of 10,008 events a seek took at most 92 ms, once the checkpoints were made, where
a copy from nothing to the end took 0.47 s; a seek before they are made copies from the start, which took 1.5 s to the
end as they were being made (`test_a_seek_on_a_10000_event_session_goes_from_the_nearest_checkpoint_within_its_budget`).
Each is made whole before `close` stops the rest. One that cannot be made, as on a full disk, is logged, and ends the
making, and a seek goes on from those made, or from the start
(`test_a_checkpoint_that_cannot_be_made_is_said_and_a_seek_goes_on_without_it`).

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

**Pacing.** Playing waits the recorded gap before each event, divided by the speed, or with idle skipped at most a
second, and takes every event within a frame, a fifteenth of a second, at once, as no client draws faster. A step or a
turn pauses it; a jump while playing plays on from where it lands. A time is `m:ss` or `h:mm:ss`, its seconds, and its
minutes after hours, under 60, so `9:99` is refused, saying what a jump takes. The player's clock decides only when the
next events are copied: nothing a replay draws comes from it, and what depends on the time is the copy's, as of its
newest event (section 1).

**The banner** says, always: `Replay of fix-auth, at event 120 of 10,482, 0:12:30 into it, 2026-11-09 10:42:07 UTC:
playing at 4x. Nothing here acts on the session.`, and why it could not move, where the replay refused a move, as one
whose original was written to since it opened can be, which pauses it and ends nothing. It names the event the client
has drawn through, which a client names to `Player.banner`, so it never names a point before what is on screen: going
back, a client goes on naming where the copy it shows stands until it has drawn the new one.

**Nothing acts.** Every act and form of the session's says, in both clients, `A replay acts on nothing, as it is a
read-only copy of fix-auth's record: open the session itself to act.`, before it opens a form or sends anything, and a
replay offers no op's form: the terminal's palette lists none, and the page's Commands is disabled, saying so. A diff is
one such act, as asking for one is an act, and both clients say first, in `replay.py`'s words, `A replay reads no diff,
as asking for one is an act.` and then why nothing acts
(`test_a_diff_in_a_replay_says_why_it_opens_nothing_before_anything_opens`).

### 4. Estimates are labelled with when they were written

A panel shows an event's provenance only for an event drawn, so an estimate about an event shows once the playhead has
reached it. In a replay each says when it was written, and whether it was known at the point the replay stands at: it
was not where it was written after the wall time of the replay's newest event, or where the trace it read reached past
that event, whatever the clock of the process that wrote it said, as wall times across processes are not ordered as seqs
are: `0.5 by even-split, version 1, params 44136fa3, local, of the trace at head 10,482, written 2026-11-10 09:00:00
UTC, after this point of the replay, so it was not known here`, drawn as a warning.

### 5. The terminal

`platoon-harness attach SESSION --replay` opens a replay in the workspace, and `R` on the sessions screen replays the
chosen session. It is drawn as a session is: the header says `replay` where it says `live` or `history`, and the banner
shows always. The transcript has focus, as nothing is typed to send, and the controls are plain keys there, Space,
`s`, `.`, `,`, `]`, `[` and `j`, and typed commands in the composer, `/play` to `/jump`, which the keymap table holds
and the footer, the help and the palette show. The agents move, as the replay's state moves. A copy started anew is
joined in place, keeping the agent or channel in view where it holds it, and how far you have read, which a replay keeps
in the terminal alone and writes nowhere. The workspace stops drawing the copy left behind as soon as the replay leaves
it, and its banner names the event it has drawn through until the new copy is drawn
(`test_going_back_never_draws_the_copy_left_behind_under_a_banner_naming_where_the_replay_went`). Leaving the replay
closes it.

### 6. The browser

`platoon-harness web SESSION --replay` serves the page over a replay, and the sessions page's Replay opens one on a port
of its own, as Open opens a session. A banner under the top bar says it is a replay, with the controls beside it, each
titled with what it does; a control link moves the replay, and a view link watches it, each control disabled, saying
`A view link watches the replay: a control link moves it.` `/x/replay` takes a control and answers how the replay stands.
Every act of the session's is disabled, saying why, as `x.cannot` says it for a replay, and `/x/command`, `/x/body` and a
diff are refused. As a replay's links act on nothing, not even as you, it is served past loopback whatever login its
agents ran on, by question 3's default.

The page's projection is its own fold of the record, in a folder of its own in the replay's folder, never a copy's. It
folds the copy as it grows, and folds on into the same projection across a copy started anew that holds all it has
folded, as one started on from a checkpoint does, so playing on, or jumping far on, never resets the page. As it folds
past each `spacing` events it keeps a copy of itself, through SQLite's backup, so where the replay goes back, or a kept
copy lies more than `CHECKPOINT_EVENTS` past it, a projection is started anew from the nearest copy kept at or below
where the replay went, in a folder of its own, whose `feed_id`, which now hashes the folder too, the page hears as a
reset. That projection is folded to where the replay went before the page is served it, so the page draws the session
anew from a snapshot that holds where the replay went
(`test_a_page_folds_on_across_a_copy_from_a_checkpoint_and_goes_back_from_the_nearest_copy_it_kept`). What the page is
told of the replay, in the feed, a snapshot and `/x/replay`'s answer, is where the projection it reads stands, and the
page draws the banner from the feed and the snapshot alone, holding it across a reset until it has drawn the snapshot,
so it never draws what came after under a banner naming an earlier point
(`test_a_jump_back_never_draws_what_came_after_under_a_banner_naming_where_it_went`). `/x/replay` answers once the
projection holds where the replay went.

## The hard parts

- **Going back without a hole in law 1.** A journal's events are immutable, so a copy cannot drop its newest events.
  Going back is a new copy, and the clients, which follow a journal that only grows, draw it anew: the terminal joins it
  in place and the page hears a reset.
- **A long record.** A copy from nothing folds about 20,000 events a second here, so a checkpoint every 1,024 events at
  least keeps a seek under a tenth of a second at 10,000 events, once the checkpoints are made; the seeks timed were
  timed after that. Until then a seek copies from the start, which took 1.5 s to the end of 10,008 events here as they
  were being made. Checkpoints cost disk: at most eight copies of the journal at growing lengths, about four times its
  size, 49 MB with the copy itself at 10,000 events, which a replay takes back as it closes, or the next to open takes
  back where it was killed first.
- **The page's own fold.** The page draws from a fold of its own, which folds about 5,000 events a second here, a
  quarter of the kernel's pace, so it keeps copies of itself as checkpoints are kept, and a seek in the page took 16 to
  270 ms at 10,008 events, once the page had folded that far
  (`test_a_seek_in_the_page_of_a_10000_event_replay_restores_what_the_page_folded_within_its_budget`). Its first jump
  far on folds every event up to there, which took 2.8 s to the end of 10,008 events here: it keeps no copy of what it
  has not yet folded, as making them ahead would fold the whole record in the background, from the original's events and
  bodies, which nothing reads for it.
- **Time.** A query works out what is due, spent or stalled from the time, so a copy's takes its newest event's, and a
  timer, a budget or a stall reads as it stood then, never as now.
- **What is on screen.** A client follows a copy that only grows, so a copy started anew is a moment where what it shows
  is the copy left behind while the replay already stands elsewhere. Each client names where what it shows stands, never
  where the replay went, until it has drawn the new copy.
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
- A replay reads as the runtime, so it shows every event and view whatever the person's grants. The page and the
  terminal ask a replay for nothing a session's owner does not read on a normal `web` page or in the terminal: the
  record's events through `events`, its views, provenance, and the panes a control link reads, as the owner reads every
  event already. The runtime's grants also reach its own query ops, which a person's do not, though no pane asks for
  one. Served past loopback, by question 3's default, a holder of a replay's view or control link reads what the runtime
  reads of the record through its playhead, and acts on nothing.
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
   act on nothing, not even as you. A holder of a view or control link to it reads what the runtime reads of the record
   through the playhead: every event and view, as the session's owner reads them, and nothing it could act on. Security
   and the web guide say this is the one exception to a plan login's loopback.
4. **Idle skipped.** Default: the recorded pace at 1x, with every gap longer than a second cut to a second.
5. **Checkpoints.** Default: at most eight, at least 1,024 events apart. A tighter spacing buys quicker seeks for disk.

## Evidence

- `tests/unit/kernel/test_copy.py`: a copy holds its source's rows and folds to its views, carries the bodies its events
  name and no other, takes no command, stays one when opened again, only grows, and refuses another session's journal.
- `tests/unit/runtime/test_replay.py`: a replay reads as the session read at its playhead, works out what was due, spent
  or stalled at its time on the recorded mixed team's session at events 45 and 200, refuses every write, keeps its
  copies under the root and takes them back, a killed one's by the next to open, seeks either way from the nearest
  checkpoint, goes on in its copy through a checkpoint, says a checkpoint it cannot make, replays a live session's
  record up to its opening, and keeps what estimators said as it stood then.
- `tests/integration/test_replay.py`, slow: on this node, a seek on 10,008 events took 1 to 92 ms once the checkpoints
  were made, against 474 ms for a copy from nothing to the end, and 1.5 s before they were made; a seek in the page took
  16 to 270 ms once the page had folded that far, and its first jump to the end 2.8 s.
- `tests/unit/cli/test_replay.py` and `tests/unit/cli/test_provenance.py`: pacing at each speed, steps, turns, jumps, a
  time that is no time refused, the banner at the place a client has drawn, and estimates labelled with when they were
  written, one of a trace past the playhead as not known there.
- `tests/unit/tui/test_replay.py`, `tests/unit/web/test_replay.py` and `tests/e2e/test_replay.py`, run here in Chromium and
  Firefox, and WebKit on CI alone, the last with a MutationObserver that looks at each change the page makes to itself
  across a jump back.
