"""A session recorded for the docs' images, and made again for a client to draw. A recording is a closed session's
folder, the export, trimmed to what the clients read, its manifest and its journal's events and bodies, kept as text
with every private value a run names in it replaced, and refused if the repository's privacy scan still catches
anything, so that no credential, token, local path or account goes into it. A live run of an example records one where
`PLATOON_HARNESS_RECORD` names, and the terminal UI's snapshots and the page's images draw from the one kept at
`RECORDED`, which no run has recorded yet."""

import hashlib
import json
import re
import sqlite3
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from platoon_harness.kernel import Kernel
from platoon_harness.kernel.journal import SCHEMA_VERSION, open_writer
from platoon_harness.primitives import PRIMITIVES
from platoon_harness.runtime.paths import MANIFEST, sessions_of

from .unit.test_no_internal_references import hits

ROOT = Path(__file__).parents[1]
RECORDED = ROOT / "tests" / "fixtures" / "sessions" / "mixed-team"
"""The mixed team's session, as a live run of it records it, which the docs' images draw."""
IMAGES = ("web-chat.png", "web-provenance.png")
"""The page's images, by the names the docs give them, which only a recorded session draws."""
NAME = "tally"
"""The name a recorded session goes by when it is made again."""
_JOURNAL = "journal.json"
"""When the journal was made, and the schema it is written in, which a recording is made again in only if this kernel's
is the same."""
_EVENTS = "events.jsonl"
_BODIES = "bodies.jsonl"
_JSON_COLUMNS = ("cause", "based_on", "native", "model", "data", "outcome")
_BODY = re.compile(r"sha256:([0-9a-f]{64})")
_LEFT_OUT = ("annotations.sqlite",)
"""What a closed session can hold that a recording does not carry, and so refuses: no example writes annotations."""


def record(folder: Path, into: Path, private: Mapping[str, str]) -> None:
    """Record the closed session in `folder` into `into`, each of `private`'s keys replaced by its value wherever it is,
    the longest first. Its harnesses' own folders, its workspaces, logs and tokens stay behind: a client reads none of
    them. A body that is no text is refused, as is anything the privacy scan or a private value is still found in."""
    if found := [name for name in _LEFT_OUT if (folder / name).exists()]:
        raise ValueError(f"{folder} holds {', '.join(found)}, which a recording does not carry")
    order = sorted(private, key=len, reverse=True)

    def scrubbed(text: str) -> str:
        for value in order:
            text = text.replace(value, private[value])
        return text

    journal = sqlite3.connect(f"{(folder / 'journal.sqlite').as_uri()}?mode=ro", uri=True)
    journal.row_factory = sqlite3.Row
    renamed: dict[str, str] = {}
    bodies = []
    for row in journal.execute("SELECT sha256, data FROM bodies ORDER BY sha256"):
        data = row["data"] if row["data"] is not None else _blob(folder, row["sha256"])
        try:
            text = scrubbed(data.decode())
        except UnicodeDecodeError:
            raise ValueError(f"body {row['sha256']} is no text, which a recording does not carry") from None
        renamed[row["sha256"]] = hashlib.sha256(text.encode()).hexdigest()
        bodies.append({"sha256": renamed[row["sha256"]], "text": text})
    events = []
    for row in journal.execute("SELECT * FROM events ORDER BY seq"):
        event = {
            column: json.loads(value) if column in _JSON_COLUMNS else value
            for column, value in dict(row).items()
            if value is not None
        }
        events.append(_BODY.sub(lambda body: f"sha256:{renamed.get(body[1], body[1])}", scrubbed(json.dumps(event))))
    meta = {row["key"]: row["value"] for row in journal.execute("SELECT * FROM meta WHERE key != 'session_id'")}
    journal.close()
    into.mkdir(parents=True, exist_ok=True)
    (into / _JOURNAL).write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n")
    (into / MANIFEST).write_text(scrubbed((folder / MANIFEST).read_text()))
    (into / _EVENTS).write_text("".join(f"{line}\n" for line in events))
    (into / _BODIES).write_text("".join(f"{json.dumps(body, sort_keys=True)}\n" for body in bodies))
    left = {path.name: _left(path.read_text(), private) for path in sorted(into.iterdir())}
    if any(left.values()):
        raise ValueError(f"the recording still holds what it must not: {left}")


def _blob(folder: Path, sha256: str) -> bytes:
    return (folder / "blobs" / sha256[:2] / sha256).read_bytes()


def _left(text: str, private: Mapping[str, str]) -> list[str]:
    """What the privacy scan catches in a recorded file, and each private value still in it, named by its
    replacement."""
    return [*hits(text), *(f"a private value, {name}" for value, name in private.items() if value in text)]


def restored(recording: Path, root: Path) -> str:
    """A recording made again as a closed session's folder under `root`, its journal written whole as the recording
    holds it and its views folded, for a client to read, and the session's name. One written in another schema than
    this kernel's is refused."""
    meta = json.loads((recording / _JOURNAL).read_text())
    if meta["schema_version"] != str(SCHEMA_VERSION):
        raise ValueError(
            f"{recording} is in journal schema {meta['schema_version']}, and this kernel writes {SCHEMA_VERSION}"
        )
    folder = sessions_of(root) / NAME
    folder.mkdir(mode=0o700, parents=True)
    (folder / MANIFEST).write_text((recording / MANIFEST).read_text())
    journal = open_writer(folder / "journal.sqlite", float(meta["created"]))
    journal.execute("BEGIN IMMEDIATE")
    for line in (recording / _EVENTS).read_text().splitlines():
        event = json.loads(line)
        _insert(
            journal,
            "events",
            {**event, **{column: json.dumps(event[column]) for column in _JSON_COLUMNS if column in event}},
        )
    for line in (recording / _BODIES).read_text().splitlines():
        body = json.loads(line)
        data = body["text"].encode()
        _insert(journal, "bodies", {"sha256": body["sha256"], "size": len(data), "data": data})
    journal.execute("COMMIT")
    journal.close()
    Kernel.open(folder, extensions=PRIMITIVES).close()
    return NAME


def _insert(journal: sqlite3.Connection, table: str, row: dict[str, Any]) -> None:
    columns = ", ".join(row)
    journal.execute(f"INSERT INTO {table} ({columns}) VALUES ({', '.join('?' * len(row))})", tuple(row.values()))


def finish_of(recording: Path, agent: str) -> dict[str, Any]:
    """An agent's `agent.finished` in a recorded session, as the recording holds it, whose `data` holds its report."""
    for line in (recording / _EVENTS).read_text().splitlines():
        event = json.loads(line)
        if (event["type"], event.get("agent")) == ("agent.finished", agent):
            return event
    raise LookupError(f"{agent} never finished in {recording}")
