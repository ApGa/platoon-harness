"""The public pages say what platoon-harness does, not how its making was run: no ruling or whose it was, no run's
number, no milestone of the project and no host. An RFC's own rollout milestones, as in `Implements RFC NNNN, milestone
M2`, and the runtime's owner, whose stop ends a session's turns, are not this, and neither are the RFCs, which keep
their rollout plans."""

import re

from .support import ROOT, tracked

PHRASES = (
    r"\bowner's ruling",
    r"\bpending the owner",
    r"\bawaiting the owner",
    r"\bthe owner (?:asked|chose|ruled|wants|decided)\b",
    r"\b(?:live |CI )?run #?[0-9]+\b(?!\s*(?:ms|s|seconds|minutes|times)\b)",
    r"\bruns [0-9]+ (?:to|and) [0-9]+",
    r"\blogin node",
    r"\bcompute node",
    r"\bkept outside this repository",
    r"\bmilestone [0-9]",
    r"\bat M[0-9]\b",
)
"""Phrases of how the work was run: a ruling or a person's wish as a reason, a run by its number, a milestone of the
project, or a machine it ran on. A space matches any run of white space, a line's end among it."""
PROCESS = re.compile("|".join(phrase.replace(" ", r"\s+") for phrase in PHRASES), re.IGNORECASE)


def test_no_public_page_says_how_its_making_was_run():
    pages = [page for page in tracked("*.md") if not page.is_relative_to(ROOT / "docs" / "rfcs")]
    found = [
        f"{page.relative_to(ROOT)}:{text.count(chr(10), 0, match.start()) + 1}: {' '.join(match[0].split())}"
        for page in pages
        for text in [page.read_text()]
        for match in PROCESS.finditer(text)
    ]

    assert {ROOT / "README.md", ROOT / "docs" / "STATUS.md"} <= set(pages) and found == []
