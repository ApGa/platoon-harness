"""Every relative link in the repository's Markdown names a file inside it, and every anchor a heading there, and the
docs' table of contents links every page."""

import re
from pathlib import Path

from .support import ROOT, prose, tracked

CODE_SPAN = re.compile(r"`[^`]*`")
LINK = re.compile(r"\]\((?P<target>[^)\s]+)(?:\s+\"[^\"]*\")?\)")
HEADING = re.compile(r"^#{1,6}\s+(?P<title>.+?)\s*#*$")
HTML_ANCHOR = re.compile(r"<a (?:id|name)=\"(?P<anchor>[^\"]+)\"")
SCHEME = re.compile(r"^[a-z][a-z0-9+.-]*:")
CONTENTS = ROOT / "docs" / "README.md"
INDEXED = ("docs/research/", "docs/rfcs/")
"""Folders with a README.md of their own, which the table of contents links in place of their pages."""


def slug(title: str) -> str:
    """The anchor GitHub gives a heading."""
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", title).replace("`", "")
    return re.sub(r"[^\w\- ]", "", text.strip().lower()).replace(" ", "-")


def anchors(path: Path) -> set[str]:
    """One per heading, a repeated one numbered as GitHub numbers it, and each `<a id>`."""
    found: set[str] = set()
    seen: dict[str, int] = {}
    for _, line in prose(path):
        found.update(match["anchor"] for match in HTML_ANCHOR.finditer(line))
        if heading := HEADING.match(line):
            name = slug(heading["title"])
            found.add(f"{name}-{seen[name]}" if name in seen else name)
            seen[name] = seen.get(name, 0) + 1
    return found


def links(page: Path) -> list[tuple[int, str]]:
    """Each relative link of `page`, with its line's number."""
    return [
        (number, match["target"])
        for number, line in prose(page)
        for match in LINK.finditer(CODE_SPAN.sub("", line))
        if not SCHEME.match(match["target"])
    ]


def broken(page: Path) -> list[str]:
    """Each relative link of `page` that names no file in the repository, or no heading in the page it names."""
    found = []
    for number, target in links(page):
        path_text, _, anchor = target.partition("#")
        path = (page.parent / path_text).resolve() if path_text else page
        where = f"{page.relative_to(ROOT)}:{number}: {target}"
        if not path.is_relative_to(ROOT):
            found.append(f"{where} (outside the repository)")
        elif not path.exists():
            found.append(f"{where} (no such file)")
        elif anchor and path.suffix == ".md" and anchor not in anchors(path):
            found.append(f"{where} (no such heading)")
    return found


def test_github_s_anchors_are_derived_from_headings(tmp_path):
    page = tmp_path / "page.md"
    page.write_text("# 3. Laws\n## `platoon-harness session list`\n## [RFC 0006](x.md), again\n## Notes\n## Notes\n")

    assert anchors(page) == {"3-laws", "platoon-harness-session-list", "rfc-0006-again", "notes", "notes-1"}


def test_every_relative_link_and_anchor_resolves():
    pages = tracked("*.md")

    assert ROOT / "README.md" in pages
    assert [line for page in pages for line in broken(page)] == []


def test_the_table_of_contents_links_every_page_and_the_readme_of_each_indexed_folder():
    """docs/README.md links every page under docs/ but those of research/ and rfcs/, and their README.md instead."""
    linked = {(CONTENTS.parent / target.partition("#")[0]).resolve() for _, target in links(CONTENTS)}
    pages = {page for page in tracked("docs/*.md") if not str(page.relative_to(ROOT)).startswith(INDEXED)}
    pages |= {ROOT / folder / "README.md" for folder in INDEXED}

    assert ROOT / "docs" / "architecture.md" in pages
    assert sorted(str(page.relative_to(ROOT)) for page in pages - linked - {CONTENTS}) == []
