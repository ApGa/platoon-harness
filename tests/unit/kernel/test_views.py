"""Views: versioned folds, per-view rebuild, high-water marks, unknown events."""

import pytest

from platoon_harness.kernel import Args, Event, Extension, Kernel, Refused, Txn, View, fold, op

from .support import Notes, dump, events_of, notes, refused_code, result_of


@op("alien.land")
def land(txn: Txn, a: Args) -> None:
    """Emit events only other extensions understand."""
    txn.emit("note.added", "note/a", gist="while you were out", data={"text": "while you were out"})
    txn.emit("alien.landed", "alien/1", gist="an event nobody folds", data={"from": "afar"})


alien = Extension("alien", ops=[land])


def fold_marks(kernel) -> dict[str, tuple[int, int]]:
    with kernel._reading() as db:
        rows = db.execute("SELECT * FROM v_folds").fetchall()
    return {row["view"]: (row["version"], row["high_water"]) for row in rows}


async def test_a_query_method_is_reached_through_txn_view(kernel):
    result_of(await kernel.submit(kernel.runtime, "note.add", {"text": "typed"}))
    assert result_of(kernel.query(kernel.runtime, "note.list", {})) == ["typed"]


async def test_an_op_reads_its_own_writes(folder, clock):
    @op("seen.count")
    def count(txn: Txn, a: Args) -> int:
        """Emit, then read what the fold made of it."""
        txn.emit("note.added", "note/a", gist="one", data={"text": "one"})
        return len(txn.view(Notes).texts("note/a"))

    kernel = Kernel.open(folder, clock=clock, extensions=[notes, Extension("seen", ops=[count])])
    assert result_of(await kernel.submit(kernel.runtime, "seen.count", {})) == 1
    kernel.close()


async def test_one_view_rebuilds_alone(kernel, folder):
    result_of(await kernel.submit(kernel.runtime, "note.add", {"text": "kept"}))
    before = dump(folder)
    kernel._writer._db.execute("DELETE FROM v_notes")

    await kernel.rebuild(Notes)

    assert dump(folder) == before


async def test_rebuild_all_produces_identical_contents_after_every_kind_of_event(kernel, folder):
    runtime = kernel.runtime
    result_of(await kernel.submit(runtime, "principal.add", {"id": "agent:a", "scopes": ["note.*"]}))
    result_of(await kernel.submit(runtime, "principal.add", {"id": "agent:b", "parent": "agent:a"}))
    result_of(await kernel.submit(runtime, "grant.add", {"who": "role:x", "ops": "*", "on": "inbox/{parent}"}))
    effect = result_of(await kernel.submit(runtime, "note.dispatch", {"timeout": 9.0, "on_uncertain": "retry"}))
    result_of(await kernel.submit(runtime, "effect.start", {"id": effect}))
    result_of(await kernel.submit(runtime, "note.remind", {"due": 5.0, "key": "k"}))
    result_of(await kernel.submit(runtime, "note.add", {}, key="kept"))
    await kernel.submit(runtime, "note.add", {"fail": True}, key="refused")
    args = {"type": "turn.started", "stream": "turn/a", "agent": "a", "data": {"turn": "t1"}}
    result_of(await kernel.submit(runtime, "note.mark", args))
    body = await kernel.put_body(b"secret")
    result_of(await kernel.submit(runtime, "body.tombstone", {"sha256": body}))
    await kernel.recover()
    before = dump(folder)

    await kernel.rebuild_all()

    assert dump(folder) == before
    assert all(mark == (1, kernel.head) for mark in fold_marks(kernel).values())


async def test_a_version_bump_drops_and_refolds(folder, clock):
    kernel = Kernel.open(folder, clock=clock, extensions=[notes])
    result_of(await kernel.submit(kernel.runtime, "note.add", {"text": "again"}))
    kernel.close()

    class NotesV2(View):
        name = "notes"
        version = 2
        schema = "CREATE TABLE v_notes(body TEXT NOT NULL) STRICT;"

        @fold("note.added")
        def added(self, event: Event) -> None:
            self.db.execute("INSERT INTO v_notes VALUES (?)", (event.data["text"].upper(),))

    reopened = Kernel.open(folder, clock=clock, extensions=[Extension("notes2", views=[NotesV2])])
    assert dump(folder)["v_notes"] == [("AGAIN",)]
    assert fold_marks(reopened)["notes"] == (2, 1)
    reopened.close()


async def test_a_toggled_extension_leaves_no_stale_view(folder, clock):
    kernel = Kernel.open(folder, clock=clock, extensions=[notes])
    result_of(await kernel.submit(kernel.runtime, "note.add", {"text": "before"}))
    kernel.close()

    away = Kernel.open(folder, clock=clock, extensions=[alien])
    result_of(await away.submit(away.runtime, "alien.land", {}))
    away.close()

    back = Kernel.open(folder, clock=clock, extensions=[notes])
    assert result_of(back.query(back.runtime, "note.list", {})) == ["before", "while you were out"]
    back.close()


async def test_unknown_event_types_pass_through(folder, clock):
    kernel = Kernel.open(folder, clock=clock, extensions=[alien])
    result_of(await kernel.submit(kernel.runtime, "alien.land", {}))
    await kernel.rebuild_all()
    kernel.close()

    plain = Kernel.open(folder, clock=clock)
    survivors = [event for event in events_of(plain) if event.type == "alien.landed"]
    assert [event.data for event in survivors] == [{"from": "afar"}]
    plain.close()


async def test_a_fold_never_sees_an_outcome(folder, clock):
    seen = []

    class Watcher(View):
        schema = "CREATE TABLE v_watcher(n INTEGER) STRICT;"

        @fold("note.added")
        def added(self, event: Event) -> None:
            seen.append(event.outcome)

    kernel = Kernel.open(folder, clock=clock, extensions=[notes, Extension("watcher", views=[Watcher])])
    result_of(await kernel.submit(kernel.runtime, "note.add", {}))
    await kernel.rebuild(Watcher)
    kernel.close()

    assert seen == [None, None]


def test_a_view_cannot_claim_foreign_tables(folder, clock):
    class Thief(View):
        schema = "CREATE TABLE v_principals(id TEXT) STRICT;"

    with pytest.raises(Refused) as error:
        Kernel.open(folder, clock=clock, extensions=[Extension("thief", views=[Thief])])
    assert refused_code(error) == "invalid"
    assert not folder.exists()


async def test_a_wildcard_fold_sees_every_event_and_rebuilds_the_same(folder, clock):
    class Everything(View):
        schema = "CREATE TABLE v_everything(seq INTEGER PRIMARY KEY, type TEXT NOT NULL) STRICT;"

        @fold("*")
        def seen(self, event: Event) -> None:
            self.db.execute("INSERT INTO v_everything VALUES (?, ?)", (event.seq, event.type))

    kernel = Kernel.open(folder, clock=clock, extensions=[notes, Extension("every", views=[Everything])])
    result_of(await kernel.submit(kernel.runtime, "note.add", {}))
    result_of(await kernel.submit(kernel.runtime, "note.silence", {}))
    before = dump(folder)

    await kernel.rebuild_all()

    assert dump(folder) == before
    assert [row[1] for row in before["v_everything"]] == ["note.added", "op.completed"]
    kernel.close()
