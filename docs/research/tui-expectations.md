# TUI expectations: what users expect from an agent TUI, and how to build ours

Milestone 0 research, retrieved 2026-11-02. Tags such as [E7] resolve in the Evidence appendix.

## Inspected

| Project | Commit or version | Date | License | Use |
|---|---|---|---|---|
| Toad | `dd4f90e8b370` (0.6.20) | 2026-05-26 | AGPL-3.0 | **Inspiration only: no code reuse, no dependency** |
| OpenHands-CLI | `283c6ac3610f` | 2026-10-22 | MIT | Code; closest stack (Textual) |
| pi | `c9f4c7b9fcd0` | 2026-11-01 | MIT | Code and docs |
| prime-agent | `c6d4da9421e6` | 2026-10-30 | MIT | Code (`pa-tui`) |
| Codex | `05c08d765523` | 2026-11-02 | Apache-2.0 | Code (`codex-rs/tui`) |
| OpenCode | `ff90ed91607c` | 2026-11-02 | MIT | Code (`packages/tui`, `packages/cli`) |
| Claude Code | `f0b737f94f3b` plus official docs | 2026-11-02 | Proprietary | Closed source: changelog and docs, UX inspiration only |
| Hermes Agent | Official docs, no clone | 2026-11-02 | MIT per docs | Docs only |
| Textual / Rich | 8.2.8 (latest) / 15.0.0 | 2026-11-02 | MIT | Installed and probed |
| pytest-textual-snapshot | 1.0.0 run; 1.1.0 latest | 2026-11-02 | MIT | Run |
| textual-serve | 1.1.3 | 2026-11-02 | MIT | Run on loopback |
| asciinema | 2.4.0 (pip) | 2026-11-02 | GPL-3.0+ | Run; dev tool only |

GitSwarm has no TUI, so it was not needed here. Labels: **IMPL** code on default branch, **DOC** documented only, **EXP** experimental or preview. No DRAFT/RFC capability is relied on.

## Bottom line

1. **Adopt Textual, with a sanitizing boundary of our own.** It protects against neither hostile markup nor hostile escape sequences.
2. **Hostile escapes reach the terminal through every widget tested, including `markup=False`** (real PTY, effects confirmed in an emulator).
3. **One crafted string crashes the app** in any default-markup widget; a well-formed one runs an app action on click.
4. **No widget-per-message transcript.** Append cost grows with DOM size (132 ms at 1k, 729 ms at 5k); Line-API views held 40-50 ms at 400k-1M rows.
5. **Coalesce deltas to 10-20 Hz.** Per-token updates were the problem, not concurrency.
6. **Multi-agent UX has converged on a status-grouped roster with drill-down.** Nobody has solved waiting reasons, cross-agent causality or approval scale. That is our opening.

## 1. Feature catalog

**Td** Toad, **OH** OpenHands, **Pi** pi, **Pr** Prime, **Cx** Codex, **Oc** OpenCode, **CC** Claude Code, **He** Hermes. IMPL except CC and He (DOC); `*` is preview. An omitted tool means "not found", not proof of absence.

| Feature | Who has it | Priority | Our note |
|---|---|---|---|
| Multiline composer | all [E1-E4] | Must | `TextArea` subclass |
| History, reverse search | all; Ctrl+R in OH, Cx, CC [E5] | Must | Per project |
| Paste, collapse big paste | Oc, CC, He, Cx [E6,E7] | Must | Bracketed; a paste never submits |
| @-file mentions | Td, OH, Pi, Pr, Cx, Oc, CC [E8,E9] | Must | Plus `@agent`, `#channel` |
| Images | Pi, Pr, Cx, Oc, CC, He [E10] | Should | Disabled with reason per harness |
| Slash commands | all [E11,E12] | Must | Small core plus namespaced passthrough |
| Command palette | Td, OH, Oc [E13] | Must | Textual `Provider` |
| Approvals UX | Td, OH, Pr, Cx, Oc, CC, He; none built in for Pi [E14,E15] | Must | Central queue (section 6) |
| Permission modes | CC (6), Cx, OH, Oc, Td via ACP [E16,E17] | Must | Per agent; never invent a mode |
| Diff review | Oc (richest), CC, Cx, Pi, Td, OH [E18,E19] | Must | Per agent and aggregate, hunks, reviewed marks |
| Streaming Markdown/code | all [E20] | Must | Coalesced live tail |
| Thinking display | Td, Pi, Cx, CC [E21] | Should | Only provider-exposed text |
| Tool render and collapse | all; Ctrl+O in Pi, Pr, OH, CC [E22] | Must | Collapsed, grouped |
| Background tasks | CC, Oc, Cx, He [E23] | Must | Every agent already runs apart from the view |
| Session list/resume | all [E24] | Must | Run-level plus native resume |
| Session fork/tree | Pi, Pr, Cx, Oc, CC [E25] | Should | Harness-specific, disabled with reason |
| Compaction | OH, Pi, Pr, Cx, Oc, CC, He [E26] | Must | Pass through; record the event |
| Model switching | Pi, Pr, Cx, Oc, CC, He; OH via settings [E27] | Must | Per agent, where the harness allows |
| Cost/usage | OH, Cx, Oc, Pi, Td, CC, He [E28] | Must | Label estimates and gaps; budget meter |
| Transcript search | Cx, CC*, Pr roster [E29] | Must | `/`, `n`, `N` |
| Scroll, jump to latest | Pi, Cx, Oc, CC*, Td, OH [E31] | Must | Section 3 |
| Vim mode | CC, Cx; Pi extension [E32] | Later | |
| Themes | Cx, Oc, Pi, Pr, CC, He, Td; OH one theme [E33] | Should | Dark, light, ANSI |
| Notifications | Cx, Oc, Td, Pi [E34] | Should | "Needs you" only |
| Shell escape | Td, Pr, Pi, CC, He [E35] | Should | A human-provided context event |
| MCP management | Cx, Oc, Pr, OH, Pi, CC [E36] | Should | Read-only per agent first |
| Skills/plugins | Cx, Oc, Pi, Pr, OH, CC, He [E37] | Should | Per harness; no unification claim |
| Hooks | CC, Cx, OH; Pi, Oc extensions [E38] | Should | Display; do not re-implement |
| Project instructions/memory | all [E39] | Must | Preserve native files |
| Doctor/init | Pr, He, Cx `/init`, CC [E40] | Must | Brief section 8 |
| Headless JSON | Cx, Pi, OH, Oc, CC, Pr `--print` [E42,E43] | Must | JSONL plus cursors |
| Exit codes | CC: 0, non-zero, 143 on SIGTERM; no full table found elsewhere [E43] | Must | Publish a real table |
| Roster, unread/mention | Cx, Pr, CC*, He; Oc tabs [E44-E46] | **Must** | Core surface |
| Provenance, "why waiting" | none | **Must** | Ours alone |
| Selection, copy | Cx, Pr, CC*, Td, He [E47] | Must | `get_selection` on custom widgets |
| Embedded terminal | Td, Oc [E48] | Later | Brief forbids it as a first milestone |

## 2. Keybindings

Conventions: Enter sends and Ctrl+J is the universal newline [E1-E3]. Esc interrupts (Cx, Oc, Pi, CC, OH); Ctrl+C clears a draft first in Pi, CC, He [E49]. Ctrl+O expands tools in four tools [E22]. Ctrl+G opens the editor in Cx, Pi, CC, He [E50]. Ctrl+Z suspends in Pi, Pr, CC, He [E51]. Ctrl+P is the palette in Textual, Oc, Td, but cycles models in Pi [E13]. Shift+Tab cycles permissions in CC but thinking in Pi and agents in Oc [E16]. Cx switches agents with Alt+Left/Right; Oc uses Up, Left, Right on an empty prompt [E44,E52]. Oc's leader is Ctrl+X [E53].

Terminal limits: Ctrl+H is Backspace, Ctrl+I Tab, Ctrl+M Enter, Ctrl+[ Esc on legacy terminals (so Toad's Ctrl+[ binding is fragile). Shift+Enter needs the Kitty protocol, which Textual requests [E54], and tmux needs `extended-keys` [E55]. Ctrl+digit needs enhanced keys too, so prefer Alt+digit.

Proposal, all rebindable, with help generated from the effective keymap as in Pi and Prime [E56]:

| Scope | Key | Action |
|---|---|---|
| Composer | Enter | Send to target; a busy agent queues with a visible chip |
| Composer | Shift+Enter, Alt+Enter, Ctrl+J | Newline |
| Composer | Ctrl+R / Ctrl+G / Ctrl+S | History search / external editor / stash draft |
| Composer | `/`, `@`, `#`, `!` | Commands, agents and files, channels, shell |
| Global | Ctrl+P; F1 or `?` on empty | Palette; help |
| Global | Esc | Dismiss overlay, else interrupt the **focused** agent only |
| Global | Ctrl+C | Copy selection, else clear draft, else interrupt; twice exits |
| Global | Ctrl+D on empty | **Detach.** Service-owned runs continue; embedded runs ask |
| Global | Ctrl+X Ctrl+K | Stop all, two-press |
| Global | Alt+A | Next item needing you |
| Global | Alt+Left/Right; Alt+1..9 | Previous/next agent; jump to row |
| Global | F6, Shift+F6 | Cycle pane focus |
| Global | Ctrl+B; Ctrl+X I; Ctrl+T | Navigator; inspector; tasks and board |
| Global | Ctrl+O; Shift+Tab | Tool detail; permission mode, or a disabled reason |
| Global | Ctrl+L; Ctrl+Z | Redraw; suspend |
| Transcript | `/`, `n`, `N`; `{`, `}` | Search; previous/next turn |
| Transcript | PgUp/PgDn, Ctrl+Home/End | Scroll; top; latest plus follow |
| Approval | `y`, `a`, `n`, `e`, Tab | Once, always (scope shown), deny, feedback, details |

Ctrl+B is the navigator, not "background" as in CC and Oc, because nothing in our model is foreground-bound.

## 3. Layouts, multi-agent UX, scroll

All tools share the baseline of transcript, input dock, status line. Pi states it best: a `follow: "end"` scroll view over a fixed dock, in about 45 lines [E31].

| Tool | Pattern | Status | Takeaway |
|---|---|---|---|
| Toad | Session tabs, Ctrl+S grid, sidebar, keyboard block cursor [E57] | IMPL | Concurrent sessions, not a team |
| OpenCode | Tabs with next-unread, sidebar, terminal pane, composer subagents tab, parent/child nav [E52,E58] | IMPL | Unread jumping is a first-class key |
| Codex | Command center filters **All, Needs you, Working, Ready, Inactive**; `/subagents`; foreign tasks open read-only [E44] | IMPL | Groups by what the human must do |
| CC teams | Panel under input, Enter opens transcript, prompts surface in lead; split panes need tmux or iTerm2 [E30] | EXP | No in-process resume, one team, no nesting, fixed lead |
| CC agent view | **Pinned, Ready for review, Needs input, Working, Completed**; Space peeks and replies; supervisor owns processes [E46] | EXP | Peek-and-reply is the best idea here |
| Prime | Roster grouped Running/Idle/Inactive, prompt doubles as search, subtree scope; `/factory` state rows with occupancy and budget [E45] | IMPL | Pure views over a roster subscription |
| Hermes | Work dock compressing to one line; Ctrl+T roster; steer, stop; per-branch rollups [E59] | DOC | Good narrow-layout primitive |
| pi | Deliberately no subagents; extensions add them [E60] | IMPL | A stance, not a pattern |

**Unsolved everywhere:** showing why an agent waits (which message, claim, barrier, human); causality across agents, since all tools show trees while real teams form graphs; approval fatigue, where CC's advice is to pre-approve because prompts "bubble up" [E30]; mixed-harness identity with honest gaps; peer teams with no root; two clients resolving one approval.

| Tool | Follow | Preserving position |
|---|---|---|
| CC fullscreen* | Scroll-up pauses | `Jump to bottom` with "3 new messages", sticky last-prompt header; prompts still force into view [E31b] |
| Codex | Needs tail position and no selection | Return control in the composer gap, hidden when the last row shows [E61] |
| OpenCode | `stickyScroll` | Pins an anchor node before publishing; tail-first mount [E62]. Best prepend handling found |
| pi | `follow: "end"` | Re-engages at max scroll [E31] |
| Prime | View-owned geometry | Sparse windows, layouts held across views, prepend tests [E63] |
| Toad | `Widget.anchor()` | Prunes old blocks at low/high marks [E64] |
| OpenHands | Manual `is_vertical_scroll_end` check [E65] | Implicit; racy with streaming |

Copy these: a fixed composer; follow released by upward scroll or selection; unread count on the return control; an explicit anchor for prepends.

## 4. Framework: Textual 8.2.8

Verdict: **adopt, pin `textual>=8.2,<9` with `rich`.** It alone gives Python async, Pilot, snapshots, a palette and theming together, and OpenHands and Toad prove it at product scale.

| Capability | Verified result |
|---|---|
| `TextArea`, command palette, screens, themes | Present; Ctrl+P palette, `MODES`, `ansi_color` [E67] |
| `MarkdownStream` | Accumulates fragments and appends from a task [E66] |
| `Tree` | 20k leaves: 0.64 s, move 42 ms |
| `DataTable` | 200k rows: 8.5 s to settle, move 282 ms. Pages only |
| Line API | **10M rows: 24 ms paint, 39 `render_line` calls, 33 MB** |
| `Log` / `RichLog` | 1M lines, append 41 ms, 200 MB / 100k lines, 13.4 s deferred, 448 MB. Avoid `RichLog` for history |
| Pilot, snapshots | Keys, resize and clicks passed; 2 snapshots generated and compared, 1.1 s total. OpenHands keeps 60+ [E41] |
| SVG export | 90 KB valid SVG after a 1000-line stream |
| Web serve | HTTP 200; one process per connection; no auth code at all [E80] |
| Selection | Custom Line-API widgets must implement `get_selection` [E68] |

Measured headless on a shared 192-core Xeon 8468 at load near 25, 120x40. Pilot idle-waits inflate absolute times, so read the trends.

| Scenario | Result |
|---|---|
| `Markdown.update(full_text)` per delta | 0.6 s at 100 lines, linear to 8.6 s at 1000. **Never** |
| `MarkdownStream`, 1000 lines with fences | 13.9 s; write p50 0.33 ms, p99 291 ms; stayed at end |
| One 12 KB stream, per-token | 400 tok/s; loop lag p99 76 ms |
| 8 streams of 12 KB, per-token | **Did not finish in 100 s** |
| 1 stream at 20 Hz, 100 tok/s | Lag p99 14 ms, max 67 ms |
| 8 live streams at 10 Hz | Lag p99 64 ms, max 172 ms |
| 100 agents, 1 live stream, 10 Hz | Lag p99 28 ms, max 108 ms |
| 100 agents, status rows only, 4 Hz | Lag p99 12 ms, max 31 ms |
| `Static` in `VerticalScroll`, 1k / 5k | Append 132 / 729 ms; update 99 / 476 ms |
| 300 `Markdown` widgets | Mount 6.5 s, append 833 ms, 213 MB |
| Virtual transcript, 400k rows | Append and paint 48 ms, jump 43 ms |
| Distinct cached strips | **About 1.5 KB per row** (100k rows, 148 MB) |
| Rich Markdown to strips | 125 ms for 451 lines, 4.9 ms per paragraph |
| `textual-speedups` at 5k | 638 vs 729 ms: within noise, skip |

The coalesced runs lasted 8 s (about 3 KB per stream), so they are not a like-for-like rerun of the 12 KB case. The virtual-transcript row reused shared strips, so its RSS is not a memory estimate: fully caching 400k rows would cost about 600 MB, which means an LRU around the viewport.

### Safety, verified

Markup injection, hostile text passed as a plain `str`:

| Surface | Unbalanced `[/x]` | `[@click=app.x()]` |
|---|---|---|
| `Static`, `Label`, `Button`, `Collapsible` title, `border_title` | **`MarkupError` kills the app** | **Action ran on click** |
| `OptionList`, `Tree` labels, `DataTable` cells, `RichLog(markup=True)` | **Kills the app** | **Action ran on click** |
| `markup=False` on `Static`, `OptionList`, `RichLog`; `Content(s)`, `Text(s)`, `Log` | Safe | Safe |
| `Markdown`, `TextArea`, `Input` | Safe | Safe |

`notify()` and `tooltip` were inconclusive (the text never appeared on screen); `notify` defaults to `markup=True` [E67], so treat both as unsafe. Agent, tool and branch names and file paths all look trusted but are model-controlled.

Escape sequences, captured from a real PTY and replayed through `pyte`, each alone and ST-terminated:

| Sequence | `Static(markup=False)` | `Log` | `Markdown` | `Text.from_ansi` | Sanitized |
|---|---|---|---|---|---|
| Set title (OSC 0) | **Took effect** | **Took effect** | **Took effect** | Gone | Gone |
| Clipboard (OSC 52) | **Bytes sent** | **Bytes sent** | **Bytes sent** | Gone | Gone |
| Clear (CSI 2J) | **Took effect** | **Took effect** | **Took effect** | Gone | Gone |
| Full reset (RIS) | **Took effect** | **Took effect** | **Took effect** | **Took effect** | Gone |
| Cursor move (CSI H) | **Bytes sent** | **Bytes sent** | **Bytes sent** | Gone | Gone |
| OSC 8 link | **Bytes sent** | **Bytes sent** | Not verbatim | Not verbatim | Gone |

- Cause: Rich and Textual strip only BEL, BS, VT, FF and CR [E69], so ESC passes. BEL-terminated OSC is defused by accident, which masked this in my first probe; **ST-terminated is the real attack**.
- C1 CSI (`\x9b`) and RLO also reached the PTY through `Static`.
- `pyte` does not model OSC 52, so that row is proven at byte level only.
- `Text.from_ansi` is **not** a sanitizer. A `str.translate` of C0, DEL, C1 and bidi controls blocked all six.
- Peers do this: Pi and Prime strip ANSI from tool output; Codex sanitizes titles and link targets; Oc uses `strip-ansi` [E70].

Links: `Markdown` clicks call `open_url` by default [E71]. markdown-it blocked `file:`, `javascript:` and `data:`, but `vscode://` and `x-custom://` got through. Use `open_links=False` and allow only `http` and `https`.

Other pitfalls:

- **`textual-diff-view` is AGPL**, and Toad depends on it [E19]. Render diffs ourselves.
- `anchor()` verified: scroll-up releases and holds through appends; `scroll_end` re-engages. **A 5-row prepend left the offset unchanged, so content shifted.** Compensate manually.
- Rich rendering is synchronous; send large blocks to a worker.

## 5. Native terminal handoff

`App.suspend()` verified on a PTY: it left the alt screen and disabled mouse, paste and focus reporting. The child saw a real tty with `isig icanon echo`, read stdin and returned 0, and the app re-entered and repainted. It raises `SuspendNotSupported` headless (tested), and `can_suspend` defaults false with only native drivers overriding [E73], so web sessions cannot hand off. Codex and Prime handle job control carefully too [E74].

| Harness | Same-session attach | Status |
|---|---|---|
| Codex | `resume`, `--remote ADDR`, daemon [E75] | IMPL; remote-control mode experimental |
| Claude Code | `claude attach` for background sessions, `--resume` [E46] | EXP for agent view |
| OpenCode | Global `--server`, `serve`, `service` [E76] | IMPL |
| Prime | `attach <agent>`, daemon [E45] | IMPL |
| pi, OpenHands | `--session`, `--resume`, `--last` [E77,E78] | IMPL; exclusive use assumed |

Rules:

1. **One writer per native session.** Open a native TUI only when the agent is idle or the user explicitly takes over, and show who holds it.
2. **Takeover is a human event** with a visible observability gap, unless the harness reports what happened.
3. **Never scrape a wrapped harness TUI.** PTY is a degraded fallback, and rendered text must not produce identities or tokens.
4. **Three levels:** suspend-and-exec here (Must); a new tmux window under `$TMUX` (Should); print the exact command, for SSH and web (Must).
5. **The run survives.** Service-owned agents continue, and the TUI repaints from its journal cursor.
6. **No terminal emulator for 1.0.** Toad built one and its notes still list rough edges [E48]. Limits include scrollback, resize races, alt-screen apps and key passthrough.

Recording without root: Textual SVG (verified); `asciinema rec -c` under a PTY produced a v2 `.cast` (verified; GPL and last released 2023, so a dev tool only); `pyte` replay of captured bytes works as a CI safety test.

## 6. Concrete proposal

Screens: **Workspace** (default), **Runs** (list, resume, attach; works with zero agents), **Review** (cross-agent diffs), plus overlays for palette, approval detail, settings, help and doctor. Modals are only for destructive confirmation.

```text
┌ run: refactor-auth ● 4 working  1 needs you  budget $1.20/$5 ───────────┐
│ NEEDS YOU (1)      │ reviewer  claude-code · sonnet  ● waiting │ WHY     │
│ ▸ reviewer  ⚠ ok?  │  ▸ Bash pytest -q  ✓ 42 passed            │ approval│
│ WORKING (3)        │  ▸ Edit auth.py +12 -3                    │ for 2m  │
│   impl-a  edit x.py│  one agent or channel at a time;          │ ──────  │
│   impl-b  tests    │  token streams are never merged           │ based on│
│ CHANNELS           │                                           │ board#7 │
│   #general 3 #review @1                 ↓ 3 new · End to follow│ gaps: 1 │
├────────────────────┼───────────────────────────────────────────┴─────────┤
│ CHANGED +124 -31   │ to: reviewer ▾  queued: 1                            │
│ 6 files, 3 agents  │ > _                                                  │
└────────────────────┴──────────────────────────────────────────────────────┘
 F1 help  ^P palette  Alt+A next needing you  ^O details  ^B nav
```

- **Navigator:** a virtual list, grouped by what the human must do: Needs you, Working, Blocked, Idle, Done, Failed. Excess idle rows collapse to `N idle` [E30]. Rows carry glyph plus color plus text, name, harness tag, activity, unread and mention. Group by status (default), role, tree or harness; peers without a root stay first-class. Channels, tasks, board and changed files sit below. Space peeks and replies inline, Enter focuses, `x` stops with two presses. An `All activity` row shows one line per event, never tokens.
- **Focus pane:** one of agent transcript, channel, thread, task, board object, diff. The transcript has three layers: frozen blocks on the Line API, paged from the journal with an LRU strip cache; one coalesced live tail per visible agent; nothing rendered for off-screen agents except status rows at 4 Hz or less.
- **Inspector:** hidden by default. Waiting reason, provenance by evidence type, capability level, versions, coverage gaps. Training vocabulary appears only here.
- **Composer:** the target is always shown in a `to:` chip. `@agent`, `#channel`, `+team` retarget. Harness commands route to that harness, ours to the run. CC needed guards for this ambiguity [E30], so confirm any command that lands elsewhere than the chip.
- **Approvals:** one queue, shown in Needs you and a footer chip. **They never take focus**, so a keystroke meant for the composer cannot answer one; Codex guards the related held-key case [E79]. Detail shows actor, harness, exact command or diff, and the scope of "always". Every resolution carries an idempotency key and expected version, so a second client sees "resolved by alice via web" rather than an error.

| Question | UI element | Cost |
|---|---|---|
| Who is working? | Header counts; **Working** group with harness tag | Glance |
| On what? | Row activity line; Tasks panel with claim holders | Glance |
| What is blocked? | **Blocked** group, reason on row (`waiting on impl-a`, `barrier 2/3`, `budget`, `lease expired`); event in Inspector | One key |
| What changed? | `CHANGED` summary; Review screen; per-agent diff | One key |
| Where do I act? | **Needs you** on top; Alt+A cycles; terminal title and bell on transition | One key |

| Width | Behavior |
|---|---|
| 120+ | Three panes; inspector on demand |
| 80-119 | Navigator plus focus; inspector as overlay |
| 60-79 | Focus only; navigator overlay on Ctrl+B; one-line agent strip above composer |
| under 60 | Header collapses to `4● 1⚠`; hints shorten, never wrap [E31b] |
| Height under 16 | Hide extras; composer keeps at least 3 rows, as in Pi [E31] |

A resize must not change scroll position, focus or composer target. Test with Pilot `resize_terminal`.

## 7. Implications for platoon-harness

1. **Build a single `SafeText` boundary** in the CLI package as the only path from untrusted data to a widget: replace C0 (except tab and newline), DEL, C1 and bidi controls visibly.
2. **Ban bare `str` in label-like widgets.** Use `Content` or `markup=False`, enforce with a lint check, and run a hostile-string test over every renderer.
3. **Make PTY plus `pyte` a CI test.** The headless driver writes nothing, so Pilot cannot catch escape leaks.
4. **Build `TranscriptView` on the Line API in Milestone 1**, however simple: width-keyed LRU strips, prepend compensation, follow state, `get_selection`, search, journal paging.
5. **Put one coalescer between events and widgets:** 15 Hz, bounded, dropping render frames but never journal events. This is also the slow-consumer story.
6. **Keep the TUI scheduler-free.** `Needs you` and `Blocked` come from SDK-derived state, so SwarmChat gets identical answers.
7. **Tell protocol design now that the UI needs:** typed waiting reasons, per-human unread cursors separate from agent read cursors, per-agent capability levels, and approval requests with scope and expected version.
8. **Dependencies:** `textual`, `rich` (pin together, as both peers constrain `rich` [E72]); optional `textual-autocomplete`; dev-only `pytest-textual-snapshot` and `pyte`. Avoid `textual-diff-view` (AGPL). `textual-serve` is not `platoon-harness web`: SwarmChat is the web client.
9. **Budgets from measurement:** event-loop lag p99 under 50 ms at 100 agents with one live stream, append under 60 ms at 400k rows, bounded RSS. Headless `run` must not import Textual.

## 8. Taste notes

- **Copy Codex's groups:** verbs for the human, not process states. Its `styles.md` shows a small written style guide earns its keep.
- **Copy CC's peek-and-reply:** answer one question in one key, with no context switch.
- **Copy Pi's viewport:** follow is a property, and the dock is a stack with explicit shrink rules.
- **Copy the keymap catalog** of OpenCode, Pi and Prime: one table of named actions, from which help and palette derive.
- **Copy Toad's ideas, not its code:** a block cursor makes the transcript navigable objects, and permissions show the diff beside the decision.
- **Avoid command sprawl:** Codex has 70+ slash commands, pets included. Keep a small core plus a palette.
- **Avoid destructive bare chords and mode divergence.** Oc's Ctrl+D deletes a session in a list, and CC documents flags that differ between in-process and split-pane teammates [E30]. One runtime path means no such table.
- **Avoid scattered follow logic and scope creep:** one owner of follow state, no terminal emulator, no animation for its own sake.

## 9. Unknowns and risks

- **Headless numbers only.** Real terminal throughput, SSH and tmux are unmeasured, and CC's docs name those as the real bottleneck [E31b].
- **`pyte` is one emulator.** Real terminals vary, and many gate OSC 52.
- **The ESC pass-through may be a Textual bug.** It is not yet reported upstream; keep our boundary regardless.
- **Legitimate color:** parse SGR into styles through an allow-list rather than passing bytes.
- **`TranscriptView` is real work:** wrap, selection, code blocks and resize re-render (5-125 ms per block). Frozen Rich blocks and the live Textual tail may differ at the swap. The hybrid was measured in parts, never integrated.
- **`pytest-textual-snapshot` 1.1.0 was not run;** snapshot SVGs are also brittle across Textual upgrades.
- **Accessibility and scrollback:** alt-screen UIs are poor with screen readers, and CC keeps a classic renderer for that [E31b]. Some users want inline output (Codex `--no-alt-screen`). A plain `attach --plain` follow mode may be the honest answer; undecided.
- **Partial sources:** the CC agent-view and permission-modes pages exceeded the fetch window, so their final sections, including agent-view Limitations, were not read. Hermes claims are docs-only, and CC behavior is unverifiable against source.
- **Windows is untested;** the probes used Unix `pty`.
- **Clean-room:** no upstream `platoon-harness` surfaced in any search or listing.

## Evidence appendix

Docs URLs retrieved 2026-11-02. Textual and Rich paths are package-relative at the versions above.

| Tags | Evidence |
|---|---|
| E1-E4 | **E1:** `toad@dd4f90e8b370:src/toad/widgets/prompt.py:104`; `OpenHands-CLI@283c6ac3610f:openhands_cli/tui/widgets/user_input/input_field.py:91` **E2:** `pi@c9f4c7b9fcd0:packages/tui/src/keybindings.ts:143`; `opencode@ff90ed91607c:packages/tui/src/config/keybind.ts:211` **E3:** `codex@05c08d765523:codex-rs/tui/src/keymap.rs:1746`; https://code.claude.com/docs/en/interactive-mode; https://hermes-agent.nousresearch.com/docs/user-guide/cli **E4:** `prime-agent@c6d4da9421e6:crates/pa-tui/src/editor/motion.rs:1` |
| E5-E8 | **E5:** `OpenHands-CLI@283c6ac3610f:openhands_cli/tui/widgets/user_input/input_field.py:96`; `codex@05c08d765523:codex-rs/tui/src/keymap.rs:1742` **E6:** `opencode@ff90ed91607c:packages/tui/src/config/keybind.ts:56`; `claude-code@f0b737f94f3b:CHANGELOG.md:132` **E7:** `codex@05c08d765523:codex-rs/tui/src/bottom_pane/chat_composer/paste_input.rs:1`; https://hermes-agent.nousresearch.com/docs/user-guide/tui **E8:** `OpenHands-CLI@283c6ac3610f:openhands_cli/tui/widgets/user_input/autocomplete_dropdown.py:80`; `pi@c9f4c7b9fcd0:packages/coding-agent/docs/quickstart.md:88` |
| E9-E12 | **E9:** `opencode@ff90ed91607c:packages/tui/src/component/prompt/autocomplete.tsx:183`; `codex@05c08d765523:codex-rs/tui/src/bottom_pane/file_search_popup.rs:1`; `toad@dd4f90e8b370:src/toad/widgets/path_search.py:1`; `prime-agent@c6d4da9421e6:scripts/check_at_completion.py:1` **E10:** `prime-agent@c6d4da9421e6:crates/pa-tui/src/clipboard_image.rs:1`; `codex@05c08d765523:codex-rs/tui/src/clipboard_paste.rs:1`; `opencode@ff90ed91607c:packages/tui/src/component/dialog-image-preview.tsx:1`; `pi@c9f4c7b9fcd0:packages/tui/src/components/image.ts:1` **E11:** `codex@05c08d765523:codex-rs/tui/src/slash_command.rs:95`; `pi@c9f4c7b9fcd0:packages/coding-agent/src/core/slash-commands.ts:20` **E12:** `OpenHands-CLI@283c6ac3610f:openhands_cli/tui/core/commands.py:18` |
| E13-E16 | **E13:** Textual 8.2.8 `app.py:441`; `opencode@ff90ed91607c:packages/tui/src/config/keybind.ts:57`; `toad@dd4f90e8b370:src/toad/screens/main.py:71`; `OpenHands-CLI@283c6ac3610f:openhands_cli/tui/textual_app.py:265` **E14:** `toad@dd4f90e8b370:src/toad/screens/permissions.py:140`; `codex@05c08d765523:codex-rs/tui/src/bottom_pane/approval_overlay.rs:1` **E15:** `opencode@ff90ed91607c:packages/tui/src/routes/session/permission.tsx:1`; `prime-agent@c6d4da9421e6:crates/pa-tui/src/confirm.rs:1`; `OpenHands-CLI@283c6ac3610f:openhands_cli/tui/panels/confirmation_panel.py:1`; `pi@c9f4c7b9fcd0:packages/coding-agent/README.md:19` **E16:** https://code.claude.com/docs/en/permission-modes; `pi@c9f4c7b9fcd0:packages/coding-agent/src/core/keybindings.ts:34`; `opencode@ff90ed91607c:packages/tui/src/config/keybind.ts:176` |
| E17-E20 | **E17:** `codex@05c08d765523:codex-rs/tui/src/cli.rs:70`; `OpenHands-CLI@283c6ac3610f:openhands_cli/argparsers/util.py:13` **E18:** `opencode@ff90ed91607c:packages/tui/src/config/keybind.ts:80`; `claude-code@f0b737f94f3b:mods/README.md:1`; `codex@05c08d765523:codex-rs/tui/src/diff_render.rs:1` **E19:** `toad@dd4f90e8b370:pyproject.toml:26`; `pi@c9f4c7b9fcd0:packages/coding-agent/src/modes/interactive/components/diff.ts:1`; PyPI metadata for textual-diff-view 0.1.5 (AGPL) **E20:** `toad@dd4f90e8b370:src/toad/widgets/agent_response.py:4`; `codex@05c08d765523:codex-rs/tui/src/markdown_stream.rs:1` |
| E21-E24 | **E21:** `toad@dd4f90e8b370:src/toad/widgets/agent_thought.py:7`; `pi@c9f4c7b9fcd0:packages/coding-agent/src/core/keybindings.ts:51` **E22:** `pi@c9f4c7b9fcd0:packages/coding-agent/src/core/keybindings.ts:50`; `prime-agent@c6d4da9421e6:crates/pa-tui/src/keybindings/definitions.rs:317`; `OpenHands-CLI@283c6ac3610f:openhands_cli/tui/textual_app.py:99`; `toad@dd4f90e8b370:src/toad/widgets/conversation.py:317` **E23:** `opencode@ff90ed91607c:packages/tui/src/config/keybind.ts:129`; `codex@05c08d765523:codex-rs/tui/src/slash_command.rs:131`; https://hermes-agent.nousresearch.com/docs/user-guide/cli **E24:** `toad@dd4f90e8b370:src/toad/screens/sessions.py:21`; `pi@c9f4c7b9fcd0:packages/coding-agent/src/core/slash-commands.ts:41` |
| E25-E28 | **E25:** `pi@c9f4c7b9fcd0:packages/coding-agent/src/core/slash-commands.ts:34`; `codex@05c08d765523:codex-rs/tui/src/slash_command.rs:107`; `opencode@ff90ed91607c:packages/tui/src/config/keybind.ts:122` **E26:** `OpenHands-CLI@283c6ac3610f:openhands_cli/tui/core/commands.py:24`; `pi@c9f4c7b9fcd0:packages/coding-agent/src/core/slash-commands.ts:40` **E27:** `pi@c9f4c7b9fcd0:packages/coding-agent/src/core/keybindings.ts:49`; `opencode@ff90ed91607c:packages/tui/src/config/keybind.ts:167` **E28:** `OpenHands-CLI@283c6ac3610f:openhands_cli/tui/widgets/status_line.py:198`; `toad@dd4f90e8b370:src/toad/acp/agent.py:346`; `codex@05c08d765523:codex-rs/tui/src/slash_command.rs:125` |
| E29-E31b | **E29:** `codex@05c08d765523:codex-rs/tui/src/keymap.rs:1702`; https://code.claude.com/docs/en/fullscreen; `prime-agent@c6d4da9421e6:crates/pa-tui/src/agents_view_search.rs:1` **E30:** https://code.claude.com/docs/en/agent-teams **E31:** `pi@c9f4c7b9fcd0:packages/coding-agent/src/modes/interactive/chat-viewport.ts:22`; `pi@c9f4c7b9fcd0:packages/tui/src/components/scroll-view.ts:48` **E31b:** https://code.claude.com/docs/en/fullscreen |
| E32-E35 | **E32:** `codex@05c08d765523:codex-rs/tui/src/slash_command.rs:151`; https://code.claude.com/docs/en/interactive-mode; `pi@c9f4c7b9fcd0:packages/coding-agent/docs/extensions.md:2962` **E33:** `codex@05c08d765523:codex-rs/tui/src/slash_command.rs:129`; `pi@c9f4c7b9fcd0:packages/coding-agent/docs/themes.md:1`; `OpenHands-CLI@283c6ac3610f:openhands_cli/tui/core/commands.py:13` **E34:** `codex@05c08d765523:codex-rs/tui/src/notifications/osc9.rs:1`; `opencode@ff90ed91607c:packages/tui/src/attention.ts:1`; `toad@dd4f90e8b370:src/toad/settings_schema.py:161`; `pi@c9f4c7b9fcd0:packages/tui/src/terminal.ts:1` **E35:** `prime-agent@c6d4da9421e6:crates/pa-tui/src/bash_bang.rs:1`; `toad@dd4f90e8b370:src/toad/shell.py:191`; `pi@c9f4c7b9fcd0:packages/coding-agent/src/modes/interactive/components/bash-execution.ts:1` |
| E36-E39 | **E36:** `codex@05c08d765523:codex-rs/tui/src/slash_command.rs:156`; `opencode@ff90ed91607c:packages/tui/src/component/dialog-mcp.tsx:1`; `prime-agent@c6d4da9421e6:crates/pa-tui/src/mcp_view.rs:1`; `OpenHands-CLI@283c6ac3610f:openhands_cli/tui/panels/mcp_side_panel.py:1`; `pi@c9f4c7b9fcd0:packages/coding-agent/docs/mcp.md:1` **E37:** `codex@05c08d765523:codex-rs/tui/src/slash_command.rs:117`; `opencode@ff90ed91607c:packages/tui/src/component/dialog-skill.tsx:1`; `pi@c9f4c7b9fcd0:packages/coding-agent/docs/skills.md:1`; `OpenHands-CLI@283c6ac3610f:openhands_cli/tui/core/commands.py:25` **E38:** `codex@05c08d765523:codex-rs/tui/src/slash_command.rs:119`; `pi@c9f4c7b9fcd0:packages/coding-agent/docs/extensions.md:82` **E39:** `codex@05c08d765523:codex-rs/tui/src/slash_command.rs:98`; `prime-agent@c6d4da9421e6:crates/pa-core/src/prompts/system_prompt.rs:1`; `claude-code@f0b737f94f3b:mods/README.md:1` |
| E40-E43 | **E40:** `prime-agent@c6d4da9421e6:README.md:120`; https://hermes-agent.nousresearch.com/docs/user-guide/tui **E41:** `OpenHands-CLI@283c6ac3610f:pyproject.toml:55`; `OpenHands-CLI@283c6ac3610f:tests/snapshots/test_app_snapshots.py:1`; PyPI metadata for pytest-textual-snapshot 1.1.0 **E42:** `codex@05c08d765523:codex-rs/exec/src/cli.rs:65`; `pi@c9f4c7b9fcd0:packages/coding-agent/docs/cli.md:47`; `OpenHands-CLI@283c6ac3610f:openhands_cli/argparsers/main_parser.py:89`; `opencode@ff90ed91607c:packages/cli/src/commands/commands.ts:432`; `prime-agent@c6d4da9421e6:crates/pa-cli/src/args.rs:320` **E43:** https://code.claude.com/docs/en/headless |
| E44-E47 | **E44:** `codex@05c08d765523:codex-rs/tui/src/app/agent_center/mod.rs:11`; `codex@05c08d765523:codex-rs/tui/src/app/agents_overview_view.rs:70`; `codex@05c08d765523:codex-rs/tui/src/app/agents_overview.rs:2`; `codex@05c08d765523:codex-rs/tui/src/multi_agents.rs:106` **E45:** `prime-agent@c6d4da9421e6:crates/pa-tui/src/agents_view.rs:1`; `prime-agent@c6d4da9421e6:crates/pa-tui/src/factory_view.rs:1`; `prime-agent@c6d4da9421e6:README.md:116` **E46:** https://code.claude.com/docs/en/agent-view **E47:** `codex@05c08d765523:codex-rs/tui/src/transcript_view/copy_mode.rs:1`; `prime-agent@c6d4da9421e6:crates/pa-tui/src/selection.rs:1`; https://code.claude.com/docs/en/fullscreen |
| E48-E51 | **E48:** `toad@dd4f90e8b370:src/toad/shell.py:191`; `toad@dd4f90e8b370:notes.md:18`; `opencode@ff90ed91607c:packages/tui/src/component/terminal-pane.tsx:1` **E49:** `codex@05c08d765523:codex-rs/tui/src/keymap.rs:1720`; `pi@c9f4c7b9fcd0:packages/coding-agent/src/core/keybindings.ts:26`; `opencode@ff90ed91607c:packages/tui/src/config/keybind.ts:48`; `OpenHands-CLI@283c6ac3610f:openhands_cli/tui/textual_app.py:105` **E50:** `codex@05c08d765523:codex-rs/tui/src/keymap.rs:1706`; `pi@c9f4c7b9fcd0:packages/coding-agent/src/core/keybindings.ts:60` **E51:** `pi@c9f4c7b9fcd0:packages/coding-agent/src/core/keybindings.ts:30`; `prime-agent@c6d4da9421e6:crates/pa-tui/src/suspend.rs:1` |
| E52-E55 | **E52:** `opencode@ff90ed91607c:packages/tui/src/config/keybind.ts:138`; `opencode@ff90ed91607c:packages/tui/src/routes/session/composer/subagents-tab.tsx:26` **E53:** `opencode@ff90ed91607c:packages/tui/src/config/keybind.ts:41` **E54:** Textual 8.2.8 `drivers/linux_driver.py:286` **E55:** `pi@c9f4c7b9fcd0:packages/coding-agent/docs/tmux.md:1` |
| E56-E59 | **E56:** `prime-agent@c6d4da9421e6:crates/pa-tui/src/hotkeys.rs:1`; `pi@c9f4c7b9fcd0:packages/coding-agent/docs/keybindings.md:1` **E57:** `toad@dd4f90e8b370:src/toad/widgets/session_tabs.py:1`; `toad@dd4f90e8b370:src/toad/screens/sessions.py:21`; `toad@dd4f90e8b370:src/toad/widgets/side_bar.py:24`; `toad@dd4f90e8b370:src/toad/widgets/conversation.py:1661` **E58:** `opencode@ff90ed91607c:packages/tui/src/config/keybind.ts:117`; `opencode@ff90ed91607c:packages/tui/src/component/session-tabs-rail.tsx:1` **E59:** https://hermes-agent.nousresearch.com/docs/user-guide/tui |
| E60-E63 | **E60:** `pi@c9f4c7b9fcd0:packages/coding-agent/README.md:19` **E61:** `codex@05c08d765523:codex-rs/tui/src/transcript_view.rs:434`; `codex@05c08d765523:codex-rs/tui/src/transcript_view/follow_control.rs:1` **E62:** `opencode@ff90ed91607c:packages/tui/src/routes/session/index.tsx:413` **E63:** `prime-agent@c6d4da9421e6:crates/pa-tui/src/view/lazy.rs:1`; `prime-agent@c6d4da9421e6:crates/pa-tui/src/view/handoff.rs:1`; `prime-agent@c6d4da9421e6:crates/pa-tui/src/view/tests.rs:315` |
| E64-E67 | **E64:** `toad@dd4f90e8b370:src/toad/widgets/conversation.py:1398`; `toad@dd4f90e8b370:src/toad/widgets/conversation.py:1532` **E65:** `OpenHands-CLI@283c6ac3610f:openhands_cli/tui/widgets/richlog_visualizer.py:305` **E66:** Textual 8.2.8 `widgets/_markdown.py:41` **E67:** Textual 8.2.8 `app.py:361`, `app.py:427`, `app.py:441`, `app.py:569`, `app.py:4621` |
| E68-E71 | **E68:** Textual 8.2.8 `widget.py:4213`, `widgets/_log.py:265` **E69:** Rich 15.0.0 `control.py:9`; Textual 8.2.8 `content.py:56` **E70:** `pi@c9f4c7b9fcd0:packages/coding-agent/src/utils/ansi.ts:71`; `prime-agent@c6d4da9421e6:crates/pa-tui/src/ansi.rs:17`; `codex@05c08d765523:codex-rs/tui/src/terminal_title.rs:129`; `codex@05c08d765523:codex-rs/tui/src/terminal_hyperlinks.rs:699`; `opencode@ff90ed91607c:packages/tui/src/attention.ts:12` **E71:** Textual 8.2.8 `widgets/_markdown.py:1035`, `widgets/_markdown.py:1195` |
| E72-E75 | **E72:** `OpenHands-CLI@283c6ac3610f:pyproject.toml:28`; `toad@dd4f90e8b370:pyproject.toml:12` **E73:** Textual 8.2.8 `driver.py:63`, `drivers/linux_driver.py:100`, `app.py:4734` **E74:** `codex@05c08d765523:codex-rs/tui/src/tui/job_control.rs:1`; `prime-agent@c6d4da9421e6:crates/pa-tui/src/suspend.rs:1` **E75:** `codex@05c08d765523:codex-rs/cli/src/main.rs:973`; `codex@05c08d765523:codex-rs/cli/src/main.rs:174`; `codex@05c08d765523:codex-rs/cli/src/main.rs:205` |
| E76-E79 | **E76:** `opencode@ff90ed91607c:packages/cli/src/commands/commands.ts:22` **E77:** `pi@c9f4c7b9fcd0:packages/coding-agent/docs/cli.md:48` **E78:** `OpenHands-CLI@283c6ac3610f:openhands_cli/argparsers/util.py:52` **E79:** `codex@05c08d765523:codex-rs/tui/src/activation_key_guard.rs:1` |
| E80-E80 | **E80:** Textual-serve 1.1.3 `textual_serve/server.py:329`, `textual_serve/app_service.py:94` |
