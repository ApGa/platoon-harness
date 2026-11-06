"""An isolated agent on each real binary against FakeModel, confined by the `bwrap` extension. Its harness runs a probe
in its own shell that tries each way out, commits, configures a git filter the runtime's look then runs, leaves a
process behind in a session of its own, and calls our tools. Free: dummy keys, homes of the test's own, loopback only.
The probe touches only what the test made: canaries in folders of its own, its session's folder and socket, and what
the agent started. The runtime's home is the test's, and your account's home is hidden too, as wherever the runtime
runs, so each harness runs on the paths its driver declares, and sees nothing of yours."""

import asyncio
import contextlib
import importlib.util
import os
import shutil
import signal
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from platoon_harness import Session, Team
from platoon_harness.bwrap import Bubblewrap
from platoon_harness.runtime.paths import agent_folder, socket_path
from platoon_harness.testing import FakeModel, ToolCall

from ..unit.runtime import support
from ..unit.runtime.gitting import git, repository
from ..unit.runtime.support import in_state, of_type, scripted, until

pytestmark = [pytest.mark.slow, pytest.mark.timeout(600)]

MODEL = "fake-model"
SECONDS = 120.0
ESCALATED = {"sandbox_permissions": "require_escalated", "justification": "it commits"}
PROBE = """\
tried() {{ if (echo > "$1") 2>/dev/null; then echo "$2 written"; else echo "$2 refused"; fi; }}
{{
tried "{outside}/escaped" outside
tried "{objects}/escaped" objects
tried "{private}" tmp
tried "{folder}/mine" folder
if [ -e "{session}/journal.sqlite" ]; then echo "journal seen"; else echo "journal unseen"; fi
if cat "{session}/owner.token" > /dev/null 2>&1; then echo "token read"; else echo "token unread"; fi
if [ -e "{other}" ]; then echo "other seen"; else echo "other unseen"; fi
if [ -e "{socket}" ]; then echo "socket seen"; else echo "socket unseen"; fi
echo "processes $(ls /proc | grep -cE '^[0-9]+$') highest $(ls /proc | grep -E '^[0-9]+$' | sort -n | tail -n 1)"
echo "home $HOME"
}} > escape.txt
setsid sh -c 'sleep 600' {marker} < /dev/null > /dev/null 2>&1 &
git config filter.fence.clean "sh -c 'printenv GIT_OPTIONAL_LOCKS >> {folder}/filtered; echo > {outside}/filtered; cat'"
git config filter.fence.smudge cat
echo '* filter=fence' > .git/info/attributes
git add escape.txt && git commit -q -m escape
echo changed >> README
echo probed
"""
"""What the agent runs in its shell, from its workspace, with the paths a test made filled in."""


@dataclass(frozen=True)
class Harness:
    """How one harness reaches FakeModel and the shell and tools it calls, as its own tests do. `variables` is what the
    runtime's environment holds that the role's auth profile names. `before` is shell work it does first, and `probe`
    is how it runs the probe, which commits."""

    program: str
    installed: Callable[[], bool]
    role: dict[str, Any]
    variables: Callable[[FakeModel], dict[str, str]]
    shell: Callable[[str], ToolCall]
    tool: Callable[[str, dict[str, Any]], ToolCall]
    probe: Callable[[str], ToolCall] | None = None
    before: tuple[str, ...] = ()
    state: str | None = None


def chat(model: FakeModel) -> dict[str, str]:
    return {"OPENAI_BASE_URL": f"{model.url}/v1", "OPENAI_API_KEY": "dummy-key"}


HARNESSES = {
    "claude": Harness(
        "claude",
        lambda: shutil.which("claude") is not None,
        {"harness": "claude"},
        lambda model: {"ANTHROPIC_BASE_URL": model.url, "ANTHROPIC_API_KEY": "dummy-key"},
        lambda command: ToolCall("Bash", {"command": command, "description": "probe"}),
        lambda name, arguments: ToolCall(f"mcp__ph__{name}", arguments),
        state=".claude",
    ),
    "codex": Harness(
        "codex",
        lambda: shutil.which("codex") is not None,
        {"harness": "codex", "sandbox": "workspace-write"},
        chat,
        lambda command: ToolCall("exec_command", {"cmd": command}),
        lambda name, arguments: ToolCall(name, arguments, namespace="mcp__ph"),
        probe=lambda command: ToolCall("exec_command", {"cmd": command, **ESCALATED}, id="call_gated"),
        before=("echo nested > nested.txt",),
        state=".codex",
    ),
    "pi": Harness(
        "pi",
        lambda: shutil.which("pi") is not None,
        {"harness": "pi"},
        lambda model: {**chat(model), "PI_OFFLINE": "yes"},
        lambda command: ToolCall("bash", {"command": command}),
        lambda name, arguments: ToolCall(f"mcp__ph__{name}", arguments),
        state=".pi",
    ),
    "openhands": Harness(
        "openhands",
        lambda: importlib.util.find_spec("openhands") is not None,
        {"harness": "openhands"},
        chat,
        lambda command: ToolCall("terminal", {"command": command}, id="call_gated"),
        lambda name, arguments: ToolCall(name, arguments),
    ),
}


@dataclass
class Evidence:
    """What one isolated agent's session left: what its probe found, what is outside it, and what was recorded."""

    found: dict[str, str]
    canaries: dict[str, bool]
    filtered: list[str]
    made_in: list[str | None]
    assurances: dict[str, str]
    sent: list[str]
    left: list[int]
    home: Path
    yours: tuple[list[str], list[str]]
    state: str | None
    nested: bool | None = None
    kept: list[str] = field(default_factory=list)


def lines_of(path: Path) -> dict[str, str]:
    """Each line of what the probe wrote, by its first word."""
    return dict(line.split(" ", 1) for line in path.read_text().splitlines() if " " in line)


def marked(marker: str) -> list[int]:
    """The processes whose command line holds `marker`, which only the probe's own can."""
    found = []
    for entry in Path("/proc").iterdir():
        try:
            if entry.name.isdecimal() and marker in entry.joinpath("cmdline").read_bytes().decode(errors="replace"):
                found.append(int(entry.name))
        except OSError:
            continue
    return found


async def confined(harness: Harness, folder: Path, monkeypatch: pytest.MonkeyPatch) -> Evidence:
    """One session: `bob` isolated on `harness`, beside `ann`, a scripted agent in your checkout, probing and calling
    our tools in one turn, then cancelled, so its stop looks once more and keeps its snapshot for the commit."""
    monkeypatch.setattr(support, "SECONDS", SECONDS)
    repo = repository(folder / "repo", monkeypatch)
    outside, home, root = folder / "outside", folder / "home", folder / "root"
    for made in (outside, home):
        made.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("PLATOON_HARNESS_HOME", str(root))
    session = root / "sessions" / "s"
    bob, marker = agent_folder(session, "bob"), uuid.uuid4().hex
    private = Path(f"/tmp/platoon-harness-{uuid.uuid4().hex}")
    objects = Path(git("rev-parse", "--path-format=absolute", "--git-path", "objects", cwd=repo).strip())
    paths = {"outside": outside, "repo": repo, "objects": objects, "private": private, "folder": bob}
    paths |= {"session": session, "other": agent_folder(session, "ann"), "socket": socket_path(session)}
    (repo / "probe.sh").write_text(PROBE.format(**paths, marker=marker))
    probe = (harness.probe or harness.shell)("sh probe.sh")
    sending = harness.tool("message_send", {"to": "@you", "gist": "reached"})
    async with FakeModel(*map(harness.shell, harness.before), probe, sending, "done") as model:
        for name, value in harness.variables(model).items():
            monkeypatch.setenv(name, value)
        bobs = {**harness.role, "model": MODEL, "auth": "fake", "workspace": "isolated", "approvals": "allow"}
        team = Team.model_validate(
            {
                "extensions": ["bwrap"],
                "auth": {"fake": {"env": sorted(harness.variables(model))}},
                "roles": {"bob": bobs, "ann": {"harness": scripted()}},
                "topology": {"edges": {"bob": ["human"]}},
            }
        )
        async with Session.start(team, name="s", root=root, cwd=repo) as running:
            await in_state(running, "bob", "idle")
            yours = sorted(map(str, home.rglob("*")))
            await running.send("@bob", "probe your isolation")
            await until(lambda: looked_at(running, "@bob"), running, lambda found: len(found) > 0)
            await until(lambda: of_type(running, "message.sent"), running)
            await running.cancel_agent("@bob")
            await until(lambda: stops(running), running)
            ending = await running.ending()
            started = await of_type(running, "agent.started")
            committed = await of_type(running, "repo.committed")
            messages = await of_type(running, "message.sent")
    sent = [event.gist for event in messages if event.actor == "agent:bob"]
    left = marked(marker)
    for pid in left:  # The probe started each, so this test ends it.
        with contextlib.suppress(ProcessLookupError):
            os.kill(pid, signal.SIGKILL)
    workspace = bob / "workspace"
    return Evidence(
        found=lines_of(workspace / "escape.txt"),
        canaries={
            name: path.exists()
            for name, path in {
                "outside": outside / "escaped",
                "objects": objects / "escaped",
                "tmp": private,
                "filter": outside / "filtered",
            }.items()
        },
        filtered=(bob / "filtered").read_text().split() if (bob / "filtered").exists() else [],
        made_in=[event.data["made_in"] for event in committed if event.gist.endswith(" escape")],
        assurances={event.agent: event.data["assurance"] for event in started},
        sent=sent,
        left=left,
        home=bob / "home",
        yours=(yours, sorted(map(str, home.rglob("*")))),
        state=harness.state,
        nested=(workspace / "nested.txt").exists() if harness.before else None,
        kept=[why for kept in ending.workspaces for why in kept["why"]],
    )


async def looked_at(session: Session, workspace: str) -> list[Any]:
    return [event for event in await of_type(session, "workspace.changed") if event.data["workspace"] == workspace]


async def stops(session: Session) -> list[Any]:
    return [event for event in await of_type(session, "effect.finished") if event.data["kind"] == "stop"]


@pytest.fixture(scope="module", params=sorted(HARNESSES))
def evidence(request: pytest.FixtureRequest, tmp_path_factory: pytest.TempPathFactory) -> Evidence:
    """One session per harness, which every test of a promise reads."""
    harness = HARNESSES[request.param]
    if not harness.installed():
        pytest.skip(f"{harness.program} is not installed, so no isolated harness ran here")
    if (why := Bubblewrap().refusal()) is not None:
        pytest.skip(f"bubblewrap cannot confine here, so nothing was confined: {why}")
    with pytest.MonkeyPatch.context() as monkeypatch:
        return asyncio.run(confined(harness, tmp_path_factory.mktemp(harness.program), monkeypatch))


def test_an_isolated_agent_cannot_write_outside_its_tree_and_folder(evidence):
    """It writes its tree, its folder and a /tmp of its own, and none of what it tried outside them is on disk. Here the
    test's folders are all in /tmp, so a write into one that holds what it may read lands in its own /tmp."""
    found = evidence.found
    tried = [found[name] for name in ("outside", "objects", "tmp", "folder")]
    assert tried == ["refused", "refused", "written", "written"]
    assert not any(evidence.canaries.values()), evidence.canaries


def test_an_isolated_agent_cannot_read_the_session_folder_or_another_agent_s_token(evidence):
    """No other agent's token is ever on disk, and its folder, like the session's journal and owner's token, is
    unseen."""
    assert (evidence.found["journal"], evidence.found["token"], evidence.found["other"]) == (
        "unseen",
        "unread",
        "unseen",
    )


def test_an_isolated_agent_cannot_reach_the_control_socket(evidence):
    assert evidence.found["socket"] == "unseen"


def test_an_isolated_agent_sees_only_its_own_processes(evidence):
    """A process namespace of its own numbers from one, whatever runs on the host."""
    count, _, highest = evidence.found["processes"].split()
    assert int(count) < 50 and int(highest) < 1000


def test_nothing_an_isolated_agent_starts_outlives_it(evidence):
    """It left a process in a session of its own, which ends with its harness."""
    assert evidence.left == []


def test_an_isolated_agent_can_commit_in_its_snapshot(evidence):
    """Its commit is recorded as its own, and its stop keeps its snapshot, made whole, for it."""
    assert evidence.made_in == ["@bob"]
    assert "1 commit only its branch holds" in evidence.kept
    assert evidence.nested in (None, True)  # Codex's own sandbox ran a command, nested in ours.


def test_an_isolated_agent_s_git_config_runs_nothing_outside_its_isolation(evidence):
    """Its config names a filter, which the runtime's look ran, inside the isolation."""
    assert "0" in evidence.filtered
    assert evidence.canaries["filter"] is False


def test_an_isolated_agent_still_reaches_its_tools(evidence):
    """Our tool plane is on loopback, which the isolation keeps."""
    assert evidence.sent == ["reached"]


def test_an_isolated_harness_keeps_its_state_in_its_own_home(evidence):
    """Its home is in its folder, and the runtime's own home gains nothing from its launch on."""
    before, after = evidence.yours
    assert evidence.found["home"] == str(evidence.home)
    assert after == before
    if evidence.state is not None:
        assert (evidence.home / evidence.state).is_dir()


def test_isolated_assurance_is_recorded_only_for_a_confined_launch(evidence):
    assert evidence.assurances == {"bob": "isolated", "ann": "cooperative"}
