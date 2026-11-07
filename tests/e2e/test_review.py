"""Review changes, in a real browser: what changed, in the words of the terminal's `/review`, each commit with its test
and its patch, a diff drawn as text under the page's policy, and a comment on its lines sent as a message that cites
them, over a session in a repository of the test's own, with its agent in a worktree."""

import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from playwright.async_api import Browser, Page, expect

from platoon_harness import Session, Team

from ..unit.runtime.gitting import commit, repository, working
from ..unit.runtime.support import in_state, of_type, until
from .support import SECONDS, opened, serving

pytestmark = [pytest.mark.e2e, pytest.mark.timeout(120)]

PARSER = "def parse(text):\n    return text.split()\n"
TESTED = {"command": ["true"], "timeout": "1m"}


@pytest.fixture
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("PLATOON_HARNESS_HOME", str(tmp_path / "home"))
    return tmp_path


def team(work: Callable[[Path], Any]) -> Team:
    bob = {"harness": working(work), "workspace": "worktree"}
    return Team.model_validate({"roles": {"bob": bob}, "test": TESTED})


def started(work: Callable[[Path], Any], root: Path, repo: Path) -> Session:
    """A session the test owns in `repo`, whose bob does `work` in its worktree."""
    return Session.start(team(work), name="s", root=root / "home", cwd=repo)


async def worked(session: Session) -> str:
    """Have bob take its turn, and give the commit the look after it recorded."""
    await in_state(session, "bob", "idle")
    await session.send("@bob", "go")
    [made] = await until(lambda: of_type(session, "repo.committed"), session)
    return made.data["sha"]


async def review(page: Page) -> None:
    """Open Review changes from the top bar, and wait for what changed."""
    await page.locator("[data-x-review]", has_text="Review changes").first.click()
    await expect(page.locator("#pane h2")).to_have_text("What changed", timeout=SECONDS)
    await expect(page.locator("#pane .x-change").first).to_be_visible(timeout=SECONDS)


def line(page: Page, number: int):
    return page.locator(f"#pane .x-pl[data-n='{number}']")


async def test_review_changes_lists_each_commit_with_its_test_and_patch(browser: Browser, root: Path, monkeypatch):
    """In the lines `/review` draws, a workspace's uncommitted diff beside its heading and each commit's Test and
    Patch, the patch drawn with its numbered lines and where it was read. A view link lists them, and asking for a
    diff, which is an act, is disabled there, saying why."""

    def work(cwd: Path) -> None:
        commit(cwd, "parser.py", PARSER, "Fix the parser")
        (cwd / "notes.txt").write_text("unfinished\n")

    repo = repository(root / "repo", monkeypatch)
    async with started(work, root, repo) as session:
        sha = await worked(session)
        await until(lambda: of_type(session, "workspace.changed"), session)
        async with serving("s", root / "home") as web:
            page, errors = await opened(browser, web.link("control"))
            await review(page)
            changes = page.locator("#pane .x-change")
            await expect(changes).to_have_text(
                [
                    "@bobUncommitted diff",
                    f"{sha[:12]} Fix the parser +2 -0 untestedPatchTest",
                    re.compile(r"untracked\s+notes\.txt\s+\+\? -\?"),
                ],
                timeout=SECONDS,
            )
            await changes.nth(1).get_by_role("button", name="Patch").click()
            await expect(page.locator("#pane h2")).to_have_text(f"Patch of {sha[:12]}", timeout=SECONDS)
            await expect(line(page, 8)).to_have_text("8+ return text.split()", timeout=SECONDS)
            above = await page.locator("#pane .x-review > .x-about").inner_text()
            await page.locator("#pane [data-x-review='changes']").click()
            await expect(page.locator("#pane h2")).to_have_text("What changed", timeout=SECONDS)
            await page.context.close()

            viewer, view_errors = await opened(browser, web.link("view"))
            await review(viewer)
            patch = viewer.locator("#pane .x-change").nth(1).get_by_role("button", name="Patch")
            await expect(patch).to_have_attribute("aria-disabled", "true", timeout=SECONDS)
            why = await patch.get_attribute("title")
            await viewer.context.close()

    assert above.splitlines() == [f"{sha[:12]} patch, 8 lines", "Read in @bob's worktree."]
    assert why == "This is a view link: it shows the session and acts on nothing."
    assert errors == view_errors == []


async def test_a_commit_is_tested_from_the_page_after_one_question(browser: Browser, root: Path, monkeypatch):
    """Test asks once, saying whose code it runs as you, unconfined; Keep it runs nothing, and the test runs once the
    person says so, which Read again then shows."""
    repo = repository(root / "repo", monkeypatch)
    async with started(lambda cwd: commit(cwd, "parser.py", PARSER), root, repo) as session:
        sha = await worked(session)
        async with serving("s", root / "home") as web:
            page, errors = await opened(browser, web.link("control"))
            await review(page)
            test = page.locator("#pane [data-x-test]")
            await test.click()
            asked = page.locator(".pop.x-ask")
            await expect(asked).to_contain_text("Run it?", timeout=SECONDS)
            question = await asked.locator(".ph").text_content()
            await asked.get_by_role("button", name="Keep it").click()
            kept = await of_type(session, "effect.requested")
            await test.click()
            await page.locator(".pop.x-ask").get_by_role("button", name="Test").click()
            await expect(page.locator("#pane .x-review + .x-said")).to_have_text(
                f"Testing {sha[:12]}: Read again to see what it comes to.", timeout=SECONDS
            )
            tested = await until(lambda: of_type(session, "repo.tested"), session)
            await page.locator("#pane [data-x-again]").click()
            await expect(page.locator("#pane .x-change").nth(1)).to_contain_text("tests passed", timeout=SECONDS)
            await page.context.close()

    assert question == "Test: runs @bob's commit as you, unconfined. Run it?"
    assert not [event for event in kept if event.data["kind"] == "test"]
    assert [event.data["sha"] for event in tested] == [sha]
    assert errors == []


HOSTILE = '<img src=x onerror="document.title=1"><script>document.title=2</script></div><b>bold</b>'
"""A line of a file an agent wrote, which would run and draw were it taken for markup."""


async def test_a_hostile_patch_stays_text_under_the_page_s_policy(browser: Browser, root: Path, monkeypatch):
    """Every word of a patch goes through the page's escaping, so markup in it is shown as written, draws nothing and
    runs nothing, and the page's policy has nothing to refuse."""
    repo = repository(root / "repo", monkeypatch)
    async with started(lambda cwd: commit(cwd, "page.html", f"{HOSTILE}\n"), root, repo) as session:
        sha = await worked(session)
        async with serving("s", root / "home") as web:
            page, errors = await opened(browser, web.link("control"))
            title = await page.title()
            await review(page)
            await page.locator("#pane .x-change").nth(1).get_by_role("button", name="Patch").click()
            await expect(line(page, 7)).to_have_text(f"7+{HOSTILE}", timeout=SECONDS)
            drawn = await page.locator("#pane .x-patch img, #pane .x-patch script, #pane .x-patch b").count()
            after = await page.title()
            await page.context.close()

    assert (drawn, after) == (0, title)
    assert sha
    assert errors == []


async def test_a_comment_from_the_page_cites_the_lines_it_is_on(browser: Browser, root: Path, monkeypatch):
    """A click on a line's number chooses it, and Shift and a click every line from it to another. Comment sends what
    is written as the person's message to the commit's maker, its `based_on` citing those lines by the record's ref."""
    repo = repository(root / "repo", monkeypatch)
    async with started(lambda cwd: commit(cwd, "parser.py", PARSER), root, repo) as session:
        sha = await worked(session)
        async with serving("s", root / "home") as web:
            page, errors = await opened(browser, web.link("control"))
            await review(page)
            await page.locator("#pane .x-change").nth(1).get_by_role("button", name="Patch").click()
            await expect(line(page, 8)).to_be_visible(timeout=SECONDS)
            await line(page, 7).locator("[data-x-line]").click()
            await line(page, 8).locator("[data-x-line]").click(modifiers=["Shift"])
            about = page.locator("#pane .x-comment .x-about")
            await expect(about).to_have_text(f"Comment to @bob on lines 7 to 8 of {sha[:12]}'s patch")
            chosen = await page.locator("#pane .x-pl.x-chosen").count()
            await page.locator("#pane .x-comment textarea").fill("why split on whitespace?")
            await page.locator("#pane [data-x-comment]").click()
            [record] = await of_type(session, "repo.diffed")
            cited = f"{record.stream}@{record.version}#L7-8"
            await expect(page.locator("#pane .x-comment .x-said")).to_have_text(
                f"Sent to @bob, citing {cited}.", timeout=SECONDS
            )
            sent = [event for event in await of_type(session, "message.sent") if event.based_on]
            await page.context.close()

    assert chosen == 2
    assert [(event.actor, event.stream, event.gist, event.based_on) for event in sent] == [
        ("human:you", "inbox/bob", "why split on whitespace?", (cited,))
    ]
    assert errors == []
