"""The look on real git under `tmp_path`: what it finds, whose each commit is, what it reads of a workspace's state,
and that it changes nothing. Then the look through a session: after each turn, one at a time, and at a stop."""

import asyncio
import json
import stat
import threading
from pathlib import Path
from typing import Any

import pytest

from platoon_harness import Session, Team
from platoon_harness.primitives.repo import Commit
from platoon_harness.runtime import host, looks
from platoon_harness.runtime.git import GitError
from platoon_harness.testing import Hang

from .gitting import Working, commit, git, repository, working
from .support import harness, in_state, of_type, scripted, until
from .test_workspaces import made

pytestmark = pytest.mark.timeout(60)

EARLIER, LATER = 1_700_000_000, 1_700_000_100


@pytest.fixture
def repo(tmp_path, monkeypatch) -> Path:
    return repository(tmp_path / "repo", monkeypatch)


def tips(repo: Path) -> list[str]:
    return looks.tips_of(git("for-each-ref", "--format=%(objectname) %(refname)", cwd=repo))


def worktree(repo: Path, tmp_path: Path, agent: str) -> tuple[Path, str]:
    """An agent's worktree, made now at the checkout's HEAD, and its base."""
    workspace = made(repo, tmp_path / agent, agent=agent)
    assert workspace.base is not None
    return Path(workspace.path), workspace.base


def seen(where: str, root: Path, base: str | None, opened: list[str], makers: dict[str, Path], **options: Any):
    return looks.look(root, base=base, tips=opened, last=options.pop("last", None), makers=makers, **options)


def made_in(found: looks.Seen) -> dict[str, str | None]:
    return {commit["sha"]: commit["made_in"] for commit in found.commits}


# Whose a commit is.


def test_a_commit_is_the_agent_s_whose_workspace_made_it(repo, tmp_path):
    opened = tips(repo)
    ada, base = worktree(repo, tmp_path, "ada")
    work = commit(ada, "work")

    found = seen("@ada", ada, base, opened, {"@ada": ada, "shared": repo}, record=False)

    assert made_in(found) == {work: "@ada"}
    assert found.commits[0]["branch"] == "platoon-harness/s/ada"


def test_a_commit_is_its_maker_s_whatever_order_the_looks_run_in(repo, tmp_path):
    opened = tips(repo)
    (ada, base), (bob, _) = worktree(repo, tmp_path, "ada"), worktree(repo, tmp_path, "bob")
    work = commit(ada, "work", when=EARLIER)
    git("reset", "-q", "--hard", work, cwd=bob)
    makers = {"@ada": ada, "@bob": bob, "shared": repo}

    bob_first = seen("@bob", bob, base, opened, makers, record=False)
    ada_after = seen("@ada", ada, base, opened, makers, record=False)

    assert made_in(bob_first) == made_in(ada_after) == {work: "@ada"}


def test_a_commit_another_workspace_moved_onto_stays_its_maker_s(repo, tmp_path):
    opened = tips(repo)
    (ada, base), (bob, _) = worktree(repo, tmp_path, "ada"), worktree(repo, tmp_path, "bob")
    work = commit(ada, "work", when=EARLIER)
    git("merge", "-q", "--ff-only", work, cwd=bob)
    built = commit(bob, "more", when=LATER)

    found = seen("@bob", bob, base, opened, {"@ada": ada, "@bob": bob, "shared": repo}, record=False)

    assert made_in(found) == {work: "@ada", built: "@bob"}


def test_a_commit_two_workspaces_record_making_is_nobody_s(repo, tmp_path):
    opened = tips(repo)
    (ada, base), (bob, _) = worktree(repo, tmp_path, "ada"), worktree(repo, tmp_path, "bob")
    one, two = commit(ada, "same", when=EARLIER), commit(bob, "same", when=EARLIER)
    assert one == two

    found = seen("@ada", ada, base, opened, {"@ada": ada, "@bob": bob, "shared": repo}, record=False)

    assert made_in(found) == {one: None}


def test_a_commit_in_the_shared_workspace_is_nobody_s(repo, tmp_path):
    opened, base = tips(repo), git("rev-parse", "HEAD", cwd=repo).strip()
    yours = commit(repo, "yours")

    found = seen("shared", repo, base, opened, {"shared": repo}, record=False)

    assert made_in(found) == {yours: "shared"}


def test_a_commit_no_workspace_made_is_nobody_s(repo, tmp_path):
    opened = tips(repo)
    ada, base = worktree(repo, tmp_path, "ada")
    elsewhere = tmp_path / "elsewhere"
    git("clone", "-q", str(repo), str(elsewhere), cwd=tmp_path)
    fetched = commit(elsewhere, "fetched", when=EARLIER)
    git("fetch", "-q", str(elsewhere), "main", cwd=ada)
    git("reset", "-q", "--hard", fetched, cwd=ada)

    found = seen("@ada", ada, base, opened, {"@ada": ada, "shared": repo}, record=False)

    assert made_in(found) == {fetched: None}


def test_a_workspace_removed_while_a_look_reads_is_gone_as_one_removed_before(repo, tmp_path):
    """Another agent's stop may end its workspace while a look reads its reflog, and that is no failure of this look."""
    opened = tips(repo)
    (ada, base), (bob, _) = worktree(repo, tmp_path, "ada"), worktree(repo, tmp_path, "bob")
    work = commit(bob, "work")
    makers = {"@ada": ada, "@bob": bob, "shared": repo}
    git("worktree", "remove", "-f", "-f", str(ada), cwd=repo)

    found = seen("@bob", bob, base, opened, makers, record=False)

    assert made_in(found) == {work: "@bob"}


def test_a_maker_workspace_git_cannot_read_fails_the_look(repo, tmp_path):
    """One still on disk that git cannot read might have made the commit, so the look cannot say whose it is."""
    opened = tips(repo)
    (ada, base), (bob, _) = worktree(repo, tmp_path, "ada"), worktree(repo, tmp_path, "bob")
    commit(bob, "work")
    (ada / ".git").write_text("gitdir: /nowhere\n")

    with pytest.raises(GitError):
        seen("@bob", bob, base, opened, {"@ada": ada, "@bob": bob, "shared": repo}, record=False)


def test_commits_merged_from_the_checkout_are_not_the_merger_s(repo, tmp_path):
    opened = tips(repo)
    ada, base = worktree(repo, tmp_path, "ada")
    yours = commit(repo, "yours", when=EARLIER)
    mine = commit(ada, "mine", when=EARLIER)
    git("merge", "-q", "--no-edit", "main", cwd=ada, when=LATER)
    merge = git("rev-parse", "HEAD", cwd=ada).strip()

    found = seen("@ada", ada, base, opened, {"@ada": ada, "shared": repo}, record=False)

    assert made_in(found) == {yours: "shared", mine: "@ada", merge: "@ada"}
    assert found.commits[-1]["sha"] == merge and found.commits[-1]["parents"] == [mine, yours]


# What a look finds.


def test_a_commit_the_session_started_with_is_never_recorded(repo, tmp_path):
    git("checkout", "-q", "-b", "side", cwd=repo)
    older = commit(repo, "older")
    git("checkout", "-q", "main", cwd=repo)
    opened = tips(repo)
    ada, base = worktree(repo, tmp_path, "ada")
    git("merge", "-q", "--no-ff", "--no-edit", "side", cwd=ada)

    found = seen("@ada", ada, base, opened, {"@ada": ada, "shared": repo}, record=False)

    assert [commit["sha"] for commit in found.commits] == [git("rev-parse", "HEAD", cwd=ada).strip()]
    assert older not in made_in(found)


def test_a_commit_on_a_detached_head_is_found(repo, tmp_path):
    opened = tips(repo)
    ada, base = worktree(repo, tmp_path, "ada")
    git("checkout", "-q", "--detach", cwd=ada)
    work = commit(ada, "work")

    found = seen("@ada", ada, base, opened, {"@ada": ada, "shared": repo}, record=True)

    assert made_in(found) == {work: "@ada"}
    assert found.commits[0]["branch"] is None and found.reading["branch"] is None


def test_a_cited_commit_is_recorded_before_the_commit_citing_it(repo, tmp_path):
    opened = tips(repo)
    (ada, base), (bob, _) = worktree(repo, tmp_path, "ada"), worktree(repo, tmp_path, "bob")
    cited = commit(bob, "cited", when=EARLIER)
    citing = commit(ada, "citing", cites=cited[:8], when=LATER)

    found = seen("@ada", ada, base, opened, {"@ada": ada, "@bob": bob, "shared": repo}, record=False)

    assert [commit["sha"] for commit in found.commits] == [cited, citing]
    assert found.commits[0]["branch"] is None and found.commits[0]["made_in"] == "@bob"
    assert found.commits[1]["informed_by"] == [{"written": cited[:8], "sha": cited}]


def test_informed_by_trailers_resolve_to_full_shas_and_unresolved_text_is_kept(repo, tmp_path):
    opened = tips(repo)
    ada, base = worktree(repo, tmp_path, "ada")
    first = commit(ada, "first")
    missing = "deadbeefdeadbeef"
    citing = commit(ada, "citing", cites=f"{first},{first[:6]},{missing},the parser fix")

    found = seen("@ada", ada, base, opened, {"@ada": ada, "shared": repo}, record=False)

    [cited] = [found_commit for found_commit in found.commits if found_commit["sha"] == citing]
    assert cited["informed_by"] == [
        {"written": first, "sha": first},
        {"written": first[:6], "sha": first},
        {"written": missing, "sha": None},
        {"written": "the parser fix", "sha": None},
    ]


def test_an_informed_by_value_naming_a_ref_is_kept_unresolved(repo, tmp_path):
    """A ref names whatever it points at when asked, so even a branch named in hex digits resolves to nothing."""
    opened = tips(repo)
    ada, base = worktree(repo, tmp_path, "ada")
    first = commit(ada, "first")
    git("branch", "beefcafe", first, cwd=ada)
    citing = commit(ada, "citing", cites="HEAD,main,beefcafe,HEAD~1")

    found = seen("@ada", ada, base, opened, {"@ada": ada, "shared": repo}, record=False)

    [cited] = [found_commit for found_commit in found.commits if found_commit["sha"] == citing]
    assert cited["informed_by"] == [
        {"written": written, "sha": None} for written in ("HEAD", "main", "beefcafe", "HEAD~1")
    ]


def test_what_an_agent_wrote_of_a_commit_is_cut_to_fit_saying_so(repo, tmp_path):
    opened = tips(repo)
    ada, base = worktree(repo, tmp_path, "ada")
    git("config", "user.name", "A" * 300, cwd=ada)
    first = commit(ada, "first")
    values = [first, "x" * 300, *(f"note {number}" for number in range(20))]
    citing = commit(ada, "citing", cites=",".join(values))

    found = seen("@ada", ada, base, opened, {"@ada": ada, "shared": repo}, record=False)

    [cited] = [found_commit for found_commit in found.commits if found_commit["sha"] == citing]
    assert cited["informed_by_total"] == 22 and len(cited["informed_by"]) == 16
    assert cited["informed_by"][:2] == [{"written": first, "sha": first}, {"written": "x" * 255 + "…", "sha": None}]
    assert cited["author"] == "A" * 255 + "…"
    Commit.model_validate_json(json.dumps(cited))


async def test_a_long_informed_by_value_never_blinds_a_workspace_s_looks(repo, tmp_path):
    team = team_of(
        harness=working(lambda cwd: commit(cwd, "work", cites="see " + "x" * 300), lambda cwd: commit(cwd, "more"))
    )
    async with Session.start(team, name="s", root=tmp_path, cwd=repo) as session:
        await session.spawn("ada", "worker", "work")
        await looked(session)
        await session.send("@ada", "more")
        await looked(session, 2)
        found = await committed(session)
        gaps = [
            event for event in await of_type(session, "gap.recorded") if event.data["what"] == "workspace_unobserved"
        ]

    assert gaps == []
    assert [event.gist.split(" ", 1)[1] for event in found] == ["add work", "add more"]


# What its branch no longer reaches.


def test_a_rewrite_is_what_a_branch_no_longer_reaches_of_its_last_look(repo, tmp_path):
    opened = tips(repo)
    ada, base = worktree(repo, tmp_path, "ada")
    one, two = commit(ada, "one"), commit(ada, "two")
    git("reset", "-q", "--hard", base, cwd=ada)
    last = {"head": two, "branch": "platoon-harness/s/ada"}

    found = seen("@ada", ada, base, opened, {"@ada": ada, "shared": repo}, last=last, record=False)

    assert found.rewrite == {"branch": "platoon-harness/s/ada", "was": two, "now": base, "dropped": [one, two]}


def test_moving_an_untouched_branch_is_no_rewrite(repo, tmp_path):
    """A worker picks its parent with `git reset --hard` on its untouched branch, forward onto what was integrated
    since, or back onto what the session started with."""
    first = git("rev-parse", "HEAD", cwd=repo).strip()
    commit(repo, "second")
    opened = tips(repo)
    ada, base = worktree(repo, tmp_path, "ada")
    integrated = commit(repo, "integrated")
    last = {"head": base, "branch": "platoon-harness/s/ada"}
    makers = {"@ada": ada, "shared": repo}

    git("reset", "-q", "--hard", integrated, cwd=ada)
    forward = seen("@ada", ada, base, opened, makers, last=last, record=False)
    git("reset", "-q", "--hard", first, cwd=ada)
    back = seen("@ada", ada, base, opened, makers, last=last, record=False)

    assert forward.rewrite is None and back.rewrite is None


# What it reads of a workspace.


def test_a_merge_under_way_and_its_conflicted_paths_are_recorded(repo, tmp_path):
    opened = tips(repo)
    ada, base = worktree(repo, tmp_path, "ada")
    commit(ada, "README", "ours\n")
    commit(repo, "README", "theirs\n")
    with pytest.raises(Exception):  # noqa: B017  The merge stops on its conflict, which is the point.
        git("merge", "-q", "main", cwd=ada)
    (ada / "notes.txt").write_text("loose\n")

    reading = seen("@ada", ada, base, opened, {"@ada": ada, "shared": repo}, record=True).reading

    assert (reading["under_way"], reading["conflicted"], reading["total"]) == ("merge", 1, 2)
    assert [(path["path"], path["state"]) for path in reading["paths"]] == [
        ("README", "conflicted"),
        ("notes.txt", "untracked"),
    ]


def test_a_rebase_under_way_names_the_branch_it_rewrites(repo, tmp_path):
    opened = tips(repo)
    ada, base = worktree(repo, tmp_path, "ada")
    commit(ada, "README", "ours\n")
    commit(repo, "README", "theirs\n")
    with pytest.raises(Exception):  # noqa: B017
        git("rebase", "-q", "main", cwd=ada)

    reading = seen("@ada", ada, base, opened, {"@ada": ada, "shared": repo}, record=True).reading

    assert (reading["under_way"], reading["rebasing"], reading["branch"]) == ("rebase", "platoon-harness/s/ada", None)


def test_an_untracked_or_binary_file_s_line_counts_are_unmeasured_not_zero(repo, tmp_path):
    opened = tips(repo)
    ada, base = worktree(repo, tmp_path, "ada")
    (ada / "image.bin").write_bytes(b"\0\1\2")
    git("add", "image.bin", cwd=ada)
    git("commit", "-q", "-m", "an image", cwd=ada)
    (ada / "image.bin").write_bytes(b"\0\1\3")
    (ada / "README").write_text("hello\nagain\n")
    (ada / "new.txt").write_text("one\ntwo\n")

    found = seen("@ada", ada, base, opened, {"@ada": ada, "shared": repo}, record=True)

    assert (found.commits[0]["added"], found.commits[0]["removed"], found.commits[0]["files"]) == (None, None, 1)
    assert {path["path"]: (path["added"], path["removed"]) for path in found.reading["paths"]} == {
        "README": (1, 0),
        "image.bin": (None, None),
        "new.txt": (None, None),
    }


def test_a_long_list_of_paths_says_how_many_it_left_out(repo, tmp_path):
    opened = tips(repo)
    ada, base = worktree(repo, tmp_path, "ada")
    for index in range(400):
        (ada / f"{'a-rather-long-file-name-' * 2}{index:03}.txt").write_text("x\n")

    found = seen("@ada", ada, base, opened, {"@ada": ada, "shared": repo}, record=True)

    reading = found.reading
    assert reading["total"] == 400 and 0 < len(reading["paths"]) < 400
    assert found.whole is not None and len(json.loads(found.whole)) == 400
    assert len(json.dumps(reading).encode()) < 16 * 1024


def test_a_look_that_sees_head_move_records_the_gap_not_a_mixed_state(repo, tmp_path, monkeypatch):
    opened = tips(repo)
    ada, base = worktree(repo, tmp_path, "ada")
    real = looks.git

    def moving(*args: str, **options: Any) -> str:
        said = real(*args, **options)
        if args[0] == "rev-list":
            commit(ada, "meanwhile")
        return said

    monkeypatch.setattr(looks, "git", moving)
    commit(ada, "work")

    with pytest.raises(GitError, match="HEAD moved during the look"):
        seen("@ada", ada, base, opened, {"@ada": ada, "shared": repo}, record=True)


def test_a_look_changes_no_ref_index_or_file(repo, tmp_path):
    opened = tips(repo)
    ada, base = worktree(repo, tmp_path, "ada")
    commit(ada, "work", cites="HEAD")
    (ada / "README").write_text("edited\n")
    (ada / "loose.txt").write_text("loose\n")
    (repo / "yours.txt").write_text("yours\n")

    def state() -> list[Any]:
        files = sorted(
            (str(path), path.stat().st_mtime_ns, path.read_bytes())
            for top in (repo, ada.parent)
            for path in top.rglob("*")
            if path.is_file()
        )
        refs = [git("for-each-ref", cwd=where) + git("reflog", "--all", cwd=where) for where in (repo, ada)]
        return [files, refs]

    before = state()
    seen("shared", repo, git("rev-parse", "HEAD", cwd=repo).strip(), opened, {"@ada": ada, "shared": repo}, record=True)
    seen("@ada", ada, base, opened, {"@ada": ada, "shared": repo}, record=True)

    assert state() == before


# Through a session.


def team_of(**worker: Any) -> Team:
    """A lead and workers, each in a workspace of the mode the workers' role names, a worktree unless it says."""
    worker = {"count": 0, "workspace": "worktree", **worker}
    roles = {"lead": {"harness": scripted(), "workspace": worker["workspace"]}, "worker": worker}
    return Team.model_validate({"roles": roles})


async def committed(session: Session) -> list[Any]:
    return await of_type(session, "repo.committed")


async def looked(session: Session, count: int = 1) -> list[Any]:
    """Wait for `count` probes to finish."""

    async def finished() -> list[Any]:
        return [event for event in await of_type(session, "effect.finished") if event.data["kind"] == "probe"]

    return await until(finished, session, lambda found: len(found) >= count)


async def test_a_turn_s_commits_are_recorded_after_it_ends_as_its_agent_s(repo, tmp_path):
    team = team_of(harness=working(lambda cwd: commit(cwd, "work")))
    async with Session.start(team, name="s", root=tmp_path, cwd=repo) as session:
        await session.spawn("ada", "worker", "work")
        await looked(session)
        [found] = await committed(session)
        [ended] = [event for event in await of_type(session, "turn.ended") if event.agent == "ada"]
        rows = (await session.submit("view.watch", name="changes")).result["rows"]

    assert found.data["made_in"] == "@ada" and found.cause == () and found.seq > ended.seq
    assert (found.agent, found.turn) == (None, None)
    assert {row["id"] for row in rows} == {f"commit/{found.data['sha']}", "workspace/@ada"}


async def test_an_informed_by_value_naming_an_event_is_cited_by_the_commit_s_record(repo, tmp_path):
    """A worker's commit cites the goal it was handed, `agent/ada@1`, by its ref, which git cannot resolve and the
    record can; a ref that names no event stays as it was written, saying why."""
    team = team_of(harness=working(lambda cwd: commit(cwd, "work", cites="agent/ada@1,board/notes/plan@1")))
    async with Session.start(team, name="s", root=tmp_path, cwd=repo) as session:
        await session.spawn("ada", "worker", "work")
        await looked(session)
        [found] = await committed(session)

    assert found.based_on == ("agent/ada@1",)
    assert found.data["informed_by"] == [
        {"written": "agent/ada@1", "sha": None, "why": None},
        {"written": "board/notes/plan@1", "sha": None, "why": "no_event"},
    ]


async def test_a_commit_made_elsewhere_cites_no_event_of_this_session(tmp_path, monkeypatch):
    """A commit git made in another clone a year ago, citing `agent/ada@1` of the session it came from, is fetched into
    ada's workspace: no workspace of this session made it, so its trailer names nothing here, though this session has
    an `agent/ada@1` ada was handed."""
    repo = repository(tmp_path / "repo", monkeypatch, when=EARLIER - 10)
    elsewhere = tmp_path / "elsewhere"
    git("clone", "-q", str(repo), str(elsewhere), cwd=tmp_path)
    old = commit(elsewhere, "old.txt", when=EARLIER, cites="agent/ada@1")

    def fetch(cwd: Path) -> None:
        git("fetch", "-q", str(elsewhere), "main", cwd=cwd)
        git("reset", "-q", "--hard", old, cwd=cwd)

    async with Session.start(team_of(harness=working(fetch)), name="s", root=tmp_path, cwd=repo) as session:
        await session.spawn("ada", "worker", "a goal of this session's")
        await looked(session)
        [found] = await committed(session)
        reached = await session.contributors(f"{found.stream}@{found.version}")

    assert (found.data["sha"], found.data["made_in"], found.based_on) == (old, None, ())
    assert found.data["informed_by"] == [{"written": "agent/ada@1", "sha": None, "why": "unread"}]
    assert [(row.maker, row.kinds) for row in reached.rows] == [(None, ())]


async def test_the_shared_workspace_s_uncommitted_state_is_recorded_only_when_a_role_works_in_it(repo, tmp_path):
    (repo / "yours.txt").write_text("your own edit\n")
    readings = {}
    for mode in ("worktree", "shared"):
        team = team_of(harness=working(lambda cwd: None), workspace=mode)
        async with Session.start(team, name=mode, root=tmp_path, cwd=repo) as session:
            await session.spawn("ada", "worker", "look")
            await looked(session)
            changed = await of_type(session, "workspace.changed")
            readings[mode] = next(event.data for event in changed if event.data["workspace"] == "shared")

    assert readings["worktree"]["paths"] is None
    assert [path["path"] for path in readings["shared"]["paths"]] == ["yours.txt"]


async def test_the_probe_covers_a_harness_that_reports_nothing(repo, tmp_path):
    """A one-shot program ends with its turn, so its stop is what looks."""
    program = repo / "work.sh"
    program.write_text("#!/bin/sh\necho done > done.txt && git add done.txt && git commit -q -m 'one shot'\n")
    program.chmod(program.stat().st_mode | stat.S_IXUSR)
    harnessed = {"command": [str(program)], "mode": "oneshot"}
    async with Session.start(team_of(harness=harnessed), name="s", root=tmp_path, cwd=repo) as session:
        await session.spawn("ada", "worker", "go")
        await in_state(session, "ada", "ended")
        await until(lambda: committed(session), session)
        [found] = await committed(session)
        ending = await session.settled(timeout="20s")

    assert found.gist.endswith(" one shot") and found.data["made_in"] == "@ada"
    assert ending.unobserved == ()
    assert git("log", "-1", "--format=%s", "platoon-harness/s/ada", cwd=repo).strip() == "one shot"


async def test_a_look_that_fails_records_the_gap_and_its_agent_works_on(repo, tmp_path):
    def broken(cwd: Path) -> None:
        commit(cwd, "work")
        (cwd / ".git").write_text("gitdir: /nowhere\n")

    team = team_of(harness=working(broken, lambda cwd: None))
    async with Session.start(team, name="s", root=tmp_path, cwd=repo) as session:
        await session.spawn("ada", "worker", "work")
        await looked(session)
        gaps = [event for event in await of_type(session, "gap.recorded") if event.agent == "ada"]
        repo_events = [event async for event in session.events(match="repo/*")]
        status = await session.status("ada")

    assert [gap.data["what"] for gap in gaps] == ["workspace_unobserved"]
    assert all(event.data["workspace"] == "shared" for event in repo_events)
    assert status["state"] == "idle"


async def test_looks_run_one_at_a_time(repo, tmp_path, monkeypatch):
    entered: list[str] = []
    gate = threading.Event()
    real = host.look

    def held(root: Path, **options: Any) -> Any:
        entered.append("shared" if root == repo else root.parent.name)
        if len(entered) == 1:
            assert gate.wait(10)
        return real(root, **options)

    monkeypatch.setattr(host, "look", held)
    team = team_of(harness=working(lambda cwd: commit(cwd, "work")))
    async with Session.start(team, name="s", root=tmp_path, cwd=repo) as session:
        await session.spawn("ada", "worker", "work")
        await session.spawn("bob", "worker", "work")

        async def started() -> list[Any]:
            return [event for event in await of_type(session, "effect.started") if event.data["kind"] == "probe"]

        await until(started, session, lambda found: len(found) == 2)
        held_back = list(entered)
        gate.set()
        await looked(session, 2)

    assert held_back == ["shared"]
    assert entered in (["shared", "ada", "shared", "bob"], ["shared", "bob", "shared", "ada"])


async def stops(session: Session) -> list[Any]:
    return [event for event in await of_type(session, "effect.finished") if event.data["kind"] == "stop"]


async def test_an_ended_agent_s_stop_looks_before_it_ends_its_workspace(repo, tmp_path):
    team = team_of(harness=working(lambda cwd: commit(cwd, "work")))
    async with Session.start(team, name="s", root=tmp_path, cwd=repo) as session:
        await session.spawn("ada", "worker", "work")
        await looked(session)
        (Path((await session.status("ada"))["workspace"]["path"]) / "late.txt").write_text("late\n")
        await session.cancel_agent("@ada")
        await in_state(session, "ada", "ended")
        await until(lambda: stops(session), session)
        changed = [event for event in await of_type(session, "workspace.changed") if event.data["workspace"] == "@ada"]
        ending = await session.ending()

    assert [path["path"] for path in changed[-1].data["paths"]] == ["late.txt"]
    assert ending.workspaces[0]["why"] == ["1 uncommitted path: late.txt"]


async def test_a_turn_the_owner_s_stop_cut_off_is_looked_at_on_resume(repo, tmp_path):
    done = threading.Event()

    def work(cwd: Path) -> None:
        commit(cwd, "work")
        done.set()

    team = team_of(harness=harness(lambda: Working([work], [Hang()])))
    async with Session.start(team, name="s", root=tmp_path, cwd=repo) as session:
        await session.spawn("ada", "worker", "work")
        assert await asyncio.to_thread(done.wait, 10)
        assert await committed(session) == []
    async with Session.resume("s", root=tmp_path) as session:
        await looked(session)
        [found] = await until(lambda: committed(session), session)
        [cut] = [event for event in await of_type(session, "turn.ended") if event.agent == "ada"]

    assert found.data["made_in"] == "@ada"
    assert cut.data["reason"] == "stopped by its owner" and found.cause == () and found.seq > cut.seq
