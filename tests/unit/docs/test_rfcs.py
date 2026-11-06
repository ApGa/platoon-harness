"""The RFCs: the index lists each with the title and status it gives itself and explains every status, each holds the
sections the index names, the template holds every section and row, every RFC the repository cites exists, each of
Platoon's it cites is linked at the commit the research read, and the name they had before is gone but for the sentence
that tells it."""

import re
from pathlib import Path

from .support import ROOT, prose, tracked

RFCS = ROOT / "docs" / "rfcs"
INDEX = RFCS / "README.md"
TEMPLATE = RFCS / "0000-template.md"
STATUSES = ("Draft", "Accepted", "Implemented", "Rejected", "Deferred")
ROWS = ("Status", "Created", "Authors", "Builds on", "Discussion", "Implementation")
WHOLE_TABLE_FROM = 61
"""The first number taken after the template, from which an RFC's status table has every row."""
LISTED = re.compile(r"^\d+\. \*\*(?P<name>.+?)\*\*(?P<optional> \(optional\))?:", re.M)
ROW = re.compile(r"^\| \[(?P<number>\d{4})\]\((?P<link>[^)]+)\) \| (?P<title>.+?) \| (?P<status>[^|]+?) \|$", re.M)
FILE_NAME = re.compile(r"^\d{4}-[a-z0-9]+(?:-[a-z0-9]+)*\.md$")
CITATION = re.compile(
    r"(?<!Platoon\s)(?<!Platoon's\s)(?<!IETF\s)\bRFCs?\s+"
    r"(?P<numbers>\d{4}\b(?:(?:,\s*|,?\s+(?:and|or|to)\s+)\d{4}\b)*)"
)
"""`RFC NNNN`, or `RFCs` and a list or range, across line breaks, but Platoon's own RFCs and the IETF's."""
NOT_CITING = {"docs/spec/BRIEF.md": "verbatim brief; the RFCs it names are Platoon's"}
PLATOON_RFC = re.compile(r"Platoon\s+RFCs?\s+\d{4}")
PLATOON_LINK = re.compile(
    r"\[Platoon RFC (?P<number>\d{4})\]"
    r"\(https://github\.com/ApGa/platoon/blob/efe3b277c82c/docs/rfcs/(?P=number)-[a-z0-9-]+\.md\)"
)
"""A citation of Platoon's RFC, linked to it at the commit the research read Platoon at."""
OLD_NAME = re.compile(r"\badrs?\b|docs/adr", re.IGNORECASE)
PINNED = re.compile(r"platoon-harness@[0-9a-f]{7,40}:docs/adr/")
"""A line-numbered citation in a dated note, read at the commit it names, before the records moved."""
HISTORY = (
    "Until 2026-11-07, RFCs 0001 to 0060 were architecture decision records in `docs/adr`; earlier commits and other "
    "repositories cite them as ADR NNNN, under the same numbers."
)
NAMING_IT = {"tests/unit/docs/test_rfcs.py": "it names what it looks for"}


def rfcs() -> dict[str, Path]:
    """Every RFC by number, the template aside."""
    files = sorted(path for path in RFCS.glob("*.md") if path not in (INDEX, TEMPLATE))
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


def headings(path: Path) -> list[str]:
    return [line.removeprefix("## ") for _, line in prose(path) if line.startswith("## ")]


def status_rows(path: Path) -> list[str]:
    """The rows of the status table under the title, by name."""
    return re.findall(r"^\| (\w[\w ]*?) \| ", path.read_text().partition("\n## ")[0], re.M)


def format_section() -> str:
    index = INDEX.read_text()
    assert "\n## Format\n" in index, "the index has no Format section"
    return index[index.index("\n## Format\n") :]


def sections() -> tuple[list[str], list[str]]:
    """The sections the index's format list names, in order, and those of them it does not call optional."""
    listed = list(LISTED.finditer(format_section()))
    assert listed, "the index's Format section lists no sections"
    return [item["name"] for item in listed], [item["name"] for item in listed if not item["optional"]]


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
    for path in [TEMPLATE, *rfcs().values()]:
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


def test_the_index_explains_every_status():
    text = INDEX.read_text()

    for status in STATUSES:
        assert f"| `{status}` |" in text, f"the lifecycle table does not explain {status}"


def test_every_rfc_has_the_sections_the_index_names_in_order():
    names, required = sections()

    for number, path in rfcs().items():
        found = headings(path)
        assert found == [name for name in names if name in found], f"RFC {number} has the sections {found}"
        assert set(required) <= set(found), f"RFC {number} has no {sorted(set(required) - set(found))}"


def test_the_template_has_every_section_and_row_the_index_names():
    names, _ = sections()
    text = TEMPLATE.read_text()

    assert text.startswith("# RFC NNNN: ")
    assert headings(TEMPLATE) == names, f"the template has the sections {headings(TEMPLATE)}, the index {names}"
    assert re.search(r"^\| Status \| Draft \|$", text, re.M)
    for row in ROWS:
        assert f"`{row}`" in format_section(), f"the index's Format section does not name the {row} row"


def test_the_template_and_every_rfc_numbered_from_0061_have_the_whole_status_table():
    later = [path for number, path in rfcs().items() if int(number) >= WHOLE_TABLE_FROM]

    for path in [TEMPLATE, *later]:
        assert status_rows(path) == list(ROWS), f"{path.name} has the rows {status_rows(path)}"


def test_a_citation_names_every_number_of_a_list_across_line_breaks():
    text = "RFCs 0027, 0028, 0035 and 0043; RFC\n  0034; RFC 0001:199; RFCs 0001 to 0059; Platoon RFC 0021"
    text += "; Platoon\nRFC 0005; IETF RFC 2606; Platoon RFCs 0001 and 0021; Platoon's RFC 0005"

    assert cited(text) == ["0027", "0028", "0035", "0043", "0034", "0001", "0001", "0059"]


def test_every_rfc_cited_exists():
    files = rfcs()

    missing = [(name, number) for name, text in texts(NOT_CITING) for number in cited(text) if number not in files]
    assert missing == []


def test_every_platoon_rfc_cited_is_linked_at_the_commit_the_research_read():
    unlinked = [
        f"{name}: {match[0]}"
        for name, text in texts(NOT_CITING | NAMING_IT)
        for match in PLATOON_RFC.finditer(PLATOON_LINK.sub("", text))
    ]
    assert unlinked == []


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
