"""Loading extensions: collisions refused, naming law checked, core on the same contract."""

import pytest
from pydantic import BaseModel, ConfigDict

from platoon_harness.kernel import Args, Daemon, Event, Extension, Kernel, Principal, Refused, Txn, View, fold, op
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

    assert {"alpha.note", "beta.note", "effect.start", "ops.list"} <= set(kernel.ops)
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


@pytest.mark.parametrize("name", ["effect", "timer", "principal", "grant", "body", "runtime", "op", "ops"])
def test_core_names_are_taken(folder, clock, name):
    assert refused_at_load(folder, clock, Extension(name)) == "conflict"


def test_core_views_are_taken(folder, clock):
    assert refused_at_load(folder, clock, Extension("x", views=[type("Effects", (View,), {})])) == "conflict"


def test_only_the_listed_core_names_are_taken(folder, clock):
    load(folder, clock, Extension("command"), Extension("stamp")).close()


def test_two_views_cannot_share_a_table(folder, clock):
    class Task(View):
        schema = "CREATE TABLE v_task(n INTEGER) STRICT; CREATE TABLE v_task_log(n INTEGER) STRICT;"

    class TaskLog(View):
        name = "task_log"
        schema = "CREATE TABLE v_task_log(n INTEGER) STRICT;"

    code = refused_at_load(folder, clock, Extension("a", views=[Task]), Extension("b", views=[TaskLog]))
    assert code == "conflict"


def test_a_view_cannot_take_the_kernels_table(folder, clock):
    class Folds(View):
        schema = "CREATE TABLE v_folds(n INTEGER) STRICT;"

    assert refused_at_load(folder, clock, Extension("a", views=[Folds])) == "conflict"


def test_daemon_collisions_are_refused_at_load(folder, clock):
    async def run(kernel: Kernel) -> None:
        return None

    daemon = Daemon("twin", run)
    assert (
        refused_at_load(folder, clock, Extension("a", daemons=[daemon]), Extension("b", daemons=[daemon])) == "conflict"
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
    class Loose(BaseModel):
        text: str = ""

    class Open(Args):
        model_config = ConfigDict(extra="ignore")

    @op("alpha.note")
    def typed(txn: Txn, a: Args) -> None:
        """Typed."""

    def plain(txn: Txn, a: dict) -> None:
        """Takes a dict."""

    def loose(txn: Txn, a: Loose) -> None:
        """Takes any model."""

    def opened(txn: Txn, a: Open) -> None:
        """Ignores what it does not know."""

    def bare(txn, a) -> None:
        """Takes anything."""

    assert typed.input is Args
    for fn in (plain, loose, opened, bare):
        with pytest.raises(TypeError, match="must take Args"):
            op("alpha.note")(fn)


def test_an_op_is_a_query_or_an_exposed_read_but_not_both():
    def fn(txn: Txn, a: Args) -> None:
        """Read."""

    with pytest.raises(TypeError, match="both"):
        op("alpha.read", query=True, exposes=True)(fn)


def test_a_tool_needs_a_description():
    def fn(txn: Txn, a: Args) -> None:
        pass

    with pytest.raises(TypeError, match="description"):
        op("alpha.note", tool=True)(fn)


async def test_an_op_on_no_object_is_about_the_session(folder, clock):
    kernel = load(folder, clock, Extension("alpha", ops=[make_op("alpha.note")]))
    await kernel.submit(kernel.runtime, "principal.add", {"id": "human:ada"})
    outcome = await kernel.submit(Principal(id="human:ada"), "alpha.note", {})
    assert outcome.refusal is not None
    assert outcome.refusal.object == "session"
    kernel.close()
