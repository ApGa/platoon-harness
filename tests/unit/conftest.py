"""What the unit tests share: a folder on `sys.path` to install fake distributions into, as real `dist-info` folders."""

from pathlib import Path

import pytest


class Site:
    """A folder on `sys.path` to install distributions into."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def install(
        self,
        name: str,
        version: str = "1.0.0",
        *,
        entry_points: dict[str, dict[str, str]],
        requires: tuple[str, ...] = (),
    ) -> None:
        info = self.path / f"{name.replace('-', '_')}-{version}.dist-info"
        info.mkdir()
        lines = [
            "Metadata-Version: 2.1",
            f"Name: {name}",
            f"Version: {version}",
            *(f"Requires-Dist: {r}" for r in requires),
        ]
        (info / "METADATA").write_text("\n".join(lines) + "\n")
        sections = [
            f"[{group}]\n" + "".join(f"{k} = {v}\n" for k, v in points.items())
            for group, points in entry_points.items()
        ]
        (info / "entry_points.txt").write_text("\n".join(sections))

    def module(self, name: str, source: str) -> None:
        (self.path / f"{name}.py").write_text(source)


@pytest.fixture
def site(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Site:
    monkeypatch.syspath_prepend(tmp_path)
    return Site(tmp_path)
