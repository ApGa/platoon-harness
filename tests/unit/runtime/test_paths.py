"""Where a session lives: architecture section 4."""

import errno
import logging
import os
import stat
import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from platoon_harness.kernel import Filesystem, Kernel, Refused
from platoon_harness.primitives import PRIMITIVES
from platoon_harness.runtime import paths
from platoon_harness.runtime.paths import (
    HOME_VARIABLE,
    MANIFEST,
    Running,
    agent_folder,
    find_root,
    listing,
    new_folder,
    read_running,
    session_folder,
    socket_path,
    write_private,
)
from platoon_harness.schema import ConfigError


@pytest.fixture
def short() -> Iterator[Path]:
    """A runtime directory short enough for a socket, as `tmp_path` may not be."""
    with tempfile.TemporaryDirectory(prefix="ph-", dir="/tmp") as folder:
        yield Path(folder)


def on_network(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(paths, "filesystem", lambda path: Filesystem("lustre", "network"))


def test_a_root_comes_from_what_was_chosen_then_the_environment_then_the_state_home(tmp_path):
    state = {"XDG_STATE_HOME": str(tmp_path / "state")}
    home = {**state, HOME_VARIABLE: str(tmp_path / "home")}

    assert find_root(environ=state) == tmp_path / "state" / "platoon-harness"
    assert find_root(environ=home) == tmp_path / "home"
    assert find_root(tmp_path / "chosen", environ=home) == tmp_path / "chosen"


def test_a_default_root_on_a_network_filesystem_falls_back_with_a_notice(tmp_path, monkeypatch, caplog):
    on_network(monkeypatch)

    with caplog.at_level(logging.WARNING, "platoon_harness.runtime"):
        root = find_root(environ={"XDG_STATE_HOME": str(tmp_path)})

    assert root == Path(f"/var/tmp/platoon-harness-{os.getuid()}")
    assert len(caplog.records) == 1 and "network filesystem" in caplog.text


def test_a_chosen_root_on_a_network_filesystem_is_refused_to_a_live_writer_only(tmp_path, monkeypatch):
    on_network(monkeypatch)

    with pytest.raises(ConfigError, match="a live journal is not safe"):
        find_root(tmp_path, environ={}, writing=True)

    assert find_root(tmp_path, environ={}) == tmp_path


def test_two_sessions_cannot_share_a_name(tmp_path):
    new_folder(tmp_path, "{}", "fix-auth")

    with pytest.raises(Refused) as refused:
        new_folder(tmp_path, "{}", "fix-auth")

    assert refused.value.refusal.code == "conflict"
    assert "resume it" in str(refused.value)
    assert [path.name for path in tmp_path.iterdir()] == ["sessions"]


def test_a_crash_before_the_rename_burns_no_name(tmp_path, monkeypatch):
    def dies(*_: Any) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(Path, "rename", dies)

    with pytest.raises(KeyboardInterrupt):
        new_folder(tmp_path, "{}", "fix-auth")

    monkeypatch.undo()
    assert new_folder(tmp_path, "{}", "fix-auth").name == "fix-auth"


def test_a_folder_a_crash_left_empty_can_be_claimed(tmp_path):
    (tmp_path / "sessions" / "fix-auth").mkdir(parents=True)

    assert (new_folder(tmp_path, "{}", "fix-auth") / MANIFEST).read_text() == "{}"


def test_a_folder_holds_its_manifest_from_the_moment_it_has_a_name(tmp_path):
    folder = new_folder(tmp_path, '{"team": 1}', "fix-auth")

    assert (folder / MANIFEST).read_text() == '{"team": 1}'
    assert [found.name for found in listing(tmp_path)] == ["fix-auth"]


@pytest.mark.parametrize("name", ["../up", "a/b", "", ".hidden", "with space"])
def test_a_name_must_be_safe_as_a_part_of_a_path(tmp_path, name):
    if name:
        with pytest.raises(Refused) as refused:
            new_folder(tmp_path, "{}", name)
        assert refused.value.refusal.code == "invalid"


def test_a_session_with_no_name_gets_one_nobody_has(tmp_path):
    assert len({new_folder(tmp_path, "{}").name for _ in range(32)}) == 32


def test_a_folder_that_cannot_be_claimed_is_not_called_taken(tmp_path, monkeypatch):
    def denied(*_: Any) -> None:
        raise PermissionError(errno.EACCES, "denied")

    monkeypatch.setattr(Path, "rename", denied)

    with pytest.raises(PermissionError):
        new_folder(tmp_path, "{}", "mine")
    assert not list(tmp_path.glob(".new-*"))


def test_a_session_folder_is_private(tmp_path):
    assert stat.S_IMODE(new_folder(tmp_path, "{}", "mine").stat().st_mode) == 0o700


def test_a_session_is_found_by_name_or_refused(tmp_path):
    folder = new_folder(tmp_path, "{}", "there")

    assert session_folder(tmp_path, "there") == folder
    with pytest.raises(Refused) as refused:
        session_folder(tmp_path, "gone")
    assert refused.value.refusal.code == "not_found"


@pytest.mark.parametrize("name", ["run.", "x.lock", "a..b"])
def test_a_session_named_before_the_grammar_is_said_to_need_another_name(tmp_path, name):
    folder = tmp_path / "sessions" / name
    folder.mkdir(parents=True)
    (folder / MANIFEST).write_text("{}")

    with pytest.raises(Refused) as refused:
        session_folder(tmp_path, name)

    assert refused.value.refusal.code == "invalid"
    assert refused.value.refusal.detail == (
        f"{name} no longer names a session, since a name may not hold `..` or end in `.` or `.lock`: rename its "
        f"folder {folder} while no runtime holds it"
    )


def test_an_agent_has_a_folder_under_its_session(tmp_path):
    assert agent_folder(tmp_path, "ada") == tmp_path / "agents" / "ada"


def test_listing_scans_folders_and_the_lock_says_which_are_live(tmp_path):
    closed, live = new_folder(tmp_path, "{}", "closed"), new_folder(tmp_path, "{}", "live")
    (tmp_path / "sessions" / "never-written").mkdir()
    Kernel.open(closed, extensions=PRIMITIVES).close()
    kernel = Kernel.open(live, extensions=PRIMITIVES)

    assert [(found.name, found.live) for found in listing(tmp_path)] == [("closed", False), ("live", True)]

    kernel.close()
    assert not listing(tmp_path)[1].live


def test_listing_an_empty_root_finds_nothing(tmp_path):
    assert listing(tmp_path / "nowhere") == []


SESSION = Path("/a/session")


def test_a_socket_is_short_whatever_the_folder_is(tmp_path):
    runtime_dir = tmp_path / ("deep" * 30)
    runtime_dir.mkdir()

    path = socket_path(SESSION, {"XDG_RUNTIME_DIR": str(runtime_dir)})

    assert len(os.fsencode(path)) <= 103
    assert path.parent == Path(f"/tmp/platoon-harness-{os.getuid()}")


def test_a_socket_directory_only_this_user_can_reach(short):
    path = socket_path(SESSION, {"XDG_RUNTIME_DIR": str(short)})

    assert path.suffix == ".sock" and path.is_relative_to(short)
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700


def test_a_socket_directory_of_ours_is_tightened(short):
    open_to_all = short / "platoon-harness"
    open_to_all.mkdir()
    open_to_all.chmod(0o777)

    socket_path(SESSION, {"XDG_RUNTIME_DIR": str(short)})

    assert stat.S_IMODE(open_to_all.stat().st_mode) == 0o700


def test_a_socket_directory_of_someone_else_s_is_refused(short, monkeypatch):
    monkeypatch.setattr(paths.os, "getuid", lambda: 1)

    with pytest.raises(ConfigError, match="of this user's"):
        socket_path(SESSION, {"XDG_RUNTIME_DIR": str(short)})


def test_a_link_is_no_socket_directory(short):
    (short / "elsewhere").mkdir()
    (short / "platoon-harness").symlink_to(short / "elsewhere")

    with pytest.raises(ConfigError, match="of this user's"):
        socket_path(SESSION, {"XDG_RUNTIME_DIR": str(short)})


def test_two_sessions_have_two_sockets(short):
    environ = {"XDG_RUNTIME_DIR": str(short)}

    assert socket_path(Path("/one"), environ) != socket_path(Path("/two"), environ)
    assert socket_path(Path("/one"), environ) == socket_path(Path("/one"), environ)


def test_a_socket_goes_with_a_session_s_folder_so_a_copy_has_its_own(tmp_path, short):
    environ = {"XDG_RUNTIME_DIR": str(short)}
    original, copy = tmp_path / "original", tmp_path / "copy"
    original.mkdir()
    copy.mkdir()

    assert socket_path(original, environ) != socket_path(copy, environ)


def test_an_unusable_runtime_directory_falls_through_to_the_next(tmp_path):
    path = socket_path(SESSION, {"XDG_RUNTIME_DIR": "/proc/nonexistent"})

    assert path.parent == Path(f"/tmp/platoon-harness-{os.getuid()}")


def test_a_root_another_user_can_write_is_refused(tmp_path):
    root = tmp_path / "open"
    root.mkdir()
    root.chmod(0o777)

    with pytest.raises(ConfigError, match="nobody else can write"):
        find_root(root, environ={}, writing=True)

    assert find_root(root, environ={}) == root


def test_a_root_of_someone_else_s_is_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(paths.os, "getuid", lambda: 1)

    with pytest.raises(ConfigError, match="of this user's"):
        find_root(tmp_path, environ={}, writing=True)


def test_a_root_is_made_for_whoever_writes_there_first(tmp_path):
    root = tmp_path / "new" / "root"

    assert find_root(root, environ={}, writing=True) == root
    assert stat.S_IMODE(root.stat().st_mode) == 0o700


def test_the_fallback_root_is_made_private_when_it_is_written_to(tmp_path, monkeypatch):
    on_network(monkeypatch)
    made: list[Path] = []
    monkeypatch.setattr(paths, "_make_private", made.append)

    find_root(environ={"XDG_STATE_HOME": str(tmp_path)})
    assert made == []

    root = find_root(environ={"XDG_STATE_HOME": str(tmp_path)}, writing=True)
    assert made == [root]


def test_a_sessions_folder_is_tightened_whatever_the_root_is(tmp_path):
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    sessions.chmod(0o755)

    new_folder(tmp_path, "{}", "mine")

    assert stat.S_IMODE(sessions.stat().st_mode) == 0o700


def test_a_private_file_is_this_user_s_alone_and_replaced_in_one_step(tmp_path):
    path = tmp_path / "owner.token"

    write_private(path, "first")
    write_private(path, "second")

    assert path.read_text() == "second"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert [found.name for found in tmp_path.iterdir()] == ["owner.token"]


def test_what_a_runtime_says_of_itself_is_read_back(tmp_path):
    assert read_running(tmp_path) is None

    running = Running(pid=1, started=2.0, socket="s", incarnation=3)
    write_private(tmp_path / paths.RUNNING, running.model_dump_json())

    assert read_running(tmp_path) == running
