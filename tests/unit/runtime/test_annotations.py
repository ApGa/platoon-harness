"""Annotations: what an estimator says of the record, beside the journal and never in it (RFC 0011)."""

import asyncio
import contextlib
import inspect
import sqlite3

import pytest

from platoon_harness import Refused, Session, annotations
from platoon_harness.annotations import ANNOTATIONS

from .support import in_state, solo

pytestmark = pytest.mark.timeout(30)

CREDIT = {"kind": "credit", "producer": "even-split", "producer_version": "1", "scope": "local"}


async def test_an_estimator_writes_credit_beside_a_live_session_and_a_closed_one(tmp_path):
    async with Session.start(solo(), name="s", root=tmp_path) as session:
        await in_state(session, "bob", "idle")
        head = await session.head()
        live = await session.annotate("agent/bob@1", status="scored", value=0.5, head_seq=head, **CREDIT)

    async with Session.attach("s", root=tmp_path) as history:
        head = await history.head()
        later = {**CREDIT, "producer_version": "2"}
        closed = await history.annotate(
            "agent/bob@1", status="scored", value=1, head_seq=head, evidence=["session@1"], **later
        )
        found = await history.annotations("agent/bob@1")

        assert await history.head() == head
        assert [(row.id, row.producer_version, row.value) for row in found] == [
            (live.id, "1", 0.5),
            (closed.id, "2", 1.0),
        ]
        assert closed.evidence == ("session@1",) and closed.head_seq == head
        assert await history.annotations("session@1") == []


async def test_a_reward_row_has_one_of_five_statuses_and_a_value_only_when_scored(tmp_path):
    """No statement at all is what unscored is, so no status says it, and none but `scored` is ever zero."""
    async with Session.start(solo(), name="s", root=tmp_path) as session:
        await in_state(session, "bob", "idle")
        head = await session.head()

        written = [
            await session.annotate(
                "agent/bob@1",
                status=status,
                value=1.0 if status == "scored" else None,
                head_seq=head,
                **{**CREDIT, "producer": status},
            )
            for status in ("scored", "invalid", "error", "timeout", "cancelled")
        ]
        with pytest.raises(Refused) as unscored:
            await session.annotate("agent/bob@1", status="unscored", head_seq=head, **{**CREDIT, "producer": "z"})
        with pytest.raises(Refused) as valued:
            await session.annotate(
                "agent/bob@1", status="error", value=0.0, head_seq=head, **{**CREDIT, "producer": "x"}
            )
        with pytest.raises(Refused) as missing:
            await session.annotate("agent/bob@1", status="scored", head_seq=head, **{**CREDIT, "producer": "y"})

    assert [(row.status, row.value) for row in written] == [
        ("scored", 1.0),
        ("invalid", None),
        ("error", None),
        ("timeout", None),
        ("cancelled", None),
    ]
    assert valued.value.refusal.code == missing.value.refusal.code == unscored.value.refusal.code == "invalid"
    assert "`scored`, and only then" in str(valued.value.refusal.detail)


async def test_a_second_estimator_writes_beside_the_first_and_a_change_is_refused(tmp_path):
    async with Session.start(solo(), name="s", root=tmp_path) as session:
        await in_state(session, "bob", "idle")
        head = await session.head()
        first = await session.annotate("agent/bob@1", status="scored", value=0.25, head_seq=head, **CREDIT)

        again = await session.annotate("agent/bob@1", status="scored", value=0.25, head_seq=head, **CREDIT)
        other = {**CREDIT, "params": {"temperature": 0}}
        beside = await session.annotate("agent/bob@1", status="scored", value=0.75, head_seq=head, **other)
        with pytest.raises(Refused) as changed:
            await session.annotate("agent/bob@1", status="scored", value=0.5, head_seq=head, **CREDIT)

        assert again == first and beside.id != first.id and beside.params_hash != first.params_hash
        assert changed.value.refusal.code == "conflict" and f"annotation {first.id}" in str(
            changed.value.refusal.detail
        )
        assert len(await session.annotations()) == 2


async def test_an_annotation_is_about_events_of_the_trace_it_read(tmp_path):
    async with Session.start(solo(), name="s", root=tmp_path) as session:
        await in_state(session, "bob", "idle")
        spawned = await session.head()
        later = (await session.send("@bob", "later"))["ref"]
        head = await session.head()

        refusals = []
        for target, head_seq in (
            ("nothing@1", head),
            (later, spawned),
            ("agent/bob@1#L1-2", head),
            ("agent/bob@1", head + 9),
        ):
            with pytest.raises(Refused) as refused:
                await session.annotate(target, status="invalid", head_seq=head_seq, **CREDIT)
            refusals.append(refused.value.refusal.code)

        assert refusals == ["not_found", "invalid", "invalid", "invalid"]
        assert not (session.folder / ANNOTATIONS).exists()


async def test_a_view_credential_writes_no_annotation_and_reading_writes_nothing(tmp_path):
    async with Session.start(solo(), name="s", root=tmp_path) as session:
        await in_state(session, "bob", "idle")
        async with Session.attach("s", root=tmp_path, view=True) as viewer:
            with pytest.raises(Refused) as refused:
                await viewer.annotate("agent/bob@1", status="invalid", head_seq=1, **CREDIT)
            assert await viewer.annotations() == []

        assert refused.value.refusal.code == "not_permitted"
        assert not (session.folder / ANNOTATIONS).exists()


async def test_estimators_writing_one_statement_at_once_write_it_once(tmp_path):
    """Each holds the file from its look for the key to its write, so none finds free a key another is filling."""
    async with Session.start(solo(), name="s", root=tmp_path) as session:
        await in_state(session, "bob", "idle")
        head = await session.head()

        written = await asyncio.gather(
            *(session.annotate("agent/bob@1", status="invalid", head_seq=head, **CREDIT) for _ in range(16))
        )

        assert len({found.id for found in written}) == 1 and len(await session.annotations()) == 1


def test_annotations_have_one_checked_way_in():
    """`Session.annotate` checks a statement against the journal, and the module beside it is a schema, no writer."""
    defined = [
        value for value in vars(annotations).values() if getattr(value, "__module__", "") == annotations.__name__
    ]

    assert annotations.__all__ == ["ANNOTATIONS", "Annotate", "Annotation", "Status"]
    assert not [value for value in defined if inspect.isfunction(value)]


async def test_annotations_are_found_by_target_and_never_hold_up_a_writer(tmp_path):
    async with Session.start(solo(), name="s", root=tmp_path) as session:
        await in_state(session, "bob", "idle")
        await session.annotate("agent/bob@1", status="invalid", head_seq=await session.head(), **CREDIT)
        with contextlib.closing(sqlite3.connect(session.folder / ANNOTATIONS)) as db:
            mode = db.execute("PRAGMA journal_mode").fetchone()[0]
            plan = db.execute(
                "EXPLAIN QUERY PLAN SELECT * FROM annotations WHERE target = ? ORDER BY id", ("agent/bob@1",)
            ).fetchall()

    assert mode == "wal"
    assert "USING INDEX annotations_target (target=?)" in plan[0][3]
