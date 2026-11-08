"""What FakeModel says as each agent of an example, so the example runs on its real harnesses with only the model
scripted. An example's roles share one endpoint, so each agent is played by a script of its own, picked by the name its
preamble gives it. A play is a generator that is handed the agent's first request, yields each reply and is sent the
request that comes after it, so a later reply can rest on what a tool answered, as a model's does."""

import json
import re
import subprocess
from collections.abc import Callable, Generator, Mapping
from pathlib import Path
from typing import Any

from platoon_harness.testing import FakeModel, Request, ToolCall

from .cli import ROOT

type Reply = str | ToolCall
type Play = Callable[[Request], Generator[Reply, Request]]

MODEL = "fake-model"
"""The model each role names on FakeModel, in place of the MODEL its example's page shows."""
OFFLINE = 'auth.provider.env = ["OPENAI_BASE_URL", "OPENAI_API_KEY", "PI_OFFLINE"]'
"""The one line a run on FakeModel adds to an example's team, so pi starts with no network, as tests reach none."""
SAMPLE = ROOT / "examples" / "sample-project"


def provider(model: FakeModel, home: Path) -> dict[str, str]:
    """The environment of a run on FakeModel: its endpoint and a dummy key, which `OFFLINE` hands on with pi's switch
    for no network, and a home of the run's own, whose git config names who commits, as an agent's git reads only the
    home's."""
    home.mkdir(parents=True, exist_ok=True)
    (home / ".gitconfig").write_text(
        "[user]\n\tname = Tester\n\temail = tester@example.invalid\n[init]\n\tdefaultBranch = main\n"
    )
    url = f"{model.url}/v1"
    return {"OPENAI_BASE_URL": url, "OPENAI_API_KEY": "dummy-key", "PI_OFFLINE": "yes", "HOME": str(home)}


def on_fake_model(command: str) -> str:
    """A command as a page shows it, with the model each role names on FakeModel, and `OFFLINE` beside its settings."""
    return f"{command.replace('MODEL', MODEL)} --set '{OFFLINE}'"


def copied(commands: list[str], folder: Path, env: Mapping[str, str]) -> Path:
    """The sample project, copied into `folder` by the `cp`, `cd` and `git` commands a page shows, and the copy they
    work in."""
    copying = [command for command in commands if command.split()[0] in ("cp", "cd", "git")]
    script = "\n".join(["set -e", *copying, "pwd"]).replace("path/to/platoon-harness", str(ROOT))
    done = subprocess.run(["bash", "-c", script], cwd=folder, env=env, capture_output=True, text=True, check=True)
    return Path(done.stdout.strip())


def you_are(agent: str) -> str:
    """What the preamble tells only `agent`, which its every request carries."""
    return f"You are @{agent}."


def cast(model: FakeModel, **plays: Play) -> None:
    """Each agent named played on `model` by its play: its replies in order, and past their end `done`."""
    for agent, play in plays.items():
        model.answer(you_are(agent), _stepping(play))


def _stepping(play: Play) -> Callable[[Request], Reply]:
    running: Generator[Reply, Request] | None = None

    def reply(request: Request) -> Reply:
        nonlocal running
        try:
            if running is None:
                running = play(request)
                return next(running)
            return running.send(request)
        except StopIteration:
            return "done"

    return reply


def said(request: Request) -> str:
    """What the last message of a request says: what a tool answered, or what reached the agent."""
    content = request.json["messages"][-1]["content"]
    return content if isinstance(content, str) else "\n".join(part.get("text", "") for part in content)


def answered(request: Request) -> Any:
    """What our tool answered, as the last message of a request carries it, or None if it was refused."""
    text = said(request)
    start = text.find("{")
    if start < 0 or "Refused" in text[:start]:
        return None
    return json.JSONDecoder().raw_decode(text[start:])[0]


def pi(tool: str, **arguments: Any) -> ToolCall:
    """A call of our tool as pi shows it to its model."""
    return ToolCall(f"mcp__ph__{tool}", arguments)


def openhands(tool: str, **arguments: Any) -> ToolCall:
    """A call of our tool as OpenHands shows it to its model."""
    return ToolCall(tool, arguments)


def bash(command: str) -> ToolCall:
    """A command in pi's shell."""
    return ToolCall("bash", {"command": command})


def terminal(command: str) -> ToolCall:
    """A command in OpenHands' terminal."""
    return ToolCall("terminal", {"command": command})


def patched(path: str, old: str, new: str) -> str:
    """A shell command that replaces `old` in a file with `new`, once, and fails if `old` is not there. Each command
    here is one line, as OpenHands' terminal runs one command at a time, and several only joined by `&&` or `;`."""
    script = f"p = Path({path!r}); t = p.read_text(); assert {old!r} in t; p.write_text(t.replace({old!r}, {new!r}, 1))"
    return f"python3 -c {_quoted(f'from pathlib import Path; {script}')}"


def appended(path: str, text: str) -> str:
    """A shell command that adds `text` at the end of a file."""
    script = f"p = Path({path!r}); p.write_text(p.read_text() + {text!r})"
    return f"python3 -c {_quoted(f'from pathlib import Path; {script}')}"


def _quoted(text: str) -> str:
    return "'" + text.replace("'", "'\"'\"'") + "'"


def sha_in(text: str) -> str:
    """The first full commit SHA a text holds."""
    found = re.search(r"(?<![0-9a-f])[0-9a-f]{40}(?![0-9a-f])", text)
    assert found is not None, text
    return found[0]


# The mixed team: a pi lead and an OpenHands worker, `fixer`, on issue 1 of the sample project.

FIX_ONE = " && ".join(
    [
        patched("tally/money.py", "int(cents or 0)", 'int(cents.ljust(2, "0"))'),
        appended(
            "tests/test_money.py",
            "\n\nclass OneDigitOfCentsTest(unittest.TestCase):\n"
            "    def test_one_digit_of_cents_is_tens_of_cents(self):\n"
            '        self.assertEqual(parse_amount("12.5"), 1250)\n'
            '        self.assertEqual(parse_amount("0.5"), 50)\n',
        ),
        "python3 -m unittest",
    ]
)
"""What the worker runs: the fix of issue 1, a test that fails without it, and the tests."""
NOTE = "board/notes/fix-1@1"
FIXED = "parse_amount reads one digit of cents as tens of cents; a test holds 12.5 and 0.5, and the tests pass."
SUMMARY = "Issue 1 is fixed: one digit of cents is now read as tens of cents, with a test, as the note says."


def mixed_lead(request: Request) -> Generator[Reply, Request]:
    """The lead reads the issues, adds the task citing the job and starts `fixer`, then once it reports, reads its note
    and the code, and finishes citing the note."""
    yield ToolCall("read", {"path": "ISSUES.md"})
    yield pi("task_add", queue="tasks", gist="Fix issue 1: one digit of cents is read wrong", based_on=["inbox/lead@1"])
    yield pi("agent_spawn", name="fixer", child_role="worker", goal="Take the task on the queue `tasks`.")
    yield "The task is on the queue, and fixer has it."
    yield pi("board_get", board="notes", name="fix-1")
    yield ToolCall("read", {"path": "tally/money.py"})
    yield pi("agent_finish", gist=SUMMARY, based_on=[NOTE])


def mixed_worker(request: Request) -> Generator[Reply, Request]:
    """The worker claims the task, fixes the bug with a test, runs the tests, notes what it did citing the task, and
    completes the task and finishes citing the note."""
    yield openhands("task_claim", queue="tasks")
    yield terminal(FIX_ONE)
    yield openhands("board_post", board="notes", name="fix-1", gist=FIXED, based_on=["task/tasks/1@1"])
    yield openhands("task_complete", queue="tasks", gist=FIXED, based_on=[NOTE])
    yield openhands("agent_finish", gist=FIXED, based_on=[NOTE])


MIXED = {"lead": mixed_lead, "fixer": mixed_worker}
"""Who plays each agent of the mixed team."""


# The SDK script: two OpenHands agents, each fixing one issue in a worktree of its own.

FIX_THREE = " && ".join(
    [
        patched(
            "tally/ledger.py",
            "in csv.reader(lines)]",
            'in csv.reader(line for line in lines if line.strip() and not line.startswith("#"))]',
        ),
        appended(
            "tests/test_ledger.py",
            "\n\nclass BlankLinesAndCommentsTest(unittest.TestCase):\n"
            "    def test_they_are_skipped(self):\n"
            '        lines = ["# a trip\\n", "\\n", "ada,12.00,ada bob\\n"]\n'
            '        self.assertEqual(read_expenses(lines), [Expense("ada", 1200, ("ada", "bob"))])\n',
        ),
        "python3 -m unittest",
    ]
)
"""What fixes issue 3: blank lines and comments skipped, a test that fails without it, and the tests."""
COMMITTED = "git add -A && git commit -qm"
CENTS = "Fixed issue 1: parse_amount reads one digit of cents as tens of cents, with a test, and committed it."
COMMENTS = "Fixed issue 3: read_expenses skips blank lines and comments, with a test, and committed it."


def fixing(fix: str, subject: str, report: str) -> Play:
    """An agent that fixes an issue with a test, runs the tests, commits on its branch and finishes saying so."""

    def play(request: Request) -> Generator[Reply, Request]:
        yield terminal(fix)
        yield terminal(f"{COMMITTED} {_quoted(subject)}")
        yield openhands("agent_finish", gist=report)

    return play


SCRIPT = {
    "cents": fixing(FIX_ONE, "Read one digit of cents as tens of cents", CENTS),
    "comments": fixing(FIX_THREE, "Skip blank lines and comments in an expenses file", COMMENTS),
}
"""Who plays each agent of the SDK script."""


# The worktree team: a pi lead, OpenHands workers `ada` and `bob`, and a pi merger, through the queue `merges`.

WORKERS = ("ada", "bob")
ENDED = "Both workers have ended: each one's report says what came of its branch."


def noted(line: str) -> str:
    """A shell command that adds a line at the top of the list under `## Unreleased` in CHANGELOG.md."""
    return patched("CHANGELOG.md", "## Unreleased\n\n", f"## Unreleased\n\n- {line}\n\n")


def queue_lead(request: Request) -> Generator[Reply, Request]:
    """The lead starts `ada` on issue 1 and `bob` on issue 3, waits until both have ended, and finishes saying so."""
    yield pi("agent_spawn", name="ada", child_role="worker", goal="Fix issue 1 in ISSUES.md.")
    yield pi("agent_spawn", name="bob", child_role="worker", goal="Fix issue 3 in ISSUES.md.")
    while answered((yield pi("wait", agents=list(WORKERS))))["state"] != "released":
        yield "Waiting for both workers."
    yield pi("agent_finish", gist=ENDED)


def queue_worker(fix: str, line: str, subject: str) -> Play:
    """A worker that fixes its issue with a test, notes it in the changelog, commits on its branch, hands the branch to
    the merger and waits on its task, then finishes with the task's result."""

    def play(request: Request) -> Generator[Reply, Request]:
        yield terminal(" && ".join([fix, noted(line), f"{COMMITTED} {_quoted(subject)}"]))
        branch = re.search(r"platoon-harness/\S+", said((yield terminal("git branch --show-current"))))
        assert branch is not None
        task = answered((yield openhands("task_add", queue="merges", gist=f"merge {branch[0]}")))["task"]
        while answered((yield openhands("wait", tasks=[f"merges/{task}"])))["state"] != "released":
            yield "Waiting for the merger."
        tasks = answered((yield openhands("task_list", queue="merges")))["tasks"]
        yield openhands("agent_finish", gist=next(entry["result"] for entry in tasks if entry["id"] == task))

    return play


def merger(request: Request) -> Generator[Reply, Request]:
    """The merger claims each task on `merges` and merges the branch it names with git, completing the task with what
    came of it, a conflict naming its paths and left for a person to see, and waits for work when the queue is
    empty."""
    while True:
        claimed = answered((yield pi("task_claim", queue="merges")))
        if claimed is None:
            if answered((yield pi("wait", queue=["merges"])))["state"] == "parked":
                yield "Waiting for work on the queue."
            continue
        branch = claimed["gist"].removeprefix("merge ")
        if "CONFLICT" in said((yield bash(f"git merge --no-ff --no-edit {branch}"))):
            paths = said((yield bash("git diff --name-only --diff-filter=U"))).split()
            gist = f"conflict in {', '.join(paths)}: rebase {branch} onto mine and add it again"
        else:
            gist = f"merged {branch}"
        yield pi("task_complete", queue="merges", gist=gist)


QUEUE = {
    "lead": queue_lead,
    "ada": queue_worker(FIX_ONE, "`12.5` is read as 12.50.", "Read one digit of cents as tens of cents"),
    "bob": queue_worker(FIX_THREE, "Blank lines and comments are skipped.", "Skip blank lines and comments"),
    "merger": merger,
}
"""Who plays each agent of the worktree team."""


# The review team: an OpenHands author, a pi reviewer in a snapshot, and a pi verifier whose commands are refused.

FIX_TWO = " && ".join(
    [
        patched(
            "tally/ledger.py",
            "        share = expense.amount // len(expense.among)\n"
            "        for person in expense.among:\n"
            "            owed[person] = owed.get(person, 0) - share\n",
            "        share, left = divmod(expense.amount, len(expense.among))\n"
            "        for place, person in enumerate(expense.among):\n"
            "            owed[person] = owed.get(person, 0) - share - (place < left)\n",
        ),
        appended(
            "tests/test_ledger.py",
            "\n\nclass UnevenSplitTest(unittest.TestCase):\n"
            "    def test_the_cents_left_over_go_to_the_first_people_listed(self):\n"
            '        owed = balances([Expense("ada", 1000, ("ada", "bob", "cy"))])\n'
            '        self.assertEqual(owed, {"ada": 666, "bob": -333, "cy": -333})\n',
        ),
        "python3 -m unittest",
    ]
)
"""What fixes issue 2: the cents left over go one each to the first people listed, with a test, and the tests."""
HANDED = "Committed the fix of issue 2 and its test, and handed the commit to the reviewer."
REVIEW = "It gives the cents left over to the first people listed, with a test of it, and changes nothing else."
ASKING = "Please test {sha} with `repo test`, and answer me citing its record."


def author(request: Request) -> Generator[Reply, Request]:
    """The author fixes issue 2 with a test and commits both, hands the commit to the reviewer by its SHA citing the
    job, and finishes citing that task."""
    yield terminal(f"{FIX_TWO} && {COMMITTED} 'Split the cents left over among the first people listed'")
    commit = sha_in(said((yield terminal("git rev-parse HEAD"))))
    task = yield openhands("task_add", queue="to-reviewer", gist=f"review {commit}", based_on=["inbox/author@1"])
    yield openhands("agent_finish", gist=HANDED, based_on=[answered(task)["ref"]])


def reviewer(request: Request) -> Generator[Reply, Request]:
    """The reviewer claims the task, reads the commit with git and through `repo_commit`, waiting a second and asking
    again while the commit is not recorded yet, completes the task with its review citing the commit, and hands it on
    to the verifier citing the commit and the review."""
    sha = answered((yield pi("task_claim", queue="to-reviewer")))["gist"].removeprefix("review ")
    yield bash(f"git show --stat {sha}")
    while (commit := answered((yield pi("repo_commit", sha=sha)))) is None:
        if answered((yield pi("wait", queue=["to-reviewer"], timeout=1)))["state"] == "parked":
            yield "Waiting for the commit to be recorded."
    review = answered((yield pi("task_complete", queue="to-reviewer", gist=REVIEW, based_on=[commit["ref"]])))
    yield pi("task_add", queue="to-verifier", gist=f"verify {sha}", based_on=[commit["ref"], review["ref"]])
    yield pi("agent_finish", gist=REVIEW, based_on=[review["ref"]])


def verifier(request: Request) -> Generator[Reply, Request]:
    """The verifier claims the task, reads the commit through `repo_commit`, asks you to test it and waits for your
    answer, then completes the task with a verdict that says what you answered, citing the commit, the task and your
    answer, and finishes with it."""
    task = answered((yield pi("task_claim", queue="to-verifier")))
    sha = task["gist"].removeprefix("verify ")
    commit = answered((yield pi("repo_commit", sha=sha)))["ref"]
    yield pi("message_send", to="@you", gist=ASKING.format(sha=sha[:12]), based_on=[commit])
    if answered((yield ToolCall("mcp__ph__wait", {"from": ["@you"], "timeout": 1200})))["state"] == "parked":
        yield "Waiting for your test."
    answer = answered((yield pi("message_read", sender="you", after=0)))["entries"][-1]
    cited = [commit, task["ref"], answer["ref"]]
    verdict = f"Reviewed, and tested by you: {answer['gist']}"
    yield pi("task_complete", queue="to-verifier", gist=verdict, based_on=cited)
    yield pi("agent_finish", gist=verdict, based_on=cited)


REVIEWING = {"author": author, "reviewer": reviewer, "verifier": verifier}
"""Who plays each agent of the review team."""


# The GitSwarm population: four pi workers in worktrees, on issue 4, run by its script.

FIX_FOUR = " && ".join(
    [
        patched("tally/__main__.py", "import argparse\n", "import argparse\nimport json\n"),
        patched(
            "tally/__main__.py",
            "    arguments = parser.parse_args(argv)\n",
            '    parser.add_argument("--json", action="store_true", help="print the payments as JSON")\n'
            "    arguments = parser.parse_args(argv)\n",
        ),
        patched(
            "tally/__main__.py",
            "    for payer, payee, cents in payments:\n",
            "    if arguments.json:\n"
            '        print(json.dumps([{"from": p, "to": q, "amount": format_amount(c)} for p, q, c in payments]))\n'
            "        return 0\n"
            "    for payer, payee, cents in payments:\n",
        ),
    ]
)
"""What adds `--json`, with no test."""
TEST_FOUR = appended(
    "tests/test_cli.py",
    "\n\nclass JsonTest(unittest.TestCase):\n"
    "    def test_it_prints_the_payments_as_json(self):\n"
    "        import json\n\n"
    "        with tempfile.TemporaryDirectory() as folder:\n"
    '            expenses = Path(folder, "trip.csv")\n'
    '            expenses.write_text("ada,30.00,ada bob cy\\n")\n'
    "            printed = io.StringIO()\n"
    "            with contextlib.redirect_stdout(printed):\n"
    '                self.assertEqual(main(["--json", str(expenses)]), 0)\n'
    '        paid = [{"from": name, "to": "ada", "amount": "10.00"} for name in ("bob", "cy")]\n'
    "        self.assertEqual(json.loads(printed.getvalue()), paid)\n",
)
"""What tests `--json`."""
CONTRIBUTED = "Committed --json, with no test yet."
BUILT = "Committed a test of --json on worker-1's commit."
NOMINATED = "Nominated worker-2's commit, which does all the goal asks."
ABSTAINED = "Nothing to add: worker-3 nominated a commit that does all the goal asks."


def outcome_of(peer: str) -> Generator[Reply, Request, dict[str, Any]]:
    """A peer's entry on `outcomes`, once the program has recorded it, waiting for it if it is not there yet."""
    while answered((yield pi("wait", board=[f"outcomes/{peer}"], after=0)))["state"] != "released":
        yield f"Waiting for {peer}'s outcome."
    return answered((yield pi("board_get", board="outcomes", name=peer)))


def contributes(request: Request) -> Generator[Reply, Request]:
    """worker-1 commits `--json` with no test."""
    yield bash(f"{FIX_FOUR} && {COMMITTED} 'Add --json'")
    yield pi("agent_finish", gist=CONTRIBUTED)


def builds_on(request: Request) -> Generator[Reply, Request]:
    """worker-2 checks out worker-1's commit on its own branch by the SHA its outcome records, and commits a test on
    it."""
    entry = yield from outcome_of("worker-1")
    yield bash(f"git reset -q --hard {entry['fields']['sha']} && {TEST_FOUR} && {COMMITTED} 'Test --json'")
    yield pi("agent_finish", gist=BUILT, based_on=[entry["ref"]])


def nominates(request: Request) -> Generator[Reply, Request]:
    """worker-3 nominates worker-2's commit by the ref `repo_commit` gives for the SHA its outcome records."""
    entry = yield from outcome_of("worker-2")
    made = answered((yield pi("repo_commit", sha=entry["fields"]["sha"])))
    yield pi("message_send", to="#nominations", gist="--json and its test", based_on=[made["ref"]])
    yield pi("agent_finish", gist=NOMINATED, based_on=[made["ref"]])


def abstains(request: Request) -> Generator[Reply, Request]:
    """worker-4 abstains once worker-3's nomination is recorded."""
    entry = yield from outcome_of("worker-3")
    yield pi("agent_finish", gist=ABSTAINED, based_on=[entry["ref"]])


SWARM = {"worker-1": contributes, "worker-2": builds_on, "worker-3": nominates, "worker-4": abstains}
"""Who plays each worker of the population."""
