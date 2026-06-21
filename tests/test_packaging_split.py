from __future__ import annotations

from pathlib import Path


def test_root_pyproject_is_backend_distribution() -> None:
    text = Path("pyproject.toml").read_text(encoding="utf-8")

    assert 'name = "onepiece"' in text
    assert 'include = ["onepiece", "onepiece.*"]' in text
    assert 'onepiece-studio = "onepiece_studio.cli:main"' not in text


def test_ui_pyproject_exists_and_depends_on_backend() -> None:
    text = Path("ui/pyproject.toml").read_text(encoding="utf-8")

    assert 'name = "onepiece-studio"' in text
    assert 'onepiece[performance]>=1.0.1,<2.0.0' in text
    assert 'include = ["onepiece_studio*"]' in text
