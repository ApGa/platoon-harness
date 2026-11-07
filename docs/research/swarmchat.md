# SwarmChat research report

> Background research, dated 2026-11-02 and not maintained: [reference/compatibility.md](../reference/compatibility.md) is current.

## Inspected

| Project | Commit or version | Date | License |
|---|---|---|---|
| SwarmChat source (`Pranjal2041/swarmchat`, default branch `main`) | `fb5aa6a05b40` (the only commit on GitHub; 0 issues or PRs) | commit 2026-10-29, read 2026-11-02 | MIT, "The SwarmChat Authors" |
| `swarmchat` on PyPI | 0.1.0 (only release, classifier Beta) | uploaded 2026-10-29 | MIT |
| Probe browser | Playwright Python 1.64.1, Chrome Headless Shell 156.0.8078.4 | 2026-11-02 | Apache-2.0 / Chromium notices |

Wheel and clone agree: `page/*`, `store.py`, `api.py`, `view.py` and `server.py` compared byte-identical. Web sources: <https://swarmchat.io> and <https://pypi.org/project/swarmchat/> (retrieved 2026-11-02): no roadmap, no API docs, no stability statement, no planned browser composer.

Status labels: IMPLEMENTED (code on `main`), DOCUMENTED-ONLY. Nothing inspected is DRAFT or EXPERIMENTAL. "Probe" means I ran it on 2026-11-02. Upstream benchmark numbers were not re-run.

## Verdict

- Use option (b): serve SwarmChat's pinned, unmodified frontend assets from our runtime, with a compatibility backend over a journal projection, plus a small overlay for everything human-facing.
- Reject option (d). SwarmChat messages have no idempotency key, no metadata field, no caller-chosen IDs and no caller-chosen timestamps, so a projection into its server cannot be idempotent, and its CSP stops its own page from reaching a separate ingress.
- Probes proved the risky part. An overlay on the unmodified `app.js` added a composer and approvals. One approval raced from two clients took effect exactly once, and reconnection produced no duplicates.

## 1. Boundaries

| Module | Lines | Job | Depends on |
|---|---:|---|---|
| `store.py` | 1,249 | Files on disk, in-memory index, feed, tokens, read positions | `config`, `files`, `locking`, `policy` |
| `api.py` | 615 | One function per agent or admin request | `store`, `files` |
| `view.py` | 845 | Read-only `view_*` requests, page and gate assembly | `api`, `store` |
| `server.py` | 548 | HTTP, token routing, limits, long-held requests | `api`, `view`, `store`, `files` |
| `client.py` | 505 | Python client, wait loop, acks, `--where` sandbox | `files` only; never imports `store` |
| `cli.py` | 732 | Commands; `view` may start a read-only server | `client`, `config`, `server` lazily |
| `policy.py` | 165 | Roles and rules | none |

- Dependencies: none at runtime (`swarmchat@fb5aa6a05b40:pyproject.toml:13`). Python 3.9+, stdlib only. Python total is 5,006 lines.
- The client/server boundary is plain HTTP, `POST /v1/<name>` with JSON (`swarmchat@fb5aa6a05b40:swarmchat/server.py:1`). Requests are dispatched in `swarmchat@fb5aa6a05b40:swarmchat/server.py:387`.
- Viewer delivery: plain JS, no framework, no build step, no external requests. Five source files in `swarmchat/page/`, shipped as package data (`swarmchat@fb5aa6a05b40:pyproject.toml:46`).

| Frontend file | Lines | Bytes |
|---|---:|---:|
| `app.js` | 2,408 | 140,472 |
| `app.css` | 448 | 38,501 |
| `index.html` | 52 | 1,893 |
| `gate.html`, `gate.js` | 63 | 3,060 |

- `index.html`, `app.css` and `app.js` gzip to 52,962 bytes (measured), matching the documented 53 KB.
- Two-step load: `GET /view` returns only the token form (`swarmchat@fb5aa6a05b40:swarmchat/server.py:309`). The form then POSTs `view_page`, swaps the document and injects `app.js` by `textContent` (`swarmchat@fb5aa6a05b40:swarmchat/page/gate.js:9`). The CSP on the gate response already allows the app script's hash.
- `app.js` is one classic strict-mode script with top-level bindings and one document click handler over `data-*` attributes (`swarmchat@fb5aa6a05b40:swarmchat/page/app.js:1652`).
- Structure: helpers and `html` template (1-52), API and pictures (53-119), state `S` (122), hash router (161-221), sidebar (`side`, 280), message rendering (377), text-file viewer with its own highlighter and Markdown parser (428-950), `ChatView` (998), list views (1161-1285), `PersonView`, `BoardView`, `PostView`, `ThreadPane` (1413), `KnewPane` (1437), overlays (1467), feed loop (1583), `MapView` with worker (1717-2316), boot (2392).
- There is no module system, plugin hook or public JS API.

Docs that disagree with code:

| Claim | Reality | Status |
|---|---|---|
| Budget "about 1,500 lines. v0.1 is 1,560" (`swarmchat@fb5aa6a05b40:DESIGN.md:392`) | 5,006 Python lines | DOCUMENTED-ONLY, stale |
| "Attachments: later" (`swarmchat@fb5aa6a05b40:DESIGN.md:407`) | Implemented (`swarmchat@fb5aa6a05b40:swarmchat/api.py:296`) | Stale |
| "One HTML file" (`swarmchat@fb5aa6a05b40:DESIGN.md:264`) | Gate plus fetched page. No route serves the assembled `body`; only the install check reads it (`swarmchat@fb5aa6a05b40:.github/workflows/tests.yml:31`) | Partly true |
| Client config at `~/.config/swarmchat/config` (`swarmchat@fb5aa6a05b40:DESIGN.md:41`) | `config.json` (`swarmchat@fb5aa6a05b40:swarmchat/client.py:171`) | Stale |

## 2. HTTP API

**Transport and auth** (`swarmchat@fb5aa6a05b40:swarmchat/server.py:407`)

| Token | Form | Stored as | Reaches | Rotation |
|---|---|---|---|---|
| Super admin | 32 random bytes hex, `DIR/admin.token` | Plain file 0600, digest in memory | `ADMIN` requests and all `view_*`; never agent requests | None |
| View | 32 random bytes hex, `DIR/view.token` | Same | `view_*`, `view_feed`, `view_download` only | None; no request exists |
| User | 24 random bytes hex | SHA-256 only | Agent `METHODS`, `download`, `send_files`; `ADMIN` if rules allow | `settings_token`, `token_rotate` |
| Read-only process view token | 32 random bytes hex | Memory | `view_*` only, on a server started over a stopped folder | Per process |

Roles (`swarmchat@fb5aa6a05b40:swarmchat/policy.py:44`): super admin (not a user, never posts), administrator, channel creator, channel manager, member. Until `admins` is set, members also get manager powers (`swarmchat@fb5aa6a05b40:swarmchat/policy.py:67`). Admins do not read private chats through agent requests.

**Endpoints**

| Group | Requests | Evidence |
|---|---|---|
| No token | `GET /v1/health` (version, limits), `GET /view`, `GET /` (302 to `/view`) | `swarmchat@fb5aa6a05b40:swarmchat/server.py:304` |
| Agent | `whoami`, `people`, `chats`, `read`, `mark_read`, `send`, `edit`, `delete`, `react`, `chat_info`, `channel_create`, `channel_list`, `channel_join`, `channel_visibility`, `channel_add`, `channel_remove`, `channel_leave`, `channel_rename`, `channel_describe`, `channel_managers`, `channel_archive`, `channel_unarchive`, `notifications`, `wait`, `settings_notify`, `settings_status`, `settings_token`, `settings_show` | `swarmchat@fb5aa6a05b40:swarmchat/api.py:558` |
| Agent, special body | `send_files` (one JSON line, then raw bytes), `download` (binary, metadata in `X-Attachment`) | `swarmchat@fb5aa6a05b40:swarmchat/server.py:426`, `swarmchat@fb5aa6a05b40:swarmchat/server.py:465` |
| Admin | `user_add`, `user_remove`, `token_rotate`, `policy_set`, `policy_show`, `role_change` | `swarmchat@fb5aa6a05b40:swarmchat/api.py:615` |
| View | `view_info`, `view_snapshot`, `view_messages`, `view_thread`, `view_receipts`, `view_posts`, `view_search`, `view_activity`, `view_as`, `view_knew`, `view_text`, `view_page`, `view_feed`, `view_download` | `swarmchat@fb5aa6a05b40:swarmchat/view.py:794`, `swarmchat@fb5aa6a05b40:swarmchat/server.py:38` |

**The viewer is read-only: IMPLEMENTED, enforced on the server.**

- The view token resolves only to the `VIEW` set; a view handler has no write path. Upstream test: `swarmchat@fb5aa6a05b40:tests/test_view.py:46`, and a folder-unchanged test at `swarmchat@fb5aa6a05b40:tests/test_view.py:62`.
- Probe against the real server: `send`, `whoami`, `user_add` with the view token all returned 401. `view_snapshot` and `view_feed` with a user token returned 401. A forced `fetch('/v1/send')` from inside the page returned 401.
- Probe: after browsing, Bob's read position was unchanged at 0 and no `read` lines were written. The page has no input in `#main`. Message actions are only Thread, What had X read?, Read by, and copy ID.
- `view_as` calls the agent `read` with `peek: true` (`swarmchat@fb5aa6a05b40:swarmchat/view.py:720`), so "as an agent" moves nothing.
- Weak spot: `can_view` accepts the admin token, and `swarmchat view --admin-token` puts it in the link (`swarmchat@fb5aa6a05b40:swarmchat/cli.py:328`). The page stays passive, but a full control credential then sits in `localStorage`. We must not copy this.

**Live updates:** long-poll only, no SSE or WebSocket. `view_feed` holds up to `min(timeout, max_wait)`; the page asks for 25 s and retries every 2 s on failure (`swarmchat@fb5aa6a05b40:swarmchat/page/app.js:1583`). The feed is an in-memory ring of 20,000 entries, renumbered on each start, with a random `feed_id` (`swarmchat@fb5aa6a05b40:swarmchat/store.py:421`). `reset: true` makes the page take a new snapshot (`swarmchat@fb5aa6a05b40:swarmchat/view.py:292`). Up to 5,000 entries per reply.

**Origin and Host: no checks.** Probe: `POST /v1/view_info` with `Origin: https://evil.example`, `Host: evil.example` and a valid token returned 200. No `Access-Control-*` headers are sent, and `OPTIONS` returns 501, so a cross-origin browser call fails at preflight because `Authorization` is non-simple. Safety rests on bearer headers, not on origin policy. That is reasonable for a viewer and not enough for our control ingress.

**Rendering safety: IMPLEMENTED, and held up in probes.**

- All agent text goes through `esc()` or the `html` tagged template, with a `Safe` wrapper for trusted markup (`swarmchat@fb5aa6a05b40:swarmchat/page/app.js:10`).
- Message bodies are not Markdown. They get inline code, `@mention` spans, autolinked `http(s)` URLs and fenced code (`swarmchat@fb5aa6a05b40:swarmchat/page/app.js:380`).
- Markdown applies only to attachments, through a hand-written parser: raw HTML shows as text, only web and mail links link, images are never fetched (`swarmchat@fb5aa6a05b40:swarmchat/page/app.js:730`, `swarmchat@fb5aa6a05b40:swarmchat/page/app.js:812`).
- CSP on `/view`, by hash (`swarmchat@fb5aa6a05b40:swarmchat/view.py:840`): `default-src 'none'; script-src <gate hash> <app hash>; style-src 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self'; worker-src blob:; base-uri 'none'; form-action 'none'; frame-ancestors 'none'`. Also `Referrer-Policy: no-referrer`, `X-Content-Type-Options: nosniff`.
- Probe: `<img onerror>`, `<script>` and an attribute-breakout URL in messages, plus `javascript:` links and raw HTML in an attachment, rendered as text with `window.__pwned` unset. An injected inline script and a remote image were both blocked by CSP.
- Token handling: `#token=` is stripped from the address bar, then kept in `localStorage` (`swarmchat@fb5aa6a05b40:swarmchat/page/app.js:2394`). Links only accept lowercase hex of 16 or more characters (`swarmchat@fb5aa6a05b40:swarmchat/page/gate.js:26`).
- `view_info` returns the absolute data path to anyone with the view token (`swarmchat@fb5aa6a05b40:swarmchat/view.py:264`). Our backend must return a run label instead.

**Robustness, IMPLEMENTED:** token checked before the body is read, deadlines on header and body, connection eviction, 32 requests per user, disk floor (`swarmchat@fb5aa6a05b40:swarmchat/server.py:1`). `view_*` requests bypass the per-user counter because `me` is `None` (`swarmchat@fb5aa6a05b40:swarmchat/server.py:357`).

## 3. Data model

All IMPLEMENTED.

| Object | Shape | Notes |
|---|---|---|
| User | `id` (`[a-z0-9][a-z0-9._-]{0,39}`), `name`, `fields`, `status`, `token_sha256` | No human/agent distinction. IDs of removed users stay retired (`swarmchat@fb5aa6a05b40:swarmchat/store.py:589`) |
| Chat | 16 hex random `id`, chosen by the server (`swarmchat@fb5aa6a05b40:swarmchat/store.py:815`) | `name` set means channel; otherwise direct, found by exact member set. API reports `channel`/`direct`; viewer adds `group` for more than 2 members (`swarmchat@fb5aa6a05b40:swarmchat/view.py:56`) |
| Channel | Name 1-80 chars, no commas, unique, never equal to a user's id or name | `public`, `archived`, `description`, `managers` |
| Message | Log line `{seq, kind:"message", from, text, at, reply_to?, mentions?, attachments?}` (`swarmchat@fb5aa6a05b40:swarmchat/store.py:1015`) | ID is `<chat>:<seq>`. **No metadata, client ID or idempotency field exists** |
| Thread | No object. `reply_to` forms a tree of any depth inside a chat (`swarmchat@fb5aa6a05b40:swarmchat/store.py:1064`) | Replies must stay in the same chat |
| Mentions | Parsed by the server from `@id`, `@Full Name`, `@First`, `@all/everyone/here/channel`; an ambiguous mention is refused with 400 (`swarmchat@fb5aa6a05b40:swarmchat/store.py:970`) | |
| Edit, delete, react | Later log lines pointing at `target`; `view()` folds them in | Deleting blanks the message's line in place, same length, journaled for crash safety (`swarmchat@fb5aa6a05b40:swarmchat/store.py:328`). The log is not strictly immutable |
| File | Attachment `{id:"a"+16 hex, name, size, type, sha256, folder?}`, blob at `blobs/ab/<sha256>` | Hash never reaches members; refcounted (`swarmchat@fb5aa6a05b40:swarmchat/api.py:333`) |
| System lines | `created`, `added`, `removed`, `renamed`, `described`, `managers`, `visibility`, `archived`, `unarchived` | Same log as messages |

Ordering:

- `seq` is a per-chat total order over **all** lines, so message seqs are sparse. Probe: message seqs 2-5, then a `read` line took seq 6.
- `at` is server-assigned and non-decreasing per chat for messages (`swarmchat@fb5aa6a05b40:swarmchat/store.py:1035`). Senders cannot supply a time.
- There is no durable global order. Cross-chat reads merge by `(at, chat, seq)` (`swarmchat@fb5aa6a05b40:swarmchat/api.py:126`). Feed number `n` is global but volatile.
- `fsync` is off by default (`swarmchat@fb5aa6a05b40:swarmchat/config.py:17`), so a message survives a process crash but not a machine crash (`swarmchat@fb5aa6a05b40:bench/RESULTS.md:9`).

Read receipts, exactly:

1. A cursor is one number per user and chat (`state/<user>.json`).
2. `mark_read` writes `{kind:"read", from, at, upto}` into the chat log, consuming a seq, then updates memory (`swarmchat@fb5aa6a05b40:swarmchat/store.py:1178`). State files flush every second (`swarmchat@fb5aa6a05b40:swarmchat/config.py:35`).
3. A non-peek `read` advances only to the first unread message not shown, so a filter cannot hide a message (`swarmchat@fb5aa6a05b40:swarmchat/api.py:98`, `swarmchat@fb5aa6a05b40:swarmchat/store.py:1190`).
4. The client always sends `wait` with `peek: true` and confirms via `ack` on its next request or on close (`swarmchat@fb5aa6a05b40:swarmchat/client.py:495`, `swarmchat@fb5aa6a05b40:swarmchat/server.py:397`). A cut-off wait confirms nothing.
5. Threads and peeks move nothing (`swarmchat@fb5aa6a05b40:swarmchat/api.py:259`).
6. Senders see `read_by` and `unread_by` only on their own messages (`swarmchat@fb5aa6a05b40:swarmchat/api.py:45`). The viewer sees everything via `view_receipts` and `positions`.
7. After a kill, up to a second of positions is lost and messages come again: 338 repeats in 21,876 deliveries, upstream's own number (`swarmchat@fb5aa6a05b40:bench/RESULTS.md:67`).

So a "read" means "reached the client", not understood. Upstream says the same of its "What had it read?" view (`swarmchat@fb5aa6a05b40:DESIGN.md:307`).

## 4. Integration options

| | (a) Upstream extension | (b) Compatibility backend | (c) Narrow maintained patch | (d) Own server + projection + ingress |
|---|---|---|---|---|
| Exact work | Propose composer, command routes and render hooks upstream, then wait | Implement 14 `view_*` requests, gate and CSP over a projection; overlay; command ingress | Keep a diff against `app.js`. A frontend patch still needs a backend, so this is a component of (b) or (d), not a whole option. Patching SwarmChat's server instead adds human writes to its store, which is (d)'s authority problem | Run the server; bridge holding every participant's token; mapping table; reverse proxy rewriting page and CSP; ingress service |
| Needs from SwarmChat | Maintainers accepting a stated product change; the viewer "only looks" (`swarmchat@fb5aa6a05b40:DESIGN.md:17`) | Page assets and an undocumented wire shape | Same plus patchable source | Idempotent writes, caller IDs, message metadata, timestamps, on-behalf-of. **None exist** |
| Drift risk | Low after merge; unknown timeline; one-commit repo, no contribution history | Low with exact pin; deliberate on upgrade; contract test catches shape change | Medium: hunks against one large file | High: two live data models to reconcile |
| Two authorities | Yes, if humans write to its store | **No.** Journal only; projection rebuildable | Depends on backend | **Yes.** A second durable log with its own IDs, order, times, membership, deletions |
| Read receipts | Would move its own cursors | Rendered from our delivery evidence; the browser writes none | As backend | Bridge must call `mark_read` to fake them; each adds a log line and shifts seqs |
| Echo loops | Bridge needs echo suppression | None. Commands fold into the journal, projection is one way, nothing re-ingests | As backend | Avoidable only by never reading back, and agents holding tokens would break that |
| Reconnect | As upstream | `after` on a durable cursor; `reset` only on projection version change | As backend | Feed resets on every server restart; retried `send` duplicates |

Why (d) fails, from code:

- `send` takes no idempotency key (`swarmchat@fb5aa6a05b40:swarmchat/api.py:288`). The client itself refuses to retry and warns "The request may have been applied" (`swarmchat@fb5aa6a05b40:swarmchat/client.py:232`). A crash between `send` and saving our mapping duplicates the message, and with no metadata field the only way to detect it is a marker in visible text.
- Chat IDs are server-random, so wiping and replaying the data directory changes every chat ID and link. "Rebuildable view" and "stable mapping" conflict.
- `at` is server time, so projected history shows projection time, not event time.
- `connect-src 'self'` stops the served page from reaching a separate ingress. A human composer needs a proxy that rewrites the page and CSP, which is most of (b) anyway.
- The default `min_free` of 1 GB can refuse projection writes with 507 (`swarmchat@fb5aa6a05b40:swarmchat/config.py:31`).
- Token holders can `edit` and `delete`, and deletion rewrites data the journal claims as evidence.

**Recommendation: (b), with an overlay; (c) only as exact-match serve-time edits for what an overlay cannot reach; (a) as a small seam proposal.** This satisfies the brief's "journal authoritative", "no two authorities", "same command service as the TUI" and "reuse the frontend" together. Do not implement the agent API; agents keep our MCP and tool CLI.

### Wire contract the backend must honor

Unversioned upstream internals, verified from `view.py` and `app.js`:

- `view_snapshot`: `{feed, now, server:{name,version,read_only,data,feed,feed_id}, users:[{id,name,fields,status,removed?}], chats:[{id,kind,name,description,public,archived,members,managers,created_by,created_at,seq,messages,last_at,last:{seq,from,at,text,deleted,files},sent,last_by,recent}]}`. `at` values are ISO strings; `last_by` and `now` are seconds.
- Message: `{id,chat,seq,kind,from,at,text,reply_to?,reply_to_from?,mentions?,attachments?,edited_at?,deleted?,reactions?,replies,parent?}`.
- Feed: `{feed,events,reset?}`; event kinds `user`, `message`, `change`, `read`, `chat` (`swarmchat@fb5aa6a05b40:swarmchat/view.py:311`). `change` carries the whole new message; `chat` carries `event` and `summary`.
- Invariants: per-chat integer `seq` strictly increasing; IDs shaped `<chat>:<seq>` because the page parses them (`swarmchat@fb5aa6a05b40:swarmchat/page/app.js:1681`); tokens lowercase hex of 16+; `/v1/...` root-relative in `api`, `download`, `picture` and the gate, so the page cannot be mounted under a sub-path.
- Tolerance (probe): an unknown feed kind on a known chat is ignored. An unknown line kind inside a `chat` event renders as a system line showing the kind name. Unknown message fields pass through to `messageHtml`.

Suggested mapping: keep a persisted table `event_id <-> chat:seq`. `chat` is 16 hex from a hash of run and channel. `seq` is the projection's per-chat ordinal. `feed` is a durable projection cursor. `feed_id` is a hash of run and projection schema version. The token, not the URL, selects the run, because paths are fixed. `app.js` never calls `view_info` (grep and probe), so the overlay can use it for capabilities.

### Exact frontend changes

Overlay technique, proven by probes: append our JS to `app.js` as one script at serve time and recompute the CSP hash. `function` and `class` bindings are reassignable; `const` bindings are not, but `KEYS`, `S`, `side` and `overlay` are mutable objects. Reassignment must run synchronously in the same script, before `boot` passes its first `await`.

| Need | Change | Hook | Runtime support |
|---|---|---|---|
| Capabilities | Fetch caps at start; every control disabled with a reason, not hidden | Overlay; `view_info` extension field | Token scopes |
| Compose | Composer at bottom of `ChatView`, Shift+Enter multiline, target label, `@` completion | Subclass `ChatView` (probed) | `x/command send` with a stable `command_id` per draft |
| Reply | Reply action; composer in `ThreadPane` | String insert before `<div class="actions">` in `messageHtml` output (probed); wrap `ThreadPane` | `reply_to` mapped to our message ID |
| Human vs agent | `fields.kind`; badge in rows and avatars; fix "N agents" stat, which counts every user (`swarmchat@fb5aa6a05b40:swarmchat/page/app.js:251`) | Wrap `avatar`; **`#stats` needs a post-render override or an edit** | Projected field |
| As-agent mode | Composer stays the human; disable with a reason while `S.route.as` is set | Overlay | None |
| Lifecycle | Actions in `PersonView` and Map pane: stop, cancel, retire, spawn, each with confirm and conflict display | Wrap `PersonView`; extend `onClick` | Commands with `expected_version` |
| Approvals | Card in the message plus a "Needs you" sidebar entry and counter | Wrap `messageHtml`, `onClick` (probed); sidebar via `side.build` | Approval resolves through `change` events; 409 on conflict |
| Attachments | Picker, drag and drop, paste, size limits, progress | Overlay; `fetch` works under `connect-src 'self'`. Forms must `preventDefault` because `form-action 'none'` | Binary upload to content store, then reference in the send command |
| Tool activity | Compact line under a message or turn, expandable; never in the main stream | New system kinds plus overlay renderer | Separate read RPC, paged |
| Tasks and board | New view for task status, claims, leases | **`readRoute` allowlists layouts** (`swarmchat@fb5aa6a05b40:swarmchat/page/app.js:168`): replace `readRoute`, push to `KEYS`, or add a `task` route key | Projection tables |
| Artifacts and diffs | Present as attachments; `.diff`, `.md`, logs and CSV already render through the file viewer | Reuse `openText`, `view_text` | Artifact bodies by content reference |
| Provenance | Pane with evidence type, version, gaps; "follow into provenance" action | **Pane choice is fixed in `route`** (`swarmchat@fb5aa6a05b40:swarmchat/page/app.js:211`): reuse the `knew` key or wrap `route` | Graph query RPC |
| Honest wording | "Read by" becomes "Delivered to"; rewrite the `--peek` text in `KnewPane` (`swarmchat@fb5aa6a05b40:swarmchat/page/app.js:1457`), login text (`swarmchat@fb5aa6a05b40:swarmchat/page/index.html:43`), branding | **Literal strings: serve-time exact-match edits** | Evidence labels |

Serve-time edits, if needed, should each assert exactly one match against pinned SHA-256 and fail closed. Bold rows are where a small upstream hook set would help: named hook points in render, route and sidebar. That is the proposal for (a), plus an optional API base path.

Receipts mapping: `positions` and `view_receipts` show agents' observed delivery from journal events, labeled as delivery and never as understanding. Human unread state, if kept, lives in a separate human table and never touches agent cursors. `view_knew` maps to observed exposure with coverage gaps. No `view_*` request writes anything.

Probe results (stub backend with in-memory authority, unmodified installed assets, overlay appended):

| Check | Result |
|---|---|
| Composer, send, `<b>` stays text, reload | 2 messages after reload, 0 `<b>` elements, no duplicates |
| View-only credential | Composer disabled; `cmd_send` 403 |
| Same approval clicked at the same moment from 2 browsers | One 200, one 409; effect applied once; both cards updated live |
| Offline, message lands, back online | 0 copies while offline, 1 after |
| Same feed entry delivered twice under new numbers | Still 1 copy; the page dedupes by `seq` |

## 5. Assets: import or vendor

- Import works. `importlib.resources.files("swarmchat.page")` read the installed assets in the probe, though `page` has no `__init__.py` and is not a promised API. The wheel carries `LICENSE` in `dist-info/licenses/`.
- **Recommend importing from the installed package**, in an optional SwarmChat extension, not the SDK core. Zero transitive dependencies. Read only the five page files; never import `swarmchat.server` or `store` at runtime.
- Pinning: `swarmchat==0.1.0` exact, with `uv.lock` hashes. At startup check SHA-256 of each asset against an allowlist, and on mismatch disable the web client with a clear reason. Current values: `app.js 20e425ebb49b…`, `app.css 3dc776935e38…`, `index.html 00f9da6be1f4…`, `gate.js 83cb82cebcb7…`, `gate.html ab77cea699e1…`. Record the version and hashes in the reproducibility manifest. Upgrades are explicit PRs that re-run the contract and browser suites.
- MIT notice: we serve a modified combination, so keep the copyright and license text in third-party notices and in a banner comment on the served script. Compute the CSP hash after adding the banner.
- Vendoring is the fallback, for a yanked release or if overlay plus edits stop being small: `third_party/swarmchat/` with LICENSE, source commit and a patch list.
- Keep overlay code in plain JS and match upstream's no-build style. It stays readable, and the release adds no Node toolchain.

## 6. End-to-end testing

- Upstream has no browser tests in repo or CI. CI is `unittest` on Linux, macOS and Windows with Python 3.9 and 3.13, plus an install check that the page files ship (`swarmchat@fb5aa6a05b40:.github/workflows/tests.yml:31`). 181 `def test` total across 7 files; the real server runs against a temp folder. `Page` tests check headers and CSP hash only (`swarmchat@fb5aa6a05b40:tests/test_view.py:498`). `app.js` logic is untested in CI. Browser numbers in `bench/RESULTS.md` have no committed script.
- **Playwright with headless Chromium works here.** RHEL 9.4 x86_64, no root. Python `playwright` 1.64.1 plus `chromium_headless_shell`. `ldd` found all 50 libraries, none missing. The 2-client stub smoke took 4.7 s wall. Browser cache including ffmpeg is 278 MB. 330 fonts visible, 1 emoji font.
- A Singularity image was not needed. `singularity-ce` 4.4.1 and `podman` are present as fallbacks and were not tried.
- Tested only with Chromium headless shell. The screenshot shows correct layout with text intact.

Traps found:

- `page.wait_for_function("...string...")` failed with `EvalError` because the page's CSP forbids `eval`. Use locators. `page.evaluate` works.
- Never set `bypass_csp` in these tests, because it would void the safety checks.
- `set_offline(True)` does not end a long poll already in flight. Wait out the hold before asserting.
- Live updates can remove a button before a second client clicks it. To race, schedule clicks for a shared wall-clock time.
- `follow()` catches exceptions from `apply`, so an overlay bug can show up only as "Offline" (`swarmchat@fb5aa6a05b40:swarmchat/page/app.js:1596`). Fail tests on `pageerror` and unexpected console errors.

Proposed suite, Python `pytest` plus Playwright, using `--only-shell` for speed:

| Test | Asserts |
|---|---|
| Shape conformance | Same scenario against real `swarmchat` (dev dependency) and our backend; key sets and types of all 14 replies match |
| Human message path | Browser message reaches a fake driver's supported input path once |
| Two clients | Reply appears in browser and TUI test client |
| Approval race | Exactly once across two clients, loser sees 409 explained |
| Credentials | View link cannot command; composer disabled with reason; forged `from` rejected |
| Origin and Host | Foreign values rejected on the command route; remote bind needs explicit opt-in |
| Safe rendering | XSS corpus in messages, names, channel names, file names, tool output, artifacts, with CSP on |
| Reconnect | Offline window, retried command, reload: no duplicate messages or actions |
| Receipts | Browsing changes no agent cursor and writes no journal event |

## Implications for platoon-harness

1. Choose (b). Build a projection from the journal into tables shaped for the 14 `view_*` replies, rebuildable, with persisted ID mappings.
2. Mount the backend as an event sink/frontend extension. All mutations go through one `x/command` route into the SDK command service; the bridge owns no scheduling.
3. Implement `view_*` requests in order: page, snapshot, feed, messages and thread for Milestone 1 (the stub smoke called only the first four, plus `view_info` from the overlay); the rest by Milestone 4. An unguarded rejection in a view leaves it blank, so every reachable view needs a real reply or a disabled entry. Back `view_search` with SQLite FTS or a bounded scan.
4. Add a durable feed. The page's protocol already fits: batches of at most 5,000, `after` cursor, `reset` only on projection version change.
5. Credentials: separate view and control token classes. Link tokens are one-time and exchanged for expiring, revocable, run-scoped session tokens that are lowercase hex so the page accepts them. The admin or owner credential never reaches a browser. Assume `localStorage` persistence, which is why expiry matters.
6. On the control route require Bearer token, Origin and Host allowlists, `command_id`, and `expected_version` where relevant; bind loopback by default; require explicit opt-in plus TLS for remote exposure.
7. Keep the CSP as strict as upstream's, with hashes recomputed. Render new content through upstream's `html` template only.
8. Keep observer state out of the content log. Upstream's `read` lines in the message log are exactly what the brief forbids for us.
9. Borrow semantics for SDK cursors: `wait` starts from the durable cursor, ack rides on the next request, a cut-off wait confirms nothing, and filtered reads never advance past unshown messages. Our supported delivery still needs turn-boundary semantics that SwarmChat does not model.
10. Bound telemetry: tool and token events do not enter `chat.messages`-like tables, so normal channels stay readable.
11. Provide upstream, unpushed, a short note requesting render, route and sidebar hooks and an API base path. The product does not depend on it.

## Taste notes

- Elegant: the `html` tagged template plus `Safe` makes escaping the default, and hash-only CSP backs it up.
- Elegant: the token gate returns nothing useful without a token, and a fragment-only link keeps the token out of logs.
- Elegant: `wait` with ack on next request makes the safe failure direction automatic. A cut-off call just redelivers.
- Elegant: "a search never marks read a message it left out" is a real adversarial thought in a small rule.
- Elegant: the server defends itself plainly: token before body, deadlines, per-user cap, eviction only of idle connections, and each limit explained in one comment.
- Elegant: one snapshot, then a numbered feed, with a window of 150 messages on screen and a hard cap of 700. Worth copying for TUI views.
- Avoid: read receipts and content sharing one sequence space; zero extension seams in a single global script; an in-memory feed as the only change stream; plaintext long-lived tokens with no rotation for view and admin; design documents left stale against code.
- Avoid: `--where` Python `eval`, however carefully guarded. Typed filters are a smaller thing to trust.

## Unknowns and risks

- The `view_*` wire shape is internal and unversioned. Exact pin plus conformance test contains this; an upgrade could still be costly.
- The project is days old: one commit, one release, 45 stars, no stated roadmap. Upstream may change direction or add a composer. Pinning insulates us, and we would then re-evaluate.
- Overlay coupling to top-level names is real. Probes covered `ChatView`, `messageHtml`, `onClick` and `api`; `readRoute`, `route`, `PersonView`, `side` and sidebar changes are read from code, not probed.
- Probe scope: stub authority was an in-memory list under one lock, so the exactly-once result proves the UI flow, not our journal transaction. Overlay was unstyled. Map, board and the feed `reset` path were not exercised in a browser. Firefox, WebKit and macOS are untested.
- Fixed `/v1/` paths mean one run per origin or token-selected runs. `localStorage` holds one token per origin, so two runs in tabs on one origin collide on reload. Separate ports avoid this.
- Large runs: upstream's page cost was measured with 3,527 chats and 1,000 users on upstream's backend. Ours is unmeasured. Snapshot size grows with chats, and `S.chats` is held fully in memory.
- `style-src 'unsafe-inline'` remains in the CSP because the page relies on it. CSS injection stays limited by escaping, not by policy.
- `swarmchat.page` has no `__init__.py`; resource access worked on Python 3.12 and was not tested on other versions.
