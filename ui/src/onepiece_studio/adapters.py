from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

import pandas as pd

from onepiece.frame_utils import ensure_name_index
from onepiece.services import DatasetQuery, apply_dataset_query
from onepiece.sources.core import read_hdf_path
from onepiece_studio.state import (
    CONTROL_DROP_CONVERGENCE,
    CONTROL_DROP_TEST,
    CONTROL_FMAX_MAX,
    CONTROL_MATERIAL_QUERY,
    CONTROL_NUMERIC,
    CONTROL_ROW_KEY,
    CONTROL_SELECTED_FACETS,
    CONTROL_STATUS,
    CONTROL_TEXT_EXCLUDE,
    CONTROL_TEXT_INCLUDE,
    CONTROL_USE_STATUS,
    CONTROL_VISIBLE_STATES,
)


@runtime_checkable
class DatabaseSource(Protocol):
    """Small protocol every OnePiece Studio data source should satisfy."""

    name: str

    def load(self) -> pd.DataFrame:
        """Return the current table as a DataFrame."""


@dataclass(slots=True)
class DataFrameSource:
    dataframe: pd.DataFrame
    name: str = "database"

    def load(self) -> pd.DataFrame:
        return ensure_name_index(self.dataframe.copy())


@dataclass(slots=True)
class HDFSource:
    path: Path | str
    key: str = "df"
    name: str | None = None
    numpy_pickle_compat: bool = True

    def load(self) -> pd.DataFrame:
        return read_hdf_path(
            Path(self.path),
            key=self.key,
            numpy_pickle_compat=self.numpy_pickle_compat,
        )

    @property
    def display_name(self) -> str:
        return self.name or Path(self.path).name


def load_source_cached(source: DatabaseSource) -> pd.DataFrame:
    """Load a source, caching file-backed reads across Streamlit reruns.

    The cache key includes the file's mtime, so an updated file is reread.
    Falls back to a plain load for in-memory sources and unreadable paths
    (those raise their friendly error inside ``load``).
    """
    path = getattr(source, "path", None)
    if path is None:
        return source.load()
    resolved = Path(path)
    try:
        mtime_ns = resolved.stat().st_mtime_ns
    except OSError:
        return source.load()
    key = str(getattr(source, "key", "df"))
    return _cached_read(str(resolved), key, mtime_ns).copy()


_CACHED_READ_IMPL = None


def _cached_read(path: str, key: str, mtime_ns: int) -> pd.DataFrame:
    global _CACHED_READ_IMPL
    if _CACHED_READ_IMPL is None:
        import streamlit as st

        @st.cache_resource(max_entries=4, show_spinner="Loading dataset...")
        def _read(path: str, key: str, mtime_ns: int) -> pd.DataFrame:
            return read_hdf_path(Path(path), key=key)

        _CACHED_READ_IMPL = _read
    return _CACHED_READ_IMPL(path, key, mtime_ns)


def row_key_from_row(row: pd.Series, fallback: Any) -> str:
    """Stable identity key for one row, matching :func:`row_keys`."""
    if "source_hdf" in row.index and "source_row" in row.index:
        return f"{row['source_hdf']}::{row['source_row']}"
    return str(fallback)


def row_keys(dataframe: pd.DataFrame) -> pd.Series:
    """Stable per-row identity keys shared by filters, statuses, and edits."""
    if {"source_hdf", "source_row"}.issubset(dataframe.columns):
        return dataframe["source_hdf"].astype(str) + "::" + dataframe["source_row"].astype(str)
    return pd.Series(dataframe.index.astype(str), index=dataframe.index)


def ensure_controlroom_state(st: Any, dataframe: pd.DataFrame) -> None:
    """Seed the Filter-page session-state keys with their defaults."""
    st.session_state.setdefault(CONTROL_TEXT_INCLUDE, "")
    st.session_state.setdefault(CONTROL_TEXT_EXCLUDE, "")
    st.session_state.setdefault(CONTROL_USE_STATUS, True)
    st.session_state.setdefault(CONTROL_STATUS, {})
    st.session_state.setdefault(CONTROL_SELECTED_FACETS, {})
    st.session_state.setdefault(CONTROL_NUMERIC, {})
    st.session_state.setdefault(CONTROL_MATERIAL_QUERY, {})
    st.session_state.setdefault(CONTROL_FMAX_MAX, None)
    st.session_state.setdefault(CONTROL_DROP_CONVERGENCE, False)
    st.session_state.setdefault(CONTROL_DROP_TEST, False)
    if CONTROL_ROW_KEY not in st.session_state:
        st.session_state[CONTROL_ROW_KEY] = row_keys(dataframe)


def apply_controlroom_filters(st: Any, dataframe: pd.DataFrame) -> pd.DataFrame:
    """Apply the session's Filter-page selections without rendering anything."""
    ensure_controlroom_state(st, dataframe)
    query = DatasetQuery(
        text_include=st.session_state.get(CONTROL_TEXT_INCLUDE, ""),
        text_exclude=st.session_state.get(CONTROL_TEXT_EXCLUDE, ""),
        drop_convergence=bool(st.session_state.get(CONTROL_DROP_CONVERGENCE, True)),
        drop_test=bool(st.session_state.get(CONTROL_DROP_TEST, True)),
        materials=dict(st.session_state.get(CONTROL_MATERIAL_QUERY, {})),
        selected_facets=dict(st.session_state.get(CONTROL_SELECTED_FACETS, {})),
        fmax_max=st.session_state.get(CONTROL_FMAX_MAX),
        numeric_ranges=dict(st.session_state.get(CONTROL_NUMERIC, {})),
        use_status=bool(st.session_state.get(CONTROL_USE_STATUS, True)),
        visible_states=list(st.session_state.get(CONTROL_VISIBLE_STATES, ["included", "review", "reference"])),
    )
    return apply_dataset_query(
        dataframe,
        query,
        row_key_series=row_keys(dataframe),
        status_map=st.session_state.get(CONTROL_STATUS, {}),
    )


@dataclass(slots=True)
class OnePieceSource:
    """Adapter for OnePiece-like objects without coupling OnePiece Studio to one API."""

    onepiece: Any
    name: str = "onepiece"

    def load(self) -> pd.DataFrame:
        if hasattr(self.onepiece, "to_dataframe"):
            return ensure_name_index(self.onepiece.to_dataframe().copy())
        if hasattr(self.onepiece, "dataframe"):
            return ensure_name_index(self.onepiece.dataframe.copy())
        if hasattr(self.onepiece, "df"):
            return ensure_name_index(self.onepiece.df.copy())
        raise TypeError(
            "OnePieceSource needs an object with to_dataframe(), .dataframe, or .df."
        )


