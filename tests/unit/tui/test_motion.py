"""The agents' motion, from the record's state alone, a frame at a time: each motion starts with its state or its event
and stops with it, stepped here by hand, never by waiting."""

from textual.app import App, ComposeResult
from textual.content import Content

from platoon_harness_cli.tui import logo
from platoon_harness_cli.tui.motion import BLINK, FLOURISHES, FPS, GLYPHS, Motion
from platoon_harness_cli.tui.rows import Row
from platoon_harness_cli.tui.workspace import Navigator


def frames(motion: Motion, count: int) -> list[tuple[str, ...]]:
    """The small sprite's pixels over `count` frames."""
    seen = []
    for _ in range(count):
        seen.append(motion.sprite())
        motion.advance()
    return seen


def stepping(pixels: tuple[str, ...]) -> list[int]:
    """Which of the small sprite's agents is mid-stride: its legs apart, as no agent at rest has them."""
    return [index for index, (left, top, _) in enumerate(logo.SMALL_AT) if pixels[top + 5][left] != "."]


def test_agents_step_in_turn_while_any_work_faster_as_more_work_and_stand_still_once_none_does():
    motion = Motion()
    motion.follow({"lead": "working", "w": "idle"}, live=True, settled=False)
    one = frames(motion, 12)
    motion.follow({"lead": "working", "w": "working", "v": "working"}, live=True, settled=False)
    motion.flourish = None
    three = frames(motion, 3)
    motion.follow({"lead": "idle", "w": "idle", "v": "idle"}, live=True, settled=False)

    assert [stepping(pixels) for pixels in one[::4]] == [[0], [1], [2]], "one working: an agent steps a second"
    assert len({tuple(stepping(pixels)) for pixels in one[:4]}) == 1
    assert [stepping(pixels) for pixels in three] in ([[0], [1], [2]], [[1], [2], [0]], [[2], [0], [1]])
    assert motion.working == 0 and all(not stepping(pixels) for pixels in frames(motion, BLINK))


def test_a_live_session_at_rest_blinks_now_and_then_and_its_resting_agents_breathe():
    motion = Motion()
    motion.follow({"lead": "idle", "w": "done"}, live=True, settled=True)
    seen = frames(motion, 2 * BLINK)
    rings = []
    for _ in range(BLINK):
        rings.append(motion.glyph("idle"))
        motion.advance()

    assert motion.resting and motion.moving
    assert [at for at, pixels in enumerate(seen) if pixels != logo.SMALL] == [0, BLINK], "a blink every six seconds"
    assert rings.count(GLYPHS["idle"][1]) == FPS and rings.count(GLYPHS["idle"][0]) == BLINK - FPS, (
        "a breath out of a second every six"
    )
    assert motion.glyph("done") is None


def test_history_and_an_agent_whose_state_is_unknown_never_move():
    """A session no runtime holds moves not at all; an agent whose state is unknown stands still, and so does the
    sprite's blink, which would say every agent rests."""
    motion = Motion()
    motion.follow({"lead": "working"}, live=False, settled=False)
    history = (motion.moving, motion.sprite(), motion.glyph("working"))
    motion.follow({"lead": "unknown", "w": "idle"}, live=True, settled=False)

    assert history == (False, logo.SMALL, None)
    assert not motion.resting and motion.glyph("unknown") is None and motion.glyph("idle") is not None
    assert all(pixels == logo.SMALL for pixels in frames(motion, 2 * BLINK))


def test_an_event_plays_a_flourish_of_a_second_at_most_and_the_first_state_seen_plays_none():
    """A wave as an agent finishes or the session settles, eyes that look up as one comes to need you, a stir as more
    start working; none for the state the screen first draws, and none for a state a session that is history leaves."""
    played = []
    motion = Motion()
    for states, settled in (
        ({"lead": "needs_you"}, False),
        ({"lead": "working"}, False),
        ({"lead": "idle", "w": "needs_you"}, False),
        ({"lead": "idle", "w": "done"}, False),
        ({"lead": "idle", "w": "done"}, True),
    ):
        motion.follow(states, live=True, settled=settled)
        played.append(motion.flourish)
        lasted = 0
        while motion.flourish is not None:
            motion.advance()
            lasted += 1
        assert lasted <= FPS, "a flourish takes a second at most"
    motion.follow({}, live=False, settled=False)
    motion.follow({"lead": "needs_you"}, live=True, settled=False)

    assert played == [None, "stir", "look", "wave", "wave"]
    assert motion.flourish is None and max(FLOURISHES.values()) <= FPS


class Alone(App[None]):
    def compose(self) -> ComposeResult:
        yield Navigator()


def team(navigator: Navigator, states: dict[str, str]) -> None:
    """Rows for the logo and an agent in each state, as the workspace draws them."""
    art = logo.sprite(logo.SMALL, logo.TRUECOLOUR)
    navigator.show(
        [
            *(Row(cells, lead=cells.cell_length, moves="logo") for cells in art),
            *(
                Row(Content(f"{'●' if state == 'working' else '○'} @{agent}"), f"@{agent}", lead=2, moves=state)
                for agent, state in states.items()
            ),
        ]
    )


async def test_the_navigator_moves_while_its_state_says_to_drawing_only_the_rows_whose_frame_changed():
    app = Alone()
    async with app.run_test(size=(40, 12)) as pilot:
        navigator = app.query_one(Navigator)
        team(navigator, {"lead": "working"})
        navigator.follow({"lead": "working"}, live=True, settled=False)
        ticking = navigator._ticking is not None
        refreshed: list[int] = []
        navigator.refresh_lines = lambda y, count=1: refreshed.append(y)  # type: ignore[method-assign]
        drawn = []
        for _ in range(4):
            navigator.advance()
            await pilot.pause()
            drawn.append(navigator.render_line(4).text[0])
        navigator.follow({"lead": "working"}, live=False, settled=False)
        stopped = navigator._ticking is None

    assert ticking and stopped
    assert set(refreshed) <= {0, 1, 2, 3, 4}, "only the logo's rows and the working agent's glyph"
    assert set(drawn) == set(GLYPHS["working"])


async def test_nothing_moves_where_motion_is_off():
    """`motion = false` in tui.toml, or Textual's animation level below full, as `TEXTUAL_ANIMATIONS` sets it."""
    stood = []
    for level, motion in (("basic", True), ("none", True), ("full", False)):
        app = Alone()
        app.motion = motion  # type: ignore[attr-defined]
        async with app.run_test(size=(40, 12)):
            app.animation_level = level  # type: ignore[assignment]
            navigator = app.query_one(Navigator)
            team(navigator, {"lead": "working"})
            navigator.follow({"lead": "working"}, live=True, settled=False)
            stood.append(navigator._ticking is None and navigator.render_line(4).text[0] == "●")

    assert stood == [True, True, True]
