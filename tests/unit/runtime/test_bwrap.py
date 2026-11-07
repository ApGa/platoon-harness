"""The `bwrap` extension's isolation, on the machine's own bubblewrap: what a command run under its wrap can write,
read, see and leave behind, and what its probe says where it cannot confine. Each test probes only what it made."""

import os
import shutil
import socket
import subprocess
import tempfile
import threading
import uuid
from collections.abc import Iterator, Sequence
from pathlib import Path

import pytest

from platoon_harness.bwrap import Bubblewrap, extension
from platoon_harness.testing import check_extension

from . import support

pytestmark = pytest.mark.timeout(60)

SECONDS = 30.0


@pytest.fixture
def bwrap() -> Bubblewrap:
    return support.bubblewrap()


@pytest.fixture
def beyond_tmp(tmp_path) -> Iterator[Path]:
    """A base directory outside /tmp, where the private /tmp does not reach, so hiding and the read-only root are shown
    on their own: the test's own folder where the system keeps those elsewhere, else one under XDG_RUNTIME_DIR, which
    goes after. Where neither is outside /tmp, there is nothing to show here, as the private /tmp alone would cover a
    folder under it."""
    if not _under_tmp(tmp_path):
        yield tmp_path
        return
    base = os.environ.get("XDG_RUNTIME_DIR")
    if not base or _under_tmp(Path(base)):
        pytest.skip("no writable directory outside /tmp, so hiding beyond the private /tmp is not shown")
    made = Path(tempfile.mkdtemp(dir=base, prefix="platoon-harness-test-"))
    try:
        yield made
    finally:
        shutil.rmtree(made, ignore_errors=True)


def _under_tmp(path: Path) -> bool:
    return path.resolve().is_relative_to(Path("/tmp").resolve())


def run(
    isolation: Bubblewrap, command: str, writable: Path, *, readable: Sequence[Path] = (), hidden: Sequence[Path] = ()
) -> str:
    """What `command` says, run by `sh` under the wrap, in `writable`."""
    argv = [*isolation.wrap(writable, readable, hidden), "/bin/sh", "-c", command]
    done = subprocess.run(argv, cwd=writable, capture_output=True, text=True, timeout=SECONDS, check=False)
    assert done.returncode == 0, done.stderr
    return done.stdout


def tried(path: Path) -> str:
    """A shell's words for whether it could write `path`."""
    return f'if (echo > "{path}") 2>/dev/null; then echo "{path.name} written"; else echo "{path.name} refused"; fi'


async def test_the_extension_passes_the_check_every_extension_does(tmp_path):
    checks = await check_extension(extension, folder=tmp_path / "check")

    assert checks.failed == (), str(checks)


def test_the_probe_says_why_bwrap_cannot_confine_here(tmp_path, monkeypatch):
    blocked = tmp_path / "blocked" / "bwrap"
    blocked.parent.mkdir()
    blocked.write_text("#!/bin/sh\necho 'No permissions to create new namespace' >&2\nexit 1\n")
    blocked.chmod(0o700)

    monkeypatch.setenv("PATH", str(tmp_path / "nowhere"))
    missing = Bubblewrap().refusal()
    monkeypatch.setenv("PATH", f"{blocked.parent}{os.pathsep}/usr/bin:/bin")
    said = Bubblewrap().refusal()

    assert missing == "`bwrap` is not on PATH: install bubblewrap"
    assert said == (
        "`bwrap` cannot confine anything here, as where user namespaces are blocked: No permissions to create new "
        "namespace"
    )


def test_a_bubblewrap_that_cannot_confine_fails_where_ci_requires_it_and_skips_elsewhere(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", str(tmp_path / "nowhere"))
    monkeypatch.delenv(support.REQUIRE_BWRAP, raising=False)
    with pytest.raises(pytest.skip.Exception) as skipped:
        support.bubblewrap()
    monkeypatch.setenv(support.REQUIRE_BWRAP, "1")
    with pytest.raises(pytest.fail.Exception) as failed:
        support.bubblewrap()

    reason = "bubblewrap cannot confine here, so nothing was confined: `bwrap` is not on PATH: install bubblewrap"
    assert str(skipped.value) == reason
    assert str(failed.value) == f"{reason}, and PLATOON_HARNESS_REQUIRE_BWRAP=1 says it must"


def test_a_wrapped_command_writes_only_its_folder_and_a_tmp_of_its_own(bwrap, tmp_path):
    """A hidden folder is empty and read-only, what it may read is read-only, and /tmp is its own, so of everything it
    tried only its folder's file is on disk after, and a folder of the real /tmp is not there to see."""
    folder, home = tmp_path / "folder", tmp_path / "home"
    for made in (folder, home / "objects"):
        made.mkdir(parents=True)
    outside = Path(tempfile.mkdtemp(dir="/tmp", prefix="platoon-harness-test-"))
    private = Path("/tmp") / f"platoon-harness-test-{uuid.uuid4().hex}"
    places = (folder / "mine", home / "escaped", home / "objects" / "escaped", outside / "escaped", private)
    try:
        said = run(bwrap, "; ".join(map(tried, places)), folder, readable=[home / "objects"], hidden=[home])
        seen = run(bwrap, f"test -e {outside} && echo seen || echo unseen", folder)

        assert said.split("\n")[:5] == ["mine written", *["escaped refused"] * 3, f"{private.name} written"]
        assert seen == "unseen\n"
        assert [path.exists() for path in places] == [True, False, False, False, False]
    finally:
        shutil.rmtree(outside, ignore_errors=True)


def test_a_hidden_folder_and_the_outside_hold_where_the_private_tmp_does_not_reach(bwrap, beyond_tmp):
    """Outside the system temp dir, so the private /tmp cannot be what hides it: a hidden folder shows only what it may
    read, read-only, and a folder bound nowhere is seen through the read-only root yet cannot be written."""
    home, outside, folder = beyond_tmp / "home", beyond_tmp / "outside", beyond_tmp / "folder"
    (home / "keys").mkdir(parents=True)
    (home / "keys" / "secret").write_text("canary\n")
    (home / "objects").mkdir()
    (home / "objects" / "pack").write_text("borrowed\n")
    outside.mkdir()
    folder.mkdir()
    probe = "; ".join(
        (
            f"cat {home}/objects/pack",
            f"cat {home}/keys/secret 2>/dev/null || echo unread",
            tried(home / "objects" / "x"),
            f"test -e {outside} && echo seen || echo unseen",
            tried(outside / "escaped"),
        )
    )

    said = run(bwrap, probe, folder, readable=[home / "objects"], hidden=[home])

    assert said.split("\n")[:5] == ["borrowed", "unread", "x refused", "seen", "escaped refused"]
    assert (home / "keys" / "secret").read_text() == "canary\n"
    assert not (outside / "escaped").exists()


def test_what_a_wrapped_command_may_read_is_read_only_where_it_is_hidden(bwrap, tmp_path):
    home = tmp_path / "home"
    (home / "keys").mkdir(parents=True)
    (home / "keys" / "secret").write_text("canary\n")
    (home / "objects").mkdir()
    (home / "objects" / "pack").write_text("borrowed\n")
    folder = tmp_path / "folder"
    folder.mkdir()
    unread = f"cat {home}/keys/secret 2>/dev/null || echo unread"
    command = f"cat {home}/objects/pack; {unread}; {tried(home / 'objects' / 'x')}"

    said = run(bwrap, command, folder, readable=[home / "objects"], hidden=[home])

    assert said.split("\n")[:3] == ["borrowed", "unread", "x refused"]


def test_an_installed_path_resolves_inside_as_it_does_outside(bwrap, tmp_path):
    """A program on a link into a hidden folder, through a link of a folder, which looks beside where it resolves."""
    home = tmp_path / "home"
    release = home / "releases" / "1.0"
    (release / "bin").mkdir(parents=True)
    (release / "resources").write_text("1.0\n")
    (release / "bin" / "tool").write_text('#!/bin/sh\ncat "$(dirname "$(readlink -f "$0")")/../resources"\n')
    (release / "bin" / "tool").chmod(0o700)
    (home / "current").symlink_to("releases/1.0")
    (home / "bin").mkdir()
    (home / "bin" / "tool").symlink_to(home / "current" / "bin" / "tool")
    (home / "keys").mkdir()
    folder = tmp_path / "folder"
    folder.mkdir()

    said = run(bwrap, f"{home}/bin/tool; ls {home}", folder, readable=[home / "bin" / "tool", release], hidden=[home])

    assert said.split("\n")[:3] == ["1.0", "bin", "current"]
    assert "keys" not in said


def test_a_wrapped_command_sees_only_its_own_processes(bwrap, tmp_path):
    said = run(bwrap, "ls /proc | grep -E '^[0-9]+$' | sort -n | tr '\\n' ' '", tmp_path)

    pids = [int(pid) for pid in said.split()]
    assert pids[0] == 1 and len(pids) <= 8 and max(pids) < 100


def test_nothing_a_wrapped_command_starts_outlives_it(bwrap, tmp_path):
    """It starts a process in a session of its own, which ignores `SIGTERM`, and leaves it running."""
    marker = f"platoon-harness-test-{uuid.uuid4().hex}"
    command = f"setsid sh -c 'trap \"\" TERM; sleep 600' {marker} </dev/null >/dev/null 2>&1 & echo started"

    said = run(bwrap, command, tmp_path)
    left = [entry for entry in Path("/proc").iterdir() if entry.name.isdecimal() and marker in cmdline(entry)]
    for entry in left:
        os.kill(int(entry.name), 9)

    assert said == "started\n"
    assert left == []


def cmdline(entry: Path) -> str:
    try:
        return entry.joinpath("cmdline").read_bytes().decode(errors="replace")
    except OSError:
        return ""


def test_a_wrapped_command_still_reaches_loopback(bwrap, tmp_path):
    """The network is kept, so a harness reaches our tools and a training system's gateway on loopback."""
    server = socket.create_server(("127.0.0.1", 0))
    server.settimeout(SECONDS)
    heard: list[bytes] = []

    def accept() -> None:
        connection, _ = server.accept()
        with connection:
            heard.append(connection.recv(64))

    listening = threading.Thread(target=accept)
    listening.start()
    port = server.getsockname()[1]
    try:
        run(bwrap, f"bash -c 'exec 3<>/dev/tcp/127.0.0.1/{port}; echo reached >&3'", tmp_path)
    finally:
        listening.join(SECONDS)
        server.close()

    assert heard == [b"reached\n"]
