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
from textual.content import Content
from textual.widgets import Static

from platoon_harness import Session, Team
from platoon_harness.config import PROJECT_FILE, Manifest
from platoon_harness.kernel import is_held
from platoon_harness.runtime.paths import read_running
from platoon_harness_cli import machine
from platoon_harness_cli.sessions import ask_to_stop
from platoon_harness_cli.tui.app import TerminalUI
from platoon_harness_cli.tui.composer import Composer
from platoon_harness_cli.tui.dialogs import Confirm, Help
from platoon_harness_cli.tui.sessions import Sessions
from platoon_harness_cli.tui.transcript import Transcript
from platoon_harness_cli.tui.workspace import Workspace

from ..unit.runtime.support import in_state, of_type, until
from ..unit.tui.support import at_once, drawn, workspace
from .scripts import inside

pytestmark = pytest.mark.timeout(90)


@pytest.fixture(autouse=True)
def importable(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """A detached runtime is another process, and it must find the harnesses these tests name. Each test works in a
    folder of its own, where the sessions screen looks for the project's team."""
    monkeypatch.setenv("PYTHONPATH", str(Path(__file__).parents[2]))
    monkeypatch.setenv("PLATOON_HARNESS_HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)


def saying() -> Team:
    return Team.model_validate({"roles": {"lead": {"harness": inside("saying")}}})


async def test_a_session_with_no_runtime_opens_as_read_only_history_with_resume_offered(tmp_path):
    async with Session.start(saying(), name="s", root=tmp_path, cwd=tmp_path) as owner:
        await in_state(owner, "lead", "idle")
        await owner.send("@lead", "before it stopped")
        await in_state(owner, "lead", "idle")
    head = (tmp_path / "sessions" / "s" / "journal.sqlite").stat().st_size
    folder = tmp_path / "sessions" / "s"
    before = sorted(path.name for path in folder.iterdir())

    app = TerminalUI("s")
    async with app.run_test(size=(120, 30)) as pilot:
        text = await drawn(pilot, lambda text: "before it stopped" in text and "history" in text)
        assert "/resume resumes it, which can spend money" in text
        assert "history: /resume resumes it to send" in text

        await pilot.press(*"hello", "enter")
        await drawn(pilot, lambda text: "history: /resume resumes it to send" in text)
        await pilot.press("ctrl+q")

    assert app.return_value is None, "leaving history said it runs on"
    assert (tmp_path / "sessions" / "s" / "journal.sqlite").stat().st_size == head
    assert sorted(path.name for path in folder.iterdir()) == sorted([*before, "marks.sqlite"]), "it wrote but marks"
    assert not is_held(tmp_path / "sessions" / "s")


async def test_esc_then_ry_typed_at_once_resumes_nothing_as_no_chord_spends(tmp_path):
    """Resuming can spend money, so no chord does it: a terminal sends Alt and R as Esc then r, and the question that
    follows takes the y after it."""
    async with Session.start(saying(), name="s", root=tmp_path, cwd=tmp_path) as owner:
        await in_state(owner, "lead", "idle")

    app = TerminalUI("s")
    async with app.run_test(size=(120, 30)) as pilot:
        await drawn(pilot, lambda text: "history" in text)
        composer = app.screen.query_one(Composer)
        at_once(app, "\x1bry")
        await drawn(pilot, lambda _: composer.text.endswith("y"))
        assert isinstance(app.screen, Workspace)
        await pilot.press("ctrl+q")

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

        seqs = [block.first for block in workspace(app).query_one(Transcript).blocks]
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


ESCAPED = "kestrel \\x1b]0;owned\\x1b\\"
"""The hostile agent's words as its transcript shows them, escaped. The navigator cuts them short of this."""


def _shown(screen: pyte.Screen) -> str:
    return "\n".join(screen.display)


def _read(master: int, within: float) -> bytes | None:
    """What a terminal is sent within `within` seconds, or None once its program has gone."""
    if not select.select([master], [], [], within)[0]:
        return b""
    try:
        return os.read(master, 65536)
    except OSError:
        return None


def attached_in_a_pty(session: str) -> tuple[pyte.Screen, bytes]:
    """`platoon-harness attach` on a real terminal, read through an emulator until its transcript shows the agent's
    words, then left by typing `/quit`, with keys every terminal delivers: the screen as it was then, and every byte it
    wrote. The terminal reads until the program has gone, as a real one does: one that stops reading blocks the
    program's writes, and Textual's exit waits for them."""
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
        while not all(said in _shown(screen) for said in (ESCAPED, "/ commands")) and time.monotonic() < deadline:
            if (chunk := _read(master, 1.0)) is None:
                break
            written += chunk
            stream.feed(chunk)
    finally:
        os.write(master, b"/quit\r")
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline and attached.poll() is None and (chunk := _read(master, 0.1)) is not None:
            written += chunk
        os.close(master)
        try:
            attached.wait(timeout=max(deadline - time.monotonic(), 0.1))
        except subprocess.TimeoutExpired:
            attached.kill()
            attached.wait()
            raise AssertionError(f"/quit left it running, on this screen:\n{_shown(screen)}") from None
    return screen, bytes(written)


async def test_no_escape_from_an_agent_ever_reaches_the_terminal(tmp_path):
    async with Session.start(hostile(), name="s", root=tmp_path, cwd=tmp_path) as owner:
        await in_state(owner, "lead", "idle")
        await owner.send("@lead", "go")
        await until(lambda: of_type(owner, "turn.ended"), owner)

    screen, written = await asyncio.to_thread(attached_in_a_pty, "s")
    shown = _shown(screen)

    assert ESCAPED in shown
    assert shown.splitlines()[-1].split()[:2] == ["/", "commands"]
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
    """Enter in the form goes to its next field, and from the last starts the session. Ctrl+D comes back to the
    sessions screen, and the session runs on."""
    (tmp_path / PROJECT_FILE).write_text(f'[roles.lead]\nharness = "{inside("saying")}"\n')
    app = TerminalUI()
    async with app.run_test(size=(120, 30)) as pilot:
        footer = (await drawn(pilot, lambda text: "No sessions yet" in text)).splitlines()[-1]
        assert "n new" in footer and "? help" in footer and "q quit" in footer

        await pilot.press("n")
        await pilot.pause()
        await pilot.press("enter", *"crew", "enter")
        assert not isinstance(app.screen, Workspace)
        await pilot.press(*"yes", "enter")
        await drawn(pilot, lambda text: "@lead" in text and " live " in text)

        folder = tmp_path / "sessions" / "crew"
        running = read_running(folder)
        assert running is not None and running.pid != os.getpid()
        await pilot.press("ctrl+d")
        await drawn(pilot, lambda text: "crew" in text and "Sessions" in text)
        assert isinstance(app.screen, Sessions) and is_held(folder)
        await pilot.press("ctrl+q")
    assert app.return_value is None and is_held(folder)


async def test_a_whole_session_takes_no_ctrl_alt_or_function_key(tmp_path):
    """Started from the sessions screen, a message sent, an approval answered from the dock reached by Shift+Tab, the
    agent interrupted, then detached and quit, with letters, Enter, Esc, Shift+Tab and the arrows alone, which every
    terminal delivers, as a terminal that keeps chords for itself, such as an editor's, does not."""
    (tmp_path / PROJECT_FILE).write_text(f'[roles.lead]\nharness = "{inside("asks_then_hangs")}"\n')
    folder = tmp_path / "sessions" / "crew"
    app = TerminalUI()
    async with app.run_test(size=(120, 30)) as pilot:
        await drawn(pilot, lambda text: "No sessions yet" in text)
        await pilot.press("n")
        await pilot.pause()
        await pilot.press("enter", *"crew", "enter", *"yes", "enter")
        await drawn(pilot, lambda text: "@lead" in text and " live " in text)
        guest = await Session.attach("crew")

        await pilot.press(*"ship it", "enter")
        await drawn(pilot, lambda text: "Ship the fix?" in text)
        await pilot.press("shift+tab", "down")
        await drawn(pilot, lambda text: "y Allow" in text and "n Deny" in text)
        await pilot.press("y")
        resolved = await until(lambda: of_type(guest, "approval.resolved"), guest)
        assert [(event.data["verdict"], event.data["via"]) for event in resolved] == [("allow", "tui")]
        await drawn(pilot, lambda _: app.focused is workspace(app).query_one(Composer))
        await in_state(guest, "lead", "running")

        await pilot.press("escape")
        ended = await until(lambda: of_type(guest, "turn.ended"), guest)
        assert [event.data["reason"] for event in ended] == ["interrupted"]

        await pilot.press(*"/detach", "enter")
        await drawn(pilot, lambda text: "crew" in text and "Sessions" in text)
        assert isinstance(app.screen, Sessions) and is_held(folder)
        await pilot.press("q")

    assert app.return_value is None and is_held(folder)
    sent = [event.gist for event in await of_type(guest, "message.sent") if event.actor == "human:you"]
    assert sent == ["ship it"], "a typed command reached an agent"
    await guest.leave()


async def test_several_agents_on_a_plan_login_are_asked_about_once_and_the_answer_is_plan_login(tmp_path):
    (tmp_path / PROJECT_FILE).write_text(f'[roles.lead]\nharness = "{inside("planned")}"\ncount = 2\n')
    app = TerminalUI()
    async with app.run_test(size=(120, 30)) as pilot:
        await drawn(pilot, lambda text: "No sessions yet" in text)
        await pilot.press("n")
        await pilot.pause()
        await pilot.press("tab", *"crew", "tab", *"yes", "enter")
        text = await drawn(pilot, lambda text: "your own work?" in text)
        assert "lead would run several agents headless on one plan login" in text

        await pilot.press("y")
        await drawn(pilot, lambda text: "@lead-1" in text and "@lead-2" in text)
        await pilot.press("ctrl+q")

    manifest = Manifest.model_validate_json((tmp_path / "sessions" / "crew" / "manifest.json").read_bytes())
    assert manifest.plan_login is True


async def test_a_team_left_to_its_program_is_refused_from_the_sessions_screen_naming_the_script_way(tmp_path):
    """The terminal UI starts a session as a person, and `until = "program"` leaves one to a program."""
    (tmp_path / PROJECT_FILE).write_text(
        f'[roles.lead]\nharness = "{inside("saying")}"\n[topology]\nuntil = "program"\n'
    )
    script_way = 'start it from a script, with `Session.start(team, principal="program:<name>")`'
    app = TerminalUI()
    async with app.run_test(size=(120, 30)) as pilot:
        await drawn(pilot, lambda text: "No sessions yet" in text)
        await pilot.press("n")
        await pilot.pause()
        await pilot.press("tab", *"crew", "tab", *"yes", "enter")
        await drawn(pilot, lambda _: any(script_way in str(notice.message) for notice in app._notifications))
        assert isinstance(app.screen, Sessions)
        await pilot.press("ctrl+q")

    assert not (tmp_path / "sessions" / "crew").exists()


async def test_stopping_a_session_takes_one_confirmation_and_resuming_says_it_can_spend_money(tmp_path):
    guest = await Session.start(saying(), name="s", root=tmp_path, detach=True)
    await in_state(guest, "lead", "idle")
    await guest.leave()
    folder = tmp_path / "sessions" / "s"
    (tmp_path / PROJECT_FILE).write_text(f'[roles.lead]\nharness = "{inside("saying")}"\n')
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


def on_path(monkeypatch: pytest.MonkeyPatch, folder: Path, *names: str) -> None:
    """Harnesses on PATH that each say a version and exit at once, which none can start on, and nothing else on it but
    the system's own."""
    found = folder / "bin"
    found.mkdir(exist_ok=True)
    for name in names:
        (found / name).write_text('#!/bin/sh\n[ "$1" = --version ] && echo "9.9.9 (fake)"\nexit 0\n')
        (found / name).chmod(0o755)
    monkeypatch.setenv("PATH", f"{found}:/usr/bin:/bin")


def asked(app: TerminalUI) -> str:
    """The question open over the screen, whole however its dialog wraps it, or nothing."""
    screen = app.screen
    if not isinstance(screen, Confirm):
        return ""
    question = screen.query(Static).first().content
    return question.plain if isinstance(question, Content) else str(question)


def settled(app: TerminalUI) -> bool:
    """The sessions screen shows, with nothing it set going still under way: no look, and no offer."""
    return isinstance(app.screen, Sessions) and all(worker.is_finished for worker in app.workers)


OFFER = "No team is in {}. Write platoon-harness.toml there from the harnesses on PATH: {}?"


async def test_with_no_team_the_sessions_screen_offers_once_to_write_one_from_the_harnesses_on_path(
    tmp_path, monkeypatch
):
    """With none on PATH it says so and asks nothing. Turned down, it is not offered again as the screen looks again or
    comes back to the top. Taken, as the screen opens anew, it writes what `init` writes, and the screen starts
    sessions from that."""
    project = tmp_path / PROJECT_FILE
    on_path(monkeypatch, tmp_path)
    app = TerminalUI()
    async with app.run_test(size=(120, 30)) as pilot:
        await drawn(pilot, lambda text: "No sessions yet" in text and settled(app))
        said = f"No team is in {tmp_path}, and none can be written there: none is on PATH: install one of "
        assert [notice.message for notice in app._notifications] == [said + "claude, codex, pi"]
        await pilot.press("ctrl+q")

    on_path(monkeypatch, tmp_path, "claude", "codex")
    app = TerminalUI()
    async with app.run_test(size=(120, 30)) as pilot:
        await drawn(pilot, lambda _: asked(app))
        assert asked(app) == OFFER.format(tmp_path, "a lead on claude, which starts workers on codex")

        await pilot.press("n")
        await drawn(pilot, lambda text: "No sessions yet. n starts one from a team file." in text and settled(app))
        await pilot.press("l")
        await drawn(pilot, lambda _: settled(app))
        await pilot.press("question_mark")
        await drawn(pilot, lambda _: isinstance(app.screen, Help))
        await pilot.press("escape")
        await drawn(pilot, lambda _: settled(app))
        assert not project.exists(follow_symlinks=False)
        await pilot.press("ctrl+q")

    app = TerminalUI()
    async with app.run_test(size=(120, 30)) as pilot:
        await drawn(pilot, lambda _: asked(app))
        await pilot.press("y")
        await drawn(pilot, lambda text: "No sessions yet. n starts one from platoon-harness.toml." in text)
        said = (
            "Wrote platoon-harness.toml: a lead on claude, which starts workers on codex. n starts a session from it."
        )
        assert said in [notice.message for notice in app._notifications]
        await pilot.press("ctrl+q")

    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    assert machine.init() == 0
    assert (elsewhere / PROJECT_FILE).read_text() == project.read_text()


@pytest.mark.parametrize("planted", ["file", "link"])
async def test_writing_a_team_from_the_tui_never_overwrites_nor_writes_through_a_link(tmp_path, monkeypatch, planted):
    """A file, or a link to a file that is not there, put where the team goes while the offer is open, stays as it
    was, and the link makes no file. Once anything is there, nothing is offered."""
    on_path(monkeypatch, tmp_path, "claude")
    project, linked = tmp_path / PROJECT_FILE, tmp_path / "linked.toml"
    app = TerminalUI()
    async with app.run_test(size=(120, 30)) as pilot:
        await drawn(pilot, lambda _: asked(app))
        if planted == "file":
            project.write_text("# mine\n")
        else:
            project.symlink_to(linked)
        await pilot.press("y")
        await drawn(pilot, lambda _: settled(app))
        notices = [notice.message for notice in app._notifications]
        assert f"Nothing was written, as something is at {PROJECT_FILE} now" in "".join(notices), notices
        await pilot.press("ctrl+q")

    assert not linked.exists(follow_symlinks=False)
    assert project.readlink() == linked if planted == "link" else project.read_text() == "# mine\n"

    app = TerminalUI()
    async with app.run_test(size=(120, 30)) as pilot:
        await drawn(pilot, lambda text: "No sessions yet" in text and settled(app))
        assert not app._notifications
        await pilot.press("ctrl+q")


@pytest.mark.parametrize("found", [True, False], ids=["exiting-at-once", "not-on-path"])
async def test_a_harness_that_cannot_start_says_what_doctor_finds(tmp_path, monkeypatch, found):
    """A lead on `claude`, which says its version and exits at once, or which is not on PATH: the session starts from
    the project's team, its lead fails, and the person is told what `platoon-harness doctor` says of claude, in its
    words."""
    on_path(monkeypatch, tmp_path, *(["claude"] if found else []))
    (tmp_path / PROJECT_FILE).write_text('[roles.lead]\nharness = "claude"\n')
    doctor = [Path(sys.executable).parent / "platoon-harness", "doctor"]
    said = (await asyncio.to_thread(subprocess.run, doctor, capture_output=True, text=True, timeout=60)).stdout
    claude = " ".join(next(line for line in said.splitlines() if line.startswith("claude ")).split(maxsplit=1))
    app = TerminalUI()
    async with app.run_test(size=(120, 30)) as pilot:
        await drawn(pilot, lambda text: "No sessions yet" in text)
        await pilot.press("n")
        await pilot.pause()
        await pilot.press("enter", *"crew", "enter", "enter")
        told = f"@lead could not start, and doctor, run here, finds {claude}"
        await drawn(pilot, lambda text: "lead failed" in text and told in [n.message for n in app._notifications])
        await pilot.press("ctrl+q")

    assert claude.startswith("claude 9.9.9 (fake), login unknown, not checked" if found else "claude not on PATH")


def test_a_terminal_ui_that_fails_exits_1(monkeypatch):
    """Textual shows what went wrong, and the command says it failed, as any refused command does."""
    from platoon_harness_cli import tui

    def failing(app, **_):
        app._return_code = 1

    monkeypatch.setattr(TerminalUI, "run", failing)

    assert tui.run("s") == 1
