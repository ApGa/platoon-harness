# RFC 0063: What an offer showed is answered by its ref

| | |
|---|---|
| Status | Accepted, 2026-11-07 |
| Created | 2026-11-07 |
| Authors | Apurva Gandhi (`ApGa`) |
| Builds on | [`primitives/provenance.py`](../../packages/sdk/src/platoon_harness/primitives/provenance.py), [`primitives/common.py`](../../packages/sdk/src/platoon_harness/primitives/common.py), [architecture section 11](../architecture.md#11-provenance), [RFC 0036](0036-one-ref-names-what-a-model-is-shown.md), [RFC 0037](0037-an-offer-is-confirmed-only-by-its-harness.md) and [RFC 0038](0038-provenance-is-answered-from-the-record.md) |
| Discussion | The notes of Platoon's `platoon-teams` bridge, under the SDK asks still open, kept outside this repository |
| Implementation | `feat: Show the text each item of an offer showed, by the offer's ref` |

## Summary

`context.show(offer)`, a query op with `Session.shown` and the command `context show`, gives the text each item of an offer
showed, in the offer's order, where the journal proves it by the item's digest, and null where it does not: a gist as it was
shown, with any fields beside it, and a body or the lines of one. An offer goes on recording refs and digests, never text.

## Motivation

An offer, `context.offered`, records each item by the ref of the event it showed, its form, gist or body, and a digest of what it
showed ([RFC 0036](0036-one-ref-names-what-a-model-is-shown.md), [RFC 0037](0037-an-offer-is-confirmed-only-by-its-harness.md)).
What it showed is not always the event's own words. A spawn shows its goal, a board entry its gist with its fields, a commit its
gist with its SHA and its workspace, and an entry that carries another event, a child's report or a board's announce, its own
words under the carried event's ref. The form a gist is shown in with its fields was private to `Exposed.gist`.

Platoon's bridge shows a training step's inputs in its viewer, each with its text where the record proves it. To prove a board
entry's text it rebuilt that private form, so a change to it would leave the text null; and a report or an announce, whose words
no event it names holds, it could not show at all. A training system, a viewer, or a person asking what an agent was shown had no
public way to the text an offer showed.

## Proposal

### 1. One query, by the offer's ref

```python
async def shown(self, offer: str) -> tuple[str | None, ...]: ...  # Session; the op is context.show(offer)
```

It takes an offer's ref, `context/<agent>@<version>`, and answers one text or null for each item, in the offer's order, so a reader
that walks an agent's offers, as a training system does, asks once per offer. It refuses any other ref `invalid`. It is a query
for people and programs and no agent's tool, as the other provenance queries are, and a command, `platoon-harness context show`,
as every op a person may run is.

### 2. Proved by the digest

A gist is one of the texts an offer shows of the event the item names: its own gist, with the fields it holds, as a board entry's
are; a commit's gist with its SHA and its workspace; a spawn's goal; or the gist of an entry shown by that ref, a message or one
that carries the event. A body is the whole body the digest names, or the lines the ref names of its event's body. The answer is
the one whose hash is the item's digest, so it is never another's text. It reads only bodies the journal holds, as no op reads
`blobs/`, so a body past 64 KiB, and one redacted since, is null.

### 3. One shown form

The text an offer shows of a gist with fields is made by one function, which the offer's digest and the query both use, and the
fields a commit shows beside its gist by one more, which `repo.commit` and the query both use.

## Alternatives

| Alternative | Why not |
|---|---|
| Record the shown text in each offer | An event's data is capped at 16 KiB, and a read of 32 board entries with their fields could pass it and be refused; every handover of one entry to many readers would hold its words again; and the journal would change for what it already proves |
| Make the shown form public as a function | It says how a gist with fields is shown, not which gist an item showed: a report's or an announce's words lie in the entry that carries the event, which the item does not name |
| A field `text` on what `exposure` and `lineage` return | They answer about one event and page its offers, so a reader walking an agent's offers would ask once per event and lose what lies past a page |
| Name the op `shown` | The naming law refuses an op named in the past tense. `context.show` shows an offer on an agent's context stream, and `Session.shown` reads as what it answers |

## Consequences

- A training system shows a step's inputs by `Session.shown`, and builds no shown form of its own. The bridge's rebuilt form can
  go once it pins a commit that holds this.
- A gist the SDK comes to show in a new form needs a text here. The test that makes every kind of offer and proves each item's
  text fails until it has one.
- A body past 64 KiB is null here though its bytes are kept, and a whole one is still read by its digest with `get_body`.

## Evidence

- [tests/unit/primitives/test_provenance.py](../../tests/unit/primitives/test_provenance.py),
  `test_context_show_gives_the_text_each_item_of_an_offer_showed`: every kind of offer the SDK makes, a launch, a handover of an
  announce and of a child's report, and reads of a board entry with its fields and its lines, a message with its body, a task and
  its result and a commit, each item's text held to its digest, and the form of a board entry's gist with its fields pinned;
  `test_context_show_says_null_for_what_the_journal_no_longer_proves`; and the scenario's answers, alike after a rebuild and on a
  closed copy.
- [tests/unit/runtime/test_session.py](../../tests/unit/runtime/test_session.py),
  `test_what_an_offer_showed_through_the_facade`.
- The bridge's display and its notes, in Platoon's `platoon-teams`, kept outside this repository.
