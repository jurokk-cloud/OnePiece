from __future__ import annotations

import operator
import re
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from functools import reduce
from typing import Any

import numpy as np
import pandas as pd

from onepiece._polars import dataframe_is_polars_safe, get_polars
from onepiece.adsorption import formula_counts, row_element_count_map, structure_columns_in_frame


@dataclass(frozen=True, slots=True)
class DatasetQuery:
    text_include: str = ""
    text_exclude: str = ""
    drop_convergence: bool = False
    drop_test: bool = False
    materials: dict[str, Any] | None = None
    selected_facets: dict[str, list[str]] | None = None
    fmax_max: float | None = None
    numeric_ranges: dict[str, tuple[float, float]] | None = None
    use_status: bool = True
    visible_states: list[str] | None = None


def apply_dataset_query(
    dataframe: pd.DataFrame,
    query: DatasetQuery | Mapping[str, Any] | None = None,
    *,
    row_key_series: pd.Series | None = None,
    status_map: Mapping[str, str] | None = None,
) -> pd.DataFrame:
    active = dataframe.copy()
    normalized = _normalize_query(query)

    include_text = normalized.get("text_include", "").strip()
    if include_text:
        active = filter_text(active, include_text, include=True)

    exclude_text = normalized.get("text_exclude", "").strip()
    if exclude_text:
        active = filter_text(active, exclude_text, include=False)

    if normalized.get("drop_convergence", False):
        active = filter_text(active, "convergence", include=False)
    if normalized.get("drop_test", False):
        active = filter_text(active, "test", include=False)

    active = apply_materials_search(active, normalized.get("materials", {}))

    active = _apply_scalar_filters(
        active,
        selected_facets=normalized.get("selected_facets", {}) or {},
        fmax_max=normalized.get("fmax_max"),
        numeric_ranges=normalized.get("numeric_ranges", {}) or {},
    )

    if normalized.get("use_status", True):
        allowed = set(normalized.get("visible_states", ["included", "review", "reference"]))
        if status_map is None:
            status_map = {}
        if row_key_series is not None and active.index.is_unique:
            active_keys = row_key_series.loc[active.index]
        else:
            # With duplicate index labels, .loc would return more rows than
            # active has; rebuild the keys from the surviving rows instead.
            active_keys = _fallback_row_keys(active)
        keep = active_keys.map(lambda key: status_map.get(key, "included") in allowed)
        active = active[keep.to_numpy()]

    return active


def filter_text(dataframe: pd.DataFrame, text: str, *, include: bool) -> pd.DataFrame:
    tokens = [token for token in text.split() if token]
    if not tokens:
        return dataframe
    accelerated = _filter_text_with_polars(dataframe, tokens=tokens, include=include)
    if accelerated is not None:
        return accelerated
    haystack = search_haystack(dataframe)
    mask = pd.Series(True, index=dataframe.index)
    for token in tokens:
        token_mask = haystack.str.contains(token, case=False, na=False, regex=False)
        mask = mask & token_mask if include else mask & ~token_mask
    return dataframe[mask]


def filter_any_token(dataframe: pd.DataFrame, tokens: list[str]) -> pd.DataFrame:
    accelerated = _filter_text_with_polars(dataframe, tokens=tokens, include=True, match_any=True)
    if accelerated is not None:
        return accelerated
    haystack = search_haystack(dataframe)
    mask = pd.Series(False, index=dataframe.index)
    for token in tokens:
        mask = mask | haystack.str.contains(token, case=False, na=False, regex=False)
    return dataframe[mask]


def search_haystack(dataframe: pd.DataFrame) -> pd.Series:
    text_columns = [
        column
        for column in ["dataset", "dataset_label", "Name", "Formula", "legend"]
        if column in dataframe.columns
    ]
    haystack = pd.Series("", index=dataframe.index, dtype="object")
    for column in text_columns:
        haystack = haystack + " " + dataframe[column].astype(str)

    for column in ["Path", "path", "source_hdf"]:
        if column in dataframe.columns:
            haystack = haystack + " " + dataframe[column].astype(str).map(path_tail)

    if not text_columns and all(column not in dataframe.columns for column in ["Path", "path", "source_hdf"]):
        fallback = [column for column in dataframe.columns if dataframe[column].dtype == "object"][:8]
        for column in fallback:
            haystack = haystack + " " + dataframe[column].astype(str)
    return haystack


def path_tail(value: Any) -> str:
    text = str(value or "")
    if not text:
        return ""
    parts = re.split(r"[\\/]", text)
    if not parts:
        return text
    tail = parts[-1]
    parent = parts[-2] if len(parts) > 1 else ""
    return f"{parent} {tail}".strip()


def apply_materials_search(dataframe: pd.DataFrame, query: dict[str, Any]) -> pd.DataFrame:
    if dataframe.empty or not query:
        return dataframe
    active = dataframe.copy()
    elements_by_row = _row_elements(active)

    formula = str(query.get("formula", "")).strip()
    if formula and "Formula" in active.columns:
        active = active[active["Formula"].astype(str).str.contains(formula, case=False, na=False, regex=False)]
        elements_by_row = elements_by_row.loc[active.index]

    anonymous_formula = str(query.get("anonymous_formula", "")).strip()
    if anonymous_formula and "Formula" in active.columns:
        target = _normalize_anonymous_formula(anonymous_formula)
        anon = active["Formula"].map(_anonymous_formula)
        active = active[anon == target]
        elements_by_row = elements_by_row.loc[active.index]

    chemsys = _parse_element_tokens(query.get("chemsys", ""))
    if chemsys:
        mode = query.get("chemsys_mode", "contains all")
        if mode == "exact":
            keep = elements_by_row.map(lambda elements: set(elements) == set(chemsys))
        else:
            keep = elements_by_row.map(lambda elements: set(chemsys).issubset(set(elements)))
        active = active[keep]
        elements_by_row = elements_by_row.loc[active.index]

    include_elements = query.get("include_elements", [])
    if include_elements:
        include_set = set(include_elements)
        mode = query.get("element_mode", "all")
        if mode == "any":
            keep = elements_by_row.map(lambda elements: bool(set(elements) & include_set))
        elif mode == "exact":
            keep = elements_by_row.map(lambda elements: set(elements) == include_set)
        else:
            keep = elements_by_row.map(lambda elements: include_set.issubset(set(elements)))
        active = active[keep]
        elements_by_row = elements_by_row.loc[active.index]

    exclude_elements = query.get("exclude_elements", [])
    if exclude_elements:
        exclude_set = set(exclude_elements)
        keep = elements_by_row.map(lambda elements: not bool(set(elements) & exclude_set))
        active = active[keep]
        elements_by_row = elements_by_row.loc[active.index]

    nelements = query.get("nelements")
    if nelements:
        counts = elements_by_row.map(len)
        if _range_is_restrictive(counts, nelements):
            active = active[counts.between(int(nelements[0]), int(nelements[1]), inclusive="both")]
            elements_by_row = elements_by_row.loc[active.index]

    natoms = query.get("natoms")
    if natoms:
        atom_counts = row_atom_counts(active)
        if _range_is_restrictive(atom_counts, natoms):
            active = active[atom_counts.between(int(natoms[0]), int(natoms[1]), inclusive="both")]
            elements_by_row = elements_by_row.loc[active.index]

    record_types = query.get("record_types", [])
    if record_types:
        record_labels = record_type_series(active)
        active = active[record_labels.isin(record_types)]
        elements_by_row = elements_by_row.loc[active.index]

    quality_flags = query.get("quality_flags", [])
    if quality_flags and "quality_flag" in active.columns:
        active = active[active["quality_flag"].astype(str).isin(quality_flags)]
        elements_by_row = elements_by_row.loc[active.index]

    for column, bounds in query.get("property_ranges", {}).items():
        if column in active.columns and bounds:
            values = pd.to_numeric(active[column], errors="coerce").replace([np.inf, -np.inf], np.nan)
            if _range_is_restrictive(values, bounds):
                active = active[values.between(float(bounds[0]), float(bounds[1]), inclusive="both")]
                elements_by_row = elements_by_row.loc[active.index]

    return active


def _apply_scalar_filters(
    dataframe: pd.DataFrame,
    *,
    selected_facets: dict[str, list[str]],
    fmax_max: float | None,
    numeric_ranges: dict[str, tuple[float, float]],
) -> pd.DataFrame:
    accelerated = _apply_scalar_filters_with_polars(
        dataframe,
        selected_facets=selected_facets,
        fmax_max=fmax_max,
        numeric_ranges=numeric_ranges,
    )
    if accelerated is not None:
        return accelerated

    active = dataframe.copy()
    for column, values in selected_facets.items():
        if column in active.columns and values:
            active = active[active[column].astype(str).isin(values)]

    if "fmax" in active.columns and fmax_max is not None:
        active = active[active["fmax"].replace([np.inf, -np.inf], np.nan).fillna(np.inf) <= float(fmax_max)]

    for column, bounds in numeric_ranges.items():
        if column in active.columns:
            numeric = active[column].replace([np.inf, -np.inf], np.nan)
            active = active[numeric.between(float(bounds[0]), float(bounds[1]), inclusive="both")]
    return active


def _apply_scalar_filters_with_polars(
    dataframe: pd.DataFrame,
    *,
    selected_facets: dict[str, list[str]],
    fmax_max: float | None,
    numeric_ranges: dict[str, tuple[float, float]],
) -> pd.DataFrame | None:
    pl = get_polars()
    if pl is None or dataframe.empty:
        return None

    needed_string_columns = [column for column, values in selected_facets.items() if column in dataframe.columns and values]
    needed_numeric_columns = [
        column for column in ["fmax", *numeric_ranges.keys()]
        if column in dataframe.columns
    ]
    if not dataframe_is_polars_safe(dataframe, needed_numeric_columns):
        return None

    prepared = pd.DataFrame({"__rowid__": np.arange(len(dataframe), dtype=np.int64)}, index=dataframe.index)
    for column in needed_string_columns:
        prepared[column] = dataframe[column].astype("string")
    for column in needed_numeric_columns:
        prepared[column] = pd.to_numeric(dataframe[column], errors="coerce")

    try:
        polars_frame = pl.from_pandas(prepared, include_index=False)
    except Exception:
        return None

    filters: list[Any] = []
    for column, values in selected_facets.items():
        if column in prepared.columns and values:
            filters.append(pl.col(column).cast(pl.String).is_in([str(value) for value in values]))
    if "fmax" in prepared.columns and fmax_max is not None:
        filters.append(pl.col("fmax").fill_null(float("inf")) <= float(fmax_max))
    for column, bounds in numeric_ranges.items():
        if column in prepared.columns:
            filters.append(pl.col(column).is_between(float(bounds[0]), float(bounds[1]), closed="both"))
    if not filters:
        return None

    try:
        rowids = (
            polars_frame
            .filter(reduce(operator.and_, filters))
            .get_column("__rowid__")
            .to_list()
        )
    except Exception:
        return None
    return dataframe.iloc[rowids].copy()


def _filter_text_with_polars(
    dataframe: pd.DataFrame,
    *,
    tokens: list[str],
    include: bool,
    match_any: bool = False,
) -> pd.DataFrame | None:
    pl = get_polars()
    if pl is None or dataframe.empty or not tokens:
        return None

    text_columns = [
        column
        for column in ["dataset", "dataset_label", "Name", "Formula", "legend"]
        if column in dataframe.columns
    ]
    fallback_columns = []
    if not text_columns and all(column not in dataframe.columns for column in ["Path", "path", "source_hdf"]):
        fallback_columns = [
            column
            for column in dataframe.columns
            if dataframe[column].dtype == "object" and dataframe_is_polars_safe(dataframe, [column])
        ][:8]
    active_columns = [*text_columns, *fallback_columns]
    path_columns = [column for column in ["Path", "path", "source_hdf"] if column in dataframe.columns]
    if not active_columns and not path_columns:
        return None

    prepared = pd.DataFrame({"__rowid__": np.arange(len(dataframe), dtype=np.int64)}, index=dataframe.index)
    expr_columns: list[str] = []
    for column in active_columns:
        prepared[column] = dataframe[column].astype("string")
        expr_columns.append(column)
    for column in path_columns:
        derived = f"__tail_{column}"
        prepared[derived] = dataframe[column].astype(str).map(path_tail).astype("string")
        expr_columns.append(derived)

    try:
        polars_frame = pl.from_pandas(prepared, include_index=False)
    except Exception:
        return None

    haystack = pl.concat_str([pl.col(column).fill_null("") for column in expr_columns], separator=" ").str.to_lowercase()
    try:
        token_filters = [haystack.str.contains(re.escape(token.lower())) for token in tokens]
        base_expr = reduce(operator.or_ if match_any else operator.and_, token_filters)
        expr = base_expr if include else ~base_expr
        rowids = polars_frame.filter(expr).get_column("__rowid__").to_list()
    except Exception:
        return None
    return dataframe.iloc[rowids].copy()


def query_description(query: dict[str, Any]) -> str:
    parts = []
    if query.get("formula"):
        parts.append(f"formula contains {query['formula']}")
    if query.get("anonymous_formula"):
        parts.append(f"anonymous_formula = {_normalize_anonymous_formula(query['anonymous_formula'])}")
    if query.get("chemsys"):
        parts.append(f"chemsys {query.get('chemsys_mode', 'contains all')} {query['chemsys']}")
    if query.get("include_elements"):
        parts.append(f"elements {query.get('element_mode', 'all')} {','.join(query['include_elements'])}")
    if query.get("exclude_elements"):
        parts.append(f"exclude {','.join(query['exclude_elements'])}")
    if query.get("nelements"):
        parts.append(f"nelements={query['nelements'][0]}..{query['nelements'][1]}")
    if query.get("natoms"):
        parts.append(f"natoms={query['natoms'][0]}..{query['natoms'][1]}")
    if query.get("record_types"):
        parts.append(f"record_type in {','.join(query['record_types'])}")
    for column, bounds in query.get("property_ranges", {}).items():
        parts.append(f"{column}={bounds[0]:.4g}..{bounds[1]:.4g}")
    return "LOCAL MATERIALS QUERY: " + (" AND ".join(parts) if parts else "all rows")


def _normalize_query(query: DatasetQuery | Mapping[str, Any] | None) -> dict[str, Any]:
    if query is None:
        return {}
    if isinstance(query, DatasetQuery):
        return asdict(query)
    return dict(query)


def _fallback_row_keys(dataframe: pd.DataFrame) -> pd.Series:
    if {"source_hdf", "source_row"}.issubset(dataframe.columns):
        return dataframe["source_hdf"].astype(str) + "::" + dataframe["source_row"].astype(str)
    return dataframe.index.map(str).to_series(index=dataframe.index)


def _row_elements(dataframe: pd.DataFrame) -> pd.Series:
    structure_columns = tuple(structure_columns_in_frame(dataframe))
    return dataframe.apply(
        lambda row: tuple(sorted(row_element_count_map(row, structure_columns=structure_columns))),
        axis=1,
    )


def row_element_counts(dataframe: pd.DataFrame) -> pd.Series:
    """Return the number of distinct elements inferred for each row."""
    return _row_elements(dataframe).map(len)


def row_atom_counts(dataframe: pd.DataFrame) -> pd.Series:
    """Return atom counts per row, from ``n_atoms`` or the row structures."""
    if "n_atoms" in dataframe.columns:
        return pd.to_numeric(dataframe["n_atoms"], errors="coerce")
    structure_columns = tuple(structure_columns_in_frame(dataframe))
    counts_by_row = dataframe.apply(
        lambda row: row_element_count_map(row, structure_columns=structure_columns),
        axis=1,
    )
    if not counts_by_row.empty:
        return counts_by_row.map(lambda counts: float(sum(counts.values())) if counts else np.nan)
    return pd.Series(np.nan, index=dataframe.index)


def _anonymous_formula(value: Any) -> str:
    counts = formula_counts(value)
    if not counts:
        return ""
    ordered_counts = sorted(counts.values())
    letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    parts = []
    for index, count in enumerate(ordered_counts):
        suffix = "" if count == 1 else str(count)
        parts.append(f"{letters[index]}{suffix}")
    return "".join(parts)


def _normalize_anonymous_formula(value: str) -> str:
    counts = []
    for _element, number in re.findall(r"([A-Z])(\d*)", str(value).upper()):
        counts.append(int(number or 1))
    letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    return "".join(f"{letters[index]}{'' if count == 1 else count}" for index, count in enumerate(sorted(counts)))


def _parse_element_tokens(value: Any) -> list[str]:
    text = str(value).replace("-", " ").replace(",", " ")
    return [token for token in text.split() if _looks_like_element(token)]


def _looks_like_element(value: Any) -> bool:
    return bool(re.fullmatch(r"[A-Z][a-z]?", str(value)))


def record_type_series(dataframe: pd.DataFrame) -> pd.Series:
    """Classify each row as gas reference, clean surface, adsorbate, etc."""
    text = pd.Series("", index=dataframe.index)
    for column in ["Name", "Path", "dataset", "dataset_label"]:
        if column in dataframe.columns:
            text = text + " " + dataframe[column].astype(str)
    lower = text.str.lower()
    labels = pd.Series("calculation", index=dataframe.index)
    labels[lower.str.contains("gasphase|gas/", regex=True, na=False)] = "gas_reference"
    labels[lower.str.contains("clean", regex=False, na=False)] = "clean_surface"
    labels[lower.str.contains("co|ch3o|hco|co2|oh", regex=True, na=False)] = "adsorbate"
    labels[lower.str.contains("copt", regex=False, na=False)] = "constrained_optimization"
    if "record_type" in dataframe.columns:
        explicit = dataframe["record_type"].astype("string").str.strip()
        has_explicit = explicit.notna() & ~explicit.str.lower().isin(["", "nan", "none", "nat"])
        labels.loc[has_explicit] = explicit.loc[has_explicit].astype(str)
    return labels


def _range_is_restrictive(values: pd.Series, bounds: Any) -> bool:
    if not bounds:
        return False
    finite = _finite(pd.to_numeric(values, errors="coerce"))
    if finite.empty:
        return False
    lower, upper = float(bounds[0]), float(bounds[1])
    return lower > float(finite.min()) or upper < float(finite.max())


def _finite(series: pd.Series) -> pd.Series:
    return series.replace([np.inf, -np.inf], np.nan).dropna()
