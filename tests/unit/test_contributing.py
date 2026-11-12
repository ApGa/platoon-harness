"""CONTRIBUTING.md stays true: each command it shows is one CI or a hook runs, one that makes a generated page, or one
it runs by hand for a stated reason; it shows the release workflow's commands under Releases, and names every hook; its
commit types are the ones the hook and the title check accept; the paths it names and the version it shows are real; and
the pull request template asks for what it asks. The workflows themselves pin every action, and read only but where they
publish, and the ruff hook runs the ruff the dev group pins."""

import re
import tomllib
from pathlib import Path
from typing import Any

import yaml

import platoon_harness

ROOT = Path(__file__).parents[2]
GUIDE = ROOT / "CONTRIBUTING.md"
TEXT = GUIDE.read_text()
HOOKS = yaml.safe_load((ROOT / ".pre-commit-config.yaml").read_text())
TEMPLATE = ROOT / ".github" / "pull_request_template.md"
TITLE_CHECK = "amannn/action-semantic-pull-request"
DEFAULT_TYPES = ("build", "chore", "ci", "docs", "feat", "fix", "perf", "refactor", "revert", "style", "test")
"""The types conventional-pre-commit v4.0.0 and the title check each accept when given none."""
GENERATED = {
    "docs/reference/cli.md": "uv run python -m platoon_harness_cli.reference > docs/reference/cli.md",
    "docs/reference/python.md": "uv run python -m platoon_harness_cli.reference python > docs/reference/python.md",
    "docs/reference/team-file.md": "uv run python -m platoon_harness_cli.team_file > docs/reference/team-file.md",
    "docs/how-to/tui.md": "uv run python -m platoon_harness_cli.tui.keymap docs/how-to/tui.md",
}
"""Each generated page, and the command that makes it again, which the page names."""
BY_HAND = {
    "git clone https://github.com/ApGa/platoon-harness.git && cd platoon-harness": "makes a checkout",
    "uv run pre-commit install": "installs the hooks, which CI runs without",
    "uv run platoon-harness --version": "checks a checkout",
    "uv run pytest -q -m slow": "needs harness binaries, which CI does not have",
    "uv run playwright install chromium-headless-shell": "CI installs it with --with-deps, which needs root",
    "PLATOON_HARNESS_LIVE=1 uv run pytest -q -m live tests/live/test_claude.py": "spends model calls on real logins",
    "uv run ruff check . && uv run ruff format --check .": "the ruff hooks' checks, without their fixes",
    (
        "PLATOON_HARNESS_LIVE=1 PLATOON_HARNESS_RECORD=tests/fixtures/sessions/mixed-team uv run pytest -q -m live "
        "tests/live/test_examples.py -k mixed_team"
    ): "spends model calls on a person's key, and records the docs' session",
    "uv run pytest -q tests/unit/tui/test_snapshots.py -k recorded --snapshot-update": (
        "makes the snapshots of a session recorded by hand"
    ),
    "PLATOON_HARNESS_IMAGES=docs/assets uv run pytest -q -m e2e tests/e2e/test_page_images.py": (
        "writes the docs' page images, from a session recorded by hand"
    ),
    "uv run pre-commit run conventional-pre-commit --hook-stage commit-msg --commit-msg-filename message.txt": (
        "the commit-msg hook, on a message not committed"
    ),
    "git switch main && git pull --ff-only": "a maintainer's, before tagging a release",
    'git tag -a v0.2.0 -m "platoon-harness 0.2.0"': "a maintainer's, as only maintainers make a release's tag",
    "git push origin v0.2.0": "a maintainer's, as the tag it pushes publishes the release",
}
"""Each command the guide shows that neither CI nor a hook runs, and why it is run by hand."""
PUBLISHES = "github.repository == 'ApGa/platoon-harness' && github.event_name == 'push' && "
"""How the condition of a job that publishes begins: on a push to this repository, never to a fork or for a pull
request."""
PINNED = re.compile(r"(?P<action>[\w.-]+/[\w./-]+)@(?P<commit>[0-9a-f]{40})  # (?P<release>v\d+\.\d+\.\d+)")
"""An action pinned to a commit, with the release it is beside it."""
FENCE = re.compile(r"^(?P<indent> *)```(?P<language>[\w-]*)$")
PATH = re.compile(r"`((?:\.github|docs|examples|packages|tests)/[\w./-]*|[\w.-]+\.(?:md|toml|yaml|txt))`")


def blocks(language: str, text: str = TEXT) -> list[str]:
    """Each fenced block of `language`, without the indentation of a block inside a list."""
    found, lines, index = [], text.splitlines(), 0
    while index < len(lines):
        fence = FENCE.match(lines[index])
        index += 1
        if fence is None:
            continue
        body = []
        while lines[index].strip() != "```":
            body.append(lines[index].removeprefix(fence["indent"]))
            index += 1
        index += 1
        if fence["language"] == language:
            found.append("\n".join(body))
    return found


def shown(text: str = TEXT) -> list[str]:
    """Each command of the guide's shell blocks, one per line, but comments."""
    return [line for block in blocks("bash", text) for line in block.splitlines() if line and not line.startswith("#")]


def section(heading: str) -> str:
    """The guide's section under `## heading`, up to the next."""
    start = TEXT.index(f"\n## {heading}\n")
    end = TEXT.find("\n## ", start + 1)
    return TEXT[start : end if end != -1 else None]


def steps(workflow: str = "*") -> list[dict[str, Any]]:
    """Each step of each job of the workflows `workflow` names, a file name without `.yml`, or all of them."""
    return [
        step
        for path in sorted((ROOT / ".github" / "workflows").glob(f"{workflow}.yml"))
        for job in yaml.safe_load(path.read_text())["jobs"].values()
        for step in job["steps"]
    ]


def ci_runs(workflow: str = "*") -> list[str]:
    """Each line of each `run` of each step of the workflows `workflow` names."""
    return [line for step in steps(workflow) if "run" in step for line in step["run"].strip().splitlines()]


def actions() -> list[str]:
    """What each step of each workflow `uses`, as it is written, with its comment."""
    return [
        line.split("uses: ", 1)[1]
        for path in sorted((ROOT / ".github" / "workflows").glob("*.yml"))
        for line in path.read_text().splitlines()
        if line.lstrip("- ").startswith("uses: ")
    ]


def hooks() -> list[dict[str, Any]]:
    """Each hook, with its repository's `rev`."""
    return [{**hook, "rev": repo.get("rev")} for repo in HOOKS["repos"] for hook in repo["hooks"]]


def table(header: str) -> list[list[str]]:
    """The body rows of the guide's table whose header row is `header`, as cells."""
    lines = TEXT.splitlines()
    start = lines.index(header)
    rows = []
    for line in lines[start + 2 :]:
        if not line.startswith("|"):
            break
        rows.append([cell.strip() for cell in line.strip("|").split("|")])
    return rows


def test_every_command_shown_is_run_by_ci_a_hook_or_a_generator_or_by_hand_for_a_reason():
    run = set(ci_runs()) | {hook["entry"] for hook in hooks() if "entry" in hook} | set(GENERATED.values())
    commands = shown()

    assert commands
    assert [command for command in commands if command not in run and command not in BY_HAND] == []
    assert [command for command in BY_HAND if command not in commands] == []


def test_every_command_the_release_workflow_runs_is_shown():
    """Under Releases, in the order the workflow runs them, so a release is checked by hand as CI checks it."""
    runs = ci_runs("release")

    assert runs
    assert [command for command in shown(section("Releases")) if command in runs] == runs


def test_each_generated_page_names_the_command_that_makes_it_again():
    for page, command in GENERATED.items():
        assert command in (ROOT / page).read_text()
        assert command in shown()


def test_every_hook_is_named():
    assert hooks()
    assert [hook["id"] for hook in hooks() if f"`{hook['id']}`" not in TEXT] == []


def test_a_plain_install_installs_every_git_hook_the_config_uses():
    default = HOOKS.get("default_stages", ["pre-commit"])
    stages = {stage for hook in hooks() for stage in hook.get("stages", default)}

    assert stages <= set(HOOKS["default_install_hook_types"])
    assert "uv run pre-commit install" in shown()


def test_the_commit_types_are_the_ones_the_hook_and_the_title_check_accept():
    types = sorted(row[0].strip("`") for row in table("| Type | For |"))
    [hook] = [hook for hook in hooks() if hook["id"] == "conventional-pre-commit"]
    [check] = [step for step in steps() if str(step.get("uses", "")).startswith(TITLE_CHECK)]

    assert hook["rev"] == "v4.0.0", "the guide gives v4.0.0's rules"
    assert types == sorted([arg for arg in hook.get("args", []) if not arg.startswith("-")] or DEFAULT_TYPES)
    assert types == sorted(str(check.get("with", {}).get("types", "")).split() or DEFAULT_TYPES)


def test_the_example_messages_are_ones_the_title_check_accepts():
    """A whole message has a subject, a blank line and a body, and a list has a subject on each line."""
    [check] = [step for step in steps() if str(step.get("uses", "")).startswith(TITLE_CHECK)]
    summary = re.compile(check["with"]["subjectPattern"])
    types = {row[0].strip("`") for row in table("| Type | For |")}
    examples = [block.splitlines() for block in blocks("text") if re.match(r"[a-z]+!?: ", block)]
    subjects = [line for lines in examples for line in (lines[:1] if "" in lines else lines)]

    assert len(examples) >= 3 and len(subjects) > len(examples)
    for lines in examples:
        if "" in lines:
            assert any(line.startswith("BREAKING CHANGE: ") for line in lines) == ("!" in lines[0].split(":")[0])
    for subject in subjects:
        kind, _, text = subject.partition(": ")
        assert kind.removesuffix("!") in types, subject
        assert summary.fullmatch(text), subject


def test_every_action_is_pinned_to_a_commit_and_every_workflow_reads_only_by_default():
    """A tag moved upstream, or a release of a tool `uvx` fetches, changes nothing a workflow runs, a workflow's token
    reads only, and no checkout keeps credentials for a later step. A job that publishes alone asks for more, an OIDC
    token and nothing else, on a push to this repository, in the `pypi` environment, and runs no code of the repository:
    it uploads what the build made."""
    workflows = [yaml.safe_load(path.read_text()) for path in (ROOT / ".github" / "workflows").glob("*.yml")]
    jobs = [job for workflow in workflows for job in workflow["jobs"].values()]
    publishing = [job for job in jobs if "id-token" in job.get("permissions", {})]
    reading = [job for job in jobs if job not in publishing]
    checkouts = [step for step in steps() if step.get("uses", "").startswith("actions/checkout@")]
    fetched = [line for step in steps() for line in step.get("run", "").splitlines() if line.startswith("uvx ")]

    assert len(actions()) == len([step for step in steps() if "uses" in step]) > 0
    assert [action for action in actions() if PINNED.fullmatch(action) is None] == []
    assert (
        checkouts and [step for step in checkouts if step.get("with", {}).get("persist-credentials") is not False] == []
    )
    assert [line for line in fetched if re.match(r"uvx (--from dist/|[\w-]+@[\d.]+ )", line) is None] == []
    assert [workflow.get("permissions") for workflow in workflows] == [{"contents": "read"}] * len(workflows)
    assert {access for job in reading for access in job.get("permissions", {}).values()} <= {"read"}
    assert publishing and {job["if"].startswith(PUBLISHES) for job in publishing} == {True}
    assert [(job["permissions"], job["environment"]["name"]) for job in publishing] == [
        ({"id-token": "write"}, "pypi")
    ] * len(publishing)
    assert {step["uses"].partition("@")[0] for job in publishing for step in job["steps"]} == {
        "actions/download-artifact",
        "pypa/gh-action-pypi-publish",
    }


def test_the_ruff_hook_runs_the_ruff_the_dev_group_pins():
    dev = tomllib.loads((ROOT / "pyproject.toml").read_text())["dependency-groups"]["dev"]
    [pin] = [requirement for requirement in dev if requirement.startswith("ruff==")]
    revs = {hook["rev"] for hook in hooks() if hook["id"].startswith("ruff")}

    assert revs == {f"v{pin.removeprefix('ruff==')}"}


def test_the_paths_the_guide_names_exist():
    paths = set(PATH.findall(TEXT)) - {"message.txt"}

    assert ROOT / "pyproject.toml" in {ROOT / path for path in paths}
    assert sorted(path for path in paths if not (ROOT / path).exists()) == []


def test_the_version_shown_is_the_one_the_command_line_prints():
    version = f"platoon-harness {platoon_harness.__version__}"

    assert version in blocks("text")


def test_the_pull_request_template_asks_for_what_the_guide_asks():
    template = TEMPLATE.read_text()
    sections = re.findall(r'CONTRIBUTING\.md, (?:under )?"([^"]+)"', template)
    both = (" ".join(template.split()), " ".join(TEXT.split()))

    assert "](.github/pull_request_template.md)" in TEXT
    for heading in ("Summary", "Why", "Links", "Tests", "Checklist"):
        assert f"\n## {heading}\n" in template
    for asked in ("`<type>: <summary>`", "no scope", "sentence case", "final period", "live tests", "BREAKING CHANGE:"):
        assert all(asked in text for text in both), asked
    for asked in ("Fixes #123", "Implements RFC NNNN, milestone M2", "`tests/public_api.txt`"):
        assert all(asked in text for text in both), asked
    assert sections and [section for section in sections if f"\n## {section}\n" not in TEXT] == []
    commands = re.findall(r"`(uv run [^`]+)`", template)
    unrun = [command for command in commands if not any(run.startswith(command) for run in ci_runs())]
    assert commands and unrun == []
