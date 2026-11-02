"""check_extension: a third party's extension held to what a core primitive keeps to."""

import textwrap

from pydantic import Field

from platoon_harness.kernel import Args, Event, Extension, Kernel, Txn, View, fold, op
from platoon_harness.testing import check_extension


class Cast(Args):
    choice: str = Field(description="What you vote for.")


class Bare(Args):
    choice: str


@op("ballot.cast", tool=True)
def cast(txn: Txn, a: Cast) -> None:
    """Cast a vote. Refused `conflict` when you have voted."""
    txn.emit("ballot.voted", "ballot/one", gist=a.choice, data={"choice": a.choice})


@op("ballot.spoil", tool=True)
def undescribed(txn: Txn, a: Bare) -> None:
    """Spoil your vote. See `ballot.nowhere`."""


class Votes(View):
    schema = "CREATE TABLE v_votes(choice TEXT PRIMARY KEY, n INTEGER NOT NULL) WITHOUT ROWID, STRICT;"

    @fold("ballot.voted")
    def counted(self, event: Event) -> None:
        self.db.execute(
            "INSERT INTO v_votes VALUES (?, 1) ON CONFLICT DO UPDATE SET n = n + 1", (event.data["choice"],)
        )


class Drifting(View):
    """A fold that depends on what it should not: its count of calls survives a rebuild."""

    schema = "CREATE TABLE v_drifting(n INTEGER PRIMARY KEY) STRICT;"
    calls = 0

    @fold("ballot.voted")
    def counted(self, event: Event) -> None:
        type(self).calls += 1
        self.db.execute("INSERT INTO v_drifting VALUES (?)", (type(self).calls,))


async def vote(kernel: Kernel) -> None:
    for choice in ("a", "b", "a"):
        outcome = await kernel.submit(kernel.runtime, "ballot.cast", {"choice": choice})
        assert outcome.refusal is None


def states(result) -> dict[str, str]:
    return {check.name: check.state for check in result.checks}


async def test_a_good_extension_passes_every_check(tmp_path):
    good = Extension("ballot", ops=[cast], views=[Votes])

    result = await check_extension(good, folder=tmp_path / "s", scenario=vote)

    assert states(result) == dict.fromkeys(
        ("names", "naming_law", "schemas", "descriptions", "public_api_only", "rebuild_equals_live"), "passed"
    )


async def test_no_scenario_is_a_skip_with_a_reason(tmp_path):
    result = await check_extension(Extension("ballot", ops=[cast]), folder=tmp_path / "s")

    assert result.get("rebuild_equals_live").state == "skipped"
    assert "no scenario" in result.get("rebuild_equals_live").reason


async def test_a_name_a_primitive_holds_is_refused(tmp_path):
    result = await check_extension(Extension("agent", ops=[]), folder=tmp_path / "s")

    assert result.get("names").state == "failed"
    assert "agent" in result.get("names").reason


async def test_an_op_outside_its_namespace_breaks_the_naming_law(tmp_path):
    result = await check_extension(Extension("poll", ops=[cast]), folder=tmp_path / "s")

    assert result.get("naming_law").state == "failed"
    assert "outside namespace" in result.get("naming_law").reason


async def test_every_failure_comes_at_once(tmp_path):
    result = await check_extension(Extension("ballot", ops=[undescribed]), folder=tmp_path / "s")

    assert result.get("schemas").reason == "ballot.spoil does not describe choice"
    assert result.get("descriptions").reason == (
        "ballot.spoil does not say what a refusal means; ballot.spoil names ballot.nowhere, which is not an op"
    )


async def test_a_view_that_differs_from_its_rebuild_fails(tmp_path):
    Drifting.calls = 0

    result = await check_extension(
        Extension("ballot", ops=[cast], views=[Drifting]), folder=tmp_path / "s", scenario=vote
    )

    assert result.get("rebuild_equals_live").reason == "v_drifting differs after a rebuild"


async def test_a_private_kernel_name_fails(tmp_path, monkeypatch):
    source = tmp_path / "rude.py"
    source.write_text(
        textwrap.dedent(
            """
            from platoon_harness.kernel.txn import Stamps
            from platoon_harness.kernel import Args, Txn, op, Sneaky

            class Nothing(Args):
                pass

            @op("rude.poke")
            def poke(txn: Txn, a: Nothing) -> None:
                txn._db.execute("SELECT 1")
            """
        )
    )
    code = compile(source.read_text().replace(", Sneaky", ""), str(source), "exec")
    namespace = {"__name__": "rude"}
    exec(code, namespace)

    result = await check_extension(Extension("rude", ops=[namespace["poke"]]), folder=tmp_path / "s")

    reason = result.get("public_api_only").reason
    assert "rude.py reaches _db" in reason
    assert "reaches into platoon_harness.kernel.txn" in reason
    assert "imports Sneaky" in reason
