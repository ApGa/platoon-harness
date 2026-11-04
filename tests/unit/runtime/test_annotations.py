"""Annotations: what an estimator says of the record, beside the journal and never in it (ADR 0011)."""

import asyncio

import pytest

from platoon_harness import Refused, Session
from platoon_harness.annotations import ANNOTATIONS, Annotate, annotate, annotations

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


async def test_unscored_is_never_zero(tmp_path):
    async with Session.start(solo(), name="s", root=tmp_path) as session:
        await in_state(session, "bob", "idle")
        head = await session.head()

        unscored = await session.annotate("agent/bob@1", status="unscored", head_seq=head, **CREDIT)
        with pytest.raises(Refused) as valued:
            await session.annotate(
                "agent/bob@1", status="error", value=0.0, head_seq=head, **{**CREDIT, "producer": "x"}
            )
        with pytest.raises(Refused) as missing:
            await session.annotate("agent/bob@1", status="scored", head_seq=head, **{**CREDIT, "producer": "y"})

    assert unscored.value is None and unscored.status == "unscored"
    assert valued.value.refusal.code == missing.value.refusal.code == "invalid"
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
                await session.annotate(target, status="unscored", head_seq=head_seq, **CREDIT)
            refusals.append(refused.value.refusal.code)

        assert refusals == ["not_found", "invalid", "invalid", "invalid"]
        assert not (session.folder / ANNOTATIONS).exists()


async def test_a_view_credential_writes_no_annotation_and_reading_writes_nothing(tmp_path):
    async with Session.start(solo(), name="s", root=tmp_path) as session:
        await in_state(session, "bob", "idle")
        async with Session.attach("s", root=tmp_path, view=True) as viewer:
            with pytest.raises(Refused) as refused:
                await viewer.annotate("agent/bob@1", status="unscored", head_seq=1, **CREDIT)
            assert await viewer.annotations() == []

        assert refused.value.refusal.code == "not_permitted"
        assert not (session.folder / ANNOTATIONS).exists()


async def test_estimators_writing_one_statement_at_once_write_it_once(tmp_path):
    """Each holds the file from its look for the key to its write, so none finds free a key another is filling."""
    statement = Annotate(target="agent/bob@1", status="unscored", head_seq=1, **CREDIT)  # type: ignore[arg-type]

    written = await asyncio.gather(*(asyncio.to_thread(annotate, tmp_path, statement, float(n)) for n in range(16)))

    assert len({found.id for found in written}) == 1 and len(annotations(tmp_path)) == 1
