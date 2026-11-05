"""What every subprocess driver shares, against real processes that misbehave."""

import asyncio
import base64
import contextlib
import json
import os
import signal
import subprocess
import sys
import textwrap
from urllib.parse import quote

import pytest

from platoon_harness.config import Secret
from platoon_harness.drivers import Delta, DriverError, Exited, GapReport, Item, Native, Ready
from platoon_harness.drivers.process import (
    _SH,
    _TRAMPOLINE,
    LOG,
    LOG_LIMIT,
    RECORD,
    Process,
    Record,
    _gone,
    _started,
    reap,
)
from platoon_harness.rpc import read_lines

from .support import Heard, group_of, make_spec, running, spawn_group

pytestmark = pytest.mark.timeout(30)


def lines_into(found: list[bytes], *, then: asyncio.Event | None = None):
    """A reader that keeps each line of stdout."""

    async def read(process: Process) -> None:
        async for line in read_lines(process.stdout):
            found.append(line)
            if then is not None:
                then.set()

    return read


async def drain(process: Process) -> None:
    await process.stdout.read()


async def launch(tmp_path, *command, read=drain, report=None, spec=None, **options) -> Process:
    return await Process.launch(command, spec or make_spec(tmp_path), report or Heard(), read=read, **options)


async def test_the_record_is_on_disk_before_the_harness_runs(tmp_path):
    spec = make_spec(tmp_path)
    found = []
    process = await launch(
        tmp_path, "sh", "-c", f'cat {spec.folder / RECORD}; echo; echo "$$"', read=lines_into(found), spec=spec
    )

    await process.exited()
    await process.stop(1)

    record = json.loads(found[0])
    assert record["pid"] == int(found[1])
    assert record["started"]


def test_a_harness_never_runs_if_its_launcher_dies_before_recording_it(tmp_path):
    marker = tmp_path / "ran"

    done = subprocess.run(
        [_SH, "-c", _TRAMPOLINE, "sh", "touch", str(marker)], stdin=subprocess.DEVNULL, capture_output=True, timeout=10
    )

    assert done.returncode != 0
    assert not marker.exists()


async def test_the_harness_owns_stdin_after_the_release(tmp_path):
    found = []
    process = await launch(tmp_path, "cat", read=lines_into(found))

    process.stdin.write(b"first\nsecond\n")
    process.stdin.close()
    await process.exited()
    await process.stop(1)

    assert found == [b"first", b"second"]


async def test_a_harness_leads_its_own_group(tmp_path):
    spec = make_spec(tmp_path)
    process = await launch(tmp_path, "sleep", "100", spec=spec)
    record = Record.read(spec.folder)

    assert group_of(record.pid) == record.pid != os.getpgrp()
    assert os.getsid(record.pid) == record.pid
    await process.stop(1)


async def test_the_exit_is_reported_after_what_it_wrote_last(tmp_path):
    heard = Heard()

    async def read(process: Process) -> None:
        async for line in read_lines(process.stdout):
            process.put(Item(kind="message", gist=line.decode()))

    process = await launch(tmp_path, "sh", "-c", "echo last; exit 3", read=read, report=heard)
    exited = await heard.until(Exited)
    await process.stop(1)

    assert heard.reports[0].gist == "last"
    assert exited.reason == "exited with code 3"
    assert process.returncode == 3


async def test_a_program_that_is_not_there_is_refused_before_anything_starts(tmp_path):
    with pytest.raises(DriverError, match="no-such-program"):
        await launch(tmp_path, "no-such-program")
    with pytest.raises(DriverError, match="not a directory"):
        await launch(tmp_path, "sh", spec=make_spec(tmp_path, cwd=tmp_path / "missing"))


async def test_a_relative_program_is_found_from_the_cwd(tmp_path):
    script = tmp_path / "agent.sh"
    script.write_text("#!/bin/sh\necho hello\n")
    script.chmod(0o755)
    found = []

    process = await launch(tmp_path, "./agent.sh", read=lines_into(found))
    await process.exited()
    await process.stop(1)

    assert found == [b"hello"]


async def test_stop_asks_by_end_of_stdin_first(tmp_path):
    marker = tmp_path / "asked"
    ready = asyncio.Event()
    script = f"echo ready; cat >/dev/null; touch {marker}"
    process = await launch(tmp_path, "sh", "-c", script, read=lines_into([], then=ready))
    await ready.wait()

    await process.stop(5)

    assert (marker.exists(), process.returncode) == (True, 0)


async def test_stop_ends_a_harness_that_will_not_hear_stdin_with_term_before_kill(tmp_path):
    marker = tmp_path / "termed"
    ready = asyncio.Event()
    script = f"trap 'touch {marker}; exit 0' TERM; echo ready; while :; do sleep 0.01; done"
    process = await launch(tmp_path, "sh", "-c", script, read=lines_into([], then=ready))
    await ready.wait()

    await process.stop(1)

    assert marker.exists()


async def test_a_stop_that_came_to_sigkill_says_so(tmp_path):
    """A tool that leads a group of its own outlives a SIGKILL, and what it does next nobody sees."""
    ready, heard = asyncio.Event(), Heard()
    script = "trap '' TERM; echo ready; while :; do sleep 0.01; done"
    process = await launch(tmp_path, "sh", "-c", script, read=lines_into([], then=ready), report=heard)
    await ready.wait()

    await process.stop(0.05)

    assert GapReport(what="crash_window") in heard.reports


async def test_a_stop_that_term_answered_leaves_no_gap(tmp_path):
    ready, heard = asyncio.Event(), Heard()
    script = "trap 'exit 0' TERM; echo ready; while :; do sleep 0.01; done"
    process = await launch(tmp_path, "sh", "-c", script, read=lines_into([], then=ready), report=heard)
    await ready.wait()

    await process.stop(1)

    assert not [report for report in heard.reports if isinstance(report, GapReport)]


async def test_stop_kills_a_child_that_ignores_term(tmp_path):
    ready = asyncio.Event()
    spec = make_spec(tmp_path)
    script = "trap '' TERM; echo ready; while :; do sleep 0.01; done"
    process = await launch(tmp_path, "sh", "-c", script, read=lines_into([], then=ready), spec=spec)
    record = Record.read(spec.folder)
    await ready.wait()

    await process.stop(0.05)

    assert process.returncode == -signal.SIGKILL
    assert group_of(record.pid) is None
    assert not (spec.folder / RECORD).exists()


async def test_stop_ends_a_forked_child_that_outlives_its_leader(tmp_path):
    heard = Heard()
    found = []
    spec = make_spec(tmp_path)
    process = await launch(
        tmp_path,
        "sh",
        "-c",
        "sleep 100 & echo $!; exit 0",
        read=lines_into(found),
        report=heard,
        spec=spec,
    )
    record = Record.read(spec.folder)

    await heard.until(Exited)
    child = int(found[0])
    assert running(child)
    assert not running(record.pid)
    assert group_of(child) == record.pid

    await process.stop(1)

    assert not running(child)


EXITED_MEMBER = textwrap.dedent(
    """
    import os, sys, time
    if os.fork() == 0:
        member = os.fork()
        if member == 0:
            os._exit(0)
        os.waitid(os.P_PID, member, os.WEXITED | os.WNOWAIT)
        os.setpgid(0, 0)
        print(member, os.getpid(), flush=True)
        time.sleep(100)
        os._exit(0)
    os.execvp(sys.argv[1], sys.argv[1:])
    """
)
"""A group whose member has exited, and whose parent of that member has left the group and never reaps it."""


async def test_a_member_that_has_exited_holds_up_no_stop(tmp_path):
    """A member that has exited stays in its group until its parent reaps it, which a busy reaper can make take seconds,
    and it runs nothing, so a stop neither waits for it nor takes it for something that outlived a signal."""
    ready, heard = asyncio.Event(), Heard()
    found: list[bytes] = []
    command = (sys.executable, "-c", EXITED_MEMBER, "sleep", "100")
    process = await launch(tmp_path, *command, read=lines_into(found, then=ready), report=heard)
    await ready.wait()
    member, parent = map(int, found[0].split())
    assert not running(member) and group_of(member) is not None

    await process.stop(0.05)

    assert process.returncode == -signal.SIGTERM
    assert not [report for report in heard.reports if isinstance(report, GapReport)]
    assert not running(parent)


def test_a_group_left_with_only_an_exited_member_is_gone():
    command = [sys.executable, "-c", EXITED_MEMBER, "true"]
    leader = subprocess.Popen(command, start_new_session=True, stdout=subprocess.PIPE)
    member, parent = map(int, leader.stdout.readline().split())
    leader.wait()
    leader.stdout.close()
    record = Record(pid=leader.pid, started="whatever it was")
    try:
        assert not running(member) and group_of(member) == leader.pid

        assert record.state() == "gone"
    finally:
        os.kill(parent, signal.SIGKILL)


MAIN_THREAD_EXITS = textwrap.dedent(
    """
    import ctypes, signal, threading
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    libc = ctypes.CDLL(None)
    libc.pthread_self.restype = ctypes.c_ulong
    libc.pthread_join.argtypes = (ctypes.c_ulong, ctypes.c_void_p)
    main = libc.pthread_self()

    def outlive():
        libc.pthread_join(main, None)
        print("main exited", flush=True)
        libc.pause()

    threading.Thread(target=outlive).start()
    libc.pthread_exit(None)
    """
)
"""A harness that ignores TERM, whose main thread exits while another runs on."""


async def test_a_harness_whose_main_thread_exited_runs_until_sigkill(tmp_path):
    """Its main thread reads as exited in `/proc` while another runs, so a stop that took that for its end would leave
    it running and say nothing."""
    ready, heard = asyncio.Event(), Heard()
    spec = make_spec(tmp_path)
    command = (sys.executable, "-c", MAIN_THREAD_EXITS)
    process = await launch(tmp_path, *command, read=lines_into([], then=ready), report=heard, spec=spec)
    leader = Record.read(spec.folder).pid
    try:
        await ready.wait()

        await process.stop(0.05)

        assert GapReport(what="crash_window") in heard.reports
        assert group_of(leader) is None
    finally:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(leader, signal.SIGKILL)


async def test_stop_ends_what_left_the_group_by_the_tmpdir_it_inherited(tmp_path):
    found = []
    ready = asyncio.Event()
    script = 'setsid sleep 100 & left=$!; nohup sleep 100 >/dev/null 2>&1 & echo "$left $!"; exec sleep 100'
    process = await launch(tmp_path, "sh", "-c", script, read=lines_into(found, then=ready))
    await ready.wait()

    await process.stop(1)

    assert not [pid for pid in map(int, found[0].split()) if running(pid)]


async def test_what_clears_its_own_environment_escapes_and_nothing_of_a_stranger_s_is_touched(tmp_path):
    stranger = spawn_group("sleep", "100")
    found = []
    ready = asyncio.Event()
    script = "env -i setsid sleep 100 & echo $!; exec sleep 100"
    process = await launch(tmp_path, "sh", "-c", script, read=lines_into(found, then=ready))
    try:
        await ready.wait()

        await process.stop(1)

        assert running(int(found[0]))
        assert running(stranger.pid)
    finally:
        for pid in (int(found[0]), stranger.pid):
            os.kill(pid, signal.SIGKILL)
        stranger.wait()


async def test_reap_ends_what_left_a_group_a_crash_left_behind(tmp_path):
    spec = make_spec(tmp_path)
    found = []
    ready = asyncio.Event()
    process = await launch(
        tmp_path,
        "sh",
        "-c",
        "setsid sleep 100 & echo $!; exec sleep 100",
        read=lines_into(found, then=ready),
        spec=spec,
    )
    await ready.wait()
    record = Record.read(spec.folder)
    assert record is not None
    os.killpg(record.pid, signal.SIGKILL)
    await process.exited()

    assert await reap(spec.folder, 1) == ()

    assert not running(int(found[0]))
    await process.stop(1)


async def test_a_forked_child_holding_stdout_cannot_hold_up_the_exit_report(tmp_path):
    heard = Heard()
    process = await launch(tmp_path, "sh", "-c", "sleep 100 & exit 7", report=heard)

    assert (await heard.until(Exited)).reason == "exited with code 7"
    await process.stop(1)


async def test_a_second_stop_waits_for_the_first(tmp_path):
    process = await launch(tmp_path, "sleep", "100")

    await asyncio.gather(process.stop(1), process.stop(1))
    await process.stop(1)

    assert process.returncode == -signal.SIGTERM


async def test_stop_after_the_exit_signals_nothing(tmp_path):
    heard = Heard()
    process = await launch(tmp_path, "true", report=heard)
    await heard.until(Exited)

    await process.stop(1)

    assert process.returncode == 0


async def test_what_outlives_sigkill_is_refused_loudly(tmp_path, monkeypatch):
    import platoon_harness.drivers.process as module

    process = await launch(tmp_path, "sleep", "100")
    monkeypatch.setattr(module, "_gone", lambda group, within: asyncio.sleep(0, result=False))

    with pytest.raises(DriverError, match="outlived SIGKILL"):
        await process.stop(0)

    monkeypatch.undo()
    process._stopping = None
    await process.stop(1)


async def test_a_reused_pid_is_no_group_of_ours(tmp_path):
    stranger = spawn_group("sleep", "100")
    record = Record(pid=stranger.pid, started="another process altogether")
    record.write(tmp_path)
    try:
        assert record.state() == "gone"

        assert await reap(tmp_path, 1) == ()

        assert stranger.poll() is None
        assert not (tmp_path / RECORD).exists()
    finally:
        stranger.kill()
        stranger.wait()


async def test_a_group_with_its_recorded_leader_is_reaped(tmp_path):
    spec = make_spec(tmp_path)
    process = await launch(tmp_path, "sleep", "100", spec=spec)

    assert await reap(spec.folder, 1) == ()

    assert not (spec.folder / RECORD).exists()
    await process.stop(1)


async def test_two_stops_of_one_group_at_once_each_end_it_and_neither_fails(tmp_path):
    """A shutdown's stop and an agent's own can reap one folder at once: the record the first removes is no failure of
    the second's."""
    spec = make_spec(tmp_path)
    process = await launch(tmp_path, "sleep", "100", spec=spec)

    assert await asyncio.gather(reap(spec.folder, 1), reap(spec.folder, 1)) == [(), ()]

    assert not (spec.folder / RECORD).exists()
    await process.stop(1)


async def test_a_recorded_group_that_is_gone_needs_nothing(tmp_path):
    finished = spawn_group("true")
    finished.wait()
    Record(pid=finished.pid, started="anything").write(tmp_path)

    assert await reap(tmp_path, 1) == ()

    assert not (tmp_path / RECORD).exists()


def leave_a_group_without_its_leader() -> tuple[int, int]:
    leader = subprocess.Popen(
        ["sh", "-c", "sleep 100 & echo $!"], start_new_session=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL
    )
    member = int(leader.stdout.readline())
    leader.wait()
    leader.stdout.close()
    return leader.pid, member


async def test_a_leaderless_group_cannot_be_proved_ours_so_it_is_left_alone_and_named(tmp_path):
    leader, member = await asyncio.to_thread(leave_a_group_without_its_leader)
    record = Record(pid=leader, started="whatever it was")
    record.write(tmp_path)
    try:
        assert record.state() == "unproven"

        assert await reap(tmp_path, 1) == (f"process group {leader} outlived its leader and cannot be proved ours",)

        assert running(member)
        assert (tmp_path / RECORD).exists()
    finally:
        os.killpg(leader, signal.SIGKILL)


async def test_reap_finds_a_wire_program_s_own_record_too(tmp_path):
    finished = spawn_group("true")
    finished.wait()
    inner = tmp_path / "wire"
    inner.mkdir()
    Record(pid=finished.pid, started="anything").write(tmp_path)
    Record(pid=finished.pid, started="anything").write(inner)

    await reap(tmp_path, 1)

    assert not (inner / RECORD).exists()


async def test_reap_reads_no_record_a_harness_left_in_its_own_tmp(tmp_path):
    stranger = spawn_group("sleep", "100")
    planted = tmp_path / "tmp"
    planted.mkdir()
    started = _started(stranger.pid)
    assert started is not None
    Record(pid=stranger.pid, started=started).write(planted)
    try:
        assert await reap(tmp_path, 1) == ()

        assert stranger.poll() is None
    finally:
        stranger.kill()
        stranger.wait()


@pytest.mark.parametrize("record", [b"", b"not json", b'{"pid": "seven"}'])
async def test_a_record_that_cannot_be_read_is_named_and_stops_nothing(tmp_path, record):
    (tmp_path / RECORD).write_bytes(record)

    assert await reap(tmp_path, 1) == (f"{RECORD} cannot be read",)
    assert not (tmp_path / RECORD).exists()


async def test_a_pipe_drains_while_nobody_takes_the_reports(tmp_path):
    release = asyncio.Event()
    taken = []
    seen = 0
    all_read = asyncio.Event()

    async def blocked(report) -> None:
        await release.wait()
        taken.append(report)

    async def read(process: Process) -> None:
        nonlocal seen
        async for line in read_lines(process.stdout):
            process.put(Item(kind="message", gist=line.decode()))
            seen += 1
            if seen == 1000:
                all_read.set()

    process = await launch(tmp_path, "seq", "1000", read=read, report=blocked)

    await all_read.wait()
    release.set()
    await process.exited()
    await process.stop(1)

    assert len([report for report in taken if isinstance(report, Item)]) == 1000


async def test_a_quota_breach_stops_the_agent_with_a_gap(tmp_path):
    release = asyncio.Event()
    heard = Heard()
    spec = make_spec(tmp_path)

    async def blocked(report) -> None:
        await release.wait()
        await heard(report)

    async def read(process: Process) -> None:
        async for line in read_lines(process.stdout):
            process.put(Item(kind="message", gist=line.decode()))
            if process.returncode is not None:
                release.set()

    process = await launch(tmp_path, "yes", read=read, report=blocked, quota=8 * 1024, spec=spec)
    await process.exited()
    release.set()
    native = await heard.until(Native)
    await heard.until(Exited)
    await process.stop(1)

    assert native.raw == "reports passed their quota"
    assert [gap.what for gap in heard.of(GapReport)] == ["stream_lost"]
    assert len(heard.of(Exited)) == 1
    assert not (spec.folder / RECORD).exists()


async def test_a_delta_past_the_quota_is_dropped_and_stops_nothing(tmp_path):
    release = asyncio.Event()
    taken = []

    async def blocked(report) -> None:
        await release.wait()
        taken.append(report)

    async def read(process: Process) -> None:
        async for line in read_lines(process.stdout):
            process.put(Delta(text=line.decode()))

    process = await launch(tmp_path, "seq", "1000", read=read, report=blocked, quota=8 * 1024)

    await process.exited()
    release.set()
    await process.stop(1)

    assert process.returncode == 0
    assert 0 < len([report for report in taken if isinstance(report, Delta)]) < 1000
    assert [report for report in taken if isinstance(report, GapReport)] == []


async def test_a_reader_that_crashes_stops_the_agent_with_a_gap(tmp_path):
    heard = Heard()
    spec = make_spec(tmp_path)

    async def read(process: Process) -> None:
        async for _ in read_lines(process.stdout, limit=8):
            pass

    process = await launch(tmp_path, "sh", "-c", "echo a long line; sleep 100", read=read, report=heard, spec=spec)

    assert "a line passed 8 bytes" in (await heard.until(Native)).raw
    await heard.until(GapReport, lambda gap: gap.what == "stream_lost")
    await heard.until(Exited)
    await process.stop(1)
    assert process.returncode == -signal.SIGTERM


async def test_a_reporter_that_fails_stops_the_agent(tmp_path):
    async def broken(report) -> None:
        raise RuntimeError("the journal has closed")

    async def read(process: Process) -> None:
        process.put(Item(kind="message", gist="hello"))
        await drain(process)

    spec = make_spec(tmp_path)
    process = await launch(tmp_path, "sleep", "100", read=read, report=broken, spec=spec)
    record = Record.read(spec.folder)

    await process.stop(1)

    assert group_of(record.pid) is None


async def test_stderr_goes_to_a_log_and_never_to_a_report(tmp_path):
    heard = Heard()
    spec = make_spec(tmp_path)
    process = await launch(tmp_path, "sh", "-c", "echo oops >&2", report=heard, spec=spec)

    await heard.until(Exited)
    await process.stop(1)

    assert (spec.folder / LOG).read_bytes() == b"oops\n"
    assert (spec.folder / LOG).stat().st_mode & 0o777 == 0o600
    assert heard.of(Item) == [] and heard.of(Native) == []


async def test_the_log_stays_bounded_and_keeps_the_newest(tmp_path):
    spec = make_spec(tmp_path)
    script = "import sys\nfor i in range(40): sys.stderr.write(f'{i:04} ' * 40_000)\nsys.stderr.write('the end')"
    heard = Heard()
    process = await launch(tmp_path, sys.executable, "-I", "-c", script, report=heard, spec=spec)

    await heard.until(Exited)
    await process.stop(1)

    log, older = spec.folder / LOG, spec.folder / f"{LOG}.1"
    assert log.stat().st_size <= LOG_LIMIT and older.stat().st_size <= LOG_LIMIT
    assert log.read_bytes().endswith(b"the end")


@pytest.mark.skipif(not os.path.exists("/dev/full"), reason="needs a device that is always full")
async def test_a_full_disk_cannot_stall_a_harness_through_its_log(tmp_path):
    spec = make_spec(tmp_path)
    spec.folder.mkdir(parents=True)
    (spec.folder / LOG).symlink_to("/dev/full")
    heard = Heard()
    script = "import sys\nsys.stderr.write('x' * 1_000_000)"

    process = await launch(tmp_path, sys.executable, "-I", "-c", script, report=heard, spec=spec)

    assert (await heard.until(Exited)).reason == "exited with code 0"
    await process.stop(1)


async def test_a_log_that_cannot_open_leaves_no_harness(tmp_path):
    spec = make_spec(tmp_path)
    (spec.folder / LOG).mkdir(parents=True)
    marker = tmp_path / "ran"

    with pytest.raises(IsADirectoryError):
        await launch(tmp_path, "touch", str(marker), spec=spec)

    assert not marker.exists()
    assert not (spec.folder / RECORD).exists()


SECRET = "s3cret/value+with=specials"


@pytest.mark.parametrize(
    "form",
    [
        SECRET,
        quote(SECRET, safe=""),
        base64.b64encode(SECRET.encode()).decode(),
        base64.urlsafe_b64encode(SECRET.encode()).decode().rstrip("="),
        json.dumps({"key": SECRET}),
    ],
)
async def test_no_credential_reaches_the_log_in_any_form(tmp_path, form):
    spec = make_spec(tmp_path, access={"API_KEY": Secret(SECRET)})
    heard = Heard()
    process = await launch(tmp_path, "sh", "-c", f"printf '%s' '{form}' >&2", report=heard, spec=spec)

    await heard.until(Exited)
    await process.stop(1)

    log = (spec.folder / LOG).read_text()
    assert "***" in log
    assert form not in log


async def test_a_credential_split_across_two_writes_is_still_masked(tmp_path):
    spec = make_spec(tmp_path, access={"API_KEY": Secret(SECRET)})
    heard = Heard()
    first, second = SECRET[:9], SECRET[9:]
    script = (
        f"import sys,time\nsys.stderr.write({first!r});sys.stderr.flush();time.sleep(.05);sys.stderr.write({second!r})"
    )
    process = await launch(tmp_path, sys.executable, "-I", "-c", script, report=heard, spec=spec)

    await heard.until(Exited)
    await process.stop(1)

    assert (spec.folder / LOG).read_text() == "***"


async def test_a_quota_counts_what_a_list_in_a_report_holds(tmp_path):
    heard = Heard()
    wide = Ready(tools_visible=("x" * 4096,) * 8)

    async def read(process: Process) -> None:
        process.put(wide)
        await drain(process)

    process = await launch(tmp_path, "true", read=read, report=heard, quota=16 * 1024)

    await heard.until(GapReport)
    await process.stop(1)

    assert heard.of(Ready) == []


LEFT_BEHIND = textwrap.dedent(
    """
    import asyncio, sys, tempfile
    from pathlib import Path

    from platoon_harness.drivers import AgentSpec
    from platoon_harness.drivers.process import Process

    folder = Path(sys.argv[1])

    async def report(_):
        pass

    async def read(process):
        print(process_pid(folder), flush=True)
        await process.stdout.read()

    def process_pid(folder):
        import json
        return json.loads((folder / "proc.json").read_text())["pid"]

    async def main():
        spec = AgentSpec(agent="a", role="r", cwd=folder, folder=folder)
        await Process.launch(["sleep", "100"], spec, report, read=read)
        await asyncio.sleep(0)

    {ending}
    """
)


@pytest.mark.parametrize(
    "ending",
    [
        "asyncio.run(main())",
        "loop = asyncio.new_event_loop(); loop.run_until_complete(main()); loop.close()",
        "loop = asyncio.new_event_loop(); loop.run_until_complete(main()); sys.exit(0)",
    ],
    ids=["asyncio_run", "closed_by_hand", "left_open"],
)
def test_a_closed_loop_leaves_no_process_behind(tmp_path, ending):
    program = tmp_path / "program.py"
    program.write_text(LEFT_BEHIND.replace("{ending}", ending))

    done = subprocess.run(
        [sys.executable, str(program), str(tmp_path)], capture_output=True, text=True, timeout=20, check=False
    )

    record = Record.read(tmp_path)
    assert record is not None
    assert asyncio.run(_gone(record.pid, 10.0))  # A signal sent as an interpreter exits lands a moment later.
    assert record.state() == "gone"
    assert 'drivers/process.py", line' not in done.stderr, done.stderr
    assert done.stderr == "" or ending != "asyncio.run(main())", done.stderr
