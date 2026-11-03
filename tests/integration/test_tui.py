"""The terminal UI on a detached runtime, the mode it uses: attaching to history, a runtime stopped, resumed and killed
under it, and Ctrl+D leaving the runtime to run on."""

import asyncio
import fcntl
import os
import pty
import select
import signal
import struct
import subprocess
import sys
import termios
import time
from pathlib import Path

import pyte
import pytest

from platoon_harness import Session, Team
from platoon_harness.config import Manifest
from platoon_harness.kernel import is_held
from platoon_harness.runtime.paths import read_running
from platoon_harness_cli.sessions import ask_to_stop
from platoon_harness_cli.tui.app import TerminalUI
from platoon_harness_cli.tui.sessions import Sessions
from platoon_harness_cli.tui.transcript import Transcript

from ..unit.runtime.support import in_state, of_type, until
from ..unit.tui.support import drawn, workspace
from .scripts import inside

pytestmark = pytest.mark.timeout(90)


@pytest.fixture(autouse=True)
def importable(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """A detached runtime is another process, and it must find the harnesses these tests name."""
    monkeypatch.setenv("PYTHONPATH", str(Path(__file__).parents[2]))
    monkeypatch.setenv("PLATOON_HARNESS_HOME", str(tmp_path))


def saying() -> Team:
    return Team.model_validate({"roles": {"lead": {"harness": inside("saying")}}})


async def test_a_session_with_no_runtime_opens_as_read_only_history_with_resume_offered(tmp_path):
    async with Session.start(saying(), name="s", root=tmp_path, cwd=tmp_path) as owner:
        await in_state(owner, "lead", "idle")
        await owner.send("@lead", "before it stopped")
        await in_state(owner, "lead", "idle")
    head = (tmp_path / "sessions" / "s" / "journal.sqlite").stat().st_size

    app = TerminalUI("s")
    async with app.run_test(size=(120, 30)) as pilot:
        text = await drawn(pilot, lambda text: "before it stopped" in text and "history" in text)
        assert "Alt+R resumes it, which can spend money" in text
        assert "this is history" in text

        await pilot.press(*"hello", "enter")
        await drawn(pilot, lambda text: "Alt+R resumes the session to send" in text)

    assert (tmp_path / "sessions" / "s" / "journal.sqlite").stat().st_size == head
    assert not is_held(tmp_path / "sessions" / "s")


async def test_a_runtime_stopped_resumed_and_killed_under_the_tui_shows_as_what_it_is_and_nothing_twice(tmp_path):
    guest = await Session.start(saying(), name="s", root=tmp_path, detach=True)
    await in_state(guest, "lead", "idle")
    app = TerminalUI("s")
    async with app.run_test(size=(120, 30)) as pilot:
        await drawn(pilot, lambda text: "@lead" in text and " live " in text)
        await pilot.press(*"first", "enter")
        await drawn(pilot, lambda text: "@lead  done" in text)

        await ask_to_stop(guest)
        await drawn(pilot, lambda text: "Its runtime stopped, as its owner asked" in text)

        await guest.leave()
        guest = await Session.resume("s", detach=True)
        await drawn(pilot, lambda text: " live " in text and "owner asked" not in text, within=30)
        await pilot.press(*"second", "enter")
        await drawn(pilot, lambda text: text.count("@lead  done") == 2)

        running = read_running(tmp_path / "sessions" / "s")
        assert running is not None
        os.killpg(running.pid, signal.SIGKILL)
        await drawn(pilot, lambda text: "went without its shutdown" in text)

        seqs = [block.event.seq for block in workspace(app).query_one(Transcript).blocks]
        assert seqs == sorted(set(seqs))
        sent = [event.gist for event in await of_type(guest, "message.sent") if event.actor == "human:you"]
        assert sent == ["first", "second"]
    await guest.leave()


async def test_ctrl_d_detaches_and_the_runtime_runs_on(tmp_path):
    guest = await Session.start(saying(), name="s", root=tmp_path, detach=True)
    await in_state(guest, "lead", "idle")
    app = TerminalUI("s")
    async with app.run_test(size=(100, 30)) as pilot:
        await drawn(pilot, lambda text: "@lead" in text)
        await pilot.press(*"x", "backspace", "ctrl+d")
        await pilot.pause()

    assert app.return_value == "s"
    assert is_held(tmp_path / "sessions" / "s")
    await guest.send("@lead", "still there?")
    await in_state(guest, "lead", "idle")
    await guest.leave()


def hostile() -> Team:
    return Team.model_validate({"roles": {"lead": {"harness": inside("hostile")}}})


def _shown(screen: pyte.Screen) -> str:
    return "\n".join(screen.display)


def attached_in_a_pty(session: str) -> tuple[pyte.Screen, bytes]:
    """`platoon-harness attach` on a real terminal, read through an emulator until it shows the agent's words, then
    left with Ctrl+Q: the screen, and every byte it wrote."""
    environ = {**os.environ, "TERM": "xterm-256color", "COLUMNS": "120", "LINES": "30"}
    master, slave = pty.openpty()
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 30, 120, 0, 0))
    command = Path(sys.executable).parent / "platoon-harness"
    attached = subprocess.Popen(
        [command, "attach", session], stdin=slave, stdout=slave, stderr=slave, env=environ, start_new_session=True
    )
    os.close(slave)
    written = bytearray()
    screen = pyte.Screen(120, 30)
    stream = pyte.ByteStream(screen)
    try:
        deadline = time.monotonic() + 30
        while "kestrel" not in _shown(screen) and time.monotonic() < deadline:
            if select.select([master], [], [], 1.0)[0]:
                try:
                    chunk = os.read(master, 65536)
                except OSError:
                    break
                written += chunk
                stream.feed(chunk)
    finally:
        os.write(master, b"\x11")
        try:
            attached.wait(timeout=30)
        except subprocess.TimeoutExpired:
            attached.kill()
            attached.wait()
            raise AssertionError(f"Ctrl+Q left it running, on this screen:\n{_shown(screen)}") from None
        finally:
            os.close(master)
    return screen, bytes(written)


async def test_no_escape_from_an_agent_ever_reaches_the_terminal(tmp_path):
    async with Session.start(hostile(), name="s", root=tmp_path, cwd=tmp_path) as owner:
        await in_state(owner, "lead", "idle")
        await owner.send("@lead", "go")
        await until(lambda: of_type(owner, "turn.ended"), owner)

    screen, written = await asyncio.to_thread(attached_in_a_pty, "s")
    shown = _shown(screen)

    assert "kestrel \\x1b]0;owned\\x1b\\" in shown
    assert b"\x1b]0;owned" not in written and b"\x1b]52;" not in written and b"\x1bc" not in written
    assert "\x9b".encode() not in written and "‮".encode() not in written
    assert screen.title != "owned"


def test_a_headless_run_never_imports_textual(tmp_path):
    harness = f"roles.solo.harness = {inside('saying')!r}"
    script = (
        "import sys\nfrom platoon_harness_cli.main import main\n"
        f"code = main(['run', '--set', {harness!r}, 'say hello'])\n"
        "print('imported' if 'textual' in sys.modules else 'not imported', code)\n"
    )

    done = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, timeout=60, check=False)

    assert done.stdout.strip().splitlines()[-1] == "not imported 0", done.stderr


def sessions_of(app: TerminalUI) -> Sessions:
    assert isinstance(app.screen, Sessions), type(app.screen)
    return app.screen


async def test_the_sessions_screen_works_with_no_sessions_and_starts_one_on_a_detached_runtime(tmp_path):
    team = tmp_path / "crew.toml"
    team.write_text(f'[roles.lead]\nharness = "{inside("saying")}"\n')
    app = TerminalUI()
    async with app.run_test(size=(120, 30)) as pilot:
        await drawn(pilot, lambda text: "No sessions yet" in text)

        await pilot.press("n")
        await pilot.pause()
        await pilot.press(*str(team), "tab", *"crew", "tab", *"yes", "enter")
        await drawn(pilot, lambda text: "@lead" in text and " live " in text)

        folder = tmp_path / "sessions" / "crew"
        running = read_running(folder)
        assert running is not None and running.pid != os.getpid()
        await pilot.press("ctrl+q")
    assert app.return_value == "crew" and is_held(folder)


async def test_several_agents_on_a_plan_login_are_asked_about_once_and_the_answer_is_plan_login(tmp_path):
    team = tmp_path / "crew.toml"
    team.write_text(f'[roles.lead]\nharness = "{inside("planned")}"\ncount = 2\n')
    app = TerminalUI()
    async with app.run_test(size=(120, 30)) as pilot:
        await drawn(pilot, lambda text: "No sessions yet" in text)
        await pilot.press("n")
        await pilot.pause()
        await pilot.press(*str(team), "tab", *"crew", "tab", *"yes", "enter")
        text = await drawn(pilot, lambda text: "your own work?" in text)
        assert "lead would run several agents headless on one plan login" in text

        await pilot.press("y")
        await drawn(pilot, lambda text: "@lead-1" in text and "@lead-2" in text)
        await pilot.press("ctrl+q")

    manifest = Manifest.model_validate_json((tmp_path / "sessions" / "crew" / "manifest.json").read_bytes())
    assert manifest.plan_login is True


async def test_stopping_a_session_takes_one_confirmation_and_resuming_says_it_can_spend_money(tmp_path):
    guest = await Session.start(saying(), name="s", root=tmp_path, detach=True)
    await in_state(guest, "lead", "idle")
    await guest.leave()
    folder = tmp_path / "sessions" / "s"
    app = TerminalUI()
    async with app.run_test(size=(120, 30)) as pilot:
        await drawn(pilot, lambda text: "live" in text)

        await pilot.press("s")
        await drawn(pilot, lambda text: "Stop s?" in text)
        await pilot.press("y")
        await drawn(pilot, lambda text: "stopped" in text and "live" not in text)
        assert not is_held(folder)

        await pilot.press("r")
        await drawn(pilot, lambda text: "which can spend money" in text)
        await pilot.press("n")
        await pilot.pause()
        assert not is_held(folder)

        await pilot.press("r")
        await drawn(pilot, lambda text: "which can spend money" in text)
        await pilot.press("y")
        await drawn(pilot, lambda text: "@lead" in text and " live " in text)
        assert is_held(folder)
        await pilot.press("ctrl+q")
