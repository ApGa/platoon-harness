"""The research is dated background: its index says so, and each note opens with its date, that it is not maintained and
that the compatibility reference is current."""

import re

from .support import ROOT, tracked

BANNER = re.compile(
    r"> Background research, dated \d{4}-\d{2}-\d{2}(?: to \d{4}-\d{2}-\d{2})? and not maintained: "
    r"\[reference/compatibility\.md\]\((?:\.\./)+reference/compatibility\.md\) is current\."
)


def test_the_research_index_says_it_is_dated_and_not_maintained():
    title = (ROOT / "docs" / "research" / "README.md").read_text().splitlines()[0]

    assert title == "# Background research (dated; not maintained; reference/compatibility.md is current)"


def test_each_research_note_opens_with_its_date_and_the_page_that_is_current():
    notes = [
        page for page in tracked("docs/research/*.md") if page.name != "README.md" and "fixtures" not in page.parts
    ]

    assert ROOT / "docs" / "research" / "spikes" / "real-harness.md" in notes
    assert [page.relative_to(ROOT) for page in notes if not BANNER.fullmatch(page.read_text().splitlines()[2])] == []
