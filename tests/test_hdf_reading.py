from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from onepiece_studio.adapters import HDFSource

from onepiece.sources.core import read_hdf_path


def _write_hdf(path: Path, key: str = "df") -> pd.DataFrame:
    frame = pd.DataFrame({"Name": ["a", "b"], "E": [1.0, 2.0]})
    frame.to_hdf(path, key=key)
    return frame


def test_read_hdf_path_reads_frame(tmp_path: Path) -> None:
    hdf_path = tmp_path / "data.hdf"
    _write_hdf(hdf_path)

    frame = read_hdf_path(hdf_path, key="df")

    assert list(frame["E"]) == [1.0, 2.0]


def test_read_hdf_path_missing_file_names_the_path(tmp_path: Path) -> None:
    missing = tmp_path / "nope.hdf"

    with pytest.raises(FileNotFoundError, match="nope.hdf"):
        read_hdf_path(missing, key="df")


def test_read_hdf_path_wrong_key_lists_available_keys(tmp_path: Path) -> None:
    hdf_path = tmp_path / "data.hdf"
    _write_hdf(hdf_path, key="results")

    with pytest.raises(RuntimeError, match="Available keys: results"):
        read_hdf_path(hdf_path, key="df")


def test_read_hdf_path_unreadable_file_raises_friendly_error(tmp_path: Path) -> None:
    bogus = tmp_path / "not_really.hdf"
    bogus.write_bytes(b"this is not an HDF file")

    with pytest.raises(RuntimeError, match="Could not load HDF file"):
        read_hdf_path(bogus, key="df")


def test_hdf_source_delegates_to_single_read_path(tmp_path: Path) -> None:
    hdf_path = tmp_path / "data.hdf"
    _write_hdf(hdf_path)

    loaded = HDFSource(path=hdf_path).load()

    assert list(loaded["E"]) == [1.0, 2.0]
    assert loaded.index.name == "Name"


def test_hdf_source_propagates_friendly_key_error(tmp_path: Path) -> None:
    hdf_path = tmp_path / "data.hdf"
    _write_hdf(hdf_path, key="results")

    with pytest.raises(RuntimeError, match="Available keys: results"):
        HDFSource(path=hdf_path, key="df").load()
