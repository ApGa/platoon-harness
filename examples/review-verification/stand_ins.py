"""Scripted stand-ins for the review team's harnesses, which do what job.md and each role's instructions ask with git
and no model at all. With this folder on `PYTHONPATH`, a role whose harness is `stand_ins:author`, `stand_ins:reviewer`
or `stand_ins:verifier` runs one. They show the flow: a commit, its review, your test of it and a verdict, each citing
what it rests on. Each runs in the runtime's own process, so none shows what a sandbox or an approval stops."""

import asyncio
import json
import subprocess
from pathlib import Path
from typing import Any

from platoon_harness.testing import ScriptedDriver

FILES = {
    "slug.py": '''def slug(text):
    """Text in lower case, with its words joined by hyphens."""
    return "-".join(text.lower().split())
''',
    "test_slug.py": """import unittest

from slug import slug


class SlugTest(unittest.TestCase):
    def test_its_words_are_lowered_and_joined_by_hyphens(self):
        self.assertEqual(slug("Hello  World"), "hello-world")
""",
}
"""What the author commits: the function the job asks for, and its test."""
JOB = "inbox/author@1"
"""The ref of the job, the first entry in the author's inbox."""
PATIENCE = 20 * 60
"""How many seconds the verifier waits for your answer: the 20 minutes its instructions say."""


def answer(result: Any) -> Any:
    """What one of our tools answered, from its MCP result."""
    return json.loads(result["content"][0]["text"])


def git(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=False)


def why(done: subprocess.CompletedProcess[str]) -> str:
    """The first line git said of a command that failed."""
    said = (done.stderr or done.stdout).strip()
    return said.splitlines()[0] if said else f"exit {done.returncode}"


class Author(ScriptedDriver):
    """Its turn writes slug.py and its test, commits both on its branch, adds a task to `to-reviewer` naming the commit
    and citing the job, and finishes citing the task. If its commit fails, it finishes saying so and adds no task."""

    async def _walk(self, steps: Any) -> str:
        cwd = self._spec.cwd
        for name, text in FILES.items():
            (cwd / name).write_text(text)
        await asyncio.to_thread(git, "add", *FILES, cwd=cwd)
        committed = await asyncio.to_thread(git, "commit", "-q", "-m", "Add slug and its test", cwd=cwd)
        if committed.returncode != 0:
            await self._call("agent_finish", {"gist": f"git commit failed: {why(committed)}"})
            return "stopped"
        sha = (await asyncio.to_thread(git, "rev-parse", "HEAD", cwd=cwd)).stdout.strip()
        task = {"queue": "to-reviewer", "gist": f"review {sha}", "based_on": [JOB]}
        added = answer(await self._call("task_add", task))["ref"]
        gist = "Committed slug.py and its test, and handed the commit to the reviewer."
        await self._call("agent_finish", {"gist": gist, "based_on": [added]})
        return "stopped"


class Reviewer(ScriptedDriver):
    """Its first turn claims the task on `to-reviewer`, and each reads the commit the task names through `git show` and
    `repo_commit`. A commit is recorded at the look after the turn that made it, which can come after this turn
    begins, so while `repo_commit` says it is not recorded yet, it waits a second for work on `to-reviewer` and asks
    again at its next turn. Once it has the commit's ref, it completes the task with its review citing the commit, adds
    a task to `to-verifier` naming the commit and citing it and the review, and finishes with its review."""

    task: dict[str, Any] | None = None

    async def _walk(self, steps: Any) -> str:
        if self.task is None:
            self.task = answer(await self._call("task_claim", {"queue": "to-reviewer"}))
        sha = self.task["gist"].removeprefix("review ")
        shown = await asyncio.to_thread(git, "show", "--name-only", "--format=", sha, cwd=self._spec.cwd)
        read = await self._call("repo_commit", {"sha": sha})
        if read.get("isError"):
            await self._call("wait", {"queue": ["to-reviewer"], "timeout": 1})
            return "stopped"
        commit = answer(read)["ref"]
        changed = shown.stdout.split()
        if sorted(changed) == sorted(FILES):
            review = "It adds slug.py and its test, as the job asks, and changes nothing else."
        else:
            review = f"It changes {', '.join(changed) or 'nothing'}, where the job asks for slug.py and its test."
        done = {"queue": "to-reviewer", "gist": review, "based_on": [commit]}
        reviewed = answer(await self._call("task_complete", done))["ref"]
        await self._call("task_add", {"queue": "to-verifier", "gist": f"verify {sha}", "based_on": [commit, reviewed]})
        await self._call("agent_finish", {"gist": review, "based_on": [reviewed]})
        return "stopped"


class Verifier(ScriptedDriver):
    """Its first turn claims the task on `to-verifier`, reads the commit it names through `repo_commit`, asks you to
    test it, citing it, and waits up to 20 minutes for your answer. Its next turn completes the task with a verdict that
    says what you answered, citing the commit, the task and your answer, and finishes with it, or with no answer from
    you fails the task saying so. It declares Codex's read-only sandbox, so the team's verifier runs on it as written,
    and runs no command, so it shows nothing of what that sandbox stops."""

    asked: tuple[str, list[str]] | None = None
    """The commit it asked you to test, and what it cites: that commit's ref and its task's."""

    async def _walk(self, steps: Any) -> str:
        if self.asked is None:
            task = answer(await self._call("task_claim", {"queue": "to-verifier"}))
            sha = task["gist"].removeprefix("verify ")
            commit = answer(await self._call("repo_commit", {"sha": sha}))["ref"]
            self.asked = sha, [commit, task["ref"]]
            ask = f"Please test {sha[:12]} with `repo test`, and answer me citing its record."
            await self._call("message_send", {"to": "@you", "gist": ask, "based_on": [commit]})
            if answer(await self._call("wait", {"from": ["@you"], "timeout": PATIENCE}))["state"] != "released":
                return "stopped"
        sha, cited = self.asked
        answers = answer(await self._call("message_read", {"sender": "you", "after": 0}))["entries"]
        if not answers:
            said = f"Not verified: nobody tested {sha[:12]}."
            await self._call("task_fail", {"queue": "to-verifier", "gist": said, "based_on": cited})
            await self._call("agent_finish", {"gist": said, "based_on": cited})
            return "stopped"
        verdict = f"Reviewed, and tested by you: {answers[-1]['gist']}"
        cited = [*cited, answers[-1]["ref"]]
        await self._call("task_complete", {"queue": "to-verifier", "gist": verdict, "based_on": cited})
        await self._call("agent_finish", {"gist": verdict, "based_on": cited})
        return "stopped"


def author() -> ScriptedDriver:
    return Author()


def reviewer() -> ScriptedDriver:
    return Reviewer()


def verifier() -> ScriptedDriver:
    declared = ScriptedDriver().describe().capabilities
    return Verifier(capabilities=declared.model_copy(update={"sandboxes": frozenset({"read-only"})}))
