# RFC 0066: An approval carries the whole of what it asks

| | |
|---|---|
| Status | Draft |
| Created | 2026-11-08 |
| Authors | Apurva Gandhi (`ApGa`) |
| Builds on | [`primitives/reports.py`](../../packages/sdk/src/platoon_harness/primitives/reports.py), [`primitives/approvals.py`](../../packages/sdk/src/platoon_harness/primitives/approvals.py), [`runtime/host.py`](../../packages/sdk/src/platoon_harness/runtime/host.py), [`testing/conformance.py`](../../packages/sdk/src/platoon_harness/testing/conformance.py), [architecture section 7](../architecture.md#approvals) and [section 9](../architecture.md#9-drivers), [RFC 0008](0008-driver-contract-and-wire.md) and [RFC 0044](0044-a-level-is-earned-on-the-machine-that-runs-it.md) |
| Discussion | Milestone 4's plan and the critiques of its first draft, kept outside this repository |
| Implementation | `feat: Carry an approval's whole ask as a body, redacted and bounded`, `feat: Send the whole ask from Claude Code, Codex, pi and OpenHands approvals`, `feat: Join a Codex file change approval to the patch of the item it names` and `feat: Check in check_driver that an approval shows its whole ask` |

## Summary

A driver's `approval.requested` report gains `body`, the whole of what its harness asks to do: the command, the patch or the
tool's input, as the harness gave it. The host masks it as it masks every report, keeps its first 64 KiB, cut at a character's
end, and counts in `cut` the bytes it left out. The record's `approval.requested` names that body, so `blob.get` reads an
approval's whole ask at `approval/<id>@1`, and a body can be redacted as any can. `claude`, `codex`, `pi`, the OpenHands worker,
`ScriptedDriver` and a wire program each send it, and a wire program that sends none still asks. Codex names no patch when it asks
about a file change, so its driver joins the request's `itemId` to the patch of the item Codex started under that id. A new check,
`approval_shows_its_ask`, proves on each real binary against FakeModel that an approval carries the whole command it asks about.
This is step 1 of 2: step 2 shows the whole ask in both clients before anyone answers it.

## Motivation

An approval says what it asks in its gist alone, at most 280 characters. A person deciding one reads part of what will run:

- Claude Code asks for an `Edit` with the text it writes as its input, and the gist holds the tool's name and the start of that
  input as JSON ([`drivers/claude.py`](../../packages/sdk/src/platoon_harness/drivers/claude.py)).
- A command past 280 characters is cut, whichever harness asks, and what follows the cut, a `; rm -rf`, is what a person needs
  most to see.
- Codex's request to apply a patch names the item it holds up and no patch, so the gist is the request's reason or else its
  method's name, `item/fileChange/requestApproval`
  ([`drivers/codex.py`](../../packages/sdk/src/platoon_harness/drivers/codex.py)). A person allows a patch they cannot see.

The terminal's dock and the page's card show that gist and Allow and Deny, and nothing else. Milestone 4's definition of done asks
that both clients show the whole ask before Allow or Deny, which needs the ask in the record first.

## Proposal

### 1. The report carries the ask

```python
class ApprovalRequested(Args):
    type: Literal["approval.requested"] = "approval.requested"
    id: Name
    gist: Gist
    body: str | None = None  # the whole ask, until the host stores it; None when the harness does not say it
    cut: int = 0             # bytes of the whole ask the body leaves out
```

`body` is the whole of what the harness asks to do, as it gave it, and its gist is a line saying what that is. It is text until
the host stores it, as an item's body is. None means the driver cannot say, which is unknown and not an empty ask. A driver sends
the ask whole. A wire program that cut it already, so that its frame stays within a line, says in `cut` how many bytes it left
out.

### 2. The host masks it, then bounds it

The host masks every report with the credentials the agent holds, in each form a text can carry one, before it takes it, and the
ask is masked with the rest. Then it keeps the ask whole up to 64 KiB, the most the journal holds in an event's own row, and past
that its first 64 KiB, cut at the end of the last whole character, adding the bytes it left out to `cut`. It stores what it kept as
a body, as it stores an item's. Masking comes first, so a cut never splits a secret into a part the mask would miss.

The bound is the host's, and not each driver's, so every driver and a wire program in any language get it without a rule of their
own, and no ask reaches the journal unbounded. An ask is cut at a character's end, and not at a line's, as a patch is
([RFC 0065](0065-a-diff-is-read-on-request-as-a-test-is-run.md)), since an ask is often one line, a command or a tool's input as
JSON, and a cut at a line's end would keep nothing of it.

### 3. The record names it

`approval.request`, the op only the runtime holds, and `agent.report` take the body's ref and `cut`, and `approval.requested`
records them at payload version 2:

```python
{"id": "a1", "policy": "ask", "body": "sha256:…", "cut": 0}
```

The event's body is the ask, so a client reads it by the body's ref, as it reads any body, and `blob.get` reads it at
`approval/<id>@1`, the first event of the approval's stream, a page of whole lines at a time, as it reads any body held in the
journal's row. An agent reads its own, as the event is its, and nobody else's. A body the journal does
not hold in its row is refused `invalid`, as `blob.get` could not read it, and the host then answers the approval `deny`, as it
does any approval the journal refuses. `body.tombstone` redacts an ask as it redacts any body, for a secret the mask did not know.
A version 1 payload has neither field, which a reader takes as an ask nobody said and nothing cut. The `Approvals` view and the
attention row are unchanged: a client reads the ask by its ref when it shows it.

### 4. What each driver sends

| Driver | The ask |
|---|---|
| `claude` | The tool's name, then its input as JSON, the text the gist begins with |
| `codex` | A command's `command`; a file change's patch, below; and any other request, for permissions or a tool of the user's own, its params as JSON |
| `pi` | What the gate asks pi to confirm, the tool's name and its input as JSON, or a user's own extension's title and message |
| `openhands` | Each action of the step it asks about, its tool's name and its arguments as the model gave them, as one approval covers a step |
| `ScriptedDriver` | The gated tool's name and its input as JSON; `Ask(gist, body)` scripts one |
| The wire | What the program sends, an optional field within protocol 2 |

### 5. Codex's file change is the patch of the item it names

Codex's `item/fileChange/requestApproval` names `itemId` and an optional reason, and no patch. Codex starts that item, a
`fileChange` holding each file's change, before it asks, so the driver keeps each started file change's patch by the item's id and
gives a request for that id its patch as the ask. A request for an item the driver never saw start asks with its ask unknown. The
driver reads only its own thread's items, so a native child's file change asks with its patch unknown too.

The patch is each file the item changes, by its kind and path as Codex gives them, `add a.py`, then that file's change as Codex
gives it: an added or deleted file's text, or an update's unified diff. Codex's diff names no path, so the line before it does.
A completed patch item's body is the same text, so a person reads one patch whether they are asked about it or read what came of it.

### 6. A check proves it

`approval_shows_its_ask` scripts the harness's gated tool with a command longer than a gist holds, `touch asked` and a comment,
waits for the approval, denies it, and passes when the approval's body holds that command whole. The command writes a file, as
Claude Code runs an `echo` without asking, and the denial keeps it from running. It needs `approvals`, as
`approval_answered` does. FakeModel's log is the ground truth: the command is what the model asked to run. A failure leaves
`operational` unmet, as one of `approval_answered` or `denial_holds` does, since a person cannot control what they cannot see.

### 7. The wire

`body` and `cut` are optional fields of the `approval.requested` frame within protocol 2. A program that leaves them out still
asks, with its ask unknown, and nothing it sends or reads changes. Nothing is released yet, so no runtime that refuses the fields
exists outside this repository.

## The hard parts

- **A secret outside the known set.** The mask knows the credentials the agent holds, and an ask can carry one it does not, a key a
  model read from a file and put into a command. It becomes a stored body. `body.tombstone` redacts it, and the person who sees it
  first is the one deciding, which is the reason to show it.
- **A large ask on the wire.** A wire program's line is at most 16 MiB, and one past it stops the agent with a gap. A program with
  an ask that large cuts it and says so in `cut`.
- **Hostile text.** An ask is whatever a model wrote. Step 2 draws it through `SafeText` in the terminal and as text under the
  page's policy, as every other body is drawn.

## Alternatives

| Alternative | Why not |
|---|---|
| A longer gist | A gist is what any client shows for any event, at most 280 characters, and an event's data holds 16 KiB. A patch or a file's text is a body |
| Each driver cuts the ask, as `Native.raw` is cut | Every driver and wire program, in any language, would have to mask and then cut in bytes. One that did not would either have its report refused, leaving its harness waiting on an approval nobody sees, or reach the journal unbounded. The host already masks every report |
| Cut at a line's end, as a patch is | An ask is often one line, a command or a tool's input as JSON, and would keep nothing |
| Keep an ask of any size | A body past 64 KiB is held outside the journal's row, in `blobs/`, which no op reads, so `blob.get` would give no text |
| Carry the ask on the attention row or the `Approvals` view | A row is in every watcher's snapshot, and 64 KiB a row would cost each one. The ask is read by its ref when a client shows it |
| Codex: every request's params as JSON, a command's too | A person reads a command as the shell runs it, and JSON escapes its quotes |
| Codex: the patch from `turn/diff/updated` | That is the whole turn's diff, not the item's, and it is said after the item starts |
| A new protocol number | The fields are optional, so a program written before them is unchanged, and none has been released |
| Scopes, a denial with feedback, or permission modes | No harness's honouring of them is verified, so milestone 4 adds none, which is the default pending the owner's ruling |

## Consequences

- A person can read the whole of what they are asked to allow, up to 64 KiB, before deciding, once step 2 draws it.
- A Codex file change is shown as its patch, which until now nobody saw at the moment of asking.
- An approval costs a stored body, of up to 64 KiB, beside its event.
- An ask holding a secret the mask does not know is kept until someone redacts it.
- A driver whose approval hides its ask fails `approval_shows_its_ask`, and is not `operational`.
- A completed Codex patch item's body names each file before its change, where it held the changes alone.

## Rollout plan

| Milestone | Scope | Exit check | Pull requests |
|---|---|---|---|
| M1 carried | `ApprovalRequested.body` and `cut`, the host's bound, `approval.requested` at version 2, each shipped driver's ask, Codex's file change joined to its item, and `approval_shows_its_ask` | `tests/unit/primitives/test_approvals.py`, `test_host.py`, `test_check_driver.py`, `test_claude.py`, `test_codex.py`, `test_pi.py` and `test_wire.py`, and the slow conformance runs in `tests/integration/` on each real binary, Codex's file change among them | |
| M2 shown in both clients | The terminal's dock and the page's card open an approval's whole ask before it is answered, and say where it was cut | The tests of milestone 4's stage S08 | |

## Open questions

1. Should approvals gain scopes, a denial with feedback, or permission modes? M1 builds the default, pending the owner's ruling:
   none in milestone 4, as no harness's honouring of them is verified, and the whole ask is shown before anyone answers. Any of
   them would change what an answer carries, not what a request asks, so it would remove nothing M1 builds. Needed before
   milestone 4 closes.

## Evidence

- Codex's request names the item and no patch: `FileChangeRequestApprovalParams` holds `threadId`, `turnId`, `itemId`,
  `startedAtMs`, `reason` and `grantRoot` (`codex@05c08d765523:codex-rs/app-server-protocol/src/protocol/v2/item.rs:1741`), and
  the app-server sets `itemId` to the patch call's id (`codex@05c08d765523:codex-rs/app-server/src/bespoke_event_handling.rs:642`).
  Codex starts the `fileChange` item under that id, holding each file's change, before it asks
  (`codex@05c08d765523:codex-rs/core/src/tools/handlers/apply_patch.rs:575`), and gives an added file's text, a deleted file's
  text, or an update's diff with no path (`codex@05c08d765523:codex-rs/app-server-protocol/src/protocol/item_builders.rs:342`).
- On Codex 0.167.0 against FakeModel, with the sandbox `read-only`, a model's `exec_command` running `apply_patch` made the item
  start and then the request for it under the same id, which `test_a_file_change_approval_on_the_real_binary_carries_its_patch`
  in `tests/integration/test_codex.py` keeps.
- `approval_shows_its_ask` passed on Claude Code 2.1.319, Codex 0.167.0, pi 1.5.0 and the OpenHands SDK 1.59.0 against
  FakeModel, in each harness's `test_the_<harness>_driver_conforms`, and on `ScriptedDriver` and a wire program in
  `tests/conformance`. With `echo` in place of `touch`, no approval came from Claude Code 2.1.319, which ran the command unasked and
  sent its output to the model as the tool's result.
- The bound is the most the journal holds in an event's own row, 64 KiB, as for a test's output and a patch. How often an ask
  passes it is unmeasured: a command is short, and an `Edit`, a `Write` or a patch carries the text it writes (UNVERIFIED).
- The tests named in the rollout plan's M1.
