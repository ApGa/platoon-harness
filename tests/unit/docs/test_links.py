"""Every relative link in the repository's Markdown names a file inside it, and every anchor a heading there."""

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).parents[3]
FENCE = re.compile(r"^\s*(```|~~~)")
CODE_SPAN = re.compile(r"`[^`]*`")
LINK = re.compile(r"\]\((?P<target>[^)\s]+)(?:\s+\"[^\"]*\")?\)")
HEADING = re.compile(r"^#{1,6}\s+(?P<title>.+?)\s*#*$")
HTML_ANCHOR = re.compile(r"<a (?:id|name)=\"(?P<anchor>[^\"]+)\"")
SCHEME = re.compile(r"^[a-z][a-z0-9+.-]*:")


def markdown() -> list[Path]:
    """Every Markdown file git tracks, or would track once added."""
    listed = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z", "--", "*.md"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return sorted({ROOT / name for name in listed.split("\0") if name and (ROOT / name).is_file()})


def prose(path: Path) -> list[tuple[int, str]]:
    """The lines outside fenced code, with their numbers."""
    lines, fenced = [], False
    for number, line in enumerate(path.read_text().splitlines(), 1):
        if FENCE.match(line):
            fenced = not fenced
        elif not fenced:
            lines.append((number, line))
    return lines


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


def broken(page: Path) -> list[str]:
    """Each relative link of `page` that names no file in the repository, or no heading in the page it names."""
    found = []
    for number, line in prose(page):
        for match in LINK.finditer(CODE_SPAN.sub("", line)):
            target = match["target"]
            if SCHEME.match(target):
                continue
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
    page.write_text("# 3. Laws\n## `platoon-harness session list`\n## [ADR 0006](x.md), again\n## Notes\n## Notes\n")

    assert anchors(page) == {"3-laws", "platoon-harness-session-list", "adr-0006-again", "notes", "notes-1"}


def test_every_relative_link_and_anchor_resolves():
    pages = markdown()

    assert ROOT / "README.md" in pages
    assert [line for page in pages for line in broken(page)] == []
