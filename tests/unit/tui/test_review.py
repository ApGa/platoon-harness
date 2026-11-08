"""What changed, in the terminal: the header, `/review`, the inspector's workspace and a conflict in the dock, on a
session in a repository of the test's own, with its agent in a worktree."""

import asyncio
import contextlib
import subprocess
import time
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

import pytest

from platoon_harness import Refused, Session, Team
from platoon_harness.kernel import Clock, ManualClock
from platoon_harness_cli import review
from platoon_harness_cli.review import PAGE, Diff, place, snapshots_of
from platoon_harness_cli.tui.app import TerminalUI
from platoon_harness_cli.tui.review import Patch, patch_rows, rows_of

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


def team(*work: Callable[[Path], Any], workspace: str = "worktree", **fields: Any) -> Team:
    lead = {"harness": working(*work), "workspace": workspace}
    return Team.model_validate({"roles": {"lead": lead}, "topology": {"edges": {"lead": ["human"]}}, **fields})


@contextlib.asynccontextmanager
async def attached(
    team: Team, root: Path, repo: Path, clock: Clock | None = None
) -> AsyncIterator[tuple[Session, object]]:
    """A session the test owns in `repo`, with `lead` up, and the TUI attached to it."""
    async with Session.start(team, name="s", root=root, cwd=repo, clock=clock) as owner:
        await in_state(owner, "lead", "idle")
        app = TerminalUI("s")
        async with app.run_test(size=(140, 32)) as pilot:
            await drawn(pilot, lambda text: "@lead" in text)
            yield owner, pilot


@contextlib.asynccontextmanager
async def worked_on(team: Team, root: Path, repo: Path) -> AsyncIterator[Session]:
    """A session the test owns in `repo`, once `lead` has taken a turn and the look after it has run."""
    async with Session.start(team, name="s", root=root, cwd=repo) as owner:
        await in_state(owner, "lead", "idle")
        await owner.send("@lead", "go")
        await looked(owner)
        yield owner


async def read_of(session: Session, of: str) -> Diff:
    """The diff of `of`, as `/review` asks for it."""
    return await review.read(session, (await session.repo_diff(of))["effect"])


def diffs_read(session_events: list[Any]) -> list[Any]:
    return [event for event in session_events if event.data["kind"] == "diff"]


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


async def test_review_lists_what_changed_and_reading_it_to_its_end_moves_your_mark(root, repo, monkeypatch):
    marked: asyncio.Future[int] = asyncio.get_running_loop().create_future()
    mark = Session.mark

    async def written(session: Session, stream: str, seq: int) -> None:
        try:
            await mark(session, stream, seq)
        finally:
            if stream == "repo/repo" and not marked.done():
                marked.set_result(seq)

    monkeypatch.setattr(Session, "mark", written)
    async with attached(team(worked), root, repo) as (owner, pilot):
        await pilot.press(*"go", "enter")
        await looked(owner)
        await drawn(pilot, lambda text: "1 commit," in text)
        newest = max(row["seq"] for row in (await owner.submit("view.watch", name="changes")).result["rows"])
        await pilot.press("alt+d")
        text = await drawn(pilot, lambda text: "What changed" in text and "notes.txt" in text)
        head = git("rev-parse", "platoon-harness/s/lead", cwd=repo).strip()
        read = await marked
        kept = await owner.marks()
        await pilot.press("escape")
        await pilot.press("alt+d")
        again = await drawn(pilot, lambda text: "What changed" in text and "notes.txt" in text)

    assert f"● {head[:12]} add work  +1 -0" in text
    assert "● untracked    notes.txt  +? -?" in text
    assert "Enter: its diff" in text
    assert read == kept.get("repo/repo") == newest
    assert f"  {head[:12]} add work" in again and "● untracked" not in again


async def test_the_inspector_names_the_agent_s_workspace(root, repo):
    async with attached(team(worked), root, repo) as (owner, pilot):
        await pilot.press("f2")
        text = await drawn(pilot, lambda text: "workspace worktree" in text)
        base = (await owner.status("lead"))["workspace"]["base"]

    for said in ("workspace worktree, cooperative", "branch platoon-harness/s/lead", f"from {base[:12]}"):
        assert said in text


async def test_a_conflict_in_the_dock_says_to_tell_its_agent_or_resolve_it_in_your_own_checkout(root, repo):
    """Never in the agent's worktree, whose path it does not give, as a commit made there is recorded as the agent's."""
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
    assert "conflict @lead merge stopped on conflicts in 1 file, README: tell @lead, or resolve it in your own" in line
    assert path[:20] not in line


async def test_review_tests_a_commit_once_you_say_yes_and_shows_what_it_came_to(root, repo):
    """The key that tests takes the chosen commit's act, which says whose code it runs as you, and asks first."""
    async with attached(team(worked, test={"command": ["true"], "timeout": "1m"}), root, repo) as (owner, pilot):
        await pilot.press(*"go", "enter")
        await looked(owner)
        await drawn(pilot, lambda text: "1 commit," in text)
        await pilot.press("alt+d")
        listed = await drawn(pilot, lambda text: "What changed" in text and "notes.txt" in text)
        await pilot.press("down", "t")
        asked = await drawn(pilot, lambda text: "Run it?" in text)
        await pilot.press("y")
        await until(lambda: of_type(owner, "repo.tested"), owner)
        await pilot.press("escape")
        await pilot.press("alt+d")
        again = await drawn(pilot, lambda text: "tests passed" in text)

    head = git("rev-parse", "platoon-harness/s/lead", cwd=repo).strip()
    assert f"{head[:12]} add work  +1 -0  untested" in listed and "t: test the chosen commit" in listed
    assert "Test: runs @lead's commit as you, unconfined. Run it?" in asked
    assert f"{head[:12]} add work  +1 -0  tests passed" in again


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
            "tests": None,
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
        "tests": None,
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


def test_review_says_why_a_commit_s_test_failed_or_erred():
    failed = {**commit_of("aaaa", "@ada", 3), "tests": "failed", "tests_exit": 2, "tests_why": None}
    erred = {
        **commit_of("bbbb", "@ada", 4),
        "tests": "error",
        "tests_exit": None,
        "tests_why": "its timeout came first",
    }
    passed = {**commit_of("cccc", "@ada", 5), "tests": "passed", "tests_exit": 0, "tests_why": None}
    changes = {row["id"]: row for row in (failed, erred, passed)}

    lines = [row.line.plain.rstrip() for row in rows_of(changes, mark=9)]

    assert lines[1:] == [
        "  cccc made  +1 -0  tests passed",
        "  bbbb made  +1 -0  tests error: its timeout came first",
        "  aaaa made  +1 -0  tests failed: exit 2",
    ]


HOSTILE = "\x1b]0;owned\x07 [bold]not markup[/bold]"
"""A line of a file an agent wrote: a control that would retitle a terminal, and markup."""


async def test_a_commit_s_patch_is_asked_for_once_and_drawn_a_page_at_a_time_through_safetext(root, repo):
    """Enter on a commit asks for its patch, which the runtime reads once: opened again, it gives the patch it kept.
    Its lines are drawn a page at a time, and Enter on the last row draws on. Each line is text, whatever it holds: a
    control shows as its escape, and markup as itself."""
    lines = "".join(f"line {number} of a long file\n" for number in range(800))

    async with attached(team(lambda cwd: commit(cwd, "long.txt", f"{HOSTILE}\n{lines}")), root, repo) as (
        owner,
        pilot,
    ):
        await pilot.press(*"go", "enter")
        await looked(owner)
        await drawn(pilot, lambda text: "1 commit" in text)
        await pilot.press("alt+d")
        await drawn(pilot, lambda text: "What changed" in text and "add long.txt" in text)
        await pilot.press("down", "enter")
        first = await drawn(pilot, lambda text: "Read in @lead's worktree." in text)
        await pilot.press("up")
        last = await drawn(pilot, lambda text: "more lines: Enter reads on" in text)
        await pilot.press("enter")
        patch = pilot.app.screen
        assert isinstance(patch, Patch)
        on = await drawn(pilot, lambda text: patch.shown > PAGE)
        await pilot.press("escape")
        await drawn(pilot, lambda text: "What changed" in text)
        await pilot.press("enter")
        again = await drawn(pilot, lambda text: "Read in @lead's worktree." in text)
        asked = diffs_read(await of_type(owner, "effect.requested"))
        records = await of_type(owner, "repo.diffed")

    head = git("rev-parse", "platoon-harness/s/lead", cwd=repo).strip()
    lines = patch.diff.lines if patch.diff else None
    assert lines is not None and len(lines) > PAGE
    assert f"{head[:12]} patch, {len(lines)} lines" in first
    assert "    7 +\\x1b]0;owned\\x07 [bold]not markup[/bold]" in first
    assert f"{len(lines) - PAGE} more lines: Enter reads on" in last
    assert f"{lines[PAGE].number:>5} {lines[PAGE].text}" in on and "more lines" not in on
    assert [line.number for line in lines] == list(range(1, len(lines) + 1))
    assert f"{head[:12]} patch, {len(lines)} lines" in again
    assert len(asked) == len(records) == 1


async def test_a_cut_patch_says_where_it_was_cut(root, repo):
    """At the end of the last line within 64 KiB, below its last line, and that the rest is in git at its commit."""
    lines = "".join(f"line {number} of a long file\n" for number in range(4000))

    async with worked_on(team(lambda cwd: commit(cwd, "long.txt", lines)), root, repo) as owner:
        sha = (await of_type(owner, "repo.committed"))[0].data["sha"]
        diff = await read_of(owner, sha)

    assert diff.lines is not None
    rows = [row.line.plain.rstrip() for row in patch_rows(diff, len(diff.lines), 120)]
    kept = diff.lines[-1]
    assert diff.above[0] == f"{sha[:12]} patch, cut after {kept.number} lines at 64 KiB"
    assert rows[-2] == f"{kept.number:>5} {kept.text}"
    assert rows[-1] == f"Cut here, at the end of the last line within 64 KiB: the rest is in git, at {sha[:12]}."


async def test_a_line_longer_than_one_result_holds_is_drawn_and_so_is_every_line_after_it(root, repo):
    """A patch is read whole, so a line past the 12 KiB a `blob.get` result holds, as a minified file's can be, is
    drawn like any other, and so is each line after it."""
    long = "y" * 13_000
    text = "short\n" * 50 + f"{long}\n" + "tail\n" * 5

    async with worked_on(team(lambda cwd: commit(cwd, "app.min.js", text)), root, repo) as owner:
        sha = (await of_type(owner, "repo.committed"))[0].data["sha"]
        diff = await read_of(owner, sha)

    assert diff.lines is not None and diff.below is None
    assert [(line.number, line.text, line.tone) for line in diff.lines[-6:]] == [
        (57, f"+{long}", "good"),
        *((number, "+tail", "good") for number in range(58, 63)),
    ]
    rows = patch_rows(diff, PAGE, 120)
    assert "".join(row.line.plain[6:] for row in rows if row.key == "57") == f"+{long}"
    assert rows[-1].line.plain.rstrip() == "   62 +tail"


async def test_an_effect_that_ends_keeping_no_diff_is_refused_where_waiting_would_never_end(root, repo):
    """A diff is read by the effect `repo diff` gave, and a test's, which keeps none, is refused once it ends."""
    tested = team(worked, test={"command": ["true"], "timeout": "1m"})
    async with worked_on(tested, root, repo) as owner:
        sha = (await of_type(owner, "repo.committed"))[0].data["sha"]
        effect = await owner.repo_test(sha)
        await until(lambda: of_type(owner, "repo.tested"), owner)
        with pytest.raises(Refused) as refused:
            await review.read(owner, effect)

    assert (refused.value.refusal.code, refused.value.refusal.detail) == ("not_found", f"effect {effect} kept no diff")


async def test_what_follows_a_line_separator_in_an_added_line_is_drawn_as_added_never_as_context(root, repo):
    """Git ends a line at a newline alone, and the kernel numbers lines at a form feed or U+2028 too, so what follows
    one in an added line is drawn as that added line goes on, the separator shown as its escape, and a file's first
    line hidden in it heads nothing."""
    text = "ok();\u2028 evil();\nb = 1\x0cdiff --git a/x b/x\nc = 2\n"

    async with worked_on(team(lambda cwd: commit(cwd, "app.js", text)), root, repo) as owner:
        sha = (await of_type(owner, "repo.committed"))[0].data["sha"]
        diff = await read_of(owner, sha)

    assert diff.lines is not None
    assert [(line.number, line.text, line.tone, line.continues) for line in diff.lines[6:]] == [
        (7, "+ok();\\u2028", "good", False),
        (8, " evil();", "good", True),
        (9, "+b = 1\\x0c", "good", False),
        (10, "diff --git a/x b/x", "good", True),
        (11, "+c = 2", "good", False),
    ]
    rows = [row.line.plain for row in patch_rows(diff, PAGE, 120)]
    assert rows[7:9] == ["    8 ↳  evil();", "    9 +b = 1\\x0c"]


async def test_a_binary_file_is_named_and_never_drawn(root, repo):
    """As git names it, while what it holds is never drawn; and a patch that is no text is not drawn at all, saying
    why."""
    secret = "\x00\x01 bytes nobody reads \x00" * 8

    def work(cwd: Path) -> None:
        commit(cwd, "blob.bin", secret)
        (cwd / "latin.txt").write_bytes(b"caf\xe9\n")
        git("add", "latin.txt", cwd=cwd)
        git("commit", "-q", "-m", "add latin.txt", cwd=cwd)

    async with attached(team(work), root, repo) as (owner, pilot):
        await pilot.press(*"go", "enter")
        await looked(owner)
        await drawn(pilot, lambda text: "2 commits" in text)
        await pilot.press("alt+d")
        await drawn(pilot, lambda text: "What changed" in text and "add blob.bin" in text)
        await pilot.press("down", "down", "enter")
        binary = await drawn(pilot, lambda text: "Binary files" in text)
        latin = (await of_type(owner, "repo.committed"))[1].data["sha"]
        diff = await read_of(owner, latin)

    assert "    4 Binary files /dev/null and b/blob.bin differ" in binary and "bytes nobody reads" not in binary
    assert diff.lines is None
    assert [row.line.plain for row in patch_rows(diff, PAGE, 120)] == [
        "It is not UTF-8, so it is not drawn, and no line of it can be cited."
    ]


async def test_an_uncommitted_diff_says_when_it_was_read(root, repo):
    """Enter on a workspace asks for what it holds uncommitted, read at each ask, and says the HEAD it is against and
    when its reading began, on the session's clock."""
    clock = ManualClock(1000.0)
    async with attached(team(worked), root, repo, clock) as (owner, pilot):
        await pilot.press(*"go", "enter")
        await looked(owner)
        await drawn(pilot, lambda text: "1 commit," in text)
        await pilot.press("alt+d")
        await drawn(pilot, lambda text: "What changed" in text and "notes.txt" in text)
        await pilot.press("enter")
        text = await drawn(pilot, lambda text: "What it held at" in text)

    head = git("rev-parse", "platoon-harness/s/lead", cwd=repo).strip()
    at = time.strftime("%H:%M:%S", time.localtime(1000.0))
    assert f"@lead uncommitted against {head[:12]}, " in text
    assert f"What it held at {at}, read in @lead's worktree." in text
    assert "+unfinished" in text


async def test_a_snapshot_or_isolated_workspace_s_diff_says_where_it_was_read(root, repo):
    """In the repository git read it in: a snapshot's own, an isolated one's inside its isolation, an agent's worktree,
    or for a commit whose workspace has gone, yours."""
    async with worked_on(team(worked, workspace="snapshot"), root, repo) as owner:
        sha = (await of_type(owner, "repo.committed"))[0].data["sha"]
        of_commit, of_workspace = [await read_of(owner, of) for of in (sha, "@lead")]

    assert of_commit.above[1] == "Read in @lead's own repository, a snapshot."
    assert of_workspace.above[1].startswith("What it held at ")
    assert of_workspace.above[1].endswith(", read in @lead's own repository, a snapshot.")
    assert place("@ada", "isolated", commit=True) == "@ada's own repository, inside its isolation"
    assert place("@ada", "worktree", commit=False) == "@ada's worktree"
    assert place("shared", None, commit=True) == "your repository"
    assert place("shared", None, commit=False) == "your checkout"


async def test_a_comment_on_chosen_lines_is_a_message_to_the_commit_s_maker_citing_them(root, repo):
    """Space chooses a line of the patch and, on another, every line between; `c` writes a comment at the foot, which
    goes to the agent whose workspace made the commit, its `based_on` citing those lines by the record's ref. Esc goes
    back to the patch keeping what was written. With no line chosen it cites the commit."""

    def work(cwd: Path) -> None:
        commit(cwd, "notes.txt", "one\ntwo\nthree\n")

    async with attached(team(work), root, repo) as (owner, pilot):
        await pilot.press(*"go", "enter")
        await looked(owner)
        await drawn(pilot, lambda text: "1 commit" in text)
        await pilot.press("alt+d")
        await drawn(pilot, lambda text: "What changed" in text and "add notes.txt" in text)
        await pilot.press("down", "enter")
        await drawn(pilot, lambda text: "Read in @lead's worktree." in text)
        await pilot.press(*["down"] * 6, "space", "down", "space", "c")
        about = await drawn(pilot, lambda text: "Comment to @lead" in text)
        await pilot.press(*"why", "escape")
        kept = await drawn(pilot, lambda text: "Comment to @lead" not in text)
        await pilot.press("c")
        await drawn(pilot, lambda text: "Comment to @lead" in text)
        await pilot.press("space", *"these?", "enter")
        [lines] = await until(lambda: comments(owner), owner)
        await pilot.press("c")
        await drawn(pilot, lambda text: "Comment to @lead on the commit" in text)
        await pilot.press(*"and", "space", *"this?", "enter")
        _, whole = await until(lambda: comments(owner), owner, lambda found: len(found) == 2)
        [record] = await of_type(owner, "repo.diffed")
        [made] = await of_type(owner, "repo.committed")

    sha = made.data["sha"]
    assert f"Comment to @lead on lines 7 to 8 of {sha[:12]}'s patch" in about
    assert "c: comment" in kept and "Read in @lead's worktree." in kept
    assert (lines.stream, lines.gist, lines.based_on) == (
        "inbox/lead",
        "why these?",
        (f"{record.stream}@{record.version}#L7-8",),
    )
    assert (whole.gist, whole.based_on) == ("and this?", (f"{made.stream}@{made.version}",))


async def comments(session: Session) -> list[Any]:
    """What you sent that cites something, as only a comment of the test's does."""
    return [event for event in await of_type(session, "message.sent") if event.actor == "human:you" and event.based_on]


async def test_a_comment_on_a_change_no_agent_made_has_nobody_to_go_to(root, repo):
    """Your checkout is no agent's workspace, so a comment on what it holds uncommitted is refused, saying why, and
    nothing is sent."""
    lead = {"harness": working(lambda cwd: (cwd / "README").write_text("edited\n")), "workspace": "shared"}
    shared = Team.model_validate({"roles": {"lead": lead}, "topology": {"edges": {"lead": ["human"]}}})
    async with worked_on(shared, root, repo) as owner:
        diff = await review.read(owner, (await owner.repo_diff("shared"))["effect"])
        with pytest.raises(Refused) as refused:
            await review.comment(owner, diff, (1, 2), "who did this?")
        sent = await comments(owner)

    assert diff.to is None and sent == []
    assert diff.unsendable == "A comment goes to whoever made the change, and no agent's workspace made your checkout."
    assert refused.value.refusal.code == "not_found"
