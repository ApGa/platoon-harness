"""The README says what the design, STATUS and the examples say: its concepts are architecture section 2's nine words,
each milestone stands as STATUS says, and its Python is the example script's own lines."""

import re

from .support import ROOT

README = (ROOT / "README.md").read_text()
STATES = ("done", "in progress", "planned")


def section(text: str, heading: str) -> str:
    """The body of the `## heading` section of `text`."""
    return text.split(f"\n## {heading}\n", 1)[1].split("\n## ", 1)[0]


def first_table(text: str) -> list[str]:
    """The lines of the first table in `text`, its header and separator among them."""
    lines = text.splitlines()
    start = next(index for index, line in enumerate(lines) if line.startswith("|"))
    end = next((index for index, line in enumerate(lines[start:], start) if not line.startswith("|")), len(lines))
    return lines[start:end]


def milestones() -> dict[str, set[str]]:
    """Each milestone's number, and the state STATUS gives it, which its State cell starts with."""
    status = (ROOT / "docs" / "STATUS.md").read_text()
    states = {}
    for line in first_table(section(status, "Milestones"))[2:]:
        name, *_, state = (cell.strip() for cell in line.strip("|").split("|"))
        states[re.match(r"M(\d) ", name)[1]] = {next(word for word in STATES if state.startswith(word))}
    return states


def told() -> dict[str, set[str]]:
    """Each milestone the README's Status section names, and the states said of it before the sentence goes on."""
    states: dict[str, set[str]] = {}
    for sentence in re.split(r"(?<=\.) ", " ".join(section(README, "Status").split())):
        if sentence.startswith("Milestone"):
            head = re.split(r"[:.]", sentence)[0]
            for number in re.findall(r"\b\d\b", head):
                states.setdefault(number, set()).update(word for word in STATES if word in head)
    return states


def test_the_concepts_are_architecture_s_nine_words():
    words = first_table(section((ROOT / "docs" / "architecture.md").read_text(), "2. Vocabulary"))

    assert len(words) == 2 + 9
    assert first_table(section(README, "Concepts")) == words


def test_each_milestone_stands_as_status_says():
    assert len(milestones()) == 5
    assert told() == milestones()


def test_the_python_shown_is_the_example_script_s_own_lines():
    [block] = re.findall(r"^```python\n(.*?)^```$", README, re.MULTILINE | re.DOTALL)
    path, *lines = block.splitlines()
    script = ROOT / path.removeprefix("# ").removesuffix(" (abridged)")

    assert script == ROOT / "examples" / "sdk-script" / "run.py"
    assert [line for line in lines if line and line not in script.read_text().splitlines()] == []
