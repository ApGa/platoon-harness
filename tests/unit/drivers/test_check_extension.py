"""check_extension: a third party's extension held to what a core primitive keeps to."""

import importlib
import textwrap

import pytest
from pydantic import Field

from platoon_harness.bwrap import extension as bwrap
from platoon_harness.kernel import Args, Daemon, Event, Extension, Kernel, Refused, Txn, View, fold, op
from platoon_harness.testing import check_extension
from platoon_harness.topology import Topology


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


async def test_the_result_names_each_declared_part_no_check_covers(tmp_path):
    """No check runs a daemon, a preset or an isolation, so beside checks that all pass each is named, saying what
    that leaves unknown, in the result and in what it prints. An extension that declares none has nothing unchecked."""

    async def tick(kernel: Kernel) -> None:
        """Touch the world, which no check sees."""

    def pair(author: str, reviewer: str) -> Topology:
        return Topology(edges={author: [f"role:{reviewer}"]})

    class Fence:
        """An isolation that confines nothing."""

    parts = {"daemons": [Daemon("tick", tick)], "presets": [pair], "isolation": Fence()}
    declared = Extension("ballot", ops=[cast], views=[Votes], **parts)

    result = await check_extension(declared, folder=tmp_path / "declared", scenario=vote)
    plain = await check_extension(Extension("ballot", ops=[cast], views=[Votes]), folder=tmp_path / "plain")

    assert result.failed == ()
    assert result.unchecked == (
        "daemon tick: no check runs it, so nothing here says what it does or which effects it performs",
        "preset pair: no check runs it, so nothing here says the topology it returns is valid",
        "isolation Fence: no check runs it, so nothing here says it confines",
    )
    assert str(result).splitlines()[-3:] == [f"unchecked {part}" for part in result.unchecked]
    assert plain.unchecked == ()


async def test_bwrap_s_result_says_its_confinement_is_unchecked(tmp_path):
    """The SDK's `bwrap` passes every check that runs, and its result says that none says it confines."""
    result = await check_extension(bwrap, folder=tmp_path / "s")

    assert result.failed == ()
    assert result.unchecked == ("isolation Bubblewrap: no check runs it, so nothing here says it confines",)


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


async def test_two_extensions_cannot_claim_one_tool_name(tmp_path):
    @op("task_claim.now", tool=True)
    def now(txn: Txn, a: Args) -> None:
        """Claim. Refused never."""

    @op("task.claim_now", tool=True)
    def same(txn: Txn, a: Args) -> None:
        """Claim. Refused never."""

    with pytest.raises(Refused, match="task_claim_now is defined by both"):
        Kernel.open(tmp_path / "both", extensions=[Extension("task_claim", ops=[now]), Extension("task", ops=[same])])


@pytest.mark.parametrize("name", ["`ballot.no_such_op`", "`ballot.v2`", "`ballot_tally.count.all`"])
async def test_a_description_naming_an_op_with_an_underscore_or_a_digit_that_is_not_there_fails(tmp_path, name):
    @op("ballot.say", tool=True)
    def say(txn: Txn, a: Args) -> None:
        """Say a name. Refused never."""

    say.fn.__doc__ = f"See {name}. Refused never."

    result = await check_extension(Extension("ballot", ops=[say]), folder=tmp_path / "session")

    assert states(result)["descriptions"] == "failed"


async def test_a_description_is_free_to_name_an_argument(tmp_path):
    @op("ballot.say", tool=True)
    def say(txn: Txn, a: Args) -> None:
        """Pass `choice`, or see `session.status`. Refused never."""

    result = await check_extension(Extension("ballot", ops=[say]), folder=tmp_path / "session")

    assert states(result)["descriptions"] == "passed"


async def test_a_plain_import_of_a_kernel_module_fails(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(tmp_path)
    (tmp_path / "plain_import.py").write_text(
        textwrap.dedent(
            """
            import platoon_harness.kernel.journal
            from platoon_harness.kernel import Args, Txn, op

            @op("plain.go", tool=True)
            def go(txn: Txn, a: Args) -> None:
                \"\"\"Go. Refused never.\"\"\"
            """
        )
    )
    extension = Extension("plain", ops=[importlib.import_module("plain_import").go])

    result = await check_extension(extension, folder=tmp_path / "session")

    assert states(result)["public_api_only"] == "failed"
    assert "platoon_harness.kernel.journal" in result.get("public_api_only").reason
