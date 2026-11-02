"""Where a session lives: architecture section 4."""

import logging
import os
import stat
import tempfile
from collections.abc import Iterator
from pathlib import Path

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
    new_folder(tmp_path, "fix-auth")

    with pytest.raises(Refused) as refused:
        new_folder(tmp_path, "fix-auth")

    assert refused.value.refusal.code == "conflict"
    assert "resume it" in str(refused.value)


@pytest.mark.parametrize("name", ["../up", "a/b", "", ".hidden", "with space"])
def test_a_name_must_be_safe_as_a_part_of_a_path(tmp_path, name):
    if name:
        with pytest.raises(Refused) as refused:
            new_folder(tmp_path, name)
        assert refused.value.refusal.code == "invalid"


def test_a_session_with_no_name_gets_one_nobody_has(tmp_path):
    assert len({new_folder(tmp_path).name for _ in range(32)}) == 32


def test_a_session_folder_is_private(tmp_path):
    assert stat.S_IMODE(new_folder(tmp_path, "mine").stat().st_mode) == 0o700


def test_a_session_is_found_by_name_or_refused(tmp_path):
    folder = new_folder(tmp_path, "there")
    (folder / MANIFEST).write_text("{}")

    assert session_folder(tmp_path, "there") == folder
    with pytest.raises(Refused) as refused:
        session_folder(tmp_path, "gone")
    assert refused.value.refusal.code == "not_found"


def test_an_agent_has_a_folder_under_its_session(tmp_path):
    assert agent_folder(tmp_path, "ada") == tmp_path / "agents" / "ada"


def test_listing_scans_folders_and_the_lock_says_which_are_live(tmp_path):
    closed, live = new_folder(tmp_path, "closed"), new_folder(tmp_path, "live")
    new_folder(tmp_path, "never-written")
    (closed / MANIFEST).write_text("{}")
    (live / MANIFEST).write_text("{}")
    Kernel.open(closed, extensions=PRIMITIVES).close()
    kernel = Kernel.open(live, extensions=PRIMITIVES)

    assert [(found.name, found.live) for found in listing(tmp_path)] == [("closed", False), ("live", True)]

    kernel.close()
    assert not listing(tmp_path)[1].live


def test_listing_an_empty_root_finds_nothing(tmp_path):
    assert listing(tmp_path / "nowhere") == []


def test_a_socket_is_short_whatever_the_folder_is(tmp_path):
    runtime_dir = tmp_path / ("deep" * 30)
    runtime_dir.mkdir()

    path = socket_path("a-session", {"XDG_RUNTIME_DIR": str(runtime_dir)})

    assert len(os.fsencode(path)) <= 103
    assert path.parent == Path(f"/tmp/platoon-harness-{os.getuid()}")


def test_a_socket_directory_only_this_user_can_reach(short):
    path = socket_path("a-session", {"XDG_RUNTIME_DIR": str(short)})

    assert path.suffix == ".sock" and path.is_relative_to(short)
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700


def test_a_socket_directory_of_ours_is_tightened(short):
    open_to_all = short / "platoon-harness"
    open_to_all.mkdir()
    open_to_all.chmod(0o777)

    socket_path("a-session", {"XDG_RUNTIME_DIR": str(short)})

    assert stat.S_IMODE(open_to_all.stat().st_mode) == 0o700


def test_a_socket_directory_of_someone_else_s_is_refused(short, monkeypatch):
    monkeypatch.setattr(paths.os, "getuid", lambda: 1)

    with pytest.raises(Refused, match="of this user's"):
        socket_path("a-session", {"XDG_RUNTIME_DIR": str(short)})


def test_a_link_is_no_socket_directory(short):
    (short / "elsewhere").mkdir()
    (short / "platoon-harness").symlink_to(short / "elsewhere")

    with pytest.raises(Refused, match="of this user's"):
        socket_path("a-session", {"XDG_RUNTIME_DIR": str(short)})


def test_two_sessions_have_two_sockets(short):
    environ = {"XDG_RUNTIME_DIR": str(short)}

    assert socket_path("one", environ) != socket_path("two", environ)
    assert socket_path("one", environ) == socket_path("one", environ)


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
