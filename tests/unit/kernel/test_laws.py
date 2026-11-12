"""Architecture section 3: each law the kernel can answer for, under its own name."""

import ast
import asyncio
import re
import sqlite3
import sys
from pathlib import Path

import pytest
from pydantic import Field, TypeAdapter, ValidationError, create_model

from platoon_harness import kernel as kernel_package
from platoon_harness.kernel import Args, Event, Extension, Kernel, Refused, Txn, View, fold, op
from platoon_harness.primitives import Exposure
from platoon_harness.testing.extension import private_reaches

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
    for statement in (
        "UPDATE events SET gist = 'edited'",
        "DELETE FROM events",
        "INSERT OR REPLACE INTO events SELECT * FROM events WHERE seq = 1",
    ):
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


@pytest.mark.parametrize("field", ["actor", "role", "session", "token"])
def test_no_tool_schema_claims_an_identity(field):
    declared = create_model("Spoof", __base__=Args, **{field: (str, ...)})
    aliased = create_model("Aliased", __base__=Args, name=(str, Field(alias=field)))

    def tool(txn: Txn, a: Args) -> None:
        """Claim to be someone."""

    for spoof in (declared, aliased):
        tool.__annotations__["a"] = spoof
        with pytest.raises(TypeError, match="identity"):
            op("note.spoof", tool=True)(tool)
        assert op("note.spoof", runtime=True)(tool).input is spoof


class _Who(Args):
    principal: str


class _Nested(Args):
    who: _Who


class _Listed(Args):
    who: tuple[_Who, ...] = ()


class _Renamed(Args):
    role: str = Field(alias="r")


@pytest.mark.parametrize("spoof", [_Nested, _Listed, _Renamed])
def test_no_tool_schema_hides_an_identity(spoof):
    def tool(txn: Txn, a: Args) -> None:
        """Claim to be someone."""

    tool.__annotations__["a"] = spoof
    with pytest.raises(TypeError, match="identity"):
        op("note.spoof", tool=True)(tool)


@pytest.mark.parametrize(
    "field", ["Actor", "actor_id", "sessionId", "api_token", "agent_id", "caller_role", "on_behalf_of", "user"]
)
def test_the_usual_spellings_of_an_identity_are_refused(field):
    def tool(txn: Txn, a: Args) -> None:
        """Claim to be someone."""

    tool.__annotations__["a"] = create_model("Near", __base__=Args, **{field: (str, ...)})
    with pytest.raises(TypeError, match="identity"):
        op("note.spoof", tool=True)(tool)


async def test_identity_comes_from_a_credential(kernel):
    await enroll(kernel, ALICE)
    await grant(kernel, "agent:alice")
    refused = await kernel.submit(ALICE, "note.add", {"text": "hi", "agent": "bob"})

    assert refusal_of(refused) == "invalid"
    assert "agent" in str(refused.refusal.detail)
    journaled = events_of(kernel)[-1]
    assert journaled.type == "op.refused"
    assert journaled.actor == "agent:alice"
    assert journaled.outcome.refusal.code == "invalid"


async def test_a_spoof_on_a_query_can_be_journaled(kernel):
    await enroll(kernel, ALICE)
    await grant(kernel, "agent:alice")
    head = kernel.head
    spoof = {"actor": "human:ada"}
    assert refusal_of(kernel.query(ALICE, "note.list", spoof)) == "invalid"
    assert kernel.head == head

    assert refusal_of(await kernel.submit(ALICE, "note.list", spoof)) == "invalid"

    journaled = events_of(kernel)[-1]
    assert (journaled.type, journaled.actor) == ("op.refused", "agent:alice")


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


async def test_absence_stays_honest(kernel):
    effect = result_of(await kernel.submit(kernel.runtime, "note.dispatch", {}))

    event = events_of(kernel)[0]

    unknown = (event.agent, event.turn, event.context_version, event.episode, event.correlation, event.model)
    assert unknown == (None, None, None, None, None, None)
    listed = result_of(kernel.query(kernel.runtime, "effect.ready", {}))
    assert [(row["id"], row["timeout"], row["agent"]) for row in listed] == [(effect, None, None)]
    answers = TypeAdapter(Exposure).json_schema()["discriminator"]["mapping"]
    assert set(answers) == {"seen", "not_seen", "unknown"}
    with pytest.raises(ValidationError):
        TypeAdapter(Exposure).validate_python(False)


def test_nothing_has_a_private_api():
    kernel_folder = Path(kernel_package.__file__).parent
    for name in ("auth", "bodies", "effects", "timers", "core"):
        path = kernel_folder / f"{name}.py"
        assert private_reaches(ast.parse(path.read_text())) == [], path.name

    code = sorted(Path(__file__).parents[3].glob("packages/*/src/**/*.py"))
    assert code, "packages/*/src/**/*.py matches nothing"
    for path in code:
        if kernel_folder in path.parents:
            continue
        tree = ast.parse(path.read_text())
        assert private_reaches(tree) == [], path.name
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("platoon_harness.kernel"):
                assert node.module == "platoon_harness.kernel", f"{path.name} reaches into {node.module}"
                assert {alias.name for alias in node.names} <= set(kernel_package.__all__), path.name


def test_nothing_claims_mid_generation():
    """Every doc, the root's Markdown and the packages' code; the law's own words and the rule in AGENTS.md that
    carries it out are no claim."""
    root = Path(__file__).parents[3]
    not_claims = re.compile(r'Nothing claims mid-generation|Never say "exactly once" or "mid-generation"\.')
    texts = []
    for pattern in ("packages/*/src/**/*.py", "*.md", "docs/**/*.md"):
        found = sorted(root.glob(pattern))
        assert found, f"{pattern} matches nothing"
        texts += found
    claims = [
        f"{path.relative_to(root)}: {line}"
        for path in texts
        for line in path.read_text().splitlines()
        if "mid-generation" in not_claims.sub("", line).lower()
    ]
    assert claims == []


def test_the_kernel_imports_only_the_standard_library_and_pydantic():
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
