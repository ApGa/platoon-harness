"""The same flow through a detached runtime and guests on the control socket: the mode the TUI and `serve` use."""

import asyncio
import fcntl
import os
import signal
from pathlib import Path

import pytest

from platoon_harness import Refused, Session
from platoon_harness.kernel import is_held
from platoon_harness.runtime.opening import prepare
from platoon_harness.runtime.paths import MANIFEST, read_running
from platoon_harness.schema import ConfigError

from ..unit.drivers.support import running
from ..unit.runtime.support import SECONDS, in_state, of_type, rebuilt_equals_live, until
from .scripts import inside, manager_worker, wire

pytestmark = pytest.mark.timeout(90)


@pytest.fixture(autouse=True)
def importable(monkeypatch: pytest.MonkeyPatch) -> None:
    """A detached runtime is another process, and it must find the harnesses these tests name."""
    monkeypatch.setenv("PYTHONPATH", str(Path(__file__).parents[2]))


async def exited(pid: int) -> None:
    """Wait for a process to end. The lock goes a moment before the interpreter does."""
    descriptor = os.pidfd_open(pid)
    loop = asyncio.get_running_loop()
    ended = asyncio.Event()
    loop.add_reader(descriptor, ended.set)
    try:
        await asyncio.wait_for(ended.wait(), SECONDS)
    finally:
        loop.remove_reader(descriptor)
        os.close(descriptor)


def team(worker: str = "worker"):
    return manager_worker(inside("lead"), inside(worker))


async def gone(session: Session) -> None:
    """Wait until a detached runtime has let go of its session, which is an flock only that can release."""
    fd = os.open(session.folder / "lock", os.O_RDONLY)
    try:
        await asyncio.wait_for(asyncio.to_thread(fcntl.flock, fd, fcntl.LOCK_SH), SECONDS)
    finally:
        os.close(fd)


async def test_a_detached_runtime_runs_the_whole_flow_for_a_guest(tmp_path: Path):
    wired = manager_worker(wire("lead"), wire("worker"))
    guest = await Session.start(wired, name="fix-auth", root=tmp_path, detach=True)
    found = read_running(guest.folder)

    assert not guest.owner
    assert found is not None and found.pid != os.getpid()
    assert is_held(guest.folder)
    assert (guest.folder / "runtime.log").exists()

    await guest.send("@lead", "Fix the flaky test")
    ending = await guest.settled(timeout="30s")

    assert (ending.state, ending.reason) == ("closing", "settled")
    assert {row["status"] for row in ending.agents} == {"finished"}
    assert (await guest.read())["entries"][0]["gist"] == "The test is fixed."
    await gone(guest)
    assert not (guest.folder / "runtime.json").exists()
    await exited(found.pid)
    await guest.leave()
    await rebuilt_equals_live(guest.folder)


async def test_a_human_message_and_an_approval_resolved_by_one_of_two_racing_guests(tmp_path: Path):
    first = await Session.start(team("asking"), name="s", root=tmp_path, detach=True)
    second = await Session.attach("s", root=tmp_path)

    await first.send("@lead", "Fix the flaky test")
    settling = asyncio.ensure_future(first.settled(timeout="45s"))

    for _ in range(2):
        pending = await until(first.approvals, first)
        asked = pending[0]
        races = await asyncio.gather(
            first.resolve(asked["id"], "allow", expected_version=asked["version"], via="tui"),
            second.resolve(asked["id"], "allow", expected_version=asked["version"], via="web"),
            return_exceptions=True,
        )
        won = [race for race in races if isinstance(race, dict)]
        lost = [race for race in races if isinstance(race, Refused)]

        assert len(won) == 1 and len(lost) == 1
        assert lost[0].refusal.code == "conflict"
        assert lost[0].refusal.detail["resolved_by"] == "human:you"
        assert lost[0].refusal.detail["via"] in ("tui", "web")

    ending = await asyncio.wait_for(settling, 45)

    assert ending.reason == "settled"
    assert len(await of_type(second, "approval.resolved")) == 2
    await first.leave()
    await second.leave()


async def test_a_guest_that_disconnects_changes_nothing(tmp_path: Path):
    owner = await Session.start(team("hanging"), name="s", root=tmp_path, detach=True)
    await owner.send("@lead", "Fix the flaky test")
    await until(lambda: of_type(owner, "task.claimed"), owner)
    guest = await Session.attach("s", root=tmp_path)
    before = [event.seq async for event in guest.events()]
    found = read_running(guest.folder)
    assert found is not None

    await guest.leave()

    assert [event.seq async for event in owner.events()][: len(before)] == before
    assert is_held(owner.folder) and running(found.pid)
    await owner.cancel()
    ending = await owner.settled(timeout="30s")
    assert ending.reason == "cancelled"
    await gone(owner)
    await owner.leave()


async def test_sigterm_runs_the_owner_s_shutdown(tmp_path: Path):
    guest = await Session.start(team("hanging"), name="s", root=tmp_path, detach=True)
    await guest.send("@lead", "Fix the flaky test")
    await until(lambda: of_type(guest, "task.claimed"), guest)
    await in_state(guest, "w1", "running")
    found = read_running(guest.folder)
    assert found is not None

    os.kill(found.pid, signal.SIGTERM)
    await gone(guest)

    assert not (guest.folder / "runtime.json").exists()
    assert list(guest.folder.rglob("proc.json")) == []
    assert (await guest.status())["state"] == "stopped"
    types = [event.type async for event in guest.events()]
    assert types[-1] == "session.stopped"
    assert "turn.lost" not in types
    await guest.leave()


async def test_attach_to_a_closed_session_reads_history_and_writes_nothing(tmp_path: Path):
    guest = await Session.start(team(), name="s", root=tmp_path, detach=True)
    await guest.send("@lead", "Fix the flaky test")
    await guest.settled(timeout="30s")
    await gone(guest)
    await guest.leave()
    journal = guest.folder / "journal.sqlite"
    before = journal.read_bytes(), journal.stat().st_mtime_ns

    async with Session.attach("s", root=tmp_path) as history:
        assert (await history.status())["state"] == "closing"
        assert [row["status"] for row in await history.agents()] == ["finished"] * 3
        assert (await history.query("notes"))["total"] == 2
        outcome = await history.submit("message.send", to="@you", gist="too late")

    assert outcome.refusal is not None and "platoon-harness resume s" in str(outcome.refusal.detail)
    assert (journal.read_bytes(), journal.stat().st_mtime_ns) == before
    assert not is_held(guest.folder)


async def test_a_program_that_cannot_describe_itself_is_refused_before_any_cost(tmp_path: Path):
    silent = {"command": ["/bin/sh", "-c", "exit 1"], "mode": "wire"}

    with pytest.raises(ConfigError, match="did not describe itself"):
        await Session.start(manager_worker(silent, wire("worker")), root=tmp_path, detach=True)


async def test_a_detached_runtime_that_cannot_start_says_why(tmp_path: Path):
    folder = await asyncio.to_thread(prepare, team(), name="s", root=tmp_path)
    (folder / MANIFEST).write_text("not a manifest")

    with pytest.raises(Refused) as refused:
        await Session.resume("s", root=tmp_path, detach=True)

    assert "did not start" in str(refused.value)
