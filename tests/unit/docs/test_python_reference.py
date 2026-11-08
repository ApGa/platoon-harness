"""The Python API reference, `docs/reference/python.md`, is made from `tests/public_api.txt` and the docstrings, and
marks each module and name that a row of STATUS on the SDK calls experimental."""

import re
from collections.abc import Iterator
from pathlib import Path

import pytest

from platoon_harness_cli.reference import EXPERIMENTAL, python_reference

from .support import ROOT, headings

PAGE = ROOT / "docs" / "reference" / "python.md"
LISTED = ROOT / "tests" / "public_api.txt"
STATUS = ROOT / "docs" / "STATUS.md"
PROMISED = (
    "each name `tests/public_api.txt` lists, and each attribute and method without a leading underscore that a class "
    "it lists defines"
)
"""What the public API is, by default, pending the owner's ruling."""
MARK = re.compile(
    r"^#{2,3} `(?P<name>[\w.]+)`\n\n\*\*Experimental\.\*\* \[STATUS\]\(\.\./STATUS\.md\): (?P<lead>.+)\.$", re.MULTILINE
)
"""A module's or a name's heading, and the mark under it, quoting the start of a row of STATUS."""


def rows(status: str) -> Iterator[tuple[str, str, str]]:
    """Each row of STATUS's capabilities: the heading it is under, its capability and its state."""
    heading = ""
    for line in status.partition("\n## Capabilities\n")[2].splitlines():
        if line.startswith("### "):
            heading = line
        elif line.startswith("| ") and not line.startswith(("| Capability |", "|---")):
            capability, state = (cell.strip() for cell in re.split(r"(?<!\\)\|", line)[1:3])
            yield heading, capability, state


def experimental(status: str) -> set[str]:
    """The start of each row under a heading that names a module of the SDK, up to the first colon of its capability,
    whose state or capability says experimental."""
    return {
        capability.partition(": ")[0]
        for heading, capability, state in rows(status)
        if re.search(r"`platoon_harness[`.]", heading) and "experimental" in f"{capability} {state}"
    }


def test_the_python_reference_is_made_again_from_the_public_names():
    """On a failure, run `uv run python -m platoon_harness_cli.reference python > docs/reference/python.md`. Each name
    the list holds has a heading of its own, or is a member of one that has."""
    page = PAGE.read_text()
    headings = set(re.findall(r"^### `([\w.]+)`$", page, re.MULTILINE))
    names = {line.partition("(")[0].partition("[")[0] for line in LISTED.read_text().split()}
    owners = {name: {name, name.rsplit(".", 1)[0], name.rsplit(".", 2)[0]} for name in names}

    assert page == python_reference(ROOT)
    assert sorted(name for name, owned in owners.items() if not owned & headings) == []


def test_a_class_is_shown_with_each_attribute_whose_name_has_no_leading_underscore():
    """`Kernel.runtime`, assigned with no annotation, which a scenario submits as, is shown, and no attribute whose name
    has a leading underscore is, such as `View._folds`."""
    stubs = re.findall(r"^```python\n(class .*?)^```$", PAGE.read_text(), re.MULTILINE | re.DOTALL)
    kernel = next(stub for stub in stubs if stub.startswith("class Kernel:"))

    assert '    runtime = Principal(id="runtime")\n' in kernel
    assert [line for stub in stubs for line in stub.splitlines() if line.startswith("    _")] == []


def test_each_link_within_the_page_lands_on_the_heading_it_names():
    """GitHub numbers a repeated anchor by the headings before it, so `platoon_harness.Session`, whose heading comes
    before its module's, `platoon_harness.session`, takes the anchor without a number, and a link to the module takes
    the one with."""
    landing = headings(PAGE)
    linked = re.findall(r"\[(`[\w.]+`)\]\(#([\w-]+)\)", PAGE.read_text())

    assert ("`platoon_harness.session`", "platoon_harnesssession-1") in linked
    assert [(text, anchor, landing.get(anchor)) for text, anchor in linked if landing.get(anchor) != text] == []


def test_each_page_that_says_what_0_1_0_promises_says_it_in_the_same_words():
    """The page, the extending index, the tutorial, CHANGELOG and STATUS each say what the public API is in one set of
    words, so none promises more or less than another while the owner's ruling is pending."""
    pages = [PAGE, *(ROOT / "docs" / "extending" / name for name in ("index.md", "extensions.md"))]
    pages += [ROOT / "CHANGELOG.md", STATUS]

    assert [page.name for page in pages if PROMISED not in " ".join(page.read_text().split())] == []


def test_every_module_status_calls_experimental_is_marked_so():
    """Each row of STATUS on the SDK that calls its capability experimental, by its state or in its own words, is quoted
    by the mark of a module or a name, and each mark quotes one: the drivers it calls so, `bwrap` and isolation among
    them."""
    marked = {match["name"]: match["lead"] for match in MARK.finditer(PAGE.read_text())}

    assert set(marked.values()) == experimental(STATUS.read_text())
    assert {
        "platoon_harness.bwrap",
        "platoon_harness.drivers.claude",
        "platoon_harness.drivers.codex",
        "platoon_harness.drivers.openhands",
        "platoon_harness.drivers.pi",
        "platoon_harness.runtime.isolation",
    } <= set(marked)


@pytest.mark.parametrize(
    ("change", "said"),
    [
        ("no longer", "STATUS no longer calls these experimental"),
        ("newly", "and EXPERIMENTAL marks none"),
    ],
)
def test_a_row_status_and_the_marks_disagree_on_stops_the_reference_being_made(tmp_path: Path, change: str, said: str):
    """A row a mark quotes that STATUS no longer calls experimental, or one STATUS calls so that no mark quotes, is
    refused, saying which, rather than the page leaving a mark out or keeping one STATUS dropped."""
    status = STATUS.read_text()
    if change == "no longer":
        lead = re.escape(EXPERIMENTAL["platoon_harness.bwrap"])
        changed = re.sub(rf"^(\| {lead}[^|]*\| )experimental \|", r"\1tested |", status, count=1, flags=re.MULTILINE)
    else:
        top, kernel, rest = status.partition("\n### Kernel")
        added = "|---|---|---|\n| A capability no mark quotes | experimental | None |\n"
        changed = top + kernel + rest.replace("|---|---|---|\n", added, 1)
    (tmp_path / "tests").mkdir()
    (tmp_path / "docs").mkdir()
    (tmp_path / "tests" / "public_api.txt").write_text(LISTED.read_text())
    (tmp_path / "docs" / "STATUS.md").write_text(changed)

    with pytest.raises(ValueError, match=said):
        python_reference(tmp_path)
    assert changed != status
