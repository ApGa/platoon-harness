"""Nothing the repository holds names the machines it was built on or anyone's account: no site, host, reservation,
resource type, account or group of theirs, no path into a home directory, group storage or a per-user data directory, no
key of a shape Anthropic, OpenAI or GitHub gives out nor an AWS access key id, after an escape too, and no email address
but one under `.invalid`, which IETF RFC 2606 keeps from ever naming an account.

The scan covers every text file git tracks and every new file it does not ignore outside hidden directories, and the
names of all of them. A file is text when its first 8000 bytes hold no NUL byte, as git judges it. A file may hold what
the scan catches only where `ALLOWED` lists that text's digest, with the reason.

Banned words are stored as SHA-256 digests, so that this file does not publish them itself. A digest keeps a word out of
plain text and out of a search, but not secret: a short word is found by trying every word that short. A line has its
camelCase words split (`FooBar` and `FOOBar` read as `foo_bar`, and `FOOs` as `foos`), is lower-cased and is split into
names of letters, digits and underscores. A name matches when a run of its underscore-separated words is banned (a
resource type is two words), or is once cut at its first digit (a numbered host, account or group), either also without
a trailing `s` (a plural). To ban another word, add `hashlib.sha256(word.lower().encode()).hexdigest()`.
"""

import hashlib
import re
import subprocess
from collections.abc import Collection, Iterator
from functools import cache
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2]
BANNED_DIGESTS = frozenset(
    {
        "691c1224a07863335713b1c9f6b5d345529a6519636b7d52428234b0fef76b2e",  # the site
        "092bf25babc151516ee10f1a279ee6ff18c985232ce50922039e6160af87bc20",  # the prefix of its hosts' names
        "09a23692b3d972ae19593ac7d765c589f058f4ed0ad8c76d48b23bafd7d590e1",  # a reservation there
        "ca2bdd5b6d4548191177406fbe92213341a4201b3512f1713716b9d63e7f81cd",  # a resource type there
        "2fdc2e3915489d997e73282db1deae5a35620be49c0e8a89a3dac569868346a2",  # another resource type there
        "9f10f645170216d32bff57fe46f386ad5a3f46e30db179411561bfbbcdb279fe",  # the prefix of its accounts
        "ad99ee823dce531770957d20a75e6a5c052b2f18acfd291aa186eccb9182cbed",  # the prefix of its groups
    }
)
_ESCAPED = r"(?<=\\[nrt])|(?<=%[0-9A-Fa-f]{2})"
"""Just after an escaped newline, return or tab, as in a JSON capture, or a URL escape, as in a query."""
BANNED_PATTERNS = (
    re.compile(r"(?<![\w.~$-])/(?:home|Users)/(?!<)[\w.-]+"),
    re.compile(r"(?<![\w.~$-])/(?:groups|gs)(?=/)"),
    re.compile(r"(?<![\w.-])user_data/(?!<)[\w.-]+"),
    re.compile(r"ANTHROPIC_API_KEY=s[k]-|s[k]-ant-"),
    re.compile(r"(?:(?<![A-Za-z0-9-])|" + _ESCAPED + r")s[k]-(?:proj-|svcacct-|admin-)?[A-Za-z0-9_-]{20,}"),
    re.compile(
        r"(?:(?<![A-Za-z0-9-])|" + _ESCAPED + r")(?:g[h][pousr]_[A-Za-z0-9]{36,}|git[h]ub_pat_[A-Za-z0-9_]{22,})"
    ),
    re.compile(r"(?:(?<![A-Z0-9])|" + _ESCAPED + r")(?:A[K]IA|A[S]IA)[A-Z0-9]{16}(?![A-Z0-9])"),
    re.compile(r"[\w.+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.(?!invalid\b)[A-Za-z]{2,}\b"),
)
"""A path into a home directory, group storage or a per-user data directory, whoever it belongs to, but a URL's path and
a `<placeholder>` for the account; a key, Anthropic's, then OpenAI's, a GitHub token and an AWS access key id, each
after a name's underscore or an escape too, their letters bracketed so that this file does not match itself; and an
email address."""
ALLOWED: dict[tuple[str, str], str] = {
    ("pyproject.toml", "7fccfaca2ed8a3a9110f45f36230e10f0a66acf1eb1051407532bc492279bde8"): (
        "the author's contact, which the distribution publishes"
    )
}
"""(file, the SHA-256 digest of a text the scan catches there) -> why the file may hold that text. A digest, so that
this file does not hold the text either, and another text in its place fails until it is reviewed; the words inside an
allowed text are still scanned. Every entry must still be needed (see the last test). Keep the list short: reword the
file instead wherever its readers lose nothing."""

_NAME = re.compile(r"[a-z0-9_]+")
_CAMEL_CASE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z]{2})")


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


@cache
def _banned(name: str) -> bool:
    """Whether a run of a lower-case name's underscore-separated words is banned, or is once cut at its first digit,
    either also without a trailing `s`."""
    words = [word for word in name.split("_") if word]
    runs = {"_".join(words[start:end]) for start in range(len(words)) for end in range(start + 1, len(words) + 1)}
    candidates = runs | {re.split(r"\d", run, maxsplit=1)[0] for run in runs}
    candidates = (candidates | {candidate.removesuffix("s") for candidate in candidates}) - {""}
    return any(_digest(candidate) in BANNED_DIGESTS for candidate in candidates)


def _found(text: str) -> Iterator[tuple[int, str]]:
    """Each banned word, path, key or email address in `text`, with the number of its line."""
    for number, line in enumerate(text.split("\n"), 1):
        for name in _NAME.findall(_CAMEL_CASE.sub("_", line).lower()):
            if _banned(name):
                yield number, name
        for pattern in BANNED_PATTERNS:
            for match in pattern.finditer(line):
                yield number, match.group(0)


def hits(text: str, allowed: Collection[str] = ()) -> list[str]:
    """`line N: 'match'` for each banned word, path, key or email address in `text`, but those `allowed` by digest."""
    return [f"line {number}: {found!r}" for number, found in _found(text) if _digest(found) not in allowed]


def _git_files(root: Path, *options: str) -> list[Path]:
    listed = subprocess.run(["git", "ls-files", "-z", *options], cwd=root, capture_output=True, check=True, text=True)
    return [Path(name) for name in listed.stdout.split("\0") if name]


def _is_text(path: Path) -> bool:
    with path.open("rb") as file:
        return b"\0" not in file.read(8000)


def scanned(root: Path, *, text_only: bool = True) -> list[Path]:
    """The files git tracks under `root`, and the new ones it does not ignore outside hidden directories (environments,
    caches, an editor's settings), but `.github`; only the text files, unless `text_only` is false."""
    new = _git_files(root, "--others", "--exclude-standard")
    hidden = {path for path in new if any(part.startswith(".") and part != ".github" for part in path.parts[:-1])}
    candidates = set(_git_files(root, "--cached")) | (set(new) - hidden)
    return sorted(path for path in candidates if (root / path).is_file() and (not text_only or _is_text(root / path)))


FILES = scanned(ROOT)


def test_the_scan_covers_every_text_file():
    names = {path.as_posix() for path in FILES}

    assert {"README.md", "AGENTS.md", "CONTRIBUTING.md", "pyproject.toml", "uv.lock"} <= names
    assert {".pre-commit-config.yaml", "docs/README.md", "packages/sdk/src/platoon_harness/version.py"} <= names
    assert "tests/unit/test_no_internal_references.py" in names
    for prefix in ("packages/sdk/src/", "packages/cli/src/", "docs/research/", "examples/", "tests/", ".github/"):
        assert any(name.startswith(prefix) for name in names), prefix


MADE_UP_BANS = ("zorbix", "qnode", "qac", "zq_hx")
"""A site, the prefix of its hosts' names, that of its accounts and a resource type that nothing real is called: the
matcher's tests ban them, so that they need no banned word."""


@pytest.fixture
def made_up_bans(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Ban `MADE_UP_BANS` as well, for one test."""
    digests = {hashlib.sha256(word.encode()).hexdigest() for word in MADE_UP_BANS}
    monkeypatch.setitem(globals(), "BANNED_DIGESTS", BANNED_DIGESTS | digests)
    _banned.cache_clear()
    yield
    _banned.cache_clear()


def test_the_matcher_finds_a_word_a_numbered_host_an_account_and_a_resource_type(made_up_bans):
    site, host, account, resource = MADE_UP_BANS

    assert _banned(site) and _banned(f"{site}s") and not _banned(f"g{site}") and not _banned("platoon")
    assert _banned(f"{host}042") and _banned(f"{host}s") and not _banned(f"{host}x") and not _banned("q1")
    assert _banned(f"{account}12345xy") and not _banned(f"{account}x1")
    assert _banned(resource) and _banned(f"a_{resource}_small") and not _banned("zq") and not _banned("hx_zq")
    assert hits(f"RTYPE={resource.upper()}") == [f"line 1: '{resource}'"]
    assert hits(f"class {site.capitalize()}Bridge:") == [f"line 1: '{site}_bridge'"]
    assert hits(f"class {site.upper()}Bridge:") == [f"line 1: '{site}_bridge'"]
    assert hits(f"two {site.upper()}s and {resource.upper()}s") == [f"line 1: '{site}s'", f"line 1: '{resource}s'"]
    assert hits(f"x\nssh login1.{site}.example") == [f"line 2: '{site}'"]
    assert hits(f"x {site} y", allowed={_digest(site)}) == []
    assert hits(f"x {site}@example.com", allowed={_digest(f"{site}@example.com")}) == [f"line 1: '{site}'"]


HOME, USERS, GROUPS = ("/".join(("", top, "someone", "notes")) for top in ("home", "Users", "groups"))


@pytest.mark.parametrize(
    ("line", "caught"),
    [
        (f"see {HOME}", True),
        (f"see {USERS}", True),
        (f"({GROUPS})", True),
        ("/".join(("", "gs", "team", "cache")), True),
        ("log_path: ./data/" + "/".join(("user_data", "someone")), True),
        ("ANTHROPIC_API_KEY=" + "sk-x", True),
        ("sk-" + "ant-x", True),
        ("write to someone" + "@example.com", True),
        ("write to tester@example.invalid", False),
        ("opencode@ff90ed91607c:packages/protocol/src/groups/event.ts:69", False),
        ("`claude-agent-acp@0.99.1`", False),
        (f"https://example.com{HOME} and ~{HOME}", False),
        ("/".join(("", "home", "<user>", "notes")), False),
    ],
)
def test_the_scan_tells_a_local_path_from_a_path_in_a_repository(line, caught):
    assert bool(hits(line)) == caught


def test_the_scan_catches_openai_github_and_aws_key_shapes():
    """Each key is made here from parts, so that this file holds none, and is caught in each line around it: after a
    name's underscore, an escaped newline as a JSON capture writes one, or a URL escape. Each near miss is a shape the
    repository holds on purpose or one too short to be a key."""
    tail = "a1B2c3D4" * 6
    keys = [
        "s" + "k-" + tail,
        "s" + "k-proj-" + tail,
        "s" + "k-svcacct-" + tail,
        "g" + "hp_" + tail[:36],
        "g" + "hs_" + tail[:36],
        "git" + "hub_pat_" + tail[:22] + "_" + tail,
        "AK" + "IA" + "Q3EXAMPLE7KEYID9",
        "AS" + "IA" + "Q3EXAMPLE7KEYID9",
    ]
    around = ["token = {}\n", '"key:\\n{}"', "Authorization=Bearer%20{}", "OPENAI_KEY_{}"]
    near = ["api_key = " + "s" + "k-hunter2", "task-" + tail, "g" + "hp_" + tail[:20], "AK" + "IA" + "Q3EXAMPLE7KEY"]

    assert [(line, key) for line in around for key in keys if hits(line.format(key)) != [f"line 1: {key!r}"]] == []
    assert [line for line in near if hits(line)] == []


def test_the_scan_finds_a_word_planted_in_a_new_file_and_skips_what_git_ignores(tmp_path, made_up_bans):
    site = MADE_UP_BANS[0]
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / ".gitignore").write_text("ignored.md\n")
    (tmp_path / "tracked.md").write_text(f"see {GROUPS}\n")
    subprocess.run(["git", "add", "tracked.md"], cwd=tmp_path, check=True)
    (tmp_path / "new.md").write_text(f"ssh login1.{site}.example\n")
    (tmp_path / "ignored.md").write_text(f"{site}\n")
    (tmp_path / ".editor").mkdir()
    (tmp_path / ".editor" / "settings.md").write_text(f"{site}\n")

    found = {path.as_posix(): hits((tmp_path / path).read_text()) for path in scanned(tmp_path)}

    assert found == {".gitignore": [], "new.md": [f"line 1: '{site}'"], "tracked.md": ["line 1: '/groups'"]}


@pytest.mark.parametrize("path", FILES, ids=lambda path: path.as_posix())
def test_no_internal_references(path):
    text = (ROOT / path).read_text(encoding="utf-8", errors="replace")
    found = hits(text, {digest for (file, digest) in ALLOWED if file == path.as_posix()})

    assert not found, f"{path} names a site, an account, a local path, a key or an email address:\n" + "\n".join(found)


def test_no_file_name_names_a_site_or_an_account():
    named = {path.as_posix(): hits(path.as_posix()) for path in scanned(ROOT, text_only=False)}

    assert {path: found for path, found in named.items() if found} == {}


def test_every_allowed_text_is_still_needed():
    for (file, digest), reason in ALLOWED.items():
        assert reason.strip(), f"say why {file} may hold the text of digest {digest}"
        found = {_digest(text) for _, text in _found((ROOT / file).read_text(encoding="utf-8", errors="replace"))}
        assert digest in found, f"{file} holds nothing the scan catches of digest {digest}: drop its ALLOWED entry"
