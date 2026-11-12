"""The release workflow publishes what it built: its build job uploads the files before any step runs code the lock does
not pin, a pinned uv and a pinned hatchling build them, a tag's run is never cancelled, and each check of a tag says
why it failed."""

import re
import tomllib
from pathlib import Path

import yaml

ROOT = Path(__file__).parents[2]
WORKFLOW = yaml.safe_load((ROOT / ".github" / "workflows" / "release.yml").read_text())
BUILD = WORKFLOW["jobs"]["build"]["steps"]
ON_A_TAG = "github.ref_type == 'tag'"


def test_the_build_uploads_its_files_before_any_step_runs_code_the_lock_does_not_pin():
    """Between the build and the upload runs only the check that the tag names the version built, which reads dist/."""
    [built] = [index for index, step in enumerate(BUILD) if step.get("run") == "uv build --no-sources"]
    [uploaded] = [index for index, step in enumerate(BUILD) if "upload-artifact@" in step.get("uses", "")]
    [between] = BUILD[built + 1 : uploaded]

    assert built < uploaded
    assert "uses" not in between and between["run"].startswith('test -f "dist/')


def test_a_pinned_uv_and_a_pinned_hatchling_build_a_release():
    [setup] = [step for step in BUILD if step.get("uses", "").startswith("astral-sh/setup-uv@")]
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text())
    constraints = pyproject["tool"]["uv"]["build-constraint-dependencies"]

    assert re.fullmatch(r"\d+\.\d+\.\d+", setup["with"]["version"])
    assert pyproject["build-system"]["build-backend"] == "hatchling.build"
    assert [constraint for constraint in constraints if re.fullmatch(r"hatchling==\d+\.\d+\.\d+", constraint)]


def test_a_tag_s_run_is_never_cancelled():
    """A second push of the same tag cannot stop an upload under way, while a newer push to a branch still cancels."""
    assert WORKFLOW["concurrency"]["cancel-in-progress"] == "${{ github.ref_type != 'tag' }}"


def test_each_check_of_a_tag_says_why_it_failed():
    checks = [step["run"] for step in BUILD if step.get("if") == ON_A_TAG]

    assert checks
    assert [run for run in checks if not re.search(r' \|\| \{ echo "::error::[^"]+"; exit 1; \}$', run)] == []
