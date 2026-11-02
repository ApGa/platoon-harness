"""Property tests: the kernel's promises over generated command sequences."""

import asyncio
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from platoon_harness.kernel import Kernel, ManualClock

from .support import dump, events_of, notes

STREAMS = st.sampled_from(["note/a", "note/b", "note/c"])
KEYS = st.sampled_from([None, "k1", "k2", "k3"])

note = st.fixed_dictionaries(
    {},
    optional={
        "stream": STREAMS,
        "text": st.text(max_size=8),
        "copies": st.integers(1, 3),
        "fail": st.booleans(),
        "cause": st.lists(st.integers(-1, 40), max_size=2),
        "based_on": st.lists(st.builds("{}@{}".format, STREAMS, st.integers(0, 12)), max_size=2),
        "refs": st.lists(st.builds("{}@{}#L1".format, STREAMS, st.integers(0, 12)), max_size=2),
    },
)
commands = st.lists(
    st.one_of(
        st.tuples(st.just("note.add"), note, KEYS),
        st.tuples(st.just("note.silence"), st.just({}), KEYS),
        st.tuples(st.just("note.nope"), st.just({}), KEYS),
        st.tuples(st.just("note.add"), st.just({"undeclared": 1}), KEYS),
        st.tuples(st.just("note.dispatch"), st.fixed_dictionaries({"timeout": st.sampled_from([None, 5.0])}), KEYS),
        st.tuples(
            st.just("note.remind"), st.fixed_dictionaries({"due": st.just(1.0), "key": st.sampled_from("xy")}), KEYS
        ),
        st.tuples(st.just("effect.start"), st.fixed_dictionaries({"id": st.integers(1, 12)}), KEYS),
        st.tuples(
            st.just("effect.finish"),
            st.fixed_dictionaries({"id": st.integers(1, 12), "attempt": st.integers(1, 2)}),
            KEYS,
        ),
        st.tuples(
            st.just("grant.add"),
            st.fixed_dictionaries({"who": st.sampled_from(["all", "role:x"]), "ops": st.just("*")}),
            KEYS,
        ),
        st.tuples(st.just("runtime.start"), st.just({}), KEYS),
    ),
    max_size=24,
)


def scenario(folder: Path, body: Any) -> Any:
    """Run `body` against a fresh kernel and always close it."""

    async def run() -> Any:
        kernel = Kernel.open(folder, clock=ManualClock(1000.0), extensions=[notes])
        try:
            return await body(kernel)
        finally:
            kernel.close()

    return asyncio.run(run())


async def replay(kernel: Kernel, script: list[tuple[str, dict[str, Any], str | None]]) -> list[Any]:
    return [await kernel.submit(kernel.runtime, name, args, key=key) for name, args, key in script]


quick = settings(max_examples=30, deadline=None)


@quick
@given(script=commands)
def test_rebuild_equals_live(tmp_path_factory: pytest.TempPathFactory, script) -> None:
    folder = tmp_path_factory.mktemp("rebuild") / "session"

    async def body(kernel: Kernel) -> None:
        await replay(kernel, script)
        before = dump(folder)
        await kernel.rebuild_all()
        assert dump(folder) == before

    scenario(folder, body)


@quick
@given(script=commands)
def test_idempotent_retry(tmp_path_factory: pytest.TempPathFactory, script) -> None:
    folder = tmp_path_factory.mktemp("retry") / "session"

    async def body(kernel: Kernel) -> None:
        first = {}
        for (name, args, key), outcome in zip(script, await replay(kernel, script), strict=True):
            if key is not None and outcome.refusal is not None and outcome.refusal.code == "key_reused":
                continue
            if key is not None:
                first.setdefault(key, (name, args, outcome))
        head = kernel.head
        for key, (name, args, outcome) in first.items():
            assert await kernel.submit(kernel.runtime, name, args, key=key) == outcome
        assert kernel.head == head

    scenario(folder, body)


@quick
@given(script=commands)
def test_gapless_stream_versions(tmp_path_factory: pytest.TempPathFactory, script) -> None:
    folder = tmp_path_factory.mktemp("gapless") / "session"

    async def body(kernel: Kernel) -> None:
        await replay(kernel, script)
        events = events_of(kernel)
        assert [event.seq for event in events] == list(range(1, len(events) + 1))
        streams: dict[str, list[int]] = {}
        for event in events:
            streams.setdefault(event.stream, []).append(event.version)
        for versions in streams.values():
            assert versions == list(range(1, len(versions) + 1))

    scenario(folder, body)


@quick
@given(script=commands)
def test_every_reference_points_backward(tmp_path_factory: pytest.TempPathFactory, script) -> None:
    folder = tmp_path_factory.mktemp("backward") / "session"

    async def body(kernel: Kernel) -> None:
        await replay(kernel, script)
        seen = {}
        for event in events_of(kernel):
            assert all(0 < cause < event.seq for cause in event.cause)
            for ref in event.based_on:
                stream, _, version = ref.partition("@")
                assert seen[stream, int(version)] < event.seq
            seen[event.stream, event.version] = event.seq

    scenario(folder, body)


@quick
@given(script=commands)
def test_every_command_ends_on_exactly_one_outcome(tmp_path_factory: pytest.TempPathFactory, script) -> None:
    folder = tmp_path_factory.mktemp("outcome") / "session"

    async def body(kernel: Kernel) -> None:
        outcomes = await replay(kernel, script)
        fresh = {outcome.seq for outcome in outcomes}
        carrying = {event.seq for event in events_of(kernel) if event.outcome is not None}
        assert carrying == fresh

    scenario(folder, body)
