# RFC 0015: Textual, a SafeText boundary and a Line API transcript

| | |
|---|---|
| Status | Accepted, 2026-11-02 |

## Summary

One sanitizing boundary for untrusted text, and a Line API transcript paged from the journal

## Motivation

The TUI must be useful enough for everyday work, at up to 100 agents, while showing text that models control. That includes agent, tool and branch names and file paths, which look trusted and are not. A transcript has no upper size. Clients must hold no timers and decide nothing, so rendering must never be able to lose an event.

## Proposal

The TUI uses Textual, pinned `textual>=8.2,<9` with `rich`, in the CLI package only. Untrusted text crosses one `SafeText` boundary, which visibly replaces C0 (except tab and newline), DEL, C1 and bidi controls. A lint bans bare `str` in label-like widgets. `TranscriptView` sits on the Line API and pages from the journal, so history is virtual. One 15 Hz coalescer between the journal and widgets drops render frames, never events. Approvals never take focus.

## Alternatives

| Alternative | Why not |
|---|---|
| Another framework | Textual alone gave Python async, Pilot, snapshots, a palette and theming together |
| Toad's code | AGPL-3.0. Its interaction ideas may inform us, and its code may not. `textual-diff-view` is AGPL too, so we render diffs ourselves |
| Trusting `markup=False` or `Text.from_ansi` | Hostile escapes reached a real PTY through `Static(markup=False)`, `Log` and `Markdown`, and ST-terminated OSC is the real attack. Full reset (RIS) survived `Text.from_ansi` |
| Sanitizing at each call site | One missed label is a crash from an unbalanced `[/x]`, or an action run on click. One boundary can be linted |
| A widget per message, or `RichLog` | Append cost 132 ms at 1k and 729 ms at 5k, and `RichLog` took 448 MB at 100k lines. The Line API painted in 24 ms at 10M rows |
| Rendering per token | 8 streams of 12 KB did not finish in 100 s. At 10 Hz, 8 live streams held lag p99 at 64 ms |

## Consequences

- We own what a custom Line API widget loses: `get_selection`, prepend compensation, and an LRU around the viewport, since strips cost about 1.5 KB per row.
- `Markdown` runs with `open_links=False`, and only `http` and `https` are followed.
- The SDK stays free of Textual, and a boundary test enforces it. `SafeText` lives in the CLI package.
- `textual-serve` is not the web client: it has no auth and runs one process per connection. See [RFC 0014](0014-swarmchat-compatibility-backend.md).
- Measurements came from a loaded shared host with Pilot idle-waits, so trends are firmer than absolute times. 15 Hz itself was not measured: the nearest probes ran at 10 Hz and 20 Hz.

## Evidence

- [tui-expectations.md](../research/tui-expectations.md), bottom line, section 4 (measurements and safety) and section 7.
- [Research index](../research/README.md), the Textual confirmation under the twelve critical claims. [Architecture sections 12 and 15](../architecture.md).
