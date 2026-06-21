from __future__ import annotations

from pathlib import Path

import pandas as pd
from onepiece_studio.adapters import DataFrameSource, HDFSource
from onepiece_studio.demo import empty_source, local_default_source


def test_local_default_source_is_empty_without_configured_hdf(monkeypatch) -> None:
    monkeypatch.delenv("ONEPIECE_STUDIO_DEFAULT_HDF", raising=False)
    monkeypatch.setattr("onepiece_studio.demo.DEFAULT_LOCAL_HDF", None)

    source, config = local_default_source()

    assert isinstance(source, DataFrameSource)
    assert source.name == "empty-session"
    assert list(source.load().columns) == ["Name", "Formula", "Path", "struc", "CONTCAR", "E", "fmax"]
    assert source.load().empty
    assert config.primary_key == "Name"
    assert "struc" in config.structure_columns
    assert "E" in config.metric_columns


def test_local_default_source_uses_explicit_environment_hdf(monkeypatch, tmp_path: Path) -> None:
    hdf_path = tmp_path / "configured.hdf"
    pd.DataFrame({"Name": ["row"], "E": [1.0]}).to_hdf(hdf_path, key="df")
    monkeypatch.setenv("ONEPIECE_STUDIO_DEFAULT_HDF", str(hdf_path))
    monkeypatch.setattr("onepiece_studio.demo.DEFAULT_LOCAL_HDF", str(hdf_path))

    source, config = local_default_source()

    assert isinstance(source, HDFSource)
    assert Path(source.path) == hdf_path
    assert config.primary_key == "Name"


def test_empty_source_returns_clean_dataframe_source() -> None:
    source, config = empty_source()

    assert isinstance(source, DataFrameSource)
    assert source.load().empty
    assert config.title == "OnePiece Studio"
