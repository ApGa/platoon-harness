"""Loading extensions: collisions refused, naming law checked, core on the same contract."""

import pytest

from platoon_harness.kernel import Args, Daemon, Event, Extension, Kernel, Refused, Txn, View, fold, op
from platoon_harness.kernel.core import CORE

from .support import refused_code, result_of


def make_op(name: str):
    def fn(txn: Txn, a: Args) -> None:
        """A generic op."""
        txn.emit("alpha.noted", "alpha/a", gist=name)

    return op(name)(fn)


class Alpha(View):
    schema = "CREATE TABLE v_alpha(seq INTEGER PRIMARY KEY) STRICT;"

    @fold("alpha.noted")
    def noted(self, event: Event) -> None:
        self.db.execute("INSERT INTO v_alpha VALUES (?)", (event.seq,))


def load(folder, clock, *extensions) -> Kernel:
    return Kernel.open(folder, clock=clock, extensions=extensions)


def refused_at_load(folder, clock, *extensions) -> str:
    with pytest.raises(Refused) as error:
        load(folder, clock, *extensions)
    return refused_code(error)


async def test_ops_and_views_load_from_several_extensions(folder, clock):
    class Beta(View):
        schema = "CREATE TABLE v_beta(seq INTEGER) STRICT;"

    kernel = load(
        folder,
        clock,
        Extension("alpha", ops=[make_op("alpha.note")], views=[Alpha]),
        Extension("beta", ops=[make_op("beta.note")], views=[Beta]),
    )

    result_of(await kernel.submit(kernel.runtime, "alpha.note", {}))
    result_of(await kernel.submit(kernel.runtime, "beta.note", {}))

    assert kernel._db.execute("SELECT count(*) FROM v_alpha").fetchone()[0] == 2
    assert {"alpha.note", "beta.note", "effect.start"} <= set(kernel.ops)
    assert kernel.extensions[-1].name == "beta"
    kernel.close()


def test_op_collisions_are_refused_at_load(folder, clock):
    code = refused_at_load(folder, clock, Extension("alpha", ops=[make_op("alpha.note"), make_op("alpha.note")]))
    assert code == "conflict"


def test_view_collisions_are_refused_at_load(folder, clock):
    class Other(View):
        name = "alpha"
        schema = "CREATE TABLE v_alpha(n INTEGER) STRICT;"

    assert (
        refused_at_load(folder, clock, Extension("alpha", views=[Alpha]), Extension("beta", views=[Other]))
        == "conflict"
    )


def test_extension_collisions_are_refused_at_load(folder, clock):
    assert refused_at_load(folder, clock, Extension("alpha"), Extension("alpha")) == "conflict"


def test_core_names_are_taken(folder, clock):
    assert refused_at_load(folder, clock, Extension("effect")) == "conflict"
    assert refused_at_load(folder, clock, Extension("x", views=[type("Effects", (View,), {})])) == "conflict"


def test_daemon_and_component_collisions_are_refused_at_load(folder, clock):
    async def run(kernel: Kernel) -> None:
        return None

    daemon = Daemon("twin", run)
    assert (
        refused_at_load(folder, clock, Extension("a", daemons=[daemon]), Extension("b", daemons=[daemon])) == "conflict"
    )
    presets = {"mesh": object()}
    assert (
        refused_at_load(folder, clock, Extension("a", presets=presets), Extension("b", presets=presets)) == "conflict"
    )


def test_an_op_must_live_in_its_extensions_namespace(folder, clock):
    assert refused_at_load(folder, clock, Extension("alpha", ops=[make_op("beta.note")])) == "invalid"


@pytest.mark.parametrize("name", ["alpha.noted", "alpha.sent", "alpha.deep.claimed"])
def test_ops_are_imperative(folder, clock, name):
    assert refused_at_load(folder, clock, Extension("alpha", ops=[make_op(name)])) == "invalid"


@pytest.mark.parametrize("name", ["alpha.embed", "alpha.read", "alpha.set", "alpha"])
def test_imperatives_that_look_past_are_allowed(folder, clock, name):
    load(folder, clock, Extension("alpha", ops=[make_op(name)])).close()


@pytest.mark.parametrize("event_type", ["alpha.note", "noted", "alpha.embed"])
def test_folded_events_are_past_tense(folder, clock, event_type):
    bad = type(
        "Bad",
        (View,),
        {"schema": "CREATE TABLE v_bad(n INTEGER) STRICT;", "seen": fold(event_type)(lambda self, event: None)},
    )
    assert refused_at_load(folder, clock, Extension("alpha", views=[bad])) == "invalid"


def test_core_obeys_the_same_law():
    assert all(operation.name.startswith(extension.name) for extension in CORE for operation in extension.ops)
    assert not any(operation.tool for extension in CORE for operation in extension.ops)


def test_an_op_needs_typed_args():
    @op("alpha.note")
    def typed(txn: Txn, a: Args) -> None:
        """Typed."""

    assert typed.input is Args
