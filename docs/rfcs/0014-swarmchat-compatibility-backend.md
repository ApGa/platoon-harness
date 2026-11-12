# RFC 0014: SwarmChat compatibility backend plus overlay

| | |
|---|---|
| Status | Accepted, 2026-11-02 |

## Summary

Upstream's page and our projection, one way, plus an overlay. Upstream's server never runs

## Motivation

SwarmChat must be a real second client, not a log dump, with the journal authoritative and no second scheduler. SwarmChat's viewer is read-only by design, and its server is a separate durable store with its own ids, order and times. Its messages have no idempotency key, no metadata, no caller-chosen ids and no caller-chosen timestamps. Its CSP stops the page from reaching a separate ingress.

## Proposal

Upstream's server never runs. A follower folds the journal into its own rebuildable `swarmchat.sqlite`. We serve the pinned, hash-checked frontend assets, the `view_*` replies over that projection, an overlay for everything human-facing, and one `/x/command` route into the same ops the TUI uses. The projection is one way: nothing re-ingests it.

## Alternatives

| Option | Why not |
|---|---|
| (d) Run upstream's server and bridge into it | Two authorities. The same `send` twice made 2 messages, chat ids are server-random so a replay changes every link, `at` is server time, and token holders can edit and delete what the journal claims as evidence |
| (a) Extend upstream first | The viewer "only looks" by design, a composer is a product change, and the project is days old with no stated roadmap. A short seam note can still go upstream |
| (c) A maintained patch to `app.js` | Hunks against one large file, and a frontend patch still needs a backend. Exact-match serve-time edits stay available for what an overlay cannot reach |

## Consequences

- Echo loops have no path, and a retry reuses its key, so reconnects cannot duplicate.
- The journal cannot be rewritten from the browser, and browsing writes nothing. "Read by" becomes "Delivered to", drawn from delivery evidence.
- `view_*` is an unversioned internal shape. An exact pin and a contract test contain that, and upgrades are deliberate work.
- One session per port, because the page keeps one token per origin in `localStorage` and its `/v1/` paths are fixed.
- Link tokens are one-time and exchanged for expiring ones. View and control tokens are separate classes.
- The overlay couples to the page's top-level names. The probes used an in-memory stub authority, so they prove the UI flow, not our journal transaction, and large sessions are unmeasured on our backend.

## Evidence

- Design-phase research, not published, on SwarmChat 0.1.0's real server: eight mutating requests with a view token gave 401, browsing changed no files, and the same `send` twice made two messages, ignoring a supplied `id`, `at` and `metadata`. A foreign `Origin` and `Host` were accepted.
- [Architecture section 12](../architecture.md).
