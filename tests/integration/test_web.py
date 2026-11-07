"""`platoon-harness web`, run as a process of its own against a session served by another: it says its links, follows
the session as its runtime goes and comes back, serves TLS when told to, and leaves nothing behind."""

import asyncio
import http.client
import json
import signal
import socket
import ssl
import subprocess
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import pytest

from .cli import SECONDS, Cli, crew, finished, line_where, said, solo

pytestmark = pytest.mark.timeout(120)


@pytest.fixture
async def cli(tmp_path: Path) -> AsyncIterator[Cli]:
    made = Cli(tmp_path)
    yield made
    await asyncio.to_thread(made.end)


async def links(process: asyncio.subprocess.Process) -> dict[str, str]:
    """The links `web` says on stderr, by kind."""
    assert process.stderr is not None
    found: dict[str, str] = {}
    async with asyncio.timeout(SECONDS):
        while len(found) < 2 and (line := (await process.stderr.readline()).decode()):
            for kind in ("view", "control"):
                if f"{kind} link" in line:
                    found[kind] = line.rpartition(" ")[2].strip()
    return found


def call(link: str, method: str, path: str, body: Any = None, token: str = "", context: Any = None) -> Any:
    """One request as the page makes one, to the server `link` names."""
    parts = urlsplit(link)
    origin = f"{parts.scheme}://{parts.netloc}"
    connection = (
        http.client.HTTPSConnection(parts.hostname, parts.port, timeout=SECONDS, context=context)
        if parts.scheme == "https"
        else http.client.HTTPConnection(parts.hostname, parts.port, timeout=SECONDS)
    )
    headers = {"Origin": origin, "Content-Type": "application/json"} if method == "POST" else {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    connection.request(method, path, None if body is None else json.dumps(body), headers)
    reply = connection.getresponse()
    data = reply.read()
    connection.close()
    return reply.status, json.loads(data) if reply.getheader("content-type") == "application/json" else data


def opened(link: str, context: Any = None) -> str:
    status, answer = call(link, "POST", "/x/exchange", {}, link.partition("#link=")[2], context)
    assert status == 200, answer
    return answer["token"]


async def test_web_says_its_links_and_ends_cleanly_on_sigterm_or_ctrl_c_leaving_the_session_running(cli: Cli):
    team = cli.write("solo.toml", solo("listening"))
    serving = await cli.start("serve", "--team", team, "--trust", "--name", "s")
    await said(serving, "serving session s")

    for signum in (signal.SIGTERM, signal.SIGINT):
        web = await cli.start("web", "s")
        found = await links(web)
        status, gate = await asyncio.to_thread(call, found["view"], "GET", "/view")
        token = await asyncio.to_thread(opened, found["control"])
        _, info = await asyncio.to_thread(call, found["control"], "POST", "/v1/view_info", {}, token)

        web.send_signal(signum)
        done = await finished(web)
        port = urlsplit(found["view"]).port

        assert done.code == 0, done.stderr
        assert f"ssh -N -L {port}:127.0.0.1:{port} {socket.gethostname()}" in done.stderr
        assert status == 200 and b"<form>" in gate
        assert info["x"] | {"may": [], "forms": []} == {
            "credential": "control",
            "live": True,
            "person": "you",
            "session": "s",
            "may": [],
            "forms": [],
            "confirmed": info["x"]["confirmed"],
            "body_limit": info["x"]["body_limit"],
            "cannot": None,
        }
        assert {"message.send", "session.close"} <= {form["op"] for form in info["x"]["forms"]}
    status = await cli.run("session", "status", "s")
    await cli.run("session", "stop", "s")
    await finished(serving)

    assert json.loads(status.stdout)["state"] == "open"


async def test_web_follows_its_session_as_its_runtime_goes_and_comes_back(cli: Cli):
    team = cli.write("crew.toml", crew(worker="hanging"))
    run = await cli.start("run", "go", "--team", team, "--trust", "--name", "s", "--json")
    await line_where(run, [], "type", "task.claimed")
    await cli.run("session", "stop", "s")
    await finished(run)
    web = await cli.start("web", "s")
    found = await links(web)
    token = await asyncio.to_thread(opened, found["control"])
    _, before = await asyncio.to_thread(call, found["control"], "POST", "/v1/view_info", {}, token)

    resumed = await cli.start("session", "resume", "s")
    _, fed = await asyncio.to_thread(
        call, found["control"], "POST", "/v1/view_feed", {"after": before["feed"], "timeout": 25}, token
    )
    await finished(resumed)
    web.send_signal(signal.SIGTERM)
    done = await finished(web)

    assert before["x"]["live"] is False and "platoon-harness session resume s" in before["x"]["cannot"]
    assert fed["events"], "nothing the resumed runtime did reached the page"
    assert done.code == 0, done.stderr


async def test_one_web_serves_a_session_and_a_second_is_refused_saying_where_the_first_is(cli: Cli):
    """Two would fold one projection at once, each its own way, and one crashed on a line the other had written."""
    team = cli.write("solo.toml", solo("listening"))
    serving = await cli.start("serve", "--team", team, "--trust", "--name", "s")
    await said(serving, "serving session s")
    web = await cli.start("web", "s")
    found = await links(web)
    token = await asyncio.to_thread(opened, found["control"])

    _, info = await asyncio.to_thread(call, found["control"], "POST", "/v1/view_info", {}, token)
    second = await cli.run("web", "s")
    for n in range(2):
        await cli.run("message", "send", "s", "--to", "@bob", "--gist", f"note {n}")
    fed, after = [], info["feed"]
    async with asyncio.timeout(SECONDS):
        while len(fed) < 2:
            params = {"after": after, "timeout": 25}
            _, page = await asyncio.to_thread(call, found["control"], "POST", "/v1/view_feed", params, token)
            fed += [event for event in page["events"] if event.get("message", {}).get("text", "").startswith("note")]
            after = page["feed"]
    _, notes = await asyncio.to_thread(call, found["control"], "POST", "/v1/view_search", {"text": "note"}, token)
    web.send_signal(signal.SIGTERM)
    done = await finished(web)
    await cli.run("session", "stop", "s")
    await finished(serving)

    authority = urlsplit(found["view"]).netloc
    assert second.code == 64 and f"web serves session s already, at {authority} in process {web.pid}" in second.stderr
    assert info["x"]["live"] is True and done.code == 0, done.stderr
    assert sorted(message["text"] for message in notes["messages"]) == ["note 0", "note 1"]


async def test_web_refuses_an_address_other_than_loopback_without_tls(cli: Cli):
    team = cli.write("solo.toml", solo("listening"))
    serving = await cli.start("serve", "--team", team, "--trust", "--name", "s")
    await said(serving, "serving session s")

    remote = await cli.run("web", "s", "--host", "192.0.2.7")
    wildcards = [await cli.run("web", "s", "--host", host) for host in ("0.0.0.0", "::", "0")]
    halves = await cli.run("web", "s", "--certificate", "cert.pem")
    await cli.run("session", "stop", "s")
    await finished(serving)

    assert [remote.code, *(wildcard.code for wildcard in wildcards), halves.code] == [64] * 5
    assert "needs TLS" in remote.stderr and all("names no one address" in wildcard.stderr for wildcard in wildcards)


def health(address: str, authority: str) -> int:
    """What `web` answers on one address for its health, asked as a browser that resolved the name to it would."""
    with socket.create_connection((address, int(authority.rpartition(":")[2])), timeout=SECONDS) as connection:
        connection.sendall(f"GET /v1/health HTTP/1.1\r\nHost: {authority}\r\n\r\n".encode())
        return int(connection.makefile("rb").readline().split()[1])


async def test_web_serves_every_address_its_name_has_on_the_port_it_says(cli: Cli):
    team = cli.write("solo.toml", solo("listening"))
    serving = await cli.start("serve", "--team", team, "--trust", "--name", "s")
    await said(serving, "serving session s")
    addresses = {info[4][0] for info in socket.getaddrinfo("localhost", 0, type=socket.SOCK_STREAM)}

    web = await cli.start("web", "s", "--host", "localhost")
    authority = urlsplit((await links(web))["view"]).netloc
    statuses = [await asyncio.to_thread(health, address, authority) for address in sorted(addresses)]
    web.send_signal(signal.SIGTERM)
    done = await finished(web)
    await cli.run("session", "stop", "s")
    await finished(serving)

    assert authority.startswith("localhost:") and statuses == [200] * len(addresses)
    assert done.code == 0, done.stderr


async def test_web_on_no_such_session_is_refused(cli: Cli):
    done = await cli.run("web", "nobody")

    assert done.code == 1 and "nobody" in done.stderr


def certified(folder: Path) -> tuple[Path, Path]:
    """A certificate for 127.0.0.1, signed by itself, and its key."""
    certificate, key = folder / "cert.pem", folder / "key.pem"
    subprocess.run(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-keyout",
            key,
            "-out",
            certificate,
            "-days",
            "1",
            "-subj",
            "/CN=127.0.0.1",
            "-addext",
            "subjectAltName=IP:127.0.0.1",
        ],
        check=True,
        capture_output=True,
        timeout=SECONDS,
    )
    return certificate, key


async def test_web_serves_tls_with_the_certificate_it_is_given(cli: Cli, tmp_path: Path):
    certificate, key = await asyncio.to_thread(certified, tmp_path)
    team = cli.write("solo.toml", solo("listening"))
    serving = await cli.start("serve", "--team", team, "--trust", "--name", "s")
    await said(serving, "serving session s")
    web = await cli.start("web", "s", "--certificate", str(certificate), "--key", str(key))
    found = await links(web)
    context = ssl.create_default_context(cafile=certificate)

    status, _ = await asyncio.to_thread(call, found["view"], "GET", "/view", context=context)
    token = await asyncio.to_thread(opened, found["view"], context)
    web.send_signal(signal.SIGTERM)
    done = await finished(web)
    await cli.run("session", "stop", "s")
    await finished(serving)

    assert found["view"].startswith("https://127.0.0.1:") and status == 200 and len(token) == 64
    assert "ssh -N -L" not in done.stderr


SPARE = f"""{solo("listening")}
[roles.helper]
harness = "tests.integration.scripts:planned"
count = 0
"""
"""A team whose `bob` listens, beside a role on a plan login that starts no agent, as a person can spawn it."""


async def test_a_session_on_a_plan_login_is_refused_any_address_but_loopback_with_78(cli: Cli, tmp_path: Path):
    """A control link acts as you, on your login, so a session on a plan login stays on loopback, whether its owner said
    several agents may run on one, one agent came up on one alone, or a role none of whose agents has started would
    start one there, as a control link could spawn it."""
    certificate, key = await asyncio.to_thread(certified, tmp_path)
    remote = ("--host", "192.0.2.7", "--certificate", str(certificate), "--key", str(key))
    said_so = await cli.start(
        "serve", "--team", cli.write("said.toml", solo("listening")), "--name", "said", "--trust", "--plan-login"
    )
    alone = await cli.start("serve", "--team", cli.write("alone.toml", solo("planned")), "--name", "alone", "--trust")
    spare = await cli.start("serve", "--team", cli.write("spare.toml", SPARE), "--name", "spare", "--trust")
    await said(said_so, "serving session said")
    await said(alone, "serving session alone")
    await said(spare, "serving session spare")
    following = await cli.start("events", "alone", "--follow", "--json")
    await line_where(following, [], "type", "agent.started")
    following.send_signal(signal.SIGTERM)
    await finished(following)

    owner_said = await cli.run("web", "said", *remote)
    came_up = await cli.run("web", "alone", *remote)
    would_start = await cli.run("web", "spare", *remote)
    web = await cli.start("web", "alone")
    found = await links(web)
    web.send_signal(signal.SIGTERM)
    done = await finished(web)
    for name, serving in (("said", said_so), ("alone", alone), ("spare", spare)):
        await cli.run("session", "stop", name)
        await finished(serving)
    refused = owner_said.stderr + came_up.stderr + would_start.stderr

    assert owner_said.code == 78 and "runs on a plan login, as its owner said" in owner_said.stderr
    assert came_up.code == 78 and "runs on a plan login, as bob came up on one" in came_up.stderr
    assert would_start.code == 78 and "runs on a plan login, as helper would start on one" in would_start.stderr
    assert "forward its port" in came_up.stderr and "view link" not in refused
    assert found["control"].startswith("http://127.0.0.1:") and done.code == 0, done.stderr
