"""The same scenario through SwarmChat's own server, here in the test alone, and through ours: every `view_*` reply the
page uses has the same keys, each of the same type. Our own additions are named `x` or begin `x_`."""

import asyncio
import http.client
import json
import threading
from pathlib import Path
from typing import Any

import pytest

from platoon_harness import Session

from .support import Browser, caught_up, scenario, served, team

pytestmark = pytest.mark.timeout(60)

MAPS = frozenset({"sent", "last_by", "positions", "fields"})
"""Objects keyed by people or chats, whose keys are data and not shape."""
OPTIONAL = frozenset(
    {
        "reply_to",
        "reply_to_from",
        "mentions",
        "attachments",
        "edited_at",
        "deleted",
        "reactions",
        "parent",
        "read_by",
        "unread_by",
    }
)
"""What a message holds only when it has one: either side may lack it, and where both hold it, it is held alike."""


@pytest.fixture(autouse=True)
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("PLATOON_HARNESS_HOME", str(tmp_path))
    return tmp_path


def _type(value: Any) -> str:
    return "number" if isinstance(value, int | float) and not isinstance(value, bool) else type(value).__name__


def shape(value: Any, key: str = "") -> Any:
    """What a reply is made of: an object's keys and the shape of each, a list's items merged, by `kind` where they have
    one, and for anything else the set of its types, of which null says nothing."""
    if isinstance(value, dict) and key in MAPS:
        return ("map", merged([shape(item) for item in value.values()]))
    if isinstance(value, dict):
        return {name: shape(item, name) for name, item in value.items() if name != "x" and not name.startswith("x_")}
    if isinstance(value, list):
        kinds: dict[str, list[Any]] = {}
        for item in value:
            kinds.setdefault(item.get("kind", "") if isinstance(item, dict) else "", []).append(shape(item))
        return ("list", {kind: merged(items) for kind, items in kinds.items()})
    return frozenset() if value is None else frozenset({_type(value)})


def merged(shapes: list[Any]) -> Any:
    found: Any = frozenset()
    for one in shapes:
        found = _merge(found, one)
    return found


def _merge(a: Any, b: Any) -> Any:
    if a == frozenset():
        return b
    if b == frozenset():
        return a
    if isinstance(a, dict) and isinstance(b, dict):
        return {key: _merge(a.get(key, frozenset()), b.get(key, frozenset())) for key in a.keys() | b.keys()}
    if isinstance(a, tuple) and isinstance(b, tuple) and a[0] == b[0]:
        if a[0] == "map":
            return ("map", _merge(a[1], b[1]))
        return (
            "list",
            {
                kind: _merge(a[1].get(kind, frozenset()), b[1].get(kind, frozenset()))
                for kind in a[1].keys() | b[1].keys()
            },
        )
    if isinstance(a, frozenset) and isinstance(b, frozenset):
        return a | b
    raise AssertionError(f"{a} and {b} are different shapes")


def differences(ours: Any, theirs: Any, where: str = "") -> list[str]:
    """Where two shapes part, comparing only what both say something of."""
    if ours == frozenset() or theirs == frozenset():
        return []
    if isinstance(ours, dict) and isinstance(theirs, dict):
        found = [f"{where}.{key}: only ours" for key in ours.keys() - theirs.keys() - OPTIONAL]
        found += [f"{where}.{key}: only SwarmChat's" for key in theirs.keys() - ours.keys() - OPTIONAL]
        for key in ours.keys() & theirs.keys():
            found += differences(ours[key], theirs[key], f"{where}.{key}")
        return found
    if isinstance(ours, tuple) and isinstance(theirs, tuple) and ours[0] == theirs[0]:
        if ours[0] == "map":
            return differences(ours[1], theirs[1], f"{where}{{}}")
        return [
            found
            for kind in ours[1].keys() & theirs[1].keys()
            for found in differences(ours[1][kind], theirs[1][kind], f"{where}[{kind}]")
        ]
    return [] if ours == theirs else [f"{where}: ours is {ours}, SwarmChat's is {theirs}"]


def swarmchat(folder: Path) -> dict[str, Any]:
    """The scenario on SwarmChat's own server, and each reply the page uses."""
    from swarmchat import config
    from swarmchat.client import Client
    from swarmchat.server import make_server

    data = folder / "data"
    httpd, store = make_server(config.load(data=str(data), port=0, min_free=0))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        admin = Client(httpd.url, (data / "admin.token").read_text().strip())
        alice = Client(httpd.url, admin.user_add(id="alice", name="alice")["token"])
        bob = Client(httpd.url, admin.user_add(id="bob", name="bob")["token"])
        alice.channel_create(name="general", members="bob", public=True)
        note = folder / "plan.txt"
        note.write_text("Step one, then step two.\n")
        plan = alice.send(chat="#general", text="plan", attach=[str(note)])["message"]
        bob.send(chat="#general", text="a reply", reply_to=plan["id"])
        hello = alice.send(chat="bob", text="@bob I started a worker.")["message"]
        bob.read(chat="alice")
        token = (data / "view.token").read_text().strip()

        def view(name: str, params: dict[str, Any] | None = None) -> Any:
            connection = http.client.HTTPConnection("127.0.0.1", httpd.server_address[1], timeout=10)
            body = json.dumps(params or {})
            connection.request("POST", f"/v1/{name}", body, {"Authorization": f"Bearer {token}"})
            reply = connection.getresponse()
            assert reply.status == 200, (name, reply.read())
            answer = json.loads(reply.read())
            connection.close()
            return answer

        file = plan["attachments"][0]["id"]
        return {
            "view_info": view("view_info"),
            "view_snapshot": view("view_snapshot"),
            "view_messages": view("view_messages", {"chat": plan["chat"]}),
            "view_thread": view("view_thread", {"id": plan["id"]}),
            "view_receipts": view("view_receipts", {"id": hello["id"]}),
            "view_search": view("view_search", {"text": "plan"}),
            "view_as": view("view_as", {"user": "alice", "unread": True}),
            "view_knew": view("view_knew", {"id": plan["id"]}),
            "view_text": view("view_text", {"id": file}),
            "view_feed": view("view_feed", {"after": 0}),
        }
    finally:
        httpd.shutdown()
        httpd.server_close()
        store.close()


async def ours(root: Path) -> dict[str, Any]:
    """The scenario on our backend, as near as a session says it, and each reply the page uses."""
    async with Session.start(team(), name="s", root=root, cwd=root) as session, served(session, root) as web:
        await scenario(session)
        browser = await Browser(web).opened("view")
        snapshot = await browser.view("view_snapshot")
        general = next(chat for chat in snapshot["chats"] if chat["name"] == "general")
        plan = next(
            line
            for line in (await browser.view("view_messages", {"chat": general["id"]}))["messages"]
            if line.get("text") == "plan"
        )
        await session.send("#general", "a reply", reply_to=plan["x_ref"])
        await caught_up(web, session)
        direct = next(chat for chat in snapshot["chats"] if sorted(chat["members"]) == ["lead", "you"])
        hello = (await browser.view("view_messages", {"chat": direct["id"]}))["messages"][1]
        return {
            "view_info": await browser.view("view_info"),
            "view_snapshot": await browser.view("view_snapshot"),
            "view_messages": await browser.view("view_messages", {"chat": general["id"]}),
            "view_thread": await browser.view("view_thread", {"id": plan["id"]}),
            "view_receipts": await browser.view("view_receipts", {"id": hello["id"]}),
            "view_search": await browser.view("view_search", {"text": "plan"}),
            "view_as": await browser.view("view_as", {"user": "lead", "unread": True}),
            "view_knew": await browser.view("view_knew", {"id": plan["id"]}),
            "view_text": await browser.view("view_text", {"id": plan["attachments"][0]["id"]}),
            "view_feed": await browser.view("view_feed", {"after": 0}),
        }


async def test_every_view_reply_has_swarmchat_s_shape(root):
    theirs = await asyncio.to_thread(swarmchat, root / "upstream")
    mine = await ours(root)

    found = {name: differences(shape(mine[name]), shape(theirs[name]), name) for name in theirs}

    assert {name: parted for name, parted in found.items() if parted} == {}
    assert all(mine[name] and theirs[name] for name in theirs)


def test_the_comparison_finds_a_key_one_side_lacks_and_a_type_that_differs():
    assert differences(shape({"a": 1, "b": "x"}), shape({"a": 2})) == [".b: only ours"]
    assert differences(shape({"a": [{"kind": "m", "n": 1}]}), shape({"a": [{"kind": "m", "n": "1"}]})) == [
        ".a[m].n: ours is frozenset({'number'}), SwarmChat's is frozenset({'str'})"
    ]
    assert differences(shape({"sent": {"lead": 1}}), shape({"sent": {"alice": 2}})) == []
