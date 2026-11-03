"""The environment of a harness: an allowlist, and redaction of what it had to hold."""

import base64
import json
import os
import re
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any, overload
from urllib.parse import quote, quote_plus

from platoon_harness.config import Secret
from platoon_harness.tools.ph import TOKEN_VARIABLE, URL_VARIABLE

from . import AgentSpec, Report

_INHERITED = ("PATH", "HOME")
_MASK = b"***"
_CONTINUATION = 0b1000_0000
_CONTINUATION_MASK = 0b1100_0000

__all__ = ["Held", "Redactor", "harness_env", "inherited", "private", "secrets_of"]


def inherited(*names: str, environ: Mapping[str, str] = os.environ) -> dict[str, str]:
    """All a process takes from ours: what any process needs, and `names`, what a harness needs to sign in as it does in
    the shell, which is where its login lives and its way out to the network. A variable that would change a harness's
    behavior, or that leaks a parent's identity, has no way through, and provider keys stay in auth profiles."""
    return {name: environ[name] for name in (*_INHERITED, *names) if name in environ}


def harness_env(spec: AgentSpec, *names: str, environ: Mapping[str, str] = os.environ) -> dict[str, str]:
    """The whole environment of one harness process: what it inherits, a `TMPDIR` of its own, and what `spec` names.
    Later entries win: `spec.env` over the inherited, and `spec.access` over both."""
    env = {**inherited(*names, environ=environ), "TMPDIR": str(_tmpdir(spec.folder))}
    if spec.tools is not None:
        env["PATH"] = os.pathsep.join(filter(None, (str(spec.tools.bin), env.get("PATH"))))
        env[URL_VARIABLE] = spec.tools.url
        env[TOKEN_VARIABLE] = spec.tools.token.reveal()
    return {**env, **spec.env, **{name: secret.reveal() for name, secret in spec.access.items()}}


def _tmpdir(folder: Path) -> Path:
    path = folder / "tmp"
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    return path


def private(path: Path, text: str) -> str:
    """Write a file nobody else may read, and return where."""
    path.touch(mode=0o600)
    path.chmod(0o600)
    path.write_text(text)
    return str(path)


def secrets_of(spec: AgentSpec) -> tuple[Secret, ...]:
    """Every credential a spec holds."""
    return (*spec.access.values(), *(() if spec.tools is None else (spec.tools.token,)))


def _forms(value: str) -> set[bytes]:
    """A secret as text may carry it: plain, JSON-escaped, URL-quoted, and base64 in either alphabet."""
    raw = value.encode()
    encoded = {base64.b64encode(raw), base64.urlsafe_b64encode(raw)}
    return {
        raw,
        json.dumps(value)[1:-1].encode(),
        quote(value, safe="").encode(),
        quote_plus(value).encode(),
        *encoded,
        *(form.rstrip(b"=") for form in encoded),
    }


class Redactor:
    """Masks secrets, in their encoded forms too, wherever a harness's words go next. `reach` is one byte short of the
    longest form, so holding that much back keeps a secret from straddling two chunks, and `Held` does."""

    def __init__(self, secrets: Iterable[Secret]) -> None:
        forms = {form for secret in secrets if (value := secret.reveal()) for form in _forms(value)}
        longest_first = sorted(forms, key=len, reverse=True)
        self._pattern = re.compile(b"|".join(map(re.escape, longest_first))) if forms else None
        self.reach = max(map(len, forms), default=1) - 1

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
