"""The team editor on the sessions page, in a real browser, served by `platoon-harness web` with no session over a
project folder whose PATH holds no harness: it reads the project's team as fields, says each problem at its field, shows
`team show`'s sentences and the diff a save makes, saves the file keeping its comments, and Start saves first and starts
what was saved. The keyboard reaches every field and act, each field's problems are its accessible description, and at a
phone's width the editor scrolls no wider than the screen."""

import asyncio
import re
import shutil
import sys
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from playwright.async_api import Browser, Page, expect

from platoon_harness import Team
from platoon_harness.config import Manifest

from ..integration.cli import Cli, finished, solo
from ..integration.test_web import sessions_link
from .support import PHONE, REACHED, SECONDS, watched

pytestmark = [pytest.mark.e2e, pytest.mark.timeout(180)]

TEAM = f"# Bob, alone, on a scripted harness.\n{solo('saying')}"


@pytest.fixture
async def cli(tmp_path: Path) -> AsyncIterator[Cli]:
    made = Cli(tmp_path)
    yield made
    await asyncio.to_thread(made.end)


async def web(cli: Cli) -> tuple[asyncio.subprocess.Process, str]:
    """`web` with no session, on a PATH that holds git and this environment's programs and no harness, so `doctor`
    finds none of them, and its one link."""
    bin = cli.folder / "bin"
    bin.mkdir()
    (bin / "git").symlink_to(shutil.which("git") or "/usr/bin/git")
    process = await cli.start("web", PATH=f"{Path(sys.executable).parent}:{bin}")
    return process, await sessions_link(process)


async def edited(browser: Browser, link: str, viewport: dict[str, int], **more: bool) -> tuple[Page, list[str]]:
    """The sessions page with its team editor open, its fields drawn."""
    page = await (await browser.new_context(viewport=viewport, **more)).new_page()
    errors = watched(page)
    await page.goto(link)
    await expect(page.locator("#look")).to_be_visible(timeout=SECONDS)
    await page.get_by_role("button", name="Edit").click()
    await expect(page.locator('fieldset[data-where="roles.bob"]')).to_be_visible(timeout=SECONDS)
    return page, errors


async def test_the_team_editor_says_problems_at_their_fields_saves_keeping_comments_and_start_saves_first(
    browser: Browser, cli: Cli
):
    """A change is checked as it is made: its diff, a problem at its field, and `team show`'s sentences. Save writes
    the file with its comment kept, and Start, with a change not yet saved, saves it first, then starts from what it
    saved, asking trust as a start does, and the session's manifest keeps that team."""
    cli.write("platoon-harness.toml", TEAM)
    process, link = await web(cli)
    page, errors = await edited(browser, link, {"width": 1280, "height": 900})
    bob = page.locator('fieldset[data-where="roles.bob"]')
    said = page.locator("#team-said")

    await expect(bob.get_by_label("harness")).to_have_value("tests.integration.scripts:saying")
    await bob.get_by_label("model").fill("m1")
    await bob.get_by_label("count").fill("two")
    await bob.get_by_label("count").press("Tab")
    count = bob.get_by_label("count")
    await expect(count).to_have_attribute("aria-invalid", "true", timeout=SECONDS)
    await expect(count).to_have_accessible_description(re.compile(r"error: roles\.bob\.count: is a whole number$"))
    await expect(count).to_have_value("two")
    await expect(page.locator("#diff")).to_contain_text('+model = "m1"')
    save = page.get_by_role("button", name="Save")
    await expect(save).to_have_accessible_description("Fix each change marked first: the editor could not make it.")
    await count.fill("")
    await count.press("Tab")
    await expect(count).not_to_have_attribute("aria-invalid", "true", timeout=SECONDS)

    adding = page.get_by_role("group", name="Add a role")
    await adding.get_by_label("name").fill("bob")
    await adding.get_by_role("button", name="Add a role").click()
    await expect(bob).to_contain_text("error: roles.bob: is there already", timeout=SECONDS)
    await adding.get_by_label("name").fill("critic")
    await adding.get_by_label("harness").select_option("claude")
    await adding.get_by_role("button", name="Add a role").click()
    critic = page.locator('fieldset[data-where="roles.critic"]')
    await expect(critic).to_be_visible(timeout=SECONDS)
    await critic.get_by_label("count").fill("0")
    await critic.get_by_label("count").press("Tab")
    await expect(page.locator("#diff")).to_contain_text("+count = 0", timeout=SECONDS)
    await expect(page.locator("#preview")).to_contain_text("Critics (claude) may message no one.")
    await expect(save).not_to_have_attribute("aria-disabled", "true")
    await save.click()
    await expect(said).to_have_text(f"Saved platoon-harness.toml in {cli.folder}.", timeout=SECONDS)
    await expect(page.locator("#diff")).to_have_text("Nothing: the draft is the file as it stands.", timeout=SECONDS)
    await expect(save).to_have_accessible_description("Nothing to save: the draft is the file as it stands.")
    await expect(bob).not_to_contain_text("is there already")
    saved = (cli.folder / "platoon-harness.toml").read_text()

    await bob.get_by_label("approvals").select_option("allow")
    await expect(page.locator("#diff")).to_contain_text('+approvals = "allow"', timeout=SECONDS)
    start = page.get_by_role("button", name="Start")
    await page.locator("#start").get_by_label("Team file").fill("other.toml")
    await expect(start).to_have_accessible_description(
        re.compile(r"^Team file names another file, and the team editor")
    )
    await page.locator("#start").get_by_label("Team file").fill("")
    await expect(start).not_to_have_attribute("aria-disabled", "true")
    await page.locator("#start").get_by_label("Name").fill("s")
    await start.click()
    dialog = page.get_by_role("dialog")
    await expect(dialog).to_contain_text('roles.bob.harness = "tests.integration.scripts:saying"', timeout=SECONDS)
    await dialog.get_by_role("button", name="Trust and start").click()
    await expect(page.locator("#list .row").first).to_be_visible(timeout=SECONDS)
    await page.goto(link.partition("#")[0])
    await expect(page.locator('tr[data-session="s"]')).to_contain_text("live", timeout=SECONDS)
    manifest = Manifest.model_validate_json((cli.folder / "home" / "sessions" / "s" / "manifest.json").read_bytes())

    process.terminate()
    done = await finished(process)
    stopped = await cli.run("session", "stop", "s")

    assert saved == f'{TEAM}model = "m1"\n\n[roles.critic]\nharness = "claude"\ncount = 0\n'
    assert (cli.folder / "platoon-harness.toml").read_text() == saved.replace('"m1"\n', '"m1"\napprovals = "allow"\n')
    assert Team.loads(manifest.team).roles["bob"].approvals == "allow"
    assert done.code == 0, done.stderr
    assert stopped.code == 0, stopped.stderr
    assert errors == []


async def test_the_keyboard_reaches_every_field_and_act_of_the_team_editor_and_at_390_px_it_scrolls_no_wider(
    browser: Browser, cli: Cli
):
    """Tab goes through every field in order, from Edit to Save, one that cannot be changed here among them, which says
    why first in its description; and on a phone's screen with touch every act and field lies within the screen's sides
    with nothing over it, and the page scrolls no wider."""
    cli.write("platoon-harness.toml", TEAM.replace("[roles.bob]", '[roles.lead]\nharness = "claude"\n\n[roles.bob]'))
    process, link = await web(cli)
    page, errors = await edited(browser, link, PHONE, has_touch=True)
    sandbox = page.locator('fieldset[data-where="roles.lead"]').get_by_label("sandbox")

    await expect(sandbox).to_have_accessible_description(re.compile(r"^`?claude`? declares no sandbox, so none can be"))
    await expect(sandbox).to_have_attribute("aria-disabled", "true")
    fields = await page.locator("#team-form [data-where]:is(input, select, textarea)").evaluate_all(
        "els => els.map(el => el.dataset.where)"
    )
    await page.get_by_role("button", name="Close").focus()
    walked: list[str] = []
    for _ in range(len(fields) + 40):
        await page.keyboard.press("Tab")
        now = await page.evaluate("[document.activeElement.dataset.where, document.activeElement.id]")
        if now[1] == "save":
            break
        if now[0]:
            walked.append(now[0])
    reached = await page.evaluate(REACHED)
    await page.context.close()

    process.terminate()
    done = await finished(process)

    assert walked == fields and "roles.lead.sandbox" in walked
    assert reached["missed"] == [] and reached["wider"] == 0 and reached["acts"] > len(fields)
    assert done.code == 0, done.stderr
    assert errors == []


async def test_what_the_team_editor_is_told_stays_text_under_its_policy(browser: Browser, cli: Cli):
    """A value that holds markup is drawn as that text in its field, the preview and the diff, and nothing in it runs
    or loads."""
    hostile = "<img src=x onerror=document.title=1>"
    cli.write("platoon-harness.toml", TEAM)
    process, link = await web(cli)
    page, errors = await edited(browser, link, {"width": 1280, "height": 900})

    instructions = page.locator('fieldset[data-where="roles.bob"]').get_by_label("instructions")
    await instructions.fill(hostile)
    await instructions.press("Tab")
    await expect(page.locator("#diff")).to_contain_text(hostile, timeout=SECONDS)
    found = await page.evaluate("[document.title, document.querySelectorAll('img').length]")

    process.terminate()
    done = await finished(process)

    assert found == ["Sessions · platoon-harness", 0]
    assert done.code == 0, done.stderr
    assert errors == []
