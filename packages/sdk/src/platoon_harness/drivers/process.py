"""What every subprocess driver shares: a process group recorded before exec, with pipes that always drain."""

import asyncio
import contextlib
import errno
import json
import os
import shutil
import signal
import stat
import subprocess
import sys
import weakref
from asyncio.subprocess import PIPE, SubprocessStreamProtocol
from collections import deque
from collections.abc import Callable, Coroutine, Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any, Literal, Self

from platoon_harness.kernel import GIST_LIMIT, Clock, first
from platoon_harness.primitives import Delta, Exited, GapReport, Native, Report
from platoon_harness.schema import Model

from . import RAW_LIMIT, SHORT_LIMIT, AgentSpec, DriverError, Reporter, unknown_frame
from .env import Held, Redactor, harness_env, open_beneath, secrets_of, tmpdir

RECORD = "proc.json"
LOG = "stderr.log"
WIRE = "wire"
LOG_LIMIT = 1024 * 1024
REPORT_QUOTA = 64 * 1024 * 1024

_SH = "/bin/sh"
_TRAMPOLINE = 'read -r go && exec "$@"'
_BUFFER = 256 * 1024
_CHUNK = 64 * 1024
_REPORT_FLOOR = 1024
_FLUSH = 0.5
_VERIFY = 5.0
_LOST_GRACE = 1.0
_STATUS_SECONDS = 5.0

GroupState = Literal["ours", "gone", "unproven"]
Reader = Callable[["Process"], Coroutine[Any, Any, None]]

__all__ = [
    "LOG",
    "LOG_LIMIT",
    "RECORD",
    "REPORT_QUOTA",
    "WIRE",
    "GroupState",
    "Process",
    "Reader",
    "Record",
    "clean",
    "exit_reason",
    "reap",
    "run",
    "status",
]


def _boot_id() -> str:
    return Path("/proc/sys/kernel/random/boot_id").read_text().strip()


def _started(pid: int) -> str | None:
    """What tells this process from any other that ever held its pid, or None if nothing holds it. It survives exec."""
    if sys.platform == "linux":
        try:
            stat = Path(f"/proc/{pid}/stat").read_bytes()
        except (FileNotFoundError, ProcessLookupError):
            return None
        return f"{_boot_id()}:{stat.rpartition(b')')[2].split()[19].decode()}"
    found = subprocess.run(["ps", "-o", "lstart=", "-p", str(pid)], capture_output=True, text=True, check=False)
    return found.stdout.strip() or None


def _occupied(group: int) -> bool:
    """Whether a group has a member, counting one that has exited and that its parent has not reaped yet."""
    try:
        os.killpg(group, 0)
    except (ProcessLookupError, PermissionError):
        return False
    return True


def _running(group: int) -> bool:
    """Whether anything in a group still runs. A member that has exited stays in its group until its parent reaps it,
    which a busy reaper can make take seconds, so on Linux it is not counted. A process whose main thread has exited
    reads as exited too while its other threads run, so one with a thread left counts. Elsewhere every member does."""
    if not _occupied(group):
        return False
    if sys.platform != "linux":
        return True
    me = os.getuid()
    with os.scandir("/proc") as entries:
        for entry in entries:
            try:
                if not entry.name.isdecimal() or entry.stat(follow_symlinks=False).st_uid != me:
                    continue
                state, _, pgrp = Path(entry.path, "stat").read_bytes().rpartition(b")")[2].split()[:3]
                if int(pgrp) == group and (state not in (b"Z", b"X") or len(os.listdir(Path(entry.path, "task"))) > 1):
                    return True
            except (OSError, ValueError):
                continue
    return False


def _signal(group: int, signum: signal.Signals) -> None:
    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.killpg(group, signum)


class Record(Model):
    """A process group, written down before its leader could exec, so that no harness can exist unrecorded."""

    pid: int
    started: str

    @classmethod
    def of(cls, pid: int) -> Self | None:
        """The record of the process that holds `pid` now, or None when none does."""
        started = _started(pid)
        return None if started is None else cls(pid=pid, started=started)

    def write(self, folder: Path) -> None:
        """Replace the record in one step, on disk before this returns, following no symlink a confined agent could
        plant in its folder."""
        scratch = folder / f"{RECORD}.tmp"
        with os.fdopen(open_beneath(folder, scratch, os.O_WRONLY | os.O_CREAT | os.O_TRUNC), "w") as file:
            json.dump(self.model_dump(), file)
            file.flush()
            os.fsync(file.fileno())
        scratch.replace(folder / RECORD)
        descriptor = os.open(folder, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    @classmethod
    def read(cls, folder: Path) -> Self | None:
        try:
            fd = open_beneath(folder, folder / RECORD, os.O_RDONLY)
        except FileNotFoundError:
            return None
        with os.fdopen(fd, "rb") as file:
            return cls.model_validate_json(file.read())

    def state(self) -> GroupState:
        """Whether this group is still ours. A leader with the recorded start time proves it, and one without shows the
        pid was reused, so nothing of ours is left. With the leader gone and members alive it stays `unproven`: a group
        keeps its id only while it has members, so those may belong to a stranger that reused the pid and exited too."""
        started = _started(self.pid)
        if started is not None:
            return "ours" if started == self.started else "gone"
        return "unproven" if _running(self.pid) else "gone"


async def _gone(group: int, within: float) -> bool:
    """Whether nothing in a group runs by `within`. Looking at what runs costs a scan of every process, so it waits
    while the group has members, and looks once at the end."""
    loop = asyncio.get_running_loop()
    deadline, delay = loop.time() + within, 0.001
    while _occupied(group):
        if loop.time() >= deadline:
            return not _running(group)
        await asyncio.sleep(delay)
        delay = min(delay * 2, 0.05)
    return True


async def _termed(group: int, grace: float) -> bool:
    """Ask a whole group to end, and say whether it did."""
    _signal(group, signal.SIGTERM)
    return await _gone(group, grace)


async def _killed(group: int) -> None:
    _signal(group, signal.SIGKILL)
    if not await _gone(group, _VERIFY):
        raise DriverError(f"process group {group} outlived SIGKILL")


async def _end(group: int, grace: float) -> None:
    """End a whole group: TERM, wait, KILL, then verify."""
    if not await _termed(group, grace):
        await _killed(group)


def _marked(folders: Iterable[Path]) -> list[int]:
    """Pidfds of this user's processes whose environment holds the `TMPDIR` of one of `folders`, which only what a
    harness started inherits, whichever group it left for. Each is opened before it is looked at, so a pid reused since
    signals nobody. Only Linux lets one process read another's environment, and what clears its own is not found."""
    if sys.platform != "linux":
        return []
    markers = {f"TMPDIR={tmpdir(folder)}".encode() for folder in folders}
    found, me = [], os.getuid()
    with os.scandir("/proc") as entries:
        for entry in entries:
            try:
                if not entry.name.isdecimal() or entry.stat(follow_symlinks=False).st_uid != me:
                    continue
                pidfd = os.pidfd_open(int(entry.name))
            except OSError:
                continue
            try:
                held = not markers.isdisjoint(Path(entry.path, "environ").read_bytes().split(b"\0"))
            except OSError:
                held = False
            if held:
                found.append(pidfd)
            else:
                os.close(pidfd)
    return found


async def _end_marked(folders: Iterable[Path], grace: float) -> None:
    """End what a harness left running outside its group: TERM, wait, then KILL. A pidfd can be read once its process
    has exited, which is how this waits."""
    pidfds = _marked(folders)
    loop = asyncio.get_running_loop()
    exits = []
    for pidfd in pidfds:
        exited = loop.create_future()
        loop.add_reader(pidfd, lambda pidfd=pidfd, exited=exited: _note(loop, pidfd, exited))
        exits.append(exited)
        with contextlib.suppress(ProcessLookupError):
            signal.pidfd_send_signal(pidfd, signal.SIGTERM)
    try:
        if exits:
            _, staying = await asyncio.wait(exits, timeout=grace)
            for pidfd, exited in zip(pidfds, exits, strict=True):
                if exited in staying:
                    with contextlib.suppress(ProcessLookupError):
                        signal.pidfd_send_signal(pidfd, signal.SIGKILL)
            if staying:
                await asyncio.wait(staying, timeout=_VERIFY)
    finally:
        for pidfd in pidfds:
            loop.remove_reader(pidfd)
            os.close(pidfd)


def _note(loop: asyncio.AbstractEventLoop, pidfd: int, exited: asyncio.Future[None]) -> None:
    loop.remove_reader(pidfd)
    if not exited.done():
        exited.set_result(None)


def _unlink_beneath(folder: Path, path: Path) -> None:
    """Remove `path` beneath `folder`, following no symlink an agent could plant: a symlink at the name is removed, not
    what it points to, and a symlink where a folder should be is removed in its place."""
    *parts, name = path.relative_to(folder).parts
    dir_fd = os.open(folder, os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in parts:
            try:
                step = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=dir_fd)
            except OSError:
                with contextlib.suppress(OSError):
                    os.unlink(part, dir_fd=dir_fd)
                return
            os.close(dir_fd)
            dir_fd = step
        with contextlib.suppress(FileNotFoundError):
            os.unlink(name, dir_fd=dir_fd)
    finally:
        os.close(dir_fd)


def _remove_beneath(folder: Path, path: Path) -> str | None:
    """Remove `path`, a file or a whole folder at that place beneath `folder`, following no symlink an agent could
    plant, and say what stays: a symlink at its name goes, and what it names stays, and one on its way is not followed,
    so what lies past it stays. Nothing there is nothing to remove."""
    *parts, name = path.parts
    try:
        dir_fd = os.open(folder, os.O_RDONLY | os.O_DIRECTORY)
    except FileNotFoundError:
        return None
    try:
        for part in parts:
            try:
                step = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=dir_fd)
            except OSError as error:
                if error.errno not in (errno.ENOTDIR, errno.ELOOP):
                    raise
                planted = stat.S_ISLNK(os.lstat(part, dir_fd=dir_fd).st_mode)
                return "stays, as a symlink on its way is not followed" if planted else None
            os.close(dir_fd)
            dir_fd = step
        found = os.lstat(name, dir_fd=dir_fd)
        if stat.S_ISDIR(found.st_mode):
            shutil.rmtree(name, dir_fd=dir_fd)
        else:
            os.unlink(name, dir_fd=dir_fd)
        return "was a symlink, which went, and what it named stays" if stat.S_ISLNK(found.st_mode) else None
    except FileNotFoundError:
        return None
    finally:
        os.close(dir_fd)


def clean(folder: Path, credentials: Iterable[Path]) -> tuple[str, ...]:
    """Remove from an ended agent's `folder` what its harness kept that is no record: its `TMPDIR`, and `credentials`,
    where beneath the folder its driver says its harness keeps one. Return what stays of them, in words."""
    said = []
    for path in (tmpdir(Path()), *credentials):
        try:
            stays = _remove_beneath(folder, path)
        except OSError as error:
            stays = f"could not be removed: {error.strerror or error}"
        if stays is not None:
            said.append(f"{path} {stays}")
    return tuple(said)


async def reap(folder: Path, grace: float) -> tuple[str, ...]:
    """End what a crash left in an agent's `folder` and return what was left alone, in words: a group not provably ours,
    or a record that cannot be read. A reused pid can never make this signal a stranger. Only the driver's own record
    and a wire program's are read, following no symlink a confined agent could plant, because a harness can write under
    its folder. What left a group is found by the `TMPDIR` it inherited, which proves it ours, so a group that outlived
    its leader is named for what that misses."""
    left, unproven, recorded = [], [], False
    for path in (folder / RECORD, folder / WIRE / RECORD):
        try:
            fd = open_beneath(folder, path, os.O_RDONLY)
        except FileNotFoundError:
            continue
        except OSError:  # A symlink planted where a record goes: refused, named, and removed.
            recorded = True
            left.append(f"{path.relative_to(folder)} cannot be read")
            _unlink_beneath(folder, path)
            continue
        recorded = True
        with os.fdopen(fd, "rb") as file:
            raw = file.read()
        try:
            record = Record.model_validate_json(raw)
        except ValueError:
            left.append(f"{path.relative_to(folder)} cannot be read")
            _unlink_beneath(folder, path)
            continue
        match record.state():
            case "ours":
                await _end(record.pid, grace)
            case "unproven":
                unproven.append((path, record))
                continue
            case "gone":
                pass
        _unlink_beneath(folder, path)  # A stop of the same agent under way, as a shutdown runs, may remove it first.
    if recorded:  # A stop that ran to its end left no record, and nothing.
        await _end_marked((folder, folder / WIRE), grace)
    for path, record in unproven:
        if record.state() == "gone":
            _unlink_beneath(folder, path)
        else:
            left.append(f"process group {record.pid} outlived its leader and cannot be proved ours")
    return tuple(left)


async def run(
    command: Sequence[str],
    *,
    cwd: Path,
    folder: Path,
    env: Mapping[str, str],
    output: Path,
    limit: float,
    clock: Clock,
    grace: float,
) -> int | None:
    """Run `command` in `cwd` as a harness is run, in a group of its own recorded in `folder` before it can exec, on
    `env`, which should give it `folder`'s `TMPDIR`, with nothing on stdin and all it prints in `output`, until it exits
    or `limit` seconds pass on `clock`. Then what is left of it is ended, as `reap` ends it, whichever way it went. Its
    exit code, negative for the signal that ended it, or None when its limit came first."""
    folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    with output.open("wb") as printed:
        process = await asyncio.create_subprocess_exec(
            _SH,
            "-c",
            _TRAMPOLINE,
            "sh",
            *command,
            stdin=PIPE,
            stdout=printed,
            stderr=subprocess.STDOUT,
            env=env,
            cwd=cwd,
            start_new_session=True,
        )
    try:
        record = Record.of(process.pid)
        if record is None:
            raise DriverError(f"{command[0]} died before it could be recorded")
        record.write(folder)
        assert process.stdin is not None
        process.stdin.write(b"\n")
        await process.stdin.drain()
        process.stdin.close()
        exited = await first(process.wait(), clock.sleep(limit))
    finally:
        await reap(folder, grace)
        await process.wait()
    return process.returncode if exited else None


class _Streams(SubprocessStreamProtocol):
    """The usual streams, and word of the leader's exit, since `Process.wait` also waits for every pipe to close, and a
    forked child can hold one open for ever."""

    def __init__(self, limit: int, loop: asyncio.AbstractEventLoop) -> None:
        super().__init__(limit=limit, loop=loop)
        self.exited = asyncio.Event()

    def process_exited(self) -> None:
        super().process_exited()
        self.exited.set()


class _Log:
    """A bounded pair of files in an agent's `folder`: past `LOG_LIMIT` the current one becomes `.1`, so the newest
    text survives. What a full disk will not take is dropped, since a log must never stall the harness that writes it.
    It follows no symlink a confined agent could plant where its log goes, so its words never land outside its tree."""

    def __init__(self, folder: Path, name: str) -> None:
        self._folder = folder
        self._path = folder / name
        self._descriptor = self._open()

    def _open(self) -> int | None:
        """The log's descriptor, or None where a symlink was planted at its path: it is not followed and the log is
        dropped, since following it would write outside the folder and refusing the launch would stall the harness."""
        try:
            return open_beneath(self._folder, self._path, os.O_WRONLY | os.O_CREAT | os.O_APPEND)
        except OSError as error:
            if error.errno == errno.ELOOP:
                return None
            raise

    def write(self, data: bytes) -> None:
        if self._descriptor is None:
            return
        with contextlib.suppress(OSError):
            if os.fstat(self._descriptor).st_size + len(data) > LOG_LIMIT:
                self._path.replace(self._path.with_suffix(".log.1"))
                os.close(self._descriptor)
                self._descriptor = self._open()
            if self._descriptor is not None:
                os.write(self._descriptor, data[-LOG_LIMIT:])

    def close(self) -> None:
        if self._descriptor is not None:
            os.close(self._descriptor)


def _kill(record: Record) -> None:
    """The last resort for a group nobody stopped, which works with no loop to rely on."""
    if record.state() != "gone":
        _signal(record.pid, signal.SIGKILL)


def status(command: Sequence[str], env: Mapping[str, str]) -> subprocess.CompletedProcess[bytes] | None:
    """What a harness says of itself in a short run of its own, or None if it says nothing in time."""
    try:
        return subprocess.run(command, capture_output=True, env=env, timeout=_STATUS_SECONDS, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None


def exit_reason(code: int | None) -> str:
    """How a leader's end reads."""
    return f"killed by signal {-code}" if code is not None and code < 0 else f"exited with code {code}"


def _size(report: Report) -> int:
    """What a report weighs against the quota: a floor, since each holds a place, and the text it carries."""
    weight = _REPORT_FLOOR
    for name, value in report:
        if isinstance(value, str) and name != "type":
            weight += len(value)
        elif isinstance(value, tuple):
            weight += sum(map(len, value))
    return weight


def _check_program(command: Sequence[str], spec: AgentSpec, env: Mapping[str, str]) -> None:
    """Refuse a program that cannot run, while the reason can still reach whoever asked."""
    program = spec.cwd / command[0] if os.sep in command[0] else command[0]
    if not spec.cwd.is_dir():
        raise DriverError(f"{spec.cwd} is not a directory")
    if shutil.which(program, path=env.get("PATH")) is None:
        raise DriverError(f"{command[0]} is not an executable on the harness's PATH")


class Process:
    """One harness process and its group, from before exec until verified gone.

    `read` is called once, at once, and returns the driver's reader of `stdout`, which must wait only on the pipe, so
    that the pipe drains. It hands what it finds to `put`, which never waits either. A harness's end reaches `report` as
    `exited`. If nothing stops it, a closing loop or interpreter takes the group down rather than leave it. The host
    masks what `put` passes on, and text cut to fit is masked first, as a cut can split a secret: `gist`, `reason` and
    `unknown` do both.
    """

    def __init__(
        self,
        transport: asyncio.SubprocessTransport,
        streams: _Streams,
        record: Record,
        log: _Log,
        spec: AgentSpec,
        report: Reporter,
        read: Reader,
        quota: int,
    ) -> None:
        assert streams.stdin and streams.stdout and streams.stderr
        self.stdin, self.stdout, self._stderr = streams.stdin, streams.stdout, streams.stderr
        self._transport = transport
        self._streams = streams
        self._record = record
        self._folder = spec.folder
        self._confined = bool(spec.wrap)
        self._report = report
        self.redact = Redactor(secrets_of(spec))
        self._quota = quota
        self._waiting = 0
        self._queue: deque[tuple[Report, int] | None] = deque()
        self._queued = asyncio.Event()
        self._sealed = False
        self._exit_reported = False
        self._released = asyncio.Event()
        self._stopping: asyncio.Task[None] | None = None
        self._reaper = weakref.finalize(self, _kill, record)
        self._forwarding = asyncio.create_task(self._forward())
        self._logging = asyncio.create_task(self._log(log))
        self._reading = asyncio.create_task(read(self))
        self._reading.add_done_callback(self._read_ended)
        self._owning = asyncio.create_task(self._own())

    @classmethod
    async def launch(
        cls,
        command: Sequence[str],
        spec: AgentSpec,
        report: Reporter,
        *,
        read: Reader,
        env: Mapping[str, str] | None = None,
        quota: int = REPORT_QUOTA,
    ) -> "Process":
        """Start `command` in its own group, on the allowlisted environment, or on `env`, which a driver builds from
        that one, under `spec.wrap`, whose program is then the group's leader. The harness cannot exec until its record
        is on disk: `sh` waits for one line on stdin, and exits unexecuted if we die first."""
        spec.folder.mkdir(mode=0o700, parents=True, exist_ok=True)
        env = harness_env(spec) if env is None else env
        _check_program(command, spec, env)
        log = _Log(spec.folder, LOG)
        loop = asyncio.get_running_loop()
        transport, streams = await loop.subprocess_exec(
            lambda: _Streams(_BUFFER, loop),
            _SH,
            "-c",
            _TRAMPOLINE,
            "sh",
            *spec.wrap,
            *command,
            stdin=PIPE,
            stdout=PIPE,
            stderr=PIPE,
            env=env,
            cwd=spec.cwd,
            start_new_session=True,
        )
        pid = transport.get_pid()
        try:
            record = Record.of(pid)
            if record is None:
                raise DriverError(f"{command[0]} died before it could be recorded")
            record.write(spec.folder)
            assert streams.stdin is not None
            streams.stdin.write(b"\n")
            await streams.stdin.drain()
        except BaseException:
            transport.close()
            log.close()
            raise
        return cls(transport, streams, record, log, spec, report, read, quota)

    @property
    def returncode(self) -> int | None:
        """How the leader ended, once it has."""
        return self._transport.get_returncode()

    async def exited(self) -> None:
        """Wait for the leader. A forked child may live on, and only `stop` ends it."""
        await self._streams.exited.wait()

    def put(self, *reports: Report) -> None:
        """Queue reports, without waiting, so that a pipe always drains. Past the quota a delta is dropped, as deltas
        may be, and anything else stops this agent with a gap."""
        for report in reports:
            if self._sealed:
                return
            size = _size(report)
            if self._waiting + size <= self._quota:
                self._waiting += size
                self._enqueue(report, size)
                self._exit_reported |= isinstance(report, Exited)
            elif not isinstance(report, Delta):
                self._lose("reports passed their quota")

    def gist(self, text: str) -> str:
        return self.redact(text)[:GIST_LIMIT]

    def reason(self, text: str) -> str:
        return self.redact(text)[:SHORT_LIMIT]

    def unknown(self, kind: str, raw: str) -> None:
        """Report a frame nobody's vocabulary covers."""
        self.put(*unknown_frame(self.reason(kind), self.redact(raw)))

    def _lose(self, why: str) -> None:
        """Stop this agent with a gap, since what it reports can no longer be whole."""
        if not self._sealed:
            self._sealed = True
            self._enqueue(Native(kind="stream", raw=self.redact(why)[:RAW_LIMIT]))
            self._enqueue(GapReport(what="stream_lost"))
            self._stop_soon(_LOST_GRACE)

    def _read_ended(self, reading: asyncio.Task[None]) -> None:
        """A reader that crashes, or one that ends while the harness runs on, leaves nothing to hear it by. An end of
        stdout comes a moment before the exit that caused it, so that second case waits to see."""
        if reading.cancelled():
            return
        if (error := reading.exception()) is not None:
            self._lose(f"reading stopped: {error}")
        elif not self._streams.exited.is_set():
            asyncio.get_running_loop().call_later(_FLUSH, self._lose_if_running)

    def _lose_if_running(self) -> None:
        if not self._streams.exited.is_set():
            self._lose("the harness closed stdout and ran on")

    def _enqueue(self, report: Report, size: int = 0) -> None:
        self._queue.append((report, size))
        self._queued.set()

    async def _forward(self) -> None:
        """Hand reports over in order, the last being the end of the queue. One that cannot be taken stops this agent,
        since nobody can hear it now."""
        while True:
            await self._queued.wait()
            self._queued.clear()
            while self._queue:
                queued = self._queue.popleft()
                if queued is None:
                    return
                report, size = queued
                self._waiting -= size
                try:
                    await self._report(report)
                except Exception:
                    self._sealed = True
                    self._stop_soon(_LOST_GRACE)
                    return

    async def _log(self, log: _Log) -> None:
        """Keep stderr in a bounded log, masked, and out of the journal."""
        held = Held(self.redact)
        try:
            while chunk := await self._stderr.read(_CHUNK):
                log.write(held.feed(chunk))
            log.write(held.flush())
        finally:
            log.close()

    async def _own(self) -> None:
        """Report the leader's end, after what it wrote last, then hold the group until `stop` has ended it. Only a
        closing loop cuts this short, and then the group goes with it."""
        try:
            await self._streams.exited.wait()
            _, reading = await asyncio.wait({self._reading}, timeout=_FLUSH)
            for task in reading:
                task.cancel()
            await asyncio.gather(*reading, return_exceptions=True)
            if not self._exit_reported:
                self._enqueue(Exited(reason=exit_reason(self.returncode)))
            self._sealed = True
            self._queue.append(None)
            self._queued.set()
            await self._released.wait()
        except asyncio.CancelledError:
            _kill(self._record)
            await asyncio.wait_for(self._streams.exited.wait(), _VERIFY)
            self._let_go()
            raise
        self._let_go()

    def _let_go(self) -> None:
        self._reaper.detach()
        self._transport.close()

    def _stop_soon(self, grace: float) -> None:
        if self._stopping is None:
            self._stopping = asyncio.create_task(self._stop(grace))

    async def stop(self, grace: float) -> None:
        """End the whole tree: end of stdin, wait, TERM, wait, KILL, then verify, and what left the group too. A harness
        under a wrap gets no TERM, as its confiner passes none on and dies of one, which kills the harness outright. A
        stop that came to KILL reports `crash_window`. A second call waits for the first."""
        self._stop_soon(grace)
        assert self._stopping is not None
        await asyncio.shield(self._stopping)

    async def _stop(self, grace: float) -> None:
        """A SIGKILL gives a harness no chance to end what it started, and a tool that leads a group of its own lives
        on, so that is a gap. It is said first, since the leader's end closes the queue. Stdin that has closed already
        has had its say. What left the group gets what is left of twice `grace`."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + 2 * grace
        if not self.stdin.is_closing():
            self.stdin.close()
            with contextlib.suppress(TimeoutError):
                async with asyncio.timeout(grace):
                    await self.exited()
        if self._record.state() != "gone" and (self._confined or not await _termed(self._record.pid, grace)):
            self._enqueue(GapReport(what="crash_window"))
            await _killed(self._record.pid)
        await _end_marked((self._folder,), max(deadline - loop.time(), 0.0))
        (self._folder / RECORD).unlink(missing_ok=True)
        self._released.set()
        await asyncio.wait({self._owning, self._logging, self._forwarding}, timeout=_FLUSH)
