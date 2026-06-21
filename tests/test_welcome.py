from __future__ import annotations

from pathlib import Path

from onepiece_studio.ui import welcome


def _use_tmp_config(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))


def test_recent_files_round_trip(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_config(monkeypatch, tmp_path)

    welcome.remember_recent_file(tmp_path / "a.hdf", "df")
    welcome.remember_recent_file(tmp_path / "b.hdf", "results")

    entries = welcome.load_recent_files()
    assert [entry["path"] for entry in entries] == [str(tmp_path / "b.hdf"), str(tmp_path / "a.hdf")]
    assert entries[0]["key"] == "results"


def test_remember_recent_file_deduplicates_and_caps(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_config(monkeypatch, tmp_path)

    for index in range(12):
        welcome.remember_recent_file(tmp_path / f"file_{index}.hdf")
    welcome.remember_recent_file(tmp_path / "file_11.hdf")

    entries = welcome.load_recent_files()
    assert len(entries) == welcome.MAX_RECENT_FILES
    assert entries[0]["path"] == str(tmp_path / "file_11.hdf")
    assert len({entry["path"] for entry in entries}) == len(entries)


def test_load_recent_files_survives_corrupt_state(monkeypatch, tmp_path: Path) -> None:
    _use_tmp_config(monkeypatch, tmp_path)
    target = welcome.recent_files_path()
    target.parent.mkdir(parents=True)
    target.write_text("{not json", encoding="utf-8")

    assert welcome.load_recent_files() == []


def test_tutorial_selection_points_at_bundled_dataset() -> None:
    selection = welcome.tutorial_selection()

    assert Path(selection["path"]).exists()
    assert selection["key"] == "df"


def test_source_from_selection_builds_standard_config(tmp_path: Path) -> None:
    selection = {"path": str(tmp_path / "data.hdf"), "key": "df"}

    source, config = welcome.source_from_selection(selection)

    assert source.key == "df"
    assert config.title == "OnePiece Studio: data.hdf"
    assert config.primary_key == "Name"
    assert "struc" in config.structure_columns
