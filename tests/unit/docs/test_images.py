"""Each image the docs show says under it what drew it: a screenshot of the terminal UI a scripted session or the
mixed team's session as a live run recorded it, as the snapshot it is a copy of was drawn, and an image of the page,
which only that recording draws, only once there is one."""

import re

from ...recorded import IMAGES, RECORDED
from ..tui.test_snapshots import RECORDED_SNAPSHOTS, SCREENSHOTS
from .support import ROOT, tracked

SHOWN = re.compile(r"^!\[[^\]]*\]\([^)]*assets/(?P<image>[\w.-]+)\)\n\n(?P<caption>(?:.+\n?)+)", re.MULTILINE)
"""An image a page shows, and the paragraph under it, its caption."""


def captions() -> list[tuple[str, str, str]]:
    """Each image a page shows, by its name in `docs/assets`, with the page and the caption under it."""
    return [
        (match["image"], str(page.relative_to(ROOT)), " ".join(match["caption"].split()))
        for page in tracked("*.md")
        for match in SHOWN.finditer(page.read_text())
    ]


def test_each_image_the_docs_show_says_under_it_what_drew_it():
    """`scripted` under a screenshot of a scripted session, and `recorded` under an image of the recorded session."""
    recorded = {*IMAGES, *RECORDED_SNAPSHOTS} if RECORDED.exists() else set(IMAGES)
    wrong = [
        (page, image, caption)
        for image, page, caption in captions()
        if ("recorded" if image in recorded else "scripted") not in caption
    ]

    assert {image for image, _, _ in captions()} <= {*SCREENSHOTS, *IMAGES}
    assert wrong == []


def test_an_image_of_the_page_is_shown_only_once_a_live_run_has_recorded_a_session_to_draw_it():
    assert RECORDED.exists() or [image for image, _, _ in captions() if image in IMAGES] == []
