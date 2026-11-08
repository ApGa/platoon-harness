"""The workspace's layout at each size the guide names, the review and the provenance panel, as snapshots, on a
session's history so nothing moves: a session of scripted harnesses, and the mixed team's session as a live run of it
recorded it, which no live run has recorded yet. The docs show the recorded session's snapshots once there is one, and
the scripted session's until then."""

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from pathlib import Path
from typing import Any

import pytest
from textual.app import App

from platoon_harness import Session, Team
from platoon_harness.annotations import Annotation
from platoon_harness.drivers import AgentSpec
from platoon_harness.kernel import Event
from platoon_harness.primitives import Contributors, Interactions, Lineage, Uses
from platoon_harness.testing import Do, Say, ScriptedDriver
from platoon_harness_cli.tui.app import CSS, TerminalUI
from platoon_harness_cli.tui.dialogs import Form
from platoon_harness_cli.tui.provenance import Provenance
from platoon_harness_cli.tui.review import Patch
from platoon_harness_cli.tui.workspace import Workspace

from ...recorded import RECORDED, finish_of, restored
from ..cli.test_provenance import opened, reached
from ..primitives.test_provenance import ask, scenario
from ..runtime.gitting import commit, repository, working
from ..runtime.support import in_state, of_type, until
from .support import drawn

SIZES = {"wide": (120, 32), "medium": (90, 28), "narrow": (70, 24), "slim": (52, 20), "short": (100, 14)}
SNAPSHOTS = Path(__file__).parent / "__snapshots__" / "test_snapshots"
ASSETS = Path(__file__).parents[3] / "docs" / "assets"
SCRIPTED_SNAPSHOTS = {
    **{f"tui-{size}.svg": f"test_the_workspace_s_layout_at_each_size[{size}].raw" for size in SIZES},
    "tui-review.svg": "test_review_lists_what_changed.raw",
    "tui-patch.svg": "test_the_review_draws_a_patch.raw",
    "tui-provenance.svg": "test_the_provenance_panel_draws_each_link_with_how_it_is_known.raw",
    "tui-who-reached-whom.svg": "test_who_reached_whom_draws_each_kind_apart.raw",
}
"""Each screenshot the docs show, in docs/assets, by the snapshot below that draws it from a scripted session."""
RECORDED_SNAPSHOTS = {
    **{f"tui-{size}.svg": f"test_the_recorded_mixed_team_s_layout_at_each_size[{size}].raw" for size in SIZES},
    "tui-review.svg": "test_the_recorded_mixed_team_s_review_lists_what_changed.raw",
    "tui-provenance.svg": "test_the_recorded_mixed_team_s_provenance_of_the_lead_s_answer.raw",
}
"""Each screenshot the snapshot below draws from the mixed team's recorded session: all but the patch, which is read
from git when it opens, and a recording keeps no repository."""
SCREENSHOTS = SCRIPTED_SNAPSHOTS | (RECORDED_SNAPSHOTS if RECORDED.exists() else {})
"""Each screenshot the docs show, in docs/assets, by the snapshot below that it is a copy of: the recorded session's
once a live run has recorded one, and the scripted session's until then, and for the patch."""


async def split(spec: AgentSpec, call: Callable[[str, Mapping[str, Any]], Awaitable[Any]]) -> None:
    """Spawn the worker under an id of the harness's own, as a harness's call goes, so it is drawn under its call."""
    await call("agent_spawn", {"name": "w", "child_role": "worker", "goal": "fix the parser"})


LEAD = [
    [Say("kestrel: I will split the work"), Do(split)],
    [Say("Done: the worker fixed the parser, and its 3 tests pass.")],
]
"""The lead's turns: it splits the work and spawns a worker, and once the worker's report starts its next turn, says
the parser is fixed."""


def scripted_lead() -> ScriptedDriver:
    return ScriptedDriver(LEAD)


def scripted_worker() -> ScriptedDriver:
    return ScriptedDriver([[Say("parser fixed, 3 tests pass")]])


def team() -> Team:
    """A lead and a worker on harnesses named the same in every run, as a snapshot draws their names."""
    lead = {"harness": f"{__name__}:scripted_lead", "may_spawn": ["worker"]}
    worker = {"harness": f"{__name__}:scripted_worker", "count": 0}
    return Team.model_validate({"roles": {"lead": lead, "worker": worker}, "topology": {"limits": {"max_depth": 1}}})


async def _history(root: Path) -> None:
    async with Session.start(team(), name="s", root=root, cwd=root) as owner:
        await in_state(owner, "lead", "idle")
        await owner.send("@lead", "fix the parser, with a worker")
        await until(owner.status, owner, lambda status: status["settled"])


@pytest.fixture
def history(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PLATOON_HARNESS_HOME", str(tmp_path))
    asyncio.run(_history(tmp_path))


@pytest.mark.parametrize("size", SIZES)
def test_the_workspace_s_layout_at_each_size(snap_compare, history, size):
    async def ready(pilot) -> None:
        await drawn(pilot, lambda text: "kestrel" in text and "Done: the worker" in text)

    assert snap_compare(TerminalUI("s"), terminal_size=SIZES[size], run_before=ready)


@pytest.fixture
def recorded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    """The mixed team's session as a live run recorded it, made again as history, and its name."""
    if not RECORDED.exists():
        pytest.skip("no live run has recorded the mixed team yet, so the docs' screenshots are of scripted harnesses")
    monkeypatch.setenv("PLATOON_HARNESS_HOME", str(tmp_path))
    return restored(RECORDED, tmp_path)


@pytest.mark.parametrize("size", SIZES)
def test_the_recorded_mixed_team_s_layout_at_each_size(snap_compare, recorded, size):
    answer = finish_of(RECORDED, "lead")["data"]["gist"]

    async def ready(pilot) -> None:
        await drawn(pilot, lambda text: answer[:30] in " ".join(text.split()) and ended(pilot.app.screen))

    assert snap_compare(TerminalUI(recorded), terminal_size=SIZES[size], run_before=ready)


def ended(screen: object) -> bool:
    """Whether the workspace's header has read how the session ended, which it reads after its status, so that both
    are drawn as they stay: below 60 columns the header shows neither."""
    header = screen.query_one("#header") if isinstance(screen, Workspace) else None
    return header is not None and (screen.size.width < 60 or "tokens" in str(header.content))


def test_the_recorded_mixed_team_s_review_lists_what_changed(snap_compare, recorded):
    async def listed(pilot) -> None:
        await drawn(pilot, lambda text: "uncommitted" in text and ended(pilot.app.screen))
        await pilot.press("alt+d")
        await drawn(pilot, lambda text: "What changed" in text and "tally/money.py" in text)

    assert snap_compare(TerminalUI(recorded), terminal_size=(120, 32), run_before=listed)


def drawn_whole(screen: object) -> bool:
    """Whether a provenance panel has drawn down to its credit, which on a real session lies below the fold."""
    return isinstance(screen, Provenance) and any("Credit and rewards" in line.text for line in screen.lines)


def test_the_recorded_mixed_team_s_provenance_of_the_lead_s_answer(snap_compare, recorded):
    finish = finish_of(RECORDED, "lead")
    answer = f"{finish['stream']}@{finish['version']}"

    async def asked(pilot) -> None:
        await drawn(pilot, lambda text: "The session is closed" in text and ended(pilot.app.screen))
        await pilot.press("slash", *"provenance", "enter")
        await drawn(pilot, lambda _: isinstance(pilot.app.screen, Form))
        await pilot.press("home", "ctrl+k", *answer, "enter")
        await drawn(pilot, lambda text: f"Provenance of {answer}" in text and drawn_whole(pilot.app.screen))

    assert snap_compare(TerminalUI(recorded), terminal_size=(120, 48), run_before=asked)


WHEN = 1_700_000_000
"""When every commit of the review's history is made, so that each is the same commit in every run."""


def worked(cwd: Path) -> None:
    commit(cwd, "parser.py", "def parse(text):\n    return text.split()\n", "Fix the parser", when=WHEN)
    (cwd / "notes.txt").write_text("unfinished\n")
    (cwd / "README").write_text("hello, edited\n")


async def _reviewed(root: Path, repo: Path) -> None:
    team = Team.model_validate({"roles": {"lead": {"harness": working(worked), "workspace": "worktree"}}})
    async with Session.start(team, name="s", root=root, cwd=repo) as owner:
        await in_state(owner, "lead", "idle")
        await owner.send("@lead", "fix the parser")

        async def probes() -> list:
            return [event for event in await of_type(owner, "effect.finished") if event.data["kind"] == "probe"]

        await until(probes, owner)


@pytest.fixture
def reviewed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PLATOON_HARNESS_HOME", str(tmp_path / "home"))
    repo = repository(tmp_path / "repo", monkeypatch, when=WHEN)
    asyncio.run(_reviewed(tmp_path / "home", repo))


def test_review_lists_what_changed(snap_compare, reviewed):
    async def opened(pilot) -> None:
        await drawn(pilot, lambda text: "1 commit, 2 paths uncommitted" in text)
        await pilot.press("alt+d")
        await drawn(pilot, lambda text: "What changed" in text and "notes.txt" in text)

    assert snap_compare(TerminalUI("s"), terminal_size=(120, 32), run_before=opened)


SHA = "3f9c2a1b2c3d4e5f60718293a4b5c6d7e8f90a1b"
PATCH = """\
diff --git a/parser.py b/parser.py
index 3b18e51..a4c2d8f 100644
--- a/parser.py
+++ b/parser.py
@@ -1,2 +1,5 @@
 def parse(text):
-    return text.split()
+    \"\"\"The words of `text`, and none for blank text.\"\"\"
+    if not text.strip():
+        return []
+    return text.split()
diff --git a/logo.png b/logo.png
new file mode 100644
index 0000000..e69de29
Binary files /dev/null and b/logo.png differ
"""
"""A commit's patch as git shows it: a text file's change, and a file git takes for binary, which it names."""


class Read:
    """A session as the review's patch asks one, answering what a session that kept one commit's patch would, so that
    every ref and number is the same each run."""

    def __init__(self) -> None:
        self._record = Event.model_validate(
            {
                "v": 1,
                "seq": 40,
                "stream": "repo/app",
                "version": 12,
                "type": "repo.diffed",
                "actor": "runtime",
                "agent": None,
                "turn": None,
                "context_version": None,
                "episode": None,
                "topology_rev": 1,
                "correlation": None,
                "cause": (),
                "based_on": (),
                "native": {},
                "model": None,
                "wall_time": 0.0,
                "gist": f"{SHA[:12]} patch, {PATCH.count(chr(10))} lines",
                "data": {"effect": 38, "sha": SHA, "workspace": None, "read_in": "@lead", "body": "sha256:" + "0" * 64}
                | {"head": None, "read_at": None, "cut": False, "untracked_repositories": 0, "why": None},
                "outcome": None,
            }
        )

    async def repo_diff(self, of: str) -> dict[str, Any]:
        return {"effect": 38, "ref": "repo/app@12"}

    async def events(self, after: int, match: str | None = None, **_: Any) -> AsyncIterator[Event]:
        yield self._record

    async def status(self, agent: str) -> dict[str, Any]:
        return {"workspace": {"mode": "worktree"}}

    async def repo_commit(self, sha: str) -> dict[str, Any]:
        return {"ref": "repo/app@9", "sha": SHA, "gist": f"{SHA[:12]} fix the parser", "made_in": "@lead"}

    async def get_body(self, ref: str, *, limit: int | None = None) -> bytes:
        return PATCH.encode()


class Patched(App[None]):
    CSS = CSS

    def on_mount(self) -> None:
        self.push_screen(Patch(Read(), SHA[:12]))  # type: ignore[arg-type]


def test_the_review_draws_a_patch(snap_compare):
    async def read(pilot) -> None:
        await drawn(pilot, lambda text: "Read in @lead's worktree." in text)

    assert snap_compare(Patched(), terminal_size=(100, 28), run_before=read)


class Answered:
    """A session as the provenance panel asks one, answering what the queries answered of a journal written on a manual
    clock, so that every seq and head is the same each run."""

    name = "s"

    def __init__(self, answers: dict[str, Any]) -> None:
        self._answers = answers

    async def lineage(self, ref: str) -> Lineage:
        return Lineage.model_validate(self._answers["lineage"])

    async def uses(self, ref: str) -> Uses:
        return Uses.model_validate(self._answers["uses"])

    async def contributors(self, ref: str) -> Contributors:
        return Contributors.model_validate(self._answers["contributors"])

    async def interactions(self, *, after: str | None = None) -> Interactions:
        return Interactions.model_validate(self._answers["interactions"])

    async def annotations(self, target: str) -> list[Annotation]:
        estimate = {"target": target, "kind": "credit", "producer": "even-split", "producer_version": "0"}
        estimate |= {"params_hash": "0" * 64, "scope": "team", "status": "scored", "value": 0.5, "evidence": ()}
        return [Annotation.model_validate({"id": 1, **estimate, "head_seq": 49, "wall_time": 0.0})]


class Panel(App[None]):
    CSS = CSS

    def __init__(self, session: Answered, ref: str | None) -> None:
        super().__init__()
        self._session, self._ref = session, ref

    def on_mount(self) -> None:
        self.push_screen(Provenance(self._session, self._ref))  # type: ignore[arg-type]


async def _traced(folder: Path) -> tuple[str, dict[str, Any]]:
    kernel = await opened(folder)
    refs = await scenario(kernel)
    answers = {query: ask(kernel, query, ref=refs["message"]) for query in ("lineage", "uses", "contributors")}
    kernel.close()
    return refs["message"], answers


def test_the_provenance_panel_draws_each_link_with_how_it_is_known(snap_compare, tmp_path):
    ref, answers = asyncio.run(_traced(tmp_path / "session"))

    async def read(pilot) -> None:
        await drawn(pilot, lambda text: "Credit and rewards" in text and "even-split" in text)

    assert snap_compare(Panel(Answered(answers), ref), terminal_size=(120, 48), run_before=read)


async def _reached(folder: Path) -> dict[str, Any]:
    kernel = await opened(folder)
    await reached(kernel)
    answer = ask(kernel, "interactions")
    kernel.close()
    return answer


def test_who_reached_whom_draws_each_kind_apart(snap_compare, tmp_path):
    answers = {"interactions": asyncio.run(_reached(tmp_path / "session"))}

    async def read(pilot) -> None:
        await drawn(pilot, lambda text: "Each agent's unknowns" in text and "@bob: unknown" in text)

    assert snap_compare(Panel(Answered(answers), None), terminal_size=(120, 40), run_before=read)


def test_each_screenshot_the_docs_show_is_its_snapshot_byte_for_byte():
    """So a screenshot shows what the terminal UI draws now, and nothing but what a test drew. On a failure, copy the
    snapshot over the screenshot as the message says."""
    assert sorted(path.name for path in ASSETS.glob("tui-*.svg")) == sorted(SCREENSHOTS)
    for screenshot, snapshot in SCREENSHOTS.items():
        copy = f"cp 'tests/unit/tui/__snapshots__/test_snapshots/{snapshot}' docs/assets/{screenshot}"
        assert (ASSETS / screenshot).read_bytes() == (SNAPSHOTS / snapshot).read_bytes(), copy
