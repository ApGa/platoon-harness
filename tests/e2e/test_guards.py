"""What keeps SwarmChat's page safe, in a real browser: a view link that cannot act, a link that opens once, a sender
no page can choose, a command refused from another origin or a rebound name, and hostile text that stays text under
the page's policy."""

import asyncio
import contextlib
import json
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from playwright.async_api import Browser, Page, expect

from platoon_harness import Session, Team
from platoon_harness.testing import Ask, Call, Hang, Say

from ..unit.runtime.support import in_state, of_type, scripted, until
from .support import REBOUND, SECONDS, chat, opened, said, serving

pytestmark = [pytest.mark.e2e, pytest.mark.timeout(120)]

COMPOSER = "#main .x-composer textarea"
TOKEN = "localStorage.getItem('swarmchat.view.token')"
HOSTILE = (
    '<img src=x onerror="window.__pwned=1"> <script>window.__pwned=1</script> "><svg onload="window.__pwned=1"> '
    '<a href="javascript:window.__pwned=1">a link</a> [a link](javascript:window.__pwned=1) '
    '<iframe src="http://evil.example/frame"></iframe> <img src="http://evil.example/pixel.png"> '
    '<link rel="stylesheet" href="http://evil.example/style.css"> '
    "<style>body{background:url(http://evil.example/bg)}</style> "
    'http://evil.example/"onmouseover="window.__pwned=1 `</code><img src=x onerror=window.__pwned=1>` '
    "```html\n</pre><img src=x onerror=window.__pwned=1>\n``` {{constructor.constructor('window.__pwned=1')()}} "
    "\u202eevil \x1b]0;owned\x07 $` $' $&"
)


@pytest.fixture
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("PLATOON_HARNESS_HOME", str(tmp_path))
    return tmp_path


def asking() -> Team:
    """`bob`, which asks for an approval when told to go, and says so to the person."""
    turn = [Call("message_send", {"to": "@you", "gist": "I will ask you first."}), Ask("Ship the fix?"), Hang()]
    return Team.model_validate(
        {"roles": {"bob": {"harness": scripted(turn)}}, "topology": {"edges": {"bob": ["human"]}}}
    )


async def posted(page: Page, path: str, body: str) -> int:
    """What the page's own server answers a POST with the page's own token, as a script on the page could send it."""
    script = """async ([path, body]) => (await fetch(path, {method: 'POST', body,
        headers: {'Authorization': 'Bearer ' + localStorage.getItem('swarmchat.view.token'),
                  'Content-Type': 'application/json'}})).status"""
    return await page.evaluate(script, [path, body])


async def test_a_view_link_cannot_command_upload_or_mint_and_its_controls_say_why(chromium: Browser, root: Path):
    why = "This is a view link: it shows the session and acts on nothing."
    async with Session.start(asking(), name="s", root=root, cwd=root) as session, serving("s", root) as web:
        await in_state(session, "bob", "idle")
        await session.send("@bob", "go")
        await until(session.approvals, session)
        head = await session.head()
        page, errors = await opened(chromium, web.link("view"), "status of 403")
        await chat(page, "bob & you")

        command = json.dumps({"op": "message.send", "args": {"to": "@bob", "gist": "x"}, "key": "k"})
        statuses = [
            await posted(page, "/x/command", command),
            await posted(page, "/x/body", "bytes"),
            await posted(page, "/x/link", json.dumps({"class": "control"})),
        ]
        for control in (
            page.locator(COMPOSER),
            page.locator("#main [data-x-attach]"),
            page.locator('[data-x-decide="allow"]'),
            page.locator("[data-x-reply]").first,
        ):
            await expect(control).to_be_disabled(timeout=SECONDS)
            await expect(control).to_have_accessible_description(why)
        needs = page.locator("[data-x-needs]")
        await expect(needs).to_be_disabled()
        await expect(needs).to_have_accessible_description(why)
        await page.goto(web.link("view").partition("#")[0] + "#person=you")
        for act in await page.locator("[data-x-act]").all():
            await expect(act).to_be_disabled()
            await expect(act).to_have_accessible_description(why)
        assert await session.head() == head
        await page.context.close()

    assert statuses == [403, 403, 403]
    assert errors == []


async def test_a_spent_link_is_refused(chromium: Browser, root: Path):
    async with Session.start(asking(), name="s", root=root, cwd=root) as session, serving("s", root) as web:
        await in_state(session, "bob", "idle")
        link = web.link("control")
        page, errors = await opened(chromium, link)
        again = await (await chromium.new_context()).new_page()

        await again.goto(link)

        await expect(again.locator(".err")).to_have_text(
            "this link was used already or has expired: ask for a new one", timeout=SECONDS
        )
        await expect(again.locator("#list")).to_have_count(0)
        await page.context.close()
        await again.context.close()

    assert errors == []


async def test_a_sender_cannot_be_chosen_from_the_page_since_identity_comes_from_the_credential(
    chromium: Browser, root: Path
):
    async with Session.start(asking(), name="s", root=root, cwd=root) as session, serving("s", root) as web:
        await in_state(session, "bob", "idle")
        page, errors = await opened(chromium, web.link("control"))
        await chat(page, "bob & you")
        forged = []
        for n, field in enumerate(("sender", "actor", "from")):
            args = {"to": "@bob", "gist": "as someone else", field: "@bob"}
            script = """async command => (await fetch('/x/command', {method: 'POST', body: JSON.stringify(command),
                headers: {'Authorization': 'Bearer ' + localStorage.getItem('swarmchat.view.token'),
                          'Content-Type': 'application/json'}})).json()"""
            forged.append(await page.evaluate(script, {"op": "message.send", "args": args, "key": f"{n:032x}"}))
        await page.locator(COMPOSER).fill("as myself")
        await page.keyboard.press("Enter")
        await expect(said(page, "as myself")).to_have_count(1, timeout=SECONDS)
        sent = [event for event in await of_type(session, "message.sent") if event.actor != "agent:bob"]
        refused = [event for event in await of_type(session, "op.refused") if event.outcome.op == "message.send"]
        await page.context.close()

    assert [outcome["refusal"]["code"] for outcome in forged] == ["invalid"] * 3
    assert [event.actor for event in refused] == ["human:you"] * 3
    assert [(event.actor, event.gist) for event in sent] == [("human:you", "as myself")]
    assert errors == []


async def test_a_decision_said_through_text_a_replacement_would_expand_is_drawn_as_that_text(
    chromium: Browser, root: Path
):
    """`via` is free text, and replace reads a dollar and a quote or a backtick in what it puts in as other text."""
    via = "ci $` and $' and $& end"
    async with Session.start(asking(), name="s", root=root, cwd=root) as session, serving("s", root) as web:
        await in_state(session, "bob", "idle")
        await session.send("@bob", "go")
        approval = (await until(session.approvals, session))[0]
        await session.resolve(approval["id"], "allow", expected_version=approval["version"], via=via)
        page, errors = await opened(chromium, web.link("control"))
        await chat(page, "bob & you")

        await expect(page.locator(".x-card.x-done")).to_have_text(f"Allowed by you via {via}", timeout=SECONDS)
        await expect(said(page, "Ship the fix?")).to_have_count(1)
        await page.context.close()

    assert errors == []


@contextlib.asynccontextmanager
async def elsewhere(page: bytes) -> AsyncIterator[str]:
    """Another site on this machine, serving one page at its root: an origin of its own, on another port."""

    async def answer(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        with contextlib.suppress(ConnectionError, asyncio.IncompleteReadError):
            await reader.readuntil(b"\r\n\r\n")
            writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nConnection: close\r\n\r\n" + page)
            await writer.drain()
        writer.close()

    server = await asyncio.start_server(answer, "127.0.0.1", 0)
    try:
        yield f"http://127.0.0.1:{server.sockets[0].getsockname()[1]}/"
    finally:
        server.close()
        await server.wait_closed()


async def test_a_page_of_another_origin_or_a_rebound_name_is_refused_on_the_command_route(
    chromium: Browser, root: Path
):
    async with Session.start(asking(), name="s", root=root, cwd=root) as session, serving("s", root) as web:
        await in_state(session, "bob", "idle")
        page, errors = await opened(chromium, web.link("control"))
        stolen = await page.evaluate(TOKEN)
        head = await session.head()
        target = json.dumps(f"http://127.0.0.1:{web.port}/x/command")
        command = json.dumps({"op": "message.send", "args": {"to": "@bob", "gist": "from elsewhere"}, "key": "k"})
        attack = f"""<!doctype html><script>
            window.simple = fetch({target}, {{method: 'POST', mode: 'no-cors', body: {json.dumps(command)},
                headers: {{'Content-Type': 'text/plain'}}}}).then(() => 'sent', () => 'blocked');
            window.bearing = fetch({target}, {{method: 'POST', body: {json.dumps(command)},
                headers: {{'Authorization': 'Bearer {stolen}', 'Content-Type': 'application/json'}}}})
                .then(() => 'answered', () => 'blocked');
        </script>"""
        other = await (await chromium.new_context()).new_page()
        answers: list[tuple[str, int]] = []
        other.on("response", lambda response: answers.append((response.request.method, response.status)))
        async with elsewhere(attack.encode()) as site:
            await other.goto(site)
            sent = await other.evaluate("Promise.all([window.simple, window.bearing])")

        rebound = f"http://{REBOUND}:{web.port}"
        gate = await other.goto(f"{rebound}/view")
        form = f"""<!doctype html><form method="post" action="/x/command" enctype="text/plain">
            <input name='{command[:-1]}, "pad": "' value='"}}'></form><script>document.forms[0].submit()</script>"""
        await other.route(f"{rebound}/attack", lambda route: route.fulfill(body=form, content_type="text/html"))
        async with other.expect_response(lambda response: response.url.endswith("/x/command")) as posted_from:
            await other.goto(f"{rebound}/attack")
        rebound_post = await posted_from.value
        await other.context.close()
        assert await session.head() == head
        await page.context.close()

    assert sent == ["sent", "blocked"] and ("POST", 403) in answers
    assert gate is not None and gate.status == 421 and rebound_post.status == 421
    assert errors == []


def hostile() -> Team:
    """`constructor`, whose words, approval, channel and long body are hostile, in a topic named `__proto__`."""
    long = (HOSTILE + "\n") * 60
    turn = [
        Say(HOSTILE),
        Call("message_send", {"to": "#__proto__", "gist": HOSTILE[:280], "body": long}),
        Ask(HOSTILE[:280]),
        Hang(),
    ]
    roles = {"constructor": {"harness": scripted(turn)}}
    topology = {
        "edges": {"constructor": ["human"]},
        "channels": {"__proto__": {"kind": "topic", "writers": "all", "readers": "all"}},
    }
    return Team.model_validate({"roles": roles, "topology": topology})


async def test_hostile_text_names_files_approvals_and_bodies_stay_text_under_the_page_s_policy(
    chromium: Browser, root: Path
):
    async with Session.start(hostile(), name="s", root=root, cwd=root) as session, serving("s", root) as web:
        await in_state(session, "constructor", "idle")
        await session.send("@constructor", HOSTILE[:280])
        await until(session.approvals, session)
        page, errors = await opened(chromium, web.link("control"))
        origin = f"http://127.0.0.1:{web.port}"
        requested: list[str] = []
        page.on("request", lambda request: requested.append(request.url))

        await chat(page, "constructor & you")
        await expect(page.locator(".x-card")).to_have_count(1, timeout=SECONDS)
        await page.locator(COMPOSER).fill(HOSTILE)
        await page.keyboard.press("Enter")
        await expect(page.locator(COMPOSER)).to_have_value("", timeout=SECONDS)
        name = '<img src=x onerror="window.__pwned=1">.txt'
        await page.locator("#main [data-x-file]").set_input_files(
            {"name": name, "mimeType": "text/plain", "buffer": b"x"}
        )
        await page.locator("#main .x-composer button.primary").click()
        await expect(said(page, f"file {name}")).to_have_count(1, timeout=SECONDS)
        await expect(said(page, "<script>window.__pwned=1</script>").first).to_be_visible(timeout=SECONDS)
        await chat(page, "__proto__")
        await page.locator("#main .snip").first.click()
        await expect(page.locator(".tv .tvb")).to_contain_text("onerror", timeout=SECONDS)
        await page.locator(".tv [data-close]").click()
        await page.goto(f"{origin}/view#person=constructor")
        await expect(page.locator(".person h1")).to_have_text("constructor", timeout=SECONDS)
        await page.locator("[data-tab=people]").click()

        pwned = await page.evaluate("window.__pwned")
        handlers = await page.evaluate(
            "[...document.querySelectorAll('*')].flatMap(e => [...e.attributes].map(a => a.name))"
            ".filter(name => name.startsWith('on'))"
        )
        injected = await page.evaluate(
            "document.querySelectorAll('img, iframe, object, embed, link:not([rel=icon]), "
            'a[href^="javascript"]\').length'
        )
        await page.context.close()

    assert pwned is None and handlers == [] and injected == 0
    assert [url for url in requested if not url.startswith((origin, "data:", "blob:"))] == []
    assert errors == []
