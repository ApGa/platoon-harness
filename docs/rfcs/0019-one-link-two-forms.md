# RFC 0019: One link, two forms

| | |
|---|---|
| Status | Accepted, 2026-11-03 |

## Summary

`Session` has one link, in-process or over a socket. Start and resume are one path, and a client only pulls

## Motivation

A script owns a session in-process, a TUI is a guest of a detached runtime, and a guest may find the runtime gone. The three must share
one implementation and its semantics. The kernel already answers most of this: an `Outcome` is data, a key dedupes a retry, and a
reader pulls. What was missing was how one class reaches a kernel in another process without a second code path, how a runtime starts
and restarts, and what `settled` should do about an approval nobody will answer.

## Proposal

- **`Session` holds one `Link`, in two forms.** `Local` is the kernel in-process, `Remote` is the control socket, and the server is a
  `Local` per connection, so the methods mirror by construction. Nothing above the link knows which it has. History is `Local` on a
  read-only kernel.
- **Start and resume are one path.** `prepare` checks the team and writes the manifest, and a runtime needs only the folder. It runs
  `recover`, then opening under fixed keys, which answer from the journal if they already ran, then reap, resume, reconcile.
- **A client only pulls.** `read` is a page, and `changed` and `delta` are long-polls. A long-poll comes back within 25 s, so a client
  that gave up frees the server's task.
- **A view credential is a class of connection, not a principal.** It binds the human's identity with writes denied at the door, so
  a try writes nothing. A scoped principal would journal `op.refused` for each try, and a reader that can grow the journal is no reader.
- **`needs_human` asks who else is attached.** An `ask` nobody could answer returns at once. "Could" means another client with a
  control credential, which `others` counts. A script that answers its own approvals attaches a guest to do it, or states a policy.
- **A one-shot agent ends with its turn.** `turn.ended` is its end, and `stopped` means it finished. So no window exists in which it
  is idle but about to exit, and nothing has to tell that window from settled.

## Alternatives

| Alternative | Why not |
|---|---|
| A push subscription on the socket | Each client would need a queue in the runtime, which law 8 forbids. A slow one would then be someone else's problem |
| Separate `SessionOwner` and `SessionClient` classes | Two facades to keep equal, which is what one link removes. The difference is what leaving does, so that is all that differs |
| A parent process opening the session, then handing over | Two writers in the life of one journal, and the opening would not be resumable by what resumed it |
| `settled(approvals=...)` | The policy is a durable session setting. Said at the wait, it would hold for nobody else and leave no record |
| A timeout as the answer to an unanswerable `ask` | CI would wait out its budget for a question nobody can hear. It must never hang on a confirmation nobody can see |
| `Exited.code`, read at exit | It leaves a one-shot agent idle between its turn's end and its exit, where `settled` is true and wrong. Ending it with its turn removes the window and the field |

## Consequences

- A guest whose runtime goes falls back to history on its own, and finds the next runtime on its next call. A command it had in flight
  retries under its key, so losing an ack costs no duplicate.
- A detached runtime exits once a session that has stopped accepting work has drained. A guest calling `settled` finds that as a closed
  connection, falls back to history, and reads the same ending there.
- `needs_human` reads connections, so a guest attached only to watch with a control credential holds it off. Use a view credential to
  watch.
- A body crosses the socket as base64 in one line, so it is limited to about 12 MiB there. A larger one is refused before it is sent.
- Nothing here has run on macOS, or under a real harness.

## Evidence

- `tests/integration/test_detached.py`, `tests/integration/test_crash.py`, and `tests/unit/runtime/`.
- [Architecture sections 4 and 12](../architecture.md), [law 8](../architecture.md#3-laws), [RFC 0006](0006-per-session-runtime.md).
