"""Isolated workspaces on real git under `tmp_path`: refused before any cost where one cannot be given, and otherwise a
snapshot whose harness, and the runtime's own git in its tree, run under its isolation's wrap."""

import os
import pwd
import shutil
from pathlib import Path
from typing import Any

import pytest

from platoon_harness import ConfigError, Session, Team
from platoon_harness.bwrap import Bubblewrap
from platoon_harness.drivers import AgentSpec, DriverInfo, Login, Reporter
from platoon_harness.kernel import Extension
from platoon_harness.runtime import isolation
from platoon_harness.runtime.paths import agent_folder
from platoon_harness.testing import ScriptedDriver

from .gitting import Working, commit, repository
from .support import extension, harness, in_state, of_type, until
from .test_workspaces import problems_of, workspace_of

pytestmark = pytest.mark.timeout(60)

FENCED = 'printf "%s\\t%s\\n" "$PWD" "$*" >> "$0"; exec "$@"'
"""What a fence runs before each command it is given: a line of where and what, in its log, which is `$0`."""


class Fence:
    """An isolation that confines nothing and writes down what it is given to run, and where, for a test to read. What
    it was last asked to keep a command to is `asked`."""

    def __init__(self, log: Path, refusal: str | None = None) -> None:
        self.log = log
        self.said = refusal
        self.asked: tuple[Path, tuple[Path, ...], tuple[Path, ...]] | None = None

    def refusal(self) -> str | None:
        return self.said

    def wrap(self, writable: Path, readable: Any, hidden: Any) -> tuple[str, ...]:
        self.asked = (writable, tuple(readable), tuple(hidden))
        return ("/bin/sh", "-c", FENCED, str(self.log))

    def lines(self) -> list[tuple[str, str]]:
        """Each command the fence ran, as where and what."""
        text = self.log.read_text() if self.log.exists() else ""
        return [(where, what) for where, _, what in (line.partition("\t") for line in text.splitlines())]


class Placed(Working):
    """A harness each of whose turns does its next piece of `work`, and which says where it is installed and what login
    it has, as a harness in a process of its own does. Each spec it starts on goes in `started`."""

    def __init__(self, *work: Any, login: Login | None = None, started: list[AgentSpec] | None = None) -> None:
        super().__init__(work)
        self._login = login
        self._started = [] if started is None else started

    def describe(self) -> DriverInfo:
        return super().describe().model_copy(update={"installed": (Path("/bin/sh"),), "login": self._login})

    async def start(self, spec: AgentSpec, report: Reporter) -> None:
        self._started.append(spec)
        await super().start(spec, report)


def isolated_team(*extensions: str, login: Login | None = None, auth: bool = False) -> Team:
    """`bob`, in an isolated workspace, on a harness that says where it is installed and what login it has."""
    bob = {"harness": harness(lambda: Placed(login=login)), "workspace": "isolated"}
    profiles = {"auth": {"fake": {"env": ["FAKE_KEY"]}}} if auth else {}
    bob |= {"auth": "fake"} if auth else {}
    return Team.model_validate({"extensions": extensions, "roles": {"bob": bob}, **profiles})


@pytest.fixture
def repo(tmp_path, monkeypatch) -> Path:
    return repository(tmp_path / "repo", monkeypatch)


# Before any cost.


async def test_isolated_with_no_extension_that_confines_is_refused_before_any_cost(repo, tmp_path):
    with pytest.raises(ConfigError) as refused:
        await Session.start(isolated_team(), root=tmp_path / "home", cwd=repo)

    what = "roles.bob.workspace: `isolated` needs an extension the team names whose isolation confines a harness"
    assert what in str(refused.value)
    assert not (tmp_path / "home" / "sessions").exists()


def test_two_extensions_that_confine_are_refused_naming_both(repo, tmp_path):
    fence = extension(Extension("fence", isolation=Fence(tmp_path / "fenced")))
    wall = extension(Extension("wall", isolation=Fence(tmp_path / "walled")))

    found = problems_of(isolated_team(fence, wall), repo, tmp_path / "home")

    assert found["error"] == [
        "extensions: `fence` and `wall` each give an isolation, and an isolated agent runs in one: name one"
    ]


def test_an_isolation_that_cannot_confine_here_is_refused_before_any_cost(repo, tmp_path):
    fence = extension(Extension("fence", isolation=Fence(tmp_path / "fenced", "user namespaces are blocked here")))

    found = problems_of(isolated_team(fence), repo, tmp_path / "home")

    assert found["error"] == ["extensions.fence: user namespaces are blocked here"]


def test_a_harness_that_declares_no_installed_path_is_refused_before_any_cost(repo, tmp_path):
    fence = extension(Extension("fence", isolation=Fence(tmp_path / "fenced")))
    team = Team.model_validate(
        {"extensions": [fence], "roles": {"bob": {"harness": harness(ScriptedDriver), "workspace": "isolated"}}}
    )

    found = problems_of(team, repo, tmp_path / "home")

    assert found["error"] == [
        "roles.bob.harness: `scripted` declares no path its harness is installed at, so an isolation could not show "
        "it: a harness in the runtime's own process cannot be confined, and one `PATH` does not find cannot run"
    ]


@pytest.mark.parametrize("login", ["plan", "key"])
def test_isolated_on_a_plan_login_is_refused(repo, tmp_path, login):
    """Or on any login of the harness's own, which is in your home, where an isolated harness never looks."""
    fence = extension(Extension("fence", isolation=Fence(tmp_path / "fenced")))

    found = problems_of(isolated_team(fence, login=login), repo, tmp_path / "home")
    given = problems_of(isolated_team(fence, login=login, auth=True), repo, tmp_path / "home")
    gateway = problems_of(isolated_team(fence, login=login), repo, tmp_path / "home", trainable=True)

    assert found["error"] == [
        f"roles.bob.auth: `isolated` gives `scripted` a home of its own, where the {login} login it signs in with in "
        "yours is not: give the role an auth profile"
    ]
    assert "error" not in given
    assert not [problem for problem in gateway.get("error", ()) if problem.startswith("roles.bob.auth")]


def test_isolated_is_refused_where_a_snapshot_is(tmp_path):
    fence = extension(Extension("fence", isolation=Fence(tmp_path / "fenced")))
    (tmp_path / "plain").mkdir()

    found = problems_of(isolated_team(fence), tmp_path / "plain", tmp_path / "home")

    assert found["error"] == [
        f"roles.bob.workspace: `isolated` needs a git work tree, and {tmp_path / 'plain'} is in no git work tree"
    ]


# A launch, and the runtime's own git.


async def test_isolated_assurance_is_recorded_only_for_a_confined_launch(repo, tmp_path):
    fence = Fence(tmp_path / "fenced")
    started: list[AgentSpec] = []
    ann = {"harness": harness(lambda: Placed(started=started)), "workspace": "snapshot"}
    cy = {"harness": harness(lambda: Placed(started=started)), "workspace": "isolated", "count": 0}
    bob = {"harness": harness(lambda: Placed(started=started)), "workspace": "isolated"}
    team = Team.model_validate(
        {"extensions": [extension(Extension("fence", isolation=fence))], "roles": {"bob": bob, "ann": ann, "cy": cy}}
    )
    async with Session.start(team, name="s", root=tmp_path / "home", cwd=repo) as session:
        await in_state(session, "bob", "idle")
        await in_state(session, "ann", "idle")
        made = workspace_of(session, "bob")
        fence.said = "user namespaces were blocked since"
        await session.spawn("cy", "cy")
        await in_state(session, "cy", "ended")
        assurances = {event.agent: event.data["assurance"] for event in await of_type(session, "agent.started")}
        ending = await session.ending()

    assert (made.mode, made.assurance) == ("isolated", "isolated")
    assert assurances == {"bob": "isolated", "ann": "cooperative"}
    assert {spec.agent: spec.wrap for spec in started} == {"bob": ("/bin/sh", "-c", FENCED, str(fence.log)), "ann": ()}
    cy = next(row for row in ending.agents if row["agent"] == "cy")
    assert cy["reason"] == "its spawn failed: user namespaces were blocked since"


async def test_an_isolated_harness_keeps_its_state_in_its_own_home(repo, tmp_path):
    fence = Fence(tmp_path / "fenced")
    started: list[AgentSpec] = []
    bob = {"harness": harness(lambda: Placed(started=started)), "workspace": "isolated"}
    team = Team.model_validate({"extensions": [extension(Extension("fence", isolation=fence))], "roles": {"bob": bob}})
    async with Session.start(team, name="s", root=tmp_path / "home", cwd=repo) as session:
        await in_state(session, "bob", "idle")
        made = workspace_of(session, "bob")
    folder = agent_folder(session.folder, "bob")

    [spec] = started
    assert spec.env == {"HOME": str(folder / "home")}
    assert (folder / "home").is_dir()
    assert fence.asked == (folder, (Path(str(made.objects)), Path("/bin/sh")), isolation.hidden(session.folder))
    assert {Path.home(), tmp_path / "home", Path(pwd.getpwuid(os.getuid()).pw_dir)} <= set(
        isolation.hidden(session.folder)
    )


async def test_the_runtime_s_git_in_an_isolated_tree_runs_under_its_wrap(repo, tmp_path):
    """Its looks, the stop's reading of what it would lose, making a kept one whole, and finding its objects for the
    session's bundle, in its repository."""
    fence = Fence(tmp_path / "fenced")
    bob = {"harness": harness(lambda: Placed(lambda cwd: commit(cwd, "work"))), "workspace": "isolated"}
    team = Team.model_validate({"extensions": [extension(Extension("fence", isolation=fence))], "roles": {"bob": bob}})
    async with Session.start(team, name="s", root=tmp_path / "home", cwd=repo) as session:
        await in_state(session, "bob", "idle")
        tree = Path(workspace_of(session, "bob").path)
        await session.send("@bob", "commit your work")
        await until(lambda: of_type(session, "repo.committed"), session)
        await session.cancel_agent("@bob")
        await until(lambda: stops(session), session)
        [kept] = (await session.ending()).workspaces
        committed = await of_type(session, "repo.committed")

    ran = fence.lines()
    assert [event.data["made_in"] for event in committed] == ["@bob"]
    assert {where for where, _ in ran} == {str(tree), str(tree / ".git")}
    assert any(what.startswith("git ") and " status " in f" {what} " for _, what in ran)
    assert any(" log -g " in f" {what} " for _, what in ran)
    assert any(" repack -a -d " in f" {what} " for _, what in ran)
    assert any(" --git-path objects" in what for where, what in ran if where == str(tree / ".git"))
    assert kept["why"] == ["1 commit only its branch holds"]


async def looked_at(session: Session, workspace: str) -> list[Any]:
    return [event for event in await of_type(session, "workspace.changed") if event.data["workspace"] == workspace]


async def stops(session: Session) -> list[Any]:
    return [event for event in await of_type(session, "effect.finished") if event.data["kind"] == "stop"]


# On real bubblewrap.


@pytest.fixture
def confining() -> None:
    if shutil.which("bwrap") is None or (why := Bubblewrap().refusal()) is not None:
        pytest.skip(f"bubblewrap cannot confine here, so nothing was confined: {why or 'bwrap is not on PATH'}")


@pytest.mark.usefixtures("confining")
async def test_an_isolated_agent_s_git_config_runs_nothing_outside_its_isolation(repo, tmp_path, monkeypatch):
    """An agent's own config names a filter, which the runtime's look runs as your git would: inside the isolation,
    where what it would write outside its folder is not there to be written, and on the allowlist its harness gets, so
    a variable only the runtime's environment holds never reaches it."""
    monkeypatch.setenv("PH_RUNTIME_ONLY", "leaked")
    outside = tmp_path / "outside"
    outside.mkdir()

    def configure(cwd: Path) -> None:
        folder = cwd.parent
        seen = f'echo "locks=$GIT_OPTIONAL_LOCKS runtime=$PH_RUNTIME_ONLY" >> {folder}/filtered'
        clean = f"sh -c '{seen}; : > {outside}/escaped; cat'"
        with (cwd / ".git" / "config").open("a") as config:
            config.write(f'[filter "fence"]\n\tclean = "{clean}"\n\tsmudge = cat\n')
        (cwd / ".git" / "info" / "attributes").write_text("* filter=fence\n")
        (cwd / "README").write_text("changed\n")

    bob = {"harness": harness(lambda: Placed(configure)), "workspace": "isolated"}
    team = Team.model_validate({"extensions": ["bwrap"], "roles": {"bob": bob}})
    async with Session.start(team, name="s", root=tmp_path / "home", cwd=repo) as session:
        await in_state(session, "bob", "idle")
        await session.send("@bob", "configure your git")
        await until(lambda: looked_at(session, "@bob"), session)
    folder = agent_folder(session.folder, "bob")

    assert (folder / "filtered").read_text().splitlines()[-1] == "locks=0 runtime="
    assert not (outside / "escaped").exists()
