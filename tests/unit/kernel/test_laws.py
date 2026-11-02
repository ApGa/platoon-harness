"""Architecture section 3: each law the kernel can answer for, under its own name."""

import ast
import asyncio
import sqlite3
import sys
from pathlib import Path

import pytest

from platoon_harness import kernel as kernel_package
from platoon_harness.kernel import Args, Event, Extension, Kernel, Refused, Txn, View, fold, op

from .support import (
    ALICE,
    HUMAN,
    dump,
    enroll,
    events_of,
    grant,
    notes,
    refusal_of,
    refused_code,
    result_of,
)


async def test_the_journal_is_the_only_truth(kernel, folder):
    await enroll(kernel, HUMAN)
    await grant(kernel, "human:ada")
    result_of(await kernel.submit(HUMAN, "note.add", {"text": "one"}))
    result_of(await kernel.submit(HUMAN, "note.dispatch", {"timeout": 5}))
    before = dump(folder)

    await kernel.rebuild_all()

    assert dump(folder) == before
    db = sqlite3.connect(folder / "journal.sqlite")
    for statement in ("UPDATE events SET gist = 'edited'", "DELETE FROM events"):
        with pytest.raises(sqlite3.IntegrityError, match="events are immutable"):
            db.execute(statement)
    db.close()


async def test_folds_are_pure(folder, clock):
    class Nosy(View):
        schema = "CREATE TABLE v_nosy(n INTEGER) STRICT;"

        @fold("note.added")
        def added(self, event: Event) -> None:
            self.db.execute("SELECT count(*) FROM v_principals")

    kernel = Kernel.open(folder, clock=clock, extensions=[notes])
    result_of(await kernel.submit(kernel.runtime, "note.add", {}))
    kernel.close()
    assert "emit" not in vars(View)
    with pytest.raises(sqlite3.DatabaseError, match="not authorized"):
        Kernel.open(folder, clock=clock, extensions=[notes, Extension("nosy", views=[Nosy])])


def test_operations_cannot_wait_on_the_world():
    with pytest.raises(TypeError, match="cannot wait on the world"):

        @op("note.wait")
        async def waits(txn: Txn, a: Args) -> None:
            """Wait."""

    with pytest.raises(TypeError, match="cannot wait on the world"):

        @op("note.stream")
        def streams(txn: Txn, a: Args):
            """Yield."""
            yield None


async def test_ack_follows_commit(kernel, gate):
    head = kernel.head
    held = asyncio.create_task(kernel.submit(kernel.runtime, "gate.hold", {}))
    await gate.wait_entered()
    second = asyncio.create_task(kernel.submit(kernel.runtime, "note.add", {}))
    await asyncio.sleep(0)

    assert not held.done() and not second.done()
    assert events_of(kernel, after=head) == []

    gate.release.set()
    first = await held
    assert first.seq is not None
    assert events_of(kernel, after=head)[0].seq == first.seq
    await second


async def test_replay_executes_nothing(kernel, folder):
    called = []

    @op("spy.run")
    def run(txn: Txn, a: Args) -> None:
        """Count."""
        called.append(1)
        txn.effect("deliver", {})

    spied = Kernel.open(folder / "other", clock=kernel.clock, extensions=[Extension("spy", ops=[run])])
    result_of(await spied.submit(spied.runtime, "spy.run", {}))
    head = spied.head

    await spied.rebuild_all()

    assert called == [1]
    assert spied.head == head
    assert [e.type for e in events_of(spied) if e.type.startswith("effect.")] == ["effect.requested"]
    spied.close()


async def test_identity_comes_from_a_credential(kernel):
    with pytest.raises(TypeError, match="identity"):

        class Spoof(Args):
            actor: str

    await enroll(kernel, ALICE)
    await grant(kernel, "agent:alice")
    refused = await kernel.submit(ALICE, "note.add", {"text": "hi", "agent": "bob"})

    assert refusal_of(refused) == "invalid"
    assert "agent" in str(refused.refusal.detail)
    journaled = events_of(kernel)[-1]
    assert journaled.type == "op.refused"
    assert journaled.actor == "agent:alice"
    assert journaled.outcome.refusal.code == "invalid"


async def test_references_point_backward(kernel):
    await enroll(kernel, HUMAN)
    await grant(kernel, "human:ada")
    first = result_of(await kernel.submit(HUMAN, "note.add", {}))

    assert result_of(await kernel.submit(HUMAN, "note.add", {"cause": [first["seq"]]}))
    assert result_of(await kernel.submit(HUMAN, "note.add", {"based_on": ["note/a@1"], "refs": ["note/a@2#L1-2"]}))
    head = kernel.head
    for args in ({"cause": [head + 1]}, {"cause": [0]}, {"based_on": ["note/a@99"]}, {"refs": ["note/b@1"]}):
        assert refusal_of(await kernel.submit(HUMAN, "note.add", args)) == "not_found"
    assert refusal_of(await kernel.submit(HUMAN, "note.add", {"refs": ["not a ref"]})) == "invalid"


async def test_observers_cost_nothing(kernel):
    follower = kernel.follow(kernel.runtime, after=0)
    result_of(await kernel.submit(kernel.runtime, "note.add", {}))
    first = await anext(aiter(follower))

    results = await asyncio.gather(*(kernel.submit(kernel.runtime, "note.add", {}) for _ in range(100)))

    assert all(outcome.refusal is None for outcome in results)
    assert not kernel._pulse._waiters
    caught_up = await anext(aiter(follower))
    assert caught_up.events[-1].seq == kernel.head
    assert first.events[0].seq == 1
    await follower.aclose()


async def test_agent_reads_are_evidence_human_reads_are_nothing(kernel):
    await enroll(kernel, ALICE)
    await enroll(kernel, HUMAN)
    await grant(kernel, "all")
    result_of(await kernel.submit(HUMAN, "note.add", {"text": "secret"}))
    head = kernel.head

    assert result_of(await kernel.submit(HUMAN, "note.read", {})) == ["secret"]
    assert result_of(kernel.query(HUMAN, "note.read", {})) == ["secret"]
    assert kernel.head == head

    assert result_of(await kernel.submit(ALICE, "note.read", {})) == ["secret"]
    assert [e.type for e in events_of(kernel, after=head)] == ["note.offered"]
    assert refusal_of(kernel.query(ALICE, "note.read", {})) == "unsupported"
    with pytest.raises(Refused) as error:
        kernel.read(ALICE, after=0)
    assert refused_code(error) == "not_permitted"


def test_nothing_has_a_private_api():
    allowed = set(sys.stdlib_module_names) | {"pydantic"}
    for path in Path(kernel_package.__file__).parent.glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Import):
                roots = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                assert node.level <= 1, f"{path.name} reaches outside the kernel"
                roots = [(node.module or "").split(".")[0]] if node.level == 0 else []
            else:
                continue
            assert set(roots) <= allowed, f"{path.name} imports {roots}"
