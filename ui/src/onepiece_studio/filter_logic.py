"""Pure Filter-page computation helpers.

Everything here is plain pandas/python: notebook commands, option
discovery for the filter widgets, and table shaping for display. Nothing
in this module renders or imports Streamlit, so it stays importable from
scripts and tests on its own. The filter application itself lives in
:func:`onepiece_studio.adapters.apply_controlroom_filters`.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import numpy as np
import pandas as pd

from onepiece.services import filter_any_token, filter_text, record_type_series
from onepiece_studio.adapters import row_keys
from onepiece_studio.materials_columns import column_context, profile_review
from onepiece_studio.workflow_logic import short_value


def run_command(command: str, dataframe: pd.DataFrame) -> pd.DataFrame:
    """Evaluate one of the Filter page's notebook commands."""
    if dataframe.empty:
        return dataframe
    if command == "Show active DataFrame":
        return dataframe
    if command == "Top low-energy candidates":
        energy = first_existing(
            dataframe,
            ["form_G_per_Area", "formation_energy_per_atom", "form_G_per_alloy", "E"],
        )
        if energy:
            return dataframe.sort_values(energy).head(40)
    if command == "Find clean reference rows":
        return filter_text(dataframe, "clean", include=True).head(80)
    if command == "Find adsorption-like rows":
        tokens = ["CO", "CO2", "H2O", "OH", "O2", "H2", "ads"]
        return filter_any_token(dataframe, tokens).head(80)
    if command == "Find quality problems":
        problems = dataframe.iloc[0:0].copy()
        if "fmax" in dataframe.columns and pd.api.types.is_numeric_dtype(dataframe["fmax"]):
            problems = pd.concat([problems, dataframe[dataframe["fmax"] > 0.05]])
        problems = pd.concat([problems, filter_text(dataframe, "crash error fail", include=True)])
        return problems.loc[~problems.index.duplicated(keep="first")].head(80)
    if command == "Phase-diagram candidate table":
        columns = [
            c
            for c in [
                "dataset",
                "source_hdf",
                "source_row",
                "Name",
                "Formula",
                "Ga_percent",
                "Monolayer_alloy",
                "hkl",
                "E",
                "formation_energy_per_atom",
                "form_G_per_Area",
                "form_G_per_alloy",
                "fmax",
            ]
            if c in dataframe.columns
        ]
        return dataframe[columns].head(120)
    if command == "Column focus review":
        return profile_review(dataframe)
    if command == "Column context table":
        return column_context(dataframe)
    return dataframe


def record_type_options(dataframe: pd.DataFrame) -> list[str]:
    return sorted(record_type_series(dataframe).dropna().unique().tolist())


def quality_flag_options(dataframe: pd.DataFrame) -> list[str]:
    if "quality_flag" not in dataframe.columns:
        return []
    return sorted(dataframe["quality_flag"].dropna().astype(str).unique().tolist())


def materials_property_columns(dataframe: pd.DataFrame) -> list[str]:
    preferred = [
        "energy_above_hull",
        "e_above_hull",
        "stability",
        "delta_e",
        "formation_energy_per_atom",
        "form_G_per_Area",
        "form_G_per_alloy",
        "energy_per_atom",
        "E",
        "band_gap",
        "density",
        "volume",
        "Volume",
        "Area",
        "fmax",
        "n_atoms",
        "Ga_percent",
        "Monolayer_alloy",
    ]
    numeric = [column for column in dataframe.columns if pd.api.types.is_numeric_dtype(dataframe[column])]
    ordered = [column for column in preferred if column in numeric]
    ordered.extend([column for column in numeric if column not in ordered])
    return ordered[:40]


def facet_columns(dataframe: pd.DataFrame) -> list[str]:
    preferred = [
        "dataset",
        "source_hdf",
        "hkl",
        "slabsize",
        "layers",
        "cluster",
        "convergence",
        "clean",
        "adsorbate",
        "adsorbate_species",
        "Surface Alloy",
        "M",
        "MO",
    ]
    columns = []
    for column in preferred:
        if column in dataframe.columns and _safe_unique_count(dataframe[column]) <= 80:
            columns.append(column)
    return columns[:10]


def numeric_filter_columns(dataframe: pd.DataFrame) -> list[str]:
    preferred = [
        "E",
        "fmax",
        "formation_energy_per_atom",
        "form_G_per_Area",
        "form_G_per_alloy",
        "Ga_percent",
        "Monolayer_alloy",
        "Area",
        "Ga",
        "Cu",
        "O",
        "H",
        "C",
    ]
    return [
        column
        for column in preferred
        if column in dataframe.columns and pd.api.types.is_numeric_dtype(dataframe[column])
    ]


def name_options(dataframe: pd.DataFrame) -> list[str]:
    rows = []
    keys = row_keys(dataframe)
    for index, row in dataframe.head(500).iterrows():
        name = str(row.get("Name", index))
        dataset = str(row.get("dataset", ""))
        rows.append(f"{keys.loc[index]} | {dataset} | {name}")
    return rows


def status_table(status: Mapping[str, str], dataframe: pd.DataFrame) -> pd.DataFrame:
    if not status:
        return pd.DataFrame()
    rows = []
    key_to_index = {key: index for index, key in row_keys(dataframe).items()}
    for key, state in status.items():
        index = key_to_index.get(key)
        row = dataframe.loc[index] if index is not None else {}
        rows.append(
            {
                "row_key": key,
                "state": state,
                "dataset": row.get("dataset", "") if hasattr(row, "get") else "",
                "Name": row.get("Name", "") if hasattr(row, "get") else "",
            }
        )
    return pd.DataFrame(rows)


def display_command_frame(dataframe: pd.DataFrame) -> pd.DataFrame:
    visible = dataframe.copy()
    priority = [
        "dataset",
        "source_hdf",
        "source_row",
        "Name",
        "Formula",
        "E",
        "fmax",
        "formation_energy_per_atom",
        "form_G_per_Area",
        "form_G_per_alloy",
        "hkl",
        "slabsize",
        "Monolayer_alloy",
        "Ga",
        "Cu",
        "O",
        "Path",
    ]
    ordered = [column for column in priority if column in visible.columns]
    ordered.extend([column for column in visible.columns if column not in ordered])
    visible = visible[ordered]
    for column in visible.columns:
        if visible[column].dtype == "object":
            visible[column] = visible[column].map(short_value)
    return visible


def clamp_float(value: Any, *, minimum: float, maximum: float, fallback: float) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        numeric = float(fallback)
    return min(maximum, max(minimum, numeric))


def finite_values(series: pd.Series) -> pd.Series:
    return series.replace([np.inf, -np.inf], np.nan).dropna()


def first_existing(dataframe: pd.DataFrame, columns: list[str]) -> str | None:
    for column in columns:
        if column in dataframe.columns and pd.api.types.is_numeric_dtype(dataframe[column]):
            return column
    return None


def _safe_unique_count(series: pd.Series) -> int:
    try:
        return int(series.nunique(dropna=True))
    except TypeError:
        return int(series.dropna().map(repr).nunique(dropna=True))
