"""SIGKILL: what was acked survives, and what was half done never happened."""

import signal
import subprocess
import sys
from pathlib import Path
from textwrap import dedent

from platoon_harness.kernel import Args, Extension, Kernel, Txn, op

from .support import dump, events_of

WORKER = dedent(
    """
    import asyncio
    import os
    import signal
    import sys

    from platoon_harness.kernel import Args, Extension, Kernel, Txn, op


    class Step(Args):
        n: int
        die: bool = False


    @op("crash.step", on=lambda a: f"crash/{a.n}")
    def step(txn: Txn, a: Step) -> None:
        txn.emit("crash.stepped", f"crash/{a.n}", gist="first half", data={"n": a.n})
        if a.die:
            os.kill(os.getpid(), signal.SIGKILL)
        txn.emit("crash.stepped", f"crash/{a.n}", gist="second half", data={"n": a.n})


    async def main() -> None:
        kernel = Kernel.open(sys.argv[1], extensions=[Extension("crash", ops=[step])])
        mode = sys.argv[2]
        n = 0
        while mode == "forever" or n < 8:
            batch = range(n, n + 4)
            outcomes = await asyncio.gather(*(kernel.submit(kernel.runtime, "crash.step", {"n": i}) for i in batch))
            print(*(i for i, o in zip(batch, outcomes) if o.refusal is None), flush=True)
            n += 4
        die = n + 2
        args = [{"n": i, "die": i == die} for i in range(n, n + 6)]
        await asyncio.gather(*(kernel.submit(kernel.runtime, "crash.step", a) for a in args))


    asyncio.run(main())
    """
)


class Step(Args):
    n: int
    die: bool = False


@op("crash.step")
def step(txn: Txn, a: Step) -> None:
    """Stand in for the worker's op on reopening."""


crash = Extension("crash", ops=[step])


def worker(tmp_path: Path, folder: Path, mode: str) -> subprocess.Popen[str]:
    script = tmp_path / "worker.py"
    script.write_text(WORKER)
    return subprocess.Popen(
        [sys.executable, str(script), str(folder), mode], stdout=subprocess.PIPE, text=True, cwd=tmp_path
    )


async def verify(folder: Path, acked: set[int]) -> dict[int, int]:
    """Reopen after the kill. Return how many events each command left."""
    kernel = Kernel.open(folder, extensions=[crash])
    halves: dict[int, int] = {}
    for event in events_of(kernel):
        if event.type == "crash.stepped":
            halves[event.data["n"]] = halves.get(event.data["n"], 0) + 1
    assert acked <= set(halves)
    assert set(halves.values()) == {2}
    before = dump(folder)
    await kernel.rebuild_all()
    assert dump(folder) == before
    kernel.close()
    return halves


async def test_a_kill_inside_an_op_leaves_no_trace_of_it(tmp_path, folder):
    process = worker(tmp_path, folder, "finite")
    output, _ = process.communicate(timeout=60)

    assert process.returncode == -signal.SIGKILL
    acked = {int(token) for token in output.split()}
    assert acked == set(range(8))
    halves = await verify(folder, acked)
    assert 10 not in halves


async def test_a_kill_from_outside_loses_no_ack(tmp_path, folder):
    process = worker(tmp_path, folder, "forever")
    assert process.stdout is not None
    acked = set()
    while len(acked) < 40:
        acked |= {int(token) for token in process.stdout.readline().split()}
    process.kill()
    process.wait(timeout=60)
    process.stdout.close()

    await verify(folder, acked)
