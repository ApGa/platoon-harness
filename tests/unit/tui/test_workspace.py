"""The workspace on scripted harnesses: a session the test owns, and the TUI attached to it as a guest over its
socket."""

import asyncio
import contextlib
import time
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from rich.cells import cell_len

from platoon_harness import Session, Team
from platoon_harness.testing import Ask, Call, Hang, Say, ScriptedDriver
from platoon_harness_cli.ops import _command, person_ops
from platoon_harness_cli.tui import live as live_module
from platoon_harness_cli.tui import transcript as transcript_module
from platoon_harness_cli.tui.app import Harness
from platoon_harness_cli.tui.composer import Composer
from platoon_harness_cli.tui.keymap import keys
from platoon_harness_cli.tui.transcript import Transcript

from ..runtime.support import harness, in_state, of_type, until
from .support import drawn, workspace

pytestmark = pytest.mark.timeout(60)


@pytest.fixture(autouse=True)
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("PLATOON_HARNESS_HOME", str(tmp_path))
    return tmp_path


def team(*turns, **roles) -> Team:
    """`lead`, the one agent the session starts, on a scripted harness, and any other roles."""
    lead = {"harness": harness(lambda: ScriptedDriver(turns)), "may_spawn": list(roles)}
    others = {
        name: {"harness": harness(lambda turns=turns: ScriptedDriver(turns)), "count": 0}
        for name, turns in roles.items()
    }
    topology = {"edges": {"lead": ["children", "human"]}, "limits": {"max_depth": 2}}
    return Team.model_validate({"roles": {"lead": lead, **others}, "topology": topology})


@contextlib.asynccontextmanager
async def attached(team: Team, root: Path, *, size=(120, 32)) -> AsyncIterator[tuple[Session, Harness, object]]:
    """A session the test owns, with `lead` up, and the TUI attached to it."""
    async with Session.start(team, name="s", root=root, cwd=root) as owner:
        await in_state(owner, "lead", "idle")
        app = Harness("s")
        async with app.run_test(size=size) as pilot:
            await drawn(pilot, lambda text: "@lead" in text)
            yield owner, app, pilot


async def test_a_message_from_the_composer_reaches_the_target_shown_once(root):
    async with attached(team([Say("on it")]), root) as (owner, app, pilot):
        assert app.focused is app.screen.query_one(Composer)

        await pilot.press(*"fix the flaky test", "enter")
        await drawn(pilot, lambda text: "@lead  on it" in text)

        sent = [event for event in await of_type(owner, "message.sent") if event.actor == "human:you"]
        assert [(event.stream, event.gist) for event in sent] == [("inbox/lead", "fix the flaky test")]
        lines = [block.line.plain for block in app.screen.query_one(Transcript).blocks]
        assert sum("fix the flaky test" in line for line in lines) == 1
        assert app.screen.query_one(Composer).text == ""


async def test_an_approval_never_takes_focus_so_a_key_meant_for_the_composer_never_answers_it(root):
    async with attached(team([Ask("Ship the fix?"), Say("shipped")]), root) as (owner, app, pilot):
        await pilot.press(*"go", "enter")
        await drawn(pilot, lambda text: "Ship the fix?" in text)
        composer = app.screen.query_one(Composer)

        await pilot.press(*"yes", "y", "n")

        assert app.focused is composer and composer.text == "yesyn"
        assert await of_type(owner, "approval.resolved") == []

        await pilot.press("alt+y")
        await drawn(pilot, lambda text: "shipped" in text)

        resolved = await of_type(owner, "approval.resolved")
        assert [(event.data["verdict"], event.data["via"]) for event in resolved] == [("allow", "tui")]
        assert app.focused is composer


async def test_a_second_client_s_answer_shows_as_theirs_and_its_message_shows_once(root):
    async with attached(team([Ask("Ship the fix?"), Say("shipped")]), root) as (owner, app, pilot):
        await pilot.press(*"go", "enter")
        await drawn(pilot, lambda text: "Ship the fix?" in text)
        second = await Session.attach("s", root=root)
        asked = (await second.approvals())[0]

        await asyncio.gather(
            second.resolve(asked["id"], "deny", expected_version=asked["version"], via="web"),
            second.send("@lead", "from the browser"),
        )
        await pilot.press("alt+y")
        await drawn(pilot, lambda text: "from the browser" in text)

        resolved = await of_type(owner, "approval.resolved")
        assert [(event.data["verdict"], event.data["via"]) for event in resolved] == [("deny", "web")]
        lines = [block.line.plain for block in app.screen.query_one(Transcript).blocks]
        assert sum("from the browser" in line for line in lines) == 1
        shown = [notice.message for notice in app._notifications]
        assert not any("conflict" in said for said in shown)
        await second.leave()


async def test_esc_interrupts_the_agent_in_view_and_is_disabled_with_the_runtime_s_reason_when_it_would_stop_nothing(
    root,
):
    async with attached(team([Hang()], [Say("again")]), root) as (owner, _, pilot):
        await pilot.press(*"go", "enter")
        await in_state(owner, "lead", "running")

        await pilot.press("escape")
        ended = await until(lambda: of_type(owner, "turn.ended"), owner)
        assert [event.data["reason"] for event in ended] == ["interrupted"]
        await in_state(owner, "lead", "idle")
        await drawn(pilot, lambda text: "turn interrupted" in text)

        await pilot.press("escape")
        text = await drawn(pilot, lambda text: "neither in a turn" in text)
        assert "interrupt:" in text

        await pilot.press(*"again", "enter")
        await drawn(pilot, lambda text: "@lead  again" in text and "neither in a turn" not in text)


async def test_stop_below_stops_the_turns_below_the_agent_in_view_and_says_it_stops_turns_not_waits(root):
    spawning = [Call("agent_spawn", {"name": "w", "child_role": "worker", "goal": "work"}), Hang()]
    async with attached(team(spawning, worker=[[Hang()]]), root) as (owner, app, pilot):
        await pilot.press(*"go", "enter")
        await in_state(owner, "w", "running")

        await pilot.press("alt+s")
        ended = await until(lambda: of_type(owner, "turn.ended"), owner, lambda found: len(found) == 2)

        assert {event.agent: event.data["reason"] for event in ended} == {"lead": "interrupted", "w": "interrupted"}
        notices = [notice.message for notice in app._notifications]
        assert any("It stops turns, not waits" in said for said in notices)


def with_notes(base: Team) -> Team:
    """`base`, with a topic `notes` that wakes nobody, for a long history that costs no turn."""
    given = base.canonical()
    channels = {"notes": {"kind": "topic", "writers": "all", "readers": "all", "delivery": "pull"}}
    topology = {**given.get("topology", {}), "channels": channels}
    return Team.model_validate({**given, "topology": topology})


async def post(session: Session, count: int, start: int = 0) -> None:
    """Post notes 30 at a time, within what one principal may have in flight."""
    for first in range(start, start + count, 30):
        last = min(first + 30, start + count)
        await asyncio.gather(*(session.send("#notes", f"note {n}") for n in range(first, last)))


async def show_notes(pilot) -> Transcript:
    await pilot.press("alt+down", "alt+down")
    await drawn(pilot, lambda text: "#notes" in text.splitlines()[1])
    return pilot.app.screen.query_one(Transcript)


def top_line(transcript: Transcript) -> str:
    return transcript.render_line(0).text


async def test_a_history_far_larger_than_the_screen_is_read_back_a_page_at_a_time(root):
    async with Session.start(with_notes(team()), name="s", root=root, cwd=root) as owner:
        await post(owner, 1500)
        await in_state(owner, "lead", "idle")
        app = Harness("s")
        async with app.run_test(size=(120, 32)) as pilot:
            await drawn(pilot, lambda text: "@lead" in text)
            transcript = await show_notes(pilot)
            await drawn(pilot, lambda text: "note 1499" in text)
            assert len(transcript.blocks) <= 2 * 256

            await pilot.press("pageup")
            while transcript.blocks[0].event.gist != "note 0":
                loaded = len(transcript.blocks)
                transcript.scroll_to(y=0, animate=False, immediate=True)
                oldest = top_line(transcript)
                await drawn(pilot, lambda text, loaded=loaded: len(transcript.blocks) > loaded)
                assert top_line(transcript) == oldest, "a page read back moved what was on screen"

            assert [block.event.gist for block in transcript.blocks] == [f"note {n}" for n in range(1500)]


async def test_scroll_is_kept_while_reading_and_what_comes_is_counted_until_the_person_follows_again(root):
    async with Session.start(with_notes(team()), name="s", root=root, cwd=root) as owner:
        await post(owner, 300)
        await in_state(owner, "lead", "idle")
        app = Harness("s")
        async with app.run_test(size=(120, 32)) as pilot:
            await drawn(pilot, lambda text: "@lead" in text)
            transcript = await show_notes(pilot)
            await drawn(pilot, lambda text: "note 299" in text)

            await pilot.press("pageup", "pageup")
            await pilot.pause()
            reading = top_line(transcript)
            assert not transcript.following

            await post(owner, 7, start=300)
            await drawn(pilot, lambda text: "7 new" in text)
            assert top_line(transcript) == reading

            await pilot.press("ctrl+end")
            await drawn(pilot, lambda text: "note 306" in text)
            assert transcript.following and transcript.unseen == 0


SIZES = [(120, 32), (100, 30), (79, 24), (59, 20), (100, 15), (45, 12), (120, 32)]


@pytest.mark.parametrize("reading", [False, True], ids=["following", "reading"])
async def test_a_resize_never_changes_scroll_position_focus_or_the_composer_s_target(root, reading):
    async with Session.start(with_notes(team()), name="s", root=root, cwd=root) as owner:
        await post(owner, 200)
        await in_state(owner, "lead", "idle")
        app = Harness("s")
        async with app.run_test(size=SIZES[0]) as pilot:
            await drawn(pilot, lambda text: "@lead" in text)
            transcript = await show_notes(pilot)
            await drawn(pilot, lambda text: "note 199" in text)
            if reading:
                await pilot.press("pageup", "pageup")
            await pilot.press(*"half a thought")
            screen = workspace(app)
            before = (top_line(transcript).strip(), app.focused, screen.target, transcript.following)

            for width, height in SIZES[1:]:
                await pilot.resize_terminal(width, height)
                text = await drawn(pilot, lambda text, width=width: len(text.splitlines()[0]) == width)

                assert app.focused is before[1] and screen.target == before[2] and transcript.following == before[3]
                assert screen.query_one("#navigator").display == (width >= 80)
                assert screen.query_one("#dock").display is False or height >= 16
                assert "need you" in text.splitlines()[0] or width < 60
                if reading:
                    assert top_line(transcript).strip() == before[0]
                else:
                    assert transcript.scroll_y == transcript.max_scroll_y
            assert screen.query_one(Composer).text == "half a thought"


async def test_wide_combining_emoji_and_right_to_left_text_keeps_every_line_its_width(root):
    said = ["中文の行 全角", "é combining", "family 👨‍👩‍👧 and 🇯🇵", "שלום עולם and مرحبا"]
    async with attached(team([Say(text) for text in said]), root, size=(61, 24)) as (_, app, pilot):
        await pilot.press(*"go", "enter")
        text = await drawn(pilot, lambda text: "שלום עולם" in text)

        for line in said:
            assert line.split()[0] in text
        transcript = app.screen.query_one(Transcript)
        width = transcript.scrollable_content_region.width
        assert all(transcript.render_line(y).cell_length == width for y in range(transcript.size.height))
        assert all(cell_len(row) == 61 for row in text.splitlines())


HOSTILE = "\x1b]0;owned\x1b\\ \x1b[2J \x9b31m ‮evil‬ [/x] [@click=app.quit]x[/] \x1b]52;c;ZXZpbA==\x07"
UNSAFE = [chr(code) for code in (*range(0x09), *range(0x0B, 0x20), 0x7F, *range(0x80, 0xA0), 0x202E, 0x202C)]


async def test_hostile_text_from_an_agent_reaches_no_renderer_unescaped(root):
    hostile = team([Say(HOSTILE), Call("message_send", {"to": "@you", "gist": HOSTILE}), Ask(HOSTILE)])
    async with attached(hostile, root) as (_, app, pilot):
        await pilot.press(*"go", "enter")
        await drawn(pilot, lambda text: text.count("\\x1b]0;owned") >= 2)
        await pilot.press("f2")
        await pilot.press("ctrl+o")
        await pilot.press("alt+down")
        text = await drawn(pilot, lambda text: "\\u202eevil" in text)

        assert app.is_running
        assert not [char for char in UNSAFE if char in text]
        assert "[/x]" in text and "[@click=app.quit]x[/]" in text
        await pilot.press("ctrl+p")
        await pilot.press(*"agent")
        await pilot.press("escape")
        assert app.is_running


async def test_a_slow_screen_drops_frames_and_never_events(root, monkeypatch):
    monkeypatch.setattr(live_module, "PENDING", 64)
    async with attached(with_notes(team()), root) as (owner, app, _):
        live = workspace(app).live
        assert live is not None
        draw, sizes, seen, gate = live._draw, [], [], asyncio.Event()

        async def slow(events, deltas):
            sizes.append(len(events))
            seen.extend(event.seq for event in events)
            await gate.wait()
            await draw(events, deltas)

        live._draw = slow
        after, frames, began = live._read_through, live.frames, time.monotonic()
        await post(owner, 600)
        head = await owner.head()
        gate.set()
        while not seen or seen[-1] < head:
            await live.next_frame(live.frames)
        spent = time.monotonic() - began

        assert seen == [event.seq async for event in owner.events(seen[0] - 1)] and seen[0] <= after + 1
        assert max(sizes) <= 64
        assert live.frames - frames <= spent * 15 + 2
        assert live.frames - frames < len(seen) / 10


async def test_the_palette_s_session_commands_are_the_command_line_s_worded_for_a_person(root):
    async with attached(team(), root) as (owner, app, pilot):
        commands = {title: said for title, said, _ in workspace(app).commands()}
        for name, operation in person_ops().items():
            assert commands[name.replace(".", " ")] == _command(operation).__doc__.split("\n\n")[0]

        await pilot.press("ctrl+p", *"agent retire")
        await pilot.press("enter")
        await drawn(pilot, lambda text: "agent:" in text)
        await pilot.press("enter")
        await drawn(pilot, lambda text: "cannot be taken back" in text)
        await pilot.press("y")
        ended = await until(lambda: of_type(owner, "agent.ended"), owner)

        assert [(event.agent, event.data["status"]) for event in ended] == [("lead", "retired")]


async def test_the_footer_is_the_keymap_table_s(root):
    async with attached(team(), root) as (_, _, pilot):
        footer = (await drawn(pilot, lambda text: "help" in text)).splitlines()[-1]

        for key in (*keys("everywhere"), *keys("workspace")):
            assert (f"{key.shown} {key.name}" in footer) == key.footer


async def test_a_transcript_holds_a_window_of_lines_read_from_the_journal_either_way(root, monkeypatch):
    monkeypatch.setattr(transcript_module, "WINDOW", 600)
    async with Session.start(with_notes(team()), name="s", root=root, cwd=root) as owner:
        await post(owner, 1500)
        await in_state(owner, "lead", "idle")
        app = Harness("s")
        async with app.run_test(size=(120, 32)) as pilot:
            await drawn(pilot, lambda text: "@lead" in text)
            transcript = await show_notes(pilot)
            await drawn(pilot, lambda text: "note 1499" in text)

            await pilot.press("pageup")
            while transcript.blocks[0].event.gist != "note 0":
                transcript.scroll_to(y=0, animate=False, immediate=True, force=True)
                oldest = top_line(transcript)
                await drawn(pilot, lambda text, oldest=oldest: top_line(transcript) == oldest)
                assert len(transcript.blocks) <= 600
            assert transcript.blocks[-1].event.gist == "note 599"

            await post(owner, 5, start=1500)
            while not transcript.following:
                await pilot.press("pagedown", "pagedown", "pagedown", "pagedown")
                await drawn(pilot, lambda text: True)
                assert len(transcript.blocks) <= 600
            assert transcript.blocks[-1].event.gist == "note 1504"

            await pilot.press("pageup", "pageup")
            await pilot.press("ctrl+end")
            await drawn(pilot, lambda text: "note 1504" in text)
            assert transcript.following

            await post(owner, 700, start=1505)
            await drawn(pilot, lambda text: "note 2204" in text)
            assert len(transcript.blocks) <= 600


async def test_the_composer_retargets_recalls_attaches_a_file_and_asks_before_sending_elsewhere(root, tmp_path):
    attachment = tmp_path / "spec.md"
    attachment.write_text("# The spec\n\nAll of it.")
    async with attached(with_notes(team([Say("one")], [Say("two")], [Say("three")])), root) as (owner, app, pilot):
        screen = workspace(app)
        await pilot.press(*"#notes ", *"for the channel", "enter")
        await drawn(pilot, lambda text: "to: #notes" in text)
        assert screen.target == "#notes"

        await pilot.press("up")
        assert screen.query_one(Composer).text == "for the channel"
        await pilot.press("down")
        assert screen.query_one(Composer).text == ""

        await pilot.press("alt+f")
        await pilot.press(*str(attachment), "enter")
        await drawn(pilot, lambda text: "+ spec.md" in text)
        await pilot.press(*"@nobody look", "enter")
        await drawn(pilot, lambda text: "goes to #notes, as shown" in text)
        await pilot.press("y")
        await until(lambda: of_type(owner, "message.sent"), owner, lambda sent: len(sent) == 2)

        sent = [event for event in await of_type(owner, "message.sent") if event.actor == "human:you"]
        assert [(event.stream, event.gist) for event in sent] == [
            ("channel/notes", "for the channel"),
            ("channel/notes", "@nobody look"),
        ]
        assert (await owner.get_body(sent[1].data["body"])) == attachment.read_bytes()


async def test_a_channel_s_unread_count_and_a_mention_come_from_the_person_s_marks(root):
    mentioning = team([Call("message_send", {"to": "@you", "gist": "a question for you"})])
    async with Session.start(with_notes(mentioning), name="s", root=root, cwd=root) as owner:
        await post(owner, 3)
        await in_state(owner, "lead", "idle")
        app = Harness("s")
        async with app.run_test(size=(120, 32)) as pilot:
            await drawn(pilot, lambda text: "#notes 3" in text)
            await pilot.press(*"go", "enter")
            text = await drawn(pilot, lambda text: "a question for you" in text and "⚠ 1 need you" in text)
            assert "@lead@" in text

            head = await owner.head()
            await pilot.press("alt+a")
            await drawn(pilot, lambda text: "⚠ 0 need you" in text)
            await pilot.press("alt+down")
            text = await drawn(pilot, lambda text: "note 2" in text)
            assert "#notes 3" not in text

        marked = await owner.marks()
        assert marked["inbox/you"] >= marked["channel/notes"] >= head
        assert await owner.head() == head, "reading wrote nothing to the journal"


async def test_the_inspector_says_why_an_agent_waits_what_it_runs_on_and_what_it_spent(root):
    async with attached(team([Ask("May I?")]), root) as (_, _, pilot):
        await pilot.press(*"go", "enter")
        await drawn(pilot, lambda text: "May I?" in text)
        await pilot.press("f2")
        text = await drawn(pilot, lambda text: "why asks you to approve" in text)

        for said in ("role lead, parent none", "harness driver_", "model its default", "operational unverified"):
            assert said in text
