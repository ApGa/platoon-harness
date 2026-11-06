"""The RFCs: the index lists each with the title and status it gives itself, each holds the sections the index names,
every RFC the repository cites exists, and the name they had before is gone but for the sentence that tells it."""

import re
from pathlib import Path

from .support import ROOT, prose, tracked

RFCS = ROOT / "docs" / "rfcs"
INDEX = RFCS / "README.md"
STATUSES = ("Draft", "Accepted", "Implemented", "Rejected", "Deferred")
ROW = re.compile(r"^\| \[(?P<number>\d{4})\]\((?P<link>[^)]+)\) \| (?P<title>.+?) \| (?P<status>[^|]+?) \|$", re.M)
FILE_NAME = re.compile(r"^\d{4}-[a-z0-9]+(?:-[a-z0-9]+)*\.md$")
CITATION = re.compile(
    r"(?<!Platoon\s)(?<!IETF\s)\bRFCs?\s+"
    r"(?P<numbers>\d{4}\b(?:(?:,\s*|,?\s+(?:and|or|to)\s+)\d{4}\b)*)"
)
"""`RFC NNNN`, or `RFCs` and a list or range, across line breaks, but Platoon's own RFCs and the IETF's."""
NOT_CITING = {"docs/spec/BRIEF.md": "verbatim brief; the RFCs it names are Platoon's"}
OLD_NAME = re.compile(r"\badrs?\b|docs/adr", re.IGNORECASE)
PINNED = re.compile(r"platoon-harness@[0-9a-f]{7,40}:docs/adr/")
"""A line-numbered citation in a dated note, read at the commit it names, before the records moved."""
HISTORY = (
    "Until 2026-11-07, RFCs 0001 to 0060 were architecture decision records in `docs/adr`; earlier commits and other "
    "repositories cite them as ADR NNNN, under the same numbers."
)
NAMING_IT = {"tests/unit/docs/test_rfcs.py": "it names the old name to look for it"}


def rfcs() -> dict[str, Path]:
    """Every RFC by number."""
    files = sorted(path for path in RFCS.glob("*.md") if path != INDEX)
    numbers = [path.name[:4] for path in files]
    assert files, "docs/rfcs holds no RFC"
    assert len(numbers) == len(set(numbers)), f"two RFCs share a number: {numbers}"
    return dict(zip(numbers, files, strict=True))


def title_and_status(path: Path) -> tuple[str, str]:
    """The title from `# RFC NNNN: Title`, and the status from the Status row of the status table, on one line."""
    text = path.read_text()
    title = re.fullmatch(rf"# RFC {path.name[:4]}: (.+)", text.splitlines()[0])
    assert title, f"{path.name} must start with '# RFC {path.name[:4]}: <title>'"
    status = re.search(r"^\| Status \| (.+?) \|$", text, re.M)
    assert status, f"{path.name} gives no status"
    return title[1], status[1]


def text_of(path: Path) -> str | None:
    """A file's text, or None for a binary one, which git tells by a NUL byte."""
    data = path.read_bytes()
    return None if b"\0" in data[:8000] else data.decode()


def texts(exempt: dict[str, str]) -> list[tuple[str, str]]:
    """Every text file the repository tracks but those exempt, by name, with what it holds."""
    assert all((ROOT / name).is_file() for name in exempt), f"an exemption names no file: {exempt}"
    found = [(str(path.relative_to(ROOT)), text_of(path)) for path in tracked()]
    assert ("README.md", (ROOT / "README.md").read_text()) in found
    return [(name, text) for name, text in found if text is not None and name not in exempt]


def cited(text: str) -> list[str]:
    return [number for match in CITATION.finditer(text) for number in re.findall(r"\d{4}", match["numbers"])]


def test_rfc_file_names_are_numbered_and_hyphenated():
    for path in rfcs().values():
        assert FILE_NAME.match(path.name), f"{path.name} is not NNNN-lower-case-words.md"


def test_the_index_lists_every_rfc_with_its_title_and_status():
    rows = {}
    for row in ROW.finditer(INDEX.read_text()):
        assert row["number"] not in rows, f"RFC {row['number']} is listed twice"
        rows[row["number"]] = row
    files = rfcs()

    assert sorted(rows) == sorted(files), "the index and docs/rfcs list different RFCs"
    for number, path in files.items():
        row = rows[number]
        title, status = title_and_status(path)
        assert row["link"] == path.name
        assert row["title"] == title, f"RFC {number}: the index says {row['title']!r}, the RFC {title!r}"
        assert row["status"] in STATUSES, f"RFC {number}: {row['status']!r} is not one of {STATUSES}"
        assert re.match(rf"{row['status']}\b", status), f"RFC {number}: the index says {row['status']}, it {status}"


def test_every_rfc_has_the_sections_the_index_names_in_order():
    listed = re.search(r"^- Sections, in order: (.+)\.$", INDEX.read_text(), re.M)
    assert listed, "the index names no sections"

    for number, path in rfcs().items():
        headings = [line.removeprefix("## ") for _, line in prose(path) if line.startswith("## ")]
        assert headings == listed[1].split(", "), f"RFC {number} has the sections {headings}"


def test_a_citation_names_every_number_of_a_list_across_line_breaks():
    text = "RFCs 0027, 0028, 0035 and 0043; RFC\n  0034; RFC 0001:199; RFCs 0001 to 0059; Platoon RFC 0021"
    text += "; Platoon\nRFC 0005; IETF RFC 2606; Platoon RFCs 0001 and 0021"

    assert cited(text) == ["0027", "0028", "0035", "0043", "0034", "0001", "0001", "0059"]


def test_every_rfc_cited_exists():
    files = rfcs()

    missing = [(name, number) for name, text in texts(NOT_CITING) for number in cited(text) if number not in files]
    assert missing == []


def test_the_old_name_is_gone_but_for_the_sentence_that_tells_it():
    history = re.compile(r"\s+".join(map(re.escape, HISTORY.split())))
    assert history.search(INDEX.read_text()), "docs/rfcs/README.md does not say what the RFCs were called before"

    left = []
    for name, text in texts(NAMING_IT):
        text = PINNED.sub("", text)
        if name == str(INDEX.relative_to(ROOT)):
            text = history.sub("", text, count=1)
        left += [f"{name}: {match[0]}" for match in OLD_NAME.finditer(text)]
    assert left == []
