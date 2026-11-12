"""The front pages say what the design and the examples say: the concepts page's nine words are architecture section
2's, and the README's Python is the example script's own lines."""

import re

from .support import ROOT

README = (ROOT / "README.md").read_text()


def section(text: str, heading: str) -> str:
    """The body of the `## heading` section of `text`."""
    return text.split(f"\n## {heading}\n", 1)[1].split("\n## ", 1)[0]


def first_table(text: str) -> list[str]:
    """The lines of the first table in `text`, its header and separator among them."""
    lines = text.splitlines()
    start = next(index for index, line in enumerate(lines) if line.startswith("|"))
    end = next((index for index, line in enumerate(lines[start:], start) if not line.startswith("|")), len(lines))
    return lines[start:end]


def test_the_concepts_are_architecture_s_nine_words():
    words = first_table(section((ROOT / "docs" / "architecture.md").read_text(), "2. Vocabulary"))
    concepts = (ROOT / "docs" / "getting-started" / "concepts.md").read_text()

    assert len(words) == 2 + 9
    assert first_table(section(concepts, "The nine words")) == words


def test_the_python_shown_is_the_example_script_s_own_lines():
    [block] = re.findall(r"^```python\n(.*?)^```$", README, re.MULTILINE | re.DOTALL)
    path, *lines = block.splitlines()
    script = ROOT / path.removeprefix("# ").removesuffix(" (abridged)")

    assert script == ROOT / "examples" / "sdk-script" / "run.py"
    assert [line for line in lines if line and line not in script.read_text().splitlines()] == []
