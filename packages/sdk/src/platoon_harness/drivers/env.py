"""The environment of a harness: an allowlist, and redaction of what it had to hold."""

import os
import re
import shutil
import sys
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any, overload

from platoon_harness.config import Secret, forms
from platoon_harness.tools.ph import TOKEN_VARIABLE, URL_VARIABLE

from . import BEARER_VARIABLE, AgentSpec, Gateway, Report

_INHERITED = ("PATH", "HOME")
_STATE = ("CLAUDE_CONFIG_DIR", "CODEX_HOME", "PI_CODING_AGENT_DIR", "PI_CODING_AGENT_SESSION_DIR")
"""Where a harness keeps its state when told to keep it elsewhere than under its home."""
_MASK = b"***"
_CONTINUATION = 0b1000_0000
_CONTINUATION_MASK = 0b1100_0000

PYTHON = tuple(dict.fromkeys(map(Path, (sys.executable, sys.prefix, sys.base_prefix, Path(__file__).parents[2]))))
"""What the runtime's own Python reads to run our modules, as our shim and the OpenHands worker do: the interpreter,
its environment, the installation that is made from, and the folder our package is in."""

__all__ = [
    "PYTHON",
    "Held",
    "Redactor",
    "harness_env",
    "inherited",
    "on_path",
    "open_beneath",
    "private",
    "secrets_of",
    "tmpdir",
]


def inherited(*names: str, environ: Mapping[str, str] = os.environ) -> dict[str, str]:
    """All a process takes from ours: what any process needs, and `names`, what a harness needs to sign in as it does in
    the shell, which is where its login lives and its way out to the network. A variable that would change a harness's
    behavior, or that leaks a parent's identity, has no way through, and provider keys stay in auth profiles."""
    return {name: environ[name] for name in (*_INHERITED, *names) if name in environ}


def harness_env(spec: AgentSpec, *names: str, environ: Mapping[str, str] = os.environ) -> dict[str, str]:
    """The whole environment of one harness process: what it inherits, a `TMPDIR` of its own, and what `spec` names.
    Later entries win: `spec.env` over the inherited, and model access over both, each variable it names or a gateway's
    bearer under `BEARER_VARIABLE`. A `HOME` that `spec.env` names is the harness's home, so none of `names` that would
    keep its state elsewhere is inherited."""
    own = tmpdir(spec.folder)
    own.mkdir(mode=0o700, parents=True, exist_ok=True)
    names = tuple(name for name in names if name not in _STATE) if "HOME" in spec.env else names
    env = {**inherited(*names, environ=environ), "TMPDIR": str(own)}
    if spec.tools is not None:
        env["PATH"] = os.pathsep.join(filter(None, (str(spec.tools.bin), env.get("PATH"))))
        env[URL_VARIABLE] = spec.tools.url
        env[TOKEN_VARIABLE] = spec.tools.token.reveal()
    access = {BEARER_VARIABLE: spec.access.bearer} if isinstance(spec.access, Gateway) else spec.access
    return {**env, **spec.env, **{name: secret.reveal() for name, secret in access.items()}}


def on_path(*programs: str) -> tuple[Path, ...]:
    """Where `PATH` finds each of `programs`, as a harness reaches it, for those it finds."""
    return tuple(Path(found) for program in programs if (found := shutil.which(program)) is not None)


def tmpdir(folder: Path) -> Path:
    """A harness's own `TMPDIR`, which whatever it starts inherits, and so carries the name of its folder."""
    return folder / "tmp"


def open_beneath(folder: Path, path: Path, flags: int, mode: int = 0o600) -> int:
    """Open `path`, which lies at or beneath `folder`, following no symlink below `folder`, and return the descriptor.
    So a confined agent that plants a symlink in its own folder cannot send the runtime's read or write through it to a
    path outside the folder. `folder`'s own path is the runtime's and is opened as it reads, symlinks and all."""
    dir_fd = os.open(folder, os.O_RDONLY | os.O_DIRECTORY)
    try:
        *parts, name = path.relative_to(folder).parts
        for part in parts:
            step = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=dir_fd)
            os.close(dir_fd)
            dir_fd = step
        return os.open(name, flags | os.O_NOFOLLOW, mode, dir_fd=dir_fd)
    finally:
        os.close(dir_fd)


def private(folder: Path, path: Path, text: str) -> str:
    """Write a file under `folder` that nobody else may read, following no symlink an agent could plant below `folder`,
    and return where."""
    fd = open_beneath(folder, path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as file:
        file.write(text)
    return str(path)


def secrets_of(spec: AgentSpec) -> tuple[Secret, ...]:
    """Every credential a spec holds: a gateway's bearer, or each value of its access, and its token."""
    access = (spec.access.bearer,) if isinstance(spec.access, Gateway) else tuple(spec.access.values())
    return (*access, *(() if spec.tools is None else (spec.tools.token,)))


class Redactor:
    """Masks secrets, in their encoded forms too, wherever a harness's words go next. `reach` is one byte short of the
    longest form, so holding that much back keeps a secret from straddling two chunks, and `Held` does."""

    def __init__(self, secrets: Iterable[Secret]) -> None:
        found = {form for secret in secrets if secret.reveal() for form in forms(secret)}
        longest_first = sorted(found, key=len, reverse=True)
        self._pattern = re.compile(b"|".join(map(re.escape, longest_first))) if found else None
        self.reach = max(map(len, found), default=1) - 1

    @overload
    def __call__(self, text: bytes) -> bytes: ...

    @overload
    def __call__(self, text: str) -> str: ...

    def __call__(self, text: bytes | str) -> bytes | str:
        if self._pattern is None:
            return text
        if isinstance(text, str):
            return self._pattern.sub(_MASK, text.encode(errors="surrogatepass")).decode(errors="surrogatepass")
        return self._pattern.sub(_MASK, text)

    def masked(self, report: Report) -> Report:
        """A report with every text in it masked."""
        changes: dict[str, Any] = {}
        for name, value in report:
            if isinstance(value, str) and name != "type":
                changes[name] = self(value)
            elif isinstance(value, tuple):
                changes[name] = tuple(map(self, value))
        return report.model_copy(update=changes)


class Held:
    """One stream through a `Redactor`. What could be the start of a secret waits for the next chunk, and a cut never
    falls inside a character."""

    def __init__(self, redact: Redactor) -> None:
        self._redact = redact
        self._held = b""

    def feed(self, chunk: bytes) -> bytes:
        text = self._redact(self._held + chunk)
        cut = max(len(text) - self._redact.reach, 0)
        while 0 < cut < len(text) and text[cut] & _CONTINUATION_MASK == _CONTINUATION:
            cut -= 1
        self._held = text[cut:]
        return text[:cut]

    def flush(self) -> bytes:
        text, self._held = self._redact(self._held), b""
        return text
