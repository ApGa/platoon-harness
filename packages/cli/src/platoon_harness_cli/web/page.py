"""SwarmChat's page, as pinned: its five files read from the installed package, each held to its SHA-256, put together
as upstream's server puts them, under a banner with SwarmChat's notice, with our scripts beside its own, and served
under a policy that lets only those scripts run."""

import base64
import hashlib
from importlib import resources
from typing import NamedTuple

PINNED = {
    "index.html": "00f9da6be1f44e73c8a8120f3c0ea46df1f0f9d9b901e546d32681a51d405c8e",
    "app.css": "3dc776935e38c8f32e7fa2383eea8924ed4f114f861b5fb56ec005e91578a3b4",
    "app.js": "20e425ebb49b3cfa2d47e208f97b7dc319638568987bd23d8410021fa3b1a3de",
    "gate.html": "ab77cea699e17bb4157d30b1d834a185b4a690598574e07617acac92f4383cee",
    "gate.js": "83cb82cebcb7aada0fcc610e456b2bccc62b62c293dc92aa5b39453adad12bec",
}
"""SwarmChat 0.1.0's page files, from source commit fb5aa6a05b40, by the SHA-256 of each."""
VERSION = "0.1.0"
BANNER = """/* What follows is SwarmChat 0.1.0's page script, pinned by platoon-harness, which serves it over its own
   backend and puts its own scripts beside it. SwarmChat is under this license:

MIT License

Copyright (c) 2026 The SwarmChat Authors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
*/
"""
"""SwarmChat's notice, which each of its scripts we serve begins with."""


class Unpinned(Exception):
    """The installed page is not the one pinned, so it is not served."""


class Page(NamedTuple):
    """What is served: the gate, which takes a token, the viewer it puts in its own place, with its one script, and the
    policy, which names by hash every script the two may run."""

    gate: bytes
    html: str
    js: str
    policy: str


def edited(name: str, text: str, old: str, new: str) -> str:
    """`text`, the pinned file `name`, with `old` made `new`. `old` must stand in it once, or the page is not served."""
    if (found := text.count(old)) != 1:
        raise Unpinned(f"SwarmChat's {name} holds {old!r} {found} times, where its pinned version holds it once")
    return text.replace(old, new)


def _pinned(name: str) -> str:
    try:
        data = resources.files("swarmchat").joinpath("page", name).read_bytes()
    except (ModuleNotFoundError, OSError) as error:
        raise Unpinned(f"SwarmChat {VERSION}'s {name} cannot be read: {error}") from None
    if (found := hashlib.sha256(data).hexdigest()) != PINNED[name]:
        raise Unpinned(f"SwarmChat's {name} is not the one pinned: its SHA-256 is {found}, not {PINNED[name]}")
    return data.decode()


def _ours(name: str) -> str:
    return resources.files(__package__).joinpath(name).read_text()


def _hash(script: str) -> str:
    return f"'sha256-{base64.b64encode(hashlib.sha256(script.encode()).digest()).decode()}'"


def load() -> Page:
    """The page, or `Unpinned` with the reason when the installed files are not the ones pinned."""
    gate_js = BANNER + _pinned("gate.js")
    js = BANNER + _pinned("app.js") + "\n" + _ours("overlay.js")
    exchange = _ours("exchange.js")
    scripts = f"<script>{exchange}</script><script>{gate_js}</script>"
    gate = edited("gate.html", _pinned("gate.html"), "<!--JS-->", scripts)
    html = edited("index.html", _pinned("index.html"), "<!--CSS-->", f"<style>{_pinned('app.css')}</style>")
    html = edited("index.html", html, "<!--JS-->", "")
    policy = (
        f"default-src 'none'; script-src {_hash(exchange)} {_hash(gate_js)} {_hash(js)}; style-src 'unsafe-inline'; "
        "img-src 'self' data: blob:; connect-src 'self'; worker-src blob:; base-uri 'none'; form-action 'none'; "
        "frame-ancestors 'none'"
    )
    return Page(gate.encode(), html, js, policy)
