"""Guard the three-track docs landing page (phase5-docs task 1).

The index must present exactly three named entry paths (UI / notebook /
concepts), and every docs page must be reachable from exactly one of them.
The full no-warnings check (`sphinx -W`) runs in .harness/verify.sh and the
CI release gate; these tests cover the structure without needing Sphinx.
"""

from __future__ import annotations

import re
from pathlib import Path

DOCS_SOURCE = Path("docs/source")

TOCTREE_RE = re.compile(r"```\{toctree\}\n(.*?)```", re.DOTALL)


def _index_toctrees() -> dict[str, list[str]]:
    """Map each toctree caption in index.md to its page entries."""
    text = (DOCS_SOURCE / "index.md").read_text(encoding="utf-8")
    toctrees: dict[str, list[str]] = {}
    for block in TOCTREE_RE.findall(text):
        caption = ""
        entries: list[str] = []
        for line in block.splitlines():
            line = line.strip()
            if line.startswith(":caption:"):
                caption = line.removeprefix(":caption:").strip().strip('"')
            elif line and not line.startswith(":"):
                entries.append(line)
        toctrees[caption] = entries
    return toctrees


def test_index_has_three_named_tracks() -> None:
    captions = list(_index_toctrees())

    assert len(captions) == 3
    assert any("UI" in caption for caption in captions)
    assert any("Notebook" in caption for caption in captions)
    assert any("Thesis" in caption or "Concept" in caption for caption in captions)


def test_every_page_in_exactly_one_track() -> None:
    toctrees = _index_toctrees()
    listed = [entry for entries in toctrees.values() for entry in entries]
    pages = {path.stem for path in DOCS_SOURCE.glob("*.md")} - {"index"}

    orphans = pages - set(listed)
    assert not orphans, f"docs pages missing from every track: {sorted(orphans)}"

    dangling = set(listed) - pages
    assert not dangling, f"toctree entries without a page: {sorted(dangling)}"

    duplicates = {entry for entry in listed if listed.count(entry) > 1}
    assert not duplicates, f"pages listed in more than one track: {sorted(duplicates)}"
