"""What changed, in the terminal: the header, `/review`, the inspector's workspace and a conflict in the dock, on a
session in a repository of the test's own, with its agent in a worktree."""

import contextlib
import subprocess
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

import pytest

from platoon_harness import Session, Team
from platoon_harness_cli.tui.app import TerminalUI
from platoon_harness_cli.tui.review import rows_of, snapshots_of

from ..runtime.gitting import commit, git, repository, working
from ..runtime.support import in_state, of_type, until
from .support import drawn

pytestmark = pytest.mark.timeout(60)


@pytest.fixture
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("PLATOON_HARNESS_HOME", str(tmp_path / "home"))
    return tmp_path / "home"


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    return repository(tmp_path / "repo", monkeypatch)


def team(*work: Callable[[Path], Any]) -> Team:
    lead = {"harness": working(*work), "workspace": "worktree"}
    return Team.model_validate({"roles": {"lead": lead}, "topology": {"edges": {"lead": ["human"]}}})


@contextlib.asynccontextmanager
async def attached(team: Team, root: Path, repo: Path) -> AsyncIterator[tuple[Session, object]]:
    """A session the test owns in `repo`, with `lead` up, and the TUI attached to it."""
    async with Session.start(team, name="s", root=root, cwd=repo) as owner:
        await in_state(owner, "lead", "idle")
        app = TerminalUI("s")
        async with app.run_test(size=(140, 32)) as pilot:
            await drawn(pilot, lambda text: "@lead" in text)
            yield owner, pilot


async def looked(owner: Session) -> None:
    async def probes() -> list[Any]:
        return [event for event in await of_type(owner, "effect.finished") if event.data["kind"] == "probe"]

    await until(probes, owner)


def worked(cwd: Path) -> None:
    commit(cwd, "work")
    (cwd / "notes.txt").write_text("unfinished\n")


async def test_the_header_says_what_changed_or_why_nothing_is_observed(root, repo):
    async with attached(team(worked), root, repo) as (owner, pilot):
        before = (await drawn(pilot, lambda text: "changes" in text.splitlines()[0])).splitlines()[0]
        await pilot.press(*"go", "enter")
        await looked(owner)
        after = (await drawn(pilot, lambda text: "1 commit," in text.splitlines()[0])).splitlines()[0]

    assert "changes not measured" in before
    assert "1 commit, 1 path uncommitted" in after


async def test_review_lists_what_changed_and_draws_diffs_disabled_saying_why(root, repo):
    async with attached(team(worked), root, repo) as (owner, pilot):
        await pilot.press(*"go", "enter")
        await looked(owner)
        await drawn(pilot, lambda text: "1 commit," in text)
        newest = max(row["seq"] for row in (await owner.submit("view.watch", name="changes")).result["rows"])
        await pilot.press("alt+d")
        text = await drawn(pilot, lambda text: "What changed" in text and "notes.txt" in text)
        head = git("rev-parse", "platoon-harness/s/lead", cwd=repo).strip()
        marked = await until(owner.marks, owner, lambda marks: marks.get("repo/repo", 0) >= newest)
        await pilot.press("escape")
        await pilot.press("alt+d")
        again = await drawn(pilot, lambda text: "What changed" in text and "notes.txt" in text)

    assert f"● {head[:12]} add work  +1 -0" in text
    assert "● untracked    notes.txt  +? -?" in text
    assert "Diffs come with review, which is planned." in text
    assert marked["repo/repo"] == newest
    assert f"  {head[:12]} add work" in again and "● untracked" not in again


async def test_the_inspector_names_the_agent_s_workspace(root, repo):
    async with attached(team(worked), root, repo) as (owner, pilot):
        await pilot.press("f2")
        text = await drawn(pilot, lambda text: "workspace worktree" in text)
        base = (await owner.status("lead"))["workspace"]["base"]

    for said in ("workspace worktree, cooperative", "branch platoon-harness/s/lead", f"from {base[:12]}"):
        assert said in text


async def test_a_conflict_in_the_dock_says_where_to_resolve_it(root, repo):
    git("checkout", "-q", "-b", "theirs", cwd=repo)
    commit(repo, "README", "theirs\n")
    git("checkout", "-q", "main", cwd=repo)

    def merged(cwd: Path) -> None:
        commit(cwd, "README", "ours\n")
        with contextlib.suppress(subprocess.CalledProcessError):
            git("merge", "-q", "theirs", cwd=cwd)

    async with attached(team(merged), root, repo) as (owner, pilot):
        await pilot.press(*"go", "enter")
        await looked(owner)
        path = (await owner.status("lead"))["workspace"]["path"]
        text = await drawn(pilot, lambda text: "conflict @lead" in text)

    line = next(line for line in text.splitlines() if "conflict @lead" in line)
    assert "conflict @lead merge stopped on conflicts in 1 file, README: resolve it in" in line
    assert path[:20] in line


def test_an_isolated_workspace_s_commits_are_said_to_be_in_a_repository_of_its_own():
    roster = [
        {"agent": "ada", "workspace": {"mode": "isolated", "path": "/s/agents/ada/workspace", "branch": "b"}},
        {"agent": "bob", "workspace": {"mode": "worktree", "path": "/s/agents/bob/workspace", "branch": "c"}},
        {"agent": "cy", "workspace": None},
    ]
    changes = {row["id"]: row for row in (commit_of("aaaa", "@ada", 3), commit_of("bbbb", "@bob", 4))}

    lines = [row.line.plain.rstrip() for row in rows_of(changes, mark=4, snapshots=snapshots_of(roster))]

    assert lines[0] == "@ada, a snapshot, whose commits are in its own repository"
    assert lines[2] == "@bob"


def test_review_groups_commits_by_the_workspace_that_made_them():
    def commit_row(sha: str, made_in: str | None, seq: int) -> dict[str, Any]:
        found = {"id": f"commit/{sha}", "kind": "commit", "commit": sha, "gist": f"{sha} made", "made_in": made_in}
        return {
            **found,
            "branch": None,
            "added": 1,
            "removed": 0,
            "files": 1,
            "recorded": seq,
            "dropped": False,
            "seq": seq,
        }

    reading = {"kind": "workspace", "head": None, "branch": "main", "under_way": "merge", "rebasing": None}
    changes = {
        row["id"]: row
        for row in (
            commit_row("aaaa", "@ada", 3),
            commit_row("bbbb", "shared", 4),
            commit_row("cccc", None, 5),
            commit_row("dddd", "@ada", 6),
            {**reading, "id": "workspace/shared", "workspace": "shared", "total": 3, "conflicted": 1, "seq": 7},
            {
                "id": "path/shared/a.py",
                "kind": "path",
                "workspace": "shared",
                "path": "a.py",
                "state": "conflicted",
                "added": 2,
                "removed": 0,
                "seq": 7,
            },
        )
    }

    lines = [row.line.plain.rstrip() for row in rows_of(changes, mark=5)]

    assert lines == [
        "@ada",
        "● dddd made  +1 -0",
        "  aaaa made  +1 -0",
        "your checkout, a merge under way",
        "● conflicted   a.py  +2 -0",
        "  2 more",
        "nobody's",
        "  cccc made  +1 -0",
        "  bbbb made  +1 -0",
    ]


def commit_of(sha: str, made_in: str, recorded: int, seq: int | None = None, dropped: bool = False) -> dict[str, Any]:
    found = {"id": f"commit/{sha}", "kind": "commit", "commit": sha, "gist": f"{sha} made", "made_in": made_in}
    return {
        **found,
        "branch": None,
        "added": 1,
        "removed": 0,
        "files": 1,
        "recorded": recorded,
        "dropped": dropped,
        "seq": recorded if seq is None else seq,
    }


def test_review_lists_commits_newest_recorded_first_whatever_a_rewrite_moved():
    """An amend drops the commit it replaced, which moves that row's seq, and not its place."""
    changes = {
        row["id"]: row
        for row in (
            commit_of("aaaa", "@ada", 3, seq=9, dropped=True),
            commit_of("bbbb", "@ada", 5),
            commit_of("cccc", "@ada", 8),
        )
    }

    lines = [row.line.plain.rstrip() for row in rows_of(changes, mark=9)]

    assert lines == ["@ada", "  cccc made  +1 -0", "  bbbb made  +1 -0", "  aaaa made  +1 -0 dropped"]


def test_review_says_a_snapshot_s_commits_are_in_its_own_repository():
    changes = {row["id"]: row for row in (commit_of("aaaa", "@ada", 3), commit_of("bbbb", "@cy", 4))}

    lines = [row.line.plain.rstrip() for row in rows_of(changes, mark=9, snapshots={"@cy"})]

    assert lines == [
        "@ada",
        "  aaaa made  +1 -0",
        "@cy, a snapshot, whose commits are in its own repository",
        "  bbbb made  +1 -0",
    ]
