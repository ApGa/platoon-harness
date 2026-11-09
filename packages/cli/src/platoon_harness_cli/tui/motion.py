"""Motion: the small sprite's agents and the navigator's glyphs moving a little, from the record's state alone, a few
frames a second. While agents of a live session work, the sprite's agents step in turn, faster as more work, and a
working agent's dot stirs; while each agent of a live session that has not ended rests, they blink now and then; and a
resting agent's ring breathes out for a second every six while the session is live, whether others work or not. An
event gets a flourish of a second at most: a wave when an agent finishes or the session settles, eyes that look up at
you when one comes to need you, and a stir when more start working. A session that is history never moves, nor does an
agent whose state is unknown, and nothing moves where motion is off."""

from collections.abc import Mapping

from textual.app import App

from . import logo

FPS = 4
"""Frames a second while anything moves."""
TICK = 1 / FPS
ENDED = frozenset({"done", "failed", "lost"})
"""The states of an agent that has ended, which a session's resting leaves aside."""
FLOURISHES = {"wave": 4, "look": 3, "stir": 3}
"""How many frames each flourish takes: a second at most."""
BLINK = 24
"""How many frames apart a resting session's agents blink: every six seconds, one at a time."""
GLYPHS = {"working": ("●", "•"), "idle": ("○", "◦")}
"""The frames of an agent's glyph that moves: a working agent's dot, which stirs, and a resting agent's ring, which
breathes."""
PACES = {"working": (2, 2), "idle": (BLINK - FPS, FPS)}
"""How many frames each of a glyph's two frames lasts: a working agent's dot stirs twice a second, and a resting
agent's ring breathes out for a second every six, as the logo blinks."""
_STRIDE = (*logo.AGENT[:5], "x...x")
_BLINK = (logo.AGENT[0], "xxxxx", *logo.AGENT[2:])
_WAVES = (
    (logo.AGENT[0], logo.AGENT[1], ".xxx.x", "xxxx.", *logo.AGENT[4:]),
    (logo.AGENT[0], "x.x.xx", ".xxx.", "xxxx.", *logo.AGENT[4:]),
)
_LOOK = (logo.AGENT[0], "xwxwx", *logo.AGENT[2:])


def allowed(app: App) -> bool:
    """Whether motion is on in `app`: at Textual's full animation level, and where its settings do not turn it off
    with `motion = false`."""
    return app.animation_level == "full" and getattr(app, "motion", True)


class Motion:
    """What moves, from the record's state as `follow` gives it, a frame at a time as `advance` steps it: `working`,
    how many agents work, `idle`, how many rest, `resting`, whether every agent that has not ended rests, and
    `flourish`, the event being played, if any."""

    def __init__(self) -> None:
        self.frame = 0
        self.working = 0
        self.idle = 0
        self.resting = False
        self.flourish: str | None = None
        self._began = 0
        self._states: dict[str, str] | None = None
        self._settled: bool | None = None

    @property
    def moving(self) -> bool:
        return bool(self.working or self.idle or self.flourish)

    def follow(self, states: Mapping[str, str], *, live: bool, settled: bool) -> None:
        """Take each agent's state and whether the session has settled, as the record says them now. On history all
        stops, and the state it was in before is forgotten, so a runtime that comes back plays no event for it."""
        if not live:
            self.working, self.idle, self.resting, self.flourish = 0, 0, False, None
            self._states = self._settled = None
            return
        before, self._states = self._states, dict(states)
        working = sum(state == "working" for state in states.values())
        ongoing = [state for state in states.values() if state not in ENDED]
        self.resting = not working and bool(ongoing) and all(state == "idle" for state in ongoing)
        if before is not None:
            came = {agent: state for agent, state in states.items() if before.get(agent) != state}
            if "needs_you" in came.values():
                self._play("look")
            elif "done" in came.values() or (settled and self._settled is False):
                self._play("wave")
            elif working > self.working:
                self._play("stir")
        self.working, self.idle, self._settled = working, ongoing.count("idle"), settled

    def _play(self, flourish: str) -> None:
        self.flourish, self._began = flourish, self.frame

    def advance(self) -> None:
        """Step a frame, ending a flourish that has taken its frames."""
        self.frame += 1
        if self.flourish is not None and self.frame - self._began >= FLOURISHES[self.flourish]:
            self.flourish = None

    def sprite(self) -> tuple[str, ...]:
        """The small sprite's pixels this frame: a flourish's, else an agent stepping while any work, else one
        blinking now and then while all rest, else the sprite at rest."""
        played = self.frame - self._began
        changed: dict[int, tuple[str, ...]] = {}
        if self.flourish == "wave":
            changed = {2: _WAVES[played % 2]}
        elif self.flourish == "look":
            changed = {index: _LOOK for index in range(3)} if played != 1 else {}
        elif self.flourish == "stir":
            changed = {played % 3: _STRIDE}
        elif self.working:
            pace = {1: 4, 2: 2}.get(self.working, 1)
            changed = {(self.frame // pace) % 3: _STRIDE}
        elif self.resting and self.frame % BLINK == 0:
            changed = {(self.frame // BLINK) % 3: _BLINK}
        return logo.composed(logo.AGENT, logo.SMALL_AT, logo.SMALL_SIZE, changed) if changed else logo.SMALL

    def glyph(self, state: str) -> str | None:
        """The glyph of an agent in `state` this frame, where it moves: a working agent's and a resting agent's of a
        live session. None where it stands still, as an agent's in any other state does."""
        if (state == "working" and self.working) or (state == "idle" and self.idle):
            held, out = PACES[state]
            return GLYPHS[state][int(self.frame % (held + out) >= held)]
        return None
