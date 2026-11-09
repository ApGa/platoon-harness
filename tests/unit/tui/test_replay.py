"""A replay in the terminal: drawn as its session is, from a copy of its record that grows as it plays, under a banner
saying it is one, with its controls on keys where nothing is typed and as typed commands, and nothing in it acting."""

import asyncio
from pathlib import Path

import pytest

from platoon_harness import Session
from platoon_harness.config import PROJECT_FILE
from platoon_harness.kernel import ManualClock
from platoon_harness.testing import Say
from platoon_harness_cli import replay as replay_module
from platoon_harness_cli.replay import nothing_acts, reads_no_diff
from platoon_harness_cli.tui.app import TerminalUI
from platoon_harness_cli.tui.composer import Composer
from platoon_harness_cli.tui.dialogs import Form
from platoon_harness_cli.tui.provenance import Provenance
from platoon_harness_cli.tui.review import Review
from platoon_harness_cli.tui.rows import Rows
from platoon_harness_cli.tui.sessions import Sessions
from platoon_harness_cli.tui.transcript import Transcript
from platoon_harness_cli.tui.workspace import Workspace

from ...recorded import RECORDED, restored
from ..runtime.support import in_state, of_type, solo, until
from .support import drawn, screen_text, workspace

pytestmark = pytest.mark.timeout(90)

CREDIT = {"kind": "credit", "producer": "even-split", "producer_version": "1", "scope": "local"}


@pytest.fixture(autouse=True)
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("PLATOON_HARNESS_HOME", str(tmp_path))
    return tmp_path


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> ManualClock:
    """The clock the replay plays by, which moves only when told to."""
    clock = ManualClock(0.0)
    monkeypatch.setattr(replay_module, "SystemClock", lambda: clock)
    return clock


async def recorded(root: Path) -> int:
    """A closed session `s` whose `bob` answered two messages, a turn each, sent a minute apart by the clock its
    runtime keeps, and its head."""
    team, runtime = solo([Say("on it")], [Say("shipped")]), ManualClock(1_000_000.0)
    async with Session.start(team, name="s", root=root, cwd=root, clock=runtime) as session:
        await in_state(session, "bob", "idle")
        for count, words in enumerate(("fix the flaky test", "and ship it"), 1):
            runtime.advance(60.0)
            await session.send("@bob", words)
            await until(lambda: of_type(session, "turn.ended"), session, lambda ended, count=count: len(ended) == count)
    async with Session.attach("s", root=root) as history:
        return await history.head()


def told(app: TerminalUI, said: str) -> int:
    return sum(said in notice.message for notice in app._notifications)


async def jump(pilot, where: str) -> None:
    """Jump through `j`'s form, from the transcript, where nothing is typed."""
    pilot.app.screen.query_one(Transcript).focus()
    await pilot.press("j")
    await drawn(pilot, lambda _: isinstance(pilot.app.screen, Form))
    await pilot.press(*where, "enter")


async def test_a_replay_is_drawn_as_its_session_from_its_start_under_a_banner_saying_so(root):
    head = await recorded(root)
    app = TerminalUI("s", replay=True)
    async with app.run_test(size=(120, 32)) as pilot:
        text = await drawn(pilot, lambda text: "Replay of s, before its first event" in text)
        assert "replay · " in text and "no agents yet" in text and "on it ▸" not in text
        assert app.focused is app.screen.query_one(Transcript)

        await jump(pilot, str(head))
        text = await drawn(pilot, lambda text: f"at event {head:,} of {head:,}" in text and "shipped" in text)
        assert "@bob" in text and "fix the flaky test" in text and "Nothing here acts on the session." in text


@pytest.mark.parametrize("size", [(50, 30), (120, 14), (50, 14)], ids=["narrow", "short", "narrow-and-short"])
async def test_the_banner_says_it_is_a_replay_at_every_size(root, size):
    await recorded(root)
    app = TerminalUI("s", replay=True)
    async with app.run_test(size=size) as pilot:
        await drawn(pilot, lambda text: "Replay of s, before" in text)


async def test_the_replay_s_controls_are_keys_where_nothing_is_typed_and_typed_commands(root, clock):
    head = await recorded(root)
    async with Session.attach("s", root=root) as history:
        first, second = (event.seq for event in await of_type(history, "turn.ended"))
    app = TerminalUI("s", replay=True)
    async with app.run_test(size=(120, 32)) as pilot:
        await drawn(pilot, lambda text: "before its first event" in text)
        await pilot.press("full_stop", "full_stop")
        await drawn(pilot, lambda text: "at event 2 of" in text)
        await pilot.press("comma")
        await drawn(pilot, lambda text: "at event 1 of" in text)
        await pilot.press("right_square_bracket")
        ended = await drawn(pilot, lambda text: f"at event {first} of" in text and "on it ▸" in text)
        assert "shipped ▸" not in ended and "paused" in ended

        app.screen.query_one(Composer).focus()
        await pilot.press(*"/turn", "enter")
        await drawn(pilot, lambda text: f"at event {second} of" in text and "shipped ▸" in text)
        await pilot.press(*"/turn-back", "enter")
        await drawn(pilot, lambda text: f"at event {first} of" in text and "shipped ▸" not in text)
        await pilot.press(*"/speed", "enter")
        await pilot.press(*"/play", "enter")
        await drawn(pilot, lambda text: "playing at 4x" in text)
        await clock.slept_until(15.0)
        clock.advance(15.0)
        await drawn(pilot, lambda text: f"at event {head} of {head}" in text and "paused" in text)
        app.screen.query_one(Transcript).focus()
        await pilot.press("space")
        await drawn(pilot, lambda text: "playing at 4x" in text and "shipped ▸" not in text)
        await pilot.press("space")
        await drawn(pilot, lambda text: "paused" in text)


async def test_nothing_in_a_replay_acts_and_each_act_says_why(root):
    head = await recorded(root)
    app = TerminalUI("s", replay=True)
    async with app.run_test(size=(120, 32)) as pilot:
        await drawn(pilot, lambda text: "before its first event" in text)
        await jump(pilot, str(head))
        await drawn(pilot, lambda text: "shipped" in text)
        why = nothing_acts("s")
        assert why in app.screen.query_one("#chip").render().plain

        app.screen.query_one(Composer).focus()
        await pilot.press(*"go again", "enter")
        await drawn(pilot, lambda _: told(app, why) == 1)
        await pilot.press(*["backspace"] * 8)
        for act in ("/interrupt", "/resume", "/file", "/yes"):
            await pilot.press(*act, "enter")
            await drawn(pilot, lambda _, act=act: told(app, f"{act[1:]}: {why}") == 1)
        assert not any(title.startswith("agent ") for title, _, _ in workspace(app).commands())

    async with Session.attach("s", root=root) as history:
        assert await history.head() == head


async def test_a_diff_in_a_replay_says_why_it_opens_nothing_before_anything_opens(root):
    name = restored(RECORDED, root)
    app = TerminalUI(name, replay=True)
    async with app.run_test(size=(160, 40)) as pilot:
        await drawn(pilot, lambda text: "before its first event" in text)
        await jump(pilot, "999999")
        await drawn(pilot, lambda text: "at event 345 of 345" in text)
        await pilot.press("alt+d")
        await drawn(pilot, lambda text: isinstance(app.screen, Review) and "tally/money.py" in text)
        rows = app.screen.query_one(Rows)
        rows.focus()
        rows.move_to("path/shared/tally/money.py")
        await pilot.press("enter")
        await drawn(pilot, lambda _: told(app, reads_no_diff(name)) == 1)

        assert isinstance(app.screen, Review)
        assert reads_no_diff(name).startswith("A replay reads no diff, as asking for one is an act. A replay acts")


async def test_going_back_draws_the_copy_anew_keeping_the_agent_in_view(root):
    head = await recorded(root)
    app = TerminalUI("s", replay=True)
    async with app.run_test(size=(120, 32)) as pilot:
        await drawn(pilot, lambda text: "before its first event" in text)
        await jump(pilot, str(head))
        await drawn(pilot, lambda text: "shipped" in text)
        screen, before = app.screen, workspace(app).live
        assert before is not None and screen.focus_on is not None and screen.focus_on.key == "@bob"

        app.screen.query_one(Transcript).focus()
        await pilot.press("left_square_bracket", "left_square_bracket")
        text = await drawn(pilot, lambda text: "on it" in text and "shipped" not in text)

        assert app.screen is screen and workspace(app).live is not before
        assert workspace(app).focus_on is not None and workspace(app).focus_on.key == "@bob"
        assert "@bob · bob on" in text


async def test_going_back_never_draws_the_copy_left_behind_under_a_banner_naming_where_the_replay_went(
    root, monkeypatch
):
    """Until the copy started anew is drawn, the screen goes on naming where the copy it shows stands, though it is
    drawn again meanwhile."""
    head = await recorded(root)
    joined, rejoin = asyncio.Event(), Workspace._rejoin

    async def held(self: Workspace) -> None:
        await joined.wait()
        await rejoin(self)

    monkeypatch.setattr(Workspace, "_rejoin", held)
    app = TerminalUI("s", replay=True)
    async with app.run_test(size=(120, 32)) as pilot:
        await drawn(pilot, lambda text: "before its first event" in text)
        await jump(pilot, str(head))
        await drawn(pilot, lambda text: f"at event {head:,} of" in text and "shipped" in text)
        screen = workspace(app)
        assert screen.player is not None

        await screen.player.go(1)
        screen._redraw()
        await pilot.pause()
        text = screen_text(app)
        assert "shipped" in text and f"at event {head:,} of" in text and "at event 1 of" not in text

        joined.set()
        await drawn(pilot, lambda text: "at event 1 of" in text and "shipped" not in text)


async def test_an_estimate_shown_in_a_replay_says_when_it_was_written(root):
    head = await recorded(root)
    async with Session.attach("s", root=root) as history:
        said = next(event for event in await of_type(history, "item.recorded") if event.gist == "on it")
        target = f"{said.stream}@{said.version}"
        await history.annotate(target, status="scored", value=0.5, head_seq=head, **CREDIT)
    app = TerminalUI("s", replay=True)
    async with app.run_test(size=(120, 40)) as pilot:
        await drawn(pilot, lambda text: "before its first event" in text)
        await jump(pilot, str(said.seq))
        await drawn(pilot, lambda text: "on it" in text)
        transcript = app.screen.query_one(Transcript)
        transcript.focus()
        await pilot.press("p")
        await drawn(pilot, lambda _: isinstance(app.screen, Provenance))
        panel = app.screen
        assert isinstance(panel, Provenance)
        text = await drawn(pilot, lambda _: any("written" in line.text for line in panel.lines))

        line = next(line for line in panel.lines if line.kind == "credit")
        assert (
            "0.5 by even-split" in line.text and "after this point of the replay, so it was not known here" in line.text
        )
        assert line.warn and "Credit and rewards" in text


async def test_the_sessions_screen_replays_the_chosen_session_and_leaving_takes_its_copies_back(root, monkeypatch):
    await recorded(root)
    monkeypatch.chdir(root)
    (root / PROJECT_FILE).write_text("")
    app = TerminalUI()
    async with app.run_test(size=(120, 32)) as pilot:
        await drawn(pilot, lambda text: "○ history" in text)
        await pilot.press("R")
        await drawn(pilot, lambda text: "Replay of s, before its first event" in text)
        assert isinstance(app.screen, Workspace) and app.screen.replaying
        assert list((root / "replays").iterdir())
        await pilot.press("ctrl+d")
        await drawn(pilot, lambda _: isinstance(app.screen, Sessions))
        await drawn(pilot, lambda _: not list((root / "replays").iterdir()))
